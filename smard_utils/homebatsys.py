"""
HomeBatSys - Home storage autarky analysis.

Simulates a household battery charged from excess solar and discharged to
cover demand, using a fixed electricity tariff.  No spot-price data needed.

Usage:
    homebatsys --data 2024-home-smardformat.csv --fix-price 0.28
    homebatsys --data data.csv --fix-price 0.30 --feed-in 0.08
    homebatsys --data data.csv --capacity 5 10 20 --power 3.5 7 10

Output metrics
--------------
cap [kWh]   Battery capacity.
grid [kWh]  Annual grid imports (residual demand after solar + battery).
savings [€] (grid_no_bat - grid_with_bat) * fix_price
            + (export_with_bat - export_no_bat) * feed_in_price
autarky [%] 1 - grid_import / total_demand
selfcons[%] 1 - exported_solar / total_solar
€/kWh       Savings per kWh of battery capacity (investment indicator).
cycles      Equivalent full discharge cycles per year.
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from smard_utils.core.battery import Battery
from smard_utils.core.bms import BatteryManagementSystem
from smard_utils.drivers.home_driver import HomeDriver
from smard_utils.bms_strategies.autarky import AutoarkyStrategy


euro_sign = "\N{euro sign}"


# ---------------------------------------------------------------------------
# Main application class
# ---------------------------------------------------------------------------

class HomeBatSys:
    """Home storage system – autarky optimisation with fixed electricity price."""

    def __init__(self, csv_file_path: str, basic_data_set: dict = None):
        """
        Initialise home battery analysis system.

        Args:
            csv_file_path: Path to SMARD-format household CSV
            basic_data_set: Configuration dictionary
        """
        self.basic_data_set = (basic_data_set or {}).copy()

        self.driver = HomeDriver(self.basic_data_set)
        self.driver.load_data(csv_file_path)

        self.data = self.driver.data
        self.resolution = self.driver.resolution
        self.strategy = AutoarkyStrategy(self.basic_data_set)
        self.results_df = None

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def _run_one(self, capacity_kwh: float, power_kw: float) -> dict:
        """Run a single battery simulation and return summary metrics."""
        battery = Battery(self.basic_data_set, capacity_kwh, power_kw)
        bms = BatteryManagementSystem(self.strategy, battery, self.driver)
        bms.initialize()

        fix_price = self.basic_data_set.get('fix_price', 0.28)

        step_results = []
        for i in range(len(self.driver)):
            step_results.append(bms.step(i, fix_price, fix_price))

        df = pd.DataFrame(step_results)

        total_grid_import = df['residual_kwh'].sum()
        total_export = df['export_kwh'].sum()
        total_discharge = df['net_discharge'].sum()

        total_solar = self.data['my_renew'].sum()
        total_demand = self.data['my_demand'].sum()

        autarky = 1.0 - total_grid_import / max(total_demand, 1e-10)
        selfcons = 1.0 - total_export / max(total_solar, 1e-10)
        equiv_cycles = total_discharge / max(capacity_kwh, 1e-10)

        return {
            'capacity_kwh': capacity_kwh,
            'power_kw': power_kw,
            'grid_import_kwh': total_grid_import,
            'export_kwh': total_export,
            'autarky': autarky,
            'selfcons': selfcons,
            'equiv_cycles': equiv_cycles,
        }

    # ------------------------------------------------------------------
    # Analysis loop
    # ------------------------------------------------------------------

    def run_analysis(self, capacity_list=None, power_list=None):
        """
        Run battery analysis for multiple capacities.

        Args:
            capacity_list: Battery capacities in kWh (default: 5 10 15 20)
            power_list:    Battery powers in kW     (default: 3.5 7 8.5 10)
        """
        if capacity_list is None:
            capacity_list = [5, 10, 15, 20]
        if power_list is None:
            power_list = [3.5, 7.0, 8.5, 10.0]

        print("\nStarting home battery autarky analysis...")

        full_cap = [0.0] + list(capacity_list)
        full_pwr = [0.0] + list(power_list)

        n = len(full_cap)
        max_workers = min(n, os.cpu_count() or 1)
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(self._run_one, full_cap, full_pwr))

        # Store results for webapp / programmatic access
        _fix = self.basic_data_set.get('fix_price', 0.28)
        _fin = self.basic_data_set.get('feed_in_price', 0.0)
        _g0 = results[0]['grid_import_kwh']
        _e0 = results[0]['export_kwh']
        for r in results:
            r['savings_eur'] = (_g0 - r['grid_import_kwh']) * _fix + (r['export_kwh'] - _e0) * _fin
        self.results_df = pd.DataFrame(results)
        self._print_results(results)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _print_results(self, results: list):
        fix_price = self.basic_data_set.get('fix_price', 0.28)
        feed_in_price = self.basic_data_set.get('feed_in_price', 0.0)

        # Baseline (no battery, index 0)
        base = results[0]
        grid_no_bat = base['grid_import_kwh']
        export_no_bat = base['export_kwh']

        total_solar = self.data['my_renew'].sum()
        total_demand = self.data['my_demand'].sum()

        print(f"\n{'='*72}")
        print(f"Home Battery Autarky Analysis")
        print(f"  Fix price : {fix_price:.3f} {euro_sign}/kWh")
        if feed_in_price > 0:
            print(f"  Feed-in   : {feed_in_price:.3f} {euro_sign}/kWh")
        print(f"  Solar     : {total_solar:.0f} kWh/year")
        print(f"  Demand    : {total_demand:.0f} kWh/year")
        print(f"{'='*72}")

        cols = [
            "cap [kWh]",
            "grid [kWh]",
            f"savings [{euro_sign}]",
            "autarky [%]",
            "selfcons[%]",
            f"{euro_sign}/kWh",
            "cycles",
        ]

        rows = []
        for i, r in enumerate(results):
            cap = r['capacity_kwh']
            grid = r['grid_import_kwh']

            # Net savings: avoided grid cost minus lost feed-in revenue
            savings = (
                (grid_no_bat - grid) * fix_price
                + (r['export_kwh'] - export_no_bat) * feed_in_price
            )

            if i == 0:
                cap_str = "0 (no bat)"
                savings_str = "0"
                eur_per_kwh_str = "-"
                cycles_str = "-"
            else:
                cap_str = f"{cap:.0f}"
                savings_str = f"{savings:.0f}"
                eur_per_kwh_str = f"{savings / max(cap, 1e-10):.1f}"
                cycles_str = f"{r['equiv_cycles']:.0f}"

            rows.append([
                cap_str,
                f"{grid:.0f}",
                savings_str,
                f"{r['autarky'] * 100:.1f}",
                f"{r['selfcons'] * 100:.1f}",
                eur_per_kwh_str,
                cycles_str,
            ])

        df_out = pd.DataFrame(rows, columns=cols)
        with pd.option_context('display.max_columns', None):
            print(df_out.to_string(index=False))
        print(f"{'='*72}")
        print(f"  {euro_sign}/kWh = annual savings per kWh of battery capacity")


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

basic_data_set = {
    "fix_price": 0.28,        # €/kWh grid electricity (all-in incl. taxes)
    "feed_in_price": 0.0,     # €/kWh feed-in tariff (0 = no payment)
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    """Main function."""
    from smard_utils.utils.cli import apply_config

    parser = argparse.ArgumentParser(
        prog="homebatsys",
        description=(
            "Home storage autarky analysis – fixed electricity price.\n"
            "Input: SMARD-format CSV (e.g. from senec2smardformat)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  homebatsys --data 2024-home.csv
  homebatsys --data 2024-home.csv --fix-price 0.32 --feed-in 0.08
  homebatsys --data 2024-home.csv --capacity 5 10 20 --power 3.5 7 10
""",
    )

    parser.add_argument(
        "-d", "--data",
        required=True,
        metavar="FILE",
        help="Path to SMARD-format household CSV",
    )
    parser.add_argument(
        "--fix-price",
        type=float,
        default=None,
        metavar="EUR_KWH",
        help="Grid electricity price in €/kWh, all-in (default: 0.28)",
    )
    parser.add_argument(
        "--feed-in",
        type=float,
        default=None,
        metavar="EUR_KWH",
        help="Feed-in tariff in €/kWh (default: 0 = no payment)",
    )
    parser.add_argument(
        "--capacity",
        nargs="+",
        type=float,
        default=None,
        metavar="KWH",
        help="Battery capacity list in kWh (default: 5 10 15 20)",
    )
    parser.add_argument(
        "--power",
        nargs="+",
        type=float,
        default=None,
        metavar="KW",
        help="Battery power list in kW (default: 3.5 7 8.5 10)",
    )
    parser.add_argument(
        "-s", "--strategy",
        choices=["autarky"],
        default="autarky",
        help="BMS strategy (only 'autarky' is supported for home storage)",
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        metavar="FILE",
        help="Path to JSON config file (auto-detect basic_data_set.conf in cwd)",
    )

    args = parser.parse_args(argv)

    apply_config(basic_data_set, args)

    # CLI args override config
    if args.fix_price is not None:
        basic_data_set["fix_price"] = args.fix_price
    if args.feed_in is not None:
        basic_data_set["feed_in_price"] = args.feed_in

    # Capacity / power lists
    capacity_list = args.capacity   # kWh, None → use defaults
    power_list = args.power         # kW,  None → use defaults

    if (capacity_list is None) != (power_list is None):
        parser.error("--capacity and --power must be given together")

    if capacity_list is not None and len(capacity_list) != len(power_list):
        parser.error(
            f"--capacity ({len(capacity_list)} values) and "
            f"--power ({len(power_list)} values) must have the same length"
        )

    if not os.path.exists(args.data):
        print(f"Data file not found: {args.data}")
        return

    analyzer = HomeBatSys(args.data, basic_data_set=basic_data_set)
    analyzer.run_analysis(
        capacity_list=capacity_list,
        power_list=power_list,
    )


if __name__ == "__main__":
    main()

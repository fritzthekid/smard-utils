"""
BioBatSys - Biogas battery system analysis (Refactored).

Uses new modular architecture with backward-compatible interface.
"""

import os
import logging
import types

import pandas as pd
import numpy as np

from smard_utils.core.battery import Battery
from smard_utils.core.bms import BatteryManagementSystem
from smard_utils.core.analytics import BatteryAnalytics
from smard_utils.drivers.biogas_driver import BiogasDriver
from smard_utils.bms_strategies.registry import get_strategy
from smard_utils.core.base_sys import BaseAnalysisSys

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

euro_sign = "\N{euro sign}"
root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/.."


class BioBatSys(BaseAnalysisSys):
    """Biogas battery system with spot-price trading strategy."""

    def __init__(self, csv_file_path, region="", basic_data_set={},
                 driver=None, strategy=None):
        """
        Initialize biogas analysis system.

        Args:
            csv_file_path: Path to SMARD CSV data file
            region: Region code (e.g., "_de" for Germany)
            basic_data_set: Configuration dictionary
            driver: Optional EnergyDriver override (D3 — injectable)
            strategy: Optional BMSStrategy override (D2 — injectable)
        """
        self.region = region
        self.basic_data_set = basic_data_set.copy()

        # Initialize driver (injectable for testing, D3)
        self.driver = driver or BiogasDriver(basic_data_set)
        self.driver.load_data(csv_file_path)

        # Initialize analytics
        self.analytics = BatteryAnalytics(self.driver, basic_data_set)
        self.analytics.prepare_prices()

        # Initialize strategy via registry (injectable for testing, D2)
        strategy_name = basic_data_set.get("strategy", "price_threshold")
        self.strategy = strategy or get_strategy(strategy_name, basic_data_set)

        # Storage for results
        self.battery_results = None
        self.exporting_l = []
        self.fcr_revenues_l = []
        self.resolution = self.driver.resolution
        self.data = self.driver.data

    def _run_one(self, capacity_mwh: float, power_mw: float) -> dict:
        """
        Run a single battery simulation and return raw per-timestep results.

        If fcr_capacity_kw is set in config, that portion of the battery power is
        reserved for FCR (Frequency Containment Reserve / Regelleistung) and is not
        available for spot-market arbitrage:

            arbitrage_power_kw = power_kw - fcr_kw

        FCR revenue is calculated separately in run_analysis() as:
            fcr_kw * fcr_price_eur_per_kw_year

        Args:
            capacity_mwh: Battery capacity in MWh
            power_mw:     Battery charge/discharge power in MW

        Returns:
            Dict with keys:
                capacity_mwh  - Echo of input capacity
                power_mw      - Echo of input power
                power_kw      - power_mw converted to kW
                fcr_kw        - Power reserved for FCR (capped at power_kw)
                step_results  - List of per-timestep dicts from bms.step()
                export_flags  - Boolean array, True where energy was exported
        """
        power_kw = power_mw * 1000
        fcr_capacity_kw = self.basic_data_set.get("fcr_capacity_kw", 0)
        fcr_kw = min(fcr_capacity_kw, power_kw)
        arbitrage_power_kw = power_kw - fcr_kw

        battery = Battery(self.basic_data_set, capacity_mwh * 1000, arbitrage_power_kw)
        bms = BatteryManagementSystem(self.strategy, battery, self.driver)
        bms.initialize()

        step_results = []
        for i in range(len(self.driver)):
            price = self.driver.data['price_per_kwh'].iloc[i]
            avg_price = self.driver.data['avrgprice'].iloc[i]
            step_results.append(bms.step(i, price, avg_price))

        return {
            'capacity_mwh': capacity_mwh,
            'power_mw': power_mw,
            'power_kw': power_kw,
            'fcr_kw': fcr_kw,
            'step_results': step_results,
            'export_flags': bms.export_flags.copy(),
        }

    def run_analysis(self, capacity_list=[1.0, 5, 10, 20, 100],
                     power_list=[0.5, 2.5, 5, 10, 50]):
        """
        Run battery analysis for multiple capacities (parallel across cores).

        Args:
            capacity_list: List of battery capacities (MWh)
            power_list: List of battery powers (MW)
        """
        print("\nStarting biogas battery analysis...")

        fcr_price = self.basic_data_set.get("fcr_price_eur_per_kw_year", 0)

        full_capacity_list = [0.0] + list(capacity_list)
        full_power_list = [0.0] + list(power_list)

        n = len(full_capacity_list)
        max_workers = min(n, os.cpu_count() or 1)
        with self._make_executor(max_workers) as executor:
            run_outputs = list(executor.map(self._run_one, full_capacity_list, full_power_list))

        for output in run_outputs:
            proxy = types.SimpleNamespace(export_flags=output['export_flags'])
            self.analytics.add_simulation_result(
                output['capacity_mwh'] * 1000, output['power_kw'], proxy, output['step_results']
            )
            self.exporting_l.append((
                np.size(output['export_flags']) - np.count_nonzero(output['export_flags']),
                output['export_flags'].sum()
            ))
            self.fcr_revenues_l.append(output['fcr_kw'] * fcr_price)

        self.battery_results = self.analytics.get_results_dataframe()
        self._convert_to_legacy_format()
        self.print_battery_results()

    def _convert_to_legacy_format(self):
        """
        Convert new results format to legacy format expected by print_battery_results.

        Legacy format:
        - Row 0: "no rule" marker baseline (capacity = -1)
        - Row 1+: Actual simulations (including 0.0 MWh no-battery)
        """
        df = self.battery_results

        # Row 0: "no rule" baseline — all biogas exported at spot price,
        # no battery, no flex constraints. Matches solbatsys "always" concept.
        no_rule_exflow = self.data["my_renew"].sum()
        no_rule_revenue = (self.data["my_renew"] * self.data["price_per_kwh"]).sum()
        marker_baseline = {
            'capacity kWh': -1.0,
            'residual kWh': 0.0,
            'exflow kWh': no_rule_exflow,
            'autarky rate': 1.0,
            'spot price [€]': 0.0,
            'fix price [€]': 0.0,
            'revenue [€]': no_rule_revenue
        }

        # Start with marker baseline, then add actual simulation results
        # (including the 0.0 MWh no-battery simulation which is now in df)
        legacy_df = pd.DataFrame([marker_baseline])

        for _, row in df.iterrows():
            result_row = {
                'capacity kWh': row['capacity_kwh'],
                'residual kWh': row['residual_kwh'],
                'exflow kWh': row['export_kwh'],
                'autarky rate': row['autarky_rate'],
                'spot price [€]': row['spot_cost_eur'],
                'fix price [€]': row['fix_cost_eur'],
                'revenue [€]': row['revenue_eur']
            }
            legacy_df = pd.concat([legacy_df, pd.DataFrame([result_row])], ignore_index=True)

        self.battery_results = legacy_df

    def print_battery_results(self):
        """
        Print biogas-specific results with flex premium.

        Flex premium is only applied when export hours exceed min_flex_hours
        (default: 4380h = half a year), reflecting EEG flex requirements.
        """
        flex_add_full = (self.basic_data_set.get("constant_biogas_kw", 0) *
                        self.basic_data_set.get("flex_add_per_kwh", 0))
        min_flex_hours = self.basic_data_set.get("min_flex_hours", 4380)

        # Compute export hours per simulation
        export_hours = [e[1] * self.resolution for e in self.exporting_l]

        # Flex premium per simulation: only if export hours < threshold
        # (flexible operation = NOT running at full capacity all the time)
        # exporting_l[0] corresponds to 0.0 MWh (no battery), [1] to first capacity, etc.
        flex_per_sim = []
        for eh in export_hours:
            flex_per_sim.append(flex_add_full if eh < min_flex_hours else 0)

        rev1 = self.battery_results["revenue [€]"].iloc[1] if len(self.battery_results) > 1 else 0

        # FCR revenues per simulation (aligned with exporting_l: [0.0MWh, cap1, cap2, ...])
        # fcr_revenues_l[0] = 0.0 MWh (always 0), [1:] = actual battery sizes
        fcr_per_sim = self.fcr_revenues_l if self.fcr_revenues_l else [0.0] * len(self.exporting_l)
        show_fcr = any(r > 0 for r in fcr_per_sim)

        # Auto-scale based on data magnitude
        if abs(self.data["my_renew"].sum()) / 1000 > 1000:
            scaler = 1000
            cols = ["cap MWh", "exfl MWh", "export [h]", "rev [T€]", "revadd [T€]", "rev €/kWh", "cycles"]
            if show_fcr:
                cols.append("fcr [T€]")
        else:
            scaler = 1
            cols = ["cap kWh", "exfl kWh", "export [h]", "rev [€]", "revadd [€]", "rev €/kWh", "cycles"]
            if show_fcr:
                cols.append("fcr [€]")

        # Print export statistics
        if len(self.exporting_l) > 1:
            print(f"exporting {export_hours[1]:.0f} hours but not {self.exporting_l[1][0] * self.resolution:.0f} hours"
                  f" (flex premium applies if export < {min_flex_hours} h)")
        if show_fcr:
            fcr_kw = self.basic_data_set.get("fcr_capacity_kw", 0)
            fcr_price = self.basic_data_set.get("fcr_price_eur_per_kw_year", 0)
            print(f"FCR: {fcr_kw:.0f} kW reserved @ {fcr_price:.0f} €/kW/year")

        # Format results (matches original: skip marker row 0, start from row 1)
        capacity_l = ["no rule"] + [f"{(c / scaler)}" for c in self.battery_results["capacity kWh"][2:]]

        exflowl = (
            [f"{(self.battery_results['exflow kWh'].iloc[0] / scaler):.1f}"] +
            [f"{(e / scaler):.1f}" for e in self.battery_results["exflow kWh"][2:]]
        )

        # Row 1 (0.0 MWh) gets no flex premium, rows 2+ get conditional flex premium
        # flex_per_sim[0] = 0.0 MWh baseline, flex_per_sim[1] = first capacity, etc.
        # Row 0 = 'no rule': actual theoretical max (all biogas exported unoptimised)
        no_rule_rev = self.battery_results['revenue [€]'].iloc[0]
        revenue_l = [f"{(no_rule_rev / scaler):.1f}"] + [
            f"{((rev + flex) / scaler):.1f}"
            for rev, flex in zip(self.battery_results["revenue [€]"][2:], flex_per_sim[1:])
        ]

        revenue_gain = ["nn"] + [
            f"{((rev - rev1 + flex + fcr) / scaler):.2f}"
            for rev, flex, fcr in zip(
                self.battery_results["revenue [€]"][2:], flex_per_sim[1:], fcr_per_sim[1:]
            )
        ]

        capacity_costs = [f"{0:.2f}"] + [
            f"{((rev - rev1 + flex + fcr) / max(1e-10, c)):.2f}"
            for rev, c, flex, fcr in zip(
                self.battery_results["revenue [€]"][2:],
                self.battery_results["capacity kWh"][2:],
                flex_per_sim[1:],
                fcr_per_sim[1:]
            )
        ]

        # Export hours per simulation
        no_rule_hours = int(len(self.data) * self.resolution)
        expo_l = [f"{no_rule_hours}"] + [f"{int(eh)}" for eh in export_hours[1:]]

        # Equivalent full cycles: "-" for no_rule, then from analytics (skip 0.0 MWh baseline row)
        analytics_df = self.analytics.get_results_dataframe()
        cycles_l = ["-"] + [f"{c:.0f}" for c in analytics_df['equivalent_cycles'][1:]]

        arrays = [capacity_l, exflowl, expo_l, revenue_l, revenue_gain, capacity_costs, cycles_l]
        if show_fcr:
            fcr_l = ["nn"] + [f"{(r / scaler):.1f}" for r in fcr_per_sim[1:]]
            arrays.append(fcr_l)

        values = np.array(arrays).T

        battery_results_norm = pd.DataFrame(values, columns=cols)

        with pd.option_context('display.max_columns', None):
            print(battery_results_norm)


# Default configuration
basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 11,
    "hourly_demand_kw": -100000,
    "solar_max_power": 0,
    "wind_nominal_power": 0,
    "constant_biogas_kw": 1000,
    "fix_contract": False,
    "marketing_costs": -0.003,
    "flex_add_per_kwh": 100,
    "flex_factor": 3,
    "load_threshold_hytheresis": 0.0,
    "load_threshold": 1.0,
    "control_exflow": 0,
    "fcr_capacity_kw": 0,
    "fcr_price_eur_per_kw_year": 0,
}


def main(argv=None):
    """Main function."""
    from smard_utils.utils.cli import create_parser, resolve_data_path
    from smard_utils.utils.cli import apply_config, resolve_capacity_power

    parser = create_parser(
        prog="biobatsys",
        description="Biogas battery system analysis with spot-price trading",
        default_strategy="price_threshold",
    )
    parser.add_argument("--biogas", type=float, default=None, metavar="KW",
                        help="Biogas nominal power in kW (default: 1000)")
    parser.add_argument("--fcr-kw", type=float, default=None, metavar="KW",
                        help="FCR capacity reserved for Regelleistung in kW (default: 0)")
    parser.add_argument("--fcr-price", type=float, default=None, metavar="EUR_PER_KW_YEAR",
                        help="FCR capacity price in EUR/kW/year (default: 0)")
    args = parser.parse_args(argv)

    apply_config(basic_data_set, args)

    region = f"_{args.region}"
    data_file = resolve_data_path(args)

    if args.year:
        basic_data_set["year"] = args.year

    basic_data_set["strategy"] = args.strategy
    if args.biogas is not None:
        basic_data_set["constant_biogas_kw"] = args.biogas
    if args.fcr_kw is not None:
        basic_data_set["fcr_capacity_kw"] = args.fcr_kw
    if args.fcr_price is not None:
        basic_data_set["fcr_price_eur_per_kw_year"] = args.fcr_price

    if not os.path.exists(data_file):
        print(f"Data file not found: {data_file}")
        return

    analyzer = BioBatSys(data_file, region, basic_data_set=basic_data_set)

    capacity_list, power_list = resolve_capacity_power(
        args, [1.0, 5, 10, 20, 100], [0.5, 2.5, 5, 10, 50]
    )
    analyzer.run_analysis(capacity_list=capacity_list, power_list=power_list)


if __name__ == "__main__":
    main()

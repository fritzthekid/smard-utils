"""
SolBatSys - Solar battery system analysis (Refactored).

Uses new modular architecture with backward-compatible interface.
"""

import logging
import os
import types

import numpy as np
import pandas as pd

from smard_utils.bms_strategies.registry import get_strategy
from smard_utils.core.analytics import BatteryAnalytics
from smard_utils.core.base_sys import BaseAnalysisSys
from smard_utils.core.battery import Battery
from smard_utils.core.bms import BatteryManagementSystem
from smard_utils.drivers.solar_driver import SolarDriver

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

euro_sign = "\N{EURO SIGN}"
root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/.."


class SolBatSys(BaseAnalysisSys):
    """Solar battery system with dynamic discharge optimization."""

    def __init__(
        self, csv_file_path, region="", basic_data_set={}, driver=None, strategy=None
    ):
        """
        Initialize solar analysis system.

        Args:
            csv_file_path: Path to SMARD CSV data file
            region: Region code (e.g., "_de" for Germany)
            basic_data_set: Configuration dictionary
        """
        self.region = region
        self.basic_data_set = basic_data_set.copy()

        # Initialize driver (injectable for testing, D3)
        self.driver = driver or SolarDriver(basic_data_set, region=region)
        self.driver.load_data(csv_file_path)

        # Initialize analytics
        self.analytics = BatteryAnalytics(self.driver, basic_data_set)
        self.analytics.prepare_prices()

        # Initialize strategy via registry (injectable for testing, D2)
        strategy_name = basic_data_set.get("strategy", "dynamic_discharge")
        self.strategy = strategy or get_strategy(strategy_name, basic_data_set)

        # Storage for results
        self.battery_results = None
        self.exporting_l = []
        self.resolution = self.driver.resolution
        self.data = self.driver.data

    def _run_one(self, capacity_mwh: float, power_mw: float) -> dict:
        """Run a single battery simulation and return raw results."""
        battery = Battery(self.basic_data_set, capacity_mwh * 1000, power_mw * 1000)
        bms = BatteryManagementSystem(self.strategy, battery, self.driver)
        bms.initialize()

        step_results = []
        for i in range(len(self.driver)):
            price = self.driver.data["price_per_kwh"].iloc[i]
            avg_price = self.driver.data["avrgprice"].iloc[i]
            step_results.append(bms.step(i, price, avg_price))

        return {
            "capacity_mwh": capacity_mwh,
            "power_mw": power_mw,
            "step_results": step_results,
            "export_flags": bms.export_flags.copy(),
        }

    def run_analysis(
        self,
        capacity_list=[1.0, 5, 10, 20, 50, 70],
        power_list=[0.5, 2.5, 5, 10, 25, 35],
    ):
        """
        Run battery analysis for multiple capacities (parallel across cores).

        Args:
            capacity_list: List of battery capacities (MWh)
            power_list: List of battery powers (MW)
        """
        print("\nStarting solar battery analysis...")

        full_capacity_list = [0.0] + list(capacity_list)
        full_power_list = [0.0] + list(power_list)

        n = len(full_capacity_list)
        max_workers = min(n, os.cpu_count() or 1)
        with self._make_executor(max_workers) as executor:
            run_outputs = list(
                executor.map(self._run_one, full_capacity_list, full_power_list)
            )

        for output in run_outputs:
            proxy = types.SimpleNamespace(export_flags=output["export_flags"])
            self.analytics.add_simulation_result(
                output["capacity_mwh"] * 1000,
                output["power_mw"] * 1000,
                proxy,
                output["step_results"],
            )
            self.exporting_l.append(
                (
                    np.size(output["export_flags"])
                    - np.count_nonzero(output["export_flags"]),
                    output["export_flags"].sum(),
                )
            )

        self.battery_results = self.analytics.get_results_dataframe()
        self._convert_to_legacy_format()
        self.print_battery_results()

    def _convert_to_legacy_format(self):
        """Convert new results format to legacy solar format."""
        df = self.battery_results

        # Create "always export" baseline (theoretical maximum)
        baseline_always = {
            "capacity kWh": -1.0,  # Special marker
            "exflow kWh": self.data["my_renew"].sum(),
            "revenue [€]": (self.data["my_renew"] * self.data["price_per_kwh"]).sum(),
        }

        # Start with "always" baseline, then add actual simulation results
        # (including the 0.0 MWh no-battery simulation which is now in df)
        legacy_df = pd.DataFrame([baseline_always])

        for _, row in df.iterrows():
            legacy_row = {
                "capacity kWh": row["capacity_kwh"],
                "exflow kWh": row["export_kwh"],
                "revenue [€]": row["revenue_eur"],
            }
            legacy_df = pd.concat(
                [legacy_df, pd.DataFrame([legacy_row])], ignore_index=True
            )

        self.battery_results = legacy_df

    def print_battery_results(self):
        """
        Print solar-specific results.

        Matches original solbatsys.py output format.
        """
        rev0 = (self.data["price_per_kwh"] * self.data["my_renew"]).sum()
        exf0 = self.data["my_renew"].sum()
        texp0 = len(self.data["my_renew"]) * self.resolution
        # Row 1 is the no-battery (0.0 MWh) baseline in our implementation
        rev1 = (
            self.battery_results["revenue [€]"].iloc[1]
            if len(self.battery_results) > 1
            else 0
        )

        # Auto-scale
        if abs(self.data["my_renew"].sum()) / 1000 > 1000:
            scaler = 1000
            cols = [
                "cap MWh",
                "exfl MWh",
                "export [h]",
                "rev [T€]",
                "revadd [T€]",
                "rev €/kWh",
                "cycles",
            ]
        else:
            scaler = 1
            cols = [
                "cap kWh",
                "exfl kWh",
                "export [h]",
                "rev [€]",
                "revadd [€]",
                "rev €/kWh",
                "cycles",
            ]

        # Format results (include row 1 which is the no-battery baseline)
        capacity_l = ["always"] + [
            f"{(c / scaler)}" for c in self.battery_results["capacity kWh"][1:]
        ]

        exflowl = [f"{(exf0 / scaler):.1f}"] + [
            f"{(e / scaler):.1f}" for e in self.battery_results["exflow kWh"][1:]
        ]

        revenue_l = [f"{(rev0 / scaler):.1f}"] + [
            f"{(f / scaler):.1f}" for f in self.battery_results["revenue [€]"][1:]
        ]

        revenue_gain = [f"{((rev0 - rev1) / scaler):.2f}"] + [
            f"{((r - rev1) / scaler):.2f}"
            for r in self.battery_results["revenue [€]"][1:]
        ]

        capacity_costs = (
            [f"{0:.2f}"]
            + [f"{0:.2f}"]
            + [
                f"{((r - rev1) / max(1e-10, c)):.2f}"
                for r, c in zip(
                    self.battery_results["revenue [€]"][2:],
                    self.battery_results["capacity kWh"][2:],
                )
            ]
        )

        # expo_l: "always" baseline + actual simulation export times (including 0.0 MWh)
        expo_l = [f"{int(texp0)}"] + [
            f"{int(e[1] * self.resolution)}" for e in self.exporting_l
        ]

        # Equivalent full cycles: "-" for always baseline, then from analytics
        analytics_df = self.analytics.get_results_dataframe()
        cycles_l = ["-"] + [f"{c:.0f}" for c in analytics_df["equivalent_cycles"]]

        values = np.array(
            [
                capacity_l,
                exflowl,
                expo_l,
                revenue_l,
                revenue_gain,
                capacity_costs,
                cycles_l,
            ]
        ).T

        battery_results_norm = pd.DataFrame(values, columns=cols)

        with pd.option_context("display.max_columns", None):
            print(battery_results_norm)


# Default configuration
basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 11,
    "hourly_demand_kw": -100000,
    "year_demand": -100000,
    "solar_max_power": 10000,
    "wind_nominal_power": 0,
    "constant_biogas_kw": 0,
    "fix_contract": False,
    "marketing_costs": -0.003,
}


def main(argv=None):
    """Main function."""
    from smard_utils.utils.cli import (
        apply_config,
        create_parser,
        resolve_capacity_power,
        resolve_data_path,
    )

    parser = create_parser(
        prog="solbatsys",
        description="Solar battery system analysis with dynamic discharge",
        default_strategy="dynamic_discharge",
    )
    parser.add_argument(
        "--solar",
        type=float,
        default=None,
        metavar="KWP",
        help="Solar peak power in kWp (default: 10000)",
    )
    args = parser.parse_args(argv)

    apply_config(basic_data_set, args)

    region = f"_{args.region}"
    data_file = resolve_data_path(args)

    if args.year:
        basic_data_set["year"] = args.year

    basic_data_set["strategy"] = args.strategy
    if args.solar is not None:
        basic_data_set["solar_max_power"] = args.solar

    if not os.path.exists(data_file):
        print(f"Data file not found: {data_file}")
        return

    analyzer = SolBatSys(data_file, region, basic_data_set=basic_data_set)

    capacity_list, power_list = resolve_capacity_power(
        args, [1.0, 5, 10, 20, 50, 70], [0.5, 2.5, 5, 10, 25, 35]
    )
    analyzer.run_analysis(capacity_list=capacity_list, power_list=power_list)


if __name__ == "__main__":
    main()

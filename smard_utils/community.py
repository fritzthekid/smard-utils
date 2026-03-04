"""
SmardAnalyseSys - Community energy analysis (Refactored).

Uses new modular architecture with backward-compatible interface.
Analyzes a small community with solar + wind + demand.
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
from smard_utils.drivers.community_driver import CommunityDriver

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

euro_sign = "\N{EURO SIGN}"
root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/.."


class SmardAnalyseSys(BaseAnalysisSys):
    """Community energy system with solar + wind + demand analysis."""

    def __init__(
        self, csv_file_path, region="_lu", basic_data_set={}, driver=None, strategy=None
    ):
        """
        Initialize community analysis system.

        Args:
            csv_file_path: Path to SMARD CSV data file
            region: Region code ("_lu" for Luxembourg, "_de" for Germany)
            basic_data_set: Configuration dictionary
        """
        self.region = region
        self.basic_data_set = basic_data_set.copy()

        # Initialize driver (injectable for testing, D3)
        self.driver = driver or CommunityDriver(basic_data_set, region=region)
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
        self, capacity_list=[0.1, 1.0, 5, 10, 20], power_list=[0.05, 0.5, 2.5, 5, 10]
    ):
        """
        Run battery analysis for multiple capacities (parallel across cores).

        Args:
            capacity_list: List of battery capacities (MWh)
            power_list: List of battery powers (MW)
        """
        print("\nStarting community energy analysis...")

        if len(capacity_list) != len(power_list):
            raise ValueError("capacity_list and power_list must have the same length")

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
        self.print_results()
        self.print_battery_results()

    def print_results(self):
        """Print summary of community energy data."""
        print(
            f"reference region: {self.region}, "
            f"demand: {(self.data['total_demand'].sum() / 1000):.2f} GWh, "
            f"solar: {(self.data['solar'].sum() / 1000):.2f} GWh, "
            f"wind {(self.data['wind_onshore'].sum() / 1000):.2f} GWh"
        )
        print(
            f"total demand: {(self.data['my_demand'].sum() / 1e3):.2f} MWh "
            f"total Renewable_Source: {(self.data['my_renew'].sum() / 1e3):.2f} MWh"
        )

    def _convert_to_legacy_format(self):
        """Convert new results format to legacy community format."""
        df = self.battery_results

        # Row 0: "no renew" baseline (all demand at market price)
        total_demand = self.data["my_demand"].sum()
        spot_price_no = (self.data["my_demand"] * self.data["price_per_kwh"]).sum()
        fix_price_no = total_demand * self.analytics.costs_per_kwh

        no_renew = {
            "capacity kWh": -1.0,
            "residual kWh": total_demand,
            "exflow kWh": 0.0,
            "autarky rate": 0.0,
            f"spot price [{euro_sign}]": spot_price_no,
            f"fix price [{euro_sign}]": fix_price_no,
            f"revenue [{euro_sign}]": 0.0,
        }

        legacy_df = pd.DataFrame([no_renew])

        for _, row in df.iterrows():
            result_row = {
                "capacity kWh": row["capacity_kwh"],
                "residual kWh": row["residual_kwh"],
                "exflow kWh": row["export_kwh"],
                "autarky rate": row["autarky_rate"],
                f"spot price [{euro_sign}]": row["spot_cost_eur"],
                f"fix price [{euro_sign}]": row["fix_cost_eur"],
                f"revenue [{euro_sign}]": row["revenue_eur"],
            }
            legacy_df = pd.concat(
                [legacy_df, pd.DataFrame([result_row])], ignore_index=True
            )

        self.battery_results = legacy_df

    def print_battery_results(self):
        """Print community-specific results with spot/fix price analysis."""
        sp0 = self.battery_results[f"spot price [{euro_sign}]"].iloc[1]
        fp0 = self.battery_results[f"fix price [{euro_sign}]"].iloc[1]

        # 2 zeros for "no renew" (row 0) and "no bat" (row 1), gains from row 2+
        spotprice_gain = [f"{0:.2f}", f"{0:.2f}"] + [
            f"{((sp0 - s) / max(1e-10, c)):.2f}"
            for s, c in zip(
                self.battery_results[f"spot price [{euro_sign}]"][2:],
                self.battery_results["capacity kWh"][2:],
            )
        ]
        fixprice_gain = [f"{0:.2f}", f"{0:.2f}"] + [
            f"{((fp0 - f) / max(1e-10, c)):.2f}"
            for f, c in zip(
                self.battery_results[f"fix price [{euro_sign}]"][2:],
                self.battery_results["capacity kWh"][2:],
            )
        ]

        # Auto-scale
        if max(self.data["my_renew"].sum(), self.data["my_demand"].sum()) / 1000 > 1000:
            scaler = 1000
            cols = [
                "cap MWh",
                "resi MWh",
                "exfl MWh",
                "autarky",
                f"spp [T{euro_sign}]",
                f"fixp [T{euro_sign}]",
                f"sp {euro_sign}/kWh",
                f"fp {euro_sign}/kWh",
                "cycles",
            ]
        else:
            scaler = 1
            cols = [
                "cap kWh",
                "resi kWh",
                "exfl kWh",
                "autarky",
                f"spp [{euro_sign}]",
                f"fixp [{euro_sign}]",
                f"sp {euro_sign}/kWh",
                f"fp {euro_sign}/kWh",
                "cycles",
            ]

        capacity_l = ["no renew", "no bat"] + [
            f"{(c / scaler)}" for c in self.battery_results["capacity kWh"][2:]
        ]
        residual_l = [
            f"{(r / scaler):.1f}" for r in self.battery_results["residual kWh"]
        ]
        exflowl = [f"{(e / scaler):.1f}" for e in self.battery_results["exflow kWh"]]
        autarky_rate_l = [f"{a:.2f}" for a in self.battery_results["autarky rate"]]
        spot_price_l = [
            f"{(s / scaler):.1f}"
            for s in self.battery_results[f"spot price [{euro_sign}]"]
        ]
        fix_price_l = [
            f"{(f / scaler):.1f}"
            for f in self.battery_results[f"fix price [{euro_sign}]"]
        ]

        # Equivalent full cycles: "-" for no_renew, "0" for no_bat, then from analytics
        analytics_df = self.analytics.get_results_dataframe()
        cycles_l = ["-", "0"] + [
            f"{c:.0f}" for c in analytics_df["equivalent_cycles"][1:]
        ]

        values = np.array(
            [
                capacity_l,
                residual_l,
                exflowl,
                autarky_rate_l,
                spot_price_l,
                fix_price_l,
                spotprice_gain,
                fixprice_gain,
                cycles_l,
            ]
        ).T

        battery_results_norm = pd.DataFrame(values, columns=cols)

        with pd.option_context("display.max_columns", None):
            print(battery_results_norm)


# Default configuration for community scenario
basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 11,
    "year_demand": 2804 * 1000 * 6,
    "solar_max_power": 5000,
    "wind_nominal_power": 5000,
    "fix_contract": False,
    "marketing_costs": 0.003,
    "battery_discharge": 0.0005,
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
        prog="community",
        description="Community energy analysis (solar + wind + demand)",
        default_strategy="dynamic_discharge",
        default_region="lu",
        extra_strategies=["autarky"],
    )
    parser.add_argument(
        "--solar",
        type=float,
        default=None,
        metavar="KWP",
        help="Solar peak power in kWp (default: 5000)",
    )
    parser.add_argument(
        "--wind",
        type=float,
        default=None,
        metavar="KW",
        help="Wind nominal power in kW (default: 5000)",
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
    if args.wind is not None:
        basic_data_set["wind_nominal_power"] = args.wind

    if not os.path.exists(data_file):
        print(f"Data file not found: {data_file}")
        return

    analyzer = SmardAnalyseSys(data_file, region, basic_data_set=basic_data_set)

    capacity_list, power_list = resolve_capacity_power(
        args, [0.1, 1.0, 5, 10, 20], [0.05, 0.5, 2.5, 5, 10]
    )
    analyzer.run_analysis(capacity_list=capacity_list, power_list=power_list)


if __name__ == "__main__":
    main()

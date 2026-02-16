"""
SolBatSys - Solar battery system analysis (Refactored).

Uses new modular architecture with backward-compatible interface.
"""

import pandas as pd
import numpy as np
import os
import sys
import logging

from smard_utils.core.battery import Battery
from smard_utils.core.bms import BatteryManagementSystem
from smard_utils.core.analytics import BatteryAnalytics
from smard_utils.drivers.solar_driver import SolarDriver
from smard_utils.bms_strategies.dynamic_discharge import DynamicDischargeStrategy
from smard_utils.bms_strategies.day_ahead import DayAheadStrategy

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

euro_sign = "\N{euro sign}"
root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/.."


class SolBatSys:
    """Solar battery system with dynamic discharge optimization."""

    def __init__(self, csv_file_path, region="", basic_data_set={}):
        """
        Initialize solar analysis system.

        Args:
            csv_file_path: Path to SMARD CSV data file
            region: Region code (e.g., "_de" for Germany)
            basic_data_set: Configuration dictionary
        """
        self.region = region
        self.basic_data_set = basic_data_set.copy()

        # Initialize driver
        self.driver = SolarDriver(basic_data_set, region=region)
        self.driver.load_data(csv_file_path)

        # Initialize analytics
        self.analytics = BatteryAnalytics(self.driver, basic_data_set)
        self.analytics.prepare_prices()

        # Initialize strategy (default: DynamicDischarge with saturation curves)
        strategy_name = basic_data_set.get("strategy", "dynamic_discharge")
        if strategy_name == "day_ahead":
            self.strategy = DayAheadStrategy(basic_data_set)
        else:
            self.strategy = DynamicDischargeStrategy(basic_data_set)

        # Storage for results
        self.battery_results = None
        self.exporting_l = []
        self.resolution = self.driver.resolution
        self.data = self.driver.data

    def run_analysis(self, capacity_list=[1.0, 5, 10, 20, 50, 70],
                     power_list=[0.5, 2.5, 5, 10, 25, 35]):
        """
        Run battery analysis for multiple capacities.

        Args:
            capacity_list: List of battery capacities (MWh)
            power_list: List of battery powers (MW)
        """
        print("\nStarting solar battery analysis...")

        # Run simulations (including 0.0 MWh for no-battery baseline)
        full_capacity_list = [0.0] + list(capacity_list)
        full_power_list = [0.0] + list(power_list)

        for capacity, power in zip(full_capacity_list, full_power_list):
            battery = Battery(self.basic_data_set, capacity * 1000, power * 1000)
            bms = BatteryManagementSystem(self.strategy, battery, self.driver)
            bms.initialize()

            # Simulation loop
            results = []
            for i in range(len(self.driver)):
                price = self.driver.data['price_per_kwh'].iloc[i]
                avg_price = self.driver.data['avrgprice'].iloc[i]
                step_result = bms.step(i, price, avg_price)
                results.append(step_result)

            # Record results
            self.analytics.add_simulation_result(
                capacity * 1000, power * 1000, bms, results
            )

            # Track export flags
            self.exporting_l.append((
                np.size(bms.export_flags) - np.count_nonzero(bms.export_flags),
                bms.export_flags.sum()
            ))

        # Get results
        self.battery_results = self.analytics.get_results_dataframe()

        # Convert to legacy format
        self._convert_to_legacy_format()

        # Print custom solar results
        self.print_battery_results()

    def _convert_to_legacy_format(self):
        """Convert new results format to legacy solar format."""
        df = self.battery_results

        # Create "always export" baseline (theoretical maximum)
        baseline_always = {
            'capacity kWh': -1.0,  # Special marker
            'exflow kWh': self.data['my_renew'].sum(),
            'revenue [€]': (self.data['my_renew'] * self.data['price_per_kwh']).sum()
        }

        # Start with "always" baseline, then add actual simulation results
        # (including the 0.0 MWh no-battery simulation which is now in df)
        legacy_df = pd.DataFrame([baseline_always])

        for _, row in df.iterrows():
            legacy_row = {
                'capacity kWh': row['capacity_kwh'],
                'exflow kWh': row['export_kwh'],
                'revenue [€]': row['revenue_eur']
            }
            legacy_df = pd.concat([legacy_df, pd.DataFrame([legacy_row])], ignore_index=True)

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
        rev1 = self.battery_results["revenue [€]"].iloc[1] if len(self.battery_results) > 1 else 0

        # Auto-scale
        if abs(self.data["my_renew"].sum()) / 1000 > 1000:
            scaler = 1000
            cols = ["cap MWh", "exfl MWh", "export [h]", "rev [T€]", "revadd [T€]", "rev €/kWh"]
        else:
            scaler = 1
            cols = ["cap kWh", "exfl kWh", "export [h]", "rev [€]", "revadd [€]", "rev €/kWh"]

        # Format results (include row 1 which is the no-battery baseline)
        capacity_l = ["always"] + [f"{(c / scaler)}" for c in self.battery_results["capacity kWh"][1:]]

        exflowl = [f"{(exf0 / scaler):.1f}"] + [
            f"{(e / scaler):.1f}" for e in self.battery_results["exflow kWh"][1:]
        ]

        revenue_l = [f"{(rev0 / scaler):.1f}"] + [
            f"{(f / scaler):.1f}" for f in self.battery_results["revenue [€]"][1:]
        ]

        revenue_gain = [f"{((rev0 - rev1) / scaler):.2f}"] + [
            f"{((r - rev1) / scaler):.2f}" for r in self.battery_results["revenue [€]"][1:]
        ]

        capacity_costs = [f"{0:.2f}"] + [f"{0:.2f}"] + [
            f"{((r - rev1) / max(1e-10, c)):.2f}"
            for r, c in zip(self.battery_results["revenue [€]"][2:], self.battery_results["capacity kWh"][2:])
        ]

        # expo_l: "always" baseline + actual simulation export times (including 0.0 MWh)
        expo_l = [f"{int(texp0)}"] + [f"{int(e[1] * self.resolution)}" for e in self.exporting_l]

        values = np.array([capacity_l, exflowl, expo_l, revenue_l, revenue_gain, capacity_costs]).T

        battery_results_norm = pd.DataFrame(values, columns=cols)

        with pd.option_context('display.max_columns', None):
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
    from smard_utils.utils.cli import create_parser, resolve_data_path

    parser = create_parser(
        prog="solbatsys",
        description="Solar battery system analysis with dynamic discharge",
        default_strategy="dynamic_discharge",
    )
    args = parser.parse_args(argv)

    region = f"_{args.region}"
    data_file = resolve_data_path(args)

    if args.year:
        basic_data_set["year"] = args.year

    basic_data_set["strategy"] = args.strategy

    if not os.path.exists(data_file):
        print(f"Data file not found: {data_file}")
        return

    analyzer = SolBatSys(data_file, region, basic_data_set=basic_data_set)

    analyzer.run_analysis(
        capacity_list=[1.0, 5, 10, 20, 50, 70],
        power_list=[0.5, 2.5, 5, 10, 25, 35]
    )


if __name__ == "__main__":
    main()

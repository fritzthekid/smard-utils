"""
BioBatSys - Biogas battery system analysis (Refactored).

Uses new modular architecture with backward-compatible interface.
"""

import pandas as pd
import numpy as np
import os
import sys
import logging

from smard_utils.core.driver import EnergyDriver
from smard_utils.core.battery import Battery
from smard_utils.core.bms import BatteryManagementSystem
from smard_utils.core.analytics import BatteryAnalytics
from smard_utils.drivers.biogas_driver import BiogasDriver
from smard_utils.bms_strategies.price_threshold import PriceThresholdStrategy
from smard_utils.bms_strategies.day_ahead import DayAheadStrategy

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

euro_sign = "\N{euro sign}"
root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/.."


class BioBatSys:
    """Biogas battery system with spot-price trading strategy."""

    def __init__(self, csv_file_path, region="", basic_data_set={}):
        """
        Initialize biogas analysis system.

        Args:
            csv_file_path: Path to SMARD CSV data file
            region: Region code (e.g., "_de" for Germany)
            basic_data_set: Configuration dictionary
        """
        self.region = region
        self.basic_data_set = basic_data_set.copy()

        # Initialize driver
        self.driver = BiogasDriver(basic_data_set)
        self.driver.load_data(csv_file_path)

        # Initialize analytics
        self.analytics = BatteryAnalytics(self.driver, basic_data_set)
        self.analytics.prepare_prices()

        # Initialize strategy (default: BatteryBioBatModel logic)
        strategy_name = basic_data_set.get("strategy", "price_threshold")
        if strategy_name == "day_ahead":
            self.strategy = DayAheadStrategy(basic_data_set)
        else:
            self.strategy = PriceThresholdStrategy(basic_data_set)

        # Storage for results
        self.battery_results = None
        self.exporting_l = []
        self.resolution = self.driver.resolution
        self.data = self.driver.data

    def run_analysis(self, capacity_list=[1.0, 5, 10, 20, 100],
                     power_list=[0.5, 2.5, 5, 10, 50]):
        """
        Run battery analysis for multiple capacities.

        Args:
            capacity_list: List of battery capacities (MWh)
            power_list: List of battery powers (MW)
        """
        print("\nStarting biogas battery analysis...")

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
            result_dict = self.analytics.add_simulation_result(
                capacity * 1000, power * 1000, bms, results
            )

            # Track export flags for print method
            self.exporting_l.append((
                np.size(bms.export_flags) - np.count_nonzero(bms.export_flags),
                bms.export_flags.sum()
            ))

        # Get results DataFrame (standard format)
        self.battery_results = self.analytics.get_results_dataframe()

        # Convert to legacy format for backward compatibility
        self._convert_to_legacy_format()

        # Print custom biogas results
        self.print_battery_results()

    def _convert_to_legacy_format(self):
        """
        Convert new results format to legacy format expected by print_battery_results.

        Legacy format:
        - Row 0: "no rule" marker baseline (capacity = -1)
        - Row 1+: Actual simulations (including 0.0 MWh no-battery)
        """
        df = self.battery_results

        # Row 0: "no rule" marker baseline
        marker_baseline = {
            'capacity kWh': -1.0,
            'residual kWh': 0.0,
            'exflow kWh': 0.0,
            'autarky rate': 1.0,
            'spot price [€]': 0.0,
            'fix price [€]': 0.0,
            'revenue [€]': 0.0
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

        # Auto-scale based on data magnitude
        if abs(self.data["my_renew"].sum()) / 1000 > 1000:
            scaler = 1000
            cols = ["cap MWh", "exfl MWh", "export [h]", "rev [T€]", "revadd [T€]", "rev €/kWh"]
        else:
            scaler = 1
            cols = ["cap kWh", "exfl kWh", "export [h]", "rev [€]", "revadd [€]", "rev €/kWh"]

        # Print export statistics
        if len(self.exporting_l) > 1:
            print(f"exporting {export_hours[1]:.0f} hours but not {self.exporting_l[1][0] * self.resolution:.0f} hours"
                  f" (flex premium applies if export < {min_flex_hours} h)")

        # Format results (matches original: skip marker row 0, start from row 1)
        capacity_l = ["no rule"] + [f"{(c / scaler)}" for c in self.battery_results["capacity kWh"][2:]]

        exflowl = [f"{(e / scaler):.1f}" for e in self.battery_results["exflow kWh"][1:]]

        # Row 1 (0.0 MWh) gets no flex premium, rows 2+ get conditional flex premium
        # flex_per_sim[0] = 0.0 MWh baseline, flex_per_sim[1] = first capacity, etc.
        val = self.battery_results['revenue [€]'][1] if len(self.battery_results) > 1 else 0
        revenue_l = [f"{(val / scaler):.1f}"] + [
            f"{((rev + flex) / scaler):.1f}"
            for rev, flex in zip(self.battery_results["revenue [€]"][2:], flex_per_sim[1:])
        ]

        revenue_gain = ["nn"] + [
            f"{((rev - rev1 + flex) / scaler):.2f}"
            for rev, flex in zip(self.battery_results["revenue [€]"][2:], flex_per_sim[1:])
        ]

        capacity_costs = [f"{0:.2f}"] + [f"{0:.2f}"] + [
            f"{((rev - rev1 + flex) / max(1e-10, c)):.2f}"
            for rev, c, flex in zip(
                self.battery_results["revenue [€]"][3:],
                self.battery_results["capacity kWh"][3:],
                flex_per_sim[2:]
            )
        ]

        # Export hours per simulation
        expo_l = [f"{int(eh)}" for eh in export_hours]

        values = np.array([capacity_l, exflowl, expo_l, revenue_l, revenue_gain, capacity_costs]).T

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
}


def main(argv=None):
    """Main function."""
    from smard_utils.utils.cli import create_parser, resolve_data_path

    parser = create_parser(
        prog="biobatsys",
        description="Biogas battery system analysis with spot-price trading",
        default_strategy="price_threshold",
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

    analyzer = BioBatSys(data_file, region, basic_data_set=basic_data_set)

    analyzer.run_analysis(
        capacity_list=[1.0, 5, 10, 20, 100],
        power_list=[0.5, 2.5, 5, 10, 50]
    )


if __name__ == "__main__":
    main()

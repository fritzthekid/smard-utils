"""
Battery simulation analytics and profit calculation.

Collects simulation data and calculates financial metrics.
"""

import os

import numpy as np
import pandas as pd

from smard_utils.core.price_provider import PriceProvider

root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/../.."


class BatteryAnalytics:
    """Collect simulation data and calculate profits."""

    def __init__(self, driver, basic_data_set: dict):
        """
        Initialize analytics with driver and configuration.

        Args:
            driver: EnergyDriver instance
            basic_data_set: Configuration dictionary
        """
        self.driver = driver
        self.basic_data_set = basic_data_set
        self.simulation_results = []
        self.costs_per_kwh = basic_data_set.get("fix_costs_per_kwh", 11) / 100

    def prepare_prices(self, provider=None):
        """
        Load and merge price data into driver data (delegates to PriceProvider, S1/D1).

        Args:
            provider: Optional PriceProvider override (injectable for testing).
                      If None, a default PriceProvider is created from root_dir.

        Adds columns to driver data: price_per_kwh, avrgprice
        """
        if provider is None:
            provider = PriceProvider(root_dir, self.basic_data_set)
        provider.load_prices(self.driver)

    def add_simulation_result(
        self, capacity: float, power: float, bms, step_results: list
    ) -> dict:
        """
        Add a completed simulation to analytics.

        Args:
            capacity: Battery capacity (kWh)
            power: Battery power (kW)
            bms: BatteryManagementSystem instance
            step_results: List of dicts from bms.step()

        Returns:
            Dict with calculated metrics:
                capacity_kwh      - Echo of input capacity
                power_kw          - Echo of input power
                residual_kwh      - Total unmet demand (= grid imports)
                export_kwh        - Total energy exported to grid
                loss_kwh          - Total I2R + efficiency losses
                autarky_rate      - 1 - residual / total_demand  [0..1]
                spot_cost_eur     - sum(residual[t] * spot_price[t])
                fix_cost_eur      - residual_kwh * fix_costs_per_kwh
                revenue_eur       - sum(export[t] * (price[t] - marketing_costs))
                export_hours      - Hours with non-zero export
                total_discharge_kwh - Cumulative energy discharged from battery
                equivalent_cycles - total_discharge / capacity  (full cycles/year)
                net_profit_spot   - revenue - spot_cost
                net_profit_fix    - revenue - fix_cost
        """
        df = pd.DataFrame(step_results)

        # Calculate totals
        total_residual = df["residual_kwh"].sum()
        total_export = df["export_kwh"].sum()
        total_demand = self.driver.data["my_demand"].sum()
        total_loss = df["loss_kwh"].sum()

        # Autarky rate (self-sufficiency)
        autarky_rate = (
            1.0 - (total_residual / total_demand) if total_demand > 0 else 1.0
        )

        # Cost calculations
        spot_cost = (df["residual_kwh"] * df["price"]).sum()
        fix_cost = total_residual * self.costs_per_kwh

        # Revenue from exports
        marketing_cost = self.basic_data_set.get("marketing_costs", 0.0)
        revenue = (df["export_kwh"] * (df["price"] - marketing_cost)).sum()

        # Export time
        export_hours = bms.export_flags.sum() * self.driver.resolution

        # Equivalent full cycles = total energy discharged / nominal capacity
        total_discharge = df["net_discharge"].sum()
        equivalent_cycles = total_discharge / capacity if capacity > 0 else 0.0

        result = {
            "capacity_kwh": capacity,
            "power_kw": power,
            "residual_kwh": total_residual,
            "export_kwh": total_export,
            "loss_kwh": total_loss,
            "autarky_rate": autarky_rate,
            "spot_cost_eur": spot_cost,
            "fix_cost_eur": fix_cost,
            "revenue_eur": revenue,
            "export_hours": export_hours,
            "total_discharge_kwh": total_discharge,
            "equivalent_cycles": equivalent_cycles,
            "net_profit_spot": revenue - spot_cost,
            "net_profit_fix": revenue - fix_cost,
        }

        self.simulation_results.append(result)
        return result

    def get_results_dataframe(self) -> pd.DataFrame:
        """Return all results as DataFrame."""
        return pd.DataFrame(self.simulation_results)

    def calculate_capacity_roi(self) -> pd.DataFrame:
        """
        Calculate ROI per capacity unit.

        Returns:
            DataFrame with revenue_gain and eur_per_kwh columns added
        """
        df = self.get_results_dataframe()

        if len(df) < 2:
            return df

        # Baseline is row 0 (no battery / zero capacity)
        baseline_revenue = df.iloc[0]["revenue_eur"]

        df["revenue_gain"] = df["revenue_eur"] - baseline_revenue
        df["eur_per_kwh"] = df["revenue_gain"] / df["capacity_kwh"].replace(0, np.nan)

        return df

    def print_summary(self, scaler: float = None, unit: str = None):
        """
        Print formatted results table.

        Args:
            scaler: Scaling factor (1 for kWh, 1000 for MWh)
            unit: Unit label (kWh or MWh)
        """
        df = self.calculate_capacity_roi()

        if df.empty:
            print("No simulation results to display.")
            return

        # Auto-detect scaler based on data magnitude
        if scaler is None:
            max_val = max(df["capacity_kwh"].max(), df["export_kwh"].max())
            if max_val / 1000 > 1000:
                scaler = 1000
                unit = "MWh"
            else:
                scaler = 1
                unit = "kWh"

        euro_sign = "\N{EURO SIGN}"

        print(f"\n{'='*80}")
        print("Battery Simulation Results")
        print(f"{'='*80}")

        # Select and format columns
        cols = {
            "capacity_kwh": f"Cap [{unit}]",
            "export_kwh": f"Export [{unit}]",
            "export_hours": "Export [h]",
            "revenue_eur": f'Revenue [{"T" + euro_sign if scaler == 1000 else euro_sign}]',
            "revenue_gain": f'Gain [{"T" + euro_sign if scaler == 1000 else euro_sign}]',
            "eur_per_kwh": f"{euro_sign}/kWh",
        }

        display_df = df[[col for col in cols.keys() if col in df.columns]].copy()

        # Scale values
        for col in ["capacity_kwh", "export_kwh"]:
            if col in display_df.columns:
                display_df[col] = display_df[col] / scaler

        if scaler == 1000:
            for col in ["revenue_eur", "revenue_gain"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col] / 1000

        # Rename columns
        display_df.columns = [cols[col] for col in display_df.columns]

        # Print with formatting
        with pd.option_context("display.max_columns", None, "display.precision", 2):
            print(display_df.to_string(index=False))

        print(f"{'='*80}\n")

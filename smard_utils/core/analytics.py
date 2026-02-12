"""
Battery simulation analytics and profit calculation.

Collects simulation data and calculates financial metrics.
"""

import pandas as pd
import numpy as np
import os


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

    def prepare_prices(self):
        """
        Load and merge price data into driver data.

        Adds columns: price_per_kwh, avrgprice
        """
        year = self.basic_data_set.get("year")

        if self.basic_data_set.get("fix_contract", False) or year is None:
            # Fixed price contract
            marketing_costs = self.basic_data_set.get("marketing_costs", 0.0)
            self.driver._data["price_per_kwh"] = self.costs_per_kwh + marketing_costs
            self.driver._data["avrgprice"] = self.costs_per_kwh + marketing_costs
        else:
            # Load hourly spot prices
            path = f"{root_dir}/costs"
            costs_file = f"{path}/{year}-hour-price.csv"

            if not os.path.exists(costs_file):
                print(f"⚠ Price file not found: {costs_file}, using fixed price")
                self.driver._data["price_per_kwh"] = self.costs_per_kwh
                self.driver._data["avrgprice"] = self.costs_per_kwh
                return

            costs = pd.read_csv(costs_file)
            costs["price"] /= 100  # Convert from ct/kWh to €/kWh

            total_average = costs["price"].mean()

            # Calculate rolling 25-hour average (centered)
            window_size = 25
            costs["avrgprice"] = costs["price"].rolling(
                window=window_size,
                center=True,
                min_periods=1
            ).mean()

            # Fill edge values
            costs.fillna({"avrgprice": total_average}, inplace=True)

            # Parse datetime and set index
            costs["dtime"] = pd.to_datetime(costs["time"])
            costs = costs.set_index("dtime")

            if costs.index[0].year != year:
                raise ValueError(f"Year mismatch: costs file is {costs.index[0].year}, expected {year}")

            # Vectorized alignment to data timestamps
            start_time = costs.index[0]
            hours_diff = ((self.driver.data.index - start_time).total_seconds() / 3600).astype(int)
            hours_diff = np.clip(hours_diff, 0, len(costs) - 1)

            marketing_costs = self.basic_data_set.get("marketing_costs", 0.0)
            self.driver._data["price_per_kwh"] = costs["price"].iloc[hours_diff].values + marketing_costs
            self.driver._data["avrgprice"] = costs["avrgprice"].iloc[hours_diff].values + marketing_costs

    def add_simulation_result(self, capacity: float, power: float,
                             bms, step_results: list) -> dict:
        """
        Add a completed simulation to analytics.

        Args:
            capacity: Battery capacity (kWh)
            power: Battery power (kW)
            bms: BatteryManagementSystem instance
            step_results: List of dicts from bms.step()

        Returns:
            Dict with calculated metrics
        """
        df = pd.DataFrame(step_results)

        # Calculate totals
        total_residual = df['residual_kwh'].sum()
        total_export = df['export_kwh'].sum()
        total_demand = self.driver.data['my_demand'].sum()
        total_loss = df['loss_kwh'].sum()

        # Autarky rate (self-sufficiency)
        autarky_rate = 1.0 - (total_residual / total_demand) if total_demand > 0 else 1.0

        # Cost calculations
        spot_cost = (df['residual_kwh'] * df['price']).sum()
        fix_cost = total_residual * self.costs_per_kwh

        # Revenue from exports
        marketing_cost = self.basic_data_set.get("marketing_costs", 0.0)
        revenue = (df['export_kwh'] * (df['price'] - marketing_cost)).sum()

        # Export time
        export_hours = bms.export_flags.sum() * self.driver.resolution

        result = {
            'capacity_kwh': capacity,
            'power_kw': power,
            'residual_kwh': total_residual,
            'export_kwh': total_export,
            'loss_kwh': total_loss,
            'autarky_rate': autarky_rate,
            'spot_cost_eur': spot_cost,
            'fix_cost_eur': fix_cost,
            'revenue_eur': revenue,
            'export_hours': export_hours,
            'net_profit_spot': revenue - spot_cost,
            'net_profit_fix': revenue - fix_cost
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
        baseline_revenue = df.iloc[0]['revenue_eur']

        df['revenue_gain'] = df['revenue_eur'] - baseline_revenue
        df['eur_per_kwh'] = df['revenue_gain'] / df['capacity_kwh'].replace(0, np.nan)

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
            max_val = max(df['capacity_kwh'].max(), df['export_kwh'].max())
            if max_val / 1000 > 1000:
                scaler = 1000
                unit = "MWh"
            else:
                scaler = 1
                unit = "kWh"

        euro_sign = "\N{euro sign}"

        print(f"\n{'='*80}")
        print(f"Battery Simulation Results")
        print(f"{'='*80}")

        # Select and format columns
        cols = {
            'capacity_kwh': f'Cap [{unit}]',
            'export_kwh': f'Export [{unit}]',
            'export_hours': 'Export [h]',
            'revenue_eur': f'Revenue [{"T" + euro_sign if scaler == 1000 else euro_sign}]',
            'revenue_gain': f'Gain [{"T" + euro_sign if scaler == 1000 else euro_sign}]',
            'eur_per_kwh': f'{euro_sign}/kWh'
        }

        display_df = df[[col for col in cols.keys() if col in df.columns]].copy()

        # Scale values
        for col in ['capacity_kwh', 'export_kwh']:
            if col in display_df.columns:
                display_df[col] = display_df[col] / scaler

        if scaler == 1000:
            for col in ['revenue_eur', 'revenue_gain']:
                if col in display_df.columns:
                    display_df[col] = display_df[col] / 1000

        # Rename columns
        display_df.columns = [cols[col] for col in display_df.columns]

        # Print with formatting
        with pd.option_context('display.max_columns', None, 'display.precision', 2):
            print(display_df.to_string(index=False))

        print(f"{'='*80}\n")

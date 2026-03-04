"""
Price provider — loads spot-price CSV and merges into driver data.

Extracted from BatteryAnalytics.prepare_prices() to satisfy SRP (S1) and
Dependency Inversion (D1): analytics no longer hard-codes the price-file
path — it receives an injectable PriceProvider instead.
"""

import os

import numpy as np
import pandas as pd


class PriceProvider:
    """
    Loads hourly spot-price CSV and merges prices into an EnergyDriver\'s data.

    The default constructor uses the project\'s own costs/ directory; inject a
    custom instance (or subclass) to test with synthetic prices or a different
    data source.
    """

    def __init__(self, root_dir: str, basic_data_set: dict):
        """
        Args:
            root_dir: Project root directory (contains costs/ sub-dir).
            basic_data_set: Config dict with 'year', 'fix_contract',
                            'fix_costs_per_kwh', 'marketing_costs'.
        """
        self.root_dir = root_dir
        self.basic_data_set = basic_data_set
        self._costs_per_kwh = basic_data_set.get("fix_costs_per_kwh", 11) / 100

    def load_prices(self, driver) -> None:
        """
        Add price_per_kwh and avrgprice columns to driver._data.

        Uses a fixed price when fix_contract is True or when the spot-price
        CSV is not found.  Otherwise loads the hourly CSV from costs/{year}-hour-price.csv
        and aligns it to the driver\'s timestamps.

        Args:
            driver: EnergyDriver instance (must have _data and data.index set).
        """
        year = self.basic_data_set.get("year")
        marketing_costs = self.basic_data_set.get("marketing_costs", 0.0)

        if self.basic_data_set.get("fix_contract", False) or year is None:
            self._apply_fixed_price(driver, marketing_costs)
            return

        costs_file = os.path.join(self.root_dir, "costs", f"{year}-hour-price.csv")
        if not os.path.exists(costs_file):
            print(f"⚠ Price file not found: {costs_file}, using fixed price")
            self._apply_fixed_price(driver, marketing_costs)
            return

        self._apply_spot_price(driver, costs_file, marketing_costs, year)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_fixed_price(self, driver, marketing_costs: float) -> None:
        price = self._costs_per_kwh + marketing_costs
        driver._data["price_per_kwh"] = price
        driver._data["avrgprice"] = price

    def _apply_spot_price(
        self, driver, costs_file: str, marketing_costs: float, year: int
    ) -> None:
        costs = pd.read_csv(costs_file)
        costs["price"] /= 100  # ct/kWh → €/kWh

        total_average = costs["price"].mean()
        costs["avrgprice"] = (
            costs["price"].rolling(window=25, center=True, min_periods=1).mean()
        )
        costs.fillna({"avrgprice": total_average}, inplace=True)

        costs["dtime"] = pd.to_datetime(costs["time"])
        costs = costs.set_index("dtime")

        if costs.index[0].year != year:
            raise ValueError(
                f"Year mismatch: costs file is {costs.index[0].year}, expected {year}"
            )

        start_time = costs.index[0]
        hours_diff = ((driver.data.index - start_time).total_seconds() / 3600).astype(
            int
        )
        hours_diff = np.clip(hours_diff, 0, len(costs) - 1)

        driver._data["price_per_kwh"] = (
            costs["price"].iloc[hours_diff].values + marketing_costs
        )
        driver._data["avrgprice"] = (
            costs["avrgprice"].iloc[hours_diff].values + marketing_costs
        )

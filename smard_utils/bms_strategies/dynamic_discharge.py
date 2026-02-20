"""
Dynamic discharge strategy with saturation curves.

Used by solar systems: discharge intensity based on daily price ranking.
"""

import numpy as np
import pandas as pd
from smard_utils.core.bms import BMSStrategy


class DynamicDischargeStrategy(BMSStrategy):
    """SolBat logic: Saturation curves + dynamic discharge factor."""

    def __init__(self, basic_data_set: dict):
        """
        Initialize strategy with SOC and discharge parameters.

        Args:
            basic_data_set: Configuration dict with:
                - limit_soc_threshold: SOC operation window (default: 0.05)
                - control_exflow: Export control mode (default: 3)
                - min_soc, max_soc: SOC limits
        """
        super().__init__(basic_data_set)
        self.limit_soc_threshold = basic_data_set.get("limit_soc_threshold", 0.05)
        self.control_exflow = basic_data_set.get("control_exflow", 3)
        self.price_array = np.zeros(24)  # Hourly discharge factors [-1, 1]
        self.data = None  # Full dataset for rolling window
        self.dt_h = None  # Time resolution
        self.last_update_day = None  # Track when price array was last updated

    def setup_price_array(self, data: pd.DataFrame, dt_h: float):
        """
        Store data reference for dynamic price array updates.

        Args:
            data: DataFrame with price_per_kwh column
            dt_h: Timestep duration in hours
        """
        self.data = data
        self.dt_h = dt_h

    def _update_price_array(self, current_index: int):
        """
        Update 24-hour price ranking from current position.

        This creates a discharge factor array based on the NEXT 24 hours
        of prices, updated daily at 13:00.

        Args:
            current_index: Current timestep index
        """
        if self.data is None or "price_per_kwh" not in self.data.columns:
            self.price_array = np.zeros(24)
            return

        price_per_kwh = self.data["price_per_kwh"]

        # Rolling 24-hour window from current position
        rest_len = min(int(24 / self.dt_h), len(price_per_kwh) - current_index)

        vals = [(price_per_kwh.index[j].hour, price_per_kwh.iloc[j])
                for j in range(current_index, current_index + rest_len)]

        # Deduplicate by hour (keep first occurrence)
        vals_set = []
        vals_indices = []
        for val in vals:
            if val[0] not in vals_indices:
                vals_set.append(val)
                vals_indices.append(val[0])

        if len(vals_set) == 0:
            self.price_array = np.zeros(24)
            return

        # Sort by price to get ranking
        vals = sorted(vals_set, key=lambda x: x[1])

        # Create array with rankings
        nvals = np.ones(24) * 12  # Default middle value
        for idx, v in enumerate(vals):
            nvals[v[0]] = idx  # Rank: 0 (cheapest) to 23 (most expensive)

        # Normalize to [-1, 1]
        if max(nvals) - min(nvals) > 0.001:
            self.price_array = ((nvals - min(nvals)) / (max(nvals) - min(nvals)) * 2) - 1
        else:
            self.price_array = np.zeros(24)

    def _discharging_factor(self, timestamp) -> float:
        """
        Get discharge factor for current hour.

        Args:
            timestamp: Current timestamp

        Returns:
            Discharge factor in range [-1, 1]
        """
        return self.price_array[timestamp.hour]

    def _saturation_curve(self, x: float, df: float, df_min: float, sub: float) -> float:
        """
        Concave saturation curve for discharge amount.

        Args:
            x: Discharge factor [-1, 1]
            df: Curve shape parameter (higher = steeper)
            df_min: Minimum threshold to start discharging
            sub: Substitute value if > 0

        Returns:
            Discharge intensity factor [0, 1]
        """
        if sub > 0:
            return sub

        if x <= df_min:
            return 0.0

        u = (x - df_min) / (1 - df_min)
        return 1 - (1 - u) ** df

    def should_charge(self, context: dict) -> bool:
        """
        Charge when discharge factor is negative and SOC permits.

        Args:
            context: Decision context

        Returns:
            True if should charge
        """
        df = self._discharging_factor(context['timestamp'])
        max_soc = self.basic_data_set.get("max_soc", 0.95)

        return (df < 0 and
                context['current_storage'] <= (max_soc - self.limit_soc_threshold) * context['capacity'] and
                context['current_storage'] >= self.limit_soc_threshold)

    def should_discharge(self, context: dict) -> bool:
        """
        Discharge when discharge factor exceeds threshold and SOC permits.

        Updates price array daily at 13:00.

        Args:
            context: Decision context

        Returns:
            True if should discharge
        """
        # Update price array daily at 13:00
        timestamp = context['timestamp']
        current_day = timestamp.date()
        if (self.last_update_day != current_day and
            timestamp.hour == 13 and timestamp.minute == 0):
            self._update_price_array(context['index'])
            self.last_update_day = current_day

        df = self._discharging_factor(timestamp)
        df_min = 0.7  # Discharge only in top ~30% of daily prices
        min_soc = self.basic_data_set.get("min_soc", 0.05)

        return (df > df_min and
                context['current_storage'] >= (min_soc + self.limit_soc_threshold) * context['capacity'] and
                context['current_storage'] >= self.limit_soc_threshold)

    def should_export(self, context: dict) -> bool:
        """
        Export when price is positive and control mode permits.

        Args:
            context: Decision context

        Returns:
            True if should export excess
        """
        return context['price'] >= 0 and self.control_exflow > 1

    def calculate_charge_amount(self, context: dict) -> float:
        """
        Calculate charge amount limited by power and SOC.

        Args:
            context: Decision context

        Returns:
            Energy to charge (kWh)
        """
        max_soc = self.basic_data_set.get("max_soc", 0.95)

        allowed_energy = min(
            context['power_limit'] * context['resolution'],
            (max_soc * context['capacity']) - context['current_storage']
        )
        surplus = max(0.0, context['renew'] - abs(context.get('demand', 0)))
        return min(surplus, allowed_energy)

    def calculate_discharge_amount(self, context: dict) -> float:
        """
        Calculate discharge amount using saturation curve.

        Applies concave curve to modulate discharge power based on
        how profitable the current hour is relative to daily prices.

        Args:
            context: Decision context

        Returns:
            Energy to discharge (kWh)
        """
        df = self._discharging_factor(context['timestamp'])
        min_soc = self.basic_data_set.get("min_soc", 0.05)

        # Saturation curve parameters (optimized for >= 20 MWh)
        df_param = 3      # Curve steepness
        df_min = 0.7      # Minimum threshold
        sub = 0.0         # No substitute

        allowed_energy = min(
            context['power_limit'] * context['resolution'],
            context['current_storage'] - (min_soc * context['capacity'])
        )

        # Apply saturation curve to modulate discharge
        factor = self._saturation_curve(df, df_param, df_min, sub)
        result = factor * allowed_energy

        # For community scenarios: only discharge to cover local deficit.
        # - Surplus hour (renew >= demand): no discharge needed, return 0.
        # - Deficit hour (renew < demand): cap discharge at the actual deficit.
        # For solar/biogas (demand < 0): guard is False, discharge normally.
        demand = context.get('demand', 0)
        if demand > 0:
            net_deficit = demand - context['renew']
            if net_deficit <= 0:
                return 0.0  # Surplus hour: battery not needed
            result = min(result, net_deficit)

        return result

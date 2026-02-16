"""
Day-ahead price strategy with realistic information constraints.

Simulates real-world operation where the operator only knows prices that
have been published by the EPEX Spot Day-Ahead auction (at ~13:00 CET
for the next day's 24 hours).

Price data source: netztransparenz.de (Spotmarktpreis nach §3 Nr. 42a EEG)
"""

import numpy as np
import pandas as pd
from smard_utils.core.bms import BMSStrategy


class DayAheadStrategy(BMSStrategy):
    """
    Day-ahead market strategy with realistic information boundary.

    At 13:00 each day, receives the next day's 24 hourly prices from
    the day-ahead auction. Plans optimal charge/discharge schedule
    based only on prices known at decision time.
    """

    def __init__(self, basic_data_set: dict):
        """
        Initialize strategy with thresholds and planning parameters.

        Args:
            basic_data_set: Configuration dict with:
                - discharge_threshold: Multiplier for discharge (default: 1.2)
                - charge_threshold: Multiplier for charge (default: 0.8)
                - min_soc, max_soc: SOC limits
                - control_exflow: Export control mode (default: 3)
        """
        super().__init__(basic_data_set)
        self.discharge_threshold = basic_data_set.get("discharge_threshold", 1.2)
        self.charge_threshold = basic_data_set.get("charge_threshold", 0.8)
        self.control_exflow = basic_data_set.get("control_exflow", 3)

        # Planning state
        self.data = None
        self.dt_h = None

        # Hour-by-hour schedule: 'charge', 'discharge', or 'idle'
        # Indexed by (date, hour) -> action
        self.schedule = {}
        # Known price averages per planning window
        self.known_avg = 0.0

        # Track last plan update
        self.last_plan_day = None
        # Track which day's prices we currently know
        self.known_until_date = None

    def setup_price_array(self, data: pd.DataFrame, dt_h: float):
        """
        Store data reference for day-ahead planning.

        Called by BMS.initialize().

        Args:
            data: DataFrame with price_per_kwh column (full year)
            dt_h: Timestep duration in hours
        """
        self.data = data
        self.dt_h = dt_h

    def _update_day_ahead_plan(self, current_index: int):
        """
        Build charge/discharge schedule from known day-ahead prices.

        Information boundary:
        - At simulation start (index 0): knows today's prices
        - At 13:00 each day: receives tomorrow's 24 hourly prices
        - Schedule covers: today (remaining hours) + tomorrow (if after 13:00)

        Args:
            current_index: Current timestep index in the simulation
        """
        if self.data is None or "price_per_kwh" not in self.data.columns:
            return

        timestamp = self.data.index[current_index]
        current_date = timestamp.date()
        current_hour = timestamp.hour

        # Determine the planning window based on information available
        # Day-ahead prices are published at 13:00 for the NEXT day
        known_prices = []

        if current_hour >= 13:
            # After 13:00: know today's remaining + tomorrow's full 24h
            # Collect today's remaining hours
            for h in range(current_hour, 24):
                idx = self._find_index_for_hour(current_date, h)
                if idx is not None:
                    price = self.data["price_per_kwh"].iloc[idx]
                    known_prices.append((current_date, h, price, idx))

            # Collect tomorrow's 24 hours (just received from day-ahead auction)
            tomorrow = current_date + pd.Timedelta(days=1)
            for h in range(24):
                idx = self._find_index_for_hour(tomorrow, h)
                if idx is not None:
                    price = self.data["price_per_kwh"].iloc[idx]
                    known_prices.append((tomorrow, h, price, idx))

            self.known_until_date = tomorrow
        else:
            # Before 13:00: only know today's prices (received yesterday at 13:00)
            for h in range(24):
                idx = self._find_index_for_hour(current_date, h)
                if idx is not None:
                    price = self.data["price_per_kwh"].iloc[idx]
                    known_prices.append((current_date, h, price, idx))

            self.known_until_date = current_date

        if not known_prices:
            return

        # Compute average from known prices only (backward-looking)
        prices_only = [p[2] for p in known_prices]
        self.known_avg = np.mean(prices_only)

        # Build schedule: rank prices and assign actions
        self.schedule = {}
        for date, hour, price, idx in known_prices:
            key = (date, hour)
            if price >= self.discharge_threshold * self.known_avg:
                self.schedule[key] = 'discharge'
            elif price <= self.charge_threshold * self.known_avg:
                self.schedule[key] = 'charge'
            else:
                self.schedule[key] = 'idle'

        self.last_plan_day = current_date

    def _find_index_for_hour(self, date, hour):
        """
        Find the data index for a specific date and hour.

        Args:
            date: Target date
            hour: Target hour (0-23)

        Returns:
            Index into self.data or None if not found
        """
        if self.data is None:
            return None

        # Calculate expected index from start
        start_time = self.data.index[0]
        target_time = pd.Timestamp(year=date.year, month=date.month,
                                    day=date.day, hour=hour)
        hours_diff = (target_time - start_time).total_seconds() / 3600
        idx = int(round(hours_diff / self.dt_h))

        if 0 <= idx < len(self.data):
            return idx
        return None

    def _get_planned_action(self, timestamp) -> str:
        """
        Get the planned action for the current timestamp.

        Args:
            timestamp: Current timestamp

        Returns:
            'charge', 'discharge', or 'idle'
        """
        key = (timestamp.date(), timestamp.hour)
        return self.schedule.get(key, 'idle')

    def _maybe_update_plan(self, context: dict):
        """
        Check if plan needs updating (at 13:00 or on new day).

        Args:
            context: Decision context with timestamp and index
        """
        timestamp = context['timestamp']
        current_date = timestamp.date()

        # Update at simulation start
        if self.last_plan_day is None:
            self._update_day_ahead_plan(context['index'])
            return

        # Update at 13:00 when new day-ahead prices become available
        if (timestamp.hour == 13 and timestamp.minute == 0 and
                self.last_plan_day != current_date):
            self._update_day_ahead_plan(context['index'])
            return

        # Also update at midnight if we've entered a new day
        # (use the plan made yesterday at 13:00, but re-scope to today)
        if current_date != self.last_plan_day and timestamp.hour == 0:
            self._update_day_ahead_plan(context['index'])

    def should_charge(self, context: dict) -> bool:
        """
        Charge when the day-ahead plan says 'charge' and SOC permits.

        Args:
            context: Decision context

        Returns:
            True if should charge
        """
        self._maybe_update_plan(context)

        action = self._get_planned_action(context['timestamp'])
        if action != 'charge':
            return False

        max_soc = self.basic_data_set.get("max_soc", 0.95)
        return context['current_storage'] < max_soc * context['capacity']

    def should_discharge(self, context: dict) -> bool:
        """
        Discharge when the day-ahead plan says 'discharge' and SOC permits.

        Args:
            context: Decision context

        Returns:
            True if should discharge
        """
        self._maybe_update_plan(context)

        action = self._get_planned_action(context['timestamp'])
        if action != 'discharge':
            return False

        min_soc = self.basic_data_set.get("min_soc", 0.05)
        return context['current_storage'] > min_soc * context['capacity']

    def should_export(self, context: dict) -> bool:
        """
        Export when price is non-negative and control mode permits.

        Args:
            context: Decision context

        Returns:
            True if should export excess
        """
        return context['price'] >= 0 and self.control_exflow > 1

    def calculate_charge_amount(self, context: dict) -> float:
        """
        Calculate charge amount limited by power, SOC, and available renewable.

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
        return min(context['renew'], allowed_energy)

    def calculate_discharge_amount(self, context: dict) -> float:
        """
        Calculate discharge amount with saturation curve modulation.

        Uses the price ranking to modulate how aggressively to discharge:
        higher-ranked (more expensive) hours get more power.

        Args:
            context: Decision context

        Returns:
            Energy to discharge (kWh)
        """
        min_soc = self.basic_data_set.get("min_soc", 0.05)

        allowed_energy = min(
            context['power_limit'] * context['resolution'],
            context['current_storage'] - (min_soc * context['capacity'])
        )

        # Modulate discharge based on how far above threshold the price is
        price = context['price']
        if self.known_avg > 0:
            price_ratio = price / self.known_avg
            # Scale from 0 to 1 based on how much above threshold
            # At threshold (1.2): factor ~ 0
            # At 2x average: factor ~ 1
            intensity = min(1.0, max(0.0,
                (price_ratio - self.discharge_threshold) /
                (2.0 - self.discharge_threshold)
            ))
            # Apply concave saturation curve: 1 - (1-x)^3
            factor = 1.0 - (1.0 - intensity) ** 3
        else:
            factor = 1.0

        return factor * allowed_energy

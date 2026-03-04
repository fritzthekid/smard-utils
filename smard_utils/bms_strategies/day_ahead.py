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
        super().__init__(basic_data_set)
        self.discharge_threshold = basic_data_set.get("discharge_threshold", 1.2)
        self.charge_threshold = basic_data_set.get("charge_threshold", 0.8)
        self.control_exflow = basic_data_set.get("control_exflow", 3)

        self.data = None
        self.dt_h = None
        self.schedule = {}
        self.known_avg = 0.0
        self.last_plan_day = None
        self.known_until_date = None

    def setup_price_array(self, data: pd.DataFrame, dt_h: float):
        """Store data reference for day-ahead planning (called by BMS.initialize())."""
        self.data = data
        self.dt_h = dt_h

    # ------------------------------------------------------------------
    # Planning helpers (split from original _update_day_ahead_plan, S6)
    # ------------------------------------------------------------------

    def _collect_prices_for_date(self, date) -> list:
        """
        Collect all (date, hour, price, idx) tuples for an entire calendar day.

        Args:
            date: Target date object

        Returns:
            List of (date, hour, price, idx) for each hour found in data
        """
        entries = []
        for h in range(24):
            idx = self._find_index_for_hour(date, h)
            if idx is not None:
                price = self.data["price_per_kwh"].iloc[idx]
                entries.append((date, h, price, idx))
        return entries

    def _collect_prices_from_hour(self, date, from_hour: int) -> list:
        """
        Collect (date, hour, price, idx) tuples from a specific hour onward.

        Args:
            date: Target date object
            from_hour: First hour to include (0–23)

        Returns:
            List of (date, hour, price, idx) for from_hour..23
        """
        entries = []
        for h in range(from_hour, 24):
            idx = self._find_index_for_hour(date, h)
            if idx is not None:
                price = self.data["price_per_kwh"].iloc[idx]
                entries.append((date, h, price, idx))
        return entries

    def _assign_schedule(self, known_prices: list):
        """
        Build hour-by-hour schedule from a list of known price entries.

        Prices are ranked against their local average; hours above the
        discharge threshold are scheduled to discharge, hours below the
        charge threshold are scheduled to charge.

        Args:
            known_prices: List of (date, hour, price, idx) tuples
        """
        if not known_prices:
            return

        prices_only = [p[2] for p in known_prices]
        self.known_avg = np.mean(prices_only)

        self.schedule = {}
        for date, hour, price, _ in known_prices:
            key = (date, hour)
            if price >= self.discharge_threshold * self.known_avg:
                self.schedule[key] = "discharge"
            elif price <= self.charge_threshold * self.known_avg:
                self.schedule[key] = "charge"
            else:
                self.schedule[key] = "idle"

    def _update_day_ahead_plan(self, current_index: int):
        """
        Rebuild schedule from known day-ahead prices at the given timestep.

        Information boundary:
        - At simulation start (index 0): knows today's prices
        - At 13:00 each day: receives tomorrow's full 24 h from auction
        - Schedule covers: today (remaining hours) + tomorrow (if ≥13:00)

        Args:
            current_index: Current timestep index in the simulation
        """
        if self.data is None or "price_per_kwh" not in self.data.columns:
            return

        timestamp = self.data.index[current_index]
        current_date = timestamp.date()
        current_hour = timestamp.hour

        if current_hour >= 13:
            # After 13:00: today's remaining hours + tomorrow's full day
            known_prices = self._collect_prices_from_hour(
                current_date, current_hour
            ) + self._collect_prices_for_date(current_date + pd.Timedelta(days=1))
            self.known_until_date = current_date + pd.Timedelta(days=1)
        else:
            # Before 13:00: only today's prices (received yesterday at 13:00)
            known_prices = self._collect_prices_for_date(current_date)
            self.known_until_date = current_date

        self._assign_schedule(known_prices)
        self.last_plan_day = current_date

    # ------------------------------------------------------------------
    # Schedule lookup
    # ------------------------------------------------------------------

    def _find_index_for_hour(self, date, hour):
        """Return data index for a specific date+hour, or None if out of range."""
        if self.data is None:
            return None
        start_time = self.data.index[0]
        target_time = pd.Timestamp(
            year=date.year, month=date.month, day=date.day, hour=hour
        )
        hours_diff = (target_time - start_time).total_seconds() / 3600
        idx = int(round(hours_diff / self.dt_h))
        return idx if 0 <= idx < len(self.data) else None

    def _get_planned_action(self, timestamp) -> str:
        """Return scheduled action ('charge', 'discharge', or 'idle') for timestamp."""
        key = (timestamp.date(), timestamp.hour)
        return self.schedule.get(key, "idle")

    def _maybe_update_plan(self, context: dict):
        """Trigger plan rebuild at simulation start, 13:00, or midnight."""
        timestamp = context["timestamp"]
        current_date = timestamp.date()

        if self.last_plan_day is None:
            self._update_day_ahead_plan(context["index"])
            return

        if (
            timestamp.hour == 13
            and timestamp.minute == 0
            and self.last_plan_day != current_date
        ):
            self._update_day_ahead_plan(context["index"])
            return

        if current_date != self.last_plan_day and timestamp.hour == 0:
            self._update_day_ahead_plan(context["index"])

    # ------------------------------------------------------------------
    # BMSStrategy interface
    # ------------------------------------------------------------------

    def should_charge(self, context: dict) -> bool:
        self._maybe_update_plan(context)
        action = self._get_planned_action(context["timestamp"])
        if action == "discharge":
            return False
        max_soc = self.basic_data_set.get("max_soc", 0.95)
        return context["current_storage"] < max_soc * context["capacity"]

    def should_discharge(self, context: dict) -> bool:
        self._maybe_update_plan(context)
        action = self._get_planned_action(context["timestamp"])
        if action != "discharge":
            return False
        min_soc = self.basic_data_set.get("min_soc", 0.05)
        return context["current_storage"] > min_soc * context["capacity"]

    def should_export(self, context: dict) -> bool:
        return context["price"] >= 0 and self.control_exflow > 1

    def calculate_charge_amount(self, context: dict) -> float:
        max_soc = self.basic_data_set.get("max_soc", 0.95)
        allowed_energy = min(
            context["power_limit"] * context["resolution"],
            (max_soc * context["capacity"]) - context["current_storage"],
        )
        surplus = max(0.0, context["renew"] - abs(context.get("demand", 0)))
        return min(surplus, allowed_energy)

    def calculate_discharge_amount(self, context: dict) -> float:
        min_soc = self.basic_data_set.get("min_soc", 0.05)
        efficiency_discharge = self.basic_data_set.get("efficiency_discharge", 0.96)
        allowed_energy = min(
            context["power_limit"] * context["resolution"],
            (context["current_storage"] - min_soc * context["capacity"])
            * efficiency_discharge,
        )
        price = context["price"]
        if self.known_avg > 0:
            price_ratio = price / self.known_avg
            intensity = min(
                1.0,
                max(
                    0.0,
                    (price_ratio - self.discharge_threshold)
                    / (2.0 - self.discharge_threshold),
                ),
            )
            factor = 1.0 - (1.0 - intensity) ** 3
        else:
            factor = 1.0

        result = factor * allowed_energy

        demand = context.get("demand", 0)
        if demand > 0:
            net_deficit = demand - context["renew"]
            if net_deficit <= 0:
                return 0.0
            result = min(result, net_deficit)

        return result

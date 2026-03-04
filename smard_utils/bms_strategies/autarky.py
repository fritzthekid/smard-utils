"""
Autarky strategy for home storage systems.

Charges battery from excess solar generation; discharges to cover demand
shortfall.  Goal: maximise self-sufficiency (Autarkie) using a fixed
electricity tariff — no spot-price knowledge required.
"""

from smard_utils.core.bms import BMSStrategy


class AutoarkyStrategy(BMSStrategy):
    """
    Simple charge-from-surplus / discharge-to-cover-deficit strategy.

    Convention: demand > 0 (household consumption), renew > 0 (solar).

    Decision tree per timestep:
        surplus = renew - demand
        deficit = demand - renew

        1. deficit > 0 and battery above min_soc  → discharge (cover deficit)
        2. surplus > 0 and battery below max_soc  → charge (store excess)
        3. surplus > 0 and battery full           → export physical surplus
        4. everything else                         → idle
    """

    def should_discharge(self, context: dict) -> bool:
        deficit = context["demand"] - context["renew"]
        if deficit <= 0:
            return False
        min_soc = self.basic_data_set.get("min_soc", 0.05)
        return context["current_storage"] > min_soc * context["capacity"]

    def should_charge(self, context: dict) -> bool:
        surplus = context["renew"] - context["demand"]
        if surplus <= 0:
            return False
        max_soc = self.basic_data_set.get("max_soc", 0.95)
        return context["current_storage"] < max_soc * context["capacity"]

    def should_export(self, context: dict) -> bool:
        # Always allow physical surplus to flow out (avoids curtailment).
        # Feed-in revenue is handled by HomeBatSys, not by this flag.
        return True

    def calculate_charge_amount(self, context: dict) -> float:
        surplus = max(0.0, context["renew"] - context["demand"])
        max_soc = self.basic_data_set.get("max_soc", 0.95)
        room = max_soc * context["capacity"] - context["current_storage"]
        allowed = context["power_limit"] * context["resolution"]
        return min(surplus, room, allowed)

    def calculate_discharge_amount(self, context: dict) -> float:
        deficit = max(0.0, context["demand"] - context["renew"])
        min_soc = self.basic_data_set.get("min_soc", 0.05)
        efficiency_discharge = self.basic_data_set.get("efficiency_discharge", 0.96)
        available = (
            context["current_storage"] - min_soc * context["capacity"]
        ) * efficiency_discharge
        allowed = context["power_limit"] * context["resolution"]
        return min(deficit, available, allowed)

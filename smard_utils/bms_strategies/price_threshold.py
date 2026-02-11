"""
Price threshold strategy with hysteresis.

Used by biogas systems: charge at low prices, discharge at high prices.
"""

from smard_utils.core.bms import BMSStrategy


class PriceThresholdStrategy(BMSStrategy):
    """BioBat logic: Load/unload based on price thresholds."""

    def __init__(self, basic_data_set: dict):
        """
        Initialize strategy with threshold parameters.

        Args:
            basic_data_set: Configuration dict with:
                - load_threshold: Charge threshold multiplier (default: 1.0)
                - load_threshold_high: Discharge threshold multiplier (default: 1.2)
                - export_threshold: Export threshold multiplier (default: 0.9)
        """
        super().__init__(basic_data_set)
        self.load_threshold = basic_data_set.get("load_threshold", 1.0)
        self.load_threshold_high = basic_data_set.get("load_threshold_high", 1.2)
        self.export_threshold = basic_data_set.get("export_threshold", 0.9)
        self.meanprice = None  # Set during simulation

    def setup_meanprice(self, data):
        """Calculate mean price for export threshold."""
        if 'price_per_kwh' in data.columns:
            self.meanprice = data['price_per_kwh'].mean()
        else:
            self.meanprice = 0.0

    def should_charge(self, context: dict) -> bool:
        """
        Charge when price below average.

        Args:
            context: Decision context

        Returns:
            True if should charge
        """
        price = context['price']
        avg_price = context['avg_price']
        return price < self.load_threshold * avg_price

    def should_discharge(self, context: dict) -> bool:
        """
        Discharge when price above threshold (uses load_threshold, not load_threshold_high!).

        Args:
            context: Decision context

        Returns:
            True if should discharge
        """
        price = context['price']
        avg_price = context['avg_price']
        # BioBat uses same load_threshold for both charge and discharge
        return price > self.load_threshold * abs(avg_price)

    def should_export(self, context: dict) -> bool:
        """
        BioBat never exports except when discharging (handled in case 1).

        Args:
            context: Decision context

        Returns:
            False (never export in cases 2 or 3)
        """
        # BioBat only exports when actively discharging
        return False

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
        return min(context['renew'], allowed_energy)

    def calculate_discharge_amount(self, context: dict) -> float:
        """
        Calculate discharge amount limited by power and SOC.

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
        return allowed_energy

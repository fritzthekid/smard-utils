"""
Battery Management System.

Orchestrates battery control using pluggable strategies for profit optimization.
"""

from abc import ABC, abstractmethod
import numpy as np


class BMSStrategy(ABC):
    """Abstract strategy for battery management control decisions."""

    def __init__(self, basic_data_set: dict):
        """
        Initialize strategy with configuration.

        Args:
            basic_data_set: Configuration dictionary
        """
        self.basic_data_set = basic_data_set

    @abstractmethod
    def should_charge(self, context: dict) -> bool:
        """
        Decide if battery should charge.

        Args:
            context: Dict with keys: index, renew, demand, price, avg_price,
                    current_storage, capacity, soc, timestamp, resolution, power_limit

        Returns:
            True if battery should charge
        """
        pass

    @abstractmethod
    def should_discharge(self, context: dict) -> bool:
        """
        Decide if battery should discharge.

        Args:
            context: Decision context (see should_charge)

        Returns:
            True if battery should discharge
        """
        pass

    @abstractmethod
    def should_export(self, context: dict) -> bool:
        """
        Decide if excess energy should be exported to grid.

        Args:
            context: Decision context (see should_charge)

        Returns:
            True if should export excess
        """
        pass

    @abstractmethod
    def calculate_charge_amount(self, context: dict) -> float:
        """
        Calculate how much energy to charge.

        Args:
            context: Decision context (see should_charge)

        Returns:
            Energy to charge (kWh)
        """
        pass

    @abstractmethod
    def calculate_discharge_amount(self, context: dict) -> float:
        """
        Calculate how much energy to discharge.

        Args:
            context: Decision context (see should_charge)

        Returns:
            Energy to discharge (kWh)
        """
        pass


class BatteryManagementSystem:
    """Core BMS - orchestrates battery control using a strategy."""

    def __init__(self, strategy: BMSStrategy, battery, driver):
        """
        Initialize BMS with strategy, battery, and data driver.

        Args:
            strategy: BMSStrategy instance for control decisions
            battery: Battery instance for physical simulation
            driver: EnergyDriver instance for data access
        """
        self.strategy = strategy
        self.battery = battery
        self.driver = driver
        self.export_flags = np.full(len(driver), False, dtype=bool)

    def initialize(self):
        """Setup before simulation (called once before loop)."""
        if hasattr(self.strategy, 'setup_price_array'):
            self.strategy.setup_price_array(self.driver.data, self.driver.resolution)
        # Initialize price array with first 24 hours (for DynamicDischargeStrategy)
        if hasattr(self.strategy, '_update_price_array'):
            self.strategy._update_price_array(0)

    def step(self, index: int, price: float, avg_price: float) -> dict:
        """
        Execute one simulation timestep.

        Args:
            index: Timestep index
            price: Current electricity price (€/kWh)
            avg_price: Average/reference price (€/kWh)

        Returns:
            Dict with keys: storage_kwh, soc, stored_kwh, net_discharge, loss_kwh,
                           export_kwh, residual_kwh, price, avg_price
        """
        renew, demand = self.driver.get_timestep(index)

        # Build context for strategy
        context = {
            'index': index,
            'renew': renew,
            'demand': demand,
            'price': price,
            'avg_price': avg_price,
            'current_storage': self.battery.current_storage,
            'capacity': self.battery.capacity_kwh,
            'soc': self.battery.soc(),
            'timestamp': self.driver.data.index[index],
            'resolution': self.driver.resolution,
            'power_limit': self.battery.p_max_kw
        }

        # Strategy decides actions using if-elif-elif-else tree (matches original logic)
        export_amount = 0.0

        if self.strategy.should_discharge(context):
            # Case 1: Discharge battery
            discharge_amount = self.strategy.calculate_discharge_amount(context)
            result = self.battery.execute(
                discharge_kwh=discharge_amount,
                dt_h=self.driver.resolution
            )
            # Export ALL renewable + battery discharge
            export_amount = renew + result['net_discharge']
            self.export_flags[index] = True

        elif self.strategy.should_charge(context):
            # Case 2: Charge battery
            charge_amount = self.strategy.calculate_charge_amount(context)
            result = self.battery.execute(
                charge_kwh=charge_amount,
                dt_h=self.driver.resolution
            )
            remaining_renew = renew - charge_amount
            # Only export leftover if profitable (price > 0 and control permits)
            if remaining_renew > 0 and self.strategy.should_export(context):
                export_amount = remaining_renew
                self.export_flags[index] = True
            else:
                export_amount = 0  # Energy wasted!

        elif self.strategy.should_export(context):
            # Case 3: Export without battery action
            result = self.battery.execute(dt_h=self.driver.resolution)
            export_amount = max(0, renew)
            if export_amount > 0:
                self.export_flags[index] = True
        else:
            # Case 4: Don't export - energy wasted!
            result = self.battery.execute(dt_h=self.driver.resolution)
            export_amount = 0

        # Calculate residual demand (unmet demand)
        # demand can be negative (convention: consumption is negative)
        residual_kwh = max(0.0, abs(demand) - renew - result['net_discharge'])

        return {
            **result,
            'export_kwh': export_amount,
            'residual_kwh': residual_kwh,
            'price': price,
            'avg_price': avg_price
        }

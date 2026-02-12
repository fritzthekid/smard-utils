"""
Tests for core/bms.py - Battery Management System.
"""

import pytest
import pandas as pd
import numpy as np
from smard_utils.core.bms import BatteryManagementSystem, BMSStrategy
from smard_utils.core.battery import Battery
from smard_utils.core.driver import EnergyDriver


class MockStrategy(BMSStrategy):
    """Mock strategy for testing."""

    def __init__(self, basic_data_set):
        super().__init__(basic_data_set)
        self.charge_flag = False
        self.discharge_flag = False
        self.export_flag = True

    def should_charge(self, context):
        return self.charge_flag

    def should_discharge(self, context):
        return self.discharge_flag

    def should_export(self, context):
        return self.export_flag

    def calculate_charge_amount(self, context):
        return min(50, context['renew'])

    def calculate_discharge_amount(self, context):
        return min(50, context['current_storage'])


class MockDriver(EnergyDriver):
    """Mock driver for testing."""

    def __init__(self, basic_data_set):
        super().__init__(basic_data_set)
        self.resolution = 1.0

    def load_data(self, data_source):
        # Create simple test data
        dates = pd.date_range('2024-01-01', periods=24, freq='h')
        self._data = pd.DataFrame({
            'my_renew': np.ones(24) * 100,  # 100 kWh renewable each hour
            'my_demand': np.zeros(24),  # No demand
        }, index=dates)
        return self._data

    def get_timestep(self, index):
        return self._data['my_renew'].iloc[index], self._data['my_demand'].iloc[index]


class TestBMS:
    """Test suite for BatteryManagementSystem."""

    def test_bms_initialization(self):
        """Test BMS initializes correctly."""
        strategy = MockStrategy({})
        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        driver = MockDriver({})
        driver.load_data(None)

        bms = BatteryManagementSystem(strategy, battery, driver)

        assert bms.strategy == strategy
        assert bms.battery == battery
        assert bms.driver == driver
        assert len(bms.export_flags) == 24

    def test_bms_case1_discharge(self):
        """Test BMS case 1: discharge battery."""
        strategy = MockStrategy({})
        strategy.discharge_flag = True  # Enable discharge

        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        driver = MockDriver({})
        driver.load_data(None)

        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        # Execute one step
        result = bms.step(0, price=0.15, avg_price=0.10)

        # Should discharge and export renewable + discharge
        assert result['export_kwh'] > 100  # renewable + battery discharge
        assert result['net_discharge'] > 0
        assert bms.export_flags[0] == True

    def test_bms_case2_charge(self):
        """Test BMS case 2: charge battery."""
        strategy = MockStrategy({})
        strategy.charge_flag = True  # Enable charge
        strategy.export_flag = False  # Disable export

        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        driver = MockDriver({})
        driver.load_data(None)

        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        # Execute one step
        result = bms.step(0, price=0.05, avg_price=0.10)

        # Should charge and not export leftover (export_flag is False)
        assert result['stored_kwh'] > 0
        assert result['export_kwh'] == 0  # No export because should_export() is False
        assert bms.export_flags[0] == False

    def test_bms_case2_charge_with_export(self):
        """Test BMS case 2: charge battery with export of leftover."""
        strategy = MockStrategy({})
        strategy.charge_flag = True  # Enable charge
        strategy.export_flag = True  # Enable export

        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        driver = MockDriver({})
        driver.load_data(None)

        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        # Execute one step
        result = bms.step(0, price=0.05, avg_price=0.10)

        # Should charge and export leftover
        assert result['stored_kwh'] > 0
        assert result['export_kwh'] > 0  # Leftover renewable exported
        assert bms.export_flags[0] == True

    def test_bms_case3_export_only(self):
        """Test BMS case 3: export without battery action."""
        strategy = MockStrategy({})
        strategy.export_flag = True  # Enable export

        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        driver = MockDriver({})
        driver.load_data(None)

        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        # Execute one step
        result = bms.step(0, price=0.10, avg_price=0.10)

        # Should export renewable without battery action
        assert result['export_kwh'] == 100  # All renewable
        assert result['stored_kwh'] == 0
        assert result['net_discharge'] == 0
        assert bms.export_flags[0] == True

    def test_bms_case4_no_export(self):
        """Test BMS case 4: don't export (energy wasted)."""
        strategy = MockStrategy({})
        strategy.export_flag = False  # Disable export

        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        driver = MockDriver({})
        driver.load_data(None)

        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        # Execute one step
        result = bms.step(0, price=0.10, avg_price=0.10)

        # Should not export (energy wasted)
        assert result['export_kwh'] == 0
        assert result['stored_kwh'] == 0
        assert result['net_discharge'] == 0
        assert bms.export_flags[0] == False

    def test_bms_residual_demand(self):
        """Test BMS calculates residual demand correctly."""
        strategy = MockStrategy({})

        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        driver = MockDriver({})
        driver.load_data(None)

        # Modify driver to have demand
        driver._data['my_demand'] = -150  # 150 kWh demand

        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        # Execute one step
        result = bms.step(0, price=0.10, avg_price=0.10)

        # Renewable (100) < Demand (150), so residual should be ~50
        assert result['residual_kwh'] > 0
        assert result['residual_kwh'] == pytest.approx(50, rel=0.1)

    def test_bms_export_flags_tracking(self):
        """Test BMS correctly tracks export flags."""
        strategy = MockStrategy({})
        strategy.export_flag = True

        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        driver = MockDriver({})
        driver.load_data(None)

        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        # Execute multiple steps
        for i in range(10):
            bms.step(i, price=0.10, avg_price=0.10)

        # Should have tracked exports
        assert bms.export_flags[:10].sum() == 10
        assert bms.export_flags[10:].sum() == 0

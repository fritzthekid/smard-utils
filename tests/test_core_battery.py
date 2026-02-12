"""
Tests for core/battery.py - Physical battery model.
"""

import pytest
from smard_utils.core.battery import Battery


class TestBattery:
    """Test suite for Battery class."""

    def test_battery_initialization(self):
        """Test battery initializes with correct parameters."""
        basic_data_set = {
            "efficiency_charge": 0.96,
            "efficiency_discharge": 0.96,
            "min_soc": 0.05,
            "max_soc": 0.95,
        }

        battery = Battery(basic_data_set, capacity_kwh=1000, p_max_kw=500)

        assert battery.capacity_kwh == 1000
        assert battery.p_max_kw == 500
        assert battery.current_storage == 500  # 50% initial SOC
        assert battery.efficiency_charge == 0.96
        assert battery.efficiency_discharge == 0.96

    def test_battery_soc_calculation(self):
        """Test state of charge calculation."""
        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        battery.current_storage = 750

        assert battery.soc() == 0.75

    def test_battery_soc_zero_capacity(self):
        """Test SOC with zero capacity doesn't raise error."""
        battery = Battery({}, capacity_kwh=0, p_max_kw=0)

        # Should return 0 instead of raising ZeroDivisionError
        assert battery.soc() == 0.0

    def test_battery_charge(self):
        """Test battery charging."""
        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        battery.current_storage = 400  # 40% SOC

        result = battery.execute(charge_kwh=100, dt_h=1.0)

        # Should have charged (with losses)
        assert result['storage_kwh'] > 400
        assert result['stored_kwh'] > 0
        assert result['net_discharge'] == 0
        assert result['loss_kwh'] > 0  # I²R losses

    def test_battery_discharge(self):
        """Test battery discharging."""
        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        battery.current_storage = 600  # 60% SOC

        result = battery.execute(discharge_kwh=100, dt_h=1.0)

        # Should have discharged (with losses)
        assert result['storage_kwh'] < 600
        assert result['net_discharge'] > 0
        assert result['stored_kwh'] == 0
        assert result['loss_kwh'] > 0  # I²R losses

    def test_battery_self_discharge(self):
        """Test battery self-discharge over time."""
        basic_data_set = {"battery_discharge": 0.001}  # 0.1% per hour
        battery = Battery(basic_data_set, capacity_kwh=1000, p_max_kw=500)
        battery.current_storage = 500

        # Execute with no charge/discharge
        result = battery.execute(dt_h=1.0)

        # Should have self-discharged
        assert result['storage_kwh'] < 500
        assert result['storage_kwh'] == pytest.approx(499.5, rel=1e-3)

    def test_battery_soc_limits(self):
        """Test battery respects SOC limits."""
        basic_data_set = {"min_soc": 0.1, "max_soc": 0.9}
        battery = Battery(basic_data_set, capacity_kwh=1000, p_max_kw=500)

        # Try to discharge below min SOC
        battery.current_storage = 150  # 15% SOC
        result = battery.execute(discharge_kwh=200, dt_h=1.0)

        # Should not go below min_soc
        assert result['storage_kwh'] >= 100  # 10% of 1000

    def test_battery_power_limit(self):
        """Test battery respects power limits."""
        battery = Battery({}, capacity_kwh=10000, p_max_kw=100)
        battery.current_storage = 5000

        # Try to discharge more than power limit allows in 1 hour
        result = battery.execute(discharge_kwh=200, dt_h=1.0)

        # Should be limited by power (100 kW * 1h = 100 kWh)
        # Plus losses, so net discharge should be less than 100
        assert result['net_discharge'] < 100

    def test_battery_energy_conservation(self):
        """Test energy conservation (charge + losses = input)."""
        battery = Battery({}, capacity_kwh=1000, p_max_kw=500)
        initial_storage = battery.current_storage

        charge_amount = 50
        result = battery.execute(charge_kwh=charge_amount, dt_h=1.0)

        # Energy stored + losses should approximately equal input
        # (accounting for efficiency and I²R losses)
        stored = result['storage_kwh'] - initial_storage
        total_accounted = stored + result['loss_kwh']

        # Should be less than input due to efficiency
        assert total_accounted < charge_amount
        assert stored > 0

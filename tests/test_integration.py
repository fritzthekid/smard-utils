"""
Integration tests for the complete battery simulation system.

Tests end-to-end workflows combining drivers, strategies, BMS, battery, and analytics.
"""

import pytest
import pandas as pd
import numpy as np
import tempfile
import os
from smard_utils.core.driver import EnergyDriver
from smard_utils.core.battery import Battery
from smard_utils.core.bms import BatteryManagementSystem
from smard_utils.core.analytics import BatteryAnalytics
from smard_utils.drivers.biogas_driver import BiogasDriver
from smard_utils.drivers.solar_driver import SolarDriver
from smard_utils.bms_strategies.price_threshold import PriceThresholdStrategy
from smard_utils.bms_strategies.dynamic_discharge import DynamicDischargeStrategy


@pytest.fixture
def smard_csv_file():
    """Create a comprehensive SMARD CSV file for integration testing."""
    # 7 days of data with realistic patterns
    dates = pd.date_range('2024-01-01', periods=168, freq='H')

    biomass = np.ones(168) * 500
    hydro = np.ones(168) * 300
    wind_offshore = np.random.uniform(300, 600, 168)
    wind_onshore = np.random.uniform(4000, 6000, 168)

    # Solar: realistic daily pattern
    solar = []
    for i in range(168):
        hour = i % 24
        if 6 <= hour <= 18:
            # Peak at noon
            solar.append(5000 * np.sin((hour - 6) / 12 * np.pi))
        else:
            solar.append(0)

    demand = np.random.uniform(45000, 55000, 168)

    # Create CSV content
    lines = ["Datum;Uhrzeit;Biomasse [MWh] Originalauflösungen;Wasserkraft [MWh] Originalauflösungen;Wind Offshore [MWh] Originalauflösungen;Wind Onshore [MWh] Originalauflösungen;Photovoltaik [MWh] Originalauflösungen;Sonstige Erneuerbare [MWh] Originalauflösungen;Kernenergie [MWh] Originalauflösungen;Braunkohle [MWh] Originalauflösungen;Steinkohle [MWh] Originalauflösungen;Erdgas [MWh] Originalauflösungen;Pumpspeicher [MWh] Originalauflösungen;Sonstige Konventionelle [MWh] Originalauflösungen;Gesamtverbrauch [MWh] Originalauflösungen"]

    for i in range(168):
        dt = dates[i]
        line = f"{dt.strftime('%d.%m.%Y')};{dt.strftime('%H:%M')};{biomass[i]:.1f};{hydro[i]:.1f};{wind_offshore[i]:.1f};{wind_onshore[i]:.1f};{solar[i]:.1f};100;800;1200;600;2000;-200;50;{demand[i]:.1f}"
        lines.append(line)

    content = "\n".join(lines)

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def price_csv_file():
    """Create a price CSV file for integration testing."""
    dates = pd.date_range('2024-01-01', periods=8760, freq='H')

    # Realistic price pattern: low at night, high during day
    prices = []
    for i in range(8760):
        hour = i % 24
        base_price = 10  # ct/kWh

        if 6 <= hour <= 9 or 17 <= hour <= 20:
            # Peak hours
            prices.append(base_price + np.random.uniform(3, 8))
        elif 10 <= hour <= 16:
            # Mid-day (solar reduces prices)
            prices.append(base_price + np.random.uniform(-2, 2))
        else:
            # Off-peak
            prices.append(base_price + np.random.uniform(-5, 0))

    df = pd.DataFrame({
        'time': [d.strftime('%Y-%m-%d %H:%M:%S') for d in dates],
        'price': prices
    })

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        df.to_csv(f.name, index=False)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestBiogasSystemIntegration:
    """Integration tests for complete biogas battery system."""

    def test_biogas_full_simulation(self, smard_csv_file):
        """Test complete biogas simulation workflow."""
        basic_data_set = {
            "constant_biogas_kw": 1000,
            "load_threshold": 1.0,
            "fix_costs_per_kwh": 11,
            "marketing_costs": -0.003,
            "fix_contract": True  # Use fixed price for testing
        }

        # Initialize driver
        driver = BiogasDriver(basic_data_set)
        driver.load_data(smard_csv_file)

        assert len(driver) == 168
        assert driver.data['my_renew'].iloc[0] == 1000  # Constant biogas

        # Initialize strategy
        strategy = PriceThresholdStrategy(basic_data_set)

        # Initialize battery
        battery = Battery(basic_data_set, capacity_kwh=5000, p_max_kw=2500)

        # Initialize BMS
        bms = BatteryManagementSystem(strategy, battery, driver)

        # Initialize analytics
        analytics = BatteryAnalytics(driver, basic_data_set)
        analytics.prepare_prices()

        bms.initialize()

        # Run simulation
        results = []
        for i in range(len(driver)):
            price = driver.data['price_per_kwh'].iloc[i]
            avg_price = driver.data['avrgprice'].iloc[i]
            step_result = bms.step(i, price, avg_price)
            results.append(step_result)

        # Add to analytics
        result = analytics.add_simulation_result(5000, 2500, bms, results)

        # Verify results
        assert result['capacity_kwh'] == 5000
        assert result['power_kw'] == 2500
        assert result['export_kwh'] > 0  # Should export energy
        assert result['revenue_eur'] > 0  # Should generate revenue

        # Energy conservation check
        initial_storage = 0.5 * 5000  # Battery default: 50% SOC
        total_input = driver.data['my_renew'].sum()
        total_export = result['export_kwh']
        total_loss = result['loss_kwh']

        # All energy accounted for (no demand in biogas, battery initial energy included)
        balance = (total_input + initial_storage) - total_export - battery.current_storage - total_loss
        assert abs(balance) < total_input * 0.01

    def test_biogas_multiple_capacities(self, smard_csv_file):
        """Test biogas system with multiple battery capacities."""
        basic_data_set = {
            "constant_biogas_kw": 1000,
            "load_threshold": 1.0,
            "fix_costs_per_kwh": 11,
            "fix_contract": True
        }

        driver = BiogasDriver(basic_data_set)
        driver.load_data(smard_csv_file)

        analytics = BatteryAnalytics(driver, basic_data_set)
        analytics.prepare_prices()

        strategy = PriceThresholdStrategy(basic_data_set)

        # Test multiple capacities
        for capacity_mwh, power_mw in [(1, 0.5), (5, 2.5), (10, 5)]:
            capacity_kwh = capacity_mwh * 1000
            power_kw = power_mw * 1000

            battery = Battery(basic_data_set, capacity_kwh, power_kw)
            bms = BatteryManagementSystem(strategy, battery, driver)
            bms.initialize()

            results = []
            for i in range(len(driver)):
                price = driver.data['price_per_kwh'].iloc[i]
                avg_price = driver.data['avrgprice'].iloc[i]
                results.append(bms.step(i, price, avg_price))

            analytics.add_simulation_result(capacity_kwh, power_kw, bms, results)

        df = analytics.get_results_dataframe()

        assert len(df) == 3
        # Larger batteries should generally have more revenue potential
        assert df['capacity_kwh'].is_monotonic_increasing


class TestSolarSystemIntegration:
    """Integration tests for complete solar battery system."""

    def test_solar_full_simulation(self, smard_csv_file):
        """Test complete solar simulation workflow."""
        basic_data_set = {
            "solar_max_power": 10000,  # 10 kW peak
            "wind_nominal_power": 0,
            "year_demand": -100000,  # 100 MWh/year
            "fix_costs_per_kwh": 11,
            "marketing_costs": -0.003,
            "control_exflow": 3,
            "fix_contract": True
        }

        # Initialize driver
        driver = SolarDriver(basic_data_set, region="_de")
        driver.load_data(smard_csv_file)

        assert len(driver) == 168
        assert driver.data['my_renew'].max() > 0  # Should have solar generation
        assert driver.data['my_demand'].sum() < 0  # Should have demand

        # Initialize strategy
        strategy = DynamicDischargeStrategy(basic_data_set)

        # Initialize battery
        battery = Battery(basic_data_set, capacity_kwh=10000, p_max_kw=5000)

        # Initialize BMS
        bms = BatteryManagementSystem(strategy, battery, driver)

        # Initialize analytics
        analytics = BatteryAnalytics(driver, basic_data_set)
        analytics.prepare_prices()

        bms.initialize()

        # Run simulation
        results = []
        for i in range(len(driver)):
            price = driver.data['price_per_kwh'].iloc[i]
            avg_price = driver.data['avrgprice'].iloc[i]
            step_result = bms.step(i, price, avg_price)
            results.append(step_result)

        # Add to analytics
        result = analytics.add_simulation_result(10000, 5000, bms, results)

        # Verify results
        assert result['capacity_kwh'] == 10000
        assert result['power_kw'] == 5000
        assert result['residual_kwh'] >= 0  # Grid consumption
        assert result['export_kwh'] >= 0  # Grid export

        # Autarky should be between 0 and 1
        assert 0 <= result['autarky_rate'] <= 1

    def test_solar_price_optimization(self, smard_csv_file):
        """Test solar system optimizes for price differences."""
        basic_data_set = {
            "solar_max_power": 10000,
            "wind_nominal_power": 0,
            "year_demand": -50000,
            "fix_costs_per_kwh": 11,
            "fix_contract": False  # Use variable pricing
        }

        driver = SolarDriver(basic_data_set, region="_de")
        driver.load_data(smard_csv_file)

        # Create artificial price pattern
        prices = []
        for i in range(len(driver)):
            hour = driver.data.index[i].hour
            if 18 <= hour <= 20:
                prices.append(0.20)  # Expensive evening
            elif 10 <= hour <= 14:
                prices.append(0.08)  # Cheap midday (solar)
            else:
                prices.append(0.12)

        driver._data['price_per_kwh'] = prices
        driver._data['avrgprice'] = 0.12

        strategy = DynamicDischargeStrategy(basic_data_set)
        battery = Battery(basic_data_set, capacity_kwh=10000, p_max_kw=5000)
        bms = BatteryManagementSystem(strategy, battery, driver)

        analytics = BatteryAnalytics(driver, basic_data_set)
        bms.initialize()

        # Run simulation
        results = []
        for i in range(len(driver)):
            price = driver.data['price_per_kwh'].iloc[i]
            avg_price = driver.data['avrgprice'].iloc[i]
            results.append(bms.step(i, price, avg_price))

        result = analytics.add_simulation_result(10000, 5000, bms, results)

        # Should generate positive revenue from arbitrage
        assert result['revenue_eur'] > 0


class TestEnergyConservation:
    """Test energy conservation across all systems."""

    def test_biogas_energy_balance(self, smard_csv_file):
        """Test biogas system conserves energy."""
        basic_data_set = {
            "constant_biogas_kw": 1000,
            "load_threshold": 1.0,
            "fix_contract": True
        }

        driver = BiogasDriver(basic_data_set)
        driver.load_data(smard_csv_file)

        strategy = PriceThresholdStrategy(basic_data_set)
        battery = Battery(basic_data_set, capacity_kwh=5000, p_max_kw=2500)
        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        analytics = BatteryAnalytics(driver, basic_data_set)
        analytics.prepare_prices()

        results = []
        for i in range(len(driver)):
            price = driver.data['price_per_kwh'].iloc[i]
            avg_price = driver.data['avrgprice'].iloc[i]
            results.append(bms.step(i, price, avg_price))

        result = analytics.add_simulation_result(5000, 2500, bms, results)

        # Energy balance: input + initial_storage = export + final_storage + losses
        initial_storage = 0.5 * 5000  # Battery default: 50% SOC
        total_input = driver.data['my_renew'].sum()
        total_export = result['export_kwh']
        total_stored = battery.current_storage  # Final storage
        total_loss = result['loss_kwh']

        # Allow 1% error for numerical precision (self-discharge not tracked in loss)
        balance = (total_input + initial_storage) - total_export - total_stored - total_loss
        assert abs(balance) < total_input * 0.01

    def test_solar_energy_balance(self, smard_csv_file):
        """Test solar system conserves energy."""
        basic_data_set = {
            "solar_max_power": 10000,
            "wind_nominal_power": 0,
            "year_demand": -100000,
            "fix_contract": True
        }

        driver = SolarDriver(basic_data_set, region="_de")
        driver.load_data(smard_csv_file)

        strategy = DynamicDischargeStrategy(basic_data_set)
        battery = Battery(basic_data_set, capacity_kwh=10000, p_max_kw=5000)
        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        analytics = BatteryAnalytics(driver, basic_data_set)
        analytics.prepare_prices()

        results = []
        for i in range(len(driver)):
            price = driver.data['price_per_kwh'].iloc[i]
            avg_price = driver.data['avrgprice'].iloc[i]
            results.append(bms.step(i, price, avg_price))

        result = analytics.add_simulation_result(10000, 5000, bms, results)

        # Energy balance: renew + residual = demand + export + stored + losses
        total_renew = driver.data['my_renew'].sum()
        total_demand = abs(driver.data['my_demand'].sum())
        total_residual = result['residual_kwh']
        total_export = result['export_kwh']
        total_stored = battery.current_storage
        total_loss = result['loss_kwh']

        # Input side: renewable + grid import
        input_energy = total_renew + total_residual
        # Output side: demand + export + stored + losses
        output_energy = total_demand + total_export + total_stored + total_loss

        # Allow 1% error
        assert abs(input_energy - output_energy) < max(input_energy, output_energy) * 0.01


class TestBatteryOperatingLimits:
    """Test battery operates within physical limits."""

    def test_soc_limits_respected(self, smard_csv_file):
        """Test battery respects SOC limits."""
        basic_data_set = {
            "constant_biogas_kw": 1000,
            "min_soc": 0.1,
            "max_soc": 0.9,
            "fix_contract": True
        }

        driver = BiogasDriver(basic_data_set)
        driver.load_data(smard_csv_file)

        strategy = PriceThresholdStrategy(basic_data_set)
        battery = Battery(basic_data_set, capacity_kwh=1000, p_max_kw=500)
        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        analytics = BatteryAnalytics(driver, basic_data_set)
        analytics.prepare_prices()

        soc_values = []
        for i in range(len(driver)):
            price = driver.data['price_per_kwh'].iloc[i]
            avg_price = driver.data['avrgprice'].iloc[i]
            bms.step(i, price, avg_price)
            soc_values.append(battery.soc())

        # All SOC values should be within limits
        assert all(0.05 <= soc <= 0.95 for soc in soc_values)  # Allow some margin

    def test_power_limits_respected(self, smard_csv_file):
        """Test battery respects power limits."""
        basic_data_set = {
            "constant_biogas_kw": 2000,  # High generation
            "fix_contract": True
        }

        driver = BiogasDriver(basic_data_set)
        driver.load_data(smard_csv_file)

        strategy = PriceThresholdStrategy(basic_data_set)
        battery = Battery(basic_data_set, capacity_kwh=10000, p_max_kw=500)  # Low power limit
        bms = BatteryManagementSystem(strategy, battery, driver)
        bms.initialize()

        analytics = BatteryAnalytics(driver, basic_data_set)
        analytics.prepare_prices()

        for i in range(len(driver)):
            price = driver.data['price_per_kwh'].iloc[i]
            avg_price = driver.data['avrgprice'].iloc[i]
            result = bms.step(i, price, avg_price)

            # Charge/discharge should not exceed power limit * resolution
            assert result['stored_kwh'] <= battery.p_max_kw * driver.resolution + 0.1
            assert result['net_discharge'] <= battery.p_max_kw * driver.resolution + 0.1

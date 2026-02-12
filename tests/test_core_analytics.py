"""
Tests for core/analytics.py - Battery simulation analytics.
"""

import pytest
import pandas as pd
import numpy as np
import tempfile
import os
from smard_utils.core.analytics import BatteryAnalytics
from smard_utils.core.driver import EnergyDriver


class MockDriver(EnergyDriver):
    """Mock driver for testing."""

    def __init__(self, basic_data_set):
        super().__init__(basic_data_set)
        self.resolution = 1.0

    def load_data(self, data_source):
        dates = pd.date_range('2024-01-01', periods=24, freq='h')
        self._data = pd.DataFrame({
            'my_renew': np.ones(24) * 100,
            'my_demand': np.ones(24) * 80,
        }, index=dates)
        return self._data

    def get_timestep(self, index):
        return self._data['my_renew'].iloc[index], self._data['my_demand'].iloc[index]


class MockBMS:
    """Mock BMS for testing."""

    def __init__(self):
        self.export_flags = np.array([1, 0, 1, 0] * 6)  # 24 hours


class TestBatteryAnalytics:
    """Test suite for BatteryAnalytics."""

    def test_analytics_initialization(self):
        """Test analytics initializes correctly."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 12})

        assert analytics.driver == driver
        assert analytics.costs_per_kwh == 0.12
        assert len(analytics.simulation_results) == 0

    def test_prepare_prices_fixed_contract(self):
        """Test price preparation with fixed contract."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {
            "fix_contract": True,
            "fix_costs_per_kwh": 10
        })
        analytics.prepare_prices()

        assert 'price_per_kwh' in driver.data.columns
        assert 'avrgprice' in driver.data.columns
        assert driver.data['price_per_kwh'].iloc[0] == 0.10
        assert driver.data['avrgprice'].iloc[0] == 0.10

    def test_prepare_prices_no_year(self):
        """Test price preparation without year falls back to fixed price."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})
        analytics.prepare_prices()

        assert 'price_per_kwh' in driver.data.columns
        assert driver.data['price_per_kwh'].iloc[0] == 0.11

    def test_prepare_prices_missing_file(self):
        """Test price preparation with missing price file."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {
            "year": 9999,  # Non-existent year
            "fix_costs_per_kwh": 11
        })
        analytics.prepare_prices()

        # Should fall back to fixed price
        assert 'price_per_kwh' in driver.data.columns
        assert driver.data['price_per_kwh'].iloc[0] == 0.11

    def test_prepare_prices_with_marketing_costs(self):
        """Test price preparation includes marketing costs."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {
            "fix_contract": True,
            "fix_costs_per_kwh": 10,
            "marketing_costs": 0.02
        })
        analytics.prepare_prices()

        assert driver.data['price_per_kwh'].iloc[0] == pytest.approx(0.12)  # 0.10 + 0.02

    def test_add_simulation_result(self):
        """Test adding simulation results."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})
        analytics.prepare_prices()

        # Create mock step results
        step_results = []
        for i in range(24):
            step_results.append({
                'residual_kwh': 10.0,
                'export_kwh': 90.0,
                'loss_kwh': 5.0,
                'price': 0.15
            })

        bms = MockBMS()
        result = analytics.add_simulation_result(
            capacity=1000, power=500, bms=bms, step_results=step_results
        )

        assert result['capacity_kwh'] == 1000
        assert result['power_kw'] == 500
        assert result['residual_kwh'] == 240  # 10 * 24
        assert result['export_kwh'] == 2160  # 90 * 24
        assert result['loss_kwh'] == 120  # 5 * 24
        assert result['export_hours'] == 12  # 12 hours exporting (resolution 1.0)
        assert len(analytics.simulation_results) == 1

    def test_autarky_rate_calculation(self):
        """Test autarky rate calculation."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})
        analytics.prepare_prices()

        # Scenario: 80 kWh demand, 10 kWh residual -> 87.5% autarky
        step_results = []
        for i in range(24):
            step_results.append({
                'residual_kwh': 10.0,
                'export_kwh': 70.0,
                'loss_kwh': 0.0,
                'price': 0.15
            })

        bms = MockBMS()
        result = analytics.add_simulation_result(
            capacity=1000, power=500, bms=bms, step_results=step_results
        )

        total_demand = 80 * 24  # from MockDriver
        total_residual = 10 * 24
        expected_autarky = 1.0 - (total_residual / total_demand)

        assert result['autarky_rate'] == pytest.approx(expected_autarky, rel=0.01)

    def test_revenue_calculation(self):
        """Test revenue and cost calculations."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {
            "fix_costs_per_kwh": 11,
            "marketing_costs": -0.003
        })
        analytics.prepare_prices()

        step_results = []
        for i in range(24):
            step_results.append({
                'residual_kwh': 10.0,
                'export_kwh': 90.0,
                'loss_kwh': 5.0,
                'price': 0.15
            })

        bms = MockBMS()
        result = analytics.add_simulation_result(
            capacity=1000, power=500, bms=bms, step_results=step_results
        )

        # Revenue = export * (price - marketing_cost)
        expected_revenue = 90 * 24 * (0.15 - (-0.003))
        assert result['revenue_eur'] == pytest.approx(expected_revenue, rel=0.01)

        # Spot cost = residual * price
        expected_spot_cost = 10 * 24 * 0.15
        assert result['spot_cost_eur'] == pytest.approx(expected_spot_cost, rel=0.01)

        # Fix cost = residual * fix_costs_per_kwh
        expected_fix_cost = 10 * 24 * 0.11
        assert result['fix_cost_eur'] == pytest.approx(expected_fix_cost, rel=0.01)

    def test_get_results_dataframe(self):
        """Test getting results as DataFrame."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})
        analytics.prepare_prices()

        # Add multiple simulations
        for capacity in [1000, 2000, 3000]:
            step_results = [
                {'residual_kwh': 10, 'export_kwh': 90, 'loss_kwh': 5, 'price': 0.15}
                for _ in range(24)
            ]
            bms = MockBMS()
            analytics.add_simulation_result(capacity, capacity // 2, bms, step_results)

        df = analytics.get_results_dataframe()

        assert len(df) == 3
        assert 'capacity_kwh' in df.columns
        assert 'revenue_eur' in df.columns
        assert df['capacity_kwh'].iloc[0] == 1000

    def test_calculate_capacity_roi(self):
        """Test ROI calculation per capacity unit."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})
        analytics.prepare_prices()

        # Add baseline (0 capacity) + two simulations
        for i, capacity in enumerate([0, 1000, 2000]):
            step_results = []
            for _ in range(24):
                step_results.append({
                    'residual_kwh': 10,
                    'export_kwh': 90 + i * 10,  # Increasing export
                    'loss_kwh': 5,
                    'price': 0.15
                })
            bms = MockBMS()
            analytics.add_simulation_result(capacity, capacity // 2, bms, step_results)

        df = analytics.calculate_capacity_roi()

        assert 'revenue_gain' in df.columns
        assert 'eur_per_kwh' in df.columns

        # Row 0 (zero capacity) should have zero gain
        baseline_revenue = df.iloc[0]['revenue_eur']

        # Row 1 should have gain = revenue[1] - baseline
        assert df['revenue_gain'].iloc[1] == pytest.approx(
            df['revenue_eur'].iloc[1] - baseline_revenue, rel=0.01
        )

        # Row 2 should have higher gain
        assert df['revenue_gain'].iloc[2] > df['revenue_gain'].iloc[1]

    def test_calculate_capacity_roi_empty(self):
        """Test ROI calculation with empty results."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})
        df = analytics.calculate_capacity_roi()

        assert len(df) == 0

    def test_print_summary_auto_scaling(self):
        """Test print summary with auto-scaling."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})
        analytics.prepare_prices()

        # Add small-scale simulation (should use kWh)
        step_results = [
            {'residual_kwh': 10, 'export_kwh': 90, 'loss_kwh': 5, 'price': 0.15}
            for _ in range(24)
        ]
        bms = MockBMS()
        analytics.add_simulation_result(1000, 500, bms, step_results)

        # Should not raise error
        analytics.print_summary()

    def test_print_summary_large_scale(self):
        """Test print summary with large-scale data (MWh)."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})
        analytics.prepare_prices()

        # Add large-scale simulation (should use MWh)
        step_results = [
            {'residual_kwh': 10000, 'export_kwh': 90000, 'loss_kwh': 5000, 'price': 0.15}
            for _ in range(24)
        ]
        bms = MockBMS()
        analytics.add_simulation_result(5000000, 2500000, bms, step_results)

        # Should not raise error
        analytics.print_summary()

    def test_print_summary_empty(self):
        """Test print summary with no results."""
        driver = MockDriver({})
        driver.load_data(None)

        analytics = BatteryAnalytics(driver, {"fix_costs_per_kwh": 11})

        # Should not raise error
        analytics.print_summary()

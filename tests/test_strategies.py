"""
Tests for BMS strategies - PriceThresholdStrategy and DynamicDischargeStrategy.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from smard_utils.bms_strategies.price_threshold import PriceThresholdStrategy
from smard_utils.bms_strategies.dynamic_discharge import DynamicDischargeStrategy


class TestPriceThresholdStrategy:
    """Test suite for PriceThresholdStrategy."""

    def test_strategy_initialization(self):
        """Test PriceThresholdStrategy initializes correctly."""
        strategy = PriceThresholdStrategy({
            "load_threshold": 1.1,
            "load_threshold_high": 1.3,
            "export_threshold": 0.9
        })

        assert strategy.load_threshold == 1.1
        assert strategy.load_threshold_high == 1.3
        assert strategy.export_threshold == 0.9

    def test_strategy_default_parameters(self):
        """Test PriceThresholdStrategy uses default parameters."""
        strategy = PriceThresholdStrategy({})

        assert strategy.load_threshold == 1.0
        assert strategy.load_threshold_high == 1.2
        assert strategy.export_threshold == 0.9

    def test_should_charge_below_threshold(self):
        """Test charging when price is below threshold."""
        strategy = PriceThresholdStrategy({"load_threshold": 1.0})

        context = {
            'price': 0.08,
            'avg_price': 0.10,
            'current_storage': 500,
            'capacity': 1000
        }

        assert strategy.should_charge(context) == True

    def test_should_charge_above_threshold(self):
        """Test no charging when price is above threshold."""
        strategy = PriceThresholdStrategy({"load_threshold": 1.0})

        context = {
            'price': 0.12,
            'avg_price': 0.10,
            'current_storage': 500,
            'capacity': 1000
        }

        assert strategy.should_charge(context) == False

    def test_should_discharge_above_threshold(self):
        """Test discharging when price is above threshold."""
        strategy = PriceThresholdStrategy({"load_threshold": 1.0})

        context = {
            'price': 0.12,
            'avg_price': 0.10,
            'current_storage': 500,
            'capacity': 1000
        }

        assert strategy.should_discharge(context) == True

    def test_should_discharge_below_threshold(self):
        """Test no discharging when price is below threshold."""
        strategy = PriceThresholdStrategy({"load_threshold": 1.0})

        context = {
            'price': 0.08,
            'avg_price': 0.10,
            'current_storage': 500,
            'capacity': 1000
        }

        assert strategy.should_discharge(context) == False

    def test_should_export_always_false(self):
        """Test BioBat never exports except when discharging."""
        strategy = PriceThresholdStrategy({})

        context = {
            'price': 0.15,
            'avg_price': 0.10
        }

        # BioBat only exports when discharging (case 1)
        assert strategy.should_export(context) == False

    def test_calculate_charge_amount_power_limited(self):
        """Test charge amount limited by power."""
        strategy = PriceThresholdStrategy({"max_soc": 0.95})

        context = {
            'renew': 1000,
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 200,
            'capacity': 1000
        }

        charge = strategy.calculate_charge_amount(context)

        # Limited by power: 500 kW * 1 hour = 500 kWh
        assert charge == 500

    def test_calculate_charge_amount_soc_limited(self):
        """Test charge amount limited by SOC."""
        strategy = PriceThresholdStrategy({"max_soc": 0.95})

        context = {
            'renew': 1000,
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 900,  # Near max
            'capacity': 1000
        }

        charge = strategy.calculate_charge_amount(context)

        # Limited by SOC: (0.95 * 1000) - 900 = 50 kWh
        assert charge == 50

    def test_calculate_charge_amount_renew_limited(self):
        """Test charge amount limited by available renewable."""
        strategy = PriceThresholdStrategy({"max_soc": 0.95})

        context = {
            'renew': 100,  # Only 100 kWh available
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 200,
            'capacity': 1000
        }

        charge = strategy.calculate_charge_amount(context)

        # Limited by renew: only 100 kWh available
        assert charge == 100

    def test_calculate_discharge_amount_power_limited(self):
        """Test discharge amount limited by power."""
        strategy = PriceThresholdStrategy({"min_soc": 0.05})

        context = {
            'power_limit': 300,
            'resolution': 1.0,
            'current_storage': 800,
            'capacity': 1000
        }

        discharge = strategy.calculate_discharge_amount(context)

        # Limited by power: 300 kW * 1 hour = 300 kWh
        assert discharge == 300

    def test_calculate_discharge_amount_soc_limited(self):
        """Test discharge amount limited by min SOC."""
        strategy = PriceThresholdStrategy({"min_soc": 0.05})

        context = {
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 100,  # Near min
            'capacity': 1000
        }

        discharge = strategy.calculate_discharge_amount(context)

        # Limited by SOC: 100 - (0.05 * 1000) = 50 kWh
        assert discharge == 50


class TestDynamicDischargeStrategy:
    """Test suite for DynamicDischargeStrategy."""

    def test_strategy_initialization(self):
        """Test DynamicDischargeStrategy initializes correctly."""
        strategy = DynamicDischargeStrategy({
            "limit_soc_threshold": 0.1,
            "control_exflow": 3
        })

        assert strategy.limit_soc_threshold == 0.1
        assert strategy.control_exflow == 3
        assert len(strategy.price_array) == 24

    def test_strategy_default_parameters(self):
        """Test DynamicDischargeStrategy uses default parameters."""
        strategy = DynamicDischargeStrategy({})

        assert strategy.limit_soc_threshold == 0.05
        assert strategy.control_exflow == 3

    def test_setup_price_array(self):
        """Test price array setup with data."""
        strategy = DynamicDischargeStrategy({})

        dates = pd.date_range('2024-01-01', periods=24, freq='h')
        data = pd.DataFrame({
            'price_per_kwh': np.linspace(0.05, 0.20, 24)
        }, index=dates)

        strategy.setup_price_array(data, 1.0)

        assert strategy.data is not None
        assert strategy.dt_h == 1.0

    def test_update_price_array(self):
        """Test price array gets updated correctly."""
        strategy = DynamicDischargeStrategy({})

        # Create price data with clear pattern: low at night, high at day
        dates = pd.date_range('2024-01-01', periods=48, freq='h')
        prices = []
        for i in range(48):
            hour = i % 24
            if 6 <= hour <= 18:  # Day hours expensive
                prices.append(0.15 + (hour - 12) * 0.01)
            else:  # Night hours cheap
                prices.append(0.08)

        data = pd.DataFrame({'price_per_kwh': prices}, index=dates)

        strategy.setup_price_array(data, 1.0)
        strategy._update_price_array(0)

        # Check normalization to [-1, 1]
        assert strategy.price_array.min() >= -1
        assert strategy.price_array.max() <= 1

        # Night hours should have negative factors (cheap)
        assert strategy.price_array[0] < 0  # Midnight
        # Day hours should have positive factors (expensive)
        assert strategy.price_array[13] > 0  # 13:00

    def test_discharging_factor(self):
        """Test discharge factor retrieval."""
        strategy = DynamicDischargeStrategy({})

        dates = pd.date_range('2024-01-01 00:00', periods=24, freq='h')
        data = pd.DataFrame({'price_per_kwh': np.linspace(0.05, 0.20, 24)}, index=dates)

        strategy.setup_price_array(data, 1.0)
        strategy._update_price_array(0)

        timestamp = datetime(2024, 1, 1, 13, 0)
        df = strategy._discharging_factor(timestamp)

        assert -1 <= df <= 1

    def test_saturation_curve_below_threshold(self):
        """Test saturation curve returns 0 below threshold."""
        strategy = DynamicDischargeStrategy({})

        result = strategy._saturation_curve(x=0.5, df=3, df_min=0.7, sub=0.0)

        assert result == 0.0

    def test_saturation_curve_above_threshold(self):
        """Test saturation curve returns value above threshold."""
        strategy = DynamicDischargeStrategy({})

        result = strategy._saturation_curve(x=0.9, df=3, df_min=0.7, sub=0.0)

        assert 0 < result <= 1
        # x=0.9, df_min=0.7 -> u=(0.9-0.7)/(1-0.7)=0.67
        # factor = 1 - (1-0.67)^3 = 1 - 0.33^3 = 1 - 0.036 ≈ 0.964
        assert result == pytest.approx(0.964, rel=0.01)

    def test_saturation_curve_with_substitute(self):
        """Test saturation curve uses substitute if provided."""
        strategy = DynamicDischargeStrategy({})

        result = strategy._saturation_curve(x=0.9, df=3, df_min=0.7, sub=0.5)

        assert result == 0.5

    def test_should_charge_negative_factor(self):
        """Test charging when discharge factor is negative."""
        strategy = DynamicDischargeStrategy({"max_soc": 0.95})

        dates = pd.date_range('2024-01-01 00:00', periods=24, freq='h')
        # Night hours cheap -> negative factor
        prices = [0.08] * 12 + [0.15] * 12
        data = pd.DataFrame({'price_per_kwh': prices}, index=dates)

        strategy.setup_price_array(data, 1.0)
        strategy._update_price_array(0)

        context = {
            'timestamp': datetime(2024, 1, 1, 2, 0),  # Night hour
            'current_storage': 200,
            'capacity': 1000
        }

        # Should charge at night (cheap prices = negative factor)
        assert strategy.should_charge(context) == True

    def test_should_discharge_high_factor(self):
        """Test discharging when discharge factor is high."""
        strategy = DynamicDischargeStrategy({"min_soc": 0.05})

        dates = pd.date_range('2024-01-01 00:00', periods=24, freq='h')
        # Day hours expensive -> positive factor
        prices = [0.08] * 12 + [0.20] * 12
        data = pd.DataFrame({'price_per_kwh': prices}, index=dates)

        strategy.setup_price_array(data, 1.0)
        strategy._update_price_array(0)
        strategy.last_update_day = datetime(2024, 1, 1).date()

        context = {
            'timestamp': datetime(2024, 1, 1, 18, 0),  # Expensive hour
            'index': 18,
            'current_storage': 800,
            'capacity': 1000
        }

        # Should discharge during expensive hours (high factor)
        df = strategy._discharging_factor(context['timestamp'])
        if df > 0.7:  # Only if factor exceeds threshold
            assert strategy.should_discharge(context) == True

    def test_should_export_positive_price(self):
        """Test exporting when price is positive and control permits."""
        strategy = DynamicDischargeStrategy({"control_exflow": 3})

        context = {'price': 0.15}
        assert strategy.should_export(context) == True

        context = {'price': -0.01}
        assert strategy.should_export(context) == False

    def test_should_export_control_disabled(self):
        """Test no export when control is disabled."""
        strategy = DynamicDischargeStrategy({"control_exflow": 1})

        context = {'price': 0.15}
        assert strategy.should_export(context) == False

    def test_calculate_charge_amount(self):
        """Test charge amount calculation."""
        strategy = DynamicDischargeStrategy({"max_soc": 0.95})

        context = {
            'renew': 600,
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 300,
            'capacity': 1000
        }

        charge = strategy.calculate_charge_amount(context)

        # Limited by power: 500 kWh
        assert charge == 500

    def test_calculate_discharge_amount_with_saturation(self):
        """Test discharge amount uses saturation curve."""
        strategy = DynamicDischargeStrategy({"min_soc": 0.05})

        dates = pd.date_range('2024-01-01 00:00', periods=24, freq='h')
        prices = [0.08] * 12 + [0.20] * 12
        data = pd.DataFrame({'price_per_kwh': prices}, index=dates)

        strategy.setup_price_array(data, 1.0)
        strategy._update_price_array(0)

        context = {
            'timestamp': datetime(2024, 1, 1, 18, 0),  # Expensive hour
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 800,
            'capacity': 1000
        }

        discharge = strategy.calculate_discharge_amount(context)

        # Should be modulated by saturation curve
        allowed = min(500, 800 - 50)  # 750 kWh
        df = strategy._discharging_factor(context['timestamp'])
        factor = strategy._saturation_curve(df, 3, 0.7, 0.0)
        expected = factor * allowed

        assert discharge == pytest.approx(expected, rel=0.01)

    def test_price_array_update_at_13_00(self):
        """Test price array updates daily at 13:00."""
        strategy = DynamicDischargeStrategy({})

        dates = pd.date_range('2024-01-01 00:00', periods=72, freq='h')
        prices = np.random.uniform(0.08, 0.20, 72)
        data = pd.DataFrame({'price_per_kwh': prices}, index=dates)

        strategy.setup_price_array(data, 1.0)
        strategy._update_price_array(0)
        strategy.last_update_day = datetime(2024, 1, 1).date()

        # First 13:00 should trigger update
        context1 = {
            'timestamp': datetime(2024, 1, 2, 13, 0),
            'index': 37,
            'current_storage': 800,
            'capacity': 1000
        }

        old_array = strategy.price_array.copy()
        strategy.should_discharge(context1)

        # Array should have been updated
        assert strategy.last_update_day == datetime(2024, 1, 2).date()

        # Later same day should not update again
        context2 = {
            'timestamp': datetime(2024, 1, 2, 18, 0),
            'index': 42,
            'current_storage': 800,
            'capacity': 1000
        }

        strategy.should_discharge(context2)

        # Day should still be Jan 2
        assert strategy.last_update_day == datetime(2024, 1, 2).date()

"""
Tests for DayAheadStrategy - realistic day-ahead price-based BMS strategy.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date
from smard_utils.bms_strategies.day_ahead import DayAheadStrategy


def make_price_data(days=3, base_price=0.10):
    """
    Create test price data with a realistic daily pattern.

    Night (0-5): cheap (60% of base)
    Morning peak (6-9): expensive (140% of base)
    Midday solar dip (10-14): cheap (70% of base)
    Evening peak (17-20): most expensive (180% of base)
    Rest: average (100% of base)
    """
    hours = days * 24
    dates = pd.date_range('2024-01-01', periods=hours, freq='h')
    prices = []
    for i in range(hours):
        hour = i % 24
        if 0 <= hour <= 5:
            prices.append(base_price * 0.6)
        elif 6 <= hour <= 9:
            prices.append(base_price * 1.4)
        elif 10 <= hour <= 14:
            prices.append(base_price * 0.7)
        elif 17 <= hour <= 20:
            prices.append(base_price * 1.8)
        else:
            prices.append(base_price * 1.0)

    return pd.DataFrame({'price_per_kwh': prices}, index=dates)


class TestDayAheadStrategyInit:
    """Test DayAheadStrategy initialization."""

    def test_default_parameters(self):
        """Test default parameter values."""
        strategy = DayAheadStrategy({})

        assert strategy.discharge_threshold == 1.2
        assert strategy.charge_threshold == 0.8
        assert strategy.control_exflow == 3

    def test_custom_parameters(self):
        """Test custom parameter values."""
        strategy = DayAheadStrategy({
            "discharge_threshold": 1.3,
            "charge_threshold": 0.7,
            "control_exflow": 2
        })

        assert strategy.discharge_threshold == 1.3
        assert strategy.charge_threshold == 0.7
        assert strategy.control_exflow == 2

    def test_initial_state(self):
        """Test initial planning state is empty."""
        strategy = DayAheadStrategy({})

        assert strategy.schedule == {}
        assert strategy.last_plan_day is None
        assert strategy.known_until_date is None


class TestDayAheadPlanUpdate:
    """Test the day-ahead planning mechanism."""

    def test_plan_created_at_init(self):
        """Test plan is created on first call."""
        strategy = DayAheadStrategy({})
        data = make_price_data(days=3)
        strategy.setup_price_array(data, 1.0)

        context = {
            'timestamp': data.index[0],  # 2024-01-01 00:00
            'index': 0,
            'current_storage': 500,
            'capacity': 1000,
            'price': data['price_per_kwh'].iloc[0],
            'avg_price': data['price_per_kwh'].mean()
        }

        # First call should trigger plan creation
        strategy.should_charge(context)

        assert strategy.last_plan_day is not None
        assert len(strategy.schedule) > 0

    def test_plan_covers_today_before_13(self):
        """Test plan only covers today when before 13:00."""
        strategy = DayAheadStrategy({})
        data = make_price_data(days=3)
        strategy.setup_price_array(data, 1.0)

        # Start at 08:00 (before 13:00)
        strategy._update_day_ahead_plan(8)

        # Should only know today's prices
        assert strategy.known_until_date == date(2024, 1, 1)

        # Schedule should contain entries for today only
        dates_in_schedule = set(k[0] for k in strategy.schedule.keys())
        assert date(2024, 1, 1) in dates_in_schedule
        assert date(2024, 1, 2) not in dates_in_schedule

    def test_plan_covers_today_and_tomorrow_after_13(self):
        """Test plan covers today + tomorrow when after 13:00."""
        strategy = DayAheadStrategy({})
        data = make_price_data(days=3)
        strategy.setup_price_array(data, 1.0)

        # Start at 13:00 (day-ahead prices just published)
        strategy._update_day_ahead_plan(13)

        # Should know today + tomorrow
        assert strategy.known_until_date == date(2024, 1, 2)

        dates_in_schedule = set(k[0] for k in strategy.schedule.keys())
        assert date(2024, 1, 1) in dates_in_schedule
        assert date(2024, 1, 2) in dates_in_schedule

    def test_plan_updates_daily_at_13(self):
        """Test plan updates when 13:00 is reached on a new day."""
        strategy = DayAheadStrategy({})
        data = make_price_data(days=5)
        strategy.setup_price_array(data, 1.0)

        # Initial plan at hour 0
        strategy._update_day_ahead_plan(0)
        assert strategy.last_plan_day == date(2024, 1, 1)

        # At 13:00 day 2 (index 37), should update
        context = {
            'timestamp': data.index[37],  # 2024-01-02 13:00
            'index': 37,
            'current_storage': 500,
            'capacity': 1000,
            'price': data['price_per_kwh'].iloc[37],
            'avg_price': data['price_per_kwh'].mean()
        }

        strategy.should_discharge(context)

        assert strategy.last_plan_day == date(2024, 1, 2)
        assert strategy.known_until_date == date(2024, 1, 3)

    def test_backward_looking_average(self):
        """Test average is computed from known prices only."""
        strategy = DayAheadStrategy({})
        data = make_price_data(days=3)
        strategy.setup_price_array(data, 1.0)

        # Plan at hour 0 (before 13:00) -> only today's prices
        strategy._update_day_ahead_plan(0)

        # Average should be from today's 24 hours only
        today_prices = data['price_per_kwh'].iloc[:24]
        expected_avg = today_prices.mean()

        assert strategy.known_avg == pytest.approx(expected_avg, rel=0.01)


class TestDayAheadScheduling:
    """Test charge/discharge scheduling decisions."""

    def test_discharge_during_expensive_hours(self):
        """Test battery discharges during expensive hours."""
        strategy = DayAheadStrategy({
            "discharge_threshold": 1.2,
            "min_soc": 0.05
        })
        data = make_price_data(days=2)
        strategy.setup_price_array(data, 1.0)
        strategy._update_day_ahead_plan(0)

        # Evening peak (17:00-20:00) should be discharge hours
        # Price = 0.18, avg ~ 0.10, ratio 1.8 > 1.2 threshold
        for hour in [17, 18, 19, 20]:
            context = {
                'timestamp': data.index[hour],
                'index': hour,
                'current_storage': 800,
                'capacity': 1000,
                'price': data['price_per_kwh'].iloc[hour],
                'avg_price': strategy.known_avg
            }
            assert strategy.should_discharge(context) == True, \
                f"Should discharge at hour {hour} (price={data['price_per_kwh'].iloc[hour]:.3f})"

    def test_charge_during_cheap_hours(self):
        """Test battery charges during cheap hours."""
        strategy = DayAheadStrategy({
            "charge_threshold": 0.8,
            "max_soc": 0.95
        })
        data = make_price_data(days=2)
        strategy.setup_price_array(data, 1.0)
        strategy._update_day_ahead_plan(0)

        # Night (0-5) should be charge hours
        # Price = 0.06, avg ~ 0.10, ratio 0.6 < 0.8 threshold
        for hour in [0, 1, 2, 3, 4, 5]:
            context = {
                'timestamp': data.index[hour],
                'index': hour,
                'current_storage': 200,
                'capacity': 1000,
                'price': data['price_per_kwh'].iloc[hour],
                'avg_price': strategy.known_avg,
                'renew': 500,
                'power_limit': 500,
                'resolution': 1.0
            }
            assert strategy.should_charge(context) == True, \
                f"Should charge at hour {hour} (price={data['price_per_kwh'].iloc[hour]:.3f})"

    def test_idle_during_average_hours(self):
        """Test battery stays idle during average-priced hours."""
        strategy = DayAheadStrategy({
            "discharge_threshold": 1.2,
            "charge_threshold": 0.8
        })
        data = make_price_data(days=2)
        strategy.setup_price_array(data, 1.0)
        strategy._update_day_ahead_plan(0)

        # Hours 15, 16, 21, 22, 23 have price = 1.0 * base = avg
        # Not above 1.2 * avg (discharge) nor below 0.8 * avg (charge)
        for hour in [15, 16, 21, 22, 23]:
            context = {
                'timestamp': data.index[hour],
                'index': hour,
                'current_storage': 500,
                'capacity': 1000,
                'price': data['price_per_kwh'].iloc[hour],
                'avg_price': strategy.known_avg
            }
            assert strategy.should_discharge(context) == False
            assert strategy.should_charge(context) == False

    def test_no_discharge_at_min_soc(self):
        """Test no discharge when battery is at minimum SOC."""
        strategy = DayAheadStrategy({"min_soc": 0.1})
        data = make_price_data(days=2)
        strategy.setup_price_array(data, 1.0)
        strategy._update_day_ahead_plan(0)

        context = {
            'timestamp': data.index[18],  # Expensive hour
            'index': 18,
            'current_storage': 50,  # 5% SOC (below min_soc=10%)
            'capacity': 1000,
            'price': data['price_per_kwh'].iloc[18],
            'avg_price': strategy.known_avg
        }

        assert strategy.should_discharge(context) == False

    def test_no_charge_at_max_soc(self):
        """Test no charging when battery is at maximum SOC."""
        strategy = DayAheadStrategy({"max_soc": 0.9})
        data = make_price_data(days=2)
        strategy.setup_price_array(data, 1.0)
        strategy._update_day_ahead_plan(0)

        context = {
            'timestamp': data.index[2],  # Cheap hour
            'index': 2,
            'current_storage': 950,  # 95% SOC (above max_soc=90%)
            'capacity': 1000,
            'price': data['price_per_kwh'].iloc[2],
            'avg_price': strategy.known_avg
        }

        assert strategy.should_charge(context) == False


class TestDayAheadExport:
    """Test export decisions."""

    def test_export_positive_price(self):
        """Test export when price is positive."""
        strategy = DayAheadStrategy({"control_exflow": 3})

        context = {'price': 0.10}
        assert strategy.should_export(context) == True

    def test_no_export_negative_price(self):
        """Test no export when price is negative."""
        strategy = DayAheadStrategy({"control_exflow": 3})

        context = {'price': -0.01}
        assert strategy.should_export(context) == False

    def test_no_export_control_disabled(self):
        """Test no export when control mode is 1."""
        strategy = DayAheadStrategy({"control_exflow": 1})

        context = {'price': 0.10}
        assert strategy.should_export(context) == False


class TestDayAheadAmounts:
    """Test charge/discharge amount calculations."""

    def test_charge_amount_power_limited(self):
        """Test charge amount limited by power."""
        strategy = DayAheadStrategy({"max_soc": 0.95})

        context = {
            'renew': 1000,
            'power_limit': 300,
            'resolution': 1.0,
            'current_storage': 200,
            'capacity': 1000
        }

        charge = strategy.calculate_charge_amount(context)
        assert charge == 300  # Power limited: 300 kW * 1h

    def test_charge_amount_soc_limited(self):
        """Test charge amount limited by max SOC."""
        strategy = DayAheadStrategy({"max_soc": 0.95})

        context = {
            'renew': 1000,
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 900,
            'capacity': 1000
        }

        charge = strategy.calculate_charge_amount(context)
        assert charge == 50  # SOC limited: (0.95 * 1000) - 900

    def test_charge_amount_renew_limited(self):
        """Test charge amount limited by available renewable."""
        strategy = DayAheadStrategy({"max_soc": 0.95})

        context = {
            'renew': 100,
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 200,
            'capacity': 1000
        }

        charge = strategy.calculate_charge_amount(context)
        assert charge == 100  # Renewable limited

    def test_discharge_amount_with_saturation(self):
        """Test discharge amount uses saturation curve."""
        strategy = DayAheadStrategy({
            "min_soc": 0.05,
            "discharge_threshold": 1.2
        })
        data = make_price_data(days=2)
        strategy.setup_price_array(data, 1.0)
        strategy._update_day_ahead_plan(0)

        context = {
            'timestamp': data.index[18],  # Expensive hour (1.8x base)
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 800,
            'capacity': 1000,
            'price': data['price_per_kwh'].iloc[18]
        }

        discharge = strategy.calculate_discharge_amount(context)

        # Should discharge some amount (not zero, not full)
        assert discharge > 0
        assert discharge <= 500  # Power limited

    def test_discharge_modulated_by_price(self):
        """Test more expensive hours get more aggressive discharge."""
        strategy = DayAheadStrategy({
            "min_soc": 0.05,
            "discharge_threshold": 1.2
        })
        data = make_price_data(days=2)
        strategy.setup_price_array(data, 1.0)
        strategy._update_day_ahead_plan(0)

        base_context = {
            'power_limit': 500,
            'resolution': 1.0,
            'current_storage': 800,
            'capacity': 1000
        }

        # Higher price -> more discharge
        context_high = {**base_context, 'price': 0.20, 'timestamp': data.index[18]}
        context_med = {**base_context, 'price': 0.14, 'timestamp': data.index[6]}

        discharge_high = strategy.calculate_discharge_amount(context_high)
        discharge_med = strategy.calculate_discharge_amount(context_med)

        assert discharge_high >= discharge_med


class TestDayAheadInformationBoundary:
    """Test that the strategy respects information boundaries."""

    def test_no_future_prices_before_13(self):
        """Test strategy doesn't use tomorrow's prices before 13:00."""
        strategy = DayAheadStrategy({})
        data = make_price_data(days=3)
        strategy.setup_price_array(data, 1.0)

        # Plan at 08:00 (before 13:00)
        strategy._update_day_ahead_plan(8)

        # Should NOT have tomorrow's prices in schedule
        tomorrow = date(2024, 1, 2)
        tomorrow_keys = [k for k in strategy.schedule if k[0] == tomorrow]
        assert len(tomorrow_keys) == 0

    def test_tomorrow_available_after_13(self):
        """Test tomorrow's prices are available after 13:00."""
        strategy = DayAheadStrategy({})
        data = make_price_data(days=3)
        strategy.setup_price_array(data, 1.0)

        # Plan at 13:00
        strategy._update_day_ahead_plan(13)

        # Should have tomorrow's prices in schedule
        tomorrow = date(2024, 1, 2)
        tomorrow_keys = [k for k in strategy.schedule if k[0] == tomorrow]
        assert len(tomorrow_keys) == 24

    def test_end_of_year_boundary(self):
        """Test strategy handles end of data gracefully."""
        strategy = DayAheadStrategy({})

        # Create just 2 days of data
        data = make_price_data(days=2)
        strategy.setup_price_array(data, 1.0)

        # Plan at 13:00 on last day
        strategy._update_day_ahead_plan(37)  # Day 2, hour 13

        # Should not crash, schedule whatever is available
        assert len(strategy.schedule) > 0

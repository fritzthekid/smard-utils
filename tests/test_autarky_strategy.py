"""
Tests for AutoarkyStrategy (bms_strategies/autarky.py).

Covers every branch of:
  should_discharge, should_charge, should_export,
  calculate_charge_amount, calculate_discharge_amount
"""
import pytest
from smard_utils.bms_strategies.autarky import AutoarkyStrategy


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def ctx(renew, demand, current_storage, capacity,
        power_limit=100.0, resolution=1.0):
    """Build a minimal BMS context dict."""
    return {
        'renew': renew,
        'demand': demand,
        'current_storage': current_storage,
        'capacity': capacity,
        'power_limit': power_limit,
        'resolution': resolution,
        'price': 0.0,
        'avg_price': 0.0,
    }


@pytest.fixture
def strat():
    return AutoarkyStrategy({'min_soc': 0.05, 'max_soc': 0.95,
                              'efficiency_discharge': 0.96})


@pytest.fixture
def strat_defaults():
    return AutoarkyStrategy({})


# ---------------------------------------------------------------------------
# should_discharge
# ---------------------------------------------------------------------------

class TestShouldDischarge:

    def test_discharges_when_deficit_and_soc_ok(self, strat):
        c = ctx(renew=0.5, demand=2.0, current_storage=8.0, capacity=10.0)
        assert strat.should_discharge(c) is True

    def test_no_discharge_when_no_deficit(self, strat):
        c = ctx(renew=3.0, demand=1.0, current_storage=8.0, capacity=10.0)
        assert strat.should_discharge(c) is False

    def test_no_discharge_when_surplus_zero_deficit(self, strat):
        c = ctx(renew=2.0, demand=2.0, current_storage=8.0, capacity=10.0)
        assert strat.should_discharge(c) is False

    def test_no_discharge_when_soc_at_min(self, strat):
        # current_storage == min_soc * capacity → NOT above min
        c = ctx(renew=0.0, demand=2.0, current_storage=0.5, capacity=10.0)
        assert strat.should_discharge(c) is False

    def test_no_discharge_when_soc_below_min(self, strat):
        c = ctx(renew=0.0, demand=2.0, current_storage=0.3, capacity=10.0)
        assert strat.should_discharge(c) is False

    def test_discharges_just_above_min(self, strat):
        # 0.51 > 0.05 * 10 = 0.5
        c = ctx(renew=0.0, demand=2.0, current_storage=0.51, capacity=10.0)
        assert strat.should_discharge(c) is True

    def test_default_min_soc(self, strat_defaults):
        # Default min_soc = 0.05; at exactly 5% SOC → not above
        c = ctx(renew=0.0, demand=2.0, current_storage=0.5, capacity=10.0)
        assert strat_defaults.should_discharge(c) is False


# ---------------------------------------------------------------------------
# should_charge
# ---------------------------------------------------------------------------

class TestShouldCharge:

    def test_charges_when_surplus_and_room(self, strat):
        c = ctx(renew=3.0, demand=0.5, current_storage=4.0, capacity=10.0)
        assert strat.should_charge(c) is True

    def test_no_charge_when_no_surplus(self, strat):
        c = ctx(renew=0.5, demand=2.0, current_storage=4.0, capacity=10.0)
        assert strat.should_charge(c) is False

    def test_no_charge_when_equal(self, strat):
        c = ctx(renew=1.0, demand=1.0, current_storage=4.0, capacity=10.0)
        assert strat.should_charge(c) is False

    def test_no_charge_when_battery_full(self, strat):
        # current_storage == max_soc * capacity
        c = ctx(renew=3.0, demand=0.5, current_storage=9.5, capacity=10.0)
        assert strat.should_charge(c) is False

    def test_no_charge_when_above_max_soc(self, strat):
        c = ctx(renew=3.0, demand=0.5, current_storage=9.8, capacity=10.0)
        assert strat.should_charge(c) is False

    def test_charges_just_below_max_soc(self, strat):
        # 9.49 < 0.95 * 10 = 9.5
        c = ctx(renew=3.0, demand=0.5, current_storage=9.49, capacity=10.0)
        assert strat.should_charge(c) is True

    def test_default_max_soc(self, strat_defaults):
        # Default max_soc = 0.95
        c = ctx(renew=3.0, demand=0.5, current_storage=9.5, capacity=10.0)
        assert strat_defaults.should_charge(c) is False


# ---------------------------------------------------------------------------
# should_export
# ---------------------------------------------------------------------------

class TestShouldExport:

    def test_always_true_with_surplus(self, strat):
        c = ctx(renew=5.0, demand=1.0, current_storage=9.5, capacity=10.0)
        assert strat.should_export(c) is True

    def test_always_true_with_no_surplus(self, strat):
        c = ctx(renew=0.0, demand=2.0, current_storage=3.0, capacity=10.0)
        assert strat.should_export(c) is True

    def test_always_true_empty_battery(self, strat):
        c = ctx(renew=0.0, demand=0.0, current_storage=0.0, capacity=10.0)
        assert strat.should_export(c) is True


# ---------------------------------------------------------------------------
# calculate_discharge_amount
# ---------------------------------------------------------------------------

class TestCalculateDischargeAmount:

    def test_deficit_limited(self, strat):
        deficit = 1.0
        c = ctx(renew=1.0, demand=2.0, current_storage=9.0, capacity=10.0,
                power_limit=100.0)
        amount = strat.calculate_discharge_amount(c)
        assert amount == pytest.approx(deficit, rel=1e-3)

    def test_available_limited(self, strat):
        # available = (0.8 - 0.05*10) * 0.96 = 0.3 * 0.96 = 0.288
        c = ctx(renew=0.0, demand=10.0, current_storage=0.8, capacity=10.0,
                power_limit=100.0)
        expected = (0.8 - 0.05 * 10.0) * 0.96
        assert strat.calculate_discharge_amount(c) == pytest.approx(expected, rel=1e-3)

    def test_power_limited(self, strat):
        c = ctx(renew=0.0, demand=10.0, current_storage=9.0, capacity=10.0,
                power_limit=1.0, resolution=1.0)
        assert strat.calculate_discharge_amount(c) == pytest.approx(1.0, rel=1e-3)

    def test_amount_nonnegative_when_soc_at_min(self, strat):
        c = ctx(renew=0.0, demand=10.0, current_storage=0.5, capacity=10.0,
                power_limit=100.0)
        assert strat.calculate_discharge_amount(c) == pytest.approx(0.0, abs=1e-9)

    def test_default_efficiency(self, strat_defaults):
        # efficiency_discharge default = 0.96
        c = ctx(renew=0.0, demand=10.0, current_storage=1.5, capacity=10.0,
                power_limit=100.0)
        expected = (1.5 - 0.05 * 10.0) * 0.96
        assert strat_defaults.calculate_discharge_amount(c) == pytest.approx(expected, rel=1e-3)


# ---------------------------------------------------------------------------
# calculate_charge_amount
# ---------------------------------------------------------------------------

class TestCalculateChargeAmount:

    def test_surplus_limited(self, strat):
        surplus = 2.0
        c = ctx(renew=3.0, demand=1.0, current_storage=4.0, capacity=10.0,
                power_limit=100.0)
        assert strat.calculate_charge_amount(c) == pytest.approx(surplus, rel=1e-3)

    def test_room_limited(self, strat):
        # room = 0.95*10 - 9.0 = 0.5
        c = ctx(renew=5.0, demand=0.5, current_storage=9.0, capacity=10.0,
                power_limit=100.0)
        assert strat.calculate_charge_amount(c) == pytest.approx(0.5, rel=1e-3)

    def test_power_limited(self, strat):
        c = ctx(renew=5.0, demand=0.5, current_storage=4.0, capacity=10.0,
                power_limit=1.0, resolution=1.0)
        assert strat.calculate_charge_amount(c) == pytest.approx(1.0, rel=1e-3)

    def test_zero_when_no_surplus(self, strat):
        c = ctx(renew=0.5, demand=2.0, current_storage=4.0, capacity=10.0,
                power_limit=100.0)
        assert strat.calculate_charge_amount(c) == pytest.approx(0.0, abs=1e-9)

    def test_zero_when_battery_full(self, strat):
        # room = 9.5 - 9.5 = 0
        c = ctx(renew=3.0, demand=0.5, current_storage=9.5, capacity=10.0,
                power_limit=100.0)
        assert strat.calculate_charge_amount(c) == pytest.approx(0.0, abs=1e-9)

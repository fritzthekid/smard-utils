"""
Strategy registry.

Central mapping from strategy name → class.  Adding a new strategy only
requires registering it here — no application class needs to change (O1, O2).
"""

from smard_utils.bms_strategies.price_threshold import PriceThresholdStrategy
from smard_utils.bms_strategies.dynamic_discharge import DynamicDischargeStrategy
from smard_utils.bms_strategies.day_ahead import DayAheadStrategy
from smard_utils.bms_strategies.autarky import AutoarkyStrategy

STRATEGY_REGISTRY: dict = {
    "price_threshold": PriceThresholdStrategy,
    "dynamic_discharge": DynamicDischargeStrategy,
    "day_ahead": DayAheadStrategy,
    "autarky": AutoarkyStrategy,
}


def get_strategy(name: str, basic_data_set: dict):
    """
    Instantiate a strategy by name from the registry.

    Args:
        name: Strategy key (e.g. "day_ahead")
        basic_data_set: Config dict passed to strategy constructor

    Returns:
        BMSStrategy instance

    Raises:
        ValueError: If name is not in the registry
    """
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        available = list(STRATEGY_REGISTRY)
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return cls(basic_data_set)

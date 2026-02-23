"""
Battery Management System control strategies.

Strategies implement profit optimization logic:
- PriceThresholdStrategy: Hysteresis-based price thresholds (BioBat)
- DynamicDischargeStrategy: Saturation curves with dynamic discharge (SolBat)
- AutoarkyStrategy: Charge from surplus solar, discharge to cover deficit (HomeBat)
"""

from .price_threshold import PriceThresholdStrategy
from .dynamic_discharge import DynamicDischargeStrategy
from .autarky import AutoarkyStrategy

__all__ = ['PriceThresholdStrategy', 'DynamicDischargeStrategy', 'AutoarkyStrategy']

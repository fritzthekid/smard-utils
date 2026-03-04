"""
Battery Management System control strategies.

Strategies implement profit optimization logic:
- PriceThresholdStrategy: Hysteresis-based price thresholds (BioBat)
- DynamicDischargeStrategy: Saturation curves with dynamic discharge (SolBat)
- AutoarkyStrategy: Charge from surplus solar, discharge to cover deficit (HomeBat)
"""

from .autarky import AutoarkyStrategy
from .dynamic_discharge import DynamicDischargeStrategy
from .price_threshold import PriceThresholdStrategy

__all__ = ["PriceThresholdStrategy", "DynamicDischargeStrategy", "AutoarkyStrategy"]

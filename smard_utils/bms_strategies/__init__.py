"""
Battery Management System control strategies.

Strategies implement profit optimization logic:
- PriceThresholdStrategy: Hysteresis-based price thresholds (BioBat)
- DynamicDischargeStrategy: Saturation curves with dynamic discharge (SolBat)
"""

from .price_threshold import PriceThresholdStrategy
from .dynamic_discharge import DynamicDischargeStrategy

__all__ = ['PriceThresholdStrategy', 'DynamicDischargeStrategy']

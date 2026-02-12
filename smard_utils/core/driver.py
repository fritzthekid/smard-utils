"""
Energy data driver base class.

Provides abstract interface for loading and preparing time-series energy data.
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class EnergyDriver(ABC):
    """Abstract base class for energy data providers."""

    def __init__(self, basic_data_set: dict):
        """
        Initialize driver with configuration.

        Args:
            basic_data_set: Configuration dictionary containing driver-specific parameters
        """
        self.basic_data_set = basic_data_set.copy() if basic_data_set else {}
        self.resolution = None  # Time resolution in hours
        self._data = None

    @abstractmethod
    def load_data(self, data_source: str) -> pd.DataFrame:
        """
        Load and prepare data from source.

        Must create a DataFrame with at least these columns:
        - my_renew: Renewable energy generation (kWh per timestep)
        - my_demand: Energy demand (kWh per timestep)
        - DatetimeIndex: Timestamp for each row

        Must set self.resolution to timestep duration in hours.

        Args:
            data_source: Path to data file or data source identifier

        Returns:
            Prepared DataFrame with my_renew and my_demand columns
        """
        pass

    @property
    def data(self) -> pd.DataFrame:
        """Returns DataFrame with my_renew and my_demand columns."""
        if self._data is None:
            raise ValueError("No data loaded. Call load_data() first.")
        return self._data

    def get_timestep(self, index: int) -> tuple:
        """
        Get renewable and demand for a specific timestep.

        Args:
            index: Timestep index (0-based)

        Returns:
            Tuple of (renew, demand) in kWh
        """
        return (
            float(self._data['my_renew'].iloc[index]),
            float(self._data['my_demand'].iloc[index])
        )

    def __len__(self) -> int:
        """Return number of timesteps."""
        return len(self._data) if self._data is not None else 0

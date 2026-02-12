"""
Community energy driver.

Thin subclass of SolarDriver for community scenarios with solar + wind + demand.
Default region is Luxembourg (_lu).
"""

import pandas as pd
from smard_utils.drivers.solar_driver import SolarDriver


class CommunityDriver(SolarDriver):
    """Driver for community energy analysis (solar + wind + demand scaling)."""

    def __init__(self, basic_data_set: dict, region: str = "_lu"):
        super().__init__(basic_data_set, region=region)

    def load_data(self, csv_file_path: str) -> pd.DataFrame:
        df = super().load_data(csv_file_path)
        # SolarDriver divides year_demand by 1000 (kWh->MWh) for my_demand,
        # but my_renew stays in kWh. For community scenarios where demand
        # is significant, both must be in kWh.
        self._data["my_demand"] = self._data["my_demand"] * 1000
        return self._data

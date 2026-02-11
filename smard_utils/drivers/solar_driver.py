"""
Solar PV energy driver.

Loads SMARD data and scales proportionally based on installed capacity.
"""

import pandas as pd
import numpy as np
from smard_utils.core.driver import EnergyDriver


class SolarDriver(EnergyDriver):
    """Driver for solar PV with proportional scaling from SMARD data."""

    def __init__(self, basic_data_set: dict, region: str = "_de"):
        """
        Initialize solar driver.

        Args:
            basic_data_set: Configuration dictionary
            region: Region code ("_de" for Germany, "_lu" for Luxembourg)
        """
        super().__init__(basic_data_set)
        self.region = region

    def load_data(self, csv_file_path: str) -> pd.DataFrame:
        """
        Load SMARD data and scale proportionally.

        Args:
            csv_file_path: Path to SMARD CSV file

        Returns:
            DataFrame with proportionally scaled my_renew and my_demand
        """
        print("Loading SMARD data for solar analysis...")

        df = pd.read_csv(csv_file_path, sep=';', decimal=',')

        # Create datetime column
        df['DateTime'] = pd.to_datetime(df['Datum'] + ' ' + df['Uhrzeit'])
        df = df.set_index('DateTime')

        # Remove non-energy columns
        energy_cols = [col for col in df.columns if '[MWh]' in col]
        df = df[energy_cols]

        # Rename columns for easier handling
        column_mapping = {}
        for col in df.columns:
            if 'Wind Onshore' in col:
                column_mapping[col] = 'wind_onshore'
            elif 'Wind Offshore' in col:
                column_mapping[col] = 'wind_offshore'
            elif 'Photovoltaik' in col:
                column_mapping[col] = 'solar'
            elif 'Wasserkraft' in col:
                column_mapping[col] = 'hydro'
            elif 'Biomasse' in col:
                column_mapping[col] = 'biomass'
            elif 'Erdgas [MWh]' in col:
                column_mapping[col] = 'oel'
            elif 'Gesamtverbrauch' in col or 'Netzlast' in col:
                column_mapping[col] = 'total_demand'

        df = df.rename(columns=column_mapping)

        # Calculate resolution
        self.resolution = ((df.index[1] - df.index[0]).seconds) / 3600

        # Calculate totals for scaling
        total_demand = df["total_demand"].sum() * self.resolution
        year_demand_kwh = self.basic_data_set.get("year_demand", 0)
        year_demand = year_demand_kwh / 1000  # Convert kWh to MWh

        # Get max installed capacity from data
        total_installed_solar = df["solar"].max()  # MWp
        total_installed_wind = df["wind_onshore"].max()  # MW

        # Proportional scaling
        df["my_demand"] = df["total_demand"] * year_demand / total_demand * self.resolution

        df["my_renew"] = (
            df["wind_onshore"] *
            self.basic_data_set.get("wind_nominal_power", 0) /
            max(total_installed_wind, 1) * self.resolution
        )
        df["my_renew"] += (
            df["solar"] *
            self.basic_data_set.get("solar_max_power", 0) /
            max(total_installed_solar, 1) * self.resolution
        )

        df = df.fillna(0)

        print(f"✓ Loaded {len(df)} {(df.index[1]-df.index[0]).seconds/60} minutes records")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        print(f"Solar scaling: {self.basic_data_set.get('solar_max_power', 0)} kW peak")
        print(f"Wind scaling: {self.basic_data_set.get('wind_nominal_power', 0)} kW nominal")

        self._data = df
        return df

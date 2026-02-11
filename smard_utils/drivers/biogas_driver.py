"""
Biogas plant energy driver.

Loads SMARD data and provides constant biogas injection.
"""

import pandas as pd
import numpy as np
from smard_utils.core.driver import EnergyDriver


def remove_holes_from_data(data):
    """
    Remove holes from data by linear interpolation.

    Args:
        data: DataFrame with DateTime_x column

    Returns:
        DataFrame with interpolated DateTime column
    """
    avrgdiff = (data["DateTime_x"].iloc[-1] - data["DateTime_x"].iloc[0]) / (len(data) - 1)
    data["DateTime"] = [data["DateTime_x"].iloc[0] + i * avrgdiff for i, e in enumerate(data["DateTime_x"])]
    return data


class BiogasDriver(EnergyDriver):
    """Driver for biogas plant with constant renewable energy injection."""

    def load_data(self, csv_file_path: str) -> pd.DataFrame:
        """
        Load SMARD data and configure for constant biogas injection.

        Args:
            csv_file_path: Path to SMARD CSV file

        Returns:
            DataFrame with my_renew (constant biogas) and my_demand (zero)
        """
        print("Loading SMARD data for biogas analysis...")

        df = pd.read_csv(csv_file_path, sep=';', decimal=',')

        # Create datetime column
        df['DateTime_x'] = pd.to_datetime(df['Datum'] + ' ' + df['Uhrzeit'])

        # Remove holes from data
        df = remove_holes_from_data(df)
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

        # Constant biogas injection (production only, no demand)
        df["my_renew"] = self.basic_data_set.get("constant_biogas_kw", 0) * self.resolution
        df["my_demand"] = df["total_demand"] * 0  # No demand scenario

        df = df.fillna(0)

        print(f"✓ Loaded {len(df)} {(df.index[1]-df.index[0]).seconds/60} minutes records")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        print(f"Constant biogas: {self.basic_data_set.get('constant_biogas_kw', 0)} kW")

        self._data = df
        return df

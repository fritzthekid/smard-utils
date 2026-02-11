"""
SENEC home battery driver.

Loads SENEC monitoring data with pass-through values.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from smard_utils.core.driver import EnergyDriver


class SenecDriver(EnergyDriver):
    """Driver for SENEC home battery with pass-through measurements."""

    def load_data(self, csv_file_path: str) -> pd.DataFrame:
        """
        Load SENEC CSV data.

        Args:
            csv_file_path: Path to SENEC monitoring CSV file

        Returns:
            DataFrame with my_renew (solar) and my_demand (consumption)
        """
        print("Loading SENEC home battery data...")

        df = pd.read_csv(csv_file_path)

        # Column mapping for SENEC format
        column_mapping = {}
        for col in df.columns:
            if 'Uhrzeit' in col:
                column_mapping[col] = 'stime'
            elif 'Netzbezug [kW]' in col:
                column_mapping[col] = 'act_residual_kw'
            elif 'Netzeinspeisung [kW]' in col:
                column_mapping[col] = 'act_export_kw'
            elif 'Stromverbrauch [kW]' in col:
                column_mapping[col] = 'act_total_demand_kw'
            elif 'Akkubeladung [kW]' in col:
                column_mapping[col] = 'act_battery_inflow_kw'
            elif 'Akkuentnahme [kW]' in col:
                column_mapping[col] = 'act_battery_exflow_kw'
            elif 'Stromerzeugung [kW]' in col:
                column_mapping[col] = 'act_solar_kw'
            elif 'Akku Spannung [V]' in col:
                column_mapping[col] = 'act_battery_voltage'
            elif 'Akku Stromstärke [A]' in col:
                column_mapping[col] = 'act_battery_current'

        df = df.rename(columns=column_mapping)

        # Parse datetime
        dtl = []
        diff = []
        for i, st in enumerate(df["stime"]):
            t = datetime.strptime(st, "%d.%m.%Y %H:%M:%S")
            if i > 0:
                diff.append((t - dtl[-1]).seconds)
            dtl.append(t)

        df["time"] = dtl
        df = df.set_index("time")

        # Calculate variable resolution (average timestep)
        self.resolution = sum(diff) / len(diff) / 3600

        # Pass-through data (kW → kWh)
        df["solar"] = df["act_solar_kw"] * self.resolution
        df["wind_onshore"] = df["solar"] * 0  # No wind for home systems

        df["total_demand"] = df["act_total_demand_kw"] * self.resolution
        df["my_demand"] = df["total_demand"].values
        df["my_renew"] = df["solar"].values

        # Also keep actual battery data for validation
        df["act_battery_inflow"] = df["act_battery_inflow_kw"] * self.resolution
        df["act_battery_exflow"] = df["act_battery_exflow_kw"] * self.resolution

        df = df.fillna(0)

        print(f"✓ Loaded {len(df)} records")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        print(f"Average resolution: {self.resolution * 60:.1f} minutes")
        print(f"Total solar generation: {df['my_renew'].sum():.1f} kWh")
        print(f"Total consumption: {df['my_demand'].sum():.1f} kWh")

        self._data = df
        return df

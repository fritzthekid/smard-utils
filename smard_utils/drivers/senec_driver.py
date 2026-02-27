"""
SENEC home battery driver.

Loads SENEC monitoring data with pass-through values.
"""

import pandas as pd
from datetime import datetime
from smard_utils.core.driver import EnergyDriver


class SenecDriver(EnergyDriver):
    """Driver for SENEC home battery with pass-through measurements."""

    # ------------------------------------------------------------------
    # Sub-step helpers (split out for SRP, S7)
    # ------------------------------------------------------------------

    def _rename_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Map SENEC column names to standardised internal names.

        Args:
            df: Raw DataFrame from CSV

        Returns:
            DataFrame with renamed columns
        """
        mapping = {}
        for col in df.columns:
            if 'Uhrzeit' in col:
                mapping[col] = 'stime'
            elif 'Netzbezug [kW]' in col:
                mapping[col] = 'act_residual_kw'
            elif 'Netzeinspeisung [kW]' in col:
                mapping[col] = 'act_export_kw'
            elif 'Stromverbrauch [kW]' in col:
                mapping[col] = 'act_total_demand_kw'
            elif 'Akkubeladung [kW]' in col:
                mapping[col] = 'act_battery_inflow_kw'
            elif 'Akkuentnahme [kW]' in col:
                mapping[col] = 'act_battery_exflow_kw'
            elif 'Stromerzeugung [kW]' in col:
                mapping[col] = 'act_solar_kw'
            elif 'Akku Spannung [V]' in col:
                mapping[col] = 'act_battery_voltage'
            elif 'Akku Stromstärke [A]' in col:
                mapping[col] = 'act_battery_current'
        return df.rename(columns=mapping)

    def _parse_timestamps(self, df: pd.DataFrame) -> tuple:
        """
        Parse the 'stime' column into datetime objects and compute average resolution.

        Args:
            df: DataFrame with 'stime' column

        Returns:
            (list of datetime objects, average resolution in hours)
        """
        dtl = []
        diff = []
        for i, st in enumerate(df["stime"]):
            t = datetime.strptime(st, "%d.%m.%Y %H:%M:%S")
            if i > 0:
                diff.append((t - dtl[-1]).seconds)
            dtl.append(t)
        resolution = sum(diff) / len(diff) / 3600
        return dtl, resolution

    def _build_energy_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert power columns (kW) to energy per period (kWh) and create renew/demand.

        Args:
            df: DataFrame with timestamp index and power columns

        Returns:
            DataFrame with my_renew, my_demand, and actual battery flow columns
        """
        res = self.resolution
        df["solar"] = df["act_solar_kw"] * res
        df["wind_onshore"] = 0.0  # No wind for home systems

        df["total_demand"] = df["act_total_demand_kw"] * res
        df["my_demand"] = df["total_demand"].values
        df["my_renew"] = df["solar"].values

        df["act_battery_inflow"] = df["act_battery_inflow_kw"] * res
        df["act_battery_exflow"] = df["act_battery_exflow_kw"] * res
        return df

    # ------------------------------------------------------------------
    # EnergyDriver interface
    # ------------------------------------------------------------------

    def load_data(self, csv_file_path: str) -> pd.DataFrame:
        """
        Load SENEC CSV data.

        Delegates parsing, column mapping, timestamp handling, and energy
        column construction to focused sub-methods (S7 refactor).

        Args:
            csv_file_path: Path to SENEC monitoring CSV file

        Returns:
            DataFrame with my_renew (solar) and my_demand (consumption)
        """
        print("Loading SENEC home battery data...")

        df = pd.read_csv(csv_file_path, sep=';')
        df = self._rename_columns(df)

        timestamps, self.resolution = self._parse_timestamps(df)
        df["time"] = timestamps
        df = df.set_index("time")

        df = self._build_energy_columns(df)
        df = df.fillna(0)

        print(f"✓ Loaded {len(df)} records")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        print(f"Average resolution: {self.resolution * 60:.1f} minutes")
        print(f"Total solar generation: {df['my_renew'].sum():.1f} kWh")
        print(f"Total consumption: {df['my_demand'].sum():.1f} kWh")

        self._data = df
        return df

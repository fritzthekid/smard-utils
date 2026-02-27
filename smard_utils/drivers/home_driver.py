"""
Home storage driver.

Loads SMARD-format CSV produced by senec2smardformat (or any equivalent
household CSV) and exposes the data as direct kWh-per-period values — no
national-grid scaling applied.

Column convention: demand > 0  (household consumption)
"""

import pandas as pd
from smard_utils.core.driver import EnergyDriver


class HomeDriver(EnergyDriver):
    """Driver for household PV + demand data in SMARD CSV format."""

    def load_data(self, csv_file_path: str) -> pd.DataFrame:
        """
        Load SMARD-format household CSV.

        Expected columns (semicolon-separated, comma decimal):
            Datum                              – date  YYYY-MM-DD
            Uhrzeit                            – time  HH:MM
            Photovoltaik [MWh]                 – solar kWh per period
            Gesamtverbrauch (Netzlast) [MWh]   – demand kWh per period

        Args:
            csv_file_path: Path to SMARD-format CSV file

        Returns:
            DataFrame with my_renew and my_demand columns
        """
        df = pd.read_csv(csv_file_path, sep=';', decimal=',')

        # Build datetime index
        df['DateTime'] = pd.to_datetime(
            df['Datum'] + ' ' + df['Uhrzeit'], dayfirst=True, format='mixed'
        )
        df = df.set_index('DateTime')

        # Locate solar and demand columns
        solar_col = demand_col = None
        for col in df.columns:
            if 'Photovoltaik' in col:
                solar_col = col
            elif 'Gesamtverbrauch' in col or 'Netzlast' in col:
                demand_col = col

        if solar_col is None:
            raise ValueError("Column 'Photovoltaik' not found in CSV")
        if demand_col is None:
            raise ValueError("Column 'Gesamtverbrauch'/'Netzlast' not found in CSV")

        solar = pd.to_numeric(df[solar_col], errors='coerce').fillna(0).clip(lower=0)
        demand = pd.to_numeric(df[demand_col], errors='coerce').fillna(0).clip(lower=0)

        self.resolution = ((df.index[1] - df.index[0]).seconds) / 3600

        result = pd.DataFrame(index=df.index)
        result['my_renew'] = solar.values   # kWh per period, positive
        result['my_demand'] = demand.values  # kWh per period, positive (community sign)

        # Spot-price columns not used by AutoarkyStrategy, but the BMS framework
        # requires them to be present so analytics can access them if needed.
        fix_price = self.basic_data_set.get('fix_price', 0.28)
        result['price_per_kwh'] = fix_price
        result['avrgprice'] = fix_price

        self._data = result
        return result

    def log_info(self, csv_file_path: str = ""):
        """
        Print diagnostic summary of loaded data.

        Call this after load_data() when console output is desired.
        Separating logging from data loading satisfies SRP (S4).

        Args:
            csv_file_path: Original file path to include in output
        """
        if self._data is None:
            return
        result = self._data
        print(f"Loading home data: {csv_file_path}")
        print(f"  Records   : {len(result)}")
        print(f"  Resolution: {self.resolution * 60:.0f} min")
        print(f"  Date range: {result.index[0]}  \u2192  {result.index[-1]}")
        print(f"  Solar     : {result['my_renew'].sum():.1f} kWh")
        print(f"  Demand    : {result['my_demand'].sum():.1f} kWh")

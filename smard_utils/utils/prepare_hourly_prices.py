"""
Prepare hourly spot market prices from netztransparenz.de raw data.

Downloads are available at:
https://www.netztransparenz.de/de-de/Erneuerbare-Energien-und-Umlagen/EEG/Transparenzanforderungen/Marktpr%C3%A4mie/Spotmarktpreis-nach-3-Nr-42a-EEG

The raw CSV has German formatting (semicolon separator, comma decimal)
with columns: Datum, von, Zeitzone von, bis, Zeitzone bis, Spotmarktpreis in ct/kWh

This script converts to a clean CSV with columns:
time, sdate, stimestart, zone_start, stimeend, zone_end, price
"""

import os
import pandas as pd
from datetime import datetime


def prepare_costs(year: int = 2024, raw_dir: str = None, output_dir: str = None):
    """
    Convert raw netztransparenz.de price CSV to processed format.

    Args:
        year: Year of the price data
        raw_dir: Directory containing raw CSV file (default: project bck/ directory)
        output_dir: Directory for output CSV file (default: project costs/ directory)
    """
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    if raw_dir is None:
        raw_dir = os.path.join(root_dir, "bck")
    if output_dir is None:
        output_dir = os.path.join(root_dir, "costs")

    raw_file = os.path.join(raw_dir, f"{year}-hour-price-raw.csv")
    output_file = os.path.join(output_dir, f"{year}-hour-price.csv")

    if not os.path.exists(raw_file):
        print(f"Raw price file not found: {raw_file}")
        return None

    df = pd.read_csv(raw_file, sep=';', decimal=',')

    # Map German column names to English
    column_mapping = {}
    for col in df.columns:
        if 'Datum' in col:
            column_mapping[col] = 'sdate'
        elif 'von' == col:
            column_mapping[col] = 'stimestart'
        elif 'bis' == col:
            column_mapping[col] = 'stimeend'
        elif 'Zeitzone von' == col:
            column_mapping[col] = 'zone_start'
        elif 'Zeitzone bis' == col:
            column_mapping[col] = 'zone_end'
        elif 'Spotmarktpreis' in col:
            column_mapping[col] = 'price'

    df = df.rename(columns=column_mapping)

    # Create datetime index from date + start time
    dtl = []
    for sd, st in zip(df["sdate"], df["stimestart"]):
        t = datetime.strptime(f"{sd} {st}", "%d.%m.%Y %H:%M")
        dtl.append(t)
    df["time"] = dtl
    df = df.set_index("time")

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    df.to_csv(output_file)
    print(f"Processed {len(df)} hourly prices for {year} -> {output_file}")

    return df


if __name__ == "__main__":
    import sys
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    prepare_costs(year)

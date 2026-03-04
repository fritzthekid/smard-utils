"""
SENEC to SMARD format converter.

Converts SENEC home battery monitoring CSV files to SMARD-compatible CSV
for use with community and solbatsys analysis tools.

Usage:
    senec2smardformat -i 2023-combine.csv -o 2023-smard.csv

Output is resampled to regular 5-minute intervals.  When using the output
with community or solbatsys, set:
    --solar-peak <peak_kW>   (printed after conversion)
    --year-demand <kWh>      (printed after conversion, adjust for partial year)
"""

import argparse
import os
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _parse_timestamp_col(df: pd.DataFrame) -> pd.Series:
    """Find and parse the SENEC 'Uhrzeit' timestamp column."""
    for col in df.columns:
        if "Uhrzeit" in col:
            return pd.to_datetime(df[col], format="%d.%m.%Y %H:%M:%S", errors="coerce")
    raise ValueError(
        "No 'Uhrzeit' column found in SENEC CSV. "
        "Expected format: 'DD.MM.YYYY HH:MM:SS'"
    )


def _find_col(df: pd.DataFrame, keyword: str) -> str:
    """Return the first column name containing keyword, or raise."""
    for col in df.columns:
        if keyword in col:
            return col
    raise ValueError(f"Column containing '{keyword}' not found in SENEC CSV")


def load_senec(csv_file_path: str) -> pd.DataFrame:
    """
    Load a SENEC yearly CSV and return a clean DataFrame.

    Returns a DataFrame with DatetimeIndex and columns:
        solar_kw   – PV generation (Stromerzeugung)
        demand_kw  – total household load (Stromverbrauch)

    Fixes applied:
        - Unparseable timestamps dropped
        - Out-of-order / backwards timestamps sorted (df[i+1] < df[i])
        - Duplicate timestamps deduplicated (keep first)
    """
    df = pd.read_csv(csv_file_path, sep=",", index_col=0)

    # Parse timestamps
    timestamps = _parse_timestamp_col(df)
    bad = timestamps.isna().sum()
    if bad:
        print(f"  Dropped {bad} rows with unparseable timestamps")
    df = df[timestamps.notna()].copy()
    df.index = timestamps[timestamps.notna()].values

    # Fix: sort ascending (handles timestamps going backwards)
    df.sort_index(inplace=True)

    # Fix: remove duplicates (keep first occurrence)
    n_before = len(df)
    df = df[~df.index.duplicated(keep="first")]
    removed = n_before - len(df)
    if removed:
        print(f"  Removed {removed} duplicate timestamps")

    # Extract required power columns (kW)
    solar_col = _find_col(df, "Stromerzeugung")
    demand_col = _find_col(df, "Stromverbrauch")

    result = pd.DataFrame(index=df.index)
    result["solar_kw"] = pd.to_numeric(df[solar_col], errors="coerce").clip(lower=0)
    result["demand_kw"] = pd.to_numeric(df[demand_col], errors="coerce").clip(lower=0)
    result.fillna(0, inplace=True)
    result.index.name = "time"
    return result


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------


def resample_to_5min(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample irregular SENEC data to a regular 5-minute grid.

    Steps:
    1. Aggregate any sub-5-min measurements within each bin (mean).
    2. Reindex to a complete 5-min grid covering the full date range.
    3. Interpolate gaps linearly (time-weighted, up to 1-hour gaps).
    4. Clamp to non-negative (physical constraint).
    """
    # Step 1: aggregate within each 5-min bin
    df_5min = df.resample("5min").mean()

    # Step 2: complete regular grid (no missing slots)
    start = df.index[0].floor("5min")
    end = df.index[-1].ceil("5min")
    grid = pd.date_range(start=start, end=end, freq="5min")
    df_5min = df_5min.reindex(grid)

    # Step 3: interpolate gaps (max 12 steps = 1 hour)
    df_5min = df_5min.interpolate(method="time", limit=12)
    df_5min.fillna(0, inplace=True)

    # Step 4: clamp
    df_5min = df_5min.clip(lower=0)

    df_5min.index.name = "time"
    return df_5min


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_smard(df: pd.DataFrame, output_path: str) -> None:
    """
    Write a SMARD-compatible CSV from 5-minute resampled SENEC data.

    Column convention:
        Photovoltaik [MWh]                 – solar energy per 5-min period (kWh)
        Wind Onshore [MWh]                 – zero (no wind data in SENEC)
        Gesamtverbrauch (Netzlast) [MWh]   – demand energy per 5-min period (kWh)

    Although labelled [MWh] (required for SolarDriver column detection), the
    values are in kWh because individual household data is three orders of
    magnitude smaller than national SMARD data.  The SolarDriver scaling
    (solar_col * solar_max_power / max(solar_col)) compensates automatically
    when solar_max_power is set to the actual PV peak power in kW.

    Field separator: semicolon (;)
    Decimal separator: comma (,)  – matches SMARD / SolarDriver convention
    """
    resolution_h = 5 / 60  # 5-minute periods

    out = pd.DataFrame(index=df.index)
    out["Datum"] = df.index.strftime("%Y-%m-%d")
    out["Uhrzeit"] = df.index.strftime("%H:%M")
    out["Photovoltaik [MWh]"] = df["solar_kw"] * resolution_h
    out["Wind Onshore [MWh]"] = 0.0
    out["Gesamtverbrauch (Netzlast) [MWh]"] = df["demand_kw"] * resolution_h

    out.to_csv(
        output_path,
        sep=";",
        decimal=",",
        index=False,
        float_format="%.4f",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="senec2smardformat",
        description=(
            "Convert SENEC home battery CSV to SMARD-compatible format.\n"
            "Output can be used directly with: community, solbatsys"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        metavar="FILE",
        help="Input SENEC CSV file (e.g. 2023-combine.csv)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="FILE",
        help="Output SMARD-format CSV file",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)

    print(f"Loading SENEC data: {args.input}")
    df_raw = load_senec(args.input)
    print(f"  Records loaded : {len(df_raw)}")
    print(f"  Date range     : {df_raw.index[0]}  →  {df_raw.index[-1]}")

    print("Resampling to 5-minute intervals...")
    df_5min = resample_to_5min(df_raw)
    print(f"  Output records : {len(df_5min)}")

    print(f"Writing: {args.output}")
    write_smard(df_5min, args.output)

    # Print hints for downstream tools
    peak_solar_kw = df_raw["solar_kw"].max()
    total_solar_kwh = (df_raw["solar_kw"] * (5 / 60)).sum()
    total_demand_kwh = (df_raw["demand_kw"] * (5 / 60)).sum()

    days = (df_raw.index[-1] - df_raw.index[0]).days + 1
    scale = 365 / max(days, 1)

    print()
    print("Use the output file with community or solbatsys:")
    print(f"  --solar-peak  {peak_solar_kw:.1f}")
    print(
        f"  --year-demand {total_demand_kwh:.0f}  "
        f"({'full year' if abs(scale - 1) < 0.05 else f'partial year, ~{total_demand_kwh * scale:.0f} annualised'})"
    )
    print(f"  (solar yield: {total_solar_kwh:.0f} kWh over {days} days)")


if __name__ == "__main__":
    main()

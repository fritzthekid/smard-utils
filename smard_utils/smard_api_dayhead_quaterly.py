from datetime import datetime, timedelta

import pandas as pd
import requests


def get_smard_day_ahead(year, week_offset=0):
    """
    SMARD API - Wochenweise Daten
    Filter 4169 = Day-Ahead Preis DE/LU
    """
    # Berechne Montag der Woche
    start_date = datetime(year, 1, 1)
    start_date += timedelta(days=-start_date.weekday())  # Zum Montag
    start_date += timedelta(weeks=week_offset)

    timestamp_ms = int(start_date.timestamp() * 1000)

    # Timestamps abrufen
    index_url = "https://www.smard.de/app/chart_data/4169/DE/index_quarterhour.json"
    timestamps = requests.get(index_url).json()["timestamps"]

    # Passenden Timestamp finden
    closest = min(timestamps, key=lambda x: abs(x - timestamp_ms))

    # Daten abrufen
    data_url = f"https://www.smard.de/app/chart_data/4169/DE/4169_DE_quarterhour_{closest}.json"
    data = requests.get(data_url).json()

    df = pd.DataFrame(data["series"], columns=["timestamp_ms", "price"])
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms")
    df = df.dropna()

    return df[["timestamp", "price"]]


# Alle Wochen 2024 durchlaufen
dfs = []
for week in range(0, 52):
    try:
        df = get_smard_day_ahead(2024, week)
        dfs.append(df)
    except:
        print(f"Week {week} failed")

df_2024_full = pd.concat(dfs).drop_duplicates().sort_values("timestamp")

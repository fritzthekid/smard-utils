import requests
import pandas as pd
from datetime import datetime

def get_day_ahead_prices(year, month=None):
    """
    Holt Day-Ahead Preise von Energy-Charts
    Ab 30.09.2025: 15-Min Auflösung!
    """
    if month:
        start = f"{year}-{month:02d}-01T00:00"
        end = f"{year}-{month:02d}-28T23:59"
    else:
        start = f"{year}-01-01T00:00"
        end = f"{year}-12-31T23:59"
    
    url = "https://api.energy-charts.info/price"
    params = {
        "bzn": "DE-LU",
        "start": start,
        "end": end
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    df = pd.DataFrame({
        'timestamp': pd.to_datetime(data['unix_seconds'], unit='s'),
        'price_eur_mwh': data['price']
    })
    
    return df

# Beispiel: 2020 + 2024
df_2020 = get_day_ahead_prices(2020)
df_2024 = get_day_ahead_prices(2024)

print(f"2020: {len(df_2020)} Preispunkte")
print(f"2024: {len(df_2024)} Preispunkte")
print(f"Durchschnitt 2020: {df_2020['price_eur_mwh'].mean():.2f} €/MWh")
print(f"Durchschnitt 2024: {df_2024['price_eur_mwh'].mean():.2f} €/MWh")

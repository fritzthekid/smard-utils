import requests
import pandas as pd

def get_intraday_v1_2024():
    # Modul 1224: Intraday-Auktion 15 Min
    # Wir nutzen den v1-Endpunkt, der oft lückenloser ist
    modul = "1224"
    url = f"https://www.smard.de/pj-api/v1/app/chart/data/{modul}/DE/{modul}_DE_quarterhour_1704063600000.json"
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers)
    
    if r.status_code != 200:
        return f"Fehler: {r.status_code}"
    
    data = r.json()
    df = pd.DataFrame(data['series'], columns=['timestamp', 'price'])
    
    # Zeitumwandlung
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Europe/Berlin')
    
    # Filter auf das Jahr 2024
    df = df[df['datetime'].dt.year == 2024]
    
    # Validitäts-Check
    valid_share = (df['price'].notnull() & (df['price'] != 0)).sum() / len(df) * 100
    print(f"Datensatz geladen. Gültige Preise (ungleich 0/NaN): {valid_share:.2f}%")
    
    return df

df_intraday_final = get_intraday_v1_2024()
print(df_intraday_final)

#!/usr/bin/env python3
"""
SENEC PV-Batterie Jahres-Downloader
Automatischer Download der SENEC-Daten für ein komplettes Jahr (wochenweise)
5-Minuten-Auflösung von mein-senec.de
"""

import requests
import time
import os
from datetime import datetime, timedelta
import pandas as pd
import getpass
from urllib.parse import urljoin

class SENECDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'de-DE,de;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.base_url = "https://mein-senec.de"
        self.logged_in = False
        self.anlage_nummer = 0  # Standard-Anlagennummer
        
    def login(self, username, password):
        """Login zu SENEC Portal"""
        print("🔐 Anmeldung bei SENEC Portal...")
        
        try:
            # Login-Seite aufrufen
            # https://www.mein-senec.de/endkunde/oauth2/authorization/endkunde-portal
            # login_page_url = f"{self.base_url}/endkunde/login"
            login_page_url = f"https://www.mein-senec.de/endkunde/oauth2/authorization/endkunde-portal"
            login_page = self.session.get(login_page_url)
            
            if login_page.status_code != 200:
                print(f"❌ Login-Seite nicht erreichbar: {login_page.status_code}")
                return False
            
            # Login-Daten (muss eventuell angepasst werden je nach HTML-Struktur)
            login_data = {
                'username': username,
                'password': password,
                # Eventuell weitere versteckte Felder nötig
            }
            
            # Prüfe ob CSRF-Token oder andere versteckte Felder nötig sind
            if 'csrf' in login_page.text.lower():
                print("⚠️  CSRF-Token erkannt - eventuell zusätzliche Felder nötig")
            
            # Login durchführen
            login_url = f"{self.base_url}/endkunde/login"
            response = self.session.post(
                login_url, 
                data=login_data,
                allow_redirects=True
            )
            
            # Prüfen ob Login erfolgreich (Dashboard oder Hauptseite)
            if response.status_code == 200 and ('dashboard' in response.url.lower() or 'main' in response.url.lower()):
                print("✅ Erfolgreich angemeldet!")
                self.logged_in = True
                return True
            elif 'logout' in response.text.lower() or 'abmelden' in response.text.lower():
                print("✅ Erfolgreich angemeldet!")
                self.logged_in = True
                return True
            else:
                print("❌ Login fehlgeschlagen!")
                print(f"Status: {response.status_code}, URL: {response.url}")
                return False
                
        except Exception as e:
            print(f"❌ Fehler beim Login: {e}")
            return False
    
    def test_download_url(self, week, year):
        """Teste ob Download-URL funktioniert"""
        url = f"{self.base_url}/endkunde/api/statistischeDaten/download"
        params = {
            'anlageNummer': self.anlage_nummer,
            'woche': week,
            'jahr': year
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            print(f"🔍 Test-URL: {response.url}")
            print(f"Status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type', 'unbekannt')}")
            print(f"Content-Length: {len(response.content)} bytes")
            
            if response.status_code == 200:
                # Prüfe ob es wirklich CSV-Daten sind
                content_preview = response.text[:200] if response.text else "Leer"
                print(f"Vorschau: {content_preview}")
                return True
            else:
                print(f"❌ Download fehlgeschlagen: {response.status_code}")
                if response.text:
                    print(f"Fehler-Details: {response.text[:300]}")
                return False
                
        except Exception as e:
            print(f"❌ Fehler beim Test-Download: {e}")
            return False
    
    def download_week_data(self, week, year, output_file):
        """CSV-Daten für eine Woche herunterladen"""
        url = f"{self.base_url}/endkunde/api/statistischeDaten/download"
        params = {
            'anlageNummer': self.anlage_nummer,
            'woche': week,
            'jahr': year
        }
        
        try:
            print(f"📥 Download Woche {week}/{year}...")
            
            response = self.session.get(url, params=params, timeout=60)
            
            if response.status_code == 200:
                # Prüfe Content-Type
                content_type = response.headers.get('content-type', '')
                
                if 'csv' in content_type.lower() or response.text.strip().startswith(('Datum', 'Zeit', 'timestamp')):
                    # Ist CSV-Datei
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    
                    # Prüfe ob Datei Inhalt hat
                    file_size = os.path.getsize(output_file)
                    if file_size > 100:  # Mindestens 100 Bytes
                        print(f"✅ Gespeichert: {output_file} ({file_size} bytes)")
                        return True
                    else:
                        print(f"⚠️  Datei sehr klein: {file_size} bytes")
                        return False
                        
                elif 'html' in content_type.lower():
                    print("❌ HTML-Antwort erhalten (eventuell nicht angemeldet)")
                    return False
                else:
                    print(f"⚠️  Unbekannter Content-Type: {content_type}")
                    # Versuche trotzdem zu speichern
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    return True
            else:
                print(f"❌ Download fehlgeschlagen: Status {response.status_code}")
                if response.text:
                    error_preview = response.text[:200]
                    print(f"Fehler-Details: {error_preview}")
                return False
                
        except Exception as e:
            print(f"❌ Fehler beim Download: {e}")
            return False
    
    def get_weeks_in_year(self, year):
        """Berechne alle Wochen-Nummern für ein Jahr"""
        # ISO-Wochen-Nummern: 1-52 (manchmal 53)
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)
        
        # Erste und letzte Kalenderwoche des Jahres finden
        first_week = start_date.isocalendar()[1]
        last_week = end_date.isocalendar()[1]
        
        # Spezialfall: Wenn letzte Woche im nächsten Jahr liegt
        if last_week == 1:
            last_week = 52
            # Prüfe ob Jahr 53 Wochen hat
            test_date = datetime(year, 12, 28)  # Immer in der letzten Woche des Jahres
            if test_date.isocalendar()[1] == 53:
                last_week = 53
        
        weeks = list(range(first_week, last_week + 1))
        
        # Für den Fall dass Jahr nicht mit Woche 1 beginnt
        if first_week > 1:
            weeks = list(range(1, last_week + 1))
        
        return weeks

def main():
    """Hauptfunktion"""
    print("🔋 SENEC Batterie-Daten Jahres-Downloader")
    print("=" * 50)
    
    # Jahr eingeben
    try:
        year = int(input("Jahr eingeben (z.B. 2024): "))
    except ValueError:
        year = 2024
        print(f"Verwende Standard-Jahr: {year}")
    
    # Anlagennummer (falls abweichend)
    try:
        anlage_input = input("Anlagennummer (Enter für 0): ").strip()
        anlage_nummer = int(anlage_input) if anlage_input else 0
    except ValueError:
        anlage_nummer = 0
    
    # Anmeldedaten
    print(f"\n🔐 SENEC Portal Anmeldedaten:")
    username = input("Benutzername: ")
    password = getpass.getpass("Passwort: ")
    
    # Output-Verzeichnis
    output_dir = f"senec_data_{year}"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Downloader initialisieren
    downloader = SENECDownloader()
    downloader.anlage_nummer = anlage_nummer
    
    # Login versuchen
    login_success = downloader.login(username, password)
    
    if not login_success:
        print("\n❌ Login fehlgeschlagen!")
        print("Optionen:")
        print("1. Anmeldedaten prüfen")
        print("2. Direkt Download ohne Login versuchen (falls API öffentlich)")
        
        choice = input("Trotzdem versuchen? (j/n): ").lower()
        if choice != 'j':
            return
    
    # Wochen für das Jahr bestimmen
    weeks = downloader.get_weeks_in_year(year)
    print(f"\n📅 Wochen zu downloaden: {weeks[0]} bis {weeks[-1]} ({len(weeks)} Wochen)")
    
    # Erst einen Test-Download
    print(f"\n🧪 Test-Download für Woche {weeks[0]}...")
    if not downloader.test_download_url(weeks[0], year):
        print("❌ Test-Download fehlgeschlagen!")
        return
    
    # Alle Wochen downloaden
    successful_downloads = 0
    all_files = []
    
    for week in weeks:
        filename = f"senec_woche_{week:02d}_{year}.csv"
        filepath = os.path.join(output_dir, filename)
        
        success = downloader.download_week_data(week, year, filepath)
        
        if success:
            successful_downloads += 1
            all_files.append(filepath)
        
        # Pause zwischen Downloads (höflich sein)
        time.sleep(1)
    
    print(f"\n" + "=" * 50)
    print(f"✅ Download abgeschlossen!")
    print(f"Erfolgreich: {successful_downloads}/{len(weeks)} Wochen")
    
    # CSV-Dateien zusammenfügen
    if all_files:
        print(f"\n🔗 Füge {len(all_files)} CSV-Dateien zusammen...")
        combine_senec_csv_files(all_files, os.path.join(output_dir, f"senec_{year}_komplett.csv"))
    
    print(f"\n📁 Alle Dateien gespeichert in: {output_dir}/")
    print(f"📊 Mit 5-Minuten-Auflösung ergeben das ca. {successful_downloads * 7 * 24 * 12:,} Datenpunkte!")

def combine_senec_csv_files(csv_files, output_file):
    """Kombiniere alle SENEC CSV-Dateien zu einer"""
    try:
        combined_df = pd.DataFrame()
        
        print("Verarbeite CSV-Dateien...")
        for i, csv_file in enumerate(csv_files, 1):
            if os.path.exists(csv_file) and os.path.getsize(csv_file) > 100:
                try:
                    # Versuche verschiedene CSV-Trennzeichen
                    for sep in [';', ',', '\t']:
                        try:
                            df = pd.read_csv(csv_file, sep=sep, encoding='utf-8')
                            if len(df.columns) > 1:  # Erfolgreich geparst
                                break
                        except:
                            continue
                    else:
                        # Falls kein Trennzeichen funktioniert
                        df = pd.read_csv(csv_file, encoding='utf-8')
                    
                    if not df.empty:
                        combined_df = pd.concat([combined_df, df], ignore_index=True)
                        print(f"  {i:2d}/{len(csv_files)}: {os.path.basename(csv_file)} ({len(df)} Zeilen)")
                    
                except Exception as e:
                    print(f"  ⚠️  Fehler bei {csv_file}: {e}")
        
        if not combined_df.empty:
            # Duplikate entfernen falls vorhanden
            original_count = len(combined_df)
            
            # Versuche nach Datum/Zeit zu sortieren (Spaltenname kann variieren)
            date_columns = [col for col in combined_df.columns if any(word in col.lower() for word in ['datum', 'zeit', 'time', 'timestamp'])]
            
            if date_columns:
                try:
                    combined_df = combined_df.drop_duplicates(subset=date_columns)
                    combined_df = combined_df.sort_values(date_columns)
                    print(f"📅 Sortiert nach: {date_columns}")
                except:
                    print("⚠️  Sortierung nicht möglich")
            
            # Speichern
            combined_df.to_csv(output_file, sep=';', index=False, encoding='utf-8')
            
            duplicate_count = original_count - len(combined_df)
            print(f"\n✅ Kombinierte Datei erstellt: {output_file}")
            print(f"📊 Gesamt-Datensätze: {len(combined_df):,}")
            if duplicate_count > 0:
                print(f"🗑️  Duplikate entfernt: {duplicate_count}")
            print(f"📋 Spalten: {list(combined_df.columns)}")
            
            # Zeige Zeitraum
            if date_columns:
                try:
                    first_date = combined_df[date_columns[0]].iloc[0]
                    last_date = combined_df[date_columns[0]].iloc[-1]
                    print(f"⏰ Zeitraum: {first_date} bis {last_date}")
                except:
                    pass
        
    except Exception as e:
        print(f"❌ Fehler beim Kombinieren: {e}")

if __name__ == "__main__":
    main()
    
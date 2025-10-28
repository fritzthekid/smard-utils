#!/usr/bin/env python3
"""
SMARD Energy Data Downloader - Fixed Version
Downloads German energy generation data from smard.de API for the year 2024
Uses the correct SMARD API endpoints instead of the web interface

based on:
https://github.com/bundesAPI/smard-api
https://github.com/mobility-university/SMARD/tree/main

"""

import requests
import time
import os
from datetime import datetime, timedelta
import pandas as pd
import json
from typing import List, Dict, Tuple

resolution = {"name":'quarterhour',"seconds":60*60*60*0.25}

class SmardAPIDownloader:
    def __init__(self):
        self.base_url = "https://www.smard.de/app/chart_data"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Filter IDs and their descriptions
        self.filters = {
            '1223': 'Braunkohle',
            '1224': 'Kernenergie', 
            '1225': 'Wind Offshore',
            '1226': 'Wasserkraft',
            '1227': 'Sonstige Konventionelle',
            '1228': 'Sonstige Erneuerbare',
            '4066': 'Biomasse',
            '4067': 'Wind Onshore', 
            '4068': 'Photovoltaik',
            '4069': 'Steinkohle',
            '4070': 'Pumpspeicher',
            '4071': 'Erdgas',
            '410': 'Gesamtverbrauch (Netzlast)',
            '4359': 'Residuallast',
            '4387': 'Pumpspeicher Verbrauch'
        }
        
        self.region = 'LU'
        self.resolution = resolution["name"]
        
    def get_available_timestamps(self, filter_id: str) -> List[int]:
        """Get available timestamps for a specific filter"""
        url = f"{self.base_url}/{filter_id}/{self.region}/index_{self.resolution}.json"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # The response contains an array of timestamps
            timestamps = data.get('timestamps', [])
            return sorted(timestamps)
            
        except Exception as e:
            print(f"✗ Error getting timestamps for filter {filter_id}: {e}")
            return []
    
    def get_timeseries_data(self, filter_id: str, timestamp: int) -> Dict:
        """Get timeseries data for a specific filter and timestamp"""
        url = f"{self.base_url}/{filter_id}/{self.region}/{filter_id}_{self.region}_{self.resolution}_{timestamp}.json"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data
            
        except Exception as e:
            print(f"✗ Error getting data for filter {filter_id}, timestamp {timestamp}: {e}")
            return {}
    
    def timestamp_to_datetime(self, timestamp: int) -> datetime:
        """Convert milliseconds timestamp to datetime"""
        return datetime.fromtimestamp(timestamp / 1000)
    
    def datetime_to_timestamp(self, dt: datetime) -> int:
        """Convert datetime to milliseconds timestamp"""
        return int(dt.timestamp() * 1000)
    
    def filter_timestamps_for_year(self, timestamps: List[int], year: int = 2024) -> List[int]:
        """Filter timestamps to only include those from the specified year"""
        start_year = datetime(year, 1, 1)
        end_year = datetime(year, 12, 31, 23, 59, 59)
        
        start_ts = self.datetime_to_timestamp(start_year)
        end_ts = self.datetime_to_timestamp(end_year)
        
        filtered = [ts for ts in timestamps if start_ts <= ts <= end_ts]
        return sorted(filtered)
    
    def download_filter_data(self, filter_id: str, year: int = 2024) -> pd.DataFrame:
        """Download all data for a specific filter for the given year"""
        print(f"Downloading data for {self.filters.get(filter_id, filter_id)}...")
        
        # Get available timestamps
        all_timestamps = self.get_available_timestamps(filter_id)
        if not all_timestamps:
            print(f"✗ No timestamps available for filter {filter_id}")
            return pd.DataFrame()
        
        # Filter for the specified year
        year_timestamps = self.filter_timestamps_for_year(all_timestamps, year)
        if not year_timestamps:
            print(f"✗ No timestamps found for year {year} in filter {filter_id}")
            return pd.DataFrame()
        
        print(f"Found {len(year_timestamps)} data points for {year}")
        
        all_data = []
        
        for i, timestamp in enumerate(year_timestamps):
            if i > 0 and i % 10 == 0:
                print(f"  Progress: {i}/{len(year_timestamps)} ({i/len(year_timestamps)*100:.1f}%)")
            
            data = self.get_timeseries_data(filter_id, timestamp)
            if data and 'series' in data:
                # Process the series data
                for entry in data['series']:
                    if len(entry) >= 2 and entry[1] is not None:
                        timestamp_ms = entry[0]
                        value = entry[1]
                        dt = self.timestamp_to_datetime(timestamp_ms)
                        
                        all_data.append({
                            'Datum': dt.strftime('%Y-%m-%d'),
                            'Uhrzeit': dt.strftime('%H:%M'),
                            'Timestamp': timestamp_ms,
                            'DateTime': dt,
                            f'{self.filters.get(filter_id, filter_id)} [MWh]': value
                        })
            
            # Small delay to be respectful
            time.sleep(0.1)
        
        if all_data:
            df = pd.DataFrame(all_data)
            df = df.drop_duplicates(subset=['Timestamp'])
            df = df.sort_values('Timestamp')
            print(f"✓ Downloaded {len(df)} records for {self.filters.get(filter_id, filter_id)}")
            return df
        else:
            print(f"✗ No data downloaded for filter {filter_id}")
            return pd.DataFrame()
    
    def download_all_data(self, year: int = 2024, output_dir: str = "smard_data") -> None:
        """Download all energy data for the specified year"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        print(f"Starting download of SMARD data for year {year}")
        print("=" * 60)
        
        all_dataframes = {}
        successful_downloads = 0
        
        # Download data for each filter
        for filter_id in self.filters.keys():
            print(f"\n{filter_id}: {self.filters[filter_id]}")
            print("-" * 40)
            
            df = self.download_filter_data(filter_id, year)
            if not df.empty:
                all_dataframes[filter_id] = df
                successful_downloads += 1
                
                # Save individual filter data
                filename = f"{output_dir}/smard_{year}_{filter_id}_{self.filters[filter_id].replace(' ', '_')}.csv"
                df.to_csv(filename, sep=';', decimal=',', index=False, encoding='utf-8')
                print(f"✓ Saved to: {filename}")
            
            # Delay between different filters
            time.sleep(1)
        
        print(f"\n" + "=" * 60)
        print(f"Download completed!")
        print(f"Successful downloads: {successful_downloads}/{len(self.filters)}")
        
        # Combine all data into one DataFrame
        if all_dataframes:
            print("\nCombining all data...")
            self.combine_all_data(all_dataframes, year, output_dir)
    
    def combine_all_data(self, dataframes: Dict[str, pd.DataFrame], year: int, output_dir: str) -> None:
        """Combine all filter dataframes into one comprehensive dataset"""
        if not dataframes:
            print("No data to combine!")
            return
        
        # Start with the first dataframe as base
        first_key = list(dataframes.keys())[0]
        combined_df = dataframes[first_key][['Datum', 'Uhrzeit', 'Timestamp', 'DateTime']].copy()
        
        # Add data from each filter
        for filter_id, df in dataframes.items():
            value_column = [col for col in df.columns if '[MWh]' in col][0]
            combined_df = combined_df.merge(
                df[['Timestamp', value_column]], 
                on='Timestamp', 
                how='outer'
            )
        
        # Sort by timestamp and clean up
        combined_df = combined_df.sort_values('Timestamp')
        combined_df = combined_df.drop(['Timestamp'], axis=1)
        
        # Save combined data
        output_file = f"{output_dir}/smard_{year}_complete.csv"
        combined_df.to_csv(output_file, sep=';', decimal=',', index=False, encoding='utf-8')
        
        print(f"✓ Combined data saved to: {output_file}")
        print(f"Total rows: {len(combined_df)}")
        print(f"Date range: {combined_df['Datum'].min()} to {combined_df['Datum'].max()}")
        print(f"Columns: {len(combined_df.columns)}")
        
        # Show summary statistics
        print(f"\nData summary:")
        for col in combined_df.columns:
            if '[MWh]' in col:
                non_null_count = combined_df[col].notna().sum()
                print(f"  {col}: {non_null_count} data points")

def main():
    """Main function"""
    downloader = SmardAPIDownloader()
    
    print("SMARD Energy Data Downloader (API Version)")
    print("Downloading German energy generation data for 2024")
    print("Using the official SMARD API endpoints")
    print()
    
    # Download the full year
    downloader.download_all_data(year=2024)
    
    print(f"\n🎉 Download completed!")
    print("Files created in 'smard_data/' directory:")
    print("- Individual CSV files for each energy source")
    print("- smard_2024_complete.csv - Combined data file")

if __name__ == "__main__":
    main()

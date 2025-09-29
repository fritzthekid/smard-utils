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
import json
from datetime import datetime, timedelta
import time
import os
import zipfile
import io
import logging
import argparse
from urllib.parse import urlencode

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_smard_data(start_date, end_date, module_ids, output_dir="smard_data"):
    """
    Downloads electricity generation data from smard.de for a given period.

    The data is downloaded in chunks of up to 14 days, as the API seems to have a limit.
    The downloaded zip files are extracted, and the contained CSV files are saved.

    Args:
        start_date (datetime): The start date of the data period.
        end_date (datetime): The end date of the data period.
        module_ids (list): A list of integer module IDs for the data categories.
        output_dir (str): The directory where the CSV files will be saved.
    """
    base_url = "https://www.smard.de/nip-download-manager/nip/download/market-data"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logging.info(f"Created output directory: {output_dir}")

    current_date = start_date
    while current_date <= end_date:
        # The API seems to handle up to 14 days per request well.
        chunk_end_date = min(current_date + timedelta(days=13), end_date)
        
        from_timestamp = int(current_date.timestamp() * 1000)
        to_timestamp = int(chunk_end_date.timestamp() * 1000) + (24 * 60 * 60 * 1000 - 1) # end of day

        market_data_attributes = {
            "resolution": "hour",
            "from": from_timestamp,
            "to": to_timestamp,
            "moduleIds": module_ids,
            "selectedCategory": 1, # Stromerzeugung
            "activeChart": False,
            "style": "color",
            "categoriesModuleOrder": {},
            "region": "DE",
            "language": "de",
            "format": "CSV"
        }

        # The server expects a URL-encoded form where 'request_form' contains the JSON string.
        # We must manually encode it to get the correct format.
        payload = urlencode({'request_form': json.dumps(market_data_attributes)})

        # The server is particular about headers. We need to mimic a browser request.
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }

        logging.info(f"Requesting data from {current_date.strftime('%Y-%m-%d')} to {chunk_end_date.strftime('%Y-%m-%d')}...")

        if True:
            # Send the request with the correct headers and payload
            response = requests.post(base_url, headers=headers, data=payload)
            response.raise_for_status()

            # The response is a zip file in memory
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for file_info in z.infolist():
                    if file_info.filename.endswith('.csv'):
                        # Create a unique filename to avoid overwriting
                        output_filename = f"Stromerzeugung_{current_date.strftime('%Y%m%d')}_{chunk_end_date.strftime('%Y%m%d')}.csv"
                        output_path = os.path.join(output_dir, output_filename)
                        z.extract(file_info, path=output_dir)
                        # Rename the extracted file
                        os.rename(os.path.join(output_dir, file_info.filename), output_path)
                        logging.info(f"  -> Saved {output_path}")

        elif False: # requests.exceptions.RequestException as e:
            logging.error(f"An error occurred during request: {e}")
        else: # zipfile.BadZipFile:
            logging.error("Downloaded file is not a valid zip file. Response text: %s", response.text[:200])

        # Move to the next time window
        current_date = chunk_end_date + timedelta(days=1)
        
        # Be polite to the server
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download electricity generation data from smard.de.")
    parser.add_argument('--start', type=str, default='2024-01-01', help='Start date in YYYY-MM-DD format.')
    parser.add_argument('--end', type=str, default='2024-12-31', help='End date in YYYY-MM-DD format.')
    parser.add_argument('--output', type=str, default='smard_data', help='Output directory for CSV files.')
    args = parser.parse_args()

    try:
        start_date = datetime.strptime(args.start, '%Y-%m-%d')
        end_date = datetime.strptime(args.end, '%Y-%m-%d')
    except ValueError:
        logging.error("Invalid date format. Please use YYYY-MM-DD.")
        exit(1)

    # --- Configuration ---
    # Module IDs from your example URL for "Realisierte Erzeugung" (Electricity Generation)
    # This can be changed for other data categories.
    STROMERZEUGUNG_MODULE_IDS = [
        1004066, 1004067, 1004068, 1001223, 1004069, 1004071,
        1004070, 1001226, 1001228, 1001227, 1001225, 2005097,
        5000410, 6000411
    ]

    logging.info(f"Starting download of smard.de data from {args.start} to {args.end}...")
    get_smard_data(start_date, end_date, STROMERZEUGUNG_MODULE_IDS, output_dir=args.output)
    logging.info("Download process finished.")

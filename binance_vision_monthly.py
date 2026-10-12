import os
import requests
import zipfile
import pandas as pd
from datetime import datetime

symbol = "SOLUSDT"
interval = "15m"
start_year = 2021
end_year = datetime.now().year
current_year = datetime.now().year
current_month = datetime.now().month

BASE = "https://data.binance.vision/data/spot/monthly/klines"

download_folder = f"data_{symbol}"
os.makedirs(download_folder, exist_ok=True)

csv_files = []

# STEP 1 — DOWNLOAD FILES
for year in range(start_year, end_year + 1):
    for month in range(1, 13):

        if year == current_year and month > current_month:
            break
        
        mm = f"{month:02d}"
        url = f"{BASE}/{symbol}/{interval}/{symbol}-{interval}-{year}-{mm}.zip"
        local_zip = f"{download_folder}/{symbol}-{year}-{mm}.zip"

        r = requests.get(url)
        if r.status_code == 200:
            with open(local_zip, "wb") as f:
                f.write(r.content)

            with zipfile.ZipFile(local_zip, 'r') as z:
                z.extractall(download_folder)

            os.remove(local_zip)

            csv_file = f"{download_folder}/{symbol}-{interval}-{year}-{mm}.csv"
            csv_files.append(csv_file)

            print(f"Downloaded {symbol} {year}-{mm}")
        else:
            print(f"No data for {symbol} {year}-{mm}")

# STEP 2 — MERGE ALL CSV FILES
all_dfs = [pd.read_csv(file, header=None) for file in csv_files]
merged = pd.concat(all_dfs, ignore_index=True)

# Remove corrupted rows
merged = merged[(merged[0] > 946684800000) & (merged[0] < 1893456000000)]

merged.columns = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_base_volume", "taker_quote_volume", "ignore"
]

merged["open_time"] = pd.to_datetime(merged["open_time"], unit="ms")
merged = merged.sort_values("open_time")

# SAVE INSIDE FOLDER
output_file = f"{download_folder}/{symbol}_{interval}_merged.csv"
merged.to_csv(output_file, index=False)

print("\n✅ FINAL FILE SAVED:", output_file)

import os
import requests
import zipfile
import pandas as pd
from datetime import datetime

# --- CONFIGURATION ---
symbol = "SOLUSDT"
interval = "5m"
start_year = 2025

# Get current date
now = datetime.now()
end_year = now.year
current_month = now.month

BASE = "https://data.binance.vision/data/spot/monthly/klines"

download_folder = f"data_{symbol}"
os.makedirs(download_folder, exist_ok=True)

all_dfs = []

print(f"🚀 Starting download for {symbol} ({interval}) from {start_year} to present...")

# STEP 1 — DOWNLOAD & LOAD MONTHS
for year in range(start_year, end_year + 1):
    for month in range(1, 13):
        
        # STOP CONDITION: Binance monthly data is only available for COMPLETED months.
        if year == end_year and month >= current_month:
            break
        
        mm = f"{month:02d}"
        file_name = f"{symbol}-{interval}-{year}-{mm}"
        url = f"{BASE}/{symbol}/{interval}/{file_name}.zip"
        local_zip = f"{download_folder}/{file_name}.zip"

        print(f"Downloading {year}-{mm}...", end=" ")
        
        try:
            r = requests.get(url, stream=True)
            if r.status_code == 200:
                with open(local_zip, "wb") as f:
                    for chunk in r.iter_content(chunk_size=128):
                        f.write(chunk)

                with zipfile.ZipFile(local_zip, 'r') as z:
                    csv_name = z.namelist()[0]
                    z.extractall(download_folder)

                csv_path = f"{download_folder}/{csv_name}"
                df = pd.read_csv(csv_path, header=None)
                all_dfs.append(df)

                os.remove(local_zip)
                os.remove(csv_path)

                print("✅ OK")
            else:
                print(f"❌ Not Found (Status: {r.status_code})")
        except Exception as e:
            print(f"⚠️ Error: {e}")

# STEP 2 — MERGE & CLEAN
if len(all_dfs) > 0:
    print("\nProcessing merged data...")
    merged = pd.concat(all_dfs, ignore_index=True)

    # 1. NAME COLUMNS
    merged.columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base_volume", "taker_quote_volume", "ignore"
    ]

    # 2. SANITY CHECK (Removes garbage rows causing errors)
    merged["open_time"] = pd.to_numeric(merged["open_time"], errors='coerce')
    merged = merged.dropna(subset=["open_time"])

    # Valid range: Year 2020 (1577836800000) to Year 2030 (1893456000000)
    valid_range = (merged["open_time"] > 1500000000000) & (merged["open_time"] < 1900000000000)
    merged = merged[valid_range]

    # 3. CONVERT TYPES
    numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume"]
    for col in numeric_cols:
        merged[col] = pd.to_numeric(merged[col], errors='coerce')

    # 4. CONVERT TIME
    merged["open_time"] = pd.to_datetime(merged["open_time"], unit="ms")
    merged["close_time"] = pd.to_datetime(merged["close_time"], unit="ms")

    # 5. FINAL CLEANUP
    merged = merged.sort_values("open_time")
    merged.reset_index(drop=True, inplace=True)

    # SAVE
    output_file = f"{symbol}_{interval}_merged.csv"
    merged.to_csv(output_file, index=False)

    print(f"\n🎉 SUCCESS! Data saved to: {output_file}")
    print(f"📊 Total Rows: {len(merged)}")
    if not merged.empty:
        print(f"📅 Range: {merged['open_time'].min()} to {merged['open_time'].max()}")
    
    try:
        os.rmdir(download_folder)
    except:
        pass

else:
    print("\n❌ No data was downloaded.")
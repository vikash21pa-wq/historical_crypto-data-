import requests
import pandas as pd
import datetime as dt
import time

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

def to_seconds(ts):
    return int(ts.timestamp())

def get_delta_candles(symbol, resolution, start_ist, end_ist):
    url = "https://api.india.delta.exchange/v2/history/candles"
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "start": to_seconds(start_ist),
        "end": to_seconds(end_ist)
    }

    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200:
        return None

    j = r.json()
    if not j.get("success"):
        return None

    candles = j.get("result", [])
    if not candles:
        return None

    df = pd.DataFrame(candles)
    df["Date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(IST)
    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    })

    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df = df.astype({
        "Open": float,
        "High": float,
        "Low": float,
        "Close": float,
        "Volume": float
    })

    return df.sort_values("Date")


# =====================
# CONFIG
# =====================
SYMBOL = "SOLUSD"
RESOLUTION = "5m"
MAX_CANDLES = 1000
STEP = dt.timedelta(minutes=MAX_CANDLES)

start_dt = dt.datetime(2026, 1, 1, tzinfo=IST)
end_dt   = dt.datetime.now(IST)

all_data = []

while start_dt < end_dt:
    window_end = min(start_dt + STEP, end_dt)

    print(f"Fetching {start_dt} → {window_end}")

    df = get_delta_candles(SYMBOL, RESOLUTION, start_dt, window_end)
    if df is not None and not df.empty:
        all_data.append(df)

    start_dt = window_end
    time.sleep(0.25)  # rate-limit safety


# =====================
# SAVE
# =====================
df = pd.concat(all_data).drop_duplicates("Date").sort_values("Date")
df["Date"] = df["Date"].dt.tz_localize(None)

df.to_csv(f"{SYMBOL}_{RESOLUTION}_DELTA.csv", index=False)
print("Saved full historical data")

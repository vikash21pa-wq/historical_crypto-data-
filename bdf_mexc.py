import asyncio
import aiohttp
import pandas as pd
import datetime as dt
import os
import warnings
from urllib3.exceptions import NotOpenSSLWarning

warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

def to_seconds(ts):
    return int(ts.timestamp())

# =====================
# ASYNC FETCHERS
# =====================
async def fetch_delta(session, symbol, resolution, start_dt, end_dt):
    url = "https://api.india.delta.exchange/v2/history/candles"
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "start": to_seconds(start_dt),
        "end": to_seconds(end_dt)
    }

    async with session.get(url, params=params) as r:
        if r.status != 200:
            return None
        j = await r.json()
        if not j.get("success"):
            return None

        candles = j.get("result", [])
        if not candles:
            return None

        df = pd.DataFrame(candles)
        df["Date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(IST)
        return df[["Date", "open", "high", "low", "close", "volume"]] \
            .rename(columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume"
            })


async def fetch_mexc_fair(session, symbol, interval, start_dt, end_dt):
    url = f"https://contract.mexc.com/api/v1/contract/kline/fair_price/{symbol}"
    params = {
        "interval": interval,
        "start": to_seconds(start_dt),
        "end": to_seconds(end_dt)
    }

    async with session.get(url, params=params) as r:
        if r.status != 200:
            return None

        j = await r.json()
        if not j.get("success"):
            return None

        d = j.get("data", {})
        if not d or not d.get("time"):
            return None

        return pd.DataFrame({
            "Date": pd.to_datetime(d["time"], unit="s", utc=True).tz_convert(IST),
            "Open": d["open"],
            "High": d["high"],
            "Low": d["low"],
            "Close": d["close"],
            "Volume": d["vol"]
        })


# =====================
# RUNNER
# =====================
async def run():
    start_dt = dt.datetime(2025, 1, 1, tzinfo=IST)
    end_dt = dt.datetime.now(IST)

    STEP = dt.timedelta(minutes=2000)
    tasks = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        cur = start_dt
        while cur < end_dt:
            nxt = min(cur + STEP, end_dt)
            tasks.append(fetch_delta(session, "BTCUSD_PERP", "1m", cur, nxt))
            tasks.append(fetch_mexc_fair(session, "BTC_USDT", "Min1", cur, nxt))
            cur = nxt

        print(f"Launching {len(tasks)} async jobs...")
        results = await asyncio.gather(*tasks)

    delta_frames = []
    mexc_frames = []

    for df in results:
        if df is None or df.empty:
            continue
        if "Volume" in df.columns:
            delta_frames.append(df)
        else:
            mexc_frames.append(df)

    # =====================
    # SAVE
    # =====================
    base = os.path.dirname(os.path.abspath(__file__))

    if delta_frames:
        df = pd.concat(delta_frames).drop_duplicates("Date").sort_values("Date")
        df["Date"] = df["Date"].dt.tz_localize(None)
        df.to_csv(os.path.join(base, "BTC_DELTA_1m.csv"), index=False)

    if mexc_frames:
        df = pd.concat(mexc_frames).drop_duplicates("Date").sort_values("Date")
        df["Date"] = df["Date"].dt.tz_localize(None)
        df.to_csv(os.path.join(base, "BTC_MEXC_FAIR_1m.csv"), index=False)

    print("✅ DONE")


if __name__ == "__main__":
    asyncio.run(run())

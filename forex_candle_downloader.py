"""
Forex/Metal 1-Minute Candle Downloader — histdata.com
Free yearly ZIP downloads, no API key, data since 2000.
Mirrors the Binance monthly-zip approach (iterate by period, download, merge, save).

Format returned: datetime | open | high | low | close | volume
"""

import requests
import re
import zipfile
import io
import pandas as pd
from datetime import datetime, timedelta
import os
import time

BASE          = "https://www.histdata.com"
DOWNLOAD_PAGE = BASE + "/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes"
POST_URL      = BASE + "/get.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _fetch_form_data(page_path: str) -> dict | None:
    """
    GET the histdata page and scrape all hidden form fields.
    page_path examples: 'XAUUSD/2021'  or  'XAUUSD/2026/01'
    Returns dict of form fields ready to POST, or None on failure.
    """
    url  = f"{DOWNLOAD_PAGE}/{page_path}"
    page = requests.get(url, headers=HEADERS, timeout=30)
    if page.status_code != 200:
        return None
    fields = re.findall(r'name="([^"]+)" id="[^"]+" value="([^"]*)"', page.text)
    if not fields:
        return None
    data = {k: v for k, v in fields}   # last value wins on duplicates
    data.setdefault("platform",  "ASCII")
    data.setdefault("timeframe", "M1")
    data["referer_url"] = url
    return data


def _download_zip(form_data: dict) -> bytes | None:
    """POST form_data to histdata.com/get.php and return raw zip bytes."""
    referer = form_data.pop("referer_url", BASE)
    post_headers = {
        **HEADERS,
        "Referer":      referer,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    resp = requests.post(POST_URL, data=form_data, headers=post_headers, timeout=120)
    if resp.status_code == 200 and len(resp.content) > 200:
        return resp.content
    return None


def _parse_zip(content: bytes) -> pd.DataFrame | None:
    """Extract CSV from zip and parse into DataFrame."""
    try:
        z    = zipfile.ZipFile(io.BytesIO(content))
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        raw  = z.open(csv_name).read().decode("utf-8", errors="replace")
    except Exception:
        return None

    lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
    if not lines:
        return None

    rows = [l.split(";") for l in lines]
    df   = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["datetime"])


def download_period(pair: str, year: int, month: int | None = None) -> pd.DataFrame | None:
    """
    Download one year (month=None) or one specific month.
    Yearly  page path: 'XAUUSD/2021'
    Monthly page path: 'XAUUSD/2026/01'
    """
    if month is None:
        page_path = f"{pair}/{year}"
    else:
        page_path = f"{pair}/{year}/{month:02d}"

    form_data = _fetch_form_data(page_path)
    if not form_data:
        return None
    content = _download_zip(form_data)
    if not content:
        return None
    return _parse_zip(content)


def download_forex(symbols: list, start: datetime, end: datetime, output_dir: str = "forex_data"):
    os.makedirs(output_dir, exist_ok=True)
    summary = []

    for raw_sym in symbols:
        pair = raw_sym.upper().replace("/", "").replace("-", "").replace("=X", "").replace(" ", "")

        print(f"\n{'='*55}")
        print(f"  {pair}  |  1m  |  {start.date()}  to  {end.date()}")
        print(f"{'='*55}")

        all_dfs = []
        now     = datetime.now()

        # ── Full years ────────────────────────────────────────────────────────
        first_year = start.year
        # For full years, only download years that are fully or partially available
        # Use monthly downloads for the current (incomplete) year
        last_full_year = now.year - 1

        for year in range(first_year, last_full_year + 1):
            print(f"  Downloading year {year} ...", end=" ", flush=True)
            df = download_period(pair, year)
            if df is not None and not df.empty:
                all_dfs.append(df)
                print(f"OK  ({len(df):,} rows)")
            else:
                print("No data / not available")
            time.sleep(1.5)

        # ── Current year: download month by month ─────────────────────────────
        cur_year = now.year
        print(f"  Current year {cur_year} - downloading month by month")
        for month in range(1, now.month + 1):
            print(f"    {cur_year}-{month:02d} ...", end=" ", flush=True)
            df = download_period(pair, cur_year, month)
            if df is not None and not df.empty:
                all_dfs.append(df)
                print(f"OK  ({len(df):,} rows)")
            else:
                print("No data")
            time.sleep(1.5)

        if not all_dfs:
            print(f"\n  No data collected for {pair}")
            summary.append((pair, 0, "N/A", "N/A"))
            continue

        # ── Merge & filter to requested date range ────────────────────────────
        merged = (
            pd.concat(all_dfs, ignore_index=True)
            .drop_duplicates(subset="datetime")
            .sort_values("datetime")
            .reset_index(drop=True)
        )

        merged = merged[(merged["datetime"] >= start) & (merged["datetime"] <= end)]

        out_path = os.path.join(output_dir, f"{pair}_1m.csv")
        merged.to_csv(out_path, index=False)

        first_dt = str(merged["datetime"].iloc[0])[:19]
        last_dt  = str(merged["datetime"].iloc[-1])[:19]

        print(f"\n  Saved  : {out_path}")
        print(f"  Rows   : {len(merged):,}")
        print(f"  Range  : {first_dt}  to  {last_dt}")
        summary.append((pair, len(merged), first_dt, last_dt))

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  DOWNLOAD SUMMARY")
    print(f"{'='*65}")
    print(f"  {'Symbol':<12} {'Rows':<12} {'From':<22} {'To'}")
    print(f"  {'-'*62}")
    for sym, rows, frm, to in summary:
        print(f"  {sym:<12} {rows:<12,} {frm:<22} {to}")
    print(f"{'='*65}")
    print(f"  Files saved in: {output_dir}/")


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("   FOREX/METAL 1-MINUTE CANDLE DOWNLOADER")
    print("   Source: histdata.com  |  Free  |  No API key")
    print("=" * 60)
    print()
    print("Enter symbols (comma-separated).")
    print("Examples: XAUUSD, EURUSD, GBPUSD, USDJPY, XAGUSD")
    raw = input("> ").strip()
    symbols = [s.strip() for s in raw.split(",") if s.strip()]
    if not symbols:
        print("No symbols. Exiting.")
        return

    print()
    print("Enter start date (YYYY-MM-DD):")
    try:
        start = datetime.strptime(input("> ").strip(), "%Y-%m-%d")
    except ValueError:
        print("Invalid date format. Exiting.")
        return

    yesterday = datetime.now() - timedelta(days=1)
    yesterday = yesterday.replace(hour=23, minute=59, second=59)

    print()
    print(f"Enter end date (YYYY-MM-DD), or press Enter for yesterday ({yesterday.date()}):")
    end_raw = input("> ").strip()
    end = datetime.strptime(end_raw, "%Y-%m-%d").replace(hour=23, minute=59, second=59) if end_raw else yesterday

    print()
    print("Output folder (press Enter for 'forex_data'):")
    out_dir = input("> ").strip() or "forex_data"

    now = datetime.now()
    years_span = now.year - start.year + 1
    total_reqs  = len(symbols) * (years_span + now.month)

    print()
    print("Request summary:")
    print(f"  Symbols      : {', '.join(s.upper() for s in symbols)}")
    print(f"  Start        : {start.date()}")
    print(f"  End          : {end.date()}")
    print(f"  ~Requests    : {total_reqs}  (yearly + monthly for current year)")
    print(f"  Output dir   : {out_dir}/")
    print()
    if input("Proceed? [Y/n]: ").strip().lower() not in ("", "y", "yes"):
        print("Aborted.")
        return

    download_forex(symbols, start, end, out_dir)
    print("\nDone!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
download_candles_v2.py — Parallel Binance candle downloader
- Parallelises all (symbol × interval) pairs via ThreadPoolExecutor
- Auto-starts from each symbol's actual listing date (no pre-listing gap / errors)
- Global rate-limiter keeps total requests well under Binance limits
- Per-request retry with exponential back-off

CONFIGURE THESE:
"""

SYMBOLS = [
    'BTCUSDT',
    'ETHUSDT',
    'SOLUSDT',
    'BNBUSDT',
    'XRPUSDT',
    'ADAUSDT',
    'DOGEUSDT',
    'LINKUSDT',
    'MATICUSDT',
    'AVAXUSDT',
    'DOTUSDT',
    'LTCUSDT',
    'TRXUSDT',
    'BCHUSDT',
    'APTUSDT',
    'ARBUSDT',
    'OPUSDT',
    'CFXUSDT',
    'ATOMUSDT',
    'NEARUSDT',
    'ASTERUSDT',
    # Added
    'SUIUSDT',
    'INJUSDT',
    'UNIUSDT',
    'AAVEUSDT',
    'LDOUSDT',
    'RUNEUSDT',
    'FETUSDT',
    'FILUSDT',
    'SEIUSDT',
]

INTERVALS   = ['1m', '5m', '15m', '30m']
START_DATE  = '2021-01-01'
END_DATE    = '2026-03-27'
OUTPUT_DIR  = r'C:\Users\GIGA\Desktop\candlestick data'

MAX_WORKERS       = 8      # parallel (symbol, interval) pairs
MAX_REQ_PER_SEC   = 8      # global cap; Binance allows ~20/s on /api/v3/klines
RETRY_ATTEMPTS    = 5      # retries per chunk on error
CANDLES_PER_REQ   = 1000   # Binance max

# ─────────────────────────────────────────────────────────────────────────────

import os, csv, time, json, threading, urllib.request, urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

BINANCE_URL = 'https://api.binance.com/api/v3/klines'

# ── Global rate-limiter (token-bucket style) ──────────────────────────────────
_rl_lock      = threading.Lock()
_rl_last_call = 0.0
_rl_min_gap   = 1.0 / MAX_REQ_PER_SEC   # seconds between requests

def _rate_wait():
    """Block until it's safe to fire the next request."""
    global _rl_last_call
    with _rl_lock:
        now  = time.monotonic()
        wait = _rl_min_gap - (now - _rl_last_call)
        if wait > 0:
            time.sleep(wait)
        _rl_last_call = time.monotonic()

# ── Progress printer (thread-safe) ───────────────────────────────────────────
_print_lock = threading.Lock()

def tprint(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)

# ── Core helpers ─────────────────────────────────────────────────────────────

def ts_ms(date_str: str) -> int:
    return int(datetime.strptime(date_str, '%Y-%m-%d')
               .replace(tzinfo=timezone.utc).timestamp() * 1000)

def fetch_chunk(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    """Fetch one chunk (≤1000 candles) with retry + back-off."""
    params = urllib.parse.urlencode({
        'symbol':    symbol,
        'interval':  interval,
        'startTime': start_ms,
        'endTime':   end_ms,
        'limit':     CANDLES_PER_REQ,
    })
    url = f'{BINANCE_URL}?{params}'

    for attempt in range(RETRY_ATTEMPTS):
        _rate_wait()
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors='replace')
            # 400 = bad symbol / invalid params — no point retrying
            if e.code == 400:
                raise ValueError(f'Binance 400 for {symbol}/{interval}: {body}') from e
            # 429 / 418 = rate-limited — back off longer
            backoff = (2 ** attempt) * (2 if e.code in (429, 418) else 1)
            tprint(f'    [warn] HTTP {e.code} {symbol} {interval} — retry {attempt+1} in {backoff}s')
            time.sleep(backoff)
        except Exception as e:
            backoff = 2 ** attempt
            tprint(f'    [warn] {type(e).__name__} {symbol} {interval} — retry {attempt+1} in {backoff}s')
            time.sleep(backoff)

    raise RuntimeError(f'Failed to fetch chunk after {RETRY_ATTEMPTS} attempts: {symbol} {interval}')


def find_actual_start(symbol: str, interval: str, requested_start_ms: int) -> int:
    """
    Return the timestamp of the very first available candle for this symbol/interval.
    If data exists at requested_start_ms we just use that; otherwise we probe
    forward so we never waste time iterating over a pre-listing gap.
    """
    chunk = fetch_chunk(symbol, interval, requested_start_ms, requested_start_ms + 86_400_000 * 30)
    if chunk:
        return chunk[0][0]   # first candle open-time in the probe window
    # Symbol not available yet at START_DATE — find real listing by binary search
    # between START_DATE and END_DATE (coarse: just use a wide probe)
    probe_ms = requested_start_ms
    end_ms   = ts_ms(END_DATE) + 86_400_000
    step     = 86_400_000 * 90   # 90-day steps
    while probe_ms < end_ms:
        chunk = fetch_chunk(symbol, interval, probe_ms, min(probe_ms + step, end_ms))
        if chunk:
            return chunk[0][0]
        probe_ms += step
    raise ValueError(f'{symbol} has no data between {START_DATE} and {END_DATE}')


def download(symbol: str, interval: str) -> list:
    """Download all candles for one (symbol, interval) pair."""
    start_ms = ts_ms(START_DATE)
    end_ms   = ts_ms(END_DATE) + 86_400_000   # include full end day

    actual_start = find_actual_start(symbol, interval, start_ms)
    if actual_start > start_ms:
        dt = datetime.fromtimestamp(actual_start / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
        tprint(f'  [{symbol} {interval}] listed from {dt} (skipping pre-listing gap)')

    rows    = []
    current = actual_start
    while current < end_ms:
        chunk = fetch_chunk(symbol, interval, current, end_ms)
        if not chunk:
            break
        rows.extend(chunk)
        current = chunk[-1][0] + 1

    return rows


def save(rows: list, symbol: str, interval: str, out_dir: str) -> str:
    folder = os.path.join(out_dir, interval)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f'{symbol}{interval}.csv')

    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        for k in rows:
            ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            writer.writerow([ts, k[1], k[2], k[3], k[4], k[5]])

    return path


def process(symbol: str, interval: str) -> tuple:
    """Worker function run inside the thread pool."""
    try:
        rows = download(symbol, interval)
        path = save(rows, symbol, interval, OUTPUT_DIR)
        return symbol, interval, len(rows), path, None
    except Exception as e:
        return symbol, interval, 0, None, str(e)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    tasks = [(s, i) for s in SYMBOLS for i in INTERVALS]
    total = len(tasks)

    print(f'Symbols  : {len(SYMBOLS)}')
    print(f'Intervals: {INTERVALS}')
    print(f'Range    : {START_DATE} → {END_DATE}')
    print(f'Output   : {OUTPUT_DIR}')
    print(f'Tasks    : {total}  |  Workers: {MAX_WORKERS}')
    print()

    done = 0
    errors = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process, s, i): (s, i) for s, i in tasks}
        for fut in as_completed(futures):
            symbol, interval, n_rows, path, err = fut.result()
            done += 1
            if err:
                tprint(f'  [{done}/{total}] ERROR  {symbol} {interval}: {err}')
                errors.append((symbol, interval, err))
            else:
                tprint(f'  [{done}/{total}] OK     {symbol} {interval}  {n_rows:,} candles → {path}')

    print()
    if errors:
        print(f'Completed with {len(errors)} error(s):')
        for s, i, e in errors:
            print(f'  {s} {interval}: {e}')
    else:
        print('All downloads completed successfully.')


if __name__ == '__main__':
    main()

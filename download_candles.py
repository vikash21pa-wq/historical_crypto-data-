#!/usr/bin/env python3
"""
Download Binance USDT-perp candle data for any assets and date range.
Output matches the CSV format used by all backtest files (Date,O,H,L,C,V).

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

    # 🆕 Added (unique from B07 list)
    'SUIUSDT',
    'INJUSDT',
    'UNIUSDT',
    'AAVEUSDT',
    'LDOUSDT',
    'RUNEUSDT',
    'FETUSDT',
    'FILUSDT',
    'SEIUSDT'
]


INTERVALS  = ['1m', '5m', '15m', '30m']                       # any Binance interval
START_DATE = '2021-01-01'                                     # YYYY-MM-DD
END_DATE   = '2026-03-27'                                     # YYYY-MM-DD (inclusive)
OUTPUT_DIR = '/Users/ayush/Desktop/candlestick data'          # base dir; interval subfolders created automatically

# ─────────────────────────────────────────────────────────────────────────────

import os
import csv
import time
import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone

BINANCE_URL = 'https://api.binance.com/api/v3/klines'

def ts_ms(date_str):
    return int(datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)

def fetch_chunk(symbol, interval, start_ms, end_ms):
    params = urllib.parse.urlencode({
        'symbol':    symbol,
        'interval':  interval,
        'startTime': start_ms,
        'endTime':   end_ms,
        'limit':     1000,
    })
    url = f'{BINANCE_URL}?{params}'
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def download(symbol, interval, start_date, end_date):
    start_ms = ts_ms(start_date)
    end_ms   = ts_ms(end_date) + 86_400_000   # include full end day

    rows = []
    current = start_ms
    while current < end_ms:
        chunk = fetch_chunk(symbol, interval, current, end_ms)
        if not chunk:
            break
        rows.extend(chunk)
        current = chunk[-1][0] + 1
        if len(rows) % 50_000 == 0:
            print(f'    {len(rows):,} candles...')
        time.sleep(0.05)   # stay well under rate limit

    return rows

def save(rows, symbol, interval, out_dir):
    folder = os.path.join(out_dir, interval)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f'{symbol}{interval}.csv')

    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        for k in rows:
            ts  = datetime.utcfromtimestamp(k[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
            writer.writerow([ts, k[1], k[2], k[3], k[4], k[5]])

    return path

def main():
    print(f'Symbols  : {SYMBOLS}')
    print(f'Intervals: {INTERVALS}')
    print(f'Range    : {START_DATE} to {END_DATE}')
    print(f'Output   : {OUTPUT_DIR}')
    print()

    for symbol in SYMBOLS:
        for interval in INTERVALS:
            print(f'  {symbol} {interval} ...', end=' ', flush=True)
            try:
                rows = download(symbol, interval, START_DATE, END_DATE)
                path = save(rows, symbol, interval, OUTPUT_DIR)
                print(f'{len(rows):,} candles → {path}')
            except Exception as e:
                print(f'ERROR: {e}')

    print('\nDone.')

if __name__ == '__main__':
    main()

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import math

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
FILE_PATH = '/Users/ayush/Desktop/Historical-Crypto_Data/SOLUSDT5m.csv' # UPDATE THIS
INITIAL_CAPITAL = 1000.0
FEE_RATE = 0.0004 # 0.04%
CONTRACT_VOL = 1000 # Size of trade in contracts (e.g. 1000 USDT worth or units)

# STRATEGY PARAMS
RSI_PERIOD = 8
RSI_LONG_THRESH = 30 # Relaxed as per your request
RSI_SHORT_THRESH = 70
PROFIT_BOOK_PERCENT = 1.0 # 100% (Fixed the bug)
STOPLOSS_PERCENT = -0.01 # -1%

# ==========================================
# 🛠️ INDICATOR FUNCTIONS
# ==========================================
def calculate_rsi(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calculate_sma(series, period):
    return series.rolling(window=period).mean()

# ==========================================
# 🧠 STRATEGY LOGIC
# ==========================================
class Backtester:
    def __init__(self, data):
        self.df = data
        self.balance = INITIAL_CAPITAL
        self.positions = []
        self.trades = [] # History of closed trades
        self.current_position = None # {'side': 'long'/'short', 'price': 0.0, 'vol': 0, 'time': t, 'context': {}}
        
    def get_sfi_signal(self, i):
        """
        ⚠️ IMPORTANT: PLACE YOUR SFI LOGIC HERE ⚠️
        Since I don't have your 'sf.dart', I am simulating signals 
        using RSI just to make the code runnable.
        """
        row = self.df.iloc[i]
        prev_row = self.df.iloc[i-1]
        
        # --- MOCK LOGIC (REPLACE WITH REAL SFI) ---
        direction = 0 
        entry_price = 0.0
        target_price = 0.0
        
        # Example: If RSI crosses 30 upwards -> Long Signal
        if prev_row['rsi'] < 30 and row['rsi'] >= 30:
            direction = 1
            entry_price = row['close']
            target_price = row['close'] * 1.01 # 1% target
            
        # Example: If RSI crosses 70 downwards -> Short Signal
        elif prev_row['rsi'] > 70 and row['rsi'] <= 70:
            direction = -1
            entry_price = row['close']
            target_price = row['close'] * 0.99 # 1% target
            
        return direction, entry_price, target_price

    def run(self):
        print(f"🔄 Running Backtest on {len(self.df)} candles...")
        
        for i in range(201, len(self.df)):
            current = self.df.iloc[i]
            prev = self.df.iloc[i-1]
            prev2 = self.df.iloc[i-2]
            
            # 1. Update Indicators
            ema200 = current['ema200']
            avg_vol = current['vol_ma']
            is_alive_volume = current['volume'] > (avg_vol * 0.5)
            is_price_below_ema = current['close'] < ema200
            candle_color = "Green" if current['close'] >= current['open'] else "Red"
            
            # Get SFI Data (Simulated or Real)
            sfi_dir, sfi_entry, first_target = self.get_sfi_signal(i)
            
            # --- EXECUTION LOGIC ---
            
            # CHECK EXIT (If Position Exists)
            if self.current_position:
                self.check_exit(current, first_target)
            
            # CHECK ENTRY (If No Position)
            if self.current_position is None and is_alive_volume:
                
                # LONG ENTRY LOGIC
                # Note: Translating your Dart logic exactly
                if (sfi_dir == 1 and 
                    prev2['rsi'] < RSI_LONG_THRESH and 
                    prev['rsi'] >= RSI_LONG_THRESH):
                    
                    if is_price_below_ema:
                        self.open_position('long', current, is_price_below_ema, candle_color)

                # SHORT ENTRY LOGIC
                elif (sfi_dir == -1 and 
                      prev2['rsi'] > RSI_SHORT_THRESH and 
                      prev['rsi'] <= RSI_SHORT_THRESH):
                      
                    self.open_position('short', current, is_price_below_ema, candle_color)

    def open_position(self, side, row, is_below_ema, color):
        self.current_position = {
            'side': side,
            'price': row['close'],
            'vol': CONTRACT_VOL,
            'time': row['time'],
            'context': {
                'trend': 'Below EMA' if is_below_ema else 'Above EMA',
                'color': color,
                'hour': row['time'].hour
            }
        }

    def check_exit(self, row, target_price):
        pos = self.current_position
        price = row['close']
        pnl_percent = 0.0
        
        should_exit = False
        exit_reason = ""
        
        if pos['side'] == 'long':
            pnl_percent = (price - pos['price']) / pos['price']
            
            if pnl_percent <= STOPLOSS_PERCENT: 
                should_exit = True
                exit_reason = "StopLoss"
            elif price >= target_price and target_price > 0: # Target Hit
                should_exit = True
                exit_reason = "Target Hit"
                
        elif pos['side'] == 'short':
            pnl_percent = (pos['price'] - price) / pos['price']
            
            if pnl_percent <= STOPLOSS_PERCENT:
                should_exit = True
                exit_reason = "StopLoss"
            elif price <= target_price and target_price > 0:
                should_exit = True
                exit_reason = "Target Hit"

        if should_exit:
            self.close_position(price, row['time'], exit_reason)

    def close_position(self, price, time, reason):
        pos = self.current_position
        vol = pos['vol']
        
        # Calculate Gross PnL
        if pos['side'] == 'long':
            gross_pnl = (price - pos['price']) * vol
        else:
            gross_pnl = (pos['price'] - price) * vol
            
        # Fees
        trade_val = price * vol
        fee = trade_val * FEE_RATE
        net_pnl = gross_pnl - fee
        
        self.balance += net_pnl
        
        # Record Trade
        self.trades.append({
            'entry_time': pos['time'],
            'exit_time': time,
            'side': pos['side'],
            'entry_price': pos['price'],
            'exit_price': price,
            'net_pnl': net_pnl,
            'balance': self.balance,
            'reason': reason,
            'trend': pos['context']['trend'],
            'candle_color': pos['context']['color'],
            'hour': pos['context']['hour']
        })
        
        self.current_position = None

# ==========================================
# 📊 ANALYTICS & PLOTTING
# ==========================================
def analyze_results(trades):
    if not trades:
        print("No trades made.")
        return

    df_trades = pd.DataFrame(trades)
    df_trades['win'] = df_trades['net_pnl'] > 0
    
    print("\n" + "="*50)
    print(f"💰 FINAL BALANCE: ${trades[-1]['balance']:.2f}")
    print(f"📉 TOTAL PnL: ${(trades[-1]['balance'] - INITIAL_CAPITAL):.2f}")
    print(f"🔢 TOTAL TRADES: {len(df_trades)}")
    print(f"✅ WIN RATE: {(df_trades['win'].mean() * 100):.1f}%")
    print("="*50)

    # --- DEEP DIVE 1: SIDE (LONG vs SHORT) ---
    print("\n--- 1. PERFORMANCE BY SIDE ---")
    print(df_trades.groupby('side')[['net_pnl', 'win']].agg(
        {'net_pnl': 'sum', 'win': 'mean'}
    ).rename(columns={'win': 'win_rate'}))

    # --- DEEP DIVE 2: TREND CONTEXT ---
    print("\n--- 2. PERFORMANCE BY TREND (EMA 200) ---")
    print(df_trades.groupby('trend')[['net_pnl', 'win']].agg(
        {'net_pnl': 'sum', 'win': 'mean'}
    ))
    
    # --- DEEP DIVE 3: CANDLE COLOR ---
    print("\n--- 3. PERFORMANCE BY ENTRY CANDLE COLOR ---")
    print(df_trades.groupby('candle_color')[['net_pnl', 'win']].agg(
        {'net_pnl': 'sum', 'win': 'mean'}
    ))

    # --- PLOTTING ---
    plot_charts(df_trades)

def plot_charts(trade_df):
    # 1. Equity Curve
    plt.figure(figsize=(12, 6))
    plt.plot(trade_df['exit_time'], trade_df['balance'], label='Account Balance', color='blue')
    plt.title('Account Growth (Equity Curve)')
    plt.xlabel('Date')
    plt.ylabel('Balance ($)')
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend()
    plt.show()

    # 2. Scatter Plot of Wins vs Losses
    plt.figure(figsize=(12, 6))
    wins = trade_df[trade_df['net_pnl'] > 0]
    losses = trade_df[trade_df['net_pnl'] <= 0]
    
    plt.scatter(wins['exit_time'], wins['net_pnl'], color='green', alpha=0.6, label='Wins')
    plt.scatter(losses['exit_time'], losses['net_pnl'], color='red', alpha=0.6, label='Losses')
    plt.axhline(0, color='black', linewidth=1)
    plt.title('Trade PnL Distribution')
    plt.ylabel('PnL per Trade ($)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.show()
    
    # 3. Hourly Performance
    hourly_pnl = trade_df.groupby('hour')['net_pnl'].sum()
    plt.figure(figsize=(10, 5))
    hourly_pnl.plot(kind='bar', color=np.where(hourly_pnl>0, 'g', 'r'))
    plt.title('PnL by Hour of Day (When are you losing?)')
    plt.xlabel('Hour (0-23)')
    plt.ylabel('Total PnL')
    plt.grid(axis='y')
    plt.show()

# ==========================================
# 🚀 MAIN EXECUTION
# ==========================================
# ==========================================
# 🚀 MAIN EXECUTION
# ==========================================
def main():
    # 1. Load Data
    print(f"📂 Loading data from {FILE_PATH}...")
    try:
        # FIX: Removed header=None so it reads the first row as column names
        df = pd.read_csv(FILE_PATH) 
        
        # Standardize column names (lowercase, strip whitespace)
        df.columns = [c.lower().strip() for c in df.columns]
        
        # Mapping: Rename your specific CSV columns to what the bot expects
        # Adjust these keys if your CSV headers are different (e.g., 'date' vs 'timestamp')
        rename_map = {
            'date': 'time',
            'timestamp': 'time', 
            'open': 'open',
            'high': 'high', 
            'low': 'low',
            'close': 'close',
            'volume': 'volume'
        }
        df.rename(columns=rename_map, inplace=True)
        
        # Ensure we have the required columns
        required_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            print(f"❌ CSV format error. Found columns: {df.columns.tolist()}")
            print(f"   Expected columns like: {required_cols}")
            return

        # Convert Time
        # Handles both Unix timestamps (int) and string dates
        try:
            if pd.api.types.is_numeric_dtype(df['time']):
                # Check if timestamp is in milliseconds (huge numbers) or seconds
                if df['time'].iloc[0] > 10000000000: # likely ms
                    df['time'] = pd.to_datetime(df['time'], unit='ms')
                else:
                    df['time'] = pd.to_datetime(df['time'], unit='s')
            else:
                df['time'] = pd.to_datetime(df['time'])
        except Exception as e:
            print(f"❌ Date parsing error: {e}")
            return
             
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return

    # 2. Add Indicators
    print("📊 Calculating Indicators...")
    df['rsi'] = calculate_rsi(df['close'], RSI_PERIOD)
    df['ema200'] = calculate_ema(df['close'], 200)
    df['vol_ma'] = calculate_sma(df['volume'], 20)

    # 3. Run Strategy
    bt = Backtester(df)
    bt.run()

    # 4. Analyze
    analyze_results(bt.trades)

if __name__ == "__main__":
    main()
 
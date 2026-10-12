#!/usr/bin/env python3
"""
Asterdex Account Data Extraction Script
This script queries Q's Asterdex account for comprehensive trading and financial data.

IMPORTANT: This script must be run from a whitelisted IP address.

Usage:
    python asterdex_data_extraction.py

The script will:
1. Query account balance
2. Export trade history
3. Export deposit history
4. Export withdrawal history
5. Export order history
6. Generate a summary report

All data will be saved as JSON files in the same directory.
"""

import hmac
import hashlib
import os
import time
import requests
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode

# ============================================================================
# CONFIGURATION
# ============================================================================

# Asterdex API Configuration
BASE_URL = "https://fapi.asterdex.com"
API_HEADER = "X-MBX-APIKEY"

# API Keys - Update these with the correct keys
API_KEY = os.environ.get("ASTERDEX_API_KEY")
SECRET_KEY = os.environ.get("ASTERDEX_SECRET_KEY")

# Output directory (same as script location)
OUTPUT_DIR = Path(__file__).parent

# ============================================================================
# API CLIENT CLASS
# ============================================================================

class AsterdexAPI:
    def __init__(self, api_key, secret_key):
        if not api_key or not secret_key:
            raise ValueError(
                "Set ASTERDEX_API_KEY and ASTERDEX_SECRET_KEY environment variables."
            )
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = BASE_URL
    
    def _generate_signature(self, params):
        """Generate HMAC SHA256 signature for request
        
        Note: Asterdex may use Binance-like signature method:
        - Create query string from sorted parameters (excluding signature itself)
        - Sign the query string with HMAC SHA256
        - Append signature as a parameter
        """
        # Remove signature if it exists (don't sign the signature itself)
        params_to_sign = {k: v for k, v in params.items() if k != 'signature'}
        query_string = urlencode(sorted(params_to_sign.items()))
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature, query_string
    
    def _get_headers(self):
        """Get request headers with API key"""
        return {
            API_HEADER: self.api_key,
            'Content-Type': 'application/json',
        }
    
    def _request(self, method, endpoint, params=None, signed=False, debug=False):
        """Make API request"""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        if params is None:
            params = {}
        
        if signed:
            # Add timestamp first (before generating signature)
            params['timestamp'] = int(time.time() * 1000)
            # Generate signature from current params
            signature, query_string = self._generate_signature(params)
            # Add signature to params
            params['signature'] = signature
            
            if debug:
                print(f"  DEBUG: Params before signature: {dict(sorted((k, v) for k, v in params.items() if k != 'signature'))}")
                print(f"  DEBUG: Query string for signing: {query_string}")
                print(f"  DEBUG: Generated signature: {signature[:30]}...")
                print(f"  DEBUG: Final URL params: {dict(params)}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=params, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Check for errors before parsing JSON
            if response.status_code != 200:
                error_data = {
                    'error': True,
                    'status_code': response.status_code,
                    'endpoint': endpoint,
                    'url': response.url,
                    'response_text': response.text[:2000]  # Increased to see more detail
                }
                try:
                    error_json = response.json()
                    error_data['response_json'] = error_json
                    # Extract error code and message if available
                    if 'code' in error_json:
                        error_data['error_code'] = error_json.get('code')
                    if 'msg' in error_json:
                        error_data['error_message'] = error_json.get('msg')
                except:
                    pass
                if debug:
                    print(f"  DEBUG: Error response (status {response.status_code}):")
                    print(f"    URL: {response.url}")
                    if 'error_code' in error_data:
                        print(f"    Error Code: {error_data['error_code']}")
                    if 'error_message' in error_data:
                        print(f"    Error Message: {error_data['error_message']}")
                    print(f"    Response: {response.text[:500]}")
                return error_data
            
            return response.json()
        except requests.exceptions.RequestException as e:
            error_info = {
                'error': True,
                'exception': str(e),
                'endpoint': endpoint
            }
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_info['response_json'] = e.response.json()
                except:
                    error_info['status_code'] = e.response.status_code
                    error_info['response_text'] = e.response.text[:1000]
            if debug:
                print(f"  DEBUG: Request exception: {error_info}")
            return error_info
    
    def get_account(self, debug=False):
        """Get account information (balance, positions, etc.)"""
        endpoints = [
            '/fapi/v1/account',
            '/fapi/v2/account',
            '/fapi/v3/account',
            '/api/v1/account',
            '/api/v2/account',
        ]
        for endpoint in endpoints:
            if debug:
                print(f"  Trying endpoint: {endpoint}")
            result = self._request('GET', endpoint, signed=True, debug=debug)
            if result and not result.get('error'):
                return result
            elif debug and result:
                print(f"  Failed: {result.get('status_code', 'unknown')} - {result.get('response_text', result.get('exception', 'unknown error'))[:200]}")
        return None
    
    def get_trade_history(self, symbol=None, limit=1000, startTime=None, endTime=None):
        """Get trade history"""
        params = {'limit': limit}
        if symbol:
            params['symbol'] = symbol
        if startTime:
            params['startTime'] = startTime
        if endTime:
            params['endTime'] = endTime
        
        endpoints = ['/fapi/v1/userTrades', '/fapi/v1/trades']
        for endpoint in endpoints:
            result = self._request('GET', endpoint, params=params, signed=True)
            if result and not result.get('error'):
                return result
        return None
    
    def get_all_trades(self, limit=1000, debug=False):
        """Get all trades (may need to paginate)
        
        Note: Many exchanges require a symbol parameter for trade endpoints.
        If this fails, we may need to get list of symbols first, or try without limit.
        """
        all_trades = []
        
        # Try with limit parameter
        endpoints_with_limit = [
            ('/fapi/v1/userTrades', {'limit': limit}),
            ('/fapi/v1/myTrades', {'limit': limit}),
            ('/fapi/v1/trades', {'limit': limit}),
            ('/api/v1/userTrades', {'limit': limit}),
            ('/api/v1/myTrades', {'limit': limit}),
        ]
        
        # Try without limit (some APIs don't need it)
        endpoints_without_limit = [
            '/fapi/v1/userTrades',
            '/fapi/v1/myTrades',
            '/fapi/v1/trades',
            '/api/v1/userTrades',
            '/api/v1/myTrades',
        ]
        
        # Try endpoints with limit first
        for endpoint, params in endpoints_with_limit:
            if debug:
                print(f"  Trying endpoint: {endpoint} with params: {params}")
            result = self._request('GET', endpoint, params=params, signed=True, debug=debug)
            if result and not result.get('error'):
                if isinstance(result, list):
                    all_trades.extend(result)
                elif isinstance(result, dict):
                    if 'data' in result:
                        all_trades.extend(result['data'])
                    elif 'trades' in result:
                        all_trades.extend(result['trades'])
                    elif 'list' in result:
                        all_trades.extend(result['list'])
                if all_trades:
                    return all_trades
        
        # Try without limit
        for endpoint in endpoints_without_limit:
            if debug:
                print(f"  Trying endpoint: {endpoint} without limit")
            result = self._request('GET', endpoint, params={}, signed=True, debug=debug)
            if result and not result.get('error'):
                if isinstance(result, list):
                    all_trades.extend(result)
                elif isinstance(result, dict):
                    if 'data' in result:
                        all_trades.extend(result['data'])
                    elif 'trades' in result:
                        all_trades.extend(result['trades'])
                if all_trades:
                    return all_trades
        
        return all_trades
    
    def get_orders(self, symbol=None, limit=1000, debug=False):
        """Get order history"""
        params = {'limit': limit}
        if symbol:
            params['symbol'] = symbol
        
        endpoints = [
            '/fapi/v1/allOrders',
            '/fapi/v1/orders',
            '/fapi/v1/orderList',
            '/api/v1/allOrders',
            '/api/v1/orders',
        ]
        for endpoint in endpoints:
            if debug:
                print(f"  Trying endpoint: {endpoint}")
            result = self._request('GET', endpoint, params=params, signed=True, debug=debug)
            if result and not result.get('error'):
                return result
            elif debug and result:
                print(f"  Failed: {result.get('status_code', 'unknown')} - {result.get('response_text', result.get('exception', 'unknown error'))[:200]}")
        return None
    
    def get_deposits(self, limit=1000, debug=False):
        """Get deposit history"""
        params = {'limit': limit}
        
        endpoints = [
            '/fapi/v1/capital/deposit/hisrec',
            '/fapi/v1/depositHistory',
            '/fapi/v1/deposits',
            '/api/v1/depositHistory',
            '/api/v1/deposits',
            '/api/v1/capital/deposit/hisrec',
        ]
        for endpoint in endpoints:
            if debug:
                print(f"  Trying endpoint: {endpoint}")
            result = self._request('GET', endpoint, params=params, signed=True, debug=debug)
            if result and not result.get('error'):
                return result
            elif debug and result:
                print(f"  Failed: {result.get('status_code', 'unknown')} - {result.get('response_text', result.get('exception', 'unknown error'))[:200]}")
        return None
    
    def get_withdrawals(self, limit=1000, debug=False):
        """Get withdrawal history"""
        params = {'limit': limit}
        
        endpoints = [
            '/fapi/v1/capital/withdraw/history',
            '/fapi/v1/withdrawHistory',
            '/fapi/v1/withdrawals',
            '/api/v1/withdrawHistory',
            '/api/v1/withdrawals',
            '/api/v1/capital/withdraw/history',
        ]
        for endpoint in endpoints:
            if debug:
                print(f"  Trying endpoint: {endpoint}")
            result = self._request('GET', endpoint, params=params, signed=True, debug=debug)
            if result and not result.get('error'):
                return result
            elif debug and result:
                print(f"  Failed: {result.get('status_code', 'unknown')} - {result.get('response_text', result.get('exception', 'unknown error'))[:200]}")
        return None


# ============================================================================
# DATA PROCESSING FUNCTIONS
# ============================================================================

def format_timestamp(ts):
    """Format timestamp to readable date"""
    try:
        if isinstance(ts, (int, float)):
            if ts > 1e12:  # Milliseconds
                ts = ts / 1000
            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        return str(ts)
    except:
        return str(ts)


def generate_summary_report(account_data, trades, deposits, withdrawals, orders):
    """Generate a human-readable summary report"""
    report = []
    report.append("=" * 80)
    report.append("ASTERDEX ACCOUNT SUMMARY REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # Account Balance
    report.append("ACCOUNT BALANCE")
    report.append("-" * 80)
    if account_data:
        if isinstance(account_data, dict):
            if 'assets' in account_data:
                for asset in account_data['assets']:
                    if float(asset.get('walletBalance', 0)) > 0:
                        report.append(f"{asset.get('asset', 'Unknown')}: {asset.get('walletBalance', 0)}")
            elif 'balances' in account_data:
                for balance in account_data['balances']:
                    if float(balance.get('free', 0)) > 0 or float(balance.get('locked', 0)) > 0:
                        report.append(f"{balance.get('asset', 'Unknown')}: Free={balance.get('free', 0)}, Locked={balance.get('locked', 0)}")
            else:
                report.append(f"Balance data structure: {json.dumps(account_data, indent=2)[:500]}")
    else:
        report.append("No account data retrieved")
    report.append("")
    
    # Trade Statistics
    report.append("TRADE STATISTICS")
    report.append("-" * 80)
    if trades:
        trade_list = trades if isinstance(trades, list) else (trades.get('data', []) or trades.get('trades', []) or [])
        report.append(f"Total trades: {len(trade_list)}")
        if trade_list:
            # Calculate totals
            total_volume = 0
            total_commission = 0
            for trade in trade_list[:100]:  # Sample first 100
                if isinstance(trade, dict):
                    total_volume += float(trade.get('quoteQty', trade.get('qty', 0)))
                    total_commission += float(trade.get('commission', 0))
            
            report.append(f"Sample volume (first 100 trades): {total_volume:.2f}")
            report.append(f"Sample commission (first 100 trades): {total_commission:.2f}")
    else:
        report.append("No trade data retrieved")
    report.append("")
    
    # Deposits
    report.append("DEPOSITS")
    report.append("-" * 80)
    if deposits:
        deposit_list = deposits if isinstance(deposits, list) else (deposits.get('data', []) or deposits.get('deposits', []) or [])
        report.append(f"Total deposits: {len(deposit_list)}")
        if deposit_list:
            total_deposits = 0
            for deposit in deposit_list:
                if isinstance(deposit, dict):
                    amount = float(deposit.get('amount', deposit.get('qty', 0)))
                    total_deposits += amount
                    asset = deposit.get('asset', deposit.get('coin', 'Unknown'))
                    time_str = format_timestamp(deposit.get('insertTime', deposit.get('time', '')))
                    report.append(f"  {time_str}: {amount} {asset}")
            report.append(f"Total deposit amount: {total_deposits:.8f}")
    else:
        report.append("No deposit data retrieved")
    report.append("")
    
    # Withdrawals
    report.append("WITHDRAWALS")
    report.append("-" * 80)
    if withdrawals:
        withdrawal_list = withdrawals if isinstance(withdrawals, list) else (withdrawals.get('data', []) or withdrawals.get('withdrawals', []) or [])
        report.append(f"Total withdrawals: {len(withdrawal_list)}")
        if withdrawal_list:
            total_withdrawals = 0
            for withdrawal in withdrawal_list:
                if isinstance(withdrawal, dict):
                    amount = float(withdrawal.get('amount', withdrawal.get('qty', 0)))
                    total_withdrawals += amount
                    asset = withdrawal.get('asset', withdrawal.get('coin', 'Unknown'))
                    time_str = format_timestamp(withdrawal.get('applyTime', withdrawal.get('time', '')))
                    status = withdrawal.get('status', 'Unknown')
                    report.append(f"  {time_str}: {amount} {asset} (Status: {status})")
            report.append(f"Total withdrawal amount: {total_withdrawals:.8f}")
    else:
        report.append("No withdrawal data retrieved")
    report.append("")
    
    # Orders
    report.append("ORDERS")
    report.append("-" * 80)
    if orders:
        order_list = orders if isinstance(orders, list) else (orders.get('data', []) or orders.get('orders', []) or [])
        report.append(f"Total orders: {len(order_list)}")
        if order_list:
            # Group by status
            status_counts = {}
            for order in order_list[:50]:  # Sample first 50
                if isinstance(order, dict):
                    status = order.get('status', 'Unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
            for status, count in status_counts.items():
                report.append(f"  {status}: {count}")
    else:
        report.append("No order data retrieved")
    report.append("")
    
    report.append("=" * 80)
    report.append("END OF REPORT")
    report.append("=" * 80)
    
    return "\n".join(report)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("=" * 80)
    print("ASTERDEX ACCOUNT DATA EXTRACTION")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize API client
    print("Initializing API client...")
    api = AsterdexAPI(API_KEY, SECRET_KEY)
    
    # Test connection with debug
    print("Testing API connection...")
    account = api.get_account(debug=True)
    if account and account.get('error'):
        print("ERROR: Failed to connect to Asterdex API")
        print(f"Error details: {json.dumps(account, indent=2)}")
        print()
        print("Possible reasons:")
        print("1. IP address not whitelisted")
        print("2. API keys are incorrect")
        print("3. API keys don't have required permissions")
        print("4. API endpoint structure differs from expected")
        return
    
    if account:
        print("✓ API connection successful! Account endpoint returned data.")
    else:
        print("⚠ WARNING: Account endpoint returned no data, but no error was detected.")
        print("This may indicate the endpoint exists but requires different parameters.")
    print()
    
    # 1. Get Account Balance
    print("=" * 80)
    print("1. FETCHING ACCOUNT BALANCE")
    print("=" * 80)
    account = api.get_account(debug=True)
    if account and not account.get('error'):
        output_file = OUTPUT_DIR / "asterdex_account_balance.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(account, f, indent=2, default=str)
        print(f"✓ Account balance saved to: {output_file}")
    else:
        print("✗ Failed to retrieve account balance")
        account = None
    print()
    
    # 2. Get Trade History
    print("=" * 80)
    print("2. FETCHING TRADE HISTORY")
    print("=" * 80)
    trades = api.get_all_trades(limit=1000, debug=True)
    if trades:
        output_file = OUTPUT_DIR / "asterdex_trades.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(trades, f, indent=2, default=str)
        print(f"✓ Trade history saved to: {output_file}")
        print(f"  Total trades: {len(trades)}")
    else:
        print("✗ Failed to retrieve trade history")
        trades = []
    print()
    
    # 3. Get Deposit History
    print("=" * 80)
    print("3. FETCHING DEPOSIT HISTORY")
    print("=" * 80)
    deposits = api.get_deposits(limit=1000, debug=True)
    if deposits and not deposits.get('error'):
        output_file = OUTPUT_DIR / "asterdex_deposits.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(deposits, f, indent=2, default=str)
        print(f"✓ Deposit history saved to: {output_file}")
    else:
        print("✗ Failed to retrieve deposit history")
        deposits = None
    print()
    
    # 4. Get Withdrawal History
    print("=" * 80)
    print("4. FETCHING WITHDRAWAL HISTORY")
    print("=" * 80)
    withdrawals = api.get_withdrawals(limit=1000, debug=True)
    if withdrawals and not withdrawals.get('error'):
        output_file = OUTPUT_DIR / "asterdex_withdrawals.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(withdrawals, f, indent=2, default=str)
        print(f"✓ Withdrawal history saved to: {output_file}")
    else:
        print("✗ Failed to retrieve withdrawal history")
        withdrawals = None
    print()
    
    # 5. Get Order History
    print("=" * 80)
    print("5. FETCHING ORDER HISTORY")
    print("=" * 80)
    orders = api.get_orders(limit=1000, debug=True)
    if orders and not orders.get('error'):
        output_file = OUTPUT_DIR / "asterdex_orders.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(orders, f, indent=2, default=str)
        print(f"✓ Order history saved to: {output_file}")
    else:
        print("✗ Failed to retrieve order history")
        orders = None
    print()
    
    # 6. Generate Summary Report
    print("=" * 80)
    print("6. GENERATING SUMMARY REPORT")
    print("=" * 80)
    summary = generate_summary_report(account, trades, deposits, withdrawals, orders)
    output_file = OUTPUT_DIR / "asterdex_summary_report.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(summary)
    print(f"✓ Summary report saved to: {output_file}")
    print()
    
    # Print summary to console
    print(summary)
    
    print("=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("All data files have been saved to:")
    print(f"  {OUTPUT_DIR}")
    print()
    print("Files generated:")
    print("  - asterdex_account_balance.json")
    print("  - asterdex_trades.json")
    print("  - asterdex_deposits.json")
    print("  - asterdex_withdrawals.json")
    print("  - asterdex_orders.json")
    print("  - asterdex_summary_report.txt")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExtraction interrupted by user")
    except Exception as e:
        print(f"\n\nERROR: Unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

#!/usr/bin/env python3
"""Monitor and log all Quotex HTTP requests and WebSocket messages"""

import json
import logging
from datetime import datetime
from io import StringIO
from unittest.mock import patch
import requests

# Setup logging
log_stream = StringIO()
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

request_log = logging.getLogger('request_monitor')
request_log.setLevel(logging.DEBUG)

# Add file handler
fh = logging.FileHandler('quotex_traffic.log')
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
fh.setFormatter(formatter)
request_log.addHandler(fh)

# Also print to console
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
request_log.addHandler(ch)

print("🔐 Connecting to Quotex with traffic monitoring...")

# Monkey-patch requests to log all HTTP calls
original_request = requests.Session.request

def logged_request(self, method, url, **kwargs):
    request_log.info(f"→ REQUEST: {method} {url}")

    # Log headers (excluding sensitive data)
    if 'headers' in kwargs:
        safe_headers = {k: (v[:50] + '...' if len(str(v)) > 50 else v)
                       for k, v in kwargs['headers'].items()}
        request_log.debug(f"  Headers: {safe_headers}")

    # Log request data
    if 'data' in kwargs:
        data = kwargs['data']
        if isinstance(data, str):
            data_log = data[:200] + '...' if len(data) > 200 else data
        else:
            data_log = str(data)[:200]
        request_log.debug(f"  Data: {data_log}")

    if 'json' in kwargs:
        request_log.debug(f"  JSON: {json.dumps(kwargs['json'], indent=2, default=str)[:500]}")

    # Make the actual request
    response = original_request(self, method, url, **kwargs)

    # Log response
    request_log.info(f"← RESPONSE: {response.status_code} {len(response.content)} bytes")

    if response.status_code < 400 and response.headers.get('content-type', '').startswith('application/json'):
        try:
            response_data = response.json()
            response_log = json.dumps(response_data, indent=2, default=str)[:500]
            request_log.debug(f"  Response JSON: {response_log}")
        except:
            pass

    return response

requests.Session.request = logged_request

print("\n" + "="*80)
print("CONNECTING AND MONITORING TRAFFIC")
print("="*80 + "\n")

try:
    from pyquotex import client as quotex_client

    client = quotex_client(email="ctrlprcrypto@gmail.com", password="CtrlPrCrypto@2023")
    print(f"✅ Connected to Quotex")
    print(f"   Account ID: {client.account_id}")
    print(f"   Is Demo: {client.account_is_demo}\n")

    print("="*80)
    print("TEST 1: Getting instruments (triggers HTTP)")
    print("="*80 + "\n")

    try:
        instruments = client.get_instruments()
        print(f"✅ Instruments fetched: {len(instruments) if instruments else 0} items\n")
    except Exception as e:
        print(f"⚠️  {e}\n")

    print("="*80)
    print("TEST 2: Getting balance")
    print("="*80 + "\n")

    try:
        balance = client.get_balance()
        print(f"✅ Balance: {balance}\n")
    except Exception as e:
        print(f"⚠️  {e}\n")

    print("="*80)
    print("TEST 3: Getting candle data")
    print("="*80 + "\n")

    try:
        candles = client.get_candle_data("EURUSD_otc", 60, 10)
        print(f"✅ Candles fetched: {type(candles)}\n")
    except Exception as e:
        print(f"⚠️  {e}\n")

    print("="*80)
    print("TEST 4: Checking account balance data structure")
    print("="*80 + "\n")

    if hasattr(client.api, 'account_balance'):
        balance_data = client.api.account_balance
        print(f"✅ Account balance structure:")
        print(json.dumps(balance_data, indent=2, default=str))
        print()

    print("="*80)
    print("✅ Traffic monitoring complete")
    print("="*80)
    print(f"\n📌 Full traffic log saved to: quotex_traffic.log")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

#!/usr/bin/env python3
"""Comprehensive analysis of Quotex data structures and what they send"""

import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv()

from pyquotex.stable_api import Quotex

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD")

async def main():
    print("🔐 Connecting to Quotex...")
    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)
    connected, msg = await client.connect()
    if not connected:
        print(f"❌ Connection failed: {msg}")
        return

    print(f"✅ Connected\n")

    # Get initial balance
    await asyncio.wait_for(client.get_balance(), timeout=5)

    print("="*80)
    print("QUOTEX DATA FLOW ANALYSIS")
    print("="*80)

    print("\n1️⃣ ACCOUNT BALANCE DATA STRUCTURE")
    print("-" * 80)
    if hasattr(client.api, 'account_balance'):
        balance = client.api.account_balance
        print(json.dumps(balance, indent=2))
        print("\n📊 What Quotex sends:")
        print("   • liveBalance: Real money balance")
        print("   • demoBalance: Practice/demo account balance")
        print("   • tournamentsBalances: Balances for tournament accounts")
        print("   • dayLimit: Daily trading limit")
        print("   • dayBalance: Daily balance")

    print("\n2️⃣ SESSION DATA STRUCTURE")
    print("-" * 80)
    if hasattr(client.api, 'session_data'):
        session = client.api.session_data
        print("Keys:", list(session.keys()))
        for key, value in session.items():
            if isinstance(value, str):
                preview = value[:100] + "..." if len(value) > 100 else value
            else:
                preview = str(value)[:100]
            print(f"  • {key}: {preview}")

        print("\n📊 What Quotex sends:")
        print("   • cookies: Session cookies for maintaining authentication")
        print("   • token: API token/session token")
        print("   • user_agent: Browser user agent string")

    print("\n3️⃣ WEBSOCKET MESSAGES (wss_message)")
    print("-" * 80)
    if hasattr(client.api, 'wss_message'):
        wss_msg = client.api.wss_message
        print(f"Type: {type(wss_msg).__name__}")
        if isinstance(wss_msg, list) and len(wss_msg) > 0:
            print("Current content:")
            print(json.dumps(wss_msg, indent=2))
            print("\n📊 What Quotex sends via WebSocket:")
            print("   • Asset symbols (e.g., 'EURUSD')")
            print("   • Period/timeframe identifiers")
            print("   • Real-time price updates")
            print("   • Candle data")

    print("\n4️⃣ PROFILE DATA")
    print("-" * 80)
    if hasattr(client.api, 'profile') and client.api.profile:
        profile = client.api.profile
        print(f"Profile type: {type(profile).__name__}")

        # Get all non-private attributes
        attrs = {}
        for attr in dir(profile):
            if not attr.startswith('_'):
                try:
                    val = getattr(profile, attr)
                    if not callable(val):
                        attrs[attr] = val
                except:
                    pass

        if attrs:
            print("Available attributes:")
            for key, val in attrs.items():
                print(f"  • {key}: {repr(val)}")

            print("\n📊 What Quotex sends in profile:")
            print("   • User identification (profile_id, nick_name)")
            print("   • Account balances (demo_balance, live_balance)")
            print("   • Location/currency info (country, currency_code)")
            print("   • Account level/status (profile_level)")
        else:
            print("⚠️  Profile attributes are empty (may need additional data fetch)")

    print("\n5️⃣ TESTING ACTUAL WEBSOCKET MESSAGES")
    print("-" * 80)

    # Capture initial wss_message
    initial_msg = getattr(client.api, 'wss_message', None)
    print(f"Initial wss_message: {initial_msg}")

    print("\nCalling various API methods to see what WebSocket data is generated...")

    # Try getting instruments
    try:
        print("  • Calling get_instruments()...")
        instruments = await asyncio.wait_for(client.get_instruments(), timeout=5)
        print(f"    ✅ Got {len(instruments)} instruments")

        current_msg = getattr(client.api, 'wss_message', None)
        if current_msg != initial_msg:
            print(f"    WebSocket update: {current_msg}")
    except Exception as e:
        print(f"    ⚠️  {e}")

    # Try getting candles
    try:
        print("  • Calling get_candle_data()...")
        candles = await asyncio.wait_for(
            client.get_candle_data("EURUSD_otc", 60, 10),
            timeout=5
        )
        print(f"    ✅ Got candle data")

        current_msg = getattr(client.api, 'wss_message', None)
        if current_msg != initial_msg:
            print(f"    WebSocket update: {current_msg}")
    except Exception as e:
        print(f"    ⚠️  {e}")

    print("\n6️⃣ QUOTEX API METHODS THAT SEND DATA")
    print("-" * 80)

    api_methods = [attr for attr in dir(client.api)
                  if not attr.startswith('_') and callable(getattr(client.api, attr))]

    # Filter for likely data-sending methods
    send_methods = [m for m in api_methods if any(x in m.lower() for x in
                   ['send', 'request', 'buy', 'sell', 'trade', 'subscribe', 'candle', 'price'])]

    print("Methods that likely send data:")
    for method in send_methods[:15]:
        print(f"   • {method}")
    if len(send_methods) > 15:
        print(f"   ... and {len(send_methods) - 15} more")

    print("\n7️⃣ HTTP REQUEST ENDPOINTS")
    print("-" * 80)

    if hasattr(client.api, 'https_url'):
        print(f"Base HTTPS URL: {client.api.https_url}")
    if hasattr(client.api, 'wss_url'):
        print(f"WebSocket URL: {client.api.wss_url}")
    if hasattr(client.api, 'host'):
        print(f"Host: {client.api.host}")

    print("\n📊 Common endpoints Quotex likely uses:")
    print("   • /login - Authentication")
    print("   • /profile - User profile data")
    print("   • /balance - Account balance")
    print("   • /instruments - Available trading instruments")
    print("   • /candles - Historical candle data")
    print("   • /trades - Trading operations")
    print("   • /websocket - Real-time data stream")

    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)
    print("\n📋 SUMMARY: Quotex sends:")
    print("   1. Authentication: cookies, tokens, session data")
    print("   2. Account Info: balance (live/demo), profile, limits")
    print("   3. Market Data: instruments, candles, real-time prices")
    print("   4. WebSocket: asset symbols, periods, price updates")

    await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

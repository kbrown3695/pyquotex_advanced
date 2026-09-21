#!/usr/bin/env python3
"""Inspect Quotex data flow - WebSocket messages, HTTP requests, and real-time data"""

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
    try:
        client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)
        connected, msg = await client.connect()
        if not connected:
            print(f"❌ Connection failed: {msg}")
            return

        print(f"✅ Connected")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    print("\n" + "="*80)
    print("CALLING get_balance() to populate account data")
    print("="*80)

    try:
        balance = await asyncio.wait_for(client.get_balance(), timeout=5)
        print(f"✅ Balance: {balance}")
    except Exception as e:
        print(f"⚠️ get_balance() failed: {e}")

    # Now check account info
    account_id = getattr(client, 'account_id', 'N/A')
    is_demo = getattr(client, 'account_is_demo', 'N/A')
    print(f"   Account ID: {account_id}")
    print(f"   Is Demo: {is_demo}")

    print("\n" + "="*80)
    print("TEST 1: API Object Structure")
    print("="*80)

    if not hasattr(client, 'api') or client.api is None:
        print("❌ No client.api object")
        await client.close()
        return

    print(f"✅ client.api exists: {type(client.api)}")
    api_attrs = [attr for attr in dir(client.api) if not attr.startswith('_')]
    print(f"✅ API has {len(api_attrs)} public attributes/methods")

    important_attrs = ['account_balance', 'websocket', 'websocket_client', 'wss_message',
                      'session_data', 'profile', 'settings']

    print("\n📋 Checking important attributes:")
    for attr in important_attrs:
        if attr in api_attrs:
            try:
                val = getattr(client.api, attr)
                val_type = type(val).__name__

                if attr == 'account_balance' and isinstance(val, dict):
                    print(f"   ✅ {attr:25} = {val_type}")
                    for k, v in val.items():
                        print(f"       {k}: {v}")
                elif attr == 'session_data' and isinstance(val, dict):
                    print(f"   ✅ {attr:25} = {val_type} (keys: {list(val.keys())})")
                elif attr == 'wss_message' and isinstance(val, dict):
                    print(f"   ✅ {attr:25} = {val_type}")
                else:
                    print(f"   ✅ {attr:25} = {val_type}")
            except Exception as e:
                print(f"   ❌ {attr:25} = [Error: {e}]")
        else:
            print(f"   ⚠️  {attr:25} = [not found in api attributes]")

    print("\n" + "="*80)
    print("TEST 2: Full API Attributes List")
    print("="*80)

    print(f"All public attributes ({len(api_attrs)}):")
    for i, attr in enumerate(api_attrs):
        if i % 3 == 0:
            print()
            print(f"  ", end="")
        print(f"{attr:25} ", end="")
    print("\n")

    print("="*80)
    print("TEST 3: WebSocket Data")
    print("="*80)

    if hasattr(client.api, 'wss_message'):
        wss_msg = client.api.wss_message
        print(f"✅ wss_message exists: {type(wss_msg)}")
        if wss_msg:
            try:
                msg_str = json.dumps(wss_msg, indent=2, default=str)
                if len(msg_str) > 1000:
                    print(msg_str[:1000] + "\n   ... (truncated)")
                else:
                    print(msg_str)
            except Exception as e:
                print(f"   {str(wss_msg)[:500]}")
        else:
            print("   (empty/None)")

    print("\n" + "="*80)
    print("TEST 4: Testing subscribe_realtime_candle")
    print("="*80)

    try:
        print("Subscribing to EURUSD_otc (60s candles)...")
        await client.subscribe_realtime_candle("EURUSD_otc", 60)
        print("✅ Subscribed")

        # Wait for WebSocket message
        await asyncio.sleep(1.5)

        if hasattr(client.api, 'wss_message'):
            wss_msg = client.api.wss_message
            if wss_msg:
                print(f"\n✅ Message received after subscribe:")
                try:
                    msg_str = json.dumps(wss_msg, indent=2, default=str)
                    if len(msg_str) > 1000:
                        print(msg_str[:1000] + "\n   ... (truncated)")
                    else:
                        print(msg_str)
                except:
                    print(wss_msg)
    except Exception as e:
        print(f"⚠️ Error: {e}")

    print("\n" + "="*80)
    print("✅ Data flow inspection complete")
    print("="*80)

    await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

#!/usr/bin/env python3
"""Deep inspection of what data Quotex actually provides."""

import asyncio
import os
import time
from dotenv import load_dotenv

load_dotenv()

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD")

try:
    from pyquotex.stable_api import Quotex
except ImportError:
    print("❌ pyquotex not installed")
    exit(1)


async def deep_inspect():
    """Deep inspection of Quotex data sources."""

    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)

    print("🔐 Connecting to Quotex...")
    connected, msg = await client.connect()
    if not connected:
        print(f"❌ Connection failed: {msg}")
        return

    print(f"✅ Connected\n")

    # === TEST 1: get_balance() at different times ===
    print("="*80)
    print("TEST 1: get_balance() reliability")
    print("="*80)

    for i in range(3):
        try:
            print(f"  Attempt {i+1}...", end=" ", flush=True)
            start = time.time()
            balance = await asyncio.wait_for(client.get_balance(), timeout=2)
            elapsed = time.time() - start
            print(f"✅ {balance} ({elapsed:.2f}s)")
        except asyncio.TimeoutError:
            print(f"⏱️  TIMEOUT (>2s)")
        except Exception as e:
            print(f"❌ {type(e).__name__}: {e}")
        await asyncio.sleep(0.5)

    # === TEST 2: Check session_data ===
    print("\n" + "="*80)
    print("TEST 2: Checking client.api.session_data")
    print("="*80)

    if hasattr(client.api, 'session_data'):
        print(f"✅ session_data exists (type: {type(client.api.session_data)})")
        if client.api.session_data:
            print(f"   Value: {client.api.session_data}")
    else:
        print(f"❌ No session_data attribute")

    # === TEST 3: Check settings ===
    print("\n" + "="*80)
    print("TEST 3: Checking client.api.settings")
    print("="*80)

    if hasattr(client.api, 'settings'):
        print(f"✅ settings exists (type: {type(client.api.settings)})")
        if client.api.settings:
            print(f"   Keys: {client.api.settings.keys() if hasattr(client.api.settings, 'keys') else dir(client.api.settings)}")
            if hasattr(client.api.settings, 'items'):
                for key, value in list(client.api.settings.items())[:10]:
                    print(f"     {key}: {repr(value)[:80]}")
    else:
        print(f"❌ No settings attribute")

    # === TEST 4: WebSocket data ===
    print("\n" + "="*80)
    print("TEST 4: WebSocket-related attributes")
    print("="*80)

    ws_attrs = ['websocket', 'websocket_client', 'wss_message', 'realtime_price_data']
    for attr in ws_attrs:
        if hasattr(client.api, attr):
            val = getattr(client.api, attr, None)
            print(f"✅ {attr:25s}: {type(val).__name__:20s} = {repr(val)[:60]}")

    # === TEST 5: Check if get_balance is cached ===
    print("\n" + "="*80)
    print("TEST 5: Fast repeated get_balance() calls")
    print("="*80)

    try:
        for i in range(5):
            start = time.time()
            balance = await asyncio.wait_for(client.get_balance(), timeout=0.5)
            elapsed = time.time() - start
            print(f"  Call {i+1}: {balance} ({elapsed*1000:.0f}ms)")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")

    # === TEST 6: Check account_balance attribute ===
    print("\n" + "="*80)
    print("TEST 6: client.api.account_balance")
    print("="*80)

    if hasattr(client.api, 'account_balance'):
        val = getattr(client.api, 'account_balance', None)
        print(f"✅ account_balance exists: {val} (type: {type(val)})")
    else:
        print(f"❌ No account_balance attribute")

    # === TEST 7: Get history ===
    print("\n" + "="*80)
    print("TEST 7: get_history() for account info")
    print("="*80)

    try:
        print(f"  Calling get_history()...", end=" ", flush=True)
        history = await asyncio.wait_for(client.api.get_history(), timeout=3)
        print(f"✅ Got history")
        if history:
            print(f"   Type: {type(history)}")
            print(f"   Keys/attrs: {list(history.keys()) if hasattr(history, 'keys') else dir(history)[:10]}")
            if isinstance(history, dict):
                for k, v in list(history.items())[:5]:
                    print(f"     {k}: {repr(v)[:80]}")
    except asyncio.TimeoutError:
        print(f"⏱️  TIMEOUT")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")

    # === TEST 8: Account mode check ===
    print("\n" + "="*80)
    print("TEST 8: Account mode detection")
    print("="*80)

    print(f"  account_is_demo: {getattr(client, 'account_is_demo', 'N/A')}")
    print(f"  Is this accurate? (Should be 1 for PRACTICE mode)")

    await client.close()
    print("\n✅ Deep inspection complete")


if __name__ == "__main__":
    try:
        asyncio.run(deep_inspect())
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

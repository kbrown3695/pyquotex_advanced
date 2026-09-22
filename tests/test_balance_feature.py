#!/usr/bin/env python3
"""Test the real and demo balance fetching feature."""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD")

try:
    from pyquotex.stable_api import Quotex
except ImportError:
    print("❌ pyquotex not installed")
    exit(1)


async def test_balances():
    """Test getting real and demo balances."""

    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)

    print("🔐 Connecting to Quotex...")
    connected, msg = await client.connect()
    if not connected:
        print(f"❌ Connection failed: {msg}")
        return

    print(f"✅ Connected: {msg}")
    print(f"✅ Account ID: {client.account_id}")

    print("\n" + "="*80)
    print("TEST 1: Get Balances (Current Mode)")
    print("="*80)

    # Check profile
    if client.api.profile:
        print(f"✅ Profile loaded")
        print(f"   Demo Balance:  ${client.api.profile.demo_balance:.2f}")
        print(f"   Real Balance:  ${client.api.profile.live_balance:.2f}")
        print(f"   Current Mode:  {'REAL' if client.account_is_demo == 0 else 'PRACTICE'}")

    # Get current balance via get_balance()
    current_balance = await client.get_balance()
    print(f"\n   get_balance(): ${current_balance:.2f}")

    print("\n" + "="*80)
    print("TEST 2: Switch to PRACTICE Mode")
    print("="*80)

    try:
        await client.change_account("PRACTICE")
        await asyncio.sleep(2)

        if client.api.profile:
            print(f"✅ Switched to PRACTICE")
            print(f"   Demo Balance:  ${client.api.profile.demo_balance:.2f}")
            print(f"   Real Balance:  ${client.api.profile.live_balance:.2f}")
            balance = await client.get_balance()
            print(f"   get_balance(): ${balance:.2f}")
    except Exception as e:
        print(f"⚠️  Could not switch to PRACTICE: {e}")

    print("\n" + "="*80)
    print("TEST 3: Switch to REAL Mode")
    print("="*80)

    try:
        await client.change_account("REAL")
        await asyncio.sleep(2)

        if client.api.profile:
            print(f"✅ Switched to REAL")
            print(f"   Demo Balance:  ${client.api.profile.demo_balance:.2f}")
            print(f"   Real Balance:  ${client.api.profile.live_balance:.2f}")
            balance = await client.get_balance()
            print(f"   get_balance(): ${balance:.2f}")
    except Exception as e:
        print(f"⚠️  Could not switch to REAL: {e}")

    print("\n" + "="*80)
    print("TEST 4: Profile Structure")
    print("="*80)

    if client.api.profile:
        profile = client.api.profile
        print(f"✅ Profile attributes:")
        print(f"   demo_balance:    {getattr(profile, 'demo_balance', 'N/A')}")
        print(f"   live_balance:    {getattr(profile, 'live_balance', 'N/A')}")
        print(f"   account_balance: {getattr(profile, 'account_balance', 'N/A')}")

        # Show all attributes
        print(f"\n   All profile attributes:")
        for attr in dir(profile):
            if not attr.startswith('_'):
                val = getattr(profile, attr, None)
                if not callable(val):
                    print(f"      {attr}: {val}")

    await client.close()
    print("\n✅ Test completed")


if __name__ == "__main__":
    try:
        asyncio.run(test_balances())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

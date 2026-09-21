#!/usr/bin/env python3
"""Inspect pyquotex CLIENT object to find balance fields."""

import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv()

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD")

try:
    from pyquotex.stable_api import Quotex
except ImportError:
    print("❌ pyquotex not installed")
    exit(1)


async def inspect_client():
    """Connect and inspect CLIENT structure."""

    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)

    print("🔐 Connecting to Quotex...")
    connected, msg = await client.connect()
    if not connected:
        print(f"❌ Connection failed: {msg}")
        return

    print(f"✅ Connected")

    # Try to get account info
    account_id = getattr(client, 'account_id', 'N/A')
    is_demo = getattr(client, 'account_is_demo', 'N/A')
    print(f"   Account ID: {account_id}")
    print(f"   Is Demo: {is_demo}")

    # Get balance to ensure profile is loaded
    print("\n📊 Calling get_balance()...")
    try:
        balance = await asyncio.wait_for(client.get_balance(), timeout=5)
        print(f"✅ get_balance() returned: {balance} (type: {type(balance)})")
    except Exception as e:
        print(f"⚠️ get_balance() failed: {e}")

    # Inspect API object
    print("\n" + "="*80)
    print("🔍 INSPECTING CLIENT.api")
    print("="*80)

    if client.api:
        print(f"✅ client.api exists (type: {type(client.api)})")
        print(f"✅ client.api attributes: {[k for k in dir(client.api) if not k.startswith('_')]}")
    else:
        print("❌ client.api is None")
        return

    # Inspect profile
    print("\n" + "="*80)
    print("🔍 INSPECTING CLIENT.api.profile")
    print("="*80)

    if client.api.profile:
        profile = client.api.profile
        print(f"✅ profile exists (type: {type(profile)})")

        # List all attributes
        attrs = [k for k in dir(profile) if not k.startswith('_')]
        print(f"✅ All attributes ({len(attrs)}): {attrs}")

        # Print values of key attributes
        print("\n📋 Attribute VALUES:")
        for attr in attrs:
            try:
                value = getattr(profile, attr)
                if not callable(value):
                    print(f"  {attr:30s} = {repr(value)[:100]}")
            except Exception as e:
                print(f"  {attr:30s} = [ERROR: {e}]")

        # Print __dict__
        print("\n📋 Profile __dict__ (direct access):")
        try:
            for key, value in profile.__dict__.items():
                print(f"  {key:30s} = {repr(value)[:100]}")
        except Exception as e:
            print(f"❌ Cannot access __dict__: {e}")
    else:
        print("⚠️ profile is None - trying to refresh...")
        try:
            await asyncio.wait_for(client.get_balance(), timeout=3)
            print("✅ Refreshed, trying again...")
            if client.api.profile:
                profile = client.api.profile
                print(f"✅ Now profile exists (type: {type(profile)})")
                print(f"✅ Attributes: {[k for k in dir(profile) if not k.startswith('_')]}")
            else:
                print("❌ Still no profile")
        except Exception as e:
            print(f"❌ Refresh failed: {e}")

    # Look for balance in different places
    print("\n" + "="*80)
    print("🔍 SEARCHING FOR BALANCE VALUES")
    print("="*80)

    balance_keywords = [
        'balance', 'demo', 'real', 'account', 'live', 'training',
        'practice', 'funds', 'equity', 'money', 'amount'
    ]

    if client.api.profile:
        print("\n📍 Checking profile attributes for balance keywords:")
        profile = client.api.profile
        for attr in dir(profile):
            if not attr.startswith('_'):
                for keyword in balance_keywords:
                    if keyword.lower() in attr.lower():
                        try:
                            value = getattr(profile, attr)
                            if not callable(value):
                                print(f"  ✅ {attr:40s} = {value}")
                        except:
                            pass

    # Try to access account info differently
    print("\n📍 Checking client attributes:")
    for attr in dir(client):
        if not attr.startswith('_'):
            for keyword in ['balance', 'account', 'profile']:
                if keyword.lower() in attr.lower():
                    try:
                        value = getattr(client, attr)
                        if not callable(value) and value is not None:
                            print(f"  ✅ client.{attr:35s} = {repr(value)[:80]}")
                    except:
                        pass

    await client.close()
    print("\n✅ Inspection complete")


if __name__ == "__main__":
    try:
        asyncio.run(inspect_client())
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

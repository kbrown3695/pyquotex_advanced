#!/usr/bin/env python3
"""
Test: Find the right way to fetch balance from Quotex API
"""
import asyncio
import os
from dotenv import load_dotenv
from pyquotex.stable_api import Quotex

load_dotenv()

async def test_balance_methods():
    """Test different methods to fetch account balance."""

    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")

    if not email or not password:
        print("❌ No credentials in .env")
        return

    print(f"🔐 Connecting as {email}...")
    client = Quotex(email=email, password=password, host="qxbroker.com", lang="en")

    try:
        # Connect
        check, reason = await client.connect()
        if not check:
            print(f"❌ Connection failed: {reason}")
            return

        print(f"✅ Connected: {reason}")
        print()

        # Switch to PRACTICE
        print("📋 Switching to PRACTICE account...")
        await client.change_account("PRACTICE")
        print("✅ Switched to PRACTICE")
        print()

        # Test 1: Check API attributes
        print("=" * 60)
        print("TEST 1: Inspect CLIENT.api attributes")
        print("=" * 60)

        if hasattr(client, 'api'):
            print(f"✅ client.api exists: {type(client.api)}")

            # Check for account_balance
            if hasattr(client.api, 'account_balance'):
                ab = client.api.account_balance
                print(f"   account_balance: {ab}")
                if isinstance(ab, dict):
                    for k, v in ab.items():
                        print(f"      {k}: {v}")
            else:
                print("   ❌ account_balance not found")

            # Check for profile
            if hasattr(client.api, 'profile'):
                profile = client.api.profile
                print(f"   profile: {profile}")
            else:
                print("   ❌ profile not found")

        print()

        # Test 2: Call get_balance()
        print("=" * 60)
        print("TEST 2: Call client.get_balance()")
        print("=" * 60)

        try:
            balance = await asyncio.wait_for(client.get_balance(), timeout=3)
            print(f"✅ get_balance() returned: {balance}")
        except asyncio.TimeoutError:
            print("❌ get_balance() timeout")
        except Exception as e:
            print(f"❌ get_balance() error: {e}")

        print()

        # Test 3: Check if account_balance populated after get_balance
        print("=" * 60)
        print("TEST 3: Check account_balance after get_balance()")
        print("=" * 60)

        if hasattr(client.api, 'account_balance'):
            ab = client.api.account_balance
            print(f"   account_balance: {ab}")
            if isinstance(ab, dict):
                for k, v in ab.items():
                    print(f"      {k}: {v}")
        else:
            print("   ❌ account_balance still not found")

        print()

        # Test 4: Try to access websocket directly
        print("=" * 60)
        print("TEST 4: Inspect WebSocket connection")
        print("=" * 60)

        if hasattr(client, 'ws') and client.ws:
            print(f"✅ WebSocket connected: {type(client.ws)}")

            # Try to send a refresh request if method exists
            if hasattr(client, 'get_account_info'):
                try:
                    info = await asyncio.wait_for(client.get_account_info(), timeout=2)
                    print(f"   get_account_info(): {info}")
                except:
                    pass

            # Try other methods
            if hasattr(client, 'get_account_balance'):
                try:
                    bal = await asyncio.wait_for(client.get_account_balance(), timeout=2)
                    print(f"   get_account_balance(): {bal}")
                except:
                    pass

            if hasattr(client, 'get_user_info'):
                try:
                    info = await asyncio.wait_for(client.get_user_info(), timeout=2)
                    print(f"   get_user_info(): {info}")
                except Exception as e:
                    print(f"   get_user_info() error: {e}")
        else:
            print("❌ WebSocket not connected")

        print()

        # Test 5: List all methods available
        print("=" * 60)
        print("TEST 5: Available client methods")
        print("=" * 60)

        methods = [m for m in dir(client) if not m.startswith('_') and callable(getattr(client, m))]
        balance_methods = [m for m in methods if 'balance' in m.lower() or 'account' in m.lower()]

        print("Balance/Account related methods:")
        for method in balance_methods:
            print(f"   - {method}()")

        print()
        print("=" * 60)
        print("TEST 6: Final account_balance state")
        print("=" * 60)

        if hasattr(client.api, 'account_balance'):
            ab = client.api.account_balance
            print(f"account_balance dict: {ab}")

            # Extract key values
            if isinstance(ab, dict):
                print(f"\nExtracted values:")
                print(f"  liveBalance: ${ab.get('liveBalance', 0):.2f}")
                print(f"  demoBalance: ${ab.get('demoBalance', 0):.2f}")
                print(f"  dayBalance: ${ab.get('dayBalance', 0):.2f}")
                print(f"  dayLimit: ${ab.get('dayLimit', 0):.2f}")

        await client.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_balance_methods())

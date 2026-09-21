#!/usr/bin/env python3
"""Inspect WebSocket messages sent and received by Quotex"""

import asyncio
import json
import time
import os
from datetime import datetime
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
    print("INSPECTING WEBSOCKET INFRASTRUCTURE")
    print("="*80)

    # Check WebSocket state
    print(f"\n✅ WebSocket Status:")
    if hasattr(client.api, 'websocket_alive'):
        print(f"   websocket_alive: {client.api.websocket_alive}")
    if hasattr(client.api, 'websocket_thread'):
        print(f"   websocket_thread: {client.api.websocket_thread}")
    if hasattr(client.api, 'websocket'):
        print(f"   websocket: {type(client.api.websocket)}")
    if hasattr(client.api, 'websocket_client'):
        print(f"   websocket_client: {type(client.api.websocket_client)}")
    if hasattr(client.api, 'wss_url'):
        print(f"   wss_url: {client.api.wss_url}")

    # Inspect WebSocketApp
    if hasattr(client.api, 'websocket'):
        ws_app = client.api.websocket
        print(f"\n✅ WebSocketApp Details:")
        print(f"   URL: {ws_app.url if hasattr(ws_app, 'url') else 'N/A'}")
        print(f"   Status: {ws_app.status if hasattr(ws_app, 'status') else 'N/A'}")

    print("\n" + "="*80)
    print("CURRENT MESSAGE IN wss_message")
    print("="*80)

    if hasattr(client.api, 'wss_message'):
        wss_msg = client.api.wss_message
        print(f"✅ wss_message exists: {type(wss_msg)}")
        if wss_msg:
            try:
                print(f"\n📋 Current message content:")
                print(json.dumps(wss_msg, indent=2, default=str))
            except Exception as e:
                print(f"Error formatting: {e}")
                print(wss_msg)
        else:
            print("   (empty or None)")

    print("\n" + "="*80)
    print("TRIGGERING WEBSOCKET MESSAGES")
    print("="*80)

    print("\n1️⃣ Testing subscribe_realtime_candle()...")
    try:
        # First, capture what wss_message is before
        msg_before = getattr(client.api, 'wss_message', None)
        print(f"   wss_message before: {type(msg_before)}")

        # Subscribe
        result = await client.subscribe_realtime_candle("EURUSD_otc", 60)
        print(f"✅ subscribe_realtime_candle returned: {result}")

        # Wait a bit for message to arrive
        await asyncio.sleep(2)

        # Check what message was captured
        msg_after = getattr(client.api, 'wss_message', None)
        if msg_after and msg_after != msg_before:
            print(f"\n✅ New message captured:")
            try:
                print(json.dumps(msg_after, indent=2, default=str))
            except:
                print(msg_after)
        else:
            print("   (no new message received)")

    except Exception as e:
        print(f"⚠️  Error: {e}")

    print("\n2️⃣ Testing unsubscribe_realtime_candle()...")
    try:
        result = await client.unsubscribe_realtime_candle("EURUSD_otc", 60)
        print(f"✅ unsubscribe_realtime_candle returned: {result}")

        await asyncio.sleep(1)

        msg_now = getattr(client.api, 'wss_message', None)
        if msg_now:
            print(f"\n📨 Message after unsubscribe:")
            try:
                print(json.dumps(msg_now, indent=2, default=str))
            except:
                print(msg_now)
    except Exception as e:
        print(f"⚠️  Error: {e}")

    print("\n" + "="*80)
    print("INSPECTING WEBSOCKET CLIENT METHODS")
    print("="*80)

    if hasattr(client.api, 'websocket_client'):
        ws_client = client.api.websocket_client
        print(f"\n✅ WebSocket client: {type(ws_client)}")

        # List public methods
        methods = [m for m in dir(ws_client) if not m.startswith('_') and callable(getattr(ws_client, m, None))]
        print(f"   Methods: {methods[:10]}...")

        # Check for send/message methods
        for method_name in ['send', 'send_message', 'on_message', 'receive']:
            if hasattr(ws_client, method_name):
                method = getattr(ws_client, method_name)
                if callable(method):
                    print(f"   ✅ {method_name}: {type(method)}")

    print("\n" + "="*80)
    print("CHECKING SIGNAL/INDICATOR SUBSCRIPTIONS")
    print("="*80)

    try:
        # Try subscribing to signals
        result = await client.subscribe_signals()
        print(f"✅ subscribe_signals() returned: {result}")

        await asyncio.sleep(1)

        msg = getattr(client.api, 'wss_message', None)
        if msg:
            print(f"\n📨 Message after subscribing to signals:")
            try:
                print(json.dumps(msg, indent=2, default=str)[:500])
            except:
                print(str(msg)[:500])
    except Exception as e:
        print(f"⚠️  subscribe_signals failed: {e}")

    print("\n" + "="*80)
    print("✅ WebSocket inspection complete")
    print("="*80)

    await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

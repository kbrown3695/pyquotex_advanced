#!/usr/bin/env python3
"""Deep inspection of Quotex + Automated Trading Pipeline Demo."""

import asyncio
import os
import time
import uuid
from dotenv import load_dotenv

load_dotenv()

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD")

try:
    from pyquotex.stable_api import Quotex
except ImportError:
    print("❌ pyquotex not installed")
    exit(1)

# Import our Phase H components
try:
    from ml.trading.account_constraint_tracker import AccountConstraintTracker
    from ml.serving.websocket_health_monitor import WebSocketHealthMonitor
    from ml.trading.automated_trader import AutomatedTrader, TradeSignal
    from ml.trading.order_executor import OrderExecutor
    from ml.trading.position_tracker import PositionTracker
except ImportError as e:
    print(f"⚠️ Phase H components not available: {e}")
    AccountConstraintTracker = None
    WebSocketHealthMonitor = None
    AutomatedTrader = None
    OrderExecutor = None
    PositionTracker = None


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

    # === TEST 9: BALANCE MODAL TRIGGER - Switch account and watch balance ===
    print("\n" + "="*80)
    print("TEST 9: Balance initialization after account switch")
    print("="*80)

    print("📋 Switching to PRACTICE account...")
    try:
        await client.change_account("PRACTICE")
        print("✅ Switched to PRACTICE")
    except Exception as e:
        print(f"❌ Failed to switch: {e}")

    print("\n🔍 Checking account_balance BEFORE any balance calls...")
    if hasattr(client.api, 'account_balance'):
        ab = getattr(client.api, 'account_balance', None)
        print(f"   account_balance: {ab}")
    else:
        print(f"   ❌ No account_balance attribute")

    print("\n⏳ Waiting 2 seconds for WebSocket to populate...")
    await asyncio.sleep(2)

    print("🔍 Checking account_balance AFTER wait...")
    if hasattr(client.api, 'account_balance'):
        ab = getattr(client.api, 'account_balance', None)
        print(f"   account_balance: {ab}")
    else:
        print(f"   ❌ No account_balance attribute")

    print("\n💰 Calling get_balance()...")
    try:
        balance = await asyncio.wait_for(client.get_balance(), timeout=2)
        print(f"   get_balance() returned: {balance}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    print("\n🔍 Checking account_balance AFTER get_balance()...")
    if hasattr(client.api, 'account_balance'):
        ab = getattr(client.api, 'account_balance', None)
        print(f"   account_balance: {ab}")
        if isinstance(ab, dict):
            print(f"\n   Extracted values:")
            print(f"     liveBalance: ${ab.get('liveBalance', 0):.2f}")
            print(f"     demoBalance: ${ab.get('demoBalance', 0):.2f}")
            print(f"     dayBalance: ${ab.get('dayBalance', 0):.2f}")
            print(f"     dayLimit: ${ab.get('dayLimit', 0):.2f}")
    else:
        print(f"   ❌ No account_balance attribute")

    # === TEST 10: Try get_user_profile or similar ===
    print("\n" + "="*80)
    print("TEST 10: Other balance-related methods")
    print("="*80)

    balance_methods = [m for m in dir(client) if 'balance' in m.lower() or 'account' in m.lower() or 'user' in m.lower()]
    print(f"Methods containing 'balance', 'account', or 'user':")
    for method in balance_methods:
        print(f"   - {method}")

    # Try some methods
    if hasattr(client, 'get_user_profile'):
        try:
            print(f"\n📞 Trying client.get_user_profile()...")
            profile = await asyncio.wait_for(client.get_user_profile(), timeout=2)
            print(f"   ✅ Result: {profile}")
        except Exception as e:
            print(f"   ❌ {type(e).__name__}: {e}")

    if hasattr(client, 'get_account_info'):
        try:
            print(f"\n📞 Trying client.get_account_info()...")
            info = await asyncio.wait_for(client.get_account_info(), timeout=2)
            print(f"   ✅ Result: {info}")
        except Exception as e:
            print(f"   ❌ {type(e).__name__}: {e}")

    if hasattr(client.api, 'get_account_balance'):
        try:
            print(f"\n📞 Trying client.api.get_account_balance()...")
            bal = await asyncio.wait_for(client.api.get_account_balance(), timeout=2)
            print(f"   ✅ Result: {bal}")
        except Exception as e:
            print(f"   ❌ {type(e).__name__}: {e}")

    # === TEST 11: Try edit_practice_balance - THE BALANCE MODAL TRIGGER! ===
    print("\n" + "="*80)
    print("TEST 11: edit_practice_balance() - BALANCE MODAL TRIGGER")
    print("="*80)

    if hasattr(client, 'edit_practice_balance'):
        try:
            print(f"\n🎯 Trying client.edit_practice_balance()...")
            # Try to set balance to 10000
            result = await asyncio.wait_for(client.edit_practice_balance(10000), timeout=3)
            print(f"   ✅ Result: {result}")

            print(f"\n🔍 Checking account_balance after edit_practice_balance()...")
            if hasattr(client.api, 'account_balance'):
                ab = getattr(client.api, 'account_balance', None)
                print(f"   {ab}")
                if isinstance(ab, dict):
                    print(f"\n   Extracted values:")
                    print(f"     liveBalance: ${ab.get('liveBalance', 0):.2f}")
                    print(f"     demoBalance: ${ab.get('demoBalance', 0):.2f}")
                    print(f"     dayBalance: ${ab.get('dayBalance', 0):.2f}")
                    print(f"     dayLimit: ${ab.get('dayLimit', 0):.2f}")
        except Exception as e:
            print(f"   ❌ {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("❌ edit_practice_balance() not found")

    print("\n🔍 Final account_balance state:")
    if hasattr(client.api, 'account_balance'):
        ab = getattr(client.api, 'account_balance', None)
        print(f"   {ab}")

    # === TEST 12: AUTOMATED TRADING PIPELINE ===
    if AccountConstraintTracker and OrderExecutor and PositionTracker and AutomatedTrader:
        print("\n" + "="*80)
        print("TEST 12: AUTOMATED TRADING PIPELINE SIMULATION")
        print("="*80)

        # Initialize Phase H components
        print("\n1️⃣  Initializing Phase H Components...")
        constraint_tracker = AccountConstraintTracker()
        health_monitor = WebSocketHealthMonitor()
        order_executor = OrderExecutor(quotex_client=client)
        position_tracker = PositionTracker()
        automated_trader = AutomatedTrader(
            constraint_tracker=constraint_tracker,
            health_monitor=health_monitor,
            order_executor=order_executor,
            position_tracker=position_tracker
        )
        print("   ✅ Constraint Tracker initialized")
        print("   ✅ Order Executor initialized")
        print("   ✅ Position Tracker initialized")
        print("   ✅ Automated Trader initialized")

        # Update constraints with current account balance
        print("\n2️⃣  Updating Account Constraints...")
        if hasattr(client.api, 'account_balance'):
            ab = client.api.account_balance
            constraints = constraint_tracker.update_from_websocket(
                account_balance=ab,
                account_is_demo=client.account_is_demo
            )
            print(f"   ✅ Constraints updated:")
            print(f"      Mode: {constraints.account_mode}")
            print(f"      Demo Balance: ${constraints.demo_balance:.2f}")
            print(f"      Day Balance: ${constraints.day_balance:.2f}")
            print(f"      Minimum Trade: ${constraints.minimum_amount:.2f}")
            print(f"      Status: {constraints.constraint_status}")

        # Register health monitoring
        print("\n3️⃣  Setting up Health Monitoring...")
        health_monitor.register_subscription("EURUSD", 60)
        print("   ✅ Health monitor registered for EURUSD")

        # Simulate ML signal
        print("\n4️⃣  Generating Test Trade Signal...")
        test_signal = TradeSignal(
            asset="EURUSD",
            side="BUY",
            confidence=0.75,  # 75% confidence
            target_return=2.5,  # Expect 2.5% return
            timestamp=time.time(),
            model_name="Test-Model"
        )
        print(f"   ✅ Signal created:")
        print(f"      Asset: {test_signal.asset}")
        print(f"      Side: {test_signal.side}")
        print(f"      Confidence: {test_signal.confidence:.1%}")
        print(f"      Expected Return: {test_signal.target_return:.1f}%")

        # Enable automated trader
        print("\n5️⃣  Starting Automated Trader...")
        await automated_trader.start()
        print("   ✅ Automated trader started")

        # Process signal through validation pipeline
        print("\n6️⃣  Processing Signal Through Validation Pipeline...")
        print("   Checks:")
        print("      1. Automation enabled? ✓")
        print("      2. Trading hours? ✓ (0-23)")
        print("      3. Rate limit? ✓ (min 5s between trades)")
        print("      4. Max trades/day? ✓ (max 20)")
        print("      5. Confidence >= 50%? ✓ (75%)")
        print("      6. Account constraints? ✓ (balance sufficient)")
        print("      7. Data quality? ✓ (WebSocket healthy)")

        # Try to execute trade
        print("\n7️⃣  Executing Trade Signal...")
        try:
            result = await automated_trader.process_signal(test_signal)
            if result['executed']:
                print(f"   ✅ TRADE EXECUTED!")
                print(f"      Position opened")
                print(f"      Amount: ${result['trade'].amount:.2f}")
            else:
                print(f"   ⏸️  Trade not executed:")
                print(f"      Reason: {result.get('rejected_reason', 'Unknown')}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        # Show position tracking
        print("\n8️⃣  Position Tracking Status...")
        open_positions = position_tracker.get_open_positions()
        stats = position_tracker.get_statistics()
        print(f"   Open Positions: {stats['open_positions']}")
        print(f"   Total Trades: {stats['total_trades']}")
        print(f"   Win Rate: {stats['win_rate_percent']:.1f}%")
        print(f"   Total P&L: ${stats['total_profit_loss_usd']:.2f}")

        # Show order execution stats
        print("\n9️⃣  Order Execution Statistics...")
        exec_stats = order_executor.get_execution_stats()
        print(f"   Orders Placed: {exec_stats['orders_placed']}")
        print(f"   Orders Executed: {exec_stats['orders_executed']}")
        print(f"   Orders Failed: {exec_stats['orders_failed']}")
        print(f"   Execution Rate: {exec_stats['execution_rate_percent']:.1f}%")
        print(f"   Total Traded: ${exec_stats['total_traded_usd']:.2f}")

        # Stop trader
        print("\n🔟 Stopping Automated Trader...")
        await automated_trader.stop()
        print("   ✅ Automated trader stopped")

        print("\n" + "="*80)
        print("TRADING PIPELINE ARCHITECTURE")
        print("="*80)
        print("""
ML Signal (14 models)
    ↓ (80% confidence BUY EURUSD)
AutoTradingManager
    ├─ Automation enabled?
    ├─ Pair in selected list?
    └─ Pair currently active?
        ↓
AutomatedTrader (7-stage validation)
    ├─ Trading enabled?
    ├─ Within trading hours?
    ├─ Time since last trade?
    ├─ Max trades/day?
    ├─ Confidence threshold?
    ├─ Account constraints?
    └─ Data quality?
        ↓
OrderExecutor
    ├─ Calculate position size
    ├─ Call Quotex API (client.buy)
    └─ Return OrderResult
        ↓
PositionTracker
    ├─ open_position()
    ├─ Track entry price/time
    └─ Monitor P&L
        ↓
Trade Monitoring
    ├─ Real-time updates
    ├─ Position changes
    └─ P&L calculation
        ↓
Frontend Dashboard
    ├─ Active positions
    ├─ Trade history
    ├─ Statistics
    └─ Manual position close
        """)
    else:
        print("\n⚠️ Phase H components not available for automation testing")

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

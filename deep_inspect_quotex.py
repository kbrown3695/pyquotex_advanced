#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 Deep WebSocket Order Execution Inspector
============================================
Verifies if orders actually reach Quotex broker via WebSocket.
"""

import asyncio
import os
import time
import logging
from dotenv import load_dotenv

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('websocket_inspection.log')
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD")

try:
    from pyquotex.stable_api import Quotex
except ImportError:
    logger.error("❌ pyquotex not installed")
    exit(1)

# Import Phase H components
try:
    from ml.trading.order_executor import OrderExecutor
except ImportError as e:
    logger.warning(f"⚠️  OrderExecutor not available: {e}")
    OrderExecutor = None


async def test_tuple_unpacking():
    """Verify tuple unpacking logic"""

    logger.info("\n" + "=" * 80)
    logger.info("🧪 TEST 1: TUPLE UNPACKING LOGIC")
    logger.info("=" * 80)

    logger.info("\nTesting Python tuple truthiness:")

    # The bug
    logger.info("\n❌ BROKEN CODE (old):")
    logger.info("   if result:  # where result is a tuple")
    logger.info("      orders_executed += 1")

    test_cases = [
        ("(True, response)", (True, {"id": "123"})),
        ("(False, error)", (False, "Connection failed")),
        ("(False, None)", (False, None))
    ]

    for name, result in test_cases:
        if result:
            logger.info(f"   {name} → if result: TRUE ❌ (Wrong! Should check first element)")

    # The fix
    logger.info("\n✅ FIXED CODE (new):")
    logger.info("   success, response = result")
    logger.info("   if not success:")
    logger.info("      orders_failed += 1")

    for name, result in test_cases:
        success, response = result
        logger.info(f"   {name} → {'Failed' if not success else 'Executed'} ✅")

    logger.info("\n✅ Tuple unpacking logic verified!")
    return True


async def test_raw_order_execution():
    """Test raw order execution directly to Quotex WebSocket"""

    logger.info("\n" + "=" * 80)
    logger.info("🧪 TEST 2: RAW ORDER EXECUTION")
    logger.info("=" * 80)

    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)

    logger.info("🔐 Connecting to Quotex...")
    try:
        connected, msg = await client.connect()
        if not connected:
            logger.error(f"❌ Connection failed: {msg}")
            return False
    except Exception as e:
        logger.error(f"❌ Connection error: {e}")
        return False

    logger.info("✅ Connected to Quotex")

    # Set to PRACTICE mode
    client.set_account_mode("PRACTICE")

    try:
        balance = await client.get_balance()
        logger.info(f"📊 Practice Balance: ${balance:.2f}")
    except Exception as e:
        logger.warning(f"⚠️  Could not get balance: {e}")

    # Test CALL order
    logger.info("\n📍 Sending CALL (Bullish) Order...")
    logger.info("   Asset: EURUSD")
    logger.info("   Amount: $10")
    logger.info("   Duration: 300s")
    logger.info("   Direction: call")

    try:
        result = await client.buy(
            amount=10.0,
            asset="EURUSD",
            direction="call",
            duration=300,
            time_mode="TIME"
        )

        logger.info(f"\n📦 RAW RESULT:")
        logger.info(f"   Type: {type(result)}")
        logger.info(f"   Value: {result}")

        # Proper tuple unpacking (THE FIX)
        if isinstance(result, tuple):
            success, response = result
            logger.info(f"\n✅ TUPLE UNPACKED:")
            logger.info(f"   Success: {success}")
            logger.info(f"   Response type: {type(response)}")

            if success:
                logger.info(f"\n🎉 ORDER EXECUTED BY BROKER!")
                if isinstance(response, dict) and "id" in response:
                    logger.info(f"   Order ID: {response.get('id')}")
                    logger.info(f"   Response keys: {list(response.keys())}")
                    return True
                else:
                    logger.warning(f"   ⚠️  Response: {response}")
                    return False
            else:
                logger.error(f"❌ BROKER REJECTED: {response}")
                return False
        else:
            logger.error(f"❌ NOT A TUPLE: {type(result)}")
            return False

    except Exception as e:
        logger.error(f"❌ EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def test_order_executor():
    """Test OrderExecutor with detailed logging"""

    logger.info("\n" + "=" * 80)
    logger.info("🧪 TEST 3: ORDER EXECUTOR LAYER")
    logger.info("=" * 80)

    if not OrderExecutor:
        logger.warning("⚠️  OrderExecutor not available, skipping")
        return None

    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD)

    logger.info("🔐 Connecting...")
    try:
        connected, msg = await client.connect()
        if not connected:
            logger.error(f"❌ Connection failed: {msg}")
            return False
    except Exception as e:
        logger.error(f"❌ Connection error: {e}")
        return False

    logger.info("✅ Connected")
    client.set_account_mode("PRACTICE")

    # Create OrderExecutor
    executor = OrderExecutor(quotex_client=client, logger=logger)

    logger.info("\n📍 Testing execute_buy_order() with direction='call'...")

    try:
        order_result = await executor.execute_buy_order(
            asset="EURUSD",
            amount=10.0,
            expiration_time=300,
            signal_confidence=0.75,
            direction="call"
        )

        logger.info(f"\n📦 ORDER RESULT:")
        logger.info(f"   Order ID: {order_result.order_id}")
        logger.info(f"   Status: {order_result.status}")
        logger.info(f"   Message: {order_result.message}")
        logger.info(f"   Amount: ${order_result.amount}")

        if order_result.status == "EXECUTED":
            logger.info(f"\n✅ ORDER EXECUTED SUCCESSFULLY!")
            logger.info(f"   Stats - Placed: {executor.orders_placed}, Executed: {executor.orders_executed}")
            return True
        else:
            logger.error(f"❌ ORDER FAILED: {order_result.message}")
            logger.info(f"   Stats - Placed: {executor.orders_placed}, Failed: {executor.orders_failed}")
            return False
    except Exception as e:
        logger.error(f"❌ OrderExecutor error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def main():
    """Main inspection flow"""

    if not QUOTEX_EMAIL or not QUOTEX_PASSWORD:
        logger.error("❌ QUOTEX_EMAIL and QUOTEX_PASSWORD not set in .env")
        return

    logger.info("\n")
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║" + " " * 78 + "║")
    logger.info("║" + "  🔍 QUOTEX WEBSOCKET ORDER EXECUTION DEEP INSPECTION".center(78) + "║")
    logger.info("║" + "  Diagnosing why orders aren't reaching broker".center(78) + "║")
    logger.info("║" + " " * 78 + "║")
    logger.info("╚" + "=" * 78 + "╝")

    results = {
        "tuple_unpacking": await test_tuple_unpacking(),
        "raw_execution": await test_raw_order_execution(),
        "order_executor": await test_order_executor()
    }

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📋 INSPECTION SUMMARY")
    logger.info("=" * 80)

    for test_name, passed in results.items():
        if passed is None:
            status = "⏭️  SKIP"
        else:
            status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} - {test_name}")

    logger.info("\n" + "=" * 80)
    logger.info("🔍 DIAGNOSIS")
    logger.info("=" * 80)

    if results.get("raw_execution"):
        logger.info("✅ Raw WebSocket orders ARE reaching Quotex")
        logger.info("   Problem is likely in OrderExecutor layer")
    else:
        logger.info("❌ Raw WebSocket orders NOT reaching Quotex")
        logger.info("   Problem: WebSocket connection or Quotex API")

    if results.get("order_executor"):
        logger.info("✅ OrderExecutor IS properly executing orders")
    elif results.get("order_executor") is None:
        logger.info("⏭️  OrderExecutor test skipped")
    else:
        logger.info("❌ OrderExecutor NOT executing orders")

    logger.info("\n✅ Inspection complete. Check websocket_inspection.log for full details.\n")


if __name__ == "__main__":
    asyncio.run(main())

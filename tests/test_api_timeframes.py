#!/usr/bin/env python3
"""
Quick diagnostic test to check which Quotex API timeframes are supported.
Run this AFTER the main app is running (it uses the already-authenticated CLIENT).
"""

import asyncio
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

async def test_timeframes():
    """Test which timeframes the Quotex API supports using engine.py's CLIENT."""

    print("🔍 Quotex API Timeframe Test")
    print("=" * 50)

    # Import from engine.py to use the already-authenticated CLIENT
    try:
        from engine import CLIENT, DISPLAY_TO_INTERNAL, log
    except ImportError:
        print("❌ Could not import CLIENT from engine.py")
        print("Make sure you're in the QuotexChart directory and engine.py exists")
        return

    if not CLIENT or not CLIENT.api:
        print("❌ CLIENT not initialized in engine.py")
        print("⚠️  Run the main app first to authenticate with Quotex")
        print("   Then run this test again in another terminal")
        return

    try:
        print("✅ Using authenticated CLIENT from engine.py")

        # Test timeframes (in seconds)
        test_periods = [
            (5, "5s"),
            (10, "10s"),
            (15, "15s"),
            (30, "30s"),
            (60, "1m"),
            (300, "5m"),
            (900, "15m"),
            (3600, "1h"),
            (14400, "4h"),
        ]

        asset = "AUD/CAD (OTC)"  # Use display name
        internal_asset = DISPLAY_TO_INTERNAL.get(asset, "AUDCAD_otc")
        current_time = time.time()

        print(f"\n📊 Testing timeframes for {asset} ({internal_asset}):")
        print("-" * 50)

        for period, label in test_periods:
            try:
                # Request 10 candles for this timeframe
                candles = await CLIENT.get_candles(internal_asset, current_time, 10 * period, period)

                if candles and len(candles) > 0:
                    print(f"✅ {label:6} ({period:5}s) - {len(candles):3} candles loaded")
                else:
                    print(f"⚠️  {label:6} ({period:5}s) - No data returned")

            except Exception as e:
                print(f"❌ {label:6} ({period:5}s) - Error: {str(e)[:50]}")

        print("\n" + "=" * 50)
        print("💡 Analysis & Next Steps:")
        print("=" * 50)
        print("\n✅ Expected Results:")
        print("  • 5s-30s: ❌ Fail (API doesn't support) → aggregation handles it")
        print("  • 1m (60s): ✅ Pass (base timeframe)")
        print("  • 5m, 15m, 1h: ✅ Pass (standard timeframes)")
        print("  • 4h: ✅ Should pass or fail (check result)")

        print("\n🛠️  How to fix if timeframes don't load:")
        print("  1. Aggregation is NOW IN engine.py for 5s/10s/15s/30s")
        print("  2. Check engine.py:795 load_timeframe_data()")
        print("  3. If 1m loads, aggregation will work")
        print("  4. Debug logs enabled (CONSOLE_LEVEL=2)")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(test_timeframes())
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted")
    except Exception as e:
        print(f"❌ Fatal error: {e}")

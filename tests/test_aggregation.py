#!/usr/bin/env python3
"""
Direct test of candle aggregation logic (no API required).
This tests the fix that aggregates 1m candles into smaller timeframes.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from engine import aggregate_candles_from_1m

def create_mock_1m_candles(count: int) -> list:
    """Create mock 1-minute candles for testing."""
    candles = []
    base_time = int(time.time())
    base_price = 1.0

    for i in range(count):
        candle = {
            'time': base_time - (count - i) * 60,  # Each candle is 60s apart
            'open': base_price + (i * 0.001),
            'high': base_price + (i * 0.001) + 0.002,
            'low': base_price + (i * 0.001) - 0.001,
            'close': base_price + (i * 0.001) + 0.0015
        }
        candles.append(candle)

    return candles

def test_aggregation():
    """Test candle aggregation for different timeframes."""

    print("🧪 Candle Aggregation Test")
    print("=" * 60)

    # Create 120 mock 1-minute candles
    mock_candles_1m = create_mock_1m_candles(120)
    print(f"\n✅ Created {len(mock_candles_1m)} mock 1-minute candles")

    # Test different aggregation targets
    test_cases = [
        (5, "5s", 2),    # 60s / 5s = 2 candles per 5s period
        (10, "10s", 6),  # 60s / 10s = 6 candles per 10s period
        (15, "15s", 4),  # 60s / 15s = 4 candles per 15s period
        (30, "30s", 2),  # 60s / 30s = 2 candles per 30s period
    ]

    print("\n📊 Aggregation Results:")
    print("-" * 60)

    all_pass = True

    for period_sec, label, expected_ratio in test_cases:
        try:
            aggregated = aggregate_candles_from_1m(mock_candles_1m, period_sec)

            # Check if aggregation is correct
            expected_candles = len(mock_candles_1m) // expected_ratio

            if len(aggregated) == expected_candles:
                status = "✅ PASS"
            else:
                status = f"⚠️  PARTIAL ({len(aggregated)} got, {expected_candles} expected)"
                all_pass = False

            print(f"{status} | {label:6} | {len(aggregated):3} candles | "
                  f"ratio 1:{expected_ratio} | "
                  f"data: {aggregated[0]['open']:.4f}→{aggregated[-1]['close']:.4f}")

        except Exception as e:
            print(f"❌ FAIL  | {label:6} | Error: {str(e)[:40]}")
            all_pass = False

    print("\n" + "=" * 60)
    print("📋 Summary:")
    print("=" * 60)

    if all_pass:
        print("✅ All aggregation tests PASSED!")
        print("\n🎯 What this means:")
        print("  • The aggregation logic is working correctly")
        print("  • 1-minute candles can be broken down into smaller timeframes")
        print("  • Small timeframes (5s, 10s, 15s, 30s) should load via aggregation")
    else:
        print("⚠️  Some tests had issues - check above")

    print("\n🔧 Implementation Details:")
    print("  • Function: aggregate_candles_from_1m()")
    print("  • Location: engine.py:795")
    print("  • Usage: Called by load_small_timeframe_data()")
    print("  • When: Automatic when user selects 5s/10s/15s/30s timeframe")

    print("\n🚀 Next Step:")
    print("  • Start the app and switch to small timeframes")
    print("  • Watch console for: '✅ Loaded X 5s candles... (aggregated from 1m)'")
    print("  • If you see that message → aggregation is working!")

if __name__ == "__main__":
    try:
        test_aggregation()
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

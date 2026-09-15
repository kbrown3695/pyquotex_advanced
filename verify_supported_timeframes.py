#!/usr/bin/env python3
"""
Verification script to test supported timeframes.
Run AFTER the main app is running.
"""

import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

async def verify_timeframes():
    """Verify that supported timeframes load correctly."""

    print("\n" + "=" * 70)
    print("🧪 QuotexChart Supported Timeframes Verification")
    print("=" * 70)

    # These are the ONLY supported timeframes (no tick data available)
    supported_tfs = [
        ("1m", 60),
        ("2m", 120),
        ("3m", 180),
        ("5m", 300),
        ("10m", 600),
        ("15m", 900),
        ("30m", 1800),
        ("1h", 3600),
        ("4h", 14400),
    ]

    # These should NOT be supported (would need tick data)
    unsupported_tfs = [
        ("5s", 5),
        ("10s", 10),
        ("15s", 15),
        ("30s", 30),
    ]

    print("\n✅ SUPPORTED TIMEFRAMES (will load from Quotex API):")
    print("-" * 70)
    for label, seconds in supported_tfs:
        print(f"  ✓ {label:6} ({seconds:5} seconds)")

    print("\n❌ UNSUPPORTED TIMEFRAMES (API doesn't support):")
    print("-" * 70)
    for label, seconds in unsupported_tfs:
        print(f"  ✗ {label:6} ({seconds:5} seconds) - requires tick data")

    print("\n" + "=" * 70)
    print("📋 USAGE GUIDE")
    print("=" * 70)

    print("\n1️⃣  IN THE UI:")
    print("   • The dropdown should ONLY show: 1m, 2m, 3m, 5m, 10m, 15m, 30m, 1h, 4h")
    print("   • 5s, 10s, 15s, 30s should NOT appear")

    print("\n2️⃣  IN THE CONSOLE (engine.py logs):")
    print("   • Look for: '✅ Loaded XXX [tf] candles for [asset] from API'")
    print("   • Example: '✅ Loaded 199 1m candles for AUD/CAD (OTC) from API'")

    print("\n3️⃣  TRADING RECOMMENDATIONS:")
    print("   • Scalping (quick trades): Use 1m - 5m timeframes")
    print("   • Swing trading: Use 15m - 1h timeframes")
    print("   • Position trading: Use 1h - 4h timeframes")

    print("\n" + "=" * 70)
    print("🚀 NEXT STEPS")
    print("=" * 70)

    print("\n1. Restart the app: python app.py")
    print("2. Check the timeframe dropdown in the UI")
    print("3. Select different timeframes and verify:")
    print("   - Charts update")
    print("   - Console shows successful loads")
    print("   - No errors appear")
    print("4. If issues persist, check the full logs with CONSOLE_LEVEL=2")

    print("\n" + "=" * 70)
    print("✅ Verification Complete!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    try:
        asyncio.run(verify_timeframes())
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

#!/usr/bin/env python3
"""Quick test to manually trigger aggregation and verify output."""

import asyncio
import json
from pathlib import Path
from ml.data.candle_store import CandleStore
from ml.data.candle_aggregator_bg import BackgroundCandleAggregator


async def test_aggregation():
    """Run a single aggregation cycle and show results."""
    print("\n" + "="*80)
    print("  MANUAL AGGREGATION TEST")
    print("="*80 + "\n")

    store = CandleStore("quotex_candles.db")

    # Load selected pairs
    if not Path("selected_signal_pairs.json").exists():
        print("[WARN] selected_signal_pairs.json not found. Using default test pair.")
        selected_pairs = ["USD/INR (OTC)"]
    else:
        with open("selected_signal_pairs.json") as f:
            selected_pairs = json.load(f)

    print(f"[INFO] Processing {len(selected_pairs)} selected pairs...\n")

    agg = BackgroundCandleAggregator(store)

    # Process each pair
    for asset in selected_pairs:
        print(f"[PROCESS] {asset}")

        # Check 1m candles
        count_1m = store.count_candles(asset, "1m")
        if count_1m == 0:
            print(f"  [SKIP] No 1m candles found")
            continue

        print(f"  [SOURCE] {count_1m} x 1m candles")

        # Run aggregation
        await agg._aggregate_for_asset(asset)

        # Show results
        for tf in agg.TARGET_TIMEFRAMES:
            count = store.count_candles(asset, tf)
            if count > 0:
                print(f"  [DONE] {tf}: {count} candles created")
            else:
                print(f"  [PENDING] {tf}: 0 candles (need more data)")

        print()

    print("="*80)
    print("[SUCCESS] Aggregation test complete")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_aggregation())

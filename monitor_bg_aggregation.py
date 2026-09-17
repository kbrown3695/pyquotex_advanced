#!/usr/bin/env python3
"""Monitor background candle aggregation progress.

Shows real-time stats on aggregated candles for selected pairs.
"""

import json
import time
import sqlite3
import sys
from pathlib import Path
from ml.data.candle_store import CandleStore

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def print_header(text):
    print(f"\n{'='*80}")
    print(f"  {text}")
    print('='*80)


def get_selected_pairs():
    """Load selected pairs from JSON."""
    if Path("selected_signal_pairs.json").exists():
        with open("selected_signal_pairs.json") as f:
            return json.load(f)
    return []


def show_aggregation_stats():
    """Show aggregation progress for each pair."""
    store = CandleStore("quotex_candles.db")
    selected = get_selected_pairs()

    if not selected:
        print("[WARN] No selected pairs found. Check selected_signal_pairs.json")
        return

    print_header("BACKGROUND CANDLE AGGREGATION MONITOR")
    print(f"[INFO] Selected pairs: {', '.join(selected)}")
    print(f"[TIME] {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    target_timeframes = ["5s", "10s", "15s", "30s", "3m", "5m", "10m", "15m", "30m", "1h", "4h"]

    for asset in selected:
        print(f"\n[ASSET] {asset}")
        print("-" * 80)

        # Get 1m candle count (source)
        count_1m = store.count_candles(asset, "1m")
        latest_1m = store.get_latest_candle(asset, "1m")

        print(f"  1m (source): {count_1m:>6} candles", end="")
        if latest_1m:
            print(f"  |  Latest: {latest_1m['time']} (O={latest_1m['open']:.5f} C={latest_1m['close']:.5f})")
        else:
            print()

        # Show aggregated timeframes
        for tf in target_timeframes:
            count = store.count_candles(asset, tf)
            latest = store.get_latest_candle(asset, tf)

            if count > 0:
                status = "[OK]" if count > 50 else "[WAIT]"
                print(f"  {tf:>3} (agg):   {count:>6} candles  {status}", end="")
                if latest:
                    print(f"  |  Latest: {latest['time']} (O={latest['open']:.5f} C={latest['close']:.5f})")
                else:
                    print()
            else:
                print(f"  {tf:>3} (agg):   {count:>6} candles  [PENDING]")


def show_database_summary():
    """Show overall database statistics."""
    print_header("DATABASE SUMMARY")

    conn = sqlite3.connect("quotex_candles.db")
    cursor = conn.cursor()

    # Total candles
    cursor.execute("SELECT COUNT(*) FROM candles")
    total = cursor.fetchone()[0]

    # By timeframe
    cursor.execute("""
        SELECT timeframe, COUNT(*) as cnt
        FROM candles
        GROUP BY timeframe
        ORDER BY cnt DESC
    """)
    results = cursor.fetchall()

    print(f"Total candles in database: {total:,}\n")
    print("By timeframe:")
    for tf, cnt in results:
        pct = (cnt / total * 100) if total > 0 else 0
        print(f"  {tf:>3}: {cnt:>8,} candles ({pct:>5.1f}%)")

    conn.close()


if __name__ == "__main__":
    try:
        show_aggregation_stats()
        show_database_summary()
        print("\n" + "="*80)
        print("[INFO] Run this script periodically to monitor aggregation progress")
        print("="*80 + "\n")
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

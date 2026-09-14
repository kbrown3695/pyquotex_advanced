"""Verify candle data in database for all timeframes."""

from ml.data.candle_store import CandleStore
from datetime import datetime
import json


def verify_candles():
    """Verify all timeframe data in database."""
    store = CandleStore("quotex_candles.db")

    timeframes = ["5s", "10s", "15s", "30s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "4h"]
    assets = ["AUD/CAD (OTC)", "USD/PKR (OTC)", "EUR/USD (OTC)", "GBP/USD (OTC)"]

    print("\n" + "="*80)
    print("🗄️  DATABASE CANDLE VERIFICATION")
    print("="*80)

    summary = {}

    for asset in assets:
        print(f"\n📊 {asset}")
        print("-" * 80)
        asset_summary = {}

        for tf in timeframes:
            count = store.count_candles(asset, tf)
            if count > 0:
                latest = store.get_latest_candle(asset, tf)
                oldest = store.get_candles(asset, tf, limit=1, start_time=0)

                if latest and oldest:
                    latest_time = datetime.fromtimestamp(latest["time"]).strftime("%Y-%m-%d %H:%M:%S")
                    oldest_time = datetime.fromtimestamp(oldest[0]["time"]).strftime("%Y-%m-%d %H:%M:%S")

                    print(f"  {tf:6} → {count:4} candles | "
                          f"Oldest: {oldest_time} | Latest: {latest_time} | "
                          f"O={latest['open']:.5f} H={latest['high']:.5f} L={latest['low']:.5f} C={latest['close']:.5f}")

                    asset_summary[tf] = {
                        "count": count,
                        "oldest": oldest_time,
                        "latest": latest_time,
                        "latest_ohlc": {
                            "o": round(latest['open'], 5),
                            "h": round(latest['high'], 5),
                            "l": round(latest['low'], 5),
                            "c": round(latest['close'], 5)
                        }
                    }
            else:
                print(f"  {tf:6} → ❌ NO DATA")

        summary[asset] = asset_summary

    # Check data consistency
    print("\n" + "="*80)
    print("✅ VERIFICATION CHECKS")
    print("="*80)

    for asset in assets:
        print(f"\n{asset}:")
        asset_data = summary.get(asset, {})

        # Check 1m candles exist
        if "1m" in asset_data:
            m1_count = asset_data["1m"]["count"]
            print(f"  ✅ 1m candles: {m1_count} stored")
        else:
            print(f"  ❌ 1m candles: NOT FOUND")
            continue

        # Check aggregated timeframes have data
        aggregated = ["5s", "10s", "15s", "30s", "4h"]
        for agg_tf in aggregated:
            if agg_tf in asset_data:
                agg_count = asset_data[agg_tf]["count"]
                # Rough estimate: 1m should aggregate to roughly 1m_count/period candles
                period = {"5s": 5, "10s": 10, "15s": 15, "30s": 30, "4h": 240}[agg_tf]
                expected_approx = max(1, m1_count // period)

                if agg_count > 0:
                    print(f"  ✅ {agg_tf}: {agg_count} candles (expected ~{expected_approx})")
                else:
                    print(f"  ⚠️  {agg_tf}: 0 candles (aggregation may need time)")
            else:
                print(f"  ⚠️  {agg_tf}: Not in database")

        # Check standard API timeframes
        api_tfs = ["2m", "3m", "5m", "10m", "15m", "30m", "1h"]
        api_data = [tf for tf in api_tfs if tf in asset_data]
        if api_data:
            print(f"  ℹ️  API timeframes: {len(api_data)}/7 present ({', '.join(api_data)})")

    # Export summary to JSON for reference
    with open("db_verification_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\n📄 Summary saved to: db_verification_summary.json")

    # Return summary for programmatic use
    return summary


if __name__ == "__main__":
    result = verify_candles()

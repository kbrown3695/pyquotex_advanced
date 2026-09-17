"""Background async candle aggregator for selected pairs.

Continuously aggregates 1m candles into all timeframes (5s, 10s, 15s, 30s, 3m, 5m, 10m, 15m, 30m, 1h, 4h)
in the background for selected pairs only.
"""

import asyncio
import json
import os
import time
from typing import List, Dict, Optional
from pathlib import Path
from ml.data.candle_store import CandleStore


class BackgroundCandleAggregator:
    """Background async candle aggregator for selected pairs."""

    TIMEFRAME_SECONDS = {
        "5s": 5,
        "10s": 10,
        "15s": 15,
        "30s": 30,
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "10m": 600,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
    }

    # Target timeframes to aggregate into (from 1m candles)
    TARGET_TIMEFRAMES = ["5s", "10s", "15s", "30s", "3m", "5m", "10m", "15m", "30m", "1h", "4h"]

    def __init__(self, candle_store: CandleStore, selected_pairs_file: str = "selected_signal_pairs.json"):
        """Initialize background aggregator.

        Args:
            candle_store: CandleStore instance for persistence
            selected_pairs_file: Path to JSON file with selected pairs
        """
        self.store = candle_store
        self.selected_pairs_file = selected_pairs_file
        self.selected_pairs: List[str] = []
        self.running = False
        self.last_aggregation_time: Dict[str, float] = {}  # {asset: timestamp}

    def load_selected_pairs(self) -> List[str]:
        """Load selected pairs from JSON file."""
        if not os.path.exists(self.selected_pairs_file):
            return []

        try:
            with open(self.selected_pairs_file, "r") as f:
                pairs = json.load(f)
            self.selected_pairs = pairs if isinstance(pairs, list) else []
            return self.selected_pairs
        except Exception as e:
            print(f"⚠️ Failed to load selected pairs: {e}")
            return []

    async def start(self):
        """Start the background aggregation loop."""
        self.running = True
        print("[🔄] Starting background candle aggregator...")

        while self.running:
            try:
                # Reload selected pairs every minute
                self.load_selected_pairs()

                if not self.selected_pairs:
                    await asyncio.sleep(10)
                    continue

                # Aggregate for each selected pair
                for asset in self.selected_pairs:
                    try:
                        await self._aggregate_for_asset(asset)
                    except Exception as e:
                        print(f"⚠️ Aggregation error for {asset}: {e}")

                # Sleep briefly before next cycle
                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ Background aggregator error: {e}")
                await asyncio.sleep(5)

        self.running = False
        print("[✅] Background candle aggregator stopped")

    async def stop(self):
        """Stop the background aggregator."""
        self.running = False

    async def _aggregate_for_asset(self, asset: str) -> None:
        """Aggregate 1m candles into higher timeframes for one asset.

        Args:
            asset: Asset symbol (e.g. "AUD/CAD (OTC)")
        """
        # Don't re-aggregate too frequently for the same asset
        now = time.time()
        if asset in self.last_aggregation_time:
            if now - self.last_aggregation_time[asset] < 30:  # Min 30s between runs
                return

        self.last_aggregation_time[asset] = now

        # Get latest 1m candles
        latest_1m_candles = self.store.get_candles(asset, "1m", limit=500)

        if not latest_1m_candles or len(latest_1m_candles) < 5:
            return  # Not enough data

        # For each target timeframe, aggregate from 1m
        for target_tf in self.TARGET_TIMEFRAMES:
            try:
                await self._aggregate_to_timeframe(asset, target_tf, latest_1m_candles)
            except Exception as e:
                print(f"⚠️ Failed to aggregate {asset}/{target_tf}: {e}")

    async def _aggregate_to_timeframe(
        self, asset: str, target_tf: str, source_candles: List[Dict]
    ) -> None:
        """Aggregate 1m candles into a higher timeframe.

        Args:
            asset: Asset symbol
            target_tf: Target timeframe (e.g. "5m", "1h")
            source_candles: List of 1m candles (sorted by time ASC)
        """
        if not source_candles:
            return

        target_seconds = self.TIMEFRAME_SECONDS[target_tf]

        # Group 1m candles by target timeframe slots
        slots: Dict[int, List[Dict]] = {}

        for candle in source_candles:
            time_val = candle.get("time", 0)
            slot = (time_val // target_seconds) * target_seconds

            if slot not in slots:
                slots[slot] = []
            slots[slot].append(candle)

        # Aggregate each slot into a single candle
        for slot_time, candles_in_slot in sorted(slots.items()):
            if len(candles_in_slot) < 1:
                continue

            aggregated = self._aggregate_candles(candles_in_slot, slot_time)

            # Check if this candle already exists (avoid re-writing)
            existing = self.store.get_candles_in_range(asset, target_tf, slot_time, slot_time + 1)
            if not existing:
                self.store.save_candle(asset, target_tf, aggregated)

            # Yield to event loop
            await asyncio.sleep(0)

    def _aggregate_candles(self, candles: List[Dict], slot_time: int) -> Dict:
        """Aggregate multiple candles into one OHLCV candle.

        Args:
            candles: List of candles to aggregate
            slot_time: Time of the aggregated candle

        Returns:
            Aggregated candle dict
        """
        if not candles:
            return {}

        opens = [c.get("open", 0) for c in candles if c.get("open")]
        highs = [c.get("high", 0) for c in candles if c.get("high")]
        lows = [c.get("low", 0) for c in candles if c.get("low")]
        closes = [c.get("close", 0) for c in candles if c.get("close")]
        volumes = [c.get("volume", 0) for c in candles]

        return {
            "time": slot_time,
            "open": opens[0] if opens else 0,
            "high": max(highs) if highs else 0,
            "low": min(lows) if lows else 0,
            "close": closes[-1] if closes else 0,
            "volume": sum(volumes),
        }


__all__ = ["BackgroundCandleAggregator"]

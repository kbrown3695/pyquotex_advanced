"""Aggregate candles across multiple timeframes.

Takes 1m candles and builds 5s, 10s, 15s, 30s, 4h candles stored in the database.
"""

from typing import List, Dict, Any, Optional
from ml.data.candle_store import CandleStore


class TimeframeAggregator:
    """Aggregate candles into multiple timeframes."""

    # Map timeframe string to seconds
    TIMEFRAME_SECONDS = {
        "5s": 5,
        "10s": 10,
        "15s": 15,
        "30s": 30,
        "1m": 60,
        "2m": 120,
        "3m": 180,
        "5m": 300,
        "10m": 600,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
    }

    def __init__(self, candle_store: CandleStore):
        """Initialize aggregator with candle store."""
        self.store = candle_store

    def aggregate_to_timeframes(
        self, asset: str, new_candle: Dict[str, Any], min_candles: int = 2
    ) -> None:
        """Aggregate 1m candle into multiple timeframes and store.

        Args:
            asset: Asset symbol
            new_candle: Candle dict with time, open, high, low, close, volume
            min_candles: Minimum candles needed to create an aggregated candle
        """
        candle_time = new_candle["time"]

        # Aggregate into 5s, 10s, 15s, 30s, 4h
        for target_tf in ["5s", "10s", "15s", "30s", "4h"]:
            target_seconds = self.TIMEFRAME_SECONDS[target_tf]
            candle_slot = (candle_time // target_seconds) * target_seconds

            # Get all 1m candles in this target timeframe slot
            candles_in_slot = self._get_candles_in_slot(
                asset, "1m", candle_slot, target_seconds
            )

            if len(candles_in_slot) >= min_candles:
                agg_candle = self._aggregate_candles(candles_in_slot, candle_slot)
                self.store.save_candle(asset, target_tf, agg_candle)

    def _get_candles_in_slot(
        self, asset: str, timeframe: str, slot_start: int, slot_duration: int
    ) -> List[Dict[str, Any]]:
        """Get all candles in a time slot from the database."""
        slot_end = slot_start + slot_duration
        return self.store.get_candles_in_range(
            asset, timeframe, slot_start, slot_end
        )

    def _aggregate_candles(
        self, candles: List[Dict[str, Any]], slot_time: int
    ) -> Dict[str, Any]:
        """Aggregate multiple candles into one OHLCV candle."""
        if not candles:
            return {}

        opens = [c["open"] for c in candles if c.get("open")]
        highs = [c["high"] for c in candles if c.get("high")]
        lows = [c["low"] for c in candles if c.get("low")]
        closes = [c["close"] for c in candles if c.get("close")]
        volumes = [c.get("volume", 0) for c in candles]

        return {
            "time": slot_time,
            "open": opens[0] if opens else 0,
            "high": max(highs) if highs else 0,
            "low": min(lows) if lows else 0,
            "close": closes[-1] if closes else 0,
            "volume": sum(volumes),
        }


__all__ = ["TimeframeAggregator"]

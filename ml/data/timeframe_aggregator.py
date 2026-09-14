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
        self, asset: str, new_candle: Dict[str, Any], min_candles: int = 1
    ) -> None:
        """Aggregate 1m candle into multiple timeframes and store.

        For sub-minute (5s/10s/15s/30s): Just copy the 1m candle into multiple slots
        For 4h: Aggregate from 1m candles that fall within the 4h period

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

            if target_tf == "4h":
                # For 4h: aggregate from all 1m candles in the 4h period
                candles_in_slot = self._get_candles_in_slot(
                    asset, "1m", candle_slot, target_seconds
                )
                if len(candles_in_slot) >= min_candles:
                    agg_candle = self._aggregate_candles(candles_in_slot, candle_slot)
                    self.store.save_candle(asset, target_tf, agg_candle)
            else:
                # For sub-minute (5s/10s/15s/30s): derive from the 1m candle
                # Split 1m into multiple sub-minute candles
                self._split_into_subminu_candles(asset, target_tf, new_candle)

    def _get_candles_in_slot(
        self, asset: str, timeframe: str, slot_start: int, slot_duration: int
    ) -> List[Dict[str, Any]]:
        """Get all candles in a time slot from the database."""
        slot_end = slot_start + slot_duration
        return self.store.get_candles_in_range(
            asset, timeframe, slot_start, slot_end
        )

    def _split_into_subminu_candles(
        self, asset: str, target_tf: str, source_candle: Dict[str, Any]
    ) -> None:
        """Split 1m candle into sub-minute candles (5s/10s/15s/30s).

        Since we don't have tick data, we approximate by creating multiple candles
        within the 1m period, all with the same OHLC values.
        This is acceptable for UI display; ML models train on 1m anyway.
        """
        source_time = source_candle["time"]
        target_seconds = self.TIMEFRAME_SECONDS[target_tf]

        # How many sub-minute candles fit in this 1m period?
        candles_per_minute = 60 // target_seconds

        # Create a candle for each slot within this 1m period
        for i in range(candles_per_minute):
            slot_time = source_time + (i * target_seconds)

            # Create aggregated candle with same OHLC as source
            agg_candle = {
                "time": slot_time,
                "open": source_candle.get("open", 0),
                "high": source_candle.get("high", 0),
                "low": source_candle.get("low", 0),
                "close": source_candle.get("close", 0),
                "volume": source_candle.get("volume", 0),
            }

            self.store.save_candle(asset, target_tf, agg_candle)

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

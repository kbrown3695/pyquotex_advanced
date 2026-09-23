#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase I: Data Accumulation Tracker
===================================
Tracks candle accumulation across assets to know when models can be trained.

Ensures minimum data requirements are met before enabling signal-based trading:
- 500+ candles per asset
- At least 2 hours of data collection
- Prevents training on insufficient data (which causes neutral 0.5 signals)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime, timedelta


@dataclass
class AssetAccumulationStatus:
    """Track data accumulation for a single asset."""
    asset: str
    timeframe: str
    candle_count: int = 0
    first_candle_time: Optional[float] = None
    last_candle_time: Optional[float] = None
    accumulated_duration_seconds: float = 0.0

    def update_with_candle(self, current_time: float) -> None:
        """Record that a candle was received for this asset."""
        self.candle_count += 1

        if self.first_candle_time is None:
            self.first_candle_time = current_time

        self.last_candle_time = current_time
        self.accumulated_duration_seconds = current_time - self.first_candle_time

    def time_remaining_minutes(self, target_duration_seconds: float) -> float:
        """Calculate remaining time needed to reach target duration."""
        remaining = target_duration_seconds - self.accumulated_duration_seconds
        return max(0, remaining / 60.0)

    def is_ready(self, min_candles: int, min_duration_seconds: float) -> bool:
        """Check if this asset has enough data for training."""
        has_enough_candles = self.candle_count >= min_candles
        has_enough_duration = self.accumulated_duration_seconds >= min_duration_seconds
        return has_enough_candles and has_enough_duration

    def get_progress_percent(self, min_candles: int, min_duration_seconds: float) -> float:
        """Get progress toward readiness (0-100%)."""
        candle_percent = min(100, (self.candle_count / min_candles) * 100)
        duration_percent = min(100, (self.accumulated_duration_seconds / min_duration_seconds) * 100)
        return (candle_percent + duration_percent) / 2.0


class DataAccumulationTracker:
    """
    Tracks data accumulation progress across all trading assets.

    Determines when the system has collected enough historical data
    to train models with meaningful signal.
    """

    def __init__(
        self,
        min_candles: int = 500,
        min_duration_seconds: float = 3600.0,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize tracker.

        Args:
            min_candles: Minimum candles needed per asset (default 500)
            min_duration_seconds: Minimum duration of data (default 1 hour)
            logger: Optional logger instance
        """
        self.min_candles = min_candles
        self.min_duration_seconds = min_duration_seconds
        self.logger = logger or logging.getLogger(__name__)

        # Track per asset+timeframe
        self.asset_status: Dict[str, AssetAccumulationStatus] = {}

        # Overall tracking
        self.accumulation_start_time = time.time()
        self.is_accumulation_complete = False
        self.assets_ready: set = set()

    def record_candle(self, asset: str, timeframe: str = "1m") -> None:
        """Record that a candle was received.

        Args:
            asset: Asset symbol (e.g., "AUD/CAD (OTC)")
            timeframe: Candle timeframe (default "1m")
        """
        key = f"{asset}_{timeframe}"

        if key not in self.asset_status:
            self.asset_status[key] = AssetAccumulationStatus(
                asset=asset,
                timeframe=timeframe
            )

        self.asset_status[key].update_with_candle(time.time())

        # Check if this asset is now ready
        status = self.asset_status[key]
        if status.is_ready(self.min_candles, self.min_duration_seconds):
            if key not in self.assets_ready:
                self.assets_ready.add(key)
                self.logger.info(
                    f"✅ {asset} ({timeframe}) ready: {status.candle_count} candles, "
                    f"{status.accumulated_duration_seconds/60:.1f} minutes"
                )

    def get_status(self) -> Dict:
        """Get detailed accumulation status.

        Returns:
            Dict with per-asset progress and overall status
        """
        total_assets = len(self.asset_status)
        ready_assets = len(self.assets_ready)

        assets_detail = {}
        for key, status in self.asset_status.items():
            progress = status.get_progress_percent(self.min_candles, self.min_duration_seconds)
            remaining_time = status.time_remaining_minutes(self.min_duration_seconds)

            assets_detail[key] = {
                "asset": status.asset,
                "timeframe": status.timeframe,
                "candle_count": status.candle_count,
                "accumulated_minutes": status.accumulated_duration_seconds / 60.0,
                "progress_percent": round(progress, 1),
                "is_ready": status.is_ready(self.min_candles, self.min_duration_seconds),
                "time_remaining_minutes": round(remaining_time, 1)
            }

        elapsed = time.time() - self.accumulation_start_time

        return {
            "is_accumulation_complete": self.is_accumulation_complete,
            "total_assets": total_assets,
            "ready_assets": ready_assets,
            "elapsed_minutes": round(elapsed / 60.0, 1),
            "min_candles_required": self.min_candles,
            "min_duration_minutes_required": self.min_duration_seconds / 60.0,
            "assets": assets_detail
        }

    def is_ready_for_trading(self, required_ready_percent: float = 80.0) -> bool:
        """Check if enough assets are ready for trading.

        Args:
            required_ready_percent: % of assets that must be ready (default 80%)

        Returns:
            True if ready for trading
        """
        if len(self.asset_status) == 0:
            return False

        ready_percent = (len(self.assets_ready) / len(self.asset_status)) * 100
        return ready_percent >= required_ready_percent

    def get_readiness_summary(self) -> str:
        """Get human-readable readiness summary.

        Returns:
            String like "4/5 assets ready (80%), waiting for GBP/USD"
        """
        if len(self.asset_status) == 0:
            return "No assets tracked yet"

        ready_count = len(self.assets_ready)
        total_count = len(self.asset_status)
        percent = (ready_count / total_count) * 100

        not_ready = [
            k.split("_")[0] for k in self.asset_status.keys()
            if k not in self.assets_ready
        ]

        summary = f"{ready_count}/{total_count} assets ready ({percent:.0f}%)"
        if not_ready and len(not_ready) <= 3:
            summary += f", waiting for {', '.join(not_ready)}"

        return summary

    def log_progress(self) -> None:
        """Log current progress to logger."""
        status = self.get_status()
        summary = self.get_readiness_summary()

        self.logger.info(f"📊 Data Accumulation: {summary}")

        # Log details for not-ready assets
        for key, asset_status in self.asset_status.items():
            if key not in self.assets_ready:
                progress = asset_status.get_progress_percent(
                    self.min_candles,
                    self.min_duration_seconds
                )
                remaining = asset_status.time_remaining_minutes(self.min_duration_seconds)
                self.logger.info(
                    f"   {asset_status.asset}: {asset_status.candle_count}/{self.min_candles} "
                    f"candles ({progress:.0f}%), ~{remaining:.0f} min remaining"
                )

    def mark_complete(self) -> None:
        """Mark accumulation phase as complete."""
        self.is_accumulation_complete = True
        elapsed = time.time() - self.accumulation_start_time
        self.logger.info(
            f"🎉 Data accumulation complete! ({len(self.assets_ready)} assets ready, "
            f"{elapsed/60:.1f} minutes elapsed)"
        )


__all__ = ["DataAccumulationTracker", "AssetAccumulationStatus"]

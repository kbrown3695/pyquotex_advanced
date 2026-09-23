#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Signal Callback Manager - Event-Driven Signal Generation
=========================================================

Manages callbacks for real-time signal generation when new candles arrive.
Replaces polling-based AsyncSignalManager with event-driven architecture.

Features:
- Register callbacks for candle events
- Notify subscribers immediately when new candle arrives
- Async signal generation without polling
- Clean separation of concerns
"""

import asyncio
import logging
from typing import Dict, Callable, Optional, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CandleEvent:
    """Event fired when a new candle completes."""
    asset: str
    timeframe: str
    candle: Dict
    timestamp: float


class SignalCallbackManager:
    """
    Manages event callbacks for real-time signal generation.

    Replaces polling-based signal generation with event-driven notifications.
    When a new candle arrives, this manager notifies all registered subscribers
    immediately, who then generate signals asynchronously.

    Responsibilities:
    1. Register callbacks for candle events
    2. Fire candle_event when new candle arrives
    3. Manage async signal generation subscribers
    4. Coordinate multiple subscribers efficiently
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize callback manager.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.callbacks: Dict[str, List[Callable]] = {}  # asset_timeframe -> [callbacks]
        self._lock = asyncio.Lock()

    def register_candle_callback(
        self,
        asset: str,
        timeframe: str,
        callback: Callable
    ) -> None:
        """Register a callback for new candles.

        Args:
            asset: Asset symbol (e.g., "EUR/USD (OTC)")
            timeframe: Timeframe (e.g., "1m")
            callback: Async callable that receives CandleEvent
        """
        key = f"{asset}_{timeframe}"
        if key not in self.callbacks:
            self.callbacks[key] = []
        self.callbacks[key].append(callback)
        self.logger.info(f"📌 Registered callback for {asset}/{timeframe}")

    def unregister_candle_callback(
        self,
        asset: str,
        timeframe: str,
        callback: Callable
    ) -> None:
        """Unregister a callback.

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            callback: Callback to remove
        """
        key = f"{asset}_{timeframe}"
        if key in self.callbacks and callback in self.callbacks[key]:
            self.callbacks[key].remove(callback)
            self.logger.info(f"🗑️ Unregistered callback for {asset}/{timeframe}")

    async def on_candle_completed(
        self,
        asset: str,
        timeframe: str,
        candle: Dict
    ) -> None:
        """Fire event when new candle completes.

        Called by update_candle() when a candle closes.
        Immediately notifies all subscribers.

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            candle: Completed candle dict
        """
        key = f"{asset}_{timeframe}"

        if key not in self.callbacks or not self.callbacks[key]:
            return

        event = CandleEvent(
            asset=asset,
            timeframe=timeframe,
            candle=candle,
            timestamp=candle.get("time", 0)
        )

        # Fire all callbacks concurrently
        tasks = []
        for callback in self.callbacks[key]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(asyncio.create_task(callback(event)))
                else:
                    # Sync callback - wrap in task
                    tasks.append(asyncio.create_task(self._run_sync_callback(callback, event)))
            except Exception as e:
                self.logger.error(f"Error registering callback for {asset}/{timeframe}: {e}")

        # Wait for all callbacks to complete
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                self.logger.error(f"Error executing callbacks for {asset}/{timeframe}: {e}")

    async def _run_sync_callback(self, callback: Callable, event: CandleEvent) -> None:
        """Run synchronous callback in async context.

        Args:
            callback: Sync callable
            event: CandleEvent to pass
        """
        try:
            callback(event)
        except Exception as e:
            self.logger.error(f"Sync callback error: {e}")

    def get_callbacks(self, asset: str, timeframe: str) -> List[Callable]:
        """Get registered callbacks for asset/timeframe.

        Args:
            asset: Asset symbol
            timeframe: Timeframe

        Returns:
            List of registered callbacks
        """
        key = f"{asset}_{timeframe}"
        return self.callbacks.get(key, [])

    def clear_all(self) -> None:
        """Clear all registered callbacks."""
        self.callbacks.clear()
        self.logger.info("🧹 All callbacks cleared")


# Global callback manager instance
SIGNAL_CALLBACK_MANAGER = SignalCallbackManager()


def get_signal_callback_manager() -> SignalCallbackManager:
    """Get global callback manager instance."""
    return SIGNAL_CALLBACK_MANAGER


__all__ = ["SignalCallbackManager", "CandleEvent", "get_signal_callback_manager"]

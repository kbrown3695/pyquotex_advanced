"""Async signal generation manager for multiple asset pairs.

Manages parallel signal generation threads, one per asset/timeframe combination.
Each thread generates signals every 10s and caches the latest result.
"""

import threading
import time
from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime

from ml.serving.signal_service import MLSignalService


@dataclass
class SignalCache:
    """Cached signal result."""

    signal: Optional[Dict[str, Any]]
    timestamp: float
    asset: str
    timeframe: str

    def is_stale(self, max_age_seconds: float = 30.0) -> bool:
        """Check if cached signal is older than max_age."""
        return time.time() - self.timestamp > max_age_seconds


class AsyncSignalManager:
    """Manages parallel signal generation for multiple assets.

    Starts one thread per asset/timeframe combination. Each thread generates
    signals every 10s and caches the latest result. Frontend can select an
    asset and poll its latest signal without blocking.

    Usage:
        manager = AsyncSignalManager()
        manager.add_asset("AUD/CAD (OTC)", "1m", candles_getter_func)
        signal = manager.get_signal("AUD/CAD (OTC)", "1m")
    """

    def __init__(self, ml_service: MLSignalService):
        """Initialize signal manager.

        Args:
            ml_service: MLSignalService instance for generating signals
        """
        self.ml_service = ml_service
        self.signal_cache: Dict[str, SignalCache] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.stop_signals: Dict[str, threading.Event] = {}
        self.candles_getters: Dict[str, Callable] = {}
        self._lock = threading.Lock()

    def add_asset(
        self,
        asset: str,
        timeframe: str,
        get_candles_fn: Callable[[], list],
        interval_seconds: float = 10.0,
    ) -> None:
        """Add asset to signal generation.

        Starts a background thread that generates signals every interval_seconds.

        Args:
            asset: Asset symbol (e.g. "AUD/CAD (OTC)")
            timeframe: Timeframe (e.g. "1m")
            get_candles_fn: Callable that returns current candles list
            interval_seconds: How often to generate signals (default 10s)
        """
        key = f"{asset}_{timeframe}"

        with self._lock:
            if key in self.threads and self.threads[key].is_alive():
                return  # Already running

            self.candles_getters[key] = get_candles_fn
            self.stop_signals[key] = threading.Event()

            # Start signal thread
            thread = threading.Thread(
                target=self._signal_loop,
                args=(asset, timeframe, get_candles_fn, interval_seconds),
                daemon=True,
                name=f"Signals-{asset}-{timeframe}",
            )
            thread.start()
            self.threads[key] = thread

    def _signal_loop(
        self,
        asset: str,
        timeframe: str,
        get_candles_fn: Callable[[], list],
        interval_seconds: float,
    ) -> None:
        """Background thread that generates signals at regular intervals.

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            get_candles_fn: Function to get current candles
            interval_seconds: Generation interval
        """
        key = f"{asset}_{timeframe}"
        stop_event = self.stop_signals[key]

        while not stop_event.is_set():
            try:
                candles = get_candles_fn()
                if candles and len(candles) >= 26:
                    signal = self.ml_service.generate_signal(asset, timeframe, candles)

                    if signal:
                        with self._lock:
                            self.signal_cache[key] = SignalCache(
                                signal=signal.to_dict(),
                                timestamp=time.time(),
                                asset=asset,
                                timeframe=timeframe,
                            )
            except Exception as e:
                # Silently continue on error
                pass

            # Sleep until next interval or stop signal
            stop_event.wait(timeout=interval_seconds)

    def get_signal(self, asset: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Get latest cached signal for an asset.

        Args:
            asset: Asset symbol
            timeframe: Timeframe

        Returns:
            Signal dict or None if not available
        """
        key = f"{asset}_{timeframe}"
        with self._lock:
            cache = self.signal_cache.get(key)
            if cache:
                return cache.signal
        return None

    def get_all_signals(self) -> Dict[str, Dict[str, Any]]:
        """Get all cached signals.

        Returns:
            Dict mapping "asset_timeframe" → signal_dict
        """
        with self._lock:
            return {
                key: cache.signal
                for key, cache in self.signal_cache.items()
                if cache.signal is not None
            }

    def get_signal_metadata(self, asset: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Get signal metadata (timestamp, age, etc).

        Args:
            asset: Asset symbol
            timeframe: Timeframe

        Returns:
            Metadata dict or None
        """
        key = f"{asset}_{timeframe}"
        with self._lock:
            cache = self.signal_cache.get(key)
            if cache:
                age = time.time() - cache.timestamp
                return {
                    "timestamp": cache.timestamp,
                    "age_seconds": age,
                    "is_fresh": age < 30,
                    "last_update": datetime.fromtimestamp(cache.timestamp).isoformat(),
                }
        return None

    def remove_asset(self, asset: str, timeframe: str) -> None:
        """Stop signal generation for an asset.

        Args:
            asset: Asset symbol
            timeframe: Timeframe
        """
        key = f"{asset}_{timeframe}"
        with self._lock:
            if key in self.stop_signals:
                self.stop_signals[key].set()
            if key in self.threads:
                self.threads[key].join(timeout=2.0)
            if key in self.signal_cache:
                del self.signal_cache[key]

    def stop_all(self) -> None:
        """Stop all signal generation threads."""
        with self._lock:
            for stop_event in self.stop_signals.values():
                stop_event.set()

        for thread in self.threads.values():
            thread.join(timeout=2.0)

        self.signal_cache.clear()
        self.threads.clear()
        self.stop_signals.clear()


__all__ = ["AsyncSignalManager", "SignalCache"]

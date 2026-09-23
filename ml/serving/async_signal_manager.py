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

        Registers callback for event-driven signal generation on new candles.
        Falls back to polling if callback system not available.

        Args:
            asset: Asset symbol (e.g. "AUD/CAD (OTC)")
            timeframe: Timeframe (e.g. "1m")
            get_candles_fn: Callable that returns current candles list
            interval_seconds: How often to generate signals (default 10s, ignored if callbacks used)
        """
        key = f"{asset}_{timeframe}"

        with self._lock:
            if key in self.threads and self.threads[key].is_alive():
                return  # Already running

            self.candles_getters[key] = get_candles_fn

            # Try to use callback-based (event-driven) signal generation
            try:
                from ml.serving.signal_callback_manager import get_signal_callback_manager
                callback_mgr = get_signal_callback_manager()

                # Create async callback for this asset
                async def on_new_candle(event):
                    await self._generate_signal_from_event(asset, timeframe, get_candles_fn)

                # Register the callback
                callback_mgr.register_candle_callback(asset, timeframe, on_new_candle)

                import sys
                print(f"[{asset} {timeframe}] ✅ Event-driven signal generation activated", file=sys.stderr)
                self.threads[key] = None  # Mark as registered (not a thread)

            except Exception as e:
                # Fall back to polling if callback system not available
                print(f"[{asset} {timeframe}] ⚠️ Callback system unavailable, falling back to polling: {e}", file=sys.stderr)
                self.stop_signals[key] = threading.Event()
                thread = threading.Thread(
                    target=self._signal_loop,
                    args=(asset, timeframe, get_candles_fn, interval_seconds),
                    daemon=True,
                    name=f"Signals-{asset}-{timeframe}",
                )
                thread.start()
                self.threads[key] = thread

    async def _generate_signal_from_event(
        self,
        asset: str,
        timeframe: str,
        get_candles_fn: Callable[[], list],
    ) -> None:
        """Generate signal immediately when new candle event arrives (event-driven).

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            get_candles_fn: Function to get current candles
        """
        key = f"{asset}_{timeframe}"
        try:
            candles = get_candles_fn()
            if not candles or len(candles) < 26:
                return

            # Generate signal async
            signal = self.ml_service.generate_signal(asset, timeframe, candles)
            if signal:
                with self._lock:
                    self.signal_cache[key] = SignalCache(
                        signal=signal.to_dict(),
                        timestamp=time.time(),
                        asset=asset,
                        timeframe=timeframe,
                    )
                import sys
                print(f"[{asset} {timeframe}] ✅ Signal generated (event-driven): {signal.side} @ {signal.confidence:.2f}", file=sys.stderr)
        except Exception as e:
            import sys
            import traceback
            print(f"[{asset} {timeframe}] Signal generation error: {type(e).__name__}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def _signal_loop(
        self,
        asset: str,
        timeframe: str,
        get_candles_fn: Callable[[], list],
        interval_seconds: float,
    ) -> None:
        """Background thread that generates signals at regular intervals (fallback polling).

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            get_candles_fn: Function to get current candles
            interval_seconds: Generation interval
        """
        key = f"{asset}_{timeframe}"
        stop_event = self.stop_signals[key]
        error_count = 0
        max_errors = 5
        iteration = 0

        # Log thread start
        import sys
        print(f"[{asset} {timeframe}] Signal thread started", file=sys.stderr)

        while not stop_event.is_set():
            iteration += 1
            try:
                candles = get_candles_fn()
                candle_count = len(candles) if candles else 0

                if not candles:
                    # Not ready yet - log every 5 iterations
                    if iteration % 5 == 0:
                        import sys
                        print(f"[{asset} {timeframe}] ⏳ No candles available (iteration {iteration})", file=sys.stderr)
                elif len(candles) < 26:
                    # Not enough candles yet - log every 5 iterations
                    if iteration % 5 == 0:
                        import sys
                        print(f"[{asset} {timeframe}] ⏳ Only {candle_count} candles (need 26, iteration {iteration})", file=sys.stderr)
                else:
                    # Try to generate signal
                    signal = self.ml_service.generate_signal(asset, timeframe, candles)
                    if signal:
                        with self._lock:
                            self.signal_cache[key] = SignalCache(
                                signal=signal.to_dict(),
                                timestamp=time.time(),
                                asset=asset,
                                timeframe=timeframe,
                            )
                        import sys
                        print(f"[{asset} {timeframe}] Signal cached: {signal.side} @ {signal.confidence:.2f}", file=sys.stderr)
                        error_count = 0  # Reset error count on success
                    else:
                        if iteration % 10 == 0:
                            import sys
                            print(f"[{asset} {timeframe}] ML returned None (models not trained)", file=sys.stderr)
            except Exception as e:
                error_count += 1
                import sys
                import traceback
                print(f"[{asset} {timeframe}] Signal error #{error_count}: {type(e).__name__}: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                if error_count > max_errors:
                    # Stop trying after too many errors
                    print(f"[{asset} {timeframe}] Too many errors, stopping signal generation", file=sys.stderr)
                    break

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
            if key in self.threads and self.threads[key] is not None:
                try:
                    self.threads[key].join(timeout=2.0)
                except Exception:
                    pass
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

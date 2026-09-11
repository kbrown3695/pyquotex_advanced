"""Feature pipeline for transforming raw data into ML features (11-feature QuotexChart edition)."""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from ml.features.feature_registry import FeatureRegistry
from ml.features.indicators import sma, ema, rsi, macd, atr, bollinger_percent_b


@dataclass
class MLDataset:
    """Container for ML dataset."""

    X: np.ndarray
    y: np.ndarray
    feature_names: List[str]


class FeaturePipeline:
    """Transform raw market data into ML features (11 dimensions, no volume)."""

    def __init__(self):
        self.feature_names = FeatureRegistry.names()  # 11 features, ordered

    def transform_live(
        self,
        snapshot: Dict[str, float],
        history: Optional[List[Dict[str, float]]] = None,
    ) -> Tuple[np.ndarray, Dict]:
        """Transform live snapshot into feature vector (11 dimensions).

        Args:
            snapshot: Current indicator snapshot with keys: close, high, low, sma_20, sma_50, ema_12, ema_26, rsi_14, macd_histogram, atr_14, bb_percent_b
            history: Historical snapshots for rolling features

        Returns:
            Tuple of (feature array shape (11,), metadata dict)
        """

        def _g(name: str) -> float:
            """Get value from snapshot, default to 0."""
            val = snapshot.get(name)
            try:
                return float(val) if val is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        def _h(hist: List[Dict], name: str, default: float = 0.0) -> List[float]:
            """Get list of values from history."""
            return [float(h.get(name, default)) for h in hist]

        sma20 = _g("sma_20")
        sma50 = _g("sma_50")
        ema12 = _g("ema_12")
        ema26 = _g("ema_26")
        close = _g("close") or 1.0
        high = _g("high") or close
        low = _g("low") or close

        # Calculate returns from history
        return_1 = 0.0
        return_3 = 0.0

        if history and len(history) >= 3:
            close_prices = _h(history, "close", 0.0)
            close_prices.append(close)

            if len(close_prices) >= 2:
                log_prices = np.log(np.maximum(close_prices, 1e-12))
                returns = np.diff(log_prices)
                return_1 = float(returns[-1]) if len(returns) > 0 else 0.0
                return_3 = float(np.sum(returns[-3:])) if len(returns) >= 3 else return_1

            return_1 = np.clip(return_1, -0.5, 0.5)
            return_3 = np.clip(return_3, -0.5, 0.5)

        # SMA slope
        sma_slope = 0.0
        if history and len(history) >= 20:
            sma20_history = _h(history, "sma_20", 0.0)
            if len(sma20_history) >= 20 and sma20_history[0] > 1e-12:
                sma_slope = (sma20 - sma20_history[0]) / max(sma20_history[0], 1e-12)
                sma_slope = np.clip(sma_slope, -0.5, 0.5)
        else:
            if sma50 > 1e-12:
                sma_slope = (sma20 - sma50) / max(sma50, 1e-12)

        # 11-feature vector (no volume_zscore)
        features = [
            return_1,
            return_3,
            np.clip(_g("rsi_14"), 0, 100),
            np.clip(_g("macd_histogram"), -10, 10),
            max(_g("atr_14"), 0),
            np.clip(_g("bb_percent_b"), -1, 2),
            sma_slope,
            np.clip(sma20 / max(sma50, 1e-12), 0.5, 2.0),
            np.clip(ema12 / max(close, 1e-12), 0.5, 2.0),
            np.clip(ema26 / max(close, 1e-12), 0.5, 2.0),
            np.clip((high - low) / max(close, 1e-12), 0, 0.1),
        ]

        # Sanitize NaN/Inf
        features = [0.0 if not np.isfinite(f) else f for f in features]

        metadata = {
            "history_used": len(history) if history else 0,
            "return_1": return_1,
            "return_3": return_3,
            "sma_slope": sma_slope,
            "features_valid": all(np.isfinite(f) for f in features),
        }

        return np.array(features, dtype=np.float64), metadata


def build_snapshots(candles: List[dict]) -> List[Dict[str, float]]:
    """Build indicator snapshots from candle history.

    Runs all indicator calculations once over the full candle list,
    returns one snapshot dict per candle.

    Args:
        candles: List of candle dicts with keys: time, open, high, low, close

    Returns:
        List of snapshot dicts, one per candle, each containing all indicators
    """
    closes = [c['close'] for c in candles]
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]

    # Run all indicator calculations once
    sma20_vals = sma(closes, 20)
    sma50_vals = sma(closes, 50)
    sma100_vals = sma(closes, 100)
    ema12_vals = ema(closes, 12)
    ema26_vals = ema(closes, 26)
    rsi14_vals = rsi(closes, 14)
    macd_line, macd_signal, macd_hist = macd(closes)
    atr14_vals = atr(candles, 14)
    bb_pb_vals = bollinger_percent_b(closes, 20)

    # Build snapshot for each candle
    snapshots = []
    for i in range(len(candles)):
        snapshot = {
            'close': closes[i],
            'high': highs[i],
            'low': lows[i],
            'sma_20': sma20_vals[i] or 0.0,
            'sma_50': sma50_vals[i] or 0.0,
            'sma_100': sma100_vals[i] or 0.0,
            'ema_12': ema12_vals[i] or 0.0,
            'ema_26': ema26_vals[i] or 0.0,
            'rsi_14': rsi14_vals[i] or 0.0,
            'macd_histogram': macd_hist[i] or 0.0,
            'atr_14': atr14_vals[i] or 0.0,
            'bb_percent_b': bb_pb_vals[i] or 0.0,
        }
        snapshots.append(snapshot)

    return snapshots


def build_training_matrix(
    candles: List[dict],
    lookahead: int = 1,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Build labeled feature matrix for training.

    Calls build_snapshots(), then transform_live() per row (same path as inference),
    labels with forward returns.

    Args:
        candles: List of candle dicts
        lookahead: Periods ahead to label (default 1 = next candle)

    Returns:
        Tuple of (X shape (n, 11), y shape (n,), feature_names)
    """
    snapshots = build_snapshots(candles)
    closes = [c['close'] for c in candles]

    X_list = []
    y_list = []

    # Build training data using same transform_live() path as inference
    pipeline = FeaturePipeline()

    for i in range(len(snapshots) - lookahead):
        # Use same inference path
        features, meta = pipeline.transform_live(
            snapshot=snapshots[i],
            history=snapshots[:i] if i > 0 else None
        )

        if not meta['features_valid']:
            continue

        X_list.append(features)

        # Label: 1 if next candle closed higher, 0 if lower
        if i + lookahead < len(closes):
            label = 1 if closes[i + lookahead] > closes[i] else 0
            y_list.append(label)

    X = np.array(X_list, dtype=np.float64)
    y = np.array(y_list, dtype=np.int64)

    return X, y, pipeline.feature_names

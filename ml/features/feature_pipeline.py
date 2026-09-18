"""Feature pipeline for transforming raw data into ML features (23-feature edition with binary options).

Phase 1.5: Integrated binary options features (12 new features) with existing 11 features.
All features trained together for optimal model performance.
"""

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
        self.feature_names = FeatureRegistry.names()  # 23 features (11 original + 12 BO)

    def transform_live(
        self,
        snapshot: Dict[str, float],
        history: Optional[List[Dict[str, float]]] = None,
    ) -> Tuple[np.ndarray, Dict]:
        """Transform live snapshot into feature vector (23 dimensions).

        Phase 1.5: Now includes 12 binary options features + 11 original features.

        Args:
            snapshot: Current indicator snapshot with keys: close, high, low, sma_20, sma_50, ema_12, ema_26, rsi_14, macd_histogram, atr_14, bb_percent_b,
                     + BO features: momentum_velocity, trend_age, time_to_reversal, reversal_prob, vol_percentile, vol_trend, price_velocity, acceleration, support, resistance, vol_high, trend_strength
            history: Historical snapshots for rolling features

        Returns:
            Tuple of (feature array shape (23,), metadata dict)
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

        # Original 11-feature vector
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

        # Phase 1.5: Add 12 binary options features
        # These features help models understand timing and reversal risk
        bo_features = self._extract_bo_features(snapshot, history, close, high, low, sma20)
        features.extend(bo_features)

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

    def _extract_bo_features(
        self,
        snapshot: Dict[str, float],
        history: Optional[List[Dict[str, float]]],
        close: float,
        high: float,
        low: float,
        sma20: float,
    ) -> List[float]:
        """Extract 12 binary options features from snapshot and history.

        Features:
        1. momentum_velocity - How fast momentum is changing
        2. trend_age_seconds - How long trend has been active
        3. time_to_reversal_seconds - Predicted reversal time
        4. reversal_probability - Confidence in reversal
        5. volatility_percentile - Vol rank (0-100)
        6. volatility_trend - Vol increasing/decreasing
        7. price_velocity - Pips per minute
        8. acceleration - Momentum accelerating
        9. support_level - Support price
        10. resistance_level - Resistance price
        11. volatility_high_flag - Is volatility high?
        12. trend_strength - How strong is trend?
        """
        if not history or len(history) < 20:
            return [0.0] * 12

        closes = np.array([h.get('close', close) for h in history])
        closes = np.append(closes, close)

        highs = np.array([h.get('high', high) for h in history])
        highs = np.append(highs, high)

        lows = np.array([h.get('low', low) for h in history])
        lows = np.append(lows, low)

        bo_features = []

        # 1. Momentum velocity
        if len(closes) >= 40:
            roc1 = (closes[-21] - closes[-40]) / 20
            roc2 = (closes[-1] - closes[-20]) / 20
            momentum_vel = (roc2 - roc1) / 20
            momentum_vel = np.clip(momentum_vel, -0.1, 0.1)
        else:
            momentum_vel = 0.0
        bo_features.append(momentum_vel)

        # 2. Trend age (estimate in units of 60s per candle)
        if len(closes) >= 20:
            returns = np.diff(np.log(np.maximum(closes, 1e-12)))
            trend_up = np.mean(returns[-20:]) > 0
            for i in range(len(closes) - 2, 0, -1):
                rev = closes[i] - closes[max(0, i-20)]
                is_up = rev > 0
                if is_up != trend_up:
                    trend_age = (len(closes) - i - 1) * 60
                    break
            else:
                trend_age = len(closes) * 60
        else:
            trend_age = 0.0
        bo_features.append(float(min(trend_age, 12000)))  # Cap at 200 minutes

        # 3. Time to reversal (simplified: 300s default, adjusted by RSI)
        rsi = _g_from_snapshot(snapshot, "rsi_14", 50.0)
        if rsi > 70 or rsi < 30:
            time_to_reversal = 240.0
        else:
            time_to_reversal = 600.0
        bo_features.append(time_to_reversal)

        # 4. Reversal probability (based on RSI and trend age)
        if rsi > 70:
            rev_prob = 0.5
        elif rsi < 30:
            rev_prob = 0.5
        else:
            rev_prob = 0.25
        bo_features.append(rev_prob)

        # 5. Volatility percentile
        returns = np.diff(np.log(np.maximum(closes, 1e-12)))
        recent_vol = np.std(returns[-10:]) if len(returns) >= 10 else 0.0
        rolling_vols = [np.std(returns[max(0, i-20):i+1]) for i in range(20, len(returns))]
        if rolling_vols and max(rolling_vols) > 1e-10:
            vol_percentile = (sum(1 for v in rolling_vols if v <= recent_vol) / len(rolling_vols)) * 100
        else:
            vol_percentile = 5.0 if recent_vol < 1e-10 else 50.0
        bo_features.append(float(np.clip(vol_percentile, 0, 100)))

        # 6. Volatility trend
        if len(returns) >= 20:
            old_vol = np.std(returns[-20:-10])
            vol_diff = recent_vol - old_vol
            if abs(vol_diff) < 1e-10:
                vol_trend = 0.0
            else:
                vol_trend = 1.0 if vol_diff > 0 else -1.0
                vol_trend *= min(abs(vol_diff) / max(old_vol, 1e-6), 1.0)
        else:
            vol_trend = 0.0
        bo_features.append(float(np.clip(vol_trend, -1, 1)))

        # 7. Price velocity (pips per minute)
        if len(closes) >= 5:
            movement = abs(closes[-1] - closes[-5])
            price_vel = movement / 5
        else:
            price_vel = 0.0
        bo_features.append(float(np.clip(price_vel, 0, 1.0)))

        # 8. Acceleration
        if len(closes) >= 15:
            mom_recent = closes[-1] - closes[-6]
            mom_prior = closes[-6] - closes[-11]
            mom_prev = closes[-11] - closes[-16] if len(closes) >= 16 else mom_prior
            accel_recent = mom_recent - mom_prior
            accel_older = mom_prior - mom_prev
            min_threshold = max(abs(mom_recent), abs(mom_prior)) * 1e-8 or 1e-12
            if accel_recent > accel_older + min_threshold:
                acceleration = 1.0
            elif accel_recent < accel_older - min_threshold:
                acceleration = -1.0
            else:
                acceleration = 0.0
        else:
            acceleration = 0.0
        bo_features.append(acceleration)

        # 9. Support level
        current_price = (lows[-1] + highs[-1]) / 2
        swing_lows = []
        lookback = min(50, len(lows) - 2)
        for i in range(2, lookback):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                swing_lows.append(lows[i])
        valid_supports = [s for s in swing_lows if s < current_price]
        if valid_supports:
            support = float(max(valid_supports))
        else:
            support = float(np.min(lows[-min(50, len(lows)):]))
        bo_features.append(support)

        # 10. Resistance level
        swing_highs = []
        lookback = min(50, len(highs) - 2)
        for i in range(2, lookback):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                swing_highs.append(highs[i])
        valid_resistances = [r for r in swing_highs if r > current_price]
        if valid_resistances:
            resistance = float(min(valid_resistances))
        else:
            resistance = float(np.max(highs[-min(50, len(highs)):]))
        bo_features.append(resistance)

        # 11. Volatility high flag (boolean as float)
        vol_high = 1.0 if vol_percentile > 65 else 0.0
        bo_features.append(vol_high)

        # 12. Trend strength (RSI-based)
        rsi_val = _g_from_snapshot(snapshot, "rsi_14", 50.0)
        trend_strength = abs(rsi_val - 50.0) / 50.0  # 0 to 1
        bo_features.append(float(np.clip(trend_strength, 0, 1)))

        return bo_features


def _g_from_snapshot(snapshot: Dict[str, float], name: str, default: float = 0.0) -> float:
    """Helper to get value from snapshot."""
    val = snapshot.get(name, default)
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def build_snapshots(candles: List[dict]) -> List[Dict[str, float]]:
    """Build indicator snapshots from candle history (with BO features).

    Runs all indicator calculations once over the full candle list,
    returns one snapshot dict per candle (now includes 12 BO features).

    Args:
        candles: List of candle dicts with keys: time, open, high, low, close

    Returns:
        List of snapshot dicts, one per candle, each containing all indicators + BO features
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
    pipeline = FeaturePipeline()

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

        # Phase 1.5: Add BO features using history
        history_for_bo = snapshots[max(0, i-50):i] if i > 0 else []
        bo_feats = pipeline._extract_bo_features(
            snapshot,
            history_for_bo,
            closes[i],
            highs[i],
            lows[i],
            sma20_vals[i] or closes[i]
        )

        # Add BO features to snapshot
        snapshot['momentum_velocity'] = bo_feats[0]
        snapshot['trend_age_seconds'] = bo_feats[1]
        snapshot['time_to_reversal_seconds'] = bo_feats[2]
        snapshot['reversal_probability'] = bo_feats[3]
        snapshot['volatility_percentile'] = bo_feats[4]
        snapshot['volatility_trend'] = bo_feats[5]
        snapshot['price_velocity'] = bo_feats[6]
        snapshot['acceleration'] = bo_feats[7]
        snapshot['support_level'] = bo_feats[8]
        snapshot['resistance_level'] = bo_feats[9]
        snapshot['volatility_high_flag'] = bo_feats[10]
        snapshot['trend_strength'] = bo_feats[11]

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


def build_sequences(
    X: np.ndarray,
    y: np.ndarray,
    seq_len: int = 26,
) -> Tuple[np.ndarray, np.ndarray]:
    """Build sequences from flat feature matrix for RNN/Transformer models.

    Converts (n_samples, n_features) into (n_sequences, seq_len, n_features)
    using a sliding window approach.

    Args:
        X: Feature matrix shape (n_samples, n_features)
        y: Target labels shape (n_samples,)
        seq_len: Length of sequences to build (default 26)

    Returns:
        Tuple of (X_seq shape (n_sequences, seq_len, n_features), y_seq shape (n_sequences,))
    """
    if len(X) < seq_len:
        # Not enough data for even one sequence
        return np.array([]).reshape(0, seq_len, X.shape[1]), np.array([], dtype=y.dtype)

    X_seq = []
    y_seq = []

    # Build sliding window sequences
    for i in range(len(X) - seq_len + 1):
        seq = X[i : i + seq_len]
        # Use the label of the last sample in the sequence
        label = y[i + seq_len - 1]

        X_seq.append(seq)
        y_seq.append(label)

    return np.array(X_seq, dtype=np.float64), np.array(y_seq, dtype=y.dtype)

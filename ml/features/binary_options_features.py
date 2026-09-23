"""Binary Options Feature Engineering.

Extracts features optimized for binary options trading:
- Momentum velocity (how fast is trend moving?)
- Time-to-reversal prediction (when will trend flip?)
- Expiration-time optimization (which expiration times are safe?)
- Volatility percentile (is volatility high/low/normal?)
- Support/resistance detection (key levels nearby?)
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
from dataclasses import dataclass


@dataclass
class BinaryOptionsFeatures:
    """Binary options features extracted from candle history."""

    momentum_velocity: float  # pips per second
    trend_age_seconds: int  # how long has trend been active?
    time_to_reversal_seconds: int  # when will trend flip?
    reversal_probability: float  # confidence in reversal prediction (0-1)

    volatility_percentile: float  # where is vol vs historical (0-100)
    volatility_trend: float  # is vol increasing/decreasing (-1 to +1)

    price_velocity: float  # pips per minute
    acceleration: float  # is momentum accelerating or decelerating

    support_level: float  # nearest support price
    resistance_level: float  # nearest resistance price

    safe_for_1m: bool  # safe to trade 1-minute expiration?
    safe_for_2m: bool  # safe to trade 2-minute expiration?
    safe_for_5m: bool  # safe to trade 5-minute expiration?
    safe_for_15m: bool  # safe to trade 15-minute expiration?

    time_of_day_weight: float  # strength of signal based on time of day (-1 to +1)


class BinaryOptionsFeatureEngineer:
    """Extract binary options features from price history."""

    def __init__(self, lookback_periods: int = 200):
        """Initialize feature engineer.

        Args:
            lookback_periods: How many candles to analyze (default 200)
        """
        self.lookback_periods = lookback_periods

    def extract(self, candles: List[Dict]) -> BinaryOptionsFeatures:
        """Extract binary options features from candle history.

        Args:
            candles: List of candle dicts with: time, open, high, low, close

        Returns:
            BinaryOptionsFeatures object with all metrics
        """
        if len(candles) < 20:
            raise ValueError(f"Need at least 20 candles, got {len(candles)}")

        # Work with recent candles (most relevant for reversal prediction)
        recent = candles[-self.lookback_periods:]
        closes = np.array([c['close'] for c in recent])
        highs = np.array([c['high'] for c in recent])
        lows = np.array([c['low'] for c in recent])

        # Extract features
        momentum_vel = self._momentum_velocity(closes)
        trend_age = self._trend_age_seconds(closes)
        time_to_reversal, reversal_prob = self._predict_reversal(closes)

        vol_percentile, vol_trend = self._volatility_features(closes)

        price_vel = self._price_velocity(closes)
        accel = self._acceleration(closes)

        support, resistance = self._support_resistance(lows, highs)

        safe_1m, safe_2m, safe_5m, safe_15m = self._expiration_safety(time_to_reversal)

        time_weight = self._time_of_day_weight(recent[-1].get('time'))

        return BinaryOptionsFeatures(
            momentum_velocity=momentum_vel,
            trend_age_seconds=trend_age,
            time_to_reversal_seconds=time_to_reversal,
            reversal_probability=reversal_prob,
            volatility_percentile=vol_percentile,
            volatility_trend=vol_trend,
            price_velocity=price_vel,
            acceleration=accel,
            support_level=support,
            resistance_level=resistance,
            safe_for_1m=safe_1m,
            safe_for_2m=safe_2m,
            safe_for_5m=safe_5m,
            safe_for_15m=safe_15m,
            time_of_day_weight=time_weight,
        )

    def _momentum_velocity(self, closes: np.ndarray) -> float:
        """Calculate how fast momentum is changing (pips per second).

        Higher = trend is accelerating
        Lower = trend is decelerating
        """
        if len(closes) < 40:
            return 0.0

        # Compare momentum over two periods to measure acceleration
        # Period 1 (old): average rate of change over candles -40 to -20
        period1_start = closes[-40]
        period1_end = closes[-21]
        roc1 = (period1_end - period1_start) / 20

        # Period 2 (new): average rate of change over candles -20 to -1
        period2_start = closes[-20]
        period2_end = closes[-1]
        roc2 = (period2_end - period2_start) / 20

        # Velocity = how much momentum changed between periods
        velocity = (roc2 - roc1) / 20  # Normalize by period

        return float(np.clip(velocity, -0.1, 0.1))

    def _trend_age_seconds(self, closes: np.ndarray) -> int:
        """How many seconds has current trend been active?

        Used to determine if trend is mature (likely to reverse soon)
        or young (likely to continue).
        """
        if len(closes) < 20:
            return 0

        # Determine current trend direction (up or down)
        current_return = closes[-1] - closes[-20]
        is_uptrend = current_return > 0

        # Look backwards to find trend change
        # Scan from recent to past, looking for last reversal
        for i in range(len(closes) - 2, 0, -1):
            lookback = closes[i] - closes[max(0, i - 20)]
            is_up = lookback > 0

            # If direction changed, we found the reversal point
            if is_up != is_uptrend:
                # Calculate age from reversal point
                candles_since_reversal = len(closes) - i - 1
                seconds_ago = candles_since_reversal * 60  # Assume 1 candle ≈ 60 seconds
                return int(seconds_ago)

        # No reversal found in history, trend is very old
        return len(closes) * 60

    def _predict_reversal(self, closes: np.ndarray) -> Tuple[int, float]:
        """Predict when trend will reverse and confidence.

        Returns:
            (time_to_reversal_seconds, reversal_probability)
        """
        if len(closes) < 30:
            return 300, 0.3

        # Get recent price action
        recent_20 = closes[-20:]
        recent_50 = closes[-50:]

        # Calculate RSI (simplified: 14-period)
        rsi = self._calc_rsi(closes[-14:] if len(closes) >= 14 else closes)

        # Calculate momentum (rate of change over last 5 candles)
        momentum = closes[-1] - closes[-5]
        momentum_trend = closes[-5] - closes[-10] if len(closes) >= 10 else momentum

        # Signals indicating reversal likelihood
        reversal_signals = 0
        total_signals = 0
        time_predictions = []

        # Signal 1: RSI extremes (overbought > 70 or oversold < 30)
        total_signals += 1
        if rsi > 70:  # Overbought = reversal likely
            reversal_signals += 1
            time_predictions.append(240)  # Expect reversal in ~4 minutes
        elif rsi < 30:  # Oversold = reversal likely
            reversal_signals += 1
            time_predictions.append(240)
        else:
            time_predictions.append(600)  # Normal RSI = trend will continue longer

        # Signal 2: Momentum divergence (momentum slowing despite price moving)
        total_signals += 1
        if abs(momentum_trend) < abs(momentum) * 0.5:  # Momentum slowing
            reversal_signals += 1
            time_predictions.append(180)  # Reversal soon
        else:
            time_predictions.append(600)

        # Signal 3: Mean reversion (price far from 20-SMA)
        sma20 = np.mean(recent_20)
        distance_from_sma = abs(closes[-1] - sma20) / max(sma20, 1e-6)
        total_signals += 1
        if distance_from_sma > 0.01:  # Price > 1% from SMA
            reversal_signals += 1
            time_predictions.append(300)  # Pull back to SMA coming
        else:
            time_predictions.append(600)

        # Signal 4: Trend age (older trends more likely to reverse)
        trend_age = self._trend_age_seconds(closes)
        total_signals += 1
        if trend_age > 900:  # Trend > 15 minutes old
            reversal_signals += 1
            time_predictions.append(120)  # Very old trend = quick reversal
        elif trend_age > 600:  # Trend 10-15 minutes old
            reversal_signals += 0.5
            time_predictions.append(240)
        else:
            time_predictions.append(600)

        # Calculate probability (how many signals agree)
        probability = reversal_signals / total_signals

        # Average time predictions (weighted by confidence)
        avg_time = int(np.mean(time_predictions))

        # Add some randomness to avoid overfitting
        avg_time = int(avg_time * np.random.uniform(0.8, 1.2))

        return max(60, min(900, avg_time)), float(np.clip(probability, 0.1, 0.9))

    def _volatility_features(self, closes: np.ndarray) -> Tuple[float, float]:
        """Calculate volatility metrics.

        Returns:
            (volatility_percentile, volatility_trend)
            - percentile: 0-100, where vol ranks historically
            - trend: -1 to +1, whether vol is increasing/decreasing
        """
        if len(closes) < 50:
            return 50.0, 0.0

        # Calculate volatility as standard deviation of returns
        returns = np.diff(np.log(np.maximum(closes, 1e-6)))

        # Recent volatility (last 10 candles)
        recent_vol = np.std(returns[-10:])

        # Historical volatility (all 50 candles)
        historical_vol = np.std(returns)

        # Volatility percentile: where does recent vol rank historically?
        # Calculate rolling volatility over all periods
        rolling_vols = []
        for i in range(20, len(returns)):
            window_vol = np.std(returns[max(0, i-20):i+1])
            rolling_vols.append(window_vol)

        if rolling_vols:
            # Rank current volatility
            # Handle edge case: if all rolling vols are near zero (stable prices)
            max_rolling_vol = max(rolling_vols) if rolling_vols else 0

            if max_rolling_vol < 1e-10:
                # Very stable prices - low percentile
                vol_percentile = 5.0 if recent_vol < 1e-10 else 15.0
            else:
                vol_percentile = (sum(1 for v in rolling_vols if v <= recent_vol) / len(rolling_vols)) * 100
        else:
            vol_percentile = 50.0

        # Volatility trend: is vol increasing or decreasing?
        # Compare recent vol to vol from 10 periods ago
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

        return float(np.clip(vol_percentile, 0, 100)), float(np.clip(vol_trend, -1, 1))

    def _price_velocity(self, closes: np.ndarray) -> float:
        """Pips per minute of price movement."""
        if len(closes) < 5:
            return 0.0

        # Average movement over last 5 candles (~5 minutes)
        movement = abs(closes[-1] - closes[-5])
        velocity = movement / 5  # pips per minute (assuming 1 candle = 1 minute)

        return float(np.clip(velocity, 0, 1.0))

    def _acceleration(self, closes: np.ndarray) -> float:
        """Is momentum accelerating (+1) or decelerating (-1)?"""
        if len(closes) < 15:
            return 0.0

        # Compare momentum over 3 overlapping 5-candle periods
        # to determine if momentum is increasing or decreasing
        mom_period1 = closes[-1] - closes[-6]      # Most recent
        mom_period2 = closes[-6] - closes[-11]     # Middle
        mom_period3 = closes[-11] - closes[-16] if len(closes) >= 16 else mom_period2  # Oldest

        # Calculate acceleration: is momentum increasing?
        accel_recent = mom_period1 - mom_period2
        accel_older = mom_period2 - mom_period3

        # Account for floating point precision
        min_threshold = max(abs(mom_period1), abs(mom_period2)) * 1e-8 or 1e-12

        if accel_recent > accel_older + min_threshold:
            return 1.0
        elif accel_recent < accel_older - min_threshold:
            return -1.0
        else:
            return 0.0

    def _support_resistance(self, lows: np.ndarray, highs: np.ndarray) -> Tuple[float, float]:
        """Find nearest support and resistance levels.

        Returns:
            (support_price, resistance_price)
        """
        if len(lows) < 10:
            return float(np.min(lows)), float(np.max(highs))

        # Find swing lows (local minima) and swing highs (local maxima)
        # Using 5-candle window for detection
        current_price = (lows[-1] + highs[-1]) / 2

        swing_lows = []
        swing_highs = []

        # Scan for swings in last 50 candles
        lookback = min(50, len(lows))
        for i in range(2, lookback - 2):
            idx = -lookback + i

            # Swing low: low[i] is lower than neighbors
            if lows[idx] < lows[idx-1] and lows[idx] < lows[idx+1]:
                swing_lows.append(lows[idx])

            # Swing high: high[i] is higher than neighbors
            if highs[idx] > highs[idx-1] and highs[idx] > highs[idx+1]:
                swing_highs.append(highs[idx])

        # Find nearest support (highest low below current price)
        valid_supports = [s for s in swing_lows if s < current_price]
        if valid_supports:
            support = max(valid_supports)
        else:
            support = np.min(lows[-lookback:])

        # Find nearest resistance (lowest high above current price)
        valid_resistances = [r for r in swing_highs if r > current_price]
        if valid_resistances:
            resistance = min(valid_resistances)
        else:
            resistance = np.max(highs[-lookback:])

        return float(support), float(resistance)

    def _calc_rsi(self, closes: np.ndarray, period: int = 14) -> float:
        """Calculate RSI (Relative Strength Index).

        Returns value 0-100. RSI > 70 = overbought, RSI < 30 = oversold.
        """
        if len(closes) < 2:
            return 50.0

        # Calculate price changes
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Average gains and losses
        avg_gain = np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0

        # Calculate RS and RSI
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(np.clip(rsi, 0, 100))

    def _expiration_safety(self, time_to_reversal: int) -> Tuple[bool, bool, bool, bool]:
        """Determine if safe to trade each expiration time.

        Safety rule: time_to_reversal should be > expiration_time + buffer
        """
        # Need at least 30 seconds buffer for entry latency
        safe_1m = time_to_reversal > 90    # 60s + 30s buffer
        safe_2m = time_to_reversal > 150   # 120s + 30s buffer
        safe_5m = time_to_reversal > 330   # 300s + 30s buffer
        safe_15m = time_to_reversal > 930  # 900s + 30s buffer

        return safe_1m, safe_2m, safe_5m, safe_15m

    def _time_of_day_weight(self, candle_time: Optional[float]) -> float:
        """Weight signal based on time of day.

        Some times of day have better signal quality than others
        (e.g., London/NY session overlap often has better trends).

        Returns:
            -1 to +1 multiplier for signal confidence
        """
        if candle_time is None:
            return 0.0

        # Assume timestamp is Unix time (seconds since epoch)
        from datetime import datetime, timezone
        try:
            dt = datetime.fromtimestamp(candle_time, timezone.utc)
            hour_utc = dt.hour
        except (ValueError, OSError):
            # Invalid timestamp, neutral weight
            return 0.0

        # Forex trading sessions (UTC):
        # Tokyo:    22:00-06:00 (Asian)
        # London:   08:00-17:00 (European)
        # NY:       13:00-22:00 (American)
        # Overlap:  13:00-17:00 (London/NY) - best liquidity and trends

        if 13 <= hour_utc < 17:
            # London/NY overlap: strongest trends
            return 0.3
        elif 8 <= hour_utc < 13 or 17 <= hour_utc < 22:
            # London or NY session: good activity
            return 0.15
        elif 22 <= hour_utc or hour_utc < 6:
            # Tokyo session: lower volume
            return -0.15
        else:
            # Dead hours (6-8am UTC): very quiet
            return -0.3


# For backwards compatibility, export main functionality
__all__ = [
    'BinaryOptionsFeatures',
    'BinaryOptionsFeatureEngineer',
]

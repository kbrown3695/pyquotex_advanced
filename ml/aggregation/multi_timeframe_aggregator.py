"""Phase G4: Multi-Timeframe Signal Aggregation

Generates signals on 1m, 5m, and 15m timeframes independently, then aggregates
them to confirm trends and filter false signals.

Benefits:
- Filters noise on 1m by requiring 5m/15m confirmation
- Uses longer timeframes to identify true trends
- Combines entry timing (1m) with trend confirmation (5m/15m)
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from ml.aggregation.signal_aggregator import SignalResult, MultiModelAggregator
from ml.data.timeframe_aggregator import TimeframeAggregator


class MultiTimeframeAggregator:
    """Aggregate signals across multiple timeframes (1m, 5m, 15m).

    Core idea:
    1. Generate signals independently on each timeframe
    2. Require alignment for high-confidence trades
    3. Use longer timeframes to filter false signals
    4. Shorter timeframes for entry timing

    Signal Alignment Scoring:
    - 3/3 aligned (all same side): 100% agreement → +33% confidence
    - 2/3 aligned (2 agree): 67% agreement → +10% confidence
    - 1/3 aligned (all different): 33% agreement → -50% confidence
    """

    def __init__(
        self,
        signal_aggregator: MultiModelAggregator,
        timeframe_aggregator: TimeframeAggregator,
    ):
        """Initialize multi-timeframe aggregator.

        Args:
            signal_aggregator: MultiModelAggregator for Phase F weights
            timeframe_aggregator: TimeframeAggregator for candle aggregation
        """
        self.aggregator = signal_aggregator
        self.tf_aggregator = timeframe_aggregator
        self.candle_cache = {}  # Cache aggregated candles

    def aggregate(
        self,
        asset: str,
        model_outputs_1m: Dict[str, Any],
        kalman_regime: Optional[Tuple] = None,
    ) -> SignalResult:
        """Generate multi-timeframe signal.

        Args:
            asset: Asset symbol
            model_outputs_1m: Model predictions from 1m timeframe
            kalman_regime: Optional regime information (1m-based)

        Returns:
            Aggregated SignalResult with multi-timeframe metadata
        """
        # Get candles for all timeframes
        candles_1m = self.tf_aggregator.store.get_candles(asset, "1m", 100)
        candles_5m = self._get_aggregated_candles(asset, candles_1m, "5m")
        candles_15m = self._get_aggregated_candles(asset, candles_1m, "15m")

        # Generate signals on each timeframe
        signal_1m = self.aggregator.aggregate(**model_outputs_1m, kalman_regime=kalman_regime)
        signal_5m = self._generate_signal(asset, candles_5m, "5m", kalman_regime)
        signal_15m = self._generate_signal(asset, candles_15m, "15m", kalman_regime)

        # Aggregate across timeframes
        return self._combine_timeframes(signal_1m, signal_5m, signal_15m)

    def _get_aggregated_candles(
        self,
        asset: str,
        candles_1m: List[Dict[str, Any]],
        target_tf: str,
    ) -> List[Dict[str, Any]]:
        """Aggregate 1m candles to target timeframe.

        Args:
            asset: Asset symbol
            candles_1m: List of 1m candles
            target_tf: Target timeframe ("5m", "15m", etc)

        Returns:
            List of aggregated candles
        """
        if not candles_1m:
            return []

        timeframe_seconds = {"5m": 300, "15m": 900}
        target_seconds = timeframe_seconds.get(target_tf, 300)

        aggregated = []
        current_slot = None
        current_candle = None

        for candle in candles_1m:
            slot = (candle["time"] // target_seconds) * target_seconds

            if slot != current_slot:
                # New slot, save previous candle
                if current_candle:
                    aggregated.append(current_candle)

                # Start new candle
                current_slot = slot
                current_candle = {
                    "time": slot,
                    "open": candle["open"],
                    "high": candle["high"],
                    "low": candle["low"],
                    "close": candle["close"],
                    "volume": candle.get("volume", 0),
                }
            else:
                # Same slot, update OHLC
                current_candle["high"] = max(current_candle["high"], candle["high"])
                current_candle["low"] = min(current_candle["low"], candle["low"])
                current_candle["close"] = candle["close"]
                current_candle["volume"] = current_candle.get("volume", 0) + candle.get("volume", 0)

        # Don't forget last candle
        if current_candle:
            aggregated.append(current_candle)

        return aggregated

    def _generate_signal(
        self,
        asset: str,
        candles: List[Dict[str, Any]],
        timeframe: str,
        kalman_regime: Optional[Tuple] = None,
    ) -> SignalResult:
        """Generate signal from aggregated candles (reuse Phase F model outputs).

        Note: This is simplified - in production, would re-run all models on
        aggregated candles. For now, we use 1m model outputs with timeframe label.

        Args:
            asset: Asset symbol
            candles: Aggregated candles
            timeframe: Timeframe label ("5m", "15m")
            kalman_regime: Optional regime

        Returns:
            SignalResult for this timeframe
        """
        if not candles:
            return SignalResult(
                side="NEUTRAL",
                confidence=0.0,
                reason=f"No {timeframe} candles available",
                method="multi_timeframe_error",
            )

        # Simplified approach: use last 3 candles to determine trend
        recent = candles[-3:]

        # Simple trend: if last close > first open, uptrend
        trend_up = recent[-1]["close"] > recent[0]["open"]

        # Compute momentum score
        closes = [c["close"] for c in recent]
        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]

        # Momentum: recent close relative to recent range
        recent_high = max(highs)
        recent_low = min(lows)
        recent_range = recent_high - recent_low

        if recent_range > 0:
            momentum = (closes[-1] - recent_low) / recent_range
        else:
            momentum = 0.5

        # Signal based on trend and momentum
        if trend_up and momentum > 0.5:
            side = "BUY"
            confidence = 0.5 + momentum * 0.3  # 0.5-0.8 range
        elif not trend_up and momentum < 0.5:
            side = "SELL"
            confidence = 0.5 + (1.0 - momentum) * 0.3
        else:
            side = "NEUTRAL"
            confidence = 0.4

        return SignalResult(
            side=side,
            confidence=confidence,
            reason=f"{timeframe}: {'uptrend' if trend_up else 'downtrend'} (momentum {momentum:.0%})",
            method="multi_timeframe_trend",
        )

    def _combine_timeframes(
        self,
        signal_1m: SignalResult,
        signal_5m: SignalResult,
        signal_15m: SignalResult,
    ) -> SignalResult:
        """Combine signals from 3 timeframes via alignment scoring.

        Args:
            signal_1m: Signal from 1m timeframe
            signal_5m: Signal from 5m timeframe
            signal_15m: Signal from 15m timeframe

        Returns:
            Aggregated SignalResult
        """
        # Count agreement (BUY=1, SELL=-1, NEUTRAL=0)
        votes = []
        vote_dict = {}

        for signal, tf in [(signal_1m, "1m"), (signal_5m, "5m"), (signal_15m, "15m")]:
            if signal.side == "BUY":
                votes.append(1)
                vote_dict[tf] = "BUY"
            elif signal.side == "SELL":
                votes.append(-1)
                vote_dict[tf] = "SELL"
            else:
                votes.append(0)
                vote_dict[tf] = "NEUTRAL"

        # Compute alignment score (-1 to +1, where 1 = all agree)
        vote_sum = sum(votes)
        agreement_score = vote_sum / 3.0
        alignment_strength = abs(agreement_score)

        # Determine final signal based on majority
        if agreement_score >= 0.33:
            final_side = "BUY"
            supporting_confidence = np.mean([
                signal_1m.confidence if signal_1m.side == "BUY" else 0,
                signal_5m.confidence if signal_5m.side == "BUY" else 0,
                signal_15m.confidence if signal_15m.side == "BUY" else 0,
            ])
        elif agreement_score <= -0.33:
            final_side = "SELL"
            supporting_confidence = np.mean([
                signal_1m.confidence if signal_1m.side == "SELL" else 0,
                signal_5m.confidence if signal_5m.side == "SELL" else 0,
                signal_15m.confidence if signal_15m.side == "SELL" else 0,
            ])
        else:
            final_side = "NEUTRAL"
            supporting_confidence = np.mean([
                signal_1m.confidence, signal_5m.confidence, signal_15m.confidence
            ])

        # Apply alignment bonus/penalty
        # Perfect alignment (±1.0): +33% confidence
        # Partial alignment (±0.33): 0% modifier
        # Misaligned (0.0): -50% confidence
        alignment_modifier = alignment_strength * 1.0  # 0.0 to 1.0
        final_confidence = supporting_confidence * (1.0 + alignment_modifier)
        final_confidence = max(0.0, min(1.0, final_confidence))

        # Build reason string
        reason = (
            f"Multi-timeframe: 1m={signal_1m.side} ({signal_1m.confidence:.0%}), "
            f"5m={signal_5m.side} ({signal_5m.confidence:.0%}), "
            f"15m={signal_15m.side} ({signal_15m.confidence:.0%}); "
            f"alignment {alignment_strength:.0%}"
        )

        # Build components dict
        components = {
            "1m": {"side": signal_1m.side, "confidence": round(signal_1m.confidence, 3)},
            "5m": {"side": signal_5m.side, "confidence": round(signal_5m.confidence, 3)},
            "15m": {"side": signal_15m.side, "confidence": round(signal_15m.confidence, 3)},
            "alignment_score": round(agreement_score, 3),
            "alignment_strength": round(alignment_strength, 3),
            "vote_breakdown": vote_dict,
        }

        return SignalResult(
            side=final_side,
            confidence=final_confidence,
            reason=reason,
            method="multi_timeframe",
            components=components,
        )


class MultiTimeframeStats:
    """Track multi-timeframe signal statistics."""

    def __init__(self):
        self.signals = []
        self.alignment_by_outcome = {"correct": [], "incorrect": []}

    def record(
        self,
        signal: SignalResult,
        actual_outcome: Optional[str] = None,
    ) -> None:
        """Record a multi-timeframe signal.

        Args:
            signal: SignalResult from multi-timeframe aggregator
            actual_outcome: "correct" or "incorrect" (optional)
        """
        alignment = signal.components.get("alignment_strength", 0.0)
        self.signals.append({
            "side": signal.side,
            "confidence": signal.confidence,
            "alignment": alignment,
            "outcome": actual_outcome,
        })

        if actual_outcome:
            self.alignment_by_outcome[actual_outcome].append(alignment)

    def report(self) -> str:
        """Generate multi-timeframe statistics report."""
        if not self.signals:
            return "No multi-timeframe signals recorded"

        correct = [s for s in self.signals if s["outcome"] == "correct"]
        incorrect = [s for s in self.signals if s["outcome"] == "incorrect"]

        report = f"""
Multi-Timeframe Signal Statistics
==================================
Total signals: {len(self.signals)}
Correct: {len(correct)}
Incorrect: {len(incorrect)}

Alignment Analysis:
  Correct signals - avg alignment: {np.mean([s['alignment'] for s in correct]):.0%}
  Incorrect signals - avg alignment: {np.mean([s['alignment'] for s in incorrect]):.0%}

  Perfect alignment (100%): {sum(1 for s in self.signals if s['alignment'] >= 0.9)} signals
  Partial alignment (50-90%): {sum(1 for s in self.signals if 0.5 <= s['alignment'] < 0.9)} signals
  Low alignment (<50%): {sum(1 for s in self.signals if s['alignment'] < 0.5)} signals

Win rate by alignment:
  ≥90% alignment: {self._win_rate_for_alignment(0.9, 1.0):.1%}
  70-90% alignment: {self._win_rate_for_alignment(0.7, 0.9):.1%}
  50-70% alignment: {self._win_rate_for_alignment(0.5, 0.7):.1%}
  <50% alignment: {self._win_rate_for_alignment(0.0, 0.5):.1%}
        """
        return report

    def _win_rate_for_alignment(self, min_align: float, max_align: float) -> float:
        """Calculate win rate for signals in alignment range."""
        filtered = [
            s for s in self.signals
            if min_align <= s["alignment"] <= max_align
        ]

        if not filtered:
            return 0.0

        wins = sum(1 for s in filtered if s["outcome"] == "correct")
        return wins / len(filtered)

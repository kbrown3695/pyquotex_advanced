"""Phase G1: Ensemble Voting Across Regime-Specific Models

Provides consensus-based signal validation by running all regime configurations
in parallel and voting on the final prediction.

Key idea: Strong signals have consensus across regimes; weak signals disagree.
"""

from typing import Dict, Tuple, Optional, Any, List
import numpy as np
from ml.aggregation.signal_aggregator import SignalResult


class RegimeEnsembleVoter:
    """Ensemble voting across regime-specific model configurations (Phase G1).

    Generates signals using 5 different regime configurations (trending up/down,
    ranging, chaotic, default) and combines them through majority voting with
    consensus confidence scoring.

    Benefits:
    - Filters weak signals (low consensus)
    - Boosts strong signals (high consensus)
    - Reduces whipsaws (stable consensus across regimes)
    """

    def __init__(self, base_aggregator):
        """Initialize voter with base signal aggregator.

        Args:
            base_aggregator: MultiModelAggregator instance (Phase F)
        """
        self.base_aggregator = base_aggregator
        self.vote_history = {}  # Track voting stats per asset

    def vote(
        self,
        model_outputs: Dict[str, Any],
        kalman_regime: Optional[Tuple] = None,
        candles: Optional[list] = None,
    ) -> SignalResult:
        """Generate signals via ensemble voting across regimes.

        Args:
            model_outputs: Dictionary of model predictions:
                - ensemble_proba: sklearn ensemble predictions
                - kalman_proba, expected_return_proba, probability_proba: advanced models
                - kalman_regime: (regime, confidence) tuple
                - gb_directional_proba, gb_return_proba: gradient boosting
                - volatility_pred, quantile_*_pred: Phase B models
                - rl_agent_proba: Phase D reinforcement learning
                - lstm_proba, transformer_proba: Phase E deep learning
            kalman_regime: Optional (regime, confidence) tuple
            candles: Optional candle history for binary options enrichment (Phase 1.5)

        Returns:
            SignalResult with ensemble voting metadata
        """
        # Generate signals for each regime configuration
        regime_signals = self._generate_regime_signals(model_outputs, kalman_regime, candles)

        # Tally votes and compute consensus
        vote_tally, vote_breakdown = self._tally_votes(regime_signals)

        # Determine final signal and confidence
        final_signal = self._determine_final_signal(
            vote_tally, regime_signals, vote_breakdown
        )

        return final_signal

    def _generate_regime_signals(
        self,
        model_outputs: Dict[str, Any],
        kalman_regime: Optional[Tuple],
        candles: Optional[list] = None,
    ) -> Dict[str, SignalResult]:
        """Generate signals for each regime configuration.

        Args:
            model_outputs: Model predictions
            kalman_regime: Current regime
            candles: Optional candle history for binary options enrichment (Phase 1.5)

        Returns:
            Dict mapping regime_key → SignalResult
        """
        regime_signals = {}

        # List of regime configurations to test
        regime_configs = [
            "trending_up",
            "trending_down",
            "ranging",
            "chaotic",
            "default",
        ]

        for regime_key in regime_configs:
            try:
                # Generate signal using this regime's weights (Phase 1.5: include candles for BO)
                signal = self.base_aggregator.aggregate(
                    **model_outputs,
                    kalman_regime=kalman_regime,
                    override_regime_key=regime_key,
                    candles=candles,
                )
                regime_signals[regime_key] = signal
            except Exception as e:
                # Fallback to neutral if regime generation fails
                print(f"[!] Error generating signal for regime {regime_key}: {e}")
                regime_signals[regime_key] = SignalResult(
                    side="NEUTRAL",
                    confidence=0.0,
                    reason=f"Error: {str(e)}",
                    method="error",
                )

        return regime_signals

    def _tally_votes(
        self, regime_signals: Dict[str, SignalResult]
    ) -> Tuple[Dict[str, int], Dict[str, float]]:
        """Count votes and compute statistics.

        Args:
            regime_signals: Signals from each regime

        Returns:
            Tuple of (vote_tally, vote_breakdown)
            - vote_tally: {side: count} (BUY, SELL, NEUTRAL)
            - vote_breakdown: {regime: side} (for detailed analysis)
        """
        vote_tally = {"BUY": 0, "SELL": 0, "NEUTRAL": 0}
        vote_breakdown = {}

        for regime_key, signal in regime_signals.items():
            side = signal.side
            vote_tally[side] = vote_tally.get(side, 0) + 1
            vote_breakdown[regime_key] = side

        return vote_tally, vote_breakdown

    def _determine_final_signal(
        self,
        vote_tally: Dict[str, int],
        regime_signals: Dict[str, SignalResult],
        vote_breakdown: Dict[str, str],
    ) -> SignalResult:
        """Determine final signal based on voting majority and consensus.

        Args:
            vote_tally: Vote counts {side: count}
            regime_signals: All signals
            vote_breakdown: Regime breakdown

        Returns:
            Final SignalResult with voting metadata
        """
        total_votes = sum(vote_tally.values())

        # Find majority
        buy_votes = vote_tally.get("BUY", 0)
        sell_votes = vote_tally.get("SELL", 0)
        neutral_votes = vote_tally.get("NEUTRAL", 0)

        # Determine final side (require majority)
        if buy_votes > sell_votes and buy_votes > neutral_votes:
            final_side = "BUY"
            support_count = buy_votes
        elif sell_votes > buy_votes and sell_votes > neutral_votes:
            final_side = "SELL"
            support_count = sell_votes
        else:
            final_side = "NEUTRAL"
            support_count = neutral_votes

        # Compute consensus strength (0.0 to 1.0)
        consensus_strength = support_count / total_votes if total_votes > 0 else 0.0

        # Compute average confidence from supporting signals
        supporting_signals = [
            s for regime_key, s in regime_signals.items()
            if s.side == final_side
        ]

        if supporting_signals:
            avg_confidence = np.mean([s.confidence for s in supporting_signals])
        else:
            avg_confidence = np.mean([s.confidence for s in regime_signals.values()])

        # Apply consensus modifier to confidence
        # Strong consensus (5/5) → +25% confidence
        # Weak consensus (3/5) → -5% confidence
        # No consensus (tie) → -50% confidence
        consensus_modifier = 2.5 * consensus_strength - 1.0  # Range: -1.0 to +1.5
        final_confidence = avg_confidence * (1.0 + consensus_modifier)
        final_confidence = max(0.0, min(1.0, final_confidence))

        # Build reason string
        reason = (
            f"Ensemble vote {support_count}/{total_votes} ({consensus_strength:.0%}); "
            f"avg_confidence {avg_confidence:.1%}"
        )

        # Build components dict for frontend
        components = {
            "votes": vote_breakdown,
            "vote_tally": vote_tally,
            "consensus_strength": round(consensus_strength, 3),
            "regime_confidences": {
                regime_key: round(s.confidence, 3)
                for regime_key, s in regime_signals.items()
            },
            "consensus_modifier": round(consensus_modifier, 3),
        }

        return SignalResult(
            side=final_side,
            confidence=final_confidence,
            reason=reason,
            method="ensemble_voting",
            components=components,
        )

    def get_voting_stats(self, asset: str = None) -> Dict[str, Any]:
        """Get voting statistics (consensus patterns, etc).

        Args:
            asset: Optional asset name for filtered stats

        Returns:
            Dictionary of voting statistics
        """
        if asset and asset in self.vote_history:
            return self.vote_history[asset]
        else:
            # Aggregate across all assets
            all_votes = []
            for stats in self.vote_history.values():
                all_votes.extend(stats.get("votes", []))

            if not all_votes:
                return {"total_signals": 0}

            consensus_scores = [v["consensus"] for v in all_votes]

            return {
                "total_signals": len(all_votes),
                "avg_consensus": np.mean(consensus_scores),
                "std_consensus": np.std(consensus_scores),
                "strong_consensus_pct": sum(1 for c in consensus_scores if c >= 0.8) / len(consensus_scores) * 100,
                "weak_consensus_pct": sum(1 for c in consensus_scores if c <= 0.4) / len(consensus_scores) * 100,
            }


class EnsembleVotingStats:
    """Tracks ensemble voting statistics for analysis."""

    def __init__(self):
        self.signals = []
        self.consensus_by_outcome = {"correct": [], "incorrect": []}

    def record(
        self,
        signal: SignalResult,
        actual_outcome: Optional[str] = None,
    ) -> None:
        """Record a voting signal and optional outcome.

        Args:
            signal: SignalResult from voter
            actual_outcome: "correct" or "incorrect" (optional, for backtesting)
        """
        consensus = signal.components.get("consensus_strength", 0.0)
        self.signals.append({
            "side": signal.side,
            "confidence": signal.confidence,
            "consensus": consensus,
            "outcome": actual_outcome,
        })

        if actual_outcome:
            self.consensus_by_outcome[actual_outcome].append(consensus)

    def report(self) -> str:
        """Generate voting statistics report."""
        if not self.signals:
            return "No voting signals recorded"

        correct_signals = [s for s in self.signals if s["outcome"] == "correct"]
        incorrect_signals = [s for s in self.signals if s["outcome"] == "incorrect"]

        report = f"""
Ensemble Voting Statistics
==========================
Total signals: {len(self.signals)}
Correct: {len(correct_signals)}
Incorrect: {len(incorrect_signals)}

Consensus Analysis:
  Correct signals - avg consensus: {np.mean([s['consensus'] for s in correct_signals]):.1%}
  Incorrect signals - avg consensus: {np.mean([s['consensus'] for s in incorrect_signals]):.1%}

  Strong consensus (≥80%): {sum(1 for s in self.signals if s['consensus'] >= 0.8)} signals
  Weak consensus (≤40%): {sum(1 for s in self.signals if s['consensus'] <= 0.4)} signals

Win rate by consensus:
  ≥80% consensus: {self._win_rate_for_consensus(0.8, 1.0):.1%}
  60-80% consensus: {self._win_rate_for_consensus(0.6, 0.8):.1%}
  40-60% consensus: {self._win_rate_for_consensus(0.4, 0.6):.1%}
  <40% consensus: {self._win_rate_for_consensus(0.0, 0.4):.1%}
        """
        return report

    def _win_rate_for_consensus(self, min_consensus: float, max_consensus: float) -> float:
        """Calculate win rate for signals in consensus range."""
        filtered = [
            s for s in self.signals
            if min_consensus <= s["consensus"] <= max_consensus
        ]

        if not filtered:
            return 0.0

        wins = sum(1 for s in filtered if s["outcome"] == "correct")
        return wins / len(filtered)

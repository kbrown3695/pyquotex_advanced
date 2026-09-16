"""Phase G3 Integration: Wires online learning into the signal pipeline.

Manages optimizer lifecycle and integrates trade outcome tracking with
the signal aggregator to enable dynamic weight adaptation.
"""

from typing import Dict, Optional, Any
import logging
from ml.optimization.online_learning_optimizer import OnlineLearningOptimizer, OnlineLearningStats

logger = logging.getLogger(__name__)


class OnlineLearningManager:
	"""Manages Phase G3 online learning integration.

	Tracks trade outcomes and manages weight adaptation. Integrates with
	signal aggregator to optionally use adapted weights instead of baseline.
	"""

	def __init__(
		self,
		baseline_weights: Dict[str, float],
		learning_rate: float = 0.005,
		adaptation_interval: int = 10,
		min_sample_size: int = 20,
		weight_bounds: float = 0.20,
		enable_adaptation: bool = True,
		log_stats: bool = True,
	):
		"""Initialize online learning manager.

		Args:
			baseline_weights: Phase F baseline weights
			learning_rate: Adaptation aggressiveness (default 0.005)
			adaptation_interval: Adapt every N trades (default 10)
			min_sample_size: Minimum trades before adaptation (default 20)
			weight_bounds: Weight bounds as ±fraction of baseline (default 0.20)
			enable_adaptation: Whether to actually adapt weights (default True)
			log_stats: Whether to log performance stats (default True)
		"""
		self.baseline_weights = baseline_weights.copy()
		self.enable_adaptation = enable_adaptation
		self.log_stats = log_stats

		# Create optimizer
		self.optimizer = OnlineLearningOptimizer(
			baseline_weights=baseline_weights,
			learning_rate=learning_rate,
			adaptation_interval=adaptation_interval,
			min_sample_size=min_sample_size,
			weight_bounds=weight_bounds,
		)

		# Statistics tracker
		self.stats = OnlineLearningStats("G3")

	def process_trade_outcome(self, trade_result: Dict[str, Any]) -> None:
		"""Process a completed trade and update weights if enabled.

		Args:
			trade_result: Trade outcome dict with keys:
				- profit: float (P&L)
				- components: Dict[str, Any] (model predictions)
				- side: str ("BUY" or "SELL")
				- entry: float
				- exit: float
		"""
		if not self.enable_adaptation:
			return

		# Get weights before adaptation
		weights_before = self.optimizer.get_current_weights()

		# Update optimizer with trade result
		self.optimizer.update_performance(trade_result)

		# Get weights after adaptation (may be unchanged if not adaptation cycle)
		weights_after = self.optimizer.get_current_weights()

		# Record stats
		self.stats.record(trade_result, weights_before, weights_after)

		# Log if weights changed
		if weights_before != weights_after and self.log_stats:
			logger.info(
				f"G3: Weights adapted after {self.optimizer.trades_evaluated} trades. "
				f"Win rate: {self._calculate_win_rate():.2%}"
			)

	def get_current_weights(self) -> Dict[str, float]:
		"""Get current (possibly adapted) weights.

		Returns adapted weights if optimization enabled, baseline otherwise.
		"""
		if self.enable_adaptation:
			return self.optimizer.get_current_weights()
		else:
			return self.baseline_weights.copy()

	def get_performance_stats(self) -> Dict[str, Any]:
		"""Get performance statistics from optimizer."""
		return self.optimizer.get_performance_stats()

	def get_report(self) -> str:
		"""Get formatted stats report."""
		return self.stats.report()

	def _calculate_win_rate(self) -> float:
		"""Calculate overall win rate."""
		stats = self.optimizer.get_performance_stats()
		total_wins = sum(stats["model_wins"].values())
		total_losses = sum(stats["model_losses"].values())
		total = total_wins + total_losses

		if total == 0:
			return 0.5

		return total_wins / total

	def reset(self) -> None:
		"""Reset optimizer and stats."""
		self.optimizer.reset()
		self.stats = OnlineLearningStats("G3")


def create_online_learning_manager(
	baseline_weights: Dict[str, float],
	enable_g3: bool = True,
) -> Optional[OnlineLearningManager]:
	"""Factory function to create online learning manager.

	Args:
		baseline_weights: Phase F baseline weights
		enable_g3: Whether to enable G3 (default True)

	Returns:
		OnlineLearningManager if enabled, None otherwise
	"""
	if not enable_g3:
		return None

	return OnlineLearningManager(baseline_weights=baseline_weights)

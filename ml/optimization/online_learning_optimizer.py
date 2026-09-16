"""Phase G3: Online Learning - Adapts model weights based on live trading performance.

Tracks wins/losses per model and gradually adapts weights toward better performers.
Uses conservative learning rate and strict bounds to prevent overfitting.
"""

from typing import Dict, Optional, Tuple, Any
from collections import defaultdict
import numpy as np
import time


class OnlineLearningOptimizer:
	"""Adapts model weights based on live trading outcomes.

	Phase G3 implementation: tracks which models contribute to winning trades,
	gradually increases their weights, and decreases weights for losing models.
	Conservative bounds (±20% of baseline) prevent overfitting.
	"""

	def __init__(
		self,
		baseline_weights: Dict[str, float],
		learning_rate: float = 0.005,
		adaptation_interval: int = 10,
		min_sample_size: int = 20,
		weight_bounds: float = 0.20,
	):
		"""Initialize online learning optimizer.

		Args:
			baseline_weights: Phase F baseline weights (e.g., {"ensemble": 0.45, ...})
			learning_rate: How aggressively to adapt (default 0.005 = conservative)
			adaptation_interval: Adapt weights every N trades (default 10)
			min_sample_size: Minimum trades before adaptation (default 20)
			weight_bounds: Bounds as fraction of baseline, ±20% (default 0.20)
		"""
		self.baseline = baseline_weights.copy()
		self.current_weights = baseline_weights.copy()
		self.learning_rate = learning_rate
		self.adaptation_interval = adaptation_interval
		self.min_sample_size = min_sample_size
		self.weight_bounds = weight_bounds

		# Track performance per model
		self.model_wins: Dict[str, int] = defaultdict(int)
		self.model_losses: Dict[str, int] = defaultdict(int)
		self.trades_evaluated = 0

		# Track adaptation history
		self.adaptation_history: list = []
		self.last_adaptation_time = time.time()

	def update_performance(self, trade_result: Dict[str, Any]) -> None:
		"""Process a completed trade and update model performance tracking.

		Args:
			trade_result: Trade outcome with keys:
				- profit: float (positive = win, negative/zero = loss)
				- components: Dict[str, Any] (model predictions, e.g., {"ensemble": {...}})
				- side: str ("BUY" or "SELL")
				- entry: float (entry price)
				- exit: float (exit price)
		"""
		self.trades_evaluated += 1
		is_win = trade_result.get("profit", 0) > 0

		# Credit winning/losing models
		components = trade_result.get("components", {})
		for model_name in components:
			if is_win:
				self.model_wins[model_name] += 1
			else:
				self.model_losses[model_name] += 1

		# Adapt weights every N trades
		if self.trades_evaluated % self.adaptation_interval == 0:
			self._adapt_weights()

	def _adapt_weights(self) -> None:
		"""Adapt weights based on model win rates.

		Only called if minimum sample size reached. Moves weights toward winners
		and away from losers, bounded by ±20% of baseline to prevent overfitting.
		"""
		if self.trades_evaluated < self.min_sample_size:
			return  # Need minimum data

		# Calculate win rate for each model
		win_rates = {}
		for model_name in self.current_weights:
			wins = self.model_wins.get(model_name, 0)
			losses = self.model_losses.get(model_name, 0)
			total = wins + losses

			if total > 0:
				win_rates[model_name] = wins / total
			else:
				win_rates[model_name] = 0.5  # No data = neutral

		# Adjust weights based on win rates
		old_weights = self.current_weights.copy()

		for model_name, current_weight in self.current_weights.items():
			win_rate = win_rates.get(model_name, 0.5)

			# Determine direction: boost winners, reduce losers
			if win_rate > 0.55:
				# Winner: increase weight
				target = current_weight * (1 + self.learning_rate)
			elif win_rate < 0.45:
				# Loser: decrease weight
				target = current_weight * (1 - self.learning_rate)
			else:
				# Neutral: keep current
				target = current_weight

			# Apply bounds: ±20% of baseline
			min_weight = self.baseline[model_name] * (1 - self.weight_bounds)
			max_weight = self.baseline[model_name] * (1 + self.weight_bounds)

			self.current_weights[model_name] = np.clip(target, min_weight, max_weight)

		# Renormalize to sum to 1.0
		total = sum(self.current_weights.values())
		if total > 0:
			for model_name in self.current_weights:
				self.current_weights[model_name] /= total

		# Record adaptation
		self.adaptation_history.append({
			"trade_number": self.trades_evaluated,
			"timestamp": time.time(),
			"win_rates": win_rates.copy(),
			"weights_before": old_weights,
			"weights_after": self.current_weights.copy(),
		})

		self.last_adaptation_time = time.time()

	def get_current_weights(self) -> Dict[str, float]:
		"""Return current (adapted) model weights."""
		return self.current_weights.copy()

	def get_performance_stats(self) -> Dict[str, Any]:
		"""Return performance statistics per model.

		Returns:
			Dict with keys:
			- model_wins: wins per model
			- model_losses: losses per model
			- win_rates: calculated win rate per model
			- trades_evaluated: total trades processed
		"""
		win_rates = {}
		for model_name in self.current_weights:
			wins = self.model_wins.get(model_name, 0)
			losses = self.model_losses.get(model_name, 0)
			total = wins + losses

			if total > 0:
				win_rates[model_name] = wins / total
			else:
				win_rates[model_name] = 0.5

		return {
			"model_wins": dict(self.model_wins),
			"model_losses": dict(self.model_losses),
			"win_rates": win_rates,
			"trades_evaluated": self.trades_evaluated,
			"current_weights": self.current_weights.copy(),
			"baseline_weights": self.baseline.copy(),
		}

	def get_adaptation_history(self) -> list:
		"""Return full adaptation history."""
		return self.adaptation_history.copy()

	def reset(self) -> None:
		"""Reset to baseline weights and clear statistics."""
		self.current_weights = self.baseline.copy()
		self.model_wins = defaultdict(int)
		self.model_losses = defaultdict(int)
		self.trades_evaluated = 0
		self.adaptation_history = []
		self.last_adaptation_time = time.time()

	def to_dict(self) -> Dict[str, Any]:
		"""Serialize to dict for logging/saving."""
		return {
			"baseline_weights": self.baseline,
			"current_weights": self.current_weights,
			"learning_rate": self.learning_rate,
			"adaptation_interval": self.adaptation_interval,
			"min_sample_size": self.min_sample_size,
			"weight_bounds": self.weight_bounds,
			"trades_evaluated": self.trades_evaluated,
			"model_wins": dict(self.model_wins),
			"model_losses": dict(self.model_losses),
		}


class OnlineLearningStats:
	"""Records and analyzes online learning statistics."""

	def __init__(self, name: str = "G3"):
		"""Initialize stats tracker.

		Args:
			name: Name for logging (default "G3")
		"""
		self.name = name
		self.trades: list = []
		self.start_time = time.time()

	def record(
		self,
		trade_result: Dict[str, Any],
		weights_before: Dict[str, float],
		weights_after: Dict[str, float],
	) -> None:
		"""Record a trade outcome and weight changes.

		Args:
			trade_result: Trade outcome dict
			weights_before: Model weights before adaptation
			weights_after: Model weights after adaptation
		"""
		self.trades.append({
			"timestamp": time.time(),
			"trade_result": trade_result,
			"weights_before": weights_before.copy(),
			"weights_after": weights_after.copy(),
		})

	def report(self) -> str:
		"""Generate statistics report."""
		if not self.trades:
			return f"{self.name}: No trades recorded"

		# Calculate basic stats
		wins = sum(1 for t in self.trades if t["trade_result"].get("profit", 0) > 0)
		losses = len(self.trades) - wins
		win_rate = wins / len(self.trades) if self.trades else 0

		# Calculate weight changes
		weight_deltas = {}
		if self.trades:
			final_weights = self.trades[-1]["weights_after"]
			initial_weights = self.trades[0]["weights_before"]

			for model_name in initial_weights:
				initial = initial_weights.get(model_name, 0)
				final = final_weights.get(model_name, 0)
				if initial > 0:
					delta = (final - initial) / initial * 100
					weight_deltas[model_name] = delta

		# Build report
		elapsed = time.time() - self.start_time
		report_lines = [
			f"\n{self.name} Online Learning Report",
			f"{'=' * 50}",
			f"Trades: {len(self.trades)} | Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.2%}",
			f"Elapsed: {elapsed:.1f}s",
			f"\nWeight Changes:",
		]

		for model_name, delta in sorted(weight_deltas.items(), key=lambda x: -abs(x[1])):
			direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
			report_lines.append(f"  {direction} {model_name}: {delta:+.1f}%")

		return "\n".join(report_lines)

	def to_dict(self) -> Dict[str, Any]:
		"""Serialize to dict."""
		return {
			"name": self.name,
			"trades": self.trades,
			"start_time": self.start_time,
		}

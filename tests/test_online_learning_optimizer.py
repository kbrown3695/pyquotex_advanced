"""Unit tests for Phase G3 online learning optimizer."""

import pytest
import numpy as np
from ml.optimization.online_learning_optimizer import OnlineLearningOptimizer, OnlineLearningStats
from ml.serving.online_learning_manager import OnlineLearningManager


class TestOnlineLearningOptimizer:
	"""Test suite for OnlineLearningOptimizer."""

	@pytest.fixture
	def baseline_weights(self):
		"""Phase F baseline weights."""
		return {
			"ensemble": 0.45,
			"advanced": 0.25,
			"deep": 0.30,
		}

	@pytest.fixture
	def optimizer(self, baseline_weights):
		"""Create optimizer with baseline weights."""
		return OnlineLearningOptimizer(
			baseline_weights=baseline_weights,
			learning_rate=0.005,
			adaptation_interval=10,
			min_sample_size=20,
		)

	def test_initialization(self, optimizer, baseline_weights):
		"""Test optimizer initializes with correct baseline."""
		assert optimizer.baseline == baseline_weights
		assert optimizer.current_weights == baseline_weights
		assert optimizer.trades_evaluated == 0
		assert optimizer.learning_rate == 0.005

	def test_weight_normalization(self):
		"""Test that weights always sum to ~1.0."""
		weights = {"a": 0.3, "b": 0.4, "c": 0.3}
		optimizer = OnlineLearningOptimizer(baseline_weights=weights)

		# Weights should sum to 1.0
		total = sum(optimizer.current_weights.values())
		assert abs(total - 1.0) < 0.001

	def test_track_wins_and_losses(self, optimizer):
		"""Test tracking of wins and losses per model."""
		# Simulate winning trade
		trade_win = {
			"profit": 100,
			"components": {"ensemble": {}, "advanced": {}},
			"side": "BUY",
			"entry": 100,
			"exit": 101,
		}
		optimizer.update_performance(trade_win)

		# Simulate losing trade
		trade_loss = {
			"profit": -50,
			"components": {"ensemble": {}, "deep": {}},
			"side": "BUY",
			"entry": 102,
			"exit": 101,
		}
		optimizer.update_performance(trade_loss)

		assert optimizer.model_wins["ensemble"] == 1
		assert optimizer.model_wins["advanced"] == 1
		assert optimizer.model_losses["ensemble"] == 1
		assert optimizer.model_losses["deep"] == 1
		assert optimizer.trades_evaluated == 2

	def test_adaptation_requires_minimum_sample(self, optimizer, baseline_weights):
		"""Test that adaptation requires minimum sample size."""
		# Add 5 trades
		for i in range(5):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			optimizer.update_performance(trade)

		# Weights should not change yet (need min_sample_size=20)
		assert optimizer.current_weights == baseline_weights
		assert len(optimizer.adaptation_history) == 0

	def test_weight_adaptation_on_winners(self, optimizer, baseline_weights):
		"""Test that winner models get boosted."""
		# Add 20 winning trades with only "ensemble" model
		for i in range(20):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			optimizer.update_performance(trade)

		# First adaptation happens at trade 20
		assert len(optimizer.adaptation_history) > 0
		current = optimizer.current_weights["ensemble"]
		baseline = baseline_weights["ensemble"]

		# Ensemble should be boosted (100% win rate > 55%)
		assert current > baseline

	def test_weight_adaptation_on_losers(self, optimizer, baseline_weights):
		"""Test that loser models get reduced."""
		# Add 20 losing trades with only "advanced" model
		for i in range(20):
			trade = {
				"profit": -10,
				"components": {"advanced": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 99,
			}
			optimizer.update_performance(trade)

		current = optimizer.current_weights["advanced"]
		baseline = baseline_weights["advanced"]

		# Advanced should be reduced (0% win rate < 45%)
		assert current < baseline

	def test_weight_bounds_enforcement(self, optimizer, baseline_weights):
		"""Test that weights stay within ±20% of baseline."""
		# Add 100 winning trades for ensemble (aggressive boost)
		for i in range(100):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			optimizer.update_performance(trade)

		current = optimizer.current_weights["ensemble"]
		baseline = baseline_weights["ensemble"]
		min_bound = baseline * 0.8
		max_bound = baseline * 1.2

		# Should respect ±20% bounds
		assert min_bound <= current <= max_bound

	def test_weight_renormalization(self, optimizer):
		"""Test that weights are renormalized after adaptation."""
		# Add trades to trigger adaptation
		for i in range(30):
			trade = {
				"profit": 10 if i % 2 == 0 else -10,
				"components": {"ensemble": {}, "advanced": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101 if i % 2 == 0 else 99,
			}
			optimizer.update_performance(trade)

		# Weights should sum to 1.0
		total = sum(optimizer.current_weights.values())
		assert abs(total - 1.0) < 0.001

	def test_neutral_win_rate(self, optimizer, baseline_weights):
		"""Test that 50% win rate keeps weights neutral."""
		# Add alternating wins and losses
		for i in range(20):
			profit = 10 if i % 2 == 0 else -10
			trade = {
				"profit": profit,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101 if i % 2 == 0 else 99,
			}
			optimizer.update_performance(trade)

		current = optimizer.current_weights["ensemble"]
		baseline = baseline_weights["ensemble"]

		# Should stay close to baseline (neutral win rate)
		assert abs(current - baseline) < 0.01

	def test_get_performance_stats(self, optimizer):
		"""Test performance stats generation."""
		# Add some trades
		for i in range(15):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			optimizer.update_performance(trade)

		stats = optimizer.get_performance_stats()

		assert "model_wins" in stats
		assert "model_losses" in stats
		assert "win_rates" in stats
		assert "trades_evaluated" in stats
		assert "current_weights" in stats
		assert "baseline_weights" in stats
		assert stats["trades_evaluated"] == 15
		assert stats["win_rates"]["ensemble"] == 1.0  # 100% wins

	def test_reset(self, optimizer, baseline_weights):
		"""Test reset functionality."""
		# Add trades and adapt
		for i in range(30):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			optimizer.update_performance(trade)

		# Verify adaptation happened
		assert optimizer.trades_evaluated == 30
		assert len(optimizer.adaptation_history) > 0

		# Reset
		optimizer.reset()

		# Should be back to baseline
		assert optimizer.current_weights == baseline_weights
		assert optimizer.trades_evaluated == 0
		assert len(optimizer.adaptation_history) == 0

	def test_adaptation_history(self, optimizer):
		"""Test adaptation history tracking."""
		# Add trades to trigger adaptation
		for i in range(30):
			trade = {
				"profit": 10 if i < 20 else -10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101 if i < 20 else 99,
			}
			optimizer.update_performance(trade)

		history = optimizer.get_adaptation_history()

		# Should have at least one adaptation (at trade 20)
		assert len(history) > 0

		# Each entry should have required fields
		for entry in history:
			assert "trade_number" in entry
			assert "timestamp" in entry
			assert "win_rates" in entry
			assert "weights_before" in entry
			assert "weights_after" in entry


class TestOnlineLearningStats:
	"""Test suite for OnlineLearningStats."""

	def test_initialization(self):
		"""Test stats tracker initialization."""
		stats = OnlineLearningStats("test")
		assert stats.name == "test"
		assert len(stats.trades) == 0

	def test_record_trade(self):
		"""Test recording a trade."""
		stats = OnlineLearningStats()
		trade_result = {"profit": 100, "side": "BUY"}
		weights_before = {"ensemble": 0.45}
		weights_after = {"ensemble": 0.46}

		stats.record(trade_result, weights_before, weights_after)

		assert len(stats.trades) == 1
		assert stats.trades[0]["trade_result"] == trade_result

	def test_report_generation(self):
		"""Test report generation."""
		stats = OnlineLearningStats("test")

		# Add trades
		for i in range(5):
			trade_result = {
				"profit": 10 if i % 2 == 0 else -5,
				"side": "BUY",
			}
			weights_before = {"a": 0.5, "b": 0.5}
			weights_after = {"a": 0.51, "b": 0.49}

			stats.record(trade_result, weights_before, weights_after)

		report = stats.report()

		# Should contain key information
		assert "test" in report
		assert "Trades:" in report
		assert "Wins:" in report
		assert "Win Rate:" in report


class TestOnlineLearningManager:
	"""Test suite for OnlineLearningManager."""

	@pytest.fixture
	def baseline_weights(self):
		"""Phase F baseline weights."""
		return {
			"ensemble": 0.45,
			"advanced": 0.25,
			"deep": 0.30,
		}

	@pytest.fixture
	def manager(self, baseline_weights):
		"""Create manager instance."""
		return OnlineLearningManager(
			baseline_weights=baseline_weights,
			enable_adaptation=True,
		)

	def test_initialization(self, manager, baseline_weights):
		"""Test manager initialization."""
		assert manager.baseline_weights == baseline_weights
		assert manager.enable_adaptation is True
		assert manager.optimizer is not None

	def test_process_trade_outcome(self, manager):
		"""Test processing trade outcomes."""
		trade_result = {
			"profit": 100,
			"components": {"ensemble": {}},
			"side": "BUY",
			"entry": 100,
			"exit": 101,
		}

		manager.process_trade_outcome(trade_result)

		# Should track in optimizer
		assert manager.optimizer.trades_evaluated == 1

	def test_get_current_weights_adapted(self, manager, baseline_weights):
		"""Test getting adapted weights when enabled."""
		# Add winning trades to trigger adaptation
		for i in range(30):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			manager.process_trade_outcome(trade)

		weights = manager.get_current_weights()

		# Should be adapted version
		assert weights["ensemble"] > baseline_weights["ensemble"]

	def test_get_current_weights_disabled(self, baseline_weights):
		"""Test getting baseline when adaptation disabled."""
		manager = OnlineLearningManager(
			baseline_weights=baseline_weights,
			enable_adaptation=False,
		)

		# Add trades
		for i in range(30):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			manager.process_trade_outcome(trade)

		weights = manager.get_current_weights()

		# Should return baseline (no adaptation)
		assert weights == baseline_weights

	def test_get_performance_stats(self, manager):
		"""Test getting performance stats."""
		for i in range(15):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			manager.process_trade_outcome(trade)

		stats = manager.get_performance_stats()

		assert "model_wins" in stats
		assert "win_rates" in stats

	def test_reset(self, manager, baseline_weights):
		"""Test reset functionality."""
		# Add trades
		for i in range(30):
			trade = {
				"profit": 10,
				"components": {"ensemble": {}},
				"side": "BUY",
				"entry": 100,
				"exit": 101,
			}
			manager.process_trade_outcome(trade)

		# Reset
		manager.reset()

		# Should be back to baseline
		assert manager.get_current_weights() == baseline_weights

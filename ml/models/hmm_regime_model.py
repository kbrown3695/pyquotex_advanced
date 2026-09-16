"""Hidden Markov Model for regime detection (Phase C).

Uses Gaussian HMM to learn latent market regimes from returns distribution.
Each hidden state represents a distinct market regime (trending, ranging, volatile).
"""

from typing import Any, Dict, Optional, Tuple
import logging

import joblib
import numpy as np

from ml.models.base import BaseTradingModel
from ml.models.market_regime import MarketRegime

logger = logging.getLogger(__name__)


def _import_hmmlearn() -> Any:
	"""Import and return hmmlearn module (raises ImportError if absent)."""
	import hmmlearn.hmm  # noqa: PLC0415
	return hmmlearn.hmm


class HMMRegimeModel(BaseTradingModel):
	"""Gaussian Hidden Markov Model for regime detection.

	Learns 3-4 latent states representing different market regimes from returns.
	Stateful: maintains internal hidden state across calls (like Kalman filter).
	"""

	def __init__(self, n_states: int = 3, **kwargs: Any) -> None:
		self.n_states = n_states
		self.kwargs = kwargs
		self.model: Any = None
		self._metadata: Dict[str, Any] = {}
		self._feature_names: Optional[list] = None
		self._current_state: Optional[int] = None
		self._last_row_key: Optional[bytes] = None
		self._initialize_model()

	def set_feature_names(self, feature_names: list) -> None:
		"""Set feature names for this model."""
		self._feature_names = feature_names

	def _initialize_model(self) -> None:
		"""Initialize the underlying Gaussian HMM."""
		hmmlearn = _import_hmmlearn()
		self.model = hmmlearn.GaussianHMM(
			n_components=self.n_states,
			covariance_type=self.kwargs.get("covariance_type", "diag"),
			n_iter=self.kwargs.get("n_iter", 100),
			random_state=42,
		)

	def train(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> None:
		"""Train the HMM on return sequences.

		Args:
			X: Feature matrix (N, M), where first column should be returns
			y: Unused (HMM is unsupervised)
		"""
		if len(X) < 50:
			raise ValueError(f"Need ≥50 samples for HMM, got {len(X)}")

		# Use first column (returns_1) as the primary feature for HMM
		returns = X[:, 0].reshape(-1, 1) if X.ndim > 1 else X.reshape(-1, 1)

		# Fit HMM
		try:
			self.model.fit(returns)
			self._current_state = None  # Reset state after training
			self._metadata = {
				"n_samples": len(X),
				"n_states": self.n_states,
				"converged": self.model.monitor_.converged if hasattr(self.model, 'monitor_') else None,
				"transitions": self.model.transmat_.tolist() if hasattr(self.model, 'transmat_') else None,
			}
		except Exception as e:
			logger.warning(f"HMM training failed: {e}")
			raise ValueError(f"HMM training failed: {e}")

	def predict(self, X: np.ndarray) -> np.ndarray:
		"""Predict hidden states for each sample.

		Args:
			X: Feature matrix (N, M) or single sample (M,)

		Returns:
			Array of hidden state indices (0 to n_states-1)
		"""
		if self.model is None:
			raise ValueError("Model not trained")
		arr = np.asarray(X, dtype=np.float64)
		if arr.ndim == 1:
			arr = arr.reshape(1, -1)

		# Use first column (returns)
		returns = arr[:, 0].reshape(-1, 1) if arr.ndim > 1 else arr.reshape(-1, 1)
		return self.model.predict(returns)

	def predict_proba(self, X: np.ndarray) -> np.ndarray:
		"""Predict state probabilities using forward algorithm.

		Args:
			X: Feature matrix (N, M) or single sample (M,)

		Returns:
			Array of shape (N, n_states) with state probabilities
		"""
		if self.model is None:
			raise ValueError("Model not trained")
		arr = np.asarray(X, dtype=np.float64)
		if arr.ndim == 1:
			arr = arr.reshape(1, -1)

		# Use first column (returns)
		returns = arr[:, 0].reshape(-1, 1) if arr.ndim > 1 else arr.reshape(-1, 1)

		# Compute posteriors (hidden state probabilities)
		posteriors = self.model.predict_proba(returns)
		return posteriors

	def get_current_regime(self, X: np.ndarray) -> Tuple[MarketRegime, float]:
		"""Get the most likely current regime and its probability.

		Args:
			X: Single sample (M,) or last row of feature matrix

		Returns:
			Tuple of (MarketRegime, probability)
		"""
		if self.model is None:
			raise ValueError("Model not trained")

		arr = np.asarray(X, dtype=np.float64)
		if arr.ndim == 2:
			arr = arr[-1]  # Take last sample

		returns = arr[0:1].reshape(1, -1)
		proba = self.model.predict_proba(returns)[0]
		state_idx = np.argmax(proba)
		prob = proba[state_idx]

		# Map hidden states to MarketRegime
		# HMM learns 3 states; map them based on mean return
		regime = self._state_to_regime(state_idx)
		return regime, float(prob)

	def _state_to_regime(self, state_idx: int) -> MarketRegime:
		"""Map HMM hidden state to market regime.

		Uses mean return and variance of each state.
		"""
		if not hasattr(self.model, 'means_') or self.model.means_ is None:
			return MarketRegime.RANGING

		means = self.model.means_.flatten()
		if state_idx >= len(means):
			return MarketRegime.RANGING

		mean_return = means[state_idx]

		# Classify based on mean return
		if mean_return > 0.002:
			return MarketRegime.TRENDING_UP
		elif mean_return < -0.002:
			return MarketRegime.TRENDING_DOWN
		else:
			return MarketRegime.RANGING

	def get_params(self) -> Dict[str, Any]:
		"""Get model parameters."""
		return {
			"n_states": self.n_states,
			**self.kwargs,
		}

	def get_metadata(self) -> Dict[str, Any]:
		"""Get model metadata."""
		return {
			**self._metadata,
			"model_class": self.__class__.__name__,
			"n_states": self.n_states,
		}

	def get_feature_importances(self) -> np.ndarray:
		"""Get feature importances (not applicable for HMM, return transition matrix diagonal)."""
		if self.model is None or not hasattr(self.model, 'transmat_'):
			return np.array([])
		# Return diagonal of transition matrix (self-loop probabilities)
		return np.diag(self.model.transmat_)

	def save(self, path: str) -> None:
		"""Save model to disk."""
		joblib.dump(self.model, path)

	@classmethod
	def load(cls, path: str) -> "HMMRegimeModel":
		"""Load model from disk."""
		instance = cls()
		instance.model = joblib.load(path)
		return instance

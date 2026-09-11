"""Kalman/state-space model (V3.5.0 advanced ML layer).

Hand-rolled 2-state Kalman filter (local level + trend) over the returns
feature stream. Stateful across serving calls: the byte-key gate makes each
unique observation row advance the filter exactly once, even when
``MLSignalService`` feeds the same feature row to ``predict_proba`` and to each
advisory probe (``predict_regime`` / ``predict_volatility``).
"""

import math
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np

from ml.models.base import BaseTradingModel
from ml.models.market_regime import MarketRegime


class KalmanStateSpaceModel(BaseTradingModel):
	"""Local-level + trend Kalman filter for regime and volatility forecasts.

	The filter observes the ``returns_1`` feature (index 0) and tracks a hidden
	level and trend state. Regimes come from the filtered trend sign relative to
	its own uncertainty; volatility from the filtered state covariance.
	"""

	def __init__(
		self,
		process_noise: float = 1e-4,
		measurement_noise: float = 1e-2,
		min_variance: float = 1e-6,
		regime_deadband_mult: float = 1.0,
	) -> None:
		self.process_noise = process_noise
		self.measurement_noise = measurement_noise
		self.min_variance = min_variance
		self.regime_deadband_mult = regime_deadband_mult
		self._x: np.ndarray = np.zeros(2)
		self._P: np.ndarray = np.eye(2)
		self._Q: np.ndarray = np.array(
			[
				[0.25 * process_noise, 0.5 * process_noise],
				[0.5 * process_noise, process_noise],
			]
		)
		self._R: float = measurement_noise
		self._last_row_key: Optional[bytes] = None
		self._metadata: Dict[str, Any] = {}
		self._feature_names: Optional[list] = None

	# -- Kalman math --------------------------------------------------------

	def _observe(self, z: float) -> None:
		"""Predict + update one scalar observation (standard 2-state filter)."""
		F = np.array([[1.0, 1.0], [0.0, 1.0]])
		x_pred = F @ self._x
		P_pred = F @ self._P @ F.T + self._Q
		# Update (H = [1, 0])
		y = z - x_pred[0]
		S = P_pred[0, 0] + self._R
		K = np.array([P_pred[0, 0], P_pred[1, 0]]) / S
		Kcol = K.reshape(2, 1)
		self._x = x_pred + K * y
		self._P = (np.eye(2) - Kcol @ np.array([[1.0, 0.0]])) @ P_pred
		# Symmetrize to keep the covariance well-conditioned.
		self._P = (self._P + self._P.T) / 2.0

	def _consume(self, X: np.ndarray) -> None:
		"""Advance the filter by the observation row, deduping per unique row.

		``MLSignalService.predict`` passes the same feature row to
		``predict_proba`` and then to each advisory probe; the byte-key gate
		guarantees the filter steps exactly once per unique row regardless of
		how many predictors see it.
		"""
		arr = np.asarray(X, dtype=np.float64)
		if arr.ndim == 2 and arr.shape[0] != 1:
			# Explicit multi-row stream: every row is a fresh step.
			for row in arr:
				self._consume(row.reshape(1, -1))
			return
		row = arr[0] if arr.ndim == 2 else arr
		key = row.tobytes()
		if key == self._last_row_key:
			return
		self._last_row_key = key
		self._observe(float(row[0]))

	def _proba_pair(self) -> np.ndarray:
		"""P(down), P(up) from the filtered trend relative to its uncertainty."""
		trend = float(self._x[1])
		scale = max(float(np.sqrt(self._P[1, 1])), 1e-4)
		p_up = 1.0 / (1.0 + math.exp(-trend / scale))
		return np.array([1.0 - p_up, p_up])

	# -- BaseTradingModel interface ----------------------------------------

	def train(self, X: np.ndarray, y: np.ndarray) -> None:
		"""Fit filter noise to the training returns stream and warm the state.

		``X`` is the (n, n_features) feature matrix; the observation stream is
		the ``returns_1`` column (index 0). ``y`` is accepted for interface
		parity but not used by the unsupervised filter.
		"""
		arr = np.asarray(X, dtype=np.float64)
		z = arr[:, 0]
		r = (
			max(float(np.var(z)), self.min_variance)
			if z.size > 0
			else max(self.measurement_noise, self.min_variance)
		)
		q = (
			max(float(np.var(np.diff(z))) * 0.25, 1e-8)
			if z.size > 1
			else max(self.process_noise, 1e-8)
		)
		self._R = r
		self._Q = np.array([[0.25 * q, 0.5 * q], [0.5 * q, q]])
		self._x = np.array([float(np.mean(z)) if z.size > 0 else 0.0, 0.0])
		self._P = np.array([[r, 0.0], [0.0, q]])
		for value in z:
			self._observe(float(value))
		self._last_row_key = None

	def predict(self, X: np.ndarray) -> np.ndarray:
		"""Predict class labels (UP=1 / DOWN=0) from the filtered trend."""
		return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

	def predict_proba(self, X: np.ndarray) -> np.ndarray:
		"""Predict class probabilities: shape (n_samples, 2), P(up) = [:, 1]."""
		arr = np.asarray(X, dtype=np.float64)
		if arr.ndim == 1 or (arr.ndim == 2 and arr.shape[0] == 1):
			self._consume(arr)
			return self._proba_pair().reshape(1, 2)
		if arr.ndim == 2:
			rows = []
			for row in arr:
				# Explicit batch rows are fresh steps even if byte-identical.
				self._last_row_key = None
				self._consume(row.reshape(1, -1))
				rows.append(self._proba_pair())
			return np.array(rows)
		raise ValueError(f"Unexpected feature shape: {arr.shape}")

	def predict_regime(self, X: np.ndarray) -> Tuple[MarketRegime, float]:
		"""Regime from the filtered trend sign relative to its uncertainty."""
		self._consume(X)
		trend = float(self._x[1])
		deadband = self.regime_deadband_mult * max(float(np.sqrt(self._P[1, 1])), 1e-6)
		if trend > deadband:
			regime = MarketRegime.TRENDING_UP
		elif trend < -deadband:
			regime = MarketRegime.TRENDING_DOWN
		else:
			regime = MarketRegime.RANGING
		confidence = self._R / (self._R + self._P[0, 0])
		confidence = max(0.0, min(1.0, float(confidence)))
		return regime, confidence

	def predict_volatility(self, X: np.ndarray) -> float:
		"""Predictive standard deviation of the next observation."""
		self._consume(X)
		return float(np.sqrt(self._P[0, 0] + self._R))

	def get_params(self) -> Dict[str, Any]:
		"""Get model parameters."""
		return {
			"process_noise": self.process_noise,
			"measurement_noise": self.measurement_noise,
			"min_variance": self.min_variance,
			"regime_deadband_mult": self.regime_deadband_mult,
		}

	def get_metadata(self) -> Dict[str, Any]:
		"""Get model metadata."""
		return {
			"type": "kalman_state_space",
			"params": self.get_params(),
			"feature_names": self._feature_names,
		}

	def get_feature_importances(self) -> np.ndarray:
		"""State-space models expose no per-feature importances."""
		return np.array([])

	def set_feature_names(self, feature_names: list) -> None:
		"""Set feature names for metadata."""
		self._feature_names = feature_names

	def save(self, path: str) -> None:
		"""Save model to disk."""
		joblib.dump(
			{
				"x": self._x,
				"P": self._P,
				"Q": self._Q,
				"R": self._R,
				"process_noise": self.process_noise,
				"measurement_noise": self.measurement_noise,
				"min_variance": self.min_variance,
				"regime_deadband_mult": self.regime_deadband_mult,
				"feature_names": self._feature_names,
				"metadata": self._metadata,
			},
			path,
		)

	@classmethod
	def load(cls, path: str) -> "KalmanStateSpaceModel":
		"""Load model from disk."""
		data = joblib.load(path)
		instance = cls(
			process_noise=data.get("process_noise", 1e-4),
			measurement_noise=data.get("measurement_noise", 1e-2),
			min_variance=data.get("min_variance", 1e-6),
			regime_deadband_mult=data.get("regime_deadband_mult", 1.0),
		)
		instance._x = data["x"]
		instance._P = data["P"]
		instance._Q = data["Q"]
		instance._R = data["R"]
		instance._feature_names = data.get("feature_names")
		instance._metadata = data.get("metadata", {})
		return instance


__all__: list = ["KalmanStateSpaceModel"]

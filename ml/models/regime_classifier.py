"""Regime classifier model (Phase C).

LightGBM classifier for detecting market regimes (TRENDING_UP, TRENDING_DOWN, RANGING, CHAOTIC).
Uses technical indicators to classify the current market state.
"""

from typing import Any, Dict, Optional
import logging

import joblib
import numpy as np

from ml.models.base import BaseTradingModel
from ml.models.market_regime import MarketRegime

logging.getLogger("lightgbm").setLevel(logging.ERROR)


def _import_lgbm() -> Any:
	"""Import and return the lightgbm module (raises ImportError if absent)."""
	import lightgbm  # noqa: PLC0415
	return lightgbm


class RegimeClassifier(BaseTradingModel):
	"""LightGBM classifier for market regime detection.

	Classifies market state into 4 regimes:
	- TRENDING_UP: Strong uptrend (high slope, momentum)
	- TRENDING_DOWN: Strong downtrend (low slope, negative momentum)
	- RANGING: Sideways/choppy (low slope, low volatility)
	- CHAOTIC: High volatility, unclear direction
	"""

	def __init__(self, **kwargs: Any) -> None:
		self.kwargs = kwargs
		self.model: Any = None
		self._metadata: Dict[str, Any] = {}
		self._feature_names: Optional[list] = None
		self.regime_map = {
			0: MarketRegime.TRENDING_DOWN,
			1: MarketRegime.RANGING,
			2: MarketRegime.CHAOTIC,
			3: MarketRegime.TRENDING_UP,
		}
		self._initialize_model()

	def set_feature_names(self, feature_names: list) -> None:
		"""Set feature names for this model."""
		self._feature_names = feature_names

	def _initialize_model(self) -> None:
		"""Initialize the underlying LightGBM classifier."""
		lgbm = _import_lgbm()
		self.model = lgbm.LGBMClassifier(
			n_estimators=self.kwargs.get("n_estimators", 100),
			max_depth=self.kwargs.get("max_depth", 5),
			learning_rate=self.kwargs.get("learning_rate", 0.1),
			num_leaves=self.kwargs.get("num_leaves", 31),
			subsample=self.kwargs.get("subsample", 0.8),
			random_state=42,
			verbose=-1,
		)

	def train(self, X: np.ndarray, y: np.ndarray) -> None:
		"""Train the regime classifier.

		Args:
			X: Feature matrix (N, M)
			y: Target regime labels (N,) - should be integers 0-3 mapped to MarketRegime
		"""
		if len(X) < 50:
			raise ValueError(f"Need ≥50 samples for regime classifier, got {len(X)}")

		# Ensure y is numeric (0-3)
		y_numeric = np.array([regime.value if hasattr(regime, 'value') else regime for regime in y])
		self.model.fit(X, y_numeric)
		self._metadata = {
			"n_samples": len(X),
			"n_features": X.shape[1],
			"regimes": [r.name for r in MarketRegime],
		}

	def predict(self, X: np.ndarray) -> np.ndarray:
		"""Predict regime labels.

		Args:
			X: Feature matrix (N, M) or single sample (M,)

		Returns:
			Array of regime indices (0-3)
		"""
		if self.model is None:
			raise ValueError("Model not trained")
		arr = np.asarray(X, dtype=np.float64)
		if arr.ndim == 1:
			arr = arr.reshape(1, -1)
		return self.model.predict(arr)

	def predict_proba(self, X: np.ndarray) -> np.ndarray:
		"""Predict regime probabilities.

		Args:
			X: Feature matrix (N, M) or single sample (M,)

		Returns:
			Array of shape (N, 4) with probabilities for each regime
		"""
		if self.model is None:
			raise ValueError("Model not trained")
		arr = np.asarray(X, dtype=np.float64)
		if arr.ndim == 1:
			arr = arr.reshape(1, -1)
		return self.model.predict_proba(arr)

	def get_params(self) -> Dict[str, Any]:
		"""Get model parameters."""
		if self.model is None:
			return self.kwargs
		return {**self.kwargs, **self.model.get_params()}

	def get_metadata(self) -> Dict[str, Any]:
		"""Get model metadata."""
		return {
			**self._metadata,
			"model_class": self.__class__.__name__,
			"regimes": [r.name for r in MarketRegime],
		}

	def get_feature_importances(self) -> np.ndarray:
		"""Get feature importances from the LightGBM model."""
		if self.model is None or not hasattr(self.model, 'feature_importances_'):
			return np.array([])
		return np.asarray(self.model.feature_importances_, dtype=np.float64)

	def save(self, path: str) -> None:
		"""Save model to disk."""
		joblib.dump(self.model, path)

	@classmethod
	def load(cls, path: str) -> "RegimeClassifier":
		"""Load model from disk."""
		instance = cls()
		instance.model = joblib.load(path)
		return instance

"""Expected return regression model for predicting return magnitude."""

from typing import Dict, Any, Optional
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.svm import SVR
import joblib

from ml.models.base import BaseTradingModel


class ExpectedReturnModel(BaseTradingModel):
	"""Regression model for predicting expected return magnitude."""

	def __init__(
		self,
		algorithm: str = "random_forest",
		**kwargs,
	):
		self.algorithm = algorithm
		self.kwargs = kwargs
		self.model = None
		self._metadata: Dict[str, Any] = {}
		self._feature_names: Optional[list] = None

		self._initialize_model()

	def _initialize_model(self) -> None:
		"""Initialize the underlying sklearn regression model."""
		if self.algorithm == "random_forest":
			self.model = RandomForestRegressor(
				n_estimators=self.kwargs.get("n_estimators", 100),
				max_depth=self.kwargs.get("max_depth", 10),
				min_samples_split=self.kwargs.get("min_samples_split", 2),
				min_samples_leaf=self.kwargs.get("min_samples_leaf", 1),
				random_state=42,
				n_jobs=-1,
			)
		elif self.algorithm == "linear_regression":
			self.model = LinearRegression(
				positive=self.kwargs.get("positive", False),
			)
		elif self.algorithm == "ridge":
			self.model = Ridge(
				alpha=self.kwargs.get("alpha", 1.0),
				random_state=42,
			)
		elif self.algorithm == "lasso":
			self.model = Lasso(
				alpha=self.kwargs.get("alpha", 0.1),
				random_state=42,
				max_iter=self.kwargs.get("max_iter", 1000),
			)
		elif self.algorithm == "svr":
			self.model = SVR(
				C=self.kwargs.get("C", 1.0),
				epsilon=self.kwargs.get("epsilon", 0.1),
				kernel=self.kwargs.get("kernel", "rbf"),
			)
		else:
			raise ValueError(f"Unknown algorithm: {self.algorithm}")

	def train(self, X: np.ndarray, y: np.ndarray) -> None:
		"""Train the regression model."""
		# For expected return, y should be continuous values (e.g., future returns)
		self.model.fit(X, y)

	def predict(self, X: np.ndarray) -> np.ndarray:
		"""Predict expected return values."""
		return self.model.predict(X)

	def predict_proba(self, X: np.ndarray) -> np.ndarray:
		"""
		Predict class probabilities.

		For regression models, we don't have class probabilities.
		Return a uniform distribution as placeholder.
		"""
		# Return shape (n_samples, n_classes) for compatibility
		# Assuming 3 classes: DOWN, NEUTRAL, UP (like directional classifier)
		n_samples = X.shape[0]
		return np.full((n_samples, 3), 1.0 / 3.0)

	def get_params(self) -> Dict[str, Any]:
		"""Get model parameters."""
		return self.model.get_params() if hasattr(self.model, "get_params") else {}

	def get_metadata(self) -> Dict[str, Any]:
		"""Get model metadata."""
		return {
			"algorithm": self.algorithm,
			"params": self.get_params(),
			"feature_names": self._feature_names,
			"model_type": "expected_return_regression",
		}

	def get_feature_importances(self) -> np.ndarray:
		"""Get feature importances."""
		if hasattr(self.model, "feature_importances_"):
			return self.model.feature_importances_
		if hasattr(self.model, "coef_"):
			coef = self.model.coef_
			if coef.ndim > 1:
				coef = coef.flatten()
			return np.abs(coef)
		return np.array([])

	def set_feature_names(self, feature_names: list) -> None:
		"""Set feature names for metadata."""
		self._feature_names = feature_names

	def save(self, path: str) -> None:
		"""Save model to disk."""
		joblib.dump(
			{
				"model": self.model,
				"algorithm": self.algorithm,
				"feature_names": self._feature_names,
				"metadata": self._metadata,
			},
			path,
		)

	@classmethod
	def load(cls, path: str) -> "ExpectedReturnModel":
		"""Load model from disk."""
		data = joblib.load(path)
		instance = cls(algorithm=data.get("algorithm", "random_forest"))
		instance.model = data["model"]
		instance._feature_names = data.get("feature_names")
		instance._metadata = data.get("metadata", {})
		return instance

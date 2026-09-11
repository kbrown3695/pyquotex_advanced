"""Probability calibration model for trading signals.

This module provides probability calibration for classification models,
ensuring that predicted probabilities are well-calibrated and meaningful
for trading decisions.
"""

from typing import Any, Dict, Optional, Tuple

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from ml.models.base import BaseTradingModel


class ProbabilityModel(BaseTradingModel):
	"""Calibrated probability model for trading signals.

	Wraps a base classifier with probability calibration to ensure
	that predicted probabilities reflect actual likelihoods.

	This is critical for trading because:
	- A probability of 0.70 should mean 70% of predictions are correct
	- Calibrated probabilities enable proper position sizing
	- Risk management depends on accurate probability estimates
	"""

	def __init__(
		self,
		base_model: Optional[BaseTradingModel] = None,
		calibration_method: str = "sigmoid",
		cv: int = 3,
		**kwargs,
	):
		"""Initialize probability model.

		Args:
			base_model: Base classifier to calibrate (if None, uses RandomForest)
			calibration_method: 'sigmoid' or 'isotonic'
			cv: Number of cross-validation folds for calibration
			**kwargs: Additional arguments for base model
		"""
		# ``base_model``/``calibrated_model`` wrap heterogeneous sklearn
		# estimators, so type them ``Any`` (like the other model wrappers).
		self.base_model: Any = base_model
		self.calibration_method = calibration_method
		self.cv = cv
		self.kwargs = kwargs
		self.calibrated_model: Any = None
		self._metadata: Dict[str, Any] = {}
		self._feature_names: Optional[list] = None
		self._calibration_curve: Optional[Dict] = None

		if base_model is None:
			from ml.models.directional_classifier import DirectionalClassifier

			self.base_model = DirectionalClassifier(
				algorithm="random_forest",
				n_estimators=kwargs.get("n_estimators", 120),
				max_depth=kwargs.get("max_depth", 6),
			)

	def train(self, X: np.ndarray, y: np.ndarray) -> None:
		"""Train the calibrated model.

		Args:
			X: Feature matrix
			y: Target labels (0 or 1)
		"""
		# First train base model
		self.base_model.train(X, y)

		# Then calibrate probabilities
		if hasattr(self.base_model, "model") and hasattr(self.base_model.model, "predict_proba"):
			# Use sklearn's CalibratedClassifierCV
			self.calibrated_model = CalibratedClassifierCV(
				estimator=self.base_model.model,
				method=self.calibration_method,
				cv=self.cv,
			)
			self.calibrated_model.fit(X, y)
		else:
			# Fallback: use the base model directly
			self.calibrated_model = self.base_model

		# Compute calibration curve for monitoring
		self._compute_calibration_curve(X, y)

	def predict(self, X: np.ndarray) -> np.ndarray:
		"""Predict class labels."""
		if self.calibrated_model is None:
			raise ValueError("Model not trained yet")

		if hasattr(self.calibrated_model, "predict"):
			return self.calibrated_model.predict(X)

		# Fallback: use base model
		return self.base_model.predict(X)

	def predict_proba(self, X: np.ndarray) -> np.ndarray:
		"""Predict calibrated class probabilities.

		Returns:
			Array of shape (n_samples, 2) with probabilities for [class_0, class_1]
		"""
		if self.calibrated_model is None:
			raise ValueError("Model not trained yet")

		if hasattr(self.calibrated_model, "predict_proba"):
			return self.calibrated_model.predict_proba(X)

		# Fallback: use base model if it has predict_proba
		if hasattr(self.base_model, "predict_proba"):
			return self.base_model.predict_proba(X)

		# Last resort: convert decision function to probability
		if hasattr(self.base_model, "predict"):
			predictions = self.base_model.predict(X)
			proba = np.zeros((len(X), 2))
			proba[:, 1] = predictions
			proba[:, 0] = 1 - predictions
			return proba

		raise RuntimeError("No predict_proba method available")

	def predict_with_uncertainty(
		self,
		X: np.ndarray,
	) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
		"""Predict with uncertainty estimates.

		Returns:
			Tuple of (predictions, probabilities, uncertainty_scores)
		"""
		proba = self.predict_proba(X)
		predictions = (proba[:, 1] >= 0.5).astype(int)

		# Uncertainty = 1 - max_probability (higher = more uncertain)
		max_proba = np.max(proba, axis=1)
		uncertainty = 1 - max_proba

		return predictions, proba[:, 1], uncertainty

	def get_params(self) -> Dict[str, Any]:
		"""Get model parameters."""
		return {
			"calibration_method": self.calibration_method,
			"cv": self.cv,
			"base_model_params": self.base_model.get_params()
			if hasattr(self.base_model, "get_params")
			else {},
		}

	def get_metadata(self) -> Dict[str, Any]:
		"""Get model metadata."""
		return {
			"type": "calibrated_probability_model",
			"calibration_method": self.calibration_method,
			"calibration_curve": self._calibration_curve,
			"cv_folds": self.cv,
			"feature_names": self._feature_names,
			"base_model_metadata": self.base_model.get_metadata()
			if hasattr(self.base_model, "get_metadata")
			else {},
		}

	def get_feature_importances(self) -> np.ndarray:
		"""Get feature importances from base model."""
		if hasattr(self.base_model, "get_feature_importances"):
			return self.base_model.get_feature_importances()
		if hasattr(self.calibrated_model, "feature_importances_"):
			return self.calibrated_model.feature_importances_
		return np.array([])

	def set_feature_names(self, feature_names: list) -> None:
		"""Set feature names for metadata."""
		self._feature_names = feature_names
		if hasattr(self.base_model, "set_feature_names"):
			self.base_model.set_feature_names(feature_names)

	def _compute_calibration_curve(self, X: np.ndarray, y: np.ndarray) -> None:
		"""Compute calibration curve for monitoring.

		Groups predictions into bins and computes actual vs predicted.
		"""
		if len(X) < 100:
			return

		proba = self.predict_proba(X)[:, 1]

		# Use sklearn's calibration_curve if available
		try:
			from sklearn.calibration import calibration_curve

			fraction_positive, mean_predicted_value = calibration_curve(
				y, proba, n_bins=10, strategy="uniform"
			)

			self._calibration_curve = {
				"fraction_positive": fraction_positive.tolist(),
				"mean_predicted_value": mean_predicted_value.tolist(),
				"n_bins": 10,
			}

			# Calculate calibration metrics
			self._calibration_curve["brier_score"] = float(np.mean((proba - y) ** 2))
			self._calibration_curve["ece"] = float(
				np.mean(np.abs(fraction_positive - mean_predicted_value))
			)

		except Exception:
			# Simple fallback calibration
			bins: np.ndarray = np.linspace(0, 1, 11)
			bin_indices = np.asarray(np.digitize(proba, bins))

			fraction_positive = []
			mean_predicted = []
			counts = []

			for i in range(1, len(bins)):
				indices = [j for j, b in enumerate(bin_indices) if b == i]
				if len(indices) < 5:
					continue
				counts.append(len(indices))
				fraction_positive.append(float(np.mean(y[indices])))
				mean_predicted.append(float(np.mean(proba[indices])))

			self._calibration_curve = {
				"fraction_positive": fraction_positive,
				"mean_predicted_value": mean_predicted,
				"counts": counts,
				"brier_score": float(np.mean((proba - y) ** 2)),
				"ece": float(
					np.mean([abs(f - m) for f, m in zip(fraction_positive, mean_predicted)])
				),
			}

	def save(self, path: str) -> None:
		"""Save calibrated model to disk."""
		import os

		import joblib

		# Ensure directory exists
		os.makedirs(os.path.dirname(path), exist_ok=True)

		# Save full model
		joblib.dump(
			{
				"calibrated_model": self.calibrated_model,
				"base_model": self.base_model,
				"calibration_method": self.calibration_method,
				"cv": self.cv,
				"feature_names": self._feature_names,
				"metadata": self._metadata,
				"calibration_curve": self._calibration_curve,
			},
			path,
		)

	@classmethod
	def load(cls, path: str) -> "ProbabilityModel":
		"""Load calibrated model from disk."""
		import joblib

		data = joblib.load(path)

		instance = cls(
			calibration_method=data.get("calibration_method", "sigmoid"),
			cv=data.get("cv", 3),
		)
		instance.calibrated_model = data.get("calibrated_model")
		instance.base_model = data.get("base_model")
		instance._feature_names = data.get("feature_names")
		instance._metadata = data.get("metadata", {})
		instance._calibration_curve = data.get("calibration_curve")

		return instance


class ProbabilityCalibrator:
	"""Utility class for calibrating probability models.

	Provides methods for:
	- Calibration curve analysis
	- Brier score computation
	- Reliability diagrams
	- Expected calibration error (ECE)
	"""

	@staticmethod
	def compute_brier_score(y_true: np.ndarray, y_pred_proba: np.ndarray) -> float:
		"""Compute Brier score (mean squared error of probabilities).

		Lower is better. Brier score of 0 is perfect, 0.25 is random for binary.
		"""
		return float(np.mean((y_pred_proba - y_true) ** 2))

	@staticmethod
	def compute_ece(
		y_true: np.ndarray,
		y_pred_proba: np.ndarray,
		n_bins: int = 10,
	) -> float:
		"""Compute Expected Calibration Error (ECE).

		Measures how well calibrated probabilities are.
		Lower is better.
		"""
		bins: np.ndarray = np.linspace(0, 1, n_bins + 1)
		bin_indices = np.asarray(np.digitize(y_pred_proba, bins))

		ece = 0.0
		for i in range(1, len(bins)):
			indices = [j for j, b in enumerate(bin_indices) if b == i]
			if len(indices) == 0:
				continue

			pred_mean = np.mean(y_pred_proba[indices])
			actual_mean = np.mean(y_true[indices])
			ece += (len(indices) / len(y_true)) * float(abs(pred_mean - actual_mean))

		return float(ece)

	@staticmethod
	def compute_mce(
		y_true: np.ndarray,
		y_pred_proba: np.ndarray,
		n_bins: int = 10,
	) -> float:
		"""Compute Maximum Calibration Error (MCE).

		Measures the worst-case calibration error.
		"""
		bins: np.ndarray = np.linspace(0, 1, n_bins + 1)
		bin_indices = np.asarray(np.digitize(y_pred_proba, bins))

		mce = 0.0
		for i in range(1, len(bins)):
			indices = [j for j, b in enumerate(bin_indices) if b == i]
			if len(indices) == 0:
				continue

			pred_mean = np.mean(y_pred_proba[indices])
			actual_mean = np.mean(y_true[indices])
			mce = max(mce, float(abs(pred_mean - actual_mean)))

		return float(mce)

	@staticmethod
	def reliability_diagram_data(
		y_true: np.ndarray,
		y_pred_proba: np.ndarray,
		n_bins: int = 10,
	) -> Dict[str, Any]:
		"""Generate data for reliability diagram.

		Returns:
			Dictionary with 'x' (mean predicted) and 'y' (mean actual) for each bin
		"""
		bins: np.ndarray = np.linspace(0, 1, n_bins + 1)
		bin_indices = np.asarray(np.digitize(y_pred_proba, bins))

		x_vals = []
		y_vals = []
		counts = []

		for i in range(1, len(bins)):
			indices = [j for j, b in enumerate(bin_indices) if b == i]
			if len(indices) < 2:
				continue

			x_vals.append(float(np.mean(y_pred_proba[indices])))
			y_vals.append(float(np.mean(y_true[indices])))
			counts.append(len(indices))

		return {
			"mean_predicted": x_vals,
			"fraction_positive": y_vals,
			"counts": counts,
			"n_bins": len(x_vals),
		}

	@staticmethod
	def calibrate_with_isotonic(
		y_true: np.ndarray,
		y_pred_proba: np.ndarray,
	) -> np.ndarray:
		"""Calibrate probabilities using isotonic regression.

		Non-parametric calibration that can fix any monotonic miscalibration.
		"""
		iso = IsotonicRegression(
			y_min=0.0,
			y_max=1.0,
			out_of_bounds="clip",
		)
		iso.fit(y_pred_proba, y_true)
		return iso.transform(y_pred_proba)

	@staticmethod
	def calibrate_with_sigmoid(
		y_true: np.ndarray,
		y_pred_proba: np.ndarray,
	) -> np.ndarray:
		"""Calibrate probabilities using sigmoid (Platt) scaling.

		Parametric calibration using logistic regression.
		"""
		# Reshape for sklearn
		X = y_pred_proba.reshape(-1, 1)
		lr = LogisticRegression(
			C=1e8,  # Large C for near-perfect fit
			max_iter=1000,
		)
		lr.fit(X, y_true)

		# Get calibrated probabilities
		calibrated = lr.predict_proba(X)[:, 1]
		return calibrated

"""Directional classifier model for UP/DOWN prediction."""

from typing import Dict, Any, Optional
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
import joblib

from ml.models.base import BaseTradingModel


class DirectionalClassifier(BaseTradingModel):
    """Directional classifier for UP/DOWN market prediction."""

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
        """Initialize the underlying sklearn model."""
        if self.algorithm == "random_forest":
            self.model = RandomForestClassifier(
                n_estimators=self.kwargs.get("n_estimators", 120),
                max_depth=self.kwargs.get("max_depth", 6),
                min_samples_leaf=self.kwargs.get("min_samples_leaf", 3),
                min_samples_split=self.kwargs.get("min_samples_split", 5),
                random_state=42,
                n_jobs=-1,
            )
        elif self.algorithm == "logistic_regression":
            self.model = LogisticRegression(
                max_iter=self.kwargs.get("max_iter", 1000),
                C=self.kwargs.get("C", 1.0),
                class_weight="balanced",
                random_state=42,
            )
        elif self.algorithm == "svm":
            self.model = LinearSVC(
                C=self.kwargs.get("C", 1.0),
                random_state=42,
                max_iter=10000,
                class_weight="balanced",
            )
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the classifier."""
        self.model.fit(X, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels."""
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        if hasattr(self.model, "predict_proba"):
            return self.model.predict_proba(X)
        # Fallback for models without predict_proba
        try:
            from sklearn.calibration import CalibratedClassifierCV

            calibrated = CalibratedClassifierCV(
                self.model,
                method="sigmoid",
                cv=3,
            )
            calibrated.fit(X, self.model.predict(X))
            return calibrated.predict_proba(X)
        except Exception:
            # Simple fallback: convert decision function to probability
            if hasattr(self.model, "decision_function"):
                scores = self.model.decision_function(X)
                prob = 1.0 / (1.0 + np.exp(-scores))
                return np.column_stack((1 - prob, prob))
            raise

    def get_params(self) -> Dict[str, Any]:
        """Get model parameters."""
        return self.model.get_params() if hasattr(self.model, "get_params") else {}

    def get_metadata(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "algorithm": self.algorithm,
            "params": self.get_params(),
            "feature_names": self._feature_names,
        }

    def get_feature_importances(self) -> np.ndarray:
        """Get feature importances."""
        if hasattr(self.model, "feature_importances_"):
            return self.model.feature_importances_
        if hasattr(self.model, "coef_"):
            coef = self.model.coef_
            if coef.ndim == 2 and coef.shape[0] == 1:
                coef = coef[0]
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
    def load(cls, path: str) -> "DirectionalClassifier":
        """Load model from disk."""
        data = joblib.load(path)
        instance = cls(algorithm=data.get("algorithm", "random_forest"))
        instance.model = data["model"]
        instance._feature_names = data.get("feature_names")
        instance._metadata = data.get("metadata", {})
        return instance

"""Quantile prediction model (Phase B).

LightGBM quantile regressor for predicting uncertainty bands (upper/lower
confidence intervals) around directional predictions.
"""

from typing import Any, Dict, List, Optional
import logging

import joblib
import numpy as np

from ml.models.base import BaseTradingModel

# Suppress LightGBM warnings about insufficient data
logging.getLogger("lightgbm").setLevel(logging.ERROR)


def _import_lgbm() -> Any:
    """Import and return the lightgbm module (raises ImportError if absent)."""
    import lightgbm  # noqa: PLC0415
    return lightgbm


class QuantileModel(BaseTradingModel):
    """LightGBM quantile regressor for uncertainty bands.

    Predicts upper and lower quantiles (e.g., 0.75 and 0.25) to define
    confidence intervals around return predictions.
    """

    def __init__(self, quantile: float = 0.75, **kwargs: Any) -> None:
        self.quantile = quantile  # 0.75 for upper, 0.25 for lower
        self.kwargs = kwargs
        self.model: Any = None
        self._metadata: Dict[str, Any] = {}
        self._feature_names: Optional[list] = None
        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initialize the underlying LightGBM quantile regressor."""
        lgbm = _import_lgbm()
        self.model = lgbm.LGBMRegressor(
            n_estimators=self.kwargs.get("n_estimators", 80),
            max_depth=self.kwargs.get("max_depth", 4),
            learning_rate=self.kwargs.get("learning_rate", 0.08),
            subsample=self.kwargs.get("subsample", 0.8),
            objective="quantile",
            alpha=self.quantile,
            random_state=42,
        )

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the quantile regressor.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target values (n_samples,) - typically next-period returns
        """
        self.model.fit(X, y, verbose=-1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict quantile values."""
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return a uniform placeholder for API compatibility."""
        n_samples = X.shape[0]
        return np.full((n_samples, 3), 1.0 / 3.0)

    def get_params(self) -> Dict[str, Any]:
        """Get model parameters."""
        return self.model.get_params() if hasattr(self.model, "get_params") else {}

    def get_metadata(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "algorithm": "lightgbm_quantile",
            "quantile": self.quantile,
            "params": self.get_params(),
            "feature_names": self._feature_names,
            "model_type": "quantile_regressor",
        }

    def get_feature_importances(self) -> np.ndarray:
        """Get feature importances."""
        if hasattr(self.model, "feature_importances_"):
            return self.model.feature_importances_
        return np.array([])

    def set_feature_names(self, feature_names: list) -> None:
        """Set feature names for metadata."""
        self._feature_names = feature_names

    def save(self, path: str) -> None:
        """Save model to disk."""
        joblib.dump(
            {
                "model": self.model,
                "quantile": self.quantile,
                "feature_names": self._feature_names,
                "metadata": self._metadata,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "QuantileModel":
        """Load model from disk."""
        data = joblib.load(path)
        quantile = data.get("quantile", 0.75)
        instance = cls(quantile=quantile)
        instance.model = data["model"]
        instance._feature_names = data.get("feature_names")
        instance._metadata = data.get("metadata", {})
        return instance


__all__: List[str] = ["QuantileModel"]

"""Volatility prediction model (Phase B).

LightGBM regressor for predicting next-period volatility, used to dampen
confidence scores when volatility is high.
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


class VolatilityModel(BaseTradingModel):
    """LightGBM regressor for volatility prediction.

    Predicts next-period volatility (as ATR or std dev of returns).
    High volatility dampens confidence in directional signals.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.model: Any = None
        self._metadata: Dict[str, Any] = {}
        self._feature_names: Optional[list] = None
        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initialize the underlying LightGBM regressor."""
        lgbm = _import_lgbm()
        self.model = lgbm.LGBMRegressor(
            n_estimators=self.kwargs.get("n_estimators", 80),
            max_depth=self.kwargs.get("max_depth", 4),
            learning_rate=self.kwargs.get("learning_rate", 0.08),
            subsample=self.kwargs.get("subsample", 0.8),
            random_state=42,
        )

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the volatility regressor.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Volatility targets (n_samples,) - should be ATR or std dev of returns
        """
        self.model.fit(X, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict volatility values."""
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
            "algorithm": "lightgbm_volatility",
            "params": self.get_params(),
            "feature_names": self._feature_names,
            "model_type": "volatility_regressor",
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
                "feature_names": self._feature_names,
                "metadata": self._metadata,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "VolatilityModel":
        """Load model from disk."""
        data = joblib.load(path)
        instance = cls()
        instance.model = data["model"]
        instance._feature_names = data.get("feature_names")
        instance._metadata = data.get("metadata", {})
        return instance


__all__: List[str] = ["VolatilityModel"]

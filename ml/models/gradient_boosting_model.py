"""Gradient boosting models (V3.5 ML layer).

Primary boosting implementations for the live ML seam. ``xgboost`` and
``lightgbm`` are optional runtime dependencies: the model imports them lazily
so the rest of the stack still imports if a wheel is unavailable.
"""

from typing import Any, Dict, List, Optional
import logging
import warnings

import joblib
import numpy as np

from ml.models.base import BaseTradingModel

# Suppress xgboost, lightgbm, and sklearn joblib warnings
logging.getLogger("xgboost").setLevel(logging.ERROR)
logging.getLogger("lightgbm").setLevel(logging.ERROR)
logging.getLogger("sklearn").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module="xgboost")
warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.*")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")


def _import_xgb() -> Any:
    """Import and return the xgboost module (raises ImportError if absent)."""
    import xgboost  # noqa: PLC0415 - lazy import keeps the base stack importable

    return xgboost


def _import_lgbm() -> Any:
    """Import and return the lightgbm module (raises ImportError if absent)."""
    import lightgbm  # noqa: PLC0415

    return lightgbm


class GradientBoostingDirectionalModel(BaseTradingModel):
    """Gradient-boosted UP/DOWN classifier (default: XGBoost).

    Predicts P(up) via ``predict_proba``; the calibrated wrapper
    ``ProbabilityModel`` can be layered on top for well-calibrated
    probabilities.
    """

    def __init__(
        self,
        algorithm: str = "xgboost",
        **kwargs: Any,
    ) -> None:
        self.algorithm = algorithm
        self.kwargs = kwargs
        self.model: Any = None
        self._metadata: Dict[str, Any] = {}
        self._feature_names: Optional[list] = None

        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initialize the underlying booster classifier."""
        common = dict(
            n_estimators=self.kwargs.get("n_estimators", 120),
            max_depth=self.kwargs.get("max_depth", 6),
            learning_rate=self.kwargs.get("learning_rate", 0.05),
            subsample=self.kwargs.get("subsample", 0.8),
            random_state=42,
        )
        if self.algorithm == "xgboost":
            xgb = _import_xgb()
            self.model = xgb.XGBClassifier(
                use_label_encoder=False,
                eval_metric="logloss",
                **common,
            )
        elif self.algorithm == "lightgbm":
            lgbm = _import_lgbm()
            self.model = lgbm.LGBMClassifier(**common)
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the boosted classifier."""
        self.model.fit(X, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels."""
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities: shape (n_samples, 2), P(up) = [:, 1]."""
        return self.model.predict_proba(X)

    def get_params(self) -> Dict[str, Any]:
        """Get model parameters."""
        return self.model.get_params() if hasattr(self.model, "get_params") else {}

    def get_metadata(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "algorithm": self.algorithm,
            "params": self.get_params(),
            "feature_names": self._feature_names,
            "model_type": "gradient_boosting_classifier",
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
                "algorithm": self.algorithm,
                "feature_names": self._feature_names,
                "metadata": self._metadata,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "GradientBoostingDirectionalModel":
        """Load model from disk."""
        data = joblib.load(path)
        instance = cls(algorithm=data.get("algorithm", "xgboost"))
        instance.model = data["model"]
        instance._feature_names = data.get("feature_names")
        instance._metadata = data.get("metadata", {})
        return instance


class GradientBoostingReturnModel(BaseTradingModel):
    """Gradient-boosted regression model for expected-return magnitude."""

    def __init__(
        self,
        algorithm: str = "xgboost",
        **kwargs: Any,
    ) -> None:
        self.algorithm = algorithm
        self.kwargs = kwargs
        self.model: Any = None
        self._metadata: Dict[str, Any] = {}
        self._feature_names: Optional[list] = None

        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initialize the underlying booster regressor."""
        common = dict(
            n_estimators=self.kwargs.get("n_estimators", 100),
            max_depth=self.kwargs.get("max_depth", 5),
            learning_rate=self.kwargs.get("learning_rate", 0.05),
            subsample=self.kwargs.get("subsample", 0.8),
            random_state=42,
        )
        if self.algorithm == "xgboost":
            xgb = _import_xgb()
            self.model = xgb.XGBRegressor(**common)
        elif self.algorithm == "lightgbm":
            lgbm = _import_lgbm()
            self.model = lgbm.LGBMRegressor(**common)
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the boosted regressor."""
        self.model.fit(X, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict expected-return values."""
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
            "algorithm": self.algorithm,
            "params": self.get_params(),
            "feature_names": self._feature_names,
            "model_type": "gradient_boosting_regressor",
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
                "algorithm": self.algorithm,
                "feature_names": self._feature_names,
                "metadata": self._metadata,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "GradientBoostingReturnModel":
        """Load model from disk."""
        data = joblib.load(path)
        instance = cls(algorithm=data.get("algorithm", "xgboost"))
        instance.model = data["model"]
        instance._feature_names = data.get("feature_names")
        instance._metadata = data.get("metadata", {})
        return instance


__all__: List[str] = [
    "GradientBoostingDirectionalModel",
    "GradientBoostingReturnModel",
]

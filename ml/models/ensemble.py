"""Ensemble model for robust predictions."""

from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.ensemble import VotingClassifier
from sklearn.preprocessing import LabelEncoder

from ml.models.base import BaseTradingModel
from ml.models.directional_classifier import DirectionalClassifier


class EnsembleModel(BaseTradingModel):
    """Ensemble of multiple models for better generalization."""

    def __init__(
        self,
        model_names: Optional[List[str]] = None,
        voting: str = "soft",
        **kwargs,
    ):
        self.model_names = model_names or ["random_forest", "logistic_regression"]
        self.voting = voting
        self.kwargs = kwargs
        self.ensemble: Any = None
        self._metadata: Dict[str, Any] = {}
        self._feature_names: Optional[list] = None

    def _initialize_ensemble(self) -> None:
        """Initialize the ensemble with individual models."""
        estimators = []
        for name in self.model_names:
            # Create individual model
            if name == "random_forest":
                model = DirectionalClassifier(
                    algorithm="random_forest",
                    n_estimators=self.kwargs.get("n_estimators", 100),
                    max_depth=self.kwargs.get("max_depth", 5),
                )
            elif name == "logistic_regression":
                model = DirectionalClassifier(
                    algorithm="logistic_regression",
                    C=self.kwargs.get("C", 1.0),
                )
            elif name == "svm":
                model = DirectionalClassifier(
                    algorithm="svm",
                    C=self.kwargs.get("C", 1.0),
                )
            elif name == "gradient_boosting":
                from ml.models.gradient_boosting_model import (
                    GradientBoostingDirectionalModel,
                )

                model = GradientBoostingDirectionalModel(
                    n_estimators=self.kwargs.get("n_estimators", 100),
                    max_depth=self.kwargs.get("max_depth", 5),
                )
            elif name == "lightgbm":
                from ml.models.gradient_boosting_model import (
                    GradientBoostingDirectionalModel,
                )

                model = GradientBoostingDirectionalModel(
                    algorithm="lightgbm",
                    n_estimators=self.kwargs.get("n_estimators", 100),
                    max_depth=self.kwargs.get("max_depth", 5),
                )
            else:
                continue

            estimators.append((name, model.model))

        if len(estimators) < 2:
            raise ValueError("Need at least 2 models for ensemble")

        # n_jobs=1: fitting members in parallel loky subprocesses crashes
        # LightGBM's Dataset construction on Windows (OpenMP access violation).
        # Fitting in-process preserves the lightgbm-first import guard.
        self.ensemble = VotingClassifier(
            estimators=estimators,
            voting=self.voting,
            n_jobs=1,
        )

    @classmethod
    def from_models(
        cls,
        members: List[Tuple[str, BaseTradingModel]],
        voting: str = "soft",
    ) -> "EnsembleModel":
        """Build an ensemble from already-trained model instances.

        Args:
            members: List of ``(name, BaseTradingModel)`` pairs. Each member's
                raw sklearn estimator (``.model``) is used in the voting.
            voting: "soft" (probability averaging) or "hard" (label votes).

        Returns:
            An ``EnsembleModel`` whose ``ensemble`` is ready to predict.
        """
        instance = cls(
            model_names=[name for name, _ in members],
            voting=voting,
        )
        raw = [
            (name, model.model)
            for name, model in members
            if getattr(model, "model", None) is not None
        ]
        # n_jobs=1 avoids LightGBM's OpenMP crash inside loky subprocesses.
        instance.ensemble = VotingClassifier(
            estimators=raw,
            voting=voting,
            n_jobs=1,
        )
        # The members are already trained, so adopt their fitted state instead
        # of re-fitting: predict_proba (soft) only iterates ``estimators_`` and
        # ``predict`` needs ``classes_``/``le_`` to invert the argmax.
        instance.ensemble.estimators_ = [est for _, est in raw]
        instance.ensemble.named_estimators_ = dict(raw)
        classes = next(
            (
                getattr(est, "classes_", None)
                for _, est in raw
                if getattr(est, "classes_", None) is not None
            ),
            None,
        )
        if classes is not None:
            le = LabelEncoder()
            le.classes_ = np.asarray(classes)
            instance.ensemble.le_ = le
            instance.ensemble.classes_ = le.classes_
        return instance

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the ensemble."""
        self._initialize_ensemble()
        self.ensemble.fit(X, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels."""
        return self.ensemble.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        if hasattr(self.ensemble, "predict_proba"):
            return self.ensemble.predict_proba(X)
        # Fallback for hard voting
        raise ValueError("Ensemble does not support probability prediction")

    def get_params(self) -> Dict[str, Any]:
        """Get model parameters."""
        return {
            "model_names": self.model_names,
            "voting": self.voting,
            "params": self.kwargs,
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "type": "ensemble",
            "model_names": self.model_names,
            "voting": self.voting,
            "feature_names": self._feature_names,
        }

    def get_feature_importances(self) -> np.ndarray:
        """Get average feature importances across ensemble."""
        importances = []
        for name, estimator in self.ensemble.named_estimators_.items():
            if hasattr(estimator, "feature_importances_"):
                importances.append(estimator.feature_importances_)
            elif hasattr(estimator, "coef_"):
                coef = estimator.coef_
                if coef.ndim == 2 and coef.shape[0] == 1:
                    coef = coef[0]
                importances.append(np.abs(coef))

        if importances:
            return np.mean(importances, axis=0)
        return np.array([])

    def set_feature_names(self, feature_names: list) -> None:
        """Set feature names for metadata."""
        self._feature_names = feature_names

    def save(self, path: str) -> None:
        """Save ensemble to disk."""
        joblib.dump(
            {
                "ensemble": self.ensemble,
                "model_names": self.model_names,
                "voting": self.voting,
                "feature_names": self._feature_names,
                "metadata": self._metadata,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "EnsembleModel":
        """Load ensemble from disk."""
        data = joblib.load(path)
        instance = cls(
            model_names=data.get("model_names", ["random_forest"]),
            voting=data.get("voting", "soft"),
        )
        instance.ensemble = data["ensemble"]
        instance._feature_names = data.get("feature_names")
        instance._metadata = data.get("metadata", {})

        # Validate and restore soft-voting attributes after loading
        # joblib.dump/load can lose VotingClassifier's fitted state
        if instance.voting == "soft" and instance.ensemble is not None:
            if not hasattr(instance.ensemble, "predict_proba"):
                # Ensemble lost predict_proba after deserialization
                # Try to restore from estimators_ if they exist
                if hasattr(instance.ensemble, "estimators_"):
                    classes = None
                    for est in instance.ensemble.estimators_:
                        if hasattr(est, "classes_"):
                            classes = est.classes_
                            break

                    if classes is not None:
                        le = LabelEncoder()
                        le.classes_ = np.asarray(classes)
                        instance.ensemble.le_ = le
                        instance.ensemble.classes_ = le.classes_

        return instance

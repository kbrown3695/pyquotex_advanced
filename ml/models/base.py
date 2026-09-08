"""Base model interface for ML models."""

from abc import ABC, abstractmethod
from typing import Dict, Any
import numpy as np


class BaseTradingModel(ABC):
    """Abstract base class for trading models."""

    @abstractmethod
    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the model on the given data."""
        pass

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict target values."""
        pass

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        pass

    @abstractmethod
    def get_params(self) -> Dict[str, Any]:
        """Get model parameters."""
        pass

    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """Get model metadata."""
        pass

    @abstractmethod
    def get_feature_importances(self) -> np.ndarray:
        """Get feature importances."""
        pass

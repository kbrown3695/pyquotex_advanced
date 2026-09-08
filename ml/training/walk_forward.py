"""Walk-forward validation for time-series models."""

from typing import List, Dict, Optional
from dataclasses import dataclass
import numpy as np

from ml.training.validation import evaluate_model


@dataclass
class WalkForwardWindow:
    """A single walk-forward window."""

    train_start: int
    train_end: int
    test_start: int
    test_end: int


class WalkForwardValidator:
    """Perform walk-forward validation on time-series data."""

    def __init__(
        self,
        train_size: int,
        test_size: int,
        step_size: Optional[int] = None,
    ):
        self.train_size = train_size
        self.test_size = test_size
        self.step_size = step_size or test_size

    def generate_windows(self, total_samples: int) -> List[WalkForwardWindow]:
        """Generate walk-forward validation windows."""
        windows = []
        current_start = 0

        while current_start + self.train_size + self.test_size <= total_samples:
            windows.append(
                WalkForwardWindow(
                    train_start=current_start,
                    train_end=current_start + self.train_size,
                    test_start=current_start + self.train_size,
                    test_end=current_start + self.train_size + self.test_size,
                )
            )
            current_start += self.step_size

        return windows

    def validate(
        self,
        model_factory,
        X: np.ndarray,
        y: np.ndarray,
    ) -> Dict[str, List[float]]:
        """Run walk-forward validation.

        Args:
            model_factory: Callable that returns a new model instance
            X: Feature matrix
            y: Target vector

        Returns:
            Dictionary with metrics for each window
        """
        windows = self.generate_windows(len(X))

        if not windows:
            return {"error": "Not enough data for walk-forward validation"}

        results = {
            "auc": [],
            "precision": [],
            "recall": [],
            "f1": [],
            "accuracy": [],
        }

        for window in windows:
            X_train = X[window.train_start : window.train_end]
            y_train = y[window.train_start : window.train_end]
            X_test = X[window.test_start : window.test_end]
            y_test = y[window.test_start : window.test_end]

            model = model_factory()
            model.train(X_train, y_train)

            metrics = evaluate_model(model, X_test, y_test)

            for key in results:
                if key in metrics:
                    results[key].append(metrics[key])

        return results

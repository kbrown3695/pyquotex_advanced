"""Time-series validation for ML models."""

from typing import Tuple
import numpy as np


def chronological_split(
    X: np.ndarray,
    y: np.ndarray,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split data chronologically without random shuffling.

    Args:
        X: Feature matrix
        y: Target vector
        train_ratio: Proportion for training
        validation_ratio: Proportion for validation

    Returns:
        Tuple of (X_train, X_val, X_test, y_train, y_val, y_test)
    """
    n = len(X)

    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + validation_ratio))

    return (
        X[:train_end],
        X[train_end:val_end],
        X[val_end:],
        y[:train_end],
        y[train_end:val_end],
        y[val_end:],
    )


def evaluate_model(
    model,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> dict:
    """Evaluate model on validation data.

    Returns:
        Dictionary with metrics: auc, precision, recall, f1, accuracy
    """
    from sklearn.metrics import (
        roc_auc_score,
        precision_score,
        recall_score,
        f1_score,
        accuracy_score,
        confusion_matrix,
    )

    y_pred = model.predict(X_val)

    try:
        y_proba = model.predict_proba(X_val)
        auc = roc_auc_score(y_val, y_proba[:, 1])
    except Exception:
        auc = roc_auc_score(y_val, y_pred)

    return {
        "auc": float(auc),
        "precision": float(precision_score(y_val, y_pred, zero_division=0)),
        "recall": float(recall_score(y_val, y_pred, zero_division=0)),
        "f1": float(f1_score(y_val, y_pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_val, y_pred)),
        "confusion_matrix": confusion_matrix(y_val, y_pred).tolist(),
    }

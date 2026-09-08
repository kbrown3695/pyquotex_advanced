"""ML models module (core ensemble tier only)."""

# Load LightGBM before XGBoost on Windows: both bundle an OpenMP runtime, and if
# xgboost's libomp loads first, LightGBM's Dataset construction crashes with an
# access violation (OSError). Guarded so a missing LightGBM never breaks the rest.
try:
    import lightgbm  # noqa: F401
except ImportError:
    pass

from ml.models.base import BaseTradingModel
from ml.models.directional_classifier import DirectionalClassifier
from ml.models.ensemble import EnsembleModel
from ml.models.gradient_boosting_model import (
    GradientBoostingDirectionalModel,
    GradientBoostingReturnModel,
)

__all__ = [
    "BaseTradingModel",
    "DirectionalClassifier",
    "EnsembleModel",
    "GradientBoostingDirectionalModel",
    "GradientBoostingReturnModel",
]

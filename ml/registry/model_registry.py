"""Model registry - filesystem-only, no DB (replaces dollar's DB/MLflow registry)."""

import os
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from ml.models.base import BaseTradingModel
from ml.models.directional_classifier import DirectionalClassifier
from ml.models.ensemble import EnsembleModel
from ml.models.gradient_boosting_model import (
    GradientBoostingDirectionalModel,
    GradientBoostingReturnModel,
)
from ml.models.kalman_state_space import KalmanStateSpaceModel
from ml.models.expected_return_model import ExpectedReturnModel
from ml.models.probability_model import ProbabilityModel
from ml.models.regime_classifier import RegimeClassifier
from ml.models.hmm_regime_model import HMMRegimeModel


class ModelRegistry:
    """Filesystem-based model registry.

    Models are stored per asset+timeframe+model_key:
    models/<slug>__<model_key>/
      active.json                   # {"active_version": "20260909T142233"}
      versions/
        20260909T142233/
          model.joblib              # serialized ensemble/classifier
          metadata.json             # training metadata (includes model_class, model_module)
    """

    def __init__(self, base_dir: str = "models"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True, parents=True)
        self._cache: Dict[str, BaseTradingModel] = {}
        self._model_class_map = {
            "DirectionalClassifier": DirectionalClassifier,
            "EnsembleModel": EnsembleModel,
            "GradientBoostingDirectionalModel": GradientBoostingDirectionalModel,
            "GradientBoostingReturnModel": GradientBoostingReturnModel,
            "KalmanStateSpaceModel": KalmanStateSpaceModel,
            "ExpectedReturnModel": ExpectedReturnModel,
            "ProbabilityModel": ProbabilityModel,
            "RegimeClassifier": RegimeClassifier,
            "HMMRegimeModel": HMMRegimeModel,
        }

    def _slugify(self, asset: str, timeframe: str, model_key: str = "default") -> str:
        """Convert asset+timeframe+model_key to filesystem-safe slug.

        E.g. "AUD/CAD (OTC)", "1m", "kalman" -> "aud_cad_otc_1m__kalman"
        """
        combined = f"{asset}_{timeframe}__{model_key}"
        slug = re.sub(r'[^A-Za-z0-9]+', '_', combined).strip('_').lower()
        return slug

    def _get_asset_dir(self, asset: str, timeframe: str, model_key: str = "default") -> Path:
        """Get the asset+timeframe+model_key directory path."""
        slug = self._slugify(asset, timeframe, model_key)
        return self.base_dir / slug

    def get_active_model(
        self,
        asset: str,
        timeframe: str,
        model_key: str = "default",
    ) -> Optional[BaseTradingModel]:
        """Load the active model for asset+timeframe+model_key.

        Returns None if no trained model exists yet.
        If active.json is missing/corrupt, self-heals by picking the latest version.
        """
        slug = self._slugify(asset, timeframe, model_key)
        cache_key = f"{asset}_{timeframe}_{model_key}"

        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]

        asset_dir = self._get_asset_dir(asset, timeframe, model_key)
        if not asset_dir.exists():
            return None

        # Try to load from active.json pointer
        active_file = asset_dir / "active.json"
        version_dir = None

        if active_file.exists():
            try:
                with open(active_file, 'r') as f:
                    active_data = json.load(f)
                    version_name = active_data.get("active_version")
                    if version_name:
                        version_dir = asset_dir / "versions" / version_name
                        if not version_dir.exists():
                            version_dir = None
            except (json.JSONDecodeError, IOError):
                version_dir = None

        # Self-heal: pick latest version if pointer is missing/invalid
        if version_dir is None:
            versions_dir = asset_dir / "versions"
            if versions_dir.exists():
                versions = sorted([d.name for d in versions_dir.iterdir() if d.is_dir()])
                if versions:
                    version_dir = versions_dir / versions[-1]

        if version_dir is None or not version_dir.exists():
            return None

        # Load the model
        model_path = version_dir / "model.joblib"
        if not model_path.exists():
            return None

        try:
            model = self._load_model(version_dir)
            self._cache[cache_key] = model
            return model
        except Exception as e:
            print(f"❌ Failed to load model from {model_path}: {e}")
            return None

    def save_and_activate(
        self,
        model: BaseTradingModel,
        asset: str,
        timeframe: str,
        metrics: Dict[str, Any],
        algorithm: str = "ensemble",
        model_key: str = "default",
    ) -> Dict[str, Any]:
        """Save model and set it as active for asset+timeframe+model_key.

        Args:
            model: Trained model (EnsembleModel or DirectionalClassifier)
            asset: Asset name (e.g. "AUD/CAD (OTC)")
            timeframe: Timeframe (e.g. "1m")
            metrics: Training metrics dict
            algorithm: Algorithm name for metadata
            model_key: Model identifier key (e.g. "kalman", "ensemble"), default "default"

        Returns:
            Dict with save results: {version, path, status}
        """
        asset_dir = self._get_asset_dir(asset, timeframe, model_key)
        asset_dir.mkdir(parents=True, exist_ok=True)

        # Create version directory with timestamp
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        version_dir = asset_dir / "versions" / timestamp
        version_dir.mkdir(parents=True, exist_ok=True)

        # Save model via joblib
        model_path = version_dir / "model.joblib"
        try:
            model.save(str(model_path))
        except Exception as e:
            return {"error": f"Failed to save model: {e}"}

        # Save metadata with type tags for explicit dispatch
        metadata = {
            "algorithm": algorithm,
            "model_class": type(model).__name__,
            "model_module": type(model).__module__,
            "asset": asset,
            "timeframe": timeframe,
            "version": timestamp,
            "trained_at": datetime.now().isoformat(),
            "feature_names": model._feature_names,
            "metrics": metrics,
        }
        metadata_path = version_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)

        # Atomically update active.json pointer
        active_file = asset_dir / "active.json"
        active_tmp = asset_dir / "active.json.tmp"
        active_data = {"active_version": timestamp}

        with open(active_tmp, 'w') as f:
            json.dump(active_data, f)
        os.replace(active_tmp, active_file)

        # Invalidate cache for this asset
        cache_key = f"{asset}_{timeframe}_{model_key}"
        if cache_key in self._cache:
            del self._cache[cache_key]

        return {
            "status": "saved",
            "version": timestamp,
            "path": str(model_path),
            "asset": asset,
            "timeframe": timeframe,
            "model_key": model_key,
        }

    def _load_model(self, version_dir) -> BaseTradingModel:
        """Load a model from disk by reading metadata and dispatching to correct loader.

        Args:
            version_dir: Path to the version directory (contains model.joblib and metadata.json)

        Returns:
            Loaded BaseTradingModel instance
        """
        if isinstance(version_dir, str):
            version_dir = Path(version_dir)

        model_path = version_dir / "model.joblib"
        metadata_path = version_dir / "metadata.json"

        # Try reading metadata for explicit type dispatch
        model_class_name = None
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    model_class_name = metadata.get("model_class")
            except (json.JSONDecodeError, IOError):
                pass

        # Use explicit type-tag dispatch if we have a class name in metadata
        if model_class_name and model_class_name in self._model_class_map:
            model_class = self._model_class_map[model_class_name]
            return model_class.load(str(model_path))

        # Fallback: try each class in priority order (for old metadata without type tags)
        # Try loading as ensemble first (most common)
        try:
            return EnsembleModel.load(str(model_path))
        except Exception:
            pass

        # Try loading as directional classifier
        try:
            return DirectionalClassifier.load(str(model_path))
        except Exception:
            pass

        # Try loading as gradient boosting classifier
        try:
            return GradientBoostingDirectionalModel.load(str(model_path))
        except Exception:
            pass

        # Try loading as gradient boosting regressor
        try:
            return GradientBoostingReturnModel.load(str(model_path))
        except Exception:
            pass

        # Try the new Phase A models
        try:
            return KalmanStateSpaceModel.load(str(model_path))
        except Exception:
            pass

        try:
            return ExpectedReturnModel.load(str(model_path))
        except Exception:
            pass

        try:
            return ProbabilityModel.load(str(model_path))
        except Exception:
            pass

        # Try Phase C models (regime classification)
        try:
            return RegimeClassifier.load(str(model_path))
        except Exception:
            pass

        try:
            return HMMRegimeModel.load(str(model_path))
        except Exception:
            pass

        raise ValueError(f"Unable to load model from {model_path} - unknown format")

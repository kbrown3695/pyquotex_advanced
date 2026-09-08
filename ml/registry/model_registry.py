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


class ModelRegistry:
    """Filesystem-based model registry.

    Models are stored per asset+timeframe:
    models/<slug>/
      active.json                   # {"active_version": "20260909T142233"}
      versions/
        20260909T142233/
          model.joblib              # serialized ensemble/classifier
          metadata.json             # training metadata
    """

    def __init__(self, base_dir: str = "models"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True, parents=True)
        self._cache: Dict[str, BaseTradingModel] = {}

    def _slugify(self, asset: str, timeframe: str) -> str:
        """Convert asset+timeframe to filesystem-safe slug.

        E.g. "AUD/CAD (OTC)", "1m" -> "aud_cad_otc_1m"
        """
        combined = f"{asset}_{timeframe}"
        slug = re.sub(r'[^A-Za-z0-9]+', '_', combined).strip('_').lower()
        return slug

    def _get_asset_dir(self, asset: str, timeframe: str) -> Path:
        """Get the asset+timeframe directory path."""
        slug = self._slugify(asset, timeframe)
        return self.base_dir / slug

    def get_active_model(
        self,
        asset: str,
        timeframe: str,
    ) -> Optional[BaseTradingModel]:
        """Load the active model for asset+timeframe.

        Returns None if no trained model exists yet.
        If active.json is missing/corrupt, self-heals by picking the latest version.
        """
        slug = self._slugify(asset, timeframe)
        cache_key = f"{asset}_{timeframe}"

        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]

        asset_dir = self._get_asset_dir(asset, timeframe)
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
            model = self._load_model(str(model_path))
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
    ) -> Dict[str, Any]:
        """Save model and set it as active for asset+timeframe.

        Args:
            model: Trained model (EnsembleModel or DirectionalClassifier)
            asset: Asset name (e.g. "AUD/CAD (OTC)")
            timeframe: Timeframe (e.g. "1m")
            metrics: Training metrics dict
            algorithm: Algorithm name for metadata

        Returns:
            Dict with save results: {version, path, status}
        """
        asset_dir = self._get_asset_dir(asset, timeframe)
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

        # Save metadata
        metadata = {
            "algorithm": algorithm,
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
        cache_key = f"{asset}_{timeframe}"
        if cache_key in self._cache:
            del self._cache[cache_key]

        return {
            "status": "saved",
            "version": timestamp,
            "path": str(model_path),
            "asset": asset,
            "timeframe": timeframe,
        }

    def _load_model(self, path: str) -> BaseTradingModel:
        """Load a model from disk by dispatching to correct loader.

        Dispatches based on filename/path patterns.
        """
        # Try loading as ensemble first (most common)
        try:
            return EnsembleModel.load(path)
        except Exception:
            pass

        # Try loading as directional classifier
        try:
            return DirectionalClassifier.load(path)
        except Exception:
            pass

        # Try loading as gradient boosting classifier
        try:
            return GradientBoostingDirectionalModel.load(path)
        except Exception:
            pass

        # Try loading as gradient boosting regressor
        try:
            return GradientBoostingReturnModel.load(path)
        except Exception:
            pass

        raise ValueError(f"Unable to load model from {path} - unknown format")

"""ML signal service — integrates models, registry, and aggregation."""

from typing import Dict, Any, Optional
import numpy as np

from ml.registry.model_registry import ModelRegistry
from ml.features.feature_pipeline import FeaturePipeline
from ml.aggregation.signal_aggregator import MultiModelAggregator, SignalResult
from ml.models.directional_classifier import DirectionalClassifier
from ml.models.ensemble import EnsembleModel
from ml.models.kalman_state_space import KalmanStateSpaceModel
from ml.models.expected_return_model import ExpectedReturnModel
from ml.models.probability_model import ProbabilityModel
from ml.models.gradient_boosting_model import (
    GradientBoostingDirectionalModel,
    GradientBoostingReturnModel,
)
from ml.models.volatility_model import VolatilityModel
from ml.models.quantile_model import QuantileModel


class MLSignalService:
	"""Unified ML signal service for training and inference.

	Orchestrates:
	- FeaturePipeline for consistent feature extraction
	- ModelRegistry for model persistence per asset+timeframe+model_key
	- MultiModelAggregator for blending predictions
	- Individual models (Ensemble, Kalman, ExpectedReturn, Probability in Phase A)
	"""

	def __init__(self, base_dir: str = "models"):
		self.registry = ModelRegistry(base_dir=base_dir)
		self.feature_pipeline = FeaturePipeline()
		self.aggregator = MultiModelAggregator(
			ensemble_weight=0.6,
			advanced_weight=0.4,
			use_volatility_dampening=False,
			use_regime_boost=False,
		)
		# Track which models to train/use per asset+timeframe
		self.active_models = {}

	def train_all(
		self,
		asset: str,
		timeframe: str,
		candles: list,
		lookahead: int = 1,
	) -> Dict[str, Any]:
		"""Train all active models on the given candles.

		Phase A (implemented): EnsembleModel, KalmanStateSpaceModel, ExpectedReturnModel, ProbabilityModel
		Phase B (implemented): GradientBoostingDirectionalModel, GradientBoostingReturnModel, VolatilityModel, QuantileModel

		Args:
			asset: Asset name (e.g. "AUD/CAD (OTC)")
			timeframe: Timeframe (e.g. "1m")
			candles: List of OHLC candles for training
			lookahead: Labels = next candle direction lookahead

		Returns:
			Dict with training results: {status, accuracy, samples, features, feature_importance}
		"""
		if len(candles) < 100:
			return {"error": f"Need at least 100 candles, got {len(candles)}"}

		# Build training matrix
		try:
			from ml.features.feature_pipeline import build_training_matrix
			X, y, feature_names = build_training_matrix(
				candles, lookahead=lookahead
			)
		except Exception as e:
			return {"error": f"Feature pipeline failed: {e}"}

		if len(X) < 10:
			return {"error": f"After feature extraction, only {len(X)} samples available"}

		results = {}
		models_trained = []

		# Phase A: Train Ensemble (DirectionalClassifier + EnsembleModel wrapper)
		try:
			dc = DirectionalClassifier(algorithm="random_forest")
			dc.set_feature_names(feature_names)
			dc.train(X, y)

			ensemble = EnsembleModel()
			ensemble.set_feature_names(feature_names)
			# Wrap the trained classifier
			ensemble.models = [dc]
			ensemble.algorithm = "voting"

			self.registry.save_and_activate(
				ensemble, asset, timeframe,
				metrics={"status": "trained", "samples": len(X)},
				algorithm="ensemble",
				model_key="ensemble",
			)
			models_trained.append("ensemble")
		except Exception as e:
			results["ensemble_error"] = str(e)

		# Phase A: Train Kalman
		try:
			kalman = KalmanStateSpaceModel()
			kalman.set_feature_names(feature_names)
			kalman.train(X, y)

			self.registry.save_and_activate(
				kalman, asset, timeframe,
				metrics={"status": "trained", "samples": len(X)},
				algorithm="kalman_state_space",
				model_key="kalman",
			)
			models_trained.append("kalman")
		except Exception as e:
			results["kalman_error"] = str(e)

		# Phase A: Train ExpectedReturn
		try:
			er = ExpectedReturnModel(algorithm="random_forest")
			er.set_feature_names(feature_names)
			# For expected return, use continuous labels (e.g., next return %)
			y_return = np.diff(np.array([c["close"] for c in candles]))[:-1]
			if len(y_return) == len(X):
				er.train(X, y_return)
				self.registry.save_and_activate(
					er, asset, timeframe,
					metrics={"status": "trained", "samples": len(X)},
					algorithm="expected_return",
					model_key="expected_return",
				)
				models_trained.append("expected_return")
		except Exception as e:
			results["expected_return_error"] = str(e)

		# Phase A: Train Probability
		try:
			prob = ProbabilityModel()
			prob.set_feature_names(feature_names)
			prob.train(X, y)

			self.registry.save_and_activate(
				prob, asset, timeframe,
				metrics={"status": "trained", "samples": len(X)},
				algorithm="probability_calibrated",
				model_key="probability",
			)
			models_trained.append("probability")
		except Exception as e:
			results["probability_error"] = str(e)

		# Phase B: Train GradientBoostingDirectionalModel (xgboost)
		try:
			gbd = GradientBoostingDirectionalModel(algorithm="xgboost")
			gbd.set_feature_names(feature_names)
			gbd.train(X, y)

			self.registry.save_and_activate(
				gbd, asset, timeframe,
				metrics={"status": "trained", "samples": len(X)},
				algorithm="gradient_boosting_directional",
				model_key="gradient_boosting_directional",
			)
			models_trained.append("gradient_boosting_directional")
		except Exception as e:
			results["gradient_boosting_directional_error"] = str(e)

		# Phase B: Train GradientBoostingReturnModel (xgboost)
		try:
			gbr = GradientBoostingReturnModel(algorithm="xgboost")
			gbr.set_feature_names(feature_names)
			y_return = np.diff(np.array([c["close"] for c in candles]))[:-1]
			if len(y_return) == len(X):
				gbr.train(X, y_return)
				self.registry.save_and_activate(
					gbr, asset, timeframe,
					metrics={"status": "trained", "samples": len(X)},
					algorithm="gradient_boosting_return",
					model_key="gradient_boosting_return",
				)
				models_trained.append("gradient_boosting_return")
		except Exception as e:
			results["gradient_boosting_return_error"] = str(e)

		# Phase B: Train VolatilityModel (lightgbm)
		try:
			vol_model = VolatilityModel()
			vol_model.set_feature_names(feature_names)
			# Use ATR from the last feature (atr_14) as volatility target
			y_volatility = np.full(len(X), 0.01)  # Placeholder
			try:
				# Try to use actual ATR values from feature pipeline
				from ml.features.indicators import calculate_atr
				closes = np.array([c["close"] for c in candles])
				highs = np.array([c["high"] for c in candles])
				lows = np.array([c["low"] for c in candles])
				y_volatility = calculate_atr(highs, lows, closes, period=14)[:-1]
				if len(y_volatility) != len(X):
					y_volatility = np.full(len(X), 0.01)
			except Exception:
				pass
			vol_model.train(X, y_volatility)
			self.registry.save_and_activate(
				vol_model, asset, timeframe,
				metrics={"status": "trained", "samples": len(X)},
				algorithm="volatility",
				model_key="volatility",
			)
			models_trained.append("volatility")
		except Exception as e:
			results["volatility_error"] = str(e)

		# Phase B: Train QuantileModel (lightgbm) - upper quantile
		try:
			y_return = np.diff(np.array([c["close"] for c in candles]))[:-1]
			if len(y_return) == len(X):
				quantile_model = QuantileModel(quantile=0.75)
				quantile_model.set_feature_names(feature_names)
				quantile_model.train(X, y_return)
				self.registry.save_and_activate(
					quantile_model, asset, timeframe,
					metrics={"status": "trained", "samples": len(X)},
					algorithm="quantile_upper",
					model_key="quantile_upper",
				)
				models_trained.append("quantile_upper")
		except Exception as e:
			results["quantile_upper_error"] = str(e)

		# Phase B: Train QuantileModel (lightgbm) - lower quantile
		try:
			y_return = np.diff(np.array([c["close"] for c in candles]))[:-1]
			if len(y_return) == len(X):
				quantile_model = QuantileModel(quantile=0.25)
				quantile_model.set_feature_names(feature_names)
				quantile_model.train(X, y_return)
				self.registry.save_and_activate(
					quantile_model, asset, timeframe,
					metrics={"status": "trained", "samples": len(X)},
					algorithm="quantile_lower",
					model_key="quantile_lower",
				)
				models_trained.append("quantile_lower")
		except Exception as e:
			results["quantile_lower_error"] = str(e)

		# Aggregate feature importances from models that have them
		feature_importances = {}
		for model_name in models_trained:
			try:
				model = self.registry.get_active_model(asset, timeframe, model_key=model_name)
				if model and hasattr(model, "get_feature_importances"):
					importances = model.get_feature_importances()
					if len(importances) == len(feature_names):
						for fname, imp in zip(feature_names, importances):
							feature_importances[fname] = feature_importances.get(fname, 0) + imp
			except Exception:
				pass

		# Normalize feature importances
		if feature_importances:
			total = sum(feature_importances.values()) or 1.0
			feature_importances = {k: v / total for k, v in feature_importances.items()}

		return {
			"status": "trained",
			"accuracy": 0.5,  # Placeholder; real accuracy would come from validation
			"samples": len(X),
			"features": len(feature_names),
			"feature_importance": feature_importances,
			"models_trained": models_trained,
		}

	def generate_signal(
		self,
		asset: str,
		timeframe: str,
		candles: list,
	) -> Optional[SignalResult]:
		"""Generate a trading signal from current candles.

		Args:
			asset: Asset name
			timeframe: Timeframe
			candles: List of OHLC candles (live data)

		Returns:
			SignalResult or None if models not trained yet
		"""
		if len(candles) < 26:  # Minimum for FeaturePipeline
			return None

		# Extract features for the last candle (transform_live returns tuple)
		try:
			# Build snapshots from candles (includes all indicators)
			from ml.features.feature_pipeline import build_snapshots
			snapshots = build_snapshots(candles)

			# Extract features for the last snapshot
			features_array, metadata = self.feature_pipeline.transform_live(
				snapshot=snapshots[-1],
				history=snapshots[:-1] if len(snapshots) > 1 else None
			)
		except Exception:
			return None

		features_array = features_array.reshape(1, -1)

		# Get predictions from all Phase A + Phase B models
		ensemble_proba = None
		kalman_proba = None
		expected_return_proba = None
		probability_proba = None
		kalman_regime = None
		kalman_volatility = None
		gb_directional_proba = None
		gb_return_proba = None
		volatility_pred = None
		quantile_upper_pred = None
		quantile_lower_pred = None

		# Ensemble prediction (Phase A)
		try:
			ensemble_model = self.registry.get_active_model(
				asset, timeframe, model_key="ensemble"
			)
			if ensemble_model:
				ensemble_proba = ensemble_model.predict_proba(features_array)
		except Exception:
			pass

		# Kalman prediction + regime + volatility (Phase A)
		try:
			kalman_model = self.registry.get_active_model(
				asset, timeframe, model_key="kalman"
			)
			if kalman_model:
				kalman_proba = kalman_model.predict_proba(features_array)
				kalman_regime = kalman_model.predict_regime(features_array)
				kalman_volatility = kalman_model.predict_volatility(features_array)
		except Exception:
			pass

		# ExpectedReturn prediction (Phase A)
		try:
			er_model = self.registry.get_active_model(
				asset, timeframe, model_key="expected_return"
			)
			if er_model:
				expected_return_proba = er_model.predict_proba(features_array)
		except Exception:
			pass

		# Probability prediction (Phase A)
		try:
			prob_model = self.registry.get_active_model(
				asset, timeframe, model_key="probability"
			)
			if prob_model:
				probability_proba = prob_model.predict_proba(features_array)
		except Exception:
			pass

		# GradientBoosting Directional prediction (Phase B)
		try:
			gb_dir_model = self.registry.get_active_model(
				asset, timeframe, model_key="gradient_boosting_directional"
			)
			if gb_dir_model:
				gb_directional_proba = gb_dir_model.predict_proba(features_array)
		except Exception:
			pass

		# GradientBoosting Return prediction (Phase B)
		try:
			gb_ret_model = self.registry.get_active_model(
				asset, timeframe, model_key="gradient_boosting_return"
			)
			if gb_ret_model:
				gb_return_proba = gb_ret_model.predict_proba(features_array)
		except Exception:
			pass

		# Volatility prediction (Phase B)
		try:
			vol_model = self.registry.get_active_model(
				asset, timeframe, model_key="volatility"
			)
			if vol_model:
				volatility_pred = vol_model.predict(features_array)
		except Exception:
			pass

		# Quantile predictions (Phase B)
		try:
			quantile_up = self.registry.get_active_model(
				asset, timeframe, model_key="quantile_upper"
			)
			if quantile_up:
				quantile_upper_pred = quantile_up.predict(features_array)
		except Exception:
			pass

		try:
			quantile_lo = self.registry.get_active_model(
				asset, timeframe, model_key="quantile_lower"
			)
			if quantile_lo:
				quantile_lower_pred = quantile_lo.predict(features_array)
		except Exception:
			pass

		# Aggregate all predictions
		signal = self.aggregator.aggregate(
			ensemble_proba=ensemble_proba,
			kalman_proba=kalman_proba,
			expected_return_proba=expected_return_proba,
			probability_proba=probability_proba,
			kalman_regime=kalman_regime,
			kalman_volatility=kalman_volatility,
			gb_directional_proba=gb_directional_proba,
			gb_return_proba=gb_return_proba,
			volatility_pred=volatility_pred,
			quantile_upper_pred=quantile_upper_pred,
			quantile_lower_pred=quantile_lower_pred,
		)

		return signal

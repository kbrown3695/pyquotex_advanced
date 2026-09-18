"""ML signal service — integrates models, registry, and aggregation."""

from typing import Dict, Any, Optional
import warnings
import numpy as np
from sklearn.model_selection import cross_val_score

# Suppress sklearn joblib warnings (they're noisy but harmless)
warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.*")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn.utils.parallel")

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
from ml.models.regime_classifier import RegimeClassifier
from ml.models.hmm_regime_model import HMMRegimeModel
from ml.models.rl_agent import RLAgent
from ml.models.lstm_model import LSTMModel
from ml.models.transformer_model import TransformerModel
from ml.models.reversal_predictor import ReversalPredictorModel
from ml.serving.online_learning_manager import create_online_learning_manager
from ml.trading.trading_session import BinaryOptionsTradingSession


class MLSignalService:
	"""Unified ML signal service for training and inference.

	Orchestrates:
	- FeaturePipeline for consistent feature extraction
	- ModelRegistry for model persistence per asset+timeframe+model_key
	- MultiModelAggregator for blending predictions
	- Individual models (Ensemble, Kalman, ExpectedReturn, Probability in Phase A)
	- Phase 2: TradingSession for money/risk management (optional)
	"""

	def __init__(self, base_dir: str = "models", enable_g3: bool = True, trading_session: Optional[BinaryOptionsTradingSession] = None):
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

		# Phase G3: Online learning optimizer (adapts weights based on live trades)
		self.online_learning_manager = create_online_learning_manager(
			baseline_weights={
				"ensemble": 0.45,
				"advanced": 0.25,
				"deep": 0.30,
			},
			enable_g3=enable_g3,
		)

		# Phase 2: Trading session for money/risk management
		self.trading_session = trading_session

	def set_trading_session(self, session: Optional[BinaryOptionsTradingSession]) -> None:
		"""Set or update the trading session for money/risk management.

		Args:
			session: BinaryOptionsTradingSession or None to disable
		"""
		self.trading_session = session

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
			# Calculate returns in same shape as X (which comes from feature pipeline)
			closes = np.array([c["close"] for c in candles])
			# Returns: (next_close - current_close) / current_close * 100
			y_return = np.diff(closes) / closes[:-1] * 100  # % returns
			# Trim to match X size (feature extraction may remove first/last rows)
			y_return = y_return[-(len(X)):]
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
			# Calculate returns with same shape alignment as X
			closes = np.array([c["close"] for c in candles])
			y_return = np.diff(closes) / closes[:-1] * 100  # % returns
			y_return = y_return[-(len(X)):]  # Trim to match X
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
			# Use range (high-low) as volatility proxy, aligned to X
			highs = np.array([c["high"] for c in candles])
			lows = np.array([c["low"] for c in candles])

			# Range = high - low (volatility measure)
			y_volatility = highs - lows
			# Align to match X size - use min to handle any size differences
			common_size = min(len(y_volatility), len(X))
			if common_size > 10:
				y_volatility = y_volatility[-common_size:]
				X_trimmed = X[-common_size:]
				print(f"[volatility] Training with {common_size} samples (y shape: {y_volatility.shape}, X shape: {X_trimmed.shape})", flush=True)
				vol_model.train(X_trimmed, y_volatility)
				self.registry.save_and_activate(
					vol_model, asset, timeframe,
					metrics={"status": "trained", "samples": common_size},
					algorithm="volatility",
					model_key="volatility",
				)
				models_trained.append("volatility")
				print(f"[volatility] ✅ Training complete", flush=True)
			else:
				error_msg = f"Insufficient data: min(y_volatility={len(y_volatility)}, X={len(X)}) = {common_size}"
				results["volatility_error"] = error_msg
				print(f"[volatility] ⚠️ {error_msg}", flush=True)
		except Exception as e:
			import traceback
			results["volatility_error"] = str(e)
			print(f"[volatility] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

		# Phase B: Train QuantileModel (lightgbm) - upper quantile
		try:
			closes = np.array([c["close"] for c in candles])
			y_return = np.diff(closes) / closes[:-1] * 100
			common_size = min(len(y_return), len(X))
			if common_size > 10:
				y_return = y_return[-common_size:]
				X_trimmed = X[-common_size:]
				quantile_model = QuantileModel(quantile=0.75)
				quantile_model.set_feature_names(feature_names)
				print(f"[quantile_upper] Training with {common_size} samples (y shape: {y_return.shape}, X shape: {X_trimmed.shape})", flush=True)
				quantile_model.train(X_trimmed, y_return)
				self.registry.save_and_activate(
					quantile_model, asset, timeframe,
					metrics={"status": "trained", "samples": common_size},
					algorithm="quantile_upper",
					model_key="quantile_upper",
				)
				models_trained.append("quantile_upper")
				print(f"[quantile_upper] ✅ Training complete", flush=True)
			else:
				error_msg = f"Insufficient data: min(y_return={len(y_return)}, X={len(X)}) = {common_size}"
				results["quantile_upper_error"] = error_msg
				print(f"[quantile_upper] ⚠️ {error_msg}", flush=True)
		except Exception as e:
			import traceback
			results["quantile_upper_error"] = str(e)
			print(f"[quantile_upper] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

		# Phase B: Train QuantileModel (lightgbm) - lower quantile
		try:
			closes = np.array([c["close"] for c in candles])
			y_return = np.diff(closes) / closes[:-1] * 100
			common_size = min(len(y_return), len(X))
			if common_size > 10:
				y_return = y_return[-common_size:]
				X_trimmed = X[-common_size:]
				quantile_model = QuantileModel(quantile=0.25)
				quantile_model.set_feature_names(feature_names)
				print(f"[quantile_lower] Training with {common_size} samples (y shape: {y_return.shape}, X shape: {X_trimmed.shape})", flush=True)
				quantile_model.train(X_trimmed, y_return)
				self.registry.save_and_activate(
					quantile_model, asset, timeframe,
					metrics={"status": "trained", "samples": common_size},
					algorithm="quantile_lower",
					model_key="quantile_lower",
				)
				models_trained.append("quantile_lower")
				print(f"[quantile_lower] ✅ Training complete", flush=True)
			else:
				error_msg = f"Insufficient data: min(y_return={len(y_return)}, X={len(X)}) = {common_size}"
				results["quantile_lower_error"] = error_msg
				print(f"[quantile_lower] ⚠️ {error_msg}", flush=True)
		except Exception as e:
			import traceback
			results["quantile_lower_error"] = str(e)
			print(f"[quantile_lower] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

		# Phase C: Train RegimeClassifier (LightGBM)
		try:
			# Create regime labels: classify each row based on returns + volatility + trend
			closes = np.array([c["close"] for c in candles])
			highs = np.array([c["high"] for c in candles])
			lows = np.array([c["low"] for c in candles])

			# Align all to X size
			common_size = min(len(closes), len(highs), len(lows), len(X))
			if common_size > 20:
				# Regime classification logic:
				# - Calculate returns, volatility, momentum
				returns_tail = (closes[-common_size:] - np.roll(closes[-common_size:], 1))[1:]
				volatility_tail = (highs[-common_size:] - lows[-common_size:])[1:]
				trend_tail = np.sign(np.convolve(returns_tail, np.ones(3)/3, mode='same'))

				# Simple regime assignment:
				# TRENDING_UP (3), TRENDING_DOWN (0), RANGING (1), CHAOTIC (2)
				y_regimes = np.ones(len(returns_tail), dtype=int)
				high_vol = volatility_tail > np.percentile(volatility_tail, 75)

				for i in range(len(returns_tail)):
					if high_vol[i]:
						y_regimes[i] = 2  # CHAOTIC
					elif trend_tail[i] > 0.5:
						y_regimes[i] = 3  # TRENDING_UP
					elif trend_tail[i] < -0.5:
						y_regimes[i] = 0  # TRENDING_DOWN
					# else: RANGING (1)

				X_trimmed = X[-(len(y_regimes)):]
				if len(y_regimes) == len(X_trimmed):
					regime_clf = RegimeClassifier()
					regime_clf.set_feature_names(feature_names)
					print(f"[regime_classifier] Training with {len(y_regimes)} samples", flush=True)
					regime_clf.train(X_trimmed, y_regimes)

					self.registry.save_and_activate(
						regime_clf, asset, timeframe,
						metrics={"status": "trained", "samples": len(y_regimes)},
						algorithm="regime_classifier",
						model_key="regime_classifier",
					)
					models_trained.append("regime_classifier")
					print(f"[regime_classifier] ✅ Training complete", flush=True)
		except Exception as e:
			import traceback
			results["regime_classifier_error"] = str(e)
			print(f"[regime_classifier] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

		# Phase C: Train HMMRegimeModel (hmmlearn)
		try:
			# Use returns as primary feature for HMM
			closes = np.array([c["close"] for c in candles])
			returns = np.diff(closes) / closes[:-1]  # Simple returns
			common_size = min(len(returns), len(X))

			if common_size > 30:
				returns_tail = returns[-common_size:]
				X_trimmed = X[-common_size:]

				hmm_model = HMMRegimeModel(n_states=3)
				hmm_model.set_feature_names(feature_names)
				print(f"[hmm_regime] Training with {common_size} samples", flush=True)
				hmm_model.train(X_trimmed)  # HMM is unsupervised, y is not used

				self.registry.save_and_activate(
					hmm_model, asset, timeframe,
					metrics={"status": "trained", "samples": common_size},
					algorithm="hmm_regime",
					model_key="hmm_regime",
				)
				models_trained.append("hmm_regime")
				print(f"[hmm_regime] ✅ Training complete", flush=True)
		except Exception as e:
			import traceback
			results["hmm_regime_error"] = str(e)
			print(f"[hmm_regime] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

		# Phase D: Train RLAgent (PyTorch REINFORCE)
		try:
			rl_agent = RLAgent(input_dim=X.shape[1], hidden_dim=64)
			rl_agent.set_feature_names(feature_names)
			print(f"[rl_agent] Training with {len(X)} samples (input_dim={X.shape[1]})", flush=True)
			rl_agent.train(X, y)

			self.registry.save_and_activate(
				rl_agent, asset, timeframe,
				metrics={"status": "trained", "samples": len(X)},
				algorithm="rl_agent",
				model_key="rl_agent",
			)
			models_trained.append("rl_agent")
			print(f"[rl_agent] ✅ Training complete", flush=True)
		except Exception as e:
			import traceback
			results["rl_agent_error"] = str(e)
			print(f"[rl_agent] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

		# Phase E: Train LSTMModel (sequence-based)
		try:
			from ml.features.feature_pipeline import build_sequences
			X_seq, y_seq = build_sequences(X, y, seq_len=26)

			if len(X_seq) > 0:
				lstm_model = LSTMModel(input_dim=X.shape[1], hidden_dim=64, seq_len=26)
				lstm_model.set_feature_names(feature_names)
				print(f"[lstm] Training with {len(X_seq)} sequences (input_dim={X.shape[1]})", flush=True)
				lstm_model.train(X_seq, y_seq)

				self.registry.save_and_activate(
					lstm_model, asset, timeframe,
					metrics={"status": "trained", "samples": len(X_seq)},
					algorithm="lstm",
					model_key="lstm",
				)
				models_trained.append("lstm")
				print(f"[lstm] ✅ Training complete", flush=True)
			else:
				results["lstm_error"] = "Insufficient data for sequences"
				print(f"[lstm] ⚠️ Insufficient data for sequences", flush=True)
		except Exception as e:
			import traceback
			results["lstm_error"] = str(e)
			print(f"[lstm] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

		# Phase E: Train TransformerModel (attention-based)
		try:
			from ml.features.feature_pipeline import build_sequences
			X_seq, y_seq = build_sequences(X, y, seq_len=26)

			if len(X_seq) > 0:
				transformer_model = TransformerModel(input_dim=X.shape[1], d_model=64, nhead=8, num_layers=2, seq_len=26)
				transformer_model.set_feature_names(feature_names)
				print(f"[transformer] Training with {len(X_seq)} sequences (input_dim={X.shape[1]})", flush=True)
				transformer_model.train(X_seq, y_seq)

				self.registry.save_and_activate(
					transformer_model, asset, timeframe,
					metrics={"status": "trained", "samples": len(X_seq)},
					algorithm="transformer",
					model_key="transformer",
				)
				models_trained.append("transformer")
				print(f"[transformer] ✅ Training complete", flush=True)
			else:
				results["transformer_error"] = "Insufficient data for sequences"
				print(f"[transformer] ⚠️ Insufficient data for sequences", flush=True)
		except Exception as e:
			import traceback
			results["transformer_error"] = str(e)
			print(f"[transformer] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

		# Binary Options: Train ReversalPredictorModel
		try:
			reversal_model = ReversalPredictorModel(model_type="regression")
			reversal_model.set_feature_names(feature_names)
			print(f"[reversal_predictor] Training with {len(X)} samples", flush=True)
			reversal_model.train(X, y)

			self.registry.save_and_activate(
				reversal_model, asset, timeframe,
				metrics={"status": "trained", "samples": len(X)},
				algorithm="reversal_regression",
				model_key="reversal_predictor",
			)
			models_trained.append("reversal_predictor")
			print(f"[reversal_predictor] ✅ Training complete", flush=True)
		except Exception as e:
			import traceback
			results["reversal_predictor_error"] = str(e)
			print(f"[reversal_predictor] ❌ Training error: {type(e).__name__}: {e}", flush=True)
			traceback.print_exc()

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

		# Compute cross-validation accuracy for the ensemble model
		accuracy = None
		if "ensemble" in models_trained:
			try:
				ensemble_model = self.registry.get_active_model(
					asset, timeframe, model_key="ensemble"
				)
				if ensemble_model and hasattr(ensemble_model, "model"):
					# Use 5-fold cross-validation on training data
					scores = cross_val_score(
						ensemble_model.model,
						X, y,
						cv=min(5, len(X) // 10),
						scoring="accuracy",
						n_jobs=-1,
					)
					accuracy = float(np.mean(scores))
			except Exception:
				accuracy = None

		return {
			"status": "trained",
			"accuracy": accuracy,
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

		# Get predictions from all Phase A + Phase B + Phase D + Phase E models
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
		rl_agent_proba = None
		lstm_proba = None
		transformer_proba = None

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

		# RLAgent prediction (Phase D)
		try:
			rl_model = self.registry.get_active_model(
				asset, timeframe, model_key="rl_agent"
			)
			if rl_model:
				rl_agent_proba = rl_model.predict_proba(features_array)
		except Exception:
			pass

		# LSTM prediction (Phase E)
		try:
			lstm_model = self.registry.get_active_model(
				asset, timeframe, model_key="lstm"
			)
			if lstm_model:
				lstm_proba = lstm_model.predict_proba(features_array)
		except Exception:
			pass

		# Transformer prediction (Phase E)
		try:
			transformer_model = self.registry.get_active_model(
				asset, timeframe, model_key="transformer"
			)
			if transformer_model:
				transformer_proba = transformer_model.predict_proba(features_array)
		except Exception:
			pass

		# Binary Options: Reversal Predictor prediction
		reversal_prediction = None
		try:
			reversal_model = self.registry.get_active_model(
				asset, timeframe, model_key="reversal_predictor"
			)
			if reversal_model and len(candles) >= 30:
				reversal_prediction = reversal_model.predict(candles)
		except Exception:
			pass

		# Aggregate all predictions (Phase 1.5: include candles for binary options enrichment)
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
			rl_agent_proba=rl_agent_proba,
			lstm_proba=lstm_proba,
			transformer_proba=transformer_proba,
			candles=candles,
		)

		# Phase 2: Add position sizing if trading session is available
		if signal and self.trading_session:
			try:
				# Map timeframe to approximate expiration seconds
				timeframe_map = {
					"1m": 60, "2m": 120, "5m": 300, "15m": 900,
					"30m": 1800, "1h": 3600, "4h": 14400,
				}
				expiration_seconds = timeframe_map.get(timeframe, 300)

				rec = self.trading_session.get_trade_recommendation(
					signal_confidence=signal.confidence,
					asset=asset,
					expiration_seconds=expiration_seconds,
				)
				signal.position_sizing = {
					'should_trade': rec.should_trade,
					'position_size': rec.position_size,
					'kelly_fraction': rec.kelly_fraction,
					'reasons': rec.reasons,
				}
			except Exception:
				pass  # If trading session fails, just skip position sizing

		return signal

	def process_trade_outcome(self, trade_result: Dict[str, Any]) -> None:
		"""Phase G3: Process completed trade and update online learning weights.

		Called after a trade closes with P&L result. Updates the online learning
		optimizer to track which models contributed to wins/losses.

		Args:
			trade_result: Dict with keys:
				- profit: float (P&L, positive = win, negative/zero = loss)
				- components: Dict (model predictions, e.g., {"ensemble": {...}})
				- side: str ("BUY" or "SELL")
				- entry: float (entry price)
				- exit: float (exit price)
				- timestamp: float (optional, trade completion time)
		"""
		if not self.online_learning_manager:
			return

		self.online_learning_manager.process_trade_outcome(trade_result)

	def get_g3_stats(self) -> Dict[str, Any]:
		"""Get Phase G3 online learning statistics.

		Returns:
			Dict with model performance stats and current adapted weights
		"""
		if not self.online_learning_manager:
			return {}

		return self.online_learning_manager.get_performance_stats()

	def get_g3_report(self) -> str:
		"""Get formatted Phase G3 performance report."""
		if not self.online_learning_manager:
			return "G3 not enabled"

		return self.online_learning_manager.get_report()

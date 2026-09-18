"""Multi-model signal aggregation for Phase A and beyond.

Combines outputs from multiple models (directional classifiers, regime detectors,
volatility estimators) into a single calibrated trading signal.
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np


class SignalResult:
	"""Structured trading signal output, matching ml_signals.py contract."""

	def __init__(
		self,
		side: str,
		confidence: float,
		reason: str,
		method: str = "ensemble",
		components: Optional[Dict[str, Any]] = None,
		timestamp: Optional[float] = None,
		binary_options_features: Optional[Dict[str, Any]] = None,
		confidence_by_expiration: Optional[Dict[str, float]] = None,
		safe_expirations: Optional[List[str]] = None,
		position_sizing: Optional[Dict[str, Any]] = None,
	):
		self.side = side  # 'BUY' or 'SELL'
		self.confidence = max(0.0, min(1.0, confidence))
		self.reason = reason
		self.method = method
		self.components = components or {}
		self.timestamp = timestamp
		self.binary_options_features = binary_options_features or {}
		self.confidence_by_expiration = confidence_by_expiration or {}
		self.safe_expirations = safe_expirations or []
		self.position_sizing = position_sizing or {}

	def to_dict(self) -> Dict[str, Any]:
		"""Convert to JSON-serializable dict, matching ml_signals.py::SignalResult.to_dict()."""
		import time
		result = {
			"side": self.side,
			"confidence": round(self.confidence, 3),
			"reason": self.reason,
			"method": self.method,
			"components": self.components,
			"timestamp": self.timestamp or time.time(),
		}

		# Add binary options features if available
		if self.binary_options_features:
			result["binary_options"] = {
				"time_to_reversal_seconds": self.binary_options_features.get("time_to_reversal_seconds", 0),
				"reversal_probability": round(self.binary_options_features.get("reversal_probability", 0), 3),
				"momentum_velocity": round(self.binary_options_features.get("momentum_velocity", 0), 6),
				"volatility_percentile": round(self.binary_options_features.get("volatility_percentile", 0), 1),
				"support_level": self.binary_options_features.get("support_level", 0),
				"resistance_level": self.binary_options_features.get("resistance_level", 0),
			}

		if self.confidence_by_expiration:
			result["confidence_by_expiration"] = {
				k: round(v, 3) for k, v in self.confidence_by_expiration.items()
			}

		if self.safe_expirations:
			result["safe_expirations"] = self.safe_expirations

		# Add position sizing if available (Phase 2)
		if self.position_sizing:
			result["position_sizing"] = {
				"should_trade": self.position_sizing.get("should_trade", False),
				"position_size": round(self.position_sizing.get("position_size", 0), 2),
				"kelly_fraction": round(self.position_sizing.get("kelly_fraction", 0), 4),
				"reasons": self.position_sizing.get("reasons", []),
			}

		return result


class MultiModelAggregator:
	"""Aggregates predictions from multiple models into a single signal.

	Phase A: Supports DirectionalClassifier, EnsembleModel, Kalman, ExpectedReturn, Probability.
	Phase B+: adds volatility, quantile, regime, RL, sequence nets.
	Phase F: Optimized weights with regime-specific tuning.
	"""

	def __init__(
		self,
		ensemble_weight: float = 0.45,
		advanced_weight: float = 0.25,
		deep_weight: float = 0.30,
		use_volatility_dampening: bool = True,
		use_regime_boost: bool = True,
		use_regime_weights: bool = True,
		use_weight_smoothing: bool = False,
		weight_smoother = None,
	):
		"""Initialize aggregator with Phase F optimized weights.

		Args:
			ensemble_weight: Weight for sklearn ensemble (0-1), default 0.45 (Phase F)
			advanced_weight: Weight for advanced models (0-1), default 0.25 (Phase F)
			deep_weight: Weight for deep learning models (0-1), default 0.30 (Phase F)
			use_volatility_dampening: Whether to dampen on high volatility (Phase B+)
			use_regime_boost: Whether to boost/dampen by regime (Phase C+)
			use_regime_weights: Whether to use regime-specific weights (Phase F)
			use_weight_smoothing: Whether to smooth weight transitions (Phase G2)
			weight_smoother: Optional KalmanWeightSmoother instance (Phase G2)
		"""
		# Normalize layer weights
		total_weight = ensemble_weight + advanced_weight + deep_weight
		self.ensemble_weight = ensemble_weight / total_weight
		self.advanced_weight = advanced_weight / total_weight
		self.deep_weight = deep_weight / total_weight
		self.use_volatility_dampening = use_volatility_dampening
		self.use_regime_boost = use_regime_boost
		self.use_regime_weights = use_regime_weights
		self.use_weight_smoothing = use_weight_smoothing
		self.weight_smoother = weight_smoother

		# Phase F: Regime-specific weight configurations
		self.regime_weights = self._get_regime_weights()

		# Phase 1.5: Binary options feature engineering
		try:
			from ml.features.binary_options_features import BinaryOptionsFeatureEngineer
			self.bo_engineer = BinaryOptionsFeatureEngineer()
		except (ImportError, ModuleNotFoundError):
			self.bo_engineer = None

	def _get_regime_weights(self) -> Dict[str, Dict[str, float]]:
		"""Return regime-specific weight configurations for Phase F optimization."""
		return {
			"default": {
				"ensemble": 0.45,
				"advanced": 0.25,
				"deep": 0.30,
			},
			"trending_up": {
				"ensemble": 0.50,
				"advanced": 0.20,
				"deep": 0.30,
				"rl_agent": 0.60,
				"lstm": 0.65,
			},
			"trending_down": {
				"ensemble": 0.50,
				"advanced": 0.20,
				"deep": 0.30,
				"rl_agent": 0.60,
				"lstm": 0.65,
			},
			"ranging": {
				"ensemble": 0.30,
				"advanced": 0.40,
				"deep": 0.30,
				"kalman": 0.45,
				"probability": 0.30,
				"transformer": 0.60,
			},
			"chaotic": {
				"ensemble": 0.60,
				"advanced": 0.20,
				"deep": 0.20,
				"rl_agent": 0.10,
				"lstm": 0.60,
			},
		}

	def blend_ensemble(self, ensemble_proba: np.ndarray) -> Tuple[float, Dict[str, Any]]:
		"""Extract and store sklearn ensemble prediction.

		Args:
			ensemble_proba: (n_samples, 2) array with [P(down), P(up)]

		Returns:
			Tuple of (p_up_single_sample, components_dict)
		"""
		if ensemble_proba is None or len(ensemble_proba) == 0:
			return 0.5, {"ensemble": None}

		p_up = float(ensemble_proba[-1, 1])
		return p_up, {"ensemble": {"p_up": p_up}}

	def blend_advanced(
		self,
		kalman_proba: Optional[np.ndarray] = None,
		expected_return_proba: Optional[np.ndarray] = None,
		probability_proba: Optional[np.ndarray] = None,
		rl_agent_proba: Optional[np.ndarray] = None,
		kalman_weight: float = 0.30,
		expected_return_weight: float = 0.25,
		probability_weight: float = 0.25,
		rl_agent_weight: float = 0.20,
		regime_key: Optional[str] = None,
	) -> Tuple[float, Dict[str, Any]]:
		"""Blend advanced (non-sklearn) model predictions with configurable weights.

		Args:
			kalman_proba: (n_samples, 2) Kalman predict_proba output
			expected_return_proba: (n_samples, 3) ExpectedReturn placeholder output
			probability_proba: (n_samples, 2) Probability calibrated output
			rl_agent_proba: (n_samples, 2) RLAgent policy predictions (Phase D+)
			kalman_weight: relative weight for Kalman (0-1), default 0.30 (Phase F)
			expected_return_weight: relative weight for ExpectedReturn (0-1), default 0.25 (Phase F)
			probability_weight: relative weight for Probability (0-1), default 0.25 (Phase F)
			rl_agent_weight: relative weight for RLAgent (0-1), default 0.20 (Phase F)
			regime_key: optional regime key for regime-specific weights

		Returns:
			Tuple of (blended_p_up, components_dict)
		"""
		components = {}

		# Apply regime-specific weights if provided (Phase F)
		if regime_key and regime_key in self.regime_weights:
			regime_cfg = self.regime_weights[regime_key]
			if "kalman" in regime_cfg:
				kalman_weight = regime_cfg["kalman"]
			if "probability" in regime_cfg:
				probability_weight = regime_cfg["probability"]
			if "rl_agent" in regime_cfg:
				rl_agent_weight = regime_cfg["rl_agent"]

		weights_sum = kalman_weight + expected_return_weight + probability_weight + rl_agent_weight

		if weights_sum == 0:
			return 0.5, components

		# Normalize weights
		k_w = kalman_weight / weights_sum
		e_w = expected_return_weight / weights_sum
		p_w = probability_weight / weights_sum
		r_w = rl_agent_weight / weights_sum

		p_up_sum = 0.0
		count = 0

		if kalman_proba is not None and len(kalman_proba) > 0:
			p_up = float(kalman_proba[-1, 1])
			p_up_sum += k_w * p_up
			count += 1
			components["kalman"] = {"p_up": p_up}

		if expected_return_proba is not None and len(expected_return_proba) > 0:
			# ExpectedReturn returns (n, 3) uniform placeholder; extract middle value
			p_up = float(expected_return_proba[-1, 1])
			p_up_sum += e_w * p_up
			count += 1
			components["expected_return"] = {"p_up": p_up}

		if probability_proba is not None and len(probability_proba) > 0:
			p_up = float(probability_proba[-1, 1])
			p_up_sum += p_w * p_up
			count += 1
			components["probability"] = {"p_up": p_up}

		if rl_agent_proba is not None and len(rl_agent_proba) > 0:
			p_up = float(rl_agent_proba[-1, 1])
			p_up_sum += r_w * p_up
			count += 1
			components["rl_agent"] = {"p_up": p_up}

		if count == 0:
			return 0.5, components

		return p_up_sum, components

	def enrich_signal_with_binary_options(
		self,
		signal: SignalResult,
		candles: Optional[List[Dict[str, Any]]] = None,
	) -> SignalResult:
		"""Enrich signal with binary options timing features.

		Args:
			signal: Base signal from ensemble models
			candles: Recent candle history

		Returns:
			Signal with binary options features added
		"""
		if not self.bo_engineer or not candles or len(candles) < 20:
			return signal

		try:
			# Extract binary options features
			bo_features = self.bo_engineer.extract(candles)

			# Calculate expiration-optimized confidence
			confidence_by_expiration = {
				"1m": self._adjust_confidence_for_expiration(signal.confidence, bo_features, 60),
				"2m": self._adjust_confidence_for_expiration(signal.confidence, bo_features, 120),
				"5m": self._adjust_confidence_for_expiration(signal.confidence, bo_features, 300),
				"15m": self._adjust_confidence_for_expiration(signal.confidence, bo_features, 900),
			}

			# Determine safe expirations
			safe_expirations = []
			if bo_features.safe_for_1m:
				safe_expirations.append("1m")
			if bo_features.safe_for_2m:
				safe_expirations.append("2m")
			if bo_features.safe_for_5m:
				safe_expirations.append("5m")
			if bo_features.safe_for_15m:
				safe_expirations.append("15m")

			# Create new signal result with BO features
			enriched_signal = SignalResult(
				side=signal.side,
				confidence=signal.confidence,
				reason=signal.reason,
				method=signal.method,
				components=signal.components,
				timestamp=signal.timestamp,
				binary_options_features={
					"time_to_reversal_seconds": bo_features.time_to_reversal_seconds,
					"reversal_probability": bo_features.reversal_probability,
					"momentum_velocity": bo_features.momentum_velocity,
					"volatility_percentile": bo_features.volatility_percentile,
					"support_level": bo_features.support_level,
					"resistance_level": bo_features.resistance_level,
				},
				confidence_by_expiration=confidence_by_expiration,
				safe_expirations=safe_expirations,
			)

			return enriched_signal

		except Exception as e:
			# If BO feature extraction fails, return original signal
			import logging
			logging.warning(f"Binary options enrichment failed: {e}")
			return signal

	def _adjust_confidence_for_expiration(
		self,
		base_confidence: float,
		bo_features,
		expiration_seconds: int,
	) -> float:
		"""Adjust confidence based on reversal risk for expiration time.

		Args:
			base_confidence: Model confidence (0-1)
			bo_features: Binary options features
			expiration_seconds: Expiration time in seconds (60, 120, 300, 900)

		Returns:
			Adjusted confidence for this expiration time
		"""
		# If reversal likely before expiration, reduce confidence
		time_to_reversal = bo_features.time_to_reversal_seconds
		reversal_prob = bo_features.reversal_probability

		if time_to_reversal < expiration_seconds:
			# Reversal risk within expiration window
			# Reduce confidence by reversal probability
			adjusted = base_confidence * (1.0 - reversal_prob * 0.5)
		else:
			# Reversal unlikely before expiration
			# Keep confidence, maybe slightly boost
			adjusted = base_confidence * (1.0 + bo_features.time_of_day_weight * 0.1)

		return max(0.3, min(0.95, adjusted))  # Clamp to reasonable range

	def aggregate(
		self,
		ensemble_proba: Optional[np.ndarray] = None,
		kalman_proba: Optional[np.ndarray] = None,
		expected_return_proba: Optional[np.ndarray] = None,
		probability_proba: Optional[np.ndarray] = None,
		kalman_regime: Optional[Tuple] = None,
		kalman_volatility: Optional[float] = None,
		gb_directional_proba: Optional[np.ndarray] = None,
		gb_return_proba: Optional[np.ndarray] = None,
		volatility_pred: Optional[np.ndarray] = None,
		quantile_upper_pred: Optional[np.ndarray] = None,
		quantile_lower_pred: Optional[np.ndarray] = None,
		rl_agent_proba: Optional[np.ndarray] = None,
		lstm_proba: Optional[np.ndarray] = None,
		transformer_proba: Optional[np.ndarray] = None,
		override_regime_key: Optional[str] = None,
		candles: Optional[List[Dict[str, Any]]] = None,
	) -> SignalResult:
		"""Aggregate all model outputs into a single SignalResult.

		Phase A: uses ensemble + advanced (Kalman, ExpectedReturn, Probability)
		Phase B: adds gradient boosting models + volatility/quantile dampening
		Phase C: adds regime classification and HMM
		Phase D: adds RLAgent policy gradient predictions
		Phase E: adds LSTM and Transformer sequence models
		Phase F: adds regime-specific weight optimization
		Phase G1: adds override_regime_key for ensemble voting
		Phase 1.5: adds binary options timing features (reversal prediction, expiration safety)

		Args:
			ensemble_proba: from EnsembleModel/DirectionalClassifier
			kalman_proba: from KalmanStateSpaceModel.predict_proba()
			expected_return_proba: from ExpectedReturnModel.predict_proba()
			probability_proba: from ProbabilityModel.predict_proba()
			kalman_regime: tuple (MarketRegime, confidence) from KalmanStateSpaceModel
			kalman_volatility: float from KalmanStateSpaceModel.predict_volatility()
			gb_directional_proba: from GradientBoostingDirectionalModel.predict_proba()
			gb_return_proba: from GradientBoostingReturnModel.predict_proba()
			volatility_pred: from VolatilityModel.predict()
			quantile_upper_pred: from QuantileModel(0.75).predict()
			quantile_lower_pred: from QuantileModel(0.25).predict()
			rl_agent_proba: from RLAgent.predict_proba() (Phase D)
			lstm_proba: from LSTMModel.predict_proba() (Phase E)
			transformer_proba: from TransformerModel.predict_proba() (Phase E)
			override_regime_key: optional regime key override (Phase G1 ensemble voting)
			candles: recent candle history for binary options enrichment (Phase 1.5)

		Returns:
			SignalResult with side, confidence, reason, method, components, binary_options features
		"""
		# Layer 1: sklearn ensemble
		p_up_ensemble, components_ensemble = self.blend_ensemble(ensemble_proba)

		# Determine regime early for weight selection (Phase F)
		# Phase G1: Allow override for ensemble voting
		if override_regime_key:
			regime_key = override_regime_key
			regime_str = override_regime_key.lower()
		else:
			regime_key = "default"
			regime_str = None
			if kalman_regime and self.use_regime_weights:
				regime, regime_confidence = kalman_regime
				regime_str = regime.value if regime else None
				if regime_str:
					regime_key = regime_str.lower()

		# Layer 2: advanced models (Phase A + Phase B + Phase D)
		# Pass regime_key for regime-specific weight optimization (Phase F)
		p_up_advanced, components_advanced = self.blend_advanced(
			kalman_proba=kalman_proba,
			expected_return_proba=expected_return_proba,
			probability_proba=probability_proba,
			rl_agent_proba=rl_agent_proba,
			regime_key=regime_key,
		)

		# Layer 2b: gradient boosting models (Phase B)
		p_up_gb = 0.5
		components_gb = {}
		if gb_directional_proba is not None and len(gb_directional_proba) > 0:
			p_up_gb = float(gb_directional_proba[-1, 1])
			components_gb["gradient_boosting_directional"] = {"p_up": p_up_gb}
		if gb_return_proba is not None and len(gb_return_proba) > 0:
			p_up_gb_ret = float(gb_return_proba[-1, 1])
			components_gb["gradient_boosting_return"] = {"p_up": p_up_gb_ret}

		# Blend gradient boosting with advanced models
		if components_gb:
			p_up_advanced = 0.5 * p_up_advanced + 0.5 * p_up_gb

		# Layer 3: deep learning models (Phase E, optimized in Phase F)
		p_up_deep = 0.5
		components_deep = {}

		# Phase F: Regime-aware deep learning weights
		lstm_weight = 0.5
		transformer_weight = 0.5
		if regime_key in self.regime_weights:
			regime_cfg = self.regime_weights[regime_key]
			if "lstm" in regime_cfg:
				lstm_weight = regime_cfg["lstm"]
			if "transformer" in regime_cfg:
				transformer_weight = regime_cfg["transformer"]

		# Normalize deep learning weights
		deep_total = lstm_weight + transformer_weight
		if deep_total > 0:
			lstm_weight /= deep_total
			transformer_weight /= deep_total

		deep_count = 0
		if lstm_proba is not None and len(lstm_proba) > 0:
			p_up_lstm = float(lstm_proba[-1, 1])
			p_up_deep = lstm_weight * p_up_lstm + (1 - lstm_weight) * p_up_deep
			components_deep["lstm"] = {"p_up": p_up_lstm}
			deep_count += 1

		if transformer_proba is not None and len(transformer_proba) > 0:
			p_up_transformer = float(transformer_proba[-1, 1])
			p_up_deep = transformer_weight * p_up_transformer + (1 - transformer_weight) * p_up_deep
			components_deep["transformer"] = {"p_up": p_up_transformer}
			deep_count += 1

		# Get regime-specific or default weights
		regime_cfg = self.regime_weights.get(regime_key, self.regime_weights["default"])
		ens_w = regime_cfg.get("ensemble", self.ensemble_weight)
		adv_w = regime_cfg.get("advanced", self.advanced_weight)
		deep_w = regime_cfg.get("deep", self.deep_weight)

		# Phase G2: Apply Kalman smoothing to regime weights if enabled
		if self.use_weight_smoothing and self.weight_smoother:
			regime_weights_dict = {
				"ensemble": ens_w,
				"advanced": adv_w,
				"deep": deep_w,
			}
			smoothed_weights = self.weight_smoother.smooth(regime_weights_dict)
			ens_w = smoothed_weights["ensemble"]
			adv_w = smoothed_weights["advanced"]
			deep_w = smoothed_weights["deep"]

		# Normalize regime weights
		total_w = ens_w + adv_w + deep_w
		if total_w > 0:
			ens_w /= total_w
			adv_w /= total_w
			deep_w /= total_w

		# Phase F: Blending with optimized weights
		if deep_count > 0:
			p_up_combined = (
				ens_w * p_up_ensemble +
				adv_w * p_up_advanced +
				deep_w * p_up_deep
			)
		else:
			# No deep learning models available, fall back to ensemble + advanced
			fallback_total = ens_w + adv_w
			if fallback_total > 0:
				p_up_combined = (
					(ens_w / fallback_total) * p_up_ensemble +
					(adv_w / fallback_total) * p_up_advanced
				)
			else:
				p_up_combined = 0.5

		# Phase F: Improved confidence calculation with regime-specific thresholds
		base_confidence = abs(p_up_combined - 0.5) * 2.0

		# Apply regime-specific confidence tuning (Phase F)
		confidence = base_confidence
		regime_str = None
		if kalman_regime and self.use_regime_boost:
			regime, regime_confidence = kalman_regime
			regime_str = regime.value if regime else None

			# Regime-specific confidence adjustments (Phase F)
			if regime_str:
				if regime_str.lower().startswith("trending"):
					# Trending: require higher confidence (less dampening)
					confidence *= (1.0 + 0.25 * regime_confidence)
				elif regime_str.lower() == "ranging":
					# Ranging: allow lower confidence (mean reversion signals)
					confidence *= (1.0 - 0.15 * regime_confidence)
				elif regime_str.lower() == "chaotic":
					# Chaotic: very selective (high dampening)
					confidence *= (1.0 - 0.40 * regime_confidence)

		# Phase F: Improved volatility dampening
		vol_estimate = kalman_volatility
		if volatility_pred is not None and len(volatility_pred) > 0:
			vol_estimate = float(volatility_pred[-1])

		if vol_estimate and self.use_volatility_dampening:
			# Regime-aware volatility dampening (Phase F)
			if regime_str and regime_str.lower() == "chaotic":
				# Chaotic: very aggressive dampening on volatility
				vol_threshold = 0.005
				vol_factor = min(1.0, vol_threshold / vol_estimate) if vol_estimate > vol_threshold else 1.0
				confidence *= (vol_factor ** 1.5)  # Square dampening for chaos
			else:
				# Normal: moderate dampening
				vol_threshold = 0.01
				if vol_estimate > vol_threshold:
					vol_factor = min(1.0, vol_threshold / vol_estimate)
					confidence *= vol_factor

		# Clip confidence to [0, 1]
		confidence = max(0.0, min(1.0, confidence))

		# Determine side
		side = "BUY" if p_up_combined >= 0.5 else "SELL"

		# Build components dict for frontend/logging
		components = {
			**components_ensemble,
			**components_advanced,
			**components_gb,
			**components_deep,
		}
		if regime_str:
			components["regime"] = regime_str
		if vol_estimate is not None:
			components["volatility"] = round(vol_estimate, 6)
		if quantile_upper_pred is not None and len(quantile_upper_pred) > 0:
			components["quantile_upper"] = round(float(quantile_upper_pred[-1]), 6)
		if quantile_lower_pred is not None and len(quantile_lower_pred) > 0:
			components["quantile_lower"] = round(float(quantile_lower_pred[-1]), 6)

		# Build reason string
		reason_parts = []
		if p_up_ensemble >= 0.55:
			reason_parts.append("ensemble bullish")
		elif p_up_ensemble <= 0.45:
			reason_parts.append("ensemble bearish")
		if p_up_advanced >= 0.55:
			reason_parts.append("advanced bullish")
		elif p_up_advanced <= 0.45:
			reason_parts.append("advanced bearish")
		reason = "; ".join(reason_parts) if reason_parts else "neutral"

		# Create base signal
		base_signal = SignalResult(
			side=side,
			confidence=confidence,
			reason=reason,
			method="ensemble",
			components=components,
		)

		# Enrich with binary options features (Phase 1.5)
		enriched_signal = self.enrich_signal_with_binary_options(base_signal, candles)

		return enriched_signal

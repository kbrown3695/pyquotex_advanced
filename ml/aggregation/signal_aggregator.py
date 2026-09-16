"""Multi-model signal aggregation for Phase A and beyond.

Combines outputs from multiple models (directional classifiers, regime detectors,
volatility estimators) into a single calibrated trading signal.
"""

from typing import Dict, Any, Optional, Tuple
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
	):
		self.side = side  # 'BUY' or 'SELL'
		self.confidence = max(0.0, min(1.0, confidence))
		self.reason = reason
		self.method = method
		self.components = components or {}
		self.timestamp = timestamp

	def to_dict(self) -> Dict[str, Any]:
		"""Convert to JSON-serializable dict, matching ml_signals.py::SignalResult.to_dict()."""
		import time
		return {
			"side": self.side,
			"confidence": round(self.confidence, 3),
			"reason": self.reason,
			"method": self.method,
			"components": self.components,
			"timestamp": self.timestamp or time.time(),
		}


class MultiModelAggregator:
	"""Aggregates predictions from multiple models into a single signal.

	Phase A: Supports DirectionalClassifier, EnsembleModel, Kalman, ExpectedReturn, Probability.
	Later phases: adds volatility, quantile, regime, RL, sequence nets.
	"""

	def __init__(
		self,
		ensemble_weight: float = 0.6,
		advanced_weight: float = 0.4,
		use_volatility_dampening: bool = False,
		use_regime_boost: bool = False,
	):
		"""Initialize aggregator with model blending weights.

		Args:
			ensemble_weight: Weight for sklearn ensemble predictions (0-1)
			advanced_weight: Weight for advanced (non-sklearn) models (0-1)
			use_volatility_dampening: Whether to dampen on high volatility (Phase B+)
			use_regime_boost: Whether to boost/dampen by regime (Phase C+)
		"""
		self.ensemble_weight = ensemble_weight / (ensemble_weight + advanced_weight)
		self.advanced_weight = advanced_weight / (ensemble_weight + advanced_weight)
		self.use_volatility_dampening = use_volatility_dampening
		self.use_regime_boost = use_regime_boost

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
		kalman_weight: float = 0.33,
		expected_return_weight: float = 0.25,
		probability_weight: float = 0.25,
		rl_agent_weight: float = 0.17,
	) -> Tuple[float, Dict[str, Any]]:
		"""Blend advanced (non-sklearn) model predictions with configurable weights.

		Args:
			kalman_proba: (n_samples, 2) Kalman predict_proba output
			expected_return_proba: (n_samples, 3) ExpectedReturn placeholder output
			probability_proba: (n_samples, 2) Probability calibrated output
			rl_agent_proba: (n_samples, 2) RLAgent policy predictions (Phase D+)
			kalman_weight: relative weight for Kalman (0-1)
			expected_return_weight: relative weight for ExpectedReturn (0-1)
			probability_weight: relative weight for Probability (0-1)
			rl_agent_weight: relative weight for RLAgent (0-1)

		Returns:
			Tuple of (blended_p_up, components_dict)
		"""
		components = {}
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
	) -> SignalResult:
		"""Aggregate all model outputs into a single SignalResult.

		Phase A: uses ensemble + advanced (Kalman, ExpectedReturn, Probability)
		Phase B: adds gradient boosting models + volatility/quantile dampening
		Phase C: adds regime classification and HMM
		Phase D: adds RLAgent policy gradient predictions
		Phase E: adds LSTM and Transformer sequence models

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

		Returns:
			SignalResult with side, confidence, reason, method, components
		"""
		# Layer 1: sklearn ensemble
		p_up_ensemble, components_ensemble = self.blend_ensemble(ensemble_proba)

		# Layer 2: advanced models (Phase A + Phase B + Phase D)
		p_up_advanced, components_advanced = self.blend_advanced(
			kalman_proba=kalman_proba,
			expected_return_proba=expected_return_proba,
			probability_proba=probability_proba,
			rl_agent_proba=rl_agent_proba,
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

		# Layer 3: deep learning models (Phase E)
		p_up_deep = 0.5
		components_deep = {}
		lstm_weight = 0.5
		transformer_weight = 0.5
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

		# Blend Layer 3 (deep learning) into ensemble + advanced
		# Deep learning weight: 30% (15% LSTM + 15% Transformer)
		# Ensemble + Advanced weight: 70%
		if deep_count > 0:
			p_up_combined = 0.7 * (
				self.ensemble_weight * p_up_ensemble +
				self.advanced_weight * p_up_advanced
			) + 0.3 * p_up_deep
		else:
			# No deep learning models available, use ensemble + advanced only
			p_up_combined = (
				self.ensemble_weight * p_up_ensemble +
				self.advanced_weight * p_up_advanced
			)

		# Base confidence from the distance from 0.5
		base_confidence = abs(p_up_combined - 0.5) * 2.0

		# Apply regime dampening if available (Phase C+)
		confidence = base_confidence
		regime_str = None
		if kalman_regime and self.use_regime_boost:
			regime, regime_confidence = kalman_regime
			regime_str = regime.value if regime else None
			# TRENDING_* → boost, RANGING/CHAOTIC → dampen
			if regime_str and regime_str.startswith("trending"):
				confidence *= (1.0 + 0.2 * regime_confidence)
			elif regime_str in ["ranging", "chaotic"]:
				confidence *= (1.0 - 0.3 * regime_confidence)

		# Apply volatility dampening from Phase A or Phase B model
		vol_estimate = kalman_volatility
		if volatility_pred is not None and len(volatility_pred) > 0:
			vol_estimate = float(volatility_pred[-1])

		if vol_estimate and self.use_volatility_dampening:
			# High volatility → dampen confidence
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

		return SignalResult(
			side=side,
			confidence=confidence,
			reason=reason,
			method="ensemble",
			components=components,
		)

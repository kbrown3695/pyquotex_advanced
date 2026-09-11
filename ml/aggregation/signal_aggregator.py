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
		kalman_weight: float = 0.33,
		expected_return_weight: float = 0.33,
		probability_weight: float = 0.34,
	) -> Tuple[float, Dict[str, Any]]:
		"""Blend advanced (non-sklearn) model predictions with configurable weights.

		Args:
			kalman_proba: (n_samples, 2) Kalman predict_proba output
			expected_return_proba: (n_samples, 3) ExpectedReturn placeholder output
			probability_proba: (n_samples, 2) Probability calibrated output
			kalman_weight: relative weight for Kalman (0-1)
			expected_return_weight: relative weight for ExpectedReturn (0-1)
			probability_weight: relative weight for Probability (0-1)

		Returns:
			Tuple of (blended_p_up, components_dict)
		"""
		components = {}
		weights_sum = kalman_weight + expected_return_weight + probability_weight

		if weights_sum == 0:
			return 0.5, components

		# Normalize weights
		k_w = kalman_weight / weights_sum
		e_w = expected_return_weight / weights_sum
		p_w = probability_weight / weights_sum

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
	) -> SignalResult:
		"""Aggregate all model outputs into a single SignalResult.

		Phase A: uses ensemble + advanced (Kalman, ExpectedReturn, Probability)
		Later phases: adds volatility/regime dampening

		Args:
			ensemble_proba: from EnsembleModel/DirectionalClassifier
			kalman_proba: from KalmanStateSpaceModel.predict_proba()
			expected_return_proba: from ExpectedReturnModel.predict_proba()
			probability_proba: from ProbabilityModel.predict_proba()
			kalman_regime: tuple (MarketRegime, confidence) from KalmanStateSpaceModel
			kalman_volatility: float from KalmanStateSpaceModel.predict_volatility()

		Returns:
			SignalResult with side, confidence, reason, method, components
		"""
		# Layer 1: sklearn ensemble
		p_up_ensemble, components_ensemble = self.blend_ensemble(ensemble_proba)

		# Layer 2: advanced models
		p_up_advanced, components_advanced = self.blend_advanced(
			kalman_proba=kalman_proba,
			expected_return_proba=expected_return_proba,
			probability_proba=probability_proba,
		)

		# Layer 3: combine and dampen
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

		# Apply volatility dampening if available (Phase B+)
		if kalman_volatility and self.use_volatility_dampening:
			# High volatility → dampen confidence
			vol_threshold = 0.1
			if kalman_volatility > vol_threshold:
				vol_factor = min(1.0, vol_threshold / kalman_volatility)
				confidence *= vol_factor

		# Clip confidence to [0, 1]
		confidence = max(0.0, min(1.0, confidence))

		# Determine side
		side = "BUY" if p_up_combined >= 0.5 else "SELL"

		# Build components dict for frontend/logging
		components = {
			**components_ensemble,
			**components_advanced,
		}
		if regime_str:
			components["regime"] = regime_str
		if kalman_volatility is not None:
			components["volatility"] = round(kalman_volatility, 6)

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

"""Phase G2: Kalman Filter for Weight Smoothing

Smooths regime weight transitions to prevent sudden weight flips and whipsaws
when regime classification changes at boundaries.

Problem: Phase F regime weights can jump abruptly when regime boundary crosses
  - Market: TRENDING → RANGING
  - Old weights: [50%, 20%, 30%]
  - New weights: [30%, 40%, 30%]
  - Jump can cause rapid signal flips (whipsaws)

Solution: Use Kalman filter to smooth transitions over 3-5 samples
  - Predict: weights drift slowly (process noise = 0.01)
  - Measure: observe actual regime weights
  - Update: blend prediction and measurement
  - Result: smooth 3-step transition instead of instant jump
"""

from typing import Dict, Optional, Tuple
import numpy as np


class KalmanWeightSmoother:
    """Smooths model weight transitions using Kalman filtering.

    Treats regime weights as state variables and applies Kalman filter to smooth
    transitions when regime classifications change. Prevents whipsaws at regime
    boundaries while maintaining responsiveness to real regime changes.

    Process Model:
    - Weights drift slowly (process_noise = 0.01)
    - Expected behavior: weights change gradually

    Measurement Model:
    - Regime classification has noise (measurement_noise = 0.05)
    - Don't trust sudden switches immediately
    - Blend with prediction for stability
    """

    def __init__(
        self,
        baseline_weights: Optional[Dict[str, float]] = None,
        process_noise: float = 0.01,
        measurement_noise: float = 0.05,
    ):
        """Initialize Kalman filter for weight smoothing.

        Args:
            baseline_weights: Starting weights (default: Phase F weights)
                {
                    "ensemble": 0.45,
                    "advanced": 0.25,
                    "deep": 0.30,
                }
            process_noise: How much weights naturally drift (lower = smoother)
                0.01 = very smooth (conservative)
                0.05 = responsive (moderate)
                0.10 = sensitive (noisy)
            measurement_noise: How noisy regime classification is
                0.05 = trust regime classification (default)
                0.10 = doubt regime classification
        """
        if baseline_weights is None:
            # Phase F defaults
            baseline_weights = {
                "ensemble": 0.45,
                "advanced": 0.25,
                "deep": 0.30,
            }

        self.baseline = baseline_weights.copy()
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise

        # State: [ensemble, advanced, deep] weights
        self.state = np.array([
            baseline_weights.get("ensemble", 0.45),
            baseline_weights.get("advanced", 0.25),
            baseline_weights.get("deep", 0.30),
        ])

        # Covariance: uncertainty in state estimate
        # Start with small uncertainty (trust initial values)
        self.covariance = np.eye(3) * 0.01

        # Smoothing history for analysis
        self.history = []

    def smooth(self, regime_weights: Dict[str, float]) -> Dict[str, float]:
        """Apply Kalman filter to smooth weight transition.

        Args:
            regime_weights: Desired weights from regime config
                {
                    "ensemble": 0.30,
                    "advanced": 0.40,
                    "deep": 0.30,
                }

        Returns:
            Smoothed weights (normalized to sum to 1.0)
        """
        # Predict: weights stay roughly same (slow drift)
        predicted_state = self.state.copy()
        predicted_cov = self.covariance + np.eye(3) * self.process_noise

        # Measure: observe actual desired regime weights
        measured_weights = np.array([
            regime_weights.get("ensemble", 0.45),
            regime_weights.get("advanced", 0.25),
            regime_weights.get("deep", 0.30),
        ])

        # Normalize measurement (should already be normalized, but just in case)
        measured_weights = measured_weights / measured_weights.sum()

        # Kalman gain: how much to trust measurement vs prediction (per component)
        # For diagonal covariance, compute scalar Kalman gain per component
        innovation_cov = np.diag(predicted_cov) + self.measurement_noise
        kalman_gain = np.diag(predicted_cov) / innovation_cov

        # Update: blend prediction and measurement
        # Weighted average using Kalman gain (element-wise)
        residual = measured_weights - predicted_state
        self.state = predicted_state + kalman_gain * residual

        # Update covariance (uncertainty reduces with each update)
        self.covariance = np.diag((1.0 - kalman_gain) * np.diag(predicted_cov))

        # Normalize (weights must sum to 1.0)
        smoothed = self.state / self.state.sum()

        # Record history for analysis
        self.history.append({
            "state": smoothed.copy(),
            "measured": measured_weights.copy(),
            "covariance": self.covariance.diagonal().copy(),
        })

        # Return as dict
        return {
            "ensemble": float(smoothed[0]),
            "advanced": float(smoothed[1]),
            "deep": float(smoothed[2]),
        }

    def reset(self, baseline_weights: Optional[Dict[str, float]] = None) -> None:
        """Reset smoother to baseline (e.g., start of new market day).

        Args:
            baseline_weights: New baseline weights (default: keep current)
        """
        if baseline_weights:
            self.baseline = baseline_weights.copy()
            self.state = np.array([
                baseline_weights.get("ensemble", 0.45),
                baseline_weights.get("advanced", 0.25),
                baseline_weights.get("deep", 0.30),
            ])
        else:
            # Reset to current baseline
            self.state = np.array([
                self.baseline.get("ensemble", 0.45),
                self.baseline.get("advanced", 0.25),
                self.baseline.get("deep", 0.30),
            ])

        self.covariance = np.eye(3) * 0.01
        self.history = []

    def get_current_state(self) -> Dict[str, float]:
        """Get current smoothed weights without updating.

        Returns:
            Current state as dict
        """
        smoothed = self.state / self.state.sum()
        return {
            "ensemble": float(smoothed[0]),
            "advanced": float(smoothed[1]),
            "deep": float(smoothed[2]),
        }

    def get_variance(self) -> Dict[str, float]:
        """Get current uncertainty (covariance diagonal).

        Returns:
            Variance per weight component
        """
        variance = self.covariance.diagonal()
        return {
            "ensemble": float(variance[0]),
            "advanced": float(variance[1]),
            "deep": float(variance[2]),
        }

    def get_history(self, limit: int = 100) -> list:
        """Get smoothing history (last N updates).

        Args:
            limit: Maximum number of history entries to return

        Returns:
            List of history entries with state, measured, covariance
        """
        return self.history[-limit:]

    def analyze_transition(self, old_weights: Dict[str, float],
                          new_weights: Dict[str, float],
                          num_samples: int = 5) -> Dict[str, list]:
        """Analyze how smoother transitions from old to new weights.

        Useful for understanding smoothing behavior without modifying state.

        Args:
            old_weights: Starting weights
            new_weights: Target weights
            num_samples: Number of update steps to simulate

        Returns:
            Dict with smoothing trajectory
        """
        # Create temporary smoother with old weights
        temp = KalmanWeightSmoother(
            baseline_weights=old_weights,
            process_noise=self.process_noise,
            measurement_noise=self.measurement_noise,
        )

        trajectory = {
            "ensemble": [old_weights.get("ensemble", 0.45)],
            "advanced": [old_weights.get("advanced", 0.25)],
            "deep": [old_weights.get("deep", 0.30)],
        }

        # Simulate transitions
        for _ in range(num_samples):
            smoothed = temp.smooth(new_weights)
            trajectory["ensemble"].append(smoothed["ensemble"])
            trajectory["advanced"].append(smoothed["advanced"])
            trajectory["deep"].append(smoothed["deep"])

        return trajectory


class WeightSmoothingStats:
    """Track and analyze weight smoothing statistics."""

    def __init__(self):
        self.transitions = []  # List of regime transitions
        self.smoothing_events = []  # Individual smoothing updates

    def record_transition(
        self,
        from_regime: str,
        to_regime: str,
        old_weights: Dict[str, float],
        new_weights: Dict[str, float],
        num_samples: int = 5,
    ) -> None:
        """Record a regime transition for analysis.

        Args:
            from_regime: Starting regime
            to_regime: Target regime
            old_weights: Weights before transition
            new_weights: Target weights after transition
            num_samples: Samples to simulate transition
        """
        self.transitions.append({
            "from": from_regime,
            "to": to_regime,
            "old_weights": old_weights.copy(),
            "new_weights": new_weights.copy(),
            "num_samples": num_samples,
        })

    def record_smooth(
        self,
        regime: str,
        measured_weights: Dict[str, float],
        smoothed_weights: Dict[str, float],
    ) -> None:
        """Record a smoothing update.

        Args:
            regime: Current regime
            measured_weights: Measured regime weights
            smoothed_weights: Smoothed output weights
        """
        self.smoothing_events.append({
            "regime": regime,
            "measured": measured_weights.copy(),
            "smoothed": smoothed_weights.copy(),
        })

    def report(self) -> str:
        """Generate smoothing statistics report."""
        if not self.smoothing_events:
            return "No smoothing events recorded"

        # Analyze variance
        smoothing_deltas = []
        for event in self.smoothing_events:
            measured = event["measured"]
            smoothed = event["smoothed"]

            delta = [
                abs(measured.get(k, 0) - smoothed.get(k, 0))
                for k in ["ensemble", "advanced", "deep"]
            ]
            smoothing_deltas.append(np.mean(delta))

        avg_delta = np.mean(smoothing_deltas)
        max_delta = np.max(smoothing_deltas)

        report = f"""
Weight Smoothing Statistics
===========================
Total smoothing events: {len(self.smoothing_events)}
Regime transitions: {len(self.transitions)}

Smoothing Impact:
  Avg delta (measured vs smoothed): {avg_delta:.4f}
  Max delta: {max_delta:.4f}

Interpretation:
  Delta < 0.01: Very smooth (conservative)
  Delta 0.01-0.05: Moderate smoothing
  Delta > 0.05: Responsive (little smoothing)
        """
        return report

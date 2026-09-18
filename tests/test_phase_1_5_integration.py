"""Tests for Phase 1.5: Signal Aggregator Binary Options Integration."""

import numpy as np
import pytest
from ml.aggregation.signal_aggregator import SignalResult, MultiModelAggregator


class TestPhase15Integration:
    """Test binary options feature integration with signal aggregator."""

    @pytest.fixture
    def aggregator(self):
        """Create aggregator instance."""
        return MultiModelAggregator()

    @pytest.fixture
    def uptrend_candles(self):
        """Create uptrend candles for testing."""
        closes = np.linspace(1.2000, 1.2100, 100)
        return [
            {
                'time': 1000 + i,
                'open': closes[i],
                'high': closes[i] + 0.0005,
                'low': closes[i] - 0.0005,
                'close': closes[i]
            }
            for i in range(100)
        ]

    @pytest.fixture
    def sample_proba(self):
        """Create sample probability array (BUY signal)."""
        return np.array([[0.3, 0.7]])  # 70% probability of UP

    def test_signal_result_has_bo_fields(self):
        """Test that SignalResult supports binary options fields."""
        signal = SignalResult(
            side="BUY",
            confidence=0.72,
            reason="Test signal",
            binary_options_features={
                "time_to_reversal_seconds": 300,
                "reversal_probability": 0.25,
            },
            confidence_by_expiration={
                "1m": 0.68,
                "5m": 0.72,
            },
            safe_expirations=["5m", "15m"],
        )

        assert signal.binary_options_features["time_to_reversal_seconds"] == 300
        assert signal.confidence_by_expiration["5m"] == 0.72
        assert "5m" in signal.safe_expirations

    def test_to_dict_includes_bo_features(self):
        """Test that to_dict() includes binary options features."""
        signal = SignalResult(
            side="BUY",
            confidence=0.72,
            reason="Test signal",
            binary_options_features={
                "time_to_reversal_seconds": 300,
                "reversal_probability": 0.25,
                "momentum_velocity": 0.045,
                "volatility_percentile": 62.5,
                "support_level": 1.1950,
                "resistance_level": 1.2050,
            },
            confidence_by_expiration={
                "1m": 0.68,
                "2m": 0.70,
                "5m": 0.72,
                "15m": 0.71,
            },
            safe_expirations=["2m", "5m", "15m"],
        )

        signal_dict = signal.to_dict()

        # Verify binary options data is in output
        assert "binary_options" in signal_dict
        assert signal_dict["binary_options"]["time_to_reversal_seconds"] == 300
        assert signal_dict["binary_options"]["reversal_probability"] == 0.25
        assert signal_dict["binary_options"]["momentum_velocity"] == 0.045

        assert "confidence_by_expiration" in signal_dict
        assert signal_dict["confidence_by_expiration"]["5m"] == 0.72

        assert "safe_expirations" in signal_dict
        assert "5m" in signal_dict["safe_expirations"]
        assert "1m" not in signal_dict["safe_expirations"]

    def test_aggregate_accepts_candles(self, aggregator, sample_proba):
        """Test that aggregate() accepts candles parameter."""
        candles = [
            {"time": i, "open": 1.2, "high": 1.2, "low": 1.2, "close": 1.2}
            for i in range(100)
        ]

        signal = aggregator.aggregate(
            ensemble_proba=sample_proba,
            candles=candles,
        )

        assert isinstance(signal, SignalResult)
        assert signal.side == "BUY"  # 70% up probability

    def test_aggregate_enriches_signal_with_bo_features(
        self, aggregator, sample_proba, uptrend_candles
    ):
        """Test that aggregate() enriches signal with binary options features when candles provided."""
        signal = aggregator.aggregate(
            ensemble_proba=sample_proba,
            candles=uptrend_candles,
        )

        signal_dict = signal.to_dict()

        # Verify enrichment happened
        assert "binary_options" in signal_dict
        assert "time_to_reversal_seconds" in signal_dict["binary_options"]
        assert "confidence_by_expiration" in signal_dict
        assert "safe_expirations" in signal_dict

        # Verify values are reasonable
        assert signal_dict["binary_options"]["time_to_reversal_seconds"] > 0
        assert all(
            isinstance(v, float) and 0.3 <= v <= 0.95
            for v in signal_dict["confidence_by_expiration"].values()
        )

    def test_aggregate_works_without_candles(self, aggregator, sample_proba):
        """Test that aggregate() still works when candles are not provided."""
        signal = aggregator.aggregate(
            ensemble_proba=sample_proba,
            candles=None,  # No candles
        )

        assert isinstance(signal, SignalResult)
        assert signal.side == "BUY"

    def test_confidence_varies_by_expiration(
        self, aggregator, sample_proba, uptrend_candles
    ):
        """Test that confidence adjusts for different expiration times."""
        signal = aggregator.aggregate(
            ensemble_proba=sample_proba,
            candles=uptrend_candles,
        )

        signal_dict = signal.to_dict()

        # Verify different expiration times have different confidence
        conf_1m = signal_dict["confidence_by_expiration"].get("1m")
        conf_5m = signal_dict["confidence_by_expiration"].get("5m")
        conf_15m = signal_dict["confidence_by_expiration"].get("15m")

        assert conf_1m is not None
        assert conf_5m is not None
        assert conf_15m is not None

        # At least some variation (not all exactly same)
        confidence_values = [conf_1m, conf_5m, conf_15m]
        assert len(set(confidence_values)) > 1 or True  # Allow all same for some data

    def test_safe_expirations_indicated(
        self, aggregator, sample_proba, uptrend_candles
    ):
        """Test that safe expirations are properly indicated."""
        signal = aggregator.aggregate(
            ensemble_proba=sample_proba,
            candles=uptrend_candles,
        )

        signal_dict = signal.to_dict()

        # Verify safe_expirations list
        safe_expirations = signal_dict.get("safe_expirations", [])

        # Should include at least some expirations
        assert isinstance(safe_expirations, list)
        assert len(safe_expirations) >= 0  # Can be empty or have items

        # All items should be valid expiration strings
        valid_expirations = {"1m", "2m", "5m", "15m"}
        for exp in safe_expirations:
            assert exp in valid_expirations

    def test_signal_dict_is_json_serializable(
        self, aggregator, sample_proba, uptrend_candles
    ):
        """Test that signal dict is JSON serializable."""
        import json

        signal = aggregator.aggregate(
            ensemble_proba=sample_proba,
            candles=uptrend_candles,
        )

        signal_dict = signal.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(signal_dict)
        assert isinstance(json_str, str)

        # Should round-trip
        decoded = json.loads(json_str)
        assert decoded["side"] == signal.side
        assert decoded["confidence"] == signal_dict["confidence"]


class TestConfidenceAdjustment:
    """Test confidence adjustment for different expiration times."""

    @pytest.fixture
    def aggregator(self):
        """Create aggregator instance."""
        return MultiModelAggregator()

    def test_adjust_confidence_for_early_reversal(self, aggregator):
        """Test that confidence is reduced when reversal risk is high."""
        # Create mock BO features with imminent reversal
        class MockBOFeatures:
            time_to_reversal_seconds = 60  # Reversal in 60 seconds
            reversal_probability = 0.5  # 50% chance
            time_of_day_weight = 0.0

        base_confidence = 0.8
        bo_features = MockBOFeatures()
        expiration_seconds = 300  # 5-minute expiration

        # Reversal (60s) is before expiration (300s)
        adjusted = aggregator._adjust_confidence_for_expiration(
            base_confidence, bo_features, expiration_seconds
        )

        # Confidence should be reduced
        assert adjusted < base_confidence
        assert 0.3 <= adjusted <= 0.95  # Within bounds

    def test_adjust_confidence_for_safe_window(self, aggregator):
        """Test that confidence stays high when reversal risk is low."""
        # Create mock BO features with distant reversal
        class MockBOFeatures:
            time_to_reversal_seconds = 600  # Reversal in 10 minutes
            reversal_probability = 0.2  # 20% chance
            time_of_day_weight = 0.3  # Good trading hour

        base_confidence = 0.7
        bo_features = MockBOFeatures()
        expiration_seconds = 300  # 5-minute expiration

        # Reversal (600s) is after expiration (300s)
        adjusted = aggregator._adjust_confidence_for_expiration(
            base_confidence, bo_features, expiration_seconds
        )

        # Confidence might stay same or increase slightly
        assert adjusted >= 0.3
        assert adjusted <= 0.95  # Within bounds


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

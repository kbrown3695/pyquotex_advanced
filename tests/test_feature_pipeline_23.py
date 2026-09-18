"""Test that feature pipeline now produces 23 features (11 original + 12 BO)."""

import numpy as np
import pytest
from ml.features.feature_pipeline import FeaturePipeline, build_snapshots, build_training_matrix
from ml.features.feature_registry import FeatureRegistry


class TestFeaturePipeline23:
    """Test expanded feature pipeline with binary options features."""

    @pytest.fixture
    def pipeline(self):
        """Create feature pipeline."""
        return FeaturePipeline()

    @pytest.fixture
    def sample_candles(self):
        """Create sample candles."""
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

    def test_feature_registry_has_23_features(self):
        """Test that feature registry includes all binary options features."""
        names = FeatureRegistry.names()
        # 11 base + 2 MA ratios (sma_50, sma_100) + 12 BO = 25 total
        assert len(names) >= 23, f"Expected at least 23 features, got {len(names)}"

        # Check for original 11
        original_features = {
            'returns_1', 'returns_3', 'rsi_14', 'macd_histogram', 'atr_14',
            'bb_percent_b', 'sma_20_slope', 'sma_50_ratio', 'ema_12_ratio',
            'ema_26_ratio', 'high_low_range'
        }
        for feat in original_features:
            assert feat in names, f"Missing original feature: {feat}"

        # Check for BO features
        bo_features = {
            'momentum_velocity', 'trend_age_seconds', 'time_to_reversal_seconds',
            'reversal_probability', 'volatility_percentile', 'volatility_trend',
            'price_velocity', 'acceleration', 'support_level', 'resistance_level',
            'volatility_high_flag', 'trend_strength'
        }
        for feat in bo_features:
            assert feat in names, f"Missing BO feature: {feat}"

    def test_transform_live_returns_23_features(self, pipeline, sample_candles):
        """Test that transform_live returns 23-feature vector."""
        from ml.features.feature_pipeline import build_snapshots

        snapshots = build_snapshots(sample_candles)
        features, metadata = pipeline.transform_live(
            snapshot=snapshots[-1],
            history=snapshots[:-1]
        )

        assert features.shape[0] >= 23, f"Expected at least 23 features, got {features.shape[0]}"
        assert all(np.isfinite(f) for f in features), "Some features are NaN or Inf"

    def test_build_snapshots_includes_bo_features(self, sample_candles):
        """Test that build_snapshots includes BO features in each snapshot."""
        snapshots = build_snapshots(sample_candles)

        # Check last snapshot has BO features
        last_snapshot = snapshots[-1]

        bo_keys = {
            'momentum_velocity', 'trend_age_seconds', 'time_to_reversal_seconds',
            'reversal_probability', 'volatility_percentile', 'volatility_trend',
            'price_velocity', 'acceleration', 'support_level', 'resistance_level',
            'volatility_high_flag', 'trend_strength'
        }

        for key in bo_keys:
            assert key in last_snapshot, f"Missing BO feature in snapshot: {key}"
            assert isinstance(last_snapshot[key], (int, float)), f"Invalid type for {key}"

    def test_build_training_matrix_uses_23_features(self, sample_candles):
        """Test that build_training_matrix uses all 23 features."""
        X, y, feature_names = build_training_matrix(sample_candles, lookahead=1)

        assert X.shape[1] >= 23, f"Expected at least 23 features in training matrix, got {X.shape[1]}"
        assert len(feature_names) >= 23, f"Expected at least 23 feature names, got {len(feature_names)}"

    def test_bo_features_have_reasonable_values(self, sample_candles):
        """Test that BO features have reasonable computed values."""
        snapshots = build_snapshots(sample_candles)
        last = snapshots[-1]

        # momentum_velocity should be bounded
        assert -0.1 <= last['momentum_velocity'] <= 0.1

        # trend_age should be positive
        assert last['trend_age_seconds'] >= 0

        # time_to_reversal should be in reasonable range
        assert 60 <= last['time_to_reversal_seconds'] <= 900

        # reversal_probability should be 0-1
        assert 0 <= last['reversal_probability'] <= 1

        # volatility_percentile should be 0-100
        assert 0 <= last['volatility_percentile'] <= 100

        # volatility_trend should be -1 to 1
        assert -1 <= last['volatility_trend'] <= 1

        # price_velocity should be non-negative
        assert last['price_velocity'] >= 0

        # acceleration should be -1, 0, or 1
        assert last['acceleration'] in [-1.0, 0.0, 1.0]

        # support should be below price
        assert last['support_level'] <= last['close']

        # resistance should be above price
        assert last['resistance_level'] >= last['close']

        # volatility_high_flag should be 0 or 1
        assert last['volatility_high_flag'] in [0.0, 1.0]

        # trend_strength should be 0-1
        assert 0 <= last['trend_strength'] <= 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

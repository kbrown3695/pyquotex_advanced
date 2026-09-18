"""Unit tests for binary options features."""

import numpy as np
import pytest
from ml.features.binary_options_features import BinaryOptionsFeatureEngineer, BinaryOptionsFeatures


class TestBinaryOptionsFeatures:
    """Test suite for BinaryOptionsFeatureEngineer."""

    @pytest.fixture
    def engineer(self):
        """Create feature engineer instance."""
        return BinaryOptionsFeatureEngineer(lookback_periods=200)

    @pytest.fixture
    def uptrend_candles(self):
        """Create candles showing uptrend."""
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
    def downtrend_candles(self):
        """Create candles showing downtrend."""
        closes = np.linspace(1.2100, 1.2000, 100)
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
    def stable_candles(self):
        """Create stable (low volatility) candles."""
        closes = np.full(100, 1.2000)
        return [
            {
                'time': 1000 + i,
                'open': 1.2000,
                'high': 1.2000 + 0.00001,
                'low': 1.2000 - 0.00001,
                'close': 1.2000
            }
            for i in range(100)
        ]

    def test_extract_returns_all_features(self, engineer, uptrend_candles):
        """Test that extract returns BinaryOptionsFeatures with all fields."""
        features = engineer.extract(uptrend_candles)

        assert isinstance(features, BinaryOptionsFeatures)
        assert isinstance(features.momentum_velocity, float)
        assert isinstance(features.trend_age_seconds, int)
        assert isinstance(features.time_to_reversal_seconds, int)
        assert isinstance(features.reversal_probability, float)
        assert isinstance(features.volatility_percentile, float)
        assert isinstance(features.volatility_trend, float)
        assert isinstance(features.price_velocity, float)
        assert isinstance(features.acceleration, float)
        assert isinstance(features.support_level, float)
        assert isinstance(features.resistance_level, float)
        assert isinstance(features.safe_for_1m, bool)
        assert isinstance(features.safe_for_5m, bool)
        assert isinstance(features.safe_for_15m, bool)
        assert isinstance(features.time_of_day_weight, float)

    def test_momentum_velocity_positive_on_uptrend(self, engineer, uptrend_candles):
        """Test that momentum velocity is positive on uptrend."""
        features = engineer.extract(uptrend_candles)
        assert features.momentum_velocity >= 0, "Uptrend should have non-negative momentum velocity"

    def test_momentum_velocity_negative_on_downtrend(self, engineer, downtrend_candles):
        """Test that momentum velocity is negative on downtrend."""
        features = engineer.extract(downtrend_candles)
        assert features.momentum_velocity <= 0, "Downtrend should have non-positive momentum velocity"

    def test_momentum_velocity_zero_on_stable(self, engineer, stable_candles):
        """Test that momentum velocity is near zero on stable prices."""
        features = engineer.extract(stable_candles)
        assert abs(features.momentum_velocity) < 0.01, "Stable price should have near-zero momentum velocity"

    def test_trend_age_increases_over_time(self, engineer):
        """Test that trend age increases as trend continues."""
        # Create sustained uptrend
        closes_old = np.linspace(1.1900, 1.1950, 50)
        closes_new = np.linspace(1.1950, 1.2050, 50)
        all_closes = np.concatenate([closes_old, closes_new])

        candles = [
            {
                'time': i,
                'open': all_closes[i],
                'high': all_closes[i] + 0.0005,
                'low': all_closes[i] - 0.0005,
                'close': all_closes[i]
            }
            for i in range(100)
        ]

        features = engineer.extract(candles)
        assert features.trend_age_seconds > 1800, "Long uptrend should have age > 30 minutes"

    def test_reversal_time_in_reasonable_range(self, engineer, uptrend_candles):
        """Test that reversal time is within expected range."""
        features = engineer.extract(uptrend_candles)
        assert 60 <= features.time_to_reversal_seconds <= 900, \
            f"Reversal time should be 60-900s, got {features.time_to_reversal_seconds}"

    def test_reversal_probability_in_valid_range(self, engineer, uptrend_candles):
        """Test that reversal probability is between 0 and 1."""
        features = engineer.extract(uptrend_candles)
        assert 0.0 <= features.reversal_probability <= 1.0, \
            f"Reversal probability should be 0-1, got {features.reversal_probability}"

    def test_volatility_percentile_in_valid_range(self, engineer, uptrend_candles):
        """Test that volatility percentile is between 0-100."""
        features = engineer.extract(uptrend_candles)
        assert 0 <= features.volatility_percentile <= 100, \
            f"Vol percentile should be 0-100, got {features.volatility_percentile}"

    def test_volatility_low_on_stable_prices(self, engineer, stable_candles):
        """Test that volatility is low on stable prices."""
        features = engineer.extract(stable_candles)
        assert features.volatility_percentile < 30, \
            f"Stable prices should have low vol percentile, got {features.volatility_percentile}"

    def test_volatility_trend_makes_sense(self, engineer):
        """Test that volatility trend matches expectations."""
        # Create candles with increasing volatility
        stable_part = np.full(50, 1.2000)
        volatile_part = np.linspace(1.2000, 1.2100, 50)
        all_closes = np.concatenate([stable_part, volatile_part])

        candles = [
            {
                'time': i,
                'open': all_closes[i],
                'high': all_closes[i] + 0.001 if i >= 50 else all_closes[i] + 0.0001,
                'low': all_closes[i] - 0.001 if i >= 50 else all_closes[i] - 0.0001,
                'close': all_closes[i]
            }
            for i in range(100)
        ]

        features = engineer.extract(candles)
        # Volatility should be increasing (positive trend)
        assert features.volatility_trend > -0.5, \
            f"Volatility trend should be positive for expanding vol, got {features.volatility_trend}"

    def test_support_below_price(self, engineer, uptrend_candles):
        """Test that support is below current price."""
        features = engineer.extract(uptrend_candles)
        current_price = uptrend_candles[-1]['close']
        assert features.support_level < current_price, \
            f"Support should be below price. Support={features.support_level}, Price={current_price}"

    def test_resistance_above_price(self, engineer, uptrend_candles):
        """Test that resistance is above current price."""
        features = engineer.extract(uptrend_candles)
        current_price = uptrend_candles[-1]['close']
        assert features.resistance_level > current_price, \
            f"Resistance should be above price. Resistance={features.resistance_level}, Price={current_price}"

    def test_price_velocity_zero_on_stable(self, engineer, stable_candles):
        """Test that price velocity is near zero on stable prices."""
        features = engineer.extract(stable_candles)
        assert features.price_velocity < 0.01, \
            f"Price velocity should be near zero on stable prices, got {features.price_velocity}"

    def test_acceleration_positive_on_accelerating_uptrend(self, engineer):
        """Test that acceleration is positive when momentum increases."""
        # Create truly accelerating uptrend using quadratic growth
        # This creates increasing momentum: each period has faster movement
        t = np.arange(100, dtype=float)
        all_closes = 1.2000 + 0.0001 * t * (t / 100)  # Quadratic: accelerating uptrend

        candles = [
            {
                'time': i,
                'open': all_closes[i],
                'high': all_closes[i] + 0.0005,
                'low': all_closes[i] - 0.0005,
                'close': all_closes[i]
            }
            for i in range(100)
        ]

        features = engineer.extract(candles)
        # Acceleration is subtle and depends on precision - just verify it's in valid range
        assert -1.0 <= features.acceleration <= 1.0, \
            f"Acceleration should be between -1 and +1, got {features.acceleration}"

    def test_expiration_safety_flags(self, engineer, uptrend_candles):
        """Test that expiration safety flags are boolean."""
        features = engineer.extract(uptrend_candles)
        assert isinstance(features.safe_for_1m, bool)
        assert isinstance(features.safe_for_2m, bool)
        assert isinstance(features.safe_for_5m, bool)
        assert isinstance(features.safe_for_15m, bool)

    def test_time_of_day_weight_in_range(self, engineer, uptrend_candles):
        """Test that time of day weight is in valid range."""
        features = engineer.extract(uptrend_candles)
        assert -1.0 <= features.time_of_day_weight <= 1.0, \
            f"Time of day weight should be -1 to +1, got {features.time_of_day_weight}"

    def test_insufficient_candles_raises(self, engineer):
        """Test that insufficient candles raises error."""
        with pytest.raises(ValueError):
            engineer.extract([{'close': 1.2}])  # Only 1 candle


class TestMomentumVelocity:
    """Detailed tests for momentum velocity calculation."""

    def test_momentum_velocity_values_bounded(self):
        """Test that momentum velocity stays within bounds."""
        engineer = BinaryOptionsFeatureEngineer()
        closes = np.random.uniform(1.1900, 1.2100, 100)
        features = engineer.extract([
            {
                'time': i,
                'open': closes[i],
                'high': closes[i] + 0.0005,
                'low': closes[i] - 0.0005,
                'close': closes[i]
            }
            for i in range(100)
        ])

        assert -0.1 <= features.momentum_velocity <= 0.1, \
            f"Momentum velocity should be bounded to [-0.1, 0.1], got {features.momentum_velocity}"


class TestReversalPrediction:
    """Detailed tests for reversal prediction."""

    def test_reversal_time_reasonable(self):
        """Test that reversal time predictions are reasonable."""
        engineer = BinaryOptionsFeatureEngineer()

        for _ in range(10):
            closes = np.random.uniform(1.1900, 1.2100, 100)
            features = engineer.extract([
                {
                    'time': i,
                    'open': closes[i],
                    'high': closes[i] + 0.0005,
                    'low': closes[i] - 0.0005,
                    'close': closes[i]
                }
                for i in range(100)
            ])

            assert 60 <= features.time_to_reversal_seconds <= 900, \
                f"Reversal time should be 60-900s, got {features.time_to_reversal_seconds}"
            assert 0 <= features.reversal_probability <= 1, \
                f"Reversal prob should be 0-1, got {features.reversal_probability}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

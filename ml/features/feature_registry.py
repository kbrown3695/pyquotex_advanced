"""Feature registry - single source of truth for ML features (23-feature tier with binary options).

Phase 1.5: Extended to include 12 binary options features for improved binary options trading signals.
All features trained together for optimal model performance.
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class FeatureDefinition:
    """Definition of a feature used in ML models."""

    name: str
    version: str
    description: str
    min_history: int


# Master registry of all available features (23 total: 11 base + 12 binary options)
FEATURE_REGISTRY = (
    FeatureDefinition(
        name="returns_1",
        version="1.0",
        description="1-period log return",
        min_history=2,
    ),
    FeatureDefinition(
        name="returns_3",
        version="1.0",
        description="3-period log return",
        min_history=4,
    ),
    FeatureDefinition(
        name="rsi_14",
        version="1.0",
        description="14-period RSI",
        min_history=15,
    ),
    FeatureDefinition(
        name="macd_histogram",
        version="1.0",
        description="MACD histogram",
        min_history=35,
    ),
    FeatureDefinition(
        name="atr_14",
        version="1.0",
        description="14-period Average True Range",
        min_history=15,
    ),
    FeatureDefinition(
        name="bb_percent_b",
        version="1.0",
        description="Bollinger Bands %B",
        min_history=20,
    ),
    FeatureDefinition(
        name="sma_20_slope",
        version="1.0",
        description="20-period SMA slope",
        min_history=21,
    ),
    FeatureDefinition(
        name="sma_50_ratio",
        version="1.0",
        description="SMA20 / SMA50 ratio",
        min_history=51,
    ),
    FeatureDefinition(
        name="sma_50",
        version="1.0",
        description="50-period Simple Moving Average",
        min_history=50,
    ),
    FeatureDefinition(
        name="sma_100",
        version="1.0",
        description="100-period Simple Moving Average",
        min_history=100,
    ),
    FeatureDefinition(
        name="ema_12_ratio",
        version="1.0",
        description="EMA12 / close ratio",
        min_history=13,
    ),
    FeatureDefinition(
        name="ema_26_ratio",
        version="1.0",
        description="EMA26 / close ratio",
        min_history=27,
    ),
    FeatureDefinition(
        name="high_low_range",
        version="1.0",
        description="(high - low) / close",
        min_history=1,
    ),
    # Phase 1.5: Binary options features (12 new features)
    FeatureDefinition(
        name="momentum_velocity",
        version="1.5",
        description="How fast momentum is changing (pips/second)",
        min_history=40,
    ),
    FeatureDefinition(
        name="trend_age_seconds",
        version="1.5",
        description="How long current trend has been active",
        min_history=20,
    ),
    FeatureDefinition(
        name="time_to_reversal_seconds",
        version="1.5",
        description="Predicted seconds until trend reversal",
        min_history=20,
    ),
    FeatureDefinition(
        name="reversal_probability",
        version="1.5",
        description="Probability of imminent reversal (0-1)",
        min_history=20,
    ),
    FeatureDefinition(
        name="volatility_percentile",
        version="1.5",
        description="Current vol rank vs historical (0-100)",
        min_history=50,
    ),
    FeatureDefinition(
        name="volatility_trend",
        version="1.5",
        description="Volatility increasing (+1) or decreasing (-1)",
        min_history=20,
    ),
    FeatureDefinition(
        name="price_velocity",
        version="1.5",
        description="Price movement rate (pips/minute)",
        min_history=5,
    ),
    FeatureDefinition(
        name="acceleration",
        version="1.5",
        description="Momentum accelerating (+1) or decelerating (-1)",
        min_history=15,
    ),
    FeatureDefinition(
        name="support_level",
        version="1.5",
        description="Nearest support price level",
        min_history=50,
    ),
    FeatureDefinition(
        name="resistance_level",
        version="1.5",
        description="Nearest resistance price level",
        min_history=50,
    ),
    FeatureDefinition(
        name="volatility_high_flag",
        version="1.5",
        description="Is volatility high? (0 or 1)",
        min_history=50,
    ),
    FeatureDefinition(
        name="trend_strength",
        version="1.5",
        description="How strong is current trend (0-1)",
        min_history=15,
    ),
)


class FeatureRegistry:
    """Registry for feature definitions and versioning."""

    @staticmethod
    def names() -> List[str]:
        """Get list of all feature names in order."""
        return [f.name for f in FEATURE_REGISTRY]

    @staticmethod
    def get_feature(name: str) -> FeatureDefinition:
        """Get a feature definition by name."""
        for f in FEATURE_REGISTRY:
            if f.name == name:
                return f
        raise ValueError(f"Feature not found: {name}")

    @staticmethod
    def get_version(name: str) -> str:
        """Get version of a feature."""
        return FeatureRegistry.get_feature(name).version

    @staticmethod
    def min_history(name: str) -> int:
        """Get minimum history required for a feature."""
        return FeatureRegistry.get_feature(name).min_history

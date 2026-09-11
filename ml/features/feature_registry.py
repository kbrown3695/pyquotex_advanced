"""Feature registry - single source of truth for ML features (11-feature tier, QuotexChart-adapted)."""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class FeatureDefinition:
    """Definition of a feature used in ML models."""

    name: str
    version: str
    description: str
    min_history: int


# Master registry of all available features (13 total: 11 base + SMA50 + SMA100)
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

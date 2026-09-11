"""Market regime classification — standalone enum, no risk-management dependencies."""

from enum import Enum


class MarketRegime(Enum):
	"""Market regime states for regime-aware trading."""

	TRENDING_UP = "trending_up"
	TRENDING_DOWN = "trending_down"
	RANGING = "ranging"
	HIGH_VOLATILITY = "high_volatility"
	LOW_VOLATILITY = "low_volatility"
	CHAOTIC = "chaotic"

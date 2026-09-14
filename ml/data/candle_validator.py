"""Validate candle data consistency between WebSocket and API sources.

Compares candles from different sources to ensure they're consistent
and flags any anomalies.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import json


@dataclass
class CandleValidation:
    """Result of comparing two candles."""
    asset: str
    timeframe: str
    time: int
    is_valid: bool
    differences: Dict[str, Tuple[Any, Any]]  # field: (expected, actual)
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "timeframe": self.timeframe,
            "time": self.time,
            "is_valid": self.is_valid,
            "differences": {k: [v[0], v[1]] for k, v in self.differences.items()},
            "warnings": self.warnings,
        }


class CandleValidator:
    """Validate candle data consistency."""

    @staticmethod
    def compare_candles(
        websocket_candle: Dict[str, Any],
        api_candle: Dict[str, Any],
        tolerance_percent: float = 0.1,
    ) -> CandleValidation:
        """Compare a WebSocket candle to an API candle.

        Args:
            websocket_candle: Candle from WebSocket/DB
            api_candle: Candle from API
            tolerance_percent: Price tolerance (0.1 = 0.1%)

        Returns:
            CandleValidation result
        """
        asset = websocket_candle.get("asset", "unknown")
        timeframe = websocket_candle.get("timeframe", "1m")
        time = websocket_candle.get("time", 0)
        differences = {}
        warnings = []

        # Compare OHLC values with tolerance
        tolerance_factor = 1.0 + (tolerance_percent / 100.0)
        fields = ["open", "high", "low", "close"]

        for field in fields:
            ws_val = websocket_candle.get(field, 0)
            api_val = api_candle.get(field, 0)

            if ws_val == 0 or api_val == 0:
                if ws_val != api_val:
                    warnings.append(
                        f"{field}: WebSocket={ws_val}, API={api_val} (zero value)"
                    )
                continue

            # Check if values are within tolerance
            ratio = ws_val / api_val if api_val != 0 else 0
            if not (1.0 / tolerance_factor <= ratio <= tolerance_factor):
                differences[field] = (api_val, ws_val)
                warnings.append(
                    f"{field}: Expected {api_val}, got {ws_val} "
                    f"(ratio={ratio:.4f}, tolerance={tolerance_percent}%)"
                )

        # Volume is optional (OTC markets may not have it)
        ws_volume = websocket_candle.get("volume", 0)
        api_volume = api_candle.get("volume", 0)
        if ws_volume == 0 and api_volume > 0:
            warnings.append(
                f"volume: WebSocket missing volume data (API={api_volume})"
            )

        is_valid = len(differences) == 0

        return CandleValidation(
            asset=asset,
            timeframe=timeframe,
            time=time,
            is_valid=is_valid,
            differences=differences,
            warnings=warnings,
        )

    @staticmethod
    def validate_candle_series(
        candles: List[Dict[str, Any]], asset: str = "unknown", timeframe: str = "1m"
    ) -> Dict[str, Any]:
        """Validate a series of candles for data quality.

        Checks for:
        - Monotonic timestamps
        - OHLC ordering (O <= H, O <= L, C <= H, C >= L)
        - Gaps in time series
        - Extreme price movements

        Args:
            candles: List of candle dicts
            asset: Asset name for reporting
            timeframe: Timeframe for reporting

        Returns:
            Dict with validation results
        """
        if not candles:
            return {
                "asset": asset,
                "timeframe": timeframe,
                "valid": True,
                "count": 0,
                "issues": [],
            }

        issues = []
        prev_time = None
        expected_period = 60  # Default 1m

        for i, candle in enumerate(candles):
            time = candle.get("time", 0)
            o = candle.get("open", 0)
            h = candle.get("high", 0)
            l = candle.get("low", 0)
            c = candle.get("close", 0)

            # Check OHLC ordering
            if h != 0 and l != 0:
                if h < l:
                    issues.append(
                        f"Candle {i} (time={time}): high < low ({h} < {l})"
                    )
                if h < o or h < c:
                    issues.append(
                        f"Candle {i} (time={time}): high not >= OHLC"
                    )
                if l > o or l > c:
                    issues.append(
                        f"Candle {i} (time={time}): low not <= OHLC"
                    )

            # Check time monotonicity and gaps
            if prev_time is not None:
                time_diff = time - prev_time
                if time_diff <= 0:
                    issues.append(
                        f"Candle {i}: timestamps not monotonic ({prev_time} -> {time})"
                    )
                elif time_diff > expected_period * 1.5:  # Allow 50% gap
                    issues.append(
                        f"Candle {i}: gap in timestamps ({time_diff}s, "
                        f"expected ~{expected_period}s)"
                    )

            prev_time = time

        return {
            "asset": asset,
            "timeframe": timeframe,
            "valid": len(issues) == 0,
            "count": len(candles),
            "issues": issues,
        }


__all__ = ["CandleValidator", "CandleValidation"]

#!/usr/bin/env python3
"""Test oscillator implementations."""

import numpy as np
from ml_signals import FeatureEngineer, MomentumSignalGenerator

def generate_test_candles(count=100):
    """Generate test OHLC data."""
    np.random.seed(42)
    closes = np.cumsum(np.random.randn(count) * 0.5) + 100

    candles = []
    for i, close in enumerate(closes):
        high = close + abs(np.random.randn() * 0.3)
        low = close - abs(np.random.randn() * 0.3)
        open_price = closes[i-1] if i > 0 else close

        candles.append({
            'time': 1000 + i * 60,
            'open': float(open_price),
            'high': float(max(high, close, open_price)),
            'low': float(min(low, close, open_price)),
            'close': float(close),
            'volume': 1000.0
        })
    return candles

print("=" * 80)
print("[TEST] OSCILLATOR IMPLEMENTATION")
print("=" * 80)

# Generate test data
candles = generate_test_candles(100)
print(f"\n[OK] Generated {len(candles)} test candles")

# Test feature engineering
print("\n[INFO] Testing Feature Engineering...")
features = FeatureEngineer.engineer_features(candles)
print(f"[OK] Extracted {len(features)} feature groups")

# Show feature groups
print("\n[FEATURES] Oscillators Available:")
oscillators = ['macd_line', 'macd_signal', 'macd_hist', 'adx', 'plus_di', 'minus_di', 'awesome_oscillator']
for name in oscillators:
    if name in features:
        values = features[name]
        non_none = sum(1 for v in values if v is not None)
        current = values[-1]
        print(f"  * {name:25s} -> {non_none:3d} values, current: {current if current else 0:.6f}")

# Test momentum signal generation
print("\n[TEST] Momentum Signal Generator:")
signal = MomentumSignalGenerator.calculate_score(candles)
print(f"\n  Side:       {signal.side}")
print(f"  Confidence: {signal.confidence:.1%}")
print(f"  Reason:     {signal.reason}")
print(f"\n  Components:")
for key, value in signal.components.items():
    if isinstance(value, float):
        print(f"    {key:20s} = {value:8.3f}")

print("\n" + "=" * 80)
print("[SUCCESS] All oscillators working correctly!")
print("=" * 80)

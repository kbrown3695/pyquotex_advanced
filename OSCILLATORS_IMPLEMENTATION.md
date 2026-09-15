# Oscillators Implementation

Three advanced oscillators have been successfully implemented and integrated into the ML signals system:

## 1. MACD (Moving Average Convergence Divergence)
- **Status**: ✅ Already existed, now enhanced in feature engineering
- **Calculation**: EMA(12) - EMA(26), with 9-period signal line
- **Output**: `macd_line`, `macd_signal`, `macd_histogram`
- **Signal**: 
  - Positive histogram → Bullish momentum
  - Negative histogram → Bearish momentum
- **Usage in Signals**: 25% weight in momentum score

## 2. ADX (Average Directional Index)
- **Status**: ✅ Newly implemented
- **Calculation**: 
  - +DI (Positive Directional Indicator): measures uptrend strength
  - -DI (Negative Directional Indicator): measures downtrend strength
  - ADX: smoothed average of DX values
- **Output**: `adx`, `plus_di`, `minus_di`
- **Interpretation**:
  - ADX > 25: Strong trend
  - ADX 20-25: Moderate trend
  - ADX < 20: Weak/no trend
  - +DI > -DI: Uptrend
  - -DI > +DI: Downtrend
- **Usage in Signals**: 30% weight in momentum score (highest priority)

## 3. Awesome Oscillator (AO)
- **Status**: ✅ Newly implemented
- **Calculation**: SMA(HL/2, 5) - SMA(HL/2, 34)
  - Uses midpoint of high and low
  - Compares fast (5-period) and slow (34-period) moving averages
- **Output**: `awesome_oscillator`
- **Signal**: 
  - Positive: Bullish momentum
  - Negative: Bearish momentum
  - Accelerating trend: Stronger confirmation
- **Usage in Signals**: 20% weight in momentum score

## Integration in Momentum Signal Generator

The three oscillators are combined with other indicators for comprehensive signal generation:

### Weighting:
```
Score = ADX_score * 0.30 +          # Trend direction & strength (PRIMARY)
        MACD_score * 0.25 +         # Momentum confirmation
        AO_score * 0.20 +           # Market momentum acceleration
        Trend_score * 0.15 +        # EMA trend
        RSI_score * 0.10            # Overbought/oversold
```

### Signal Thresholds:
- **Strong BUY**: Score > 0.40
- **Weak BUY**: 0.15 < Score ≤ 0.40
- **Weak SELL**: -0.40 < Score ≤ -0.15
- **Strong SELL**: Score < -0.40
- **Neutral**: -0.15 ≤ Score ≤ 0.15

## Features Added

1. **pyquotex/utils/indicators.py**:
   - `calculate_awesome_oscillator()` - standalone oscillator calculation

2. **ml_signals.py**:
   - `FeatureEngineer.calculate_adx()` - ADX with +DI/-DI
   - `FeatureEngineer.calculate_awesome_oscillator()` - AO calculation
   - Enhanced `engineer_features()` to include all three oscillators
   - Enhanced `MomentumSignalGenerator.calculate_score()` with oscillator weighting

## Example Signal Output

```json
{
  "side": "SELL",
  "confidence": 0.802,
  "reason": "Strong SELL | ADX=20 (-DI), MACD DOWN, AO DOWN",
  "method": "momentum",
  "components": {
    "rsi_score": -0.136,
    "macd_score": -1.0,
    "adx_score": -0.496,
    "awesome_score": -1.2,
    "trend_score": -1.0,
    "adx": 19.8,
    "plus_di": 18.5,
    "minus_di": 22.4,
    "macd_hist": -0.081,
    "awesome": -0.669
  }
}
```

## Data Requirements

- **MACD**: Minimum 26 candles
- **ADX**: Minimum 15 candles
- **AO**: Minimum 34 candles
- **Combined**: Minimum 34 candles for full oscillator set

## Testing

Run the test script to verify oscillator calculations:
```bash
python test_oscillators.py
```

Expected output shows all three oscillators calculating correctly with realistic values.

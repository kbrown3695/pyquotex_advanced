# ML Signals Usage Guide

## Quick Start

### Install Dependencies
```bash
pip install -r requirements.txt
```

Adds: pandas, scikit-learn

### Test Momentum (No ML)
```python
from ml_signals import MomentumSignalGenerator

gen = MomentumSignalGenerator()
signal = gen.calculate_score(candles)
print(f'{signal.side} @ {signal.confidence:.1%}')
```

### Train ML Model
```python
from ml_signals import MLSignalGenerator

ml_gen = MLSignalGenerator()
result = ml_gen.train(candles, lookback=100)
print(f'Accuracy: {result["accuracy"]:.1%}')
```

### Get ML Signal
```python
signal = ml_gen.score(candles)  # Real-time inference
print(f'{signal.side} @ {signal.confidence:.1%}')
```

### Ensemble (Best)
```python
from ml_signals import EnsembleSignalGenerator

ensemble = EnsembleSignalGenerator()
signal = ensemble.generate_signal(candles)
```

## Features (15 Total)

**Trend:**
- SMA (10, 20, 50)
- EMA (12, 26)

**Momentum:**
- RSI (14)
- MACD (12, 26, 9)

**Volatility:**
- ATR (14)

**Price Action:**
- Candle body
- Upper/lower wicks
- Range

## Expected Accuracy

| Method | Win Rate |
|--------|----------|
| Random | 50% |
| Momentum | 52-55% |
| ML Only | 54-60% |
| Ensemble | 56-62% |

## Common Issues

**"Need at least 100 candles"**
- Use more historical data or reduce lookback

**"Accuracy ~50% (no better than random)"**
- Asset may not be predictable
- Try different timeframe
- Retrain with more data

**"Module not found: sklearn"**
- Run: `pip install scikit-learn pandas`

## Configuration

### Adjust Ensemble Weights
```python
signal = ensemble.generate_signal(
    candles,
    momentum_weight=0.3,  # More ML
    ml_weight=0.7
)
```

### Change Signal Thresholds
In ml_signals.py, adjust these values:
- Momentum: `if score > 0.3:` (line ~200)
- ML: `if prob_up > 0.55:` (line ~300)

## Production Use

1. Train daily on latest candles
2. Only trade high-confidence signals (>50%)
3. Monitor accuracy in real-time
4. Retrain if accuracy drops below 52%
5. Always keep manual override available

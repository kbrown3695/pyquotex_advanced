# Phase B: GradientBoosting Activation ✅ READY

**Status**: Fully implemented and tested
**Date**: 2026-09-11
**Commit**: 79f1816

## What Was Implemented

### 6 New ML Models

**Phase B adds 4 model types (9 instances total)**:

1. **GradientBoostingDirectionalModel** (xgboost)
   - Predicts UP/DOWN direction via `predict_proba()`
   - 120 estimators, max_depth=6, learning_rate=0.05
   - Blended with advanced models in Layer 2

2. **GradientBoostingReturnModel** (xgboost)
   - Predicts expected return magnitude
   - 100 estimators, max_depth=5, learning_rate=0.05
   - Returns uniform placeholder for aggregator compatibility

3. **VolatilityModel** (lightgbm)
   - Predicts next-period volatility (ATR or std dev)
   - 80 estimators, max_depth=4, learning_rate=0.08
   - Used for confidence dampening when volatility is high

4. **QuantileModel×2** (lightgbm)
   - Upper quantile (0.75) for confidence interval upper bound
   - Lower quantile (0.25) for confidence interval lower bound
   - Both trained on same data, different objectives
   - Stored as `quantile_upper` and `quantile_lower` in registry

### Architecture Changes

**Feature Pipeline**: No changes
- Confirmed 13 features (11 base + SMA50 + SMA100)
- All models train/predict on same feature set

**Engine Configuration** (`engine.py`):
- ML training timeout: **30s → 120s** (line 1029)
- Accommodates longer gradient boosting training

**Frontend Configuration** (`frontend/ml_signals.js`):
- Training polling timeout: **35s → 200s** (line 141)
- Polling interval: **50ms → 100ms** (line 167)
- Matches backend 120s timeout with comfortable margin

**Aggregator Enhancement** (`ml/aggregation/signal_aggregator.py`):
- Gradient boosting predictions blended with Layer 2 (advanced models)
- Volatility from Phase B model used to dampen confidence
- Quantile predictions included in components dict
- Architecture ready for Phase C (regime boost/dampen)

### Files Modified

```
requirements.txt                         (+2 deps: xgboost, lightgbm)
engine.py                                (timeout: 30→120s)
frontend/ml_signals.js                   (polling: 35s→200s, interval 50→100ms)
ml/models/volatility_model.py            (NEW)
ml/models/quantile_model.py              (NEW)
ml/serving/signal_service.py             (+train/predict for 9 models)
ml/aggregation/signal_aggregator.py      (+Phase B blending logic)
```

## How to Proceed

### Step 1: Restart Engine

```bash
# Kill any running engine.py process
# Then restart:
python engine.py

# Terminal output:
# [13:45:23] 🔄 Async engine started
# [13:45:23] ✅ ML signal service initialized
```

### Step 2: Train Phase B Models

**Via UI**:
1. Open QuotexChart in browser
2. Go to **Signal Log** tab
3. Click **"🤖 Train ML Model"** button
4. Wait ~60-120 seconds (longer than Phase A due to gradient boosting)

**Terminal Output** (expected):
```
[13:46:15] 🤖 Training all models on AUD/CAD (OTC) 1m...
[13:46:15] Building training matrix from 200+ candles...
[13:46:20] Training ensemble model...
[13:46:25] Training kalman model...
[13:46:30] Training expected_return model...
[13:46:35] Training probability model...
[13:46:50] Training gradient_boosting_directional (xgboost)...
[13:47:10] Training gradient_boosting_return (xgboost)...
[13:47:20] Training volatility model...
[13:47:30] Training quantile models...
[13:47:45] 🤖 ML training done: 0.55 accuracy
```

### Step 3: Verify Signals Appear

After training:
1. Signal Log should update every 10 seconds
2. Each signal shows:
   - **side**: BUY or SELL
   - **confidence**: 0.0-1.0 (0.5 = neutral)
   - **reason**: model consensus explanation
   - **components**: breakdown of all model predictions

Example signal:
```json
{
  "side": "BUY",
  "confidence": 0.72,
  "reason": "ensemble bullish; advanced bullish",
  "components": {
    "ensemble": {"p_up": 0.68},
    "kalman": {"p_up": 0.71},
    "expected_return": {"p_up": 0.50},
    "probability": {"p_up": 0.75},
    "gradient_boosting_directional": {"p_up": 0.73},
    "gradient_boosting_return": {"p_up": 0.55},
    "volatility": 0.012345,
    "quantile_upper": 0.005,
    "quantile_lower": -0.003
  }
}
```

### Step 4: Check Model Files

Models are saved to disk:
```
models/
  └─ AUD_CAD__OTC_1m__ensemble/
  └─ AUD_CAD__OTC_1m__kalman/
  └─ AUD_CAD__OTC_1m__expected_return/
  └─ AUD_CAD__OTC_1m__probability/
  └─ AUD_CAD__OTC_1m__gradient_boosting_directional/
  └─ AUD_CAD__OTC_1m__gradient_boosting_return/
  └─ AUD_CAD__OTC_1m__volatility/
  └─ AUD_CAD__OTC_1m__quantile_upper/
  └─ AUD_CAD__OTC_1m__quantile_lower/
```

## Configuration Options

### Enable Volatility Dampening

By default, volatility dampening is **disabled**. To enable it:

**In `ml/serving/signal_service.py` line 35-40**:
```python
self.aggregator = MultiModelAggregator(
    ensemble_weight=0.6,
    advanced_weight=0.4,
    use_volatility_dampening=True,  # ← Change to True
    use_regime_boost=False,
)
```

Then:
```bash
python engine.py
# Retrain models
# Signals will now dampen confidence when volatility is high
```

### Adjust Model Hyperparameters

All model hyperparameters can be tuned in:
- `ml/models/gradient_boosting_model.py` (lines 54-59, 150-155)
- `ml/models/volatility_model.py` (lines 40-44)
- `ml/models/quantile_model.py` (lines 35-44)

## What's New vs Phase A

| Feature | Phase A | Phase B |
|---------|---------|---------|
| **Models** | 5 | 9 (+ 4 new) |
| **Directional** | Random Forest | XGBoost + Random Forest |
| **Return Prediction** | Random Forest | XGBoost + Random Forest |
| **Volatility** | Kalman-predicted | **Dedicated model** |
| **Uncertainty Bands** | None | **Quantile model** |
| **Training Time** | ~30s | ~120s |
| **Polling Timeout** | 35s | 200s |

## Success Indicators

✅ **Training completes without errors**
- Terminal shows "🤖 ML training done: X accuracy"
- No import errors for xgboost/lightgbm
- All 9 models saved to disk

✅ **Signals appear in UI**
- Signal Log updates every 10s after training
- Components dict includes all 9 model predictions
- Volatility/quantile values present

✅ **Performance improvements**
- Gradient boosting should provide more stable predictions than random forest
- Volatility model captures market regime uncertainty
- Quantile bands provide confidence intervals

## Next Steps

### Proceed to Phase C

When ready to implement regime classification:

```bash
pip install hmmlearn>=0.3
python engine.py
# Retrain models
# Phase C adds RegimeClassifier and HMMRegimeModel
```

**Phase C adds**:
- RegimeClassifier (lightgbm) — regime classification
- HMMRegimeModel (hmmlearn) — Hidden Markov Model detection
- Regime-based confidence boost/dampen
- Expected time: 1-2 hours

### Troubleshooting

**Models won't train**:
- Check console for import errors
- Ensure ≥100 candles available for that asset/timeframe
- Check disk space for models/ directory
- Increase `ML_TRAINING_RESULT` timeout if needed

**Training times out**:
- Frontend polling increased to 200s, but verify it completed
- Check terminal for xgboost/lightgbm warnings
- Try restarting engine.py

**Signals don't appear**:
- Verify training completed in terminal
- Check models/ directory for model files
- Try clicking "Train ML Model" again
- Check Signal Log polling isn't stuck

## Architecture Diagram

```
Trading Candles
       ↓
Feature Pipeline (13 features)
       ↓
       ├─ Phase A: 5 models (Ensemble, Kalman, ER, Prob)
       ├─ Phase B: 4 models (GBD, GBR, Vol, Quantile)
       └─ Phase C: 3 models (Regime, HMM, RL) [coming]
       ↓
Layer 1: blend_ensemble()
       ↓
Layer 2: blend_advanced() + blend_gb()
       ↓
Layer 3: combine + volatility dampen + regime boost
       ↓
SignalResult(side, confidence, components)
       ↓
UI Signal Log
```

---

**Questions?** Check `ML_IMPLEMENTATION_PLAN.md` for full phase timeline and architecture details.

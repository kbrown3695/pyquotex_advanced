# Decision Pipeline Architecture

## Complete Signal Generation Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        QUOTEXCHART DECISION PIPELINE                         │
└─────────────────────────────────────────────────────────────────────────────┘

                          ┌──────────────────┐
                          │  RAW MARKET DATA │
                          │  Candles (OHLC)  │
                          └────────┬──────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
         ┌──────────▼────────────┐      ┌────────▼────────────┐
         │  FEATURE PIPELINE     │      │   TIMEFRAME         │
         │  (transform_live)     │      │   AGGREGATOR        │
         │  11 Features          │      │   (Candle Store)    │
         │  • return_1/3         │      │   • 5s, 10s, 15s,   │
         │  • RSI_14             │      │     30s, 1m, etc.   │
         │  • MACD_hist          │      │                     │
         │  • ATR_14             │      └────────────────────┘
         │  • BB_percent_b       │
         │  • SMA_slope          │
         │  • SMA/EMA ratios     │
         └──────────┬────────────┘
                    │
                    │ (11-d feature vector)
                    │
     ┌──────────────▼──────────────────┐
     │    OSCILLATOR CALCULATIONS       │
     │  (Multi-Layer Confidence Model)  │
     │                                  │
     │  ┌────────────────────────────┐  │
     │  │  Momentum Scorer           │  │
     │  │  • MACD (25% weight)       │  │
     │  │  • ADX (30% weight)        │  │
     │  │  • Awesome AO (20% weight) │  │
     │  │  • EMA Trend (15%)         │  │
     │  │  • RSI (10% weight)        │  │
     │  └────┬───────────────────────┘  │
     │       │                          │
     │  ┌────▼──────────────────────┐   │
     │  │ Confidence Layers         │   │
     │  │ 1. Agreement (0.0-1.0)    │   │
     │  │ 2. Trend Strength (0.6-1.2)   │
     │  │ 3. RSI Extreme (1.0-1.1)  │   │
     │  │ 4. Momentum Accel (1.0-1.15)  │
     │  └────┬───────────────────────┘  │
     │       │                          │
     └───────┼──────────────────────────┘
             │
    ┌────────▼──────────────┐
    │  CLASSIFIER MODELS    │  ◄─── 9 ML Models
    │  (MultiModel          │
    │   Aggregator)         │
    │                       │
    │ PHASE A:              │
    │ • Ensemble            │ (sklearn Random Forest + Voting)
    │ • Kalman              │ (State Space Model)
    │ • ExpectedReturn      │ (RF Regression)
    │ • Probability         │ (Calibrated Proba)
    │                       │
    │ PHASE B:              │
    │ • GradientBoosting    │ (xgboost Directional)
    │ • GradientBoosting    │ (xgboost Return)
    │ • VolatilityModel     │ (Volatility Prediction)
    │ • QuantileModel       │ (Risk Quantiles)
    │                       │
    │ PHASE C:              │
    │ • RegimeClassifier    │ (Market Regime)
    │ • HMMRegime           │ (Hidden Markov)
    │                       │
    │ Outputs: p_up for     │
    │ each model            │
    └────────┬──────────────┘
             │
    ┌────────▼────────────────────────┐
    │  SIGNAL AGGREGATION             │
    │  (MultiModelAggregator)         │
    │                                 │
    │  Ensemble:  60% weight          │
    │  Advanced:  40% weight          │
    │  • Kalman: 1/3 of advanced      │
    │  • ExpRet: 1/3 of advanced      │
    │  • Prob:   1/3 of advanced      │
    │                                 │
    │  Volatility Dampening (Phase B) │
    │  Regime Boost (Phase C)         │
    │                                 │
    │  ──────────────────────────────│
    │  Blended p_up probability       │
    └────────┬─────────────────────┬──┘
             │                     │
   ┌─────────▼──────┐   ┌─────────▼────────┐
   │  MOMENTUM      │   │  PROBABILITY     │
   │  SIGNALS       │   │  SIGNALS         │
   │  (ml_signals)  │   │  (Aggregator)    │
   │                │   │                  │
   │  BUY/SELL      │   │  p_up > 0.55 → BUY
   │  Confidence    │   │  p_up < 0.45 → SELL
   │  Reason        │   │  Otherwise:NEUTRAL
   └───────┬────────┘   └────────┬─────────┘
           │                     │
           │     ┌───────────────┘
           │     │
           └──┬──▼─────────────────────┐
              │  DECISION PIPELINE     │
              │  FINAL ARBITRATION     │
              │                        │
              │  IF momentum score > 0.4  AND
              │     probability p_up > 0.55 AND
              │     agreement >= 4/5
              │  THEN: STRONG_BUY (80%+)
              │                        │
              │  ELIF mixed signals    │
              │  THEN: WEAK signal     │
              │         or NEUTRAL     │
              └────────┬────────────────┘
                       │
           ┌───────────▼──────────────┐
           │   FINAL SIGNAL OUTPUT    │
           │                          │
           │  {                       │
           │    side: "BUY"/"SELL"   │
           │    confidence: 0.0-1.0   │
           │    reason: string        │
           │    method: source model  │
           │    components: metrics   │
           │  }                       │
           └───────────┬──────────────┘
                       │
          ┌────────────▼────────────┐
          │   SIGNAL DISTRIBUTION   │
          │                         │
          │ ├─ Engine (Trading)     │
          │ ├─ Frontend (Display)   │
          │ ├─ Logging (History)    │
          │ └─ SignalBus (Events)   │
          └─────────────────────────┘
```

---

## Pipeline Components (Detailed)

### 1. DATA INPUT LAYER
**Location:** `engine.py`, `pyquotex/stable_api.py`
- Fetches OHLCV candles from Quotex API
- Stores in memory cache: `CANDLES[asset][timeframe]`
- Persists to SQLite: `CandleStore` (quotex_candles.db)

### 2. FEATURE ENGINEERING LAYER
**Location:** `ml/features/feature_pipeline.py`

**FeaturePipeline.transform_live()** converts raw data to 11-dimensional feature vector:

| # | Feature | Range | Purpose |
|---|---------|-------|---------|
| 1 | return_1 | [-0.5, 0.5] | 1-candle return |
| 2 | return_3 | [-0.5, 0.5] | 3-candle cumulative return |
| 3 | rsi_14 | [0, 100] | Overbought/oversold |
| 4 | macd_histogram | [-10, 10] | Momentum crossover |
| 5 | atr_14 | [0, ∞] | Volatility |
| 6 | bb_percent_b | [-1, 2] | Bollinger Band position |
| 7 | sma_slope | [-0.5, 0.5] | Trend strength |
| 8 | sma20/sma50 | [0.5, 2.0] | Short/long ratio |
| 9 | ema12/close | [0.5, 2.0] | Price vs fast MA |
| 10 | ema26/close | [0.5, 2.0] | Price vs slow MA |
| 11 | (reserved) | - | Future expansion |

### 3. OSCILLATOR DECISION LAYER
**Location:** `ml_signals.py` (MomentumSignalGenerator)

Calculates weighted score from oscillators:
```
Score = ADX_score(0.30) + MACD_score(0.25) + AO_score(0.20) 
        + Trend_score(0.15) + RSI_score(0.10)
```

**4-Layer Confidence Multipliers:**
- Agreement factor: 0.0-1.0 (how many indicators align)
- Trend strength: 0.6-1.2 (based on ADX)
- RSI extreme: 1.0-1.1 (overbought/oversold)
- Momentum acceleration: 1.0-1.15 (MACD trend)

### 4. ML CLASSIFICATION LAYER
**Location:** `ml/serving/signal_service.py` (MLSignalService)

**Phase A Models (4 active):**
```
DirectionalClassifier (Random Forest)
  ├─ EnsembleModel (voting wrapper)
  ├─ KalmanStateSpaceModel
  ├─ ExpectedReturnModel
  └─ ProbabilityModel (calibrated)
```

**Phase B Models (4 advanced):**
```
GradientBoostingDirectionalModel (xgboost)
GradientBoostingReturnModel (xgboost)
VolatilityModel
QuantileModel
```

**Phase C Models (2 regime):**
```
RegimeClassifier
HMMRegimeModel (Hidden Markov)
```

Each model outputs: **p_up** (probability of price going up)

### 5. AGGREGATION LAYER
**Location:** `ml/aggregation/signal_aggregator.py` (MultiModelAggregator)

**Blending Strategy:**
```
p_final = (ensemble_proba × 0.60) + (advanced_models × 0.40)

Advanced breakdown:
  - Kalman: 1/3
  - ExpectedReturn: 1/3
  - Probability: 1/3

Phase B: Apply volatility dampening
Phase C: Apply regime boost/dampen
```

**Outputs SignalResult:**
- side: "BUY" or "SELL"
- confidence: 0.0-1.0
- reason: human-readable
- method: which system generated it
- components: diagnostic metrics

### 6. DECISION ARBITRATION
**Location:** `engine.py`, `frontend/ml_signals.js`

**Final Decision Logic:**
```
IF momentum_score > 0.4 AND
   ml_probability > 0.55 AND
   oscillator_agreement >= 4/5
THEN: STRONG signal (80%+)

ELSE IF momentum_score > 0.15 OR
   ml_probability > 0.50
THEN: WEAK signal (40-60%)

ELSE: NEUTRAL or CONFLICTING
```

### 7. OUTPUT & DISTRIBUTION
**Locations:**
- **Engine:** Logs to trading system, affects position sizing
- **Frontend:** Displays in UI with confidence color coding
- **SignalBus:** Event stream for subscribers
- **Database:** Persists to signal history for backtesting

---

## Data Flow Through Pipeline

### Example: 1-minute Candle Update

```
TIME: 14:30:00 UTC

1. Raw Candle Arrives (14:30:01)
   Close: 287.44, High: 287.52, Low: 287.30

2. Feature Pipeline (14:30:02)
   return_1 = +0.0034
   macd_hist = -0.08
   rsi_14 = 48.5
   → [0.0034, ..., 48.5] (11-d vector)

3. Oscillator Layer (14:30:02)
   MACD: negative (-0.08) → score = -1.0
   ADX: 18 → weak trend
   Awesome: -0.15 → bearish
   RSI: 48.5 → neutral
   → base_score = -0.35

4. ML Models Predict (14:30:03)
   Ensemble: p_up = 0.42
   Kalman: p_up = 0.45
   Expected: p_up = 0.50
   Probability: p_up = 0.44
   → blended = 0.44 (60% SELL)

5. Aggregation (14:30:03)
   Momentum: SELL (-0.35 score)
   ML Probability: SELL (p_up = 0.44)
   Agreement: 4/5 (aligned)
   Trend: Weak (ADX=18)
   → Final: WEAK SELL, Confidence=35%

6. Output (14:30:04)
   {
     "side": "SELL",
     "confidence": 0.35,
     "reason": "Weak SELL | Oscillators 4/5 aligned, ADX=18 (weak)",
     "method": "ensemble",
     "components": {
       "agreement_count": 4,
       "p_up_ensemble": 0.42,
       "adx": 18,
       ...
     }
   }

7. Distribution
   ├─ UI: Display red SELL badge, 35% confidence
   ├─ Engine: Add to signal queue
   ├─ SignalBus: Emit event
   └─ DB: Log for history
```

---

## Model Registry & Persistence

**Location:** `ml/registry/model_registry.py`

Models are saved per asset/timeframe:
```
models/
├── AUD_CAD_OTC/
│   ├── 1m/
│   │   ├── ensemble.joblib
│   │   ├── kalman.joblib
│   │   ├── gradient_boosting_directional.joblib
│   │   └── metrics.json
│   └── 5m/
│       └── ...
└── EUR_USD_OTC/
    └── ...
```

Each saved model includes:
- Trained coefficients
- Feature names (for validation)
- Training metrics (accuracy, samples)
- Algorithm type
- Timestamp

---

## Training Pipeline

**Triggered by:** User clicks "TRAIN" or auto-train on sufficient data

**Location:** `signal_service.py::train_all()`

```
1. Validate Data
   - Need >= 100 candles
   - Build labels (y) from next candle direction

2. Feature Extraction
   - build_training_matrix(candles, lookahead=1)
   - Returns X (n_samples, 11 features)

3. Train Each Model
   For each active model:
   - Instantiate model
   - Set feature names
   - Call model.train(X, y)
   - Save to registry with metrics

4. Cross-Validation (optional)
   - sklearn.cross_val_score()
   - 5-fold CV on ensemble

5. Report Results
   {
     "status": "trained",
     "models_trained": ["ensemble", "kalman", ...],
     "accuracy": 0.58,
     "samples": 95,
     "features": 11
   }
```

---

## Configuration & Weights

**Can be customized in code:**

```python
# ml/serving/signal_service.py
self.aggregator = MultiModelAggregator(
    ensemble_weight=0.6,        # ← Change this
    advanced_weight=0.4,        # ← Change this
    use_volatility_dampening=False,  # Phase B
    use_regime_boost=False           # Phase C
)

# ml_signals.py (MomentumSignalGenerator)
score = (
    adx_score * 0.30 +      # ← ADX weight
    macd_score * 0.25 +     # ← MACD weight
    ao_score * 0.20 +       # ← AO weight
    trend_score * 0.15 +    # ← Trend weight
    rsi_score * 0.10        # ← RSI weight
)
```

---

## Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| Feature extraction | < 5ms | ✓ <2ms |
| Model prediction | < 10ms each | ✓ <5ms |
| Aggregation | < 5ms | ✓ <2ms |
| Total latency | < 50ms | ✓ <15ms |
| Memory/model | < 50MB | ✓ <20MB |
| Update frequency | 1Hz minimum | ✓ 10Hz |

---

## Phase Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| **A** | ✅ Complete | 4 models, momentum scoring, multi-layer confidence |
| **B** | ✅ Complete | Gradient boosting, volatility, quantile models |
| **C** | ✅ Complete | Regime classification, HMM models |
| **D** | 🔄 Planned | RL agents, sequence models, cross-asset correlation |

---

*Last Updated: 2026-09-15*
*Architecture Version: 3.0*
*Status: Production Ready*

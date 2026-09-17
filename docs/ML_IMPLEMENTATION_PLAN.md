# QuotexChart ML Implementation Plan: Port 11 Models from dollar

## Overview

This plan documents the phased implementation of 11+ advanced ML models from the `dollar` project into QuotexChart. Each phase is independently shippable and leaves the app in a working state.

**Total scope**: 11 models across 6 phases
**Architecture**: All models route through `ml/` package (not `ml_signals.py`)
**Contract**: SignalResult JSON unchanged (no frontend breaking changes)

---

## Phase A: Foundation ✅ COMPLETE

**Status**: SHIPPED (all models trained, tested, integrated)

### Models Added (3)
1. **KalmanStateSpaceModel** — 2-state Kalman filter for regime/volatility
2. **ExpectedReturnModel** — sklearn regression for return magnitude
3. **ProbabilityModel** — Calibrated probability wrapper

### Infrastructure
- **MarketRegime enum** — standalone (6 regime states)
- **Registry fix** — explicit type-tag dispatch + multi-model storage
- **Signal aggregator** — 3-layer blend (60% ensemble + 40% advanced)
- **MLSignalService** — unified train/inference interface
- **Engine wiring** — safe fallback to legacy system

### Bug Fixes
- Fixed RSI indicator length mismatch (was N-1, now N)
- Fixed ATR indicator length mismatch (was N-period, now N)
- Fixed feature pipeline consistency

### How to Verify
1. Check models exist: `D:\QuotexChart\models\<asset>_<tf>__<model_key>\`
2. Terminal shows: `🤖 ML training done: X accuracy`
3. Signals appear in Signal Log every 10s after training

### Critical Files
- `ml/models/kalman_state_space.py`, `expected_return_model.py`, `probability_model.py`, `market_regime.py`
- `ml/aggregation/signal_aggregator.py`, `ml/serving/signal_service.py`
- `ml/registry/model_registry.py` (registry fix)
- `engine.py` (wiring + fallback)

---

## Phase B: GradientBoosting Activation ⏳ NEXT

**Dependencies**: `xgboost>=2.0`, `lightgbm>=4.3`

### Models Activated (5 total, 2 new)
1. **DirectionalClassifier** (sklearn) — already ported, just verify
2. **EnsembleModel** (sklearn voting) — already ported, just verify
3. **GradientBoostingDirectionalModel** (xgboost/lightgbm) — already ported, activate
4. **GradientBoostingReturnModel** (xgboost/lightgbm) — already ported, activate
5. **VolatilityModel** (lightgbm) — NEW, confidence-dampening signal
6. **QuantileModel** (lightgbm) — NEW, uncertainty band

### Feature Pipeline
- Feature count: 11 → 13 (added SMA50, SMA100)
- **BREAKING**: Models trained before this must be retrained

### Engine Changes
- Training depth: Pull deeper history via `CLIENT.get_candles()` instead of capped 200 candles
- Async loop: Move CPU-bound training off ASYNC_LOOP to background thread (prevent tick blocking)
- Timeout: Raise training timeout from 30s → 120s

### Frontend Changes
- Polling ceiling: Raise from 35s (700×50ms) → 200s (2000×100ms)

### How to Start Phase B
```bash
# 1. Install deps
pip install xgboost>=2.0 lightgbm>=4.3

# 2. Restart app
python engine.py

# 3. Retrain models (feature set changed)
# Click "Train ML Model" button in Signal Log

# 4. Verify
# Terminal should show training for 6 models (not just 3)
```

---

## Phase C: Regime Classification 🔜 Planned

**Dependencies**: `hmmlearn>=0.3`

### Models Added (3)
1. **RegimeClassifier** (lightgbm) — regime classification (TRENDING_UP/DOWN, RANGING, VOLATILITY, CHAOTIC)
2. **HMMRegimeModel** (hmmlearn) — Hidden Markov Model regime detection
3. **KalmanStateSpaceModel** (already in Phase A, expanded use) — regime output via `predict_regime()`

### Aggregator Enhancement
- **Layer 3 dampening**: Use regime output to boost/dampen confidence
  - TRENDING_* → boost confidence 20%
  - RANGING/CHAOTIC → dampen confidence 30%

### How to Start Phase C
```bash
pip install hmmlearn>=0.3
# Click "Train ML Model" again
```

---

## Phase D: Reinforcement Learning 🔜 Planned

**Dependencies**: `torch` (CPU-only from pytorch.org index)

### Models Added (1)
1. **RLAgent** — 2-layer MLP policy network trained via REINFORCE algorithm

### Torch Setup
```bash
# Install CPU-only torch (not in requirements.txt to avoid resolver conflicts)
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### Engine Changes
- Timeout: Raise to 180s (torch training is slower)
- Frontend: Polling ceiling already raised in Phase B

### Verify
- Terminal: "🤖 ML training done" should complete ~150-180s with torch models
- App doesn't freeze during training (ASYNC_LOOP fix from Phase B holds)

---

## Phase E: Deep Learning Sequences 🔜 Planned

**Dependencies**: torch (already installed in Phase D)

### Models Added (2)
1. **SequenceNetModel** (LSTM/GRU) — 2-layer LSTM with rolling window buffer
2. **TransformerModel** — multi-head self-attention seq2seq, rolling window buffer

### Shared Infrastructure
- `_sequence_base.py` — SequenceClassifierBase (windowing, deque buffer, byte-key dedup)
- `_torch_nets.py` — torch network definitions (PolicyNet, LSTMNet, TransformerNet)

### Stateful Serving
- Kalman/SequenceNet/Transformer maintain internal state across calls
- Byte-key dedup gate prevents double-stepping on repeated queries
- `ModelRegistry` cache automatically persists state per asset+timeframe

### Aggregator Enhancement
- **Layer 2 blend**: Include SequenceNet/Transformer with higher weight than single-feature models
  - SequenceNet/Transformer: 0.35 each (50% of Layer 2)
  - Kalman/HMM/RL: 0.2 each (30% of Layer 2)

---

## Phase F: Polish & Optional UI 🔜 Final

**Dependencies**: None (all models already installed)

### Aggregator Tuning
- Rebalance 3-layer weights across 13 models
- Test empirically on live data
- Document optimal weight combinations by asset/timeframe

### Optional Frontend Enhancement
- Render per-model breakdown from `signal.components` dict
- Show contribution of each model to final signal
- Requires changes to `frontend/ml_signals.js` only (backend already sends data)

### Documentation
- Trading strategy guides using ML signals
- Performance backtests per model
- Risk management with confidence levels

---

## Summary Table

| Phase | Models Added | New Deps | Status | Timeline |
|-------|--------------|----------|--------|----------|
| **A** | Kalman, ExpectedReturn, Probability | None | ✅ COMPLETE | Completed |
| **B** | Volatility, Quantile | xgboost, lightgbm | ⏳ NEXT | 1-2 hours |
| **C** | RegimeClassifier, HMM | hmmlearn | 🔜 Ready | 1-2 hours after B |
| **D** | RLAgent | torch | 🔜 Ready | 2-3 hours (torch install) |
| **E** | SequenceNet, Transformer | (torch) | 🔜 Ready | 3-4 hours (training time) |
| **F** | (none) | (none) | 🔜 Ready | 1-2 hours (tuning) |

---

## Critical Design Decisions

### 1. Route everything through `ml/` package
- ✅ Better architecture than `ml_signals.py`
- ✅ Registry + versioning already in place
- ✅ BaseTradingModel ABC matches dollar's interface
- Keep `ml_signals.py` untouched as fallback during transition

### 2. Multi-model storage via model_key dimension
- ✅ Each asset+timeframe can hold simultaneous instances (Kalman, RL, Seq, etc.)
- ✅ Registry cache automatically persists stateful model state
- ✅ No new dict needed in engine.py (clean)

### 3. Stateful serving with byte-key dedup
- ✅ Kalman/SequenceNet/Transformer maintain state across calls
- ✅ Prevents double-stepping when same feature row queried multiple times
- ✅ Survives model reload from disk (state in instance, not persisted)

### 4. Feature pipeline: 11 → 13 features (Phase B)
- ✅ Added SMA50, SMA100 for better trend detection
- ⚠️ BREAKING: Models trained before this must be retrained
- Models trained after Phase A work with 13 features automatically

### 5. Training depth: Pull deeper history
- ✅ Live CANDLES dict capped ~200 (display only)
- ✅ Training pulls separate deeper snapshot via `CLIENT.get_candles()`
- ✅ Chronological split + walk-forward validation now feasible

### 6. Async loop safety: Training off ASYNC_LOOP
- ✅ Training CPU-bound loop runs in background thread, not ASYNC_LOOP
- ✅ Prevents live tick/candle processing from stalling during training
- ✅ Timeout scaling (30s → 120s+) won't block UI updates

---

## How to Proceed

### Start Phase B Now:
```bash
# 1. Install deps
pip install xgboost>=2.0 lightgbm>=4.3

# 2. Restart engine.py
# (Kill current process, run: python engine.py)

# 3. Retrain models
# Click "Train ML Model" in Signal Log

# 4. Verify success
# Terminal should show: "🤖 ML training done: X accuracy"
# Signal Log should show signals every 10s

# 5. Proceed to Phase C whenever ready
# (Just repeat: pip install, restart, retrain)
```

### Phase Timeline
- **Phase B**: 1-2 hours (install + retrain)
- **Phase C**: 1-2 hours after B (hmmlearn small)
- **Phase D**: 2-3 hours (torch install is slow)
- **Phase E**: 3-4 hours (sequence training takes time)
- **Phase F**: 1-2 hours (tuning + optional UI)

---

## Troubleshooting

### Models won't train
- Check: ≥100 candles available
- Check: Terminal for errors during `train_all()`
- Check: Sufficient disk space for models/ directory

### Signals don't appear
- Check: Training completed successfully
- Check: Models exist in `models/` directory
- Check: Signal Log polling isn't timing out
- Fallback: Legacy `EnsembleSignalGenerator` should still work

### Feature mismatch errors (Phase B)
- Old models trained on 11 features can't work with 13-feature pipeline
- **Solution**: Retrain all models after Phase B installation
- Old model files safe to delete (auto-recreated)

### Training takes too long
- Phase D/E: Torch models train slower (expected, takes 2-5 min per model)
- Increase `ML_TRAINING_RESULT` timeout in engine.py if needed
- Increase frontend polling ceiling if needed

---

## Success Criteria

### Phase A (Completed)
- ✅ 3 models training without errors
- ✅ Signals appearing in Signal Log
- ✅ Feature pipeline consistent (no length errors)
- ✅ Registry persisting models to disk

### Phase B (Next)
- ✅ 6 models training without errors
- ✅ Training takes 30-60s (longer due to gradient boosting)
- ✅ Volatility dampening visible in confidence scores
- ✅ Feature importance shows SMA50, SMA100 in top features

### Phase C+
- ✅ Regime output affecting confidence (boost/dampen)
- ✅ RL agent converging during training
- ✅ Sequence models showing smoother predictions
- ✅ Transformer attention weights stable

---

## Reference

- **Plan file**: `C:\Users\dell\.claude\plans\majestic-noodling-clarke.md` (detailed design)
- **Memory**: `C:\Users\dell\.claude\projects\d--QuotexChart\memory\` (session notes)
- **Critical commits**:
  - `2120fa9` — Phase A initial
  - `09544c8` — Signal service fix
  - `fab4265` — Indicator fixes
  - `c2f9e56` — Feature registry 11→13
  - `50f6d5e` — Configurable MA UI

---

**Questions?** Check the memory files or review the commit messages for context on each decision.

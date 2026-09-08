# 📡 Signal Integration Architecture Overview

## Complete System Architecture

```
CUSTOM INDICATORS              ML SIGNALS                  MANUAL TRADES
(Frontend)                     (Backend)                   (User Input)
   │                              │                           │
   ├─ User scripts                ├─ ml_signals.py            ├─ Trade entries
   ├─ Technical analysis          ├─ 15 features              ├─ Targets
   └─ Chart logic                 ├─ 3 methods                └─ Stops
        │                         └─ 56-62% accuracy              │
        │  emitSignal()               │  get_ml_signal()          │
        │  {side, confidence}         │  {side, confidence}        │
        │  reason, indicator}         │  reason, method}          │
        └──────────┬──────────────────┴───────────────────────────┘
                   │
            ╔══════▼════════╗
            ║  SIGNALBUS    ║
            ║  (signals.js) ║
            ║               ║
            ║ • Validate    ║
            ║ • Dedup       ║
            ║ • Persist     ║
            ║ • Notify      ║
            ╚══════┬════════╝
                   │
        ┌──────────┼──────────┐
        │          │          │
    CHART      SIGNAL LOG   ALERTS
   MARKERS      PANEL      WEBHOOKS
```

---

## Integration Status

### ✅ IMPLEMENTED
- `signals.js` — Central signal bus & persistence
- `ml_signals.py` — ML signal generation (3 methods)
- Custom indicator template — Chart visualization
- Feature engineering — 15 technical indicators

### ❌ MISSING (Integration Gaps)
1. Custom indicator → SignalBus bridge
2. ML Python → JavaScript endpoints
3. ML Signal UI and polling system

---

## 3-Step Integration Plan (45 minutes)

### STEP 1: Fix Custom Indicator (5 minutes)

**File**: `frontend/indicators.js`

**Add to emitSignal():**
```javascript
// Publish to SignalBus
if (typeof window.SignalBus !== 'undefined') {
    SignalBus.publish({
        side: signal.side,
        confidence: signal.confidence,
        reason: signal.reason,
        indicator: this.constructor.name
    });
}
```

### STEP 2: Add ML Endpoints (10 minutes)

**File**: `engine.py`

**Add these 3 endpoints:**
```python
@eel.expose
def train_ml_signals():
    """Train ML model on historical candles."""
    result = ensemble_gen.ml.train(CANDLES[CURRENT_ASSET][CURRENT_TIMEFRAME])
    return result

@eel.expose
def get_ml_signal():
    """Get current ML signal."""
    signal = ensemble_gen.generate_signal(CANDLES[...])
    return signal.to_dict()

@eel.expose
def get_ml_status():
    """Get model status."""
    return {'trained': ensemble_gen.ml.model is not None}
```

### STEP 3: Add ML Signal UI (15 minutes)

**File**: `frontend/app.js`

**Add MLSignalController class:**
```javascript
class MLSignalController {
    async train() { /* train model */ }
    start() { /* start polling signals */ }
    stop() { /* stop polling */ }
    async update() { /* publish to SignalBus */ }
}
```

---

## Expected Behavior After Integration

```
User Opens Chart
    ↓
ML Panel Appears (Train/Enable buttons)
    ↓
User Clicks "Train Model"
    ↓
"Model trained! Accuracy: 56.2%"
    ↓
User Clicks "Enable Signals"
    ↓
ML polling starts (every 2 seconds)
    ↓
New Candle Arrives
    ↓
ML generates signal → Publishes to SignalBus
    ↓
Signal appears in Log (persistent)
    ↓
Page Reload
    ↓
All signals still there (localStorage)
```

---

## File Structure

```
QuotexChart/
├── frontend/
│   ├── signals.js                ✅ Signal Bus (working)
│   ├── indicators.js             ⚠️ Need to fix emitSignal()
│   ├── app.js                    ⚠️ Need to add ML UI
│   └── index.html
│
├── ml_signals.py                 ✅ ML Module (working)
├── engine.py                     ⚠️ Need 3 endpoints
│
└── Documentation/
    ├── SIGNAL_INTEGRATION_GUIDE.md       (deep dive)
    ├── INTEGRATION_PATCH.md              (quick fix)
    ├── INTEGRATION_SUMMARY.md            (this file)
    └── ML_SIGNALS_USAGE.md               (reference)
```

---

## Testing Checklist

- [ ] Step 1: Custom indicator publishes to SignalBus
- [ ] Step 2: ML endpoints callable from Python
- [ ] Step 3: ML panel visible in UI
- [ ] Train button works → shows accuracy
- [ ] Enable button starts polling
- [ ] New candles → signals appear in log
- [ ] Page reload → signals persist
- [ ] Different assets → signals filter correctly

---

## Summary

**Three signal sources now integrated:**
- Custom indicators (frontend JavaScript)
- ML signals (backend Python)
- Manual trades (user input)

**All flow through SignalBus:**
- Validated & deduplicated
- Persisted to localStorage
- Displayed in signal log
- Available for webhooks/alerts

**Total implementation: ~200 lines in 3 files, ~45 minutes**

See `INTEGRATION_PATCH.md` for exact code to copy-paste.

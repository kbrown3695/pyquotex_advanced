# 📡 Signal System Integration Guide

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    THREE SIGNAL SOURCES                         │
└─────────────────────────────────────────────────────────────────┘

    1. CUSTOM INDICATORS                2. ML SIGNALS              3. MANUAL TRADES
    (Frontend - JavaScript)             (Backend - Python)        (User Input)
         │                                   │                         │
         │ emitSignal()                      │ SignalResult            │
         │ + markers                         │ + confidence            │
         │ + charts                          │ + method                │
         │                                   │                         │
         └───────────────┬───────────────────┴────────────────────┬───┘
                         │                                        │
                    ┌────▼────────────────────────────────────────▼─────┐
                    │                                                   │
                    │         SIGNALBUS.JS (SIGNAL BUS)               │
                    │                                                   │
                    │  • Validate signals (BUY/SELL only)             │
                    │  • Deduplication (1 signal per time/indicator)  │
                    │  • Confidence scoring (0.0-1.0)                 │
                    │  • Persistence (localStorage)                   │
                    │  • Subscription system                          │
                    │                                                   │
                    └────────┬──────────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐      ┌──────▼──────┐     ┌─────▼──────┐
    │ CHART   │      │ SIGNAL LOG  │     │ ALERT      │
    │MARKERS  │      │ PANEL       │     │ SYSTEM     │
    │(Arrows) │      │ (History)   │     │(Webhooks)  │
    └─────────┘      └─────────────┘     └────────────┘
```

---

## Current Integration Status

### ✅ WORKING: signals.js

**File**: `frontend/signals.js`

**What it does**:
- Central signal management and persistence
- Deduplication (prevents duplicate signals)
- localStorage persistence (survives page reload)
- Signal badge counter
- Signal log panel UI
- Subscription system for listeners

**Signal Format**:
```javascript
{
  side: 'BUY' | 'SELL',
  confidence: 0.0-1.0,
  reason: 'Human-readable description',
  time: Unix timestamp,
  indicator: 'Indicator name',
  asset: 'EUR/USD',
  timeframe: '5m'
}
```

### ✅ WORKING: Custom Indicator Template

**File**: `frontend/MyCustomIndicator` (template in indicators.js)

**What it does**:
- Draws visual lines/areas on chart
- Creates persistent signal markers (arrows)
- Implements update/updateLast for stable rendering
- Prevents jitter on live candles

**Signal Emission**:
```javascript
this.emitSignal({
  side: 'BUY',
  confidence: 0.8,
  reason: 'Bullish momentum detected'
});
```

**Current Limitation**: 
- ❌ Doesn't actually connect to SignalBus
- The emitSignal() method logs and creates markers, but doesn't call SignalBus.publish()

### ✅ WORKING: ml_signals.py

**File**: `ml_signals.py` (backend)

**What it does**:
- 15 technical feature engineering
- Momentum score generation (52-55% accuracy)
- Random Forest ML training (54-60% accuracy)
- Ensemble blending (56-62% accuracy)
- Real-time signal generation

**Signal Output Format**:
```python
SignalResult(
  side='BUY',
  confidence=0.75,
  reason='ML prediction: 75% up',
  method='ensemble',
  components={...}
)
```

**Current Limitation**:
- ❌ No JavaScript bridge
- Signals are generated in Python but not connected to frontend
- No endpoint to call Python signals from engine.py

---

## Missing Integration Points

### Gap 1: Custom Indicator → SignalBus

**Location**: Custom indicator's `emitSignal()` method

**Current Code** (in indicators.js):
```javascript
emitSignal(signal) {
    // Creates markers on chart
    const marker = this._addPersistentSignal(...);
    
    // Logs to console
    console.log('📊 Signal:', signal);
    
    // ❌ BUT DOESN'T CALL SignalBus!
}
```

**What's Missing**:
```javascript
// Should add this line:
const published = SignalBus.publish({
    side: signal.side,
    confidence: signal.confidence,
    reason: signal.reason,
    indicator: this.constructor.name
});
```

**Impact**: Signals don't appear in the signal log, not persisted, no deduplication

---

### Gap 2: Python ML → JavaScript Endpoint

**Location**: engine.py (needs new endpoints)

**Current State**:
- ✅ ml_signals.py exists with all methods
- ❌ No Eel endpoint to call it
- ❌ No mechanism to pass signals to frontend

**What's Needed**:
```python
from ml_signals import EnsembleSignalGenerator

ensemble_gen = EnsembleSignalGenerator()

@eel.expose
def train_ml_signals():
    """Train ML model on recent candles."""
    candles = CANDLES.get(CURRENT_ASSET, {}).get(CURRENT_TIMEFRAME, [])
    if len(candles) < 100:
        return {'error': 'Need 100+ candles'}
    
    result = ensemble_gen.ml.train(candles, lookback=100)
    return result

@eel.expose
def get_ml_signal():
    """Get current ML signal for chart."""
    candles = CANDLES.get(CURRENT_ASSET, {}).get(CURRENT_TIMEFRAME, [])
    if not candles:
        return None
    
    signal = ensemble_gen.generate_signal(candles)
    return signal.to_dict()
```

**Impact**: ML signals unreachable from UI, can't display confidence, can't log signals

---

### Gap 3: Frontend UI for ML Signals

**Location**: frontend (new file or integration into existing)

**What's Needed**:
```javascript
// Call ML signal endpoint
async function updateMLSignal() {
    try {
        const signal = await eel.get_ml_signal()();
        if (!signal) return;
        
        // Publish to SignalBus
        const published = SignalBus.publish({
            side: signal.side,
            confidence: signal.confidence,
            reason: signal.reason,
            indicator: 'ML-' + signal.method
        });
        
        // Show on chart
        if (published) {
            showMLSignalMarker(signal);
        }
    } catch (e) {
        console.error('ML signal error:', e);
    }
}

// Call on every new candle
// Or on user request (train/score buttons)
```

**Impact**: Users can't see ML signals, can't train models, can't use ensemble predictions

---

## Full Integration Flow

### Scenario: User Opens Chart with ML Signals Enabled

```
1. USER OPENS CHART
   ├─ frontend loads
   ├─ signals.js initializes SignalBus
   └─ ml_signals.py ready (in backend)

2. CANDLES START FLOWING
   ├─ engine.py receives price updates
   ├─ CANDLES cache filled (200+ candles)
   └─ Ready to generate signals

3. USER CLICKS "TRAIN ML"
   ├─ Frontend: eel.train_ml_signals()
   ├─ Backend: ml_signals.py trains on 100 candles
   ├─ Returns: {accuracy: 0.562, features: 15, ...}
   └─ Model saved to ml_signals_model.json

4. NEW CANDLE ARRIVES (every 1m)
   ├─ Backend: candles updated in CANDLES cache
   ├─ Frontend: updateMLSignal() triggered
   ├─ Backend: eel.get_ml_signal() called
   ├─ ml_signals.py scores current candles
   ├─ Returns: {side: 'BUY', confidence: 0.72, method: 'ensemble'}
   ├─ Frontend: SignalBus.publish(signal)
   ├─ signals.js: validates & dedupes
   ├─ signals.js: persists to localStorage
   ├─ Signal panel: shows new signal with badge
   └─ Chart: shows ML confidence indicator

5. USER SEES SIGNAL LOG
   ├─ signal.js renders signal list
   ├─ Shows: time, asset, timeframe, side, confidence, reason
   ├─ Can filter by indicator type (custom/ML/manual)
   └─ Signals persist across page reload
```

---

## Implementation Checklist

### Phase 1: Fix Custom Indicator → SignalBus (Easy)

**File**: frontend/indicators.js

**Location**: IndicatorBase.emitSignal() method (around line 248)

**Change**:
```javascript
emitSignal(signal) {
    // ✅ ADD THIS: Publish to SignalBus
    const published = SignalBus.publish({
        side: signal.side,
        confidence: signal.confidence || 0.5,
        reason: signal.reason || '',
        indicator: signal.indicator || this.constructor.name
    });
    
    // Only show marker if signal was published (not deduplicated)
    if (published) {
        // ... marker code ...
    }
}
```

**Test**: Create custom indicator, emit signal, check signal log

---

### Phase 2: Add ML Endpoints to engine.py (Medium)

**File**: engine.py

**Add these imports**:
```python
from ml_signals import EnsembleSignalGenerator

# After CLIENT definition, add:
ensemble_gen = EnsembleSignalGenerator()
ML_SIGNAL_LAST_TIME = 0
ML_SIGNAL_CACHE = None
```

**Add these endpoints**:
```python
@eel.expose
def train_ml_signals():
    """Train ML model on recent candles."""
    global ensemble_gen
    try:
        candles = CANDLES.get(CURRENT_ASSET, {}).get(CURRENT_TIMEFRAME, [])
        if not candles or len(candles) < 100:
            return {
                'error': f'Need 100+ candles, got {len(candles) if candles else 0}'
            }
        
        result = ensemble_gen.ml.train(candles, lookback=100)
        log(f"✅ ML model trained: {result}", 1)
        return result
    except Exception as e:
        log(f"❌ ML training failed: {e}", 1)
        return {'error': str(e)}

@eel.expose
def get_ml_signal():
    """Get current ML signal (with rate limiting)."""
    global ensemble_gen, ML_SIGNAL_LAST_TIME, ML_SIGNAL_CACHE
    try:
        # Rate limit: max once per 5 seconds
        now = time.time()
        if now - ML_SIGNAL_LAST_TIME < 5 and ML_SIGNAL_CACHE:
            return ML_SIGNAL_CACHE
        
        candles = CANDLES.get(CURRENT_ASSET, {}).get(CURRENT_TIMEFRAME, [])
        if not candles or len(candles) < 26:
            return None
        
        signal = ensemble_gen.generate_signal(candles)
        ML_SIGNAL_LAST_TIME = now
        ML_SIGNAL_CACHE = signal.to_dict() if signal else None
        return ML_SIGNAL_CACHE
    except Exception as e:
        log(f"⚠️ ML signal error: {e}", 2)
        return None

@eel.expose
def get_ml_model_status():
    """Get ML model training status."""
    try:
        if ensemble_gen.ml.model:
            return {
                'trained': True,
                'features': len(ensemble_gen.ml.feature_names or []),
                'last_trained': 'See ml_signals_model.json'
            }
        return {'trained': False}
    except:
        return {'trained': False}
```

**Test**: Call from JavaScript console
```javascript
eel.train_ml_signals()(result => console.log(result));
eel.get_ml_signal()(signal => console.log(signal));
```

---

### Phase 3: Frontend UI for ML Signals (Medium)

**File**: frontend/app.js (or new file)

**Add**:
```javascript
// ML Signal polling (runs every candle)
let mlSignalInterval = null;

function startMLSignalPolling() {
    if (mlSignalInterval) clearInterval(mlSignalInterval);
    
    mlSignalInterval = setInterval(() => {
        updateMLSignal();
    }, 1000); // Check every second (or tune to your needs)
}

function stopMLSignalPolling() {
    if (mlSignalInterval) {
        clearInterval(mlSignalInterval);
        mlSignalInterval = null;
    }
}

async function updateMLSignal() {
    try {
        const signal = await eel.get_ml_signal()();
        if (!signal) return;
        
        // Publish to SignalBus ✅
        const published = SignalBus.publish({
            side: signal.side,
            confidence: signal.confidence,
            reason: signal.reason,
            indicator: 'ML-' + signal.method
        });
        
        if (published) {
            console.log('✅ ML Signal published:', signal);
        }
    } catch (e) {
        console.warn('⚠️ ML signal error:', e);
    }
}

// UI: Add ML Signal panel
async function showMLSignalPanel() {
    const status = await eel.get_ml_model_status()();
    
    const html = `
        <div id="mlSignalPanel">
            <h3>🤖 ML Signals</h3>
            <div id="mlStatus">
                Model: ${status.trained ? '✅ Trained' : '❌ Not trained'}
            </div>
            <button onclick="trainMLModel()">📊 Train Model</button>
            <button onclick="toggleMLSignals()">⚡ Enable ML Signals</button>
            <div id="mlSignalDisplay"></div>
        </div>
    `;
    
    document.getElementById('indicator-panel').insertAdjacentHTML('beforeend', html);
}

async function trainMLModel() {
    const result = await eel.train_ml_signals()();
    if (result.error) {
        alert('Training failed: ' + result.error);
    } else {
        alert(`✅ Model trained! Accuracy: ${(result.accuracy * 100).toFixed(1)}%`);
    }
}

function toggleMLSignals() {
    if (mlSignalInterval) {
        stopMLSignalPolling();
        alert('ML signals disabled');
    } else {
        startMLSignalPolling();
        alert('ML signals enabled');
    }
}
```

**Test**: Open panel, click "Train Model", then "Enable ML Signals"

---

### Phase 4: Verify Integration End-to-End (Testing)

**Test Script**:
```javascript
// In browser console
async function testIntegration() {
    console.log('🧪 Testing Signal Integration...\n');
    
    // 1. Test SignalBus
    console.log('1️⃣ Testing SignalBus');
    const sig1 = SignalBus.publish({
        side: 'BUY',
        confidence: 0.8,
        reason: 'Test signal',
        indicator: 'TestIndicator'
    });
    console.log('   Published:', sig1 ? '✅' : '❌ (deduplicated)');
    
    // 2. Test ML endpoints
    console.log('\n2️⃣ Testing ML Endpoints');
    const status = await eel.get_ml_model_status()();
    console.log('   Model status:', status);
    
    // 3. Test ML signal
    console.log('\n3️⃣ Testing ML Signal');
    const mlSig = await eel.get_ml_signal()();
    console.log('   ML signal:', mlSig);
    
    // 4. Publish ML signal
    if (mlSig) {
        console.log('\n4️⃣ Publishing ML Signal to SignalBus');
        const published = SignalBus.publish({
            side: mlSig.side,
            confidence: mlSig.confidence,
            reason: mlSig.reason,
            indicator: 'ML-' + mlSig.method
        });
        console.log('   Published:', published ? '✅' : '❌');
    }
    
    // 5. Check signal log
    console.log('\n5️⃣ Signal Log');
    const signals = SignalBus.getSignals();
    console.log('   Total signals:', signals.length);
    signals.slice(-3).forEach(s => {
        console.log(`   • ${s.time} ${s.side} ${s.confidence} (${s.indicator})`);
    });
}

testIntegration();
```

---

## Architecture Diagram (After Full Integration)

```
CUSTOM INDICATOR                ML SIGNALS (Python)          MANUAL SIGNALS
     │                               │                              │
     ├─ emitSignal()                 ├─ EnsembleGenerator          ├─ User trades
     │  {side, confidence, reason}    │  {side, confidence, method} │  {side, qty}
     │                                │                              │
     └────────────────┬───────────────┴──────────────────────┬───────┘
                      │                                      │
                  ╔═══▼══════════════════════════════════════▼════╗
                  ║                                                ║
                  ║            SignalBus.publish()               ║
                  ║                                                ║
                  ║  • Validate (BUY/SELL only)                  ║
                  ║  • Dedup (1 per indicator/side/time)         ║
                  ║  • Confidence 0.0-1.0                        ║
                  ║  • Persist (localStorage)                    ║
                  ║  • Notify subscribers                        ║
                  ║                                                ║
                  └───────────┬────────────────┬───────────┬──────┘
                              │                │           │
                  ┌───────────▼──┐  ┌──────────▼──┐  ┌────▼──────┐
                  │ CHART MARKERS│  │SIGNAL LOG UI│  │ ALERT/API │
                  │   (Arrows)   │  │  (History)  │  │(Webhooks) │
                  └──────────────┘  └─────────────┘  └───────────┘
```

---

## Summary

| Component | Status | Location | Integration |
|-----------|--------|----------|-------------|
| signals.js | ✅ Done | frontend/ | Central bus |
| Custom Indicator Template | ✅ Done | indicators.js | Needs SignalBus.publish() call |
| ml_signals.py | ✅ Done | root/ | Needs engine.py endpoints |
| ML-frontend Bridge | ❌ Missing | engine.py | Need 3 endpoints |
| ML Signal UI | ❌ Missing | frontend/ | Need panel + polling |
| Custom→SignalBus | ⚠️ Partial | indicators.js | Need to call publish() |

**Total Work**: ~200 lines of code in 3 files

**Estimated Time**: 1-2 hours for full integration

# 🔧 Quick Integration Patch

## Three Easy Steps to Full Integration

### STEP 1: Fix Custom Indicator → SignalBus (5 minutes)

**File**: `frontend/indicators.js`

**Find** (around line 248):
```javascript
emitSignal({ side, confidence = 0.5, reason = '', time = null, marker = true } = {}) {
    // ... current code ...
    this._lineSeries.setData(result);
    // ... etc ...
}
```

**Replace with**:
```javascript
emitSignal({ side, confidence = 0.5, reason = '', time = null, marker = true } = {}) {
    // ✅ NEW: Publish to SignalBus (global signal hub)
    if (typeof window.SignalBus !== 'undefined') {
        const published = window.SignalBus.publish({
            side: String(side || '').toUpperCase(),
            confidence: Math.min(1, Math.max(0, Number(confidence) || 0.5)),
            reason: String(reason || ''),
            indicator: this.constructor.name
        });
        
        // Only log if not deduplicated
        if (published) {
            console.log(`✅ Signal published: ${published.side} @ ${published.confidence.toFixed(1)%} (${this.constructor.name})`);
        } else {
            console.log(`⚠️ Signal deduplicated (already recorded)`);
        }
    } else {
        console.warn('⚠️ SignalBus not available');
    }
    
    // ... rest of original code ...
}
```

**Test**: 
```javascript
// In browser console after chart opens:
Indicators.MyCustomIndicator.emitSignal({side: 'BUY', confidence: 0.8, reason: 'Test'})
SignalBus.getSignals()  // Should show your signal
```

---

### STEP 2: Add ML Endpoints to engine.py (10 minutes)

**File**: `engine.py`

**Add at the top** (after other imports):
```python
# ✅ ML SIGNALS INTEGRATION
from ml_signals import EnsembleSignalGenerator

ensemble_gen = EnsembleSignalGenerator()
ML_SIGNAL_LAST_TIME = 0
ML_SIGNAL_CACHE = None
```

**Add before** the `if __name__ == "__main__":` block (around line 830):
```python
# ======================
# ✅ ML SIGNAL ENDPOINTS
# ======================

@eel.expose
def train_ml_signals():
    """Train ML model on recent historical candles."""
    global ensemble_gen
    try:
        candles = CANDLES.get(CURRENT_ASSET, {}).get(CURRENT_TIMEFRAME, [])
        
        if not candles:
            return {'error': 'No candles available for current asset/timeframe'}
        
        if len(candles) < 100:
            return {
                'error': f'Need 100+ candles to train (have {len(candles)})',
                'have': len(candles),
                'need': 100
            }
        
        log("🤖 Training ML model...", 1)
        result = ensemble_gen.ml.train(candles, lookback=100)
        log(f"✅ ML trained: {result['accuracy']:.1%} accuracy", 1)
        return result
        
    except Exception as e:
        log(f"❌ ML training error: {e}", 1)
        return {'error': str(e)}

@eel.expose
def get_ml_signal():
    """Get current ML-generated signal for display."""
    global ensemble_gen, ML_SIGNAL_LAST_TIME, ML_SIGNAL_CACHE
    try:
        now = time.time()
        
        # Rate limit: cache for 5 seconds
        if now - ML_SIGNAL_LAST_TIME < 5 and ML_SIGNAL_CACHE:
            return ML_SIGNAL_CACHE
        
        candles = CANDLES.get(CURRENT_ASSET, {}).get(CURRENT_TIMEFRAME, [])
        
        if not candles or len(candles) < 26:
            return None  # Not enough data
        
        # Generate signal using ensemble
        signal = ensemble_gen.generate_signal(candles)
        
        # Cache result
        ML_SIGNAL_LAST_TIME = now
        ML_SIGNAL_CACHE = signal.to_dict() if signal else None
        
        if ML_SIGNAL_CACHE:
            log(f"🤖 ML signal: {signal.side} @ {signal.confidence:.1%}", 2)
        
        return ML_SIGNAL_CACHE
        
    except Exception as e:
        log(f"⚠️ ML signal error: {e}", 2)
        return None

@eel.expose
def get_ml_status():
    """Get ML model training status."""
    try:
        if ensemble_gen.ml.model is None:
            return {'status': 'untrained', 'message': 'Click "Train" to train model'}
        
        return {
            'status': 'trained',
            'features': len(ensemble_gen.ml.feature_names or []),
            'message': 'Model ready - signals enabled'
        }
    except:
        return {'status': 'error', 'message': 'Check logs'}
```

**Test**:
```bash
# In Python (or from browser console after starting bot)
python -c "
import eel
import engine

# Simulate having candles
# eel.train_ml_signals()(lambda x: print(x))
"
```

---

### STEP 3: Add ML Signal UI to frontend (15 minutes)

**File**: `frontend/app.js` (or create `frontend/ml_ui.js`)

**Add**:
```javascript
// =============================================================================
// 🤖 ML SIGNAL CONTROLLER
// =============================================================================

class MLSignalController {
    constructor() {
        this.pollInterval = null;
        this.enabled = false;
    }
    
    // Start polling for ML signals
    start() {
        if (this.enabled) return;
        this.enabled = true;
        
        console.log('🤖 ML signals enabled - polling started');
        
        // Poll every 2 seconds
        this.pollInterval = setInterval(() => this.update(), 2000);
        
        // Update immediately
        this.update();
    }
    
    // Stop polling
    stop() {
        if (!this.enabled) return;
        this.enabled = false;
        
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        
        console.log('🤖 ML signals disabled');
    }
    
    // Fetch and publish ML signal
    async update() {
        try {
            const signal = await eel.get_ml_signal()();
            
            if (!signal) return;  // No signal available yet
            
            // Publish to SignalBus
            const published = window.SignalBus?.publish({
                side: signal.side,
                confidence: signal.confidence,
                reason: signal.reason,
                indicator: 'ML-' + signal.method
            });
            
            if (published) {
                console.log(`✅ ML Signal: ${signal.side} @ ${(signal.confidence*100).toFixed(0)}%`);
                // Optional: flash UI, play sound, etc.
            }
        } catch (e) {
            console.warn('⚠️ ML update error:', e);
        }
    }
    
    // Train model on current data
    async train() {
        console.log('🤖 Training ML model...');
        
        try {
            const result = await eel.train_ml_signals()();
            
            if (result.error) {
                alert(`❌ Training failed: ${result.error}`);
                return false;
            }
            
            const msg = `✅ Model trained!\n\nAccuracy: ${(result.accuracy * 100).toFixed(1)}%\nSamples: ${result.samples}\nFeatures: ${result.features}`;
            alert(msg);
            
            // Show feature importance
            console.log('Feature Importance:', result.feature_importance);
            
            return true;
        } catch (e) {
            alert(`❌ Training error: ${e}`);
            return false;
        }
    }
}

// Create global instance
window.MLSignals = new MLSignalController();

// =============================================================================
// 🎨 ML SIGNAL UI PANEL (optional - add to your UI)
// =============================================================================

function createMLSignalPanel() {
    const html = `
        <div id="mlSignalPanel" style="padding: 10px; background: #1a1a2e; border-radius: 8px; margin: 10px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h3 style="margin: 0; color: #00C510;">🤖 ML Signals</h3>
                <div style="font-size: 0.9em; color: #999;">
                    <span id="mlStatus">Status: Loading...</span>
                </div>
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap;">
                <button 
                    onclick="MLSignals.train()" 
                    style="padding: 8px 12px; background: #667eea; color: white; border: none; border-radius: 4px; cursor: pointer;">
                    📊 Train Model
                </button>
                
                <button 
                    id="mlToggle"
                    onclick="toggleMLSignals()" 
                    style="padding: 8px 12px; background: #666; color: white; border: none; border-radius: 4px; cursor: pointer;">
                    ⚡ Enable Signals
                </button>
                
                <button 
                    onclick="clearMLCache()" 
                    style="padding: 8px 12px; background: #999; color: white; border: none; border-radius: 4px; cursor: pointer;">
                    🔄 Clear Cache
                </button>
            </div>
            
            <div id="mlInfo" style="margin-top: 10px; font-size: 0.9em; color: #aaa;"></div>
        </div>
    `;
    
    // Insert into page (adjust selector as needed)
    const parent = document.querySelector('[data-role="indicator-controls"]') || document.body;
    parent.insertAdjacentHTML('beforeend', html);
    
    updateMLStatus();
}

async function updateMLStatus() {
    try {
        const status = await eel.get_ml_status()();
        const statusEl = document.getElementById('mlStatus');
        const infoEl = document.getElementById('mlInfo');
        
        if (statusEl) {
            statusEl.textContent = `Status: ${status.status}`;
        }
        
        if (infoEl) {
            infoEl.textContent = status.message;
        }
    } catch (e) {
        console.warn('Status update error:', e);
    }
}

function toggleMLSignals() {
    if (window.MLSignals.enabled) {
        window.MLSignals.stop();
        document.getElementById('mlToggle').textContent = '⚡ Enable Signals';
        document.getElementById('mlToggle').style.background = '#666';
    } else {
        window.MLSignals.start();
        document.getElementById('mlToggle').textContent = '⏹️ Stop Signals';
        document.getElementById('mlToggle').style.background = '#00C510';
    }
}

function clearMLCache() {
    // Force immediate refresh on next update
    window.MLSignals.update();
    alert('Cache cleared - updating now');
}

// Auto-initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    createMLSignalPanel();
});
```

**Integration**: Add to `index.html` or your app initialization:
```html
<!-- At end of body, before closing -->
<script src="ml_ui.js"></script>
```

**Test**:
```javascript
// In browser console:
MLSignals.train()  // Will pop alert with results
MLSignals.start()  // Start polling
SignalBus.getSignals()  // Should show ML signals appearing
MLSignals.stop()  // Stop polling
```

---

## Verification Checklist

After applying all patches:

- [ ] Step 1: Custom indicator calls SignalBus.publish()
- [ ] Step 2: ML endpoints work (test in Python)
- [ ] Step 3: ML panel shows in UI
- [ ] [ ] Test: Click "Train Model" → accuracy shows
- [ ] [ ] Test: Click "Enable Signals" → button changes color
- [ ] [ ] Test: New candle arrives → ML signal appears in log
- [ ] [ ] Test: Reload page → signals persist in log
- [ ] [ ] Test: Switch asset → signals filtered correctly

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "SignalBus not defined" | signals.js not loaded, check script order |
| "ML endpoints 404" | engine.py not restarted after edits |
| "ModuleNotFoundError: ml_signals" | `pip install scikit-learn pandas` |
| "Need 100+ candles" | Wait for chart to load more history |
| "ML signals not appearing" | Check browser console for errors |
| "Signals disappear on reload" | signals.js localStorage may be disabled |

---

## What You'll Get

✅ Custom indicators → Signal log (persistent)
✅ ML signals → Signal log (persistent)
✅ Real-time updates (every new candle)
✅ Confidence scoring
✅ Signal history (survives reload)
✅ Training/inference UI

**Total integration: ~200 lines, 3 files, 1-2 hours**

# Data Loading & Chart Refresh Guide

## Overview

Historical data flows through a 3-stage pipeline:

```
Backend (Python) Loads Data
         ↓
UI Queue (thread-safe buffer)
         ↓
Frontend (JavaScript) Renders Chart
```

---

## How Data Flows to Chart

### Stage 1: Backend Data Loading

**Location:** `engine.py::load_timeframe_data()`

```python
async def load_timeframe_data(asset: str, tf: str, period: int):
    # Step 1: Check aggregated timeframes in database first (30s, 10s, etc.)
    if tf in {"5s", "10s", "15s", "30s", "4h"}:
        db_candles = CANDLE_STORE.get_candles(asset, tf, limit=199)
        if db_candles and len(db_candles) > 10:
            CANDLES[asset][tf] = db_candles
            return db_candles
    
    # Step 2: Fetch from Quotex API if not in DB
    internal = DISPLAY_TO_INTERNAL.get(asset)
    hist = await CLIENT.get_candles(
        internal, 
        time.time(),      # Current time
        199 * period,     # Offset: 199 candles back
        period            # Candle size
    )
    
    # Step 3: Process and store
    loaded = process_candle_data(hist, period)
    CANDLES[asset][tf] = loaded[-199:]  # Keep last 199
    return loaded
```

**Data Sources (in priority order):**
1. **SQLite Database** (CandleStore) - Aggregated timeframes only
2. **Quotex WebSocket API** - Live + historical

### Stage 2: Send to UI Queue

**Location:** `engine.py::send_to_ui()`

```python
def send_to_ui(asset: str, timeframe: str, force=False, full=False):
    # full=True  → Send ALL 199 candles (complete snapshot)
    # full=False → Send only current candle (incremental update)
    
    if full:
        # Complete reload: all candles in memory
        all_c = CANDLES.get(asset, {}).get(timeframe, []).copy()
        curr = CURRENT_CANDLE.get(asset, {}).get(timeframe)
        if curr:
            all_c[-1] = curr  # Replace with live candle
        mode = "full"
    else:
        # Incremental: only new candle
        curr = CURRENT_CANDLE.get(asset, {}).get(timeframe)
        all_c = [curr]
        mode = "update"
    
    # Push to thread-safe queue
    payload = {
        "mode": mode,
        "candles": all_c,
        "asset": asset,
        "timeframe": timeframe,
        "timeframe_seconds": TIMEFRAMES[timeframe]
    }
    UI_QUEUE.put_nowait(payload)
```

**Payload Modes:**
- `full` → Complete chart redraw (199 candles)
- `update` → Single candle merge (live update)

### Stage 3: Frontend Rendering

**Location:** `frontend/datafeed.js`

```javascript
// Receive payload from backend
const payload = incomingData;

if (payload.mode === 'full') {
    // Complete reload
    window.candleSeries.setData(payload.candles);  // ← Redraws chart
    AppState.currentCandles = payload.candles;
} else if (payload.mode === 'update') {
    // Incremental update
    window.candleSeries.update(payload.candles[0]);  // ← Just add new bar
}

// Recalculate all indicators
if (window.CM && window.CM.mainSeries) {
    window.CM.recalculate(payload.candles);  // ← Oscillators update here
}
```

---

## Reload Scenarios

### Scenario 1: Chart Opens (Full Reload)

**Trigger:** User opens chart on new asset/timeframe

**Code Path:**
```
User clicks "Open Chart"
    ↓
on_chart_opened() [frontend/app.js]
    ↓
eel.on_chart_opened() [engine.py]
    ↓
chart_opened_loader(asset)
    ├─ load_timeframe_data(asset, "1m", 60)
    │  └─ Fetch 199 * 60 = 11,940 seconds (3+ hours)
    ├─ send_to_ui(asset, "1m", full=True) ← FULL mode
    │  └─ Push ALL 199 candles
    └─ Frontend receives: mode="full"
       └─ candleSeries.setData(candles) ← Chart redraws
       └─ Recalculate indicators ← AO recalculates
```

**Result:** Chart shows 199 candles + all oscillators calculated

---

### Scenario 2: Switch Timeframe (Full Reload)

**Trigger:** User switches from 1m to 5m

**Code Path:**
```
User selects "5m" from dropdown
    ↓
onTimeframeChanged(asset, "5m") [frontend]
    ↓
eel.change_timeframe("5m") [engine.py]
    ↓
load_timeframe_data(asset, "5m", 300)
    ├─ Check DB for aggregated TF
    ├─ If missing: Fetch from API (199 * 300 seconds)
    └─ Store in CANDLES[asset]["5m"]
    ↓
send_to_ui(asset, "5m", full=True) ← FULL mode
    ↓
Frontend: candleSeries.setData(candles) ← Complete redraw
```

**Result:** Chart updates with 5m candles + oscillators recalculate

---

### Scenario 3: Live Candle Update (Incremental)

**Trigger:** New price tick arrives every ~1 second

**Code Path:**
```
Tick arrives: price = 287.50 at 14:30:15
    ↓
CURRENT_CANDLE[asset][tf] updated
    ↓
send_to_ui(asset, tf, full=False) ← UPDATE mode
    ├─ Rate limited: max 1 update per 500ms
    └─ Payload contains: 1 candle (the current one)
    ↓
Frontend: candleSeries.update(candle) ← Merge into last bar
    └─ Oscillators extend last value (no recalculation)
```

**Result:** Last bar extends/updates live, smooth animation

---

## Manual Reload Methods

### Method 1: Reload Current Asset (Frontend)

**How to force a complete reload:**

```javascript
// In browser console:
eel.change_timeframe(AppState.currentTimeframe);
```

**Effect:**
- Fetches fresh data from backend
- Reloads chart completely
- Recalculates all indicators

### Method 2: Reload All Assets (Backend)

**How to force historical data refresh:**

```python
# In engine.py after data loads:
async def reload_all_historical():
    """Force reload all historical candles from API."""
    for asset in SIGNAL_PAIRS:
        for tf in ["1m", "5m", "15m", "30m", "1h"]:
            try:
                await load_timeframe_data(asset, tf, TIMEFRAMES[tf])
                send_to_ui(asset, tf, force=True, full=True)
                await asyncio.sleep(0.5)  # Rate limit
            except Exception as e:
                log(f"Failed to reload {asset} {tf}: {e}")

# Call it:
asyncio.run(reload_all_historical())
```

### Method 3: Reload from Database Only

**For aggregated timeframes (30s, 10s, etc.):**

```python
# Reload 30s candles from CandleStore:
from ml.data.candle_store import CandleStore

store = CandleStore("quotex_candles.db")
candles_30s = store.get_candles("AUD/CAD (OTC)", "30s", limit=199)

# Push to UI:
CANDLES["AUD/CAD (OTC)"]["30s"] = candles_30s
send_to_ui("AUD/CAD (OTC)", "30s", force=True, full=True)
```

---

## Awesome Oscillator Recalculation

When chart reloads, oscillators automatically recalculate:

### Backend Calculation (for ML)
```python
# ml_signals.py
def calculate_awesome_oscillator(candles):
    hl2 = [(c['high'] + c['low']) / 2 for c in candles]
    fast_sma = calculate_sma(hl2, 5)
    slow_sma = calculate_sma(hl2, 34)
    ao = [fast - slow for fast, slow in zip(fast_sma, slow_sma)]
    return ao
```

### Frontend Calculation (for chart)
```javascript
// frontend/indicators.js
update(candles) {
    const hl2 = candles.map(c => (c.high + c.low) / 2);
    const fast = this.calculateSMA(hl2, 5);
    const slow = this.calculateSMA(hl2, 34);
    
    const aoData = [];
    for (let i = 0; i < slow.length; i++) {
        const ao = fast[i + offset] - slow[i];
        aoData.push({
            time: candles[i + offset].time,
            value: ao,
            color: ao > 0 ? '#00C510' : '#ff0000'
        });
    }
    this._aoSeries.setData(aoData);  // ← Chart updates
}
```

---

## Data Storage Layers

### 1. Memory Cache (Fastest)
```python
CANDLES = {
    "AUD/CAD (OTC)": {
        "1m": [199 candles],
        "5m": [199 candles],
        "30s": [14 candles]  # Aggregated, fewer stored
    }
}

CURRENT_CANDLE = {
    "AUD/CAD (OTC)": {
        "1m": {live candle being formed}
    }
}
```

**Access time:** < 1ms  
**Persistence:** Lost on restart

### 2. SQLite Database (Medium)
```
quotex_candles.db
├─ candles table
│  ├─ asset TEXT
│  ├─ timeframe TEXT
│  ├─ time INTEGER
│  ├─ open REAL
│  ├─ high REAL
│  ├─ low REAL
│  ├─ close REAL
│  └─ volume REAL
└─ indices
   └─ idx_asset_timeframe_time
```

**Access time:** 5-50ms (indexed query)  
**Persistence:** Permanent (survives restart)  
**Contains:** All historical candles saved during runtime

### 3. Quotex WebSocket API (Slowest)
```
get_candles(
    asset="AUDCAD_otc",
    end_from_time=time.time(),
    offset=199*60,        # Request 199 candles back
    period=60             # 1-minute candles
)
```

**Access time:** 500ms-2s (network)  
**Persistence:** N/A (real-time stream)  
**Contains:** Live market data, historical on demand

---

## Refresh Strategies

### Strategy 1: Fast (Use Cache)
```python
# If data already loaded, just push to UI
if asset in CANDLES and tf in CANDLES[asset]:
    send_to_ui(asset, tf, full=True)
    # Chart updates instantly < 100ms
```

### Strategy 2: Balanced (Check DB First)
```python
# For aggregated TF, try DB, fallback to API
if tf in {"30s", "10s", "15s", "5s"}:
    db_candles = CANDLE_STORE.get_candles(asset, tf, limit=199)
    if db_candles and len(db_candles) > 10:
        CANDLES[asset][tf] = db_candles
        send_to_ui(asset, tf, full=True)  # Fast
        return
# Fallback to API
await load_timeframe_data(asset, tf, TIMEFRAMES[tf])  # Slower
send_to_ui(asset, tf, full=True)
```

### Strategy 3: Guaranteed Fresh (Hit API)
```python
# Always fetch latest from Quotex
await load_timeframe_data(asset, tf, TIMEFRAMES[tf])
send_to_ui(asset, tf, full=True)
```

---

## Troubleshooting

### Issue: Chart doesn't update after reload

**Solution 1: Force full mode**
```python
send_to_ui(asset, tf, force=True, full=True)
```

**Solution 2: Check if data exists**
```python
if asset in CANDLES and tf in CANDLES[asset]:
    print(f"Candles loaded: {len(CANDLES[asset][tf])}")
else:
    await load_timeframe_data(asset, tf, TIMEFRAMES[tf])
```

### Issue: Oscillators not recalculating

**Solution: Frontend chart manager recalculate**
```javascript
// Force recalculation
if (window.CM && window.CM.recalculate) {
    window.CM.recalculate(AppState.currentCandles);
}
```

### Issue: 30s candles show old data

**Solution: Reload from database**
```python
# Clear memory first
CANDLES["AUD/CAD (OTC)"]["30s"] = []

# Reload from DB
db_candles = CANDLE_STORE.get_candles(
    "AUD/CAD (OTC)", 
    "30s", 
    limit=199
)
CANDLES["AUD/CAD (OTC)"]["30s"] = db_candles
send_to_ui("AUD/CAD (OTC)", "30s", full=True)
```

---

## Performance Notes

| Operation | Time | Notes |
|-----------|------|-------|
| Load 199 candles (memory) | <1ms | Instant |
| Query DB (indexed) | 5-20ms | Depends on DB size |
| Fetch API + process | 500-2000ms | Network dependent |
| Chart render (199 candles) | 50-100ms | Full setData |
| Chart update (1 candle) | 5-10ms | Incremental |
| Recalculate indicators | 10-30ms | Per indicator |
| Total: Full reload | 600-2200ms | Cache: < 50ms |

---

## Queue Architecture

```
Engine (Python) ──→ UI_QUEUE (thread-safe) ──→ Frontend (JavaScript)
                     ┌─────────────┐
                     │  Queue(50)  │
                     └──────┬──────┘
                     • Max 50 payloads
                     • FIFO order
                     • Non-blocking put
                     • Block.get(timeout)

Rate Limiting:
  • full=False: max 1 per 500ms
  • full=True: bypass rate limit
  • Prevents UI thread overload
```

---

## Summary: How to Reload

**Quick reload (current asset/timeframe):**
```javascript
// Browser console
eel.change_timeframe(AppState.currentTimeframe);
```

**Programmatic full reload:**
```python
# Python code
await load_timeframe_data(asset, tf, TIMEFRAMES[tf])
send_to_ui(asset, tf, force=True, full=True)
```

**Reload from database only:**
```python
db_candles = CANDLE_STORE.get_candles(asset, tf, limit=199)
CANDLES[asset][tf] = db_candles
send_to_ui(asset, tf, full=True)
```

**Result:** Chart + indicators (including Awesome Oscillator) refresh completely ✅

---

*Last Updated: 2026-09-15*
*Version: 1.0*

# QuotexChart — Full Data & Oscillators Architecture

## 🎯 Overview

Your app loads **1-minute candles from Quotex API**, then **aggregates them into smaller timeframes** (5s, 10s, 15s, 30s) and **persists everything to SQLite**. Charts can then scroll left infinitely, loading historical data from the database.

---

## 📊 Complete Data Flow

### Phase 1: Live Data Collection
```
Quotex API (1m candles)
    ↓
engine.py: realtime_price_loop()
    ↓
update_candle() → CANDLES in-memory cache (200 max per asset/tf)
    ↓
[When 1m candle completes]
    ↓
CANDLE_STORE.save_candle(asset, "1m", candle)
    ↓
TIMEFRAME_AGGREGATOR.aggregate_to_timeframes(asset, candle)
    ├─ Creates 5s × 12 mini-candles (same OHLC as 1m)
    ├─ Creates 10s × 6 mini-candles
    ├─ Creates 15s × 4 mini-candles
    ├─ Creates 30s × 2 mini-candles
    └─ Saves all to CANDLE_STORE database
```

### Phase 2: Historical Chart Loading
```
Frontend: User scrolls left (wants older data)
    ↓
JavaScript: chart.prependData(older_candles)
    ↓
engine.py: @eel.expose get_candles_from_store()
    ↓
CANDLE_STORE.get_candles_before(asset, tf, before_time, limit=200)
    ↓
SQLite query: SELECT * WHERE time < before_time LIMIT 200
    ↓
Return 200 candles sorted oldest→newest
    ↓
Frontend: Prepend to chart, update x-axis
```

---

## 🗄️ Database Schema

```sql
CREATE TABLE candles (
    id INTEGER PRIMARY KEY,
    asset TEXT,           -- "AUD/CAD (OTC)", "EUR/USD (OTC)", etc.
    timeframe TEXT,       -- "1m", "5s", "10s", "15s", "30s", "4h"
    time INTEGER,         -- Unix timestamp (seconds)
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    created_at TIMESTAMP,
    UNIQUE(asset, timeframe, time)
);

CREATE INDEX idx_asset_timeframe_time 
    ON candles(asset, timeframe, time DESC);
```

**Key**: `(asset, timeframe, time)` must be unique — prevents duplicates across aggregation.

---

## 🔄 How Aggregation Works

### Split vs. Aggregate
- **5s/10s/15s/30s**: Split 1m candle into multiple smaller candles (all with same OHLC)
  - Why? No tick data available from API
  - Acceptable for UI display (ML models train on 1m anyway)
  
- **4h**: Aggregate 1m candles within a 4-hour window
  - Open = first 1m open
  - High = max of all highs
  - Low = min of all lows
  - Close = last 1m close
  - Volume = sum of all volumes

### Example: 1m Candle → Sub-Minute Candles
```
1m candle at time=1000 (OHLC: 1.5030/1.5040/1.5020/1.5035)
    ↓
5s split:
  ├─ time=1000: 1.5030/1.5040/1.5020/1.5035 ✓
  ├─ time=1005: 1.5030/1.5040/1.5020/1.5035 ✓
  ├─ time=1010: 1.5030/1.5040/1.5020/1.5035 ✓
  └─ ... (12 candles total)

10s split:
  ├─ time=1000: 1.5030/1.5040/1.5020/1.5035 ✓
  ├─ time=1010: 1.5030/1.5040/1.5020/1.5035 ✓
  └─ time=1020: 1.5030/1.5040/1.5020/1.5035 ✓
```

---

## 💻 Backend API Endpoints

### 1. **Load Initial Chart Data** (when user opens chart)
```python
@eel.expose
def load_timeframe_data(asset: str, tf: str, period: int) -> List[dict]:
```
- Tries database first for aggregated timeframes
- Falls back to API for 1m/2m/3m/5m/10m/15m/30m/1h/4h
- Returns **last 199 candles** (newest)

### 2. **Scroll/Paginate** ✨ NEW ✨ (when user scrolls left)
```python
@eel.expose
def get_candles_from_store(asset: str, timeframe: str, limit: int = 200, before_time: Optional[int] = None):
```
- **Parameters**:
  - `before_time`: Unix timestamp (load candles before this time)
  - `limit`: How many candles to load (default 200)
  
- **Returns**: 200 candles sorted oldest→newest (ready to prepend to chart)

- **Usage in JavaScript**:
```javascript
// Get last candle's time
const lastTime = candleSeries.data()[0].time;

// Load older candles
fetch('/get_candles_from_store', {
  asset: "AUD/CAD (OTC)",
  timeframe: "1m",
  limit: 200,
  before_time: lastTime  // Load everything before this
})
.then(candles => {
  candleSeries.prependData(candles);  // Add to left side of chart
});
```

### 3. **Get Candle Count** (show how much history exists)
```python
@eel.expose
def get_candle_count(asset: str, timeframe: str) -> int:
```
- Returns total candles in database for this pair/timeframe

### 4. **Get Oscillator Data** (see below)
```python
# Coming next: oscillator calculations from candle data
```

---

## 📈 Oscillators Architecture

Oscillators (RSI, MACD, Stochastic, Bollinger Bands, etc.) are computed from candle data.

### Storage Strategy: **Compute on Demand** (recommended)
```
frontend.js: User switches to RSI panel
    ↓
engine.py: @eel.expose calculate_oscillator(asset, tf, oscillator_type)
    ↓
Get 200+ candles from CANDLE_STORE
    ↓
Compute RSI/MACD/etc. (in numpy/talib/pandas)
    ↓
Return values aligned to chart candles
    ↓
frontend.js: Chart draws oscillator panel
```

### Why Compute on Demand?
- ✅ **No storage overhead** — don't fill database with derived data
- ✅ **Always fresh** — no stale cached values
- ✅ **Flexible** — easy to add new oscillators
- ❌ **Slightly slower** — but fine for 200 candles (< 100ms)

### Alternative: **Pre-Compute & Store** (if needed)
If you want oscillators pre-computed:
```python
# Add to timeframe_aggregator after candle save
def compute_oscillators(asset, tf, candle):
    rsi = ta.RSI(...)
    macd = ta.MACD(...)
    # Store in separate table: oscillator_values(asset, tf, time, rsi, macd, ...)
    OSCILLATOR_STORE.save(asset, tf, candle['time'], rsi, macd, ...)
```

---

## 🔧 Implementation Checklist

### Backend (Python)
- [x] `CandleStore.get_candles()` — load most recent
- [x] `CandleStore.get_candles_before()` — **NEW** scroll query
- [x] `get_candles_from_store()` — endpoint for frontend scrolling
- [ ] **Oscillator endpoint** — `calculate_rsi(asset, tf, period=14)`
- [ ] **Multi-timeframe query** — load 1m→aggregate on-the-fly

### Frontend (JavaScript)
- [ ] Chart scroll listener → call `get_candles_from_store(before_time)`
- [ ] Prepend candles to left side of chart
- [ ] Update x-axis range
- [ ] Oscillator button → call backend endpoint
- [ ] Draw oscillator panels below/above main chart

### Database Maintenance
- [ ] Monitor `quotex_candles.db` size (1 year of 1m data ≈ 20-50MB)
- [ ] Optional: `delete_old_candles()` to trim history beyond N candles

---

## 📝 Configuration Constants

**In [engine.py](D:\QuotexChart\engine.py#L240)**:
```python
TIMEFRAMES = {
    "5s": 5, "10s": 10, "15s": 15, "30s": 30,
    "1m": 60, "2m": 120, "3m": 180, "5m": 300,
    "10m": 600, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400
}
```

**Dropdown shows only API-supported**:
```python
API_TIMEFRAMES = ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "4h"]
SUB_MINUTE = ["5s", "10s", "15s", "30s"]  # Generated via aggregator
```

---

## 🧪 Testing the System

### 1. Verify Database Storage
```bash
# SSH into server, open SQLite CLI
sqlite3 quotex_candles.db

# Count candles per timeframe
SELECT timeframe, COUNT(*) as count FROM candles 
WHERE asset='AUD/CAD (OTC)' 
GROUP BY timeframe;

# Expected output:
# 1m|500
# 5s|6000
# 10s|3000
# 15s|2000
# 30s|1000
```

### 2. Test Scroll Endpoint
```bash
# Load 200 1m candles before time=1694433600
curl -X GET "http://localhost:8080/get_candles_from_store?asset=AUD/CAD%20(OTC)&timeframe=1m&limit=200&before_time=1694433600"
```

### 3. Test on Chart
```javascript
// In browser console
eel.get_candles_from_store("AUD/CAD (OTC)", "1m", 200, 1694433600)(candles => {
  console.log("Loaded", candles.length, "candles");
  console.log("Oldest:", candles[0].time, "→ Newest:", candles[-1].time);
});
```

---

## 🚀 Next Steps

1. **Frontend Integration**
   - Add scroll event listener to chart
   - Call `get_candles_from_store()` when scrolling left
   - Prepend returned candles to chart

2. **Add Oscillators**
   - Create `calculate_rsi()`, `calculate_macd()` endpoints
   - OR use TradingView's lightweight charts library (has built-in oscillators)

3. **Performance Optimization**
   - Cache recent candles in memory (already done: `CANDLES` dict)
   - Use SQLite WAL mode for faster concurrent reads
   - Add pagination size to config (currently 200)

4. **Data Quality**
   - Monitor for duplicate candles
   - Verify 5s/10s/15s/30s have correct count per minute
   - Track API downtime and backfill gaps

---

## 📚 File Reference

| File | Purpose |
|------|---------|
| [engine.py:565](D:\QuotexChart\engine.py#L565) | `update_candle()` — processes live prices |
| [engine.py:1443](D:\QuotexChart\engine.py#L1443) | `get_candles_from_store()` — scroll endpoint |
| [ml/data/timeframe_aggregator.py](D:\QuotexChart\ml\data\timeframe_aggregator.py) | Splits/aggregates timeframes |
| [ml/data/candle_store.py](D:\QuotexChart\ml\data\candle_store.py) | SQLite storage layer |
| [quotex_candles.db](D:\QuotexChart\quotex_candles.db) | SQLite database |

---

## 🎓 Learning Resources

- **TradingView Charts**: https://www.tradingview.com/lightweight-charts/ (excellent for implementing scroll/zoom)
- **Technical Indicators**: https://pandas-ta.readthedocs.io/ (RSI, MACD, etc.)
- **SQLite Query Optimization**: https://www.sqlite.org/bestindex.html (for large candle datasets)

---

**Last Updated**: 2026-09-15  
**Status**: ✅ Architecture ready for frontend integration

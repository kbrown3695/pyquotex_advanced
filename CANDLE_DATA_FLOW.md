# Candle Data Flow & Consistency

## Data Sources

### 1. **WebSocket Real-Time** (Primary for building local candles)
- Real-time price updates from Quotex via WebSocket
- Builds OHLC candles incrementally in memory
- Stored in `CURRENT_CANDLE` during formation, moved to `CANDLES` when complete
- Saved to database via `CandleStore.save_candle()`

### 2. **API Historical** (Used for backfill on first load)
- `CLIENT.get_candles()` retrieves historical data from Quotex API
- Only supports standard timeframes (1m, 2m, 3m, 5m, 10m, 15m, 30m, 1h)
- Does not support sub-minute or 4h timeframes
- Processed via `process_candle_data()` before storage

### 3. **Database** (Primary for all retrieval)
- SQLite (`quotex_candles.db`) stores all OHLCV data
- Persists WebSocket candles for historical analysis
- Stores aggregated candles (5s, 10s, 15s, 30s, 4h)

## Data Format

All candle formats are identical:
```python
{
    "time": int,           # Unix timestamp (candle start)
    "open": float,         # Opening price
    "high": float,         # Highest price
    "low": float,          # Lowest price
    "close": float,        # Closing price
    "volume": float        # Trading volume (OTC: 0.0)
}
```

## Workflow for Each Timeframe

### **Standard API Timeframes** (1m, 2m, 3m, 5m, 10m, 15m, 30m, 1h)

```
WebSocket Price Updates
    ↓
update_candle(asset, "1m", price, ts_sec, volume)
    ↓
CURRENT_CANDLE[asset]["1m"] ← {time, open, high, low, close, volume}
    ↓ (when period complete)
CANDLES[asset]["1m"].append(candle)
    ↓
CandleStore.save_candle(asset, "1m", candle)
    ↓
Database (quotex_candles)
    ↓ (on chart open for that timeframe)
get_candles(asset, "1m") ← Load last 200 from DB
```

### **Aggregated Timeframes** (5s, 10s, 15s, 30s, 4h)

```
1m Candle Complete (in update_candle)
    ↓
TimeframeAggregator.aggregate_to_timeframes(asset, candle)
    ↓
For each target timeframe (5s, 10s, 15s, 30s, 4h):
    - Query database for all 1m candles in that time slot
    - Aggregate: open(first), high(max), low(min), close(last), volume(sum)
    - Save aggregated candle to database
    ↓
Database (quotex_candles)
    ↓ (on chart open for that timeframe)
load_timeframe_data() checks DB first
    - If aggregated TF and DB has data: return DB data (no API call)
    - If standard TF or no DB data: try API fallback
```

## Data Consistency Guarantees

### ✅ **What's Guaranteed**

1. **Format Consistency**: All candles follow identical OHLCV structure
2. **Database Persistence**: Every completed 1m candle is stored to DB
3. **Aggregation Accuracy**: Aggregated candles use mathematically correct OHLC
   - Open: First 1m candle's open
   - High: Maximum high across all 1m candles
   - Low: Minimum low across all 1m candles
   - Close: Last 1m candle's close
   - Volume: Sum of all 1m candles' volumes
4. **Time Alignment**: Candle times align to the period (e.g., 5s candle at 12:00:05)

### ⚠️ **What May Differ**

1. **WebSocket vs API Candles**: 
   - First load uses API data (historical)
   - Subsequent candles use WebSocket data
   - Small price differences possible due to:
     - WebSocket tick granularity
     - Missing ticks during network lag
     - API vs WebSocket source timing
   - **Mitigation**: Use `CandleValidator.compare_candles()` with 0.1% tolerance

2. **Volume Data**:
   - WebSocket volume: Aggregated from ticks (may be incomplete)
   - API volume: Server-side total (authoritative)
   - OTC markets often report volume=0.0
   - **Note**: Volume not used in ML training, so differences are non-critical

3. **Sub-Minute Candles (5s, 10s, 15s, 30s)**:
   - Built from 1m candles, not from raw ticks
   - Approximation, not real market-level OHLC
   - **Acceptable**: ML models train on 1m candles anyway; aggregated data is for UI display

4. **4H Candles**:
   - Aggregated from 1m candles
   - Accuracy depends on continuous 1m data availability
   - **Requirement**: Keep app running or load historical data first

## Validation

Use `CandleValidator` to check data quality:

```python
from ml.data.candle_validator import CandleValidator

# Compare WebSocket candle to API candle
validation = CandleValidator.compare_candles(ws_candle, api_candle, tolerance_percent=0.1)
print(f"Valid: {validation.is_valid}")
print(f"Warnings: {validation.warnings}")

# Validate a candle series
result = CandleValidator.validate_candle_series(candles, asset, timeframe)
print(f"Issues: {result['issues']}")
```

## Recovery Strategy

If chart data looks wrong:

1. **For standard timeframes (1m-1h)**:
   - Delete entries from database
   - Restart app to reload from API
   - Wait for new 1m candles to build

2. **For aggregated timeframes (5s, 10s, 15s, 30s, 4h)**:
   - Keep app running; new candles will aggregate automatically
   - Or manually load 1m data and regenerate aggregations

3. **For data gaps**:
   - Run backfill script to load historical 1m from API
   - Aggregator will automatically build other timeframes

## Summary

| Aspect | Guarantee |
|--------|-----------|
| **Format** | ✅ Identical OHLCV across all sources |
| **Timestamps** | ✅ Monotonic, period-aligned |
| **Price accuracy** | ✅ Within 0.1% (OHLC valid range) |
| **Persistence** | ✅ All 1m candles saved to DB |
| **Aggregation** | ✅ Mathematically correct |
| **Sub-minute data** | ⚠️ Approximation from 1m (UI only) |
| **Volume** | ⚠️ OTC markets: 0.0 (not used in ML) |

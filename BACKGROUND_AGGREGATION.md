# Background Candle Aggregation

Automatically aggregates 1-minute candles into higher timeframes (3m, 5m, 10m, 15m, 30m, 1h) **in the background** for your selected trading pairs.

## How It Works

1. **Selected Pairs** — The aggregator reads `selected_signal_pairs.json` to determine which pairs to process
2. **Async Background Loop** — Runs continuously without blocking UI/trading logic
3. **Smart Throttling** — Aggregates at most every 30 seconds per pair to avoid redundant work
4. **Database Persistence** — Stores aggregated candles in `quotex_candles.db` for charting & analysis

## Automatic Startup

The background aggregator **starts automatically** when you log in:

```
✅ Login successful
✅ Background candle aggregator started
```

## Monitoring Progress

Run the monitoring script to see aggregation progress:

```bash
python monitor_bg_aggregation.py
```

Output shows:
- **1m (source)** — Count of 1-minute candles available
- **3m/5m/10m/15m/30m/1h (agg)** — Count of aggregated candles

Example:
```
[ASSET] USD/INR (OTC)
  1m (source):   3001 candles  |  Latest: 1789633800
   3m (agg):      1000 candles  [OK]
   5m (agg):       600 candles  [OK]
```

## Aggregation Strategy

### Lower Timeframes (5s, 10s, 15s, 30s)
- Generated from 1m candles during real-time streaming
- Used for chart display and fast signal generation

### Higher Timeframes (3m, 5m, 10m, 15m, 30m, 1h)
- **Aggregated from 1m candles** using proper OHLCV logic:
  - **Open** → First candle's open in the period
  - **High** → Maximum high of all candles in the period
  - **Low** → Minimum low of all candles in the period
  - **Close** → Last candle's close in the period
  - **Volume** → Sum of all volumes in the period

## Configuration

### Selected Pairs (`selected_signal_pairs.json`)

```json
[
  "USD/INR (OTC)",
  "CHF/JPY (OTC)",
  "USD/PKR (OTC)",
  "CAD/JPY (OTC)"
]
```

**To change selected pairs:**
1. Edit `selected_signal_pairs.json`
2. Save it
3. The background aggregator will pick up changes within 60 seconds

### Aggregation Timeframes

Edit `ml/data/candle_aggregator_bg.py` to change target timeframes:

```python
TARGET_TIMEFRAMES = ["3m", "5m", "10m", "15m", "30m", "1h"]
```

## Performance Notes

- **Memory impact**: Minimal (~5-10 MB for all pairs)
- **CPU impact**: <1% during aggregation cycles
- **Database I/O**: Optimized with batch writes
- **Throttling**: 30-second minimum interval between aggregations per pair

## Troubleshooting

### No aggregated candles appearing?

1. **Check selected pairs:**
   ```bash
   python -c "import json; print(json.load(open('selected_signal_pairs.json')))"
   ```

2. **Check 1m candle count:**
   ```bash
   python monitor_bg_aggregation.py
   ```
   
   If 1m candles are missing, the system isn't receiving data yet.

3. **Verify database connection:**
   ```bash
   sqlite3 quotex_candles.db "SELECT COUNT(*) FROM candles WHERE timeframe='1m';"
   ```

### Aggregator not running?

Check engine logs for:
```
[OK] ✅ BackgroundCandleAggregator imported successfully
✅ Background candle aggregator started
```

If not present, verify:
- `ml/data/candle_aggregator_bg.py` exists
- `engine.py` has `BackgroundCandleAggregator` import

## API Reference

### BackgroundCandleAggregator

```python
from ml.data.candle_aggregator_bg import BackgroundCandleAggregator
from ml.data.candle_store import CandleStore

# Initialize
store = CandleStore("quotex_candles.db")
agg = BackgroundCandleAggregator(store)

# Start background loop
await agg.start()

# Stop gracefully
await agg.stop()
```

## Integration with ML Models

Aggregated candles are automatically available to ML models:

```python
# Get 5m candles for analysis
candles_5m = store.get_candles("USD/INR (OTC)", "5m", limit=100)

# All models can use these without waiting
for candle in candles_5m:
    # candle has: time, open, high, low, close, volume
    process(candle)
```

## Related Files

- **[engine.py](engine.py)** — Main engine that starts the aggregator
- **[ml/data/candle_aggregator_bg.py](ml/data/candle_aggregator_bg.py)** — Core aggregation logic
- **[ml/data/candle_store.py](ml/data/candle_store.py)** — SQLite persistence layer
- **[monitor_bg_aggregation.py](monitor_bg_aggregation.py)** — Progress monitoring script
- **[selected_signal_pairs.json](selected_signal_pairs.json)** — Pair selection config

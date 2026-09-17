# Frontend Integration Guide — Charts & Scrolling

This guide shows how to wire up the TradingView Lightweight Charts library (or your current charting solution) to support:
1. **Historical scrolling** (load older candles from database)
2. **Oscillators** (RSI, MACD, Bollinger Bands, etc.)

---

## 📌 Quick Start: Enable Chart Scrolling

### Step 1: Add Scroll Event Listener

```javascript
// In your chart initialization or update function
const chart = LightweightCharts.createChart(container, options);
const candleSeries = chart.addCandlestickSeries();

// Track the oldest visible candle time
let oldestVisibleTime = null;

// Listen for range changes (user scrolls/zooms)
chart.subscribeVisibleRangeChange((range) => {
  if (!range) return;
  
  // Calculate the new oldest time
  const visibleBars = range.to - range.from;
  const period = TIMEFRAMES[currentTimeframe];
  const newOldest = Math.floor(range.from * period);
  
  // Check if user scrolled past our loaded data
  if (candleSeries.data().length > 0) {
    const firstCandle = candleSeries.data()[0];
    if (newOldest < firstCandle.time) {
      loadHistoricalCandles(newOldest);
    }
  }
});

function loadHistoricalCandles(beforeTime) {
  eel.get_candles_from_store(
    CURRENT_ASSET,
    CURRENT_TIMEFRAME,
    200,  // limit
    beforeTime  // before_time parameter
  )(candles => {
    if (candles && candles.length > 0) {
      candleSeries.prependData(candles);
      console.log(`✅ Loaded ${candles.length} older candles`);
    }
  });
}
```

### Step 2: Track State

```javascript
// Global state
let CURRENT_ASSET = "AUD/CAD (OTC)";
let CURRENT_TIMEFRAME = "1m";
let TIMEFRAMES = {
  "5s": 5, "10s": 10, "15s": 15, "30s": 30,
  "1m": 60, "2m": 120, "3m": 180, "5m": 300,
  "10m": 600, "15m": 900, "30m": 1800,
  "1h": 3600, "4h": 14400
};
```

---

## 📊 Oscillators: RSI Example

### Step 1: Create Oscillator Panel

```javascript
// Add RSI as a separate panel below the main chart
const rsiPanel = chart.addLineSeries({
  color: '#0066CC',
  lineWidth: 1
});

// Draw overbought/oversold zones
chart.addLineSeries({
  color: '#888888',
  lineWidth: 1,
  lineStyle: 2  // Dashed
});
```

### Step 2: Calculate RSI on Backend

```python
# In engine.py

@eel.expose
def calculate_rsi(asset: str, timeframe: str, period: int = 14):
    """Calculate RSI oscillator for charting.
    
    Args:
        asset: Asset symbol
        timeframe: Timeframe
        period: RSI period (default 14)
    
    Returns:
        List of {time, value} dicts
    """
    global CANDLE_STORE
    if not CANDLE_STORE:
        return []
    
    try:
        import pandas as pd
        import numpy as np
        
        # Load last 200 candles (enough for reliable RSI)
        candles = CANDLE_STORE.get_candles(asset, timeframe, limit=200)
        if len(candles) < period:
            return []
        
        # Extract closes
        closes = pd.Series([c['close'] for c in candles])
        
        # Calculate RSI
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # Return as {time, value} pairs
        result = []
        for i, candle in enumerate(candles):
            if not pd.isna(rsi.iloc[i]):
                result.append({
                    'time': candle['time'],
                    'value': float(rsi.iloc[i])
                })
        
        return result
    except Exception as e:
        log(f"⚠️ RSI calculation error: {e}", 1)
        return []
```

### Step 3: Display RSI on Chart (with Scroll Support)

```javascript
// Track oscillator visibility
let rsiVisible = false;
let macdVisible = false;
let bbVisible = false;

// After loading candles
function updateRSI() {
  eel.calculate_rsi(CURRENT_ASSET, CURRENT_TIMEFRAME, 14)(rsiValues => {
    if (rsiValues && rsiValues.length > 0) {
      rsiPanel.setData(rsiValues);
      console.log(`✅ Updated RSI with ${rsiValues.length} values`);
    }
  });
}

function updateMACD() {
  eel.calculate_macd(CURRENT_ASSET, CURRENT_TIMEFRAME)(macdValues => {
    if (macdValues && macdValues.length > 0) {
      macdPanel.setData(macdValues.map(v => ({time: v.time, value: v.macd})));
      console.log(`✅ Updated MACD with ${macdValues.length} values`);
    }
  });
}

function updateBB() {
  eel.calculate_bollinger_bands(CURRENT_ASSET, CURRENT_TIMEFRAME)(bbValues => {
    if (bbValues && bbValues.length > 0) {
      bbUpperPanel.setData(bbValues.map(v => ({time: v.time, value: v.upper})));
      bbLowerPanel.setData(bbValues.map(v => ({time: v.time, value: v.lower})));
      console.log(`✅ Updated Bollinger Bands with ${bbValues.length} values`);
    }
  });
}

// Toggle functions
function toggleRSI() {
  if (!rsiVisible) {
    updateRSI();
    rsiVisible = true;
  } else {
    rsiPanel.setData([]);
    rsiVisible = false;
  }
}

function toggleMACD() {
  if (!macdVisible) {
    updateMACD();
    macdVisible = true;
  } else {
    macdPanel.setData([]);
    macdVisible = false;
  }
}

function toggleBB() {
  if (!bbVisible) {
    updateBB();
    bbVisible = true;
  } else {
    bbUpperPanel.setData([]);
    bbLowerPanel.setData([]);
    bbVisible = false;
  }
}
```

---

## 🔄 Complete Chart Initialization Example

```javascript
// Initialize chart on page load
async function initializeChart() {
  // 1. Create chart
  const container = document.getElementById('chart-container');
  const chart = LightweightCharts.createChart(container, {
    layout: {
      backgroundColor: '#ffffff',
      textColor: 'rgba(0, 0, 0, 0.9)',
    },
    width: 1000,
    height: 600,
    timeScale: {
      timeVisible: true,
      secondsVisible: false,
    },
  });

  // 2. Add main candlestick series
  const candleSeries = chart.addCandlestickSeries({
    upColor: '#00C510',
    downColor: '#ff0000',
    borderUpColor: '#00C510',
    borderDownColor: '#ff0000',
    wickUpColor: '#00C510',
    wickDownColor: '#ff0000',
  });

  // 3. Add volume bars
  const volumeSeries = chart.addHistogramSeries({
    color: '#385263',
  });

  // 4. Add oscillator panels
  const rsiPanel = chart.addLineSeries({
    color: '#0066CC',
    lineWidth: 2,
  });

  const macdPanel = chart.addLineSeries({
    color: '#FF6B6B',
    lineWidth: 1,
  });

  const bbUpperPanel = chart.addLineSeries({
    color: '#888888',
    lineWidth: 1,
    lineStyle: 2,  // Dashed
  });

  const bbLowerPanel = chart.addLineSeries({
    color: '#888888',
    lineWidth: 1,
    lineStyle: 2,  // Dashed
  });

  // 5. Load initial candles from database
  eel.get_candles_from_store(
    CURRENT_ASSET,
    CURRENT_TIMEFRAME,
    200  // Load 200 most recent
  )(candles => {
    if (candles && candles.length > 0) {
      candleSeries.setData(candles);
      
      // Extract volume for volume chart
      const volumeData = candles.map(c => ({
        time: c.time,
        value: c.volume || 0,
        color: c.close >= c.open ? '#00C51055' : '#ff000055'
      }));
      volumeSeries.setData(volumeData);
      
      console.log(`✅ Loaded ${candles.length} candles`);
      chart.timeScale().fitContent();
    }
  });

  // 6. Listen for chart scrolling
  chart.subscribeVisibleRangeChange((range) => {
    if (!range) return;
    
    const allCandles = candleSeries.data();
    if (allCandles.length === 0) return;
    
    // Check if scrolled to beginning of loaded data
    const firstCandle = allCandles[0];
    const timeframeSeconds = TIMEFRAMES[CURRENT_TIMEFRAME];
    
    // Estimate the time of the leftmost visible bar
    const timeRange = range.to - range.from;
    const visibleStartTime = Math.floor((range.from - timeRange * 0.5) * timeframeSeconds);
    
    if (visibleStartTime < firstCandle.time) {
      console.log(`📜 Scrolling left, loading candles before ${firstCandle.time}`);
      loadMoreHistory(firstCandle.time);
    }
  });

  // 7. Handle timeframe changes
  window.changeTimeframe = function(newTf) {
    CURRENT_TIMEFRAME = newTf;
    eel.change_timeframe(newTf)(() => {
      // Reload chart
      location.reload();  // Simple approach; better: async update
    });
  };

  return { chart, candleSeries, volumeSeries, rsiSeries };
}

function loadMoreHistory(beforeTime) {
  eel.get_candles_from_store(
    CURRENT_ASSET,
    CURRENT_TIMEFRAME,
    200,
    beforeTime
  )(candles => {
    if (candles && candles.length > 0) {
      candleSeries.prependData(candles);
      console.log(`✅ Prepended ${candles.length} candles`);
      
      // Recalculate oscillators with expanded data
      if (rsiVisible) updateRSI();
      if (macdVisible) updateMACD();
      if (bbVisible) updateBB();
    }
  });
}


// Start on page load
document.addEventListener('DOMContentLoaded', initializeChart);
```

---

## 🎨 HTML Structure

```html
<!DOCTYPE html>
<html>
<head>
  <title>QuotexChart</title>
  <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 20px;
      background: #f5f5f5;
    }
    
    #toolbar {
      margin-bottom: 20px;
      display: flex;
      gap: 10px;
    }
    
    #chart-container {
      width: 100%;
      height: 600px;
      background: white;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    
    button {
      padding: 8px 16px;
      background: #0066CC;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
    }
    
    button:hover {
      background: #0052A3;
    }
    
    select {
      padding: 8px 12px;
      border-radius: 4px;
      border: 1px solid #ddd;
    }
  </style>
</head>
<body>
  <div id="toolbar">
    <select id="timeframe-select" onchange="changeTimeframe(this.value)">
      <option value="1m">1 Minute</option>
      <option value="5m">5 Minutes</option>
      <option value="15m">15 Minutes</option>
      <option value="1h">1 Hour</option>
      <option value="4h">4 Hours</option>
    </select>
    
    <button onclick="toggleRSI()">📊 RSI</button>
    <button onclick="toggleMACD()">📈 MACD</button>
    <button onclick="toggleBB()">📍 Bollinger Bands</button>
  </div>
  
  <div id="chart-container"></div>
  
  <script src="chart.js"></script>
</body>
</html>
```

---

## 📝 Backend Endpoints (Already Implemented)

The following oscillator endpoints have been added to engine.py:

- **`calculate_rsi(asset, timeframe, period=14, limit=200)`** — Returns RSI values
- **`calculate_macd(asset, timeframe, limit=200)`** — Returns MACD, signal, histogram
- **`calculate_bollinger_bands(asset, timeframe, period=20, stddev=2, limit=200)`** — Returns upper, middle, lower bands

These are called automatically when you toggle oscillators or scroll to load more history.

---

## ⚡ Performance Tips

### 1. **Lazy Load Oscillators** ✅
Oscillators are only calculated when you toggle them on (not on page load). This saves computation time and keeps the UI responsive.

The toggle functions (`toggleRSI()`, `toggleMACD()`, `toggleBB()`) are defined above — they calculate on-demand and recalculate when you scroll to load historical data.

### 2. **Debounce Scroll Events**
```javascript
let scrollTimeout;

chart.subscribeVisibleRangeChange((range) => {
  clearTimeout(scrollTimeout);
  scrollTimeout = setTimeout(() => {
    // Load history (debounced)
    loadMoreHistory(...);
  }, 300);  // Wait 300ms after scroll stops
});
```

### 3. **Cache Oscillator Results**
```python
# In engine.py
OSCILLATOR_CACHE = {}

@eel.expose
def calculate_rsi(...):
    cache_key = f"{asset}_{timeframe}_rsi_14"
    if cache_key in OSCILLATOR_CACHE:
        return OSCILLATOR_CACHE[cache_key]
    
    # ... calculation ...
    
    OSCILLATOR_CACHE[cache_key] = result
    return result
```

---

## 🧪 Testing Checklist

- [ ] Chart loads 200 candles on startup
- [ ] Scroll left → loads 200 more candles
- [ ] Continue scrolling → keeps loading history (infinite scroll)
- [ ] Change timeframe → chart updates with correct data
- [ ] Toggle RSI → oscillator displays correctly
- [ ] Resize chart → responsive to window size
- [ ] No lag when scrolling (use DevTools Performance tab)
- [ ] Database queries are fast (< 100ms per 200 candles)

---

## 🔗 Integration Checklist

- [ ] Add `eel.js` script tag (already done in your HTML)
- [ ] Copy chart initialization code to your HTML
- [ ] Implement scroll event listener
- [ ] Add oscillator buttons to UI
- [ ] Create backend endpoints for RSI/MACD/BB
- [ ] Test with real data from Quotex API
- [ ] Optimize database queries if needed

---

**Next Step**: Add these endpoints to [engine.py](D:\QuotexChart\engine.py) and wire them to your frontend!

# Phase 1: Binary Options Feature Engineering - Implementation Checklist

**Status:** Skeleton Code Ready  
**Created:** 2026-09-18  
**Effort Estimate:** 4-6 hours  
**Files Created:** 4 core modules + stubs

---

## 📋 Deliverables Checklist

### ✅ Completed (Skeleton Ready)
- [x] `ml/features/binary_options_features.py` - Feature extraction class
- [x] `ml/models/reversal_predictor.py` - Reversal time prediction model
- [x] `ml/trading/money_manager.py` - Kelly Criterion position sizing
- [x] `IMPLEMENTATION_PLAN_BINARY_OPTIONS.md` - Full 3-phase plan

### ⏳ To Implement (In Order)

---

## Phase 1.1: Momentum & Reversal Detection (1-2 hours)

### Task 1.1.1: Implement `_momentum_velocity()` in BinaryOptionsFeatureEngineer

**Location:** `ml/features/binary_options_features.py:120-128`

**What it does:** Calculate how fast momentum is changing (pips per second)

**Algorithm:**
```python
def _momentum_velocity(self, closes: np.ndarray) -> float:
    """
    Compare rate of change over two periods to see acceleration:
    - Period 1 (old): closes[-40:-20] vs closes[-60:-40]
    - Period 2 (new): closes[-20:] vs closes[-40:-20]
    
    velocity = (new_roc - old_roc) / time_elapsed
    """
    # Calculate rate of change over last 20 candles
    # Then compare to RoC over previous 20 candles
    # Return: pips per second (positive = accelerating up, negative = down)
```

**Success criteria:**
- Returns float between -0.1 and +0.1 (reasonable pip range)
- Positive when momentum is accelerating upward
- Negative when momentum is accelerating downward
- Zero when momentum is stable

**Test with:** `test_momentum_velocity()`
```python
def test_momentum_velocity():
    closes = np.array([1.2000, 1.2001, 1.2003, 1.2006, 1.2010, ...])  # Accelerating
    engineer = BinaryOptionsFeatureEngineer()
    velocity = engineer._momentum_velocity(closes[-50:])
    assert velocity > 0, "Should be positive for accelerating uptrend"
```

---

### Task 1.1.2: Implement `_trend_age_seconds()` in BinaryOptionsFeatureEngineer

**Location:** `ml/features/binary_options_features.py:152-166`

**What it does:** Determine how many seconds the current trend has been active

**Algorithm:**
```python
def _trend_age_seconds(self, closes: np.ndarray) -> int:
    """
    Find the most recent trend change (reversal point)
    Calculate seconds since that reversal
    
    Steps:
    1. Calculate % return over last 5, 10, 20, 50 candles
    2. Find the most negative return (reversal point)
    3. Calculate seconds from then to now
    
    Returns: integer seconds
    """
```

**Success criteria:**
- Returns integer seconds (e.g., 120, 300, 600)
- Returns 0 if just reversed
- Returns >0 if trend is ongoing
- Increases over time as trend matures

**Test with:**
```python
def test_trend_age():
    # Uptrend that started 10 minutes ago
    closes = np.concatenate([
        np.array([1.2000] * 50),  # Flat before
        np.linspace(1.2000, 1.2050, 60),  # 10min uptrend
    ])
    engineer = BinaryOptionsFeatureEngineer()
    age = engineer._trend_age_seconds(closes[-60:])
    assert age > 500, f"Expected >500s, got {age}"  # ~10 minutes in candles
```

---

### Task 1.1.3: Implement `_predict_reversal()` in BinaryOptionsFeatureEngineer

**Location:** `ml/features/binary_options_features.py:175-192`

**What it does:** Predict when the current trend will reverse (in seconds)

**Algorithm:**
```python
def _predict_reversal(self, closes: np.ndarray) -> Tuple[int, float]:
    """
    Use multiple signals to predict reversal:
    
    Signals to use:
    1. RSI extreme (RSI > 70 or < 30): High chance of reversal soon
    2. Bollinger Band touch: Price at band edge → reversal likely
    3. Momentum divergence: Price high but momentum slowing
    4. Trend age: Older trends revert faster (mean reversion)
    5. Volatility: Expanding vol often precedes reversals
    
    Aggregate signals → time estimate + confidence
    """
```

**Success criteria:**
- Returns tuple (time_seconds, probability)
- time_seconds between 60-900 (1-15 minutes reasonable)
- probability between 0.0-1.0
- Higher probability when multiple signals agree
- Lower probability when signals conflict

**Key signals to implement:**
- RSI > 70 or < 30: Overbought/oversold, expect reversal in ~300-600 seconds
- Price at Bollinger Band edge: Expect bounce within ~60-180 seconds
- Trend age > 20min: Older trends weaker, reversal likely in ~180-600 seconds
- Volatility increasing: Reversal often follows vol spike in ~120-300 seconds

**Test with:**
```python
def test_overbought_reversal():
    # Create overbought condition (RSI > 80)
    closes = np.linspace(1.1900, 1.2100, 50)  # Strong uptrend
    engineer = BinaryOptionsFeatureEngineer()
    time_to_rev, prob = engineer._predict_reversal(closes)
    assert 180 < time_to_rev < 600, f"Expected 180-600s, got {time_to_rev}"
    assert prob > 0.4, f"Expected prob > 0.4, got {prob}"  # Overbought = likely reversal
```

---

## Phase 1.2: Volatility & Support/Resistance (1-2 hours)

### Task 1.2.1: Implement `_volatility_features()` in BinaryOptionsFeatureEngineer

**Location:** `ml/features/binary_options_features.py:220-241`

**What it does:** Calculate where volatility ranks historically (0-100) and if it's increasing/decreasing

**Algorithm:**
```python
def _volatility_features(self, closes: np.ndarray) -> Tuple[float, float]:
    """
    Calculate:
    1. volatility_percentile: Rank current volatility vs historical (0-100)
       - Calculate ATR or std dev over last 20 candles
       - Compare to historical average (all 200 candles)
       - Convert to percentile rank (0-100)
    
    2. volatility_trend: Is vol increasing (+1) or decreasing (-1)?
       - Compare vol in last 10 vs previous 10 candles
       - Return: -1 to +1 (negative = decreasing, positive = increasing)
    """
```

**Success criteria:**
- volatility_percentile between 0-100
- 50 = median historical volatility
- 80+ = high volatility (expect reversals)
- volatility_trend between -1 and +1
- Positive = vol expanding (reversal imminent)
- Negative = vol contracting (quiet period)

**Test with:**
```python
def test_volatility_percentile():
    # Base quiet candles
    quiet = np.full(100, 1.2000)  # No movement
    closes = np.concatenate([quiet, quiet, quiet])  # 300 candles quiet
    
    engineer = BinaryOptionsFeatureEngineer()
    percentile, trend = engineer._volatility_features(closes)
    assert percentile < 20, f"Quiet period should be low vol, got {percentile}"
    assert trend < 0, f"Stable vol should trend down, got {trend}"
```

---

### Task 1.2.2: Implement `_support_resistance()` in BinaryOptionsFeatureEngineer

**Location:** `ml/features/binary_options_features.py:281-295`

**What it does:** Find nearest support and resistance levels

**Algorithm:**
```python
def _support_resistance(self, lows: np.ndarray, highs: np.ndarray) -> Tuple[float, float]:
    """
    Find key price levels where reversals often happen:
    
    Approach:
    1. Identify swing highs (local peaks) in last 50 candles
    2. Identify swing lows (local troughs) in last 50 candles
    3. Return closest level above (resistance) and below (support)
    
    Swing detection: Use rolling 5-candle window
    - Swing high: high[i] >= all neighbors
    - Swing low: low[i] <= all neighbors
    """
```

**Success criteria:**
- support_level is below current price
- resistance_level is above current price
- Levels match visual chart support/resistance
- Levels update as price moves to new extremes

**Test with:**
```python
def test_support_resistance():
    highs = np.array([1.2000, 1.2050, 1.2020, 1.2010, 1.2000])
    lows = np.array([1.1950, 1.2000, 1.1980, 1.1990, 1.1995])
    closes = np.array([1.2000, 1.2050, 1.2020, 1.2010, 1.2000])
    
    engineer = BinaryOptionsFeatureEngineer()
    support, resistance = engineer._support_resistance(lows, highs)
    
    current_price = 1.2000
    assert support < current_price, "Support should be below price"
    assert resistance > current_price, "Resistance should be above price"
```

---

## Phase 1.3: Time-Based Features (30 minutes - 1 hour)

### Task 1.3.1: Implement `_price_velocity()` and `_acceleration()`

**Location:** `ml/features/binary_options_features.py:256-268`

**What they do:**
- `_price_velocity()`: pips per minute of price movement
- `_acceleration()`: is momentum accelerating (+1) or decelerating (-1)?

**Algorithm:**
```python
def _price_velocity(self, closes: np.ndarray) -> float:
    """Pips moving per minute (simple rate of change)"""
    return (closes[-1] - closes[-5]) / 5  # Last 5 candles = ~5 minutes

def _acceleration(self, closes: np.ndarray) -> float:
    """
    Compare momentum of last 5 vs previous 5 candles:
    - Positive: momentum is accelerating
    - Negative: momentum is decelerating
    """
    vel_recent = (closes[-1] - closes[-5])
    vel_prior = (closes[-6] - closes[-10])
    return 1.0 if vel_recent > vel_prior else -1.0
```

**Success criteria:**
- velocity scales with price move speed
- acceleration correctly identifies momentum changes

---

### Task 1.3.2: Implement `_time_of_day_weight()`

**Location:** `ml/features/binary_options_features.py:307-323`

**What it does:** Weight signal strength based on time of day

**Algorithm:**
```python
def _time_of_day_weight(self, candle_time: Optional[float]) -> float:
    """
    Different hours have different signal quality:
    - London/NY overlap (13:00-17:00 UTC): Strong trends, weight = +0.3
    - New York session (14:00-21:00 UTC): Active trading, weight = +0.2
    - Tokyo session (22:00-06:00 UTC): Lower volume, weight = -0.1
    - Dead hours (06:00-10:00 UTC): Very quiet, weight = -0.3
    
    Returns: -1 to +1 multiplier
    """
```

**Note:** May need UTC timestamp handling

---

## Phase 1.4: Integration Tests (30 minutes)

### Task 1.4.1: Wire BinaryOptionsFeatureEngineer into signal aggregator

**Location:** `ml/aggregation/signal_aggregator.py`

**Changes:**
```python
# Add import
from ml.features.binary_options_features import BinaryOptionsFeatureEngineer

# In SignalResult.to_dict() or new method:
def add_binary_options_data(self, candles: List[Dict]):
    """Enrich signal with binary options features"""
    engineer = BinaryOptionsFeatureEngineer()
    bo_features = engineer.extract(candles)
    
    # Add to signal
    self.binary_options_features = bo_features
    self.confidence_by_expiration = {
        "1m": self._adjust_confidence_for_expiration(bo_features, 60),
        "5m": self._adjust_confidence_for_expiration(bo_features, 300),
        "15m": self._adjust_confidence_for_expiration(bo_features, 900),
    }
```

---

## Phase 1.5: Reversal Predictor Training (1 hour)

### Task 1.5.1: Implement reversal model training

**Location:** `ml/models/reversal_predictor.py:93-112`

**Steps:**
1. Collect historical candle data (3+ months)
2. Build dataset with `build_reversal_dataset()`
3. Train with XGBRegressor or LightGBMRegressor
4. Validate predictions match actual reversals

---

## 🧪 Testing Checklist

Before moving to Phase 2:

- [ ] `test_momentum_velocity()` passes
- [ ] `test_trend_age_seconds()` passes  
- [ ] `test_predict_reversal()` passes (overbought, oversold cases)
- [ ] `test_volatility_features()` passes (high vol vs low vol)
- [ ] `test_support_resistance()` passes (levels make sense visually)
- [ ] `test_price_velocity()` passes
- [ ] `test_acceleration()` passes
- [ ] Signal aggregator produces signals with binary options features
- [ ] Reversal predictor trains without errors
- [ ] Integration test: End-to-end signal generation with BO features

---

## 📊 Validation Targets

After Phase 1, signals should show:

1. **Confidence variation by expiration**
   - 1m confidence < 5m confidence < 15m confidence (usually)
   - Or warning if reversal risk too high for chosen expiration

2. **Reasonable reversal times**
   - Typical range: 60-900 seconds (1-15 minutes)
   - Extreme/overbought: 60-300 seconds
   - Early trend: 300-900 seconds

3. **Accuracy improvement**
   - 1m expiration: 56-58% win rate (up from 54%)
   - 5m expiration: 58-60% win rate (up from 55%)
   - 15m expiration: 60-62% win rate (up from 57%)

---

## 🚀 Next Steps After Phase 1

Once Phase 1 complete:
1. Start Phase 2: Money Management (kelly.py integration)
2. Test with paper trading for 10+ trades
3. Then Phase 3: Backtesting framework

---

## Notes for Implementation

**Testing with live data:**
```python
# In ml/signals.py or frontend test:
from ml.features.binary_options_features import BinaryOptionsFeatureEngineer

def test_live_bo_features():
    """Test feature extraction with real candles"""
    candles = fetch_recent_candles('EURUSD', '5m', count=200)
    engineer = BinaryOptionsFeatureEngineer()
    features = engineer.extract(candles)
    
    print(f"Momentum velocity: {features.momentum_velocity}")
    print(f"Time to reversal: {features.time_to_reversal_seconds}s")
    print(f"Safe for 1m: {features.safe_for_1m}")
    print(f"Safe for 5m: {features.safe_for_5m}")
```

**Common pitfalls to avoid:**
- Don't use future data (lookahead bias)
- Don't assume constant candle timing (variable delays)
- Test on out-of-sample data
- Account for broker spreads in calculations

---

**Status:** Ready to implement
**Est. Duration:** 4-6 hours total
**Owner:** @kbrown3695

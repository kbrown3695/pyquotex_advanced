# Binary Options Optimization - Implementation Plan

**Status:** Planning Phase  
**Target:** Transform QuotexChart from general ML trading → Binary Options Systematic Trading  
**Total Effort:** ~10-15 hours across 3 phases  
**Current Accuracy:** 54-62% (breakeven, needs 60%+ for profitability)

---

## Phase 1: Binary Options Feature Engineering (4-6 hours)

### What gets added:
New feature extractor optimized for binary options timing

#### Files to create/modify:
1. **NEW: `ml/features/binary_options_features.py`**
   - `BinaryOptionsFeatureEngineer` class
   - Extract momentum velocity (how fast trend is moving)
   - Predict time-to-reversal (when will it flip?)
   - Volatility percentile (is vol high/low/normal?)
   - Multi-timeframe strength (1m/5m/15m)
   - Time-of-day weighting (better hours?)
   - Support/resistance detection (key levels)

2. **MODIFY: `ml/features/feature_pipeline.py`**
   - Add binary options feature extraction to pipeline
   - Keep existing 11 features (still useful)
   - Add 10-12 new binary-options-specific features
   - Total: ~23-24 features

3. **NEW: `ml/models/reversal_predictor.py`**
   - Predict time-to-reversal in seconds/minutes
   - Trained separately from directional model
   - Output: Expected reversal time + confidence

4. **MODIFY: `ml/aggregation/signal_aggregator.py`**
   - Add binary options signal adjustment
   - Input: base signal + expiration time
   - Output: signal with expiration-optimized confidence
   - Warn if reversal risk too high

#### Key metrics to add to signals:
```
{
    "side": "BUY",
    "confidence": 0.72,
    "confidence_by_expiration": {
        "1m": 0.68,      # ← adjusted for 1-min expiry
        "5m": 0.72,
        "15m": 0.70
    },
    "momentum_velocity": 0.045,          # pips per second
    "time_to_reversal_seconds": 320,     # when will it flip?
    "reversal_probability": 0.25,        # what's the chance?
    "safe_expirations": ["5m", "15m"],   # which expirations to trade?
    "dangerous_expirations": ["1m"],     # which to avoid?
    "is_high_volatility": false,
    "volatility_percentile": 0.62
}
```

#### Success criteria:
- [ ] Reversal time predictions within ±2 minutes accuracy
- [ ] Volatility percentile correlates with realized volatility
- [ ] Signals show different confidence for 1m vs 5m vs 15m
- [ ] High-confidence signals have >60% accuracy (up from 54-62%)

---

## Phase 2: Money Management & Automation (2-3 hours)

### What gets added:
Kelly Criterion position sizing + optional trade automation

#### Files to create:
1. **NEW: `ml/trading/money_manager.py`**
   - Kelly Criterion calculator
   - Position sizing based on confidence
   - Account balance risk management
   - Track consecutive wins/losses
   - Adjust bet size dynamically

2. **NEW: `ml/trading/risk_manager.py`**
   - Account-level stop-loss (e.g., don't lose >10% per day)
   - Trade-level risk parameters
   - Win rate tracking
   - Daily PnL monitoring

3. **NEW: `frontend/binary_trader.js`** (optional automation)
   - Automated trade execution via Quotex API
   - Position sizing calculator UI
   - Account balance tracker
   - Live PnL display

#### Kelly Criterion implementation:
```python
# For binary options: 85% payout on win, 100% loss on loss
win_rate = 0.57
payout = 0.85
loss = 1.0

kelly_fraction = 2 * ((win_rate * payout) - ((1 - win_rate) * loss)) / payout
# kelly_fraction ≈ 0.128 (12.8% of account per trade)

# Adjusted for confidence:
trade_size = kelly_fraction * signal_confidence
# For 0.72 confidence: 0.128 * 0.72 = 9.2% of account
```

#### Success criteria:
- [ ] Position sizing calculator produces Kelly-optimal sizes
- [ ] Account risk stays within defined bounds
- [ ] Consecutive loss handling reduces bet size
- [ ] Money manager integrates with signal aggregator

---

## Phase 3: Backtesting & Validation (2-3 hours)

### What gets added:
Binary options simulator + edge verification

#### Files to create:
1. **NEW: `ml/backtesting/binary_simulator.py`**
   - Simulates binary options trades with realistic assumptions
   - Inputs: historical candles, signals with timing
   - Output: Win rate, ROI, drawdown, Sharpe ratio
   - Accounts for slippage, fees, spread

2. **NEW: `ml/backtesting/backtest_runner.py`**
   - Runs backtest on historical data
   - Generates report: accuracy by expiration time
   - Shows break-even analysis
   - Validates money management rules

3. **NEW: `frontend/backtest_viewer.html`**
   - View backtest results
   - Charts: equity curve, win rate, drawdown
   - Filter by asset, timeframe, expiration time
   - Export report

#### Backtest report should show:
```
BACKTEST RESULTS: EUR/USD (1m expiration)
================================================
Period: Last 30 days
Trades: 245
Win Rate: 57.1% (140 wins, 105 losses)
Break-even: 54.05% (achieved!)

By Expiration Time:
  - 1m:  56.2% accuracy (235 trades)
  - 5m:  58.9% accuracy (78 trades)
  - 15m: 59.1% accuracy (45 trades)

With Money Management (Kelly @ 80%):
  - Starting balance: $1,000
  - Ending balance: $1,245 (+24.5%)
  - Max drawdown: -8.2%
  - Sharpe ratio: 1.24

Conclusion: Strategy is PROFITABLE with edge
Recommendation: SAFE for live trading at 50% Kelly sizing
```

#### Success criteria:
- [ ] Backtest shows 58%+ win rate (profitable margin)
- [ ] Different expirations show different accuracies
- [ ] Money management prevents ruin-level losses
- [ ] Results reproducible on different periods

---

## Implementation Order

### Week 1:
1. **Day 1-2:** Phase 1 feature engineering
   - Binary options feature extractor
   - Reversal predictor training
   - Signal adjustment logic

2. **Day 2-3:** Phase 2 money management
   - Kelly Criterion implementation
   - Position sizing UI
   - Risk manager

3. **Day 4:** Phase 3 backtesting
   - Binary simulator
   - Backtest runner
   - Results viewer

### Testing at each phase:
- Unit tests for feature calculations
- Integration tests with signal aggregator
- Manual testing with paper trading
- Backtest validation

---

## Critical Dependencies

```
Phase 1 (Features) → Phase 2 (Money Mgmt) → Phase 3 (Backtesting)
                          ↓
                      Phase 4: Live Trading (future)
```

**Phase 1 MUST complete** before Phase 2 starts (signals need timing info)

---

## Success Metrics

| Metric | Current | Target | Phase |
|--------|---------|--------|-------|
| Win rate | 54-62% | 58-65% | 1 |
| Accuracy by expiration | None | Tracked | 1 |
| Position sizing | Manual | Automated Kelly | 2 |
| Account safety | None | Daily/drawdown limits | 2 |
| Profitability verified | No | Yes (backtest) | 3 |
| Trade automation | No | Optional auto-execute | 2 |

---

## Risk Mitigation

- **Phase 1:** Validate features produce expected signals before integration
- **Phase 2:** Test Kelly sizing with paper money first
- **Phase 3:** Run extended backtests (60+ days) before trusting results
- **Phase 4:** Start with 10% position sizing, scale up after 100 trades

---

## Resources Needed

- Historical candle data (60-90 days minimum for backtesting)
- Feature extraction validation dataset
- Quotex API documentation (for automation)
- Paper trading account for testing

---

**Next Step:** Start Phase 1 feature engineering

# Phase G3 Integration Guide

**Status**: ✅ Complete and ready to use  
**Integration Points**: signal_service.py + engine.py  
**Hook Function**: `report_trade_outcome()`  

---

## Quick Start

### 1. Trade Completion Event

When a trade closes (either manually or via bot), extract:

```python
trade_result = {
    "profit": 150.0,                      # P&L (positive = win)
    "components": signal_result.components,  # Model predictions
    "side": "BUY",                        # Trade direction
    "entry": 1000.0,                      # Entry price
    "exit": 1150.0,                       # Exit price
}
```

### 2. Call the Hook

From JavaScript/Frontend:

```javascript
// After trade closes with P&L
eel.report_trade_outcome(
    profit,           // float: P&L
    components,       // dict: signal components
    side,             // str: "BUY" or "SELL"
    entry_price,      // float: entry
    exit_price        // float: exit
)(function(result) {
    console.log("G3 updated:", result);
});
```

Or from Python (if integrated with a trading bot):

```python
from eel_interface import eel

result = eel.report_trade_outcome(
    profit=150.0,
    components={"ensemble": {}, "kalman": {}},
    side="BUY",
    entry=1000.0,
    exit=1150.0
)()

print(f"G3 Status: {result}")
```

### 3. Response

The hook returns updated G3 statistics:

```json
{
    "success": true,
    "profit": 150.0,
    "trades_evaluated": 25,
    "win_rates": {
        "ensemble": 0.64,
        "kalman": 0.58,
        "lstm": 0.60
    },
    "current_weights": {
        "ensemble": 0.45,
        "advanced": 0.25,
        "deep": 0.30
    }
}
```

---

## Architecture

### Components

**1. OnlineLearningOptimizer** (`ml/optimization/online_learning_optimizer.py`)
- Core algorithm: tracks wins/losses per model
- Adapts weights every 10 trades
- Conservative learning rate (0.5% per cycle)
- Bounds: ±20% of baseline

**2. OnlineLearningManager** (`ml/serving/online_learning_manager.py`)
- Integration wrapper
- Manages optimizer lifecycle
- Exposes: `process_trade_outcome()`, `get_current_weights()`, `get_performance_stats()`

**3. MLSignalService** (updated in `ml/serving/signal_service.py`)
- Initializes `online_learning_manager` at startup
- Exposes: `process_trade_outcome()`, `get_g3_stats()`, `get_g3_report()`

**4. Engine Hook** (updated in `engine.py`)
- `@eel.expose report_trade_outcome()` 
- Callable from UI or trading bot
- Returns G3 stats for display/logging

### Flow Diagram

```
Trade Completed (Manual or Bot)
    ↓
Extract P&L + Signal Components
    ↓
Call report_trade_outcome() [eel.expose]
    ↓
engine.py → ML_SERVICE.process_trade_outcome()
    ↓
MLSignalService → online_learning_manager.process_trade_outcome()
    ↓
OnlineLearningOptimizer
    ├─ Track: model_wins[model] += 1 (if profit > 0)
    ├─ Track: model_losses[model] += 1 (if profit <= 0)
    ├─ Every 10 trades:
    │   ├─ Calculate win rates per model
    │   ├─ Adapt weights (±0.5% per cycle)
    │   ├─ Enforce ±20% bounds
    │   └─ Renormalize to sum to 1.0
    └─ Return stats
    ↓
Return to caller with updated weights + stats
```

---

## Implementation Examples

### Frontend (JavaScript/HTML)

```javascript
// When a trade closes on the Quotex platform

async function onTradeClose(trade) {
    // Extract data
    const profit = trade.exit_price - trade.entry_price;
    const components = trade.signal_components; // from signal_result
    
    // Call G3 hook
    const result = await new Promise((resolve) => {
        eel.report_trade_outcome(
            profit,
            components,
            trade.side,
            trade.entry_price,
            trade.exit_price
        )(resolve);
    });
    
    // Display updated stats
    console.log(`G3 Trades: ${result.trades_evaluated}`);
    console.log(`Win Rates:`, result.win_rates);
    
    // Optional: update UI with new weights
    displayAdaptedWeights(result.current_weights);
}
```

### Python Bot Integration

```python
from engine import ML_SERVICE

def on_trade_complete(trade):
    """Called when a trade closes."""
    
    profit = trade.exit - trade.entry
    
    # Get signal components from the trade's signal
    components = trade.signal_components
    
    # Update G3
    ML_SERVICE.process_trade_outcome({
        "profit": profit,
        "components": components,
        "side": trade.side,
        "entry": trade.entry,
        "exit": trade.exit,
        "timestamp": time.time(),
    })
    
    # Get updated stats
    stats = ML_SERVICE.get_g3_stats()
    print(f"Trades: {stats['trades_evaluated']}")
    print(f"Win Rates: {stats['win_rates']}")
    print(f"Adapted Weights: {stats['current_weights']}")
```

### Direct ML Service Call

```python
from ml.serving.signal_service import MLSignalService

# Initialize service
ml_service = MLSignalService(enable_g3=True)

# After training models...

# Report trade
ml_service.process_trade_outcome({
    "profit": 100.0,
    "components": {
        "ensemble": {"p_up": 0.65},
        "kalman": {"p_up": 0.60},
        "lstm": {"p_up": 0.70},
    },
    "side": "BUY",
    "entry": 1000.0,
    "exit": 1100.0,
})

# Get stats
stats = ml_service.get_g3_stats()
print(f"Ensemble win rate: {stats['win_rates']['ensemble']:.1%}")

# Get report
report = ml_service.get_g3_report()
print(report)
```

---

## What G3 Does

### Tracking

For each completed trade:

1. **Record Result**: Win or loss based on profit > 0
2. **Credit Models**: Increment win/loss counters for each model in the signal
3. **Adapt Every 10 Trades**: Calculate win rates and adjust weights

### Weight Adaptation

Every 10 trades, for each model:

```
win_rate = wins / (wins + losses)

if win_rate > 0.55:
    new_weight = current_weight * (1 + 0.005)  # Boost by 0.5%
elif win_rate < 0.45:
    new_weight = current_weight * (1 - 0.005)  # Reduce by 0.5%
else:
    new_weight = current_weight                  # Keep unchanged

# Enforce ±20% bounds around baseline
new_weight = clip(new_weight, baseline*0.8, baseline*1.2)

# Renormalize all weights to sum to 1.0
```

### Example Timeline

**Trades 1-10**:
- Ensemble: 8 wins, 2 losses (80% win rate)
- Kalman: 6 wins, 4 losses (60% win rate)
- LSTM: 7 wins, 3 losses (70% win rate)

**Trade 10 - Adaptation**:
- Ensemble: 0.45 * 1.005 = 0.45225 (boosted, >55%)
- Kalman: 0.25 (neutral, 45-55%)
- LSTM: 0.30 * 1.005 = 0.30150 (boosted, >55%)
- Renormalize: [0.45225, 0.25, 0.30150] / sum ≈ [0.450, 0.250, 0.300]

**Trades 11-20**:
- Continue tracking with slightly boosted ensemble/lstm

**Trade 20 - Adaptation**:
- Cumulative win rates drive further adaptation
- Weights converge to optimal for current market

---

## Monitoring G3

### Dashboard/UI Integration

Display in real-time:

```json
{
    "Phase G3 Status": {
        "Trades Evaluated": 47,
        "Win Rate (Overall)": "59.6%",
        "Model Win Rates": {
            "Ensemble": "62%",
            "Kalman": "55%",
            "Advanced": "58%",
            "Deep": "61%"
        },
        "Adapted Weights": {
            "Ensemble": "0.452 (+0.2% from baseline)",
            "Advanced": "0.248 (-0.8% from baseline)",
            "Deep": "0.300 (unchanged)"
        },
        "Last Adaptation": "Trade #40 (7 minutes ago)",
        "Next Adaptation": "Trade #50 (13 trades remaining)"
    }
}
```

### Logging

Each adaptation creates a log entry:

```
[16:45:23] G3: Trade #10 - First adaptation
  Ensemble: 0.45 (80% win rate, +0.5%)
  Kalman: 0.25 (60% win rate, neutral)
  LSTM: 0.30 (70% win rate, +0.5%)
  
[16:52:15] G3: Trade #20 - Second adaptation
  Ensemble: 0.453 (75% win rate, boosted again)
  Kalman: 0.248 (50% win rate, reduced -0.5%)
  LSTM: 0.303 (72% win rate, boosted again)
```

---

## Disabling G3

If you want to disable G3 temporarily:

```python
# In engine.py or initialization
ML_SERVICE = MLSignalService(enable_g3=False)

# Or via environment variable
import os
os.environ["G3_ENABLED"] = "false"
```

When disabled:
- G3 still tracks statistics (for analysis)
- But doesn't adapt weights
- Signal generation uses Phase F baseline weights

---

## Troubleshooting

### G3 Not Updating

**Check**:
1. `ML_SERVICE` is initialized: `print(ML_SERVICE.online_learning_manager)`
2. Trades are being reported: Check console logs for `report_trade_outcome` calls
3. Minimum sample size reached: G3 requires 20+ trades before first adaptation

**Fix**:
```python
if ML_SERVICE:
    stats = ML_SERVICE.get_g3_stats()
    print(f"Trades: {stats['trades_evaluated']}")
    print(f"Next adaptation at trade #{(stats['trades_evaluated'] // 10 + 1) * 10}")
```

### Weights Not Changing

**Possible Reasons**:
1. Win rate is neutral (45-55%) → no adaptation
2. Less than 10 trades since last adaptation
3. Weights already at bounds (±20%)

**Debug**:
```python
stats = ML_SERVICE.get_g3_stats()
print("Win rates:", stats['win_rates'])
print("Current weights:", stats['current_weights'])
print("Baseline weights:", stats['baseline_weights'])

# Check if at bounds
for model, current in stats['current_weights'].items():
    baseline = stats['baseline_weights'][model]
    min_w = baseline * 0.8
    max_w = baseline * 1.2
    print(f"{model}: {current:.3f} (bounds: {min_w:.3f}-{max_w:.3f})")
```

### Performance Degradation

**If win rate drops**:
1. G3 may be overfitting (try tighter bounds)
2. Market regime changed (G2 + G3 handle this together)
3. Early adaptation with few trades (need more data)

**Solution**:
- Monitor for 200+ trades before judging
- Compare win rate with/without G3
- Check model win rates to see which models are weak

---

## Configuration

### Default Settings (Recommended)

```python
OnlineLearningOptimizer(
    baseline_weights={"ensemble": 0.45, "advanced": 0.25, "deep": 0.30},
    learning_rate=0.005,           # 0.5% per cycle
    adaptation_interval=10,        # Every 10 trades
    min_sample_size=20,            # Minimum before adaptation
    weight_bounds=0.20,            # ±20%
)
```

### Conservative Settings

```python
OnlineLearningOptimizer(
    baseline_weights={...},
    learning_rate=0.002,           # Slower (0.2%)
    adaptation_interval=20,        # Less frequent
    min_sample_size=50,            # More data required
    weight_bounds=0.10,            # Tighter (±10%)
)
```

### Aggressive Settings

```python
OnlineLearningOptimizer(
    baseline_weights={...},
    learning_rate=0.01,            # Faster (1.0%)
    adaptation_interval=5,         # Very frequent
    min_sample_size=10,            # Quick to learn
    weight_bounds=0.30,            # Loose (±30%)
)
```

---

## Next Steps

1. ✅ Integration complete (this session)
2. ⏳ **TODO**: Call `report_trade_outcome()` from your trading system
3. Monitor: Watch G3 adapt over first 100+ trades
4. Validate: Compare win rate with/without G3 active
5. Optimize: Tune parameters based on live results

---

## Reference

**Files**:
- `ml/optimization/online_learning_optimizer.py` — Core optimizer
- `ml/serving/online_learning_manager.py` — Integration layer
- `ml/serving/signal_service.py` — Updated with G3 integration
- `engine.py` — Updated with eel.expose hook
- `tests/test_online_learning_optimizer.py` — Test suite (21 tests, all passing)

**Related Docs**:
- `PHASE_G3_ONLINE_LEARNING.md` — Technical implementation details
- `PHASE_G_PLANNING.md` — Overall Phase G architecture

---

**Ready to start collecting live performance data!** 🚀

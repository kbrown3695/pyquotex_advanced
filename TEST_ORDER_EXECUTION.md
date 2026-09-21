# Testing Order Execution Engine
**Verification Steps for Demo Mode Trading**

---

## 🎯 Test Plan

| # | Test | Expected | Status |
|----|------|----------|--------|
| 1 | Engine starts, loads demo balance | $10,000 balance ready | [ ] |
| 2 | OrderExecutor initializes | `✅ OrderExecutor initialized` | [ ] |
| 3 | PositionTracker initializes | `✅ PositionTracker initialized` | [ ] |
| 4 | Automation can be enabled | `enable_automation()` returns True | [ ] |
| 5 | Order stats return (no trades yet) | `orders_placed: 0` | [ ] |
| 6 | Signal generates for selected pair | Console shows signal confidence | [ ] |
| 7 | Signal executes (async) | Console shows `✅ BUY ORDER EXECUTED` or similar | [ ] |
| 8 | Position opens | `get_open_positions()` shows position | [ ] |
| 9 | Position closes | `close_position()` updates P&L | [ ] |
| 10 | Statistics update | `get_position_statistics()` increments trades | [ ] |
| 11 | Export trades | JSON file created successfully | [ ] |
| 12 | Export orders | JSON file created successfully | [ ] |

---

## 🔧 Step-by-Step Test

### Part 1: Initialization (3 min)

#### Check 1: Engine Starts
```bash
python engine.py
```

**Expected output**:
```
[OK] ✅ OrderExecutor imported successfully
[OK] ✅ PositionTracker imported successfully
✅ OrderExecutor initialized
✅ PositionTracker initialized
✅ AutomatedTrader initialized (demo mode enabled)
✅ AUTO_TRADING_MANAGER initialized
```

**If error**: Check imports in engine.py lines 135-155

#### Check 2: Frontend Connects
```bash
# Browser automatically opens at http://localhost:8080/
# Or manually: http://localhost:8080/
```

**Expected**: Login page loads (or auto-login if .env configured)

#### Check 3: Verify Balance
Console tab in frontend:
```javascript
const balance = await eel.get_real_time_balance()();
console.log(`Demo Balance: $${balance.account_balance.toFixed(2)}`);
// Expected: $10,000.00 (demo mode)
```

---

### Part 2: Enable Automation (2 min)

#### Step 1: Enable Automation
```javascript
const result = await eel.enable_automation()();
console.log(`Automation enabled: ${result.enabled}`);
// Expected: true
```

**Console should show**:
```
🚀 Automated trading ENABLED for 7 pairs
✅ Registered 7 pairs with health monitor
```

#### Step 2: Verify Automation Status
```javascript
const status = await eel.get_automation_status()();
console.log(JSON.stringify(status, null, 2));
// Expected:
// {
//   "enabled": true,
//   "pairs": {
//     "selected": 7,
//     "active": 7,
//     "list": ["CHF/JPY", "USD/INR (OTC)", ...]
//   },
//   "signals": {"today": 0, "by_pair": {...}},
//   "trades": {"today": 0, "by_pair": {...}}
// }
```

---

### Part 3: Check Empty State (2 min)

#### Step 1: Zero Orders
```javascript
const exec = await eel.get_order_execution_stats()();
console.log(exec);
// Expected: all 0s (no trades yet)
```

**Expected output**:
```javascript
{
    "orders_placed": 0,
    "orders_executed": 0,
    "orders_failed": 0,
    "execution_rate_percent": 0,
    "total_traded_usd": 0.0,
    "avg_order_size": 0.0
}
```

#### Step 2: Zero Positions
```javascript
const positions = await eel.get_open_positions()();
console.log(positions);
// Expected: {}
```

#### Step 3: Zero Trades
```javascript
const trades = await eel.get_recent_trades(10)();
console.log(trades);
// Expected: []
```

#### Step 4: Zero Statistics
```javascript
const stats = await eel.get_position_statistics()();
console.log(stats);
// Expected: all 0s
```

---

### Part 4: Wait for Signals (5-10 min)

#### Watch Console for Signals
The ML service generates signals continuously. Watch the Python console:

```
🔄 SIGNAL: Buy CHF/JPY @ 75% confidence (Ensemble)
🔄 SIGNAL: Buy USD/INR (OTC) @ 68% confidence (LSTMModel)
```

#### When Signal Arrives:

**Best case** (order executes):
```
✅ BUY ORDER EXECUTED: CHF/JPY $100.00
📍 POSITION OPENED: CHFJPY_1726953600000 BUY CHF/JPY $100.00
```

**If rejected**:
```
⚠️  Trade rejected: [reason]
```

Possible rejection reasons:
- "Automation disabled" → Enable with `enable_automation()`
- "Asset not in selected pairs" → Check selected_signal_pairs.json
- "Pair is currently deactivated" → Activate with `activate_pair()`
- "Constraint: Daily limit reached" → Set `max_trades_per_day` higher
- "Low confidence" → Wait for higher confidence signal
- "Data quality" → WebSocket may be lagging

---

### Part 5: Verify Order Execution (2-3 min)

#### Check 1: Order Stats Updated
```javascript
const exec = await eel.get_order_execution_stats()();
console.log(`Orders placed: ${exec.orders_placed}, Executed: ${exec.orders_executed}`);
// Expected: 1, 1 (if order succeeded)
```

#### Check 2: Position Opened
```javascript
const positions = await eel.get_open_positions()();
console.log(JSON.stringify(positions, null, 2));
// Expected:
// {
//   "CHF/JPY": {
//     "open_positions": 1,
//     "total_exposure_usd": 100.0,
//     "positions": [
//       {
//         "id": "CHFJPY_1726953600000",
//         "side": "BUY",
//         "amount": 100.0,
//         "entry_price": 1.0178,
//         "opened_at": "2026-09-21T14:30:00.000Z"
//       }
//     ]
//   }
// }
```

#### Check 3: Statistics Updated
```javascript
const stats = await eel.get_position_statistics()();
console.log(`Open positions: ${stats.open_positions}, Total trades: ${stats.total_trades}`);
// Expected: 1 open, 1 total (if order succeeded)
```

---

### Part 6: Close Position (5 min)

#### Step 1: Get Position ID
```javascript
const positions = await eel.get_open_positions()();
const asset = Object.keys(positions)[0];
const positionId = positions[asset].positions[0].id;
console.log(`Position ID: ${positionId}`);
```

#### Step 2: Close Position
```javascript
const result = await eel.close_position(
    positionId,
    asset,
    1.0195,  // exit price
    "manual_test_close"
)();

console.log(result);
// Expected:
// {
//   "success": true,
//   "message": "Position closed: manual_test_close",
//   "pnl_pct": 0.167,
//   "pnl_usd": 0.167,
//   "status": "CLOSED_WIN"
// }
```

**Console should show**:
```
✅ POSITION CLOSED: CHFJPY_1726953600000 CHF/JPY P&L: +0.17% ($0.17)
```

#### Step 3: Verify Trade Closed
```javascript
const trades = await eel.get_recent_trades(1)();
console.log(trades[0]);
// Expected: closed_at timestamp, pnl_usd > 0, status = CLOSED_WIN
```

---

### Part 7: Export Logs (2 min)

#### Export Positions
```javascript
const result = await eel.export_position_history("test_positions.json")();
console.log(result);
// Expected: success: true
```

**Verify file exists**:
```bash
cat test_positions.json | jq '.statistics'
```

#### Export Orders
```javascript
const result = await eel.export_order_history("test_orders.json")();
console.log(result);
// Expected: success: true
```

---

## 🎯 Expected Console Output (Complete Run)

```
[14:30:00] ✅ OrderExecutor initialized
[14:30:00] ✅ PositionTracker initialized
[14:30:02] 🚀 Automated trading ENABLED for 7 pairs
[14:30:05] 🔄 SIGNAL: Buy CHF/JPY @ 75% confidence
[14:30:06] ✅ BUY ORDER EXECUTED: CHF/JPY $100.00
[14:30:06] 📍 POSITION OPENED: CHFJPY_1726953600000 BUY CHF/JPY $100.00
[14:30:40] ✅ POSITION CLOSED: CHFJPY_1726953600000 CHF/JPY P&L: +0.17% ($0.17)
[14:30:41] Position history exported to test_positions.json
[14:30:42] Order log exported to test_orders.json
```

---

## ⚠️ Troubleshooting

### "No signals generated"
- **Check**: ML service is running (`SIGNAL_MANAGER != None`)
- **Fix**: Restart engine, wait 30 seconds for ML models to load

### "Orders placed: 0 after signal"
- **Check**: Is automation enabled? (`enable_automation()`)
- **Check**: Is pair active? (`get_active_pairs()`)
- **Check**: Is confidence >= 50%?
- **Check**: Is within trading hours? (check `automation_start_hour`, `automation_end_hour`)

### "Order execution timeout"
- **Check**: OrderExecutor has client attached (`ORDER_EXECUTOR.client != None`)
- **Check**: Quotex connection is active (check console for "Login successful")
- **Fix**: Increase timeout in order_executor.py line 130

### "Position not found when closing"
- **Check**: Position ID is correct
- **Check**: Asset name matches exactly
- **Fix**: Use `get_open_positions()` to get exact position ID

### "Statistics not updating"
- **Check**: PositionTracker initialized? (`POSITION_TRACKER != None`)
- **Check**: Positions opened successfully? (check console logs)
- **Fix**: Restart engine

---

## ✅ Success Checklist

- [ ] Engine starts without errors
- [ ] Balance shows $10,000 (demo mode)
- [ ] Automation can be enabled
- [ ] Order stats show 0 initially
- [ ] Signal generates (1+ per minute)
- [ ] Order executes (console shows ✅)
- [ ] Position opens (get_open_positions returns data)
- [ ] Position can close manually
- [ ] Statistics update (trades increment)
- [ ] Exports create JSON files
- [ ] No crashes or errors in logs

---

## 📊 Performance Expectations

| Metric | Expected | Range |
|--------|----------|-------|
| Order execution time | < 1s | 0.1-2s |
| Position tracking latency | < 100ms | <500ms |
| Statistics API response | < 50ms | <200ms |
| Export file creation | < 500ms | <2s |
| Signal generation frequency | 1/minute | 0.5-2/min |
| Execution success rate (demo) | 100% | 95-100% |

---

## 🎉 Next Steps After Testing

1. **Fine-tune risk parameters** in ml/config.py
   - Adjust `risk_per_trade_percent` (currently 2%)
   - Adjust `max_position_size_percent` (currently 5%)
   - Adjust `max_trades_per_day` (currently 20)

2. **Monitor P&L** over several hours
   - Export statistics periodically
   - Track win rate (should be 55-60%+ with Phase G weights)

3. **Optimize pair selection** in selected_signal_pairs.json
   - Test with only high-confidence pairs
   - Deactivate volatile pairs during market hours

4. **Set up logging** for long-term monitoring
   - Export daily trade logs
   - Track performance metrics

5. **Go live** (optional)
   - Change `prefer_demo_mode = False` in ml/config.py
   - Set lower `risk_per_trade_percent` (start with 0.5%)
   - Monitor first day carefully

---

**Ready to test? Start with: `python engine.py`** 🚀

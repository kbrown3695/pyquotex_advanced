# Quick Answers: Automation Initialization

## ❓ Q1: How is auto trading initialized in the engine and frontend?

### Engine (Python - `engine.py`)

**On Startup**:
1. **Import Phase H components**:
   ```python
   from ml.trading.account_constraint_tracker import AccountConstraintTracker
   from ml.serving.websocket_health_monitor import WebSocketHealthMonitor
   from ml.trading.automated_trader import AutomatedTrader
   from ml.serving.auto_trading_manager import AutoTradingManager
   ```

2. **Initialize 3 core components** (lines ~240-267):
   ```python
   CONSTRAINT_TRACKER = AccountConstraintTracker()
   HEALTH_MONITOR = WebSocketHealthMonitor()
   AUTOMATED_TRADER = AutomatedTrader(
       constraint_tracker=CONSTRAINT_TRACKER,
       health_monitor=HEALTH_MONITOR,
       trade_executor=None
   )
   ```

3. **Initialize AutoTradingManager** (new):
   ```python
   AUTO_TRADING_MANAGER = AutoTradingManager(
       constraint_tracker=CONSTRAINT_TRACKER,
       health_monitor=HEALTH_MONITOR,
       automated_trader=AUTOMATED_TRADER,
       pairs_file="selected_signal_pairs.json"  # ← Loads your pairs!
   )
   ```
   This automatically:
   - Reads `selected_signal_pairs.json`
   - Loads 7 pairs (USD/INR, CHF/JPY, etc.)
   - Registers pairs with health monitor
   - Creates pair status tracking

4. **Hard Ping Loop** (every 60 seconds, line ~653):
   ```python
   async def hard_ping_loop():
       await asyncio.sleep(HARD_PING_INTERVAL)  # 60 seconds
       if CLIENT and CLIENT.api:
           balances = await get_account_balances()
           update_tick_time()
           
           # NEW: Update constraints from WebSocket
           await update_constraints()
           
           # NEW: Log constraint status
           if CONSTRAINT_TRACKER:
               status = CONSTRAINT_TRACKER.get_status()
               if status != 'OK':
                   log(f"⚠️ Constraint Alert: ...")
   ```

### Frontend (JavaScript - via `eel.js`)

**When Page Loads**:
```javascript
// 1. Get selected pairs
eel.get_selected_pairs()(function(pairs) {
    console.log("Pairs:", pairs);  // ["USD/INR (OTC)", "CHF/JPY", ...]
});

// 2. Get automation status
eel.get_automation_status()(function(status) {
    console.log("Status:", status);  // {enabled, pairs, signals, trades, ...}
});

// 3. Start polling for balance updates (every 10 seconds)
setInterval(() => {
    eel.get_real_time_balance()(function(balance) {
        console.log("Balance:", balance);  // {real_balance, demo_balance, ...}
        updateBalanceDisplay(balance);
    });
}, 10000);
```

**User Clicks "Enable Automation"**:
```javascript
document.getElementById('enable-btn').onclick = async function() {
    const result = await eel.enable_automation()();
    if (result.success) {
        console.log("✅ Automation enabled for 7 pairs!");
        document.getElementById('status').textContent = "ENABLED";
    }
};
```

---

## ❓ Q2: How do we use assets from `selected_signal_pairs.json` for automated trading?

### Current Setup

**File Contents** (`selected_signal_pairs.json`):
```json
[
  "USD/INR (OTC)",
  "CHF/JPY (OTC)",
  "CAD/JPY (OTC)",
  "USD/PKR (OTC)",
  "CAD/CHF (OTC)",
  "CHF/JPY",
  "NZD/JPY (OTC)"
]
```

### How It Works

**Step 1: On Engine Startup**
```python
AUTO_TRADING_MANAGER = AutoTradingManager(
    pairs_file="selected_signal_pairs.json"
)
# ↓
# Automatically:
# 1. Loads JSON file
# 2. Reads 7 pairs
# 3. Registers with HEALTH_MONITOR
# 4. Creates pair_status tracking
```

**Step 2: When ML Generates a Signal**
```
ML_MODEL → "Buy CHF/JPY @ 78% confidence"
    ↓
AutoTradingManager.process_signal(signal)
    ↓
Check 1: is_enabled? (YES/NO)
    ↓
Check 2: "CHF/JPY" in selected_pairs? (YES/NO)
    ↓
If YES: Update pair_status["CHF/JPY"] and send to trader
If NO:  Reject "Asset not in selected pairs"
```

**Step 3: Only Selected Pairs Execute Trades**
```python
def should_accept_signal_for_asset(self, asset: str) -> bool:
    """Only accept if asset is in selected_pairs and automation enabled"""
    return self.is_enabled and asset in self.selected_pairs
```

### To Change Pairs

Simply edit `selected_signal_pairs.json`:
```json
[
  "EURUSD",
  "GBPUSD",
  "NEW_PAIR_HERE"
]
```

Then restart engine.py - it will automatically load the new pairs!

---

## ❓ Q3: Will the balance be updating in real-time?

### YES ✅ - Updated Every 60 Seconds

**How It Works**:

```
Hard Ping Loop (every 60 seconds)
    ↓
Fetch account_balance from WebSocket:
    - demoBalance: $Y
    - liveBalance: $X
    - dayBalance: $W
    - dayLimit: $Z
    ↓
ConstraintTracker.update_from_websocket()
    ↓
Store in: CONSTRAINT_TRACKER.current_constraints
    ↓
Frontend calls: get_real_time_balance()
    ↓
Returns latest values (updated 60s ago)
    ↓
Display in UI
```

### Real-Time Balance Display

**Console Output** (every 60 seconds):
```
💓 Hard ping OK — Real: $0.00 Demo: $10000.00 (PRACTICE)
✅ Constraints OK: dayBalance=$3000.00, dayLimit=$5000.00
🟢 Connection health: EXCELLENT (latency: 45ms, stale: 0)
```

**Frontend Display** (polls every 10 seconds):
```javascript
// Calls get_real_time_balance() every 10 seconds
// Returns cached values updated every 60 seconds
{
    'real_balance': 0.0,
    'demo_balance': 9800.0,      // ← Updated when trades execute
    'day_limit': 5000.0,
    'day_balance': 2800.0,       // ← Updated in real-time
    'minimum_amount': 1.0,
    'account_mode': 'PRACTICE',
    'timestamp': 1726956960.123  // ← Shows when last updated
}
```

### Real-Time Balance Updates in Action

**Timeline Example**:

```
T=0:00 - User enables automation
T=0:30 - ML signal generated
         → Signal: BUY CHF/JPY $200
         → Constraint check: dayBalance=$3000 ✅
         → Execute: TRADE PLACED
         ↓
T=1:00 - Hard Ping (60s cycle)
         → Fetch account_balance from WebSocket
         → NEW: demoBalance = $9,800 (was $10,000)
         → NEW: dayBalance = $2,800 (was $3,000)
         ↓
T=1:05 - Frontend calls get_real_time_balance()
         → Returns: demo_balance = $9,800 ✅
         → Display updates in real-time
         ↓
T=2:00 - Another hard ping
         → Updates balance again (if more trades executed)
```

### Guaranteed Real-Time Updates

✅ **Every 60 seconds** - Hard ping fetches latest from WebSocket  
✅ **Account constraints** - Checked every hard ping  
✅ **dayLimit/dayBalance** - From WebSocket (server source of truth)  
✅ **Frontend polling** - Every 10 seconds shows latest cached values  
✅ **Lag < 70 seconds** - From trade execution to display update  

### API For Real-Time Balance

```python
@eel.expose
def get_real_time_balance():
    """Gets latest balance from ConstraintTracker (updated every 60s)"""
    global CONSTRAINT_TRACKER
    
    if CONSTRAINT_TRACKER and CONSTRAINT_TRACKER.current_constraints:
        c = CONSTRAINT_TRACKER.current_constraints
        return {
            'real_balance': c.live_balance,
            'demo_balance': c.demo_balance,
            'day_balance': c.day_balance,          # ← Real-time
            'day_limit': c.day_limit,
            'minimum_amount': c.minimum_amount,
            'account_mode': c.account_mode,
            'timestamp': c.timestamp               # ← When fetched
        }
```

---

## 🎯 Summary

| Question | Answer |
|----------|--------|
| **Initialization** | AutoTradingManager auto-loads `selected_signal_pairs.json` at startup |
| **Selected Pairs** | Only signals for pairs in JSON file are processed for trading |
| **Real-Time Balance** | Updated every 60s from WebSocket, polled by frontend every 10s |

### Next Step: Enable Automation

1. Make sure `enable_automated_trading = True` in `ml/config.py`
2. Restart `python engine.py`
3. Click "Enable Automation" in frontend
4. Watch balance update in real-time every 60 seconds

**✅ Ready to automate selected pairs with live balance updates!**

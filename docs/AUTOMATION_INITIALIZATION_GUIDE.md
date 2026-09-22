# Automated Trading Initialization Guide
**Phase H: Complete Setup for Selected Pairs with Real-time Balance Updates**

---

## 🏗️ Architecture Overview

The automated trading system works in **3 layers**:

```
┌─────────────────────────────────────────────┐
│ Frontend (JavaScript)                        │
│ - Enable/Disable buttons                    │
│ - Real-time balance display                 │
│ - Pair status monitor                       │
└─────────────────────────────────────────────┘
              ↓↑ (eel.js calls)
┌─────────────────────────────────────────────┐
│ Engine.py (Main Process)                     │
│ - AutoTradingManager (orchestrator)         │
│ - ConstraintTracker (validation)            │
│ - HealthMonitor (data quality)              │
│ - AutomatedTrader (execution)               │
└─────────────────────────────────────────────┘
              ↓↑ (real-time data)
┌─────────────────────────────────────────────┐
│ WebSocket (Quotex API)                       │
│ - account_balance (dayLimit, dayBalance)    │
│ - Candle data (OHLCV)                       │
│ - Profile data                              │
└─────────────────────────────────────────────┘
```

---

## 🚀 Initialization Flow

### Step 1: Engine Startup (Python)

When `python engine.py` starts:

```
1. Load Configuration (ml/config.py)
   ↓
2. Initialize Quotex Client
   ↓
3. Create 3 Core Components:
   ├─ AccountConstraintTracker (tracks dayLimit/dayBalance)
   ├─ WebSocketHealthMonitor (tracks latency, staleness)
   └─ AutomatedTrader (executes trades)
   ↓
4. Create AutoTradingManager
   ├─ Loads selected_signal_pairs.json
   ├─ Registers pairs with health monitor
   └─ Ready for automation
   ↓
5. Start Hard Ping Loop (every 60s)
   ├─ Fetch account_balance from WebSocket
   ├─ Update ConstraintTracker
   ├─ Log any violations
   └─ Update frontend via UI_QUEUE
```

**Console Output**:
```
✅ AccountConstraintTracker initialized
✅ WebSocketHealthMonitor initialized
✅ AutomatedTrader initialized (demo mode enabled)
✅ AutoTradingManager initialized with selected pairs
✅ Loaded 7 trading pairs:
   - USD/INR (OTC)
   - CHF/JPY (OTC)
   - CAD/JPY (OTC)
   - USD/PKR (OTC)
   - CAD/CHF (OTC)
   - CHF/JPY
   - NZD/JPY (OTC)
```

---

### Step 2: Frontend Initialization (JavaScript)

When frontend loads:

```javascript
1. Connect to Engine (eel.js)
   ↓
2. Call get_selected_pairs()
   ├─ Retrieves list from AutoTradingManager
   └─ Display in UI
   ↓
3. Call get_automation_status()
   ├─ Get enabled/disabled status
   ├─ Get real-time balances
   └─ Display in dashboard
   ↓
4. Poll get_real_time_balance() every 5-10s
   └─ Shows live balance updates
```

---

## 📊 Real-Time Balance Updates

### How Balances Update

**Every 60 seconds** (hard ping interval):

```
WebSocket (Quotex)
  ↓
  Fetches: account_balance dict
    - liveBalance: $X
    - demoBalance: $Y
    - dayLimit: $Z
    - dayBalance: $W
  ↓
ConstraintTracker.update_from_websocket()
  ↓
  Stores in: CONSTRAINT_TRACKER.current_constraints
  ↓
Frontend calls: get_real_time_balance()
  ↓
  Returns latest cached values
  ↓
Display updated in UI
```

### API Call Flow (Frontend → Backend)

```javascript
// Frontend code (in web_app.html)
async function updateBalance() {
    const balance = await eel.get_real_time_balance()();
    console.log("Real-time Balance:", balance);
    // Output:
    // {
    //   'real_balance': 0.0,
    //   'demo_balance': 10000.0,
    //   'day_limit': 5000.0,
    //   'day_balance': 3000.0,
    //   'minimum_amount': 1.0,
    //   'account_mode': 'PRACTICE',
    //   'timestamp': 1726956960.123
    // }
    
    // Update UI
    document.getElementById('demo-balance').innerText = balance.demo_balance.toFixed(2);
    document.getElementById('day-balance').innerText = balance.day_balance.toFixed(2);
}

// Poll every 10 seconds
setInterval(updateBalance, 10000);
```

### Backend (Python)

```python
@eel.expose
def get_real_time_balance():
    """Returns latest balance from constraint tracker (updated every 60s)"""
    global CONSTRAINT_TRACKER
    
    if CONSTRAINT_TRACKER and CONSTRAINT_TRACKER.current_constraints:
        c = CONSTRAINT_TRACKER.current_constraints
        return {
            'real_balance': c.live_balance,
            'demo_balance': c.demo_balance,
            'day_balance': c.day_balance,
            'day_limit': c.day_limit,
            'timestamp': c.timestamp
        }
```

---

## ⚙️ How Selected Pairs Are Used

### File: `selected_signal_pairs.json`

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

### Pair Registration Flow

```
AutoTradingManager.__init__()
  ↓
1. load_selected_pairs()
   └─ Reads JSON file → 7 pairs loaded
  ↓
2. When enable_automation() called:
   ├─ register_pairs_with_health_monitor()
   │  └─ For each pair:
   │     └─ HEALTH_MONITOR.register_subscription("CHF/JPY", 60)
   │        └─ Now tracks: latency, staleness, candle updates
   ├─ Sets: is_enabled = True
   └─ Log: "🚀 Automated trading ENABLED for 7 pairs"
```

### Signal Processing for Selected Pairs

```
ML Model generates signal → asset = "CHF/JPY"
  ↓
AutoTradingManager.process_signal(signal)
  ↓
1. Check: is_enabled? (True/False)
2. Check: asset in selected_pairs? ("CHF/JPY" in list?)
3. If YES:
   ├─ Update pair_status["CHF/JPY"].last_signal_confidence
   ├─ Increment pair_status["CHF/JPY"].signals_today
   └─ Send to AutomatedTrader for 7-stage validation
4. If NO:
   └─ Reject: "Asset not in selected pairs"
```

---

## 🎮 Frontend Controls (API)

### Enable Automation

```javascript
// Button click handler
async function enableAutomation() {
    const result = await eel.enable_automation()();
    if (result.success) {
        console.log("✅ Automation enabled!");
        updateAutomationUI(true);
    } else {
        console.error("❌ Error:", result.error);
    }
}
```

**Backend Response**:
```python
{
    "success": True,
    "message": "Automation enabled"
}
```

### Get Selected Pairs

```javascript
async function getSelectedPairs() {
    const pairs = await eel.get_selected_pairs()();
    console.log("Selected Pairs:", pairs);
    // ["USD/INR (OTC)", "CHF/JPY (OTC)", ...]
    
    // Display in dropdown
    pairs.forEach(pair => {
        const option = document.createElement('option');
        option.value = pair;
        option.textContent = pair;
        document.getElementById('pair-selector').appendChild(option);
    });
}
```

### Get Automation Status

```javascript
async function getAutomationStatus() {
    const status = await eel.get_automation_status()();
    // Returns:
    // {
    //   "enabled": true,
    //   "uptime_minutes": 5.2,
    //   "pairs": {
    //     "selected": 7,
    //     "active": 7,
    //     "list": ["USD/INR (OTC)", ...]
    //   },
    //   "signals": {
    //     "today": 12,
    //     "by_pair": {
    //       "CHF/JPY": 3,
    //       "USD/INR (OTC)": 2,
    //       ...
    //     }
    //   },
    //   "trades": {
    //     "today": 2,
    //     "by_pair": {...}
    //   },
    //   "constraints": {...},
    //   "health": {...},
    //   "balances": {...},
    //   "trading_mode": "DEMO"
    // }
}
```

### Monitor Individual Pairs

```javascript
async function getPairStatuses() {
    const statuses = await eel.get_pair_statuses()();
    // Returns:
    // {
    //   "CHF/JPY": {
    //     "display_name": "CHF/JPY",
    //     "internal_name": "CHFJPY",
    //     "is_active": true,
    //     "last_signal": {
    //       "time": 1726956945.123,
    //       "confidence": 0.78
    //     },
    //     "signals_today": 3,
    //     "trades_today": 1
    //   },
    //   ...
    // }
    
    // Display in table
    Object.entries(statuses).forEach(([pair, status]) => {
        console.log(`${pair}: ${status.signals_today} signals, ${status.trades_today} trades`);
    });
}
```

---

## 🔄 Real-Time Update Cycle

### Every 60 Seconds (Hard Ping)

```
HARD_PING_LOOP
  ↓
1. Fetch account_balance from WebSocket
   └─ Get: demoBalance, liveBalance, dayLimit, dayBalance
   ↓
2. Call update_constraints()
   ├─ ConstraintTracker.update_from_websocket(account_balance)
   ├─ If dayBalance < minimum → SET halt_reason
   └─ Store in: CONSTRAINT_TRACKER.current_constraints
   ↓
3. Log constraint status
   ├─ If OK: "✅ Constraints OK"
   └─ If HALT: "🚫 TRADING HALT: [reason]"
   ↓
4. Frontend calls get_real_time_balance()
   └─ Gets latest from CONSTRAINT_TRACKER.current_constraints
      (timestamp will show it was just updated)
```

### Every Signal Generated

```
ML_MODEL → Generate Signal (asset="CHF/JPY", confidence=0.75)
  ↓
AutoTradingManager.process_signal(signal)
  ↓
1. Check if enabled and asset in selected pairs
2. Update pair_status["CHF/JPY"]:
   - last_signal_confidence = 0.75
   - last_signal_time = now()
   - signals_today += 1
3. Call AutomatedTrader.process_signal()
   ├─ 7-stage validation
   ├─ Check constraints (from CONSTRAINT_TRACKER)
   ├─ Check data quality (from HEALTH_MONITOR)
   └─ Execute if all pass
```

---

## 📋 Complete Example Flow

### Scenario: User Enables Automation with Selected Pairs

**Timeline**:

```
T=0:00
------
1. User clicks "Enable Automation" button
2. Frontend calls: eel.enable_automation()()

T=0:01
------
3. Backend:
   - AUTO_TRADING_MANAGER.enable_automation()
   - Registers 7 pairs with HEALTH_MONITOR
   - Sets is_enabled = True
   - Logs: "🚀 AUTOMATION ENABLED for 7 pairs"
4. Frontend receives: {"success": True}

T=0:30
------
5. ML Signal generated for "CHF/JPY"
   - Confidence: 0.78
6. AutoTradingManager receives signal
   - Check: enabled? YES
   - Check: "CHF/JPY" in pairs? YES
   - Update pair_status["CHF/JPY"].signals_today = 1
7. AutomatedTrader validates:
   - Confidence check: 0.78 >= 0.5 ✅
   - Constraint check: dayBalance=$3000, minimum=$1 ✅
   - Health check: EXCELLENT connection ✅
   - Position size: $10,000 * 2% = $200
8. TRADE EXECUTED: BUY CHF/JPY $200
   - pair_status["CHF/JPY"].trades_today = 1

T=1:00 (Hard Ping)
------
9. Fetch account_balance from WebSocket:
   - demoBalance: $9,800 (after $200 trade)
   - dayBalance: $2,800 (after $200 trade)
10. Update CONSTRAINT_TRACKER.current_constraints
11. Frontend calls get_real_time_balance()
    - Returns: demo_balance=$9,800, day_balance=$2,800
12. UI updates to show new balances LIVE

T=1:30
------
13. Another signal for "USD/INR (OTC)"
    - Process same flow...
```

---

## ✅ Checklist: Automation Setup

- [ ] **config.py**: `enable_automated_trading = True`
- [ ] **config.py**: `prefer_demo_mode = True`
- [ ] **selected_signal_pairs.json**: Contains your pairs
- [ ] **engine.py**: Running (`python engine.py`)
- [ ] **Frontend**: Loaded and connected
- [ ] **Console**: Shows "✅ AutoTradingManager initialized"
- [ ] **Frontend**: Shows selected pairs in UI
- [ ] **Frontend**: Balance updates every 60s
- [ ] **Enable button**: Click to activate automation
- [ ] **Monitor**: Watch constraints, health, and trades

---

## 🔧 Configuration Reference

### ml/config.py Settings

```python
# Enable automation
enable_automated_trading = True

# Demo/Live mode
prefer_demo_mode = True  # Use $10k demo balance

# Risk management
risk_per_trade_percent = 2.0      # 2% per trade
max_position_size_percent = 10.0  # Max 10%

# Frequency limits
max_trades_per_day = 100
min_time_between_trades_sec = 5.0  # 5 second minimum

# Constraints
enable_constraint_tracking = True
constraint_violation_halt = True

# Health monitoring
enable_health_monitoring = True
latency_warning_ms = 500.0
latency_critical_ms = 1000.0
```

---

## 🚨 Troubleshooting

### "Balance not updating"
- Check: Hard ping running (60s cycle)
- Check console: Should show "💓 Hard ping OK" every 60s
- Check: WebSocket connected
- Solution: Restart engine.py

### "Automation won't enable"
- Check: `enable_automated_trading = True` in config.py
- Check: selected_signal_pairs.json exists
- Check console: "✅ AutoTradingManager initialized"
- Solution: Restart engine.py after config change

### "Selected pairs not showing in UI"
- Check: Frontend called `get_selected_pairs()`
- Check: Pairs JSON file exists and is valid JSON
- Check console: Python shows "Loaded X trading pairs"
- Solution: Reload frontend page

### "Trades not executing"
- Check: Automation enabled (UI shows enabled)
- Check: Signal confidence >= 50%
- Check: Constraints OK (not halted)
- Check: Health status >= GOOD
- Check console: Look for ✅ or ❌ symbols

---

## 📞 API Reference

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `enable_automation()` | Enable auto-trading | `{"success": bool}` |
| `disable_automation()` | Disable auto-trading | `{"success": bool}` |
| `get_selected_pairs()` | List of pairs for trading | `["pair1", "pair2", ...]` |
| `get_automation_status()` | Full automation state | Complex dict (see above) |
| `get_pair_statuses()` | Per-pair metrics | Dict of pair statuses |
| `get_real_time_balance()` | Current balances | `{real, demo, dayLimit, dayBalance, ...}` |

---

**Automated Trading Setup Complete!**  
Selected pairs are loaded, real-time balance updates are active, and automation is ready to enable.

*Start with demo mode, validate for 24h, then go live!* 🚀

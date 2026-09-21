# Phase H Quick Start Guide
**Automated Trading with Safety Constraints**

---

## 🚀 Enable Automated Trading (Demo Mode)

### Step 1: Update Config
Edit `ml/config.py`:

```python
# Change this line:
enable_automated_trading: bool = False

# To this:
enable_automated_trading: bool = True
```

### Step 2: Verify Demo Mode
Ensure `ml/config.py` has:

```python
# Use $10k demo balance for testing
prefer_demo_mode: bool = True
demo_balance_target: float = 10000.0

# Risk settings (start conservative)
risk_per_trade_percent: float = 2.0       # 2% per trade
max_position_size_percent: float = 10.0   # Max 10%
max_trades_per_day: int = 100
min_time_between_trades_sec: float = 5.0
```

### Step 3: Start Engine
```bash
cd D:\QuotexChart
python engine.py
```

Expected output:
```
✅ AccountConstraintTracker initialized
✅ WebSocketHealthMonitor initialized
✅ AutomatedTrader initialized (demo mode enabled)
```

### Step 4: Monitor Console Logs

The system will output:

```
💓 Hard ping OK — Real: $0.00 Demo: $10000.00 (PRACTICE)
✅ Constraints OK: dayBalance=$3000.00, dayLimit=$5000.00
🟢 WebSocket Health: EXCELLENT (latency: 45ms, stale: 0)
```

---

## 📊 Check Trading Status

### Frontend Dashboard
The UI will show:
- 💰 Current balance (demo)
- 🟢 Health status
- ⚠️ Any constraint warnings
- 📈 Trades executed today

### Console Status
Every hard ping (60 seconds), you'll see:
```
💰 Balances (cached): Real=$0.00 Demo=$10000.00 Mode=PRACTICE
✅ Constraint status: OK
🟢 Connection health: EXCELLENT
```

### Get Full Status
```python
# From Python:
from engine import AUTOMATED_TRADER
status = AUTOMATED_TRADER.get_trading_status()
print(status)
```

**Output**:
```python
{
  'is_running': True,
  'mode': 'DEMO',
  'trades': {
    'today': 0,
    'total': 0,
    'rejected': 0,
    'max_per_day': 100
  },
  'constraints': {
    'constraint_status': 'OK',
    'day_balance': 3000.00,
    'day_limit': 5000.00
  },
  'health': {
    'connection': 'EXCELLENT',
    'latency_ms': 45,
    'stale_assets': 0,
    'uptime_percent': 100.0
  }
}
```

---

## ⚡ What Happens When Trading

### Good Conditions ✅
```
Signal: EURUSD BUY @ 75% confidence
  ↓
[✅ Auto-trading enabled]
[✅ Within trading hours (0-23)]
[✅ 10 seconds since last trade (>5s minimum)]
[✅ 1 trade today (< 100 max)]
[✅ Confidence 75% >= 50% minimum]
[✅ Constraints OK: dayBalance=$3000 > $1.00]
[✅ Data quality EXCELLENT: latency=45ms]
  ↓
Position Size = $10,000 * 2% = $200
  ↓
TRADE EXECUTED: EURUSD BUY $200 @ 75% confidence
```

### Blocked: Insufficient Balance ⛔
```
Signal: EURUSD BUY @ 60% confidence
  ↓
[✅ Auto-trading enabled]
...
[❌ Constraints HALT: dayBalance=$0.50 < minimum $1.00]
  ↓
TRADE REJECTED: Insufficient balance for minimum trade
```

### Blocked: Poor Data Quality ⛔
```
Signal: EURUSD BUY @ 65% confidence
  ↓
[✅ Auto-trading enabled]
...
[✅ Constraints OK]
[❌ Data quality DEGRADED: latency=1200ms, stale=2 assets]
  ↓
TRADE REJECTED: Data quality below required GOOD level
```

### Blocked: Low Confidence ⛔
```
Signal: EURUSD BUY @ 40% confidence
  ↓
[✅ Auto-trading enabled]
...
[❌ Low confidence: 40% < 50% minimum]
  ↓
TRADE REJECTED: Confidence below threshold
```

---

## 🛑 Stop Trading Anytime

### Option 1: Disable in Config
```python
# ml/config.py
enable_automated_trading: bool = False
```
Requires restart to take effect.

### Option 2: From Python
```python
from engine import AUTOMATED_TRADER
await AUTOMATED_TRADER.stop()
```

### Option 3: System Will Auto-Stop If:
- 🟢 Connection turns CRITICAL (no data)
- 🔴 Account constraints HALT (dayBalance=0)
- 🛑 Daily trade limit reached (100 trades)

---

## 📈 Demo Mode Strategy

**Recommended for first 24 hours**:

```python
# Conservative settings for testing
risk_per_trade_percent: float = 1.0        # Start with 1%
max_trades_per_day: int = 20               # Limit trades
min_time_between_trades_sec: float = 10.0  # Slower pace

# After 24h validation, increase to:
risk_per_trade_percent: float = 2.0
max_trades_per_day: int = 100
min_time_between_trades_sec: float = 5.0
```

---

## 📊 Monitoring Checklist

Every hour, verify:

- [ ] **Balances updating**: `demo_balance` should match Quotex platform
- [ ] **No constraint violations**: Check console for ⚠️ warnings
- [ ] **Health status GREEN**: Latency < 500ms, no stale assets
- [ ] **Trades recorded**: Count in `AUTOMATED_TRADER.trades_executed`
- [ ] **No errors**: Check for ❌ symbols in console

---

## 🔍 Troubleshooting

### "Automated trading disabled in config"
**Solution**: Set `enable_automated_trading = True` in `ml/config.py`

### "Insufficient balance for minimum trade"
**Solution**: Check `dayBalance` in WebSocket data, or set `demo_balance_target` higher

### "Data quality DEGRADED - latency 1500ms"
**Solution**: Check network connection, may be temporary - system will retry

### "TRADING HALT: Daily limit exhausted"
**Solution**: System prevents over-trading. Check `dayLimit` on Quotex platform or configure higher limit in settings

### "Consecutive stale events - consider reconnecting"
**Solution**: WebSocket connection may have issues. Engine will auto-reconnect (60s cycle)

---

## 📝 Compliance & Logging

### Trade Log
```bash
# Export trades from Python:
AUTOMATED_TRADER.export_trade_log('logs/trades_2026-09-21.json')
```

### Constraint History
```bash
# Check constraint violations:
CONSTRAINT_TRACKER.export_history('logs/constraints_2026-09-21.json')
```

### Health Log
```bash
# Monitor connection quality:
HEALTH_MONITOR.export_health_log('logs/websocket_2026-09-21.json')
```

All files include:
- Timestamp of each event
- Reason for accept/reject
- Final account state
- System alerts

---

## 🚀 Ready for Production?

### Demo Validation Checklist
- [ ] ✅ 24+ hours of automated trading
- [ ] ✅ Zero constraint violations
- [ ] ✅ WebSocket health consistently GOOD/EXCELLENT
- [ ] ✅ Win rate > 55%
- [ ] ✅ No rejected trades due to constraints/data quality
- [ ] ✅ Compliance logs complete

### Switch to Live (if validated)
```python
# ml/config.py
prefer_demo_mode: bool = False  # Use real money
live_account_min_balance: float = 500.0  # Auto-fallback to demo
```

⚠️ **WARNING**: Live trading uses real money. Only enable after demo validation.

---

## 📚 Configuration Reference

### Key Settings
```python
# Enable automation
enable_automated_trading = True

# Demo/Live selection
prefer_demo_mode = True           # True = use demo
live_account_min_balance = 100.0  # Auto-switch if live < $100

# Risk management
risk_per_trade_percent = 2.0      # Risk 2% per trade
max_position_size_percent = 10.0  # Max position 10%

# Trade frequency
max_trades_per_day = 100
min_time_between_trades_sec = 5.0

# Trading hours (24-hour format)
automation_start_hour = 0         # Start at midnight
automation_end_hour = 23          # End at 11pm

# Constraints
enable_constraint_tracking = True
constraint_violation_halt = True  # Stop on violation

# Health monitoring
enable_health_monitoring = True
latency_warning_ms = 500.0
latency_critical_ms = 1000.0

# Logging
enable_compliance_logging = True
export_constraint_history = True
export_health_logs = True
```

---

## 💡 Tips

1. **Start Conservative**: Use 1% risk for first 24h, increase gradually
2. **Monitor Constraints**: Watch dayBalance updates from WebSocket
3. **Watch Health**: Green (EXCELLENT) = good, Yellow (GOOD) = okay, Red (CRITICAL) = stop
4. **Log Everything**: Export logs daily for compliance audit
5. **Test First**: Validate on demo for 24h+ before live trading

---

## 🆘 Support

If issues occur:

1. Check console logs for ❌ errors
2. Review `PHASE_H_IMPLEMENTATION.md` for detailed docs
3. Run tests: `python test_phase_h.py`
4. Export logs: 
   ```bash
   AUTOMATED_TRADER.export_trade_log('debug.json')
   CONSTRAINT_TRACKER.export_history('constraints_debug.json')
   HEALTH_MONITOR.export_health_log('health_debug.json')
   ```

---

**Phase H Ready - Start Demo Trading Today! 🚀**

*Test the automation, validate the logic, then go live with confidence.*

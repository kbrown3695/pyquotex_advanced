# Phase H: Order Execution Engine
**Real-time Trade Execution via Quotex API**

---

## 📋 Overview

The Order Execution Engine enables **fully automated trading** with:
- ✅ **Live order placement** via Quotex API
- ✅ **Position tracking** (open/closed)
- ✅ **P&L calculation** per trade
- ✅ **Execution statistics** (success rate, volume, etc.)
- ✅ **Compliance logging** (all trades recorded)

---

## 🏗️ Architecture

### Components

#### 1. **OrderExecutor** (`ml/trading/order_executor.py`)
Places trades via Quotex API.

```python
# Async methods
await order_executor.execute_buy_order(
    asset="CHFJPY",
    amount=100.0,
    expiration_time=300,  # 5 min expiration
    signal_confidence=0.78
)

await order_executor.execute_sell_order(
    asset="CHFJPY",
    amount=100.0,
    signal_confidence=0.78
)
```

**Returns**: `OrderResult` with:
- `order_id`: Broker order ID
- `status`: EXECUTED / FAILED / PENDING / CANCELLED
- `execution_price`: Entry price
- `message`: Error details if failed

#### 2. **PositionTracker** (`ml/trading/position_tracker.py`)
Tracks open positions and closed trades.

```python
# Open a position
position = position_tracker.open_position(
    position_id="CHFJPY_1726953600000",
    asset="CHFJPY",
    side="BUY",
    amount=100.0,
    entry_price=1.0178
)

# Close a position
closed = position_tracker.close_position(
    position_id="CHFJPY_1726953600000",
    asset="CHFJPY",
    exit_price=1.0195,
    exit_reason="profit_target_hit"
)
# → Returns Position with profit_loss_pct and profit_loss_usd calculated
```

#### 3. **AutomatedTrader** (Updated)
Orchestrates signal → execution pipeline.

```
ML Signal (80% confidence, BUY CHFJPY)
    ↓
AutoTradingManager.process_signal()
    ↓ (checks: automation enabled, pair active)
AutomatedTrader.process_signal()
    ↓ (7-stage validation)
    1. Automated trading enabled? ✓
    2. Within trading hours? ✓
    3. Time since last trade? ✓
    4. Max trades per day? ✓
    5. Confidence >= 50%? ✓
    6. Account constraints OK? ✓
    7. WebSocket health good? ✓
AutomatedTrader._execute_trade()
    ↓
OrderExecutor.execute_buy_order()
    ↓ (async, 10s timeout)
Quotex API: client.buy("CHFJPY", 300, 100.0)
    ↓
PositionTracker.open_position()
    ↓
ExecutedTrade record created
```

---

## 🎮 Frontend API

### Monitoring (Read-Only)

#### **get_open_positions()**
```javascript
const positions = await eel.get_open_positions()();
// Returns:
{
    "CHF/JPY": {
        "open_positions": 1,
        "total_exposure_usd": 100.0,
        "positions": [
            {
                "id": "CHFJPY_1726953600000",
                "side": "BUY",
                "amount": 100.0,
                "entry_price": 1.0178,
                "opened_at": "2026-09-21T14:30:00.000Z"
            }
        ]
    }
}
```

#### **get_recent_trades(limit=20)**
```javascript
const trades = await eel.get_recent_trades(10)();
// Returns:
[
    {
        "position_id": "CHFJPY_1726953600000",
        "asset": "CHF/JPY",
        "side": "BUY",
        "amount": 100.0,
        "entry_price": 1.0178,
        "exit_price": 1.0195,
        "pnl_pct": 0.167,
        "pnl_usd": 0.167,
        "status": "CLOSED_WIN",
        "exit_reason": "profit_target_hit",
        "duration_sec": 45,
        "opened_at": "2026-09-21T14:30:00.000Z",
        "closed_at": "2026-09-21T14:30:45.000Z"
    }
]
```

#### **get_position_statistics()**
```javascript
const stats = await eel.get_position_statistics()();
// Returns:
{
    "open_positions": 1,
    "total_trades": 25,
    "winning_trades": 16,
    "losing_trades": 9,
    "win_rate_percent": 64.0,
    "total_profit_loss_usd": 125.45,
    "avg_profit_loss_per_trade": 5.02
}
```

#### **get_order_execution_stats()**
```javascript
const exec = await eel.get_order_execution_stats()();
// Returns:
{
    "orders_placed": 25,
    "orders_executed": 25,
    "orders_failed": 0,
    "execution_rate_percent": 100.0,
    "total_traded_usd": 2500.0,
    "avg_order_size": 100.0
}
```

#### **get_recent_orders(limit=10)**
```javascript
const orders = await eel.get_recent_orders(10)();
// Returns:
[
    {
        "timestamp": 1726953645.123,
        "asset": "CHF/JPY",
        "side": "BUY",
        "amount": 100.0,
        "status": "EXECUTED",
        "order_id": "ord_12345",
        "message": "Order executed successfully"
    }
]
```

### Control (Read-Write)

#### **close_position(position_id, asset, exit_price, exit_reason)**
Manually close a trading position.

```javascript
const result = await eel.close_position(
    "CHFJPY_1726953600000",
    "CHF/JPY",
    1.0200,
    "manual_close"
)();

if (result.success) {
    console.log(`✅ Position closed: P&L ${result.pnl_usd.toFixed(2)} USD`);
    console.log(`   Win Rate: ${result.status}`);
} else {
    console.error(`❌ ${result.message}`);
}
```

**Returns**:
```javascript
{
    "success": true,
    "message": "Position closed: manual_close",
    "pnl_pct": 0.217,
    "pnl_usd": 0.217,
    "status": "CLOSED_WIN"
}
```

### Export (Compliance)

#### **export_position_history(filepath)**
Export all positions to JSON file.

```javascript
const result = await eel.export_position_history("trades.json")();
// Creates: trades.json with {statistics, open_positions, recent_trades}
```

#### **export_order_history(filepath)**
Export all orders to JSON file.

```javascript
const result = await eel.export_order_history("orders.json")();
// Creates: orders.json with {statistics, orders}
```

---

## 🔌 Backend Integration

### Python: Direct Access

```python
# Get open positions
positions = POSITION_TRACKER.get_open_positions()
positions_by_asset = POSITION_TRACKER.get_position_summary_by_asset()

# Get statistics
stats = POSITION_TRACKER.get_statistics()
print(f"Win rate: {stats['win_rate_percent']:.1f}%")
print(f"Total P&L: ${stats['total_profit_loss_usd']:.2f}")

# Close position programmatically
closed = POSITION_TRACKER.close_position(
    position_id="CHFJPY_1726953600000",
    asset="CHFJPY",
    exit_price=1.0200,
    exit_reason="stop_loss"
)

# Export for compliance
POSITION_TRACKER.export_positions_log("compliance_trades.json")
ORDER_EXECUTOR.export_order_log("compliance_orders.json")
```

---

## 📊 Data Structures

### Position (Dataclass)
```python
@dataclass
class Position:
    position_id: str              # Unique ID
    asset: str                    # "CHF/JPY"
    side: str                     # "BUY" or "SELL"
    entry_amount: float           # Position size in USD
    entry_price: float = 0.0      # Entry price (optional)
    entry_time: float = time.time()
    
    # Exit info
    exit_price: float = 0.0
    exit_time: Optional[float] = None
    exit_reason: str = ""
    
    # Metrics
    status: str = "OPEN"          # OPEN, CLOSED_WIN, CLOSED_LOSS, CLOSED_BREAK_EVEN
    profit_loss_pct: float = 0.0
    profit_loss_usd: float = 0.0
```

### OrderResult (Dataclass)
```python
@dataclass
class OrderResult:
    order_id: Optional[str]       # Broker order ID
    asset: str                    # "CHFJPY"
    side: str                     # "BUY" or "SELL"
    amount: float                 # Trade amount in USD
    status: str                   # "EXECUTED", "FAILED", etc.
    timestamp: float              # Execution time
    message: str = ""             # Error details
    execution_price: float = 0.0
    profit_loss: float = 0.0
```

---

## ⚙️ Configuration

All settings in `ml/config.py`:

```python
# Risk Management
risk_per_trade_percent = 2.0           # % of balance per trade
max_position_size_percent = 5.0        # Max position as % of balance
max_trades_per_day = 20                # Daily trade limit
min_time_between_trades_sec = 5        # Cooldown between trades

# Trading Hours
automation_start_hour = 0              # Start trading (UTC hour)
automation_end_hour = 23               # Stop trading (UTC hour)

# Position Sizing
prefer_demo_mode = True                # Use demo $10k balance
enable_automated_trading = True        # Master switch
```

---

## 🧪 Testing in Demo Mode

### 1. Start Engine
```bash
python engine.py
# Loads $10k demo balance automatically
```

### 2. Monitor Frontend Console
```javascript
// Every 5 seconds, poll for updates
setInterval(async () => {
    const stats = await eel.get_position_statistics()();
    console.log(`📊 Trades: ${stats.total_trades}, W-L: ${stats.winning_trades}-${stats.losing_trades}, P&L: $${stats.total_profit_loss_usd.toFixed(2)}`);
}, 5000);
```

### 3. Enable Automation
```javascript
await eel.enable_automation()();
// Now signals will auto-execute via OrderExecutor
```

### 4. Monitor Open Positions
```javascript
setInterval(async () => {
    const positions = await eel.get_open_positions()();
    for (const [asset, data] of Object.entries(positions)) {
        console.log(`📍 ${asset}: ${data.open_positions} open (${data.total_exposure_usd.toFixed(2)} USD)`);
    }
}, 10000);
```

### 5. View Recent Trades
```javascript
const trades = await eel.get_recent_trades(5)();
trades.forEach(trade => {
    const emoji = trade.pnl_usd > 0 ? '✅' : '❌';
    console.log(`${emoji} ${trade.asset} ${trade.side} P&L: ${trade.pnl_usd.toFixed(2)} USD`);
});
```

---

## 🚨 Error Handling

### Order Execution Failures

**Timeout** (>10 seconds)
```
❌ ORDER EXECUTION ERROR: CHFJPY - Order placement timeout (>10s)
```

**API Error** (broker rejects)
```
❌ ORDER EXECUTION ERROR: CHFJPY - Order rejected by broker
```

**Constraint Violation**
```
⚠️  Trade rejected: Constraint: Daily limit reached (20/day)
```

### Position Tracking

All positions validated on creation/closure:
- ✅ Checks position exists in tracker
- ✅ Calculates P&L if prices provided
- ✅ Logs all position changes
- ✅ Maintains order history (max 1000 records)

---

## 📝 Compliance & Logging

### Audit Trail

Every trade creates permanent record:

```
📍 POSITION OPENED: CHFJPY_1726953600000 BUY CHF/JPY $100.00
   Timestamp: 2026-09-21T14:30:00.000Z
   Signal Confidence: 78.0%
   
✅ BUY ORDER EXECUTED: CHF/JPY $100.00
   Order ID: ord_12345
   Execution Time: 0.15s
   
✅ POSITION CLOSED: CHFJPY_1726953600000 CHF/JPY P&L: +0.22% ($0.22)
   Exit Reason: profit_target_hit
   Duration: 45 seconds
```

### Export Format

**Position History** (`export_positions_log()`):
```json
{
    "exported_at": "2026-09-21T14:45:30.000Z",
    "statistics": {
        "open_positions": 1,
        "total_trades": 25,
        "winning_trades": 16,
        "losing_trades": 9,
        "win_rate_percent": 64.0,
        "total_profit_loss_usd": 125.45,
        "avg_profit_loss_per_trade": 5.02
    },
    "open_positions": { ... },
    "recent_trades": [ ... ]
}
```

**Order History** (`export_order_log()`):
```json
{
    "exported_at": "2026-09-21T14:45:30.000Z",
    "statistics": {
        "orders_placed": 25,
        "orders_executed": 25,
        "orders_failed": 0,
        "execution_rate_percent": 100.0,
        "total_traded_usd": 2500.0,
        "avg_order_size": 100.0
    },
    "orders": [ ... ]
}
```

---

## ✅ Status

### Phase H: Order Execution (Complete ✅)

- ✅ OrderExecutor: BUY/SELL via Quotex API
- ✅ PositionTracker: Open/close tracking + P&L
- ✅ AutomatedTrader: Integration + signal flow
- ✅ Engine: Global instances + client wiring
- ✅ Frontend: 8 new @eel.expose endpoints
- ✅ Demo Mode: Ready for testing
- ✅ Compliance: Full audit trail + export

### Next: Testing & Optimization

1. **Test with real signals** (enable_automation + enable_automated_trading)
2. **Monitor execution rates** (get_order_execution_stats)
3. **Validate P&L calculation** (compare with manual records)
4. **Export compliance logs** (for audit)
5. **Fine-tune risk parameters** (adjust per your account)

---

## 🚀 Quick Start

```bash
# 1. Start engine (auto-loads $10k demo balance)
python engine.py

# 2. Enable automation (via frontend UI)
enable_automation() 

# 3. System is ready!
# - Signals generate → 15 models
# - AutoTradingManager filters → selected pairs only
# - AutomatedTrader validates → 7-stage checks
# - OrderExecutor places → Quotex API
# - PositionTracker records → P&L calculation
# - Frontend displays → real-time stats
```

🎉 **Your automated trading engine is live!**

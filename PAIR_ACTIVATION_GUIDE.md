# Pair Activation/Deactivation Guide
**Phase H: Control Which Pairs Trade in Automation**

---

## ✨ New Feature: Individual Pair Control

You can now **activate/deactivate specific pairs** WITHOUT editing JSON or restarting the engine!

### Default Behavior
- All pairs in `selected_signal_pairs.json` are **ACTIVE by default**
- When automation is enabled, ALL active pairs can trade
- Deactivate pairs you want to skip
- Activate pairs you want to trade

---

## 🎮 Frontend API (JavaScript)

### Activate a Single Pair
```javascript
async function enablePair(pairName) {
    const result = await eel.activate_pair(pairName)();
    if (result.success) {
        console.log("✅ Pair activated:", pairName);
    } else {
        console.error("❌ Error:", result.error);
    }
}

// Usage
enablePair("CHF/JPY");
enablePair("USD/INR (OTC)");
```

### Deactivate a Single Pair
```javascript
async function disablePair(pairName) {
    const result = await eel.deactivate_pair(pairName)();
    if (result.success) {
        console.log("⏸️  Pair deactivated:", pairName);
    } else {
        console.error("❌ Error:", result.error);
    }
}

// Usage
disablePair("CHF/JPY");  // Won't trade signals for this pair
```

### Activate ALL Pairs
```javascript
async function activateAllPairs() {
    const result = await eel.activate_all_pairs()();
    if (result.success) {
        console.log(`✅ Activated ${result.activated_count} pairs`);
    }
}
```

### Deactivate ALL Pairs
```javascript
async function deactivateAllPairs() {
    const result = await eel.deactivate_all_pairs()();
    if (result.success) {
        console.log(`⏸️  Deactivated ${result.deactivated_count} pairs`);
    }
}
```

### Get Active Pairs
```javascript
async function showActivePairs() {
    const activePairs = await eel.get_active_pairs()();
    console.log("Active pairs:", activePairs);
    // Output: ["CHF/JPY", "USD/INR (OTC)", ...]
}
```

### Get Inactive Pairs
```javascript
async function showInactivePairs() {
    const inactivePairs = await eel.get_inactive_pairs()();
    console.log("Inactive pairs:", inactivePairs);
    // Output: ["CAD/JPY (OTC)", ...]
}
```

---

## 📊 Backend Implementation

### Python Methods (AutoTradingManager)

```python
# Activate a pair
AUTO_TRADING_MANAGER.activate_pair("CHF/JPY")

# Deactivate a pair
AUTO_TRADING_MANAGER.deactivate_pair("CHF/JPY")

# Activate all
AUTO_TRADING_MANAGER.activate_all_pairs()

# Deactivate all
AUTO_TRADING_MANAGER.deactivate_all_pairs()

# Check if pair is active
is_active = AUTO_TRADING_MANAGER.is_pair_active("CHF/JPY")

# Get active pairs
active_list = AUTO_TRADING_MANAGER.get_active_pairs()

# Get inactive pairs
inactive_list = AUTO_TRADING_MANAGER.get_inactive_pairs()
```

---

## 🔄 How It Works

### Signal Processing Flow

```
ML Signal generated → "Buy CHF/JPY @ 75% confidence"
    ↓
AutoTradingManager.process_signal()
    ↓
Check 1: Automation enabled? ✅
    ↓
Check 2: "CHF/JPY" in selected_signal_pairs.json? ✅
    ↓
Check 3: "CHF/JPY" currently ACTIVE? (NEW)
    ├─ YES → Continue to trader (7-stage validation)
    └─ NO  → REJECT "Pair CHF/JPY is currently deactivated"
```

### Pair Status Tracking

Each pair maintains its own status:
```python
@dataclass
class TradingPairStatus:
    display_name: str           # "CHF/JPY"
    internal_name: str          # "CHFJPY"
    is_active: bool             # NEW: Can it trade?
    last_signal_time: float
    last_signal_confidence: float
    signals_today: int
    trades_executed: int
```

---

## 💡 Use Cases

### 1. **Market Condition Filtering**
Deactivate volatile pairs when market is unstable:
```javascript
async function handleMarketVolatility() {
    // During high volatility, trade only stable pairs
    await eel.deactivate_pair("USD/INR (OTC)");  // High volatility
    await eel.deactivate_pair("CAD/JPY (OTC)");  // High volatility
    await eel.activate_pair("CHF/JPY");          // More stable
}
```

### 2. **Pair-Specific Testing**
Test a new strategy on one pair:
```javascript
async function testNewStrategy() {
    // Disable all pairs
    await eel.deactivate_all_pairs();
    
    // Enable only one pair for testing
    await eel.activate_pair("CHF/JPY");
    
    // Monitor performance
    // Later: if good, activate others
}
```

### 3. **Risk Management**
After taking profits, disable that pair temporarily:
```javascript
async function takeProfitsAndPause() {
    // Just closed profitable CHF/JPY trades
    // Pause to lock in gains, re-enable later
    await eel.deactivate_pair("CHF/JPY");
    
    // Other pairs continue trading
}
```

### 4. **Pair Rotation**
Trade different pairs at different times:
```javascript
async function morningTrading() {
    // Morning: Trade Asian pairs
    await eel.activate_pair("USD/INR (OTC)");
    await eel.activate_pair("USD/PKR (OTC)");
    await eel.deactivate_pair("CHF/JPY");
}

async function eveningTrading() {
    // Evening: Trade EUR pairs
    await eel.deactivate_pair("USD/INR (OTC)");
    await eel.deactivate_pair("USD/PKR (OTC)");
    await eel.activate_pair("CHF/JPY");
}
```

---

## 📈 Real-Time Status Example

### get_pair_statuses() with activation info

```python
{
    "USD/INR (OTC)": {
        "display_name": "USD/INR (OTC)",
        "internal_name": "USDINR_otc",
        "is_active": True,              # ← Can trade
        "last_signal": {
            "time": 1726956945.123,
            "confidence": 0.78
        },
        "signals_today": 5,
        "trades_today": 2
    },
    "CHF/JPY": {
        "display_name": "CHF/JPY",
        "internal_name": "CHFJPY",
        "is_active": False,             # ← Deactivated
        "last_signal": {
            "time": 1726956932.456,
            "confidence": 0.72
        },
        "signals_today": 3,
        "trades_today": 0               # ← No trades (deactivated)
    },
    "CAD/JPY (OTC)": {
        "display_name": "CAD/JPY (OTC)",
        "internal_name": "CADJPY_otc",
        "is_active": True,
        "last_signal": {
            "time": 1726956950.789,
            "confidence": 0.65
        },
        "signals_today": 2,
        "trades_today": 1
    }
}
```

---

## 🎯 Quick Reference

| Action | Frontend Call | Result |
|--------|--------------|--------|
| Activate pair | `activate_pair("CHF/JPY")` | Pair can execute trades |
| Deactivate pair | `deactivate_pair("CHF/JPY")` | Signals rejected, no trades |
| Activate all | `activate_all_pairs()` | All pairs enabled |
| Deactivate all | `deactivate_all_pairs()` | All pairs disabled |
| Check active | `get_active_pairs()` | List of enabled pairs |
| Check inactive | `get_inactive_pairs()` | List of disabled pairs |

---

## ⚙️ Console Output Examples

### When Activating a Pair
```
✅ PAIR ACTIVATED: CHF/JPY
```

### When Deactivating a Pair
```
⏸️  PAIR DEACTIVATED: CHF/JPY
```

### When Signal Comes for Deactivated Pair
```
Signal for CHF/JPY rejected: "Pair CHF/JPY is currently deactivated"
```

### When Activating All Pairs
```
✅ Activated all 7 pairs
```

---

## 🔧 Configuration Persistence

**Note**: Pair activation/deactivation settings are **NOT persisted** between restarts.

**On engine restart**:
- All pairs in `selected_signal_pairs.json` are **ACTIVE by default**
- You must re-deactivate pairs if needed

**To persist settings**, you could:
1. Create a `pair_configuration.json` file
2. Load it on engine startup
3. Store activation state there

(This is optional - most users prefer fresh start each day)

---

## 🚨 Troubleshooting

### "Pair not found" error
- Check spelling (case-sensitive): "CHF/JPY" not "CHF/jpy"
- Ensure pair is in `selected_signal_pairs.json`

### Pair won't activate
- Check it's in selected pairs JSON
- Check pair name exactly matches JSON

### Signals still processing deactivated pair
- Give it a moment for hard ping cycle to update
- Refresh frontend to see current status

### Want to reset to all active
```javascript
await eel.activate_all_pairs()();
```

---

## 📝 Example UI Implementation

### HTML Toggle Switch
```html
<div class="pair-list">
  <div class="pair-item" id="pair-chfjpy">
    <span class="pair-name">CHF/JPY</span>
    <label class="toggle">
      <input type="checkbox" checked onchange="togglePair('CHF/JPY', this.checked)">
      <span class="slider"></span>
    </label>
  </div>
  <div class="pair-item" id="pair-usdinr">
    <span class="pair-name">USD/INR (OTC)</span>
    <label class="toggle">
      <input type="checkbox" checked onchange="togglePair('USD/INR (OTC)', this.checked)">
      <span class="slider"></span>
    </label>
  </div>
</div>

<script>
async function togglePair(pairName, isActive) {
    if (isActive) {
        await eel.activate_pair(pairName)();
    } else {
        await eel.deactivate_pair(pairName)();
    }
}
</script>
```

---

## ✅ Summary

✨ **You can now control which pairs trade in automation without restarting!**

- ✅ Activate/deactivate individual pairs
- ✅ Test strategies on single pairs
- ✅ Manage risk by pausing high-volatility pairs
- ✅ Rotate pairs based on market conditions
- ✅ Real-time status via get_pair_statuses()

**All without editing JSON or restarting engine.py!**

🚀 Start using pair control today!

# Balance Feature - Quick Start Guide

## What's New

✅ **Get real and demo balances** from Quotex  
✅ **Switch between REAL and PRACTICE** accounts  
✅ **Auto-logged in hard ping** (every 60 seconds)  

## Usage Examples

### JavaScript (Frontend)

#### Get Current Balances
```javascript
// Get real and demo balances
const balances = eel.get_account_balances_sync()();

console.log("Real Account:   $" + balances.real.toFixed(2));
console.log("Demo Account:   $" + balances.demo.toFixed(2));
console.log("Current Mode:   " + balances.current_mode);
console.log("Last Updated:   " + new Date(balances.timestamp * 1000));
```

**Response:**
```javascript
{
  real: 5000.50,
  demo: 1000.00,
  current_mode: "PRACTICE",
  timestamp: 1726680621.234
}
```

#### Switch to Demo Account
```javascript
const result = eel.switch_account_mode("PRACTICE")();

if (result.success) {
    console.log("✅ Switched to PRACTICE");
    console.log("Demo Balance: $" + result.demo.toFixed(2));
} else {
    console.error("❌ Failed:", result.error);
}
```

**Response:**
```javascript
{
  success: true,
  message: "Switched to PRACTICE mode",
  real: 5000.50,
  demo: 1000.00,
  current_mode: "PRACTICE"
}
```

#### Switch to Real Account
```javascript
const result = eel.switch_account_mode("REAL")();

if (result.success) {
    console.log("✅ Switched to REAL");
    console.log("Real Balance: $" + result.real.toFixed(2));
}
```

### Python (Backend)

#### Get Balances Async
```python
import asyncio
from pyquotex.stable_api import Quotex

async def check_balances():
    client = Quotex(email="your@email.com", password="pass")
    await client.connect()
    
    # Method 1: Using profile directly
    real = client.api.profile.live_balance
    demo = client.api.profile.demo_balance
    print(f"Real: ${real:.2f}, Demo: ${demo:.2f}")
    
    # Method 2: Using get_balance()
    balance = await client.get_balance()
    print(f"Current balance: ${balance:.2f}")

asyncio.run(check_balances())
```

## Display Examples

### Simple Balance Card
```html
<div class="balance-card">
  <h3>Account Balance</h3>
  <div id="real-balance">Real: $--</div>
  <div id="demo-balance">Demo: $--</div>
  <div id="mode">Mode: --</div>
  <button onclick="refreshBalances()">Refresh</button>
</div>

<script>
function refreshBalances() {
    const bal = eel.get_account_balances_sync()();
    document.getElementById("real-balance").textContent = 
        "Real: $" + bal.real.toFixed(2);
    document.getElementById("demo-balance").textContent = 
        "Demo: $" + bal.demo.toFixed(2);
    document.getElementById("mode").textContent = 
        "Mode: " + bal.current_mode;
}

function switchMode(mode) {
    const result = eel.switch_account_mode(mode)();
    if (result.success) {
        alert("✅ Switched to " + result.current_mode);
        refreshBalances();
    } else {
        alert("❌ Error: " + result.error);
    }
}
</script>
```

### Bootstrap Design
```html
<div class="card">
  <div class="card-header">
    <h5>Quotex Account</h5>
  </div>
  <div class="card-body">
    <div class="row">
      <div class="col-md-6">
        <div class="alert alert-info">
          <strong>Real Account</strong>
          <h4>$<span id="real">--</span></h4>
        </div>
      </div>
      <div class="col-md-6">
        <div class="alert alert-warning">
          <strong>Demo Account</strong>
          <h4>$<span id="demo">--</span></h4>
        </div>
      </div>
    </div>
    <div class="btn-group" role="group">
      <button class="btn btn-sm btn-primary" 
              onclick="switchMode('REAL')">Use Real</button>
      <button class="btn btn-sm btn-warning" 
              onclick="switchMode('PRACTICE')">Use Demo</button>
    </div>
  </div>
</div>
```

## Testing

### Run Test Script
```bash
python test_balance_feature.py
```

Expected output:
```
🔐 Connecting to Quotex...
✅ Connected
✅ Account ID: 12345678

================================================================================
TEST 1: Get Balances (Current Mode)
================================================================================
✅ Profile loaded
   Demo Balance:  $1000.00
   Real Balance:  $5000.50
   Current Mode:  PRACTICE
   get_balance(): $1000.00

================================================================================
TEST 2: Switch to PRACTICE Mode
================================================================================
✅ Switched to PRACTICE
   Demo Balance:  $1000.00
   Real Balance:  $5000.50
   get_balance(): $1000.00
```

## Logs to Watch

In the engine console, look for:

**Hard Ping Logs (every 60s):**
```
💓 Hard ping OK — balance: 1000.00 | Real: $5000.50 Demo: $1000.00
```

**Balance Fetch Logs:**
```
💰 Account balances: Real=$5000.50 Demo=$1000.00 Mode=PRACTICE
```

**Switch Account Logs:**
```
✅ Switched to PRACTICE mode
```

## Common Patterns

### Auto-Refresh Balance Every 30 Seconds
```javascript
setInterval(() => {
    const bal = eel.get_account_balances_sync()();
    document.getElementById("balance").textContent = 
        "Balance: $" + (bal.current_mode === "REAL" ? bal.real : bal.demo).toFixed(2);
}, 30000);
```

### Disable Real Trading Below Threshold
```javascript
const bal = eel.get_account_balances_sync()();
if (bal.current_mode === "REAL" && bal.real < 100) {
    alert("⚠️ Real account balance below $100. Switching to PRACTICE.");
    eel.switch_account_mode("PRACTICE")();
}
```

### Show Balance Alert on Mode Switch
```javascript
function switchMode(mode) {
    const result = eel.switch_account_mode(mode)();
    if (result.success) {
        const balance = mode === "REAL" ? result.real : result.demo;
        eel.show_alert(
            f"💰 Now trading on {mode} account with ${balance.toFixed(2)}"
        )();
    }
}
```

## API Reference

### `get_account_balances_sync()`
| Property | Type | Description |
|----------|------|-------------|
| `real` | float | Real account balance |
| `demo` | float | Demo/Practice account balance |
| `current_mode` | string | "REAL" or "PRACTICE" |
| `timestamp` | float | Unix timestamp of fetch |
| `error` | string | Error message (if failed) |

### `switch_account_mode(mode)`
| Parameter | Type | Value |
|-----------|------|-------|
| `mode` | string | "REAL" or "PRACTICE" |

| Response | Type | Description |
|----------|------|-------------|
| `success` | bool | Whether switch was successful |
| `message` | string | Status message |
| `real` | float | New real balance (if success) |
| `demo` | float | New demo balance (if success) |
| `current_mode` | string | New mode (if success) |
| `error` | string | Error message (if failed) |

## Troubleshooting

### "Timeout" Error
**Cause:** Network slow or Quotex API unresponsive  
**Fix:** Wait a moment and try again, check internet connection

### "Client not connected"
**Cause:** Engine not connected to Quotex yet  
**Fix:** Complete login first, then try again

### Balance Won't Update
**Cause:** Hard ping may not have run yet  
**Fix:** Click "Refresh" button or wait 60 seconds for auto-update

### Can't Switch Accounts
**Cause:** Network issue or account locked  
**Fix:** Check connection, try switching manually in Quotex app

## See Also
- Full documentation: `BALANCE_FEATURE_DOCS.md`
- Test script: `test_balance_feature.py`
- Engine code: `engine.py` (search for `get_account_balances`)

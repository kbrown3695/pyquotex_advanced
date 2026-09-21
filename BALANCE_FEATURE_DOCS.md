# Real & Demo Balance Feature

## Overview
The balance feature allows you to fetch and switch between real and demo (practice) account balances in Quotex.

## Features Implemented

### 1. Get Account Balances
**Backend Function:** `get_account_balances()` (async)
- Fetches both real and demo balances from the Quotex API
- Returns structured data with timestamps

**Frontend Function:** `get_account_balances_sync()` (exposed via EEL)
- Thread-safe synchronous wrapper for frontend
- 10-second timeout
- Returns JSON with balance data

**Response Format:**
```json
{
  "real": 5000.50,
  "demo": 1000.00,
  "current_mode": "PRACTICE",
  "timestamp": 1234567890.123
}
```

### 2. Switch Account Mode
**Frontend Function:** `switch_account_mode(mode)` (exposed via EEL)
- Switch between `"REAL"` and `"PRACTICE"` accounts
- Updates account mode on Quotex
- Returns new balance info after switching

**Parameters:**
- `mode` (string): `"REAL"` or `"PRACTICE"`

**Response Format:**
```json
{
  "success": true,
  "message": "Switched to PRACTICE mode",
  "real": 5000.50,
  "demo": 1000.00,
  "current_mode": "PRACTICE"
}
```

## Backend Implementation

### Key Functions Added

#### 1. `get_account_balances()` - Async Function
Located in `engine.py` (around line 534)

```python
async def get_account_balances() -> Dict[str, float]:
    """Get both real and demo account balances from Quotex API."""
    # Reads from: CLIENT.api.profile.live_balance
    #             CLIENT.api.profile.demo_balance
    #             CLIENT.account_is_demo
```

**What it does:**
- Checks if CLIENT and profile are available
- Extracts live_balance (real account) and demo_balance
- Determines current mode (REAL if account_is_demo==0, else PRACTICE)
- Returns all data in a dict

**Used by:**
- `hard_ping_loop()` - Now logs balance info every 60 seconds
- `get_account_balances_sync()` - Frontend wrapper

#### 2. `get_account_balances_sync()` - Exposed to Frontend
Located in `engine.py` (around line 1709)

```python
@eel.expose
def get_account_balances_sync():
    """Get real and demo balances synchronously."""
```

**What it does:**
- Runs async `get_account_balances()` in the asyncio loop
- Executes in a daemon thread to avoid blocking
- 10-second timeout for safety
- Logs the result

**Usage from Frontend:**
```javascript
const balances = eel.get_account_balances_sync()();
console.log(balances);
// Output: {real: 5000.50, demo: 1000.00, current_mode: "PRACTICE", timestamp: ...}
```

#### 3. `switch_account_mode(mode)` - Exposed to Frontend
Located in `engine.py` (around line 1735)

```python
@eel.expose
def switch_account_mode(mode: str):
    """Switch between REAL and PRACTICE account modes."""
```

**What it does:**
- Validates mode parameter (REAL or PRACTICE)
- Calls `CLIENT.change_account(mode)` asynchronously
- Fetches updated balances
- Logs the action

**Usage from Frontend:**
```javascript
const result = eel.switch_account_mode("PRACTICE")();
if (result.success) {
    console.log("Switched to:", result.current_mode);
    console.log("New balances:", result.real, result.demo);
}
```

## Integration with Existing Features

### Hard Ping Loop
The `hard_ping_loop()` now logs balance information:
```
💓 Hard ping OK — balance: 1000.00 | Real: $5000.50 Demo: $1000.00
```

This means you get:
- Connection health check (via hard ping)
- Current balance verification
- Automatic balance updates every 60 seconds

## Testing

### Test Script
Run `test_balance_feature.py` to test the feature:
```bash
python test_balance_feature.py
```

This will:
1. Connect to Quotex
2. Get current balances
3. Switch to PRACTICE mode and fetch balances
4. Switch to REAL mode and fetch balances
5. Show the full profile structure

### Frontend Testing
Add to your HTML/JavaScript:
```javascript
// Get balances
const balances = eel.get_account_balances_sync()();
console.log('Current Balances:', balances);

// Switch to demo
const result = eel.switch_account_mode("PRACTICE")();
console.log('Switch Result:', result);

// Get balances again
const updated = eel.get_account_balances_sync()();
console.log('Updated Balances:', updated);
```

## UI Display Recommendations

### Balance Card
Display both balances with mode indicator:
```
┌─ Account Balances ──────────────────┐
│ Mode: [PRACTICE ▼]                  │
│                                     │
│ Real Account:   $5,000.50          │
│ Demo Account:   $1,000.00          │
│ Last Updated:   2 seconds ago      │
│                                     │
│ [Switch to REAL]  [Refresh]        │
└─────────────────────────────────────┘
```

### In Signal Display
Show which balance is active:
```
AUD/CAD (OTC) - 1m
Signal: SELL @ 0.18
Confidence: 82%
Account: PRACTICE ($1,000.00)
```

## API Reference

### `get_account_balances_sync()` - Frontend
```
No parameters

Returns:
{
  "real": float,           // Real account balance
  "demo": float,           // Demo account balance  
  "current_mode": string,  // "REAL" or "PRACTICE"
  "timestamp": float,      // Unix timestamp
  "error": string (optional) // Error message if failed
}
```

### `switch_account_mode(mode)` - Frontend
```
Parameters:
  mode (string): "REAL" or "PRACTICE"

Returns:
{
  "success": boolean,
  "message": string,
  "real": float (if success),
  "demo": float (if success),
  "current_mode": string (if success),
  "error": string (if failed)
}
```

## Error Handling

### Timeout
- Hard timeout: 10 seconds for balance fetch
- Thread timeout: 15 seconds for thread completion
- Returns zeros and error message on timeout

### Connection Issues
- Returns cached values if profile unavailable
- Logs warning with error details
- Does not crash application

### Invalid Mode
- Returns error if mode is not "REAL" or "PRACTICE"
- Does not attempt to switch
- Returns current state

## Performance

- **Balance Fetch:** ~500ms (network dependent)
- **Account Switch:** ~2 seconds (includes profile refresh)
- **Hard Ping:** Runs every 60 seconds, takes <1 second
- **Frontend Call:** Non-blocking (runs in daemon thread)

## Future Enhancements

1. **Real-time Balance Updates**
   - WebSocket listener for balance changes
   - Notify frontend immediately on balance change

2. **Balance History**
   - Track balance changes over time
   - Show profit/loss since session start

3. **Account Comparison**
   - Compare performance between REAL and PRACTICE
   - Show correlation between modes

4. **Alerts**
   - Alert when balance drops below threshold
   - Notify on insufficient funds

5. **API Improvements**
   - Batch balance requests
   - Cache for 30 seconds to reduce API calls
   - Fallback to cached data on timeout

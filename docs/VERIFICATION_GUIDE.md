# ✅ Verification Guide for Applied Fixes

Follow these steps to verify each fix is working correctly.

---

## Test 1: Queue Overflow Logging ✅

**Objective**: Verify that queue overflows are logged (not silent).

### Steps:
1. Start the bot: `python engine.py`
2. Login successfully
3. Open chart with frequent timeframe switching (every second)
4. Monitor console output

**Expected Result**:
```
[HH:MM:SS] 🚨 UI Queue overflow (dropped 5 updates)
```
- Should see this message if you switch timeframes very rapidly
- Message throttled to once per 5 seconds (won't spam)
- Queue size increased to 100 (was 50), so harder to trigger

**Failure Indicators**:
- No overflow message despite rapid switches → queue size adequate (good!)
- Crashes → bug in logging code (bad!)

---

## Test 2: Candle Validation ✅

**Objective**: Verify corrupted candles are rejected with logging.

### Manual Test (requires broker connection):
1. Monitor console with `CONSOLE_LEVEL = 2` (verbose)
2. Look for these messages during normal operation:

```
⚠️ Candle has non-positive price: {...}
⚠️ Candle inverted: high (X) < low (Y)
⚠️ Candle OHLC out of bounds: O=X H=Y L=Z C=W
```

**Expected Result**:
- Should see **NO** validation warnings during normal operation (broker sends clean data)
- If any appear, they're logged at level 2 (verbose) and NOT displayed on chart
- Corrupted candles are silently dropped

**Failure Indicators**:
- Chart shows impossible candles (wicks longer than full range) → validation failed
- Crashes when parsing candles → validation code broken

---

## Test 3: Aggressive Resub Backoff ✅

**Objective**: Verify resub logic respects broker rate limits.

### Steps:
1. Start bot with `CONSOLE_LEVEL = 1` (normal)
2. Create artificial network issue: unplug cable/kill WiFi for 5 seconds
3. Monitor console during recovery

**Expected Behavior**:
```
[HH:MM:SS] ⚠️ get_realtime_price timeout (AUD/CAD (OTC))
[HH:MM:SS] ⚠️ 8 timeouts — trying resub (with backoff)
[HH:MM:SS] 🔁 Forced resub: AUD/CAD (OTC) [1m]
```

**Then** connection recovers. After 30-60 seconds → normal stream.

**Expected Result**:
- Resub attempt made after 8 timeouts (was 15, more conservative)
- If connection still bad, won't resub again for 15 seconds (prevents hammering)
- After 50 empty ticks, triggers full reconnect instead of infinite retry

**Failure Indicators**:
- Resub happens every second → backoff not working
- Connection never recovers even after network restored → too aggressive
- Broker responds with "rate limited" errors → backoff insufficient

---

## Test 4: Error Handling in Credentials ✅

**Objective**: Verify login endpoint validates input.

### Test Invalid Email:
```
1. Start bot
2. Click login, enter "notanemail" as email
```

**Expected Result**:
```
❌ Invalid email format
```
Browser shows error message, login rejected.

### Test Invalid Password:
```
1. Start bot
2. Enter valid email, password "ab" (too short)
```

**Expected Result**:
```
❌ Password must be at least 3 characters
```

### Test Valid Inputs:
```
1. Enter valid email and password
```

**Expected Result**:
Login proceeds to broker authentication.

---

## Test 5: Asset Validation ✅

**Objective**: Verify invalid assets are rejected.

### Steps:
1. Login successfully
2. Open browser DevTools (F12)
3. In console, run:
```javascript
eel.change_asset("INVALID_ASSET")()
```

**Expected Result** (in browser console):
```
⚠️ Unknown asset: INVALID_ASSET
```

No crash, no network call, graceful rejection.

### Valid Asset Switch:
```javascript
eel.change_asset("EUR/USD")()
```

Should work normally (if EUR/USD in your asset list).

---

## Test 6: Timeframe Validation ✅

**Objective**: Verify invalid timeframes are rejected.

### Steps:
1. Login successfully
2. Open DevTools (F12)
3. In console:
```javascript
eel.change_timeframe("999d")
```

**Expected Result**:
```
❌ Invalid timeframe: 999d
```

No crash, no API call.

### Valid Timeframe:
```javascript
eel.change_timeframe("5m")
```

Should work normally.

---

## Test 7: Exception Logging Improvements ✅

**Objective**: Verify background tasks log errors properly.

### Steps:
1. Start bot
2. Monitor console for 2 minutes with `CONSOLE_LEVEL = 2`

**Expected Output** (examples, shouldn't occur in normal operation):
```
💓 Hard ping OK — balance: 1000.50
📡 Market ping: 2 candles
🔁 Forced resub: EUR/USD [5m]
```

**If errors occur**, you should see:
```
⚠️ Hard ping timeout — triggering reconnect
⚠️ Resub connection error: OSError: [Errno 101] ...
⚠️ Market ping error: ConnectionError: ...
```

**Expected Result**:
- Specific error types listed (OSError, ConnectionError, etc.)
- NOT bare "Exception occurred"
- Appropriate action taken (reconnect, retry, etc.)

---

## Test 8: Memory Usage (Optional) ⚙️

**Objective**: Verify candle cache is bounded.

### Steps:
1. Login successfully
2. Open chart, let it run for 5 minutes
3. Switch assets 10 times
4. Monitor system memory

**Expected Result**:
- Memory usage stays under 150MB (was unbounded before)
- Switching assets doesn't leak memory
- Only current asset's candles kept in memory

**How to check**:
```bash
# In PowerShell
Get-Process python | Select-Object Name, WorkingSet
```

---

## Summary Checklist

- [ ] Test 1: Queue overflow logging works
- [ ] Test 2: Candle validation rejects bad data
- [ ] Test 3: Resub logic has backoff (not aggressive)
- [ ] Test 4: Email/password validation works
- [ ] Test 5: Asset validation works
- [ ] Test 6: Timeframe validation works
- [ ] Test 7: Error logging is specific (not bare except)
- [ ] Test 8: Memory usage bounded (optional)

---

## Troubleshooting

### "No overflow messages seen"
✅ This is GOOD! Means queue is adequately sized for your usage.

### "Validation messages in normal operation"
❌ Broker might be sending bad data. Check broker status.

### "Chart shows corrupted candles"
❌ Validation code not working. Check `process_candle_data()` function.

### "Connection hammered repeatedly"
❌ Backoff not working. Check `last_resub_time` logic.

### "Silent failures still happening"
❌ Background task not updated. Check exception handlers use specific types.

---

## Performance Baseline

Record these metrics before and after fixes:

**Before Fixes**:
- CPU: ____%
- Memory: ____ MB
- Reconnects/hour: ____
- Missed chart updates: ____ (from logs)

**After Fixes**:
- CPU: ____%
- Memory: ____ MB
- Reconnects/hour: ____
- Missed chart updates: ____ (from logs)

Expected improvement: 
- 50% fewer reconnects (with backoff)
- 0% missed UI updates (with larger queue + logging)
- Same CPU/memory

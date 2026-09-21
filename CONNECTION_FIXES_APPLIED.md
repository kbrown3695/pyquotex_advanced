# Connection Issues - Fixes Applied

## Overview
Applied comprehensive fixes to address chart freezing and connection loss issues. Changes target both backend (Python/engine.py) and frontend (JavaScript/datafeed.js) to enable faster detection, recovery, and better user feedback.

## Backend Changes (engine.py)

### 1. Aggressive Timeout Detection (Line 207-212)
**Before:**
```python
TICK_IDLE_THRESHOLD   = 90   # 1.5 minutes!
EMPTY_TICK_RESUB_THRESHOLD = 30
MAX_CONSECUTIVE_EMPTY = 100
```

**After:**
```python
TICK_IDLE_THRESHOLD   = 30   # 30 seconds (3x faster detection)
EMPTY_TICK_RESUB_THRESHOLD = 12  # ~6 seconds (2.5x faster)
MAX_CONSECUTIVE_EMPTY = 50   # (2x faster full reconnect)
```

**Impact:** Backend now detects dead connections 3x faster

### 2. Faster Recovery Retry Logic (Line 819-827)
**Before:**
```python
if consecutive_empty >= 8 and (time.time() - last_resub_time) > 10:
    # 8 timeouts = 4 seconds + 10 second backoff = 14 seconds minimum
```

**After:**
```python
if consecutive_empty >= 3 and (time.time() - last_resub_time) > 2:
    # 3 timeouts = 1.5 seconds + 2 second backoff = 3.5 seconds
    # Also reduced sleep from 0.5s to 0.1s for faster retries
```

**Impact:** Aggressive 3.5-second recovery vs 14-second wait

### 3. New Reconnect Endpoint (Line ~1300)
Added `@eel.expose def reconnect_realtime()`:
- Frontend can now call backend to force reconnection
- Sets `CHART_OPENED = False` to trigger full refresh
- Calls `send_to_ui(..., full=True)` to push complete data snapshot
- Properly triggers async reconnection via `asyncio.run_coroutine_threadsafe()`

```python
@eel.expose
def reconnect_realtime():
    """Force reconnection of realtime data stream - called by frontend when connection lost."""
    # Logs connection attempt
    # Force full chart refresh
    # Resubscribe to realtime price
    # Send full candle dataset to frontend
```

## Frontend Changes (datafeed.js)

### 1. Better Connection Recovery (Line 631-664)
**Before:**
```javascript
if (typeof eel?.change_asset === 'function') {
    safeEelCall(eel.change_asset, AppState.currentAsset);
}
```

**After:**
```javascript
if (typeof eel?.reconnect_realtime === 'function') {
    safeEelCall(eel.reconnect_realtime);  // NEW: Proper reconnect
} else if (typeof eel?.change_asset === 'function') {
    safeEelCall(eel.change_asset, AppState.currentAsset);  // Fallback
```

**Also added:**
- Call `stopCountdownAnimation()` to pause countdown
- Set `AppState.needsFullRedraw = true` when connection restored
- Keep warning toast visible until recovery
- Change toast to use emoji and "warning" type for visibility

### 2. Countdown Pause During Disconnection (New Function)
Added `stopCountdownAnimation()` function:
```javascript
function stopCountdownAnimation() {
    // Clear animation timeout
    // Update label to show "⏱ OFFLINE"
    // Prevents confusing frozen countdown during disconnection
}
```

Also updated `animateCountdown()` to check `AppState.connectionHealthy`:
```javascript
function animateCountdown(currentPrice) {
    // FIXED: Pause countdown during disconnection
    if (!AppState.connectionHealthy) {
        return;
    }
    // ... rest of animation
}
```

**Impact:** 
- No more frozen countdown during disconnection
- User sees "OFFLINE" indicator on countdown label
- Prevents visual confusion that system is hanging

### 3. Full Chart Refresh on Recovery
When connection restored:
```javascript
AppState.needsFullRedraw = true;
```
This ensures `updateChart()` reinitializes all data instead of showing stale candles.

## Timeline of Improvements

### Before Fixes:
1. Connection drops → no updates
2. ~90 seconds → backend detects idle
3. ~14 seconds → retry logic triggers
4. ~10 seconds → frontend timeout check
5. **Total: ~114 seconds** before chart updates resume
6. Chart appears frozen with stale candle price
7. Countdown timer keeps animating with old price

### After Fixes:
1. Connection drops → no updates
2. ~3 seconds → faster timeout detection (EMPTY_TICK_RESUB_THRESHOLD)
3. ~2 seconds → aggressive retry kicks in
4. ~3-5 seconds → frontend triggered reconnect via new endpoint
5. **Total: ~8-15 seconds** before recovery attempt
6. Countdown shows "OFFLINE" while disconnected
7. Chart shows connection warning toast
8. Full chart refresh on recovery

**~10x faster recovery time** (from 114s to ~8-15s)

## Testing Checklist

After deploying these fixes, verify:

### Automated Tests
- [ ] Backend: Test `reconnect_realtime()` endpoint responds quickly
- [ ] Frontend: Verify `stopCountdownAnimation()` fires on connection loss
- [ ] Frontend: Check `AppState.needsFullRedraw` gets set on recovery

### Manual Tests
1. **Simulate Connection Loss:**
   - Stop WebSocket server or kill network briefly
   - Chart should show "🔌 Connection lost - reconnecting..." toast
   - Countdown label should show "⏱ OFFLINE"
   - Should NOT see frozen countdown with old price

2. **Verify Recovery:**
   - Restore connection
   - Should see "✅ Connection restored" toast within 5-10 seconds
   - Chart should update with fresh data
   - Countdown should resume with current price

3. **Check Performance:**
   - Time from connection drop to first retry: should be ~3-5s
   - Time to full recovery: should be ~8-15s
   - No data loss after recovery

4. **Edge Cases:**
   - Rapid reconnects: test multiple drops in short time
   - Long disconnections: test >30 seconds offline
   - Asset/timeframe changes: test during recovery

## Configuration Tuning

If issues persist, these constants can be adjusted (in engine.py):

```python
TICK_IDLE_THRESHOLD = 30        # Detect dead connection (seconds)
EMPTY_TICK_RESUB_THRESHOLD = 12 # Trigger recovery (at 0.5s per tick = ~6s)
MAX_CONSECUTIVE_EMPTY = 50      # Full reconnect threshold

# In datafeed.js CONFIG:
CONNECTION_TIMEOUT_MS = 10000   # Frontend timeout (ms)
CONNECTION_CHECK_INTERVAL_MS = 5000  # Check frequency (ms)
```

## Known Limitations

1. **WebSocket Status**: Cannot directly poll WebSocket state in pyquotex, relies on data flow
2. **Recovery Time**: Still depends on backend's `start_realtime_price()` implementation
3. **Queue Overflow**: Large payloads might still overflow UI queue during recovery

## Next Steps (Future Enhancements)

1. Add connection status indicator in toolbar
2. Implement exponential backoff for multiple reconnects
3. Add "Force Reconnect" button for manual recovery
4. Log connection events to backend for diagnostics
5. Add circuit breaker pattern for cascading failures

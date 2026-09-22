# Connection Issues & Chart Freezing - Root Cause Analysis

## Problem Statement
When WebSocket connection is lost, the chart freezes on the last candle. The countdown timer continues animating with stale data, and "Connection lost, reconnecting..." message appears but data doesn't resume even after reconnection.

## Root Causes

### 1. Backend Issues (engine.py)

#### Issue A: Slow Zombie Detection (Line 787)
```python
if idle_secs > TICK_IDLE_THRESHOLD and is_websocket_connected():
```
- **TICK_IDLE_THRESHOLD** = 90 seconds (too long!)
- Takes 1.5 minutes before backend notices no data arriving
- During this time, chart appears frozen with stale candle

**Fix:** Reduce to 30 seconds for faster detection

#### Issue B: Delayed Reconnection (Line 815-825)
```python
if consecutive_empty >= 8 and (time.time() - last_resub_time) > 10:
```
- Waits for 8 consecutive timeouts (4 seconds) + 10 second backoff = 14 seconds minimum
- Multiple layers of retry logic with exponential backoff make recovery slow
- By the time reconnection happens, frontend has already given up

**Fix:** Aggressive retry on first sign of trouble (after 3 timeouts, not 8)

#### Issue C: Silent Queue Overflow (Line 765-770)
```python
except Full:
    QUEUE_OVERFLOW_COUNT += 1
    if now - QUEUE_LAST_OVERFLOW_LOG > 5:
        log(f"🚨 UI Queue overflow...")
```
- When UI queue is full, updates silently drop
- Frontend never receives the data even when backend recovered
- No alert to user that they're seeing stale data

**Fix:** Flush queue on connection recovery, force full chart refresh

#### Issue D: Rate Limiting (Line 728)
```python
if not (full or force) and (now - LAST_UI_SEND) < 0.5:
    return False
```
- Only sends incremental updates every 500ms
- If connection drops during rate-limit window, no data goes out
- Creates dead zones where updates are queued but never sent

**Fix:** Reduce rate limit to 250ms during connection recovery

### 2. Frontend Issues (datafeed.js)

#### Issue E: Weak Reconnection Logic (Line 649-651)
```javascript
if (typeof eel?.change_asset === 'function') {
    safeEelCall(eel.change_asset, AppState.currentAsset);
}
```
- `change_asset` doesn't actually restart data stream
- It just switches the asset being monitored
- If already on same asset, nothing happens
- No actual reconnection trigger

**Fix:** Call backend's `reconnect()` or `restart_realtime()` function

#### Issue F: No Visual Feedback for Frozen Chart
- Toast shows "Connection lost, reconnecting..." but disappears after 3.5 seconds
- Chart countdown timer keeps animating with old price
- User can't tell if chart is frozen or just slow

**Fix:** Add overlay or dim chart, disable countdown animation during disconnection

#### Issue G: No Auto-Refresh After Recovery
- When connection restored, frontend still holds stale candle data
- No mechanism to force full chart refresh on reconnection
- Indicators keep using old data

**Fix:** Force `AppState.needsFullRedraw = true` when connection restored

#### Issue H: Countdown Timer Bug (Line 312-320)
```javascript
function updateCountdown(candle) {
    if (!candle || !window.candleSeries) return;
    const label = ensureCountdownLabel();
    if (label) {
        label.candleEndTime = candle.time + AppState.timeframeSeconds;
        animateCountdown(candle.close);
    }
}
```
- Countdown updates only on NEW candle
- If connection dead, no new candle = countdown keeps showing stale price indefinitely
- Creates visual impression that system is "hanging"

**Fix:** Pause countdown animation when connection unhealthy

## Summary of Impacts

| Issue | Backend/Frontend | Symptom | Delay |
|-------|-----------------|---------|-------|
| Slow zombie detection | Backend | Takes 90s to notice | 90 seconds |
| Delayed reconnection | Backend | 8 timeouts + backoff | 14+ seconds |
| Queue overflow | Backend | Stale data in UI | Variable |
| Weak reconnection call | Frontend | Doesn't trigger actual reconnect | Immediate |
| No visual feedback | Frontend | Confusing to user | Immediate |
| Frozen countdown | Frontend | Looks like hang | Immediate |

**Total time to recovery: 90+ seconds** (backend detection + 14+ second retry + frontend recovery)

## Recommended Fixes (Priority Order)

### HIGH PRIORITY (Fixes chart freeze)
1. Reduce TICK_IDLE_THRESHOLD to 30 seconds
2. Implement proper reconnect() endpoint in backend
3. Call reconnect() instead of change_asset() on connection loss
4. Force full chart refresh on connection recovery

### MEDIUM PRIORITY (Improves UX)
5. Pause countdown animation during disconnection
6. Keep "Connection lost" toast visible until restored
7. Reduce rate limit to 250ms during recovery
8. Dim/overlay chart during disconnection

### LOW PRIORITY (Polish)
9. Add connection status indicator to toolbar
10. Log queue overflow events to frontend for visibility
11. Add "Force Reconnect" button for manual recovery

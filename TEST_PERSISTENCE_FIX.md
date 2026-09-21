# Test & Verify Automation State Persistence

## Quick Test Checklist

### Test 1: Configuration Persistence
**Objective**: Verify trading configuration is saved to disk

1. Open the application
2. Edit some trading configuration (risk percentage, max trades, etc.)
3. Click "Save Configuration"
4. Look for `trading_config.json` in the project root
5. Close the application
6. Reopen the application
7. ✅ **Pass**: Configuration should be restored to your previous values

### Test 2: Automation State Persistence  
**Objective**: Verify automation enable/disable state is saved

1. Open the application
2. Click "Enable Automation"
3. Look for `automation_state.json` in the project root
4. Verify it contains: `{"enabled": true, "timestamp": "..."}`
5. Close the application
6. Reopen the application
7. ✅ **Pass**: Check `automation_state.json` - it should still show enabled=true

### Test 3: Check Automation Diagnostics
**Objective**: Verify the diagnostic endpoint is working

1. Open browser console (F12)
2. Run this JavaScript:
```javascript
eel.get_automation_diagnostics()(result => {
    console.log("Automation Diagnostics:", result);
});
```

3. ✅ **Pass**: Should see output like:
```json
{
  "manager_initialized": true,
  "automation_enabled": true,
  "persisted_state": true,
  "selected_pairs": ["EUR/USD (OTC)", "CHF/JPY", ...],
  "signal_threads_running": 8,
  "signal_threads_total": 8,
  "constraint_status": { "balances": {...} }
}
```

### Test 4: Detect Why Automation Is Disabling
**Objective**: If automation disables, find out why

1. Enable Automation
2. Immediately check `automation_state.json` - should show `enabled: true`
3. Wait 5 seconds and check logs - look for error messages
4. Run:
```javascript
eel.get_automation_diagnostics()(result => {
    console.log(JSON.stringify(result, null, 2));
});
```

5. Look for:
   - ❌ `"manager_initialized": false` → Manager not initialized
   - ❌ `"automation_enabled": false` → Automation disabled
   - ❌ `"signal_threads_running": 0` → No signal threads active
   - ⚠️ `"constraint_status"` with halt reason → Account constraints blocking trades

## Common Issues & Solutions

### Issue: "Automation shows DISABLED immediately after enabling"

**Cause**: Usually one of:
1. No selected pairs loaded
2. Signal generation threads failed to start
3. Account constraints preventing trading

**Solution**:
1. Check `get_automation_diagnostics()` output
2. Check console logs for error messages
3. Verify `selected_signal_pairs.json` exists and has pairs
4. Check `get_automation_status()` for constraint violations

### Issue: "Configuration resets to defaults after restart"

**Cause**: `trading_config.json` failed to save

**Solution**:
1. Check file permissions on project directory
2. Verify `trading_config.json` exists
3. Check disk space
4. Look at console for save errors

### Issue: "automation_state.json shows enabled but UI shows DISABLED"

**Cause**: Automation was disabled after being saved

**Solution**:
1. Check logs for what caused disable
2. Run diagnostics to see current status
3. Manually enable again
4. Watch logs for failures

## Files to Check

| File | Purpose | Check When |
|------|---------|-----------|
| `trading_config.json` | Persisted trading settings | Configuration not loading |
| `automation_state.json` | Last automation state | State not persisting |
| `engine.log` | Backend logs | Automation crashes |
| `engine_error.log` | Error messages | Something failing silently |

## Enable More Verbose Logging

In `engine.py`, add this to track automation state changes:

```python
log(f"DEBUG: Before enable - is_enabled={AUTO_TRADING_MANAGER.is_enabled}", 1)
# ... enable code ...
log(f"DEBUG: After enable - is_enabled={AUTO_TRADING_MANAGER.is_enabled}", 1)
```

## Next Steps After Verification

Once these tests pass:

1. ✅ Configuration persists across app restarts
2. ✅ Automation state is saved and recoverable
3. ✅ You can diagnose automation issues via diagnostics endpoint
4. ✅ You have visibility into why automation might be disabling

## Related Fix

This complements the **Demo Balance Fix** which ensures:
- Demo balance decrements properly with each trade
- Trades are constrained by available demo balance
- No unlimited demo trading possible

Both fixes working together = **stable, predictable automated trading**.

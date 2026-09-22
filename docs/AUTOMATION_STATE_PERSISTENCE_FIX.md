# Automation State Persistence & Configuration Fix

## Problems Identified

1. **Configuration Not Persisted**: Trading configuration was only stored in memory. When the application restarted, all settings were lost.

2. **Automation State Not Saved**: When automation was enabled/disabled, the state wasn't persisted to disk. This made it impossible to restore automation state after restart.

3. **Automation Auto-Disabling**: When you clicked "Enable Automation", it would show as enabled briefly, then disable. The UI was refreshing every 5 seconds and showing the actual backend state, which might have been disabled due to an error.

4. **No Error Visibility**: There was no way to see why automation was disabling or what errors occurred.

## Solutions Implemented

### 1. Configuration Persistence (`trading_config.py`)

Added JSON file-based persistence for trading configuration:

```python
# Load configuration from disk on startup
load_config()  # Loads from trading_config.json if exists

# Save configuration to disk
persist_config(TRADING_CONFIG)  # Writes to trading_config.json
```

When you edit trading configuration:
- Settings are saved to memory AND written to `trading_config.json`
- On app restart, configuration is automatically loaded from disk
- Configuration survives application crashes/restarts

### 2. Automation State Persistence (`trading_config.py`)

Added automation enable/disable state tracking:

```python
# Save automation state
persist_automation_state(True)   # When enabling
persist_automation_state(False)  # When disabling

# Load automation state on startup
initial_state = load_automation_state()  # Reads from automation_state.json
```

When you enable/disable automation:
- State is persisted to `automation_state.json`
- Timestamp of change is recorded
- On app restart, you can check the last known state

### 3. Enhanced Error Visibility (`engine.py`)

Added new diagnostic endpoint:

```python
@eel.expose
def get_automation_diagnostics():
    # Returns detailed status including:
    # - Is manager initialized?
    # - Is automation currently enabled?
    # - What's the persisted state?
    # - How many signal threads are running?
    # - What are the constraint statuses?
```

### 4. Improved Enable/Disable Logging

Both `enable_automation()` and `disable_automation()` now:
- Persist the state to disk
- Log detailed information about what's happening
- Report any errors that occur

## Files Modified

### `trading_config.py`
- ✅ Added `load_config()` - loads from disk on startup
- ✅ Added `persist_config()` - saves to `trading_config.json`
- ✅ Added `load_automation_state()` - loads from disk
- ✅ Added `persist_automation_state()` - saves to `automation_state.json`
- ✅ Updated `save_trading_config()` - now persists to disk
- ✅ Auto-load configuration on module import

### `engine.py`
- ✅ Updated `enable_automation()` - persists state
- ✅ Updated `disable_automation()` - persists state
- ✅ Added `get_automation_diagnostics()` - shows detailed status

## Configuration Files Created

When you save configuration or enable/disable automation, these files are created:

### `trading_config.json`
```json
{
  "riskPercent": 2.0,
  "maxPositionPercent": 10.0,
  "minTradeAmount": 1.0,
  "timeframe": "1m",
  "minTimeBetweenTrades": 5,
  "maxTradesPerDay": 100,
  "startHour": 0,
  "endHour": 23,
  "minConfidence": 50,
  "targetReturn": 2.5,
  "dailyLossLimit": 500,
  "maxDrawdown": 20,
  "selectedPairs": ["EUR/USD (OTC)", "CHF/JPY", ...]
}
```

### `automation_state.json`
```json
{
  "enabled": true,
  "timestamp": "2026-09-21 10:30:45.123456"
}
```

## Usage

### Saving Configuration
Configuration is automatically saved to disk when you:
1. Click "Save Configuration" in the UI
2. Edit any trading parameters

### Enabling/Disabling Automation
When you toggle automation:
1. State is immediately saved to `automation_state.json`
2. You can see the persisted state via `get_automation_diagnostics()`

### Checking Automation Health
Call the new diagnostic endpoint:
```python
diagnostics = get_automation_diagnostics()
# Returns:
# {
#   "manager_initialized": true,
#   "automation_enabled": true,
#   "persisted_state": true,
#   "selected_pairs": ["EUR/USD (OTC)", ...],
#   "signal_threads_running": 8,
#   "signal_threads_total": 8,
#   "constraint_status": {...}
# }
```

## Troubleshooting

If automation keeps disabling:

1. **Check the logs** - Look at console output for error messages
2. **Run diagnostics** - Call `get_automation_diagnostics()` to see what's failing
3. **Check persisted state** - Look at `automation_state.json` to see the last known state
4. **Verify selected pairs** - Make sure pairs are properly loaded from `selected_signal_pairs.json`
5. **Check constraints** - Verify account balance and daily limits aren't preventing trades

## Related Issues Fixed

This fix addresses:
- ❌ Configuration lost on restart
- ❌ Automation state not persisted
- ❌ Automation unexpectedly disabling
- ❌ No visibility into automation errors
- ✅ Demo balance tracking (from previous fix)

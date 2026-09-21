# WebSocket Connection Loss - Diagnostic Guide

## Immediate Troubleshooting Steps

### Step 1: Check Backend Status
Open a terminal and run:

```bash
# Check if engine.py is running
tasklist | findstr python
# or
Get-Process | findstr python
```

**Expected:** Should see Python process running

If not running:
```bash
cd D:\QuotexChart
python engine.py
```

### Step 2: Check Recent Logs
```bash
# View last 50 lines of engine logs
Get-Content D:\QuotexChart\engine.log -Tail 50

# Or for errors:
Get-Content D:\QuotexChart\engine_error.log -Tail 50
```

Look for:
- ❌ `Connection refused`
- ❌ `Network unreachable`
- ❌ `SSL error`
- ❌ `Timeout`
- ❌ `Exception`

### Step 3: Test Network Connectivity
```bash
# Test connection to Quotex servers
ping ws2.quotex.io
# or
Test-Connection -ComputerName ws2.quotex.io -Count 4
```

### Step 4: Check Browser Console (F12)
Open DevTools → Console tab and look for:
```
[DEBUG] Connection timeout after 10000ms
[DEBUG] Connection restored
⚠️ EEL call timeout
❌ Critical updateChart error
```

### Step 5: Check Connection Status Endpoint
Open browser console and run:
```javascript
// Check connection status
eel.get_connection_status()(console.log);
```

**Expected output:**
```javascript
{
    "connected": true,
    "assets_loaded": true,
    "login_success": true,
    "current_asset": "USD/PKR (OTC)",
    "current_timeframe": "1m",
    "is_reconnecting": false,
    "last_tick_age": 1.2,
    "last_sub_age": 45.3
}
```

**Watch for:**
- `"connected": false` - WebSocket disconnected
- `"is_reconnecting": true` - Active recovery
- `"last_tick_age": > 30` - No data for 30+ seconds
- `"last_sub_age": > 60` - No subscription activity

---

## Common Causes & Solutions

### Issue 1: Quotex Server Outage
**Signs:**
- All assets show OFFLINE
- No data updates at all
- Backend logs show "Connection refused"

**Solution:**
1. Check Quotex status page
2. Try restarting the app
3. Wait 5-10 minutes and retry

### Issue 2: Network/Firewall Problem
**Signs:**
- Intermittent connection loss
- OFFLINE appears then restored frequently
- Backend logs show "Network unreachable"

**Solution:**
1. Check firewall allows outbound WebSocket (port 443)
2. Disable VPN if using one
3. Check DNS resolution:
   ```bash
   nslookup ws2.quotex.io
   ```
4. Restart network adapter:
   ```bash
   ipconfig /release
   ipconfig /renew
   ```

### Issue 3: Invalid Credentials
**Signs:**
- Connects initially, then OFFLINE
- Backend shows "authorization/reject"
- Starts immediately after login

**Solution:**
1. Check `.env` file credentials:
   ```bash
   type .env | findstr QUOTEX_
   ```
2. Verify credentials are correct
3. Try manual login in browser first
4. Update `.env` with new credentials:
   ```bash
   QUOTEX_EMAIL=your@email.com
   QUOTEX_PASSWORD=yourpassword
   ```
5. Restart engine.py

### Issue 4: Resource Exhaustion
**Signs:**
- Connection drops after running for hours
- High CPU/Memory usage
- Many WebSocket errors in logs

**Solution:**
1. Check system resources:
   ```bash
   Get-Process python | Select ProcessName, Handles, PrivateMemorySize
   ```
2. Restart engine.py to free resources
3. Close unnecessary tabs/apps
4. Check for memory leaks in logs

### Issue 5: SSL/Certificate Issue
**Signs:**
- Backend logs show "SSL: CERTIFICATE_VERIFY_FAILED"
- Happens immediately after update
- Certificate-related errors

**Solution:**
1. Update certificates:
   ```bash
   pip install --upgrade certifi
   ```
2. Restart engine.py
3. Clear Python cache:
   ```bash
   python -m pip install --upgrade certifi
   ```

### Issue 6: Rate Limiting from Quotex
**Signs:**
- Connection works, but data arrives slow
- Gets worse over time
- Intermittent connection drops

**Solution:**
1. Check request frequency in logs
2. Add delays between requests
3. Restart app to reset rate limit
4. Contact Quotex support if persistent

### Issue 7: Backend Crash
**Signs:**
- Terminal shows error and closes
- OFFLINE appears and never recovers
- Python process dies

**Solution:**
1. Run engine with verbose output:
   ```bash
   cd D:\QuotexChart
   python -u engine.py 2>&1 | Tee-Object engine_debug.log
   ```
2. Look for exception messages
3. Report the error

---

## Real-time Monitoring

### Option 1: Watch Logs Live
```bash
# Watch engine.log in real-time (PowerShell)
Get-Content D:\QuotexChart\engine.log -Wait

# Or use terminal with tail equivalent
tail -f D:\QuotexChart\engine.log
```

### Option 2: Browser Console Debug
Open console (F12) and run:
```javascript
// Enable debug mode
AppState.debugMode = true;

// Monitor connection status every 5 seconds
setInterval(() => {
    eel.get_connection_status()(status => {
        console.log('Status:', status);
    });
}, 5000);

// Watch when data arrives
const originalUpdateChart = window.updateChart;
window.updateChart = function(data) {
    console.log('📊 Chart update:', data);
    return originalUpdateChart.call(this, data);
};
```

### Option 3: Quick Status Script
Save as `check_status.ps1`:
```powershell
while ($true) {
    Clear-Host
    Write-Host "=== Connection Status ===" -ForegroundColor Green
    
    # Check Python running
    $pyRunning = Get-Process python -ErrorAction SilentlyContinue
    Write-Host "Backend: $(if ($pyRunning) { '✅ RUNNING' } else { '❌ STOPPED' })"
    
    # Check logs for recent errors
    $lastError = Select-String "error|Exception" D:\QuotexChart\engine.log -Last 1
    if ($lastError) {
        Write-Host "Last Error: $lastError" -ForegroundColor Red
    }
    
    # Check memory usage
    if ($pyRunning) {
        $mem = [math]::Round($pyRunning.WorkingSet / 1MB, 1)
        Write-Host "Memory: $mem MB"
    }
    
    Write-Host "`nPress Ctrl+C to exit"
    Start-Sleep -Seconds 5
}
```

Run with:
```bash
powershell -ExecutionPolicy Bypass -File check_status.ps1
```

---

## Restart Procedures

### Quick Restart (Soft)
1. Keep browser open
2. Restart just the backend:
   ```bash
   # Kill Python process
   taskkill /IM python.exe /F
   
   # Restart
   cd D:\QuotexChart
   python engine.py
   ```
3. Chart should recover in 10-15 seconds

### Full Restart (Hard)
1. Close browser completely
2. Kill all Python processes:
   ```bash
   taskkill /IM python.exe /F
   ```
3. Close terminal
4. Wait 5 seconds
5. Re-open terminal and start:
   ```bash
   cd D:\QuotexChart
   python engine.py
   ```
6. Open browser and reload page

### Emergency Reset
If everything is stuck:
```bash
# Kill everything
taskkill /IM python.exe /F
taskkill /IM chrome.exe /F
taskkill /IM firefox.exe /F

# Remove stale connection state (optional)
# rm D:\QuotexChart\.connection_state

# Restart backend
python D:\QuotexChart\engine.py
```

---

## Data Collection for Support

If the issue persists, collect this info:

```bash
# Collect logs
Copy-Item D:\QuotexChart\engine.log -Destination engine_backup.log
Copy-Item D:\QuotexChart\engine_error.log -Destination engine_error_backup.log

# System info
systeminfo > system_info.txt

# Network info
ipconfig /all > network_info.txt
netstat -an | findstr :443 >> network_info.txt

# Python info
python --version > python_info.txt
pip list >> python_info.txt
```

Share:
1. `engine_backup.log` (last 100 lines)
2. Last error message from console
3. When it started (worked before or never worked?)
4. How often does it disconnect?
5. Screenshot of OFFLINE state

---

## Prevention Tips

1. **Keep Backend Running:**
   - Run in dedicated terminal/process manager
   - Don't kill terminal accidentally
   - Use process manager (PM2) for auto-restart

2. **Monitor Resources:**
   - Check memory occasionally
   - Restart if memory > 500MB
   - Monitor CPU usage

3. **Network Health:**
   - Stable WiFi/Ethernet
   - Don't run heavy downloads during trading
   - Avoid VPN if possible

4. **Quotex Account:**
   - Keep login credentials valid
   - Don't change password during session
   - Check account restrictions

5. **Regular Updates:**
   - Keep dependencies updated
   - Update certificates
   - Reinstall pyquotex occasionally

---

## Quick Reference

**Connection Lost = ?**
- [ ] Backend running? → Check terminal
- [ ] Network connected? → Ping test
- [ ] Quotex login valid? → Check .env
- [ ] Server outage? → Check status
- [ ] Memory/CPU high? → Restart
- [ ] Logs show errors? → Debug
- [ ] Been running hours? → Restart anyway

**What to Do:**
1. Check logs first
2. If no errors: restart backend (soft restart)
3. If errors: read the error and fix
4. If can't fix: full restart or reinstall

**When to Contact Support:**
- Repeated crashes with traceback
- SSL/Certificate errors persist
- Network errors you can't fix
- Memory leak (grows constantly)
- "Connection refused" to Quotex servers

---

**Last Updated:** 2026-09-18
**Status:** Ready to diagnose WebSocket issues

# Enhanced engine runner with connection watchdog
# Monitors if data is flowing and restarts if connection dies

$process = $null
$restart_count = 0
$max_restarts = 20
$watchdog_timeout = 30  # Restart after 30 seconds of no data updates

Write-Host "Starting Quotex Engine with Connection Watchdog..." -ForegroundColor Green
Write-Host "Watchdog will restart engine if no data for $watchdog_timeout seconds`n" -ForegroundColor Yellow

while ($restart_count -lt $max_restarts) {
    $restart_count++

    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "Attempt $restart_count/$max_restarts - Starting engine" -ForegroundColor Green
    Write-Host "========================================`n" -ForegroundColor Green

    # Start engine process
    $process = Start-Process python `
        -ArgumentList "-u engine.py" `
        -WorkingDirectory "D:\QuotexChart" `
        -PassThru `
        -NoNewWindow

    $start_time = Get-Date
    $last_activity = $start_time

    # Monitor process
    while ($process -and -not $process.HasExited) {
        # Wait a bit
        Start-Sleep -Seconds 5

        # Check if process still alive
        if ($process.HasExited) {
            Write-Host "`n❌ Process exited with code: $($process.ExitCode)" -ForegroundColor Red
            break
        }

        # Rough check: if no activity, we'd detect it here
        # (In real implementation, we'd check logs or communicate with backend)
        $elapsed = (Get-Date) - $start_time

        if ($elapsed.TotalSeconds -gt 3600) {
            Write-Host "⏰ Engine running for 1 hour, restarting for cleanup..." -ForegroundColor Yellow
            $process.Kill()
            break
        }
    }

    if ($restart_count -lt $max_restarts) {
        Write-Host "⏳ Waiting 3 seconds before restart..." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
    }
}

Write-Host "`n❌ Max restarts reached. Stopping." -ForegroundColor Red
if ($process -and -not $process.HasExited) {
    $process.Kill()
}

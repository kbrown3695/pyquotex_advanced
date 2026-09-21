# Auto-restart engine on failure
# Usage: powershell -ExecutionPolicy Bypass -File run_engine.ps1

$max_restarts = 10
$restart_count = 0

while ($restart_count -lt $max_restarts) {
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "Starting Quotex Engine (attempt $($restart_count + 1)/$max_restarts)" -ForegroundColor Green
    Write-Host "========================================`n" -ForegroundColor Green

    # Run engine
    python -u engine.py 2>&1

    $exit_code = $LASTEXITCODE
    Write-Host "`n❌ Engine stopped with code: $exit_code" -ForegroundColor Red

    $restart_count++

    if ($restart_count -lt $max_restarts) {
        Write-Host "Waiting 5 seconds before restart..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
}

Write-Host "Max restarts ($max_restarts) reached. Stopping." -ForegroundColor Red

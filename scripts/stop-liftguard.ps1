# Stops the backend and frontend started by scripts/start-liftguard.ps1.
$ErrorActionPreference = "Continue"
$Root  = Split-Path -Parent $PSScriptRoot
$State = Join-Path $Root ".liftguard"

foreach ($name in @("frontend", "backend")) {
    $pidFile = Join-Path $State "$name.pid"
    if (-not (Test-Path $pidFile)) {
        Write-Host "[liftguard] $name was not started by the launcher (nothing to stop)"
        continue
    }
    $procId = (Get-Content $pidFile -Raw).Trim()
    if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
        # /T stops the whole tree: npm -> node -> next-server, python -> uvicorn workers.
        & taskkill.exe /PID $procId /T /F | Out-Null
        Write-Host "[liftguard] Stopped $name"
    } else {
        Write-Host "[liftguard] $name was not running"
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

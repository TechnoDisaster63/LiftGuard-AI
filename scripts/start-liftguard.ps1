# One-click LiftGuard for Windows. Run via START-LIFTGUARD.bat.
#
# 1. Checks for Python 3.11 and Node.js, and says where to get them if missing.
# 2. First run: creates backend\.venv and installs the Python packages
#    (MediaPipe, OpenCV, PyTorch - several minutes), then the dashboard's
#    npm packages. Later runs skip this unless the requirements changed.
# 3. Starts the backend (127.0.0.1:8000) and the dashboard (localhost:3000)
#    in the background, waits for /api/health, then opens the browser.
#
# Logs: .liftguard\backend.log and .liftguard\frontend.log
param([switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$Root         = Split-Path -Parent $PSScriptRoot
$State        = Join-Path $Root ".liftguard"
$Backend      = Join-Path $Root "backend"
$Frontend     = Join-Path $Root "frontend"
$Venv         = Join-Path $Backend ".venv"
$VenvPython   = Join-Path $Venv "Scripts\python.exe"
$BackendPort  = if ($env:LIFTGUARD_BACKEND_PORT)  { $env:LIFTGUARD_BACKEND_PORT }  else { "8000" }
$FrontendPort = if ($env:LIFTGUARD_FRONTEND_PORT) { $env:LIFTGUARD_FRONTEND_PORT } else { "3000" }
New-Item -ItemType Directory -Force -Path $State | Out-Null

function Say($msg)  { Write-Host "[liftguard] $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "[liftguard] $msg" -ForegroundColor Red; exit 1 }

function Test-Http($url) {
    try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true }
    catch { return $false }
}

function Find-Python {
    # The py launcher ships with the python.org installer.
    foreach ($candidate in @(@("py", "-3.11"), @("py", "-3.12"), @("python"))) {
        $exe = $candidate[0]; $pyArgs = @($candidate | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try { $ver = (& $exe @pyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null) } catch { continue }
        if ($ver -in @("3.11", "3.12")) { return @($exe) + $pyArgs }
    }
    Fail "Python 3.11 not found. Install it from https://www.python.org/downloads/release/python-3119/ (tick 'Add python.exe to PATH'), then run START-LIFTGUARD.bat again."
}

function Install-Backend {
    if (-not (Test-Path $VenvPython)) {
        $py = @(Find-Python)   # @() keeps a one-item result ("python") an array
        Say "Creating the backend environment (backend\.venv)"
        $pyArgs = @($py | Select-Object -Skip 1)
        & $py[0] @pyArgs -m venv $Venv
        if ($LASTEXITCODE -ne 0) { Fail "Couldn't create backend\.venv." }
    }
    $want  = (Get-FileHash (Join-Path $Backend "requirements.txt")).Hash
    $stamp = Join-Path $Venv ".liftguard-requirements"
    if (-not (Test-Path $stamp) -or (Get-Content $stamp -Raw).Trim() -ne $want) {
        Say "Installing backend packages - the first run takes several minutes"
        & $VenvPython -m pip install --quiet --upgrade pip
        & $VenvPython -m pip install --quiet -r (Join-Path $Backend "requirements.txt")
        if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Scroll up for the package that failed." }
        Set-Content -Path $stamp -Value $want -NoNewline
    }
}

function Install-Frontend {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        Fail "Node.js not found. Install Node 20 LTS from https://nodejs.org, then run START-LIFTGUARD.bat again."
    }
    $want    = (Get-FileHash (Join-Path $Frontend "package-lock.json")).Hash
    $modules = Join-Path $Frontend "node_modules"
    $stamp   = Join-Path $modules ".liftguard-lock"
    if (-not (Test-Path $stamp) -or (Get-Content $stamp -Raw).Trim() -ne $want) {
        Say "Installing dashboard packages"
        Push-Location $Frontend
        try { & npm.cmd ci --no-audit --no-fund --loglevel=error } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { Fail "npm ci failed. Scroll up for the error." }
        Set-Content -Path $stamp -Value $want -NoNewline
    }
}

function Start-Hidden($name, $dir, $exe, [string[]]$argList) {
    $log = Join-Path $State "$name.log"
    $proc = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $dir `
        -RedirectStandardOutput $log -RedirectStandardError (Join-Path $State "$name.err.log") `
        -WindowStyle Hidden -PassThru
    Set-Content -Path (Join-Path $State "$name.pid") -Value $proc.Id -NoNewline
    return $proc
}

function Wait-Http($url, $proc, $name, $seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (Test-Http $url) { return }
        if ($proc.HasExited) {
            Get-Content (Join-Path $State "$name.err.log") -Tail 25 -ErrorAction SilentlyContinue
            Fail "The $name stopped while starting. The last lines of .liftguard\$name.err.log are above."
        }
        Start-Sleep -Seconds 1
    }
    Fail "The $name didn't answer at $url within $seconds seconds. See .liftguard\$name.log."
}

Install-Backend
Install-Frontend

# Backend
$health = "http://127.0.0.1:$BackendPort/api/health"
if (Test-Http $health) {
    Say "Backend already running on port $BackendPort"
} else {
    Say "Starting backend on 127.0.0.1:$BackendPort"
    $b = Start-Hidden "backend" $Backend $VenvPython @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $BackendPort)
    Wait-Http $health $b "backend" 90
    Say "Backend healthy"
}

# Frontend (the browser calls the backend directly on localhost)
if (-not $env:NEXT_PUBLIC_API_BASE) { $env:NEXT_PUBLIC_API_BASE = "http://localhost:$BackendPort" }
$app = "http://localhost:$FrontendPort"
if (Test-Http "$app/") {
    Say "Dashboard already running on port $FrontendPort"
} else {
    Say "Starting dashboard on port $FrontendPort"
    $f = Start-Hidden "frontend" $Frontend "cmd.exe" @("/c", "npm.cmd", "run", "dev", "--", "-p", $FrontendPort)
    Wait-Http "$app/" $f "frontend" 120
    # The dev server compiles each page on first visit; do that now so the
    # first click in a demo doesn't wait.
    Say "Preparing pages"
    foreach ($page in @("dashboard", "live", "register", "users", "sessions", "reports", "settings")) {
        try { Invoke-WebRequest -Uri "$app/$page" -UseBasicParsing -TimeoutSec 90 | Out-Null } catch { }
    }
}

Say "LiftGuard is running at $app"
if (-not $NoBrowser) { Start-Process $app }
Write-Host ""
Write-Host "Logs are in the .liftguard folder. Press Enter here to stop LiftGuard," -ForegroundColor Green
Write-Host "or close this window and run STOP-LIFTGUARD.bat later." -ForegroundColor Green
[void](Read-Host)
& (Join-Path $PSScriptRoot "stop-liftguard.ps1")

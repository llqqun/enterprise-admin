# start.ps1 - bring up MySQL (if needed) plus the backend and the frontend.
# ASCII-only on purpose (see init.ps1 for the reason).

param(
    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoFrontend,
    [switch]$NoBackend
)

$ErrorActionPreference = 'Continue'

$projectRoot = $PSScriptRoot
$backendDir  = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$python      = Join-Path $backendDir '.venv\Scripts\python.exe'
$mysqlCtl    = Join-Path $projectRoot 'tools\mysql-ctl.ps1'

function Write-Step([string]$Message) {
    Write-Host ("[start] " + $Message) -ForegroundColor Cyan
}

function Write-Fail([string]$Message) {
    Write-Host ("[start] ERROR: " + $Message) -ForegroundColor Red
}

function Test-PortOpen {
    param([int]$Port, [string]$TargetHost = '127.0.0.1')
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($TargetHost, $Port, $null, $null)
        $signalled = $iar.AsyncWaitHandle.WaitOne(500, $false)
        if ($signalled) { $client.EndConnect($iar) }
        return $signalled
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-Port {
    param([int]$Port, [int]$TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -Port $Port) { return $true }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Test-Prerequisites {
    if (-not (Test-Path -LiteralPath $python)) {
        Write-Fail "backend virtualenv not found: $python"
        Write-Fail "Run: powershell -ExecutionPolicy Bypass -File init.ps1"
        exit 1
    }
    if (-not (Test-Path -LiteralPath (Join-Path $backendDir '.env'))) {
        Write-Fail "backend\.env not found - it holds SECRET_KEY and the DB credentials."
        Write-Fail "Run: powershell -ExecutionPolicy Bypass -File init.ps1"
        exit 1
    }
    if (-not $NoFrontend -and -not (Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules'))) {
        Write-Fail "frontend dependencies are not installed."
        Write-Fail "Run: cd frontend; npm install"
        exit 1
    }
}

Test-Prerequisites

# ---------------------------------------------------------------------------
# 1. MySQL
# ---------------------------------------------------------------------------
Write-Step "ensuring MySQL is running"
& powershell -ExecutionPolicy Bypass -File $mysqlCtl -Action start | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Fail "MySQL did not start. Check D:\devtools\mysql-logs\error.log"
    exit 1
}

# ---------------------------------------------------------------------------
# 2. backend
# ---------------------------------------------------------------------------
if ($NoBackend) {
    Write-Step "skipping the backend (-NoBackend)"
} elseif (Test-PortOpen -Port $BackendPort) {
    Write-Step "something is already listening on $BackendPort, leaving it alone"
} else {
    Write-Step "starting the API on port $BackendPort (own window, Ctrl+C there to stop)"
    Start-Process -FilePath 'powershell' -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location -LiteralPath '$backendDir'; & '$python' -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
    ) | Out-Null

    if (-not (Wait-Port -Port $BackendPort -TimeoutSeconds 60)) {
        Write-Fail "the API did not come up within 60s"
        Write-Fail "Start it by hand to see why: cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --port $BackendPort"
        exit 1
    }
    Write-Step "API is up"
}

# ---------------------------------------------------------------------------
# 3. frontend
# ---------------------------------------------------------------------------
if ($NoFrontend) {
    Write-Step "skipping the frontend (-NoFrontend)"
} elseif (Test-PortOpen -Port $FrontendPort) {
    Write-Step "something is already listening on $FrontendPort, leaving it alone"
} else {
    Write-Step "starting Vite on port $FrontendPort (own window)"
    # Run Vite's entry point directly rather than through `npm run dev`: npm would
    # add a process layer that stop.ps1 then has to chase down.
    Start-Process -FilePath 'powershell' -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location -LiteralPath '$frontendDir'; node node_modules/vite/bin/vite.js --host 127.0.0.1 --port $FrontendPort"
    ) | Out-Null

    if (-not (Wait-Port -Port $FrontendPort -TimeoutSeconds 60)) {
        Write-Fail "Vite did not come up within 60s"
        exit 1
    }
    Write-Step "frontend is up"
}

# ---------------------------------------------------------------------------
# 4. what to do next
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host 'enterprise-admin is running' -ForegroundColor Green
Write-Host ("  Web UI     http://127.0.0.1:$FrontendPort")
Write-Host ("  API docs   http://127.0.0.1:$BackendPort/docs")
Write-Host ("  Health     http://127.0.0.1:$BackendPort/health")
Write-Host ''
Write-Host 'Demo accounts (change them before any real deployment):'
Write-Host '  admin    / Admin@123456   superuser, sees every menu'
Write-Host '  manager  / Manager@123    department manager, sees a subset'
Write-Host '  staff    / Staff@123      no menu permissions (empty sidebar by design)'
Write-Host '  nobody   / Nobody@123     no menu permissions'
Write-Host ''
Write-Host 'Stop everything with: powershell -ExecutionPolicy Bypass -File stop.ps1'
Write-Host ''

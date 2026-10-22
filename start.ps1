# start.ps1 - start MySQL, the API and the frontend, together or one at a time.
# ASCII-only on purpose (see init.ps1 for the reason).
#
#   start.ps1                  all three (MySQL is started if it is not running)
#   start.ps1 -Only db         MySQL only
#   start.ps1 -Only backend    API only - does NOT touch MySQL
#   start.ps1 -Only frontend   Vite only
#   start.ps1 -Only backend -BackendPort 8100

param(
    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173,
    [ValidateSet('all', 'db', 'backend', 'frontend')]
    [string]$Only = 'all',
    [switch]$NoFrontend,
    [switch]$NoBackend
)

$ErrorActionPreference = 'Continue'

$projectRoot = $PSScriptRoot
$backendDir  = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$python      = Join-Path $backendDir '.venv\Scripts\python.exe'
$mysqlCtl    = Join-Path $projectRoot 'tools\mysql-ctl.ps1'

# Resolve what to do. -Only wins; the older -NoBackend / -NoFrontend switches still work.
$wantDb       = ($Only -eq 'all') -or ($Only -eq 'db')
$wantBackend  = (($Only -eq 'all') -or ($Only -eq 'backend')) -and (-not $NoBackend)
$wantFrontend = (($Only -eq 'all') -or ($Only -eq 'frontend')) -and (-not $NoFrontend)

function Write-Step([string]$Message) {
    Write-Host ("[start] " + $Message) -ForegroundColor Cyan
}

function Write-Fail([string]$Message) {
    Write-Host ("[start] ERROR: " + $Message) -ForegroundColor Red
}

function Write-Note([string]$Message) {
    Write-Host ("[start] " + $Message) -ForegroundColor DarkGray
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

# Prerequisites are checked only for the pieces we are about to start, so
# `-Only frontend` works on a machine where the Python venv was never created.
if ($wantBackend) {
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
}

if ($wantFrontend -and -not (Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules'))) {
    Write-Fail "frontend dependencies are not installed."
    Write-Fail "Run: cd frontend; npm install"
    exit 1
}

if (-not ($wantDb -or $wantBackend -or $wantFrontend)) {
    Write-Fail "nothing to do (Only=$Only, NoBackend=$NoBackend, NoFrontend=$NoFrontend)"
    exit 1
}

# ---------------------------------------------------------------------------
# 1. MySQL
# ---------------------------------------------------------------------------
if ($wantDb) {
    Write-Step "ensuring MySQL is running"
    & powershell -ExecutionPolicy Bypass -File $mysqlCtl -Action start | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "MySQL did not start. Check D:\devtools\mysql-logs\error.log"
        exit 1
    }
} else {
    # Deliberately not starting MySQL: the whole point of -Only is that this
    # command touches nothing else. The API can boot with MySQL down; it will
    # report the failure on the first query instead of at import time.
    Write-Note "MySQL left alone (-Only $Only). Start it with: start.ps1 -Only db"
}

# ---------------------------------------------------------------------------
# 2. backend
# ---------------------------------------------------------------------------
if (-not $wantBackend) {
    if ($Only -ne 'db') { Write-Note "backend not started (Only=$Only)" }
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
if (-not $wantFrontend) {
    if ($Only -ne 'db') { Write-Note "frontend not started (Only=$Only)" }
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
# 4. what is actually listening now
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host 'Current state' -ForegroundColor Green
$dbState = if (Test-PortOpen -Port 3306) { 'up  ' } else { 'DOWN' }
Write-Host ("  MySQL   " + $dbState + "   127.0.0.1:3306")
$apiState = if (Test-PortOpen -Port $BackendPort) { 'up  ' } else { 'DOWN' }
Write-Host ("  API     " + $apiState + "   http://127.0.0.1:$BackendPort/docs")
$webState = if (Test-PortOpen -Port $FrontendPort) { 'up  ' } else { 'DOWN' }
Write-Host ("  Web     " + $webState + "   http://127.0.0.1:$FrontendPort")
Write-Host ''
if ($Only -eq 'all') {
    Write-Host 'Demo accounts (change them before any real deployment):'
    Write-Host '  admin    / Admin@123456   superuser, sees every menu'
    Write-Host '  manager  / Manager@123    department manager, sees a subset'
    Write-Host '  staff    / Staff@123      no menu permissions (empty sidebar by design)'
    Write-Host '  nobody   / Nobody@123     no menu permissions'
    Write-Host ''
}
Write-Host 'Status of all three : powershell -ExecutionPolicy Bypass -File status.ps1'
Write-Host 'Stop one of them    : powershell -ExecutionPolicy Bypass -File stop.ps1 -Only backend|frontend|db'
Write-Host ''

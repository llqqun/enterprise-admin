# status.ps1 - show what is running, right now, without starting or stopping anything.
# ASCII-only on purpose (see init.ps1 for the reason).

param(
    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Logs
)

$ErrorActionPreference = 'Continue'

$projectRoot = $PSScriptRoot
$backendDir  = Join-Path $projectRoot 'backend'
$mysqlCtl    = Join-Path $projectRoot 'tools\mysql-ctl.ps1'

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

function Get-PortOwner {
    param([int]$Port)
    $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -First 1
    if ($conn) { return $conn.OwningProcess }
    return $null
}

function Format-State {
    param([bool]$Up)
    if ($Up) { return 'UP' } else { return 'DOWN' }
}

Write-Host ''
Write-Host 'enterprise-admin - service status' -ForegroundColor Green
Write-Host ('-' * 62)

# MySQL ---------------------------------------------------------------------
$dbUp = Test-PortOpen -Port 3306
$dbPid = Get-PortOwner -Port 3306
Write-Host ('  {0,-8} {1,-6} {2,-6} {3}' -f 'MySQL', '3306', (Format-State $dbUp), $(if ($dbPid) { "pid $dbPid" } else { '-' })) -ForegroundColor $(if ($dbUp) { 'Green' } else { 'Red' })
if ($dbUp) {
    & powershell -ExecutionPolicy Bypass -File $mysqlCtl -Action status 2>&1 | ForEach-Object {
        if ($_ -match 'version') { Write-Host ('           ' + $_) }
    }
}

# API -----------------------------------------------------------------------
$apiUp = Test-PortOpen -Port $BackendPort
$apiPid = Get-PortOwner -Port $BackendPort
Write-Host ('  {0,-8} {1,-6} {2,-6} {3}' -f 'API', $BackendPort, (Format-State $apiUp), $(if ($apiPid) { "pid $apiPid" } else { '-' })) -ForegroundColor $(if ($apiUp) { 'Green' } else { 'Red' })
if ($apiUp) {
    try {
        $health = Invoke-RestMethod -Uri ("http://127.0.0.1:" + $BackendPort + '/health') -TimeoutSec 5
        $payload = $health | ConvertTo-Json -Compress
        Write-Host ('           /health -> ' + $payload)
    } catch {
        Write-Host '           /health -> did not answer' -ForegroundColor Yellow
    }
    # A DB-backed endpoint is the real test: /health does not touch MySQL.
    try {
        $null = Invoke-RestMethod -Uri ("http://127.0.0.1:" + $BackendPort + '/api/v1/auth/captchaImage') -TimeoutSec 5
        Write-Host '           DB path -> reachable'
    } catch {
        Write-Host '           DB path -> NOT reachable (MySQL down?)' -ForegroundColor Yellow
    }
}

# Web -----------------------------------------------------------------------
$webUp = Test-PortOpen -Port $FrontendPort
$webPid = Get-PortOwner -Port $FrontendPort
Write-Host ('  {0,-8} {1,-6} {2,-6} {3}' -f 'Web', $FrontendPort, (Format-State $webUp), $(if ($webPid) { "pid $webPid" } else { '-' })) -ForegroundColor $(if ($webUp) { 'Green' } else { 'Red' })

Write-Host ('-' * 62)
Write-Host ("  API docs   http://127.0.0.1:$BackendPort/docs")
Write-Host ("  Web UI     http://127.0.0.1:$FrontendPort")
Write-Host ''

# Optionally dump the newest backend log lines: the API runs in its own window,
# so this is the quickest way to see an error without switching to it.
if ($Logs) {
    $logDir = Join-Path $backendDir 'logs'
    if (Test-Path -LiteralPath $logDir) {
        $newest = Get-ChildItem -LiteralPath $logDir -Filter 'backend-*.log' -File |
                  Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($newest) {
            Write-Host ('Last 30 lines of ' + $newest.Name) -ForegroundColor Green
            Get-Content -LiteralPath $newest.FullName -Tail 30 -Encoding UTF8 | ForEach-Object { Write-Host ('  ' + $_) }
            Write-Host ''
        } else {
            Write-Host 'no backend log file yet' -ForegroundColor Yellow
        }
    } else {
        Write-Host ('log directory not found: ' + $logDir) -ForegroundColor Yellow
    }
}

# stop.ps1 - stop the API, the frontend and MySQL, together or one at a time.
# ASCII-only on purpose (see init.ps1 for the reason).
#
#   stop.ps1                   API and frontend (MySQL is left running)
#   stop.ps1 -IncludeMysql     all three
#   stop.ps1 -Only backend     API only
#   stop.ps1 -Only frontend    Vite only
#   stop.ps1 -Only db          MySQL only

param(
    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173,
    [ValidateSet('all', 'db', 'backend', 'frontend')]
    [string]$Only = 'all',
    [switch]$IncludeMysql
)

$ErrorActionPreference = 'Continue'

$projectRoot = $PSScriptRoot
$mysqlCtl    = Join-Path $projectRoot 'tools\mysql-ctl.ps1'

$wantBackend  = ($Only -eq 'all') -or ($Only -eq 'backend')
$wantFrontend = ($Only -eq 'all') -or ($Only -eq 'frontend')
# -IncludeMysql keeps its old meaning ("all, plus the database"); -Only db is the
# explicit way to say "just the database".
$wantDb = ($Only -eq 'db') -or (($Only -eq 'all') -and $IncludeMysql.IsPresent)

function Write-Step([string]$Message) {
    Write-Host ("[stop] " + $Message) -ForegroundColor Cyan
}

function Write-Note([string]$Message) {
    Write-Host ("[stop] " + $Message) -ForegroundColor DarkGray
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

function Get-PortOwner {
    param([int]$Port)
    $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -First 1
    if ($conn) { return $conn.OwningProcess }
    return $null
}

function Stop-PortOwner {
    param([int]$Port, [string]$Label)

    # Note: $pid is a read-only automatic variable in PowerShell, hence $ownerPid.
    $ownerPid = Get-PortOwner -Port $Port
    if (-not $ownerPid) {
        Write-Step "$Label not running (nothing on $Port)"
        return
    }

    # `python -m uvicorn` and `npm run dev` both leave a launcher process above the
    # real server, so the parent is collected as well when it looks like ours.
    $parentPid = (Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue).ParentProcessId

    & taskkill /PID $ownerPid /T /F 2>&1 | Out-Null
    Write-Step "$Label stopped (pid $ownerPid)"

    if ($parentPid) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$parentPid" -ErrorAction SilentlyContinue
        if ($parent -and $parent.CommandLine -match 'uvicorn|vite|npm') {
            & taskkill /PID $parentPid /T /F 2>&1 | Out-Null
            Write-Step "  launcher stopped (pid $parentPid)"
        }
    }
}

if ($wantFrontend) {
    Stop-PortOwner -Port $FrontendPort -Label 'frontend'
} else {
    Write-Note "frontend left running (Only=$Only)"
}

if ($wantBackend) {
    Stop-PortOwner -Port $BackendPort -Label 'API'
} else {
    Write-Note "API left running (Only=$Only)"
}

if ($wantDb) {
    Write-Step "stopping MySQL"
    & powershell -ExecutionPolicy Bypass -File $mysqlCtl -Action stop | Out-Host
} else {
    Write-Note "MySQL left running (use -Only db to stop it too)"
}

Write-Host ''
Write-Host 'Ports now:' -ForegroundColor Green
$checks = @(
    @{ Port = 3306;         Label = 'MySQL' },
    @{ Port = $BackendPort; Label = 'API' },
    @{ Port = $FrontendPort; Label = 'Web' }
)
foreach ($check in $checks) {
    $listening = Test-PortOpen -Port $check.Port
    Write-Host ("  {0,-8} {1,-6} {2}" -f $check.Label, $check.Port, $(if ($listening) { 'still listening' } else { 'free' }))
}
Write-Host ''

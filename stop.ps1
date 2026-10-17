# stop.ps1 - stop the API and the frontend, optionally MySQL too.
# ASCII-only on purpose (see init.ps1 for the reason).

param(
    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173,
    [switch]$IncludeMysql
)

$ErrorActionPreference = 'Continue'

$projectRoot = $PSScriptRoot
$mysqlCtl    = Join-Path $projectRoot 'tools\mysql-ctl.ps1'

function Write-Step([string]$Message) {
    Write-Host ("[stop] " + $Message) -ForegroundColor Cyan
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

Stop-PortOwner -Port $FrontendPort -Label 'frontend'
Stop-PortOwner -Port $BackendPort  -Label 'API'

if ($IncludeMysql) {
    Write-Step "stopping MySQL (-IncludeMysql)"
    & powershell -ExecutionPolicy Bypass -File $mysqlCtl -Action stop | Out-Host
} else {
    Write-Step "MySQL left running (use -IncludeMysql to stop it too)"
}

Write-Host ''
Write-Host 'Ports now:' -ForegroundColor Green
foreach ($port in @($BackendPort, $FrontendPort)) {
    $listening = [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
    Write-Host ("  {0}  {1}" -f $port, $(if ($listening) { 'still listening' } else { 'free' }))
}
Write-Host ''

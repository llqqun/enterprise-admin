# mysql-ctl.ps1
# Start / stop / inspect the portable MySQL instance that lives outside C:.
# ASCII-only on purpose (see install-mysql.ps1 for the reason).

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('start', 'stop', 'status', 'restart')]
    [string]$Action,

    [string]$BaseDir      = 'D:\devtools\mysql-8.0.29',
    [string]$DataDir      = 'D:\devtools\mysql-data',
    [string]$LogDir       = 'D:\devtools\mysql-logs',
    [int]$Port            = 3306,
    [string]$RootPassword = 'Admin@123456',
    [int]$TimeoutSeconds  = 60
)

$ErrorActionPreference = 'Continue'

$mysqld     = Join-Path $BaseDir 'bin\mysqld.exe'
$mysqladmin = Join-Path $BaseDir 'bin\mysqladmin.exe'
$mysql      = Join-Path $BaseDir 'bin\mysql.exe'
$myIniPath  = Join-Path $BaseDir 'my.ini'
$errorLog   = Join-Path $LogDir 'error.log'

function Write-Step([string]$Message) {
    Write-Host ("[mysql-ctl] " + $Message) -ForegroundColor Cyan
}

function Write-Fail([string]$Message) {
    Write-Host ("[mysql-ctl] ERROR: " + $Message) -ForegroundColor Red
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @()
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    # Arguments are handed to CreateProcess as ONE raw string, so any argument
    # containing whitespace must be re-quoted here. Without this, a value like
    # `-e SELECT VERSION();` reaches mysql as `-e SELECT` plus a stray positional
    # `VERSION();`, which mysql then reads as a database name.
    $quoted = @($Arguments | ForEach-Object {
        if ($_ -match '\s') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    })
    $psi.FileName               = $Exe
    $psi.Arguments              = ($quoted -join ' ')
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    return [pscustomobject]@{
        ExitCode = $proc.ExitCode
        Output   = (($stdout, $stderr) -join [Environment]::NewLine).Trim()
    }
}

function Test-PortOpen {
    param([string]$TargetHost = '127.0.0.1', [int]$TargetPort = 3306, [int]$TimeoutMs = 1000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($TargetHost, $TargetPort, $null, $null)
        $signalled = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($signalled) { $client.EndConnect($iar) }
        return $signalled
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-MysqldProcess {
    Get-Process -Name 'mysqld' -ErrorAction SilentlyContinue
}

function Get-ListeningPid {
    param([int]$TargetPort = 3306)
    $conn = Get-NetTCPConnection -State Listen -LocalPort $TargetPort -ErrorAction SilentlyContinue |
            Select-Object -First 1
    if ($conn) { return $conn.OwningProcess }
    return $null
}

function Show-ErrorLogTail {
    if (Test-Path -LiteralPath $errorLog) {
        Write-Fail "--- tail of $errorLog ---"
        Get-Content -LiteralPath $errorLog -Tail 30 -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Host $_ }
    } else {
        Write-Fail "error log not found: $errorLog"
    }
}

function Start-Mysql {
    if (-not (Test-Path -LiteralPath $mysqld)) {
        Write-Fail "mysqld.exe not found: $mysqld"
        Write-Fail "Run tools\install-mysql.ps1 first."
        exit 1
    }
    if (-not (Test-Path -LiteralPath $myIniPath)) {
        Write-Fail "my.ini not found: $myIniPath"
        Write-Fail "Run tools\install-mysql.ps1 first."
        exit 1
    }

    if (Test-PortOpen -TargetPort $Port) {
        Write-Step "already listening on 127.0.0.1:$Port"
        return $true
    }

    Write-Step "starting mysqld ..."
    Start-Process -FilePath $mysqld `
                  -ArgumentList "--defaults-file=$myIniPath" `
                  -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -TargetPort $Port) {
            Write-Step "MySQL is ready on 127.0.0.1:$Port"
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Fail "MySQL did not start within $TimeoutSeconds seconds"
    Show-ErrorLogTail
    return $false
}

function Stop-Mysql {
    $running = (Get-MysqldProcess) -or (Test-PortOpen -TargetPort $Port)
    if (-not $running) {
        Write-Step "not running"
        return $true
    }

    if (Test-Path -LiteralPath $mysqladmin) {
        Write-Step "asking mysqld to shut down ..."
        Invoke-Native -Exe $mysqladmin -Arguments @(
            '-uroot', "-p$RootPassword", '-h127.0.0.1', "-P$Port", 'shutdown'
        ) | Out-Null
    }

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-PortOpen -TargetPort $Port)) {
            Write-Step "stopped (graceful)"
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Fail "graceful shutdown timed out; killing by port owner"
    $ownerPid = Get-ListeningPid -TargetPort $Port
    if ($ownerPid) {
        try {
            Stop-Process -Id $ownerPid -Force -ErrorAction Stop
            Write-Step "killed PID $ownerPid"
        } catch {
            Write-Fail ("could not kill PID " + $ownerPid + ": " + $_.Exception.Message)
            return $false
        }
    }

    Start-Sleep -Seconds 1
    if (Test-PortOpen -TargetPort $Port) {
        Write-Fail "port $Port is still listening"
        return $false
    }
    Write-Step "stopped"
    return $true
}

function Show-Status {
    $procs = Get-MysqldProcess
    $open  = Test-PortOpen -TargetPort $Port

    Write-Host ("process : " + $(if ($procs) { "running (PID " + (($procs | ForEach-Object { $_.Id }) -join ',') + ")" } else { 'not running' }))
    Write-Host ("port    : " + $(if ($open) { "listening on 127.0.0.1:$Port" } else { "nothing on $Port" }))

    if ($open -and (Test-Path -LiteralPath $mysql)) {
        $res = Invoke-Native -Exe $mysql -Arguments @(
            '-uroot', "-p$RootPassword", '-h127.0.0.1', "-P$Port",
            '-N', '-B', '-e', 'SELECT VERSION();'
        )
        if ($res.ExitCode -eq 0) {
            Write-Host ("version : " + $res.Output)
            return 0
        }
        Write-Host 'version : could not query (wrong root password?)'
        return 1
    }

    if ($open) { return 0 }
    return 1
}

# ---------------------------------------------------------------------------
switch ($Action) {
    'start' {
        if (Start-Mysql) { exit 0 } else { exit 1 }
    }
    'stop' {
        if (Stop-Mysql) { exit 0 } else { exit 1 }
    }
    'status' {
        exit (Show-Status)
    }
    'restart' {
        if (-not (Stop-Mysql)) { exit 1 }
        Start-Sleep -Seconds 1
        if (Start-Mysql) { exit 0 } else { exit 1 }
    }
}

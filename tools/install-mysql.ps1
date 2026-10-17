# install-mysql.ps1
# Unpacks the portable MySQL 8.0.29 ZIP, generates my.ini and initializes the data directory.
# ASCII-only on purpose: this host's PowerShell 5.1 console code page is GB2312 and would
# mis-decode a UTF-8 (no BOM) script containing non-ASCII text.

param(
    [string]$ZipPath     = 'D:\work\enterprise-admin\tools\downloads\mysql-8.0.29-winx64.zip',
    [string]$InstallRoot = 'D:\devtools',
    [string]$BaseDir     = 'D:\devtools\mysql-8.0.29',
    [string]$DataDir     = 'D:\devtools\mysql-data',
    [string]$LogDir      = 'D:\devtools\mysql-logs',
    [int]$Port           = 3306,
    [switch]$Force
)

$ErrorActionPreference = 'Continue'

function Write-Step([string]$Message) {
    Write-Host ("[install-mysql] " + $Message) -ForegroundColor Cyan
}

function Write-Fail([string]$Message) {
    Write-Host ("[install-mysql] ERROR: " + $Message) -ForegroundColor Red
}

# Runs a native executable and returns its exit code plus merged output.
# Does not use pipelines for the process itself, so PowerShell's native-stderr
# handling can never turn normal stderr output into a terminating error.
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @()
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    # See mysql-ctl.ps1: the raw command line must carry its own quoting for any
    # argument containing whitespace.
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

# ---------------------------------------------------------------------------
# Step 0: preconditions
# ---------------------------------------------------------------------------
$mysqld = Join-Path $BaseDir 'bin\mysqld.exe'

if ((Test-Path -LiteralPath $mysqld) -and -not $Force) {
    Write-Step "already installed at $BaseDir (use -Force to reinstall)"
} else {
    if (-not (Test-Path -LiteralPath $ZipPath)) {
        Write-Fail "ZIP not found: $ZipPath"
        Write-Fail "Download it first, e.g.:"
        Write-Fail "  curl.exe -L -o `"$ZipPath`" https://mirrors.huaweicloud.com/mysql/Downloads/MySQL-8.0/mysql-8.0.29-winx64.zip"
        exit 1
    }

    $zipItem = Get-Item -LiteralPath $ZipPath
    Write-Step ("ZIP: {0} ({1} MB)" -f $zipItem.FullName, [math]::Round($zipItem.Length / 1MB, 1))
    if ($zipItem.Length -lt 150MB) {
        Write-Fail "ZIP looks truncated (< 150 MB). Re-download before installing."
        exit 1
    }

    if (-not (Test-Path -LiteralPath $InstallRoot)) {
        New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    }

    Write-Step "extracting (this takes a minute)..."
    try {
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $InstallRoot -Force
    } catch {
        Write-Fail ("extraction failed: " + $_.Exception.Message)
        exit 1
    }

    $extracted = Join-Path $InstallRoot 'mysql-8.0.29-winx64'
    if (-not (Test-Path -LiteralPath $extracted)) {
        Write-Fail "expected folder not found after extraction: $extracted"
        exit 1
    }
    if (Test-Path -LiteralPath $BaseDir) {
        Write-Step "removing previous $BaseDir"
        Remove-Item -LiteralPath $BaseDir -Recurse -Force
    }
    Move-Item -LiteralPath $extracted -Destination $BaseDir
    Write-Step "unpacked to $BaseDir"
}

if (-not (Test-Path -LiteralPath $mysqld)) {
    Write-Fail "mysqld.exe still missing at $mysqld"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 1: data dir + logs dir
# ---------------------------------------------------------------------------
# The error log deliberately lives OUTSIDE the data directory: MySQL refuses to
# run --initialize-insecure against a datadir that already contains anything,
# and a logs/ subfolder inside it is enough to trigger exactly that failure.
# Keeping logs beside (not inside) datadir also matches MySQL's own guidance
# that datadir should hold only data, so backups stay unambiguous.
foreach ($d in @($DataDir, $LogDir)) {
    if (-not (Test-Path -LiteralPath $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Step "created $d"
    }
}

# ---------------------------------------------------------------------------
# Step 2: my.ini
# ---------------------------------------------------------------------------
$myIniPath = Join-Path $BaseDir 'my.ini'
$baseFwd   = $BaseDir -replace '\\', '/'
$dataFwd   = $DataDir -replace '\\', '/'
$logFwd    = $LogDir  -replace '\\', '/'

$myIni = @"
# Generated by install-mysql.ps1 - do not edit by hand, re-run the script instead.
[client]
port=$Port
default-character-set=utf8mb4

[mysql]
default-character-set=utf8mb4

[mysqld]
basedir=$baseFwd
datadir=$dataFwd
port=$Port
bind-address=127.0.0.1
character-set-server=utf8mb4
collation-server=utf8mb4_0900_ai_ci
default-storage-engine=INNODB
max_connections=200
max_allowed_packet=64M
explicit_defaults_for_timestamp=1
default-time-zone='+00:00'
sql_mode=STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION
log-error=$logFwd/error.log
slow_query_log=1
slow_query_log_file=$logFwd/slow.log
long_query_time=1
"@
$myIni | Set-Content -LiteralPath $myIniPath -Encoding ASCII
Write-Step "wrote $myIniPath"

# ---------------------------------------------------------------------------
# Step 3: initialize the data directory (idempotent)
# ---------------------------------------------------------------------------
$dataInitialized = Test-Path -LiteralPath (Join-Path $DataDir 'mysql')

if ($dataInitialized -and -not $Force) {
    Write-Step "data directory already initialized at $DataDir"
} else {
    if ($dataInitialized -and $Force) {
        Write-Step "clearing previously initialized data directory (-Force): $DataDir"
    } elseif (-not $dataInitialized -and
              (Get-ChildItem -LiteralPath $DataDir -Force -ErrorAction SilentlyContinue)) {
        Write-Step "clearing leftover files in an uninitialized data directory: $DataDir"
    }
    # MySQL aborts with MY-010457 if datadir is not empty. Note the pipeline form:
    # Remove-Item -LiteralPath with a wildcard would NOT expand and silently no-op.
    Get-ChildItem -LiteralPath $DataDir -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Write-Step "running mysqld --initialize-insecure ..."
    $result = Invoke-Native -Exe $mysqld -Arguments @(
        "--defaults-file=$myIniPath",
        '--initialize-insecure'
    )
    if ($result.ExitCode -ne 0) {
        Write-Fail "mysqld --initialize-insecure failed (exit $($result.ExitCode))"
        Write-Fail $result.Output
        $errLog = Join-Path $LogDir 'error.log'
        if (Test-Path -LiteralPath $errLog) {
            Write-Fail "--- tail of $errLog ---"
            Get-Content -LiteralPath $errLog -Tail 30 | ForEach-Object { Write-Host $_ }
        }
        exit 1
    }
    if ($result.Output) { Write-Step $result.Output }
    Write-Step "data directory initialized (root has NO password yet)"
}

Write-Host ''
Write-Host 'Next steps:' -ForegroundColor Green
Write-Host '  1) powershell -ExecutionPolicy Bypass -File tools\mysql-ctl.ps1 -Action start'
Write-Host '  2) set the root password and create the databases (see the plan, Task 1 Step 5)'
Write-Host ''

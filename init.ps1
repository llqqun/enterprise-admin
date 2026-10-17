# init.ps1 - one-time setup: .env, databases, schema, seed data.
# ASCII-only on purpose: this host's PowerShell 5.1 console code page is GB2312 and
# would mis-decode a UTF-8 (no BOM) script containing non-ASCII text.

param(
    [string]$BaseDir      = 'D:\devtools\mysql-8.0.29',
    [string]$RootPassword = 'Admin@123456',
    [string]$DevDatabase  = 'enterprise_admin',
    [string]$TestDatabase = 'enterprise_admin_test',
    [switch]$SkipSeed
)

$ErrorActionPreference = 'Continue'

$projectRoot = $PSScriptRoot
$backendDir  = Join-Path $projectRoot 'backend'
$python      = Join-Path $backendDir '.venv\Scripts\python.exe'
$mysqlExe    = Join-Path $BaseDir 'bin\mysql.exe'
$mysqlCtl    = Join-Path $projectRoot 'tools\mysql-ctl.ps1'
$ctl         = Join-Path $projectRoot 'tools\mysql-ctl.ps1'
$envFile     = Join-Path $backendDir '.env'

function Write-Step([string]$Message) {
    Write-Host ("[init] " + $Message) -ForegroundColor Cyan
}

function Write-Fail([string]$Message) {
    Write-Host ("[init] ERROR: " + $Message) -ForegroundColor Red
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @()
    )
    # Arguments are handed to CreateProcess as one raw string, so anything with
    # whitespace must be re-quoted here (see tools/mysql-ctl.ps1 for the full story).
    $quoted = @($Arguments | ForEach-Object {
        if ($_ -match '\s') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    })
    $psi = New-Object System.Diagnostics.ProcessStartInfo
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
# 0. preconditions
# ---------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $python)) {
    Write-Fail "backend virtualenv not found: $python"
    Write-Fail "Create it first:"
    Write-Fail "  python -m venv `"$backendDir\.venv`""
    Write-Fail "  `"$backendDir\.venv\Scripts\python.exe`" -m pip install -r `"$backendDir\requirements.txt`" -i https://pypi.tuna.tsinghua.edu.cn/simple"
    exit 1
}

if (-not (Test-Path -LiteralPath $mysqlExe)) {
    Write-Fail "portable MySQL not found at $BaseDir"
    Write-Fail "Install it first: powershell -ExecutionPolicy Bypass -File tools\install-mysql.ps1"
    exit 1
}

# ---------------------------------------------------------------------------
# 0b. keep pip's download cache off C:
# ---------------------------------------------------------------------------
# A venv-scoped pip.ini is the only place this setting can live that travels with
# the environment the project actually uses. Without it pip writes to
# %LOCALAPPDATA%\pip\cache on C:, which the project's constraints rule out.
$pipIni = Join-Path $backendDir '.venv\pip.ini'
if (-not (Test-Path -LiteralPath $pipIni)) {
    Write-Step "pointing pip's cache at D:\devtools\caches\pip (venv pip.ini)"
    @(
        '[global]',
        'cache-dir = D:\devtools\caches\pip',
        'index-url = https://pypi.tuna.tsinghua.edu.cn/simple'
    ) | Set-Content -LiteralPath $pipIni -Encoding ASCII
}

# ---------------------------------------------------------------------------
# 1. .env (generated, never committed)
# ---------------------------------------------------------------------------
if (Test-Path -LiteralPath $envFile) {
    Write-Step ".env already exists, leaving it alone"
} else {
    Write-Step "generating .env with a random SECRET_KEY"
    $secret = (& $python -c "import secrets;print(secrets.token_hex(32))").Trim()
    $lines = @(
        'APP_NAME=enterprise-admin',
        'APP_VERSION=0.1.0',
        'DEBUG=true',
        'DOCS_ENABLED=true',
        'API_V1_PREFIX=/api/v1',
        "SECRET_KEY=$secret",
        'ACCESS_TOKEN_EXPIRE_MINUTES=30',
        'REFRESH_TOKEN_EXPIRE_DAYS=7',
        'CAPTCHA_ENABLED=true',
        'MYSQL_HOST=127.0.0.1',
        'MYSQL_PORT=3306',
        "MYSQL_USER=root",
        "MYSQL_PASSWORD=$RootPassword",
        "MYSQL_DB=$DevDatabase",
        'CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173'
    )
    $lines | Set-Content -LiteralPath $envFile -Encoding ASCII
}

# ---------------------------------------------------------------------------
# 2. MySQL up
# ---------------------------------------------------------------------------
Write-Step "ensuring MySQL is running"
& powershell -ExecutionPolicy Bypass -File $ctl -Action start | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Fail "MySQL did not start. Check D:\devtools\mysql-logs\error.log"
    exit 1
}

# ---------------------------------------------------------------------------
# 3. databases
# ---------------------------------------------------------------------------
Write-Step "creating databases if missing"
$sql = "CREATE DATABASE IF NOT EXISTS $DevDatabase DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; CREATE DATABASE IF NOT EXISTS $TestDatabase DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
$result = Invoke-Native -Exe $mysqlExe -Arguments @(
    '--host=127.0.0.1', '--port=3306', '--user=root', "--password=$RootPassword",
    '--execute', $sql
)
if ($result.ExitCode -ne 0) {
    Write-Fail "could not create the databases"
    Write-Fail $result.Output
    exit 1
}
Write-Step "databases ready: $DevDatabase, $TestDatabase"

# ---------------------------------------------------------------------------
# 4. schema
# ---------------------------------------------------------------------------
Push-Location $backendDir
try {
    # `2>&1 | Out-Host` inside the script keeps alembic's INFO logging off this
    # script's stderr. Left alone, PowerShell renders those INFO lines as red error
    # records (native stderr -> ErrorRecord), which reads like a failure when it is
    # not one.
    Write-Step "applying migrations to $DevDatabase"
    & $python -m alembic upgrade head 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { Write-Fail "migration failed"; Pop-Location; exit 1 }

    Write-Step "applying migrations to $TestDatabase"
    & $python -m alembic -x "db=$TestDatabase" upgrade head 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { Write-Fail "test-database migration failed"; Pop-Location; exit 1 }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 5. seed data
# ---------------------------------------------------------------------------
if ($SkipSeed) {
    Write-Step "skipping seed data (-SkipSeed)"
} else {
    Write-Step "seeding roles, departments, menus and demo accounts (idempotent)"
    Push-Location $backendDir
    try {
        & $python -m scripts.seed_data 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) { Write-Fail "seeding failed"; Pop-Location; exit 1 }
    } finally {
        Pop-Location
    }
}

Write-Host ''
Write-Host 'Initialization complete.' -ForegroundColor Green
Write-Host 'Next: powershell -ExecutionPolicy Bypass -File start.ps1'
Write-Host ''

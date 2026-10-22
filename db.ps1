# db.ps1 - manage the portable MySQL instance on its own, without going through the API.
# ASCII-only on purpose (see init.ps1 for the reason).
#
#   db.ps1                         same as -Action status
#   db.ps1 -Action status          process / port / version / database size
#   db.ps1 -Action console         open an interactive mysql shell in a new window
#   db.ps1 -Action query -Sql "SELECT COUNT(*) FROM sys_user"
#   db.ps1 -Action databases       list databases
#   db.ps1 -Action backup          dump to D:\devtools\mysql-backups\<db>-<timestamp>.sql
#   db.ps1 -Action restore -File D:\devtools\mysql-backups\<db>-<timestamp>.sql
#
# The password is on the command line, which is acceptable for a local demo
# instance and is how tools\mysql-ctl.ps1 already works. Do not reuse this shape
# for a shared database: use a defaults-file with restricted permissions instead.

param(
    [ValidateSet('status', 'console', 'query', 'databases', 'backup', 'restore')]
    [string]$Action = 'status',

    [string]$Sql = '',

    [string]$File = '',

    [string]$Database = 'enterprise_admin',

    [string]$BaseDir = 'D:\devtools\mysql-8.0.29',
    [string]$BackupDir = 'D:\devtools\mysql-backups',
    [int]$Port = 3306,
    [string]$RootPassword = 'Admin@123456'
)

$ErrorActionPreference = 'Continue'

$mysql      = Join-Path $BaseDir 'bin\mysql.exe'
$mysqldump  = Join-Path $BaseDir 'bin\mysqldump.exe'
$mysqladmin = Join-Path $BaseDir 'bin\mysqladmin.exe'
$mysqlCtl   = Join-Path $PSScriptRoot 'tools\mysql-ctl.ps1'

function Write-Step([string]$Message) {
    Write-Host ("[db] " + $Message) -ForegroundColor Cyan
}

function Write-Fail([string]$Message) {
    Write-Host ("[db] ERROR: " + $Message) -ForegroundColor Red
}

function Test-PortOpen {
    param([int]$TargetPort = 3306, [string]$TargetHost = '127.0.0.1')
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($TargetHost, $TargetPort, $null, $null)
        $signalled = $iar.AsyncWaitHandle.WaitOne(800, $false)
        if ($signalled) { $client.EndConnect($iar) }
        return $signalled
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Invoke-Mysql {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$Exe = $mysql
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    # CreateProcess takes ONE raw string, so arguments containing whitespace have
    # to be re-quoted here - otherwise `-e SELECT 1` arrives as two arguments.
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

if (-not (Test-Path -LiteralPath $mysql)) {
    Write-Fail ("mysql.exe not found: " + $mysql)
    exit 1
}

if (-not (Test-PortOpen -TargetPort $Port)) {
    Write-Fail ("MySQL is not listening on 127.0.0.1:" + $Port)
    Write-Fail 'Start it with: start.ps1 -Only db   (or tools\mysql-ctl.ps1 -Action start)'
    exit 1
}

switch ($Action) {

    'status' {
        & powershell -ExecutionPolicy Bypass -File $mysqlCtl -Action status | Out-Host
        $res = Invoke-Mysql -Arguments @(
            '-uroot', "-p$RootPassword", '-h127.0.0.1', "-P$Port", '-N', '-B', '-e',
            ("SELECT CONCAT(table_schema, ': ', COUNT(*), ' tables, ', " +
             "ROUND(SUM(data_length+index_length)/1024/1024, 1), ' MB') " +
             "FROM information_schema.tables WHERE table_schema='$Database' GROUP BY table_schema;")
        )
        if ($res.ExitCode -eq 0) {
            Write-Host ("database : " + $res.Output)
        } else {
            Write-Fail $res.Output
            exit 1
        }
    }

    'console' {
        Write-Step ("opening an interactive shell on " + $Database)
        Write-Step 'type EXIT; to leave it'
        Start-Process -FilePath $mysql -ArgumentList @(
            '-uroot', "-p$RootPassword", '-h127.0.0.1', "-P$Port", $Database
        ) | Out-Null
    }

    'query' {
        if (-not $Sql) {
            Write-Fail '-Action query needs -Sql "SELECT ..."'
            exit 1
        }
        $res = Invoke-Mysql -Arguments @(
            '-uroot', "-p$RootPassword", '-h127.0.0.1', "-P$Port", '-t', $Database, '-e', $Sql
        )
        Write-Host $res.Output
        exit $res.ExitCode
    }

    'databases' {
        $res = Invoke-Mysql -Arguments @(
            '-uroot', "-p$RootPassword", '-h127.0.0.1', "-P$Port", '-t', '-e', 'SHOW DATABASES;'
        )
        Write-Host $res.Output
        exit $res.ExitCode
    }

    'backup' {
        if (-not (Test-Path -LiteralPath $BackupDir)) {
            New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
        }
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $target = Join-Path $BackupDir ($Database + '-' + $stamp + '.sql')
        Write-Step ("dumping " + $Database + " -> " + $target)

        # --single-transaction keeps InnoDB consistent without locking the tables,
        # so a backup does not freeze the running API.
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName  = $mysqldump
        $psi.Arguments = ('-uroot -p' + $RootPassword + ' -h127.0.0.1 -P' + $Port +
                          ' --single-transaction --routines --triggers --databases ' + $Database)
        $psi.UseShellExecute        = $false
        $psi.CreateNoWindow         = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $stream = $proc.StandardOutput
        $writer = New-Object System.IO.StreamWriter($target, $false, (New-Object System.Text.UTF8Encoding($false)))
        $buffer = New-Object char[] 8192
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $writer.Write($buffer, 0, $read)
        }
        $writer.Close()
        $err = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()

        if ($proc.ExitCode -ne 0) {
            Write-Fail 'mysqldump failed'
            Write-Fail $err
            exit 1
        }
        $size = (Get-Item -LiteralPath $target).Length
        Write-Step ("done: " + [math]::Round($size / 1KB, 1) + " KB")
        Write-Host ('  ' + $target)
    }

    'restore' {
        if (-not $File) {
            Write-Fail '-Action restore needs -File <path.sql>'
            exit 1
        }
        if (-not (Test-Path -LiteralPath $File)) {
            Write-Fail ("file not found: " + $File)
            exit 1
        }
        Write-Step ("restoring " + $File + " into " + $Database)
        Write-Step 'this overwrites the current tables of that database'

        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName  = $mysql
        $psi.Arguments = ('-uroot -p' + $RootPassword + ' -h127.0.0.1 -P' + $Port)
        $psi.UseShellExecute        = $false
        $psi.CreateNoWindow         = $true
        $psi.RedirectStandardInput  = $true
        $psi.RedirectStandardError  = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $reader = New-Object System.IO.StreamReader($File, [System.Text.Encoding]::UTF8)
        while (($line = $reader.ReadLine()) -ne $null) {
            $proc.StandardInput.WriteLine($line)
        }
        $reader.Close()
        $proc.StandardInput.Close()
        $err = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()

        if ($proc.ExitCode -ne 0) {
            Write-Fail 'restore failed'
            Write-Fail $err
            exit 1
        }
        Write-Step 'restore done'
    }
}

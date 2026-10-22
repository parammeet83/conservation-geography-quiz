<#
.SYNOPSIS
    Manage a project-local PostgreSQL cluster for development and tests.

.DESCRIPTION
    Uses the PostgreSQL binaries already installed on this machine (initdb, pg_ctl, psql)
    to run a private cluster stored in .local\pgdata, listening on localhost only.
    It does not touch any PostgreSQL Windows service you already run, and it does not
    need that server's superuser password.

    Commands:
      init    Create the cluster (once), start it, and create the app role plus the
              'cgq' and 'cgq_test' databases.
      start   Start the cluster.
      stop    Stop the cluster.
      status  Show whether the cluster is running.

    The credentials are local-development defaults that match .env.example. The server
    only listens on 127.0.0.1/::1. Override them with -AppPassword / -AdminPassword.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\dev-db.ps1 init
#>
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("init", "start", "stop", "status")]
    [string]$Command,
    [int]$Port = 5433,
    [string]$PgBin = "",
    [string]$AppUser = "cgq_app",
    [string]$AppPassword = "cgq_local_dev",
    [string]$AdminPassword = "cgq_local_admin"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DataDir = Join-Path $RepoRoot ".local\pgdata"
$LogFile = Join-Path $RepoRoot ".local\postgres.log"

function Find-PgBin {
    if ($PgBin) { return $PgBin }
    $onPath = Get-Command pg_ctl.exe -ErrorAction SilentlyContinue
    if ($onPath) { return Split-Path -Parent $onPath.Source }
    $candidates = Get-ChildItem "C:\Program Files\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Name -replace '\D', '') } -Descending
    foreach ($c in $candidates) {
        $bin = Join-Path $c.FullName "bin"
        if (Test-Path (Join-Path $bin "pg_ctl.exe")) { return $bin }
    }
    throw "PostgreSQL binaries not found. Install PostgreSQL (https://www.postgresql.org/download/windows/) or pass -PgBin 'C:\path\to\PostgreSQL\17\bin'."
}

$Bin = Find-PgBin
$PgCtl = Join-Path $Bin "pg_ctl.exe"
$InitDb = Join-Path $Bin "initdb.exe"
$Psql = Join-Path $Bin "psql.exe"

function Test-Running {
    & $PgCtl status -D $DataDir *> $null
    return $LASTEXITCODE -eq 0
}

function Start-Cluster {
    if (Test-Running) { Write-Host "PostgreSQL already running on port $Port."; return }
    # Run pg_ctl detached in a hidden window: the server process would otherwise inherit
    # this console's output handles and keep the calling terminal/pipe open.
    $pgArgs = @("start", "-D", "`"$DataDir`"", "-l", "`"$LogFile`"", "-w", "-o", "`"-p $Port -c listen_addresses=localhost`"")
    $proc = Start-Process -FilePath $PgCtl -ArgumentList $pgArgs -WindowStyle Hidden -PassThru
    $proc.WaitForExit()
    if (-not (Test-Running)) { throw "pg_ctl start failed; see $LogFile" }
    Write-Host "PostgreSQL started on localhost:$Port (data: $DataDir)."
}

function Invoke-AdminSql([string]$Sql, [string]$Database = "postgres") {
    $env:PGPASSWORD = $AdminPassword
    try {
        $out = & $Psql -h localhost -p $Port -U postgres -d $Database -v ON_ERROR_STOP=1 -tA -c $Sql
        if ($LASTEXITCODE -ne 0) { throw "psql failed: $Sql" }
        return $out
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

switch ($Command) {
    "init" {
        if (-not (Test-Path (Join-Path $DataDir "PG_VERSION"))) {
            New-Item -ItemType Directory -Force (Split-Path $DataDir) | Out-Null
            $pwFile = New-TemporaryFile
            try {
                Set-Content -Path $pwFile -Value $AdminPassword -NoNewline -Encoding ascii
                & $InitDb -D $DataDir -U postgres --pwfile=$pwFile -E UTF8 --locale=C `
                    --auth-local=scram-sha-256 --auth-host=scram-sha-256 | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "initdb failed" }
            } finally {
                Remove-Item $pwFile -Force
            }
            Write-Host "Initialised cluster in $DataDir."
        } else {
            Write-Host "Cluster already initialised in $DataDir."
        }
        Start-Cluster
        $roleExists = Invoke-AdminSql "SELECT 1 FROM pg_roles WHERE rolname = '$AppUser'"
        if (-not $roleExists) {
            Invoke-AdminSql "CREATE ROLE $AppUser LOGIN PASSWORD '$AppPassword'" | Out-Null
            Write-Host "Created role $AppUser."
        }
        foreach ($db in @("cgq", "cgq_test")) {
            $dbExists = Invoke-AdminSql "SELECT 1 FROM pg_database WHERE datname = '$db'"
            if (-not $dbExists) {
                Invoke-AdminSql "CREATE DATABASE $db OWNER $AppUser ENCODING 'UTF8'" | Out-Null
                Write-Host "Created database $db."
            }
        }
        Write-Host "Ready: postgresql+psycopg://${AppUser}:***@localhost:$Port/cgq (tests use cgq_test)."
    }
    "start" { Start-Cluster }
    "stop" {
        if (Test-Running) {
            & $PgCtl stop -D $DataDir -m fast -w | Out-Null
            Write-Host "PostgreSQL stopped."
        } else {
            Write-Host "PostgreSQL is not running."
        }
    }
    "status" {
        if (Test-Running) { Write-Host "Running on localhost:$Port (data: $DataDir)." }
        else { Write-Host "Not running." ; exit 1 }
    }
}

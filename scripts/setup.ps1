<#
.SYNOPSIS
    One-time local setup: environment file, Python venv, dependencies, database, migrations, seed.

.DESCRIPTION
    Safe to re-run: every step is idempotent. Uses the venv's python.exe directly, so no
    activation script (and no change to the PowerShell execution policy) is required.

.PARAMETER SkipDatabase
    Skip starting the project-local PostgreSQL cluster (use when DATABASE_URL in .env points
    at a server you manage yourself).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
param([switch]$SkipDatabase)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root "backend\.venv\Scripts\python.exe"

function Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Run([string]$Exe, [string[]]$Arguments, [string]$Dir = $Root) {
    Push-Location $Dir
    try {
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')" }
    } finally { Pop-Location }
}

Step "Environment file"
if (-not (Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
    Write-Host "Created .env from .env.example"
} else { Write-Host ".env already exists (left unchanged)" }

Step "Python virtual environment (backend\.venv)"
if (-not (Test-Path $Py)) { Run "py" @("-3.12", "-m", "venv", "backend\.venv") }
Run $Py @("-m", "pip", "install", "--upgrade", "pip", "--quiet")
Run $Py @("-m", "pip", "install", "-r", "backend\requirements-dev.txt", "--quiet")

Step "Frontend dependencies"
Run "npm" @("install", "--no-fund", "--no-audit") (Join-Path $Root "frontend")

if (-not $SkipDatabase) {
    Step "Local PostgreSQL (port 5433)"
    Run "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "dev-db.ps1"), "init")
}

Step "Validate question bank, migrate, seed"
$backend = Join-Path $Root "backend"
Run $Py @("-m", "app.cli", "validate") $backend
Run $Py @("-m", "alembic", "upgrade", "head") $backend
Run $Py @("-m", "app.cli", "seed") $backend
Run $Py @("-m", "app.cli", "check-db") $backend

Write-Host "`nSetup complete. Start the app with scripts\start-backend.ps1 and scripts\start-frontend.ps1 (separate terminals)." -ForegroundColor Green

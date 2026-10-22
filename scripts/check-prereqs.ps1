<#
.SYNOPSIS
    Report the versions of the tools this project needs.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\check-prereqs.ps1
#>
$ok = $true

function Check([string]$Name, [scriptblock]$Probe, [string]$Need) {
    try {
        $v = (& $Probe 2>&1 | Select-Object -First 1).ToString().Trim()
        if (-not $v) { throw "no output" }
        Write-Host ("[ OK ] {0,-12} {1}" -f $Name, $v)
    } catch {
        Write-Host ("[MISS] {0,-12} required: {1}" -f $Name, $Need) -ForegroundColor Yellow
        $script:ok = $false
    }
}

Check "Python 3.12" { py -3.12 --version } "Python 3.12+ (https://www.python.org/downloads/windows/), with the 'py' launcher"
Check "Node.js" { node --version } "Node.js 22 or 24 LTS (https://nodejs.org/)"
Check "npm" { npm --version } "npm (installed with Node.js)"
Check "Git" { git --version } "Git for Windows (https://git-scm.com/download/win)"

$pg = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_ctl.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (Get-Command pg_ctl.exe -ErrorAction SilentlyContinue) {
    Check "PostgreSQL" { pg_ctl --version } "PostgreSQL 15+"
} elseif ($pg) {
    Check "PostgreSQL" { & $pg.FullName --version } "PostgreSQL 15+"
} else {
    Write-Host "[MISS] PostgreSQL   required: PostgreSQL 15+ (https://www.postgresql.org/download/windows/) or Docker" -ForegroundColor Yellow
    $ok = $false
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Check "Docker" { docker --version } "optional"
} else {
    Write-Host "[ -- ] Docker       not installed (optional; scripts\dev-db.ps1 uses local PostgreSQL instead)"
}

if ($ok) { Write-Host "`nAll required tools found." } else { Write-Host "`nInstall the missing tools above, then re-run this check."; exit 1 }

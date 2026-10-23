<#
.SYNOPSIS
    Store the Neon PostgreSQL connection string in Google Secret Manager without echoing it.

.DESCRIPTION
    Reads the connection string from the Windows clipboard (copy it from the Neon console
    first), extracts the postgresql:// URL if the clipboard holds a larger snippet (for
    example a `psql '...'` command or a `DATABASE_URL=...` line), validates it, writes it to
    a temporary file, uploads it as a new version of secret '<SecretName>' (creating the
    secret if needed), then deletes the file. The value is never printed or placed on a
    command line.

    Use Neon's *direct* (non-pooled) connection string, e.g.
      postgresql://<user>:<password>@<endpoint>.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
    The backend accepts postgresql:// and converts it to the psycopg driver automatically.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\set-db-secret.ps1
#>
param(
    [string]$ProjectId = "conservation-geography",
    [string]$SecretName = "cgq-database-url",
    [string]$Gcloud = "$env:LOCALAPPDATA\Google\CloudSDK\google-cloud-sdk\bin\gcloud.cmd"
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Gcloud)) { $Gcloud = (Get-Command gcloud).Source }

& $Gcloud services enable secretmanager.googleapis.com --project=$ProjectId --quiet
if ($LASTEXITCODE -ne 0) { throw "Could not enable Secret Manager (are you logged in? run: gcloud auth login)" }

$tmp = Join-Path $env:TEMP ("cgq-secret-" + [guid]::NewGuid().ToString("N") + ".txt")
$clip = $null
$plain = $null
try {
    $clip = Get-Clipboard -Raw
    if ([string]::IsNullOrWhiteSpace($clip)) {
        throw "The clipboard is empty. Copy the Neon connection string, then run this script again."
    }
    $clip = $clip.Trim()

    # Accept a bare URL or a snippet containing one. The URL ends at whitespace or a quote.
    $match = [regex]::Match($clip, 'postgres(?:ql)?(?:\+psycopg)?://[^\s''"`<>]+')
    if (-not $match.Success) {
        throw "No postgresql:// URL found in the clipboard (expected postgresql://user:password@host/neondb?sslmode=require)."
    }
    $plain = $match.Value.Trim()
    $clip = $null

    # Structural checks. Error messages never include the value itself.
    if ($plain -notmatch '^postgres(ql)?(\+psycopg)?://') { throw "That does not look like a PostgreSQL URL (expected postgresql://...)." }
    if ($plain -notmatch '^postgres(?:ql)?(?:\+psycopg)?://[^:/@\s]+:[^@\s]+@[^/@\s]+/[^?/\s]+') {
        throw "The URL is incomplete: expected user, password, host and database name (postgresql://user:password@host/database)."
    }
    if ($plain -match '\.\.\.|<|>') { throw "The URL contains placeholder text (such as '...' or '<password>'); copy the full string from Neon." }
    if ($plain -notmatch 'sslmode=require') { Write-Warning "The URL has no sslmode=require; Neon requires TLS." }
    if ($plain -match '-pooler\.') { Write-Warning "This is Neon's pooled endpoint; the direct (non-pooled) connection string is recommended." }

    [IO.File]::WriteAllText($tmp, $plain, [Text.UTF8Encoding]::new($false))
    $plain = $null

    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $Gcloud secrets describe $SecretName --project=$ProjectId --quiet 2>$null | Out-Null
    $exists = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $prev
    if ($exists) {
        & $Gcloud secrets versions add $SecretName --data-file=$tmp --project=$ProjectId --quiet
    } else {
        & $Gcloud secrets create $SecretName --replication-policy=automatic --data-file=$tmp --project=$ProjectId --quiet
    }
    if ($LASTEXITCODE -ne 0) { throw "Storing the secret failed." }
    Write-Host "Stored secret '$SecretName' in project '$ProjectId'." -ForegroundColor Green
} finally {
    if (Test-Path $tmp) { Remove-Item $tmp -Force }
    $clip = $null
    $plain = $null
}

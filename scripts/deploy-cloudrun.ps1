<#
.SYNOPSIS
    Build and deploy the FastAPI backend to Google Cloud Run, then migrate and seed Neon.

.DESCRIPTION
    Idempotent. Steps:
      1. Enable the required Google Cloud APIs.
      2. Create (if missing) an Artifact Registry Docker repository and a dedicated
         runtime service account, and let it read the database secret.
      3. Build the image with Cloud Build from the repository Dockerfile (no local Docker).
      4. Create/update the Cloud Run job "<Service>-migrate" and execute it:
         `python -m app.cli release` = alembic upgrade head + seed + check-db.
      5. Deploy the Cloud Run service with DATABASE_URL from Secret Manager and
         CORS_ORIGINS set to the production frontend origin.
      6. Print the service URL and check /api/v1/health.

    The Neon connection string is never passed on the command line or printed: it must
    already exist in Secret Manager as secret '<SecretName>' (create it with scripts\set-db-secret.ps1).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\deploy-cloudrun.ps1
#>
param(
    [string]$ProjectId = "conservation-geography",
    [string]$Region = "asia-southeast1",
    [string]$Service = "cgq-api",
    [string]$Repository = "cgq",
    [string]$SecretName = "cgq-database-url",
    [string]$FrontendOrigin = "https://conservation-geography-quiz-mu.vercel.app",
    [string]$Gcloud = "$env:LOCALAPPDATA\Google\CloudSDK\google-cloud-sdk\bin\gcloud.cmd"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $Gcloud)) {
    $onPath = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($onPath) { $Gcloud = $onPath.Source } else { throw "gcloud not found. Install the Google Cloud CLI or pass -Gcloud <path>." }
}

function Step([string]$m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function G {
    # Run gcloud; native stderr (progress messages) is shown but does not abort the script.
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $Gcloud @args --project=$ProjectId --quiet } finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -ne 0) { throw "gcloud $($args -join ' ') failed with exit code $LASTEXITCODE" }
}
function GQuiet {
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $Gcloud @args --project=$ProjectId --quiet 2>$null } finally { $ErrorActionPreference = $prev }
    return $LASTEXITCODE -eq 0
}

$sha = (git -C $Root rev-parse --short HEAD).Trim()
$dirty = git -C $Root status --porcelain -- backend data/seed Dockerfile
if ($dirty) { $sha = "$sha-dirty-$(Get-Date -Format yyyyMMddHHmmss)" }
$Image = "$Region-docker.pkg.dev/$ProjectId/$Repository/api:$sha"
$SaName = "$Service-runtime"
$SaEmail = "$SaName@$ProjectId.iam.gserviceaccount.com"

Step "Enable APIs"
G services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

Step "Check secret '$SecretName' exists (value is not read)"
if (-not (GQuiet secrets describe $SecretName)) {
    throw "Secret '$SecretName' not found. Create it first with: powershell -ExecutionPolicy Bypass -File scripts\set-db-secret.ps1"
}

Step "Artifact Registry repository '$Repository'"
if (-not (GQuiet artifacts repositories describe $Repository --location=$Region)) {
    G artifacts repositories create $Repository --repository-format=docker --location=$Region --description="Conservation Geography Quiz images"
}

Step "Runtime service account '$SaEmail'"
if (-not (GQuiet iam service-accounts describe $SaEmail)) {
    G iam service-accounts create $SaName --display-name="Conservation Geography Quiz API runtime"
}
G secrets add-iam-policy-binding $SecretName --member="serviceAccount:$SaEmail" --role="roles/secretmanager.secretAccessor" | Out-Null

Step "Build image $Image (Cloud Build)"
Push-Location $Root
try { G builds submit --tag=$Image . } finally { Pop-Location }

Step "Migrate and seed the database (Cloud Run job '$Service-migrate')"
G run jobs deploy "$Service-migrate" --region=$Region --image=$Image `
    --service-account=$SaEmail --set-secrets="DATABASE_URL=${SecretName}:latest" `
    --command=python --args="-m,app.cli,release" --max-retries=0 --task-timeout=600s
G run jobs execute "$Service-migrate" --region=$Region --wait

Step "Deploy Cloud Run service '$Service'"
G run deploy $Service --region=$Region --image=$Image --platform=managed `
    --service-account=$SaEmail --allow-unauthenticated --port=8080 `
    --set-secrets="DATABASE_URL=${SecretName}:latest" `
    --set-env-vars="CORS_ORIGINS=$FrontendOrigin,LOG_LEVEL=INFO" `
    --memory=512Mi --cpu=1 --min-instances=0 --max-instances=3 --concurrency=40 --timeout=60

$url = (& $Gcloud run services describe $Service --region=$Region --project=$ProjectId --format="value(status.url)").Trim()
Step "Service URL: $url"
$health = Invoke-RestMethod "$url/api/v1/health"
Write-Host ("Health: status={0} database={1}" -f $health.status, $health.database)
Write-Host "`nSet VITE_API_BASE_URL=$url in Vercel (Production) and redeploy the frontend." -ForegroundColor Green

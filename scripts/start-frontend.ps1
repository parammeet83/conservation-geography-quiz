<#
.SYNOPSIS
    Start the Vite dev server on http://localhost:5173 (proxies /api to the backend on port 8000).
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1
#>
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "frontend")
npm run dev

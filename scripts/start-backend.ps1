<#
.SYNOPSIS
    Start the FastAPI backend on http://127.0.0.1:8000 (auto-reload for development).
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1
#>
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "backend")
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Launches the FormAI Basketball local web app.
# First run: .\scripts\setup_env.ps1  (creates the venv and installs everything)
# Every run after that: .\run.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvPython = "$root\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "No virtual environment found. Running setup first..." -ForegroundColor Yellow
    & "$root\scripts\setup_env.ps1"
}

Write-Host "Starting FormAI Basketball at http://127.0.0.1:8800 ..." -ForegroundColor Cyan
& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8800

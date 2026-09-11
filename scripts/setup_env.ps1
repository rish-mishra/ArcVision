# One-time environment setup for FormAI Basketball on Windows.
# Creates an isolated virtual environment and installs dependencies in the
# order that keeps CUDA-enabled torch (needed for GPU-accelerated YOLO
# inference) from being silently overwritten by a CPU-only wheel that
# ultralytics would otherwise pull in as a plain dependency.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Creating virtual environment..." -ForegroundColor Cyan
py -3.11 -m venv "$root\.venv"

& "$root\.venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel

Write-Host "Installing CUDA-enabled PyTorch (falls back to CPU automatically if no compatible GPU)..." -ForegroundColor Cyan
& "$root\.venv\Scripts\python.exe" -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121

Write-Host "Installing remaining dependencies..." -ForegroundColor Cyan
& "$root\.venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt"

Write-Host "Downloading base detection model weights..." -ForegroundColor Cyan
& "$root\.venv\Scripts\python.exe" "$root\scripts\download_models.py"

Write-Host "Setup complete. Launch the app with .\run.ps1" -ForegroundColor Green

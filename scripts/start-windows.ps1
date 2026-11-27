$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating Python virtual environment (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements-windows.lock
}

Write-Host "Launching Matrix Workbench..." -ForegroundColor Green
& ".venv\Scripts\python.exe" -m matrixlab.desktop @args

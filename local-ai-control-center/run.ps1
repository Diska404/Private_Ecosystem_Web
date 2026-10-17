$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Venv = Join-Path $PSScriptRoot ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "[Local AI] Membuat virtual environment..." -ForegroundColor Cyan
    py -3 -m venv $Venv
}

Write-Host "[Local AI] Memastikan dependency terpasang..." -ForegroundColor Cyan
& $Python -m pip install --disable-pip-version-check -q -r (Join-Path $PSScriptRoot "requirements.txt")

Write-Host "[Local AI] Starting Control Center at http://127.0.0.1:8765" -ForegroundColor Green
& $Python -m backend.main

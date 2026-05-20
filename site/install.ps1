# Cipher - One-line installer
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ____ _   _ ____   ____ ___  " -ForegroundColor Cyan
Write-Host " / ___| | | |  _ \ / ___/ _ \ " -ForegroundColor Cyan
Write-Host "| |   | | | | |_) | |  | | | |" -ForegroundColor Cyan
Write-Host "| |___| |_| |  _ <| |__| |_| |" -ForegroundColor Cyan
Write-Host " \____|\___/|_| \_\\____\___/ " -ForegroundColor Cyan
Write-Host ""
Write-Host "cipher.elevenpct.com" -ForegroundColor DarkGray
Write-Host ""

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "ERROR: Python 3.10+ not found" -ForegroundColor Red
    exit 1
}
Write-Host "Found: " -NoNewline -ForegroundColor DarkGray
& python --version

Write-Host ""
Write-Host "Installing cipher..." -ForegroundColor Cyan
& python -m pip install git+https://github.com/elevenpercent/cipher.git@master --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Installed: cipher" -ForegroundColor Green
} else {
    Write-Host "ERROR: Install failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Done! Run:" -ForegroundColor Green
Write-Host "  cd your-project" -ForegroundColor DarkGray
Write-Host "  cip --setup" -ForegroundColor DarkGray
Write-Host ""

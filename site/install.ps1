# Cipher - One-line installer for Windows
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

# Find Python 3.10+ — try py launcher first (Windows official), then python, then python3
$PYTHON = $null
foreach ($cmd in @("py", "python", "python3")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        try {
            $ok = & $cmd -c "import sys; print(sys.version_info >= (3,10))" 2>$null
            if ($ok -eq "True") { $PYTHON = $cmd; break }
        } catch {}
    }
}

if (-not $PYTHON) {
    Write-Host "ERROR: Python 3.10+ not found." -ForegroundColor Red
    Write-Host "Download from: https://python.org/downloads" -ForegroundColor DarkGray
    exit 1
}
Write-Host "Found: " -NoNewline -ForegroundColor DarkGray
& $PYTHON --version

Write-Host ""
Write-Host "Installing cipher..." -ForegroundColor Cyan
& $PYTHON -m pip install git+https://github.com/elevenpercent/cipher.git@master --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Install failed. Try running PowerShell as Administrator." -ForegroundColor Red
    exit 1
}
Write-Host "Installed: cipher v0.5.0" -ForegroundColor Green

# Check cip is on PATH
$cip = Get-Command cip -ErrorAction SilentlyContinue
if (-not $cip) {
    Write-Host ""
    Write-Host "NOTE: 'cip' not on PATH. Add your Python Scripts folder:" -ForegroundColor Yellow
    $scripts = & $PYTHON -c "import sysconfig; print(sysconfig.get_path('scripts'))"
    Write-Host "  $scripts" -ForegroundColor DarkGray
    Write-Host "Then restart your terminal." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Done! Run:" -ForegroundColor Green
Write-Host "  cd your-project" -ForegroundColor DarkGray
Write-Host "  cip" -ForegroundColor DarkGray
Write-Host ""

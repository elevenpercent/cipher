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
& $PYTHON -m pip install --upgrade --no-cache-dir git+https://github.com/elevenpercent/cipher.git@master --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Install failed. Try running PowerShell as Administrator." -ForegroundColor Red
    exit 1
}
Write-Host "Installed: cipher v0.6.0" -ForegroundColor Green

# Auto-add Python Scripts dir to user PATH so 'cip' works from anywhere
$scripts = & $PYTHON -c "import sysconfig; print(sysconfig.get_path('scripts'))"
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if (-not $userPath) { $userPath = "" }

if ($userPath -notlike "*$scripts*") {
    $newPath = if ($userPath) { "$userPath;$scripts" } else { $scripts }
    [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host ""
    Write-Host "Added to PATH: $scripts" -ForegroundColor Green
    Write-Host "NOTE: Restart your terminal, then run 'cip' anywhere." -ForegroundColor Yellow
} else {
    Write-Host "PATH already includes Python Scripts — 'cip' should work anywhere." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Done! Open a new terminal, then run:" -ForegroundColor Green
Write-Host "  cd your-project" -ForegroundColor DarkGray
Write-Host "  cip" -ForegroundColor DarkGray
Write-Host ""

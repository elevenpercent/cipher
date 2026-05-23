# Cipher - One-line installer for Windows
# Usage: powershell -c "irm https://cipher.elevenpct.com/install.ps1 | iex"
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ████  ████  " -NoNewline -ForegroundColor Green
Write-Host "%" -ForegroundColor Red
Write-Host "     █     █  " -ForegroundColor Green
Write-Host "     █     █  " -ForegroundColor Green
Write-Host "  ████  ████  " -ForegroundColor Green
Write-Host ""
Write-Host "  elevenpercent  ·  cipher" -ForegroundColor DarkGray
Write-Host ""

# ── Step 1: Find or install Python 3.10+ ─────────────────────────────────────
function Find-Python {
    foreach ($cmd in @("py", "python", "python3")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) {
            try {
                $ok = & $cmd -c "import sys; print(sys.version_info >= (3,10))" 2>$null
                if ($ok -eq "True") { return $cmd }
            } catch {}
        }
    }
    return $null
}

$PYTHON = Find-Python

if (-not $PYTHON) {
    Write-Host "Python 3.10+ not found — installing Python 3.12 automatically..." -ForegroundColor Yellow
    Write-Host "(this may take a minute)" -ForegroundColor DarkGray

    $arch = if ([System.Environment]::Is64BitOperatingSystem) { "amd64" } else { "win32" }
    $pyUrl = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-$arch.exe"
    $pyInstaller = "$env:TEMP\cipher-python-installer.exe"

    try {
        Write-Host "Downloading Python 3.12..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $pyUrl -OutFile $pyInstaller -UseBasicParsing
        Write-Host "Running installer..." -ForegroundColor Cyan
        $proc = Start-Process -FilePath $pyInstaller `
            -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1 SimpleInstall=1" `
            -Wait -PassThru
        Remove-Item $pyInstaller -ErrorAction SilentlyContinue
        if ($proc.ExitCode -ne 0) { throw "Installer exited with code $($proc.ExitCode)" }
        Write-Host "Python 3.12 installed." -ForegroundColor Green

        # Refresh PATH in this session so we can use the new Python immediately
        $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
        $env:PATH    = "$machinePath;$userPath"

        $PYTHON = Find-Python
        if (-not $PYTHON) { throw "Python still not found after install." }
    } catch {
        Write-Host "ERROR: Could not auto-install Python: $_" -ForegroundColor Red
        Write-Host "Please install Python 3.10+ manually from: https://python.org/downloads" -ForegroundColor DarkGray
        exit 1
    }
}

Write-Host "Python: " -NoNewline -ForegroundColor DarkGray
& $PYTHON --version

# ── Step 2: Make sure pip is available ───────────────────────────────────────
$pipOk = & $PYTHON -m pip --version 2>$null
if (-not $pipOk) {
    Write-Host "pip not found — bootstrapping..." -ForegroundColor Yellow
    try {
        & $PYTHON -m ensurepip --upgrade
    } catch {
        Write-Host "Downloading get-pip.py..." -ForegroundColor Cyan
        $getPip = "$env:TEMP\get-pip.py"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing
        & $PYTHON $getPip --quiet
        Remove-Item $getPip -ErrorAction SilentlyContinue
    }
}

# ── Step 3: Install Cipher ────────────────────────────────────────────────────
Write-Host ""
Write-Host "Installing Cipher..." -ForegroundColor Cyan

# Try git+ if git is available (faster), fall back to zip URL (no git needed)
$installed = $false
if (Get-Command git -ErrorAction SilentlyContinue) {
    $result = & $PYTHON -m pip install --upgrade --no-cache-dir `
        git+https://github.com/elevenpercent/cipher.git@master --quiet 2>&1
    if ($LASTEXITCODE -eq 0) { $installed = $true }
}

if (-not $installed) {
    $result = & $PYTHON -m pip install --upgrade --no-cache-dir `
        "https://github.com/elevenpercent/cipher/archive/refs/heads/master.zip" --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Install failed." -ForegroundColor Red
        Write-Host $result
        Write-Host "Try running PowerShell as Administrator and re-running this script." -ForegroundColor DarkGray
        exit 1
    }
}

Write-Host "Installed: Cipher v0.6.0" -ForegroundColor Green

# ── Step 4: Add Python Scripts to PATH so 'cip' works everywhere ─────────────
$scripts  = & $PYTHON -c "import sysconfig; print(sysconfig.get_path('scripts'))"
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if (-not $userPath) { $userPath = "" }

if ($userPath -notlike "*$scripts*") {
    $newPath = if ($userPath) { "$userPath;$scripts" } else { $scripts }
    [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host "Added to PATH: $scripts" -ForegroundColor Green
    Write-Host "NOTE: Open a new terminal window, then run 'cip'." -ForegroundColor Yellow
} else {
    Write-Host "PATH OK — 'cip' will work from any directory." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "All done! Open a new terminal and run:" -ForegroundColor Green
Write-Host "  cd your-project" -ForegroundColor DarkGray
Write-Host "  cip" -ForegroundColor DarkGray
Write-Host ""

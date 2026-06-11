# Cipher Uninstaller — Windows PowerShell
# Usage: irm https://cipher.elevenpct.com/uninstall.ps1 | iex
#    or: .\uninstall.ps1

Write-Host ""
Write-Host "  Cipher Uninstaller" -ForegroundColor Cyan
Write-Host "  ==================" -ForegroundColor Cyan
Write-Host ""

$removed = @()
$failed  = @()

# 1. pip uninstall
Write-Host "  Checking pip install..." -NoNewline
$pip = Get-Command pip -ErrorAction SilentlyContinue
if (-not $pip) { $pip = Get-Command pip3 -ErrorAction SilentlyContinue }
if ($pip) {
    $check = & $pip.Source show cipher-agent 2>$null
    if ($check) {
        & $pip.Source uninstall cipher-agent -y 2>$null | Out-Null
        $removed += "pip package  (cipher-agent)"
        Write-Host " removed" -ForegroundColor Green
    } else {
        Write-Host " not installed" -ForegroundColor DarkGray
    }
} else {
    Write-Host " pip not found" -ForegroundColor DarkGray
}

# 2. npm uninstall
Write-Host "  Checking npm install..." -NoNewline
$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) {
    $check = & npm list -g cipher-agent 2>$null | Select-String "cipher-agent"
    if ($check) {
        & npm uninstall -g cipher-agent 2>$null | Out-Null
        $removed += "npm package  (cipher-agent)"
        Write-Host " removed" -ForegroundColor Green
    } else {
        Write-Host " not installed" -ForegroundColor DarkGray
    }
} else {
    Write-Host " npm not found" -ForegroundColor DarkGray
}

# 3. ~/.cipher data directory
Write-Host "  Checking data directory..." -NoNewline
$dataDir = Join-Path $HOME ".cipher"
if (Test-Path $dataDir) {
    Remove-Item -Recurse -Force $dataDir -ErrorAction SilentlyContinue
    if (-not (Test-Path $dataDir)) {
        $removed += "data directory ($dataDir)"
        Write-Host " removed" -ForegroundColor Green
    } else {
        $failed += "data directory ($dataDir) — delete manually"
        Write-Host " FAILED (try as Administrator)" -ForegroundColor Red
    }
} else {
    Write-Host " not found" -ForegroundColor DarkGray
}

# 4. Stray executables in PATH
Write-Host "  Checking stray executables..." -NoNewline
$found = 0
foreach ($name in @("cipher.exe", "cip.exe", "cipher-agent.exe")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
        Remove-Item -Force $cmd.Source -ErrorAction SilentlyContinue
        $removed += "executable   ($($cmd.Source))"
        $found++
    }
}
if ($found -gt 0) {
    Write-Host " removed $found file(s)" -ForegroundColor Green
} else {
    Write-Host " none found" -ForegroundColor DarkGray
}

# 5. AppData Local / Roaming scan
foreach ($base in @($env:LOCALAPPDATA, $env:APPDATA)) {
    $dir = Join-Path $base "cipher-agent"
    if (Test-Path $dir) {
        Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
        $removed += "AppData dir  ($dir)"
    }
    $dir2 = Join-Path $base "cipher"
    if (Test-Path $dir2) {
        Remove-Item -Recurse -Force $dir2 -ErrorAction SilentlyContinue
        $removed += "AppData dir  ($dir2)"
    }
}

# Summary
Write-Host ""
if ($removed.Count -gt 0) {
    Write-Host "  Removed:" -ForegroundColor Green
    foreach ($r in $removed) { Write-Host "    - $r" -ForegroundColor Green }
}
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "  Could not remove:" -ForegroundColor Red
    foreach ($f in $failed) { Write-Host "    - $f" -ForegroundColor Red }
}
Write-Host ""
Write-Host "  Cipher has been removed." -ForegroundColor Cyan
if ($removed.Count -eq 0 -and $failed.Count -eq 0) {
    Write-Host "  (Nothing was installed — already clean.)" -ForegroundColor DarkGray
}
Write-Host ""

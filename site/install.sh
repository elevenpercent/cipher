#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "  ____ _   _ ____   ____ ___  "
echo " / ___| | | |  _ \ / ___/ _ \ "
echo "| |   | | | | |_) | |  | | | |"
echo "| |___| |_| |  _ <| |__| |_| |"
echo " \____|\___/|_| \_\\____\___/ "
echo ""
echo "cipher.elevenpct.com"
echo ""

# Find python 3.10+
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
        if [ "$ver" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10+ not found. Install it from python.org then re-run."
    exit 1
fi
echo "Found: $($PYTHON --version)"

echo ""
echo "Installing cipher..."

# Try plain pip first; fall back to --break-system-packages for PEP 668 distros
if ! "$PYTHON" -m pip install git+https://github.com/elevenpercent/cipher.git@master --quiet 2>/dev/null; then
    if ! "$PYTHON" -m pip install git+https://github.com/elevenpercent/cipher.git@master --quiet --break-system-packages; then
        echo "ERROR: Install failed. Try: pip install --user git+https://github.com/elevenpercent/cipher.git@master"
        exit 1
    fi
fi

echo "Installed: cipher v0.5.0"

# Warn if cip isn't on PATH
if ! command -v cip &>/dev/null; then
    echo ""
    echo "NOTE: 'cip' not found on PATH. You may need to add your Python scripts dir:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "  (add this to your ~/.bashrc or ~/.zshrc)"
fi

echo ""
echo "Done! Run:"
echo "  cd your-project"
echo "  cip"
echo ""

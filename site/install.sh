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

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3.10+ not found"
    exit 1
fi
echo "Found: $(python3 --version)"

echo ""
echo "Installing cipher..."
python3 -m pip install git+https://github.com/elevenpercent/cipher.git@master --quiet
echo "Installed: cipher"

echo ""
echo "Done! Run:"
echo "  cd your-project"
echo "  cip --setup"
echo ""

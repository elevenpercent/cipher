#!/usr/bin/env bash
# Cipher Uninstaller — macOS / Linux
# Usage: curl -fsSL https://cipher.elevenpct.com/uninstall.sh | bash
#    or: bash ./uninstall.sh

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; GRAY='\033[0;90m'; NC='\033[0m'

echo ""
echo -e "  ${CYAN}Cipher Uninstaller${NC}"
echo -e "  ${CYAN}==================${NC}"
echo ""

removed=()
failed=()

# 1. pip uninstall
printf "  Checking pip install... "
PIP=$(command -v pip3 || command -v pip)
if [ -n "$PIP" ]; then
    if "$PIP" show cipher-agent &>/dev/null; then
        "$PIP" uninstall cipher-agent -y &>/dev/null
        removed+=("pip package  (cipher-agent)")
        echo -e "${GREEN}removed${NC}"
    else
        echo -e "${GRAY}not installed${NC}"
    fi
else
    echo -e "${GRAY}pip not found${NC}"
fi

# 2. npm uninstall
printf "  Checking npm install... "
if command -v npm &>/dev/null; then
    if npm list -g cipher-agent 2>/dev/null | grep -q cipher-agent; then
        npm uninstall -g cipher-agent &>/dev/null
        removed+=("npm package  (cipher-agent)")
        echo -e "${GREEN}removed${NC}"
    else
        echo -e "${GRAY}not installed${NC}"
    fi
else
    echo -e "${GRAY}npm not found${NC}"
fi

# 3. ~/.cipher data directory
printf "  Checking data directory... "
DATA_DIR="$HOME/.cipher"
if [ -d "$DATA_DIR" ]; then
    rm -rf "$DATA_DIR"
    if [ ! -d "$DATA_DIR" ]; then
        removed+=("data directory ($DATA_DIR)")
        echo -e "${GREEN}removed${NC}"
    else
        failed+=("data directory ($DATA_DIR) — try: sudo rm -rf $DATA_DIR")
        echo -e "${RED}FAILED${NC}"
    fi
else
    echo -e "${GRAY}not found${NC}"
fi

# 4. Stray executables
printf "  Checking stray executables... "
found=0
for name in cipher cip cipher-agent; do
    p=$(command -v "$name" 2>/dev/null)
    if [ -n "$p" ]; then
        rm -f "$p" 2>/dev/null && removed+=("executable   ($p)") && ((found++)) || failed+=("executable ($p) — try: sudo rm -f $p")
    fi
done
if [ "$found" -gt 0 ]; then
    echo -e "${GREEN}removed $found file(s)${NC}"
else
    echo -e "${GRAY}none found${NC}"
fi

# Summary
echo ""
if [ ${#removed[@]} -gt 0 ]; then
    echo -e "  ${GREEN}Removed:${NC}"
    for r in "${removed[@]}"; do echo -e "    ${GREEN}- $r${NC}"; done
fi
if [ ${#failed[@]} -gt 0 ]; then
    echo ""
    echo -e "  ${RED}Could not remove:${NC}"
    for f in "${failed[@]}"; do echo -e "    ${RED}- $f${NC}"; done
fi
echo ""
echo -e "  ${CYAN}Cipher has been removed.${NC}"
[ ${#removed[@]} -eq 0 ] && [ ${#failed[@]} -eq 0 ] && echo -e "  ${GRAY}(Nothing was installed — already clean.)${NC}"
echo ""

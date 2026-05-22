#!/usr/bin/env bash
# Cipher - One-line installer for macOS and Linux
# Usage: curl -fsSL https://cipher.elevenpct.com/install.sh | bash
set -euo pipefail

echo ""
echo "  ____ _   _ ____   ____ ___  "
echo " / ___| | | |  _ \\ / ___/ _ \\ "
echo "| |   | | | | |_) | |  | | | |"
echo "| |___| |_| |  _ <| |__| |_| |"
echo " \\____|\\___|_| \\_\\\\____\\___/ "
echo ""
echo "cipher.elevenpct.com"
echo ""

# ── Step 1: Find or install Python 3.10+ ─────────────────────────────────────
find_python() {
    for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            ok=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
            if [ "$ok" = "True" ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=$(find_python || true)

if [ -z "$PYTHON" ]; then
    echo "Python 3.10+ not found — attempting to install automatically..."

    OS="$(uname -s)"

    if [ "$OS" = "Darwin" ]; then
        # macOS: use Homebrew, installing it first if needed
        if ! command -v brew &>/dev/null; then
            echo "Installing Homebrew (required for Python on macOS)..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add brew to PATH for Apple Silicon
            if [ -f /opt/homebrew/bin/brew ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            fi
        fi
        echo "Installing Python 3 via Homebrew..."
        brew install python3
    elif command -v apt-get &>/dev/null; then
        # Debian / Ubuntu
        echo "Installing Python 3 via apt..."
        sudo apt-get update -q
        sudo apt-get install -y python3 python3-pip python3-venv
    elif command -v dnf &>/dev/null; then
        # Fedora / RHEL / CentOS Stream
        echo "Installing Python 3 via dnf..."
        sudo dnf install -y python3 python3-pip
    elif command -v yum &>/dev/null; then
        # Older CentOS / RHEL
        echo "Installing Python 3 via yum..."
        sudo yum install -y python3 python3-pip
    elif command -v pacman &>/dev/null; then
        # Arch Linux
        echo "Installing Python via pacman..."
        sudo pacman -S --noconfirm python python-pip
    elif command -v zypper &>/dev/null; then
        # openSUSE
        echo "Installing Python 3 via zypper..."
        sudo zypper install -y python3 python3-pip
    else
        echo "ERROR: Cannot auto-install Python on this system."
        echo "Please install Python 3.10+ from: https://python.org/downloads"
        exit 1
    fi

    PYTHON=$(find_python || true)
    if [ -z "$PYTHON" ]; then
        echo "ERROR: Python still not found after installation attempt."
        echo "Please install Python 3.10+ from: https://python.org/downloads"
        exit 1
    fi
fi

echo "Python: $($PYTHON --version)"

# ── Step 2: Make sure pip is available ───────────────────────────────────────
if ! "$PYTHON" -m pip --version &>/dev/null; then
    echo "pip not found — bootstrapping..."
    if "$PYTHON" -m ensurepip --upgrade &>/dev/null; then
        true
    else
        echo "Downloading get-pip.py..."
        curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$PYTHON"
    fi
fi

# ── Step 3: Install Cipher ────────────────────────────────────────────────────
echo ""
echo "Installing Cipher..."

# Try git+ if git is available, fall back to zip URL (no git needed)
INSTALLED=false

if command -v git &>/dev/null; then
    if "$PYTHON" -m pip install --upgrade --no-cache-dir \
        git+https://github.com/elevenpercent/cipher.git@master --quiet 2>/dev/null; then
        INSTALLED=true
    fi
fi

if [ "$INSTALLED" = false ]; then
    # No git, or git install failed — use GitHub archive zip (no git required)
    FLAGS="--upgrade --no-cache-dir --quiet"
    URL="https://github.com/elevenpercent/cipher/archive/refs/heads/master.zip"

    if ! "$PYTHON" -m pip install $FLAGS "$URL" 2>/dev/null; then
        # PEP 668 distros (Debian 12+, Ubuntu 23+) require --break-system-packages
        if ! "$PYTHON" -m pip install $FLAGS --break-system-packages "$URL"; then
            echo "ERROR: Install failed. Try:"
            echo "  pip install --user $URL"
            exit 1
        fi
    fi
fi

echo "Installed: Cipher v0.6.0"

# ── Step 4: Add ~/.local/bin to PATH so 'cip' works everywhere ───────────────
LOCAL_BIN="$HOME/.local/bin"
SCRIPTS=$("$PYTHON" -c "import sysconfig; print(sysconfig.get_path('scripts'))" 2>/dev/null || echo "$LOCAL_BIN")

# Determine which shell config file to update
SHELL_RC=""
if [ -n "${BASH_VERSION:-}" ] || [ "${SHELL:-}" = "/bin/bash" ] || [ "${SHELL:-}" = "/usr/bin/bash" ]; then
    SHELL_RC="$HOME/.bashrc"
    [ -f "$HOME/.bash_profile" ] && SHELL_RC="$HOME/.bash_profile"
elif [ -n "${ZSH_VERSION:-}" ] || [ "${SHELL:-}" = "/bin/zsh" ] || [ "${SHELL:-}" = "/usr/bin/zsh" ]; then
    SHELL_RC="$HOME/.zshrc"
fi

for dir in "$SCRIPTS" "$LOCAL_BIN"; do
    if [ -d "$dir" ] && [[ ":$PATH:" != *":$dir:"* ]]; then
        export PATH="$dir:$PATH"
        if [ -n "$SHELL_RC" ] && ! grep -q "$dir" "$SHELL_RC" 2>/dev/null; then
            echo "export PATH=\"$dir:\$PATH\"" >> "$SHELL_RC"
            echo "Added $dir to PATH in $SHELL_RC"
        fi
    fi
done

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
if command -v cip &>/dev/null; then
    echo "All done! Run:"
else
    echo "All done! You may need to open a new terminal, then run:"
fi
echo "  cd your-project"
echo "  cip"
echo ""

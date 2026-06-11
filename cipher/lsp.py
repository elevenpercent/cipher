"""Lightweight LSP-style diagnostics via subprocess linters.

Runs after every file write/edit and feeds real errors back to the agent
before it wastes turns running broken code.

Supported:
  .py            → ruff (preferred) or py_compile fallback
  .js .ts .jsx .tsx → tsc --noEmit (if installed)
  others         → nothing (no false positives)
"""

import shutil
import subprocess
import sys
from pathlib import Path

_TIMEOUT = 12


def check(path: str) -> str:
    """Return diagnostic string for a file, or '' if clean / unsupported."""
    ext = Path(path).suffix.lower()
    if ext == ".py":
        return _check_python(path)
    if ext in (".js", ".ts", ".jsx", ".tsx"):
        return _check_js(path)
    return ""


def _check_python(path: str) -> str:
    if shutil.which("ruff"):
        try:
            r = subprocess.run(
                ["ruff", "check", "--output-format=concise", "--no-fix", path],
                capture_output=True, text=True, timeout=_TIMEOUT,
            )
            out = r.stdout.strip()
            if out:
                lines = [l for l in out.splitlines() if l.strip()][:12]
                return "\n".join(lines)
            return ""
        except (OSError, subprocess.TimeoutExpired):
            pass

    # py_compile: syntax only, always available
    try:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", path],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        if r.returncode != 0:
            return (r.stderr or r.stdout).strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def _check_js(path: str) -> str:
    if not shutil.which("tsc"):
        return ""
    try:
        r = subprocess.run(
            ["tsc", "--noEmit", "--allowJs", "--checkJs", "--strict", path],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        if r.returncode != 0:
            out = (r.stdout + r.stderr).strip()
            lines = [l for l in out.splitlines() if l.strip()][:12]
            return "\n".join(lines)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""

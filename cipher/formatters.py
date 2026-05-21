# Derived from opencode (MIT) - Copyright (c) 2025 opencode.ai
import os
import subprocess
import shutil
import re
from pathlib import Path


class Formatter:
    name = ""
    extensions = []
    command = ""

    def can_format(self, filepath):
        ext = Path(filepath).suffix
        return ext in self.extensions

    def format(self, filepath, cwd=None):
        raise NotImplementedError


class RuffFormatter(Formatter):
    name = "ruff"
    extensions = [".py"]
    command = "ruff"

    def format(self, filepath, cwd=None):
        if not shutil.which("ruff"):
            return None
        try:
            r = subprocess.run(
                ["ruff", "check", "--fix", filepath],
                capture_output=True, text=True, timeout=30, cwd=cwd
            )
            r2 = subprocess.run(
                ["ruff", "format", filepath],
                capture_output=True, text=True, timeout=30, cwd=cwd
            )
            output = (r.stdout + r.stderr + r2.stdout + r2.stderr).strip()
            return output[:500] if output else "Formatted with ruff"
        except subprocess.TimeoutExpired:
            return "ruff timeout"
        except Exception as e:
            return f"ruff error: {e}"


class BlackFormatter(Formatter):
    name = "black"
    extensions = [".py"]
    command = "black"

    def format(self, filepath, cwd=None):
        if not shutil.which("black"):
            return None
        try:
            r = subprocess.run(
                ["black", "--quiet", filepath],
                capture_output=True, text=True, timeout=30, cwd=cwd
            )
            output = (r.stdout + r.stderr).strip()
            if "reformatted" in output or "unchanged" in output:
                return "Formatted with black"
            return output[:500] if output else None
        except subprocess.TimeoutExpired:
            return "black timeout"
        except Exception as e:
            return f"black error: {e}"


class PrettierFormatter(Formatter):
    name = "prettier"
    extensions = [".js", ".jsx", ".ts", ".tsx", ".json", ".css", ".scss", ".html", ".md", ".yaml", ".yml"]
    command = "prettier"

    def format(self, filepath, cwd=None):
        if not shutil.which("prettier"):
            return None
        try:
            r = subprocess.run(
                ["prettier", "--write", filepath],
                capture_output=True, text=True, timeout=30, cwd=cwd
            )
            output = (r.stdout + r.stderr).strip()
            return output[:500] if output else "Formatted with prettier"
        except subprocess.TimeoutExpired:
            return "prettier timeout"
        except Exception as e:
            return f"prettier error: {e}"


class GoFmtFormatter(Formatter):
    name = "gofmt"
    extensions = [".go"]
    command = "gofmt"

    def format(self, filepath, cwd=None):
        if not shutil.which("gofmt"):
            return None
        try:
            r = subprocess.run(
                ["gofmt", "-w", filepath],
                capture_output=True, text=True, timeout=30, cwd=cwd
            )
            output = (r.stdout + r.stderr).strip()
            return output[:500] if output else "Formatted with gofmt"
        except subprocess.TimeoutExpired:
            return "gofmt timeout"
        except Exception as e:
            return f"gofmt error: {e}"


class RustFmtFormatter(Formatter):
    name = "rustfmt"
    extensions = [".rs"]
    command = "rustfmt"

    def format(self, filepath, cwd=None):
        if not shutil.which("rustfmt"):
            return None
        try:
            r = subprocess.run(
                ["rustfmt", filepath],
                capture_output=True, text=True, timeout=30, cwd=cwd
            )
            output = (r.stdout + r.stderr).strip()
            return output[:500] if output else "Formatted with rustfmt"
        except subprocess.TimeoutExpired:
            return "rustfmt timeout"
        except Exception as e:
            return f"rustfmt error: {e}"


class ClangFormatFormatter(Formatter):
    name = "clang-format"
    extensions = [".c", ".cpp", ".h", ".hpp", ".cs", ".java"]
    command = "clang-format"

    def format(self, filepath, cwd=None):
        if not shutil.which("clang-format"):
            return None
        try:
            subprocess.run(
                ["clang-format", "-i", filepath],
                capture_output=True, text=True, timeout=30, cwd=cwd
            )
            return "Formatted with clang-format"
        except subprocess.TimeoutExpired:
            return "clang-format timeout"
        except Exception as e:
            return f"clang-format error: {e}"


BUILTIN_FORMATTERS = [
    RuffFormatter(),
    BlackFormatter(),
    PrettierFormatter(),
    GoFmtFormatter(),
    RustFmtFormatter(),
    ClangFormatFormatter(),
]


class FormatterManager:
    def __init__(self):
        self.formatters = list(BUILTIN_FORMATTERS)
        self.enabled = True
        self.lint_command = ""

    def format_file(self, filepath, cwd=None):
        if not self.enabled or not filepath:
            return None
        results = []
        for fmt in self.formatters:
            if fmt.can_format(filepath):
                result = fmt.format(filepath, cwd)
                if result:
                    results.append(result)
        return results

    def format_all(self, files, cwd=None):
        if not files:
            return {}
        results = {}
        for f in files:
            r = self.format_file(f, cwd)
            if r:
                results[f] = r
        return results

    def run_lint(self, cwd=None):
        if not self.lint_command:
            return ""
        try:
            r = subprocess.run(
                self.lint_command, shell=True, capture_output=True, text=True, timeout=30, cwd=cwd
            )
            if r.returncode != 0:
                out = (r.stdout + r.stderr)[:500].strip()
                return f"Lint ({self.lint_command}):\n{out}" if out else ""
        except Exception:
            pass
        return ""

    def detect_available(self):
        available = []
        for fmt in self.formatters:
            if shutil.which(fmt.command):
                available.append(fmt.name)
        return sorted(available)

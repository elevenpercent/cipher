"""Tool implementations. Pure functions — no UI, no global state.

Read-only tools execute directly. Mutating tools (write/edit) are split
into prepare() -> diff for approval, then apply(). Commands (run/git)
return the command string for approval before execute_command() runs it.

Every result is {"ok": bool, "output": str, ...extras}.
"""

import difflib
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

MAX_OUTPUT = 12_000          # chars fed back to the model per tool
RUN_TIMEOUT = 60

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".next", ".nuxt",
    ".idea", ".vscode", "target", ".tox", "coverage", ".cache",
}

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".mp3",
    ".mp4", ".wav", ".avi", ".mov", ".zip", ".tar", ".gz", ".7z",
    ".rar", ".exe", ".dll", ".so", ".dylib", ".bin", ".db", ".sqlite",
    ".pdf", ".pyc", ".class", ".o", ".woff", ".woff2", ".ttf",
}


def _clip(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} chars total]"


def _resolve(root: str, rel: str) -> Path:
    """Resolve a path and refuse anything outside the project root."""
    rel = rel.strip().strip('"').strip("'")
    p = Path(rel)
    if not p.is_absolute():
        p = Path(root) / p
    p = p.resolve()
    root_r = Path(root).resolve()
    if root_r not in p.parents and p != root_r:
        raise ValueError(f"path escapes project root: {rel}")
    return p


# ── read-only tools ───────────────────────────────────────────────────

def tool_read(root: str, body: str) -> dict:
    spec = body.strip()
    line_range = None
    if "::" in spec:
        spec, _, rng = spec.rpartition("::")
        m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", rng)
        if m:
            line_range = (int(m.group(1)), int(m.group(2)))
    try:
        path = _resolve(root, spec)
        if path.suffix.lower() in BINARY_EXT:
            return {"ok": False, "output": f"{spec} is a binary file"}
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError) as e:
        return {"ok": False, "output": f"read failed: {e}"}
    lines = text.splitlines()
    if line_range:
        lo, hi = line_range
        lines = lines[lo - 1:hi]
        offset = lo
    else:
        offset = 1
    numbered = "\n".join(f"{i + offset:>5}| {l}" for i, l in enumerate(lines))
    return {"ok": True, "output": _clip(numbered) or "(empty file)"}


def tool_ls(root: str, body: str) -> dict:
    try:
        path = _resolve(root, body.strip() or ".")
        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except (OSError, ValueError) as e:
        return {"ok": False, "output": f"ls failed: {e}"}
    out = []
    for e in entries:
        if e.name in SKIP_DIRS:
            continue
        out.append(f"{e.name}/" if e.is_dir() else e.name)
    return {"ok": True, "output": _clip("\n".join(out)) or "(empty directory)"}


def tool_glob(root: str, body: str) -> dict:
    pattern = body.strip()
    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            posix = rel.replace(os.sep, "/")
            if fnmatch.fnmatch(posix, pattern) or fnmatch.fnmatch(name, pattern):
                matches.append(posix)
                if len(matches) >= 300:
                    break
    return {"ok": True, "output": _clip("\n".join(matches)) or "no matches"}


def tool_grep(root: str, body: str) -> dict:
    lines_in = body.strip().splitlines()
    pattern = lines_in[0].strip() if lines_in else ""
    subdir = lines_in[1].strip() if len(lines_in) > 1 else "."
    if not pattern:
        return {"ok": False, "output": "grep needs a pattern"}
    try:
        rx = re.compile(pattern, re.IGNORECASE)
        base = _resolve(root, subdir)
    except (re.error, ValueError) as e:
        return {"ok": False, "output": f"grep failed: {e}"}
    hits = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            fp = Path(dirpath) / name
            if fp.suffix.lower() in BINARY_EXT:
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = os.path.relpath(fp, root).replace(os.sep, "/")
            for n, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                    if len(hits) >= 200:
                        return {"ok": True, "output": _clip("\n".join(hits))}
    return {"ok": True, "output": _clip("\n".join(hits)) or "no matches"}


def tool_tree(root: str, body: str) -> dict:
    """Compact project overview: top 2 levels of files."""
    out = []
    base = Path(root)
    try:
        for entry in sorted(base.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
            if entry.name in SKIP_DIRS or entry.name.startswith("."):
                continue
            if entry.is_dir():
                out.append(f"{entry.name}/")
                try:
                    children = sorted(entry.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
                except OSError:
                    continue
                for c in children[:25]:
                    if c.name in SKIP_DIRS:
                        continue
                    out.append(f"  {c.name}{'/' if c.is_dir() else ''}")
            else:
                out.append(entry.name)
    except OSError as e:
        return {"ok": False, "output": f"tree failed: {e}"}
    return {"ok": True, "output": _clip("\n".join(out)) or "(empty project)"}


# ── mutating tools: prepare -> approve -> apply ───────────────────────

def _make_diff(rel: str, old: str, new: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{rel}", tofile=f"b/{rel}",
    )
    return "".join(diff)


def prepare_write(root: str, body: str) -> dict:
    """Body: first line = path, remainder = full file content."""
    first, _, content = body.partition("\n")
    rel = first.strip()
    if not rel:
        return {"ok": False, "output": "write needs a path on the first line"}
    try:
        path = _resolve(root, rel)
    except ValueError as e:
        return {"ok": False, "output": str(e)}
    old = ""
    if path.exists():
        try:
            old = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            old = ""
    if content and not content.endswith("\n"):
        content += "\n"
    rel_disp = os.path.relpath(path, root).replace(os.sep, "/")
    return {
        "ok": True, "action": "write", "path": str(path), "rel": rel_disp,
        "content": content, "new_file": not Path(path).exists(),
        "diff": _make_diff(rel_disp, old, content),
        "output": "",
    }


EDIT_RX = re.compile(r"<{4,}\n(.*?)\n?={4,}\n(.*?)\n?>{4,}", re.DOTALL)


def prepare_edit(root: str, body: str) -> dict:
    """Body: first line = path, then one or more <<<< old ==== new >>>> blocks."""
    first, _, rest = body.partition("\n")
    rel = first.strip()
    try:
        path = _resolve(root, rel)
        old_text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError) as e:
        return {"ok": False, "output": f"edit failed: {e}"}
    blocks = EDIT_RX.findall(rest)
    if not blocks:
        return {"ok": False, "output":
                "edit needs blocks like:\n<<<<\nold text\n====\nnew text\n>>>>"}
    new_text = old_text
    for old_part, new_part in blocks:
        if old_part not in new_text:
            # try a whitespace-tolerant match
            loose = re.escape(old_part.strip())
            loose = re.sub(r"\\\s+", r"\\s+", loose)
            m = re.search(loose, new_text)
            if not m:
                return {"ok": False, "output":
                        f"edit failed: text not found in {rel}:\n{old_part[:300]}"}
            new_text = new_text[:m.start()] + new_part + new_text[m.end():]
        else:
            new_text = new_text.replace(old_part, new_part, 1)
    rel_disp = os.path.relpath(path, root).replace(os.sep, "/")
    return {
        "ok": True, "action": "edit", "path": str(path), "rel": rel_disp,
        "content": new_text, "new_file": False,
        "diff": _make_diff(rel_disp, old_text, new_text),
        "output": "",
    }


def apply_file_change(prep: dict) -> dict:
    try:
        path = Path(prep["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prep["content"], encoding="utf-8")
    except OSError as e:
        return {"ok": False, "output": f"could not write {prep['rel']}: {e}"}
    n = prep["content"].count("\n")
    verb = "created" if prep.get("new_file") else "updated"
    return {"ok": True, "output": f"{verb} {prep['rel']} ({n} lines)"}


# ── commands ──────────────────────────────────────────────────────────

def execute_command(root: str, command: str) -> dict:
    if sys.platform == "win32":
        args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
    else:
        args = ["/bin/sh", "-c", command]
    try:
        proc = subprocess.run(
            args, cwd=root, capture_output=True, text=True,
            timeout=RUN_TIMEOUT, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"command timed out after {RUN_TIMEOUT}s"}
    except OSError as e:
        return {"ok": False, "output": f"could not run command: {e}"}
    out = (proc.stdout or "").rstrip()
    err = (proc.stderr or "").rstrip()
    combined = out
    if err:
        combined = f"{combined}\n[stderr]\n{err}" if combined else f"[stderr]\n{err}"
    if proc.returncode != 0:
        combined = f"{combined}\n[exit code {proc.returncode}]" if combined else f"[exit code {proc.returncode}]"
    return {"ok": proc.returncode == 0, "output": _clip(combined) or "(no output)"}


# ── web tools ─────────────────────────────────────────────────────────

_UA = {"User-Agent": "Mozilla/5.0 (cipher-agent)"}


def tool_web_fetch(root: str, body: str) -> dict:
    url = body.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(1_500_000).decode("utf-8", errors="replace")
    except OSError as e:
        return {"ok": False, "output": f"fetch failed: {e}"}
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"ok": True, "output": _clip(text, 20_000) or "(no text content)"}


def tool_web_search(root: str, body: str) -> dict:
    query = body.strip()
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except OSError as e:
        return {"ok": False, "output": f"search failed: {e}"}
    results = []
    for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL):
        href, title, snippet = m.groups()
        qm = re.search(r"uddg=([^&]+)", href)
        if qm:
            href = urllib.parse.unquote(qm.group(1))
        title = re.sub(r"<[^>]+>", "", title).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet).strip()
        results.append(f"{title}\n  {href}\n  {snippet}")
        if len(results) >= 6:
            break
    return {"ok": True, "output": "\n\n".join(results) or "no results"}


READ_ONLY_TOOLS = {
    "read": tool_read,
    "ls": tool_ls,
    "glob": tool_glob,
    "grep": tool_grep,
    "tree": tool_tree,
    "web-fetch": tool_web_fetch,
    "web-search": tool_web_search,
}

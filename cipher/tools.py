import os
import re
import json
import sys
import difflib
import subprocess
import urllib.request
import urllib.parse
import glob as glob_module
import fnmatch
from pathlib import Path
from datetime import datetime

TOOLS_DIR = Path.home() / ".cipher" / "tools"


def _load_dotenv(project_root):
    """Load key=value pairs from .env in project_root. Returns a dict."""
    env_vars = {}
    env_path = os.path.join(project_root, ".env")
    try:
        with open(env_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    env_vars[key] = value
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return env_vars

_BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.flac',
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar', '.exe', '.dll',
    '.so', '.dylib', '.bin', '.dat', '.db', '.sqlite', '.pdf',
    '.pyc', '.pyo', '.class', '.o', '.a',
}

_SKIP_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
    '.mypy_cache', '.pytest_cache', 'dist', 'build', '.next', '.nuxt',
    '.tox', 'coverage', '.coverage', 'htmlcov', 'eggs', '.eggs',
}


def _is_subpath(child, parent):
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False


def _is_binary_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in _BINARY_EXTENSIONS:
        return True
    try:
        with open(path, 'rb') as f:
            chunk = f.read(8192)
        return b'\x00' in chunk
    except Exception:
        return False


def _strip_html(raw):
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<head[^>]*>.*?</head>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') \
               .replace('&nbsp;', ' ').replace('&quot;', '"').replace('&#39;', "'")
    return re.sub(r'\s+', ' ', text).strip()


class Tool:
    name = ""
    description = ""
    parameters = {}
    builtin = False

    def execute(self, args, body, project_root, context=None):
        raise NotImplementedError


class RunTool(Tool):
    name = "run"
    description = "Execute a shell command"
    parameters = {"type": "object", "properties": {"command": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        cmd = args.strip()
        try:
            dotenv_vars = _load_dotenv(project_root)
            merged_env = {**os.environ, **dotenv_vars}
            if sys.platform == "win32":
                # Only replace &&-between-commands (not inside quotes)
                # Safe approach: replace standalone && tokens
                cmd = re.sub(r'(?<!["\'])&&(?!["\'])', '; ', cmd)
                proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "-ExecutionPolicy", "Bypass", "-Command", cmd],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, cwd=project_root, env=merged_env
                )
            else:
                proc = subprocess.Popen(
                    cmd, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, cwd=project_root, env=merged_env
                )
            try:
                out, err = proc.communicate(timeout=30)
                success = proc.returncode == 0
                combined = out.rstrip() if out.rstrip() else err.rstrip()
                result = combined or "(ok)"
                if len(result) > 4000:
                    result = result[:4000] + f"\n... (truncated, {len(result)-4000} more chars)"
                return {"result": result, "success": success, "exit_code": proc.returncode}
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    out, err = proc.communicate(timeout=5)
                    partial = (out or "").rstrip() or (err or "").rstrip()
                except Exception:
                    partial = ""
                msg = "Process timed out after 30s (still running in background)"
                if partial:
                    msg += f"\nPartial output:\n{partial[:1000]}"
                return {"result": msg, "success": True, "exit_code": 0}
        except Exception as e:
            return {"result": f"Error: {e}", "success": False, "exit_code": -1}


class WriteTool(Tool):
    name = "write"
    description = "Write content to a file"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = (args or "").strip().strip('"').strip("'")
        if not path:
            return {"result": "No path provided", "success": False}
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        root = os.path.normpath(project_root)
        if not _is_subpath(full, root):
            return {"result": "Path escapes project root", "success": False}
        old_content = ""
        if os.path.exists(full):
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    old_content = f.read()
            except Exception:
                pass
        text = body.strip() if body else ""
        try:
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)
            lines = text.count("\n") + 1 if text else 0
            return {"result": f"Written: {path} ({lines} lines)", "success": True, "old_content": old_content}
        except Exception as e:
            return {"result": f"Error: {e}", "success": False}


class ReadTool(Tool):
    name = "read"
    description = "Read a file"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = (args or "").strip().strip('"').strip("'")
        if not path:
            return {"result": "No path provided", "success": False}
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        root = os.path.normpath(project_root)
        if not _is_subpath(full, root):
            return {"result": "Path escapes project root", "success": False}
        if not os.path.exists(full):
            return {"result": f"File not found: {path}", "success": False}
        if _is_binary_file(full):
            size = os.path.getsize(full)
            return {"result": f"Binary file: {path} ({size} bytes) — cannot display", "success": False}
        try:
            line_range = json.loads(body) if body else {}
            start = line_range.get("start")
            end = line_range.get("end")
        except Exception:
            start = end = None
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return {"result": f"Error reading file: {e}", "success": False}
        if start is not None or end is not None:
            s = max(0, (start or 1) - 1)
            e = min(len(lines), end or len(lines))
            content = "".join(lines[s:e])
        else:
            content = "".join(lines)
        if len(content) > 8000:
            content = content[:8000] + f"\n... (truncated — {len(lines)} lines total, use start/end to read sections)"
        return {"result": content, "success": True, "lines": len(lines)}


class LsTool(Tool):
    name = "ls"
    description = "List directory contents"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = (args or ".").strip().strip('"').strip("'")
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        root = os.path.normpath(project_root)
        if not _is_subpath(full, root):
            return {"result": "Path escapes project root", "success": False}
        if not os.path.isdir(full):
            return {"result": f"Not a directory: {path}", "success": False}
        entries = []
        try:
            for e in sorted(os.listdir(full)):
                ep = os.path.join(full, e)
                is_dir = os.path.isdir(ep)
                if is_dir:
                    entries.append(f"DIR {e}/")
                else:
                    size = os.path.getsize(ep)
                    size_str = f"{size:,}B" if size < 1024 else f"{size//1024:,}KB"
                    entries.append(f"    {e}  ({size_str})")
        except PermissionError:
            return {"result": f"Permission denied: {path}", "success": False}
        return {"result": "\n".join(entries), "success": True, "count": len(entries)}


class TreeTool(Tool):
    name = "tree"
    description = "Show directory tree structure"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}, "depth": {"type": "integer"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = (args or ".").strip().strip('"').strip("'")
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        root = os.path.normpath(project_root)
        if not _is_subpath(full, root):
            return {"result": "Path escapes project root", "success": False}
        if not os.path.isdir(full):
            return {"result": f"Not a directory: {path}", "success": False}
        try:
            opts = json.loads(body) if body else {}
            max_depth = int(opts.get("depth", 3))
        except Exception:
            max_depth = 3
        lines = [path]
        self._walk(full, "", 0, max_depth, lines)
        result = "\n".join(lines[:300])
        if len(lines) > 300:
            result += f"\n... ({len(lines) - 300} more entries not shown)"
        return {"result": result, "success": True, "count": len(lines) - 1}

    def _walk(self, path, prefix, depth, max_depth, lines):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return
        entries = [e for e in entries if e not in _SKIP_DIRS]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            full_path = os.path.join(path, entry)
            is_dir = os.path.isdir(full_path)
            lines.append(f"{prefix}{connector}{entry}{'/' if is_dir else ''}")
            if is_dir and depth < max_depth:
                extension = "    " if is_last else "│   "
                self._walk(full_path, prefix + extension, depth + 1, max_depth, lines)


class DiffTool(Tool):
    name = "diff"
    description = "Show diff between two files, or git diff of a single file"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}, "path2": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        parts = args.strip().split(None, 1)
        path1 = parts[0].strip('"').strip("'") if parts else ""
        path2 = parts[1].strip('"').strip("'") if len(parts) > 1 else None

        if not path1:
            return {"result": "No file specified", "success": False}

        root = os.path.normpath(project_root)
        full1 = os.path.normpath(os.path.abspath(os.path.join(project_root, path1)))
        if not _is_subpath(full1, root):
            return {"result": "Path escapes project root", "success": False}

        if path2:
            full2 = os.path.normpath(os.path.abspath(os.path.join(project_root, path2)))
            if not _is_subpath(full2, root):
                return {"result": "Path escapes project root", "success": False}
            try:
                with open(full1, encoding="utf-8", errors="replace") as f:
                    lines1 = f.readlines()
                with open(full2, encoding="utf-8", errors="replace") as f:
                    lines2 = f.readlines()
                diff = list(difflib.unified_diff(lines1, lines2, fromfile=path1, tofile=path2, lineterm=""))
                result = "\n".join(diff[:300]) if diff else "Files are identical"
                return {"result": result[:4000], "success": True, "changed_lines": len(diff)}
            except Exception as e:
                return {"result": f"Error: {e}", "success": False}
        else:
            # git diff of single file
            try:
                r = subprocess.run(
                    ["git", "diff", "HEAD", "--", path1],
                    capture_output=True, text=True, timeout=15, cwd=project_root
                )
                result = r.stdout.rstrip() or r.stderr.rstrip() or "No uncommitted changes"
                return {"result": result[:4000], "success": r.returncode == 0}
            except FileNotFoundError:
                return {"result": "git not found", "success": False}
            except Exception as e:
                return {"result": f"Error: {e}", "success": False}


class GrepTool(Tool):
    name = "grep"
    description = "Search file contents with regex"
    parameters = {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        pattern = args
        search_path = body or "."
        full = os.path.normpath(os.path.join(project_root, search_path))
        root = os.path.normpath(project_root)
        if not _is_subpath(full, root):
            return {"result": "Path escapes project root", "success": False}
        if not os.path.isdir(full):
            return {"result": f"Not a directory: {search_path}", "success": False}
        if not pattern:
            return {"result": "No pattern provided", "success": False}
        try:
            regex = re.compile(pattern, re.DOTALL)
        except re.error as e:
            return {"result": f"Invalid regex: {e}", "success": False}
        matches = []
        for dirpath, dirnames, filenames in os.walk(full):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in sorted(filenames):
                fpath = os.path.join(dirpath, fn)
                if _is_binary_file(fpath):
                    continue
                rel = os.path.relpath(fpath, project_root)
                try:
                    with open(fpath, encoding="utf-8", errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line.rstrip()):
                                matches.append(f"{rel}:{i}: {line.rstrip()[:200]}")
                except Exception:
                    pass
                if len(matches) >= 200:
                    break
            if len(matches) >= 200:
                break
        result = "\n".join(matches) if matches else "No matches found"
        if len(matches) >= 200:
            result += "\n... (limit reached, narrow your search)"
        return {"result": result[:4000], "success": True, "count": len(matches)}


class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern"
    parameters = {"type": "object", "properties": {"pattern": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        pattern = args
        if not pattern:
            return {"result": "No pattern provided", "success": False}
        matches = []
        for p in glob_module.iglob(pattern, root_dir=project_root or ".", recursive=True):
            matches.append(p)
        matches.sort()
        result = "\n".join(matches[:300]) if matches else "No files matched"
        extra = f"\n... ({len(matches)-300} more)" if len(matches) > 300 else ""
        return {"result": result[:4000] + extra, "success": True, "count": len(matches)}


class EditTool(Tool):
    name = "edit"
    description = "Edit a file by replacing text"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = (args or "").strip().strip('"').strip("'")
        if not path:
            return {"result": "No path provided", "success": False}
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        root = os.path.normpath(project_root)
        if not _is_subpath(full, root):
            return {"result": "Path escapes project root", "success": False}
        if not os.path.exists(full):
            return {"result": f"File not found: {path}", "success": False}
        try:
            parsed = json.loads(body or "{}")
            old_text = parsed.get("old", "")
            new_text = parsed.get("new", "")
        except Exception:
            return {"result": "Invalid edit body", "success": False}
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return {"result": f"Error reading: {e}", "success": False}
        if old_text not in content:
            # Try swapping quote styles (' <-> ")
            swapped = old_text.translate(str.maketrans({'"': "'", "'": '"'}))
            if swapped in content:
                old_text = swapped
            else:
                # Try normalizing line endings
                normalized = old_text.replace('\r\n', '\n').replace('\r', '\n')
                content_normalized = content.replace('\r\n', '\n').replace('\r', '\n')
                if normalized in content_normalized:
                    content = content_normalized
                    old_text = normalized
                else:
                    # Try stripping trailing whitespace from each line
                    stripped = '\n'.join(line.rstrip() for line in old_text.splitlines())
                    if stripped in content:
                        old_text = stripped
                    else:
                        return {"result": f"Error: old text not found in {path}. Read the file first to get the exact text.", "success": False}
        if content.count(old_text) > 1:
            return {"result": f"Error: old text matched {content.count(old_text)} times in {path}. Make the snippet more unique.", "success": False}
        new_content = content.replace(old_text, new_text, 1)
        try:
            with open(full, "w", encoding="utf-8") as f:
                f.write(new_content)
            return {"result": f"Edited: {path}", "success": True, "old_content": old_text, "new_content": new_text}
        except Exception as e:
            return {"result": f"Error writing: {e}", "success": False}


def _playwright_fetch(url: str, timeout_ms: int = 20000) -> str | None:
    """Fetch a JS-rendered page via Playwright. Returns text or None if unavailable."""
    try:
        from playwright.sync_api import sync_playwright, Error as PWError
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent="Mozilla/5.0 (compatible; Cipher/1.0)")
                page.goto(url, timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except PWError:
                    pass  # networkidle timeout is fine — page still loaded
                text = page.inner_text("body")
                return text
            finally:
                browser.close()
    except ImportError:
        return None  # playwright not installed
    except Exception:
        return None  # playwright installed but failed (e.g. chromium not downloaded)


class WebFetchTool(Tool):
    name = "web-fetch"
    description = "Fetch content from a URL (uses Playwright for JS pages if installed)"
    parameters = {"type": "object", "properties": {"url": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        url = args.strip()
        if not url.startswith(("http://", "https://")):
            return {"result": "Invalid URL — must start with http:// or https://", "success": False}

        # Try Playwright first — handles JS-rendered pages (React, Next.js, etc.)
        pw_text = _playwright_fetch(url)
        if pw_text is not None:
            if len(pw_text) > 6000:
                pw_text = pw_text[:6000] + f"\n... (truncated)"
            return {"result": pw_text.strip(), "success": True, "renderer": "playwright"}

        # Fallback: plain urllib (fast, works for static pages)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Cipher/1.0)"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "text" not in content_type and "json" not in content_type and "xml" not in content_type:
                    return {"result": f"Non-text content type: {content_type}", "success": False}
                raw = resp.read(500_000).decode("utf-8", errors="replace")
            text = _strip_html(raw)
            if len(text) > 6000:
                text = text[:6000] + f"\n... (truncated from {len(raw)} bytes)"
            return {"result": text, "success": True, "renderer": "urllib"}
        except Exception as e:
            return {"result": f"Error fetching: {e}", "success": False}


class WebSearchTool(Tool):
    name = "web-search"
    description = "Search the web"
    parameters = {"type": "object", "properties": {"query": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        query = args.strip()
        if not query:
            return {"result": "No search query", "success": False}
        try:
            url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Cipher/1.0)"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            links = re.findall(r'<a rel="nofollow"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', raw, re.DOTALL)
            results = []
            seen_urls = set()
            for href, text in links:
                clean_href = href.strip()
                clean_text = re.sub(r"<[^>]+>", "", text).strip()
                if not clean_text or "More at" in clean_text:
                    continue
                if clean_href.startswith("//"):
                    clean_href = "https:" + clean_href
                if clean_href in seen_urls or not clean_href.startswith("http"):
                    continue
                seen_urls.add(clean_href)
                results.append(f"{len(results)+1}. {clean_text}\n   {clean_href}")
            result = "\n".join(results[:10]) if results else "No results found"
            return {"result": result[:4000], "success": True, "count": len(results)}
        except Exception as e:
            return {"result": f"Search error: {e}", "success": False}


class GitTool(Tool):
    name = "git"
    description = "Execute git commands"
    parameters = {"type": "object", "properties": {"command": {"type": "string"}, "message": {"type": "string"}}}
    builtin = True

    _SAFE_CMDS = {
        "status", "diff", "log", "show", "branch", "add", "commit",
        "push", "pull", "fetch", "stash", "checkout", "switch", "restore",
        "init", "reset", "tag", "remote", "merge", "rebase", "cherry-pick",
        "rm", "mv", "clone", "describe", "shortlog", "blame", "grep",
    }

    def execute(self, args, body, project_root, context=None):
        cmd = (args or "").strip()
        base = cmd.split()[0] if cmd else "status"
        if base not in self._SAFE_CMDS:
            return {"result": f"Git command '{base}' not allowed. Allowed: {', '.join(sorted(self._SAFE_CMDS))}", "success": False}
        if base == "commit" and body:
            full_cmd = ["git", "commit", "-m", body]
        else:
            full_cmd = ["git"] + cmd.split()
        try:
            r = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30, cwd=project_root)
            out = r.stdout.rstrip()
            err = r.stderr.rstrip()
            result = out or err or "(ok)"
            if len(result) > 3000:
                result = result[:3000] + f"\n... (truncated)"
            return {"result": result, "success": r.returncode == 0, "exit_code": r.returncode}
        except subprocess.TimeoutExpired:
            return {"result": "Error: git timeout after 30s", "success": False}
        except FileNotFoundError:
            return {"result": "Error: git not found. Install git from git-scm.com", "success": False}
        except Exception as e:
            return {"result": f"Error: {e}", "success": False}


class TodoTool(Tool):
    name = "todo"
    description = "Manage todo list"
    parameters = {"type": "object", "properties": {"action": {"type": "string"}, "task": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        context = context or {}
        todo_list = context.get("todo_list", [])
        action = "list"
        rest = args
        eq = args.find("=")
        if eq > 0:
            action = args[:eq].strip()
            rest = args[eq + 1:].strip().strip('"').strip("'")
        elif " " in args.strip():
            parts = args.split(None, 1)
            action = parts[0].lower()
            rest = parts[1].strip('"').strip("'")
        if action == "add" and rest:
            todo_list.append({"task": rest, "done": False})
            status = f"Todo added: {rest}"
        elif action == "done":
            try:
                idx = int(rest) - 1
                if 0 <= idx < len(todo_list):
                    todo_list[idx]["done"] = True
                    status = f"Todo done: {todo_list[idx]['task']}"
                else:
                    status = f"Invalid todo index: {rest}"
            except ValueError:
                status = f"Invalid todo index: {rest}"
        else:
            if not todo_list:
                status = "No todos"
            else:
                lines = []
                for i, t in enumerate(todo_list, 1):
                    mark = chr(0x2713) if t["done"] else " "
                    lines.append(f"  {i}. [{mark}] {t['task']}")
                status = "Todos:\n" + "\n".join(lines)
            return {"result": status, "success": True, "todo_list": todo_list}
        return {"result": status, "success": True, "todo_list": todo_list}


class OpenTool(Tool):
    name = "open"
    description = "Open a file in the system default app"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = (args or "").strip().strip('"').strip("'")
        if not path:
            return {"result": "No path provided", "success": False}
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        if not os.path.exists(full):
            return {"result": f"File not found: {path}", "success": False}
        try:
            if sys.platform == "win32":
                os.startfile(full)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", full])
            else:
                subprocess.Popen(["xdg-open", full])
            return {"result": f"Opened {path}", "success": True}
        except Exception as e:
            return {"result": f"Error: {e}", "success": False}


BUILTIN_TOOLS = {
    "run": RunTool(),
    "write": WriteTool(),
    "read": ReadTool(),
    "ls": LsTool(),
    "tree": TreeTool(),
    "diff": DiffTool(),
    "grep": GrepTool(),
    "glob": GlobTool(),
    "edit": EditTool(),
    "web-fetch": WebFetchTool(),
    "web-search": WebSearchTool(),
    "git": GitTool(),
    "todo": TodoTool(),
    "open": OpenTool(),
}


class ToolRegistry:
    def __init__(self):
        self._tools = dict(BUILTIN_TOOLS)
        self._custom_tools = {}

    def register(self, tool):
        if isinstance(tool, Tool):
            self._tools[tool.name] = tool
        return tool

    def unregister(self, name):
        if name in BUILTIN_TOOLS:
            return False
        self._tools.pop(name, None)
        self._custom_tools.pop(name, None)
        return True

    def get(self, name):
        return self._tools.get(name)

    def list_tools(self):
        return list(self._tools.values())

    def list_builtins(self):
        return [t for t in self._tools.values() if t.builtin]

    def list_custom(self):
        return list(self._custom_tools.values())

    def execute(self, name, args, body, project_root, context=None):
        tool = self._tools.get(name)
        if not tool:
            return {"result": f"Unknown tool: {name}", "success": False}
        return tool.execute(args, body, project_root, context)

    def discover(self, directory=None):
        directory = directory or TOOLS_DIR
        directory = Path(directory)
        directory.mkdir(exist_ok=True)
        init_file = directory / "__init__.py"
        if not init_file.exists():
            init_file.write_text("")
        sys.path.insert(0, str(directory.parent))
        count = 0
        for f in sorted(directory.glob("*.py")):
            if f.name == "__init__.py":
                continue
            try:
                mod_name = f"tools.{f.stem}"
                if mod_name in sys.modules:
                    import importlib
                    mod = importlib.reload(sys.modules[mod_name])
                else:
                    mod = __import__(mod_name, fromlist=[""])
                for name in dir(mod):
                    obj = getattr(mod, name)
                    if isinstance(obj, type) and issubclass(obj, Tool) and obj is not Tool and obj.name:
                        instance = obj()
                        self._custom_tools[instance.name] = instance
                        self._tools[instance.name] = instance
                        count += 1
            except Exception as e:
                print(f"Custom tool load error ({f.name}): {e}", file=sys.stderr)
        return count

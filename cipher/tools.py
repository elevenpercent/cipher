import os
import re
import json
import sys
import subprocess
import urllib.request
import urllib.parse
import glob as glob_module
import fnmatch
from pathlib import Path
from datetime import datetime

TOOLS_DIR = Path.home() / ".cipher" / "tools"


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
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=project_root)
            out = r.stdout.rstrip()
            err = r.stderr.rstrip()[:500]
            success = r.returncode == 0
            result = out or err or "(ok)"
            return {"result": result[:2000], "success": success, "exit_code": r.returncode}
        except subprocess.TimeoutExpired:
            return {"result": "Error: timeout", "success": False, "exit_code": -1}
        except Exception as e:
            return {"result": f"Error: {e}", "success": False, "exit_code": -1}


class WriteTool(Tool):
    name = "write"
    description = "Write content to a file"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = args.strip().strip('"').strip("'")
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        root = os.path.normpath(project_root)
        if not full.startswith(root + os.sep) and full != root:
            return {"result": "Path escapes project root", "success": False}
        old_content = ""
        if os.path.exists(full):
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    old_content = f.read()
            except Exception:
                pass
        try:
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(body.strip() if body else "")
            lines = body.count("\n") + 1 if body else 0
            return {"result": f"Written: {path} ({lines} lines)", "success": True, "old_content": old_content}
        except Exception as e:
            return {"result": f"Error: {e}", "success": False}


class ReadTool(Tool):
    name = "read"
    description = "Read a file"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = args.strip().strip('"').strip("'")
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        root = os.path.normpath(project_root)
        if not full.startswith(root + os.sep) and full != root:
            return {"result": "Path escapes project root", "success": False}
        if not os.path.exists(full):
            return {"result": f"File not found: {path}", "success": False}
        try:
            line_range = json.loads(body) if body else {}
            start = line_range.get("start")
            end = line_range.get("end")
        except Exception:
            start = end = None
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if start is not None or end is not None:
            s = max(0, (start or 1) - 1)
            e = min(len(lines), end or len(lines))
            content = "".join(lines[s:e])
        else:
            content = "".join(lines)
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
        if not full.startswith(root + os.sep) and full != root:
            return {"result": "Path escapes project root", "success": False}
        if not os.path.isdir(full):
            return {"result": f"Not a directory: {path}", "success": False}
        entries = []
        for e in sorted(os.listdir(full)):
            is_dir = os.path.isdir(os.path.join(full, e))
            icon = "DIR" if is_dir else "   "
            entries.append(f"{icon} {e}")
        return {"result": "\n".join(entries), "success": True, "count": len(entries)}


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
        if not full.startswith(root + os.sep) and full != root:
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
            for fn in sorted(filenames):
                fpath = os.path.join(dirpath, fn)
                rel = os.path.relpath(fpath, project_root)
                try:
                    with open(fpath, encoding="utf-8", errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line.rstrip()):
                                matches.append(f"{rel}:{i}: {line.rstrip()[:200]}")
                except Exception:
                    pass
                if len(matches) >= 100:
                    break
            if len(matches) >= 100:
                break
        result = "\n".join(matches) if matches else "No matches found"
        return {"result": result[:3000], "success": True, "count": len(matches)}


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
        for p in glob_module.iglob(pattern, root_dir=project_root, recursive=True):
            matches.append(p)
        matches.sort()
        result = "\n".join(matches[:200]) if matches else "No files matched"
        extra = f" ({len(matches)-200} more)" if len(matches) > 200 else ""
        return {"result": result[:3000], "success": True, "count": len(matches), "extra": extra}


class EditTool(Tool):
    name = "edit"
    description = "Edit a file by replacing text"
    parameters = {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        path = args.strip().strip('"').strip("'")
        full = os.path.abspath(os.path.join(project_root, path))
        full = os.path.normpath(full)
        root = os.path.normpath(project_root)
        if not full.startswith(root + os.sep) and full != root:
            return {"result": "Path escapes project root", "success": False}
        if not os.path.exists(full):
            return {"result": f"File not found: {path}", "success": False}
        try:
            parsed = json.loads(body)
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
            return {"result": f"Error: old text not found in {path}", "success": False}
        if content.count(old_text) > 1:
            return {"result": f"Error: old text matched {content.count(old_text)} times in {path}", "success": False}
        new_content = content.replace(old_text, new_text, 1)
        try:
            with open(full, "w", encoding="utf-8") as f:
                f.write(new_content)
            return {"result": f"Edited: {path}", "success": True, "old_content": old_text, "new_content": new_text}
        except Exception as e:
            return {"result": f"Error writing: {e}", "success": False}


class WebFetchTool(Tool):
    name = "web-fetch"
    description = "Fetch content from a URL"
    parameters = {"type": "object", "properties": {"url": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        url = args.strip()
        if not url.startswith(("http://", "https://")):
            return {"result": "Invalid URL", "success": False}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Cipher/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            text = re.sub(r'<[^>]+>', ' ', raw)
            text = re.sub(r'\s+', ' ', text).strip()[:5000]
            return {"result": text[:3000], "success": True, "bytes": len(raw)}
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
            req = urllib.request.Request(url, headers={"User-Agent": "Cipher/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            links = re.findall(r"<a rel=\"nofollow\"[^>]*href=\"([^\"]*)\"[^>]*>(.*?)</a>", raw, re.DOTALL)
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
                results.append(f"{len(results)+1}. {clean_text} - {clean_href}")
            result = "\n".join(results[:8]) if results else "No results found"
            return {"result": result[:3000], "success": True, "count": len(results)}
        except Exception as e:
            return {"result": f"Search error: {e}", "success": False}


class GitTool(Tool):
    name = "git"
    description = "Execute git commands"
    parameters = {"type": "object", "properties": {"command": {"type": "string"}, "message": {"type": "string"}}}
    builtin = True

    def execute(self, args, body, project_root, context=None):
        cmd = args.strip()
        safe_cmds = ["status", "diff", "log", "show", "branch", "add", "commit", "push", "pull", "stash", "checkout"]
        base = cmd.split()[0] if cmd else "status"
        if base not in safe_cmds:
            return {"result": f"Git command '{base}' not allowed", "success": False}
        if base == "commit" and body:
            full_cmd = f'git commit -m "{body}"'
        else:
            full_cmd = f"git {cmd}"
        try:
            r = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=project_root)
            out = r.stdout.rstrip()
            err = r.stderr.rstrip()[:500]
            result = out or err or "(ok)"
            return {"result": result[:2000], "success": r.returncode == 0, "exit_code": r.returncode}
        except subprocess.TimeoutExpired:
            return {"result": "Error: git timeout", "success": False}
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


BUILTIN_TOOLS = {
    "run": RunTool(),
    "write": WriteTool(),
    "read": ReadTool(),
    "ls": LsTool(),
    "grep": GrepTool(),
    "glob": GlobTool(),
    "edit": EditTool(),
    "web-fetch": WebFetchTool(),
    "web-search": WebSearchTool(),
    "git": GitTool(),
    "todo": TodoTool(),
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

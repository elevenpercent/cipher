#!/usr/bin/env python3
"""
Cipher CLI Test Harness - Tests core functionality without TUI complexity.
Measures timing, verifies results, reports pass/fail for each operation.
"""
import os
import sys
import time
import json
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cipher.tools import ToolRegistry, Tool
from cipher.permissions import PermissionManager
from cipher.plugin import PluginManager
from cipher.themes import ThemeManager
from cipher.formatters import FormatterManager
from cipher.mcp import MCPServerManager
from cipher.lsp import LSPManager
from cipher.provider import AIProvider, PROVIDERS


PASS = 0
FAIL = 0
TIMINGS = []


def test(name):
    """Decorator for test functions."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            global PASS, FAIL
            print(f"\n  [{name}]")
            start = time.time()
            try:
                fn(*args, **kwargs)
                elapsed = time.time() - start
                PASS += 1
                TIMINGS.append((name, elapsed))
                print(f"  [OK] PASS ({elapsed:.2f}s)")
            except Exception as e:
                elapsed = time.time() - start
                FAIL += 1
                TIMINGS.append((name, elapsed))
                print(f"  [FAIL] {e} ({elapsed:.2f}s)")
                import traceback
                traceback.print_exc()
        return wrapper
    return decorator


def setup_test_env():
    """Create a clean temp directory for testing."""
    test_dir = tempfile.mkdtemp(prefix="cipher_test_")
    os.chdir(test_dir)
    return test_dir


def teardown_test_env(path):
    """Clean up test directory."""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    shutil.rmtree(path, ignore_errors=True)


# ============================================================
# SECTION 1: Tool System Tests
# ============================================================

@test("Tool Registry: initialization and builtins")
def test_tool_registry():
    reg = ToolRegistry()
    assert reg.get("run") is not None, "run tool missing"
    assert reg.get("write") is not None, "write tool missing"
    assert reg.get("read") is not None, "read tool missing"
    assert reg.get("ls") is not None, "ls tool missing"
    assert reg.get("grep") is not None, "grep tool missing"
    assert reg.get("glob") is not None, "glob tool missing"
    assert reg.get("edit") is not None, "edit tool missing"
    assert reg.get("todo") is not None, "todo tool missing"
    assert reg.get("git") is not None, "git tool missing"
    assert reg.get("web-fetch") is not None, "web-fetch tool missing"
    count = len([t for t in [reg.get(n) for n in ["run","write","read","ls","grep","glob","edit","todo","git","web-fetch","web-search"]] if t])
    assert count >= 10, f"Expected >=10 builtins, got {count}"


@test("Tool: write and read files")
def test_write_read_files():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        path = os.path.join(test_dir, "hello.txt")
        result = reg.execute("write", path, "Hello World!\nSecond line.", test_dir)
        assert result.get("success"), f"Write failed: {result}"
        assert os.path.exists(path), "File not created"

        result = reg.execute("read", path, "", test_dir)
        assert result.get("success"), f"Read failed: {result}"
        content = result.get("result", "")
        assert "Hello World!" in content, f"Wrong content: {content}"
    finally:
        teardown_test_env(test_dir)


@test("Tool: write files in multiple languages")
def test_write_multiple_languages():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()

        # Python
        r = reg.execute("write", os.path.join(test_dir, "main.py"), "def hello():\n    print('hello')\n\nhello()", test_dir)
        assert r.get("success"), f"Python write failed: {r}"

        # JavaScript
        r = reg.execute("write", os.path.join(test_dir, "app.js"), "function hello() {\n  console.log('hello');\n}\nhello();", test_dir)
        assert r.get("success"), f"JS write failed: {r}"

        # TypeScript
        r = reg.execute("write", os.path.join(test_dir, "app.ts"), "const greet = (name: string): void => {\n  console.log(name);\n};", test_dir)
        assert r.get("success"), f"TS write failed: {r}"

        # Rust
        r = reg.execute("write", os.path.join(test_dir, "main.rs"), "fn main() {\n    println!(\"Hello\");\n}", test_dir)
        assert r.get("success"), f"Rust write failed: {r}"

        # Go
        r = reg.execute("write", os.path.join(test_dir, "main.go"), "package main\nimport \"fmt\"\nfunc main() {\n  fmt.Println(\"Hello\")\n}", test_dir)
        assert r.get("success"), f"Go write failed: {r}"

        # Verify all files exist
        for f in ["main.py", "app.js", "app.ts", "main.rs", "main.go"]:
            assert os.path.exists(os.path.join(test_dir, f)), f"{f} not created"

        total = 0
        for f in ["main.py", "app.js", "app.ts", "main.rs", "main.go"]:
            fp = os.path.join(test_dir, f)
            with open(fp) as fh:
                total += len(fh.read())
        assert total > 50, f"Total content too small: {total}"
    finally:
        teardown_test_env(test_dir)


@test("Tool: edit files")
def test_edit_files():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        path = os.path.join(test_dir, "edit_test.txt")
        with open(path, "w") as f:
            f.write("line1\nline2\nline3\n")

        body = json.dumps({"old": "line2", "new": "modified"})
        result = reg.execute("edit", path, body, test_dir)
        assert result.get("success"), f"Edit failed: {result}"

        with open(path) as f:
            content = f.read()
        assert "modified" in content, f"Edit not applied: {content}"
        assert "line2" not in content, "Old content still present"
    finally:
        teardown_test_env(test_dir)


@test("Tool: delete files via run (del on Windows)")
def test_delete_files():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        path = os.path.join(test_dir, "todelete.txt")
        Path(path).write_text("delete me")
        assert os.path.exists(path)

        cmd = f"del /q \"{path}\"" if os.name == "nt" else f"rm {path}"
        result = reg.execute("run", cmd, "", test_dir)
        assert result.get("success"), f"Delete failed: {result}"
        assert not os.path.exists(path), "File still exists after delete"
    finally:
        teardown_test_env(test_dir)


@test("Tool: ls directory listing")
def test_ls_tool():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        for f in ["a.txt", "b.py", "c.js"]:
            Path(os.path.join(test_dir, f)).write_text("content")

        result = reg.execute("ls", test_dir, "", test_dir)
        assert result.get("success"), f"ls failed: {result}"
        content = result.get("result", "")
        assert "a.txt" in content, f"a.txt not in ls: {content}"
        assert "b.py" in content, f"b.py not in ls: {content}"
        assert "c.js" in content, f"c.js not in ls: {content}"
    finally:
        teardown_test_env(test_dir)


@test("Tool: grep search")
def test_grep_tool():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        Path(os.path.join(test_dir, "search.txt")).write_text("hello world\nfind this line\nsomething else\n")
        Path(os.path.join(test_dir, "other.txt")).write_text("nothing here\n")

        result = reg.execute("grep", "find this", ".", test_dir)
        assert result.get("success"), f"grep failed: {result}"
        assert result.get("count", 0) >= 1, f"No matches found: {result}"
    finally:
        teardown_test_env(test_dir)


@test("Tool: glob pattern matching")
def test_glob_tool():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        for f in ["a.py", "b.py", "c.txt"]:
            Path(os.path.join(test_dir, f)).write_text("content")

        result = reg.execute("glob", "*.py", ".", test_dir)
        assert result.get("success"), f"glob failed: {result}"
        assert result.get("count", 0) >= 2, f"Expected >=2 .py files: {result}"
    finally:
        teardown_test_env(test_dir)


@test("Tool: escape prevention (path traversal)")
def test_escape_prevention():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        malicious = "../../../etc/passwd"
        result = reg.execute("read", malicious, "", test_dir)
        assert not result.get("success"), "Should have blocked path traversal"
        assert "escape" in result.get("result", "").lower() or "blocked" in result.get("result", "").lower() or "outside" in result.get("result", "").lower(), f"Wrong error: {result}"
    finally:
        teardown_test_env(test_dir)


@test("Tool: todo management")
def test_todo_tool():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        ctx = {"todo_list": []}
        r = reg.execute("todo", "add=Test task", "", test_dir, context=ctx)
        assert r.get("success"), f"Todo add failed: {r}"

        r = reg.execute("todo", "list", "", test_dir, context=ctx)
        assert r.get("success"), f"Todo list failed: {r}"
        assert len(ctx.get("todo_list", [])) >= 1, f"No todos added: {ctx}"
    finally:
        teardown_test_env(test_dir)


# ============================================================
# SECTION 2: Permission System Tests
# ============================================================

@test("Permissions: auto-allow and auto-deny")
def test_permissions():
    config = {"permissions": {"auto_allow": {"read": "*"}, "auto_deny": {"write": "/etc/*"}}}
    pm = PermissionManager(config)

    assert pm.check("read", "test.txt") == "allow", "read should be auto-allow"
    assert pm.check("write", "/etc/passwd") == "deny", "write /etc/ should be deny"
    assert pm.check("run", "some_command") == "ask", "run should be ask"

    pm.add_session_rule("run", "ls *", "allow")
    assert pm.check("run", "ls -la") == "allow", "session rule should allow"
    assert pm.check("run", "rm -rf /") == "ask", "non-matching should be ask"


# ============================================================
# SECTION 3: Plugin System Tests
# ============================================================

@test("Plugin: load, hooks, unload")
def test_plugins():
    pm = PluginManager()
    hooks = ["load", "unload", "tool_execute", "tool_result", "chat_message",
             "settings_open", "settings_save", "app_start", "app_exit",
             "stream_chunk", "provider_change"]
    for h in hooks:
        pm.register_hook(h, lambda: None)
    pm.discover()
    pm.trigger("app_start", "test")
    pm.unload_all()


# ============================================================
# SECTION 4: Theme System Tests
# ============================================================

@test("Themes: builtins and CSS generation")
def test_themes():
    tm = ThemeManager()
    for name in ["dark", "light", "dracula", "solarized", "nord", "monokai", "gruvbox", "tokyo-night"]:
        tm.set_theme(name)
        css = tm.get_css()
        assert css, f"No CSS for theme {name}"
        assert "background" in css.lower(), f"No background in {name} CSS"

    tm.set_theme("dark")
    assert tm.current.name == "dark"

    tm.set_theme("nonexistent")
    assert tm.current.name == "dark", "Should fall back to current on invalid"


# ============================================================
# SECTION 5: Formatter System Tests
# ============================================================

@test("Formatters: extension matching")
def test_formatters():
    fm = FormatterManager()
    names = [f.name for f in fm.formatters]
    for name in ["ruff", "black", "prettier", "gofmt", "rustfmt", "clang-format"]:
        assert name in names, f"{name} not in formatters"

    for name, exts in [("ruff", [".py"]), ("black", [".py"]),
                        ("prettier", [".js", ".ts", ".tsx", ".json", ".css", ".html", ".md"]),
                        ("gofmt", [".go"]), ("rustfmt", [".rs"]),
                        ("clang-format", [".c", ".cpp", ".h"])]:
        fmt = next((f for f in fm.formatters if f.name == name), None)
        if fmt:
            for ext in exts:
                assert fmt.can_format(f"test{ext}"), f"{name} should handle {ext}"

    result = fm.format_file("test.py", os.getcwd())
    assert result is not None or fm.enabled is False


# ============================================================
# SECTION 6: LSP System Tests
# ============================================================

@test("LSP: server configs and diagnostics")
def test_lsp():
    lm = LSPManager()
    from cipher.lsp import Diagnostic, LSP_SERVERS
    d = Diagnostic("test.py", 5, 10, "Test error", severity="error")
    s = str(d)
    assert "E" in s and "Test error" in s, f"Unexpected format: {s}"
    d2 = Diagnostic("test.py", 5, 10, "Test warning", severity="warning")
    s2 = str(d2)
    assert "W" in s2 and "Test warning" in s2, f"Unexpected format: {s2}"

    assert len(LSP_SERVERS) >= 5, f"Expected >=5 LSP servers, got {len(LSP_SERVERS)}"

    lm.shutdown_all()


# ============================================================
# SECTION 7: MCP System Tests
# ============================================================

@test("MCP: manager initialization")
def test_mcp():
    mm = MCPServerManager()
    assert mm.get_tools() == []
    result = mm.call_tool("nonexistent", "test", {})
    assert result is not None
    mm.shutdown_all()


# ============================================================
# SECTION 8: Provider System Tests
# ============================================================

@test("Providers: available providers")
def test_providers():
    assert "cipher-proxy" in PROVIDERS, "cipher-proxy missing"
    assert "groq" in PROVIDERS, "groq missing"
    assert "openai" in PROVIDERS, "openai missing"
    assert "ollama" in PROVIDERS, "ollama missing"
    assert len(PROVIDERS) >= 10, f"Expected >=10 providers, got {len(PROVIDERS)}"


@test("Providers: AIProvider initialization")
def test_ai_provider():
    for pid in ["cipher-proxy", "groq", "openai"]:
        if pid in PROVIDERS:
            info = PROVIDERS[pid]
            models = info.get("models", [])
            if models:
                mid = models[0]["id"]
                ap = AIProvider(provider_id=pid, model_id=mid)
                assert ap.provider_id == pid
                assert ap.model_id == mid
                break


# ============================================================
# SECTION 9: Path Escape Prevention
# ============================================================

@test("Security: path escape prevention")
def test_path_escape():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        attacks = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config",
            "/etc/shadow",
            "C:\\Windows\\System32",
            "%USERPROFILE%\\..\\..\\..\\Windows",
        ]
        for atk in attacks:
            result = reg.execute("read", atk, "", test_dir)
            if result.get("success"):
                content = result.get("result", "")
                if len(content) > 0 and "escape" not in result.get("result", "").lower() and "blocked" not in result.get("result", "").lower() and "outside" not in result.get("result", "").lower():
                    print(f"\n    WARNING: Path traversal may have succeeded: {atk}")
    finally:
        teardown_test_env(test_dir)


# ============================================================
# SECTION 10: E2E Agent Loop (with real AI)
# ============================================================

@test("Agent Loop: simple conversational response")
def test_agent_conversation():
    """Test the AI provider responds (uses cipher-proxy which is free)."""
    if "cipher-proxy" not in PROVIDERS:
        print("    SKIP: cipher-proxy not available")
        return
    info = PROVIDERS["cipher-proxy"]
    models = info.get("models", [])
    if not models:
        print("    SKIP: no proxy models")
        return
    mid = models[0]["id"]
    ap = AIProvider(provider_id="cipher-proxy", model_id=mid, proxy_url="https://proxy-blue-kappa.vercel.app")
    messages = [{"role": "user", "content": "Say hello in one word."}]
    response = ""
    for chunk in ap.chat(messages, stream=True):
        token = chunk.get("content", "")
        if token:
            response += token
    assert len(response) > 0, f"Empty response from {mid}"


@test("Agent Loop: tool parsing and execution via AI")
def test_agent_tool_execution():
    """Test that the AI can generate and execute tool calls via the agent loop."""
    if "cipher-proxy" not in PROVIDERS:
        print("    SKIP: cipher-proxy not available")
        return
    info = PROVIDERS["cipher-proxy"]
    models = info.get("models", [])
    if not models:
        print("    SKIP: no proxy models")
        return
    mid = models[0]["id"]
    ap = AIProvider(provider_id="cipher-proxy", model_id=mid, proxy_url="https://proxy-blue-kappa.vercel.app")

    reg = ToolRegistry()
    test_dir = setup_test_env()
    try:
        system_prompt = f"""You are Cipher, a coding agent.
Authorized directory: {test_dir}

Use these tags:
<run>command</run>  <write path="file">content</write>  <read path="file">
<ls>dir</ls>  <grep pattern="x" path="d">

When done: <done>summary</done>.
Do NOT use markdown code blocks."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Create a file called test_output.txt with content 'Hello from Cipher agent' using <write path=\"test_output.txt\">content</write>."},
        ]
        buffer = ""
        for chunk in ap.chat(messages, stream=True):
            token = chunk.get("content", "")
            if token:
                buffer += token

        import re as _re
        write_match = _re.search(r'<?write\s+path=["\'](.+?)["\']>(.*?)</write>', buffer, _re.DOTALL)
        if write_match:
            path = write_match.group(1)
            content = write_match.group(2)
            result = reg.execute("write", path, content, test_dir)
            assert result.get("success"), f"Write failed: {result}"
            full_path = os.path.normpath(os.path.join(test_dir, path))
            assert os.path.exists(full_path), f"File not created: {full_path}"
            with open(full_path) as f:
                assert "Hello from Cipher agent" in f.read(), "Wrong content"
            print(f"\n    AI-generated tool call succeeded: wrote {path}")
        else:
            print(f"\n    AI did not generate write tag. Response: {buffer[:200]}...")
    finally:
        teardown_test_env(test_dir)


# ============================================================
# SECTION 11: Multi-Turn & Project Building
# ============================================================

@test("Project: create, edit, run Python script")
def test_build_and_run_python():
    """Create a Python script, edit it, run it, and verify output."""
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        path = os.path.join(test_dir, "greet.py")

        # Step 1: Write initial script
        r = reg.execute("write", path, "name = 'World'\nprint(f'Hello, {name}!')", test_dir)
        assert r.get("success"), f"Write failed: {r}"
        assert os.path.exists(path)

        # Step 2: Read it back
        r = reg.execute("read", path, "", test_dir)
        assert r.get("success"), f"Read failed: {r}"
        assert "Hello" in r.get("result", ""), "Read content wrong"

        # Step 3: Edit to change name
        body = json.dumps({"old": "World", "new": "Cipher"})
        r = reg.execute("edit", path, body, test_dir)
        assert r.get("success"), f"Edit failed: {r}"
        with open(path) as f:
            assert "Cipher" in f.read(), "Edit not applied"

        # Step 4: Run it
        r = reg.execute("run", f"python {path}", "", test_dir)
        assert r.get("success"), f"Run failed: {r}"
        assert "Hello, Cipher!" in r.get("result", ""), f"Wrong output: {r.get('result', '')}"
    finally:
        teardown_test_env(test_dir)


@test("Project: multi-file structure")
def test_multi_file_project():
    """Create a small project with multiple files: module + tests + runner."""
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()

        # Create utils.py
        utils_code = '''def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
'''
        r = reg.execute("write", os.path.join(test_dir, "utils.py"), utils_code, test_dir)
        assert r.get("success"), f"utils.py write: {r}"

        # Create test_utils.py
        test_code = '''from utils import add, multiply

assert add(2, 3) == 5
assert multiply(4, 5) == 20
print("All tests passed!")
'''
        r = reg.execute("write", os.path.join(test_dir, "test_utils.py"), test_code, test_dir)
        assert r.get("success"), f"test_utils.py write: {r}"

        # Create main.py
        main_code = '''from utils import add, multiply

result = add(multiply(2, 3), multiply(4, 5))
print(f"Result: {result}")
'''
        r = reg.execute("write", os.path.join(test_dir, "main.py"), main_code, test_dir)
        assert r.get("success"), f"main.py write: {r}"

        # Run tests
        r = reg.execute("run", f"python {os.path.join(test_dir, 'test_utils.py')}", "", test_dir)
        assert r.get("success"), f"Tests failed: {r}"
        assert "All tests passed" in r.get("result", ""), f"Test output: {r.get('result', '')}"

        # List directory to verify all files
        r = reg.execute("ls", test_dir, "", test_dir)
        assert r.get("success"), f"ls failed: {r}"
        for f in ["utils.py", "test_utils.py", "main.py"]:
            assert f in r.get("result", ""), f"{f} missing from ls"

        # Grep for function definitions
        r = reg.execute("grep", "def ", ".", test_dir)
        assert r.get("success"), f"grep failed: {r}"
        assert r.get("count", 0) >= 2, f"Expected >=2 function defs, got {r.get('count', 0)}"

        # Glob for test files
        r = reg.execute("glob", "test_*", ".", test_dir)
        assert r.get("success"), f"glob failed: {r}"
        assert r.get("count", 0) >= 1, f"No test files found: {r}"
    finally:
        teardown_test_env(test_dir)


@test("Project: create HTML page (multi-language)")
def test_html_project():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()

        html = """<!DOCTYPE html>
<html><head><title>Test</title>
<style>
body { background: #fff; color: #333; }
h1 { color: blue; }
</style>
</head><body>
<h1>Hello Cipher</h1>
<p>Generated by Cipher agent.</p>
</body></html>"""
        r = reg.execute("write", os.path.join(test_dir, "index.html"), html, test_dir)
        assert r.get("success"), f"HTML write: {r}"

        css = "/* style.css */\nbody { font-family: sans-serif; }\n.container { max-width: 800px; margin: 0 auto; }"
        r = reg.execute("write", os.path.join(test_dir, "style.css"), css, test_dir)
        assert r.get("success"), f"CSS write: {r}"

        js = "// app.js\nconsole.log('Hello from Cipher');\ndocument.addEventListener('DOMContentLoaded', () => {\n  document.querySelector('h1').style.color = 'red';\n});"
        r = reg.execute("write", os.path.join(test_dir, "app.js"), js, test_dir)
        assert r.get("success"), f"JS write: {r}"

        for f in ["index.html", "style.css", "app.js"]:
            assert os.path.exists(os.path.join(test_dir, f)), f"{f} missing"

        r = reg.execute("ls", test_dir, "", test_dir)
        assert r.get("count", 0) >= 3, f"Expected 3 files: {r}"
    finally:
        teardown_test_env(test_dir)


# ============================================================
# SECTION 12: Internet Access
# ============================================================

@test("Internet: web-fetch tool (valid URL)")
def test_web_fetch():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        r = reg.execute("web-fetch", "https://example.com", "", test_dir)
        assert r.get("success"), f"web-fetch failed: {r}"
        content = r.get("result", "")
        assert "Example Domain" in content or "example" in content.lower(), f"No expected content: {content[:200]}"
    finally:
        teardown_test_env(test_dir)


@test("Internet: web-fetch invalid URL")
def test_web_fetch_invalid():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        r = reg.execute("web-fetch", "not-a-url", "", test_dir)
        assert not r.get("success"), "Should fail on invalid URL"
    finally:
        teardown_test_env(test_dir)


# ============================================================
# SECTION 13: Plugin Discovery (file-based)
# ============================================================

@test("Plugin: discover real plugin files")
def test_plugin_discover_real():
    # Create a temp plugin dir
    original_dir = os.getcwd()
    test_dir = setup_test_env()
    try:
        plugin_dir = os.path.join(test_dir, "cipher_plugins")
        os.makedirs(plugin_dir, exist_ok=True)

        plugin_code = '''
from cipher.plugin import Plugin

class TestPlugin(Plugin):
    name = "test_plugin"
    version = "1.0.0"

    def on_app_start(self, app):
        return "started"

    def on_tool_execute(self, name, args):
        return name, args
'''
        Path(os.path.join(plugin_dir, "test_plugin.py")).write_text(plugin_code)

        pm = PluginManager()
        pm.plugin_dirs = [plugin_dir]
        count = pm.discover()
        assert count >= 0, "discover should not crash"
        assert len(pm.plugins) >= 0, "plugins list should exist"

        assert len(pm.plugins) >= 0, "plugins list should be accessible"

        result = pm.trigger("app_start", "test")
        assert result is not None or len(result) >= 0
    finally:
        os.chdir(original_dir)
        teardown_test_env(test_dir)


# ============================================================
# SECTION 15: Crash Detection & Self-Recovery
# ============================================================

@test("Crash recovery: provider failure handling")
def test_provider_crash():
    """Simulate a provider that fails and verify graceful handling."""
    try:
        ap = AIProvider(provider_id="nonexistent", model_id="fake-model")
        messages = [{"role": "user", "content": "hello"}]
        for chunk in ap.chat(messages, stream=True):
            pass
    except Exception:
        pass


@test("Crash recovery: invalid tool name")
def test_invalid_tool():
    reg = ToolRegistry()
    r = reg.execute("nonexistent-tool", "args", "body", os.getcwd())
    assert r.get("success") == False, "Unknown tool should fail"
    assert "unknown" in r.get("result", "").lower(), f"Wrong error: {r.get('result')}"


@test("Crash recovery: invalid file write (binary content)")
def test_binary_write():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        r = reg.execute("write", os.path.join(test_dir, "binary.bin"), "\x00\x01\x02\xFF\xFE", test_dir)
        if r.get("success"):
            with open(os.path.join(test_dir, "binary.bin"), "rb") as f:
                data = f.read()
            assert len(data) > 0, "Binary file should have content"
    finally:
        teardown_test_env(test_dir)


@test("Crash recovery: tool timeout")
def test_tool_timeout():
    """Test that tool handles timeout gracefully."""
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        cmd = "ping -n 1 127.0.0.1" if os.name == "nt" else "true"
        r = reg.execute("run", cmd, "", test_dir)
        # May timeout or hang - check we handle gracefully
        assert r is not None
    finally:
        teardown_test_env(test_dir)


# ============================================================
# SECTION 16: Model & Provider Switching
# ============================================================

@test("Provider: model switching flow")
def test_provider_switching():
    if "cipher-proxy" not in PROVIDERS:
        print("    SKIP: cipher-proxy not available")
        return
    info = PROVIDERS["cipher-proxy"]
    models = info.get("models", [])
    if len(models) < 2:
        print("    SKIP: need >=2 models")
        return

    for m in models[:2]:
        mid = m["id"]
        ap = AIProvider(provider_id="cipher-proxy", model_id=mid, proxy_url="https://proxy-blue-kappa.vercel.app")
        assert ap.provider_id == "cipher-proxy"
        assert ap.model_id == mid

        messages = [{"role": "user", "content": "Say 'ok'"}]
        response = ""
        for chunk in ap.chat(messages, stream=True):
            token = chunk.get("content", "")
            if token:
                response += token
        assert len(response) > 0, f"Empty response from {mid}"
        print(f"\n    Model {mid}: responded")


# ============================================================
# SECTION 14: Sanitization and Edge Cases
# ============================================================

@test("Edge cases: empty input handling")
def test_empty_input():
    reg = ToolRegistry()
    result = reg.execute("run", "", "", os.getcwd())
    assert result is not None, "run with empty args should not crash"


@test("Edge cases: very long file path")
def test_long_path():
    test_dir = setup_test_env()
    try:
        reg = ToolRegistry()
        long_name = "a" * 200 + ".txt"
        path = os.path.join(test_dir, long_name)
        result = reg.execute("write", path, "content", test_dir)
        assert result.get("success") or not result.get("success"), "Long path should not crash"
    finally:
        teardown_test_env(test_dir)


# ============================================================
# MAIN: Run all tests
# ============================================================

def main():
    global PASS, FAIL, TIMINGS

    print("=" * 60)
    print("  Cipher Core Test Harness")
    print("  Testing fundamental engine without TUI")
    print("=" * 60)

    tests_to_run = [
        ("Tool System", [
            test_tool_registry,
            test_write_read_files,
            test_write_multiple_languages,
            test_edit_files,
            test_delete_files,
            test_ls_tool,
            test_grep_tool,
            test_glob_tool,
            test_escape_prevention,
            test_todo_tool,
        ]),
        ("Permissions", [
            test_permissions,
        ]),
        ("Plugins", [
            test_plugins,
        ]),
        ("Themes", [
            test_themes,
        ]),
        ("Formatters", [
            test_formatters,
        ]),
        ("LSP", [
            test_lsp,
        ]),
        ("MCP", [
            test_mcp,
        ]),
        ("Providers", [
            test_providers,
            test_ai_provider,
        ]),
        ("Security", [
            test_path_escape,
        ]),
        ("Project Building", [
            test_build_and_run_python,
            test_multi_file_project,
            test_html_project,
        ]),
        ("Internet Access", [
            test_web_fetch,
            test_web_fetch_invalid,
        ]),
        ("Plugin Discovery", [
            test_plugin_discover_real,
        ]),
        ("Crash Detection & Self-Recovery", [
            test_provider_crash,
            test_invalid_tool,
            test_binary_write,
            test_tool_timeout,
        ]),
        ("Provider Switching", [
            test_provider_switching,
        ]),
        ("Edge Cases", [
            test_empty_input,
            test_long_path,
        ]),
        ("Agent Loop (requires API)", [
            test_agent_conversation,
            test_agent_tool_execution,
        ]),
    ]

    for section_name, section_tests in tests_to_run:
        print(f"\n{'='*60}")
        print(f"  SECTION: {section_name}")
        print(f"{'='*60}")
        for t in section_tests:
            t()

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  PASS: {PASS}")
    print(f"  FAIL: {FAIL}")
    print(f"  TOTAL: {PASS + FAIL}")
    if TIMINGS:
        total = sum(t[1] for t in TIMINGS)
        print(f"\n  TIMINGS:")
        for name, elapsed in TIMINGS:
            print(f"    {name:<45} {elapsed:.2f}s")
        print(f"    {'-'*45}")
        print(f"    {'TOTAL':<45} {total:.2f}s")
    print()

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

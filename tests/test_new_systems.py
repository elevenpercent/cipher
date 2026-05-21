# Derived from opencode (MIT) - Copyright (c) 2025 opencode.ai
import os
import sys
import json
import tempfile
import time
from pathlib import Path

import pytest

from cipher.tools import (
    Tool, ToolRegistry, RunTool, WriteTool, ReadTool, EditTool,
    LsTool, GrepTool, GlobTool, WebFetchTool, WebSearchTool,
    GitTool, TodoTool, BUILTIN_TOOLS
)
from cipher.permissions import PermissionRule, PermissionManager
from cipher.plugin import Plugin, PluginManager, PLUGINS_DIR
from cipher.themes import Theme, ThemeManager, DARK, LIGHT, DRACULA, BUILTIN_THEMES
from cipher.formatters import (
    Formatter, FormatterManager, BUILTIN_FORMATTERS,
    RuffFormatter, BlackFormatter, PrettierFormatter
)
from cipher.lsp import LSPClient, LSPManager, Diagnostic, LSP_SERVERS
from cipher.mcp import MCPClient, MCPServerManager


class TestToolRegistry:
    def test_registry_has_all_builtins(self):
        reg = ToolRegistry()
        names = [t.name for t in reg.list_tools()]
        for n in ["run", "write", "read", "ls", "grep", "glob", "edit", "web-fetch", "web-search", "git", "todo"]:
            assert n in names

    def test_registry_get(self):
        reg = ToolRegistry()
        assert reg.get("run") is not None
        assert reg.get("nonexistent") is None

    def test_registry_register(self):
        reg = ToolRegistry()
        class TestTool(Tool):
            name = "test-tool"
            description = "test"
            def execute(self, args, body, project_root, context=None):
                return {"result": "test ok", "success": True}
        reg.register(TestTool())
        assert reg.get("test-tool") is not None

    def test_registry_unregister_builtin_fails(self):
        reg = ToolRegistry()
        assert reg.unregister("run") == False

    def test_registry_unregister_custom(self):
        reg = ToolRegistry()
        class TestTool(Tool):
            name = "custom-tool"
            description = "test"
            def execute(self, args, body, project_root, context=None):
                return {"result": "ok", "success": True}
        reg.register(TestTool())
        assert reg.unregister("custom-tool") == True
        assert reg.get("custom-tool") is None

    def test_run_tool(self):
        tool = RunTool()
        r = tool.execute("echo hello", "", os.getcwd())
        assert r["success"] == True
        assert "hello" in r["result"]

    def test_run_tool_timeout_fast(self):
        tool = RunTool()
        r = tool.execute("echo fast", "", os.getcwd())
        assert r["success"] == True

    def test_write_and_read(self):
        wt = WriteTool()
        rt = ReadTool()
        with tempfile.TemporaryDirectory() as tmp:
            r = wt.execute("test.txt", "hello world", tmp)
            assert r["success"] == True
            assert "Written" in r["result"]
            r = rt.execute("test.txt", "", tmp)
            assert r["success"] == True
            assert "hello world" in r["result"]

    def test_write_escape_prevention(self):
        wt = WriteTool()
        r = wt.execute("../../etc/passwd", "evil", os.getcwd())
        assert r["success"] == False

    def test_ls_tool(self):
        tool = LsTool()
        r = tool.execute(".", "", os.getcwd())
        assert r["success"] == True
        assert r["count"] > 0

    def test_grep_tool(self):
        tool = GrepTool()
        r = tool.execute("def test", os.getcwd(), os.getcwd())
        assert r["success"] == True

    def test_glob_tool(self):
        tool = GlobTool()
        r = tool.execute("**/*.py", "", os.getcwd())
        assert r["success"] == True

    def test_edit_tool(self):
        wt = WriteTool()
        et = EditTool()
        rt = ReadTool()
        with tempfile.TemporaryDirectory() as tmp:
            wt.execute("test.txt", "hello world", tmp)
            body = json.dumps({"old": "hello", "new": "hi"})
            r = et.execute("test.txt", body, tmp)
            assert r["success"] == True
            r = rt.execute("test.txt", "", tmp)
            assert "hi world" in r["result"]

    def test_edit_not_found(self):
        et = EditTool()
        body = json.dumps({"old": "xxx", "new": "yyy"})
        r = et.execute("nonexistent.txt", body, os.getcwd())
        assert r["success"] == False

    def test_todo_tool(self):
        tool = TodoTool()
        r = tool.execute("add=my task", "", os.getcwd(), {"todo_list": []})
        assert r["success"] == True
        assert "Todo added" in r["result"]
        todos = r["todo_list"]
        assert len(todos) == 1
        r = tool.execute("list", "", os.getcwd(), {"todo_list": todos})
        assert "my task" in r["result"]
        r = tool.execute("done=1", "", os.getcwd(), {"todo_list": todos})
        assert "Todo done" in r["result"]

    def test_web_fetch_invalid_url(self):
        tool = WebFetchTool()
        r = tool.execute("not-a-url", "", os.getcwd())
        assert r["success"] == False

    def test_git_tool_blocked(self):
        tool = GitTool()
        r = tool.execute("rm -rf .", "", os.getcwd())
        assert r["success"] == False

    def test_execute_via_registry(self):
        reg = ToolRegistry()
        r = reg.execute("run", "echo hello", "", os.getcwd())
        assert r["success"] == True
        assert "hello" in r["result"]

    def test_execute_unknown(self):
        reg = ToolRegistry()
        r = reg.execute("nonexistent", "", "", os.getcwd())
        assert r["success"] == False


class TestPermissionSystem:
    def test_rule_matches(self):
        r = PermissionRule(tool="run", pattern="echo *", action="allow")
        assert r.matches("run", "echo hello") == True
        assert r.matches("run", "rm -rf") == False
        assert r.matches("write", "echo hello") == False

    def test_rule_no_pattern(self):
        r = PermissionRule(tool="run", action="allow")
        assert r.matches("run", "anything") == True

    def test_rule_no_tool(self):
        r = PermissionRule(pattern="*", action="deny")
        assert r.matches("run", "anything") == True

    def test_rule_not_expired(self):
        r = PermissionRule(tool="run", pattern="*", action="allow")
        r.ttl = 3600
        assert r.expired() == False

    def test_permission_manager_auto_allow(self):
        pm = PermissionManager({
            "permissions": {"auto_allow": {"run": ["echo *", "ls *"]}}
        })
        assert pm.check("run", "echo hello") == "allow"
        assert pm.check("run", "rm -rf") == "ask"
        assert pm.check("write", "file.txt") == "ask"

    def test_permission_manager_auto_deny(self):
        pm = PermissionManager({
            "permissions": {"auto_deny": {"run": ["rm *", "del *"]}}
        })
        assert pm.check("run", "rm -rf /") == "deny"
        assert pm.check("run", "echo hi") == "ask"

    def test_permission_manager_auto_confirm(self):
        pm = PermissionManager({"auto_confirm": True})
        assert pm.check("run", "anything") == "allow"

    def test_non_confirm_tool_bypasses(self):
        pm = PermissionManager({})
        assert pm.check("read", "file.txt") == "allow"
        assert pm.check("ls", ".") == "allow"

    def test_session_rules(self):
        pm = PermissionManager({})
        pm.add_session_rule("run", "echo *", "allow")
        assert pm.check("run", "echo hi") == "allow"
        assert pm.check("run", "rm -rf") == "ask"

    def test_allow_once(self):
        pm = PermissionManager({})
        pm.allow_once("run", "echo hello")
        assert pm.check("run", "echo hello") == "allow"

    def test_to_config_dict(self):
        pm = PermissionManager({
            "permissions": {"auto_allow": {"run": ["echo *"]}, "auto_deny": {"git": ["push"]}}
        })
        d = pm.to_config_dict()
        assert "echo *" in d["auto_allow"]["run"]
        assert "push" in d["auto_deny"]["git"]

    def test_from_dict_roundtrip(self):
        d = {"tool": "run", "pattern": "echo *", "action": "allow", "reason": "safe"}
        r = PermissionRule.from_dict(d)
        assert r.tool == "run"
        assert r.pattern == "echo *"
        assert r.action == "allow"


class TestPluginSystem:
    def test_plugin_base_class(self):
        p = Plugin()
        assert hasattr(p, "on_load")
        assert hasattr(p, "on_unload")
        assert hasattr(p, "on_tool_execute")
        assert hasattr(p, "on_tool_result")
        assert hasattr(p, "on_chat_message")
        assert hasattr(p, "on_app_start")
        assert hasattr(p, "on_app_exit")

    def test_plugin_manager_init(self):
        pm = PluginManager()
        assert pm.plugins == []

    def test_plugin_manager_register_hook(self):
        pm = PluginManager()
        results = []
        def my_hook(arg):
            results.append(arg)
        pm.register_hook("test_event", my_hook)
        pm.trigger("test_event", "hello")
        assert results == ["hello"]

    def test_plugin_manager_multiple_hooks(self):
        pm = PluginManager()
        results = []
        pm.register_hook("evt", lambda: results.append(1))
        pm.register_hook("evt", lambda: results.append(2))
        pm.trigger("evt")
        assert results == [1, 2]

    def test_plugin_manager_discover_empty(self):
        pm = PluginManager()
        count = pm.discover()
        assert count >= 0

    def test_discover_directory(self):
        PLUGINS_DIR.mkdir(exist_ok=True)
        test_plugin = PLUGINS_DIR / "test_plugin.py"
        test_plugin.write_text("""
from cipher.plugin import Plugin

class TestPlugin(Plugin):
    name = "test-plugin"
    def on_load(self, app):
        self.loaded = True
""")
        try:
            pm = PluginManager()
            count = pm.discover()
            assert count >= 1
        finally:
            test_plugin.unlink()

    def test_unload_all(self):
        pm = PluginManager()
        pm.register_hook("test", lambda: None)
        pm.unload_all()
        assert pm.plugins == []
        assert pm._hook_registry == {}


class TestThemeSystem:
    def test_dark_theme(self):
        assert DARK.name == "dark"
        assert DARK.colors["bg"] == "#050505"
        assert DARK.colors["accent"] == "#f5c542"

    def test_light_theme(self):
        assert LIGHT.name == "light"
        assert LIGHT.colors["bg"] == "#ffffff"

    def test_dracula_theme(self):
        assert DRACULA.name == "dracula"
        assert DRACULA.colors["bg"] == "#282a36"

    def test_builtin_themes_count(self):
        assert len(BUILTIN_THEMES) >= 8

    def test_theme_css(self):
        css = DARK.css()
        assert "#050505" in css
        assert "#f5c542" in css
        assert ".msg-user" in css
        assert ".msg-assistant" in css
        assert ".msg-system" in css

    def test_theme_manager_default(self):
        tm = ThemeManager()
        assert tm.current.name == "dark"

    def test_theme_manager_set_builtin(self):
        tm = ThemeManager()
        assert tm.set_theme("nord") == True
        assert tm.current.name == "nord"
        assert tm.set_theme("light") == True
        assert tm.current.name == "light"

    def test_theme_manager_set_invalid(self):
        tm = ThemeManager()
        assert tm.set_theme("nonexistent") == False

    def test_theme_manager_list(self):
        tm = ThemeManager()
        themes = tm.list_themes()
        assert "dark" in themes
        assert "nord" in themes
        assert "monokai" in themes

    def test_theme_manager_css(self):
        tm = ThemeManager()
        tm.set_theme("dracula")
        css = tm.get_css()
        assert "#282a36" in css

    def test_custom_theme_discover(self):
        from cipher.themes import THEMES_DIR
        THEMES_DIR.mkdir(parents=True, exist_ok=True)
        custom = THEMES_DIR / "ocean.json"
        custom.write_text(json.dumps({
            "bg": "#001b2e",
            "fg": "#a0c4e8",
            "accent": "#7eb8e0",
            "muted": "#4a6a80",
        }))
        try:
            tm = ThemeManager()
            count = tm.discover()
            assert count >= 1
            tm.set_theme("ocean")
            assert tm.current.name == "ocean"
            assert tm.current.colors["bg"] == "#001b2e"
        finally:
            custom.unlink()


class TestFormatterSystem:
    def test_formatter_manager_init(self):
        fm = FormatterManager()
        assert len(fm.formatters) == len(BUILTIN_FORMATTERS)
        assert fm.enabled == True

    def test_formatter_detect_available(self):
        fm = FormatterManager()
        available = fm.detect_available()
        assert isinstance(available, list)

    def test_ruff_recognizes_py(self):
        fmt = RuffFormatter()
        assert fmt.can_format("/path/to/file.py") == True
        assert fmt.can_format("/path/to/file.js") == False

    def test_black_recognizes_py(self):
        fmt = BlackFormatter()
        assert fmt.can_format("test.py") == True

    def test_prettier_recognizes_multiple(self):
        fmt = PrettierFormatter()
        for ext in [".js", ".ts", ".tsx", ".json", ".css", ".html", ".md"]:
            assert fmt.can_format(f"/path/file{ext}") == True, f"Failed for {ext}"
        assert fmt.can_format("/path/file.py") == False

    def test_gofmt_recognizes_go(self):
        fmt = __import__("cipher.formatters", fromlist=[""]).GoFmtFormatter()
        assert fmt.can_format("main.go") == True

    def test_rustfmt_recognizes_rs(self):
        fmt = __import__("cipher.formatters", fromlist=[""]).RustFmtFormatter()
        assert fmt.can_format("main.rs") == True

    def test_clang_format_recognizes_c(self):
        fmt = __import__("cipher.formatters", fromlist=[""]).ClangFormatFormatter()
        for ext in [".c", ".cpp", ".hpp", ".java"]:
            assert fmt.can_format(f"test{ext}") == True

    def test_format_file_no_formatter(self):
        fm = FormatterManager()
        r = fm.format_file("/nonexistent/file.xyz")
        assert r is None or r == []

    def test_run_lint_no_command(self):
        fm = FormatterManager()
        assert fm.run_lint() == ""


class TestLSPSystem:
    def test_diagnostic_creation(self):
        d = Diagnostic("file.py", 10, 5, "some error", "error")
        assert d.filepath == "file.py"
        assert d.line == 10
        assert d.column == 5
        assert d.severity == "error"

    def test_diagnostic_str_error(self):
        d = Diagnostic("file.py", 10, 5, "bad code", "error")
        s = str(d)
        assert "10:5" in s
        assert "E" in s

    def test_diagnostic_str_warning(self):
        d = Diagnostic("file.py", 1, 1, "style", "warning")
        s = str(d)
        assert "W" in s

    def test_lsp_manager_init(self):
        lm = LSPManager()
        assert lm.clients == {}

    def test_lsp_servers_defined(self):
        assert ".py" in LSP_SERVERS
        assert ".js" in LSP_SERVERS
        assert ".go" in LSP_SERVERS

    def test_lsp_server_config(self):
        py_config = LSP_SERVERS[".py"]
        assert "command" in py_config
        assert "args" in py_config
        assert "name" in py_config

    def test_shutdown_all_empty(self):
        lm = LSPManager()
        lm.shutdown_all()
        assert lm.clients == {}


class TestMCPSystem:
    def test_mcp_manager_init(self):
        mm = MCPServerManager()
        assert mm.servers == {}

    def test_mcp_get_tools_empty(self):
        mm = MCPServerManager()
        assert mm.get_tools() == []

    def test_mcp_call_tool_no_server(self):
        mm = MCPServerManager()
        r = mm.call_tool("nonexistent", "test")
        assert r["success"] == False

    def test_mcp_shutdown_all(self):
        mm = MCPServerManager()
        mm.shutdown_all()
        assert mm.servers == {}

    def test_mcp_discover_empty(self):
        mm = MCPServerManager()
        count = mm.discover()
        assert count >= 0

    def test_mcp_client_init(self):
        client = MCPClient("test", "python", ["--version"])
        assert client.name == "test"
        assert client.tools == []

    def test_mcp_client_start_nonexistent(self):
        client = MCPClient("bad", "nonexistent-command-12345")
        assert client.start() == False


class TestIntegration:
    def test_tool_registry_in_permissions(self):
        reg = ToolRegistry()
        pm = PermissionManager({"permissions": {"auto_allow": {"run": ["echo *"]}}})
        r = reg.execute("run", "echo integ-test", "", os.getcwd())
        assert r["success"] == True
        assert pm.check("run", "echo integ-test") == "allow"

    def test_theme_and_tools(self):
        tm = ThemeManager()
        tm.set_theme("monokai")
        reg = ToolRegistry()
        r = reg.execute("run", "echo themed", "", os.getcwd())
        assert r["success"] == True
        assert tm.current.name == "monokai"

    def test_full_execution_flow(self):
        reg = ToolRegistry()
        pm = PermissionManager({"permissions": {"auto_allow": {"run": ["echo *"]}}})
        with tempfile.TemporaryDirectory() as tmp:
            r_write = reg.execute("write", "hello.txt", "Hello World", tmp)
            assert r_write["success"] == True
            r_read = reg.execute("read", "hello.txt", "", tmp)
            assert r_read["success"] == True
            assert "Hello World" in r_read["result"]
            r = reg.execute("run", "echo done", "", tmp)
            assert r["success"] == True
            assert pm.check("run", "echo done") == "allow"

    def test_plugin_manager_discover_and_hooks(self):
        pm = PluginManager()
        hook_results = []
        pm.register_hook("tool_execute", lambda t, a, b: hook_results.append((t, a)))
        pm.trigger("tool_execute", "test_tool", "arg1", "body1")
        assert len(hook_results) == 1
        assert hook_results[0][0] == "test_tool"

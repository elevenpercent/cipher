# Derived from opencode (MIT) - Copyright (c) 2025 opencode.ai
import os
import sys
import re
import subprocess
import time
import json
import shutil
from pathlib import Path
from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Input, Label, Button, Checkbox, Select, Rule
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from rich.text import Text
from cipher.provider import AIProvider, PROVIDERS
from cipher.tools import ToolRegistry
from cipher.permissions import PermissionManager
from cipher.plugin import PluginManager
from cipher.themes import ThemeManager
from cipher.formatters import FormatterManager
from cipher.mcp import MCPServerManager
from cipher.lsp import LSPManager
import fnmatch
import threading
import urllib.request
import glob as glob_module
import concurrent.futures

CONFIG_DIR = Path.home() / ".cipher"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
SKILLS_DIR = CONFIG_DIR / "skills"
CONFIG_DIR.mkdir(exist_ok=True)
SESSIONS_DIR.mkdir(exist_ok=True)
SKILLS_DIR.mkdir(exist_ok=True)

THINKING_FRAMES = ["-", "\\", "|", "/"]
_PROVIDER_CACHE = None
_PROVIDER_CACHE_TIME = 0


def detect_available_providers():
    available = []
    for pid, info in PROVIDERS.items():
        if info.get("type") == "local":
            if pid == "ollama":
                if shutil.which("ollama"):
                    try:
                        subprocess.run(["ollama", "list"], capture_output=True, timeout=3)
                        available.append({"id": pid, "available": True, "reason": "Installed"})
                    except Exception:
                        available.append({"id": pid, "available": False, "reason": "Ollama not running - run 'ollama serve'"})
                else:
                    available.append({"id": pid, "available": False, "reason": "Not installed - get at ollama.com"})
            elif pid == "lmstudio":
                try:
                    urllib.request.urlopen("http://localhost:1234/v1/models", timeout=2)
                    available.append({"id": pid, "available": True, "reason": "Running"})
                except Exception:
                    available.append({"id": pid, "available": False, "reason": "Not running - start LM Studio"})
        else:
            env_key = info.get("env_key", "")
            if env_key and os.getenv(env_key):
                available.append({"id": pid, "available": True, "reason": f"{env_key} found"})
            else:
                available.append({"id": pid, "available": False, "reason": f"Missing {env_key}"})
    return available


def load_config():
    defaults = {
        "provider": "cipher-proxy",
        "model": "llama-3.3-70b",
        "show_plan": True,
        "show_code": True,
        "show_summary": True,
        "show_tool_exec": True,
        "show_diff": True,
        "expand_explanations": False,
        "auto_confirm": False,
        "compact_mode": False,
        "lint_command": "",
        "skills_dir": str(SKILLS_DIR),
        "permissions": {
            "auto_allow": {},
            "auto_deny": {},
        },
        "custom_tools": [],
        "proxy_url": "https://proxy-blue-kappa.vercel.app",
        "theme": "dark",
        "mcp_servers": {},
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def save_session(session_id, messages, title=""):
    session_file = SESSIONS_DIR / f"{session_id}.json"
    data = {
        "id": session_id,
        "title": title,
        "created": datetime.now().isoformat(),
        "messages": messages,
    }
    with open(session_file, "w") as f:
        json.dump(data, f, indent=2)


def load_sessions():
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(f) as fh:
                data = json.load(fh)
            sessions.append(data)
        except Exception:
            continue
    return sessions


def load_session(session_id):
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if session_file.exists():
        with open(session_file) as f:
            return json.load(f)
    return None


def generate_title(first_message):
    clean = first_message.strip()
    if len(clean) <= 40:
        return clean
    return clean[:37] + "..."


class CodeBlock(Static):
    def __init__(self, path, content, old_content="", **kwargs):
        super().__init__(**kwargs)
        self.path = path
        self.content = content
        self.old_content = old_content
    def render(self):
        result = Text()
        result.append(f" {self.path}\n", style="bold green")
        old_lines = self.old_content.split('\n') if self.old_content else []
        new_lines = self.content.split('\n') if self.content else []
        if not self.old_content:
            for line in new_lines:
                result.append(f"+ ", style="bold green")
                result.append(f"{line}\n", style="green")
        elif not self.content:
            for line in old_lines:
                result.append(f"- ", style="bold red")
                result.append(f"{line}\n", style="red")
        else:
            max_len = max(len(old_lines), len(new_lines))
            for i in range(max_len):
                ol = old_lines[i] if i < len(old_lines) else None
                nl = new_lines[i] if i < len(new_lines) else None
                if ol != nl:
                    if ol is not None:
                        result.append(f"- ", style="bold red")
                        result.append(f"{ol}\n", style="red")
                    if nl is not None:
                        result.append(f"+ ", style="bold green")
                        result.append(f"{nl}\n", style="green")
        result.append(f"  ({len(new_lines)} lines)", style="dim")
        return result


class PlanBlock(Static):
    def __init__(self, content, **kwargs):
        super().__init__(**kwargs)
        self.content = content
    def render(self):
        result = Text()
        result.append(" Plan\n", style="bold cyan")
        for line in self.content.strip().split('\n'):
            if line.strip():
                result.append(f"  {line.strip()}\n", style="cyan")
        return result


class ExplanationBlock(Static):
    BINDINGS = [Binding("enter", "toggle", "Toggle")]
    def __init__(self, summary, details="", expanded=False, **kwargs):
        super().__init__(**kwargs)
        self.summary = summary
        self.details = details
        self.expanded = expanded
    def render(self):
        result = Text()
        arrow = "\u25bc" if self.expanded else "\u25b6"
        result.append(f" {arrow} ", style="dim")
        result.append(self.summary, style="white")
        if self.expanded and self.details:
            result.append("\n")
            result.append(self.details, style="dim")
        return result
    def action_toggle(self):
        self.expanded = not self.expanded
        self.refresh()


class ToolResult(Static):
    def __init__(self, tool, args, result, success=True, **kwargs):
        super().__init__(**kwargs)
        self.tool = tool
        self.args = args
        self.result = result
        self.success = success
    def render(self):
        result = Text()
        icon = "OK" if self.success else "FAIL"
        style = "green" if self.success else "red"
        if self.tool == "write":
            result.append(f"  {icon} ", style=style)
            result.append(f"Writing {self.args}\n", style="bold")
            for line in self.result.split('\n')[:3]:
                if line.strip():
                    result.append(f"+ {line}\n", style="green")
        elif self.tool == "run":
            result.append(f"  {icon} ", style=style)
            result.append(f"$ {self.args}\n", style="yellow")
            out = self.result[:200].strip()
            if out:
                result.append(f"  {out}\n", style="green" if self.success else "red")
        elif self.tool == "grep":
            result.append(f"  grep {self.args}\n", style="bold cyan")
            out = self.result[:300].strip()
            if out:
                for line in out.split('\n')[:5]:
                    result.append(f"  {line}\n", style="cyan")
        elif self.tool == "glob":
            result.append(f"  glob {self.args}\n", style="bold cyan")
            out = self.result[:200].strip()
            if out:
                result.append(f"  {out}\n", style="cyan")
        elif self.tool == "edit":
            result.append(f"  {icon} ", style=style)
            result.append(f"Editing {self.args}\n", style="bold")
        elif self.tool == "web-fetch":
            result.append(f"  fetch {self.args}\n", style="bold cyan")
            out = self.result[:200].strip()
            if out:
                result.append(f"  {out[:200]}\n", style="cyan")
        elif self.tool == "git":
            result.append(f"  {icon} ", style=style)
            result.append(f"git {self.args}\n", style="bold yellow")
            out = self.result[:200].strip()
            if out:
                result.append(f"  {out}\n", style="yellow")
        elif self.tool == "web-search":
            result.append(f"  search {self.args}\n", style="bold cyan")
            out = self.result[:200].strip()
            if out:
                result.append(f"  {out}\n", style="cyan")
        elif self.tool == "todo":
            result.append(f"  todo {self.args}\n", style="bold magenta")
            if self.result:
                result.append(f"  {self.result[:200]}\n", style="magenta")
        return result


class LoadingIndicator(Static):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.frame_idx = 0
        self.text = "Thinking"
        self.dots = "..."
        self.update(f"  {THINKING_FRAMES[0]} {self.text}...")
    def on_mount(self):
        self.set_interval(0.15, self._tick)
    def _tick(self):
        self.frame_idx = (self.frame_idx + 1) % len(THINKING_FRAMES)
        self.dots = "." * ((self.frame_idx % 3) + 1)
        self.update(f"  {THINKING_FRAMES[self.frame_idx]} {self.text}{self.dots}")





class SessionModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    def compose(self):
        with Container(id="session-panel"):
            yield Static("  Saved Sessions  [esc] Close", id="panel-title")
            sessions = load_sessions()
            if not sessions:
                yield Static("  No saved sessions yet", id="session-empty")
            for s in sessions[:15]:
                created = s.get("created", "unknown")[:19].replace("T", " ")
                title = s.get("title", "Untitled")[:40]
                msg_count = len(s.get("messages", [])) - 1
                yield Static(f"  {title:<40} {msg_count:>3} msgs  {created}", id=f"sess-{s['id']}", classes="sess-row")
            yield Rule()
            yield Button("Cancel", id="session_cancel", variant="default")

    def on_key(self, event):
        if event.key in ("up", "down", "enter"):
            event.prevent_default()
        rows = list(self.query(".sess-row"))
        if not rows:
            return
        current = None
        for r in rows:
            if "sess-active" in r.classes:
                current = r
                break
        idx = 0
        if current:
            idx = rows.index(current)
        if event.key == "down":
            idx = min(idx + 1, len(rows) - 1)
        elif event.key == "up":
            idx = max(idx - 1, 0)
        elif event.key == "enter":
            sid = list(self.query(".sess-active"))[0].id.replace("sess-", "") if list(self.query(".sess-active")) else None
            if sid:
                self.dismiss(sid)
            return
        for r in rows:
            r.remove_class("sess-active")
        if rows:
            rows[idx].add_class("sess-active")
            self._current_idx = idx

    def on_mount(self):
        rows = list(self.query(".sess-row"))
        if rows:
            rows[0].add_class("sess-active")
            self._current_idx = 0

    def on_button_pressed(self, event):
        if event.button.id == "session_cancel":
            self.dismiss(None)

    CSS = """
    SessionModal { align: center middle; width: 70; border: tall #f5c542; background: #0a0a0a; padding: 1 2; }
    .sess-row { margin: 0; padding: 0; color: #888; }
    .sess-active { color: #f5c542; }
    """


class SettingsModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]
    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.config = config
    def compose(self):
        with Container(id="settings-container"):
            with VerticalScroll(id="settings-scroll"):
                yield Static("  Settings", id="settings-title")
                yield Rule()
                yield Static("AI Provider", classes="settings-section")
                provider_options = [(info["name"], pid) for pid, info in PROVIDERS.items()]
                current = self.config.get("provider", "cipher-proxy")
                yield Select(provider_options, value=current, id="provider_select", prompt="Select provider...")
                model_list = PROVIDERS.get(current, {}).get("models", [])
                model_options = [(m["name"], m["id"]) for m in model_list]
                current_model = self.config.get("model", "")
                if not any(m[1] == current_model for m in model_options) and model_options:
                    current_model = model_options[0][1]
                yield Select(model_options, value=current_model or model_options[0][1] if model_options else None, id="model_select", prompt="Select model...")
                yield Rule()
                yield Static("Display", classes="settings-section")
                yield Checkbox("Show plan", id="show_plan", value=self.config.get("show_plan", True))
                yield Checkbox("Show code blocks", id="show_code", value=self.config.get("show_code", True))
                yield Checkbox("Show diff", id="show_diff", value=self.config.get("show_diff", True))
                yield Checkbox("Show tool results", id="show_tool_exec", value=self.config.get("show_tool_exec", True))
                yield Checkbox("Compact mode", id="compact_mode", value=self.config.get("compact_mode", False))
                yield Checkbox("Auto-confirm tool execution", id="auto_confirm", value=self.config.get("auto_confirm", False))
                theme_options = [("Dark", "dark"), ("Light", "light"), ("Dracula", "dracula"), ("Solarized", "solarized"), ("Nord", "nord"), ("Monokai", "monokai"), ("Gruvbox", "gruvbox"), ("Tokyo Night", "tokyo-night")]
                current_theme = self.config.get("theme", "dark")
                yield Select(theme_options, value=current_theme, id="theme_select", prompt="Select theme...")
                yield Rule()
                yield Static("Actions", classes="settings-section")
                with Horizontal():
                    yield Button("Clear Chat", id="action_clear", variant="default")
                    yield Button("New Session", id="action_new", variant="default")
                with Horizontal():
                    yield Button("Sessions", id="action_sessions", variant="default")
                    yield Button("Quit", id="action_quit", variant="default")
            yield Rule()
            with Horizontal(id="settings-footer"):
                yield Button("Save", id="settings_save", variant="primary")
                yield Button("Cancel", id="settings_cancel", variant="default")

    def on_select_changed(self, event):
        if event.select.id == "provider_select":
            pid = event.value
            if pid and pid in PROVIDERS:
                model_list = PROVIDERS[pid].get("models", [])
                model_options = [(m["name"], m["id"]) for m in model_list]
                ms = self.query_one("#model_select", Select)
                ms.set_options(model_options)
                if model_options:
                    ms.value = model_options[0][1]

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "settings_save":
            self.config["show_plan"] = self.query_one("#show_plan", Checkbox).value
            self.config["show_code"] = self.query_one("#show_code", Checkbox).value
            self.config["show_diff"] = self.query_one("#show_diff", Checkbox).value
            self.config["show_tool_exec"] = self.query_one("#show_tool_exec", Checkbox).value
            self.config["compact_mode"] = self.query_one("#compact_mode", Checkbox).value
            self.config["auto_confirm"] = self.query_one("#auto_confirm", Checkbox).value
            theme_select = self.query_one("#theme_select", Select)
            if theme_select.value:
                self.config["theme"] = str(theme_select.value)
            ps = self.query_one("#provider_select", Select)
            ms = self.query_one("#model_select", Select)
            if ps.value:
                self.config["provider"] = str(ps.value)
            if ms.value:
                self.config["model"] = str(ms.value)
            save_config(self.config)
            self.dismiss({"type": "save", "config": self.config})
        elif bid == "action_clear":
            self.dismiss({"type": "action", "action": "clear"})
        elif bid == "action_new":
            self.dismiss({"type": "action", "action": "new"})
        elif bid == "action_sessions":
            self.dismiss({"type": "action", "action": "sessions"})
        elif bid == "action_quit":
            self.dismiss({"type": "action", "action": "quit"})
        else:
            self.dismiss(None)

    CSS = """
    SettingsModal { align: center middle; }
    #settings-container { width: 55; max-height: 90%; background: $surface; border: tall #f5c542; padding: 1 2; }
    #settings-scroll { height: 1fr; overflow-y: auto; }
    #settings-footer { height: 3; }
    #settings-title { text-align: center; text-style: bold; margin-bottom: 1; }
    .settings-section { margin-top: 1; margin-bottom: 1; text-style: bold; color: $text-muted; }
    Checkbox { margin: 0 0 1 0; }
    Select { margin: 0 0 1 0; }
    Button { margin: 0 1 0 0; }
    #settings_save { margin-right: 1; }
    """


class YesNoModal(ModalScreen):
    BINDINGS = [Binding("y", "yes", "Yes"), Binding("n", "no", "No")]
    def __init__(self, tool, args, **kwargs):
        super().__init__(**kwargs)
        self.tool = tool
        self.args = args
        self.result = "no"
    def compose(self):
        with Container(id="yn-panel"):
            yield Static("  Confirm Action", id="yn-title")
            yield Static(f"  Tool: {self.tool}", id="yn-tool")
            yield Static(f"  Args: {self.args}", id="yn-args")
            yield Static("  Allow this action?", id="yn-prompt")
            with Horizontal(id="yn-buttons"):
                yield Button("  YES (y)  ", id="yn_yes", variant="primary")
                yield Button("  NO (n)   ", id="yn_no", variant="default")
    def action_yes(self):
        self.result = "yes"
        self.dismiss("yes")
    def action_no(self):
        self.result = "no"
        self.dismiss("no")
    def on_button_pressed(self, event):
        if event.button.id == "yn_yes":
            self.action_yes()
        else:
            self.action_no()
    CSS = """
    YesNoModal { align: center middle; }
        width: 50;
        height: auto;
        background: #0a0a0a;
        border: tall #f5c542;
        padding: 1 2;
    }
    """


class QuestionScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Cancel")]
    def __init__(self, question, **kwargs):
        super().__init__(**kwargs)
        self.question = question
        self.answer = ""
    def compose(self):
        with Container(id="question-panel"):
            yield Static("  Question from Cipher", id="question-title")
            yield Static(f"  {self.question}", id="question-text")
            yield Input(placeholder="Type your answer...", id="question-input")
            with Horizontal():
                yield Button("Submit", id="question_submit", variant="primary")
                yield Button("Cancel", id="question_cancel", variant="default")
    def on_button_pressed(self, event):
        if event.button.id == "question_submit":
            self.answer = self.query_one("#question-input", Input).value.strip()
            self.dismiss(self.answer)
        elif event.button.id == "question_cancel":
            self.dismiss("")
    def on_input_submitted(self, event):
        self.answer = event.value.strip()
        self.dismiss(self.answer)
    CSS = """
    QuestionScreen { align: center middle; }
        width: 60;
        height: auto;
        background: #0a0a0a;
        border: tall #f5c542;
        padding: 1 2;
    }
    """





class CipherApp(App):
    CSS = """
    Screen { background: #050505; }
    .msg-user { margin: 1 0; padding: 0 1; color: #f5c542; }
    .msg-assistant { margin: 1 0; padding: 0 1; color: #ddd; }
    .msg-plan { margin: 1 0 1 2; }
    .msg-code { margin: 1 0 1 4; }
    .msg-tool { margin: 0 0 1 4; }
    .msg-explanation { margin: 1 0 1 2; }
    .msg-system { margin: 0 0 1 0; color: $text-muted; text-style: italic; }
    .cmd-block { margin: 1 0; padding: 0 1; }
    .loading-msg { margin: 0 0 1 4; color: #f5c542; }
    """

    BINDINGS = [
        Binding("ctrl+s", "settings", "Settings", show=True),
        Binding("escape", "clear_input", "Clear input", show=False),
    ]

    def __init__(self, project_root=None, provider=None, model=None, api_key=None, session_id=None, proxy_url=None):
        super().__init__()
        self.project_root = os.path.abspath(project_root or os.getcwd())
        self.config = load_config()
        if provider:
            self.config["provider"] = provider
        if model:
            self.config["model"] = model
        if proxy_url:
            self.config["proxy_url"] = proxy_url
        self.api_key = api_key or None
        self.messages = []
        self.chat_messages = []
        self.total_tools = 0
        self.total_tokens = 0
        self.todo_list = []
        self.session_start = time.time()
        self._ai_provider = None
        self.system_prompt = self._build_system_prompt()
        self.chat_messages = [{"role": "system", "content": self.system_prompt}]
        self.command_history = []
        self.history_index = -1
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_title = ""
        self.is_processing = False
        self.loading_widget = None
        self.autocomplete = None
        self._input_event = None
        self._input_result = ""
        self._stream_widget = None
        self.tool_registry = ToolRegistry()
        self.permission_manager = PermissionManager(self.config)
        self.plugin_manager = PluginManager()
        self.theme_manager = ThemeManager()
        self.formatter_manager = FormatterManager()
        self.formatter_manager.lint_command = self.config.get("lint_command", "")
        self.mcp_manager = MCPServerManager()
        self.lsp_manager = LSPManager()

    def _build_system_prompt(self):
        skills_text = self._load_skills()
        ctools = self.config.get("custom_tools", [])
        custom_text = ""
        if ctools:
            lines = []
            for ct in ctools:
                lines.append(f"<{ct['name']}>args</{ct['name']}> - {ct.get('description', ct['name'])}")
            custom_text = "\n" + "\n".join(lines)
        return f"""You are Cipher, an autonomous coding agent. Authorized directory: {self.project_root}.{skills_text}

Respond conversationally to simple questions. For tasks, use tags to take actions:

<run>cmd</run>  <write path="p">content</write>  <read path="p" start="1" end="50">
<ls>path</ls>  <grep pattern="x" path="d">  <glob pattern="**/*.py">
<edit path="p"><old>exact</old><new>replacement</new></edit>
<web-fetch url="...">  <web-search query="...">
<git status|diff|commit message="..."|log --oneline -5>
<todo add="task"|done="N"|list>{custom_text}

When done: <done>Summary</done>.
No markdown code blocks. Relative paths. Use <edit> for small changes.
"""

    def _load_skills(self):
        skills_dir = Path(self.config.get("skills_dir", str(SKILLS_DIR)))
        if not skills_dir.is_dir():
            return ""
        texts = []
        for f in sorted(skills_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8").strip()
                if text:
                    texts.append(f"\n## Skill: {f.stem}\n{text}")
            except Exception:
                pass
        return "".join(texts)

    def compose(self):
        with Container(id="app-layout"):
            with Horizontal(id="header-bar"):
                yield Label("CIPHER //", id="header-left")
                yield Label(f"{self.config['provider']} | {self.config['model']}", id="header-right")
            yield Label(f"  {self.session_title or 'New Session'}", id="session-title")
            yield Static(" ", id="status-bar")
            yield VerticalScroll(id="chat-container")
            with Container(id="input-bar"):
                yield Input(placeholder="Ask Cipher...  Ctrl+S settings", id="chat-input")

    def on_mount(self):
        self.query_one("#chat-input").focus()
        self._add_system(f"Cipher ready")
        self._add_system(f"Provider: {self.config.get('provider')} | Model: {self.config.get('model')}")
        self._add_system(f"Work dir: {self.project_root}")
        if self.session_title:
            self.query_one("#session-title").update(f"  {self.session_title}")
        self.run_worker(self._detect_providers_async, exclusive=False, thread=True)

        saved = load_session(self.session_id)
        if saved and saved.get("messages"):
            self.chat_messages = saved["messages"]
            self.chat_messages = [m for m in self.chat_messages if m["role"] != "system"]
            self.chat_messages.insert(0, {"role": "system", "content": self.system_prompt})
            self._add_system(f"Resumed session: {saved.get('title', 'untitled')}")

        theme_name = self.config.get("theme", "dark")
        self.theme_manager.set_theme(theme_name)
        try:
            self.stylesheet.add_css(self.theme_manager.get_css())
        except Exception:
            pass
        self.plugin_manager.discover()
        self.plugin_manager.trigger("app_start", self)
        mcp_config = self.config.get("mcp_servers", {})
        if mcp_config:
            self.mcp_manager.load_config(self.config)
        else:
            self.mcp_manager.discover()
        mcp_tools = self.mcp_manager.get_tools()
        for t in mcp_tools:
            from cipher.tools import Tool
            class MCPTool(Tool):
                name = t.get("name", "")
                description = t.get("description", "")
                def execute(self_, args, body, project_root, context=None):
                    return self.mcp_manager.call_tool(t.get("_mcp_server", ""), self_.name, {"args": args, "body": body})
                builtin = False
            if MCPTool.name:
                self.tool_registry.register(MCPTool())
        custom_count = self.tool_registry.discover()
        if custom_count:
            self._add_system(f"Loaded {custom_count} custom tools")

    def _detect_providers_async(self):
        available = detect_available_providers()
        active = [p for p in available if p["available"]]
        active_str = ", ".join([p["id"] for p in active]) if active else "none"
        self.call_from_thread(self._add_system, f"Available: {active_str}")

    def _set_status(self, text):
        try:
            self.query_one("#status-bar", Static).update(text)
        except Exception:
            pass

    def _get_chat(self):
        try:
            return self.query_one("#chat-container")
        except Exception:
            return None

    def _add_user(self, text):
        container = self._get_chat()
        if container is None:
            return
        msg = Static(f"\u2192 {text}", classes="msg-user")
        container.mount(msg)
        container.scroll_end()

    def _add_assistant(self, text):
        container = self._get_chat()
        if container is None:
            return
        msg = Static(text, classes="msg-assistant")
        container.mount(msg)
        container.scroll_end()

    def _add_plan(self, text):
        if not self.config.get("show_plan", True):
            return
        container = self._get_chat()
        if container is None:
            return
        block = PlanBlock(text, classes="msg-plan")
        container.mount(block)
        container.scroll_end()

    def _add_code(self, path, content, old=""):
        if not self.config.get("show_code", True):
            return
        container = self._get_chat()
        if container is None:
            return
        block = CodeBlock(path, content, old, classes="msg-code")
        container.mount(block)
        container.scroll_end()

    def _add_tool(self, tool, args, result, success=True):
        if not self.config.get("show_tool_exec", True):
            return
        container = self._get_chat()
        if container is None:
            return
        widget = ToolResult(tool, args, result, success, classes="msg-tool")
        container.mount(widget)
        container.scroll_end()

    def _add_explanation(self, summary, details=""):
        container = self._get_chat()
        if container is None:
            return
        block = ExplanationBlock(summary, details, self.config.get("expand_explanations", False), classes="msg-explanation")
        container.mount(block)
        container.scroll_end()

    def _add_system(self, text):
        container = self._get_chat()
        if container is None:
            return
        msg = Static(f"  {text}", classes="msg-system")
        container.mount(msg)
        container.scroll_end()

    def _add_system_safe(self, text):
        try:
            self._add_system(text)
        except Exception:
            try:
                self.call_from_thread(self._add_system, text)
            except Exception:
                pass

    def _refresh_api_key(self, provider_id):
        pcfg = PROVIDERS.get(provider_id, {})
        if pcfg.get("proxy"):
            self.api_key = ""
            return
        env_key = pcfg.get("env_key", "")
        if env_key:
            env_val = os.getenv(env_key, "")
            if env_val:
                self.api_key = env_val
            else:
                self.api_key = self.config.get("api_key", "")
        else:
            self.api_key = ""

    def action_settings(self):
        def on_settings(result):
            if not result:
                return
            rt = result.get("type", "")
            if rt == "save":
                cfg = result.get("config", {})
                provider = cfg.get("provider", "")
                model = cfg.get("model", "")
                if provider and model:
                    self.config["provider"] = provider
                    self.config["model"] = model
                    self._refresh_api_key(provider)
                    self.query_one("#header-right").update(f"{provider} | {model}")
                    self._add_system(f"Provider: {provider} | Model: {model}")
                theme = cfg.get("theme", "dark")
                if self.config.get("theme") != theme:
                    self.config["theme"] = theme
                    self.theme_manager.set_theme(theme)
                    self.css = self.theme_manager.get_css()
                    self.refresh_css()
            elif rt == "action":
                action = result.get("action", "")
                if action == "clear":
                    self._do_clear()
                elif action == "new":
                    self._do_new()
                elif action == "sessions":
                    self._show_sessions()
                elif action == "quit":
                    self.exit()
        self.push_screen(SettingsModal(self.config), on_settings)

    def _do_clear(self):
        self.chat_messages = [{"role": "system", "content": self.system_prompt}]
        container = self._get_chat()
        if container is not None:
            for child in list(container.children):
                child.remove()
        self._add_system("Chat cleared.")

    def _do_new(self):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_title = ""
        self.chat_messages = [{"role": "system", "content": self.system_prompt}]
        self.total_tools = 0
        self.session_start = time.time()
        container = self._get_chat()
        if container is not None:
            for child in list(container.children):
                child.remove()
            self.query_one("#session-title").update("  New Session")
        self._add_system("New session started.")

    def _show_sessions(self):
        def on_session(sid):
            if sid:
                session = load_session(sid)
                if session:
                    self.session_id = sid
                    self.session_title = session.get("title", "Untitled")
                    self.chat_messages = session.get("messages", [])
                    self.chat_messages = [m for m in self.chat_messages if m["role"] != "system"]
                    self.chat_messages.insert(0, {"role": "system", "content": self.system_prompt})
                    container = self.query_one("#chat-container")
                    for child in list(container.children):
                        child.remove()
                    self.query_one("#session-title").update(f"  {self.session_title}")
                    self._add_system(f"Loaded: {self.session_title}")
        self.push_screen(SessionModal(), on_session)

    def action_clear_chat(self):
        self._do_clear()

    def action_quit(self):
        self.exit()

    def action_clear_input(self):
        self.query_one("#chat-input", Input).value = ""

    def on_input_changed(self, event):
        if self.autocomplete:
            self.autocomplete.update_suggestions(event.value)

    def on_input_submitted(self, event):
        try:
            user_input = event.value.strip()
            if not user_input:
                return

            if self._input_event:
                self._input_result = user_input
                evt = self._input_event
                self._input_event = None
                evt.set()
                self._add_system(f"Answer: {user_input}")
                return

            if self.autocomplete and not self.autocomplete.has_class("hidden"):
                selected = self.autocomplete.get_selected()
                if selected and user_input.lower().startswith(selected.lower().split()[0].lower()):
                    user_input = selected + " " + user_input.split(None, 1)[1] if len(user_input.split()) > 1 else selected

            if self.command_history and self.command_history[-1] != user_input:
                self.command_history.append(user_input)
            elif not self.command_history:
                self.command_history.append(user_input)
            self.history_index = len(self.command_history)
            self.query_one("#chat-input").value = ""

            if not self.session_title:
                self.session_title = generate_title(user_input)
                self.query_one("#session-title").update(f"  {self.session_title}")

            self._add_user(user_input)
            self.chat_messages.append({"role": "user", "content": user_input})
            self.chat_messages = self.chat_messages[-30:]
            save_session(self.session_id, self.chat_messages, self.session_title)

            self.is_processing = True
            self._set_status("")

            container = self.query_one("#chat-container")
            self.loading_widget = LoadingIndicator(classes="loading-msg")
            container.mount(self.loading_widget)
            container.scroll_end()

            self._stream_widget = None

            self.run_worker(self._run_agent_loop_thread, exclusive=True, thread=True)
        except Exception as e:
            self._add_system(f"Error: {e}")
            self.is_processing = False

    def _run_agent_loop_thread(self):
        max_turns = 30
        for turn in range(max_turns):
            buffer = ""
            stream_interval = 0
            try:
                self.call_from_thread(self._remove_loading)
                self._stream_widget = None
                self.call_from_thread(self._set_status, "Thinking")
                pid = self.config.get("provider", "ollama")
                mid = self.config.get("model", "ollama/qwen3:14b")
                self.call_from_thread(self._refresh_api_key, pid)
                if (self._ai_provider is None or
                    self._ai_provider.provider_id != pid or
                    self._ai_provider.model_id != mid):
                    self._ai_provider = AIProvider(provider_id=pid, model_id=mid, api_key=self.api_key, proxy_url=self.config.get("proxy_url", "http://localhost:8080"))
                for chunk in self._ai_provider.chat(self.chat_messages, stream=True):
                    token = chunk.get("content", "")
                    if not token:
                        continue
                    buffer += token
                    stream_interval += 1
                    if stream_interval % 20 == 0:
                        self._update_stream(token)
                self._update_stream("")

                try:
                    import tiktoken
                    enc = tiktoken.get_encoding("cl100k_base")
                    self.total_tokens += len(enc.encode(buffer))
                except Exception:
                    self.total_tokens += len(buffer) // 4

                self.call_from_thread(self._set_status, "Processing")

                plan_match = re.search(r'<plan>(.*?)</plan>', buffer, re.DOTALL)
                if plan_match:
                    self.call_from_thread(self._add_plan, plan_match.group(1))

                done_match = re.search(r'<done>(.*?)</done>', buffer, re.DOTALL)
                if done_match:
                    summary = done_match.group(1).strip()
                    self.call_from_thread(self._stream_finalize, f"  Done: {summary}")
                    self.chat_messages.append({"role": "assistant", "content": f"Task complete: {summary}"})
                    save_session(self.session_id, self.chat_messages, self.session_title)
                    self.call_from_thread(self._set_status, "Ready")
                    self.call_from_thread(self._remove_loading)
                    self.call_from_thread(self._set_ready)
                    return

                tools = self._parse_tools_all(buffer)
                if tools:
                    results = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                        futures = []
                        for t in tools:
                            if not self._confirm_action(t["type"], t.get("path") or t.get("args", "")):
                                results.append(f"Skipped: {t['type']} (not confirmed)")
                                self.call_from_thread(self._add_system, f"Skipped: {t['type']}")
                                continue
                            self.call_from_thread(self._set_status, f"Running {t['type']}...")
                            args = (t["type"], t.get("path") or t.get("args", ""), t.get("body", ""))
                            futures.append((t, pool.submit(self._execute_tool, *args)))
                        for t, fut in futures:
                            try:
                                result = fut.result(timeout=120)
                                self.total_tools += 1
                                results.append(f"<{t['type']}>{result}</{t['type']}>")
                                if t["type"] in ("write", "edit"):
                                    lint_result = self._run_lint()
                                    if lint_result:
                                        self.call_from_thread(self._add_system, lint_result)
                                    file_path = t.get("path", t.get("args", ""))
                                    self._format_file(file_path)
                            except concurrent.futures.TimeoutError:
                                results.append(f"<{t['type']}>Error: timed out</{t['type']}>")
                            except Exception as e:
                                results.append(f"<{t['type']}>Error: {e}</{t['type']}>")
                    combined = "\n".join(results)
                    self.chat_messages.append({"role": "assistant", "content": buffer})
                    self.chat_messages.append({"role": "user", "content": f"Results:\n{combined}\nContinue."})
                    continue

                clean = buffer
                for cp in self._CLEAN_PATTERNS:
                    clean = cp.sub('', clean)
                clean = clean.strip()
                if clean:
                    self.call_from_thread(self._stream_finalize, clean)
                    self.chat_messages.append({"role": "assistant", "content": buffer.strip()})
                else:
                    self.chat_messages.append({"role": "assistant", "content": buffer.strip()})

                save_session(self.session_id, self.chat_messages, self.session_title)
                self.call_from_thread(self._set_status, "Ready")
                self.call_from_thread(self._remove_loading)
                self.call_from_thread(self._set_ready)
                return

            except Exception as e:
                err_msg = str(e)
                if "Authentication" in err_msg or "AuthenticationError" in err_msg or "Invalid API Key" in err_msg or "401" in err_msg:
                    pid = self.config.get("provider", "unknown")
                    info = PROVIDERS.get(pid, {})
                    env_key = info.get("env_key", "API_KEY")
                    err_msg = f"Authentication failed for {info['name']}. Set {env_key} env var or run cip --setup"
                elif "connection" in err_msg.lower() or "refused" in err_msg.lower():
                    pid = self.config.get("provider", "unknown")
                    info = PROVIDERS.get(pid, {})
                    err_msg = f"Connection refused. Make sure {info['name']} is installed and running"
                self.call_from_thread(self._set_status, "Error")
                self.call_from_thread(self._add_system, f"Error: {err_msg}")
                self.call_from_thread(self._remove_loading)
                self.call_from_thread(self._set_ready)
                return

        self.call_from_thread(self._set_status, "Max turns")
        self.call_from_thread(self._add_system, "Max turns reached.")
        self.call_from_thread(self._remove_loading)
        self.call_from_thread(self._set_ready)

    def _wait_for_input(self, prompt):
        event = threading.Event()
        self._input_event = event
        self._input_result = ""
        self.call_from_thread(self._add_system, prompt)
        self.call_from_thread(self._set_status, "Waiting for your input...")
        event.wait()
        self.call_from_thread(self._set_status, "Continuing...")
        return self._input_result

    def _confirm_action(self, tool, args):
        verdict = self.permission_manager.check(tool, args)
        if verdict == "allow":
            return True
        if verdict == "deny":
            return False
        event = threading.Event()
        result = [False]
        def on_answer(answer):
            result[0] = answer == "yes"
            event.set()
        self.call_from_thread(self.push_screen, YesNoModal(tool, args), on_answer)
        event.wait()
        return result[0]

    def _update_stream(self, text):
        try:
            self.call_from_thread(self._stream_append, text)
        except Exception:
            pass

    def _stream_append(self, text):
        if self._stream_widget is None:
            self._stream_widget = Static("", classes="msg-assistant")
            container = self.query_one("#chat-container")
            container.mount(self._stream_widget)
            container.scroll_end()
        self._stream_widget.update(str(self._stream_widget.renderable) + text)
        try:
            self.query_one("#chat-container").scroll_end()
        except Exception:
            pass

    def _stream_finalize(self, text):
        if self._stream_widget is not None:
            self._stream_widget.update(text)

    def _remove_loading(self):
        if self.loading_widget:
            self.loading_widget.remove()
            self.loading_widget = None

    def _set_ready(self):
        self.is_processing = False
        self._stream_widget = None
        self.query_one("#chat-input").focus()

    _CLEAN_PATTERNS = [re.compile(p, re.DOTALL) for p in [
        r'<plan>.*?</plan>', r'<run>.*?</run>', r'<write\s+path=["\'].*?["\']>.*?</write>',
        r'<read\s+path=["\'].*?["\']\s*/?\s*>', r'<ls>.*?</ls>', r'<edit\s+path=["\'].*?["\']>.*?</edit>',
        r'<grep\s+[^>]*>', r'<glob[^>]*>', r'<web-fetch\s+[^>]*>', r'<web-search\s+[^>]*>',
        r'<git\s+[^>]*>',         r'<git\s+[^>]*/>', r'<todo[^>]*>',
    ]]

    _TOOL_PATTERNS = [
        (re.compile(r'<?run>(.+?)</run>', re.DOTALL), lambda m: {"type": "run", "path": "", "args": m.group(1), "body": ""}),
        (re.compile(r'<?write\s+path=["\'](.+?)["\']>(.*?)</write>', re.DOTALL), lambda m: {"type": "write", "path": m.group(1), "args": m.group(1), "body": m.group(2)}),
        (re.compile(r'<?read\s+path=["\'](.+?)["\'](?:\s+start=["\']?(\d+)["\']?)?(?:\s+end=["\']?(\d+)["\']?)?\s*/?\s*>', re.DOTALL), lambda m: {"type": "read", "path": m.group(1), "args": m.group(1), "body": json.dumps({"start": int(m.group(2)) if m.group(2) else None, "end": int(m.group(3)) if m.group(3) else None})}),
        (re.compile(r'<?ls>(.*?)</ls>', re.DOTALL), lambda m: {"type": "ls", "path": m.group(1).strip(), "args": m.group(1).strip(), "body": ""}),
        (re.compile(r'<edit\s+path=["\'](.+?)["\']>(.*?)</edit>', re.DOTALL), lambda m: self._parse_edit_body(m)),
        (re.compile(r'<grep(?:\s+pattern=["\'](.+?)["\'])?(?:\s+path=["\'](.*?)["\'])?\s*/?\s*>', re.DOTALL), lambda m: {"type": "grep", "path": m.group(2) or ".", "args": m.group(1) or "", "body": m.group(1) or ""}),
        (re.compile(r'<glob(?:\s+pattern=["\'](.+?)["\'])?\s*/?\s*>', re.DOTALL), lambda m: {"type": "glob", "path": "", "args": m.group(1) or "", "body": ""}),
        (re.compile(r'<web-fetch\s+url=["\'](.+?)["\']\s*/?\s*>', re.DOTALL), lambda m: {"type": "web-fetch", "path": m.group(1), "args": m.group(1), "body": ""}),
        (re.compile(r'<web-search\s+query=["\'](.+?)["\']\s*/?\s*>', re.DOTALL), lambda m: {"type": "web-search", "path": "", "args": m.group(1), "body": ""}),
        (re.compile(r'<git(?:\s+([^>]*?))?\s*/?\s*>', re.DOTALL), lambda m: self._parse_git_body(m)),
        (re.compile(r'<todo\s+(.+?)\s*/?\s*>', re.DOTALL), lambda m: {"type": "todo", "path": "", "args": m.group(1).strip(), "body": ""}),
    ]

    def _parse_tools_all(self, text):
        text = re.sub(r'```[a-z]*\n(.*?)\n```', r'\1', text, flags=re.DOTALL)
        raw = []

        patterns = list(self._TOOL_PATTERNS)
        for ct in self.config.get("custom_tools", []):
            name = ct.get("name", "")
            if name:
                pat = re.compile(rf'<{re.escape(name)}>(.*?)</{re.escape(name)}>', re.DOTALL)
                patterns.append((pat, lambda m, n=name: {"type": n, "path": "", "args": m.group(1).strip(), "body": m.group(1)}))

        for pattern, builder in patterns:
            for m in pattern.finditer(text):
                tool = builder(m)
                if tool:
                    tool["_pos"] = m.start()
                    raw.append(tool)

        raw.sort(key=lambda t: t.pop("_pos", 0))
        return raw

    def _parse_edit_body(self, m):
        inner = m.group(2)
        old_m = re.search(r'<old>(.*?)</old>', inner, re.DOTALL)
        new_m = re.search(r'<new>(.*?)</new>', inner, re.DOTALL)
        if old_m and new_m:
            return {"type": "edit", "path": m.group(1), "args": m.group(1), "body": json.dumps({"old": old_m.group(1), "new": new_m.group(1)})}
        return None

    def _parse_git_body(self, m):
        cmd = (m.group(1) or "status").strip()
        msg_m = re.search(r'message=["\'](.+?)["\']', cmd)
        if msg_m:
            cmd = re.sub(r'message=["\'].+?["\']', '', cmd).strip()
            return {"type": "git", "path": "", "args": cmd, "body": msg_m.group(1)}
        return {"type": "git", "path": "", "args": cmd, "body": ""}

    def _execute_tool(self, tool_name, args, body=""):
        if tool_name == "write":
            path = args.strip().strip('"').strip("'")
            full = os.path.abspath(os.path.join(self.project_root, path))
            full = os.path.normpath(full)
            root = os.path.normpath(self.project_root)
            old_content = ""
            if os.path.exists(full) and full.startswith(root + os.sep):
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        old_content = f.read()
                except Exception:
                    pass
            if old_content:
                self._add_code_safe(path, body.strip(), old_content)

        plugin_results = self.plugin_manager.trigger("tool_execute", tool_name, args, body)
        for pr in plugin_results:
            if pr is not None:
                return pr

        result = self.tool_registry.execute(tool_name, args, body, self.project_root, {"todo_list": self.todo_list})

        tool_result_text = result.get("result", "")
        success = result.get("success", True)

        if tool_name == "write" and result.get("old_content"):
            self._add_code_safe(args.strip().strip('"').strip("'"), body.strip(), result["old_content"])

        if tool_name == "run":
            self._add_tool_safe(tool_name, args, tool_result_text[:500], success)
        elif tool_name == "write":
            lines = body.count("\n") + 1 if body else 0
            self._add_tool_safe(tool_name, args, f"{lines} lines written", success)
        elif tool_name == "read":
            self._add_code_safe(f"{args.strip()}", tool_result_text)
        elif tool_name == "ls":
            count = result.get("count", 0)
            self._add_tool_safe(tool_name, args, f"{count} entries", success)
        elif tool_name == "grep":
            count = result.get("count", 0)
            self._add_tool_safe(tool_name, f"{args}", f"{count} matches", success)
        elif tool_name == "glob":
            count = result.get("count", 0)
            extra = result.get("extra", "")
            self._add_tool_safe(tool_name, args, f"{count} files{extra}", success)
        elif tool_name == "edit":
            self._add_code_safe(args.strip(), result.get("new_content", ""), result.get("old_content", ""))
            self._add_tool_safe(tool_name, args, "Applied", success)
        elif tool_name == "web-fetch":
            bytes_fetched = result.get("bytes", 0)
            self._add_tool_safe(tool_name, args, f"{bytes_fetched} bytes fetched", success)
        elif tool_name == "web-search":
            count = result.get("count", 0)
            self._add_tool_safe(tool_name, args, f"{count} results", success)
        elif tool_name == "git":
            self._add_tool_safe(tool_name, args, tool_result_text[:500], success)
        elif tool_name == "todo":
            if "todo_list" in result:
                self.todo_list = result["todo_list"]
            self._add_tool_safe(tool_name, args, tool_result_text, success)
        else:
            self._add_tool_safe(tool_name, args, tool_result_text[:500], success)

        self.plugin_manager.trigger("tool_result", tool_name, args, result)

        if not success and "Unknown tool" in tool_result_text:
            for ct in self.config.get("custom_tools", []):
                if tool_name == ct.get("name", ""):
                    cmd = ct.get("command", "").replace("{path}", args).replace("{args}", args)
                    self._add_tool_safe(tool_name, cmd, "")
                    try:
                        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=self.project_root)
                        out = r.stdout.rstrip()
                        err = r.stderr.rstrip()[:500]
                        result_text = out or err or "(ok)"
                        self._add_tool_safe(tool_name, cmd, result_text[:500], r.returncode == 0)
                        return result_text[:2000]
                    except Exception as e:
                        self._add_tool_safe(tool_name, cmd, str(e), False)
                        return f"Error: {e}"

        return tool_result_text[:2000]

    def _run_lint(self):
        result = self.formatter_manager.run_lint(self.project_root)
        if result:
            return result
        cmd = self.config.get("lint_command", "").strip()
        if not cmd:
            return ""
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=self.project_root)
            if r.returncode != 0:
                out = (r.stdout + r.stderr)[:500].strip()
                if out:
                    return f"Lint ({cmd}):\n{out}"
        except Exception:
            pass
        return ""

    def _format_file(self, filepath):
        result = self.formatter_manager.format_file(filepath, self.project_root)
        if result:
            for r in result:
                if r:
                    self._add_system_safe(f"[format] {r}")

    def _add_tool_safe(self, tool, args, result, success=True):
        try:
            self._add_tool(tool, args, result, success)
        except Exception:
            try:
                self.call_from_thread(self._add_tool, tool, args, result, success)
            except (RuntimeError, Exception):
                pass

    def _add_code_safe(self, path, content, old=""):
        try:
            self._add_code(path, content, old)
        except Exception:
            try:
                self.call_from_thread(self._add_code, path, content, old)
            except (RuntimeError, Exception):
                pass


def run_tui(project_root=None, provider=None, model=None, api_key=None, session_id=None, proxy_url=None):
    app = CipherApp(
        project_root=project_root,
        provider=provider,
        model=model,
        api_key=api_key,
        session_id=session_id,
        proxy_url=proxy_url,
    )
    try:
        app.run()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nCipher crashed: {e}")

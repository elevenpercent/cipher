"""Cipher - Textual TUI Chat Application"""
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
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Static, Input, Label, Button, Checkbox, Select, Rule
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from rich.text import Text
from cipher.provider import AIProvider, PROVIDERS

CONFIG_DIR = Path.home() / ".cipher"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
CONFIG_DIR.mkdir(exist_ok=True)
SESSIONS_DIR.mkdir(exist_ok=True)

SLASH_COMMANDS = {
    "/clear": "Clear chat history",
    "/stats": "Show session statistics",
    "/cd": "Change working directory",
    "/provider": "Show/switch provider",
    "/model": "Show/switch model",
    "/providers": "List all providers",
    "/models": "List all models",
    "/config": "Show configuration",
    "/dir": "Show working directory",
    "/history": "Show command history",
    "/new": "Start new session",
    "/sessions": "View saved sessions",
    "/quit": "Exit Cipher",
    "/help": "Show all commands",
}

THINKING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧"]


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
                    import urllib.request
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
        "provider": "ollama",
        "model": "ollama/qwen3:14b",
        "show_plan": True,
        "show_code": True,
        "show_summary": True,
        "show_tool_exec": True,
        "show_diff": True,
        "expand_explanations": False,
        "auto_confirm": False,
        "compact_mode": False,
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
        return result


class LoadingIndicator(Static):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.frame_idx = 0
        self.text = "Thinking"
        self.dots = ""
    def on_mount(self):
        self.set_interval(0.15, self._tick)
    def _tick(self):
        self.frame_idx = (self.frame_idx + 1) % len(THINKING_FRAMES)
        self.dots = "." * ((self.frame_idx % 3) + 1)
        self.update(f"  {THINKING_FRAMES[self.frame_idx]} {self.text}{self.dots}")


class ProviderPanel(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(False)", "Close")]
    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.available = detect_available_providers()
        self.selected_provider = self.config.get("provider", "ollama")
        self.selected_model = self.config.get("model", "")
    def compose(self):
        with Container(id="provider-panel"):
            yield Static("  Switch Provider  [esc] Close", id="panel-title")
            yield Static("Only showing providers your system can use", id="panel-hint")
            for prov in self.available:
                pid = prov["id"]
                info = PROVIDERS.get(pid, {})
                status = "AVAILABLE" if prov["available"] else "MISSING"
                status_style = "green" if prov["available"] else "red"
                cur = " [current]" if pid == self.selected_provider else ""
                models = [m["name"] for m in info.get("models", [])]
                model_str = " | ".join(models[:3])
                if len(models) > 3:
                    model_str += f" +{len(models)-3} more"
                yield Static(f"  {status}  {info['name']:<14} {model_str}{cur}", id=f"prov-{pid}", classes=f"prov-row {'prov-active' if pid == self.selected_provider else ''} {'prov-unavailable' if not prov['available'] else ''}")
            yield Rule()
            yield Static("Provider: " + self.selected_provider, id="panel-status")
            yield Static("Model: " + self.selected_model, id="panel-model")
            with Horizontal():
                yield Button("Select", id="panel_select", variant="primary")
                yield Button("Cancel", id="panel_cancel", variant="default")

    def on_key(self, event):
        if event.key == "tab":
            event.prevent_default()
            available_ids = [p["id"] for p in self.available if p["available"]]
            if self.selected_provider in available_ids:
                idx = available_ids.index(self.selected_provider)
                idx = (idx + 1) % len(available_ids)
            else:
                idx = 0
            self.selected_provider = available_ids[idx]
            models = PROVIDERS.get(self.selected_provider, {}).get("models", [])
            if models:
                self.selected_model = models[0]["id"]
            self._update_display()
        elif event.key == "up":
            event.prevent_default()
            available_ids = [p["id"] for p in self.available if p["available"]]
            if self.selected_provider in available_ids:
                idx = available_ids.index(self.selected_provider)
                idx = (idx - 1) % len(available_ids)
            else:
                idx = 0
            self.selected_provider = available_ids[idx]
            models = PROVIDERS.get(self.selected_provider, {}).get("models", [])
            if models:
                self.selected_model = models[0]["id"]
            self._update_display()
        elif event.key == "down":
            event.prevent_default()
            available_ids = [p["id"] for p in self.available if p["available"]]
            if self.selected_provider in available_ids:
                idx = available_ids.index(self.selected_provider)
                idx = (idx + 1) % len(available_ids)
            else:
                idx = 0
            self.selected_provider = available_ids[idx]
            models = PROVIDERS.get(self.selected_provider, {}).get("models", [])
            if models:
                self.selected_model = models[0]["id"]
            self._update_display()
        elif event.key == "enter":
            event.prevent_default()
            self._confirm()

    def _update_display(self):
        info = PROVIDERS.get(self.selected_provider, {})
        models = [m["name"] for m in info.get("models", [])]
        model_str = " | ".join(models[:3])
        self.query_one("#panel-status").update(f"Provider: {self.selected_provider}")
        self.query_one("#panel-model").update(f"Model: {self.selected_model}")
        for prov in self.available:
            pid = prov["id"]
            status = "AVAILABLE" if prov["available"] else "MISSING"
            cur = " [selected]" if pid == self.selected_provider else " [current]" if pid == self.config.get("provider") else ""
            info2 = PROVIDERS.get(pid, {})
            row = self.query_one(f"#prov-{pid}")
            row.update(f"  {status}  {info2['name']:<14} {model_str}{cur}")
            row.classes = f"prov-row {'prov-active' if pid == self.selected_provider else ''} {'prov-unavailable' if not prov['available'] else ''}"

    def _confirm(self):
        self.config["provider"] = self.selected_provider
        self.config["model"] = self.selected_model
        save_config(self.config)
        self.dismiss({"provider": self.selected_provider, "model": self.selected_model})

    def on_button_pressed(self, event):
        if event.button.id == "panel_select":
            self._confirm()
        elif event.button.id == "panel_cancel":
            self.dismiss(None)

    CSS = """
    ProviderPanel { align: center middle; }
    #provider-panel {
        width: 80;
        max-height: 85%;
        background: #0a0a0a;
        border: tall #f5c542;
        padding: 1 2;
        overflow-y: auto;
    }
    #panel-title { text-align: center; text-style: bold; color: #f5c542; margin-bottom: 0; }
    #panel-hint { text-align: center; color: #666; margin-bottom: 1; }
    .prov-row { margin: 0 0 0 0; padding: 0 0 0 0; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
    .prov-active { color: #f5c542; }
    .prov-unavailable { color: #444; }
    #panel-status { color: #aaa; margin-top: 1; }
    #panel-model { color: #aaa; }
    #panel_select { margin-right: 1; }
    """


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
    SessionModal { align: center middle; }
    #session-panel {
        width: 70;
        max-height: 80%;
        background: #0a0a0a;
        border: tall #f5c542;
        padding: 1 2;
        overflow-y: auto;
    }
    #panel-title { text-align: center; text-style: bold; color: #f5c542; margin-bottom: 1; }
    #session-empty { text-align: center; color: #666; margin: 2 0; }
    .sess-row { margin: 0 0 0 0; padding: 0 0 0 0; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #888; }
    .sess-active { color: #f5c542; }
    """


class SettingsModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(False)", "Close")]
    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.config = config
    def compose(self):
        with Container(id="settings-container"):
            yield Static("  Settings", id="settings-title")
            yield Rule()
            yield Static("Display", classes="settings-section")
            yield Checkbox("Show plan", id="show_plan", value=self.config.get("show_plan", True))
            yield Checkbox("Show code blocks", id="show_code", value=self.config.get("show_code", True))
            yield Checkbox("Show diff", id="show_diff", value=self.config.get("show_diff", True))
            yield Checkbox("Show tool results", id="show_tool_exec", value=self.config.get("show_tool_exec", True))
            yield Checkbox("Compact mode", id="compact_mode", value=self.config.get("compact_mode", False))
            yield Rule()
            yield Static("Behavior", classes="settings-section")
            yield Checkbox("Auto-confirm actions", id="auto_confirm", value=self.config.get("auto_confirm", False))
            yield Checkbox("Expand explanations", id="expand_explanations", value=self.config.get("expand_explanations", False))
            yield Rule()
            yield Static("AI Provider", classes="settings-section")
            provider_options = [(info["name"], pid) for pid, info in PROVIDERS.items()]
            current = self.config.get("provider", "ollama")
            yield Select(provider_options, value=current, id="provider_select", prompt="Select provider...")
            model_list = PROVIDERS.get(current, {}).get("models", [])
            model_options = [(m["name"], m["id"]) for m in model_list]
            current_model = self.config.get("model", "")
            yield Select(model_options, value=current_model if any(m[1] == current_model for m in model_options) else None, id="model_select", prompt="Select model...")
            yield Rule()
            with Horizontal():
                yield Button("Save", id="settings_save", variant="primary")
                yield Button("Cancel", id="settings_cancel", variant="default")

    def on_select_changed(self, event):
        if event.select.id == "provider_select":
            pid = event.value
            if pid and pid in PROVIDERS:
                model_list = PROVIDERS[pid].get("models", [])
                model_options = [(m["name"], m["id"]) for m in model_list]
                ms = self.query_one("#model_select", Select)
                ms.clear_options()
                ms.set_options(model_options)
                ms.value = None

    def on_button_pressed(self, event):
        if event.button.id == "settings_save":
            self.config["show_plan"] = self.query_one("#show_plan", Checkbox).value
            self.config["show_code"] = self.query_one("#show_code", Checkbox).value
            self.config["show_diff"] = self.query_one("#show_diff", Checkbox).value
            self.config["show_tool_exec"] = self.query_one("#show_tool_exec", Checkbox).value
            self.config["compact_mode"] = self.query_one("#compact_mode", Checkbox).value
            self.config["auto_confirm"] = self.query_one("#auto_confirm", Checkbox).value
            self.config["expand_explanations"] = self.query_one("#expand_explanations", Checkbox).value
            ps = self.query_one("#provider_select", Select)
            ms = self.query_one("#model_select", Select)
            if ps.value:
                self.config["provider"] = str(ps.value)
            if ms.value:
                self.config["model"] = str(ms.value)
            save_config(self.config)
            self.dismiss(self.config)
        elif event.button.id == "settings_cancel":
            self.dismiss(None)

    CSS = """
    SettingsModal { align: center middle; }
    #settings-container { width: 55; max-height: 80%; background: $surface; border: tall #f5c542; padding: 1 2; overflow-y: auto; }
    #settings-title { text-align: center; text-style: bold; margin-bottom: 1; }
    .settings-section { margin-top: 1; margin-bottom: 1; text-style: bold; color: $text-muted; }
    Checkbox { margin: 0 0 1 0; }
    Select { margin: 0 0 1 0; }
    #settings_save { margin-right: 1; }
    """


class SlashAutocomplete(Container):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.suggestions = []
        self.selected_idx = 0
    def compose(self):
        yield Static("", id="ac-display")

    def update_suggestions(self, query):
        if not query or not query.startswith("/"):
            self.suggestions = []
            self.selected_idx = 0
            self.query_one("#ac-display").update("")
            self.add_class("hidden")
            return
        parts = query.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        self.suggestions = []
        for sc, desc in SLASH_COMMANDS.items():
            if sc.startswith(cmd):
                self.suggestions.append((sc, desc))
        if not self.suggestions:
            self.add_class("hidden")
            self.query_one("#ac-display").update("")
            return
        self.selected_idx = min(self.selected_idx, len(self.suggestions) - 1)
        lines = []
        for i, (sc, desc) in enumerate(self.suggestions):
            if i == self.selected_idx:
                lines.append(f"  {sc:<14} {desc}")
            else:
                lines.append(f"  {sc:<14} {desc}")
        display = "\n".join(lines[:5])
        self.query_one("#ac-display").update(display)
        self.remove_class("hidden")
        if self.parent:
            self.parent.refresh()

    def navigate(self, direction):
        if not self.suggestions:
            return
        self.selected_idx = max(0, min(len(self.suggestions) - 1, self.selected_idx + direction))
        self.update_suggestions("/" + (self.suggestions[0][0][1:] if self.suggestions else ""))

    def get_selected(self):
        if self.suggestions and 0 <= self.selected_idx < len(self.suggestions):
            return self.suggestions[self.selected_idx][0]
        return None

    CSS = """
    SlashAutocomplete {
        height: auto;
        margin: 0 2;
        padding: 0 1;
        background: #0a0a0a;
        border-top: solid #f5c542;
    }
    SlashAutocomplete.hidden { display: none; }
    #ac-display {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        color: #f5c542;
        margin: 0;
    }
    """


class CipherApp(App):
    CSS = """
    Screen { background: #050505; }
    #app-layout { layout: vertical; height: 100%; }
    #header-bar { height: 3; dock: top; background: #0a0a0a; border-bottom: solid #1a1a1a; }
    #header-left { dock: left; margin: 0 2; color: #f5c542; text-style: bold; }
    #header-right { dock: right; margin: 0 2; color: #666; }
    #session-title { dock: top; height: 2; background: #080808; border-bottom: solid #111; margin: 0 2; color: #aaa; }
    #status-bar { height: 1; background: #080808; border-bottom: solid #111; }
    #chat-container { height: 1fr; overflow-y: auto; padding: 1 2; }
    #input-bar { height: auto; dock: bottom; background: #0a0a0a; border-top: solid #1a1a1a; }
    #chat-input { margin: 0 2; border: none; }
    .msg-user { margin: 1 0; padding: 0 1; color: #f5c542; }
    .msg-assistant { margin: 1 0; padding: 0 1; }
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
        Binding("ctrl+p", "providers", "Providers", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("escape", "clear_input", "Clear input", show=False),
    ]

    def __init__(self, project_root=None, provider=None, model=None, api_key=None, session_id=None):
        super().__init__()
        self.project_root = os.path.abspath(project_root or os.getcwd())
        self.config = load_config()
        if provider:
            self.config["provider"] = provider
        if model:
            self.config["model"] = model
        self.api_key = api_key or None
        self.messages = []
        self.chat_messages = []
        self.total_tools = 0
        self.session_start = time.time()
        self.system_prompt = self._build_system_prompt()
        self.chat_messages = [{"role": "system", "content": self.system_prompt}]
        self.command_history = []
        self.history_index = -1
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_title = ""
        self.is_processing = False
        self.loading_widget = None
        self.autocomplete = None

    def _build_system_prompt(self):
        return f"""You are Cipher, an expert autonomous coding agent.

WORKING DIRECTORY: {self.project_root}

SCOPE: ONLY create, read, write, or modify files INSIDE "{self.project_root}".
NEVER use absolute paths or "../".

## PROCESS
1. Output <plan>...</plan> FIRST
2. Then ONE action tag per turn
3. Summarize when done

## ACTION TAGS (NO markdown code blocks):
<run>command</run>
<write path="relative/path">
complete content - NO "..."
</write>
<read path="relative/path">
<ls>path</ls>

## RULES
- NEVER wrap tags in markdown code blocks
- ALWAYS write COMPLETE files
- Use RELATIVE paths
- mkdir first, then write files
"""

    def compose(self):
        with Container(id="app-layout"):
            with Horizontal(id="header-bar"):
                yield Label("CIPHER //", id="header-left")
                yield Label(f"{self.config['provider']} | {self.config['model']}", id="header-right")
            yield Label(f"  {self.session_title or 'New Session'}", id="session-title")
            yield Static("", id="status-bar")
            yield ScrollableContainer(id="chat-container")
            with Container(id="input-bar"):
                yield Input(placeholder="Ask Cipher...  Ctrl+P providers  /help commands", id="chat-input")
                yield SlashAutocomplete()

    def on_mount(self):
        self.query_one("#chat-input").focus()
        info = PROVIDERS.get(self.config.get("provider", "ollama"), {})
        available = detect_available_providers()
        available_str = ", ".join([p["id"] for p in available if p["available"]])
        if not available_str:
            available_str = "none"
        self._add_system(f"Cipher ready | {info.get('name', 'AI')} | {self.config.get('provider')} | {self.config.get('model')}")
        self._add_system(f"Available: {available_str}")
        self._add_system(f"Working: {self.project_root}")
        if self.session_title:
            self.query_one("#session-title").update(f"  {self.session_title}")

        saved = load_session(self.session_id)
        if saved and saved.get("messages"):
            self.chat_messages = saved["messages"]
            self.chat_messages = [m for m in self.chat_messages if m["role"] != "system"]
            self.chat_messages.insert(0, {"role": "system", "content": self.system_prompt})
            self._add_system(f"Resumed session: {saved.get('title', 'untitled')}")

        self.autocomplete = self.query_one(SlashAutocomplete)

    def _set_status(self, text):
        try:
            self.query_one("#status-bar", Static).update(text)
        except Exception:
            pass

    def _add_user(self, text):
        msg = Static(f"\u2192 {text}", classes="msg-user")
        container = self.query_one("#chat-container")
        container.mount(msg)
        container.scroll_end()

    def _add_assistant(self, text):
        msg = Static(text, classes="msg-assistant")
        container = self.query_one("#chat-container")
        container.mount(msg)
        container.scroll_end()

    def _add_plan(self, text):
        if not self.config.get("show_plan", True):
            return
        block = PlanBlock(text, classes="msg-plan")
        container = self.query_one("#chat-container")
        container.mount(block)
        container.scroll_end()

    def _add_code(self, path, content, old=""):
        if not self.config.get("show_code", True):
            return
        block = CodeBlock(path, content, old, classes="msg-code")
        container = self.query_one("#chat-container")
        container.mount(block)
        container.scroll_end()

    def _add_tool(self, tool, args, result, success=True):
        if not self.config.get("show_tool_exec", True):
            return
        widget = ToolResult(tool, args, result, success, classes="msg-tool")
        container = self.query_one("#chat-container")
        container.mount(widget)
        container.scroll_end()

    def _add_explanation(self, summary, details=""):
        block = ExplanationBlock(summary, details, self.config.get("expand_explanations", False), classes="msg-explanation")
        container = self.query_one("#chat-container")
        container.mount(block)
        container.scroll_end()

    def _add_system(self, text):
        msg = Static(f"  {text}", classes="msg-system")
        container = self.query_one("#chat-container")
        container.mount(msg)
        container.scroll_end()

    def on_input_changed(self, event):
        if self.autocomplete:
            self.autocomplete.update_suggestions(event.value)

    def on_key(self, event):
        if self.is_processing:
            return
        if self.autocomplete and not self.autocomplete.has_class("hidden"):
            if event.key == "up":
                event.prevent_default()
                self.autocomplete.navigate(-1)
                return
            elif event.key == "down":
                event.prevent_default()
                self.autocomplete.navigate(1)
                return
            elif event.key == "tab":
                event.prevent_default()
                selected = self.autocomplete.get_selected()
                if selected:
                    inp = self.query_one("#chat-input", Input)
                    inp.value = selected + " "
                    self.autocomplete.update_suggestions(selected + " ")
                return

    def on_input_submitted(self, event):
        user_input = event.value.strip()
        if not user_input:
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
        if self.autocomplete:
            self.autocomplete.update_suggestions("")

        if user_input.startswith("/"):
            self._handle_command(user_input)
            return

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

        self.run_worker(self._run_agent_loop_thread, exclusive=True)

    def _run_agent_loop_thread(self):
        max_turns = 20
        for turn in range(max_turns):
            buffer = ""
            try:
                self.call_from_thread(self._set_status, "Thinking")
                ai = AIProvider(
                    provider_id=self.config.get("provider", "ollama"),
                    model_id=self.config.get("model", "ollama/qwen3:14b"),
                    api_key=self.api_key,
                )
                for chunk in ai.chat(self.chat_messages, stream=True):
                    token = chunk.get("content", "")
                    if not token:
                        continue
                    buffer += token

                self.call_from_thread(self._set_status, "Processing")

                plan_match = re.search(r'<plan>(.*?)</plan>', buffer, re.DOTALL)
                if plan_match:
                    self.call_from_thread(self._add_plan, plan_match.group(1))

                tool, args, body = self._parse_tools(buffer)
                if tool:
                    result = self._execute_tool(tool, args, body)
                    self.total_tools += 1
                    self.chat_messages.append({"role": "assistant", "content": buffer})
                    self.chat_messages.append({"role": "user", "content": f"Result: {result}\nContinue."})
                    continue

                clean = re.sub(r'<plan>.*?</plan>', '', buffer, flags=re.DOTALL)
                clean = re.sub(r'<write\s+path=["\'].*?["\']>.*?</write>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'<run>.*?</run>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'<read\s+path=["\'].*?["\']\s*/?\s*>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'<ls>.*?</ls>', '', clean, flags=re.DOTALL)
                clean = clean.strip()
                if clean:
                    self.call_from_thread(self._add_explanation, clean)
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

    def _remove_loading(self):
        if self.loading_widget:
            self.loading_widget.remove()
            self.loading_widget = None

    def _set_ready(self):
        self.is_processing = False
        self.query_one("#chat-input").focus()

    def _handle_command(self, cmd):
        parts = cmd.split(None, 1)
        action = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        container = self.query_one("#chat-container")

        if action == "/clear":
            self.chat_messages = [{"role": "system", "content": self.system_prompt}]
            for child in list(container.children):
                child.remove()
            self._add_system("Chat cleared.")

        elif action == "/stats":
            elapsed = time.time() - self.session_start
            self._add_system(f"Tools: {self.total_tools} | Turns: {len(self.chat_messages)-1} | Time: {int(elapsed//60)}m {int(elapsed%60)}s")

        elif action == "/cd" and args:
            new_dir = os.path.abspath(args)
            if os.path.isdir(new_dir):
                self.project_root = new_dir
                self._add_system(f"Working directory: {new_dir}")
            else:
                self._add_system(f"Not a directory: {args}")

        elif action == "/help":
            lines = [
                "Slash commands:",
                "  /clear              Clear chat history",
                "  /stats              Show session statistics",
                "  /cd <path>          Change working directory",
                "  /provider           Show current AI provider",
                "  /provider <id>      Switch provider",
                "  /model              Show current model",
                "  /model <name>       Switch model",
                "  /providers          List all available providers",
                "  /models             List all models for current provider",
                "  /config             Show current configuration",
                "  /dir                Show working directory",
                "  /history            Show command history",
                "  /new                Start new session (reset)",
                "  /sessions           View saved sessions",
                "  /quit               Exit Cipher",
                "  /help               Show this help",
            ]
            msg = Static("\n".join(lines), classes="cmd-block")
            container.mount(msg)
            container.scroll_end()

        elif action == "/provider" and args:
            pid = args.lower()
            if pid in PROVIDERS:
                self.config["provider"] = pid
                models = PROVIDERS[pid].get("models", [])
                if models:
                    self.config["model"] = models[0]["id"]
                save_config(self.config)
                info = PROVIDERS[pid]
                self._add_system(f"Switched to {info['name']} ({pid})")
                self._add_system(f"Model: {self.config['model']}")
                self.query_one("#header-right").update(f"{pid} | {self.config['model']}")
                self.system_prompt = self._build_system_prompt()
                self.chat_messages = [{"role": "system", "content": self.system_prompt}]
            else:
                self._add_system(f"Unknown provider: {pid}")
                self._add_system(f"Available: {', '.join(PROVIDERS.keys())}")

        elif action == "/provider":
            self._add_system(f"Current provider: {self.config['provider']} ({PROVIDERS.get(self.config['provider'], {}).get('name', 'unknown')})")

        elif action == "/model" and args:
            pid = self.config.get("provider", "ollama")
            models = PROVIDERS.get(pid, {}).get("models", [])
            model_ids = [m["id"] for m in models]
            model_names = [m["name"] for m in models]
            if args in model_ids:
                self.config["model"] = args
                save_config(self.config)
                self._add_system(f"Switched to model: {args}")
                self.query_one("#header-right").update(f"{self.config['provider']} | {args}")
            else:
                for mid, mname in zip(model_ids, model_names):
                    if args.lower() in mid.lower() or args.lower() in mname.lower():
                        self.config["model"] = mid
                        save_config(self.config)
                        self._add_system(f"Switched to model: {mid}")
                        self.query_one("#header-right").update(f"{self.config['provider']} | {mid}")
                        return
                self._add_system(f"Model not found: {args}")
                self._add_system(f"Available: {', '.join(model_ids)}")

        elif action == "/model":
            self._add_system(f"Current model: {self.config['model']}")

        elif action == "/providers":
            available = detect_available_providers()
            lines = ["Available providers:"]
            for prov in available:
                pid = prov["id"]
                info = PROVIDERS.get(pid, {})
                status = "OK" if prov["available"] else "--"
                lines.append(f"  {status} {pid:<14} {info['name']} - {prov['reason']}")
            msg = Static("\n".join(lines), classes="cmd-block")
            container.mount(msg)
            container.scroll_end()

        elif action == "/models":
            pid = self.config.get("provider", "ollama")
            models = PROVIDERS.get(pid, {}).get("models", [])
            lines = [f"Models for {pid}:"]
            for m in models:
                cur = " <-- current" if m["id"] == self.config.get("model") else ""
                free = " [FREE]" if m.get("free") else ""
                lines.append(f"  {m['id']}{free}{cur}")
            msg = Static("\n".join(lines), classes="cmd-block")
            container.mount(msg)
            container.scroll_end()

        elif action == "/config":
            lines = ["Current configuration:"]
            for k, v in self.config.items():
                lines.append(f"  {k}: {v}")
            msg = Static("\n".join(lines), classes="cmd-block")
            container.mount(msg)
            container.scroll_end()

        elif action == "/dir":
            self._add_system(f"Working directory: {self.project_root}")

        elif action == "/history":
            if self.command_history:
                lines = ["Command history:"]
                for i, h in enumerate(self.command_history[-20:], 1):
                    lines.append(f"  {i}. {h}")
                msg = Static("\n".join(lines), classes="cmd-block")
                container.mount(msg)
                container.scroll_end()
            else:
                self._add_system("No history yet.")

        elif action == "/new":
            self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_title = ""
            self.chat_messages = [{"role": "system", "content": self.system_prompt}]
            self.total_tools = 0
            self.session_start = time.time()
            for child in list(container.children):
                child.remove()
            self.query_one("#session-title").update("  New Session")
            self._add_system("New session started.")

        elif action == "/sessions":
            def on_session(sid):
                if sid:
                    session = load_session(sid)
                    if session:
                        self.session_id = sid
                        self.session_title = session.get("title", "Untitled")
                        self.chat_messages = session.get("messages", [])
                        self.chat_messages = [m for m in self.chat_messages if m["role"] != "system"]
                        self.chat_messages.insert(0, {"role": "system", "content": self.system_prompt})
                        for child in list(container.children):
                            child.remove()
                        self.query_one("#session-title").update(f"  {self.session_title}")
                        self._add_system(f"Loaded session: {self.session_title}")
            self.push_screen(SessionModal(), on_session)

        elif action == "/quit":
            self.exit()

        else:
            self._add_system(f"Unknown command: {action}. Type /help for commands.")

    def _parse_tools(self, text):
        text = re.sub(r'```[a-z]*\n(.*?)\n```', r'\1', text, flags=re.DOTALL)
        m = re.search(r'<run>(.+?)</run>', text, re.DOTALL)
        if m:
            return "run", m.group(1), ""
        m = re.search(r'<write\s+path=["\'](.+?)["\']>(.*?)</write>', text, re.DOTALL)
        if m:
            return "write", m.group(1), m.group(2)
        m = re.search(r'<read\s+path=["\'](.+?)["\']\s*/?\s*>', text, re.DOTALL)
        if m:
            return "read", m.group(1), ""
        m = re.search(r'<ls>(.*?)</ls>', text, re.DOTALL)
        if m:
            return "ls", m.group(1).strip(), ""
        return None, None, None

    def _execute_tool(self, tool, args, body=""):
        if tool == "run":
            cmd = args.strip()
            self._add_tool("run", cmd, "")
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=self.project_root)
                out = r.stdout.rstrip()
                success = r.returncode == 0
                self._add_tool("run", cmd, out or "(ok)", success)
                return out or "(ok)"
            except subprocess.TimeoutExpired:
                self._add_tool("run", cmd, "Timeout (30s)", False)
                return "Error: timeout"
            except Exception as e:
                self._add_tool("run", cmd, str(e), False)
                return f"Error: {e}"

        elif tool == "write":
            path = args.strip().strip('"').strip("'")
            full = os.path.abspath(os.path.join(self.project_root, path))
            full = os.path.normpath(full)
            root = os.path.normpath(self.project_root)
            if not full.startswith(root + os.sep) and full != root:
                self._add_tool("write", path, "Escapes project root", False)
                return "Path escapes project root"
            old_content = ""
            if os.path.exists(full):
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        old_content = f.read()
                except Exception:
                    pass
            self._add_code(path, body.strip(), old_content)
            try:
                os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(body.strip())
                lines = body.count("\n") + 1
                self._add_tool("write", path, f"{lines} lines written", True)
                return f"Written: {path} ({lines} lines)"
            except Exception as e:
                self._add_tool("write", path, str(e), False)
                return f"Error: {e}"

        elif tool == "read":
            path = args.strip().strip('"').strip("'")
            full = os.path.abspath(os.path.join(self.project_root, path))
            full = os.path.normpath(full)
            root = os.path.normpath(self.project_root)
            if not full.startswith(root + os.sep) and full != root:
                self._add_tool("read", path, "Escapes project root", False)
                return "Path escapes project root"
            if not os.path.exists(full):
                self._add_tool("read", path, "File not found", False)
                return f"File not found: {path}"
            with open(full, encoding="utf-8", errors="replace") as f:
                content = f.read()
            self._add_code(path, content)
            return content

        elif tool == "ls":
            path = (args or ".").strip().strip('"').strip("'")
            full = os.path.abspath(os.path.join(self.project_root, path))
            full = os.path.normpath(full)
            root = os.path.normpath(self.project_root)
            if not full.startswith(root + os.sep) and full != root:
                self._add_tool("ls", path, "Escapes project root", False)
                return "Path escapes project root"
            if not os.path.isdir(full):
                self._add_tool("ls", path, "Not a directory", False)
                return f"Not a directory: {path}"
            entries = []
            for e in sorted(os.listdir(full)):
                is_dir = os.path.isdir(os.path.join(full, e))
                icon = "DIR" if is_dir else "   "
                entries.append(f"{icon} {e}")
            self._add_tool("ls", path, f"{len(entries)} entries", True)
            return "\n".join(entries)

        return f"Unknown tool: {tool}"


def run_tui(project_root=None, provider=None, model=None, api_key=None, session_id=None):
    app = CipherApp(
        project_root=project_root,
        provider=provider,
        model=model,
        api_key=api_key,
        session_id=session_id,
    )
    try:
        app.run()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nCipher crashed: {e}")

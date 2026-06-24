"""Cipher TUI — Textual front end for the agent loop."""

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from .agent import Agent
from .client import ChatClient
from .config import PROVIDERS, SESSIONS_DIR, load_config, resolve_endpoint, save_config
from .mcp import MCPManager


# ── approval modal ────────────────────────────────────────────────────

class ApprovalScreen(ModalScreen[str]):
    """Shows a diff or command and asks allow once / always / deny."""

    BINDINGS = [
        Binding("a", "verdict('allow')", "allow once"),
        Binding("y", "verdict('always')", "always allow"),
        Binding("d", "verdict('deny')", "deny"),
        Binding("escape", "verdict('deny')", "deny"),
    ]

    CSS = """
    ApprovalScreen { align: center middle; }
    #approval-box {
        width: 90%; max-width: 110; max-height: 80%;
        background: $surface; border: tall $warning;
        padding: 1 2;
    }
    #approval-title { text-style: bold; color: $warning; margin-bottom: 1; }
    #approval-detail { max-height: 30; border: round $primary-darken-2; padding: 0 1; }
    #approval-buttons { height: 3; margin-top: 1; align-horizontal: center; }
    #approval-buttons Button { margin: 0 2; }
    """

    def __init__(self, req: dict):
        super().__init__()
        self.req = req

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-box"):
            yield Label(self.req["title"], id="approval-title")
            with VerticalScroll(id="approval-detail"):
                yield Static(self._render_detail())
            with Horizontal(id="approval-buttons"):
                yield Button("Allow once (a)", variant="success", id="allow")
                yield Button("Always allow (y)", variant="warning", id="always")
                yield Button("Deny (d)", variant="error", id="deny")

    def _render_detail(self) -> Text:
        detail = self.req["detail"]
        if self.req["kind"] != "write":
            return Text(detail, style="bold cyan")
        text = Text()
        for line in detail.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                text.append(line + "\n", style="green")
            elif line.startswith("-") and not line.startswith("---"):
                text.append(line + "\n", style="red")
            elif line.startswith("@@"):
                text.append(line + "\n", style="cyan")
            else:
                text.append(line + "\n", style="dim")
        return text

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

    def action_verdict(self, verdict: str) -> None:
        self.dismiss(verdict)


# ── provider setup modal ──────────────────────────────────────────────

class SetupScreen(ModalScreen[bool]):
    CSS = """
    SetupScreen { align: center middle; }
    #setup-box {
        width: 70; background: $surface;
        border: tall $accent; padding: 1 2;
    }
    #setup-box Label { margin-top: 1; color: $text-muted; }
    #setup-title { text-style: bold; color: $accent; }
    #setup-buttons { height: 3; margin-top: 1; align-horizontal: center; }
    #setup-buttons Button { margin: 0 2; }
    """

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        options = [(p["name"], pid) for pid, p in PROVIDERS.items()]
        with Vertical(id="setup-box"):
            yield Label("Cipher setup", id="setup-title")
            yield Label("Provider")
            yield Select(options, value=self.cfg.get("provider", "proxy"),
                         allow_blank=False, id="sel-provider")
            yield Label("Model (blank = provider default)")
            yield Input(value=self.cfg.get("model", ""), id="in-model",
                        placeholder=self._default_model(self.cfg.get("provider", "proxy")))
            yield Label("API key (blank for proxy/ollama; env vars also work)")
            yield Input(value=self.cfg.get("api_key", ""), password=True, id="in-key")
            yield Label("Custom base URL (only for Custom provider)")
            yield Input(value=self.cfg.get("custom_base", ""), id="in-base",
                        placeholder="https://my-endpoint/v1")
            with Horizontal(id="setup-buttons"):
                yield Button("Save", variant="success", id="save")
                yield Button("Cancel", id="cancel")

    @staticmethod
    def _default_model(pid: str) -> str:
        return PROVIDERS.get(pid, {}).get("default_model", "")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sel-provider":
            self.query_one("#in-model", Input).placeholder = self._default_model(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.cfg["provider"] = self.query_one("#sel-provider", Select).value
            self.cfg["model"] = self.query_one("#in-model", Input).value.strip()
            self.cfg["api_key"] = self.query_one("#in-key", Input).value.strip()
            self.cfg["custom_base"] = self.query_one("#in-base", Input).value.strip()
            save_config(self.cfg)
            self.dismiss(True)
        else:
            self.dismiss(False)


# ── inline code editor panel ──────────────────────────────────────────

class CodePanel(Vertical):
    """Right-side live file viewer. Updates whenever the agent writes/edits a file."""

    DEFAULT_CSS = """
    CodePanel {
        width: 1fr; border-left: tall $primary-darken-2;
        background: $surface-darken-1;
    }
    #editor-header {
        height: 1; background: $primary-darken-3;
        color: $text-muted; padding: 0 1; dock: top;
    }
    #editor-scroll { padding: 0; }
    #editor-content { padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("  No file open", id="editor-header")
        with VerticalScroll(id="editor-scroll"):
            yield Static("", id="editor-content")

    def show_file(self, path: str, content: str) -> None:
        """Update panel with new file content (called from the main thread)."""
        rel = path
        try:
            rel = str(Path(path).relative_to(Path.cwd()))
        except ValueError:
            pass

        ext = Path(path).suffix.lstrip(".") or "text"
        _LANG_MAP = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "tsx": "tsx", "jsx": "jsx", "rs": "rust", "go": "go",
            "md": "markdown", "json": "json", "yaml": "yaml", "yml": "yaml",
            "toml": "toml", "sh": "bash", "ps1": "powershell",
            "html": "html", "css": "css",
        }
        lang = _LANG_MAP.get(ext, "text")

        self.query_one("#editor-header", Static).update(f"  {rel}")
        syntax = Syntax(
            content, lang,
            theme="monokai",
            line_numbers=True,
            word_wrap=False,
        )
        self.query_one("#editor-content", Static).update(syntax)
        self.query_one("#editor-scroll", VerticalScroll).scroll_home(animate=False)

    def clear(self) -> None:
        self.query_one("#editor-header", Static).update("  No file open")
        self.query_one("#editor-content", Static).update("")


# ── main app ──────────────────────────────────────────────────────────

class CipherApp(App):
    TITLE = "cipher"

    BINDINGS = [
        Binding("ctrl+p", "settings", "settings"),
        Binding("ctrl+e", "toggle_editor", "editor"),
        Binding("escape", "cancel_task", "cancel", show=False),
        Binding("ctrl+q", "quit", "quit"),
    ]

    CSS = """
    #topbar {
        dock: top; height: 1; background: $surface;
        color: $text-muted; padding: 0 1;
    }
    #main-area { height: 1fr; }
    #chat-area { width: 2fr; }
    #chat { padding: 0 1; }
    #chat > Static { margin-bottom: 1; }
    #inputbar { dock: bottom; height: 3; padding: 0 1; }
    #prompt { border: tall $accent; }
    .msg-user { color: $text; }
    .msg-tool { color: $text-muted; }
    .msg-status { color: $warning; }
    .msg-error { color: $error; }
    .msg-done { color: $success; }
    """

    def __init__(self, project_root: str, first_task: str = ""):
        super().__init__()
        self.project_root = str(Path(project_root).resolve())
        self.cfg = load_config()
        self.agent: Agent | None = None
        self.busy = False
        self.first_task = first_task
        self.session_path = SESSIONS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
        self._stream_widget: Static | None = None
        self._stream_text = ""
        self._editor_visible = False
        self._mcp: MCPManager | None = None
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._session_cost = 0.0

    # ── layout ────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static("", id="topbar")
        with Horizontal(id="main-area"):
            with Vertical(id="chat-area"):
                yield VerticalScroll(id="chat")
            yield CodePanel(id="editor-panel")
        with Vertical(id="inputbar"):
            yield Input(placeholder="Describe a task…  (Ctrl+E editor, Ctrl+P settings, Ctrl+Q quit)",
                        id="prompt")

    def on_mount(self) -> None:
        # Hide editor panel initially
        self.query_one("#editor-panel", CodePanel).display = False

        self._refresh_topbar()
        self.query_one("#prompt", Input).focus()
        self._add("msg-status",
                  f"cipher · {Path(self.project_root).name} · ready")

        # Start MCP in background so it doesn't block startup
        def _init_mcp():
            try:
                mgr = MCPManager(self.project_root)
                self._mcp = mgr
                if mgr.active:
                    tools = mgr.all_tools()
                    names = ", ".join(f"{t['server']}/{t['name']}" for t in tools[:5])
                    suffix = f" +{len(tools)-5} more" if len(tools) > 5 else ""
                    self.call_from_thread(
                        self._add_text, "msg-status",
                        f"  MCP: {len(tools)} tool(s) connected — {names}{suffix}"
                    )
            except Exception:
                pass

        threading.Thread(target=_init_mcp, daemon=True).start()

        if not self.cfg.get("_configured"):
            self.push_screen(SetupScreen(self.cfg), self._setup_closed)
        elif self.first_task:
            self._start_task(self.first_task)

    def on_unmount(self) -> None:
        if self._mcp:
            self._mcp.stop_all()

    def _setup_closed(self, saved: bool) -> None:
        if saved:
            self.cfg["_configured"] = True
            save_config(self.cfg)
            self._refresh_topbar()
        if self.first_task:
            task, self.first_task = self.first_task, ""
            self._start_task(task)

    def _refresh_topbar(self) -> None:
        _, model, _ = resolve_endpoint(self.cfg)
        provider = PROVIDERS.get(self.cfg.get("provider", "proxy"), {}).get("name", "?")
        mcp_tag = "  MCP✓" if (self._mcp and self._mcp.active) else ""

        # Token / cost display
        total_tok = self._prompt_tokens + self._completion_tokens
        if total_tok > 0:
            tok_str = f"{total_tok / 1000:.1f}k tok"
            cost_str = f"  ${self._session_cost:.4f}" if self._session_cost > 0 else "  free"
            tok_display = f"  ·  {tok_str}{cost_str}"
        else:
            tok_display = ""

        self.query_one("#topbar", Static).update(
            f" {Path(self.project_root).name}  ·  {provider}  ·  {model}{mcp_tag}{tok_display}")

    # ── editor panel toggle ───────────────────────────────────────────

    def action_toggle_editor(self) -> None:
        self._editor_visible = not self._editor_visible
        self.query_one("#editor-panel", CodePanel).display = self._editor_visible

    def _open_editor(self, path: str, content: str) -> None:
        """Called when agent writes/edits a file — auto-open editor."""
        if not self._editor_visible:
            self._editor_visible = True
            self.query_one("#editor-panel", CodePanel).display = True
        self.query_one("#editor-panel", CodePanel).show_file(path, content)

    # ── chat helpers ──────────────────────────────────────────────────

    def _add(self, css_class: str, content) -> Static:
        w = Static(content, classes=css_class)
        chat = self.query_one("#chat", VerticalScroll)
        chat.mount(w)
        chat.scroll_end(animate=False)
        return w

    def _add_text(self, css_class: str, text: str) -> Static:
        return self._add(css_class, Text(text))

    # ── input / task lifecycle ────────────────────────────────────────

    # Pure conversational inputs that should never reach the agent loop.
    _CHAT_ONLY = re.compile(
        r"^\s*(hi|hello|hey|sup|yo|what'?s up|howdy|greetings|good\s+(morning|afternoon|evening)|"
        r"thanks?|thank you|ty|cheers|ok|okay|cool|got it|sounds good|nice|great|awesome|"
        r"who are you|what are you|what can you do|help)\s*[!?.]*\s*$",
        re.IGNORECASE,
    )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        if self.busy:
            self._add_text("msg-status", "still working — Esc to cancel first")
            return
        if self._CHAT_ONLY.match(text):
            self._start_chat(text)
        else:
            self._start_task(text)

    def _start_chat(self, text: str) -> None:
        """Lightweight chat path — no agent loop, no tool tags, no approval gates."""
        self.busy = True
        self._add("msg-user", Text(f"> {text}", style="bold"))
        base, model, key = resolve_endpoint(self.cfg)
        client = ChatClient(base, model, key,
                            is_proxy=self.cfg.get("provider") == "proxy")

        def _worker():
            try:
                messages = [
                    {"role": "system", "content":
                        "You are Cipher, a helpful coding assistant. "
                        "Reply conversationally and briefly."},
                    {"role": "user", "content": text},
                ]
                reply = client.complete(messages, temperature=0.7)
                self.call_from_thread(self._add_text, "msg-ai", reply.strip())
            except Exception as e:
                self.call_from_thread(self._add_text, "msg-error", str(e))
            finally:
                self.call_from_thread(self._task_finished)

        self.run_worker(_worker, thread=True, exclusive=True)

    def _start_task(self, text: str) -> None:
        self.busy = True
        self._add("msg-user", Text(f"> {text}", style="bold"))
        base, model, key = resolve_endpoint(self.cfg)
        client = ChatClient(base, model, key,
                            is_proxy=self.cfg.get("provider") == "proxy")
        if self.agent is None:
            self.agent = Agent(
                self.project_root, client, self.cfg.get("auto_approve", {}),
                on_text=self._cb_text, on_tool=self._cb_tool,
                on_result=self._cb_result, on_status=self._cb_status,
                request_approval=self._cb_approval,
                on_file_change=self._cb_file_change,
                on_token_update=self._cb_token_update,
                mcp=self._mcp,
            )
        else:
            self.agent.client = client
            # Update MCP in case servers connected after agent was created
            if self._mcp and self.agent.mcp is None:
                self.agent.mcp = self._mcp
        self.run_worker(lambda: self._agent_worker(text), thread=True, exclusive=True)

    def _agent_worker(self, text: str) -> None:
        try:
            summary = self.agent.run_task(text)
        except Exception as e:
            summary = f"internal error: {e}"
            self.call_from_thread(self._add_text, "msg-error", summary)
        else:
            self.call_from_thread(self._finish_stream)
            self.call_from_thread(self._add, "msg-done", Text(f"✓ {summary}"))
        self.call_from_thread(self._task_finished)

    def _task_finished(self) -> None:
        self.busy = False
        self._save_session()
        self.query_one("#prompt", Input).focus()

    def action_cancel_task(self) -> None:
        if self.busy and self.agent:
            self.agent.cancel()
            self._add_text("msg-status", "cancelling…")

    def action_settings(self) -> None:
        if self.busy:
            self._add_text("msg-status", "finish or cancel the current task first")
            return
        self.push_screen(SetupScreen(self.cfg), lambda _: self._refresh_topbar())

    # ── agent callbacks (called from worker thread) ───────────────────

    def _cb_text(self, delta: str) -> None:
        self.call_from_thread(self._stream_append, delta)

    def _stream_append(self, delta: str) -> None:
        self._stream_text += delta
        if self._stream_widget is None:
            self._stream_widget = self._add("msg-ai", Text(""))
        self._stream_widget.update(Text(self._stream_text.strip()))
        self.query_one("#chat", VerticalScroll).scroll_end(animate=False)

    def _finish_stream(self) -> None:
        self._stream_widget = None
        self._stream_text = ""

    def _cb_tool(self, name: str, summary: str) -> None:
        label = f"  ⚙ {name}  {summary}".rstrip()
        self.call_from_thread(self._finish_stream)
        self.call_from_thread(self._add_text, "msg-tool", label)

    def _cb_result(self, name: str, ok: bool, output: str) -> None:
        first = output.strip().splitlines()[0][:120] if output.strip() else ""
        mark = "✓" if ok else "✗"
        cls = "msg-tool" if ok else "msg-error"
        self.call_from_thread(self._add_text, cls, f"    {mark} {first}")

    def _cb_status(self, msg: str) -> None:
        self.call_from_thread(self._add_text, "msg-status", f"  ⚡ {msg}")

    def _cb_file_change(self, path: str, content: str) -> None:
        self.call_from_thread(self._open_editor, path, content)

    def _cb_token_update(self, prompt: int, completion: int, cost: float) -> None:
        self._prompt_tokens = prompt
        self._completion_tokens = completion
        self._session_cost = cost
        self.call_from_thread(self._refresh_topbar)

    def _cb_approval(self, req: dict) -> str:
        result: dict = {}
        ready = threading.Event()

        def open_modal() -> None:
            def on_close(verdict: str | None) -> None:
                result["v"] = verdict or "deny"
                ready.set()
            self.push_screen(ApprovalScreen(req), on_close)

        self.call_from_thread(open_modal)
        ready.wait()
        return result.get("v", "deny")

    # ── session persistence ───────────────────────────────────────────

    def _save_session(self) -> None:
        if not self.agent or len(self.agent.messages) < 2:
            return
        try:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "project": self.project_root,
                "saved": time.time(),
                "messages": self.agent.messages,
            }
            self.session_path.write_text(
                json.dumps(data, indent=1), encoding="utf-8")
        except OSError:
            pass


def run_tui(project_root: str, first_task: str = "") -> None:
    CipherApp(project_root, first_task).run()

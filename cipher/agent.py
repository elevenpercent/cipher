"""The agent loop: stream model output, parse tool tags, gate mutations
behind approval callbacks, feed results back, repeat until <done>.

The loop is UI-agnostic. The TUI supplies callbacks:
    on_text(delta)                             streamed assistant prose
    on_tool(name, summary)                     a tool is about to run
    on_result(name, ok, output)                tool finished
    on_status(msg)                             fallbacks / notices
    on_file_change(path, content)              file successfully written/edited
    on_token_update(prompt, completion, total, cost_usd)  token counts
    request_approval(req) -> str               "allow" | "always" | "deny"
        req = {"kind": "write"|"run", "title": str, "detail": str}
"""

import re
import sys
from pathlib import Path

from . import lsp, tools
from .client import ChatClient, ChatError
from .config import model_cost

MAX_TURNS = 30

# Compress context when messages exceed this many characters (~25k tokens).
CONTEXT_COMPRESS_CHARS = 100_000
# Keep this many messages at the tail verbatim after compression.
CONTEXT_KEEP_RECENT = 8

TAG_NAMES = ["read", "write", "edit", "ls", "glob", "grep", "tree",
             "run", "git", "web-fetch", "web-search", "mcp", "done"]

TAG_RX = re.compile(
    r"<(" + "|".join(TAG_NAMES) + r")>(.*?)</\1>",
    re.DOTALL,
)

INTENT_RX = re.compile(
    r"\b(I'?ll|I will|I'?m going to|Let me|going to (?:create|write|add|update|fix|run|edit)|"
    r"Here'?s the|Here is the|I'?ve (?:created|written|added|updated|made|fixed))\b",
    re.IGNORECASE,
)

SHELL_NAME = "PowerShell" if sys.platform == "win32" else "sh"

_BASE_SYSTEM_PROMPT = f"""You are Cipher, an autonomous coding agent working inside a project directory.
You act by emitting tool tags. The runtime executes them and returns results. You never pretend — every file change and command happens through a tag.

TOOLS (the only way to act):
<read>path</read>                      read a file (optionally: path :: 10-80 for a line range)
<tree></tree>                          project file overview
<ls>dir</ls>                           list a directory
<glob>**/*.py</glob>                   find files by pattern
<grep>pattern</grep>                   regex-search file contents (optional 2nd line: subdirectory)
<write>path/to/file.py
full file content here</write>         create or overwrite a file (first line = path)
<edit>path/to/file.py
<<<<
exact existing text
====
replacement text
>>>></edit>                            surgical edit (repeat blocks for multiple changes)
<run>command</run>                     execute a {SHELL_NAME} command in the project root
<git>status</git>                      run a git command
<web-fetch>url</web-fetch>             fetch a web page as text
<web-search>query</web-search>         search the web
<mcp>server_name/tool_name
{{"arg": "value"}}
</mcp>                                 call an MCP tool (only when MCP servers are listed below)
<done>summary of what was done</done>  finish the task

RULES:
1. ACT, don't narrate. Never say "I'll create the file" — emit <write> instead. Never describe code in prose — put it in a tag.
2. Look before you touch. <read> a file before you <edit> it. Use <tree> or <grep> to orient in an unfamiliar codebase.
3. Prefer <edit> for changing existing files; <write> only for new files or full rewrites.
4. In <edit>, the old text must match the file EXACTLY, character for character, including indentation.
5. Verify your work: after writing code, <run> it or run the tests when it is cheap to do so.
6. Every response must contain at least one tool tag, or <done> if the task is finished. Plain text alone is allowed only for pure conversational messages (greetings, clarifying questions, short answers) that need no file or shell action.
7. For real-world factual documents (licenses, legal texts, specs), fetch them with <web-fetch> or <web-search> — never reproduce them from memory.
8. If a tool fails, read the error and correct course. Do not repeat the identical call. Analyze errors carefully — syntax errors mean your code generation failed, not that the file format was wrong.
9. Keep prose minimal: one short line before a tag describing the step is plenty.
10. Plan file structure sensibly: real projects get a proper layout (src dir, tests, README) — not one giant file, unless the task is trivially small.
11. SYNTAX MATTERS: All code must be syntactically correct before writing. For Python: closing brackets/braces match opening ones, indentation is consistent, strings are properly quoted, function definitions are complete. Do not write code with syntax errors.
"""


def _build_system_prompt(mcp_section: str = "") -> str:
    return _BASE_SYSTEM_PROMPT + mcp_section


def parse_tags(text: str) -> list[dict]:
    calls, seen = [], set()
    for m in TAG_RX.finditer(text):
        name, body = m.group(1), m.group(2)
        key = (name, body.strip()[:120])
        if key in seen:
            continue
        seen.add(key)
        calls.append({"name": name, "body": body, "pos": m.start()})
    return calls


def strip_tags(text: str) -> str:
    return TAG_RX.sub("", text).strip()


class Agent:
    def __init__(self, project_root: str, client: ChatClient, auto_approve: dict,
                 on_text, on_tool, on_result, on_status, request_approval,
                 on_file_change=None, on_token_update=None, mcp=None):
        self.root = project_root
        self.client = client
        self.auto = dict(auto_approve)
        self.on_text = on_text
        self.on_tool = on_tool
        self.on_result = on_result
        self.on_status = on_status
        self.on_file_change = on_file_change
        self.on_token_update = on_token_update
        self.mcp = mcp
        self.cancelled = False

        # Cumulative token counts for the whole session
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._session_cost = 0.0

        mcp_section = mcp.prompt_section() if mcp else ""
        self.messages: list[dict] = [
            {"role": "system", "content": _build_system_prompt(mcp_section)}
        ]

    def cancel(self):
        self.cancelled = True

    @property
    def token_counts(self) -> tuple[int, int, float]:
        """Return (prompt_tokens, completion_tokens, session_cost_usd)."""
        return self._prompt_tokens, self._completion_tokens, self._session_cost

    # ── main loop ─────────────────────────────────────────────────────

    def run_task(self, user_text: str) -> str:
        self.cancelled = False
        self.messages.append({"role": "user", "content": user_text})
        nudges = 0

        for _ in range(MAX_TURNS):
            if self.cancelled:
                return "(cancelled)"

            self._maybe_compress_context()

            try:
                response = self._stream_response()
            except ChatError as e:
                self.on_status(f"model error: {e}")
                return f"Model error: {e}"
            if self.cancelled:
                return "(cancelled)"

            self.messages.append({"role": "assistant", "content": response})
            calls = parse_tags(response)

            done = next((c for c in calls if c["name"] == "done"), None)
            actions = [c for c in calls if c["name"] != "done"]

            if not actions:
                if done:
                    return done["body"].strip()
                # Only nudge if the message looks like a deferred action,
                # not a short conversational reply (< 3 words = greeting/answer).
                words = response.strip().split()
                is_conversational = len(words) < 20
                if not is_conversational and INTENT_RX.search(response[:600]) and nudges < 2:
                    nudges += 1
                    self.messages.append({"role": "user", "content":
                        "You described actions but emitted no tool tags. Nothing happened. "
                        "Redo this step using the tags (<write>, <edit>, <run>, ...) or "
                        "finish with <done>summary</done>."})
                    continue
                return response.strip()

            results = []
            for call in actions:
                if self.cancelled:
                    return "(cancelled)"
                res = self._execute(call)
                results.append(f"<result tool=\"{call['name']}\" ok=\"{res['ok']}\">\n"
                               f"{res['output']}\n</result>")

            if done:
                return done["body"].strip()

            self.messages.append({"role": "user", "content":
                "\n".join(results) +
                "\nIf the task is complete, reply with <done>summary</done>. "
                "Otherwise continue with more tool tags."})

        return "Stopped: hit the maximum number of turns for one task."

    # ── context compression ───────────────────────────────────────────

    def _context_chars(self) -> int:
        return sum(len(str(m.get("content", ""))) for m in self.messages)

    def _maybe_compress_context(self) -> None:
        if self._context_chars() < CONTEXT_COMPRESS_CHARS:
            return
        system = self.messages[0]
        keep = min(CONTEXT_KEEP_RECENT, len(self.messages) - 1)
        recent = self.messages[-keep:]
        old = self.messages[1:-keep]
        if len(old) < 4:
            return

        history = "\n\n".join(
            f"{m['role'].upper()}: {str(m.get('content', ''))[:600]}"
            for m in old
        )
        summary_msgs = [{"role": "user", "content":
            "Summarize this coding agent conversation history. "
            "Keep: files created/modified (exact paths), commands and their outcomes, "
            "errors and how they were fixed. Be terse and specific.\n\n" + history}]
        try:
            summary = self.client.complete(summary_msgs, temperature=0.1)
            self.messages = [
                system,
                {"role": "user", "content":
                    f"[Prior context — {len(old)} messages condensed]\n{summary}"},
                {"role": "assistant", "content": "Understood."},
                *recent,
            ]
            self.on_status(f"context compressed ({len(old)} msgs → summary)")
        except Exception:
            pass  # compression failed — continue with full context

    # ── streaming ─────────────────────────────────────────────────────

    def _stream_response(self) -> str:
        parts = []
        visible_upto = 0

        def _on_usage(prompt: int, completion: int) -> None:
            self._prompt_tokens += prompt
            self._completion_tokens += completion
            cost = model_cost(self.client.model, prompt, completion)
            self._session_cost += cost
            if self.on_token_update:
                self.on_token_update(
                    self._prompt_tokens,
                    self._completion_tokens,
                    self._session_cost,
                )

        for delta in self.client.stream(
                self.messages,
                on_fallback=lambda old, new: self.on_status(
                    f"{old} unavailable — trying {new}"),
                on_usage=_on_usage):
            if self.cancelled:
                break
            parts.append(delta)
            text = "".join(parts)
            tag_at = text.find("<", visible_upto)
            safe_upto = tag_at if tag_at != -1 else len(text)
            if safe_upto > visible_upto:
                self.on_text(text[visible_upto:safe_upto])
                visible_upto = safe_upto

        # Flush any remaining prose that came after the last complete tag
        full = "".join(parts)
        after_tags = TAG_RX.sub("", full[visible_upto:]).strip()
        if after_tags:
            self.on_text(after_tags)

        return full

    # ── tool dispatch ─────────────────────────────────────────────────

    def _execute(self, call: dict) -> dict:
        name, body = call["name"], call["body"]
        summary = body.strip().splitlines()[0][:80] if body.strip() else ""
        self.on_tool(name, summary)

        if name in tools.READ_ONLY_TOOLS:
            res = tools.READ_ONLY_TOOLS[name](self.root, body)

        elif name in ("write", "edit"):
            prep = (tools.prepare_write if name == "write" else tools.prepare_edit)(self.root, body)
            if not prep["ok"]:
                res = prep
            else:
                res = self._approve_and_apply_file(prep)

        elif name in ("run", "git"):
            command = body.strip()
            if name == "git":
                command = f"git {command}"
            res = self._approve_and_run(command)

        elif name == "mcp":
            if self.mcp is None:
                res = {"ok": False, "output": "No MCP servers configured. Add servers to ~/.cipher/mcp.json"}
            else:
                res = self.mcp.call(body)

        else:
            res = {"ok": False, "output": f"unknown tool: {name}"}

        self.on_result(name, res["ok"], res["output"])
        return res

    def _approve_and_apply_file(self, prep: dict) -> dict:
        if not self.auto.get("write"):
            verdict = self.request_approval({
                "kind": "write",
                "title": ("Create" if prep["new_file"] else "Modify") + f" {prep['rel']}",
                "detail": prep["diff"] or "(no changes)",
            })
            if verdict == "deny":
                return {"ok": False, "output": f"User denied the change to {prep['rel']}. "
                                               "Ask what they want instead or adjust."}
            if verdict == "always":
                self.auto["write"] = True

        res = tools.apply_file_change(prep)

        if res["ok"]:
            diag = lsp.check(prep["path"])
            if diag:
                res["output"] = (res["output"] or "written") + f"\n\nLSP diagnostics:\n{diag}"

            if self.on_file_change:
                try:
                    content = Path(prep["path"]).read_text(encoding="utf-8", errors="replace")
                    self.on_file_change(prep["path"], content)
                except OSError:
                    pass

        return res

    def _approve_and_run(self, command: str) -> dict:
        if not self.auto.get("run"):
            verdict = self.request_approval({
                "kind": "run",
                "title": "Run command",
                "detail": command,
            })
            if verdict == "deny":
                return {"ok": False, "output": "User denied running this command."}
            if verdict == "always":
                self.auto["run"] = True
        return tools.execute_command(self.root, command)

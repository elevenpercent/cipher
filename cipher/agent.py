"""The agent loop: stream model output, parse tool tags, gate mutations
behind approval callbacks, feed results back, repeat until <done>.

The loop is UI-agnostic. The TUI supplies callbacks:
    on_text(delta)                    streamed assistant prose
    on_tool(name, summary)            a tool is about to run
    on_result(name, ok, output)       tool finished
    on_status(msg)                    fallbacks / notices
    request_approval(req) -> str      "allow" | "always" | "deny"
        req = {"kind": "write"|"run", "title": str, "detail": str}
"""

import re
import sys

from . import tools
from .client import ChatClient, ChatError

MAX_TURNS = 30

TAG_NAMES = ["read", "write", "edit", "ls", "glob", "grep", "tree",
             "run", "git", "web-fetch", "web-search", "done"]

TAG_RX = re.compile(
    r"<(" + "|".join(TAG_NAMES) + r")>(.*?)</\1>",
    re.DOTALL,
)

# Model said "I'll create..." instead of acting — force a retry.
INTENT_RX = re.compile(
    r"\b(I'?ll|I will|I'?m going to|Let me|going to (?:create|write|add|update|fix|run|edit)|"
    r"Here'?s the|Here is the|I'?ve (?:created|written|added|updated|made|fixed))\b",
    re.IGNORECASE,
)

SHELL_NAME = "PowerShell" if sys.platform == "win32" else "sh"

SYSTEM_PROMPT = f"""You are Cipher, an autonomous coding agent working inside a project directory.
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
<done>summary of what was done</done>  finish the task

RULES:
1. ACT, don't narrate. Never say "I'll create the file" — emit <write> instead. Never describe code in prose — put it in a tag.
2. Look before you touch. <read> a file before you <edit> it. Use <tree> or <grep> to orient in an unfamiliar codebase.
3. Prefer <edit> for changing existing files; <write> only for new files or full rewrites.
4. In <edit>, the old text must match the file EXACTLY, character for character, including indentation.
5. Verify your work: after writing code, <run> it or run the tests when it is cheap to do so.
6. Every response must contain at least one tool tag, or <done> if the task is finished. Plain text alone is only allowed when answering a pure question that needs no action.
7. For real-world factual documents (licenses, legal texts, specs), fetch them with <web-fetch> or <web-search> — never reproduce them from memory.
8. If a tool fails, read the error and correct course. Do not repeat the identical call.
9. Keep prose minimal: one short line before a tag describing the step is plenty.
10. Plan file structure sensibly: real projects get a proper layout (src dir, tests, README) — not one giant file, unless the task is trivially small.
"""


def parse_tags(text: str) -> list[dict]:
    """Extract tool calls in document order, deduplicated."""
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
    """Prose with tool tags removed, for display."""
    return TAG_RX.sub("", text).strip()


class Agent:
    def __init__(self, project_root: str, client: ChatClient, auto_approve: dict,
                 on_text, on_tool, on_result, on_status, request_approval):
        self.root = project_root
        self.client = client
        self.auto = dict(auto_approve)
        self.on_text = on_text
        self.on_tool = on_tool
        self.on_result = on_result
        self.on_status = on_status
        self.request_approval = request_approval
        self.cancelled = False
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def cancel(self):
        self.cancelled = True

    # ── main loop ─────────────────────────────────────────────────────

    def run_task(self, user_text: str) -> str:
        """Run one user request to completion. Returns the final summary."""
        self.cancelled = False
        self.messages.append({"role": "user", "content": user_text})
        nudges = 0

        for _ in range(MAX_TURNS):
            if self.cancelled:
                return "(cancelled)"
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
                # No tags at all: either a plain answer or a hallucination.
                if INTENT_RX.search(response[:600]) and nudges < 2:
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

    # ── helpers ───────────────────────────────────────────────────────

    def _stream_response(self) -> str:
        parts = []
        visible_upto = 0
        for delta in self.client.stream(
                self.messages,
                on_fallback=lambda old, new: self.on_status(
                    f"{old} unavailable — trying {new}")):
            if self.cancelled:
                break
            parts.append(delta)
            # Stream only prose to the UI; hold back once a tag opens.
            text = "".join(parts)
            tag_at = text.find("<", visible_upto)
            safe_upto = tag_at if tag_at != -1 else len(text)
            if safe_upto > visible_upto:
                self.on_text(text[visible_upto:safe_upto])
                visible_upto = safe_upto
        return "".join(parts)

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
        return tools.apply_file_change(prep)

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

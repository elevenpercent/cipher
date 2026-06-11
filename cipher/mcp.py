"""MCP (Model Context Protocol) client — stdio transport.

Reads server configs from ~/.cipher/mcp.json and/or the project's .mcp.json.
Starts each server as a subprocess, negotiates the MCP handshake, discovers
available tools, and exposes them to the agent via <mcp> tags.

Config format (same as Claude Desktop):
  {
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "env": {}
      }
    }
  }

Agent tool tag:
  <mcp>server_name/tool_name
  {"arg1": "value1"}
  </mcp>
"""

import json
import os
import subprocess
import threading
from pathlib import Path


# ── low-level server handle ───────────────────────────────────────────

class MCPServer:
    def __init__(self, name: str, command: str, args: list, env: dict | None):
        self.name = name
        self._cmd = [command] + (args or [])
        self._env = env
        self._proc: subprocess.Popen | None = None
        self._id = 0
        self._lock = threading.Lock()
        self.tools: list[dict] = []   # populated after start()

    def start(self) -> None:
        merged_env = {**os.environ, **(self._env or {})}
        self._proc = subprocess.Popen(
            self._cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=merged_env,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._initialize()
        self.tools = self._list_tools()

    def stop(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
            except OSError:
                pass
            self._proc = None

    def call(self, tool_name: str, arguments: dict) -> str:
        resp = self._request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        result = resp.get("result") or {}
        content = result.get("content", [])
        parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        if parts:
            return "\n".join(parts)
        if result.get("isError"):
            return f"MCP error: {result}"
        return json.dumps(result)

    # ── private ───────────────────────────────────────────────────────

    def _initialize(self) -> None:
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "cipher", "version": "1.0.0"},
            "capabilities": {},
        })
        self._notify("notifications/initialized")

    def _list_tools(self) -> list[dict]:
        resp = self._request("tools/list")
        return (resp.get("result") or {}).get("tools", [])

    def _request(self, method: str, params: dict | None = None) -> dict:
        with self._lock:
            self._id += 1
            msg: dict = {"jsonrpc": "2.0", "id": self._id, "method": method}
            if params is not None:
                msg["params"] = params
            self._write(msg)
            # Read until we get the matching response id.
            for _ in range(64):
                line = self._proc.stdout.readline()
                if not line:
                    return {}
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("id") == self._id:
                    return obj
            return {}

    def _notify(self, method: str, params: dict | None = None) -> None:
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    def _write(self, obj: dict) -> None:
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()


# ── manager: owns all servers, exposes to agent ───────────────────────

class MCPManager:
    def __init__(self, project_root: str):
        self._servers: dict[str, MCPServer] = {}
        self._load(_user_config())
        self._load(Path(project_root) / ".mcp.json")

    def _load(self, path) -> None:
        try:
            cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        for name, spec in cfg.get("mcpServers", {}).items():
            if name in self._servers:
                continue
            server = MCPServer(
                name,
                spec.get("command", ""),
                spec.get("args", []),
                spec.get("env"),
            )
            try:
                server.start()
                self._servers[name] = server
            except Exception:
                pass  # server unavailable — skip silently

    @property
    def active(self) -> bool:
        return bool(self._servers)

    def all_tools(self) -> list[dict]:
        """Flat list of {server, name, description, inputSchema}."""
        result = []
        for sname, server in self._servers.items():
            for t in server.tools:
                result.append({
                    "server": sname,
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "inputSchema": t.get("inputSchema", {}),
                })
        return result

    def prompt_section(self) -> str:
        """System-prompt block describing available MCP tools, or ''."""
        tools = self.all_tools()
        if not tools:
            return ""
        lines = ["\nMCP TOOLS (external servers — call via <mcp> tag):"]
        for t in tools:
            tag = f"{t['server']}/{t['name']}"
            lines.append(f"  {tag}  —  {t['description']}")
        lines.append(
            '\nTo call an MCP tool:\n'
            '  <mcp>server_name/tool_name\n'
            '  {"arg": "value"}\n'
            '  </mcp>\n'
            'Pass only the arguments the tool requires (see inputSchema).'
        )
        return "\n".join(lines)

    def call(self, tag_body: str) -> dict:
        """Parse a <mcp> tag body and dispatch to the right server."""
        lines = tag_body.strip().splitlines()
        if not lines:
            return {"ok": False, "output": "empty <mcp> tag"}
        header = lines[0].strip()
        if "/" not in header:
            return {"ok": False, "output": f"<mcp> first line must be server/tool, got: {header!r}"}
        server_name, tool_name = header.split("/", 1)
        server = self._servers.get(server_name)
        if server is None:
            available = ", ".join(self._servers) or "none"
            return {"ok": False, "output": f"MCP server {server_name!r} not connected. Available: {available}"}
        args_text = "\n".join(lines[1:]).strip()
        try:
            arguments = json.loads(args_text) if args_text else {}
        except json.JSONDecodeError as e:
            return {"ok": False, "output": f"invalid JSON arguments for MCP call: {e}\n{args_text}"}
        try:
            output = server.call(tool_name, arguments)
            return {"ok": True, "output": output}
        except Exception as e:
            return {"ok": False, "output": f"MCP call failed: {e}"}

    def stop_all(self) -> None:
        for s in self._servers.values():
            s.stop()
        self._servers.clear()


def _user_config() -> Path:
    from .config import CIPHER_HOME
    return CIPHER_HOME / "mcp.json"

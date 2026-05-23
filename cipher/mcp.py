import os
import json
import time
import subprocess
import sys
import threading
import queue
from pathlib import Path

MCP_SERVERS_DIR = Path.home() / ".cipher" / "mcp-servers"


class MCPClient:
    def __init__(self, name, command, args=None, env=None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.process = None
        self._queue = queue.Queue()
        self._running = False
        self._buffer = b""
        self.capabilities = {}
        self.tools = []

    def start(self):
        try:
            merged_env = os.environ.copy()
            merged_env.update(self.env)
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=merged_env,
            )
            self._running = True
            threading.Thread(target=self._reader, daemon=True).start()
            self._send_request("initialize", {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "cipher", "version": "0.4.0"},
            })
            self._send_notification("notifications/initialized", {})
            self._discover_tools()
            return True
        except Exception as e:
            return False

    def _reader(self):
        while self._running:
            try:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break
                self._buffer += chunk
                while b"\n" in self._buffer:
                    line, _, self._buffer = self._buffer.partition(b"\n")
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._queue.put(json.loads(line.decode()))
                    except json.JSONDecodeError:
                        pass
            except Exception:
                break

    def _send(self, obj):
        if not self.process or not self.process.stdin:
            return
        line = json.dumps(obj) + "\n"
        self.process.stdin.write(line.encode())
        self.process.stdin.flush()

    def _send_request(self, method, params):
        self._send({"jsonrpc": "2.0", "id": id(self), "method": method, "params": params})

    def _send_notification(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _discover_tools(self):
        self._send_request("tools/list", {})
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                msg = self._queue.get(timeout=0.5)
                if "result" in msg and "tools" in msg["result"]:
                    self.tools = msg["result"]["tools"]
                    return
            except queue.Empty:
                break

    def call_tool(self, name, arguments=None):
        self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                msg = self._queue.get(timeout=0.5)
                if "result" in msg:
                    content = msg["result"].get("content", [])
                    text_parts = []
                    for part in content:
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                    return {"result": "\n".join(text_parts), "success": True}
                if "error" in msg:
                    return {"result": f"MCP error: {msg['error'].get('message', 'unknown')}", "success": False}
            except queue.Empty:
                break
        return {"result": "MCP tool call timed out", "success": False}

    def stop(self):
        self._running = False
        if self.process:
            try:
                self._send_notification("exit", {})
                self.process.terminate()
                self.process.wait(5)
            except Exception:
                self.process.kill()
            self.process = None


class MCPServerManager:
    def __init__(self):
        self.servers = {}

    def load_config(self, config):
        servers = config.get("mcp_servers", {})
        for name, cfg in servers.items():
            client = MCPClient(
                name=name,
                command=cfg.get("command", ""),
                args=cfg.get("args", []),
                env=cfg.get("env", {}),
            )
            if client.start():
                self.servers[name] = client

    def discover(self):
        MCP_SERVERS_DIR.mkdir(exist_ok=True)
        count = 0
        for f in MCP_SERVERS_DIR.glob("*.json"):
            try:
                cfg = json.loads(f.read_text(encoding="utf-8"))
                name = cfg.get("name", f.stem)
                client = MCPClient(
                    name=name,
                    command=cfg.get("command", ""),
                    args=cfg.get("args", []),
                    env=cfg.get("env", {}),
                )
                if client.start():
                    self.servers[name] = client
                    count += 1
            except Exception:
                pass
        return count

    def get_tools(self):
        all_tools = []
        for name, client in self.servers.items():
            for tool in client.tools:
                tool["_mcp_server"] = name
                all_tools.append(tool)
        return all_tools

    def call_tool(self, server_name, tool_name, arguments=None):
        client = self.servers.get(server_name)
        if not client:
            return {"result": f"MCP server '{server_name}' not found", "success": False}
        return client.call_tool(tool_name, arguments)

    def shutdown_all(self):
        for client in self.servers.values():
            try:
                client.stop()
            except Exception:
                pass
        self.servers.clear()

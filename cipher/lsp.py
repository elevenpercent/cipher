# Derived from opencode (MIT) - Copyright (c) 2025 opencode.ai
import os
import json
import subprocess
import shutil
import threading
import queue
from pathlib import Path


LSP_SERVERS = {
    ".py": {"command": "pyright-langserver", "args": ["--stdio"], "name": "Pyright"},
    ".js": {"command": "typescript-language-server", "args": ["--stdio"], "name": "TypeScript"},
    ".ts": {"command": "typescript-language-server", "args": ["--stdio"], "name": "TypeScript"},
    ".jsx": {"command": "typescript-language-server", "args": ["--stdio"], "name": "TypeScript"},
    ".tsx": {"command": "typescript-language-server", "args": ["--stdio"], "name": "TypeScript"},
    ".go": {"command": "gopls", "args": [], "name": "gopls"},
    ".rs": {"command": "rust-analyzer", "args": [], "name": "rust-analyzer"},
    ".c": {"command": "clangd", "args": [], "name": "clangd"},
    ".cpp": {"command": "clangd", "args": [], "name": "clangd"},
    ".h": {"command": "clangd", "args": [], "name": "clangd"},
    ".hpp": {"command": "clangd", "args": [], "name": "clangd"},
}


class Diagnostic:
    def __init__(self, filepath, line, column, message, severity="warning"):
        self.filepath = filepath
        self.line = line
        self.column = column
        self.message = message
        self.severity = severity

    def __str__(self):
        sev = {"error": "E", "warning": "W", "info": "I"}.get(self.severity, "?")
        return f"{self.filepath}:{self.line}:{self.column}: {sev} {self.message}"


class LSPClient:
    def __init__(self, root_uri, server_cmd, server_args):
        self.root_uri = root_uri
        self.server_cmd = server_cmd
        self.server_args = server_args
        self.process = None
        self.request_id = 0
        self.capabilities = {}
        self._queue = queue.Queue()
        self._running = False
        self._buffer = b""

    def start(self):
        if not shutil.which(self.server_cmd):
            return False
        try:
            self.process = subprocess.Popen(
                [self.server_cmd] + self.server_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._running = True
            threading.Thread(target=self._reader, daemon=True).start()
            self._send_request("initialize", {
                "processId": os.getpid(),
                "rootUri": self.root_uri,
                "capabilities": {},
            })
            self._send_notification("initialized", {})
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
                while b"\r\n\r\n" in self._buffer:
                    header, _, rest = self._buffer.partition(b"\r\n\r\n")
                    if b"Content-Length:" in header:
                        length = int(header.split(b"Content-Length: ")[1].split(b"\r\n")[0])
                        if len(rest) >= length:
                            body = rest[:length]
                            self._buffer = rest[length:]
                            self._queue.put(json.loads(body.decode()))
                        else:
                            break
                    else:
                        self._buffer = b""
            except Exception:
                break

    def _send(self, obj):
        if not self.process or not self.process.stdin:
            return
        body = json.dumps(obj).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        self.process.stdin.write(header + body)
        self.process.stdin.flush()

    def _send_request(self, method, params):
        self.request_id += 1
        self._send({"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params})
        return self.request_id

    def _send_notification(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def open_document(self, filepath, text):
        uri = Path(filepath).as_uri()
        self._send_notification("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": self._lang_id(filepath), "version": 1, "text": text},
        })

    def close_document(self, filepath):
        uri = Path(filepath).as_uri()
        self._send_notification("textDocument/didClose", {
            "textDocument": {"uri": uri},
        })

    def change_document(self, filepath, text, version=2):
        uri = Path(filepath).as_uri()
        self._send_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": version},
            "contentChanges": [{"text": text}],
        })

    def get_diagnostics(self, filepath, timeout=5):
        uri = Path(filepath).as_uri()
        self._send_request("textDocument/publishDiagnostics", {
            "uri": uri,
        })
        diagnostics = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = self._queue.get(timeout=0.5)
                if msg.get("method") == "textDocument/publishDiagnostics":
                    for d in msg.get("params", {}).get("diagnostics", []):
                        diag = Diagnostic(
                            filepath=filepath,
                            line=d.get("range", {}).get("start", {}).get("line", 0) + 1,
                            column=d.get("range", {}).get("start", {}).get("character", 0) + 1,
                            message=d.get("message", ""),
                            severity={1: "error", 2: "warning", 3: "info", 4: "info"}.get(d.get("severity"), "info"),
                        )
                        diagnostics.append(diag)
                    return diagnostics
            except queue.Empty:
                break
        return diagnostics

    def complete(self, filepath, line, col):
        uri = Path(filepath).as_uri()
        self._send_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": col - 1},
        })
        return []

    def _lang_id(self, filepath):
        mapping = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "javascriptreact", ".tsx": "typescriptreact",
            ".go": "go", ".rs": "rust", ".c": "c", ".cpp": "cpp",
        }
        return mapping.get(Path(filepath).suffix, "plaintext")

    def stop(self):
        self._running = False
        if self.process:
            self._send_notification("exit", {})
            self.process.terminate()
            self.process.wait(5)
            self.process = None


class LSPManager:
    def __init__(self):
        self.clients = {}

    def get_client(self, filepath, root):
        ext = Path(filepath).suffix
        config = LSP_SERVERS.get(ext)
        if not config:
            return None
        root_uri = Path(root).as_uri()
        cache_key = f"{config['command']}:{root}"
        if cache_key not in self.clients:
            client = LSPClient(root_uri, config["command"], config["args"])
            if client.start():
                self.clients[cache_key] = client
            else:
                return None
        return self.clients[cache_key]

    def open_file(self, filepath, root, text):
        client = self.get_client(filepath, root)
        if client:
            client.open_document(filepath, text)

    def close_file(self, filepath, root):
        ext = Path(filepath).suffix
        config = LSP_SERVERS.get(ext)
        if not config:
            return
        root_uri = Path(root).as_uri()
        cache_key = f"{config['command']}:{root}"
        client = self.clients.get(cache_key)
        if client:
            client.close_document(filepath)

    def get_diagnostics(self, filepath, root):
        client = self.get_client(filepath, root)
        if client:
            return client.get_diagnostics(filepath)
        return []

    def shutdown_all(self):
        for client in self.clients.values():
            try:
                client.stop()
            except Exception:
                pass
        self.clients.clear()


import time

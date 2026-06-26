"""Minimal streaming chat client for OpenAI-compatible endpoints."""

import json
import urllib.error
import urllib.request


class ChatError(Exception):
    pass


class ChatClient:
    def __init__(self, base_url: str, model: str, api_key: str = "",
                 is_proxy: bool = False, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.is_proxy = is_proxy
        self.timeout = timeout

    def stream(self, messages: list[dict], temperature: float = 0.15,
               on_fallback=None, on_usage=None):
        yield from self._stream_one(self.model, messages, temperature, on_usage)

    def complete(self, messages: list[dict], temperature: float = 0.15) -> str:
        return "".join(self.stream(messages, temperature))

    @property
    def active_model(self) -> str:
        return self.model

    def _stream_one(self, model: str, messages: list[dict], temperature: float,
                    on_usage=None):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            try:
                detail = json.loads(body).get("error", body)
                if isinstance(detail, dict):
                    detail = detail.get("message", body)
            except (json.JSONDecodeError, AttributeError):
                detail = body
            raise ChatError(f"HTTP {e.code} — {detail}") from None
        except urllib.error.URLError as e:
            raise ChatError(f"connection failed — {e.reason}") from None

        emitted = False
        with resp:
            buf = b""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text.startswith("data: "):
                        continue
                    data = text[6:]
                    if data == "[DONE]":
                        return
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if parsed.get("error"):
                        err = parsed["error"]
                        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                        if not emitted:
                            raise ChatError(msg)
                        return
                    usage = parsed.get("usage")
                    if usage and on_usage:
                        on_usage(
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                        )
                    delta = (parsed.get("choices") or [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        emitted = True
                        yield content
        if not emitted:
            raise ChatError("empty response")

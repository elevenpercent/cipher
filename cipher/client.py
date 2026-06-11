"""Minimal streaming chat client for OpenAI-compatible endpoints.

Stdlib only — no SDK dependency. Yields text deltas as they arrive.
For the Cipher Proxy provider it walks the fallback chain when a
model is rate limited or down.
"""

import json
import urllib.error
import urllib.request

from .config import PROXY_FALLBACK


class ChatError(Exception):
    """Raised when the endpoint returns an error for all attempted models."""


class ChatClient:
    def __init__(self, base_url: str, model: str, api_key: str = "",
                 is_proxy: bool = False, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.is_proxy = is_proxy
        self.timeout = timeout

    # ── public ────────────────────────────────────────────────────────

    def stream(self, messages: list[dict], temperature: float = 0.15,
               on_fallback=None):
        """Yield content deltas. on_fallback(old, new) is called when the
        proxy chain switches models."""
        models = self._model_chain()
        last_err = None
        for i, model in enumerate(models):
            try:
                yield from self._stream_one(model, messages, temperature)
                return
            except ChatError as e:
                last_err = e
                if i + 1 < len(models) and on_fallback:
                    on_fallback(model, models[i + 1])
        raise ChatError(str(last_err) if last_err else "All models failed")

    def complete(self, messages: list[dict], temperature: float = 0.15) -> str:
        return "".join(self.stream(messages, temperature))

    # ── internals ─────────────────────────────────────────────────────

    def _model_chain(self) -> list[str]:
        if not self.is_proxy:
            return [self.model]
        chain = [self.model] + [m for m in PROXY_FALLBACK if m != self.model]
        return chain

    def _stream_one(self, model: str, messages: list[dict], temperature: float):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
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
            raise ChatError(f"{model}: HTTP {e.code} — {detail}") from None
        except urllib.error.URLError as e:
            raise ChatError(f"{model}: connection failed — {e.reason}") from None

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
                            raise ChatError(f"{model}: {msg}")
                        return
                    delta = (parsed.get("choices") or [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        emitted = True
                        yield content
        if not emitted:
            raise ChatError(f"{model}: empty response")

# Derived from opencode (MIT) - Copyright (c) 2025 opencode.ai
import os
import json
import time
import uuid
import subprocess
import urllib.request
from typing import Generator
import os
os.environ["LITELLM_LOG"] = "ERROR"
import litellm
import logging
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("litellm").setLevel(logging.ERROR)


def detect_gpu():
    """Returns estimated VRAM in GB or 0 if no GPU detected."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            if lines:
                return max(int(lines[0]) // 1024, 0)
    except Exception:
        pass
    return 0


def get_local_ollama_models(gpu_vram_gb=0):
    """Returns Ollama models appropriate for the available GPU VRAM."""
    all_models = [
        {"id": "ollama/qwen3:4b", "name": "Qwen3 4B (fastest)", "free": True, "min_vram": 2},
        {"id": "ollama/qwen3:8b", "name": "Qwen3 8B", "free": True, "min_vram": 4},
        {"id": "ollama/mistral:7b", "name": "Mistral 7B", "free": True, "min_vram": 4},
        {"id": "ollama/llama3.1:8b", "name": "Llama 3.1 8B", "free": True, "min_vram": 4},
        {"id": "ollama/qwen3:14b", "name": "Qwen3 14B (recommended)", "free": True, "min_vram": 8},
        {"id": "ollama/qwen2.5-coder:14b", "name": "Qwen2.5 Coder 14B", "free": True, "min_vram": 8},
        {"id": "ollama/deepseek-r1:14b", "name": "DeepSeek R1 14B", "free": True, "min_vram": 8},
        {"id": "ollama/gemma3:12b", "name": "Gemma 3 12B", "free": True, "min_vram": 8},
        {"id": "ollama/phi4:14b", "name": "Phi-4 14B (Microsoft)", "free": True, "min_vram": 8},
        {"id": "ollama/llama3.3:70b", "name": "Llama 3.3 70B", "free": True, "min_vram": 32},
    ]
    if gpu_vram_gb <= 0:
        return []
    return [m for m in all_models if m["min_vram"] <= gpu_vram_gb]

PROVIDERS = {
    "ollama": {
        "name": "Ollama",
        "desc": "Local models, 100% free, needs Ollama installed",
        "type": "local",
        "install": "ollama.com",
        "models": [
            {"id": "ollama/qwen3:14b", "name": "Qwen3 14B (recommended)", "free": True},
            {"id": "ollama/qwen3:8b", "name": "Qwen3 8B", "free": True},
            {"id": "ollama/qwen3:4b", "name": "Qwen3 4B (fastest)", "free": True},
            {"id": "ollama/qwen2.5-coder:14b", "name": "Qwen2.5 Coder 14B", "free": True},
            {"id": "ollama/llama3.3:70b", "name": "Llama 3.3 70B", "free": True},
            {"id": "ollama/llama3.1:8b", "name": "Llama 3.1 8B", "free": True},
            {"id": "ollama/deepseek-r1:14b", "name": "DeepSeek R1 14B", "free": True},
            {"id": "ollama/mistral:7b", "name": "Mistral 7B", "free": True},
            {"id": "ollama/gemma3:12b", "name": "Gemma 3 12B", "free": True},
            {"id": "ollama/phi4:14b", "name": "Phi-4 14B (Microsoft)", "free": True},
        ],
    },
    "groq": {
        "name": "Groq",
        "desc": "Fastest inference, generous free tier",
        "type": "cloud-free",
        "env_key": "GROQ_API_KEY",
        "signup_url": "console.groq.com",
        "free_tokens": "Generous free tier",
        "models": [
            {"id": "groq/llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "free": True},
            {"id": "groq/llama-3.1-8b-instant", "name": "Llama 3.1 8B (fast)", "free": True},
            {"id": "groq/mixtral-8x7b-32768", "name": "Mixtral 8x7B", "free": True},
            {"id": "groq/gemma2-9b-it", "name": "Gemma 2 9B", "free": True},
            {"id": "groq/deepseek-r1-distill-llama-70b", "name": "DeepSeek R1 Distill", "free": True},
        ],
    },
    "gemini": {
        "name": "Google Gemini",
        "desc": "Free tier, strong reasoning",
        "type": "cloud-free",
        "env_key": "GOOGLE_API_KEY",
        "signup_url": "aistudio.google.com",
        "free_tokens": "60 RPM free tier",
        "models": [
            {"id": "gemini/gemini-2.0-flash", "name": "Gemini 2.0 Flash (free)", "free": True},
            {"id": "gemini/gemini-2.0-flash-lite", "name": "Gemini 2.0 Flash Lite (free)", "free": True},
            {"id": "gemini/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "free": False},
            {"id": "gemini/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "free": False},
        ],
    },
    "openrouter": {
        "name": "OpenRouter",
        "desc": "Access 100+ models, free tiers available",
        "type": "cloud",
        "env_key": "OPENROUTER_API_KEY",
        "signup_url": "openrouter.ai",
        "models": [
            {"id": "openrouter/google/gemini-2.0-flash", "name": "Gemini 2.0 Flash (free)", "free": True},
            {"id": "openrouter/meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "free": False},
            {"id": "openrouter/anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "free": False},
            {"id": "openrouter/openai/gpt-4o", "name": "GPT-4o", "free": False},
            {"id": "openrouter/deepseek/deepseek-chat", "name": "DeepSeek Chat", "free": False},
            {"id": "openrouter/qwen/qwen3-235b-a22b", "name": "Qwen3 235B", "free": False},
            {"id": "openrouter/mistralai/mistral-large", "name": "Mistral Large", "free": False},
        ],
    },
    "lmstudio": {
        "name": "LM Studio",
        "desc": "Local OpenAI-compatible, any model",
        "type": "local",
        "install": "lmstudio.ai",
        "models": [
            {"id": "lmstudio/qwen3-14b", "name": "Qwen3 14B (via LM Studio)", "free": True},
            {"id": "lmstudio/qwen2.5-coder-32b", "name": "Qwen2.5 Coder 32B", "free": True},
            {"id": "lmstudio/llama-3.3-70b", "name": "Llama 3.3 70B", "free": True},
            {"id": "lmstudio/deepseek-r1-32b", "name": "DeepSeek R1 32B", "free": True},
        ],
    },
    "openai": {
        "name": "OpenAI",
        "desc": "GPT models, needs API key",
        "type": "cloud",
        "env_key": "OPENAI_API_KEY",
        "signup_url": "platform.openai.com",
        "models": [
            {"id": "openai/gpt-4o", "name": "GPT-4o", "free": False},
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini (cheap)", "free": False},
            {"id": "openai/gpt-4.1", "name": "GPT-4.1", "free": False},
            {"id": "openai/gpt-4.1-mini", "name": "GPT-4.1 Mini", "free": False},
            {"id": "openai/o1", "name": "o1 (reasoning)", "free": False},
            {"id": "openai/o3-mini", "name": "o3 Mini", "free": False},
            {"id": "openai/o4-mini", "name": "o4 Mini", "free": False},
        ],
    },
    "deepseek": {
        "name": "DeepSeek",
        "desc": "Strong reasoning, cheap API",
        "type": "cloud",
        "env_key": "DEEPSEEK_API_KEY",
        "signup_url": "platform.deepseek.com",
        "models": [
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3 (chat)", "free": False},
            {"id": "deepseek/deepseek-reasoner", "name": "DeepSeek R1 (reasoning)", "free": False},
        ],
    },
    "anthropic": {
        "name": "Anthropic",
        "desc": "Claude models, needs API key",
        "type": "cloud",
        "env_key": "ANTHROPIC_API_KEY",
        "signup_url": "console.anthropic.com",
        "models": [
            {"id": "anthropic/claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "free": False},
            {"id": "anthropic/claude-opus-4-20250514", "name": "Claude Opus 4", "free": False},
            {"id": "anthropic/claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku (cheap)", "free": False},
            {"id": "anthropic/claude-3-7-sonnet-latest", "name": "Claude 3.7 Sonnet", "free": False},
        ],
    },
    "mistral": {
        "name": "Mistral",
        "desc": "Open-weight models, needs API key",
        "type": "cloud",
        "env_key": "MISTRAL_API_KEY",
        "signup_url": "console.mistral.ai",
        "models": [
            {"id": "mistral/mistral-large-latest", "name": "Mistral Large", "free": False},
            {"id": "mistral/mistral-small-latest", "name": "Mistral Small", "free": False},
            {"id": "mistral/codestral-latest", "name": "Codestral (coding)", "free": False},
            {"id": "mistral/ministral-8b-latest", "name": "Ministral 8B (cheap)", "free": False},
        ],
    },
    "cohere": {
        "name": "Cohere",
        "desc": "Command models, free tier available",
        "type": "cloud-free",
        "env_key": "COHERE_API_KEY",
        "signup_url": "dashboard.cohere.com",
        "free_tokens": "Free tier available",
        "models": [
            {"id": "cohere/command-r-plus", "name": "Command R+", "free": False},
            {"id": "cohere/command-r", "name": "Command R (cheap)", "free": False},
            {"id": "cohere/command", "name": "Command", "free": False},
        ],
    },
    "perplexity": {
        "name": "Perplexity",
        "desc": "Web-connected AI, free tier",
        "type": "cloud-free",
        "env_key": "PERPLEXITY_API_KEY",
        "signup_url": "perplexity.ai",
        "free_tokens": "Free tier available",
        "models": [
            {"id": "perplexity/sonar", "name": "Sonar (web search)", "free": False},
            {"id": "perplexity/sonar-pro", "name": "Sonar Pro", "free": False},
            {"id": "perplexity/sonar-reasoning", "name": "Sonar Reasoning", "free": False},
        ],
    },
    "xai": {
        "name": "xAI (Grok)",
        "desc": "Grok models, needs API key",
        "type": "cloud",
        "env_key": "XAI_API_KEY",
        "signup_url": "console.x.ai",
        "models": [
            {"id": "xai/grok-3", "name": "Grok 3", "free": False},
            {"id": "xai/grok-3-mini", "name": "Grok 3 Mini", "free": False},
        ],
    },
    "together": {
        "name": "Together AI",
        "desc": "100+ open models, needs API key",
        "type": "cloud",
        "env_key": "TOGETHER_API_KEY",
        "signup_url": "together.ai",
        "models": [
            {"id": "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo", "name": "Llama 3.3 70B", "free": False},
            {"id": "together_ai/deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3", "free": False},
            {"id": "together_ai/Qwen/Qwen2.5-72B-Instruct-Turbo", "name": "Qwen 2.5 72B", "free": False},
            {"id": "together_ai/meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo", "name": "Llama 3.1 405B", "free": False},
        ],
    },
    "cipher-proxy": {
        "name": "Cipher Proxy",
        "desc": "Free models via proxy — no API key needed. Powered by Groq + Gemini.",
        "type": "cloud-free",
        "proxy": True,
        "models": [
            {"id": "llama-3.3-70b", "name": "Llama 3.3 70B (Groq, fast)", "free": True},
            {"id": "llama-3.1-8b", "name": "Llama 3.1 8B (Groq)", "free": True},
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash (Google)", "free": True},
        ],
    },
    "fireworks": {
        "name": "Fireworks AI",
        "desc": "Fast inference, free tier",
        "type": "cloud-free",
        "env_key": "FIREWORKS_API_KEY",
        "signup_url": "fireworks.ai",
        "free_tokens": "Free tier available",
        "models": [
            {"id": "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct", "name": "Llama 3.3 70B", "free": True},
            {"id": "fireworks_ai/accounts/fireworks/models/qwen2p5-coder-32b-instruct", "name": "Qwen2.5 Coder 32B", "free": True},
            {"id": "fireworks_ai/accounts/fireworks/models/deepseek-r1", "name": "DeepSeek R1", "free": False},
        ],
    },
}


class AIProvider:
    def __init__(self, provider_id: str = None, model_id: str = None, api_key: str = None, proxy_url: str = None):
        self.provider_id = provider_id or os.getenv("CIPHER_PROVIDER", "ollama")
        self.model_id = model_id or os.getenv("CIPHER_MODEL", "ollama/qwen3:14b")
        if not self.model_id:
            provider_config = PROVIDERS.get(self.provider_id, {})
            models = provider_config.get("models", [])
            self.model_id = models[0]["id"] if models else "llama-3.3-70b"
        self.api_key = api_key
        self.proxy_url = proxy_url or os.getenv("CIPHER_PROXY_URL", "http://localhost:8080")
        self._init_client()

    def _init_client(self):
        provider_config = PROVIDERS.get(self.provider_id, {})
        if provider_config.get("proxy"):
            self.api_key = ""
            return
        env_key = provider_config.get("env_key")
        if env_key:
            env_val = os.getenv(env_key, "")
            if env_val:
                self.api_key = env_val
        else:
            self.api_key = ""

        if self.api_key:
            litellm.api_key = self.api_key

    def chat(self, messages: list, stream: bool = True, system_prompt: str = None):
        provider_config = PROVIDERS.get(self.provider_id, {})
        if provider_config.get("proxy"):
            return self._proxy_chat(messages, stream)

        formatted = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})
        formatted.extend(messages)

        response = litellm.completion(
            model=self.model_id,
            messages=formatted,
            stream=stream,
            temperature=0.15,
        )

        if not stream:
            return response.choices[0].message.content

        return self._stream_response(response)

    def _stream_response(self, response):
        full_text = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                full_text += delta
                yield {"content": delta, "full": full_text}

    def _proxy_chat(self, messages, stream=True):
        if not stream:
            return self._proxy_chat_sync(messages)
        return self._proxy_chat_stream(messages)

    def _proxy_chat_sync(self, messages):
        url = f"{self.proxy_url.rstrip('/')}/v1/chat/completions"
        payload = json.dumps({
            "model": self.model_id,
            "messages": messages,
            "stream": False,
            "temperature": 0.15,
        }).encode()
        req = urllib.request.Request(url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Proxy error: {e}"

    def _proxy_chat_stream(self, messages):
        url = f"{self.proxy_url.rstrip('/')}/v1/chat/completions"
        payload = json.dumps({
            "model": self.model_id,
            "messages": messages,
            "stream": True,
            "temperature": 0.15,
        }).encode()
        req = urllib.request.Request(url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                buffer = ""
                while True:
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buffer += chunk.decode()
                    if buffer.endswith("\n"):
                        for line in buffer.strip().split("\n"):
                            if line.startswith("data: "):
                                data = line[6:].strip()
                                if data == "[DONE]":
                                    return
                                try:
                                    d = json.loads(data)
                                    delta = d.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if delta:
                                        yield {"content": delta, "full": ""}
                                except json.JSONDecodeError:
                                    pass
                        buffer = ""
        except Exception as e:
            yield {"content": f" Proxy error: {e}"}

    @staticmethod
    def get_provider_info(provider_id: str) -> dict:
        return PROVIDERS.get(provider_id, {})

    @staticmethod
    def list_providers() -> list:
        return [
            {"id": pid, **info}
            for pid, info in PROVIDERS.items()
        ]

    @staticmethod
    def list_models(provider_id: str = None) -> list:
        if provider_id:
            info = PROVIDERS.get(provider_id, {})
            return info.get("models", [])
        models = []
        for pid, info in PROVIDERS.items():
            for m in info.get("models", []):
                models.append({**m, "provider": pid, "provider_name": info["name"]})
        return models

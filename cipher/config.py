"""Configuration: provider presets and persisted user settings.

Everything lives in ~/.cipher/config.json. All providers speak the
OpenAI chat-completions protocol, so a provider is just a base URL,
an env-var name for its key, and a list of model ids.
"""

import json
import os
from pathlib import Path

CIPHER_HOME = Path.home() / ".cipher"
CONFIG_PATH = CIPHER_HOME / "config.json"
SESSIONS_DIR = CIPHER_HOME / "sessions"

PROXY_URL = "https://proxy-blue-kappa.vercel.app"

# Models the proxy tries in order when the primary is rate limited.
PROXY_FALLBACK = [
    "sambanova-405b",
    "sambanova-70b",
    "deepseek-chat",
    "gemini-2.0-flash",
    "llama-3.3-70b",
]

PROVIDERS = {
    "proxy": {
        "name": "Cipher Proxy (free, no key)",
        "base": PROXY_URL + "/v1",
        "env": None,
        "models": PROXY_FALLBACK,
        "default_model": "sambanova-405b",
    },
    "openai": {
        "name": "OpenAI",
        "base": "https://api.openai.com/v1",
        "env": "OPENAI_API_KEY",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "name": "Anthropic",
        "base": "https://api.anthropic.com/v1",
        "env": "ANTHROPIC_API_KEY",
        "models": ["claude-sonnet-4-5", "claude-haiku-4-5"],
        "default_model": "claude-sonnet-4-5",
    },
    "groq": {
        "name": "Groq",
        "base": "https://api.groq.com/openai/v1",
        "env": "GROQ_API_KEY",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        "default_model": "llama-3.3-70b-versatile",
    },
    "gemini": {
        "name": "Google Gemini",
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env": "GEMINI_API_KEY",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro"],
        "default_model": "gemini-2.0-flash",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base": "https://api.deepseek.com",
        "env": "DEEPSEEK_API_KEY",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
    },
    "sambanova": {
        "name": "SambaNova",
        "base": "https://api.sambanova.ai/v1",
        "env": "SAMBANOVA_API_KEY",
        "models": ["Llama-4-Maverick-17B-128E-Instruct", "Meta-Llama-3.3-70B-Instruct"],
        "default_model": "Llama-4-Maverick-17B-128E-Instruct",
    },
    "openrouter": {
        "name": "OpenRouter",
        "base": "https://openrouter.ai/api/v1",
        "env": "OPENROUTER_API_KEY",
        "models": ["anthropic/claude-sonnet-4.5", "deepseek/deepseek-chat"],
        "default_model": "deepseek/deepseek-chat",
    },
    "ollama": {
        "name": "Ollama (local)",
        "base": "http://localhost:11434/v1",
        "env": None,
        "models": ["qwen2.5-coder:14b", "llama3.1"],
        "default_model": "qwen2.5-coder:14b",
    },
    "custom": {
        "name": "Custom (any OpenAI-compatible URL)",
        "base": "",
        "env": None,
        "models": [],
        "default_model": "",
    },
}

# Cost per 1M tokens (input, output) in USD. 0.0 = free / unknown.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o":                           (2.50,  10.00),
    "gpt-4o-mini":                      (0.15,   0.60),
    "o3-mini":                          (1.10,   4.40),
    # Anthropic
    "claude-opus-4-8":                  (15.00, 75.00),
    "claude-sonnet-4-6":                (3.00,  15.00),
    "claude-sonnet-4-5":                (3.00,  15.00),
    "claude-haiku-4-5":                 (0.80,   4.00),
    # DeepSeek
    "deepseek-chat":                    (0.27,   1.10),
    "deepseek-reasoner":                (0.55,   2.19),
    # Gemini
    "gemini-2.0-flash":                 (0.10,   0.40),
    "gemini-1.5-pro":                   (1.25,   5.00),
    # Proxy / free models
    "sambanova-405b":                   (0.0,    0.0),
    "sambanova-70b":                    (0.0,    0.0),
    "Llama-4-Maverick-17B-128E-Instruct": (0.0, 0.0),
    "Meta-Llama-3.3-70B-Instruct":      (0.0,   0.0),
    "llama-3.3-70b":                    (0.0,   0.0),
    "llama-3.3-70b-versatile":          (0.0,   0.0),
    "llama-3.1-8b-instant":             (0.0,   0.0),
    "cerebras-70b":                     (0.0,   0.0),
    "cerebras-8b":                      (0.0,   0.0),
}


def model_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return total cost in USD for a call, or 0.0 if model is unknown/free."""
    inp, out = MODEL_PRICING.get(model, (0.0, 0.0))
    return (prompt_tokens * inp + completion_tokens * out) / 1_000_000


DEFAULTS = {
    "provider": "proxy",
    "model": "",            # empty -> provider default
    "api_key": "",          # stored key (BYOK); env var wins if set
    "custom_base": "",      # only for provider == custom
    "auto_approve": {       # permission gates
        "read": True,       # read-only tools never prompt
        "write": False,     # file writes/edits prompt with a diff
        "run": False,       # shell/git commands prompt
    },
    "proxy_url": PROXY_URL,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        for k, v in saved.items():
            if k == "auto_approve" and isinstance(v, dict):
                cfg["auto_approve"] = {**DEFAULTS["auto_approve"], **v}
            else:
                cfg[k] = v
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return cfg


def save_config(cfg: dict) -> None:
    CIPHER_HOME.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def resolve_endpoint(cfg: dict) -> tuple[str, str, str]:
    """Return (base_url, model, api_key) for the active provider."""
    pid = cfg.get("provider", "proxy")
    preset = PROVIDERS.get(pid, PROVIDERS["proxy"])

    if pid == "custom":
        base = (cfg.get("custom_base") or "").rstrip("/")
    elif pid == "proxy":
        base = (cfg.get("proxy_url") or PROXY_URL).rstrip("/") + "/v1"
    else:
        base = preset["base"]

    model = cfg.get("model") or preset["default_model"]

    key = cfg.get("api_key", "")
    if preset["env"]:
        key = os.environ.get(preset["env"], "") or key
    return base, model, key

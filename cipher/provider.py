"""Cipher - AI provider manager using LiteLLM"""
import os
import time
from typing import Generator

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
            {"id": "ollama/qwen3:32b", "name": "Qwen3 32B (best)", "free": True},
            {"id": "ollama/qwen2.5-coder:14b", "name": "Qwen2.5 Coder 14B", "free": True},
            {"id": "ollama/qwen2.5-coder:32b", "name": "Qwen2.5 Coder 32B", "free": True},
            {"id": "ollama/llama3.3:70b", "name": "Llama 3.3 70B", "free": True},
            {"id": "ollama/llama3.1:8b", "name": "Llama 3.1 8B", "free": True},
            {"id": "ollama/deepseek-coder-v2:16b", "name": "DeepSeek Coder V2", "free": True},
            {"id": "ollama/deepseek-r1:14b", "name": "DeepSeek R1 14B", "free": True},
            {"id": "ollama/deepseek-r1:32b", "name": "DeepSeek R1 32B", "free": True},
            {"id": "ollama/mistral:7b", "name": "Mistral 7B", "free": True},
            {"id": "ollama/gemma3:12b", "name": "Gemma 3 12B", "free": True},
            {"id": "ollama/phi4:14b", "name": "Phi-4 14B (Microsoft)", "free": True},
            {"id": "ollama/codestral:22b", "name": "Codestral 22B", "free": True},
        ],
    },
    "deepseek": {
        "name": "DeepSeek",
        "desc": "Free cloud tier, excellent at coding",
        "type": "cloud-free",
        "env_key": "DEEPSEEK_API_KEY",
        "signup_url": "platform.deepseek.com",
        "free_tokens": "5M tokens on signup",
        "models": [
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat V3", "free": True},
            {"id": "deepseek/deepseek-reasoner", "name": "DeepSeek R1", "free": True},
            {"id": "deepseek/deepseek-coder", "name": "DeepSeek Coder", "free": True},
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
    def __init__(self, provider_id: str = None, model_id: str = None, api_key: str = None):
        self.provider_id = provider_id or os.getenv("CIPHER_PROVIDER", "ollama")
        self.model_id = model_id or os.getenv("CIPHER_MODEL", "ollama/qwen3:14b")
        self.api_key = api_key
        self._client = None
        self._init_client()

    def _init_client(self):
        import litellm
        litellm.set_verbose = False

        if self.api_key:
            litellm.api_key = self.api_key

        provider_config = PROVIDERS.get(self.provider_id, {})
        env_key = provider_config.get("env_key")
        if env_key and not self.api_key:
            self.api_key = os.getenv(env_key, "")

        self._litellm = litellm

    def chat(self, messages: list, stream: bool = True, system_prompt: str = None):
        formatted = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})
        formatted.extend(messages)

        response = self._litellm.completion(
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

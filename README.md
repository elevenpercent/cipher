# Cipher

Autonomous coding agent for your terminal. Write, edit, and run code with AI.

## Install

**pip:**
```bash
pip install git+https://github.com/elevenpercent/cipher.git@master
```

**npm:**
```bash
npm install https://github.com/elevenpercent/cipher.git
```

**Windows (one-liner):**
```powershell
irm https://raw.githubusercontent.com/elevenpercent/cipher/master/install.ps1 | iex
```

**macOS / Linux:**
```bash
curl -fsSL https://cipher.elevenpct.com/install.sh | bash
```

## Use

```bash
cd your-project
cip
```

First run shows the setup screen. Pick your provider and model, then start coding.

## Keyboard

| Key     | Action        |
|---------|---------------|
| `Ctrl+S` | Open settings |
| `Esc`   | Clear input   |

Ctrl+S opens the settings modal where you can change provider/model, clear chat, start a new session, browse saved sessions, or quit.

## Providers

### Cipher Proxy (No API Key)
Just works. Free models via proxy: Llama 3.3 70B (Groq), Llama 3.1 8B (Groq), Gemini 2.0 Flash (Google).

### Local Models (No API Key, GPU recommended)
- **Ollama** — Qwen3, Llama, Mistral, DeepSeek R1. Install at ollama.com
- **LM Studio** — Any model. Install at lmstudio.ai

### Cloud (API Key Required)
- **Groq** — Free tier, fast inference
- **Google Gemini** — 60 RPM free tier
- **OpenRouter** — 100+ models, free tiers
- **OpenAI** — GPT-4o, o-series
- **Anthropic** — Claude Sonnet 4, Opus 4
- **Mistral**, **xAI (Grok)**, **Together AI**, **Fireworks**, **Cohere**, **Perplexity**

## License

MIT - See [LICENSE](LICENSE) for details.

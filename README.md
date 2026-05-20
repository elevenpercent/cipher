# Cipher

Autonomous coding agent for your terminal. Write, edit, and run code with AI.

## Install

**Windows:**
```powershell
irm https://raw.githubusercontent.com/elevenpercent/cipher/master/install.ps1 | iex
```

**macOS / Linux:**
```bash
curl -fsSL https://cipher.elevenpct.com/install.sh | bash
```

**Manual:**
```bash
pip install git+https://github.com/elevenpercent/cipher.git@master
```

## Use

```bash
cd your-project
cip
```

First run shows the setup screen. Pick your provider and model, then start coding.

## Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/clear` | Clear chat history |
| `/stats` | Show session statistics |
| `/cd <path>` | Change working directory |
| `/provider` | Show current provider |
| `/provider <id>` | Switch provider |
| `/model` | Show current model |
| `/model <name>` | Switch model |
| `/providers` | List all providers |
| `/models` | List models for current provider |
| `/config` | Show configuration |
| `/dir` | Show working directory |
| `/history` | Show command history |
| `/new` | Start new session |
| `/sessions` | View saved sessions |
| `/quit` | Exit Cipher |

## Providers

### Cipher Proxy (No API Key)
Just works. Free models via proxy — Llama 3.3 70B (Groq), Gemini 2.0 Flash.

### Local Models (No API Key, GPU recommended)
- **Ollama** — Qwen3, Llama, Mistral, DeepSeek R1. Install at ollama.com
- **LM Studio** — Any model. Install at lmstudio.ai

### Cloud (API Key Required)
- **Groq** — Free tier, fast inference
- **Google Gemini** — 60 RPM free tier
- **OpenRouter** — 100+ models
- **OpenAI** — GPT-4o, o-series
- **Anthropic** — Claude Sonnet 4, Opus 4
- **Mistral**, **xAI (Grok)**, **Together AI**, **Fireworks**, **Cohere**, **Perplexity**

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+S` | Open settings |
| `Ctrl+P` | Switch providers |
| `Ctrl+L` | Clear chat |
| `Ctrl+Q` | Quit |
| `Esc` | Clear input |
| `Tab` | Autocomplete command |
| `Up/Down` | Navigate autocomplete/history |

## License

MIT - See [LICENSE](LICENSE) for details.

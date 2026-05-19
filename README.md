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
cip --setup
```

Choose your AI provider and model interactively, then start building.

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

### Local (No API Key)

| Provider | Models | Setup |
|----------|--------|-------|
| Ollama | Qwen3, Llama, DeepSeek R1, Mistral, Phi-4 | Install at ollama.com |
| LM Studio | Any model via LM Studio | Install at lmstudio.ai |

### Cloud Free Tiers (Needs API Key, Free Tier Available)

| Provider | Models | Free Tokens |
|----------|--------|-------------|
| Groq | Llama 3.3 70B, Mixtral, Gemma 2 | Generous free tier |
| DeepSeek | DeepSeek Chat V3, Coder, Reasoner | 5M tokens on signup |
| Google Gemini | Gemini 2.0 Flash, 2.5 Pro | 60 RPM free tier |
| OpenRouter | 100+ models | Some free models |
| Fireworks AI | Llama 3.3, Qwen2.5 Coder | Free tier |
| Cohere | Command R+, Command R | Free tier |
| Perplexity | Sonar, Sonar Pro | Free tier |

### API Key Required (Paid)

| Provider | Models |
|----------|--------|
| OpenAI | GPT-4o, GPT-4.1, o1, o3, o4 |
| Anthropic | Claude Sonnet 4, Opus 4, 3.7 Sonnet |
| Mistral | Mistral Large, Codestral, Ministral |
| xAI | Grok 3, Grok 3 Mini |
| Together AI | Llama 3.3 70B, Qwen2.5 72B, 405B |

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

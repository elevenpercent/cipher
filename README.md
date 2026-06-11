# Cipher

Autonomous coding agent for your terminal. Describe a task — Cipher reads your codebase, proposes diffs, runs commands (with your approval), and ships working code.

## Install

```bash
pip install git+https://github.com/elevenpercent/cipher.git@master
```

**Windows (one-liner):**
```powershell
irm https://cipher.elevenpct.com/install.ps1 | iex
```

**macOS / Linux:**
```bash
curl -fsSL https://cipher.elevenpct.com/install.sh | bash
```

## Use

```bash
cd your-project
cipher            # or: cip
cipher -p "add tests for auth.py"   # start with a task
cipher --setup    # re-run provider setup
```

First run shows the setup screen. Pick **Cipher Proxy** to start with zero configuration — no API key needed.

## How it works

Cipher is a single agent loop with **approval gates**:

- **File changes** — every `write`/`edit` shows you a unified diff first. Allow once, always allow, or deny.
- **Commands** — every shell/git command is shown before it runs. Same three choices.
- **Read-only tools** (read, grep, glob, ls, tree, web) run freely.

The model acts through tool tags (`<read>`, `<write>`, `<edit>`, `<run>`, `<git>`, `<grep>`, `<glob>`, `<web-fetch>`, `<web-search>`) and finishes with `<done>`.

## Keyboard

| Key      | Action                  |
|----------|-------------------------|
| `Ctrl+P` | Provider settings       |
| `Esc`    | Cancel the running task |
| `Ctrl+Q` | Quit                    |
| `a / y / d` | Approve once / always / deny (in approval dialog) |

## Providers

All providers speak the OpenAI chat-completions protocol.

- **Cipher Proxy** — free, no key. Llama 4 Maverick → Llama 3.3 70B → Gemini fallback chain.
- **BYOK** — OpenAI, Anthropic, Groq, Gemini, DeepSeek, SambaNova, OpenRouter.
- **Local** — Ollama (and anything OpenAI-compatible via the Custom provider).

API keys can be stored in setup or read from env vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, …).

## Data

Config and session history live in `~/.cipher/`. Delete that folder to remove all data.

## License

MIT — see [LICENSE](LICENSE) for details.

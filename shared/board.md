# Task Board

## Rules
- Claim a task by writing your agent name next to it: `[CLAUDE]` or `[OPENCODE]`
- Never edit a file the other agent has claimed
- Mark done with `[DONE]`

## File Ownership
| Path | Owner |
|------|-------|
| site/ | CLAUDE |
| tests/ | CLAUDE |
| cipher/app.py | OPENCODE |
| cipher/themes.py | OPENCODE |
| cipher/formatters.py | OPENCODE |
| cipher/provider.py | OPENCODE |
| cipher/tools.py | OPENCODE |
| cipher/permissions.py | OPENCODE |
| cipher/lsp.py | OPENCODE |
| cipher/mcp.py | OPENCODE |
| cipher/__main__.py | OPENCODE |
| pyproject.toml | CLAUDE |
| shared/ | BOTH |

## Tasks

| Task | Owner | Status |
|------|-------|--------|
| Fix version v0.4.0 → v0.5.0 everywhere | CLAUDE | DONE |
| Improve website, install scripts, docs slash commands | CLAUDE | DONE |
| Fix crashes in app.py (5 sources) | OPENCODE | DONE |
| Add error recovery for empty/malformed AI responses | OPENCODE | DONE |
| Fix tools.py edge cases (empty path, None-safe, cross-platform) | OPENCODE | DONE |
| Audit permissions.py, provider.py, formatters.py for edge cases | OPENCODE | in progress |
| Write tests for palette actions (reset/clear/update/setup) | CLAUDE | in progress |
| Write tests for slash commands | CLAUDE | in progress |

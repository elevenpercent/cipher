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
| Fix version v0.4.0 → v0.5.0 in pyproject.toml, site/index.html, site/docs/index.html | CLAUDE | in progress |
| Improve website (copy, install section, cross-OS clarity) | CLAUDE | in progress |
| Fix install.sh: add Python version check, exit code check, --break-system-packages | CLAUDE | in progress |
| Fix install.ps1: try py/python/python3 launchers, add version check | CLAUDE | in progress |
| Fix npm install command site-wide: add -g flag | CLAUDE | in progress |
| Fix docs: add slash commands section, fix keyboard shortcuts table | CLAUDE | in progress |
| Fix crash in verify/crash flow in app.py (user reports still crashing after palette fix) | OPENCODE | todo |
| Audit app.py for any remaining crashes or unhandled exceptions | OPENCODE | todo |
| Fix any broken tool calls or edge cases in tools.py | OPENCODE | todo |
| Add error recovery when AI provider returns empty/malformed response | OPENCODE | todo |
| Write tests for palette actions (reset/clear/update/setup) | CLAUDE | todo |
| Write tests for slash commands | CLAUDE | todo |

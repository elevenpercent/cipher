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
| Fix version v0.4.0 → v0.5.0 in pyproject.toml, site/index.html, site/docs/index.html | CLAUDE | DONE |
| Improve website (copy, install section, cross-OS clarity) | CLAUDE | DONE |
| Fix install.sh: add Python version check, exit code check, --break-system-packages | CLAUDE | DONE |
| Fix install.ps1: try py/python/python3 launchers, add version check | CLAUDE | DONE |
| Fix npm install command site-wide: add -g flag | CLAUDE | DONE |
| Fix docs: add slash commands section, fix keyboard shortcuts table | CLAUDE | DONE |
| Fix crash in verify/crash flow in app.py | OPENCODE | DONE |
| Audit app.py for remaining crashes and unhandled exceptions | OPENCODE | DONE |
| Add error recovery when AI provider returns empty/malformed response | OPENCODE | DONE |
| Fix any broken tool calls or edge cases in tools.py | OPENCODE [OPENCODE] | in progress |
| Write tests for palette actions (reset/clear/update/setup) | CLAUDE | todo |
| Write tests for slash commands | CLAUDE | todo |

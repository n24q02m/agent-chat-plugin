# Contributing to agent-chat-plugin

Thanks for your interest. agent-chat-plugin is a single-file, dependency-free
Python CLI (`chat.py`, stdlib only), so setup is trivial.

## Development

1. Python 3.13 (or run `mise install`).
2. `pip install ruff` — the only dev tool.
3. Edit `chat.py` / `hooks/` / `skills/` / `commands/`.
4. Check: `ruff check .` and `python chat.py --help`.

## Commit convention

Only two prefixes: `feat:` (new features) and `fix:` (bug fixes).

## Pull requests

- One PR per feature or fix.
- Keep it dependency-free (Python stdlib only) — that is a core design goal.
- CI (ruff + CodeQL) must pass.

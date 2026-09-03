# CLAUDE.md - agent-chat-plugin

# Agent Collaboration

## Quick reference

- Repo: `n24q02m/agent-chat-plugin`
- Description: Peer AI agents coordinate through markdown messages in shared channel folders — no orchestrator, autonomous zero-token waiting, cross-platform.
- License: Apache-2.0
- Design goal: single-file, dependency-free (Python stdlib only).

## Build & Test

No build step — `chat.py` is stdlib-only. For development:

```sh
mise run lint    # ruff check .
mise run smoke   # python chat.py --help
```

## Release

Manual `workflow_dispatch` on `cd.yml` (choose `beta` or `stable`).
python-semantic-release handles the version bump, CHANGELOG, tag, GitHub Release,
and PyPI publish (via Trusted Publishing / OIDC).

## Conventions

- Commits: only `feat:` and `fix:` prefixes.
- Keep it dependency-free (Python stdlib only).
- No secrets — this CLI has none (local filesystem only, no credentials).

# agent-chat

[![PyPI](https://img.shields.io/pypi/v/agent-chat-plugin.svg)](https://pypi.org/project/agent-chat-plugin/)
[![Python](https://img.shields.io/pypi/pyversions/agent-chat-plugin.svg)](https://pypi.org/project/agent-chat-plugin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/n24q02m/agent-chat-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/n24q02m/agent-chat-plugin/actions/workflows/ci.yml)

<!-- BEGIN: AUTO-GENERATED-CROSS-PROMO -->
<details>
  <summary><strong>Sister projects from n24q02m</strong> (click to expand)</summary>

| Project | Tagline | Tag |
|---|---|---|
| [agent-chat-plugin](https://github.com/n24q02m/agent-chat-plugin) | Peer AI agents chat in a shared folder — no human relay, no orchestrator, wor... | Tooling |
| [better-code-review-graph](https://github.com/n24q02m/better-code-review-graph) | Knowledge graph for token-efficient code reviews -- semantic search and call-... | MCP |
| [better-drive](https://github.com/n24q02m/better-drive) | 2-way Google Drive sync with .driveignore filter — rclone engine, Windows tray | Tooling |
| [better-email-mcp](https://github.com/n24q02m/better-email-mcp) | IMAP/SMTP email for AI agents -- read, send, organize folders, and manage att... | MCP |
| [better-godot-mcp](https://github.com/n24q02m/better-godot-mcp) | Composite MCP server for Godot Engine -- 17 composite tools for AI-assisted g... | MCP |
| [better-notion-mcp](https://github.com/n24q02m/better-notion-mcp) | Markdown-first Notion for AI agents -- pages, databases, blocks, and comments... | MCP |
| [better-semantic-release](https://github.com/n24q02m/better-semantic-release) | Drop-in python-semantic-release fork with built-in release-safety guards (orp... | Tooling |
| [better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp) | Telegram for AI agents -- messages, chats, media, and contacts across both bo... | MCP |
| [better-workspace-mcp](https://github.com/n24q02m/better-workspace-mcp) | Google Workspace MCP server (Docs/Drive/Calendar/Gmail/Sheets/Slides/Tasks/Ch... | MCP |
| [claude-plugins](https://github.com/n24q02m/claude-plugins) | Claude Code plugin marketplace for the n24q02m MCP servers -- install web sea... | Marketplace |
| [imagine-mcp](https://github.com/n24q02m/imagine-mcp) | Image and video understanding + generation for AI agents -- across Gemini, Op... | MCP |
| [jules-task-archiver](https://github.com/n24q02m/jules-task-archiver) | Chrome Extension for bulk operations on Jules tasks via batchexecute API -- a... | Tooling |
| [mcp-core](https://github.com/n24q02m/mcp-core) | Shared foundation for building MCP servers -- Streamable HTTP transport, OAut... | MCP |
| [mnemo-mcp](https://github.com/n24q02m/mnemo-mcp) | Persistent AI memory with hybrid search and embedded sync. Open, free, unlimi... | MCP |
| [qwen3-embed](https://github.com/n24q02m/qwen3-embed) | Lightweight Qwen3 text embedding and reranking via ONNX Runtime and GGUF | Library |
| [skret](https://github.com/n24q02m/skret) | Secrets without the server. | CLI |
| [tacet](https://github.com/n24q02m/tacet) | A self-distilling neuro-symbolic cascade that amortises LLM cost across knowl... | Tooling |
| [web-core](https://github.com/n24q02m/web-core) | Shared web infrastructure package for search, scraping, HTTP security, and st... | Library |
| [wet-mcp](https://github.com/n24q02m/wet-mcp) | Open-source MCP server for AI agents: web search, content extraction, and lib... | MCP |

</details>
<!-- END: AUTO-GENERATED-CROSS-PROMO -->


**Peer AI agents chat in a shared folder — no human relay, no orchestrator, works on
Windows, waits at zero tokens.**

Multiple agent sessions (Claude Code, Codex, Cursor, OpenCode — same tool or mixed)
coordinate as equals by exchanging markdown messages in shared **channel folders**.
The folder is the whole state: git-committable, human-readable, replayable. A crashed
session loses nothing.

One dependency-free file (`chat.py`, Python stdlib) runs identically on Windows, WSL,
and Linux. Waiting for a reply blocks in-process — **an agent that is waiting spends
zero model tokens.**

> Distributed as **`agent-chat-plugin`** on PyPI and as a Claude Code plugin (the short
> name `agent-chat` was taken on PyPI). The command and skill are still `agent-chat`.

## Why this exists

Every strong multi-agent coding tool today is either **hierarchical** (a supervisor or
human drives subagents) or **single-agent**. The peer case — N equal sessions
coordinating through a folder of messages, autonomously waiting on each other — has no
lean, cross-platform, tool-agnostic answer. This is that answer. (Honest scope: this is
a young space; see `COMPARISON.md` for exactly what already exists and where this differs.)

## Quickstart

```bash
# a channel = a group chat
python chat.py init review --members alice,bob --topic "code review"

# alice posts to bob
python chat.py post review --from alice --to bob --title "Schema v0.2" --body-file msg.md

# bob reads what's new for him (only messages addressed to him or the group)
python chat.py read review --as bob

# alice waits for bob's reply — burns 0 tokens while blocked
python chat.py wait review --as alice --timeout 900
```

Root defaults to `~/agent-chat`; override with `$AGENT_CHAT_ROOT` or `--root`. Run
`python chat.py <cmd> --help` for all flags.

## How it works

- **Channels** — one folder per group chat; make as many as you need (`init`).
- **Messages** — `NNNN-<from>-<slug>.md` with frontmatter (`from`, `to`, `reply_to`,
  `status`, `title`). `to: all` broadcasts.
- **Cursors** — `read`/`wait` show only what's new for you and never re-scan the thread.
- **Atomic** — sequence numbers are allocated under a lock (no duplicate `-11`); task
  claiming uses atomic rename (lose the race -> move on).

Six rules keep peers from stepping on each other: one channel per topic; claim before
you act; message don't chatter; `wait` don't poll-with-the-model; read since your
cursor; reply in a new file. Full protocol in `SPEC.md`.

## Two modes, two budgets

- **Live swarm** — N sessions running concurrently, `wait`-ing on each other. Buys
  wall-clock parallelism + fault tolerance; costs more tokens. For abundant budgets.
- **Async handoff / audit** — post a summary when a session ends; the next session
  reads it. Nearly free — usable on a tight budget.

## Install & distribution

- **As a CLI** — `pipx install agent-chat-plugin` then run `agent-chat`
  (or `uvx --from agent-chat-plugin agent-chat`).
- **As a skill** — drop `SKILL.md` + `chat.py` into your agent's skills directory;
  works across tools that read the Agent Skills / `SKILL.md` standard.
- **As a Claude Code plugin** — via a plugin marketplace.

## Status

Early (v0). The reference implementation is tested end-to-end; the protocol may still
change. Feedback and interop with `tap` / `TICK.md` welcome.

## License

MIT.
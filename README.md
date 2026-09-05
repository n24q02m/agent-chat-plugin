# agent-chat

[![PyPI](https://img.shields.io/pypi/v/agent-chat-plugin.svg)](https://pypi.org/project/agent-chat-plugin/)
[![Python](https://img.shields.io/pypi/pyversions/agent-chat-plugin.svg)](https://pypi.org/project/agent-chat-plugin/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
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

Multiple agent sessions (OMP, Claude Code, Codex, Cursor, OpenCode — same tool or mixed)
coordinate as equals by exchanging markdown messages in shared **channel folders**.
The folder is the whole state: git-committable, human-readable, replayable. A crashed
session loses nothing.

The dependency-free CLI (`chat.py` plus the `agent_chat/` modules, Python stdlib)
runs on Windows, WSL, and Linux. Waiting for a reply blocks in-process —
**the wait loop makes no model calls and consumes no model tokens.**

> Distributed as **`agent-chat-plugin`** on PyPI and as a Claude Code plugin (the short
> name `agent-chat` was taken on PyPI). The command and skill are still `agent-chat`.

## Why this exists

Claude Code now has a native **cross-session messaging** path for Claude Code sessions
on supported platforms. The peer case this project targets is broader: N equal sessions
across Claude Code, Codex, Cursor, OpenCode, or mixed tools coordinating through a
file-backed, auditable folder of messages and autonomously waiting on each other. This
is that cross-tool answer. (Honest scope: this is a young space; see `COMPARISON.md` for
the native Claude Code overlap and the exact differences.)

### Claude Code native overlap

Claude Code `v2.1.224+` provides **Cross-session messaging** through `ListAgents` and
`SendMessage` on macOS/Linux, including WSL2; native Windows is not currently supported.
That feature is Claude-Code-only and delivers messages directly between sessions. This
project remains distinct through mixed-tool coordination, native Windows support,
Markdown channels that are git-committable and replayable, atomic claims/cursors, and
zero-token in-process waiting. On supported Claude Code platforms, the native path may
make this plugin's optional unread-notification hooks redundant; it does not replace the
file-backed protocol.

## Quickstart

Run these commands from a complete repository checkout. With the installed CLI,
replace `python chat.py` with `agent-chat` (see [Install & distribution](#install--distribution)).

```bash
# a channel = a group chat
python chat.py init review --members alice,bob --topic "code review"

# alice posts to bob
python chat.py post review --from alice --to bob --title "Schema v0.2" --body "Ready for review."

# bob reads what's new for him
python chat.py read review --as bob

# create dependent work
python chat.py task create review T-0001 --from alice --title "Implement schema"
python chat.py task create review T-0002 --from alice --title "Review schema" --depends-on T-0001

# claim, renew and complete a ready task
python chat.py task claim review T-0001 --as alice --lease-seconds 900
python chat.py task renew review T-0001 --as alice --lease-seconds 900
python chat.py task done review T-0001 --as alice

# coordinate paths and state
python chat.py lock review src/schema.py --as alice --lease-seconds 900
python chat.py unlock review src/schema.py --as alice
python chat.py state review
python chat.py compact review --as alice

# capability handshake without claiming host-native execution
python chat.py event post review --from alice --type capability --harness generic-shell
```

Root precedence is `--root` > `$AGENT_CHAT_ROOT` > `~/agent-chat`. Put the global
flag before the subcommand: `python chat.py --root "/shared/chat" channels`.
Run `python chat.py <cmd> --help` for all flags.

## How it works

- **Channels** — one folder per group chat; make as many as needed with `init`.
- **Messages** — numbered Markdown files with frontmatter and immutable replies.
- **Cursors** — `read`/`wait` show only new relevant messages.
- **Tasks** — JSON records with dependencies, readiness, status and acceptance.
- **Leases** — owner-bound claims with expiry and explicit stale recovery.
- **Path locks** — normalized workspace-relative ownership records with conflict checks.
- **State** — deterministic derived `state.md`; compaction never replaces source records.
- **Events** — versioned capability/status JSON carried through ordinary messages.
- **Atomicity** — filesystem transactions, audit events and recovery markers protect concurrent work.

Agent Chat is a coordination data layer. It does not execute agents, assign models,
approve permissions, run MCP/ACP, or wake another process. No command or hook
calls an LLM, embedding/rerank provider, graph service, relay, or Cloudflare gateway.
`state`/`compact` derive summaries from local records, not model-generated text;
capability/status events describe a peer and do not invoke it.

## Two modes, two budgets

- **Live swarm** — N sessions run concurrently and use `wait` for wall-clock parallelism.
- **Async handoff / audit** — a session posts an artifact summary for the next session.

Both modes use the same file-backed protocol and remain auditable.

## Install & distribution

- **As a CLI** — `pipx install agent-chat-plugin`, then run `agent-chat <cmd>`.
  For one-off execution use `uvx --from agent-chat-plugin agent-chat <cmd>` on
  each invocation; `uvx` does not install a persistent `agent-chat` command.
- **As a standalone Skill** — copy the root `SKILL.md`, `chat.py`, and the
  entire `agent_chat/` directory together into a compatible Skills directory.
  Copying only `chat.py` breaks task, lease, path-lock, and state commands.
- **As a Claude Code plugin** — install the marketplace package from
  [claude-plugins](https://github.com/n24q02m/claude-plugins). Keep
  `.claude-plugin/`, `hooks/`, `commands/`, `skills/`, `chat.py`, and
  `agent_chat/` together; the plugin skill is `skills/agent-chat/SKILL.md`.

PyPI installs the CLI and its Python modules, not the skill, slash command, or
lifecycle hooks. Use the checkout/plugin distribution for those assets.

All participants must address the same channel root on a filesystem with the
required atomic replacement and locking semantics. Separate home/company
`~/agent-chat` directories are separate inboxes; this package does not sync
machines or install a background service. Give each participant a distinct
`AGENT_CHAT_NAME` for hooks; CLI identities are explicit `--from`/`--as` flags.
Set environment values before starting the host, not by changing its model or
MCP configuration.

### Optional inbox hooks

`hooks/hooks.json` registers three Claude Code lifecycle commands. Python hook
scripts can be invoked by absolute checkout path in another host, but that host
must explicitly support or adapt their lifecycle/output contract:

| Hook | Output when messages are unread |
|---|---|
| `SessionStart` / `hooks/session_inbox.py` | Plain-text channel/count notice; warns about unset identity when channels exist. |
| `UserPromptSubmit` / `hooks/prompt_inbox.py` | Plain-text channel/count notice; unset identity is silent. |
| `Stop` / `hooks/stop_inbox.py` | Claude-compatible JSON with `systemMessage`; unset identity is silent. |

Set `AGENT_CHAT_ROOT` and optionally comma-separated `AGENT_CHAT_CHANNELS`
(empty means all discovered channels). Malformed channel names are skipped
without suppressing other configured inboxes. Hooks only peek: they never
advance cursors, read message bodies into notices, reply, block a turn, or wake
a peer. `read` and successful `wait` advance cursors.

The scripts prefer non-empty `CLAUDE_PLUGIN_ROOT`; otherwise they resolve
`chat.py` beside their own `hooks/` directory. An unresolved plugin root skips
with a one-line stderr diagnostic; hook failures always exit 0. Quote paths:
`python "/path/to/agent-chat-plugin/hooks/session_inbox.py"`.

A portable script is not an installed OMP/native integration. Verify each host's
explicit invocation and rendered notice; CLI installation or a successful
source check alone does not prove hooks are loaded on home or company.

See [CONTRIBUTING.md](CONTRIBUTING.md) for developer setup and runtime layout.

## Status

The reference implementation covers file-backed messages, cursors, token-free wait,
structured tasks/dependencies, leases, normalized path locks, derived state and
adapter-neutral capability/status events. MCP wrappers, ACP/wake bridges and agent
execution remain separate future designs.

## License

Apache-2.0.

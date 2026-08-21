---
name: agent-chat
description: Use when two or more agent sessions (Claude Code or other tools, same machine or peers) must coordinate through markdown files in a shared folder instead of one supervisor driving subagents — group chat, blackboard, mailbox/inbox, multi-session handoff, or an agent-chat/ directory. Triggers include peer agents, N sessions sharing a folder, waiting for another session's reply, atomic task claiming, and needing multiple separate group chats/channels.
---

# agent-chat

## Overview

Peer agent sessions coordinate by exchanging **markdown files in shared channel folders** — no supervisor, no message broker, no RAM shared between them. Each channel is one "group chat". The whole thread is plain markdown: git-committable, human-readable, replayable. A crashed session loses nothing — the files are the state.

One CLI (`chat.py`, Python stdlib only) runs identically on Windows, WSL and Linux. `wait` blocks with a sleep-poll loop, so **an agent waiting for a reply burns zero model tokens** while idle.

**Core principle:** talk through files, not through each other. Summaries as artifacts, not full transcripts passed back and forth.

## When to use

- Multiple `claude` sessions (or Cursor/Codex/OpenCode) working the same problem as equals.
- One session needs another to do something, then waits for the result.
- You want an auditable record of an agent negotiation.
- You need **several independent group chats** (one per topic/team) — make one channel each.

**When NOT to use:** a single agent with cheap subagents is cheaper and simpler — this pattern trades tokens for parallelism, fault tolerance, and auditability. If token budget is tight, use only the async/handoff path (post a summary at end of session; the next session reads it) — that mode costs almost nothing.

## Quick reference

Run via `python <skill>/chat.py <cmd>`. Root = `$AGENT_CHAT_ROOT` or `~/agent-chat` (override with `--root`).

| Do this | Command |
|---|---|
| Create a group chat | `chat.py init review --members alice,bob --topic "..."` |
| List all group chats | `chat.py channels` |
| Post a message | `chat.py post review --from alice --to bob --title "Schema v0.2" --body-file msg.md` |
| Broadcast to the group | `chat.py post review --from alice --to all --title "..."` (or omit `--to`) |
| Read what's new for me | `chat.py read review --as bob` |
| Wait for a reply (0 tokens) | `chat.py wait review --as alice --timeout 900` |
| Peek recent, keep cursor | `chat.py peek review -n 3` |
| Claim a task atomically | `chat.py claim work task-12.md --as bob` |

Structured tasks use the same channel root and write authoritative JSON records
under `<root>/<channel>/tasks/`; active lease records live under
`<root>/<channel>/claims/<task-id>.<owner>.json`. Every successful task or lease
mutation also posts an audit event through the existing message protocol:

```text
chat.py task create <channel> <task-id> --from <agent> --title <title>
chat.py task list <channel>
chat.py task show <channel> <task-id>
chat.py task update <channel> <task-id> --as <agent> [fields...]
chat.py task claim <channel> <task-id> --as <agent> --lease-seconds 300
chat.py task renew <channel> <task-id> --as <agent> --lease-seconds 300
chat.py task done <channel> <task-id> --as <agent>
chat.py task block <channel> <task-id> --as <agent>
chat.py task release <channel> <task-id> --as <agent>
chat.py task recover <channel> <task-id> --as <agent> \
  --reason "stale session" --lease-seconds 300
chat.py task recover-pending <channel> --as <agent>

`claim`, `renew`, and stale `recover` accept `--lease-seconds`, `--lease`, or
`--ttl`; the value must be a positive finite duration. `claim` advances a ready
task to `in_progress`, assigns the owner, and writes its expiry atomically with
the claim record. Only the owner can renew, release, or complete an unexpired
claim. `task done` clears an active claim atomically; when no claim exists it
preserves the direct Task 3 transition. `task release` similarly preserves the
unleased Task 3 transition. An expired claim is never silently stolen:
stale `task recover` requires a new owner and non-empty reason and records
`previous_owner`, `previous_lease_expires_at`, and `recovery_reason`.
After a crash, `task recover-pending <channel> --as <agent>` explicitly
finishes cleanup/rollback of the durable transaction marker; it never silently
steals or reassigns a stale task.

`create` accepts `--owner`, `--depends-on`, `--files-hint`, `--acceptance`, and
`--branch`. Repeat list options to add multiple values. `update` accepts
`--title`, `--owner`, `--depends-on`, `--files-hint`, `--acceptance`,
`--branch`, and `--status`; use `--clear-owner` or `--clear-branch` to set
nullable fields back to `null`. Generic updates cannot mutate an active lease;
use the lease commands instead. List values may also be comma-separated.

Task statuses are `open`, `in_progress`, `blocked`, `done`, and `cancelled`.
`done` and `cancelled` are terminal. Transitions allow `open` -> `in_progress` |
`blocked` | `cancelled`, `in_progress` -> `open` | `blocked` | `done` |
`cancelled`, and `blocked` -> `open` | `in_progress` | `cancelled`. Same-state
writes are intentionally idempotent. `task done` moves `in_progress` (or
idempotent `done`) to `done`; `task block` moves `open`, `in_progress`, or
`blocked` to `blocked`; and `task release` moves `blocked`, `in_progress`, or
`open` to `open`. A task can advance to `in_progress` or `done` only when
every ID in `depends_on` has a task record whose status is `done`. Readiness is
computed from task JSON records, never from message text.

Task and lease failures are nonzero (exit status 2) and include one stable code.
Task codes include `TASK_INVALID_COMMAND`, `TASK_INVALID_ARGUMENT`,
`TASK_INVALID_CHANNEL`, `TASK_CHANNEL_NOT_FOUND`, `TASK_NOT_FOUND`,
`TASK_ALREADY_EXISTS`, `TASK_INVALID_STATUS`, `TASK_INVALID_UPDATE`,
`TASK_INVALID_TRANSITION`, `TASK_DEPENDENCY_NOT_READY`,
`TASK_UNKNOWN_DEPENDENCY`, `TASK_DEPENDENCY_CYCLE`,
`TASK_PATH_OUTSIDE_WORKSPACE`, `TASK_LOCK_TIMEOUT`, `TASK_IO_ERROR`, and
`TASK_AUDIT_FAILED`. Lease codes include `LEASE_CONFLICT`,
`LEASE_RECOVERY_REQUIRED`, `LEASE_OWNER_MISMATCH`, `LEASE_NOT_EXPIRED`,
`LEASE_NOT_FOUND`, `LEASE_INCONSISTENT`, `LEASE_MUTATION_REQUIRED`,
`LEASE_INVALID_OWNER`, `LEASE_INVALID_TASK_ID`, `LEASE_INVALID_CHANNEL`,
`LEASE_INVALID_REASON`, `LEASE_INVALID_DURATION`, `LEASE_INVALID_TIMESTAMP`,
`LEASE_INVALID_RECORD`, `LEASE_REQUIRED_FIELD_MISSING`, `LEASE_UNKNOWN_FIELD`,
`LEASE_RECORD_ID_MISMATCH`, `LEASE_STORAGE_INVALID`,
`LEASE_PATH_OUTSIDE_WORKSPACE`, `LEASE_TRANSACTION_PENDING`,
`LEASE_TRANSACTION_CLEANUP_FAILED`, `LEASE_TRANSACTION_INVALID`,
`LEASE_TRANSACTION_NOT_FOUND`, `LEASE_TRANSACTION_RECOVERY_FAILED`,
`LEASE_AUDIT_FAILED`, and `LEASE_AUDIT_ROLLBACK_FAILED`. Lease writes use a
durable transaction marker with prepared/applied/published phases; after a
crash or cleanup failure, access fails closed until
`task recover-pending`/`LeaseStore.recover_pending()` explicitly rolls back
or finishes the published transaction.

`--reply <seq>` threads a message to an earlier one. `python chat.py <cmd> --help` for all flags.

## Folder layout

```
<root>/
  review/                     # one channel = one group chat
    _meta.json                   # members, topic, created
    0001-alice-schema-draft.md # NNNN-<from>-<slug>.md, frontmatter + body
    0002-bob-schema-review.md
    .cursors/bob.txt           # per-agent "last seq read"
  deploy/                    # a SECOND group chat, separate seq space
    ...
```

Message frontmatter: `seq, from, to, reply_to?, channel, ts, status, title`. `to: all` (or omitted) = broadcast.

## Protocol (the rules each session follows)

1. **One channel per topic/team.** Don't cram everything into one folder — that was the prototype's failure. `channels` to discover, `init` to open a new group.
2. **Claim before you act.** Use `claim` (atomic rename) or self-address a message before starting shared work. Lost the race (exit 3)? Move on — someone else has it.
3. **Message, don't chat.** To ask a peer for something, `post` a file addressed `--to them`, then do other work or `wait`. Don't stream chatter.
4. **Wait, don't poll with the LLM.** Use `wait` — it sleeps in-process. Never write a `while` loop that re-invokes the model to "check the folder" (millions of wasted tokens).
5. **Read since your cursor.** `read --as you` shows only messages newer than your cursor and addressed to you or the group, then advances it. Don't re-ingest the whole thread each turn.
6. **Reply in a new file.** Never edit another agent's message file (stale-context corruption). Post a new one with `--reply <seq>`.

## Token economics

Two modes from the same tool:
- **Live swarm** — N sessions running concurrently, `wait`-ing on each other. Higher total tokens; you buy wall-clock parallelism + fault tolerance. For abundant-budget runs.
- **Async handoff / audit** — post a summary when a session ends; the next session (or another tool) `read`s it. Nearly free — usable even under a tight budget.

The savings vs naive peer messaging are real and structural: `wait` (idle = 0 tokens), summary artifacts instead of full-history passing, cursor reads instead of full-folder rescans, and channel-scoped reads (only your groups).

## Common mistakes

| Mistake | Fix |
|---|---|
| `while true; do read; done` in the LLM loop | Use `wait` — it blocks in-process, no tokens. |
| Two sessions grab the same task | Use `claim` (atomic) — never eyeball the board. |
| Everything in one folder | One channel per topic; `init` more. |
| Editing a peer's message to "reply" | Post a new file with `--reply`. |
| Manually numbering files (`-11` twice) | Always `post` — it allocates seq under a lock. |

## Cross-platform

Pure stdlib; no `inotify`/`fswatch` dependency. `wait` uses sleep-polling (default 5s) so it works the same on Windows (no inotify), WSL, and Linux. Atomic ops use `os.mkdir` (seq lock) and `os.replace` (claim), both atomic on NTFS and POSIX.

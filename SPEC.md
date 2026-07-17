# agent-chat protocol — Specification (draft v0.1)

Status: DRAFT. Reference implementation: `chat.py` (Python stdlib) shipped as the
`agent-chat` skill. This spec is tool-agnostic — any runtime that can read/write
files can conform.

The keywords MUST, SHOULD, MAY are used as in RFC 2119.

## 1. Purpose

agent-chat defines a **file-based coordination protocol for peer agent sessions**.
Multiple agent sessions (same tool or different tools) coordinate by exchanging
markdown message files in shared **channel folders** — like a group chat / blackboard
— with **no supervisor and no required human arbiter**. The message folder is the
whole state: git-committable, human-readable, replayable. A crashed session loses
nothing.

### Non-goals

agent-chat does NOT execute agents, assign models/tools, sandbox, manage memory, or
run workflows. Those belong to the runtime. agent-chat owns only: channels, message
state, read cursors, and atomic claiming.

## 2. Terminology

- **Root** — a directory containing channels. Resolved from `$AGENT_CHAT_ROOT`, a
  `--root` argument, or a default (`~/agent-chat`).
- **Channel** — one subfolder of the root = one group chat. Has its own message
  sequence space and membership.
- **Message** — one markdown file in a channel, `NNNN-<from>-<slug>.md`.
- **Cursor** — a per-agent, per-channel marker of the last sequence number consumed.
- **Roster** — a channel's declared members.

## 3. Folder layout (normative)

```
<root>/
  <channel>/
    _meta.json                 # channel metadata (members, topic, created)
    _seq.lock                  # transient lock dir for sequence allocation
    NNNN-<from>-<slug>.md       # message files, zero-padded 4-digit sequence
    .cursors/<agent>.txt        # per-agent last-read sequence
```

- A channel MUST contain `_meta.json`. Its absence means the channel does not exist.
- Message filenames MUST begin with a zero-padded integer sequence followed by `-`.
- Files beginning with `_` or `.` MUST NOT be treated as messages.

## 4. Message format (normative)

A message is a markdown file with a YAML-style frontmatter block delimited by `---`,
followed by a free markdown body.

```
---
seq: 12
from: alice
to: bob            # a single agent, a comma-list, or "all" (broadcast)
reply_to: 11         # OPTIONAL — sequence this message answers
channel: review
ts: 2026-07-17T14:03:22+07:00
status: discussion   # free label: discussion | proposal | ack | done | ...
title: Converge schema v0.2
---
<markdown body>
```

- `seq`, `from`, `to`, `channel`, `ts`, `title` MUST be present.
- `to` absent or `all`/`*` MUST be interpreted as broadcast to the channel.
- `ts` MUST be an ISO-8601 timestamp with offset.
- A message file, once written, MUST NOT be edited by another agent. Replies MUST be
  new files referencing `reply_to`.

## 5. Operations (behavioral contract)

A conforming implementation MUST provide, by any interface (CLI, library, MCP):

| Operation | Contract |
|-----------|----------|
| **init** | Create a channel with `_meta.json` (members, topic). MUST fail if it exists. |
| **post** | Allocate the next sequence atomically, write a well-formed message file. Returns the sequence. |
| **read** | Return messages with `seq > cursor` that are relevant to the caller, then advance the cursor to the channel's max sequence. |
| **wait** | Block until a relevant message with `seq > cursor` exists, or a timeout elapses. MUST NOT consume model tokens while blocked. |
| **claim** | Atomically take ownership of a task marker; MUST fail (distinct exit/error) if already claimed. |

**Relevance:** a message is relevant to agent `X` if `to` is broadcast or contains
`X`, AND `from != X` (an agent MUST NOT be woken by its own message).

## 6. Concurrency & atomicity (normative)

- **Sequence allocation** MUST be atomic across concurrent posters. The reference
  implementation uses an atomic `mkdir` lock (`_seq.lock`) with a stale-steal timeout;
  `O_CREAT|O_EXCL` or `flock` are equally valid. Two posters MUST NOT receive the same
  sequence. (This is the defect the flat-folder prototype hit: duplicate `-11`.)
- **Claiming** MUST use an atomic filesystem primitive (`rename`/`os.replace`, atomic
  on NTFS and POSIX within a directory). The loser of a race MUST observe failure.

## 7. Autonomous wait (normative for the "live" profile)

`wait` MUST block in-process (sleep-poll or an OS file-watch) so that **no model
tokens are spent while an agent waits for a reply**. Implementations MUST NOT wait by
re-invoking the model in a loop to "check the folder".

- Default poll interval SHOULD be a few seconds; timeout SHOULD be bounded.
- Implementations MUST work where `inotify` is unavailable (Windows). Sleep-polling is
  the portable baseline; `fswatch`/`chokidar`/`ReadDirectoryChangesW` are optional
  optimizations.

## 8. Cursor semantics

- A cursor is per `(agent, channel)`, storing the highest sequence the agent has
  consumed via `read`/`wait`.
- `read`/`wait` MUST advance the cursor to the channel's current max sequence after
  delivering, so irrelevant intervening messages are not re-scanned.

## 9. Optional governance profile (informative)

For teams that want a human arbiter (the model Turnfile formalizes), agent-chat MAY
layer an OPTIONAL governance profile ON TOP without changing the core:

- A designated `maintainer` role in `_meta.json`.
- Per-action approval bands (auto / notify+veto-window / approval-required).
- A convention that merge/irreversible actions post a `status: needs-approval` message
  and `wait` for a maintainer `status: approved` reply.

The **core protocol is peer and human-optional**; governance is an add-on, not a
requirement. This is the deliberate difference from Turnfile, whose maintainer
authority is mandatory.

## 10. Conformance

A conforming implementation MUST satisfy sections 3–8. The governance profile (9) is
OPTIONAL. Cross-platform autonomous `wait` (7) is REQUIRED for the "live coordination"
profile and OPTIONAL for an "async/audit-only" profile.

## 11. Relationship to prior art (informative)

agent-chat deliberately reuses solved pieces and fills the unsolved combination:

- **Message-with-metadata files** — aligns with `tap` (file-first canonical messages).
- **Atomic claim + git-as-audit** — the pattern `TICK.md` proved (`.tick.lock`,
  every change a commit).
- **SKILL.md cross-tool distribution** — the path `planning-with-files` proved (60+ agents).
- **Optional human governance** — the model `Turnfile` formalizes (here: opt-in, not core).

The unsolved combination agent-chat targets: **peer (no required arbiter) + a folder
of messages across multiple channels + autonomous cross-platform token-free wait**.
See `COMPARISON.md`.

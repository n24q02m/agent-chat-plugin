---
description: Read your peer-agent inbox and post/reply via the agent-chat shared folder
---

Check the agent-chat shared folder for peer-agent messages and handle them.

Your identity is `$AGENT_CHAT_NAME` (set as an env var by the user; ask if it
is unset). All commands below run `python ${CLAUDE_PLUGIN_ROOT}/chat.py <cmd>`.

1. **See what channels exist**: `channels`. Each channel is a separate group
   chat; there may be more than one relevant to you.
2. **Read what's new for you**: `read <channel> --as $AGENT_CHAT_NAME` for
   each channel you care about. This shows only messages addressed to you or
   broadcast, and advances your read cursor. Add `--peek` to look without
   advancing the cursor (use this if you just want a preview, not to consume
   the message).
3. **Reply**: `post <channel> --from $AGENT_CHAT_NAME --to <peer> --reply <seq> --title "..." --body "..."`
   (or `--body-file <path>` for a long markdown body). `<seq>` is the message
   number you are replying to, shown in the `seq:` frontmatter of the message
   you read. Never edit another agent's message file -- always reply with a
   new one.
4. **Wait for a reply without spending tokens**: after posting something that
   needs a response, `wait <channel> --as $AGENT_CHAT_NAME --timeout 900` --
   this blocks in-process (sleep-poll) and burns zero model tokens while
   idle, then prints the new message(s) when they arrive.


Structured task board commands use the same root/channel as messages:

```text
python ${CLAUDE_PLUGIN_ROOT}/chat.py task create <channel> <task-id> \
  --from $AGENT_CHAT_NAME --title "..."
python ${CLAUDE_PLUGIN_ROOT}/chat.py task list <channel>
python ${CLAUDE_PLUGIN_ROOT}/chat.py task show <channel> <task-id>
python ${CLAUDE_PLUGIN_ROOT}/chat.py task update <channel> <task-id> \
  --as $AGENT_CHAT_NAME --status in_progress
python ${CLAUDE_PLUGIN_ROOT}/chat.py task done <channel> <task-id> \
  --as $AGENT_CHAT_NAME
python ${CLAUDE_PLUGIN_ROOT}/chat.py task block <channel> <task-id> \
  --as $AGENT_CHAT_NAME
python ${CLAUDE_PLUGIN_ROOT}/chat.py task release <channel> <task-id> \
  --as $AGENT_CHAT_NAME
```

`create` starts every task as `open`; repeat `--depends-on`, `--files-hint`,
or `--acceptance` for multiple values (comma-separated values are also
accepted). `update` can change `--title`, `--owner`, `--depends-on`,
`--files-hint`, `--acceptance`, `--branch`, or `--status`; nullable owner and
branch can be cleared with `--clear-owner` and `--clear-branch`.

The valid statuses are `open`, `in_progress`, `blocked`, `done`, and
`cancelled`. A task can enter `in_progress` or `done` only if all dependency
records are `done`; the CLI computes this from `tasks/*.json`, not message
body text. Invalid transitions remain rejected. Common stable failures include
`TASK_NOT_FOUND`, `TASK_ALREADY_EXISTS`, `TASK_INVALID_UPDATE`,
`TASK_INVALID_TRANSITION`, `TASK_DEPENDENCY_NOT_READY`,
`TASK_UNKNOWN_DEPENDENCY`, `TASK_DEPENDENCY_CYCLE`, and `TASK_AUDIT_FAILED`.
Task mutations are atomic and produce auditable task events in the channel.
If there is nothing new and nothing to send, say so briefly and stop -- do
not invent work. If you need to start a new group chat, use
`init <channel> --members a,b --topic "..."` first.

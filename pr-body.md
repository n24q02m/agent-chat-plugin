## Spec reference

MCP Phase 2 wave-2, item W2-1 (approved design 2026-09-01): harness-neutral plugin-root resolution for n24q02m/agent-chat-plugin. Non-STABLE source work; stable/release surfaces untouched.

## Change

- `hooks/session_inbox.py`, `hooks/prompt_inbox.py`, `hooks/stop_inbox.py`: plugin-root resolution now prefers the `CLAUDE_PLUGIN_ROOT` env var when set (Claude Code behavior unchanged); when unset/empty, falls back to the script's own directory chain (`hooks/` lives directly under the plugin root — the existing mechanism). When the root still cannot be resolved (`chat.py` not importable), each hook exits 0 with a one-line stderr note instead of crashing the harness session (skip-not-crash).
- `commands/agent-chat.md`: new "Running outside Claude Code" section — repo checkout path (`python /path/to/agent-chat-plugin/chat.py <cmd>`) or pipx-installed CLI (`pipx install agent-chat-plugin` / `uvx --from agent-chat-plugin agent-chat`), plus manual hook wiring by absolute path. All existing `${CLAUDE_PLUGIN_ROOT}` text kept for Claude Code.
- `skills/agent-chat/SKILL.md`: same harness-neutral invocation note under Quick reference. `${CLAUDE_PLUGIN_ROOT}` text kept for Claude Code.
- `tests/test_hooks.py`: both `_run_hook` helpers now pop `CLAUDE_PLUGIN_ROOT` (hermetic runs); new `_run_hook_copy` helper runs a hook copy from a directory with no `chat.py` beside it; 9 new tests across the three hook test classes covering: env-set override (unchanged behavior via env root), unset + unresolvable chain (exit 0, stdout empty, exactly one `[agent-chat]` stderr line), and broken env root (exit 0 + one-line note).

`hooks/hooks.json` is intentionally unchanged: it keeps `${CLAUDE_PLUGIN_ROOT}` (CC contract); other harnesses wire `hooks/*.py` by absolute path, which is now documented and safe (scripts never fail a session).

## Verification

- `python -m unittest discover -s tests -v` => `Ran 184 tests in 12.905s — OK (skipped=1)`; the single skip is the pre-existing platform-gated `POSIX case-sensitive path behavior`.
- `python -m unittest tests.test_hooks -v` => `Ran 25 tests — OK` (16 pre-existing + 9 new).
- Behavioral smoke (repo worktree):
  - `CLAUDE_PLUGIN_ROOT` set to the checkout → hook behaves as before (SessionStart identity warning / inbox notices printed, exit 0).
  - Hook copy in a bare directory, `CLAUDE_PLUGIN_ROOT` unset → `[agent-chat] skipping inbox check: plugin root unresolved (chat.py not importable); hook is non-blocking` on stderr, exit 0.
  - `CLAUDE_PLUGIN_ROOT` pointing at a nonexistent path → same one-line stderr note, exit 0.
- `python -m py_compile hooks/session_inbox.py hooks/prompt_inbox.py hooks/stop_inbox.py` => OK.
- `ruff==0.15.7 check hooks/ tests/test_hooks.py` (CI-pinned version) => `All checks passed!` (local ruff 0.16.5 reports pre-existing extra-rule findings also present on origin/main; CI runs 0.15.7).
- ruff-format: the only "would reformat" finding is a pre-existing call in `session_inbox.py` already unformatted on origin/main; left untouched to keep the diff scoped (CI runs `ruff check`, not format).

## Non-goals

- No packaging changes, no new entrypoints.
- No new MCP tools/actions; no provider or auth-tier changes; no relay/broker/wake work.
- No `${CLAUDE_PLUGIN_ROOT}` removal — Claude Code behavior is unchanged.
- No changes to `hooks/hooks.json` command strings.

## Rollback

Revert the squash commit on main (single self-contained commit, no migrations).

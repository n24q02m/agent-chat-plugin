## 2024-05-24 - CLI Output Alignment Bug
**Learning:** Fixed a visual alignment issue in the CLI `channels` command output where columns were misaligned if all channel names were shorter than the column header "CHANNEL".
**Action:** Always ensure dynamic column width calculation accounts for the length of the column headers, not just the data, to guarantee visual alignment.

## 2026-07-25 - Empty states already exist; keep CLI output ASCII
**Learning:** `chat.py` already prints an empty state on every path that can produce no output -- `cmd_channels` at both of its exits (`chat.py:212`, `chat.py:229`), `cmd_read` when nothing is unread (`chat.py:311`), `cmd_peek` on an empty channel (`chat.py:345`) -- and `require_channel` (`chat.py:64`) already names the recovery command. Four separate PRs proposed appending a call-to-action to those same lines; only the column-width fix addressed something that was actually broken. One of them used an em dash, which does not survive this CLI's own portability claim: the module docstring states it runs identically on Windows, WSL and Linux, and on a Windows console `sys.stdout.encoding` is `cp1252`, where non-ASCII is emitted as a byte that is invalid UTF-8 or raises `UnicodeEncodeError`.
**Action:** Run the command and paste the real before/after terminal output into the PR body as the evidence that a UX defect exists. Keep all CLI output ASCII -- use `-`, never an em dash. Write this journal to `.jules/` in lowercase; `.Jules/` is a separate, unread directory on a case-sensitive filesystem.

## 2024-08-11 - CLI Stdin EOF Prompt
**Learning:** When prompting for input via stdin in a CLI application, instructing the user to "send EOF" is too technical and can lead to confusion. Platform-specific instructions are needed.
**Action:** When reading from stdin and using `sys.stdin.isatty()` to provide a prompt, include platform-specific instructions on how to send EOF (e.g., "press Ctrl-D (or Ctrl-Z and Enter on Windows) to finish").

## 2024-08-12 - CLI Error Handling and Formatting
**Learning:** Raw stack traces from common errors like missing files (OSError) or user cancellation (KeyboardInterrupt) break the illusion of a polished tool. Additionally, printing raw Python data structures (like `['agent-1', 'agent-2']`) instead of formatted strings looks unfinished.
**Action:** Catch `KeyboardInterrupt` globally to exit cleanly (code 130). Catch common I/O errors and map them to application-specific error types with clear messages. Always format lists (e.g., `, `.join()) before presenting them to the user.

## 2024-08-13 - Truncate long strings in CLI tables
**Learning:** Extremely long member lists can push CLI table columns out of alignment and clutter the output, making it unreadable. Additionally, raw lists formatted without spaces (e.g., `alice,bob,charlie`) are visually dense.
**Action:** When displaying lists in CLI tables (e.g., in `cmd_channels`), use an ellipsis (`...`) to truncate the string to a reasonable length instead of a hard slice, preventing abrupt cut-offs. Also format lists with `, ` (comma + space) for better readability.
## 2024-03-24 - Dynamic CLI Column Alignment for Tasks
**Learning:** Hardcoded column spacing in text-based CLIs breaks visually when field content like "OWNER" or "DEPENDS_ON" has varying lengths, making it difficult for users to read table output cleanly.
**Action:** When printing tables to the CLI, calculate the maximum width needed for each column across all rows (including headers), and use `.ljust(width)` to format the text uniformly.

## 2024-05-25 - Self-documenting CLI Interfaces
**Learning:** For Python CLI applications, providing descriptive `help` text for all `argparse` arguments (both positional and optional) significantly improves usability by making the interface self-documenting via the `--help` flag.
**Action:** Always add descriptive `help` parameters to all `add_argument` calls in CLI applications, not just the top-level commands.
## 2026-08-31 - Adding help text for argparse arguments
**Learning:** For Python CLI applications, providing descriptive `help` text for all `argparse` arguments (both positional and optional) significantly improves usability by making the interface self-documenting via the `--help` flag.
**Action:** Always ensure that when defining CLI arguments using `argparse`, both positional and optional parameters are provided with a concise, descriptive `help` string to aid users in understanding the command's requirements and usage.
## 2024-05-14 - Improve argparse help text formatting
**Learning:** For Python CLI applications, providing descriptive `help` text for all `argparse` arguments significantly improves usability. For `add_subparsers` groups specifically, use the `title` argument to replace the default 'positional arguments' header and the `help` argument to describe the command group, making the interface fully self-documenting via the `--help` flag.
**Action:** Always include `title` and `help` arguments when adding subparsers in `argparse` to improve the `--help` output structure and clarity.

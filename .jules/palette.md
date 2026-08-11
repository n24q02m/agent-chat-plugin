## 2024-05-24 - CLI Output Alignment Bug
**Learning:** Fixed a visual alignment issue in the CLI `channels` command output where columns were misaligned if all channel names were shorter than the column header "CHANNEL".
**Action:** Always ensure dynamic column width calculation accounts for the length of the column headers, not just the data, to guarantee visual alignment.

## 2026-07-25 - Empty states already exist; keep CLI output ASCII
**Learning:** `chat.py` already prints an empty state on every path that can produce no output -- `cmd_channels` at both of its exits (`chat.py:212`, `chat.py:229`), `cmd_read` when nothing is unread (`chat.py:311`), `cmd_peek` on an empty channel (`chat.py:345`) -- and `require_channel` (`chat.py:64`) already names the recovery command. Four separate PRs proposed appending a call-to-action to those same lines; only the column-width fix addressed something that was actually broken. One of them used an em dash, which does not survive this CLI's own portability claim: the module docstring states it runs identically on Windows, WSL and Linux, and on a Windows console `sys.stdout.encoding` is `cp1252`, where non-ASCII is emitted as a byte that is invalid UTF-8 or raises `UnicodeEncodeError`.
**Action:** Run the command and paste the real before/after terminal output into the PR body as the evidence that a UX defect exists. Keep all CLI output ASCII -- use `-`, never an em dash. Write this journal to `.jules/` in lowercase; `.Jules/` is a separate, unread directory on a case-sensitive filesystem.

## 2024-08-11 - CLI Stdin EOF Prompt
**Learning:** When prompting for input via stdin in a CLI application, instructing the user to "send EOF" is too technical and can lead to confusion. Platform-specific instructions are needed.
**Action:** When reading from stdin and using `sys.stdin.isatty()` to provide a prompt, include platform-specific instructions on how to send EOF (e.g., "press Ctrl-D (or Ctrl-Z and Enter on Windows) to finish").
## 2026-08-11 - Use ellipses for text truncation in CLI listings
**Learning:** When text is truncated with a hard slice (`[:40]`), users may assume it is a formatting error or that the text ends abruptly.
**Action:** Use an ellipsis (`...`) instead to clearly signal to the user that text was shortened to fit constraints.

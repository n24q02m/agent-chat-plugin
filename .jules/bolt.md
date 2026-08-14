## 2024-06-25 - Frontmatter Parsing Pitfall
**Learning:** Using `Path.read_text()` to parse frontmatter from markdown files loads the entire file contents into memory. If message bodies are large, this becomes a major performance bottleneck since only the first few lines are needed.
**Action:** Always stream files line-by-line (e.g., using `path.open()` and an iterator) when parsing headers or frontmatter, stopping as soon as the relevant section is extracted to avoid O(N) memory allocation and parsing where N is the total file size.

## 2026-07-25 - The frontmatter read is done; measure before proposing the next one
**Learning:** Seven PRs proposed the same `parse_frontmatter` streaming rewrite, none with a measurement. The change is now in (`chat.py:78`). Measured afterwards on the real corpus (82 messages, 161 KB, median message 1.8 KB): 21.82 ms -> 19.14 ms per full scan, a 2.7 ms saving. It only becomes interesting at sizes this repo does not currently produce -- 50 files of 200 KB go from 86 ms to 8 ms. `_seq_from_name` (`chat.py:68`) is a bounded regex over a filename and is not worth rewriting; a PR claiming "~2.5x faster" for it shipped no numbers.
**Action:** Put a before/after measurement in the PR body, taken over this repo's own corpus (`$AGENT_CHAT_ROOT/*/*.md`, median of at least 20 runs), and propose the change only when that measured delta is material. The paths worth measuring are the ones called per message: the `cmd_wait` poll loop (`chat.py:320`) and `hooks/session_inbox.py:60`, which runs at every SessionStart.

## 2024-08-10 - O(N log N) bottlenecks in polling loops
**Learning:** Polling and counting operations like `cmd_wait` and `session_inbox.py` were calling `message_files(chan)` which globs and then sorts *all* `.md` files on every iteration. On large channels, this O(N log N) operation caused measurable CPU overhead per tick just to filter out messages older than the cursor.
**Action:** When polling or counting messages, use a plain O(N) `chan.glob("*.md")` scan to filter out unread messages first, and only sort the resulting tiny subset (the unread messages) when necessary.

## 2024-11-20 - Finding top N messages without full sort
**Learning:** `cmd_peek` was using `message_files(d)[-a.n:]`, which globs and fully sorts all files just to slice the top `N`. For channels with thousands of messages, this full O(N log N) sort is inefficient.
**Action:** When finding the top `N` highest sequence numbers from a large set of messages, use an O(N log K) min-heap approach (e.g., via `heapq`) rather than fully sorting all items. This same principle of replacing `message_files(d)` with an O(N) glob applies to simple counting scenarios like `cmd_roster`.

## 2024-08-14 - os.scandir vs Path.glob in tight loops
**Learning:** `Path.glob()` instantiates a `Path` object for every matched file, which causes significant CPU and memory overhead when scanning directories with thousands of files.
**Action:** In polling loops (like `cmd_wait`) or frequent hook executions (like `session_inbox.py`), prefer `os.scandir()` which yields lightweight `DirEntry` objects. Only instantiate `Path` objects for the files that actually pass the filtering logic.

## 2024-08-16 - os.scandir vs Path.glob beyond wait loops
**Learning:** `Path.glob()` instantiates a `Path` object for every matched file, causing CPU and memory overhead not just in polling loops but anywhere we do frequent directory scans. Profiling showed that utility functions like `cmd_channels`, `cmd_roster`, `cmd_read`, `max_seq`, `_next_seq`, and `message_files` also suffered from this overhead when operating on channels with thousands of messages.
**Action:** Replace `Path.glob("*.md")` with `os.scandir(chan)` in any function that iterates over a directory simply to count files or parse filenames (like sequence numbers). Only instantiate `Path` objects for the entries that actually need them (e.g. for reading frontmatter).

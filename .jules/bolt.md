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

## 2024-11-20 - Avoid Path.glob for shallow directory structural checks
**Learning:** Using `Path.glob("*/_meta.json")` to discover subdirectories containing a specific file instantiates a large number of internal objects and performs slower path matching compared to a direct filesystem scan.
**Action:** When finding directories based on the presence of a specific file (e.g., `_meta.json` in a channel folder), use `os.scandir()` combined with `os.path.exists()` to check for the file directly. This avoids unnecessary memory allocations and is significantly faster for workspaces with many directories.

## 2024-11-20 - Skipping redundant directory scans in poll loops
**Learning:** In tight polling loops like `cmd_wait`, scanning the directory using `os.scandir()` on every tick to find new messages becomes a CPU bottleneck for channels with thousands of messages (e.g., dropping from 2.5 million function calls down to 640k function calls in a 3-second wait loop of 10,000 files).
**Action:** When constantly polling a directory for new files, read the directory's `st_mtime` via `os.stat()` (which updates when files are added or removed) and only perform the full `os.scandir()` scan when the `st_mtime` changes. Wrap the `stat()` call in `try...except OSError` to fail safely if the OS doesn't support it or errors out.

## 2024-05-15 - Refactoring Path.glob() to os.scandir()
**Learning:** `Path.glob()` instantiates a `Path` object for every matched file, causing significant overhead in loops when filtering files (like matching sequences and evaluating applicability). Replacing it with `os.scandir()` prevents unnecessary instantiation of Path objects for all files since `DirEntry` provides lightweight access to file names and attributes. Wrapping it in a `try...except OSError: pass` block is required, since `os.scandir()` raises an exception if the directory does not exist, unlike `Path.glob()` which yields an empty generator safely.
**Action:** Always prefer `os.scandir()` combined with `try...except OSError` over `Path.glob()` for polling loops and frequent executions to improve speed while maintaining fault tolerance.

## 2024-11-20 - Fast Sequence Number Parsing with string methods
**Learning:** `_seq_from_name` was using `re.match` which incurs overhead from the regex engine. In hot paths like `max_seq` where this function is called on potentially tens of thousands of files in a directory scan, this regex overhead creates a measurable performance bottleneck. Using `str.split()` and `.isdigit()` achieves the exact same parsing rules for sequence numbers without the regex engine overhead.
**Action:** For simple prefix parsing in hot loops (like extracting leading digits before a delimiter), avoid uncompiled regular expressions and use native string methods like `split()` and `.isdigit()`, which benchmarked ~37% faster for this specific operation.

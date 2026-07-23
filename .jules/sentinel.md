## 2024-11-20 - Path Traversal via Python `pathlib.Path` Concatenation
**Vulnerability:** Arbitrary file read/write (Path Traversal) via `channel` and `task` arguments in `chat.py`.
**Learning:** In Python's `pathlib.Path`, using `base_path / user_input` is dangerous if `user_input` is not sanitized. If `user_input` is an absolute path (e.g., `/etc/passwd`), it completely replaces `base_path`. If it contains relative traversal elements (`..`), it can resolve outside `base_path`.
**Prevention:** Always validate and sanitize user input before concatenating it with paths. For filenames or single directory names, reject paths containing slashes (`/`, `\`) or `.` / `..`. Alternatively, resolve the resulting path and verify it `is_relative_to(base_path)`.

## 2025-01-20 - Path Traversal in CLI Channel Creation
**Vulnerability:** The `chat.py` CLI `channel_dir` function was vulnerable to path traversal because it did not validate the constructed channel path against its root path, allowing arbitrary directory access (e.g., `chat.py init /etc` or `chat.py init ../../../tmp/foo`).
**Learning:** Concatenating user-controlled directory components without validation using `pathlib` allows escaping the root directory boundaries. A simple slash (`/`) or `..` breaks out.
**Prevention:** Always use `.resolve().is_relative_to()` with the allowed base path to secure dynamically-constructed paths and ensure the resulting directory does not equal the root directory.

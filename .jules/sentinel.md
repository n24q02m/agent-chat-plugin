## 2024-07-21 - Path Traversal via pathlib.Path Division
**Vulnerability:** Path traversal and arbitrary absolute path access via the `root / channel` operation in `channel_dir(root: Path, channel: str) -> Path`. Since `channel` was user-controlled, passing `../foo` or `/etc` allowed manipulating the filesystem outside of the intended root directory.
**Learning:** `pathlib.Path(root) / channel` is unsafe if `channel` starts with `/` (it replaces the entire path) or contains `../` (allowing upward traversal).
**Prevention:** Always use `.resolve()` on the combined path and check `.is_relative_to(root.resolve())` to ensure the final path remains within the intended boundaries.

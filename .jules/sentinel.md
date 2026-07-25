## 2024-07-20 - [Path Traversal in CLI Arguments]
**Vulnerability:** The application blindly joined user-provided channel and task arguments directly with the root path using `pathlib.Path(root) / channel`. This allowed path traversal (e.g. `../`) allowing users to access files outside the intended directories.
**Learning:** `pathlib` operator `/` does not magically prevent directory traversal if relative path strings like `../` are passed into it. Any user-controlled file path component needs strict validation.
**Prevention:** Implement strict string-level validation against slashes (`/`, `\`) and traversal symbols (`.`, `..`) for arbitrary file and directory name inputs from CLI flags, ensuring they contain only valid base names before joining them to any root directories.

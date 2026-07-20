## 2024-05-18 - Prevent Path Traversal in CLI Tools
**Vulnerability:** The application allowed path traversal elements (e.g. `../` and `/abs/path`) in `channel` and `task` names, allowing malicious users to read, create or replace arbitrary files outside of the defined chat workspace when using CLI commands such as `init`, `read`, or `claim`.
**Learning:** Functions using input parameters for filesystem paths must securely validate that inputs cannot escape the intended directory root.
**Prevention:** Always validate that external file and folder parameters are simple basenames without traversal symbols (`/`, `\`, `.` or `..`) before concatenating them with a base directory using paths libraries.

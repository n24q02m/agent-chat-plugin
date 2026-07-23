## 2025-02-27 - Lazy reading markdown files for frontmatter
**Learning:** Loading entire markdown files into memory using `path.read_text()` and `.splitlines()` is extremely slow for large messages just to extract a small frontmatter block at the top. This can cause massive latency and memory bloat.
**Action:** When extracting yaml frontmatter from markdown files, use `with open(...)` to lazily read the file line-by-line and break early once the frontmatter is parsed. This dramatically speeds up parsing large files.

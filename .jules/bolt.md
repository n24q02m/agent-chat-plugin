## 2024-06-25 - Frontmatter Parsing Pitfall
**Learning:** Using `Path.read_text()` to parse frontmatter from markdown files loads the entire file contents into memory. If message bodies are large, this becomes a major performance bottleneck since only the first few lines are needed.
**Action:** Always stream files line-by-line (e.g., using `path.open()` and an iterator) when parsing headers or frontmatter, stopping as soon as the relevant section is extracted to avoid O(N) memory allocation and parsing where N is the total file size.

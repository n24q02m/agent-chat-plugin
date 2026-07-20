## 2024-07-20 - Streaming Markdown Frontmatter Parsing
**Learning:** `parse_frontmatter` was reading the entire file into memory `path.read_text()` just to parse the frontmatter, which is very inefficient for large markdown files (like those with long LLM generated content or log outputs).
**Action:** Use an iterator over the file lines (`path.open()`) to only read until the closing `---`, preventing O(N) memory allocation and drastically speeding up file reading for large files. This fits the < 50 line optimization constraint perfectly and prevents unnecessary IO for large files.

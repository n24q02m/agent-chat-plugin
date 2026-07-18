## 2024-05-24 - Do not use read_text() to parse headers on text files
**Learning:** For LLM text outputs (or large files generally) that use frontmatter, reading the entire file into memory using `path.read_text()` or `splitlines()` consumes unnecessary time and memory to parse the full output when only the header is needed.
**Action:** Always parse lazily using `with open(path)` line by line to break early as soon as the frontmatter section is complete, avoiding loading the entire file into memory.

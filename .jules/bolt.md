## 2024-07-22 - Lazy Loading Frontmatter
**Learning:** Loading entire markdown files into memory just to parse small YAML frontmatter causes massive performance issues when messages have large bodies, as `read_text().splitlines()` loads the whole content.
**Action:** When extracting metadata from headers, always use a line-by-line file iterator (`with open() as f: for line in f:`) and break early once the frontmatter section ends.

## 2024-07-24 - Lazy line-by-line reading for file-based message bus
**Learning:** When using markdown files as a message bus for agents, reading the entire file into memory just to parse the routing header (frontmatter) causes severe latency and memory bloat on large messages.
**Action:** Always use lazy line-by-line reading (e.g., `with open(...) as f: f.readline()`) for routing decisions in file-based queues to stop reading as soon as the relevant metadata is extracted, ignoring the body entirely.

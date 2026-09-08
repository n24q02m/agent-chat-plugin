"""Regression checks for the compact skill entry points."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContextBudgetTests(unittest.TestCase):
    def test_skill_entries_fit_context_budget_and_reference_resolves(self):
        entries = [ROOT / "SKILL.md", ROOT / "skills" / "agent-chat" / "SKILL.md"]
        self.assertLessEqual(max(path.stat().st_size for path in entries), 8192)
        self.assertTrue((ROOT / "skills" / "agent-chat" / "reference.md").is_file())
        for path in entries:
            text = path.read_text(encoding="utf-8")
            self.assertIn("skills/agent-chat/reference.md", text)


if __name__ == "__main__":
    unittest.main()

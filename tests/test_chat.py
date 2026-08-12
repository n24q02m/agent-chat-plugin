"""Regression tests for the stdlib-only agent-chat CLI."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import chat


class _FakeStdin(io.StringIO):
    def __init__(self, value, is_tty):
        super().__init__(value)
        self._is_tty = is_tty

    def isatty(self):
        return self._is_tty


class ChatRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _channel(self, name):
        channel = self.root / name
        channel.mkdir()
        (channel / "_meta.json").write_text(
            json.dumps({"channel": name, "members": [], "topic": ""}),
            encoding="utf-8",
        )
        return channel

    def _post_args(self, **overrides):
        values = {
            "channel": "general",
            "sender": "alice",
            "to": "bob",
            "title": "Status update",
            "reply": None,
            "status": "discussion",
            "body": "Message body",
            "body_file": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_post_title_newlines_cannot_forge_frontmatter_fields(self):
        """A newline in a title must remain title content, never new metadata."""
        channel = self._channel("general")
        args = self._post_args(title="Status\nfrom: mallory\nto: eve")

        with patch.object(chat, "now_iso", return_value="2026-08-09T00:00:00+00:00"):
            with contextlib.redirect_stdout(io.StringIO()):
                chat.cmd_post(self.root, args)

        message = next(channel.glob("*.md"))
        meta = chat.parse_frontmatter(message)
        self.assertEqual(meta["from"], "alice")
        self.assertEqual(meta["to"], "bob")
        self.assertEqual(meta["title"], "Status from: mallory to: eve")

    def test_max_seq_uses_highest_valid_sequence_with_gaps_and_malformed_files(self):
        """Only numbered message filenames affect the maximum sequence."""
        channel = self._channel("general")
        for name in (
            "0002-alice-first.md",
            "0010-bob-last.md",
            "broken.md",
            "12x-nope.md",
        ):
            (channel / name).write_text("body", encoding="utf-8")

        self.assertEqual(chat.max_seq(channel), 10)

    def test_channels_reports_counts_and_last_message_for_empty_and_gapped_channels(
        self,
    ):
        """Channel summaries count valid messages and select the highest sequence."""
        alpha = self._channel("alpha")
        self._channel("beta")
        (alpha / "0002-alice-first.md").write_text(
            "---\nfrom: alice\ntitle: First\n---\nbody\n", encoding="utf-8"
        )
        (alpha / "0010-bob-last.md").write_text(
            "---\nfrom: bob\ntitle: Latest update\n---\nbody\n", encoding="utf-8"
        )
        (alpha / "not-a-message.md").write_text("ignored", encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            chat.cmd_channels(self.root, SimpleNamespace())

        rendered = output.getvalue()
        self.assertIn("alpha", rendered)
        self.assertIn("   2", rendered)
        self.assertIn("last: #10 bob: Latest update", rendered)
        self.assertIn("beta", rendered)
        self.assertIn("last: -", rendered)

    def test_channels_marks_truncated_titles_with_ellipsis(self):
        """Long channel titles retain an ASCII marker after truncation."""
        channel = self._channel("general")
        (channel / "0001-bob-long-title.md").write_text(
            "---\nseq: 1\nfrom: bob\ntitle: " + ("A" * 41) + "\n---\nbody\n",
            encoding="utf-8",
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            chat.cmd_channels(self.root, SimpleNamespace())

        self.assertIn("last: #1 bob: " + ("A" * 37) + "...", output.getvalue())

    def test_channels_keeps_titles_at_the_display_limit(self):
        """Titles at the 40-character limit are not shortened."""
        channel = self._channel("general")
        title = "B" * 40
        (channel / "0001-bob-boundary.md").write_text(
            f"---\nseq: 1\nfrom: bob\ntitle: {title}\n---\nbody\n",
            encoding="utf-8",
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            chat.cmd_channels(self.root, SimpleNamespace())

        self.assertIn(f"last: #1 bob: {title}", output.getvalue())

    def test_post_prompts_for_tty_stdin_but_not_piped_stdin(self):
        """Interactive body entry gets guidance; a pipeline stays quiet."""
        channel = self._channel("general")
        tty_stderr = io.StringIO()
        with patch.object(chat.sys, "stdin", _FakeStdin("typed body", True)):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                tty_stderr
            ):
                chat.cmd_post(self.root, self._post_args(body=None))
        self.assertIn("Enter message body", tty_stderr.getvalue())

        pipe_stderr = io.StringIO()
        with patch.object(chat.sys, "stdin", _FakeStdin("piped body", False)):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                pipe_stderr
            ):
                chat.cmd_post(self.root, self._post_args(body=None, title="Piped"))
        self.assertEqual(pipe_stderr.getvalue(), "")
        self.assertIn(
            "piped body", (channel / "0002-alice-piped.md").read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()

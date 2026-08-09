"""Behavior tests for the non-blocking agent-chat Claude Code hooks."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROMPT_INBOX_HOOK = REPOSITORY_ROOT / "hooks" / "prompt_inbox.py"
STOP_INBOX_HOOK = REPOSITORY_ROOT / "hooks" / "stop_inbox.py"
SESSION_INBOX_HOOK = REPOSITORY_ROOT / "hooks" / "session_inbox.py"


class PromptInboxHookTests(unittest.TestCase):
    HOOK = PROMPT_INBOX_HOOK

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _channel(self, name="general"):
        channel = self.root / name
        channel.mkdir()
        (channel / "_meta.json").write_text(
            json.dumps({"channel": name, "members": [], "topic": ""}),
            encoding="utf-8",
        )
        return channel

    def _message(self, channel, sequence, sender, recipient="all"):
        (channel / f"{sequence:04d}-{sender}-message.md").write_text(
            "---\n"
            f"seq: {sequence}\n"
            f"from: {sender}\n"
            f"to: {recipient}\n"
            f"channel: {channel.name}\n"
            "title: Message\n"
            "---\n"
            "body\n",
            encoding="utf-8",
        )

    def _run_hook(self, **environment):
        env = os.environ.copy()
        for name in ("AGENT_CHAT_NAME", "AGENT_CHAT_ROOT", "AGENT_CHAT_CHANNELS"):
            env.pop(name, None)
        env.update(environment)
        return subprocess.run(
            [sys.executable, str(self.HOOK)],
            capture_output=True,
            check=False,
            encoding="utf-8",
            env=env,
        )

    def test_stays_quiet_when_there_are_no_messages(self):
        """Adding no peer message must not produce a prompt notice."""
        self._channel()

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_reports_relevant_messages_above_the_cursor_by_channel_and_count(self):
        """Removing relevance filtering or sequence checks must change this notice."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")
        self._message(channel, 2, "carol", "alice")
        (channel / ".cursors").mkdir()
        (channel / ".cursors" / "alice.txt").write_text("0", encoding="utf-8")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertIn("review", result.stdout)
        self.assertIn("2", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_ignores_messages_for_another_agent_and_its_own_messages(self):
        """A recipient or sender filtering regression must not wake this agent."""
        channel = self._channel()
        self._message(channel, 1, "bob", "carol")
        self._message(channel, 2, "alice", "all")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_returns_quietly_without_an_identity_or_when_root_is_missing(self):
        """Unconfigured prompt hooks must never obstruct Claude Code."""
        no_identity = self._run_hook(AGENT_CHAT_ROOT=str(self.root))
        missing_root = self._run_hook(
            AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root / "missing")
        )

        for result in (no_identity, missing_root):
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_leaves_the_read_cursor_unchanged(self):
        """Writing a cursor here would hide a message from chat.py read."""
        channel = self._channel()
        self._message(channel, 3, "bob", "alice")
        cursor = channel / ".cursors" / "alice.txt"
        cursor.parent.mkdir()
        cursor.write_text("2", encoding="utf-8")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(cursor.read_text(encoding="utf-8"), "2")

    def test_malformed_configured_channel_still_exits_zero(self):
        """An invalid configured channel must be a non-blocking hook error."""
        result = self._run_hook(
            AGENT_CHAT_NAME="alice",
            AGENT_CHAT_ROOT=str(self.root),
            AGENT_CHAT_CHANNELS="../invalid",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


class StopInboxHookTests(PromptInboxHookTests):
    HOOK = STOP_INBOX_HOOK

    def test_warning_says_the_turn_is_ending_with_channel_and_count(self):
        """Removing the Stop-specific warning context must fail this contract."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertIn("turn is ending", result.stdout)
        self.assertIn("review", result.stdout)
        self.assertIn("1", result.stdout)
        self.assertEqual(result.stderr, "")


class SessionInboxHookTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _channel(self, name="general"):
        channel = self.root / name
        channel.mkdir()
        (channel / "_meta.json").write_text(
            json.dumps({"channel": name, "members": [], "topic": ""}),
            encoding="utf-8",
        )
        return channel

    def _message(self, channel, sequence, sender, recipient="all"):
        (channel / f"{sequence:04d}-{sender}-message.md").write_text(
            "---\n"
            f"seq: {sequence}\n"
            f"from: {sender}\n"
            f"to: {recipient}\n"
            f"channel: {channel.name}\n"
            "title: Message\n"
            "---\n"
            "body\n",
            encoding="utf-8",
        )

    def _run_hook(self, **environment):
        env = os.environ.copy()
        for name in ("AGENT_CHAT_NAME", "AGENT_CHAT_ROOT", "AGENT_CHAT_CHANNELS"):
            env.pop(name, None)
        env.update(environment)
        return subprocess.run(
            [sys.executable, str(SESSION_INBOX_HOOK)],
            capture_output=True,
            check=False,
            encoding="utf-8",
            env=env,
        )

    def test_explains_missing_identity_when_a_chat_channel_exists(self):
        """Returning before root discovery must not hide an unset identity."""
        self._channel()

        result = self._run_hook(AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "[agent-chat] Inbox hook disabled: identity is unset; set AGENT_CHAT_NAME.\n",
        )
        self.assertEqual(result.stderr, "")

    def test_stays_quiet_without_an_identity_when_the_chat_root_is_missing(self):
        """An unconfigured chat installation must not produce an identity warning."""
        result = self._run_hook(AGENT_CHAT_ROOT=str(self.root / "missing"))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_keeps_configured_identity_inbox_notifications(self):
        """Identity diagnostics must not replace existing unread-message summaries."""
        channel = self._channel("review")
        self._message(channel, 1, "bob", "alice")

        result = self._run_hook(AGENT_CHAT_NAME="alice", AGENT_CHAT_ROOT=str(self.root))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "[agent-chat] alice has unread peer messages: #review (1). "
            "Run /agent-chat to read/reply.\n",
        )
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()

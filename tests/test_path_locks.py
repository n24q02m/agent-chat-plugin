"""Focused tests for normalized, auditable channel path locks."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import chat
from agent_chat.path_locks import PathLockError, PathLockStore


class PathLockStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        chat.cmd_init(
            self.root,
            SimpleNamespace(channel="review", members="alice,bob", topic="Path locks"),
        )
        self.channel = self.root / "review"
        (self.channel / "src").mkdir()
        (self.channel / "src" / "main.py").write_text("pass\n", encoding="utf-8")
        self.store = PathLockStore(self.channel, root=self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_file_file_collision_stores_normalized_and_display_paths_atomically(self):
        record = self.store.lock("alice", ["src/main.py"], lease_seconds=60)

        with self.assertRaises(PathLockError) as error:
            self.store.lock("bob", ["src/main.py"], lease_seconds=60)

        self.assertEqual(error.exception.code, "PATH_LOCK_CONFLICT")
        self.assertEqual(record.paths[0].normalized_path, "src/main.py")
        self.assertEqual(record.paths[0].display_path, "src/main.py")
        lock_files = list((self.channel / "locks").glob("*.json"))
        self.assertEqual(len(lock_files), 1)
        raw = lock_files[0].read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"))
        self.assertEqual(json.loads(raw)["paths"][0]["normalized_path"], "src/main.py")

    def test_directory_file_overlap_conflicts(self):
        self.store.lock("alice", ["src"], lease_seconds=60)

        with self.assertRaises(PathLockError) as error:
            self.store.lock("bob", ["src/main.py"], lease_seconds=60)

        self.assertEqual(error.exception.code, "PATH_LOCK_CONFLICT")
        self.assertEqual(error.exception.details["conflicts"][0]["owner"], "alice")

    def test_case_normalization_follows_platform_semantics(self):
        first = self.store.lock("alice", ["src/Main.py"], lease_seconds=60)
        if os.name == "nt":
            with self.assertRaises(PathLockError) as error:
                self.store.lock("bob", ["SRC/main.PY"], lease_seconds=60)
            self.assertEqual(error.exception.code, "PATH_LOCK_CONFLICT")
            self.assertEqual(first.paths[0].normalized_path, "src/main.py")
        else:
            second = self.store.lock("bob", ["SRC/main.PY"], lease_seconds=60)
            self.assertNotEqual(
                first.paths[0].normalized_path, second.paths[0].normalized_path
            )

    def test_parent_traversal_and_absolute_paths_are_rejected(self):
        for requested in ("../outside.txt", "src/../outside.txt", str(self.root / "outside.txt")):
            with self.subTest(requested=requested):
                with self.assertRaises(PathLockError) as error:
                    self.store.lock("alice", [requested], lease_seconds=60)
                self.assertEqual(error.exception.code, "PATH_LOCK_INVALID_PATH")

    def test_symlink_escape_is_rejected(self):
        outside = Path(self.temp_dir.name).parent / (Path(self.temp_dir.name).name + "-outside")
        outside.mkdir()
        try:
            link = self.channel / "escape"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink creation unavailable on this platform: {error}")

            with self.assertRaises(PathLockError) as error:
                self.store.lock("alice", ["escape/secret.txt"], lease_seconds=60)
            self.assertEqual(error.exception.code, "PATH_LOCK_PATH_OUTSIDE_WORKSPACE")
        finally:
            if outside.exists():
                outside.rmdir()

    def test_stale_recovery_records_previous_owner_expiry_reason_and_audit(self):
        current = [datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)]
        store = PathLockStore(self.channel, root=self.root, clock=lambda: current[0])
        original = store.lock("alice", ["src/main.py"], lease_seconds=1)
        current[0] = datetime(2026, 8, 21, 12, 0, 2, tzinfo=timezone.utc)

        recovered = store.recover(
            original.lock_id,
            "bob",
            "alice session expired",
            lease_seconds=60,
        )

        self.assertEqual(recovered.owner, "bob")
        self.assertEqual(recovered.previous_owner, "alice")
        self.assertEqual(recovered.previous_expires_at, original.expires_at)
        self.assertEqual(recovered.recovery_reason, "alice session expired")
        messages = [
            path.read_text(encoding="utf-8")
            for path in self.channel.glob("[0-9][0-9][0-9][0-9]-*.md")
        ]
        self.assertTrue(
            any(
                "path.lock.recovered" in body
                and "alice session expired" in body
                and '"previous_owner": "alice"' in body
                for body in messages
            )
        )

    def test_owner_only_unlock_and_audit(self):
        record = self.store.lock("alice", ["src/main.py"], lease_seconds=60)

        with self.assertRaises(PathLockError) as error:
            self.store.unlock(record.lock_id, "bob")

        self.assertEqual(error.exception.code, "PATH_LOCK_OWNER_MISMATCH")
        self.store.unlock(record.lock_id, "alice")
        self.assertEqual(self.store.list(), [])
        messages = [
            path.read_text(encoding="utf-8")
            for path in self.channel.glob("[0-9][0-9][0-9][0-9]-*.md")
        ]
        self.assertTrue(any("path.lock.unlocked" in body for body in messages))

    def test_cli_lock_check_unlock_and_recover_commands(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            chat.main(
                [
                    "--root",
                    str(self.root),
                    "lock",
                    "review",
                    "src/main.py",
                    "--as",
                    "alice",
                    "--lease-seconds",
                    "60",
                ]
            )
        lock_id = output.getvalue().strip().splitlines()[-1].split()[1]
        self.assertTrue(lock_id)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            chat.main(
                [
                    "--root",
                    str(self.root),
                    "check",
                    "review",
                    "src/main.py",
                ]
            )
        self.assertIn("locked", output.getvalue())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            chat.main(
                [
                    "--root",
                    str(self.root),
                    "unlock",
                    "review",
                    lock_id,
                    "--as",
                    "alice",
                ]
            )
        self.assertIn("unlocked", output.getvalue())


    def test_cli_recover_requires_reason_and_reports_prior_owner(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            chat.main(
                [
                    "--root",
                    str(self.root),
                    "lock",
                    "review",
                    "src/main.py",
                    "--as",
                    "alice",
                    "--lease-seconds",
                    "60",
                ]
            )
        lock_id = output.getvalue().strip().split()[1]
        lock_path = next((self.channel / "locks").glob("*.json"))
        record = json.loads(lock_path.read_text(encoding="utf-8"))
        record["expires_at"] = "2000-01-01T00:00:00+00:00"
        lock_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            chat.main(
                [
                    "--root",
                    str(self.root),
                    "recover",
                    "review",
                    lock_id,
                    "--as",
                    "bob",
                    "--reason",
                    "alice session expired",
                    "--lease-seconds",
                    "60",
                ]
            )
        self.assertIn("previous_owner=alice", output.getvalue())
        self.assertIn("alice session expired", output.getvalue())

if __name__ == "__main__":
    unittest.main()

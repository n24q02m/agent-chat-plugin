"""Focused Task 2 tests for the typed task model and atomic store."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import chat
from agent_chat.task_model import (
    TASK_FIELDS,
    TaskRecord,
    TaskValidationError,
)
from agent_chat.task_store import TaskStore


TIMESTAMP = "2026-08-21T12:00:00+00:00"


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        chat.cmd_init(
            self.root,
            SimpleNamespace(channel="review", members="alice,bob", topic="Task board"),
        )
        self.channel = self.root / "review"
        self.store = TaskStore(self.channel)

    def tearDown(self):
        self.temp_dir.cleanup()

    def task_data(self, **overrides):
        data = {
            "id": "T-0001",
            "channel": "review",
            "title": "Document the review flow",
            "status": "open",
            "owner": None,
            "created_by": "alice",
            "depends_on": [],
            "files_hint": ["docs/review.md"],
            "acceptance": ["Review is documented"],
            "lease_expires_at": None,
            "branch": None,
            "updated_at": TIMESTAMP,
        }
        data.update(overrides)
        return data

    def make_task(self, **overrides):
        return TaskRecord.from_dict(self.task_data(**overrides))

    def test_task_record_preserves_exact_documented_shape(self):
        task = self.make_task()

        self.assertEqual(tuple(task.to_dict()), TASK_FIELDS)
        self.assertEqual(
            set(task.to_dict()),
            {
                "id",
                "channel",
                "title",
                "status",
                "owner",
                "created_by",
                "depends_on",
                "files_hint",
                "acceptance",
                "lease_expires_at",
                "branch",
                "updated_at",
            },
        )

    def test_missing_or_unknown_fields_have_stable_codes(self):
        missing = self.task_data()
        del missing["acceptance"]
        with self.assertRaises(TaskValidationError) as missing_error:
            TaskRecord.from_dict(missing)
        self.assertEqual(missing_error.exception.code, "TASK_REQUIRED_FIELD_MISSING")

        unknown = self.task_data(extra="not allowed")
        with self.assertRaises(TaskValidationError) as unknown_error:
            TaskRecord.from_dict(unknown)
        self.assertEqual(unknown_error.exception.code, "TASK_UNKNOWN_FIELD")

    def test_all_documented_statuses_are_valid(self):
        for status in ("open", "in_progress", "blocked", "done", "cancelled"):
            with self.subTest(status=status):
                self.assertEqual(self.make_task(status=status).status, status)

    def test_invalid_transition_is_rejected_without_changing_record(self):
        self.store.create(self.make_task(), actor="alice")

        with self.assertRaises(TaskValidationError) as error:
            self.store.update("T-0001", actor="alice", status="done")

        self.assertEqual(error.exception.code, "TASK_INVALID_TRANSITION")
        self.assertEqual(self.store.show("T-0001").status, "open")

    def test_dependency_reference_must_exist(self):
        with self.assertRaises(TaskValidationError) as error:
            self.store.create(
                self.make_task(id="T-0002", depends_on=["T-9999"]), actor="alice"
            )

        self.assertEqual(error.exception.code, "TASK_UNKNOWN_DEPENDENCY")
        self.assertFalse((self.channel / "tasks" / "T-0002.json").exists())

    def test_dependency_cycles_are_rejected(self):
        self.store.create(self.make_task(id="T-0001"), actor="alice")
        self.store.create(
            self.make_task(id="T-0002", depends_on=["T-0001"]), actor="alice"
        )

        with self.assertRaises(TaskValidationError) as error:
            self.store.update("T-0001", actor="alice", depends_on=["T-0002"])

        self.assertEqual(error.exception.code, "TASK_DEPENDENCY_CYCLE")
        self.assertEqual(self.store.show("T-0001").depends_on, [])

    def test_timestamps_require_iso8601_offsets(self):
        for value in ("not-a-timestamp", "2026-08-21T12:00:00"):
            with self.subTest(value=value):
                with self.assertRaises(TaskValidationError) as error:
                    TaskRecord.from_dict(self.task_data(updated_at=value))
                self.assertEqual(error.exception.code, "TASK_INVALID_TIMESTAMP")

    def test_files_hint_must_stay_inside_channel_workspace(self):
        for path in ("../outside.txt", "/tmp/outside.txt", "C:\\outside.txt"):
            with self.subTest(path=path):
                with self.assertRaises(TaskValidationError) as error:
                    self.store.create(
                        self.make_task(id="T-" + str(len(path)), files_hint=[path]),
                        actor="alice",
                    )
                self.assertEqual(error.exception.code, "TASK_PATH_OUTSIDE_WORKSPACE")

    def test_symlinked_files_hint_cannot_escape_workspace(self):
        outside = Path(self.temp_dir.name).parent / (self.root.name + "-outside")
        outside.mkdir()
        link = self.channel / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        try:
            with self.assertRaises(TaskValidationError) as error:
                self.store.create(
                    self.make_task(files_hint=["linked/secret.txt"]), actor="alice"
                )
            self.assertEqual(error.exception.code, "TASK_PATH_OUTSIDE_WORKSPACE")
        finally:
            link.unlink(missing_ok=True)
            outside.rmdir()

    def test_create_collision_is_deterministic_and_preserves_existing_record(self):
        original = self.store.create(self.make_task(), actor="alice")
        path = self.channel / "tasks" / "T-0001.json"
        original_bytes = path.read_bytes()

        with self.assertRaises(TaskValidationError) as error:
            self.store.create(
                self.make_task(title="Must not overwrite"), actor="bob"
            )

        self.assertEqual(error.exception.code, "TASK_ALREADY_EXISTS")
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(self.store.show("T-0001").title, original.title)

    def test_mutations_write_human_json_and_auditable_messages(self):
        self.store.create(self.make_task(), actor="alice")
        self.store.update("T-0001", actor="bob", status="in_progress")

        task_path = self.channel / "tasks" / "T-0001.json"
        raw = task_path.read_text(encoding="utf-8")
        self.assertTrue(raw.startswith("{\n"))
        self.assertEqual(tuple(json.loads(raw)), TASK_FIELDS)

        messages = sorted(self.channel.glob("[0-9][0-9][0-9][0-9]-*.md"))
        self.assertEqual(len(messages), 2)
        bodies = [path.read_text(encoding="utf-8") for path in messages]
        self.assertTrue(any("task.created" in body for body in bodies))
        self.assertTrue(any("task.updated" in body for body in bodies))


if __name__ == "__main__":
    unittest.main()

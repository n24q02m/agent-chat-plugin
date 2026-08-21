"""Focused Task 2 tests for the typed task model and atomic store."""

import json
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import chat
from agent_chat.task_model import (
    TASK_FIELDS,
    TaskError,
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

    def test_list_rejects_task_record_symlink_outside_channel(self):
        tasks = self.channel / "tasks"
        tasks.mkdir()
        outside = Path(self.temp_dir.name).parent / (self.root.name + "-records")
        outside.mkdir()
        external_record = outside / "T-0001.json"
        external_record.write_text(
            json.dumps(self.task_data()), encoding="utf-8"
        )
        link = tasks / "T-0001.json"
        try:
            link.symlink_to(external_record)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        try:
            with self.assertRaises(TaskValidationError) as error:
                self.store.list()
            self.assertEqual(
                error.exception.code, "TASK_PATH_OUTSIDE_WORKSPACE"
            )
        finally:
            link.unlink(missing_ok=True)
            external_record.unlink(missing_ok=True)
            outside.rmdir()

    def test_store_enforces_explicit_root_boundary_and_channel_symlink(self):
        outside_root = Path(self.temp_dir.name).parent / (self.root.name + "-root")
        outside_root.mkdir()
        chat.cmd_init(
            outside_root,
            SimpleNamespace(channel="outside", members=None, topic=None),
        )
        outside_channel = outside_root / "outside"
        with self.assertRaises(TaskValidationError) as error:
            TaskStore(outside_channel, root=self.root)
        self.assertEqual(error.exception.code, "TASK_PATH_OUTSIDE_WORKSPACE")

        linked_channel = self.root / "linked"
        try:
            linked_channel.symlink_to(outside_channel, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        try:
            with self.assertRaises(TaskValidationError) as error:
                TaskStore(linked_channel, root=self.root)
            self.assertEqual(
                error.exception.code, "TASK_PATH_OUTSIDE_WORKSPACE"
            )
        finally:
            linked_channel.unlink(missing_ok=True)
            (outside_channel / "_meta.json").unlink(missing_ok=True)
            (outside_channel / ".cursors").rmdir()
            outside_channel.rmdir()
            outside_root.rmdir()

    def test_load_and_show_validate_persisted_dependency_graph(self):
        tasks = self.channel / "tasks"
        tasks.mkdir()
        first = self.task_data(id="T-0001", depends_on=["T-0002"])
        second = self.task_data(id="T-0002", depends_on=["T-0001"])
        (tasks / "T-0001.json").write_text(
            json.dumps(first), encoding="utf-8"
        )
        (tasks / "T-0002.json").write_text(
            json.dumps(second), encoding="utf-8"
        )

        for loader in (self.store.load, self.store.show):
            with self.subTest(loader=loader.__name__):
                with self.assertRaises(TaskValidationError) as error:
                    loader("T-0001")
                self.assertEqual(
                    error.exception.code, "TASK_DEPENDENCY_CYCLE"
                )

    def test_load_rejects_persisted_unknown_dependency(self):
        tasks = self.channel / "tasks"
        tasks.mkdir()
        record = self.task_data(depends_on=["T-9999"])
        (tasks / "T-0001.json").write_text(
            json.dumps(record), encoding="utf-8"
        )

        for loader in (self.store.load, self.store.show):
            with self.subTest(loader=loader.__name__):
                with self.assertRaises(TaskValidationError) as error:
                    loader("T-0001")
                self.assertEqual(
                    error.exception.code, "TASK_UNKNOWN_DEPENDENCY"
                )

    def test_nested_validation_uses_canonical_error_codes(self):
        with self.assertRaises(TaskValidationError) as acceptance_error:
            TaskRecord.from_dict(self.task_data(acceptance=[123]))
        self.assertEqual(
            acceptance_error.exception.code, "TASK_INVALID_ACCEPTANCE"
        )

        with self.assertRaises(TaskValidationError) as dependency_error:
            TaskRecord.from_dict(self.task_data(depends_on=[123]))
        self.assertEqual(
            dependency_error.exception.code, "TASK_INVALID_DEPENDENCY_ID"
        )

    def test_audit_failure_rolls_back_create_and_update(self):
        def fail_audit(*args, **kwargs):
            raise TaskError("TASK_AUDIT_FAILED", "injected audit failure")

        self.store._post_event = fail_audit
        with self.assertRaises(TaskError) as create_error:
            self.store.create(self.make_task(), actor="alice")
        self.assertEqual(create_error.exception.code, "TASK_AUDIT_FAILED")
        self.assertFalse((self.channel / "tasks" / "T-0001.json").exists())

        self.store._post_event = TaskStore._post_event.__get__(
            self.store, TaskStore
        )
        self.store.create(self.make_task(), actor="alice")
        self.store._post_event = fail_audit
        with self.assertRaises(TaskError) as update_error:
            self.store.update("T-0001", actor="alice", status="in_progress")
        self.assertEqual(update_error.exception.code, "TASK_AUDIT_FAILED")
        self.assertEqual(self.store.show("T-0001").status, "open")

    def test_updates_serialize_authoritative_write_and_audit_event(self):
        self.store.create(self.make_task(), actor="alice")
        first_started = threading.Event()
        release_first = threading.Event()
        second_finished = threading.Event()
        observed_statuses = []
        first_errors = []
        second_errors = []

        def ordered_event(event, task, **kwargs):
            if task.status == "in_progress":
                first_started.set()
                release_first.wait(2)
            observed_statuses.append(task.status)

        self.store._post_event = ordered_event

        def first_update():
            try:
                self.store.update(
                    "T-0001", actor="alice", status="in_progress"
                )
            except BaseException as error:
                first_errors.append(error)

        def second_update():
            try:
                self.store.update("T-0001", actor="alice", status="blocked")
            except BaseException as error:
                second_errors.append(error)
            finally:
                second_finished.set()

        first_thread = threading.Thread(target=first_update)
        second_thread = threading.Thread(target=second_update)
        first_thread.start()
        self.assertTrue(first_started.wait(2))
        second_thread.start()
        try:
            self.assertFalse(second_finished.wait(0.2))
        finally:
            release_first.set()
            first_thread.join(2)
            second_thread.join(2)

        self.assertEqual(first_errors, [])
        self.assertEqual(second_errors, [])
        self.assertEqual(observed_statuses, ["in_progress", "blocked"])

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

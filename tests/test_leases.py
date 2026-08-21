"""Focused Task 4 tests for atomic task leases and explicit recovery."""

import contextlib
import base64
import io
import json
import threading
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import chat
from agent_chat.lease_store import LeaseError, LeaseRecord, LeaseStore
from agent_chat.task_model import TaskError, TaskRecord, TaskValidationError
from agent_chat.task_store import TaskStore


TIMESTAMP = "2026-08-21T12:00:00+00:00"
EXPIRED = "2020-01-01T00:00:00+00:00"
ORPHAN_EXPIRY = "2099-01-01T00:00:00+00:00"


class LeaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        chat.cmd_init(
            self.root,
            SimpleNamespace(channel="review", members="alice,bob", topic="Task board"),
        )
        self.channel = self.root / "review"
        self.tasks = TaskStore(self.channel)
        self.leases = LeaseStore(self.channel)

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

    def create_task(self, task_id="T-0001", **overrides):
        return self.tasks.create(
            self.make_task(id=task_id, **overrides), actor="alice"
        )

    def expire_claim(self, task_id="T-0001"):
        claim_paths = list((self.channel / "claims").glob(f"{task_id}.*.json"))
        self.assertEqual(len(claim_paths), 1)
        claim_path = claim_paths[0]
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        claim["lease_expires_at"] = EXPIRED
        claim_path.write_text(json.dumps(claim, indent=2) + "\n", encoding="utf-8")
        task_path = self.channel / "tasks" / f"{task_id}.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["lease_expires_at"] = EXPIRED
        task_path.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
        return claim

    def test_two_simultaneous_claimers_have_one_winner_and_stable_conflict(self):
        self.create_task()
        barrier = threading.Barrier(2)
        successes = []
        errors = []

        def claim(owner):
            try:
                barrier.wait(2)
                successes.append(self.leases.claim("T-0001", owner, lease_seconds=30))
            except BaseException as error:
                errors.append(error)

        first = threading.Thread(target=claim, args=("alice",))
        second = threading.Thread(target=claim, args=("bob",))
        first.start()
        second.start()
        first.join(3)
        second.join(3)

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], LeaseError)
        self.assertEqual(errors[0].code, "LEASE_CONFLICT")
        current = self.tasks.show("T-0001")
        self.assertEqual(current.status, "in_progress")
        self.assertEqual(current.owner, successes[0].owner)
        self.assertEqual(len(list((self.channel / "claims").glob("*.json"))), 1)

    def test_expired_lease_requires_explicit_recovery(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)
        self.expire_claim()

        with self.assertRaises(LeaseError) as error:
            self.leases.claim("T-0001", "bob", lease_seconds=30)

        self.assertEqual(error.exception.code, "LEASE_RECOVERY_REQUIRED")
        self.assertEqual(error.exception.details["previous_owner"], "alice")
        self.assertEqual(error.exception.details["previous_lease_expires_at"], EXPIRED)

    def test_owner_can_renew_an_unexpired_lease(self):
        self.create_task()
        claimed = self.leases.claim("T-0001", "alice", lease_seconds=30)
        renewed = self.leases.renew("T-0001", "alice", lease_seconds=60)

        self.assertEqual(renewed.owner, "alice")
        self.assertGreater(renewed.lease_expires_at, claimed.lease_expires_at)
        current = self.tasks.show("T-0001")
        self.assertEqual(current.lease_expires_at, renewed.lease_expires_at)
        messages = [path.read_text(encoding="utf-8") for path in self.channel.glob("[0-9][0-9][0-9][0-9]-*.md")]
        self.assertTrue(any("lease.renewed" in body for body in messages))

    def test_owner_can_release_an_unexpired_lease(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)
        released = self.leases.release("T-0001", "alice")

        self.assertEqual(released.status, "open")
        self.assertIsNone(released.owner)
        self.assertIsNone(released.lease_expires_at)
        self.assertEqual(list((self.channel / "claims").glob("*.json")), [])
        messages = [path.read_text(encoding="utf-8") for path in self.channel.glob("[0-9][0-9][0-9][0-9]-*.md")]
        self.assertTrue(any("lease.released" in body for body in messages))

    def test_release_by_another_agent_is_rejected(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)

        with self.assertRaises(LeaseError) as error:
            self.leases.release("T-0001", "bob")

        self.assertEqual(error.exception.code, "LEASE_OWNER_MISMATCH")
        self.assertEqual(self.tasks.show("T-0001").owner, "alice")

    def test_stale_recovery_records_previous_owner_expiry_and_reason(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)
        previous = self.expire_claim()

        recovered = self.leases.recover(
            "T-0001", "bob", "alice abandoned the task", lease_seconds=45
        )

        self.assertEqual(recovered.owner, "bob")
        self.assertEqual(recovered.status, "in_progress")
        records = list((self.channel / "claims").glob("*.json"))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual(record["previous_owner"], previous["owner"])
        self.assertEqual(record["previous_lease_expires_at"], EXPIRED)
        self.assertEqual(record["recovery_reason"], "alice abandoned the task")
        messages = [path.read_text(encoding="utf-8") for path in self.channel.glob("[0-9][0-9][0-9][0-9]-*.md")]
        self.assertTrue(any("lease.recovered" in body and "alice abandoned the task" in body for body in messages))

    def test_release_rejects_orphaned_task_lease_record(self):
        self.create_task(owner="alice", lease_expires_at=ORPHAN_EXPIRY)

        with self.assertRaises(LeaseError) as error:
            self.leases.release("T-0001", "alice")

        self.assertEqual(error.exception.code, "LEASE_INCONSISTENT")

    def test_preassigned_owner_can_establish_its_first_lease(self):
        self.create_task(owner="alice")

        claimed = self.leases.claim("T-0001", "alice", lease_seconds=30)

        self.assertEqual(claimed.owner, "alice")
        self.assertEqual(claimed.status, "in_progress")

    def test_preassigned_owner_without_lease_remains_task_metadata(self):
        self.create_task(owner="alice")

        updated = self.tasks.update(
            "T-0001",
            {"title": "Updated before first claim"},
            actor="alice",
        )

        self.assertEqual(updated.owner, "alice")
        self.assertIsNone(updated.lease_expires_at)
    def test_stale_recovery_by_same_owner_keeps_one_claim_record(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)
        self.expire_claim()

        recovered = self.leases.recover(
            "T-0001", "alice", "same owner resumed", lease_seconds=30
        )

        self.assertEqual(recovered.owner, "alice")
        records = list((self.channel / "claims").glob("*.json"))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual(record["previous_owner"], "alice")
        self.assertEqual(record["recovery_reason"], "same owner resumed")

    def test_same_owner_recovery_rolls_back_both_records_when_audit_fails(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)
        previous = self.expire_claim()
        old_task = self.tasks.show("T-0001")

        def fail_audit(*args, **kwargs):
            raise TaskError("TASK_AUDIT_FAILED", "injected audit failure")

        self.leases.tasks._post_event = fail_audit
        with self.assertRaises(TaskError):
            self.leases.recover(
                "T-0001", "alice", "audit rollback", lease_seconds=30
            )

        self.assertEqual(self.tasks.show("T-0001"), old_task)
        claim_path = self.channel / "claims" / "T-0001.alice.json"
        self.assertEqual(json.loads(claim_path.read_text(encoding="utf-8")), previous)

    def test_claim_rejects_task_with_unfinished_dependency(self):
        self.create_task(task_id="T-0001")
        self.create_task(task_id="T-0002", depends_on=["T-0001"])

        with self.assertRaises(TaskValidationError) as error:
            self.leases.claim("T-0002", "bob", lease_seconds=30)

        self.assertEqual(error.exception.code, "TASK_DEPENDENCY_NOT_READY")
        self.assertEqual(self.tasks.show("T-0002").status, "open")
        self.assertFalse((self.channel / "claims").exists())

    def test_task_cli_claim_renew_release_and_recover(self):
        def run_cli(*argv):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    chat.main(["--root", str(self.root), *argv])
                except SystemExit as error:
                    return error.code, stdout.getvalue(), stderr.getvalue()
            return 0, stdout.getvalue(), stderr.getvalue()

        self.assertEqual(
            run_cli(
                "task", "create", "review", "T-0001", "--from", "alice", "--title", "Lease me"
            )[0],
            0,
        )
        code, output, error = run_cli(
            "task", "claim", "review", "T-0001", "--as", "alice", "--lease-seconds", "30"
        )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(output, "claimed task T-0001 [in_progress]\n")
        code, output, error = run_cli(
            "task", "renew", "review", "T-0001", "--as", "alice", "--lease-seconds", "30"
        )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(output, "renewed task T-0001 [in_progress]\n")
        code, output, error = run_cli("task", "release", "review", "T-0001", "--as", "alice")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(output, "released task T-0001 [open]\n")
        self.assertEqual(
            run_cli(
                "task", "create", "review", "T-0002", "--from", "alice", "--title", "Complete me"
            )[0],
            0,
        )
        self.leases.claim("T-0002", "alice", lease_seconds=30)
        code, output, error = run_cli("task", "done", "review", "T-0002", "--as", "alice")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(output, "done task T-0002 [done]\n")
        self.assertEqual(list((self.channel / "claims").glob("*.json")), [])


        self.leases.claim("T-0001", "alice", lease_seconds=30)
        self.expire_claim()
        code, output, error = run_cli(
            "task", "recover", "review", "T-0001", "--as", "bob", "--reason", "handoff", "--lease-seconds", "30"
        )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(output, "recovered task T-0001 [in_progress]\n")


    def test_owner_can_complete_and_cleanup_active_lease(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)

        completed = self.leases.complete("T-0001", "alice")

        self.assertEqual(completed.status, "done")
        self.assertIsNone(completed.owner)
        self.assertIsNone(completed.lease_expires_at)
        self.assertEqual(list((self.channel / "claims").glob("*.json")), [])
        with self.assertRaises(LeaseError) as error:
            self.leases.renew("T-0001", "alice", lease_seconds=30)
        self.assertEqual(error.exception.code, "LEASE_NOT_FOUND")

    def test_task_done_cli_clears_active_lease(self):
        def run_cli(*argv):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    chat.main(["--root", str(self.root), *argv])
                except SystemExit as error:
                    return error.code, stdout.getvalue(), stderr.getvalue()
            return 0, stdout.getvalue(), stderr.getvalue()

        self.assertEqual(
            run_cli(
                "task", "create", "review", "T-0001", "--from", "alice", "--title", "Complete me"
            )[0],
            0,
        )
        self.assertEqual(
            run_cli(
                "task", "claim", "review", "T-0001", "--as", "alice", "--lease-seconds", "30"
            )[0],
            0,
        )
        code, output, error = run_cli(
            "task", "done", "review", "T-0001", "--as", "alice"
        )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(output, "done task T-0001 [done]\n")
        self.assertEqual(list((self.channel / "claims").glob("*.json")), [])

    def test_generic_task_update_cannot_bypass_active_lease(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)

        with self.assertRaises(LeaseError) as error:
            self.tasks.update("T-0001", actor="alice", status="done")
        self.assertEqual(error.exception.code, "LEASE_MUTATION_REQUIRED")

        with self.assertRaises(LeaseError) as owner_error:
            self.tasks.update("T-0001", actor="alice", owner="bob")
        self.assertEqual(owner_error.exception.code, "LEASE_MUTATION_REQUIRED")
        self.assertEqual(self.tasks.show("T-0001").owner, "alice")

    def test_claim_list_rejects_symlinked_record_outside_channel(self):
        self.create_task()
        claims = self.channel / "claims"
        claims.mkdir()
        outside = Path(self.temp_dir.name).parent / (self.root.name + "-lease-outside")
        outside.mkdir()
        external = outside / "claim.json"
        external.write_text("{}", encoding="utf-8")
        linked = claims / "T-0001.alice.json"
        try:
            linked.symlink_to(external)
        except (OSError, NotImplementedError):
            linked.unlink(missing_ok=True)
            external.unlink(missing_ok=True)
            outside.rmdir()
            self.skipTest("symlink creation is unavailable on this platform")
        try:
            with self.assertRaises(LeaseError) as error:
                self.leases.list()
            self.assertEqual(error.exception.code, "LEASE_PATH_OUTSIDE_WORKSPACE")
        finally:
            linked.unlink(missing_ok=True)
            external.unlink(missing_ok=True)
            outside.rmdir()

    def test_oversized_lease_duration_has_stable_error(self):
        self.create_task()
        with self.assertRaises(LeaseError) as error:
            self.leases.claim("T-0001", "alice", lease_seconds=1e308)
        self.assertEqual(error.exception.code, "LEASE_INVALID_DURATION")
        self.assertEqual(self.tasks.show("T-0001").status, "open")

    def test_crashed_transaction_fails_closed_until_explicit_recovery(self):
        self.create_task()
        original_atomic_write = self.leases.tasks._atomic_write

        def crash_after_task_write(path, task):
            original_atomic_write(path, task)
            raise SystemExit("simulated process crash")

        self.leases.tasks._atomic_write = crash_after_task_write
        with self.assertRaises(SystemExit):
            self.leases.claim("T-0001", "alice", lease_seconds=30)

        pending = LeaseStore(self.channel)
        with self.assertRaises(LeaseError) as error:
            pending.load("T-0001")
        self.assertEqual(error.exception.code, "LEASE_TRANSACTION_PENDING")

        pending.recover_pending(actor="recovery")
        restored = self.tasks.show("T-0001")
        self.assertEqual((restored.status, restored.owner), ("open", None))
        self.assertEqual(list((self.channel / "claims").glob("*.json")), [])
        self.leases.tasks._atomic_write = original_atomic_write
        self.leases.claim("T-0001", "alice", lease_seconds=30)
    def test_unleased_preassigned_owner_keeps_task3_done_and_release_behavior(self):
        self.create_task(owner="alice")
        self.tasks.update("T-0001", actor="alice", status="in_progress")
        completed = self.leases.complete_or_done("T-0001", "alice")
        self.assertEqual((completed.status, completed.owner), ("done", "alice"))

        self.create_task(task_id="T-0002", owner="alice", status="blocked")
        released = self.leases.release_or_open("T-0002", "alice")
        self.assertEqual((released.status, released.owner), ("open", "alice"))

    def test_generic_status_mutations_cannot_bypass_active_lease(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)

        for status in ("blocked", "cancelled"):
            with self.subTest(status=status):
                with self.assertRaises(LeaseError) as error:
                    self.tasks.update("T-0001", actor="alice", status=status)
                self.assertEqual(error.exception.code, "LEASE_MUTATION_REQUIRED")

    def test_task_cli_block_and_update_cannot_bypass_active_lease(self):
        def run_cli(*argv):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    chat.main(["--root", str(self.root), *argv])
                except SystemExit as error:
                    return error.code, stdout.getvalue(), stderr.getvalue()
            return 0, stdout.getvalue(), stderr.getvalue()

        self.assertEqual(
            run_cli(
                "task", "create", "review", "T-0001", "--from", "alice", "--title", "Guard"
            )[0],
            0,
        )
        self.assertEqual(
            run_cli(
                "task", "claim", "review", "T-0001", "--as", "alice", "--lease-seconds", "30"
            )[0],
            0,
        )
        commands = (
            ("task", "block", "review", "T-0001", "--as", "alice"),
            (
                "task",
                "update",
                "review",
                "T-0001",
                "--as",
                "alice",
                "--status",
                "cancelled",
            ),
            (
                "task",
                "update",
                "review",
                "T-0001",
                "--as",
                "alice",
                "--owner",
                "bob",
            ),
        )
        for command in commands:
            with self.subTest(command=command):
                code, _, error = run_cli(*command)
                self.assertEqual(code, 2)
                self.assertIn("LEASE_MUTATION_REQUIRED", error)

    def test_claim_checks_task_claim_consistency_before_conflict(self):
        self.create_task()
        self.leases.claim("T-0001", "alice", lease_seconds=30)
        task_path = self.channel / "tasks" / "T-0001.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["owner"] = "bob"
        task_path.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(LeaseError) as error:
            self.leases.claim("T-0001", "bob", lease_seconds=30)
        self.assertEqual(error.exception.code, "LEASE_INCONSISTENT")

    def test_cross_channel_claim_record_is_rejected_by_read_and_list(self):
        self.create_task()
        claims = self.channel / "claims"
        claims.mkdir()
        record = LeaseRecord(
            task_id="T-0001",
            channel="other",
            owner="alice",
            lease_expires_at=ORPHAN_EXPIRY,
            claimed_at=TIMESTAMP,
            updated_at=TIMESTAMP,
        )
        (claims / "T-0001.alice.json").write_text(
            json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

        with self.assertRaises(LeaseError) as error:
            self.leases.list()
        self.assertEqual(error.exception.code, "LEASE_INCONSISTENT")
        with self.assertRaises(LeaseError) as error:
            self.leases.claim("T-0001", "bob", lease_seconds=30)
        self.assertEqual(error.exception.code, "LEASE_INCONSISTENT")

    def test_crashed_after_claim_install_fails_closed_until_recovery(self):
        self.create_task()

        def crash_audit(*args, **kwargs):
            raise SystemExit("simulated process crash after claim install")

        self.leases.tasks._post_event = crash_audit
        with self.assertRaises(SystemExit):
            self.leases.claim("T-0001", "alice", lease_seconds=30)

        pending = LeaseStore(self.channel)
        with self.assertRaises(LeaseError) as error:
            pending.load("T-0001")
        self.assertEqual(error.exception.code, "LEASE_TRANSACTION_PENDING")
        self.assertEqual(len(list((self.channel / "claims").glob("T-0001.*.json"))), 1)

        pending.recover_pending(actor="recovery")
        restored = self.tasks.show("T-0001")
        self.assertEqual((restored.status, restored.owner), ("open", None))
        self.assertEqual(list((self.channel / "claims").glob("*.json")), [])

    def test_pending_transaction_rejects_task_path_outside_tasks_layout(self):
        self.create_task()
        task_before = self.leases._encode_bytes(
            json.dumps(self.task_data(), separators=(",", ":")).encode("utf-8")
        )
        self.leases.claims_dir.mkdir()
        self.leases.transaction_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "task_id": "T-0001",
                    "task_file": "other.json",
                    "task_before": task_before,
                    "claim_changes": [],
                    "event": "lease.claimed",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(LeaseError) as error:
            self.leases.recover_pending(actor="recovery")
        self.assertEqual(error.exception.code, "LEASE_TRANSACTION_INVALID")

    def test_pending_transaction_validates_decoded_task_identity(self):
        self.create_task()
        wrong_task = self.task_data(id="T-9999")
        task_before = self.leases._encode_bytes(
            json.dumps(wrong_task, separators=(",", ":")).encode("utf-8")
        )
        self.leases.claims_dir.mkdir()
        self.leases.transaction_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "task_id": "T-0001",
                    "task_file": "tasks/T-0001.json",
                    "task_before": task_before,
                    "claim_changes": [],
                    "event": "lease.claimed",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(LeaseError) as error:
            self.leases.recover_pending(actor="recovery")
        self.assertEqual(error.exception.code, "LEASE_TRANSACTION_INVALID")

    def test_pending_transaction_rejects_claim_path_outside_claims_layout(self):
        self.create_task()
        task_before = self.leases._encode_bytes(
            json.dumps(self.task_data(), separators=(",", ":")).encode("utf-8")
        )
        self.leases.claims_dir.mkdir()
        self.leases.transaction_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "task_id": "T-0001",
                    "task_file": "tasks/T-0001.json",
                    "task_before": task_before,
                    "claim_changes": [
                        {
                            "file": "../tasks/T-0001.json",
                            "previous": None,
                            "next": None,
                        }
                    ],
                    "event": "lease.claimed",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(LeaseError) as error:
            self.leases.recover_pending(actor="recovery")
        self.assertEqual(error.exception.code, "LEASE_TRANSACTION_INVALID")

    def test_list_rechecks_pending_marker_inside_mutation_lock(self):
        self.create_task()
        original_guard = self.leases._assert_no_pending_transaction
        calls = []

        def inject_pending_marker():
            calls.append(True)
            if len(calls) == 1:
                self.leases.claims_dir.mkdir()
                task_before = self.leases._encode_bytes(
                    (self.channel / "tasks" / "T-0001.json").read_bytes()
                )
                self.leases.transaction_path.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": "T-0001",
                            "task_file": "tasks/T-0001.json",
                            "task_before": task_before,
                            "claim_changes": [],
                            "event": "lease.claimed",
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return
            original_guard()

        self.leases._assert_no_pending_transaction = inject_pending_marker
        with self.assertRaises(LeaseError) as error:
            self.leases.list()
        self.assertEqual(error.exception.code, "LEASE_TRANSACTION_PENDING")
        self.assertEqual(len(calls), 2)

    def test_pending_transaction_rejects_claim_for_other_task_or_owner(self):
        self.create_task()
        task_before = self.leases._encode_bytes(
            (self.channel / "tasks" / "T-0001.json").read_bytes()
        )
        self.leases.claims_dir.mkdir()
        self.leases.transaction_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "task_id": "T-0001",
                    "task_file": "tasks/T-0001.json",
                    "task_before": task_before,
                    "claim_changes": [
                        {
                            "file": "T-0002.bob.json",
                            "previous": None,
                            "next": None,
                        }
                    ],
                    "event": "lease.claimed",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(LeaseError) as error:
            self.leases.recover_pending(actor="recovery")
        self.assertEqual(error.exception.code, "LEASE_TRANSACTION_INVALID")

    def test_pending_transaction_preflights_claim_rollback_bytes(self):
        self.create_task()
        task_path = self.channel / "tasks" / "T-0001.json"
        task_before = self.leases._encode_bytes(
            json.dumps(self.task_data(), separators=(",", ":")).encode("utf-8")
        )
        current = self.task_data(
            status="in_progress",
            owner="alice",
            lease_expires_at="2026-08-21T12:30:00+00:00",
        )
        task_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        original_task_bytes = task_path.read_bytes()
        self.leases.claims_dir.mkdir()
        self.leases.transaction_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "task_id": "T-0001",
                    "task_file": "tasks/T-0001.json",
                    "task_before": task_before,
                    "claim_changes": [
                        {
                            "file": "T-0001.alice.json",
                            "previous": "not-base64",
                            "next": None,
                        }
                    ],
                    "event": "lease.claimed",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(LeaseError) as error:
            self.leases.recover_pending(actor="recovery")
        self.assertEqual(error.exception.code, "LEASE_TRANSACTION_INVALID")
        self.assertEqual(task_path.read_bytes(), original_task_bytes)

if __name__ == "__main__":
    unittest.main()

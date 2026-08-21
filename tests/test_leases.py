"""Focused Task 4 tests for atomic task leases and explicit recovery."""

import contextlib
import io
import json
import threading
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import chat
from agent_chat.lease_store import LeaseError, LeaseStore
from agent_chat.task_model import TaskError, TaskRecord, TaskValidationError
from agent_chat.task_store import TaskStore


TIMESTAMP = "2026-08-21T12:00:00+00:00"
EXPIRED = "2020-01-01T00:00:00+00:00"


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

    def test_preassigned_owner_can_establish_its_first_lease(self):
        self.create_task(owner="alice")

        claimed = self.leases.claim("T-0001", "alice", lease_seconds=30)

        self.assertEqual(claimed.owner, "alice")
        self.assertEqual(claimed.status, "in_progress")

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

        self.leases.claim("T-0001", "alice", lease_seconds=30)
        self.expire_claim()
        code, output, error = run_cli(
            "task", "recover", "review", "T-0001", "--as", "bob", "--reason", "handoff", "--lease-seconds", "30"
        )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(output, "recovered task T-0001 [in_progress]\n")


if __name__ == "__main__":
    unittest.main()

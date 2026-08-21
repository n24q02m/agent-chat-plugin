"""Atomic task leases and explicit stale-claim recovery.

Lease records are the active-claim index for one channel.  A task JSON record
remains authoritative for task state; a lease mutation updates both records
under the task store's channel mutation lock and emits one audit event.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import chat

from .task_model import (
    TaskError,
    TaskRecord,
    TaskValidationError,
    parse_timestamp,
    validate_transition,
)
from .task_store import TaskStore


CLAIMS_DIRNAME = "claims"
DEFAULT_LEASE_SECONDS = 300.0
LEASE_FIELDS = (
    "task_id",
    "channel",
    "owner",
    "lease_expires_at",
    "claimed_at",
    "updated_at",
    "previous_owner",
    "previous_lease_expires_at",
    "recovery_reason",
)
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class LeaseError(TaskError):
    """Base error with a stable machine-readable lease error code."""


@dataclass(frozen=True)
class LeaseRecord:
    """The human-readable JSON representation of one active task claim."""

    task_id: str
    channel: str
    owner: str
    lease_expires_at: str
    claimed_at: str
    updated_at: str
    previous_owner: str | None = None
    previous_lease_expires_at: str | None = None
    recovery_reason: str | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.task_id, "task_id", "LEASE_INVALID_TASK_ID")
        _validate_identity(self.channel, "channel", "LEASE_INVALID_CHANNEL")
        _validate_identity(self.owner, "owner", "LEASE_INVALID_OWNER")
        _lease_timestamp(self.lease_expires_at, field="lease_expires_at")
        _lease_timestamp(self.claimed_at, field="claimed_at")
        _lease_timestamp(self.updated_at, field="updated_at")
        if self.previous_owner is not None:
            _validate_identity(
                self.previous_owner, "previous_owner", "LEASE_INVALID_OWNER"
            )
        if self.previous_lease_expires_at is not None:
            _lease_timestamp(
                self.previous_lease_expires_at,
                field="previous_lease_expires_at",
            )
        if self.recovery_reason is not None:
            _validate_reason(self.recovery_reason)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeaseRecord":
        if not isinstance(data, dict):
            raise LeaseError("LEASE_INVALID_RECORD", "lease record must be a JSON object")
        actual = set(data)
        required = set(LEASE_FIELDS[:6])
        missing = [field for field in LEASE_FIELDS[:6] if field not in actual]
        if missing:
            raise LeaseError(
                "LEASE_REQUIRED_FIELD_MISSING",
                "required lease field is missing",
                fields=missing,
            )
        unknown = sorted(actual - set(LEASE_FIELDS))
        if unknown:
            raise LeaseError(
                "LEASE_UNKNOWN_FIELD",
                "lease record contains unknown fields",
                fields=unknown,
            )
        return cls(
            task_id=data["task_id"],
            channel=data["channel"],
            owner=data["owner"],
            lease_expires_at=data["lease_expires_at"],
            claimed_at=data["claimed_at"],
            updated_at=data["updated_at"],
            previous_owner=data.get("previous_owner"),
            previous_lease_expires_at=data.get("previous_lease_expires_at"),
            recovery_reason=data.get("recovery_reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "channel": self.channel,
            "owner": self.owner,
            "lease_expires_at": self.lease_expires_at,
            "claimed_at": self.claimed_at,
            "updated_at": self.updated_at,
            "previous_owner": self.previous_owner,
            "previous_lease_expires_at": self.previous_lease_expires_at,
            "recovery_reason": self.recovery_reason,
        }


def _validate_identity(value: Any, field: str, code: str) -> str:
    if not isinstance(value, str) or not value or not _ID_RE.fullmatch(value):
        raise LeaseError(code, f"{field} must be a safe identity")
    return value


def _validate_reason(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LeaseError("LEASE_INVALID_REASON", "recovery reason must not be empty")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise LeaseError(
            "LEASE_INVALID_REASON",
            "recovery reason contains a forbidden control character",
        )
    return value


def _lease_timestamp(value: Any, *, field: str) -> str:
    try:
        parse_timestamp(value, field=field)
    except TaskValidationError as error:
        raise LeaseError(
            "LEASE_INVALID_TIMESTAMP",
            error.message,
            field=field,
        ) from error
    return value


def _timestamp(value: Any, *, field: str) -> str:
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise LeaseError("LEASE_INVALID_TIMESTAMP", f"{field} needs a UTC offset")
        return value.isoformat(timespec="microseconds")
    if not isinstance(value, str):
        raise LeaseError("LEASE_INVALID_TIMESTAMP", f"{field} must be an ISO-8601 string")
    _lease_timestamp(value, field=field)
    return value


def _datetime(value: str, *, field: str) -> _dt.datetime:
    _lease_timestamp(value, field=field)
    parse_value = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    return _dt.datetime.fromisoformat(parse_value)


def _is_expired(expires_at: str, now: _dt.datetime) -> bool:
    return _datetime(expires_at, field="lease_expires_at") <= now


class LeaseStore:
    """Read and mutate active claims for one channel."""

    def __init__(
        self,
        channel: Path | str,
        root: Path | str | None = None,
        *,
        clock: Callable[[], Any] | None = None,
    ):
        self.tasks = TaskStore(channel, root=root)
        self.channel = self.tasks.channel
        self.root = self.tasks.root
        self._clock = clock or chat.now_iso
        self._assert_inside_channel(self.claims_dir)

    @property
    def claims_dir(self) -> Path:
        return self.channel / CLAIMS_DIRNAME

    def _assert_inside_channel(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self.channel.resolve(strict=False))
        except (OSError, RuntimeError, ValueError):
            raise LeaseError(
                "LEASE_PATH_OUTSIDE_WORKSPACE",
                f"lease storage path escapes channel workspace: {path}",
            )

    def _ensure_claims_dir(self) -> Path:
        self._assert_inside_channel(self.claims_dir)
        if self.claims_dir.exists() and not self.claims_dir.is_dir():
            raise LeaseError(
                "LEASE_STORAGE_INVALID",
                f"claim storage is not a directory: {self.claims_dir}",
            )
        self.claims_dir.mkdir(parents=True, exist_ok=True)
        return self.claims_dir

    def _task_path(self, task_id: str) -> Path:
        try:
            return self.tasks._task_path(task_id)
        except TaskValidationError as error:
            raise error

    def _claim_path(self, task_id: str, owner: str) -> Path:
        self._task_path(task_id)
        _validate_identity(owner, "owner", "LEASE_INVALID_OWNER")
        path = self.claims_dir / f"{task_id}.{owner}.json"
        self._assert_inside_channel(path)
        return path

    def _now(self, value: Any = None) -> _dt.datetime:
        candidate = self._clock() if value is None else value
        if isinstance(candidate, _dt.datetime):
            if candidate.tzinfo is None or candidate.utcoffset() is None:
                raise LeaseError("LEASE_INVALID_TIMESTAMP", "clock must include a UTC offset")
            return candidate
        if not isinstance(candidate, str):
            raise LeaseError("LEASE_INVALID_TIMESTAMP", "clock must return an ISO-8601 string")
        return _datetime(candidate, field="now")

    @staticmethod
    def _expiry(now: _dt.datetime, lease_seconds: Any) -> tuple[float, str]:
        if isinstance(lease_seconds, bool):
            raise LeaseError("LEASE_INVALID_DURATION", "lease duration must be positive")
        try:
            seconds = float(lease_seconds)
        except (TypeError, ValueError):
            raise LeaseError("LEASE_INVALID_DURATION", "lease duration must be positive")
        if not math.isfinite(seconds) or seconds <= 0:
            raise LeaseError("LEASE_INVALID_DURATION", "lease duration must be positive")
        expiry = now + _dt.timedelta(seconds=seconds)
        return seconds, expiry.isoformat(timespec="microseconds")

    @staticmethod
    def _read_claim(path: Path) -> LeaseRecord:
        try:
            with path.open("r", encoding="utf-8") as stream:
                raw = json.load(stream)
        except FileNotFoundError:
            raise LeaseError("LEASE_NOT_FOUND", f"lease record does not exist: {path.name}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LeaseError(
                "LEASE_INVALID_RECORD",
                f"could not read lease record {path.name}: {error}",
                path=str(path),
            )
        record = LeaseRecord.from_dict(raw)
        expected = path.parent / f"{record.task_id}.{record.owner}.json"
        if expected != path:
            raise LeaseError(
                "LEASE_RECORD_ID_MISMATCH",
                f"lease identity does not match filename {path.name!r}",
                path=str(path),
            )
        return record

    def _claims_for_task(self, task_id: str) -> list[tuple[Path, LeaseRecord]]:
        if not self.claims_dir.exists():
            return []
        if not self.claims_dir.is_dir():
            raise LeaseError(
                "LEASE_STORAGE_INVALID",
                f"claim storage is not a directory: {self.claims_dir}",
            )
        matches: list[tuple[Path, LeaseRecord]] = []
        for path in sorted(self.claims_dir.glob("*.json"), key=lambda item: item.name):
            self._assert_inside_channel(path)
            record = self._read_claim(path)
            if record.channel == self.channel.name and record.task_id == task_id:
                matches.append((path, record))
        return matches

    def _current_claim(self, task_id: str) -> tuple[Path, LeaseRecord] | None:
        claims = self._claims_for_task(task_id)
        if len(claims) > 1:
            raise LeaseError(
                "LEASE_INCONSISTENT",
                f"multiple active leases exist for task {task_id}",
                task_id=task_id,
                owners=[record.owner for _, record in claims],
            )
        return claims[0] if claims else None

    def load(self, task_id: str) -> LeaseRecord:
        self._task_path(task_id)
        with self.tasks._mutation_lock():
            current = self._current_claim(task_id)
            if current is None:
                raise LeaseError("LEASE_NOT_FOUND", f"no active lease for task {task_id}")
            return current[1]

    def list(self) -> list[LeaseRecord]:
        with self.tasks._mutation_lock():
            if not self.claims_dir.exists():
                return []
            if not self.claims_dir.is_dir():
                raise LeaseError(
                    "LEASE_STORAGE_INVALID",
                    f"claim storage is not a directory: {self.claims_dir}",
                )
            return [
                self._read_claim(path)
                for path in sorted(self.claims_dir.glob("*.json"), key=lambda item: item.name)
            ]

    def _read_task_locked(self, task_id: str) -> tuple[Path, TaskRecord, list[TaskRecord]]:
        path = self._task_path(task_id)
        records = self.tasks._read_snapshot()
        for task in records:
            if task.id == path.stem:
                return path, task, records
        raise TaskValidationError("TASK_NOT_FOUND", f"task record does not exist: {task_id}")

    def _assert_consistent(
        self,
        task: TaskRecord,
        claim: tuple[Path, LeaseRecord] | None,
    ) -> None:
        if claim is None:
            if task.owner is not None or task.lease_expires_at is not None:
                raise LeaseError(
                    "LEASE_INCONSISTENT",
                    f"task {task.id} has lease fields without an active claim record",
                    task_id=task.id,
                    owner=task.owner,
                    lease_expires_at=task.lease_expires_at,
                )
            return
        _, record = claim
        if (
            task.owner != record.owner
            or task.lease_expires_at != record.lease_expires_at
        ):
            raise LeaseError(
                "LEASE_INCONSISTENT",
                f"task {task.id} and claim record disagree",
                task_id=task.id,
                task_owner=task.owner,
                claim_owner=record.owner,
                task_lease_expires_at=task.lease_expires_at,
                claim_lease_expires_at=record.lease_expires_at,
            )

    def _candidate(
        self,
        current: TaskRecord,
        records: list[TaskRecord],
        *,
        owner: str | None,
        status: str,
        lease_expires_at: str | None,
        updated_at: str,
    ) -> TaskRecord:
        merged = current.to_dict()
        merged.update(
            {
                "owner": owner,
                "status": status,
                "lease_expires_at": lease_expires_at,
                "updated_at": updated_at,
            }
        )
        candidate = self.tasks.validate(merged)
        validate_transition(current.status, candidate.status)
        replaced = [candidate if record.id == current.id else record for record in records]
        self.tasks._validate_graph(replaced)
        if candidate.status in {"in_progress", "done"}:
            self.tasks._assert_dependencies_ready(candidate, replaced)
        return candidate

    @staticmethod
    def _json_bytes(record: LeaseRecord) -> bytes:
        return (
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2, separators=(",", ": "))
            + "\n"
        ).encode("utf-8")

    def _write_claim_exclusive(self, path: Path, record: LeaseRecord) -> None:
        self._ensure_claims_dir()
        payload = self._json_bytes(record)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(str(path), flags, 0o600)
        except FileExistsError:
            raise LeaseError(
                "LEASE_CONFLICT",
                f"claim already exists for task {record.task_id}",
                task_id=record.task_id,
            )
        temporary = False
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            temporary = True
            self.tasks._fsync_directory(path.parent)
        finally:
            if not temporary:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def _write_claim(self, path: Path, record: LeaseRecord) -> None:
        self._ensure_claims_dir()
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(self._json_bytes(record))
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            os.replace(temporary, path)
            self.tasks._fsync_directory(path.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _restore_claim(self, path: Path, previous: bytes | None) -> None:
        if previous is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            self.tasks._fsync_directory(path.parent)
            return
        self._ensure_claims_dir()
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}.rollback.", suffix=".tmp", dir=str(path.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(previous)
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            os.replace(temporary, path)
            self.tasks._fsync_directory(path.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _run_transaction(
        self,
        *,
        task_path: Path,
        current: TaskRecord,
        candidate: TaskRecord,
        claim_changes: list[tuple[Path, bytes | None, LeaseRecord | None]],
        event: str,
        actor: str,
        details: dict[str, Any],
    ) -> TaskRecord:
        task_written = False
        claim_paths_written: list[Path] = []
        try:
            self.tasks._atomic_write(task_path, candidate)
            task_written = True
            for path, _previous, record in claim_changes:
                if record is None:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    self.tasks._fsync_directory(path.parent)
                elif path.exists():
                    self._write_claim(path, record)
                else:
                    self._write_claim_exclusive(path, record)
                claim_paths_written.append(path)
            self.tasks._post_event(
                event,
                candidate,
                actor=actor,
                previous=current,
                details=details,
            )
        except Exception as error:
            try:
                if task_written:
                    self.tasks._atomic_write(task_path, current)
                for path, previous, _record in reversed(claim_changes):
                    self._restore_claim(path, previous)
            except Exception as rollback_error:
                raise LeaseError(
                    "LEASE_AUDIT_ROLLBACK_FAILED",
                    f"could not roll back lease mutation: {rollback_error}",
                    task_id=current.id,
                    event=event,
                ) from rollback_error
            if isinstance(error, TaskError):
                raise
            raise LeaseError(
                "LEASE_AUDIT_FAILED",
                f"lease mutation audit failed: {error}",
                task_id=current.id,
                event=event,
            ) from error
        return candidate

    def claim(
        self,
        task_id: str,
        owner: str,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        *,
        actor: str | None = None,
        now: Any = None,
        ttl: float | None = None,
    ) -> TaskRecord:
        _validate_identity(owner, "owner", "LEASE_INVALID_OWNER")
        if ttl is not None:
            lease_seconds = ttl
        with self.tasks._mutation_lock():
            task_path, current, records = self._read_task_locked(task_id)
            claim = self._current_claim(task_id)
            if claim is not None:
                _, existing = claim
                current_now = self._now(now)
                if _is_expired(existing.lease_expires_at, current_now):
                    raise LeaseError(
                        "LEASE_RECOVERY_REQUIRED",
                        f"expired lease for task {task_id} requires explicit recovery",
                        task_id=task_id,
                        previous_owner=existing.owner,
                        previous_lease_expires_at=existing.lease_expires_at,
                    )
                raise LeaseError(
                    "LEASE_CONFLICT",
                    f"task {task_id} is leased by {existing.owner}",
                    task_id=task_id,
                    owner=existing.owner,
                    lease_expires_at=existing.lease_expires_at,
                )
            self._assert_consistent(current, None)
            current_now = self._now(now)
            _seconds, expires_at = self._expiry(current_now, lease_seconds)
            updated_at = _timestamp(current_now, field="updated_at")
            candidate = self._candidate(
                current,
                records,
                owner=owner,
                status="in_progress",
                lease_expires_at=expires_at,
                updated_at=updated_at,
            )
            record = LeaseRecord(
                task_id=task_id,
                channel=self.channel.name,
                owner=owner,
                lease_expires_at=expires_at,
                claimed_at=updated_at,
                updated_at=updated_at,
            )
            path = self._claim_path(task_id, owner)
            return self._run_transaction(
                task_path=task_path,
                current=current,
                candidate=candidate,
                claim_changes=[(path, None, record)],
                event="lease.claimed",
                actor=actor or owner,
                details={
                    "lease_owner": owner,
                    "lease_expires_at": expires_at,
                },
            )

    def renew(
        self,
        task_id: str,
        owner: str,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        *,
        actor: str | None = None,
        now: Any = None,
        ttl: float | None = None,
    ) -> TaskRecord:
        _validate_identity(owner, "owner", "LEASE_INVALID_OWNER")
        if ttl is not None:
            lease_seconds = ttl
        with self.tasks._mutation_lock():
            task_path, current, records = self._read_task_locked(task_id)
            claim = self._current_claim(task_id)
            if claim is None:
                raise LeaseError("LEASE_NOT_FOUND", f"no active lease for task {task_id}")
            path, existing = claim
            self._assert_consistent(current, claim)
            if existing.owner != owner:
                raise LeaseError(
                    "LEASE_OWNER_MISMATCH",
                    f"lease for task {task_id} belongs to {existing.owner}",
                    task_id=task_id,
                    owner=owner,
                    current_owner=existing.owner,
                )
            current_now = self._now(now)
            if _is_expired(existing.lease_expires_at, current_now):
                raise LeaseError(
                    "LEASE_RECOVERY_REQUIRED",
                    f"expired lease for task {task_id} requires explicit recovery",
                    task_id=task_id,
                    previous_owner=existing.owner,
                    previous_lease_expires_at=existing.lease_expires_at,
                )
            _seconds, expires_at = self._expiry(current_now, lease_seconds)
            updated_at = _timestamp(current_now, field="updated_at")
            candidate = self._candidate(
                current,
                records,
                owner=owner,
                status=current.status,
                lease_expires_at=expires_at,
                updated_at=updated_at,
            )
            record = LeaseRecord(
                task_id=task_id,
                channel=self.channel.name,
                owner=owner,
                lease_expires_at=expires_at,
                claimed_at=existing.claimed_at,
                updated_at=updated_at,
                previous_owner=existing.previous_owner,
                previous_lease_expires_at=existing.previous_lease_expires_at,
                recovery_reason=existing.recovery_reason,
            )
            previous = path.read_bytes()
            return self._run_transaction(
                task_path=task_path,
                current=current,
                candidate=candidate,
                claim_changes=[(path, previous, record)],
                event="lease.renewed",
                actor=actor or owner,
                details={
                    "lease_owner": owner,
                    "lease_expires_at": expires_at,
                },
            )

    def release(
        self,
        task_id: str,
        owner: str,
        *,
        actor: str | None = None,
        now: Any = None,
    ) -> TaskRecord:
        _validate_identity(owner, "owner", "LEASE_INVALID_OWNER")
        with self.tasks._mutation_lock():
            task_path, current, records = self._read_task_locked(task_id)
            claim = self._current_claim(task_id)
            if claim is None:
                raise LeaseError("LEASE_NOT_FOUND", f"no active lease for task {task_id}")
            path, existing = claim
            self._assert_consistent(current, claim)
            if existing.owner != owner:
                raise LeaseError(
                    "LEASE_OWNER_MISMATCH",
                    f"lease for task {task_id} belongs to {existing.owner}",
                    task_id=task_id,
                    owner=owner,
                    current_owner=existing.owner,
                )
            current_now = self._now(now)
            if _is_expired(existing.lease_expires_at, current_now):
                raise LeaseError(
                    "LEASE_RECOVERY_REQUIRED",
                    f"expired lease for task {task_id} requires explicit recovery",
                    task_id=task_id,
                    previous_owner=existing.owner,
                    previous_lease_expires_at=existing.lease_expires_at,
                )
            updated_at = _timestamp(current_now, field="updated_at")
            candidate = self._candidate(
                current,
                records,
                owner=None,
                status="open",
                lease_expires_at=None,
                updated_at=updated_at,
            )
            previous = path.read_bytes()
            return self._run_transaction(
                task_path=task_path,
                current=current,
                candidate=candidate,
                claim_changes=[(path, previous, None)],
                event="lease.released",
                actor=actor or owner,
                details={
                    "lease_owner": owner,
                    "previous_lease_expires_at": existing.lease_expires_at,
                },
            )

    def recover(
        self,
        task_id: str,
        owner: str,
        reason: str,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        *,
        actor: str | None = None,
        now: Any = None,
        ttl: float | None = None,
    ) -> TaskRecord:
        _validate_identity(owner, "owner", "LEASE_INVALID_OWNER")
        _validate_reason(reason)
        if ttl is not None:
            lease_seconds = ttl
        with self.tasks._mutation_lock():
            task_path, current, records = self._read_task_locked(task_id)
            claim = self._current_claim(task_id)
            if claim is None:
                raise LeaseError("LEASE_NOT_FOUND", f"no active lease for task {task_id}")
            old_path, existing = claim
            self._assert_consistent(current, claim)
            current_now = self._now(now)
            if not _is_expired(existing.lease_expires_at, current_now):
                raise LeaseError(
                    "LEASE_NOT_EXPIRED",
                    f"lease for task {task_id} is still active",
                    task_id=task_id,
                    owner=existing.owner,
                    lease_expires_at=existing.lease_expires_at,
                )
            _seconds, expires_at = self._expiry(current_now, lease_seconds)
            updated_at = _timestamp(current_now, field="updated_at")
            candidate = self._candidate(
                current,
                records,
                owner=owner,
                status="in_progress",
                lease_expires_at=expires_at,
                updated_at=updated_at,
            )
            new_record = LeaseRecord(
                task_id=task_id,
                channel=self.channel.name,
                owner=owner,
                lease_expires_at=expires_at,
                claimed_at=updated_at,
                updated_at=updated_at,
                previous_owner=existing.owner,
                previous_lease_expires_at=existing.lease_expires_at,
                recovery_reason=reason,
            )
            old_previous = old_path.read_bytes()
            new_path = self._claim_path(task_id, owner)
            new_previous = new_path.read_bytes() if new_path.exists() else None
            return self._run_transaction(
                task_path=task_path,
                current=current,
                candidate=candidate,
                claim_changes=[
                    (old_path, old_previous, None),
                    (new_path, new_previous, new_record),
                ],
                event="lease.recovered",
                actor=actor or owner,
                details={
                    "lease_owner": owner,
                    "lease_expires_at": expires_at,
                    "previous_owner": existing.owner,
                    "previous_lease_expires_at": existing.lease_expires_at,
                    "recovery_reason": reason,
                },
            )


# Module-level wrappers keep the API consistent with task_store.py.
def claim_task(
    channel: Path | str,
    task_id: str,
    owner: str,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    *,
    root: Path | str | None = None,
    actor: str | None = None,
    now: Any = None,
    ttl: float | None = None,
) -> TaskRecord:
    return LeaseStore(channel, root=root).claim(
        task_id, owner, lease_seconds, actor=actor, now=now, ttl=ttl
    )


def renew_task(
    channel: Path | str,
    task_id: str,
    owner: str,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    *,
    root: Path | str | None = None,
    actor: str | None = None,
    now: Any = None,
    ttl: float | None = None,
) -> TaskRecord:
    return LeaseStore(channel, root=root).renew(
        task_id, owner, lease_seconds, actor=actor, now=now, ttl=ttl
    )


def release_task(
    channel: Path | str,
    task_id: str,
    owner: str,
    *,
    root: Path | str | None = None,
    actor: str | None = None,
    now: Any = None,
) -> TaskRecord:
    return LeaseStore(channel, root=root).release(task_id, owner, actor=actor, now=now)


def recover_task(
    channel: Path | str,
    task_id: str,
    owner: str,
    reason: str,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    *,
    root: Path | str | None = None,
    actor: str | None = None,
    now: Any = None,
    ttl: float | None = None,
) -> TaskRecord:
    return LeaseStore(channel, root=root).recover(
        task_id,
        owner,
        reason,
        lease_seconds,
        actor=actor,
        now=now,
        ttl=ttl,
    )


__all__ = [
    "CLAIMS_DIRNAME",
    "DEFAULT_LEASE_SECONDS",
    "LEASE_FIELDS",
    "LeaseError",
    "LeaseRecord",
    "LeaseStore",
    "claim_task",
    "recover_task",
    "release_task",
    "renew_task",
]

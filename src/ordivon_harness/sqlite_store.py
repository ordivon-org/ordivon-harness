from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import stat
from typing import Iterator
import uuid

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, loads_strict

from .core_contracts import HarnessRunContract
from .store import (
    HARNESS_STORE_EVENT_KINDS,
    HarnessEventAdmission,
    HarnessEventWrite,
    HarnessRunEventRecord,
    HarnessRunLease,
    HarnessRunProjection,
    HarnessRunStatus,
    StoredHarnessObject,
)

_SCHEMA_VERSION = 1
_EVENT_PAYLOAD_KIND = "ordivon.harness-run-event-payload"
_CONTRACT_OBJECT_KIND = "harness-run-contract"
_MAX_EVENT_BATCH = 256

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_info(key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS schema_migrations(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    from_version INTEGER NOT NULL CHECK(from_version >= 1),
    to_version INTEGER NOT NULL UNIQUE CHECK(to_version > from_version),
    name TEXT NOT NULL,
    backup_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS object_refs(
    digest TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    byte_length INTEGER NOT NULL CHECK(byte_length >= 0),
    first_seen_at_ms INTEGER NOT NULL CHECK(first_seen_at_ms >= 0)
);

CREATE TABLE IF NOT EXISTS object_validation(
    digest TEXT PRIMARY KEY REFERENCES object_refs(digest) ON DELETE CASCADE,
    device INTEGER NOT NULL CHECK(device >= 0),
    inode INTEGER NOT NULL CHECK(inode >= 0),
    byte_length INTEGER NOT NULL CHECK(byte_length >= 0),
    modified_at_ns INTEGER NOT NULL CHECK(modified_at_ns >= 0),
    changed_at_ns INTEGER NOT NULL CHECK(changed_at_ns >= 0),
    mode INTEGER NOT NULL CHECK(mode >= 0)
);

CREATE TABLE IF NOT EXISTS runs(
    harness_run_id TEXT PRIMARY KEY,
    contract_digest TEXT NOT NULL UNIQUE,
    contract_object_digest TEXT NOT NULL REFERENCES object_refs(digest),
    caller_id TEXT NOT NULL,
    caller_run_ref TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'created', 'active', 'paused', 'stopped', 'completed', 'failed', 'abandoned'
    )),
    revision INTEGER NOT NULL CHECK(revision >= 1),
    created_at_ms INTEGER NOT NULL CHECK(created_at_ms >= 0),
    updated_at_ms INTEGER NOT NULL CHECK(updated_at_ms >= created_at_ms),
    terminal_event_id TEXT,
    UNIQUE(caller_id, caller_run_ref)
);

CREATE TABLE IF NOT EXISTS run_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    harness_run_id TEXT NOT NULL REFERENCES runs(harness_run_id) ON DELETE CASCADE,
    run_revision INTEGER NOT NULL CHECK(run_revision >= 1),
    event_kind TEXT NOT NULL,
    payload_digest TEXT NOT NULL REFERENCES object_refs(digest),
    caused_by_event_id TEXT REFERENCES run_events(event_id),
    recorded_at_ms INTEGER NOT NULL CHECK(recorded_at_ms >= 0),
    UNIQUE(harness_run_id, run_revision)
);

CREATE TABLE IF NOT EXISTS run_object_refs(
    harness_run_id TEXT NOT NULL REFERENCES runs(harness_run_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES run_events(event_id) ON DELETE CASCADE,
    digest TEXT NOT NULL REFERENCES object_refs(digest),
    role TEXT NOT NULL CHECK(role IN ('payload', 'reference')),
    PRIMARY KEY(event_id, digest)
);
CREATE UNIQUE INDEX IF NOT EXISTS run_object_refs_one_payload
    ON run_object_refs(event_id) WHERE role = 'payload';

CREATE TABLE IF NOT EXISTS run_leases(
    harness_run_id TEXT PRIMARY KEY REFERENCES runs(harness_run_id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    lease_revision INTEGER NOT NULL CHECK(lease_revision >= 1),
    run_revision INTEGER NOT NULL CHECK(run_revision >= 1),
    expires_at_ms INTEGER NOT NULL CHECK(expires_at_ms >= 0)
);

CREATE TABLE IF NOT EXISTS provider_calls(
    provider_call_id TEXT PRIMARY KEY,
    harness_run_id TEXT NOT NULL REFERENCES runs(harness_run_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL CHECK(generation >= 1),
    status TEXT NOT NULL,
    record_object_digest TEXT NOT NULL REFERENCES object_refs(digest),
    updated_at_ms INTEGER NOT NULL CHECK(updated_at_ms >= 0),
    UNIQUE(harness_run_id, generation)
);

CREATE TABLE IF NOT EXISTS tool_steps(
    tool_step_id TEXT PRIMARY KEY,
    harness_run_id TEXT NOT NULL REFERENCES runs(harness_run_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK(sequence >= 1),
    status TEXT NOT NULL,
    intent_object_digest TEXT NOT NULL REFERENCES object_refs(digest),
    receipt_object_digest TEXT REFERENCES object_refs(digest),
    observation_object_digest TEXT REFERENCES object_refs(digest),
    updated_at_ms INTEGER NOT NULL CHECK(updated_at_ms >= 0),
    UNIQUE(harness_run_id, sequence)
);

CREATE TABLE IF NOT EXISTS caller_bindings(
    harness_run_id TEXT PRIMARY KEY REFERENCES runs(harness_run_id) ON DELETE CASCADE,
    caller_id TEXT NOT NULL,
    caller_run_ref TEXT NOT NULL,
    contract_digest TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL CHECK(created_at_ms >= 0),
    UNIQUE(caller_id, caller_run_ref)
);
"""


class HarnessStoreError(RuntimeError):
    pass


class HarnessRevisionConflict(HarnessStoreError):
    pass


class HarnessEventConflict(HarnessStoreError):
    pass


class HarnessLeaseHeld(HarnessStoreError):
    pass


class HarnessLeaseConflict(HarnessStoreError):
    pass


class HarnessJournalCorruption(HarnessStoreError):
    pass


class HarnessObjectMissing(HarnessStoreError):
    pass


class HarnessObjectCorrupt(HarnessStoreError):
    pass


class HarnessTerminalConflict(HarnessStoreError):
    pass


@dataclass(frozen=True, slots=True)
class _ObjectFileIdentity:
    device: int
    inode: int
    byte_length: int
    modified_at_ns: int
    changed_at_ns: int
    mode: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _ObjectFileIdentity:
        return cls(
            device=int(value.st_dev),
            inode=int(value.st_ino),
            byte_length=int(value.st_size),
            modified_at_ns=int(value.st_mtime_ns),
            changed_at_ns=int(value.st_ctime_ns),
            mode=stat.S_IMODE(value.st_mode),
        )

    def to_sql(self) -> tuple[int, int, int, int, int, int]:
        return (
            self.device,
            self.inode,
            self.byte_length,
            self.modified_at_ns,
            self.changed_at_ns,
            self.mode,
        )

    def stable_read_identity(self) -> tuple[int, int, int, int, int]:
        # ctime changes when an already-published inode loses a temporary hard-link.
        # Content address, inode, size, mtime and mode are the stable read facts.
        return (
            self.device,
            self.inode,
            self.byte_length,
            self.modified_at_ns,
            self.mode,
        )


class _ContentAddressedStore:
    def __init__(self, root: Path) -> None:
        if root.exists() and root.is_symlink():
            raise HarnessObjectCorrupt("Harness object root cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not root.is_dir():
            raise HarnessObjectCorrupt("Harness object root is not a directory")
        os.chmod(root, 0o700)
        self.root = root
        for path in self.root.glob("*.json"):
            flags = os.O_RDONLY | os.O_NONBLOCK
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(path, flags)
            except OSError as error:
                raise HarnessObjectCorrupt(
                    f"Harness object path cannot be safely opened: {path.name}"
                ) from error
            try:
                file_stat = os.fstat(descriptor)
                if not stat.S_ISREG(file_stat.st_mode):
                    raise HarnessObjectCorrupt(
                        f"Harness object path is not a regular file: {path.name}"
                    )
                if stat.S_IMODE(file_stat.st_mode) != 0o600:
                    os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)

    def put(self, value: JsonValue, *, kind: str) -> StoredHarnessObject:
        if not kind or kind != kind.strip():
            raise ValueError("Harness object kind must be non-empty and trimmed")
        envelope: JsonValue = {
            "schemaVersion": 1,
            "kind": kind,
            "payload": value,
        }
        encoded = canonical_bytes(envelope)
        digest = canonical_digest(envelope)
        path = self._path(digest)
        try:
            existing_envelope, existing, _ = self._load(digest)
        except HarnessObjectMissing:
            pass
        else:
            if canonical_bytes(existing_envelope) != encoded:
                raise HarnessObjectCorrupt(
                    "Harness content address maps to different bytes"
                )
            return existing

        temporary = path.with_suffix(f".tmp-{os.getpid()}-{uuid.uuid4().hex}")
        directory_fd: int | None = None
        try:
            with temporary.open("xb") as handle:
                os.chmod(temporary, 0o600)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                existing_envelope, existing, _ = self._load(digest)
                if canonical_bytes(existing_envelope) != encoded:
                    raise HarnessObjectCorrupt(
                        "Harness content address maps to different bytes"
                    )
                return existing
            temporary.unlink()
            directory_fd = os.open(
                self.root,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            os.fsync(directory_fd)
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
            temporary.unlink(missing_ok=True)
        return StoredHarnessObject(digest, len(encoded), kind)

    def get(self, digest: str, *, expected_kind: str | None = None) -> JsonValue:
        envelope, stored, _ = self._load(digest)
        if expected_kind is not None and stored.kind != expected_kind:
            raise HarnessObjectCorrupt(
                f"Harness object kind is {stored.kind}, expected {expected_kind}"
            )
        return envelope["payload"]

    def inspect(self, digest: str) -> StoredHarnessObject:
        _, stored, _ = self._load(digest)
        return stored

    def inspect_with_identity(self, digest: str) -> tuple[StoredHarnessObject, _ObjectFileIdentity]:
        _, stored, identity = self._load(digest)
        return stored, identity

    def _load(
        self, digest: str
    ) -> tuple[dict[str, JsonValue], StoredHarnessObject, _ObjectFileIdentity]:
        path = self._path(digest)
        flags = os.O_RDONLY | os.O_NONBLOCK
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError as error:
            raise HarnessObjectMissing(f"Harness object is missing: {digest}") from error
        except OSError as error:
            raise HarnessObjectCorrupt(f"Harness object cannot be read: {digest}") from error
        try:
            before = _ObjectFileIdentity.from_stat(os.fstat(descriptor))
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                encoded = handle.read()
            after = _ObjectFileIdentity.from_stat(os.fstat(descriptor))
        except OSError as error:
            raise HarnessObjectCorrupt(f"Harness object cannot be read: {digest}") from error
        finally:
            os.close(descriptor)
        if (
            before.stable_read_identity() != after.stable_read_identity()
            or before.byte_length != len(encoded)
        ):
            raise HarnessObjectCorrupt(f"Harness object changed while read: {digest}")
        if before.mode != 0o600:
            raise HarnessObjectCorrupt(f"Harness object mode is not private: {digest}")
        try:
            value = loads_strict(encoded)
        except ValueError as error:
            raise HarnessObjectCorrupt(f"Harness object cannot be decoded: {digest}") from error
        if canonical_digest(value) != digest:
            raise HarnessObjectCorrupt("Harness object content differs from its address")
        if not isinstance(value, dict) or set(value) != {
            "schemaVersion",
            "kind",
            "payload",
        }:
            raise HarnessObjectCorrupt("Harness object envelope fields differ")
        if value["schemaVersion"] != 1 or not isinstance(value["kind"], str):
            raise HarnessObjectCorrupt("Harness object envelope version or kind is invalid")
        stored = StoredHarnessObject(digest, len(encoded), value["kind"])
        return value, stored, after

    def _path(self, digest: str) -> Path:
        if (
            not isinstance(digest, str)
            or len(digest) != 71
            or not digest.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in digest[7:])
        ):
            raise ValueError("Harness object key must be a sha256 digest")
        return self.root / f"{digest[7:]}.json"


class SQLiteHarnessStore:
    """P0 independent Harness Journal/CAS kernel.

    This Store is the current Harness persistence authority.
    New P0 migration slices consume this boundary instead of dual-writing.
    """

    @classmethod
    def initialize(cls, root: str | Path) -> SQLiteHarnessStore:
        state_root = Path(root)
        if state_root.exists() and state_root.is_symlink():
            raise HarnessJournalCorruption("Harness state root cannot be a symlink")
        state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not state_root.is_dir():
            raise HarnessJournalCorruption("Harness state root is not a directory")
        os.chmod(state_root, 0o700)
        database = state_root / "harness.sqlite3"
        if database.exists() and database.is_symlink():
            raise HarnessJournalCorruption("Harness Journal cannot be a symlink")
        if not database.exists():
            connection = sqlite3.connect(database, isolation_level=None)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = FULL")
                connection.executescript(_SCHEMA)
            finally:
                connection.close()
            os.chmod(database, 0o600)
        return cls(state_root)

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        if not self.root.exists():
            raise FileNotFoundError(f"Harness state root does not exist: {self.root}")
        if self.root.is_symlink() or not self.root.is_dir():
            raise HarnessJournalCorruption(
                "Harness state root must be a regular directory, not a symlink"
            )
        os.chmod(self.root, 0o700)
        self.database_path = self.root / "harness.sqlite3"
        if not self.database_path.exists():
            raise FileNotFoundError(f"Harness Journal is not initialized: {self.database_path}")
        if self.database_path.is_symlink() or not self.database_path.is_file():
            raise HarnessJournalCorruption("Harness Journal must be a regular file")
        self.objects = _ContentAddressedStore(self.root / "objects")
        # Never open/close WAL or SHM sidecars after this process holds SQLite
        # locks: POSIX fcntl locks are process-associated, and closing another fd
        # for the same inode can release locks owned by the SQLite connection.
        self._harden_database_files()
        self.connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA busy_timeout = 5000")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = FULL")
            self._validate_schema()
            self._validate_open()
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()
        self._harden_database_files()

    def __enter__(self) -> SQLiteHarnessStore:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def put_object(self, value: JsonValue, *, kind: str) -> StoredHarnessObject:
        return self.objects.put(value, kind=kind)

    def get_object(self, digest: str, *, expected_kind: str | None = None) -> JsonValue:
        return self.objects.get(digest, expected_kind=expected_kind)

    def inspect_object(self, digest: str) -> StoredHarnessObject:
        return self.objects.inspect(digest)

    def create_run(self, contract: HarnessRunContract) -> HarnessEventAdmission:
        contract_object = self.objects.put(contract.to_dict(), kind=_CONTRACT_OBJECT_KIND)
        event_data: dict[str, JsonValue] = {
            "contractDigest": contract.digest,
            "contractObjectDigest": contract_object.digest,
            "callerId": contract.caller_id,
            "callerRunRef": contract.caller_run_ref,
        }
        event_payload = self._event_payload(
            event_kind="harness.run-created",
            data=event_data,
        )
        payload_object = self.objects.put(event_payload, kind=_EVENT_PAYLOAD_KIND)
        event_id = (
            "event:harness-run-created:"
            + canonical_digest(
                {
                    "harnessRunId": contract.harness_run_id,
                    "contractDigest": contract.digest,
                }
            )[7:]
        )
        with self._transaction():
            existing = self.connection.execute(
                "SELECT contract_digest, contract_object_digest, caller_id, caller_run_ref, "
                "status, revision, created_at_ms, updated_at_ms, terminal_event_id "
                "FROM runs WHERE harness_run_id = ?",
                (contract.harness_run_id,),
            ).fetchone()
            if existing is not None:
                projection = self._projection_from_row(contract.harness_run_id, existing)
                if (
                    projection.contract_digest != contract.digest
                    or projection.contract_object_digest != contract_object.digest
                    or projection.caller_id != contract.caller_id
                    or projection.caller_run_ref != contract.caller_run_ref
                    or projection.revision != 1
                    or projection.status is not HarnessRunStatus.CREATED
                ):
                    raise HarnessEventConflict(
                        "Harness Run identity is already bound to another contract"
                    )
                self._require_exact_event(
                    event_id=event_id,
                    harness_run_id=contract.harness_run_id,
                    run_revision=1,
                    event_kind="harness.run-created",
                    payload_object=payload_object,
                    caused_by_event_id=None,
                    recorded_at_ms=contract.created_at_ms,
                    referenced_objects=(contract_object,),
                )
                return HarnessEventAdmission.EXISTING

            caller = self.connection.execute(
                "SELECT harness_run_id, contract_digest FROM caller_bindings "
                "WHERE caller_id = ? AND caller_run_ref = ?",
                (contract.caller_id, contract.caller_run_ref),
            ).fetchone()
            if caller is not None:
                raise HarnessEventConflict(
                    "Harness caller Run reference is already bound to another Run"
                )
            self._admit_object(contract_object, contract.created_at_ms)
            self._admit_object(payload_object, contract.created_at_ms)
            self.connection.execute(
                "INSERT INTO runs(harness_run_id, contract_digest, contract_object_digest, "
                "caller_id, caller_run_ref, status, revision, created_at_ms, updated_at_ms, "
                "terminal_event_id) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, NULL)",
                (
                    contract.harness_run_id,
                    contract.digest,
                    contract_object.digest,
                    contract.caller_id,
                    contract.caller_run_ref,
                    HarnessRunStatus.CREATED.value,
                    contract.created_at_ms,
                    contract.created_at_ms,
                ),
            )
            self.connection.execute(
                "INSERT INTO caller_bindings(harness_run_id, caller_id, caller_run_ref, "
                "contract_digest, created_at_ms) VALUES (?, ?, ?, ?, ?)",
                (
                    contract.harness_run_id,
                    contract.caller_id,
                    contract.caller_run_ref,
                    contract.digest,
                    contract.created_at_ms,
                ),
            )
            self.connection.execute(
                "INSERT INTO run_events(event_id, harness_run_id, run_revision, event_kind, "
                "payload_digest, caused_by_event_id, recorded_at_ms) VALUES (?, ?, 1, ?, ?, NULL, ?)",
                (
                    event_id,
                    contract.harness_run_id,
                    "harness.run-created",
                    payload_object.digest,
                    contract.created_at_ms,
                ),
            )
            self._insert_event_refs(
                contract.harness_run_id,
                event_id,
                payload_object,
                (contract_object,),
            )
        return HarnessEventAdmission.CREATED

    def load_run(self, harness_run_id: str) -> HarnessRunProjection:
        row = self.connection.execute(
            "SELECT contract_digest, contract_object_digest, caller_id, caller_run_ref, "
            "status, revision, created_at_ms, updated_at_ms, terminal_event_id "
            "FROM runs WHERE harness_run_id = ?",
            (harness_run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Harness Run does not exist: {harness_run_id}")
        return self._projection_from_row(harness_run_id, row)

    def list_runs(self) -> tuple[HarnessRunProjection, ...]:
        rows = self.connection.execute(
            "SELECT harness_run_id, contract_digest, contract_object_digest, "
            "caller_id, caller_run_ref, status, revision, created_at_ms, "
            "updated_at_ms, terminal_event_id "
            "FROM runs ORDER BY created_at_ms, harness_run_id"
        ).fetchall()
        return tuple(
            self._projection_from_row(row["harness_run_id"], row) for row in rows
        )

    def append_event(
        self,
        *,
        event_id: str,
        harness_run_id: str,
        event_kind: str,
        data: dict[str, JsonValue],
        expected_revision: int,
        recorded_at_ms: int,
        lease: HarnessRunLease,
        lease_checked_at_ms: int,
        caused_by_event_id: str | None = None,
        referenced_objects: tuple[StoredHarnessObject, ...] = (),
    ) -> HarnessEventAdmission:
        return self.append_events(
            harness_run_id=harness_run_id,
            events=(
                HarnessEventWrite(
                    event_id=event_id,
                    event_kind=event_kind,
                    data=data,
                    recorded_at_ms=recorded_at_ms,
                    caused_by_event_id=caused_by_event_id,
                    referenced_objects=referenced_objects,
                ),
            ),
            expected_revision=expected_revision,
            lease=lease,
            lease_checked_at_ms=lease_checked_at_ms,
        )

    def append_events(
        self,
        *,
        harness_run_id: str,
        events: tuple[HarnessEventWrite, ...],
        expected_revision: int,
        lease: HarnessRunLease,
        lease_checked_at_ms: int,
    ) -> HarnessEventAdmission:
        """Atomically append a bounded contiguous event sequence under one exact lease.

        Exact replay of the complete batch is idempotent after response loss. A partial
        replay is rejected because it cannot prove that the caller is repeating the same
        atomic admission. One lease fences the complete revision interval and is consumed
        only after every event and the final Run projection commit together.
        """

        if not events:
            raise ValueError("Harness Event batch must be non-empty")
        if len(events) > _MAX_EVENT_BATCH:
            raise ValueError(
                f"Harness Event batch exceeds the {_MAX_EVENT_BATCH}-event bound"
            )
        if expected_revision < 1:
            raise ValueError("Harness expected revision must be positive")
        if lease_checked_at_ms < 0:
            raise ValueError("Harness lease check time must be non-negative")

        event_ids = [event.event_id for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Harness Event batch identities must be unique")

        prepared: list[tuple[HarnessEventWrite, StoredHarnessObject]] = []
        for event in events:
            self._validate_event_identity(event.event_id)
            if (
                event.event_kind not in HARNESS_STORE_EVENT_KINDS
                or event.event_kind == "harness.run-created"
            ):
                raise ValueError(
                    f"unsupported Harness store event kind: {event.event_kind}"
                )
            if event.recorded_at_ms < 0:
                raise ValueError("Harness event time must be non-negative")
            payload = self._event_payload(
                event_kind=event.event_kind,
                data=event.data,
            )
            payload_object = self.objects.put(payload, kind=_EVENT_PAYLOAD_KIND)
            for item in event.referenced_objects:
                actual = self.objects.inspect(item.digest)
                if actual != item:
                    raise HarnessObjectCorrupt(
                        f"Harness referenced object metadata differs: {item.digest}"
                    )
            prepared.append((event, payload_object))

        with self._transaction():
            placeholders = ",".join("?" for _ in event_ids)
            existing_ids = {
                row["event_id"]
                for row in self.connection.execute(
                    f"SELECT event_id FROM run_events WHERE event_id IN ({placeholders})",
                    tuple(event_ids),
                )
            }
            if existing_ids:
                if existing_ids != set(event_ids):
                    raise HarnessEventConflict(
                        "Harness Event batch is only partially admitted"
                    )
                for offset, (event, payload_object) in enumerate(prepared, start=1):
                    self._require_exact_event(
                        event_id=event.event_id,
                        harness_run_id=harness_run_id,
                        run_revision=expected_revision + offset,
                        event_kind=event.event_kind,
                        payload_object=payload_object,
                        caused_by_event_id=event.caused_by_event_id,
                        recorded_at_ms=event.recorded_at_ms,
                        referenced_objects=event.referenced_objects,
                    )
                return HarnessEventAdmission.EXISTING

            row = self.connection.execute(
                "SELECT contract_digest, contract_object_digest, caller_id, caller_run_ref, "
                "status, revision, created_at_ms, updated_at_ms, terminal_event_id "
                "FROM runs WHERE harness_run_id = ?",
                (harness_run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Harness Run does not exist: {harness_run_id}")
            current = self._projection_from_row(harness_run_id, row)
            if current.revision != expected_revision:
                raise HarnessRevisionConflict(
                    f"Harness Run revision is {current.revision}, expected {expected_revision}"
                )
            if current.status.terminal:
                raise HarnessTerminalConflict(
                    "terminal Harness Run cannot admit another event"
                )
            self._validate_exact_lease(lease, checked_at_ms=lease_checked_at_ms)
            if lease.harness_run_id != harness_run_id or lease.run_revision != expected_revision:
                raise HarnessLeaseConflict(
                    "Harness Run lease is bound to another revision"
                )

            status = current.status
            previous_time = current.updated_at_ms
            preceding_batch_ids: set[str] = set()
            terminal_event_id: str | None = None
            for index, (event, _) in enumerate(prepared):
                if status.terminal:
                    raise HarnessTerminalConflict(
                        "Harness Event batch contains an Event after terminal state"
                    )
                if event.recorded_at_ms < previous_time:
                    raise ValueError(
                        "Harness Event batch time precedes the current Run head"
                    )
                cause_id = event.caused_by_event_id
                if cause_id is not None and cause_id not in preceding_batch_ids:
                    cause = self.connection.execute(
                        "SELECT harness_run_id FROM run_events WHERE event_id = ?",
                        (cause_id,),
                    ).fetchone()
                    if cause is None or cause["harness_run_id"] != harness_run_id:
                        raise HarnessEventConflict(
                            "Harness caused-by Event is absent, later in the batch, "
                            "or belongs to another Run"
                        )
                status = self._status_after(event.event_kind, status)
                if status.terminal:
                    terminal_event_id = event.event_id
                    if index != len(prepared) - 1:
                        raise HarnessTerminalConflict(
                            "terminal Harness Event must be last in its batch"
                        )
                previous_time = event.recorded_at_ms
                preceding_batch_ids.add(event.event_id)

            final_revision = expected_revision + len(prepared)
            changed = self.connection.execute(
                "UPDATE runs SET status = ?, revision = ?, updated_at_ms = ?, "
                "terminal_event_id = ? WHERE harness_run_id = ? AND revision = ?",
                (
                    status.value,
                    final_revision,
                    previous_time,
                    terminal_event_id,
                    harness_run_id,
                    expected_revision,
                ),
            ).rowcount
            if changed != 1:
                raise HarnessRevisionConflict(
                    "Harness Run revision changed during batch admission"
                )

            for offset, (event, payload_object) in enumerate(prepared, start=1):
                self._admit_object(payload_object, event.recorded_at_ms)
                for item in event.referenced_objects:
                    self._admit_object(item, event.recorded_at_ms)
                self.connection.execute(
                    "INSERT INTO run_events(event_id, harness_run_id, run_revision, "
                    "event_kind, payload_digest, caused_by_event_id, recorded_at_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        harness_run_id,
                        expected_revision + offset,
                        event.event_kind,
                        payload_object.digest,
                        event.caused_by_event_id,
                        event.recorded_at_ms,
                    ),
                )
                self._insert_event_refs(
                    harness_run_id,
                    event.event_id,
                    payload_object,
                    event.referenced_objects,
                )
            self._consume_exact_lease(lease)
        return HarnessEventAdmission.CREATED

    def list_run_events(
        self, harness_run_id: str, *, after_sequence: int = 0
    ) -> tuple[HarnessRunEventRecord, ...]:
        if after_sequence < 0:
            raise ValueError("Harness event sequence cursor must be non-negative")
        if (
            self.connection.execute(
                "SELECT 1 FROM runs WHERE harness_run_id = ?", (harness_run_id,)
            ).fetchone()
            is None
        ):
            raise KeyError(f"Harness Run does not exist: {harness_run_id}")
        rows = self.connection.execute(
            "SELECT sequence, event_id, harness_run_id, run_revision, event_kind, "
            "payload_digest, caused_by_event_id, recorded_at_ms FROM run_events "
            "WHERE harness_run_id = ? AND sequence > ? ORDER BY sequence",
            (harness_run_id, after_sequence),
        ).fetchall()
        values: list[HarnessRunEventRecord] = []
        for row in rows:
            raw = self.objects.get(row["payload_digest"], expected_kind=_EVENT_PAYLOAD_KIND)
            if not isinstance(raw, dict) or set(raw) != {
                "schemaVersion",
                "kind",
                "eventKind",
                "data",
            }:
                raise HarnessObjectCorrupt("Harness Run event payload fields differ")
            if (
                raw["schemaVersion"] != 1
                or raw["kind"] != _EVENT_PAYLOAD_KIND
                or raw["eventKind"] != row["event_kind"]
                or not isinstance(raw["data"], dict)
            ):
                raise HarnessJournalCorruption("Harness Run event payload is inconsistent")
            values.append(
                HarnessRunEventRecord(
                    sequence=int(row["sequence"]),
                    event_id=row["event_id"],
                    harness_run_id=row["harness_run_id"],
                    run_revision=int(row["run_revision"]),
                    event_kind=row["event_kind"],
                    payload_digest=row["payload_digest"],
                    data=dict(raw["data"]),
                    caused_by_event_id=row["caused_by_event_id"],
                    recorded_at_ms=int(row["recorded_at_ms"]),
                )
            )
        return tuple(values)

    def acquire_run_lease(
        self,
        harness_run_id: str,
        *,
        owner_id: str,
        ttl_ms: int,
        now_ms: int,
    ) -> HarnessRunLease:
        if not owner_id or owner_id != owner_id.strip():
            raise ValueError("Harness lease owner must be non-empty and trimmed")
        if ttl_ms < 1 or now_ms < 0:
            raise ValueError("Harness lease TTL must be positive and time non-negative")
        with self._transaction():
            run = self.load_run(harness_run_id)
            if run.status.terminal:
                raise HarnessTerminalConflict("terminal Harness Run cannot be leased")
            current = self.connection.execute(
                "SELECT owner_id, lease_revision, run_revision, expires_at_ms "
                "FROM run_leases WHERE harness_run_id = ?",
                (harness_run_id,),
            ).fetchone()
            lease_revision = 1
            if current is not None:
                if int(current["expires_at_ms"]) > now_ms:
                    if (
                        current["owner_id"] == owner_id
                        and int(current["run_revision"]) == run.revision
                    ):
                        return HarnessRunLease(
                            harness_run_id=harness_run_id,
                            owner_id=owner_id,
                            lease_revision=int(current["lease_revision"]),
                            run_revision=run.revision,
                            expires_at_ms=int(current["expires_at_ms"]),
                        )
                    raise HarnessLeaseHeld("Harness Run is leased by another execution")
                lease_revision = int(current["lease_revision"]) + 1
            expires_at_ms = now_ms + ttl_ms
            self.connection.execute(
                "INSERT INTO run_leases(harness_run_id, owner_id, lease_revision, run_revision, "
                "expires_at_ms) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(harness_run_id) DO UPDATE SET owner_id = excluded.owner_id, "
                "lease_revision = excluded.lease_revision, run_revision = excluded.run_revision, "
                "expires_at_ms = excluded.expires_at_ms",
                (
                    harness_run_id,
                    owner_id,
                    lease_revision,
                    run.revision,
                    expires_at_ms,
                ),
            )
            return HarnessRunLease(
                harness_run_id=harness_run_id,
                owner_id=owner_id,
                lease_revision=lease_revision,
                run_revision=run.revision,
                expires_at_ms=expires_at_ms,
            )

    def release_run_lease(self, lease: HarnessRunLease) -> bool:
        with self._transaction():
            changed = self.connection.execute(
                "DELETE FROM run_leases WHERE harness_run_id = ? AND owner_id = ? "
                "AND lease_revision = ? AND run_revision = ? AND expires_at_ms = ?",
                (
                    lease.harness_run_id,
                    lease.owner_id,
                    lease.lease_revision,
                    lease.run_revision,
                    lease.expires_at_ms,
                ),
            ).rowcount
        return changed == 1

    def _validate_open(self) -> None:
        """Validate global physical authority without replaying unrelated Run histories."""
        quick = tuple(str(row[0]) for row in self.connection.execute("PRAGMA quick_check"))
        if quick != ("ok",):
            raise HarnessJournalCorruption(f"Harness Journal quick_check failed: {quick}")
        rows = self.connection.execute(
            "SELECT digest, kind, byte_length FROM object_refs ORDER BY digest"
        ).fetchall()
        for row in rows:
            actual, _ = self.objects.inspect_with_identity(row["digest"])
            expected = StoredHarnessObject(
                row["digest"], int(row["byte_length"]), row["kind"]
            )
            if actual != expected:
                raise HarnessJournalCorruption(
                    f"Harness object metadata differs from Journal: {row['digest']}"
                )

    def validate_run_history(self, harness_run_id: str) -> None:
        """Fail closed on the semantic history of one Run before execution resumes."""
        self._validate_run_history(harness_run_id)

    def doctor(self, *, full: bool = True) -> dict[str, JsonValue]:
        quick = tuple(str(row[0]) for row in self.connection.execute("PRAGMA quick_check"))
        if quick != ("ok",):
            raise HarnessJournalCorruption(f"Harness Journal quick_check failed: {quick}")
        object_rows = self.connection.execute(
            "SELECT digest, kind, byte_length FROM object_refs ORDER BY digest"
        ).fetchall()
        verified: list[tuple[str, _ObjectFileIdentity]] = []
        for row in object_rows:
            actual, identity = self.objects.inspect_with_identity(row["digest"])
            expected = StoredHarnessObject(row["digest"], int(row["byte_length"]), row["kind"])
            if actual != expected:
                raise HarnessJournalCorruption(
                    f"Harness object metadata differs from Journal: {row['digest']}"
                )
            if full:
                verified.append((row["digest"], identity))
        if verified:
            with self._transaction():
                self.connection.executemany(
                    "INSERT INTO object_validation(digest, device, inode, byte_length, "
                    "modified_at_ns, changed_at_ns, mode) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(digest) DO UPDATE SET device = excluded.device, "
                    "inode = excluded.inode, byte_length = excluded.byte_length, "
                    "modified_at_ns = excluded.modified_at_ns, "
                    "changed_at_ns = excluded.changed_at_ns, mode = excluded.mode",
                    ((digest, *identity.to_sql()) for digest, identity in verified),
                )
        run_ids = tuple(
            row["harness_run_id"]
            for row in self.connection.execute(
                "SELECT harness_run_id FROM runs ORDER BY harness_run_id"
            )
        )
        for run_id in run_ids:
            self._validate_run_history(run_id)
        event_count = int(self.connection.execute("SELECT COUNT(*) FROM run_events").fetchone()[0])
        lease_count = int(self.connection.execute("SELECT COUNT(*) FROM run_leases").fetchone()[0])
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-store-doctor",
            "healthy": True,
            "full": full,
            "runs": len(run_ids),
            "events": event_count,
            "objects": len(object_rows),
            "leases": lease_count,
            "quickCheck": list(quick),
        }

    def table_names(self) -> tuple[str, ...]:
        rows = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        return tuple(row["name"] for row in rows)

    def _validate_schema(self) -> None:
        row = self.connection.execute(
            "SELECT value FROM schema_info WHERE key = 'schema_version'"
        ).fetchone()
        if row is None or row["value"] != str(_SCHEMA_VERSION):
            raise HarnessJournalCorruption("Harness Journal schema version is unsupported")
        required = {
            "schema_info",
            "schema_migrations",
            "runs",
            "run_events",
            "object_refs",
            "run_object_refs",
            "run_leases",
            "provider_calls",
            "tool_steps",
            "caller_bindings",
            "object_validation",
        }
        missing = required - set(self.table_names())
        if missing:
            raise HarnessJournalCorruption(
                f"Harness Journal schema tables are missing: {sorted(missing)}"
            )

    def _validate_run_history(self, harness_run_id: str) -> None:
        projection = self.load_run(harness_run_id)
        events = self.list_run_events(harness_run_id)
        if not events or events[0].event_kind != "harness.run-created":
            raise HarnessJournalCorruption(f"Harness Run has no creation Event: {harness_run_id}")
        expected_revisions = tuple(range(1, len(events) + 1))
        revisions = tuple(item.run_revision for item in events)
        if revisions != expected_revisions:
            raise HarnessJournalCorruption(
                f"Harness Run Event revisions are not contiguous: {harness_run_id}"
            )
        status = HarnessRunStatus.CREATED
        terminal_event_id: str | None = None
        previous_time = -1
        for event in events:
            if event.recorded_at_ms < previous_time:
                raise HarnessJournalCorruption(
                    f"Harness Run Event time regressed: {harness_run_id}"
                )
            previous_time = event.recorded_at_ms
            status = self._status_after(event.event_kind, status)
            if terminal_event_id is not None:
                raise HarnessJournalCorruption(
                    f"Harness Run has Events after terminal state: {harness_run_id}"
                )
            if status.terminal:
                terminal_event_id = event.event_id
        if (
            projection.revision != len(events)
            or projection.status is not status
            or projection.terminal_event_id != terminal_event_id
            or projection.updated_at_ms != events[-1].recorded_at_ms
        ):
            raise HarnessJournalCorruption(
                f"Harness Run projection differs from Event history: {harness_run_id}"
            )
        contract_raw = self.objects.get(
            projection.contract_object_digest, expected_kind=_CONTRACT_OBJECT_KIND
        )
        if not isinstance(contract_raw, dict):
            raise HarnessObjectCorrupt("Harness Run Contract object must be an object")
        try:
            contract = HarnessRunContract.from_dict(contract_raw)
        except ValueError as error:
            raise HarnessObjectCorrupt("Harness Run Contract object is invalid") from error
        if (
            contract.harness_run_id != harness_run_id
            or contract.digest != projection.contract_digest
            or contract.caller_id != projection.caller_id
            or contract.caller_run_ref != projection.caller_run_ref
        ):
            raise HarnessJournalCorruption(
                f"Harness Run Contract differs from projection: {harness_run_id}"
            )

    def _event_payload(
        self, *, event_kind: str, data: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if event_kind not in HARNESS_STORE_EVENT_KINDS:
            raise ValueError(f"unsupported Harness store event kind: {event_kind}")
        return {
            "schemaVersion": 1,
            "kind": _EVENT_PAYLOAD_KIND,
            "eventKind": event_kind,
            "data": data,
        }

    def _admit_object(self, value: StoredHarnessObject, recorded_at_ms: int) -> None:
        existing = self.connection.execute(
            "SELECT kind, byte_length FROM object_refs WHERE digest = ?", (value.digest,)
        ).fetchone()
        if existing is not None:
            if existing["kind"] != value.kind or int(existing["byte_length"]) != value.byte_length:
                raise HarnessJournalCorruption(
                    f"Harness object digest has conflicting metadata: {value.digest}"
                )
            return
        self.connection.execute(
            "INSERT INTO object_refs(digest, kind, byte_length, first_seen_at_ms) "
            "VALUES (?, ?, ?, ?)",
            (value.digest, value.kind, value.byte_length, recorded_at_ms),
        )

    def _insert_event_refs(
        self,
        harness_run_id: str,
        event_id: str,
        payload_object: StoredHarnessObject,
        referenced_objects: tuple[StoredHarnessObject, ...],
    ) -> None:
        edges = {(payload_object.digest, "payload")}
        edges.update((item.digest, "reference") for item in referenced_objects)
        self.connection.executemany(
            "INSERT INTO run_object_refs(harness_run_id, event_id, digest, role) "
            "VALUES (?, ?, ?, ?)",
            ((harness_run_id, event_id, digest, role) for digest, role in sorted(edges)),
        )

    def _require_exact_event(
        self,
        *,
        event_id: str,
        harness_run_id: str,
        run_revision: int,
        event_kind: str,
        payload_object: StoredHarnessObject,
        caused_by_event_id: str | None,
        recorded_at_ms: int,
        referenced_objects: tuple[StoredHarnessObject, ...],
    ) -> None:
        row = self.connection.execute(
            "SELECT harness_run_id, run_revision, event_kind, payload_digest, "
            "caused_by_event_id, recorded_at_ms FROM run_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise HarnessEventConflict("Harness Event identity is not admitted")
        expected = (
            harness_run_id,
            run_revision,
            event_kind,
            payload_object.digest,
            caused_by_event_id,
            recorded_at_ms,
        )
        actual = (
            row["harness_run_id"],
            int(row["run_revision"]),
            row["event_kind"],
            row["payload_digest"],
            row["caused_by_event_id"],
            int(row["recorded_at_ms"]),
        )
        if actual != expected:
            raise HarnessEventConflict(
                "Harness Event identity is already bound to different content"
            )
        expected_edges = {(payload_object.digest, "payload")}
        expected_edges.update((item.digest, "reference") for item in referenced_objects)
        actual_edges = {
            (row["digest"], row["role"])
            for row in self.connection.execute(
                "SELECT digest, role FROM run_object_refs WHERE event_id = ?",
                (event_id,),
            )
        }
        if actual_edges != expected_edges:
            raise HarnessEventConflict(
                "Harness Event identity is bound to different object references"
            )

    def _validate_exact_lease(self, lease: HarnessRunLease, *, checked_at_ms: int) -> None:
        row = self.connection.execute(
            "SELECT owner_id, lease_revision, run_revision, expires_at_ms "
            "FROM run_leases WHERE harness_run_id = ?",
            (lease.harness_run_id,),
        ).fetchone()
        if (
            row is None
            or row["owner_id"] != lease.owner_id
            or int(row["lease_revision"]) != lease.lease_revision
            or int(row["run_revision"]) != lease.run_revision
            or int(row["expires_at_ms"]) != lease.expires_at_ms
            or int(row["expires_at_ms"]) <= checked_at_ms
        ):
            raise HarnessLeaseConflict("Harness Run lease is absent, superseded, or expired")

    def _consume_exact_lease(self, lease: HarnessRunLease) -> None:
        changed = self.connection.execute(
            "DELETE FROM run_leases WHERE harness_run_id = ? AND owner_id = ? "
            "AND lease_revision = ? AND run_revision = ? AND expires_at_ms = ?",
            (
                lease.harness_run_id,
                lease.owner_id,
                lease.lease_revision,
                lease.run_revision,
                lease.expires_at_ms,
            ),
        ).rowcount
        if changed != 1:
            raise HarnessLeaseConflict("Harness Run lease changed during admission")

    @staticmethod
    def _projection_from_row(harness_run_id: str, row: sqlite3.Row) -> HarnessRunProjection:
        try:
            return HarnessRunProjection(
                harness_run_id=harness_run_id,
                contract_digest=row["contract_digest"],
                contract_object_digest=row["contract_object_digest"],
                caller_id=row["caller_id"],
                caller_run_ref=row["caller_run_ref"],
                status=HarnessRunStatus(row["status"]),
                revision=int(row["revision"]),
                created_at_ms=int(row["created_at_ms"]),
                updated_at_ms=int(row["updated_at_ms"]),
                terminal_event_id=row["terminal_event_id"],
            )
        except (TypeError, ValueError) as error:
            raise HarnessJournalCorruption(
                f"Harness Run projection is invalid: {harness_run_id}"
            ) from error

    @staticmethod
    def _status_after(
        event_kind: str, current_status: HarnessRunStatus | None = None
    ) -> HarnessRunStatus:
        if event_kind == "harness.run-created":
            return HarnessRunStatus.CREATED
        if event_kind == "harness.run-paused":
            return HarnessRunStatus.PAUSED
        if event_kind == "harness.run-stopped":
            return HarnessRunStatus.STOPPED
        if event_kind == "harness.run-completed":
            return HarnessRunStatus.COMPLETED
        if event_kind == "harness.run-failed":
            return HarnessRunStatus.FAILED
        if event_kind == "harness.run-abandoned":
            return HarnessRunStatus.ABANDONED
        if event_kind in {"harness.trace-recorded", "harness.run-recovery-recorded"}:
            if current_status is None:
                raise ValueError("status-preserving Harness Event requires current status")
            return current_status
        return HarnessRunStatus.ACTIVE

    @staticmethod
    def _validate_event_identity(event_id: str) -> None:
        if (
            not isinstance(event_id, str)
            or not event_id.startswith("event:")
            or event_id != event_id.strip()
            or len(event_id.encode("utf-8")) > 500
        ):
            raise ValueError("Harness Event identity must start with event:")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def _harden_database_files(self) -> None:
        for path, required in (
            (self.database_path, True),
            (Path(str(self.database_path) + "-wal"), False),
            (Path(str(self.database_path) + "-shm"), False),
        ):
            flags = os.O_RDONLY | os.O_NONBLOCK
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(path, flags)
            except FileNotFoundError:
                if required:
                    raise HarnessJournalCorruption(
                        f"Harness Journal file disappeared: {path.name}"
                    )
                continue
            except OSError as error:
                raise HarnessJournalCorruption(
                    f"Harness Journal file cannot be safely opened: {path.name}"
                ) from error
            try:
                file_stat = os.fstat(descriptor)
                if not stat.S_ISREG(file_stat.st_mode):
                    raise HarnessJournalCorruption(
                        f"Harness Journal file is not regular: {path.name}"
                    )
                if stat.S_IMODE(file_stat.st_mode) != 0o600:
                    os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)

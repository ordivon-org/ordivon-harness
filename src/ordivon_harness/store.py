from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from anc_canonical import JsonValue

from .core_contracts import HarnessRunContract


class HarnessRunStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"

    @property
    def terminal(self) -> bool:
        return self in {
            HarnessRunStatus.STOPPED,
            HarnessRunStatus.COMPLETED,
            HarnessRunStatus.FAILED,
            HarnessRunStatus.ABANDONED,
        }


class HarnessEventAdmission(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


HARNESS_STORE_EVENT_KINDS = frozenset(
    {
        "harness.run-created",
        "harness.run-started",
        "harness.run-resumed",
        "harness.snapshot-recorded",
        "harness.provider-call-claimed",
        "harness.provider-call-superseded",
        "harness.provider-call-dispatching",
        "harness.provider-call-completed",
        "harness.provider-call-failed",
        "harness.provider-call-unknown",
        "harness.tool-step-prepared",
        "harness.tool-step-dispatched",
        "harness.tool-step-recorded",
        "harness.tool-step-unknown",
        "harness.tool-step-reconciled",
        "harness.run-paused",
        "harness.trace-recorded",
        "harness.run-recovery-recorded",
        "harness.run-stopped",
        "harness.completion-proposed",
        "harness.run-failed",
        "harness.run-completed",
        "harness.run-abandoned",
    }
)


@dataclass(frozen=True, slots=True)
class StoredHarnessObject:
    digest: str
    byte_length: int
    kind: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "digest": self.digest,
            "byteLength": self.byte_length,
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class HarnessRunProjection:
    harness_run_id: str
    contract_digest: str
    contract_object_digest: str
    caller_id: str
    caller_run_ref: str
    status: HarnessRunStatus
    revision: int
    created_at_ms: int
    updated_at_ms: int
    terminal_event_id: str | None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "harnessRunId": self.harness_run_id,
            "contractDigest": self.contract_digest,
            "contractObjectDigest": self.contract_object_digest,
            "callerId": self.caller_id,
            "callerRunRef": self.caller_run_ref,
            "status": self.status.value,
            "revision": self.revision,
            "createdAtMs": self.created_at_ms,
            "updatedAtMs": self.updated_at_ms,
            "terminalEventId": self.terminal_event_id,
        }


@dataclass(frozen=True, slots=True)
class HarnessRunEventRecord:
    sequence: int
    event_id: str
    harness_run_id: str
    run_revision: int
    event_kind: str
    payload_digest: str
    data: dict[str, JsonValue]
    caused_by_event_id: str | None
    recorded_at_ms: int

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "sequence": self.sequence,
            "eventId": self.event_id,
            "harnessRunId": self.harness_run_id,
            "runRevision": self.run_revision,
            "eventKind": self.event_kind,
            "payloadDigest": self.payload_digest,
            "data": self.data,
            "causedByEventId": self.caused_by_event_id,
            "recordedAtMs": self.recorded_at_ms,
        }


@dataclass(frozen=True, slots=True)
class HarnessRunLease:
    harness_run_id: str
    owner_id: str
    lease_revision: int
    run_revision: int
    expires_at_ms: int

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "harnessRunId": self.harness_run_id,
            "ownerId": self.owner_id,
            "leaseRevision": self.lease_revision,
            "runRevision": self.run_revision,
            "expiresAtMs": self.expires_at_ms,
        }


@runtime_checkable
class HarnessStore(Protocol):
    """Behavioral persistence boundary for one independent Harness product."""

    def create_run(self, contract: HarnessRunContract) -> HarnessEventAdmission: ...

    def load_run(self, harness_run_id: str) -> HarnessRunProjection: ...

    def list_runs(self) -> tuple[HarnessRunProjection, ...]: ...

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
    ) -> HarnessEventAdmission: ...

    def list_run_events(
        self, harness_run_id: str, *, after_sequence: int = 0
    ) -> tuple[HarnessRunEventRecord, ...]: ...

    def acquire_run_lease(
        self,
        harness_run_id: str,
        *,
        owner_id: str,
        ttl_ms: int,
        now_ms: int,
    ) -> HarnessRunLease: ...

    def release_run_lease(self, lease: HarnessRunLease) -> bool: ...

    def put_object(self, value: JsonValue, *, kind: str) -> StoredHarnessObject: ...

    def get_object(self, digest: str, *, expected_kind: str | None = None) -> JsonValue: ...

    def inspect_object(self, digest: str) -> StoredHarnessObject: ...

    def doctor(self, *, full: bool = True) -> dict[str, JsonValue]: ...

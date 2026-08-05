from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from anc_canonical import JsonValue, canonical_digest

from ..errors import HarnessLifecycleError
from ..protocol import (
    HarnessProviderCallFailureReceipt,
    HarnessProviderCallSource,
    HarnessProviderCallStatus,
    HarnessRunPauseReason,
    HarnessRunSnapshot,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
)
from ..run_state import HarnessRunState
from .model import AgentTurnResult


@runtime_checkable
class HarnessStoredObject(Protocol):
    digest: str
    byte_length: int
    kind: str


@runtime_checkable
class HarnessProviderCallRecordView(Protocol):
    record_id: str
    provider_call_id: str
    harness_run_id: str
    source_kind: HarnessProviderCallSource
    source_digest: str
    source_object_digest: str
    state_object_digest: str
    turn_id: str
    turn_sequence: int
    request_digest: str
    provider_request_digest: str
    adapter_id: str
    requested_model_id: str
    holder_id: str
    claim_generation: int
    status: HarnessProviderCallStatus
    result_digest: str | None
    result_object_digest: str | None
    failure_digest: str | None
    failure_object_digest: str | None
    previous_record_digest: str | None
    issued_at_ms: int
    expires_at_ms: int
    recorded_at_ms: int

    @property
    def digest(self) -> str: ...

    def to_dict(self) -> dict[str, JsonValue]: ...


@runtime_checkable
class HarnessDispatchFenceView(Protocol):
    fence_id: str
    harness_run_id: str
    intent_digest: str
    runtime_operation: str
    client_request_id: str
    issued_at_ms: int
    expires_at_ms: int

    @property
    def authority_generation(self) -> int: ...

    @property
    def digest(self) -> str: ...

    def to_dict(self) -> dict[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class HarnessRunStoreBinding:
    harness_run_id: str
    assignment_id: str
    assignment_generation: int
    assignment_digest: str

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-run-store-binding",
            "harnessRunId": self.harness_run_id,
            "assignmentId": self.assignment_id,
            "assignmentGeneration": self.assignment_generation,
            "assignmentDigest": self.assignment_digest,
        }


@dataclass(frozen=True, slots=True)
class StoredHarnessRunSnapshot:
    snapshot: HarnessRunSnapshot
    snapshot_object: HarnessStoredObject
    state: HarnessRunState
    state_object: HarnessStoredObject


@dataclass(frozen=True, slots=True)
class HarnessProviderCallSourceRef:
    kind: HarnessProviderCallSource
    digest: str
    object_digest: str


@dataclass(frozen=True, slots=True)
class StoredHarnessProviderCall:
    record: HarnessProviderCallRecordView
    record_object: HarnessStoredObject
    state: HarnessRunState
    state_object: HarnessStoredObject
    result: AgentTurnResult | None
    result_object: HarnessStoredObject | None
    failure: HarnessProviderCallFailureReceipt | None
    failure_object: HarnessStoredObject | None


class HarnessProviderCallClaimHeld(HarnessLifecycleError):
    pass


class HarnessProviderCallRecoveryRequired(HarnessLifecycleError):
    pass


class HarnessProviderCallRequestMismatch(HarnessLifecycleError):
    pass


@dataclass(frozen=True, slots=True)
class StoredHarnessToolStep:
    intent: HarnessToolStepIntent
    intent_object: HarnessStoredObject
    fence: HarnessDispatchFenceView | None
    fence_object: HarnessStoredObject | None
    receipt: HarnessToolStepReceipt | None
    receipt_object: HarnessStoredObject | None
    previous_receipt: HarnessToolStepReceipt | None
    previous_receipt_object: HarnessStoredObject | None
    observation: dict[str, JsonValue] | None
    observation_object: HarnessStoredObject | None


@runtime_checkable
class HarnessRunContinuityStore(Protocol):
    """Owner-neutral durable Run interface consumed by the Agent/Tool loop.

    This protocol contains Harness semantic objects only. It exposes no Host
    projection, Journal revision, lease, CAS implementation, or Task state.
    """

    @property
    def binding(self) -> HarnessRunStoreBinding: ...

    @property
    def harness_run_id(self) -> str: ...

    @property
    def provider_outcome_requires_resume(self) -> bool: ...

    @property
    def caller_revision(self) -> int: ...

    def clock_ms(self) -> int: ...

    def bind_state(self, state: HarnessRunState) -> None: ...

    def assignment_provider_source(self) -> HarnessProviderCallSourceRef: ...

    def snapshot_provider_source(
        self, retained: StoredHarnessRunSnapshot
    ) -> HarnessProviderCallSourceRef: ...

    def claim_provider_call(
        self,
        *,
        source: HarnessProviderCallSourceRef,
        turn_id: str,
        turn_sequence: int,
        request_digest: str,
        provider_request_digest: str,
        adapter_id: str,
        requested_model_id: str,
        holder_id: str,
        ttl_ms: int,
    ) -> StoredHarnessProviderCall: ...

    def mark_provider_call_dispatching(
        self, retained: StoredHarnessProviderCall
    ) -> StoredHarnessProviderCall: ...

    def complete_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        result: AgentTurnResult,
    ) -> StoredHarnessProviderCall: ...

    def fail_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        *,
        failure: HarnessProviderCallFailureReceipt,
    ) -> StoredHarnessProviderCall: ...

    def fail_claimed_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        *,
        failure: HarnessProviderCallFailureReceipt,
    ) -> StoredHarnessProviderCall: ...

    def retry_failed_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        *,
        holder_id: str,
        ttl_ms: int,
    ) -> StoredHarnessProviderCall: ...

    def load_current_provider_call(self) -> StoredHarnessProviderCall: ...

    def load_provider_replay_state(
        self,
        *,
        source: HarnessProviderCallSourceRef,
        snapshot: StoredHarnessRunSnapshot,
        additional_messages: tuple[dict[str, JsonValue], ...],
        adapter_id: str,
        requested_model_id: str,
    ) -> HarnessRunState: ...

    def prepare_tool_step(self, intent: HarnessToolStepIntent) -> StoredHarnessRunSnapshot: ...

    def assert_dispatch_fence_current(
        self,
        fence: HarnessDispatchFenceView,
        *,
        require_unexpired: bool = True,
    ) -> None: ...

    def record_tool_step_receipt(
        self,
        receipt: HarnessToolStepReceipt,
        observation: dict[str, JsonValue],
    ) -> StoredHarnessRunSnapshot: ...

    def load_current_tool_step(self) -> StoredHarnessToolStep: ...

    def record_pause(self, pause_reason: HarnessRunPauseReason) -> StoredHarnessRunSnapshot: ...

    def load_current_snapshot(self) -> StoredHarnessRunSnapshot: ...

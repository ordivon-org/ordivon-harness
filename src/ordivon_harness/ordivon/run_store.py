from __future__ import annotations

from dataclasses import dataclass, replace

from anc_canonical import JsonValue, canonical_digest, validate_json_value
from .._host_compat.extensions import (
    EventConflict,
    HostExtensionPort,
    HostKernelError,
    LeaseHeld,
    RevisionConflict,
    StoredObject,
)
from ..protocol import (
    HarnessDispatchFence,
    HarnessProviderCallFailureReceipt,
    HarnessProviderCallRecord,
    HarnessProviderCallSource,
    HarnessProviderCallStatus,
    HarnessRunPauseReason,
    HarnessRunSnapshot,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
)

from ..event_kinds import (
    HARNESS_PROVIDER_CALL_CLAIMED,
    HARNESS_PROVIDER_CALL_COMPLETED,
    HARNESS_PROVIDER_CALL_DISPATCHING,
    HARNESS_PROVIDER_CALL_FAILED,
    HARNESS_PROVIDER_CALL_SUPERSEDED,
    HARNESS_PROVIDER_CALL_UNKNOWN,
    HARNESS_RUN_SNAPSHOT_RECORDED,
    HARNESS_TOOL_STEP_PREPARED,
    HARNESS_TOOL_STEP_RECORDED,
)
from ..host import (
    CommittedHarnessAssignment,
    HarnessHost,
    HarnessLifecycleError,
    HarnessSuperseded,
)
from ..run_state import (
    HarnessRunState,
    build_state_delta,
    load_state_object,
)
from .model import AgentTurnResult

_DISPATCH_FENCE_TTL_MS = 30_000
_PROVIDER_CALL_FIELDS = (
    "activeHarnessProviderCallDigest",
    "activeHarnessProviderCallObjectDigest",
    "activeHarnessProviderCallId",
    "activeHarnessProviderCallStatus",
    "activeHarnessProviderCallExpiresAtMs",
    "activeHarnessProviderCallGeneration",
)
_RECEIPT_FIELDS = (
    "harnessToolStepReceiptDigest",
    "harnessToolStepReceiptObjectDigest",
    "harnessToolStepObservationObjectDigest",
    "harnessToolStepPreviousReceiptObjectDigest",
)


@dataclass(frozen=True, slots=True)
class StoredHarnessRunSnapshot:
    snapshot: HarnessRunSnapshot
    snapshot_object: StoredObject
    state: HarnessRunState
    state_object: StoredObject


@dataclass(frozen=True, slots=True)
class HarnessProviderCallSourceRef:
    kind: HarnessProviderCallSource
    digest: str
    object_digest: str


@dataclass(frozen=True, slots=True)
class StoredHarnessProviderCall:
    record: HarnessProviderCallRecord
    record_object: StoredObject
    state: HarnessRunState
    state_object: StoredObject
    result: AgentTurnResult | None
    result_object: StoredObject | None
    failure: HarnessProviderCallFailureReceipt | None
    failure_object: StoredObject | None


class HarnessProviderCallClaimHeld(HarnessLifecycleError):
    pass


class HarnessProviderCallRecoveryRequired(HarnessLifecycleError):
    pass


class HarnessProviderCallRequestMismatch(HarnessLifecycleError):
    pass


@dataclass(frozen=True, slots=True)
class StoredHarnessToolStep:
    intent: HarnessToolStepIntent
    intent_object: StoredObject
    fence: HarnessDispatchFence | None
    fence_object: StoredObject | None
    receipt: HarnessToolStepReceipt | None
    receipt_object: StoredObject | None
    previous_receipt: HarnessToolStepReceipt | None
    previous_receipt_object: StoredObject | None
    observation: dict[str, JsonValue] | None
    observation_object: StoredObject | None


class HostHarnessRunStore:
    """Thin Host extension over native Harness continuity objects."""

    def __init__(
        self,
        host: HarnessHost,
        committed: CommittedHarnessAssignment,
    ) -> None:
        native = committed.native_run_contract
        if native is None:
            raise ValueError("Harness Run Store requires a native Run Contract")
        self.host = host
        self.extension = HostExtensionPort(host.storage, host.kernel)
        self.committed = committed
        self.harness_run_id = native.harness_run_id
        self._bound_state: HarnessRunState | None = None
        self._provider_outcome_requires_resume = False
        self._snapshot_sequence = self._current_snapshot_sequence()

    def bind_state(self, state: HarnessRunState) -> None:
        self._require_active_time_budget_consistent(state)
        self._bound_state = state

    @property
    def provider_outcome_requires_resume(self) -> bool:
        return self._provider_outcome_requires_resume

    def assignment_provider_source(self) -> HarnessProviderCallSourceRef:
        return HarnessProviderCallSourceRef(
            HarnessProviderCallSource.ASSIGNMENT,
            self.committed.assignment.digest,
            self.committed.assignment_object.digest,
        )

    @staticmethod
    def snapshot_provider_source(
        retained: StoredHarnessRunSnapshot,
    ) -> HarnessProviderCallSourceRef:
        return HarnessProviderCallSourceRef(
            HarnessProviderCallSource.SNAPSHOT,
            retained.snapshot.digest,
            retained.snapshot_object.digest,
        )

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
    ) -> StoredHarnessProviderCall:
        if ttl_ms < 1:
            raise ValueError("Provider Call claim TTL must be positive")
        state = self._require_state()
        state_object = self.extension.put_object(
            state.to_dict(self.harness_run_id),
            kind="harness-run-state",
        )
        current = self.extension.load(self.committed.assignment.task_id)
        self._require_provider_source_current(current.data, source)
        provider_call_id = self._provider_call_id(source, turn_sequence)
        active = self._load_provider_call_from_data(current.data)
        now_ms = self.host.kernel.clock_ms()
        previous: HarnessProviderCallRecord | None = None
        generation = 1
        event_kind = HARNESS_PROVIDER_CALL_CLAIMED
        if active is not None:
            previous = active.record
            if previous.provider_call_id == provider_call_id:
                self._require_provider_request_matches(
                    previous,
                    source=source,
                    turn_id=turn_id,
                    turn_sequence=turn_sequence,
                    request_digest=request_digest,
                    provider_request_digest=provider_request_digest,
                    adapter_id=adapter_id,
                    requested_model_id=requested_model_id,
                )
                if previous.status is HarnessProviderCallStatus.COMPLETED:
                    self.committed = replace(
                        self.committed,
                        task_revision=current.projection.revision,
                    )
                    return active
                if previous.status in {
                    HarnessProviderCallStatus.FAILED,
                    HarnessProviderCallStatus.UNKNOWN,
                }:
                    self.committed = replace(
                        self.committed,
                        task_revision=current.projection.revision,
                    )
                    return active
                if previous.status is HarnessProviderCallStatus.CLAIMED:
                    if previous.holder_id == holder_id:
                        if state_object.digest != active.state_object.digest:
                            raise HarnessProviderCallRequestMismatch(
                                "Provider Call claimant state differs from its "
                                "durable claim"
                            )
                        self.committed = replace(
                            self.committed,
                            task_revision=current.projection.revision,
                        )
                        return active
                    if now_ms <= previous.expires_at_ms:
                        raise HarnessProviderCallClaimHeld(
                            "Provider Call is claimed by another Harness execution"
                        )
                    self._require_provider_outcome_state(
                        active.state,
                        state,
                        label="expired Provider Call claim",
                    )
                    generation = previous.claim_generation + 1
                    event_kind = HARNESS_PROVIDER_CALL_SUPERSEDED
                elif previous.status is HarnessProviderCallStatus.DISPATCHING:
                    raise HarnessProviderCallRecoveryRequired(
                        "Provider Call may already have been dispatched; "
                        "explicit reconciliation is required"
                    )
                else:
                    raise HarnessProviderCallRecoveryRequired(
                        "Provider Call has a terminal attempt that was not consumed"
                    )
            elif (
                previous.status is HarnessProviderCallStatus.COMPLETED
                and previous.source_kind is source.kind
                and previous.source_digest == source.digest
                and previous.source_object_digest == source.object_digest
                and turn_sequence == previous.turn_sequence + 1
            ):
                self._require_provider_time_monotonic(
                    active.state,
                    state,
                    label="next-turn Provider Call",
                )
                previous = active.record
            else:
                raise HarnessProviderCallRecoveryRequired(
                    "another Provider Call record is still active"
                )
        issued_at_ms = now_ms
        recorded_at_ms = (
            now_ms
            if previous is None
            else self.host.kernel.timestamp(previous.recorded_at_ms)
        )
        record = self._provider_call_record(
            provider_call_id=provider_call_id,
            source=source,
            state_object_digest=state_object.digest,
            turn_id=turn_id,
            turn_sequence=turn_sequence,
            request_digest=request_digest,
            provider_request_digest=provider_request_digest,
            adapter_id=adapter_id,
            requested_model_id=requested_model_id,
            holder_id=holder_id,
            generation=generation,
            status=HarnessProviderCallStatus.CLAIMED,
            result_digest=None,
            result_object_digest=None,
            failure_digest=None,
            failure_object_digest=None,
            previous_record_digest=(
                None if previous is None else previous.digest
            ),
            issued_at_ms=issued_at_ms,
            expires_at_ms=issued_at_ms + ttl_ms,
            recorded_at_ms=recorded_at_ms,
        )
        stored = self._store_provider_call(record, state_object=state_object)
        try:
            self._commit(
                kind=event_kind,
                updates=self._provider_call_updates(stored),
                remove_fields=(),
                referenced_objects=(stored.record_object, state_object),
                label="Harness Provider Call Claim",
                event_suffix=f"provider-call-claim:{record.digest[7:23]}",
            )
        except HarnessSuperseded as error:
            self._raise_provider_claim_conflict(
                provider_call_id=provider_call_id,
                holder_id=holder_id,
                cause=error,
            )
        return stored

    def mark_provider_call_dispatching(
        self,
        retained: StoredHarnessProviderCall,
    ) -> StoredHarnessProviderCall:
        current = self._require_current_provider_call(retained.record)
        if current.record.status is not HarnessProviderCallStatus.CLAIMED:
            if current.record.status is HarnessProviderCallStatus.COMPLETED:
                return current
            raise HarnessProviderCallRecoveryRequired(
                "Provider Call cannot dispatch from its current state"
            )
        now_ms = self.host.kernel.clock_ms()
        if now_ms > current.record.expires_at_ms:
            raise HarnessProviderCallClaimHeld(
                "Provider Call claim expired before physical dispatch"
            )
        dispatch_state = self._require_state()
        self._require_provider_outcome_state(
            current.state,
            dispatch_state,
            label="Provider Call dispatch admission",
        )
        dispatch_state_object = self.extension.put_object(
            dispatch_state.to_dict(self.harness_run_id),
            kind="harness-run-state",
        )
        record = self._transition_provider_call(
            current.record,
            status=HarnessProviderCallStatus.DISPATCHING,
            state_object_digest=dispatch_state_object.digest,
        )
        stored = self._store_provider_call(
            record,
            state_object=dispatch_state_object,
        )
        self._commit(
            kind=HARNESS_PROVIDER_CALL_DISPATCHING,
            updates=self._provider_call_updates(stored),
            remove_fields=(),
            referenced_objects=(stored.record_object, dispatch_state_object),
            label="Harness Provider Call Dispatch",
            event_suffix=f"provider-call-dispatch:{record.digest[7:23]}",
        )
        return stored

    def complete_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        result: AgentTurnResult,
    ) -> StoredHarnessProviderCall:
        self._provider_outcome_requires_resume = False
        current = self.load_current_provider_call()
        if current.record.status is HarnessProviderCallStatus.COMPLETED:
            if (
                current.record.previous_record_digest == retained.record.digest
                and current.result == result
            ):
                self.committed = self.host.load_current_assignment(
                    self.committed.assignment.task_id
                )
                self._provider_outcome_requires_resume = (
                    self._current_provider_outcome_requires_resume(current.record)
                )
                return current
            raise HarnessProviderCallRecoveryRequired(
                "another Provider result already completed this call"
            )
        if current.record != retained.record:
            raise HarnessSuperseded("Harness Provider Call is no longer current")
        if current.record.status is not HarnessProviderCallStatus.DISPATCHING:
            raise HarnessProviderCallRecoveryRequired(
                "Provider result arrived without a current dispatch record"
            )
        terminal_state = self._require_state()
        self._require_provider_outcome_state(current.state, terminal_state)
        self._preflight_provider_terminal(current.record)
        terminal_state_object = self.extension.put_object(
            terminal_state.to_dict(self.harness_run_id),
            kind="harness-run-state",
        )
        result_object = self.extension.put_object(
            result.to_dict(),
            kind="agent-turn-result",
        )
        record = self._transition_provider_call(
            current.record,
            status=HarnessProviderCallStatus.COMPLETED,
            state_object_digest=terminal_state_object.digest,
            result_digest=result.digest,
            result_object_digest=result_object.digest,
        )
        stored = self._store_provider_call(
            record,
            state_object=terminal_state_object,
            result=result,
            result_object=result_object,
        )
        self._provider_outcome_requires_resume = self._commit(
            kind=HARNESS_PROVIDER_CALL_COMPLETED,
            updates=self._provider_call_updates(stored),
            remove_fields=(),
            referenced_objects=(
                stored.record_object,
                terminal_state_object,
                result_object,
            ),
            label="Harness Provider Call Result",
            event_suffix=f"provider-call-completed:{record.digest[7:23]}",
            provider_terminal_from=current.record,
            provider_terminal=stored,
        )
        return stored

    def fail_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        *,
        failure: HarnessProviderCallFailureReceipt,
    ) -> StoredHarnessProviderCall:
        self._provider_outcome_requires_resume = False
        current = self.load_current_provider_call()
        if current.record.status in {
            HarnessProviderCallStatus.FAILED,
            HarnessProviderCallStatus.UNKNOWN,
        }:
            if (
                current.record.previous_record_digest == retained.record.digest
                and current.failure == failure
            ):
                self.committed = self.host.load_current_assignment(
                    self.committed.assignment.task_id
                )
                self._provider_outcome_requires_resume = (
                    self._current_provider_outcome_requires_resume(current.record)
                )
                return current
            raise HarnessProviderCallRecoveryRequired(
                "another Provider failure already completed this call"
            )
        if current.record != retained.record:
            raise HarnessSuperseded("Harness Provider Call is no longer current")
        if current.record.status is not HarnessProviderCallStatus.DISPATCHING:
            raise HarnessProviderCallRecoveryRequired(
                "Provider failure arrived without a current dispatch record"
            )
        if (
            failure.provider_call_id != current.record.provider_call_id
            or failure.request_digest != current.record.request_digest
            or (
                failure.provider_request_digest
                != current.record.provider_request_digest
            )
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider failure receipt differs from the current dispatch"
            )
        terminal_state = self._require_state()
        self._require_provider_outcome_state(current.state, terminal_state)
        self._preflight_provider_terminal(current.record)
        terminal_state_object = self.extension.put_object(
            terminal_state.to_dict(self.harness_run_id),
            kind="harness-run-state",
        )
        unknown = failure.dispatch_safety == "dispatch_ambiguous"
        status = (
            HarnessProviderCallStatus.UNKNOWN
            if unknown
            else HarnessProviderCallStatus.FAILED
        )
        failure_object = self.extension.put_object(
            failure.to_dict(),
            kind="harness-provider-call-failure",
        )
        record = self._transition_provider_call(
            current.record,
            status=status,
            state_object_digest=terminal_state_object.digest,
            failure_digest=failure.digest,
            failure_object_digest=failure_object.digest,
        )
        stored = self._store_provider_call(
            record,
            state_object=terminal_state_object,
            failure=failure,
            failure_object=failure_object,
        )
        self._provider_outcome_requires_resume = self._commit(
            kind=(
                HARNESS_PROVIDER_CALL_UNKNOWN
                if unknown
                else HARNESS_PROVIDER_CALL_FAILED
            ),
            updates=self._provider_call_updates(stored),
            remove_fields=(),
            referenced_objects=(
                stored.record_object,
                terminal_state_object,
                failure_object,
            ),
            label="Harness Provider Call Failure",
            event_suffix=f"provider-call-{status.value}:{record.digest[7:23]}",
            provider_terminal_from=current.record,
            provider_terminal=stored,
        )
        return stored

    def fail_claimed_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        *,
        failure: HarnessProviderCallFailureReceipt,
    ) -> StoredHarnessProviderCall:
        current = self._require_current_provider_call(retained.record)
        if current.record.status is not HarnessProviderCallStatus.CLAIMED:
            raise HarnessProviderCallRecoveryRequired(
                "pre-dispatch Provider failure requires a current claim"
            )
        if (
            failure.provider_call_id != current.record.provider_call_id
            or failure.request_digest != current.record.request_digest
            or (
                failure.provider_request_digest
                != current.record.provider_request_digest
            )
            or failure.dispatch_safety != "pre_dispatch_safe"
        ):
            raise HarnessProviderCallRequestMismatch(
                "pre-dispatch Provider failure differs from the current claim"
            )
        terminal_state = self._require_state()
        self._require_provider_outcome_state(current.state, terminal_state)
        terminal_state_object = self.extension.put_object(
            terminal_state.to_dict(self.harness_run_id),
            kind="harness-run-state",
        )
        failure_object = self.extension.put_object(
            failure.to_dict(),
            kind="harness-provider-call-failure",
        )
        record = self._transition_provider_call(
            current.record,
            status=HarnessProviderCallStatus.FAILED,
            state_object_digest=terminal_state_object.digest,
            failure_digest=failure.digest,
            failure_object_digest=failure_object.digest,
        )
        stored = self._store_provider_call(
            record,
            state_object=terminal_state_object,
            failure=failure,
            failure_object=failure_object,
        )
        self._commit(
            kind=HARNESS_PROVIDER_CALL_FAILED,
            updates=self._provider_call_updates(stored),
            remove_fields=(),
            referenced_objects=(
                stored.record_object,
                terminal_state_object,
                failure_object,
            ),
            label="Harness Provider Call Pre-dispatch Failure",
            event_suffix=f"provider-call-failed:{record.digest[7:23]}",
        )
        return stored

    def retry_failed_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        *,
        holder_id: str,
        ttl_ms: int,
    ) -> StoredHarnessProviderCall:
        if not holder_id or holder_id != holder_id.strip():
            raise ValueError("Provider Call retry holder must be non-empty and trimmed")
        if ttl_ms < 1:
            raise ValueError("Provider Call retry TTL must be positive")
        current = self._require_current_provider_call(retained.record)
        if current.record.status is not HarnessProviderCallStatus.FAILED:
            raise HarnessProviderCallRecoveryRequired(
                "only an explicitly safe failed Provider attempt can retry"
            )
        if (
            current.failure is None
            or current.failure.dispatch_safety != "pre_dispatch_safe"
        ):
            raise HarnessProviderCallRecoveryRequired(
                "Provider failure does not prove that redispatch is safe"
            )
        state = self._require_state()
        self._require_provider_safe_retry_state(
            current.state,
            state,
        )
        state_object = self.extension.put_object(
            state.to_dict(self.harness_run_id),
            kind="harness-run-state",
        )
        now_ms = self.host.kernel.clock_ms()
        previous = current.record
        record = self._provider_call_record(
            provider_call_id=previous.provider_call_id,
            source=HarnessProviderCallSourceRef(
                previous.source_kind,
                previous.source_digest,
                previous.source_object_digest,
            ),
            state_object_digest=state_object.digest,
            turn_id=previous.turn_id,
            turn_sequence=previous.turn_sequence,
            request_digest=previous.request_digest,
            provider_request_digest=previous.provider_request_digest,
            adapter_id=previous.adapter_id,
            requested_model_id=previous.requested_model_id,
            holder_id=holder_id,
            generation=previous.claim_generation + 1,
            status=HarnessProviderCallStatus.CLAIMED,
            result_digest=None,
            result_object_digest=None,
            failure_digest=None,
            failure_object_digest=None,
            previous_record_digest=previous.digest,
            issued_at_ms=now_ms,
            expires_at_ms=now_ms + ttl_ms,
            recorded_at_ms=self.host.kernel.timestamp(previous.recorded_at_ms),
        )
        stored = self._store_provider_call(
            record,
            state_object=state_object,
        )
        self._commit(
            kind=HARNESS_PROVIDER_CALL_SUPERSEDED,
            updates=self._provider_call_updates(stored),
            remove_fields=(),
            referenced_objects=(stored.record_object, state_object),
            label="Harness Provider Call Safe Retry",
            event_suffix=f"provider-call-retry:{record.digest[7:23]}",
        )
        return stored

    def load_current_provider_call(self) -> StoredHarnessProviderCall:
        current = self.extension.load(self.committed.assignment.task_id)
        retained = self._load_provider_call_from_data(current.data)
        if retained is None:
            raise KeyError("Task has no active Harness Provider Call")
        return retained

    def load_provider_replay_state(
        self,
        *,
        source: HarnessProviderCallSourceRef,
        snapshot: StoredHarnessRunSnapshot,
        additional_messages: tuple[dict[str, JsonValue], ...],
        adapter_id: str,
        requested_model_id: str,
    ) -> HarnessRunState | None:
        if source != self.snapshot_provider_source(snapshot):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call resume source differs from the retained Snapshot"
            )
        current = self.extension.load(self.committed.assignment.task_id)
        self._require_provider_source_current(current.data, source)
        active = self._load_provider_call_from_data(current.data)
        if active is None or active.record.status not in {
            HarnessProviderCallStatus.CLAIMED,
            HarnessProviderCallStatus.COMPLETED,
            HarnessProviderCallStatus.FAILED,
            HarnessProviderCallStatus.UNKNOWN,
        }:
            return None
        record = active.record
        if (
            record.source_kind is not source.kind
            or record.source_digest != source.digest
            or record.source_object_digest != source.object_digest
            or record.adapter_id != adapter_id
            or record.requested_model_id != requested_model_id
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call differs from the requested resume identity"
            )
        self._require_provider_continuation_state(
            record,
            snapshot_state=snapshot.state,
            provider_state=active.state,
            additional_messages=additional_messages,
        )
        self.committed = replace(
            self.committed,
            task_revision=current.projection.revision,
        )
        return active.state

    def prepare_tool_step(
        self, intent: HarnessToolStepIntent
    ) -> StoredHarnessRunSnapshot:
        self._require_intent(intent)
        snapshot = self._build_snapshot(
            HarnessRunPauseReason.EFFECT_DISPATCH_PENDING,
            active_intent_digests=(intent.digest,),
        )
        state = self._require_state()
        intent_object = self.extension.put_object(
            intent.to_dict(), kind="harness-tool-step-intent"
        )
        retained = self._store_snapshot(snapshot, state)
        issued_at_ms = self.host.kernel.clock_ms()
        fence = HarnessDispatchFence(
            fence_id=(
                "harness-dispatch-fence:"
                f"{self.harness_run_id.removeprefix('harness-run:')}:"
                f"{intent.digest[7:31]}"
            ),
            task_id=self.committed.assignment.task_id,
            task_revision=self.committed.task_revision + 1,
            harness_run_id=self.harness_run_id,
            assignment_id=self.committed.assignment.assignment_id,
            assignment_generation=self.committed.assignment.generation,
            assignment_digest=self.committed.assignment.digest,
            intent_digest=intent.digest,
            runtime_operation=intent.runtime_operation,
            client_request_id=intent.client_request_id,
            issued_at_ms=issued_at_ms,
            expires_at_ms=issued_at_ms + _DISPATCH_FENCE_TTL_MS,
        )
        fence_object = self.extension.put_object(
            fence.to_dict(), kind="harness-dispatch-fence"
        )
        self._commit(
            kind=HARNESS_TOOL_STEP_PREPARED,
            updates={
                "harnessToolStepIntentDigest": intent.digest,
                "harnessToolStepIntentObjectDigest": intent_object.digest,
                "activeHarnessToolStepIntentDigest": intent.digest,
                "harnessDispatchFenceDigest": fence.digest,
                "harnessDispatchFenceObjectDigest": fence_object.digest,
                "harnessRunSnapshotDigest": snapshot.digest,
                "harnessRunSnapshotObjectDigest": retained.snapshot_object.digest,
                "harnessRunStateObjectDigest": retained.state_object.digest,
            },
            remove_fields=_RECEIPT_FIELDS + _PROVIDER_CALL_FIELDS,
            referenced_objects=(
                intent_object,
                fence_object,
                retained.snapshot_object,
                retained.state_object,
            ),
            label="Harness Tool Step Intent",
            event_suffix=f"tool-step-prepared:{intent.digest[7:23]}",
        )
        return retained

    def assert_dispatch_fence_current(
        self,
        fence: HarnessDispatchFence,
        *,
        require_unexpired: bool = True,
    ) -> None:
        step = self.load_current_tool_step()
        current = self.extension.load(self.committed.assignment.task_id)
        current_assignment = self.host.load_current_assignment(
            self.committed.assignment.task_id
        )
        if current_assignment.assignment != self.committed.assignment:
            raise HarnessSuperseded("Harness Assignment is no longer current")
        if step.fence != fence or step.intent.digest != fence.intent_digest:
            raise HarnessSuperseded("Harness Dispatch Fence is no longer current")
        if (
            current.projection.revision != fence.task_revision
            or current.data.get("activeHarnessToolStepIntentDigest")
            != fence.intent_digest
        ):
            raise HarnessSuperseded(
                "Harness Dispatch Fence revision is no longer current"
            )
        if require_unexpired and self.host.kernel.clock_ms() > fence.expires_at_ms:
            raise HarnessSuperseded(
                "Harness Dispatch Fence expired before Runtime admission"
            )

    def record_tool_step_receipt(
        self,
        receipt: HarnessToolStepReceipt,
        observation: dict[str, JsonValue],
    ) -> None:
        if receipt.harness_run_id != self.harness_run_id:
            raise ValueError("Tool Step Receipt belongs to another Harness Run")
        validate_json_value(observation)
        if canonical_digest(observation) != receipt.observation_digest:
            raise ValueError("Tool Step Receipt differs from its Observation")
        current = self.load_current_tool_step()
        if current.intent.digest != receipt.intent_digest:
            raise ValueError("Tool Step Receipt belongs to another Intent")
        previous = current.receipt
        expected_previous = None if previous is None else previous.digest
        if receipt.previous_receipt_digest != expected_previous:
            raise ValueError(
                "Tool Step Receipt predecessor differs from current history"
            )
        if previous is not None and previous.terminal:
            raise ValueError("terminal Tool Step Receipt cannot be superseded")

        receipt_object = self.extension.put_object(
            receipt.to_dict(), kind="harness-tool-step-receipt"
        )
        observation_object = self.extension.put_object(
            observation, kind="harness-tool-observation"
        )
        updates: dict[str, JsonValue] = {
            "harnessToolStepReceiptDigest": receipt.digest,
            "harnessToolStepReceiptObjectDigest": receipt_object.digest,
            "harnessToolStepObservationObjectDigest": observation_object.digest,
        }
        referenced_objects: tuple[StoredObject, ...] = (
            receipt_object,
            observation_object,
        )
        remove_fields: tuple[str, ...] = ()
        if current.receipt_object is None:
            remove_fields += ("harnessToolStepPreviousReceiptObjectDigest",)
        else:
            updates["harnessToolStepPreviousReceiptObjectDigest"] = (
                current.receipt_object.digest
            )
            referenced_objects += (current.receipt_object,)
        if receipt.terminal:
            remove_fields += ("activeHarnessToolStepIntentDigest",)
        self._commit(
            kind=HARNESS_TOOL_STEP_RECORDED,
            updates=updates,
            remove_fields=remove_fields,
            referenced_objects=referenced_objects,
            label="Harness Tool Step Receipt",
            event_suffix=f"tool-step-recorded:{receipt.digest[7:23]}",
        )

    def load_current_tool_step(self) -> StoredHarnessToolStep:
        current = self.extension.load(self.committed.assignment.task_id)
        data = current.data
        intent_object_digest = data.get("harnessToolStepIntentObjectDigest")
        if not isinstance(intent_object_digest, str):
            raise KeyError("Task has no current Harness Tool Step Intent")
        raw_intent = self.extension.get_object(
            intent_object_digest, expected_kind="harness-tool-step-intent"
        )
        if not isinstance(raw_intent, dict):
            raise TypeError("Harness Tool Step Intent object is invalid")
        intent = HarnessToolStepIntent.from_dict(raw_intent)
        self._require_intent(intent)
        intent_object = self.extension.inspect_object(intent_object_digest)

        fence: HarnessDispatchFence | None = None
        fence_object: StoredObject | None = None
        fence_object_digest = data.get("harnessDispatchFenceObjectDigest")
        if fence_object_digest is not None:
            if not isinstance(fence_object_digest, str):
                raise ValueError("Harness Dispatch Fence object reference is invalid")
            raw_fence = self.extension.get_object(
                fence_object_digest, expected_kind="harness-dispatch-fence"
            )
            if not isinstance(raw_fence, dict):
                raise ValueError("Harness Dispatch Fence object is invalid")
            fence = HarnessDispatchFence.from_dict(raw_fence)
            fence_object = self.extension.inspect_object(fence_object_digest)
            if (
                data.get("harnessDispatchFenceDigest") != fence.digest
                or fence.intent_digest != intent.digest
                or fence.harness_run_id != self.harness_run_id
                or fence.assignment_id != intent.assignment_id
                or fence.assignment_generation != intent.assignment_generation
                or fence.assignment_digest != intent.assignment_digest
                or fence.runtime_operation != intent.runtime_operation
                or fence.client_request_id != intent.client_request_id
            ):
                raise ValueError("Harness Dispatch Fence differs from its Intent")

        receipt_object_digest = data.get("harnessToolStepReceiptObjectDigest")
        observation_object_digest = data.get("harnessToolStepObservationObjectDigest")
        if receipt_object_digest is None and observation_object_digest is None:
            return StoredHarnessToolStep(
                intent,
                intent_object,
                fence,
                fence_object,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        if not isinstance(receipt_object_digest, str) or not isinstance(
            observation_object_digest, str
        ):
            raise TypeError("Harness Tool Step result references are incomplete")
        raw_receipt = self.extension.get_object(
            receipt_object_digest, expected_kind="harness-tool-step-receipt"
        )
        raw_observation = self.extension.get_object(
            observation_object_digest, expected_kind="harness-tool-observation"
        )
        if not isinstance(raw_receipt, dict) or not isinstance(raw_observation, dict):
            raise TypeError("Harness Tool Step result objects are invalid")
        receipt = HarnessToolStepReceipt.from_dict(raw_receipt)
        validate_json_value(raw_observation)
        if (
            data.get("harnessToolStepReceiptDigest") != receipt.digest
            or receipt.intent_digest != intent.digest
            or receipt.tool_call_id != intent.tool_call_id
            or canonical_digest(raw_observation) != receipt.observation_digest
        ):
            raise ValueError("Harness Tool Step result differs from its Intent")

        previous_receipt: HarnessToolStepReceipt | None = None
        previous_receipt_object: StoredObject | None = None
        previous_object_digest = data.get("harnessToolStepPreviousReceiptObjectDigest")
        if receipt.previous_receipt_digest is None:
            if previous_object_digest is not None:
                raise ValueError(
                    "initial Tool Step Receipt unexpectedly references a predecessor"
                )
        else:
            if not isinstance(previous_object_digest, str):
                raise ValueError("Tool Step Receipt predecessor object is missing")
            raw_previous = self.extension.get_object(
                previous_object_digest, expected_kind="harness-tool-step-receipt"
            )
            if not isinstance(raw_previous, dict):
                raise ValueError("Tool Step Receipt predecessor is invalid")
            previous_receipt = HarnessToolStepReceipt.from_dict(raw_previous)
            previous_receipt_object = self.extension.inspect_object(
                previous_object_digest
            )
            if (
                previous_receipt.digest != receipt.previous_receipt_digest
                or previous_receipt.intent_digest != intent.digest
                or previous_receipt.terminal
            ):
                raise ValueError("Tool Step Receipt predecessor chain is invalid")

        active = data.get("activeHarnessToolStepIntentDigest")
        if receipt.terminal:
            if active is not None:
                raise ValueError("terminal Tool Step Receipt retained an active Intent")
        elif active != intent.digest:
            raise ValueError("non-terminal Tool Step Receipt lost its active Intent")
        return StoredHarnessToolStep(
            intent,
            intent_object,
            fence,
            fence_object,
            receipt,
            self.extension.inspect_object(receipt_object_digest),
            previous_receipt,
            previous_receipt_object,
            dict(raw_observation),
            self.extension.inspect_object(observation_object_digest),
        )

    def record_pause(
        self, pause_reason: HarnessRunPauseReason
    ) -> StoredHarnessRunSnapshot:
        snapshot = self._build_snapshot(pause_reason, active_intent_digests=())
        retained = self._store_snapshot(
            snapshot, self._require_state(), allow_delta=False
        )
        self._commit(
            kind=HARNESS_RUN_SNAPSHOT_RECORDED,
            updates={
                "harnessRunSnapshotDigest": snapshot.digest,
                "harnessRunSnapshotObjectDigest": retained.snapshot_object.digest,
                "harnessRunStateObjectDigest": retained.state_object.digest,
            },
            remove_fields=(
                "activeHarnessToolStepIntentDigest",
            )
            + _PROVIDER_CALL_FIELDS,
            referenced_objects=(retained.snapshot_object, retained.state_object),
            label="Harness Run Snapshot",
            event_suffix=f"run-snapshot:{snapshot.sequence}",
        )
        return retained

    def load_current_snapshot(self) -> StoredHarnessRunSnapshot:
        current = self.extension.load(self.committed.assignment.task_id)
        snapshot_digest = current.data.get("harnessRunSnapshotObjectDigest")
        state_digest = current.data.get("harnessRunStateObjectDigest")
        if not isinstance(snapshot_digest, str) or not isinstance(state_digest, str):
            raise KeyError("Task has no current Harness Run Snapshot")
        raw_snapshot = self.extension.get_object(
            snapshot_digest, expected_kind="harness-run-snapshot"
        )
        if not isinstance(raw_snapshot, dict):
            raise TypeError("Harness Run Snapshot object is invalid")
        snapshot = HarnessRunSnapshot.from_dict(raw_snapshot)
        if current.data.get("harnessRunSnapshotDigest") != snapshot.digest:
            raise ValueError(
                "Harness Run Snapshot semantic digest differs from its object"
            )
        self._require_snapshot(snapshot)
        state = load_state_object(
            self.host.storage.objects,
            state_digest,
            harness_run_id=self.harness_run_id,
        )
        self._validate_snapshot_state(snapshot, state)
        return StoredHarnessRunSnapshot(
            snapshot,
            self.extension.inspect_object(snapshot_digest),
            state,
            self.extension.inspect_object(state_digest),
        )

    def _provider_call_record(
        self,
        *,
        provider_call_id: str,
        source: HarnessProviderCallSourceRef,
        state_object_digest: str,
        turn_id: str,
        turn_sequence: int,
        request_digest: str,
        provider_request_digest: str,
        adapter_id: str,
        requested_model_id: str,
        holder_id: str,
        generation: int,
        status: HarnessProviderCallStatus,
        result_digest: str | None,
        result_object_digest: str | None,
        failure_digest: str | None,
        failure_object_digest: str | None,
        previous_record_digest: str | None,
        issued_at_ms: int,
        expires_at_ms: int,
        recorded_at_ms: int,
    ) -> HarnessProviderCallRecord:
        record_token = canonical_digest(
            {
                "providerCallId": provider_call_id,
                "holderId": holder_id,
                "claimGeneration": generation,
                "status": status.value,
                "providerRequestDigest": provider_request_digest,
                "resultDigest": result_digest,
                "failureDigest": failure_digest,
                "previousRecordDigest": previous_record_digest,
                "recordedAtMs": recorded_at_ms,
            }
        )[7:31]
        assignment = self.committed.assignment
        return HarnessProviderCallRecord(
            record_id=f"harness-provider-call-record:{record_token}",
            provider_call_id=provider_call_id,
            task_id=assignment.task_id,
            harness_run_id=self.harness_run_id,
            assignment_id=assignment.assignment_id,
            assignment_generation=assignment.generation,
            assignment_digest=assignment.digest,
            source_kind=source.kind,
            source_digest=source.digest,
            source_object_digest=source.object_digest,
            state_object_digest=state_object_digest,
            turn_id=turn_id,
            turn_sequence=turn_sequence,
            request_digest=request_digest,
            provider_request_digest=provider_request_digest,
            adapter_id=adapter_id,
            requested_model_id=requested_model_id,
            holder_id=holder_id,
            claim_generation=generation,
            status=status,
            result_digest=result_digest,
            result_object_digest=result_object_digest,
            failure_digest=failure_digest,
            failure_object_digest=failure_object_digest,
            previous_record_digest=previous_record_digest,
            issued_at_ms=issued_at_ms,
            expires_at_ms=expires_at_ms,
            recorded_at_ms=recorded_at_ms,
        )

    def _transition_provider_call(
        self,
        previous: HarnessProviderCallRecord,
        *,
        status: HarnessProviderCallStatus,
        state_object_digest: str | None = None,
        result_digest: str | None = None,
        result_object_digest: str | None = None,
        failure_digest: str | None = None,
        failure_object_digest: str | None = None,
    ) -> HarnessProviderCallRecord:
        return self._provider_call_record(
            provider_call_id=previous.provider_call_id,
            source=HarnessProviderCallSourceRef(
                previous.source_kind,
                previous.source_digest,
                previous.source_object_digest,
            ),
            state_object_digest=(
                previous.state_object_digest
                if state_object_digest is None
                else state_object_digest
            ),
            turn_id=previous.turn_id,
            turn_sequence=previous.turn_sequence,
            request_digest=previous.request_digest,
            provider_request_digest=previous.provider_request_digest,
            adapter_id=previous.adapter_id,
            requested_model_id=previous.requested_model_id,
            holder_id=previous.holder_id,
            generation=previous.claim_generation,
            status=status,
            result_digest=result_digest,
            result_object_digest=result_object_digest,
            failure_digest=failure_digest,
            failure_object_digest=failure_object_digest,
            previous_record_digest=previous.digest,
            issued_at_ms=previous.issued_at_ms,
            expires_at_ms=previous.expires_at_ms,
            recorded_at_ms=self.host.kernel.timestamp(previous.recorded_at_ms),
        )

    def _store_provider_call(
        self,
        record: HarnessProviderCallRecord,
        *,
        state_object: StoredObject,
        result: AgentTurnResult | None = None,
        result_object: StoredObject | None = None,
        failure: HarnessProviderCallFailureReceipt | None = None,
        failure_object: StoredObject | None = None,
    ) -> StoredHarnessProviderCall:
        if record.state_object_digest != state_object.digest:
            raise ValueError("Provider Call state object differs from its record")
        if (result is None) != (result_object is None):
            raise ValueError("Provider Call result object is incomplete")
        if (record.result_digest is None) != (result is None):
            raise ValueError("Provider Call result references are incomplete")
        if result is not None and (
            record.result_digest != result.digest
            or record.result_object_digest != result_object.digest
        ):
            raise ValueError("Provider Call result differs from its record")
        if (failure is None) != (failure_object is None):
            raise ValueError("Provider Call failure object is incomplete")
        if (record.failure_digest is None) != (failure is None):
            raise ValueError("Provider Call failure references are incomplete")
        if failure is not None and (
            record.failure_digest != failure.digest
            or record.failure_object_digest != failure_object.digest
        ):
            raise ValueError("Provider Call failure differs from its record")
        if result is not None and failure is not None:
            raise ValueError("Provider Call cannot carry both result and failure")
        record_object = self.extension.put_object(
            record.to_dict(),
            kind="harness-provider-call-record",
        )
        return StoredHarnessProviderCall(
            record,
            record_object,
            self._require_state_for_object(state_object),
            state_object,
            result,
            result_object,
            failure,
            failure_object,
        )

    def _load_provider_call_from_data(
        self,
        data: dict[str, JsonValue],
    ) -> StoredHarnessProviderCall | None:
        record_object_digest = data.get(
            "activeHarnessProviderCallObjectDigest"
        )
        if record_object_digest is None:
            if any(data.get(field) is not None for field in _PROVIDER_CALL_FIELDS):
                raise ValueError("Harness Provider Call head fields are incomplete")
            return None
        if not isinstance(record_object_digest, str):
            raise ValueError("Harness Provider Call object reference is invalid")
        raw_record = self.extension.get_object(
            record_object_digest,
            expected_kind="harness-provider-call-record",
        )
        if not isinstance(raw_record, dict):
            raise ValueError("Harness Provider Call record object is invalid")
        record = HarnessProviderCallRecord.from_dict(raw_record)
        expected_head = {
            "activeHarnessProviderCallDigest": record.digest,
            "activeHarnessProviderCallObjectDigest": record_object_digest,
            "activeHarnessProviderCallId": record.provider_call_id,
            "activeHarnessProviderCallStatus": record.status.value,
            "activeHarnessProviderCallExpiresAtMs": record.expires_at_ms,
            "activeHarnessProviderCallGeneration": record.claim_generation,
        }
        if any(data.get(field) != value for field, value in expected_head.items()):
            raise ValueError("Harness Provider Call head differs from its record")
        self._require_provider_record(record)
        state_object = self.extension.inspect_object(record.state_object_digest)
        state = load_state_object(
            self.host.storage.objects,
            state_object.digest,
            harness_run_id=self.harness_run_id,
        )
        result: AgentTurnResult | None = None
        result_object: StoredObject | None = None
        failure: HarnessProviderCallFailureReceipt | None = None
        failure_object: StoredObject | None = None
        if record.status is HarnessProviderCallStatus.COMPLETED:
            assert record.result_object_digest is not None
            raw_result = self.extension.get_object(
                record.result_object_digest,
                expected_kind="agent-turn-result",
            )
            if not isinstance(raw_result, dict):
                raise ValueError("Provider Call result object is invalid")
            result = AgentTurnResult.from_dict(raw_result)
            result_object = self.extension.inspect_object(
                record.result_object_digest
            )
            if (
                result.digest != record.result_digest
                or result_object.digest != record.result_object_digest
            ):
                raise ValueError("Provider Call result differs from its record")
        if record.status in {
            HarnessProviderCallStatus.FAILED,
            HarnessProviderCallStatus.UNKNOWN,
        }:
            assert record.failure_object_digest is not None
            raw_failure = self.extension.get_object(
                record.failure_object_digest,
                expected_kind="harness-provider-call-failure",
            )
            if not isinstance(raw_failure, dict):
                raise ValueError("Provider Call failure object is invalid")
            failure = HarnessProviderCallFailureReceipt.from_dict(raw_failure)
            failure_object = self.extension.inspect_object(
                record.failure_object_digest
            )
            if (
                failure.digest != record.failure_digest
                or failure_object.digest != record.failure_object_digest
                or failure.provider_call_id != record.provider_call_id
                or failure.request_digest != record.request_digest
                or (
                    failure.provider_request_digest
                    != record.provider_request_digest
                )
                or (
                    record.status is HarnessProviderCallStatus.UNKNOWN
                    and failure.dispatch_safety != "dispatch_ambiguous"
                )
                or (
                    record.status is HarnessProviderCallStatus.FAILED
                    and failure.dispatch_safety == "dispatch_ambiguous"
                )
            ):
                raise ValueError("Provider Call failure differs from its record")
        return StoredHarnessProviderCall(
            record,
            self.extension.inspect_object(record_object_digest),
            state,
            state_object,
            result,
            result_object,
            failure,
            failure_object,
        )

    def _require_current_provider_call(
        self,
        expected: HarnessProviderCallRecord,
    ) -> StoredHarnessProviderCall:
        current = self.load_current_provider_call()
        if current.record != expected:
            raise HarnessSuperseded(
                "Harness Provider Call is no longer current"
            )
        return current

    def _require_provider_source_current(
        self,
        data: dict[str, JsonValue],
        source: HarnessProviderCallSourceRef,
    ) -> None:
        snapshot_object_digest = data.get("harnessRunSnapshotObjectDigest")
        if source.kind is HarnessProviderCallSource.ASSIGNMENT:
            if snapshot_object_digest is not None:
                raise HarnessSuperseded(
                    "initial Provider Call source was replaced by a Run Snapshot"
                )
            if (
                source.digest != self.committed.assignment.digest
                or source.object_digest != self.committed.assignment_object.digest
            ):
                raise HarnessSuperseded(
                    "Provider Call Assignment source is no longer current"
                )
            return
        if (
            snapshot_object_digest != source.object_digest
            or data.get("harnessRunSnapshotDigest") != source.digest
        ):
            raise HarnessSuperseded(
                "Provider Call Snapshot source is no longer current"
            )

    def _require_provider_request_matches(
        self,
        record: HarnessProviderCallRecord,
        *,
        source: HarnessProviderCallSourceRef,
        turn_id: str,
        turn_sequence: int,
        request_digest: str,
        provider_request_digest: str,
        adapter_id: str,
        requested_model_id: str,
    ) -> None:
        if (
            record.source_kind is not source.kind
            or record.source_digest != source.digest
            or record.source_object_digest != source.object_digest
            or record.turn_id != turn_id
            or record.turn_sequence != turn_sequence
            or record.request_digest != request_digest
            or record.provider_request_digest != provider_request_digest
            or record.adapter_id != adapter_id
            or record.requested_model_id != requested_model_id
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call identity was reused with different immutable input"
            )

    def _require_provider_record(
        self,
        record: HarnessProviderCallRecord,
    ) -> None:
        assignment = self.committed.assignment
        if (
            record.task_id != assignment.task_id
            or record.harness_run_id != self.harness_run_id
            or record.assignment_id != assignment.assignment_id
            or record.assignment_generation != assignment.generation
            or record.assignment_digest != assignment.digest
        ):
            raise ValueError(
                "Harness Provider Call differs from the current Assignment"
            )

    def _require_provider_continuation_state(
        self,
        record: HarnessProviderCallRecord,
        *,
        snapshot_state: HarnessRunState,
        provider_state: HarnessRunState,
        additional_messages: tuple[dict[str, JsonValue], ...],
    ) -> None:
        expected_message_prefix = (
            snapshot_state.messages
            + tuple(dict(message) for message in additional_messages)
        )
        ordered_sequences = (
            (snapshot_state.observations, provider_state.observations),
            (snapshot_state.provider_usage, provider_state.provider_usage),
            (
                snapshot_state.effective_model_ids,
                provider_state.effective_model_ids,
            ),
        )
        if (
            provider_state.requested_model_id != snapshot_state.requested_model_id
            or provider_state.requested_model_id != record.requested_model_id
            or provider_state.messages[: len(expected_message_prefix)]
            != expected_message_prefix
            or any(
                current[: len(previous)] != previous
                for previous, current in ordered_sequences
            )
            or not set(snapshot_state.seen_model_call_ids).issubset(
                provider_state.seen_model_call_ids
            )
            or not set(snapshot_state.seen_tool_call_ids).issubset(
                provider_state.seen_tool_call_ids
            )
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call state is not a continuation of the resume Snapshot"
            )
        self._require_provider_time_monotonic(
            snapshot_state,
            provider_state,
            label="Provider Call continuation",
        )

        assignment_max_calls = self.committed.assignment.budget.get(
            "maxModelCalls"
        )
        snapshot_remaining_calls = snapshot_state.remaining_budget.get(
            "modelCalls"
        )
        provider_remaining_calls = provider_state.remaining_budget.get(
            "modelCalls"
        )
        if (
            type(assignment_max_calls) is not int
            or type(snapshot_remaining_calls) is not int
            or type(provider_remaining_calls) is not int
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call state omitted its model-call budget"
            )
        snapshot_model_calls = assignment_max_calls - snapshot_remaining_calls
        provider_model_calls = assignment_max_calls - provider_remaining_calls
        if (
            snapshot_model_calls < 0
            or provider_model_calls < snapshot_model_calls
            or record.turn_sequence != provider_model_calls + 1
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call turn differs from its saved Run state"
            )

        resettable_budget_fields = (
            {"observationOnlyTurns", "noProgressTurns"}
            if additional_messages
            else set()
        )
        for field, snapshot_value in snapshot_state.remaining_budget.items():
            if field in resettable_budget_fields:
                continue
            provider_value = provider_state.remaining_budget.get(field)
            if (
                type(snapshot_value) is int
                and (
                    type(provider_value) is not int
                    or provider_value > snapshot_value
                )
            ):
                raise HarnessProviderCallRequestMismatch(
                    "Provider Call budget is not a continuation of the Snapshot"
                )

    @classmethod
    def _require_provider_outcome_state(
        cls,
        previous: HarnessRunState,
        current: HarnessRunState,
        *,
        label: str = "Provider Call outcome",
    ) -> None:
        if (
            previous.messages != current.messages
            or previous.observations != current.observations
            or previous.requested_model_id != current.requested_model_id
            or previous.effective_model_id != current.effective_model_id
            or previous.seen_model_call_ids != current.seen_model_call_ids
            or previous.seen_tool_call_ids != current.seen_tool_call_ids
            or previous.provider_usage != current.provider_usage
            or previous.effective_model_ids != current.effective_model_ids
            or set(previous.remaining_budget) != set(current.remaining_budget)
        ):
            raise HarnessProviderCallRequestMismatch(
                f"{label} state changed outside active time"
            )
        for field, previous_value in previous.remaining_budget.items():
            current_value = current.remaining_budget[field]
            if field == "wallTimeMs":
                if (
                    type(previous_value) is not int
                    or type(current_value) is not int
                    or current_value > previous_value
                ):
                    raise HarnessProviderCallRequestMismatch(
                        f"{label} revived its wall-time budget"
                    )
            elif current_value != previous_value:
                raise HarnessProviderCallRequestMismatch(
                    f"{label} changed a non-time budget"
                )
        cls._require_provider_time_monotonic(
            previous,
            current,
            label=label,
        )

    @classmethod
    def _require_provider_safe_retry_state(
        cls,
        previous: HarnessRunState,
        current: HarnessRunState,
    ) -> None:
        if (
            previous.messages != current.messages
            or previous.observations != current.observations
            or previous.requested_model_id != current.requested_model_id
            or previous.effective_model_id != current.effective_model_id
            or previous.seen_model_call_ids != current.seen_model_call_ids
            or previous.seen_tool_call_ids != current.seen_tool_call_ids
            or previous.provider_usage != current.provider_usage
            or previous.effective_model_ids != current.effective_model_ids
            or set(previous.remaining_budget) != set(current.remaining_budget)
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call safe retry state changed outside retry accounting"
            )
        previous_retries = previous.remaining_budget.get("modelRetries")
        current_retries = current.remaining_budget.get("modelRetries")
        if (
            type(previous_retries) is not int
            or type(current_retries) is not int
            or current_retries != previous_retries - 1
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call safe retry did not consume exactly one retry"
            )
        for field, previous_value in previous.remaining_budget.items():
            current_value = current.remaining_budget[field]
            if field == "modelRetries":
                continue
            if field == "wallTimeMs":
                if (
                    type(previous_value) is not int
                    or type(current_value) is not int
                    or current_value > previous_value
                ):
                    raise HarnessProviderCallRequestMismatch(
                        "Provider Call safe retry revived its wall-time budget"
                    )
            elif current_value != previous_value:
                raise HarnessProviderCallRequestMismatch(
                    "Provider Call safe retry changed a non-time budget"
                )
        cls._require_provider_time_monotonic(
            previous,
            current,
            label="Provider Call safe retry",
        )

    @staticmethod
    def _require_provider_time_monotonic(
        previous: HarnessRunState,
        current: HarnessRunState,
        *,
        label: str,
    ) -> None:
        previous_elapsed = previous.active_elapsed_ms
        current_elapsed = current.active_elapsed_ms
        if previous_elapsed is not None and (
            current_elapsed is None or current_elapsed < previous_elapsed
        ):
            raise HarnessProviderCallRequestMismatch(
                f"{label} active elapsed time decreased"
            )
        previous_wall = previous.remaining_budget.get("wallTimeMs")
        current_wall = current.remaining_budget.get("wallTimeMs")
        if (
            type(previous_wall) is not int
            or type(current_wall) is not int
            or current_wall > previous_wall
        ):
            raise HarnessProviderCallRequestMismatch(
                f"{label} remaining wall time increased"
            )

    def _raise_provider_claim_conflict(
        self,
        *,
        provider_call_id: str,
        holder_id: str,
        cause: Exception,
    ) -> None:
        try:
            current = self.extension.load(self.committed.assignment.task_id)
            active = self._load_provider_call_from_data(current.data)
        except Exception:
            raise HarnessSuperseded(str(cause)) from cause
        if active is None or active.record.provider_call_id != provider_call_id:
            raise HarnessSuperseded(str(cause)) from cause
        if active.record.holder_id != holder_id:
            if active.record.status is HarnessProviderCallStatus.CLAIMED:
                raise HarnessProviderCallClaimHeld(
                    "Provider Call claim was won by another Harness execution"
                ) from cause
            raise HarnessProviderCallRecoveryRequired(
                "Provider Call may already have been dispatched by another execution"
            ) from cause
        raise HarnessSuperseded(str(cause)) from cause

    def _require_state_for_object(self, state_object: StoredObject) -> HarnessRunState:
        state = self._require_state()
        if canonical_digest(state.to_dict(self.harness_run_id)) != canonical_digest(
            self.extension.get_object(
                state_object.digest,
                expected_kind=state_object.kind,
            )
        ):
            raise ValueError("Provider Call state object differs from bound state")
        return state

    @staticmethod
    def _provider_call_updates(
        retained: StoredHarnessProviderCall,
    ) -> dict[str, JsonValue]:
        record = retained.record
        return {
            "activeHarnessProviderCallDigest": record.digest,
            "activeHarnessProviderCallObjectDigest": retained.record_object.digest,
            "activeHarnessProviderCallId": record.provider_call_id,
            "activeHarnessProviderCallStatus": record.status.value,
            "activeHarnessProviderCallExpiresAtMs": record.expires_at_ms,
            "activeHarnessProviderCallGeneration": record.claim_generation,
        }

    def _provider_call_id(
        self,
        source: HarnessProviderCallSourceRef,
        turn_sequence: int,
    ) -> str:
        token = canonical_digest(
            {
                "harnessRunId": self.harness_run_id,
                "sourceKind": source.kind.value,
                "sourceObjectDigest": source.object_digest,
                "turnSequence": turn_sequence,
            }
        )[7:39]
        return f"provider-call:{token}"

    def _build_snapshot(
        self,
        pause_reason: HarnessRunPauseReason,
        *,
        active_intent_digests: tuple[str, ...],
    ) -> HarnessRunSnapshot:
        state = self._require_state()
        self._snapshot_sequence += 1
        assignment = self.committed.assignment
        return HarnessRunSnapshot(
            snapshot_id=(
                f"harness-run-snapshot:{self.harness_run_id.removeprefix('harness-run:')}:"
                f"s{self._snapshot_sequence}"
            ),
            harness_run_id=self.harness_run_id,
            assignment_id=assignment.assignment_id,
            assignment_generation=assignment.generation,
            assignment_digest=assignment.digest,
            sequence=self._snapshot_sequence,
            tool_catalog_digest=assignment.tool_catalog_digest,
            requested_model_id=state.requested_model_id,
            effective_model_id=state.effective_model_id,
            messages_digest=state.messages_digest,
            observation_digests=state.observation_digests,
            active_tool_step_intent_digests=active_intent_digests,
            remaining_budget=state.remaining_budget,
            pause_reason=pause_reason,
            created_at_ms=self.host.kernel.clock_ms(),
        )

    def _store_snapshot(
        self,
        snapshot: HarnessRunSnapshot,
        state: HarnessRunState,
        *,
        allow_delta: bool = True,
    ) -> StoredHarnessRunSnapshot:
        self._validate_snapshot_state(snapshot, state)
        snapshot_object = self.extension.put_object(
            snapshot.to_dict(), kind="harness-run-snapshot"
        )
        state_value = state.to_dict(self.harness_run_id)
        state_kind = "harness-run-state"
        if allow_delta:
            current = self.extension.load(self.committed.assignment.task_id)
            previous_digest = current.data.get("harnessRunStateObjectDigest")
            if isinstance(previous_digest, str):
                try:
                    previous = load_state_object(
                        self.host.storage.objects,
                        previous_digest,
                        harness_run_id=self.harness_run_id,
                    )
                except (KeyError, ValueError):
                    previous = None
                if previous is not None:
                    delta = build_state_delta(
                        harness_run_id=self.harness_run_id,
                        previous_state_object_digest=previous_digest,
                        previous=previous,
                        current=state,
                    )
                    if delta is not None:
                        state_value = delta
                        state_kind = "harness-run-state-delta"
        state_object = self.extension.put_object(state_value, kind=state_kind)
        return StoredHarnessRunSnapshot(snapshot, snapshot_object, state, state_object)

    def _commit(
        self,
        *,
        kind,
        updates: dict[str, JsonValue],
        remove_fields: tuple[str, ...],
        referenced_objects: tuple[StoredObject, ...],
        label: str,
        event_suffix: str,
        provider_terminal_from: HarnessProviderCallRecord | None = None,
        provider_terminal: StoredHarnessProviderCall | None = None,
    ) -> bool:
        task_id = self.committed.assignment.task_id
        current_assignment = self.host.load_current_assignment(task_id)
        recovery_fenced = False
        if current_assignment.assignment != self.committed.assignment:
            raise HarnessSuperseded("Harness Assignment is no longer current")
        if current_assignment.task_revision != self.committed.task_revision:
            if (
                provider_terminal_from is None
                or provider_terminal is None
                or not self._recovery_allows_provider_terminal(
                    current_assignment, provider_terminal_from
                )
            ):
                raise HarnessSuperseded("Harness Assignment is no longer current")
            recovery_fenced = True
            self.committed = current_assignment
            updates = {
                **updates,
                "harnessRunRecoveryResolvedProviderCallDigest": (
                    provider_terminal.record.digest
                ),
                "harnessRunRecoveryResolvedProviderCallObjectDigest": (
                    provider_terminal.record_object.digest
                ),
                "harnessRunRecoveryResolvedPreviousProviderCallDigest": (
                    provider_terminal_from.digest
                ),
            }
        event_token = canonical_digest(
            {
                "taskId": task_id,
                "harnessRunId": self.harness_run_id,
                "eventSuffix": event_suffix,
            }
        )[7:31]
        try:
            committed = self.extension.append_preserving(
                task_id=task_id,
                expected_revision=self.committed.task_revision,
                event_id=f"event:harness-extension:{event_token}",
                kind=kind,
                updates=updates,
                remove_fields=remove_fields,
                referenced_objects=referenced_objects,
                label=label,
            )
        except (
            EventConflict,
            HostKernelError,
            LeaseHeld,
            RevisionConflict,
        ) as error:
            raise HarnessSuperseded(str(error)) from error
        self.committed = replace(
            self.committed, task_revision=committed.projection.revision
        )
        return recovery_fenced

    def _preflight_provider_terminal(
        self,
        dispatching: HarnessProviderCallRecord,
    ) -> None:
        current_assignment = self.host.load_current_assignment(
            self.committed.assignment.task_id
        )
        if current_assignment.assignment != self.committed.assignment:
            raise HarnessSuperseded("Harness Assignment is no longer current")
        if (
            current_assignment.task_revision != self.committed.task_revision
            and not self._recovery_allows_provider_terminal(
                current_assignment, dispatching
            )
        ):
            raise HarnessSuperseded(
                "Provider terminal outcome does not match the current Recovery fence"
            )

    def _current_provider_outcome_requires_resume(
        self,
        record: HarnessProviderCallRecord,
    ) -> bool:
        current = self.extension.load(self.committed.assignment.task_id)
        return bool(
            current.data.get("harnessRunRecoveryAssessmentObjectDigest")
            is not None
            and current.data.get(
                "harnessRunRecoveryResolvedProviderCallDigest"
            )
            == record.digest
            and current.data.get(
                "harnessRunRecoveryResolvedProviderCallObjectDigest"
            )
            == current.data.get("activeHarnessProviderCallObjectDigest")
        )

    def _recovery_allows_provider_terminal(
        self,
        current_assignment: CommittedHarnessAssignment,
        dispatching: HarnessProviderCallRecord,
    ) -> bool:
        current = self.extension.load(current_assignment.assignment.task_id)
        if current.data.get("harnessRunAbandonmentObjectDigest") is not None:
            return False
        active = self._load_provider_call_from_data(current.data)
        if active is None or active.record != dispatching:
            return False
        if dispatching.status is not HarnessProviderCallStatus.DISPATCHING:
            return False
        try:
            recovery = self.host.load_current_native_run_recovery(
                current_assignment.assignment.task_id
            )
        except HarnessLifecycleError:
            return False
        evidence = recovery.assessment.workspace_evidence.get(
            "providerCallReconciliation"
        )
        return bool(
            isinstance(evidence, dict)
            and evidence.get("status") == "dispatching"
            and evidence.get("providerCallId") == dispatching.provider_call_id
            and evidence.get("recordDigest") == dispatching.digest
            and evidence.get("sourceKind") == dispatching.source_kind.value
            and evidence.get("sourceDigest") == dispatching.source_digest
            and evidence.get("sourceObjectDigest")
            == dispatching.source_object_digest
            and evidence.get("stateObjectDigest")
            == dispatching.state_object_digest
            and evidence.get("claimGeneration")
            == dispatching.claim_generation
            and recovery.assessment.assignment_id
            == dispatching.assignment_id
            and recovery.assessment.assignment_generation
            == dispatching.assignment_generation
            and recovery.assessment.assignment_digest
            == dispatching.assignment_digest
        )

    def _current_snapshot_sequence(self) -> int:
        current = self.extension.load(self.committed.assignment.task_id)
        digest = current.data.get("harnessRunSnapshotObjectDigest")
        if not isinstance(digest, str):
            return 0
        raw = self.extension.get_object(digest, expected_kind="harness-run-snapshot")
        if not isinstance(raw, dict):
            raise TypeError("current Harness Run Snapshot is not an object")
        return HarnessRunSnapshot.from_dict(raw).sequence

    def _require_intent(self, intent: HarnessToolStepIntent) -> None:
        assignment = self.committed.assignment
        if (
            intent.harness_run_id != self.harness_run_id
            or intent.assignment_id != assignment.assignment_id
            or intent.assignment_generation != assignment.generation
            or intent.assignment_digest != assignment.digest
        ):
            raise ValueError("Tool Step Intent differs from the current Assignment")

    def _require_snapshot(self, snapshot: HarnessRunSnapshot) -> None:
        assignment = self.committed.assignment
        if (
            snapshot.harness_run_id != self.harness_run_id
            or snapshot.assignment_id != assignment.assignment_id
            or snapshot.assignment_generation != assignment.generation
            or snapshot.assignment_digest != assignment.digest
            or snapshot.tool_catalog_digest != assignment.tool_catalog_digest
        ):
            raise ValueError(
                "Harness Run Snapshot differs from the current Assignment"
            )

    def _require_state(self) -> HarnessRunState:
        if self._bound_state is None:
            raise RuntimeError("Harness Run state was not bound before persistence")
        return self._bound_state

    def _require_active_time_budget_consistent(
        self,
        state: HarnessRunState,
    ) -> None:
        if state.active_elapsed_ms is None:
            return
        max_wall_time_ms = self.committed.assignment.budget.get("maxWallTimeMs")
        if max_wall_time_ms is None:
            return
        remaining_wall_time_ms = state.remaining_budget.get("wallTimeMs")
        if (
            type(max_wall_time_ms) is not int
            or max_wall_time_ms < 1
            or type(remaining_wall_time_ms) is not int
            or remaining_wall_time_ms
            != max(0, max_wall_time_ms - state.active_elapsed_ms)
        ):
            raise ValueError(
                "Harness Run active elapsed time differs from its committed "
                "wall-time budget"
            )

    @staticmethod
    def _validate_snapshot_state(
        snapshot: HarnessRunSnapshot, state: HarnessRunState
    ) -> None:
        if (
            snapshot.messages_digest != state.messages_digest
            or snapshot.observation_digests != state.observation_digests
            or snapshot.remaining_budget != state.remaining_budget
            or snapshot.requested_model_id != state.requested_model_id
            or snapshot.effective_model_id != state.effective_model_id
        ):
            raise ValueError("Harness Run Snapshot differs from its bounded state")

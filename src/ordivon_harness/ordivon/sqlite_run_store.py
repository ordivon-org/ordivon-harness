from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from ..core_contracts import HarnessRunContract
from ..errors import HarnessSuperseded
from ..protocol import (
    HarnessDispatchFence,
    HarnessProviderCallFailureReceipt,
    HarnessProviderCallSource,
    HarnessProviderCallStatus,
    HarnessRunPauseReason,
    HarnessRunSnapshot,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
    HarnessToolStepStatus,
)
from ..run_state import HarnessRunState, state_from_dict
from ..sqlite_store import (
    HarnessEventConflict,
    HarnessLeaseConflict,
    HarnessLeaseHeld,
    HarnessRevisionConflict,
    SQLiteHarnessStore,
)
from ..store import (
    HarnessRunEventRecord,
    HarnessRunLease,
    StoredHarnessObject,
    new_execution_owner_id,
)
from .continuity_records import HarnessDispatchFenceV2, HarnessProviderCallRecordV2
from .model import AgentTurnResult
from .run_store_port import (
    HarnessDispatchFenceView,
    HarnessProviderCallClaimHeld,
    HarnessProviderCallRecoveryRequired,
    HarnessProviderCallRequestMismatch,
    HarnessProviderCallSourceRef,
    HarnessRunStoreBinding,
    StoredHarnessProviderCall,
    StoredHarnessRunSnapshot,
    StoredHarnessToolStep,
)

_DISPATCH_FENCE_TTL_MS = 30_000
_STORE_LEASE_TTL_MS = 30_000
_PROVIDER_EVENT_KINDS = frozenset(
    {
        "harness.provider-call-claimed",
        "harness.provider-call-superseded",
        "harness.provider-call-dispatching",
        "harness.provider-call-completed",
        "harness.provider-call-failed",
        "harness.provider-call-unknown",
    }
)
_PROVIDER_CLEAR_EVENT_KINDS = frozenset(
    {
        "harness.snapshot-recorded",
        "harness.run-paused",
        "harness.tool-step-prepared",
        "harness.run-stopped",
        "harness.run-completed",
        "harness.run-failed",
        "harness.run-abandoned",
    }
)
_TOOL_EVENT_KINDS = frozenset(
    {
        "harness.tool-step-prepared",
        "harness.tool-step-recorded",
        "harness.tool-step-unknown",
        "harness.tool-step-reconciled",
    }
)


@dataclass(frozen=True, slots=True)
class _Heads:
    provider: HarnessRunEventRecord | None
    tool: HarnessRunEventRecord | None
    snapshot: HarnessRunEventRecord | None


class SQLiteHarnessRunContinuityStore:
    """Independent event-sourced Provider/Tool/Snapshot continuity for one Run."""

    @classmethod
    def open(
        cls,
        store: SQLiteHarnessStore,
        harness_run_id: str,
        *,
        clock_ms: Callable[[], int] | None = None,
    ) -> SQLiteHarnessRunContinuityStore:
        projection = store.load_run(harness_run_id)
        raw = store.get_object(
            projection.contract_object_digest,
            expected_kind="harness-run-contract",
        )
        if not isinstance(raw, dict):
            raise TypeError("Harness Run Contract object must be an object")
        return cls(store, HarnessRunContract.from_dict(raw), clock_ms=clock_ms)

    def __init__(
        self,
        store: SQLiteHarnessStore,
        contract: HarnessRunContract,
        *,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        store.validate_run_history(contract.harness_run_id)
        projection = store.load_run(contract.harness_run_id)
        if (
            projection.contract_digest != contract.digest
            or projection.caller_id != contract.caller_id
            or projection.caller_run_ref != contract.caller_run_ref
        ):
            raise ValueError("Harness Run Contract differs from the independent Store")
        self.store = store
        self.contract = contract
        self.harness_run_id = contract.harness_run_id
        token = contract.digest[7:31]
        self._binding = HarnessRunStoreBinding(
            harness_run_id=contract.harness_run_id,
            assignment_id=f"assignment:external:{token}",
            assignment_generation=1,
            assignment_digest=contract.digest,
        )
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._execution_owner_id = new_execution_owner_id("continuity")
        self._bound_state: HarnessRunState | None = None
        self._provider_outcome_requires_resume = False
        self._snapshot_sequence = self._current_snapshot_sequence()

    @property
    def binding(self) -> HarnessRunStoreBinding:
        return self._binding

    @property
    def caller_revision(self) -> int:
        return self.store.load_run(self.harness_run_id).revision

    @property
    def provider_outcome_requires_resume(self) -> bool:
        if self._provider_outcome_requires_resume:
            return True
        current = self._load_current_provider_call_or_none()
        return bool(
            current is not None and current.record.status is HarnessProviderCallStatus.UNKNOWN
        )

    def clock_ms(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or value < 0:
            raise ValueError("Harness continuity clock must return a non-negative integer")
        return value

    def bind_state(self, state: HarnessRunState) -> None:
        self._require_active_time_budget_consistent(state)
        self._bound_state = state

    def assignment_provider_source(self) -> HarnessProviderCallSourceRef:
        projection = self.store.load_run(self.harness_run_id)
        return HarnessProviderCallSourceRef(
            HarnessProviderCallSource.ASSIGNMENT,
            self.contract.digest,
            projection.contract_object_digest,
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
        state_object = self._put_state(state)
        now_ms = self.clock_ms()
        provider_call_id = self._provider_call_id(source, turn_sequence)
        try:
            lease = self._acquire_lease("provider-claim", provider_call_id, now_ms=now_ms)
        except HarnessLeaseHeld as error:
            raise HarnessProviderCallClaimHeld(
                "Provider Call claim is being admitted by another execution"
            ) from error
        try:
            self._require_provider_source_current(source)
            active = self._load_current_provider_call_or_none()
            previous = None
            generation = 1
            event_kind = "harness.provider-call-claimed"
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
                    if previous.status in {
                        HarnessProviderCallStatus.COMPLETED,
                        HarnessProviderCallStatus.FAILED,
                        HarnessProviderCallStatus.UNKNOWN,
                    }:
                        return active
                    if previous.status is HarnessProviderCallStatus.CLAIMED:
                        if previous.holder_id == holder_id:
                            if active.state_object.digest != state_object.digest:
                                raise HarnessProviderCallRequestMismatch(
                                    "Provider Call claimant state differs from its durable claim"
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
                        event_kind = "harness.provider-call-superseded"
                    elif previous.status is HarnessProviderCallStatus.DISPATCHING:
                        raise HarnessProviderCallRecoveryRequired(
                            "Provider Call may already have been dispatched; explicit reconciliation is required"
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
                else:
                    raise HarnessProviderCallRecoveryRequired(
                        "another Provider Call record is still active"
                    )
            recorded_at_ms = self._recorded_time(
                now_ms,
                previous_recorded_at_ms=(None if previous is None else previous.recorded_at_ms),
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
                previous_record_digest=(None if previous is None else previous.digest),
                issued_at_ms=now_ms,
                expires_at_ms=now_ms + ttl_ms,
                recorded_at_ms=recorded_at_ms,
            )
            stored = self._store_provider_call(record, state_object=state_object)
            self._append_provider_event(
                lease=lease,
                event_kind=event_kind,
                stored=stored,
                caused_by_event_id=(
                    None
                    if previous is None
                    else self._provider_event_id_for_digest(previous.digest)
                ),
            )
            return stored
        finally:
            self.store.release_run_lease(lease)

    def mark_provider_call_dispatching(
        self,
        retained: StoredHarnessProviderCall,
    ) -> StoredHarnessProviderCall:
        now_ms = self.clock_ms()
        lease = self._acquire_lease(
            "provider-dispatch", retained.record.provider_call_id, now_ms=now_ms
        )
        try:
            current = self._require_current_provider_call(retained.record)
            if current.record.status is not HarnessProviderCallStatus.CLAIMED:
                if current.record.status is HarnessProviderCallStatus.COMPLETED:
                    return current
                raise HarnessProviderCallRecoveryRequired(
                    "Provider Call cannot dispatch from its current state"
                )
            if now_ms > current.record.expires_at_ms:
                raise HarnessProviderCallClaimHeld(
                    "Provider Call claim expired before physical dispatch"
                )
            state = self._require_state()
            self._require_provider_outcome_state(
                current.state,
                state,
                label="Provider Call dispatch admission",
            )
            state_object = self._put_state(state)
            record = self._transition_provider_call(
                current.record,
                status=HarnessProviderCallStatus.DISPATCHING,
                state_object_digest=state_object.digest,
                recorded_at_ms=self._recorded_time(
                    now_ms,
                    previous_recorded_at_ms=current.record.recorded_at_ms,
                ),
            )
            stored = self._store_provider_call(record, state_object=state_object)
            self._append_provider_event(
                lease=lease,
                event_kind="harness.provider-call-dispatching",
                stored=stored,
                caused_by_event_id=self._provider_event_id_for_digest(current.record.digest),
            )
            return stored
        finally:
            self.store.release_run_lease(lease)

    def complete_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        result: AgentTurnResult,
    ) -> StoredHarnessProviderCall:
        self._provider_outcome_requires_resume = False
        existing = self.load_current_provider_call()
        if existing.record.status is HarnessProviderCallStatus.COMPLETED:
            if existing.result == result and (
                existing.record == retained.record
                or existing.record.previous_record_digest == retained.record.digest
            ):
                return existing
            raise HarnessProviderCallRequestMismatch(
                "another Provider result already completed this call"
            )
        preflight = self._require_current_provider_call(retained.record)
        if preflight.record.status is not HarnessProviderCallStatus.DISPATCHING:
            raise HarnessProviderCallRecoveryRequired(
                "Provider result arrived without a current dispatch record"
            )
        now_ms = self.clock_ms()
        lease = self._acquire_lease(
            "provider-complete", retained.record.provider_call_id, now_ms=now_ms
        )
        try:
            current = self.load_current_provider_call()
            if current.record.status is HarnessProviderCallStatus.COMPLETED:
                if current.result == result and (
                    current.record == retained.record
                    or current.record.previous_record_digest == retained.record.digest
                ):
                    return current
                raise HarnessProviderCallRequestMismatch(
                    "another Provider result already completed this call"
                )
            if current.record != retained.record:
                raise HarnessSuperseded("Harness Provider Call is no longer current")
            if current.record.status is not HarnessProviderCallStatus.DISPATCHING:
                raise HarnessProviderCallRecoveryRequired(
                    "Provider result arrived without a current dispatch record"
                )
            state = self._require_state()
            self._require_provider_outcome_state(current.state, state)
            state_object = self._put_state(state)
            result_object = self.store.put_object(result.to_dict(), kind="agent-turn-result")
            record = self._transition_provider_call(
                current.record,
                status=HarnessProviderCallStatus.COMPLETED,
                state_object_digest=state_object.digest,
                result_digest=result.digest,
                result_object_digest=result_object.digest,
                recorded_at_ms=self._recorded_time(
                    now_ms,
                    previous_recorded_at_ms=current.record.recorded_at_ms,
                ),
            )
            stored = self._store_provider_call(
                record,
                state_object=state_object,
                result=result,
                result_object=result_object,
            )
            self._append_provider_event(
                lease=lease,
                event_kind="harness.provider-call-completed",
                stored=stored,
                caused_by_event_id=self._provider_event_id_for_digest(current.record.digest),
            )
            return stored
        finally:
            self.store.release_run_lease(lease)

    def fail_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        *,
        failure: HarnessProviderCallFailureReceipt,
    ) -> StoredHarnessProviderCall:
        self._provider_outcome_requires_resume = False
        now_ms = self.clock_ms()
        lease = self._acquire_lease(
            "provider-fail", retained.record.provider_call_id, now_ms=now_ms
        )
        try:
            current = self.load_current_provider_call()
            if current.record.status in {
                HarnessProviderCallStatus.FAILED,
                HarnessProviderCallStatus.UNKNOWN,
            }:
                if (
                    current.record.previous_record_digest == retained.record.digest
                    and current.failure == failure
                ):
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
            self._require_failure_matches(current.record, failure)
            state = self._require_state()
            self._require_provider_outcome_state(current.state, state)
            state_object = self._put_state(state)
            failure_object = self.store.put_object(
                failure.to_dict(), kind="harness-provider-call-failure"
            )
            status = (
                HarnessProviderCallStatus.UNKNOWN
                if failure.dispatch_safety == "dispatch_ambiguous"
                else HarnessProviderCallStatus.FAILED
            )
            record = self._transition_provider_call(
                current.record,
                status=status,
                state_object_digest=state_object.digest,
                failure_digest=failure.digest,
                failure_object_digest=failure_object.digest,
                recorded_at_ms=self._recorded_time(
                    now_ms,
                    previous_recorded_at_ms=current.record.recorded_at_ms,
                ),
            )
            stored = self._store_provider_call(
                record,
                state_object=state_object,
                failure=failure,
                failure_object=failure_object,
            )
            self._append_provider_event(
                lease=lease,
                event_kind=(
                    "harness.provider-call-unknown"
                    if status is HarnessProviderCallStatus.UNKNOWN
                    else "harness.provider-call-failed"
                ),
                stored=stored,
                caused_by_event_id=self._provider_event_id_for_digest(current.record.digest),
            )
            return stored
        finally:
            self.store.release_run_lease(lease)

    def fail_claimed_provider_call(
        self,
        retained: StoredHarnessProviderCall,
        *,
        failure: HarnessProviderCallFailureReceipt,
    ) -> StoredHarnessProviderCall:
        now_ms = self.clock_ms()
        lease = self._acquire_lease(
            "provider-pre-dispatch-fail",
            retained.record.provider_call_id,
            now_ms=now_ms,
        )
        try:
            current = self._require_current_provider_call(retained.record)
            if current.record.status is not HarnessProviderCallStatus.CLAIMED:
                raise HarnessProviderCallRecoveryRequired(
                    "pre-dispatch Provider failure requires a current claim"
                )
            self._require_failure_matches(current.record, failure)
            if failure.dispatch_safety != "pre_dispatch_safe":
                raise HarnessProviderCallRequestMismatch(
                    "pre-dispatch Provider failure is not proven safe"
                )
            state = self._require_state()
            self._require_provider_outcome_state(current.state, state)
            state_object = self._put_state(state)
            failure_object = self.store.put_object(
                failure.to_dict(), kind="harness-provider-call-failure"
            )
            record = self._transition_provider_call(
                current.record,
                status=HarnessProviderCallStatus.FAILED,
                state_object_digest=state_object.digest,
                failure_digest=failure.digest,
                failure_object_digest=failure_object.digest,
                recorded_at_ms=self._recorded_time(
                    now_ms,
                    previous_recorded_at_ms=current.record.recorded_at_ms,
                ),
            )
            stored = self._store_provider_call(
                record,
                state_object=state_object,
                failure=failure,
                failure_object=failure_object,
            )
            self._append_provider_event(
                lease=lease,
                event_kind="harness.provider-call-failed",
                stored=stored,
                caused_by_event_id=self._provider_event_id_for_digest(current.record.digest),
            )
            return stored
        finally:
            self.store.release_run_lease(lease)

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
        now_ms = self.clock_ms()
        lease = self._acquire_lease(
            "provider-retry", retained.record.provider_call_id, now_ms=now_ms
        )
        try:
            current = self._require_current_provider_call(retained.record)
            if current.record.status is not HarnessProviderCallStatus.FAILED:
                raise HarnessProviderCallRecoveryRequired(
                    "only an explicitly safe failed Provider attempt can retry"
                )
            if current.failure is None or current.failure.dispatch_safety != "pre_dispatch_safe":
                raise HarnessProviderCallRecoveryRequired(
                    "Provider failure does not prove that redispatch is safe"
                )
            state = self._require_state()
            self._require_provider_safe_retry_state(current.state, state)
            state_object = self._put_state(state)
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
                recorded_at_ms=self._recorded_time(
                    now_ms,
                    previous_recorded_at_ms=previous.recorded_at_ms,
                ),
            )
            stored = self._store_provider_call(record, state_object=state_object)
            self._append_provider_event(
                lease=lease,
                event_kind="harness.provider-call-superseded",
                stored=stored,
                caused_by_event_id=self._provider_event_id_for_digest(previous.digest),
            )
            return stored
        finally:
            self.store.release_run_lease(lease)

    def load_current_provider_call(self) -> StoredHarnessProviderCall:
        retained = self._load_current_provider_call_or_none()
        if retained is None:
            raise KeyError("Harness Run has no active Provider Call")
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
        self._require_provider_source_current(source)
        active = self._load_current_provider_call_or_none()
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
        return active.state

    def prepare_tool_step(self, intent: HarnessToolStepIntent) -> StoredHarnessRunSnapshot:
        self._require_intent(intent)
        state = self._require_state()
        now_ms = self.clock_ms()
        lease = self._acquire_lease("tool-prepare", intent.digest, now_ms=now_ms)
        try:
            snapshot = self._build_snapshot(
                HarnessRunPauseReason.EFFECT_DISPATCH_PENDING,
                active_intent_digests=(intent.digest,),
                created_at_ms=self._recorded_time(now_ms),
            )
            retained = self._store_snapshot(snapshot, state)
            intent_object = self.store.put_object(intent.to_dict(), kind="harness-tool-step-intent")
            fence = HarnessDispatchFenceV2(
                fence_id=(
                    "harness-dispatch-fence:"
                    f"{self.harness_run_id.removeprefix('harness-run:')}:"
                    f"{intent.digest[7:31]}"
                ),
                harness_run_id=self.harness_run_id,
                run_revision=lease.run_revision + 1,
                binding_digest=self.binding.digest,
                intent_digest=intent.digest,
                runtime_operation=intent.runtime_operation,
                client_request_id=intent.client_request_id,
                issued_at_ms=now_ms,
                expires_at_ms=now_ms + _DISPATCH_FENCE_TTL_MS,
            )
            fence_object = self.store.put_object(fence.to_dict(), kind="harness-dispatch-fence")
            data: dict[str, JsonValue] = {
                "toolStepIntentDigest": intent.digest,
                "toolStepIntentObjectDigest": intent_object.digest,
                "dispatchFenceDigest": fence.digest,
                "dispatchFenceObjectDigest": fence_object.digest,
                "snapshotDigest": snapshot.digest,
                "snapshotObjectDigest": retained.snapshot_object.digest,
                "stateObjectDigest": retained.state_object.digest,
                "receiptDigest": None,
                "receiptObjectDigest": None,
                "previousReceiptObjectDigest": None,
                "observationObjectDigest": None,
            }
            self._append_event(
                lease=lease,
                event_kind="harness.tool-step-prepared",
                event_id=self._event_id("tool-prepared", intent.digest),
                data=data,
                recorded_at_ms=snapshot.created_at_ms,
                referenced_objects=(
                    intent_object,
                    fence_object,
                    retained.snapshot_object,
                    retained.state_object,
                ),
                caused_by_event_id=self._latest_event_id(),
            )
            return retained
        finally:
            self.store.release_run_lease(lease)

    def assert_dispatch_fence_current(
        self,
        fence: HarnessDispatchFenceView,
        *,
        require_unexpired: bool = True,
    ) -> None:
        step = self.load_current_tool_step()
        projection = self.store.load_run(self.harness_run_id)
        if step.fence != fence or step.intent.digest != fence.intent_digest:
            raise HarnessSuperseded("Harness Dispatch Fence is no longer current")
        if projection.revision != fence.authority_generation:
            raise HarnessSuperseded("Harness Dispatch Fence revision is no longer current")
        if require_unexpired and self.clock_ms() > fence.expires_at_ms:
            raise HarnessSuperseded("Harness Dispatch Fence expired before Runtime admission")

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
        now_ms = self.clock_ms()
        lease = self._acquire_lease("tool-receipt", receipt.digest, now_ms=now_ms)
        try:
            current = self.load_current_tool_step()
            if current.intent.digest != receipt.intent_digest:
                raise ValueError("Tool Step Receipt belongs to another Intent")
            previous = current.receipt
            if previous == receipt and current.observation == observation:
                return
            expected_previous = None if previous is None else previous.digest
            if receipt.previous_receipt_digest != expected_previous:
                raise ValueError("Tool Step Receipt predecessor differs from current history")
            if previous is not None and previous.terminal:
                raise ValueError("terminal Tool Step Receipt cannot be superseded")
            receipt_object = self.store.put_object(
                receipt.to_dict(), kind="harness-tool-step-receipt"
            )
            observation_object = self.store.put_object(observation, kind="harness-tool-observation")
            referenced: list[StoredHarnessObject] = [
                current.intent_object,
                receipt_object,
                observation_object,
            ]
            if current.fence_object is not None:
                referenced.append(current.fence_object)
            if current.receipt_object is not None:
                referenced.append(current.receipt_object)
            data: dict[str, JsonValue] = {
                "toolStepIntentDigest": current.intent.digest,
                "toolStepIntentObjectDigest": current.intent_object.digest,
                "dispatchFenceDigest": (None if current.fence is None else current.fence.digest),
                "dispatchFenceObjectDigest": (
                    None if current.fence_object is None else current.fence_object.digest
                ),
                "receiptDigest": receipt.digest,
                "receiptObjectDigest": receipt_object.digest,
                "previousReceiptObjectDigest": (
                    None if current.receipt_object is None else current.receipt_object.digest
                ),
                "observationObjectDigest": observation_object.digest,
            }
            if receipt.status is HarnessToolStepStatus.UNKNOWN:
                event_kind = "harness.tool-step-unknown"
            elif receipt.reconciled:
                event_kind = "harness.tool-step-reconciled"
            else:
                event_kind = "harness.tool-step-recorded"
            self._append_event(
                lease=lease,
                event_kind=event_kind,
                event_id=self._event_id("tool-receipt", receipt.digest),
                data=data,
                recorded_at_ms=self._recorded_time(
                    receipt.created_at_ms,
                    previous_recorded_at_ms=(None if previous is None else previous.created_at_ms),
                ),
                referenced_objects=tuple(referenced),
                caused_by_event_id=self._tool_event_id_for_intent(current.intent.digest),
            )
        finally:
            self.store.release_run_lease(lease)

    def load_current_tool_step(self) -> StoredHarnessToolStep:
        event = self._heads().tool
        if event is None:
            raise KeyError("Harness Run has no current Tool Step")
        data = event.data
        intent_object_digest = self._required_digest(data, "toolStepIntentObjectDigest")
        raw_intent = self.store.get_object(
            intent_object_digest,
            expected_kind="harness-tool-step-intent",
        )
        if not isinstance(raw_intent, dict):
            raise TypeError("Harness Tool Step Intent object is invalid")
        intent = HarnessToolStepIntent.from_dict(raw_intent)
        self._require_intent(intent)
        intent_object = self.store.inspect_object(intent_object_digest)
        if data.get("toolStepIntentDigest") != intent.digest:
            raise ValueError("Harness Tool Step Intent digest differs")

        fence = None
        fence_object = None
        fence_object_digest = data.get("dispatchFenceObjectDigest")
        if fence_object_digest is not None:
            if not isinstance(fence_object_digest, str):
                raise ValueError("Harness Dispatch Fence object reference is invalid")
            raw_fence = self.store.get_object(
                fence_object_digest,
                expected_kind="harness-dispatch-fence",
            )
            if not isinstance(raw_fence, dict):
                raise ValueError("Harness Dispatch Fence object is invalid")
            version = raw_fence.get("schemaVersion")
            if version == 2:
                fence = HarnessDispatchFenceV2.from_dict(raw_fence)
            elif version == 1:
                fence = HarnessDispatchFence.from_dict(raw_fence)
            else:
                raise ValueError("Harness Dispatch Fence version is unsupported")
            fence_object = self.store.inspect_object(fence_object_digest)
            if (
                data.get("dispatchFenceDigest") != fence.digest
                or fence.intent_digest != intent.digest
                or fence.harness_run_id != self.harness_run_id
                or fence.runtime_operation != intent.runtime_operation
                or fence.client_request_id != intent.client_request_id
            ):
                raise ValueError("Harness Dispatch Fence differs from its Intent")

        receipt_object_digest = data.get("receiptObjectDigest")
        observation_object_digest = data.get("observationObjectDigest")
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
        raw_receipt = self.store.get_object(
            receipt_object_digest,
            expected_kind="harness-tool-step-receipt",
        )
        raw_observation = self.store.get_object(
            observation_object_digest,
            expected_kind="harness-tool-observation",
        )
        if not isinstance(raw_receipt, dict) or not isinstance(raw_observation, dict):
            raise TypeError("Harness Tool Step result objects are invalid")
        receipt = HarnessToolStepReceipt.from_dict(raw_receipt)
        validate_json_value(raw_observation)
        if (
            data.get("receiptDigest") != receipt.digest
            or receipt.intent_digest != intent.digest
            or receipt.tool_call_id != intent.tool_call_id
            or canonical_digest(raw_observation) != receipt.observation_digest
        ):
            raise ValueError("Harness Tool Step result differs from its Intent")

        previous_receipt = None
        previous_receipt_object = None
        previous_object_digest = data.get("previousReceiptObjectDigest")
        if receipt.previous_receipt_digest is None:
            if previous_object_digest is not None:
                raise ValueError("initial Tool Step Receipt unexpectedly references a predecessor")
        else:
            if not isinstance(previous_object_digest, str):
                raise ValueError("Tool Step Receipt predecessor object is missing")
            raw_previous = self.store.get_object(
                previous_object_digest,
                expected_kind="harness-tool-step-receipt",
            )
            if not isinstance(raw_previous, dict):
                raise ValueError("Tool Step Receipt predecessor is invalid")
            previous_receipt = HarnessToolStepReceipt.from_dict(raw_previous)
            previous_receipt_object = self.store.inspect_object(previous_object_digest)
            if (
                previous_receipt.digest != receipt.previous_receipt_digest
                or previous_receipt.intent_digest != intent.digest
                or previous_receipt.terminal
            ):
                raise ValueError("Tool Step Receipt predecessor chain is invalid")
        return StoredHarnessToolStep(
            intent,
            intent_object,
            fence,
            fence_object,
            receipt,
            self.store.inspect_object(receipt_object_digest),
            previous_receipt,
            previous_receipt_object,
            dict(raw_observation),
            self.store.inspect_object(observation_object_digest),
        )

    def record_pause(self, pause_reason: HarnessRunPauseReason) -> StoredHarnessRunSnapshot:
        state = self._require_state()
        now_ms = self.clock_ms()
        lease = self._acquire_lease("run-pause", pause_reason.value, now_ms=now_ms)
        try:
            snapshot = self._build_snapshot(
                pause_reason,
                active_intent_digests=(),
                created_at_ms=self._recorded_time(now_ms),
            )
            retained = self._store_snapshot(snapshot, state)
            self._append_event(
                lease=lease,
                event_kind="harness.run-paused",
                event_id=self._event_id("run-paused", snapshot.digest),
                data={
                    "snapshotDigest": snapshot.digest,
                    "snapshotObjectDigest": retained.snapshot_object.digest,
                    "stateObjectDigest": retained.state_object.digest,
                    "pauseReason": pause_reason.value,
                },
                recorded_at_ms=snapshot.created_at_ms,
                referenced_objects=(
                    retained.snapshot_object,
                    retained.state_object,
                ),
                caused_by_event_id=self._latest_event_id(),
            )
            return retained
        finally:
            self.store.release_run_lease(lease)

    def load_current_snapshot(self) -> StoredHarnessRunSnapshot:
        event = self._heads().snapshot
        if event is None:
            raise KeyError("Harness Run has no current Snapshot")
        data = event.data
        snapshot_object_digest = self._required_digest(data, "snapshotObjectDigest")
        state_object_digest = self._required_digest(data, "stateObjectDigest")
        raw_snapshot = self.store.get_object(
            snapshot_object_digest,
            expected_kind="harness-run-snapshot",
        )
        if not isinstance(raw_snapshot, dict):
            raise TypeError("Harness Run Snapshot object is invalid")
        snapshot = HarnessRunSnapshot.from_dict(raw_snapshot)
        if data.get("snapshotDigest") != snapshot.digest:
            raise ValueError("Harness Run Snapshot semantic digest differs")
        self._require_snapshot(snapshot)
        raw_state = self.store.get_object(
            state_object_digest,
            expected_kind="harness-run-state",
        )
        if not isinstance(raw_state, dict):
            raise TypeError("Harness Run State object is invalid")
        state = state_from_dict(raw_state, harness_run_id=self.harness_run_id)
        self._validate_snapshot_state(snapshot, state)
        return StoredHarnessRunSnapshot(
            snapshot,
            self.store.inspect_object(snapshot_object_digest),
            state,
            self.store.inspect_object(state_object_digest),
        )

    def doctor(self) -> dict[str, JsonValue]:
        base = self.store.doctor(full=True)
        events = self.store.list_run_events(self.harness_run_id)
        provider_records = 0
        tool_records = 0
        snapshots = 0
        for event in events:
            if event.event_kind in _PROVIDER_EVENT_KINDS:
                self._load_provider_from_event(event)
                provider_records += 1
            if event.event_kind in _TOOL_EVENT_KINDS:
                self._validate_tool_event(event)
                tool_records += 1
            if "snapshotObjectDigest" in event.data:
                self._load_snapshot_from_event(event)
                snapshots += 1
        from ..independent_result import IndependentRunRecorder

        independent = IndependentRunRecorder(
            self.store,
            self.contract,
            self.binding,
            clock_ms=self.clock_ms,
        ).doctor()
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-continuity-doctor",
            "healthy": True,
            "harnessRunId": self.harness_run_id,
            "runRevision": self.caller_revision,
            "providerRecords": provider_records,
            "toolRecords": tool_records,
            "snapshots": snapshots,
            "independentResult": independent,
            "store": base,
        }

    def _append_provider_event(
        self,
        *,
        lease: HarnessRunLease,
        event_kind: str,
        stored: StoredHarnessProviderCall,
        caused_by_event_id: str | None,
    ) -> None:
        references = [stored.record_object, stored.state_object]
        if stored.result_object is not None:
            references.append(stored.result_object)
        if stored.failure_object is not None:
            references.append(stored.failure_object)
        self._append_event(
            lease=lease,
            event_kind=event_kind,
            event_id=self._event_id("provider", stored.record.digest),
            data={
                "providerCallRecordDigest": stored.record.digest,
                "providerCallRecordObjectDigest": stored.record_object.digest,
                "stateObjectDigest": stored.state_object.digest,
                "resultObjectDigest": (
                    None if stored.result_object is None else stored.result_object.digest
                ),
                "failureObjectDigest": (
                    None if stored.failure_object is None else stored.failure_object.digest
                ),
            },
            recorded_at_ms=stored.record.recorded_at_ms,
            referenced_objects=tuple(references),
            caused_by_event_id=caused_by_event_id,
        )

    def _append_event(
        self,
        *,
        lease: HarnessRunLease,
        event_kind: str,
        event_id: str,
        data: dict[str, JsonValue],
        recorded_at_ms: int,
        referenced_objects: tuple[StoredHarnessObject, ...],
        caused_by_event_id: str | None,
    ) -> None:
        try:
            self.store.append_event(
                event_id=event_id,
                harness_run_id=self.harness_run_id,
                event_kind=event_kind,
                data=data,
                expected_revision=lease.run_revision,
                recorded_at_ms=recorded_at_ms,
                lease=lease,
                lease_checked_at_ms=self.clock_ms(),
                caused_by_event_id=caused_by_event_id,
                referenced_objects=referenced_objects,
            )
        except (
            HarnessEventConflict,
            HarnessLeaseConflict,
            HarnessRevisionConflict,
        ) as error:
            raise HarnessSuperseded(str(error)) from error

    def _acquire_lease(self, operation: str, token: str, *, now_ms: int) -> HarnessRunLease:
        owner_token = canonical_digest(
            {
                "harnessRunId": self.harness_run_id,
                "operation": operation,
                "token": token,
            }
        )[7:31]
        return self.store.acquire_run_lease(
            self.harness_run_id,
            owner_id=f"{self._execution_owner_id}:{operation}:{owner_token}",
            ttl_ms=_STORE_LEASE_TTL_MS,
            now_ms=now_ms,
        )

    def _heads(self) -> _Heads:
        provider = None
        tool = None
        snapshot = None
        for event in self.store.list_run_events(self.harness_run_id):
            if event.event_kind in _PROVIDER_CLEAR_EVENT_KINDS:
                provider = None
            if event.event_kind in _PROVIDER_EVENT_KINDS:
                provider = event
            if event.event_kind in _TOOL_EVENT_KINDS:
                tool = event
            if "snapshotObjectDigest" in event.data:
                snapshot = event
        return _Heads(provider=provider, tool=tool, snapshot=snapshot)

    def _load_current_provider_call_or_none(
        self,
    ) -> StoredHarnessProviderCall | None:
        event = self._heads().provider
        return None if event is None else self._load_provider_from_event(event)

    def _load_provider_from_event(self, event: HarnessRunEventRecord) -> StoredHarnessProviderCall:
        data = event.data
        record_object_digest = self._required_digest(data, "providerCallRecordObjectDigest")
        raw_record = self.store.get_object(
            record_object_digest,
            expected_kind="harness-provider-call-record",
        )
        if not isinstance(raw_record, dict):
            raise ValueError("Harness Provider Call record object is invalid")
        if raw_record.get("schemaVersion") != 2:
            raise ValueError("independent Harness Store requires caller-neutral Provider Call v2")
        record = HarnessProviderCallRecordV2.from_dict(raw_record)
        self._require_provider_record(record)
        if data.get("providerCallRecordDigest") != record.digest:
            raise ValueError("Harness Provider Call record digest differs")
        state_object_digest = self._required_digest(data, "stateObjectDigest")
        if state_object_digest != record.state_object_digest:
            raise ValueError("Harness Provider Call state reference differs")
        raw_state = self.store.get_object(
            state_object_digest,
            expected_kind="harness-run-state",
        )
        if not isinstance(raw_state, dict):
            raise TypeError("Harness Provider Call state object is invalid")
        state = state_from_dict(raw_state, harness_run_id=self.harness_run_id)
        state_object = self.store.inspect_object(state_object_digest)

        result = None
        result_object = None
        result_object_digest = data.get("resultObjectDigest")
        if result_object_digest is not None:
            if not isinstance(result_object_digest, str):
                raise ValueError("Provider result object reference is invalid")
            raw_result = self.store.get_object(
                result_object_digest,
                expected_kind="agent-turn-result",
            )
            if not isinstance(raw_result, dict):
                raise TypeError("Provider result object is invalid")
            result = AgentTurnResult.from_dict(raw_result)
            result_object = self.store.inspect_object(result_object_digest)
            if (
                record.result_digest != result.digest
                or record.result_object_digest != result_object_digest
            ):
                raise ValueError("Provider result differs from its record")
        elif record.result_digest is not None or record.result_object_digest is not None:
            raise ValueError("Provider result references are incomplete")

        failure = None
        failure_object = None
        failure_object_digest = data.get("failureObjectDigest")
        if failure_object_digest is not None:
            if not isinstance(failure_object_digest, str):
                raise ValueError("Provider failure object reference is invalid")
            raw_failure = self.store.get_object(
                failure_object_digest,
                expected_kind="harness-provider-call-failure",
            )
            if not isinstance(raw_failure, dict):
                raise TypeError("Provider failure object is invalid")
            failure = HarnessProviderCallFailureReceipt.from_dict(raw_failure)
            failure_object = self.store.inspect_object(failure_object_digest)
            if (
                record.failure_digest != failure.digest
                or record.failure_object_digest != failure_object_digest
            ):
                raise ValueError("Provider failure differs from its record")
        elif record.failure_digest is not None or record.failure_object_digest is not None:
            raise ValueError("Provider failure references are incomplete")
        return StoredHarnessProviderCall(
            record,
            self.store.inspect_object(record_object_digest),
            state,
            state_object,
            result,
            result_object,
            failure,
            failure_object,
        )

    def _validate_tool_event(self, event: HarnessRunEventRecord) -> None:
        data = event.data
        intent_object_digest = self._required_digest(data, "toolStepIntentObjectDigest")
        raw_intent = self.store.get_object(
            intent_object_digest,
            expected_kind="harness-tool-step-intent",
        )
        if not isinstance(raw_intent, dict):
            raise ValueError("Harness Tool Step Intent event object is invalid")
        intent = HarnessToolStepIntent.from_dict(raw_intent)
        self._require_intent(intent)
        if data.get("toolStepIntentDigest") != intent.digest:
            raise ValueError("Harness Tool Step Intent event digest differs")
        fence_object_digest = data.get("dispatchFenceObjectDigest")
        if fence_object_digest is not None:
            if not isinstance(fence_object_digest, str):
                raise ValueError("Harness Dispatch Fence event reference is invalid")
            raw_fence = self.store.get_object(
                fence_object_digest,
                expected_kind="harness-dispatch-fence",
            )
            if not isinstance(raw_fence, dict):
                raise ValueError("Harness Dispatch Fence event object is invalid")
            fence = (
                HarnessDispatchFenceV2.from_dict(raw_fence)
                if raw_fence.get("schemaVersion") == 2
                else HarnessDispatchFence.from_dict(raw_fence)
            )
            if (
                data.get("dispatchFenceDigest") != fence.digest
                or fence.intent_digest != intent.digest
            ):
                raise ValueError("Harness Dispatch Fence event differs")
        receipt_object_digest = data.get("receiptObjectDigest")
        observation_object_digest = data.get("observationObjectDigest")
        if receipt_object_digest is None and observation_object_digest is None:
            return
        if not isinstance(receipt_object_digest, str) or not isinstance(
            observation_object_digest, str
        ):
            raise ValueError("Harness Tool Step result event references are incomplete")
        raw_receipt = self.store.get_object(
            receipt_object_digest,
            expected_kind="harness-tool-step-receipt",
        )
        raw_observation = self.store.get_object(
            observation_object_digest,
            expected_kind="harness-tool-observation",
        )
        if not isinstance(raw_receipt, dict) or not isinstance(raw_observation, dict):
            raise ValueError("Harness Tool Step result event objects are invalid")
        receipt = HarnessToolStepReceipt.from_dict(raw_receipt)
        if (
            data.get("receiptDigest") != receipt.digest
            or receipt.intent_digest != intent.digest
            or canonical_digest(raw_observation) != receipt.observation_digest
        ):
            raise ValueError("Harness Tool Step result event differs")

    def _load_snapshot_from_event(self, event: HarnessRunEventRecord) -> StoredHarnessRunSnapshot:
        data = event.data
        snapshot_object_digest = self._required_digest(data, "snapshotObjectDigest")
        state_object_digest = self._required_digest(data, "stateObjectDigest")
        raw_snapshot = self.store.get_object(
            snapshot_object_digest,
            expected_kind="harness-run-snapshot",
        )
        raw_state = self.store.get_object(
            state_object_digest,
            expected_kind="harness-run-state",
        )
        if not isinstance(raw_snapshot, dict) or not isinstance(raw_state, dict):
            raise ValueError("Harness Snapshot event objects are invalid")
        snapshot = HarnessRunSnapshot.from_dict(raw_snapshot)
        state = state_from_dict(raw_state, harness_run_id=self.harness_run_id)
        self._require_snapshot(snapshot)
        self._validate_snapshot_state(snapshot, state)
        if data.get("snapshotDigest") != snapshot.digest:
            raise ValueError("Harness Snapshot event digest differs")
        return StoredHarnessRunSnapshot(
            snapshot,
            self.store.inspect_object(snapshot_object_digest),
            state,
            self.store.inspect_object(state_object_digest),
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
    ) -> HarnessProviderCallRecordV2:
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
        return HarnessProviderCallRecordV2(
            record_id=f"harness-provider-call-record:{record_token}",
            provider_call_id=provider_call_id,
            harness_run_id=self.harness_run_id,
            binding_digest=self.binding.digest,
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
        previous,
        *,
        status: HarnessProviderCallStatus,
        state_object_digest: str,
        recorded_at_ms: int,
        result_digest: str | None = None,
        result_object_digest: str | None = None,
        failure_digest: str | None = None,
        failure_object_digest: str | None = None,
    ) -> HarnessProviderCallRecordV2:
        return self._provider_call_record(
            provider_call_id=previous.provider_call_id,
            source=HarnessProviderCallSourceRef(
                previous.source_kind,
                previous.source_digest,
                previous.source_object_digest,
            ),
            state_object_digest=state_object_digest,
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
            recorded_at_ms=recorded_at_ms,
        )

    def _store_provider_call(
        self,
        record: HarnessProviderCallRecordV2,
        *,
        state_object: StoredHarnessObject,
        result: AgentTurnResult | None = None,
        result_object: StoredHarnessObject | None = None,
        failure: HarnessProviderCallFailureReceipt | None = None,
        failure_object: StoredHarnessObject | None = None,
    ) -> StoredHarnessProviderCall:
        if record.state_object_digest != state_object.digest:
            raise ValueError("Provider Call state object differs from its record")
        if (result is None) != (result_object is None):
            raise ValueError("Provider Call result object is incomplete")
        if result is not None and (
            record.result_digest != result.digest
            or record.result_object_digest != result_object.digest
        ):
            raise ValueError("Provider Call result differs from its record")
        if (failure is None) != (failure_object is None):
            raise ValueError("Provider Call failure object is incomplete")
        if failure is not None and (
            record.failure_digest != failure.digest
            or record.failure_object_digest != failure_object.digest
        ):
            raise ValueError("Provider Call failure differs from its record")
        record_object = self.store.put_object(record.to_dict(), kind="harness-provider-call-record")
        return StoredHarnessProviderCall(
            record,
            record_object,
            self._state_for_object(state_object),
            state_object,
            result,
            result_object,
            failure,
            failure_object,
        )

    def _put_state(self, state: HarnessRunState) -> StoredHarnessObject:
        return self.store.put_object(
            state.to_dict(self.harness_run_id),
            kind="harness-run-state",
        )

    def _state_for_object(self, stored: StoredHarnessObject) -> HarnessRunState:
        raw = self.store.get_object(stored.digest, expected_kind=stored.kind)
        if not isinstance(raw, dict):
            raise TypeError("Harness Run state object is invalid")
        state = state_from_dict(raw, harness_run_id=self.harness_run_id)
        if self._bound_state is not None and state != self._bound_state:
            raise ValueError("Provider Call state object differs from bound state")
        return state

    def _store_snapshot(
        self,
        snapshot: HarnessRunSnapshot,
        state: HarnessRunState,
    ) -> StoredHarnessRunSnapshot:
        self._validate_snapshot_state(snapshot, state)
        snapshot_object = self.store.put_object(snapshot.to_dict(), kind="harness-run-snapshot")
        state_object = self._put_state(state)
        return StoredHarnessRunSnapshot(
            snapshot,
            snapshot_object,
            state,
            state_object,
        )

    def _build_snapshot(
        self,
        pause_reason: HarnessRunPauseReason,
        *,
        active_intent_digests: tuple[str, ...],
        created_at_ms: int,
    ) -> HarnessRunSnapshot:
        state = self._require_state()
        self._snapshot_sequence += 1
        return HarnessRunSnapshot(
            snapshot_id=(
                f"harness-run-snapshot:{self.harness_run_id.removeprefix('harness-run:')}:"
                f"s{self._snapshot_sequence}"
            ),
            harness_run_id=self.harness_run_id,
            assignment_id=self.binding.assignment_id,
            assignment_generation=self.binding.assignment_generation,
            assignment_digest=self.binding.assignment_digest,
            sequence=self._snapshot_sequence,
            tool_catalog_digest=self.contract.tool_catalog_digest,
            requested_model_id=state.requested_model_id,
            effective_model_id=state.effective_model_id,
            messages_digest=state.messages_digest,
            observation_digests=state.observation_digests,
            active_tool_step_intent_digests=active_intent_digests,
            remaining_budget=state.remaining_budget,
            pause_reason=pause_reason,
            created_at_ms=created_at_ms,
        )

    def _require_provider_source_current(self, source: HarnessProviderCallSourceRef) -> None:
        snapshot_event = self._heads().snapshot
        if source.kind is HarnessProviderCallSource.ASSIGNMENT:
            if snapshot_event is not None:
                raise HarnessSuperseded(
                    "initial Provider Call source was replaced by a Run Snapshot"
                )
            if source != self.assignment_provider_source():
                raise HarnessSuperseded("Provider Call Contract source is no longer current")
            return
        if snapshot_event is None:
            raise HarnessSuperseded("Provider Call Snapshot source is absent")
        if (
            snapshot_event.data.get("snapshotDigest") != source.digest
            or snapshot_event.data.get("snapshotObjectDigest") != source.object_digest
        ):
            raise HarnessSuperseded("Provider Call Snapshot source is no longer current")

    def _require_provider_request_matches(
        self,
        record,
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

    def _require_provider_record(self, record: HarnessProviderCallRecordV2) -> None:
        if (
            record.harness_run_id != self.harness_run_id
            or record.binding_digest != self.binding.digest
        ):
            raise ValueError("Harness Provider Call differs from the current Run binding")

    def _require_current_provider_call(self, expected) -> StoredHarnessProviderCall:
        current = self.load_current_provider_call()
        if current.record != expected:
            raise HarnessSuperseded("Harness Provider Call is no longer current")
        return current

    def _require_provider_continuation_state(
        self,
        record,
        *,
        snapshot_state: HarnessRunState,
        provider_state: HarnessRunState,
        additional_messages: tuple[dict[str, JsonValue], ...],
    ) -> None:
        expected_prefix = snapshot_state.messages + tuple(
            dict(message) for message in additional_messages
        )
        ordered_sequences = (
            (snapshot_state.observations, provider_state.observations),
            (snapshot_state.provider_usage, provider_state.provider_usage),
            (snapshot_state.effective_model_ids, provider_state.effective_model_ids),
        )
        if (
            provider_state.requested_model_id != snapshot_state.requested_model_id
            or provider_state.requested_model_id != record.requested_model_id
            or provider_state.messages[: len(expected_prefix)] != expected_prefix
            or any(current[: len(previous)] != previous for previous, current in ordered_sequences)
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
        max_calls = self.contract.budget.get("maxModelCalls")
        snapshot_remaining = snapshot_state.remaining_budget.get("modelCalls")
        provider_remaining = provider_state.remaining_budget.get("modelCalls")
        if (
            type(max_calls) is not int
            or type(snapshot_remaining) is not int
            or type(provider_remaining) is not int
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call state omitted its model-call budget"
            )
        snapshot_calls = max_calls - snapshot_remaining
        provider_calls = max_calls - provider_remaining
        if (
            snapshot_calls < 0
            or provider_calls < snapshot_calls
            or record.turn_sequence != provider_calls + 1
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider Call turn differs from its saved Run state"
            )
        resettable = {"observationOnlyTurns", "noProgressTurns"} if additional_messages else set()
        for field, snapshot_value in snapshot_state.remaining_budget.items():
            if field in resettable:
                continue
            provider_value = provider_state.remaining_budget.get(field)
            if type(snapshot_value) is int and (
                type(provider_value) is not int or provider_value > snapshot_value
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
            raise HarnessProviderCallRequestMismatch(f"{label} state changed outside active time")
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
                raise HarnessProviderCallRequestMismatch(f"{label} changed a non-time budget")
        cls._require_provider_time_monotonic(previous, current, label=label)

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
            raise HarnessProviderCallRequestMismatch(f"{label} active elapsed time decreased")
        previous_wall = previous.remaining_budget.get("wallTimeMs")
        current_wall = current.remaining_budget.get("wallTimeMs")
        if (
            type(previous_wall) is not int
            or type(current_wall) is not int
            or current_wall > previous_wall
        ):
            raise HarnessProviderCallRequestMismatch(f"{label} remaining wall time increased")

    @staticmethod
    def _require_failure_matches(record, failure) -> None:
        if (
            failure.provider_call_id != record.provider_call_id
            or failure.request_digest != record.request_digest
            or failure.provider_request_digest != record.provider_request_digest
        ):
            raise HarnessProviderCallRequestMismatch(
                "Provider failure receipt differs from the current attempt"
            )

    def _require_intent(self, intent: HarnessToolStepIntent) -> None:
        if (
            intent.harness_run_id != self.harness_run_id
            or intent.assignment_id != self.binding.assignment_id
            or intent.assignment_generation != self.binding.assignment_generation
            or intent.assignment_digest != self.binding.assignment_digest
        ):
            raise ValueError("Tool Step Intent differs from the current Run binding")

    def _require_snapshot(self, snapshot: HarnessRunSnapshot) -> None:
        if (
            snapshot.harness_run_id != self.harness_run_id
            or snapshot.assignment_id != self.binding.assignment_id
            or snapshot.assignment_generation != self.binding.assignment_generation
            or snapshot.assignment_digest != self.binding.assignment_digest
            or snapshot.tool_catalog_digest != self.contract.tool_catalog_digest
        ):
            raise ValueError("Harness Run Snapshot differs from the current Run binding")

    def _require_state(self) -> HarnessRunState:
        if self._bound_state is None:
            raise RuntimeError("Harness Run state was not bound before persistence")
        return self._bound_state

    def _require_active_time_budget_consistent(self, state: HarnessRunState) -> None:
        if state.active_elapsed_ms is None:
            return
        max_wall_time_ms = self.contract.budget.get("maxWallTimeMs")
        if max_wall_time_ms is None:
            return
        remaining = state.remaining_budget.get("wallTimeMs")
        if (
            type(max_wall_time_ms) is not int
            or max_wall_time_ms < 1
            or type(remaining) is not int
            or remaining != max(0, max_wall_time_ms - state.active_elapsed_ms)
        ):
            raise ValueError(
                "Harness Run active elapsed time differs from its committed wall-time budget"
            )

    @staticmethod
    def _validate_snapshot_state(
        snapshot: HarnessRunSnapshot,
        state: HarnessRunState,
    ) -> None:
        if (
            snapshot.messages_digest != state.messages_digest
            or snapshot.observation_digests != state.observation_digests
            or snapshot.remaining_budget != state.remaining_budget
            or snapshot.requested_model_id != state.requested_model_id
            or snapshot.effective_model_id != state.effective_model_id
        ):
            raise ValueError("Harness Run Snapshot differs from its bounded state")

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

    def _provider_event_id_for_digest(self, digest: str) -> str | None:
        for event in reversed(self.store.list_run_events(self.harness_run_id)):
            if event.data.get("providerCallRecordDigest") == digest:
                return event.event_id
        return None

    def _tool_event_id_for_intent(self, digest: str) -> str | None:
        for event in reversed(self.store.list_run_events(self.harness_run_id)):
            if event.data.get("toolStepIntentDigest") == digest:
                return event.event_id
        return None

    def _latest_event_id(self) -> str | None:
        events = self.store.list_run_events(self.harness_run_id)
        return None if not events else events[-1].event_id

    def _current_snapshot_sequence(self) -> int:
        maximum = 0
        for event in self.store.list_run_events(self.harness_run_id):
            object_digest = event.data.get("snapshotObjectDigest")
            if not isinstance(object_digest, str):
                continue
            raw = self.store.get_object(
                object_digest,
                expected_kind="harness-run-snapshot",
            )
            if not isinstance(raw, dict):
                raise TypeError("current Harness Run Snapshot is not an object")
            maximum = max(maximum, HarnessRunSnapshot.from_dict(raw).sequence)
        return maximum

    def _recorded_time(
        self,
        proposed: int,
        *,
        previous_recorded_at_ms: int | None = None,
    ) -> int:
        projection = self.store.load_run(self.harness_run_id)
        values = [proposed, projection.updated_at_ms]
        if previous_recorded_at_ms is not None:
            values.append(previous_recorded_at_ms + 1)
        return max(values)

    @staticmethod
    def _event_id(label: str, digest: str) -> str:
        return f"event:harness-continuity:{label}:{digest[7:31]}"

    @staticmethod
    def _required_digest(data: dict[str, JsonValue], field: str) -> str:
        value = data.get(field)
        if not isinstance(value, str):
            raise ValueError(f"Harness continuity Event field is missing: {field}")
        return value

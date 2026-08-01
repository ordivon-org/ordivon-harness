from __future__ import annotations

from dataclasses import dataclass, replace

from anc_canonical import JsonValue, canonical_digest, validate_json_value
from ordivon_host import HostExtensionPort, HostKernelError
from ordivon_host.objects import StoredObject
from ordivon_protocol import (
    HarnessDispatchFence,
    HarnessRunPauseReason,
    HarnessRunSnapshot,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
)

from ..event_kinds import (
    HARNESS_RUN_SNAPSHOT_RECORDED,
    HARNESS_TOOL_STEP_PREPARED,
    HARNESS_TOOL_STEP_RECORDED,
)
from ..host import CommittedHarnessAssignment, HarnessHost, HarnessSuperseded
from ..run_state import (
    HarnessRunState,
    build_state_delta,
    load_state_object,
)

_DISPATCH_FENCE_TTL_MS = 30_000
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
        self._snapshot_sequence = self._current_snapshot_sequence()

    def bind_state(self, state: HarnessRunState) -> None:
        self._bound_state = state

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
            remove_fields=_RECEIPT_FIELDS,
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
            remove_fields=("activeHarnessToolStepIntentDigest",),
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
    ) -> None:
        task_id = self.committed.assignment.task_id
        current_assignment = self.host.load_current_assignment(task_id)
        if (
            current_assignment.task_revision != self.committed.task_revision
            or current_assignment.assignment != self.committed.assignment
        ):
            raise HarnessSuperseded("Harness Assignment is no longer current")
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
        except HostKernelError as error:
            raise HarnessSuperseded(str(error)) from error
        self.committed = replace(
            self.committed, task_revision=committed.projection.revision
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

    def _require_state(self) -> HarnessRunState:
        if self._bound_state is None:
            raise RuntimeError("Harness Run state was not bound before persistence")
        return self._bound_state

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

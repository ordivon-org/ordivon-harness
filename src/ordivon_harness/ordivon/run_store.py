from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value
from ordivon_protocol import (
    HarnessRunPauseReason,
    HarnessRunSnapshot,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
)
from ordivon_host.objects import StoredObject

from ..event_kinds import (
    HARNESS_RUN_SNAPSHOT_RECORDED,
    HARNESS_TOOL_STEP_PREPARED,
    HARNESS_TOOL_STEP_RECORDED,
)
from ..host import CommittedHarnessAssignment, HarnessHost, HarnessSuperseded


@dataclass(frozen=True, slots=True)
class HarnessRunState:
    messages: tuple[dict[str, JsonValue], ...]
    observations: tuple[dict[str, JsonValue], ...]
    remaining_budget: dict[str, JsonValue]
    requested_model_id: str
    effective_model_id: str | None

    def __post_init__(self) -> None:
        validate_json_value(list(self.messages))
        validate_json_value(list(self.observations))
        validate_json_value(self.remaining_budget)
        if not self.requested_model_id or self.requested_model_id != self.requested_model_id.strip():
            raise ValueError("requested model identity must be non-empty and trimmed")

    @property
    def messages_digest(self) -> str:
        return canonical_digest(list(self.messages))

    @property
    def observation_digests(self) -> tuple[str, ...]:
        return tuple(canonical_digest(item) for item in self.observations)

    def to_dict(self, harness_run_id: str) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-run-state",
            "harnessRunId": harness_run_id,
            "messages": list(self.messages),
            "observations": list(self.observations),
            "remainingBudget": self.remaining_budget,
            "requestedModelId": self.requested_model_id,
            "effectiveModelId": self.effective_model_id,
        }


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
    receipt: HarnessToolStepReceipt | None
    receipt_object: StoredObject | None
    observation: dict[str, JsonValue] | None
    observation_object: StoredObject | None


class HostHarnessRunStore:
    """Thin Host-Journal adapter for native Harness continuity objects."""

    def __init__(
        self,
        host: HarnessHost,
        committed: CommittedHarnessAssignment,
    ) -> None:
        native = committed.native_run_contract
        if native is None:
            raise ValueError("Harness Run Store requires a native Run Contract")
        self.host = host
        self.committed = committed
        self.harness_run_id = native.harness_run_id
        self._bound_state: HarnessRunState | None = None
        self._snapshot_sequence = self._current_snapshot_sequence()

    def bind_state(self, state: HarnessRunState) -> None:
        self._bound_state = state

    def prepare_tool_step(self, intent: HarnessToolStepIntent) -> StoredHarnessRunSnapshot:
        self._require_intent(intent)
        snapshot = self._build_snapshot(
            HarnessRunPauseReason.EFFECT_DISPATCH_PENDING,
            active_intent_digests=(intent.digest,),
        )
        state = self._require_state()
        intent_object = self.host.storage.put_object(
            intent.to_dict(), kind="harness-tool-step-intent"
        )
        retained = self._store_snapshot(snapshot, state)
        payload = {
            "harnessToolStepIntentDigest": intent.digest,
            "harnessToolStepIntentObjectDigest": intent_object.digest,
            "activeHarnessToolStepIntentDigest": intent.digest,
            "harnessRunSnapshotDigest": snapshot.digest,
            "harnessRunSnapshotObjectDigest": retained.snapshot_object.digest,
            "harnessRunStateObjectDigest": retained.state_object.digest,
        }
        self._commit(
            kind=HARNESS_TOOL_STEP_PREPARED,
            payload=payload,
            referenced_objects=(
                intent_object,
                retained.snapshot_object,
                retained.state_object,
            ),
            label="Harness Tool Step Intent",
            event_suffix=f"tool-step-prepared:{intent.digest[7:23]}",
        )
        return retained

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
        receipt_object = self.host.storage.put_object(
            receipt.to_dict(), kind="harness-tool-step-receipt"
        )
        observation_object = self.host.storage.put_object(
            observation, kind="harness-tool-observation"
        )
        self._commit(
            kind=HARNESS_TOOL_STEP_RECORDED,
            payload={
                "harnessToolStepReceiptDigest": receipt.digest,
                "harnessToolStepReceiptObjectDigest": receipt_object.digest,
                "harnessToolStepObservationObjectDigest": observation_object.digest,
            },
            referenced_objects=(receipt_object, observation_object),
            label="Harness Tool Step Receipt",
            event_suffix=f"tool-step-recorded:{receipt.digest[7:23]}",
            clear_active_intent=True,
        )

    def load_current_tool_step(self) -> StoredHarnessToolStep:
        current = self.host.storage.read_task_event(self.committed.assignment.task_id)
        data = self.host._data(current)
        intent_object_digest = data.get("harnessToolStepIntentObjectDigest")
        if not isinstance(intent_object_digest, str):
            raise KeyError("Task has no current Harness Tool Step Intent")
        raw_intent = self.host.storage.objects.get(
            intent_object_digest, expected_kind="harness-tool-step-intent"
        )
        if not isinstance(raw_intent, dict):
            raise ValueError("Harness Tool Step Intent object is invalid")
        intent = HarnessToolStepIntent.from_dict(raw_intent)
        self._require_intent(intent)
        intent_object = self.host.storage.objects.inspect(intent_object_digest)
        receipt_digest = data.get("harnessToolStepReceiptObjectDigest")
        observation_digest = data.get("harnessToolStepObservationObjectDigest")
        if receipt_digest is None and observation_digest is None:
            return StoredHarnessToolStep(
                intent, intent_object, None, None, None, None
            )
        if not isinstance(receipt_digest, str) or not isinstance(
            observation_digest, str
        ):
            raise ValueError("Harness Tool Step result references are incomplete")
        raw_receipt = self.host.storage.objects.get(
            receipt_digest, expected_kind="harness-tool-step-receipt"
        )
        raw_observation = self.host.storage.objects.get(
            observation_digest, expected_kind="harness-tool-observation"
        )
        if not isinstance(raw_receipt, dict) or not isinstance(
            raw_observation, dict
        ):
            raise ValueError("Harness Tool Step result objects are invalid")
        receipt = HarnessToolStepReceipt.from_dict(raw_receipt)
        validate_json_value(raw_observation)
        if (
            receipt.intent_digest != intent.digest
            or receipt.tool_call_id != intent.tool_call_id
            or canonical_digest(raw_observation) != receipt.observation_digest
        ):
            raise ValueError("Harness Tool Step result differs from its Intent")
        return StoredHarnessToolStep(
            intent,
            intent_object,
            receipt,
            self.host.storage.objects.inspect(receipt_digest),
            dict(raw_observation),
            self.host.storage.objects.inspect(observation_digest),
        )

    def record_pause(
        self, pause_reason: HarnessRunPauseReason
    ) -> StoredHarnessRunSnapshot:
        snapshot = self._build_snapshot(pause_reason, active_intent_digests=())
        retained = self._store_snapshot(snapshot, self._require_state())
        self._commit(
            kind=HARNESS_RUN_SNAPSHOT_RECORDED,
            payload={
                "harnessRunSnapshotDigest": snapshot.digest,
                "harnessRunSnapshotObjectDigest": retained.snapshot_object.digest,
                "harnessRunStateObjectDigest": retained.state_object.digest,
            },
            referenced_objects=(retained.snapshot_object, retained.state_object),
            label="Harness Run Snapshot",
            event_suffix=f"run-snapshot:{snapshot.sequence}",
            clear_active_intent=True,
        )
        return retained

    def load_current_snapshot(self) -> StoredHarnessRunSnapshot:
        current = self.host.storage.read_task_event(self.committed.assignment.task_id)
        data = self.host._data(current)
        snapshot_digest = data.get("harnessRunSnapshotObjectDigest")
        state_digest = data.get("harnessRunStateObjectDigest")
        if not isinstance(snapshot_digest, str) or not isinstance(state_digest, str):
            raise KeyError("Task has no current Harness Run Snapshot")
        raw_snapshot = self.host.storage.objects.get(
            snapshot_digest, expected_kind="harness-run-snapshot"
        )
        raw_state = self.host.storage.objects.get(
            state_digest, expected_kind="harness-run-state"
        )
        if not isinstance(raw_snapshot, dict) or not isinstance(raw_state, dict):
            raise ValueError("Harness Run Snapshot objects are invalid")
        snapshot = HarnessRunSnapshot.from_dict(raw_snapshot)
        state = self._state_from_dict(raw_state)
        self._validate_snapshot_state(snapshot, state)
        return StoredHarnessRunSnapshot(
            snapshot,
            self.host.storage.objects.inspect(snapshot_digest),
            state,
            self.host.storage.objects.inspect(state_digest),
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
        self, snapshot: HarnessRunSnapshot, state: HarnessRunState
    ) -> StoredHarnessRunSnapshot:
        self._validate_snapshot_state(snapshot, state)
        snapshot_object = self.host.storage.put_object(
            snapshot.to_dict(), kind="harness-run-snapshot"
        )
        state_object = self.host.storage.put_object(
            state.to_dict(self.harness_run_id), kind="harness-run-state"
        )
        return StoredHarnessRunSnapshot(snapshot, snapshot_object, state, state_object)

    def _commit(
        self,
        *,
        kind,
        payload: dict[str, JsonValue],
        referenced_objects: tuple[StoredObject, ...],
        label: str,
        event_suffix: str,
        clear_active_intent: bool = False,
    ) -> None:
        task_id = self.committed.assignment.task_id
        current = self.host.storage.read_task_event(task_id)
        if current.projection.revision != self.committed.task_revision:
            raise HarnessSuperseded(
                f"Task revision is {current.projection.revision}, expected {self.committed.task_revision}"
            )
        current_assignment = self.host._assignment_from_snapshot(current)
        if current_assignment is None or current_assignment.assignment != self.committed.assignment:
            raise HarnessSuperseded("Harness Assignment is no longer current")
        state_fields = self.host._current_state_fields(self.host._data(current))
        if clear_active_intent:
            state_fields.pop("activeHarnessToolStepIntentDigest", None)
        data = {
            **state_fields,
            **self.host._assignment_fields(self.committed),
            **payload,
        }
        references = self.host._dedupe_objects(
            self.host._state_objects(state_fields)
            + self.host._assignment_objects(self.committed)
            + referenced_objects
        )
        with self.host.kernel.locked_task(
            task_id,
            expected_revision=self.committed.task_revision,
            expected_state=current.projection.state,
            expected_frontier=current.projection.ready_frontier,
            label=label,
            error_factory=self.host._kernel_error,
        ) as locked:
            projection = locked.commit(
                event_id=f"event:{self.host._token(task_id)}:{event_suffix}",
                kind=kind,
                payload=data,
                state=locked.projection.state,
                frontier=locked.projection.ready_frontier,
                referenced_objects=references,
            ).projection
        self.committed = replace(self.committed, task_revision=projection.revision)

    def _current_snapshot_sequence(self) -> int:
        current = self.host.storage.read_task_event(self.committed.assignment.task_id)
        data = self.host._data(current)
        digest = data.get("harnessRunSnapshotObjectDigest")
        if not isinstance(digest, str):
            return 0
        raw = self.host.storage.objects.get(digest, expected_kind="harness-run-snapshot")
        if not isinstance(raw, dict):
            raise ValueError("current Harness Run Snapshot is not an object")
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

    def _state_from_dict(self, value: dict[str, Any]) -> HarnessRunState:
        if set(value) != {
            "schemaVersion",
            "kind",
            "harnessRunId",
            "messages",
            "observations",
            "remainingBudget",
            "requestedModelId",
            "effectiveModelId",
        }:
            raise ValueError("Harness Run state fields differ")
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-run-state"
            or value["harnessRunId"] != self.harness_run_id
            or not isinstance(value["messages"], list)
            or not isinstance(value["observations"], list)
            or not isinstance(value["remainingBudget"], dict)
            or not isinstance(value["requestedModelId"], str)
            or value["effectiveModelId"] is not None
            and not isinstance(value["effectiveModelId"], str)
        ):
            raise ValueError("Harness Run state is invalid")
        if any(not isinstance(item, dict) for item in value["messages"]):
            raise ValueError("Harness Run messages are invalid")
        if any(not isinstance(item, dict) for item in value["observations"]):
            raise ValueError("Harness Run observations are invalid")
        return HarnessRunState(
            messages=tuple(dict(item) for item in value["messages"]),
            observations=tuple(dict(item) for item in value["observations"]),
            remaining_budget=dict(value["remainingBudget"]),
            requested_model_id=value["requestedModelId"],
            effective_model_id=value["effectiveModelId"],
        )

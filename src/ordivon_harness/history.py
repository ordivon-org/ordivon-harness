from __future__ import annotations

from dataclasses import dataclass

from anc_canonical import JsonValue, canonical_digest, validate_json_value
from anc_effect_binding import EffectBinding
from anc_effect_ir import EffectEnvelope, effect_digest
from ordivon_host.domain import EventKind, TaskProjection, TaskState
from ordivon_host.effects import TaskOutcome
from ordivon_host.journal import JournalCorruption
from ordivon_host.objects import ObjectCorrupt
from ordivon_host.storage import HostStorage
from .event_kinds import (
    COMPLETION_DECIDED,
    COMPLETION_PROPOSED,
    HARNESS_PROVIDER_CALL_CLAIMED,
    HARNESS_PROVIDER_CALL_COMPLETED,
    HARNESS_PROVIDER_CALL_DISPATCHING,
    HARNESS_PROVIDER_CALL_FAILED,
    HARNESS_PROVIDER_CALL_SUPERSEDED,
    HARNESS_PROVIDER_CALL_UNKNOWN,
    HARNESS_RUN_RECORDED,
    HARNESS_RUN_SNAPSHOT_RECORDED,
    HARNESS_TOOL_STEP_PREPARED,
    HARNESS_TOOL_STEP_RECORDED,
)
from .ordivon.model import AgentTurnResult
from .protocol import (
    HarnessDispatchFence,
    HarnessProviderCallFailureReceipt,
    HarnessProviderCallRecord,
    HarnessProviderCallSource,
    HarnessProviderCallStatus,
    HarnessRunSnapshot,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
)

from .contracts import CompletionVerification, NativeHarnessRunContract, ToolGrant
from .disposition import (
    CompletionRoute,
    NativeRunFacts,
    NativeRunPhase,
    derive_native_run_disposition,
    recovery_unknowns,
)
from .models import (
    CompletionDecision,
    CompletionProposal,
    HarnessAssignment,
    HarnessRunReceipt,
)
from .recovery import NativeRunAbandonment, NativeRunRecoveryAssessment
from .run_state import HarnessRunState, load_state_object
from .tool_semantics import (
    NativeToolCatalogSnapshot,
    legacy_grant_recovery_consequence,
    recovery_consequence_from_persisted,
)

_EVENT_FIELDS = {
    "schemaVersion",
    "kind",
    "eventKind",
    "data",
    "projection",
}
_CAS_DIGEST_KEYS = frozenset(
    {
        "planDigest",
        "catalogObjectDigest",
        "effectDigest",
        "bindingDigest",
        "authorityDecisionDigest",
        "dispatchDigest",
        "requestObjectDigest",
        "observationDigest",
        "readObservationDigest",
        "verificationDigest",
        "diffObjectDigest",
        "outcomeDigest",
        "childOutcomeDigest",
        "contextObjectDigest",
        "decisionObjectDigest",
        "admissionObjectDigest",
        "intentObjectDigest",
        "observationObjectDigest",
        "invocationReceiptDigest",
        "proposalObjectDigest",
        "resolutionObjectDigest",
        "outputObservationDigest",
        "taskAttemptObjectDigest",
        "taskContractObjectDigest",
        "harnessManifestObjectDigest",
        "assignmentObjectDigest",
        "toolGrantObjectDigest",
        "toolCatalogObjectDigest",
        "nativeHarnessRunContractObjectDigest",
        "harnessRunObjectDigest",
        "harnessTraceObjectDigest",
        "runConclusionObjectDigest",
        "harnessToolStepIntentObjectDigest",
        "harnessToolStepReceiptObjectDigest",
        "harnessToolStepObservationObjectDigest",
        "harnessRunSnapshotObjectDigest",
        "harnessRunStateObjectDigest",
        "activeHarnessProviderCallObjectDigest",
        "harnessRunRecoveryAssessmentObjectDigest",
        "harnessRunRecoveryResolvedProviderCallObjectDigest",
        "harnessRunAbandonmentObjectDigest",
        "completionProposalObjectDigest",
        "completionVerificationObjectDigest",
        "completionDecisionObjectDigest",
        "outcomeObjectDigest",
    }
)
_CAS_DIGEST_LIST_KEYS = frozenset({"toolObservationObjectDigests"})
_SEMANTIC_DIGEST_OBJECT_PAIRS = {
    "outcomeDigest": "outcomeObjectDigest",
    "verificationDigest": "completionVerificationObjectDigest",
}
_PROVIDER_HEAD_FIELDS = frozenset(
    {
        "activeHarnessProviderCallDigest",
        "activeHarnessProviderCallObjectDigest",
        "activeHarnessProviderCallId",
        "activeHarnessProviderCallStatus",
        "activeHarnessProviderCallExpiresAtMs",
        "activeHarnessProviderCallGeneration",
    }
)
_PROVIDER_EVENT_STATUSES = {
    HARNESS_PROVIDER_CALL_CLAIMED: HarnessProviderCallStatus.CLAIMED,
    HARNESS_PROVIDER_CALL_SUPERSEDED: HarnessProviderCallStatus.CLAIMED,
    HARNESS_PROVIDER_CALL_DISPATCHING: HarnessProviderCallStatus.DISPATCHING,
    HARNESS_PROVIDER_CALL_COMPLETED: HarnessProviderCallStatus.COMPLETED,
    HARNESS_PROVIDER_CALL_FAILED: HarnessProviderCallStatus.FAILED,
    HARNESS_PROVIDER_CALL_UNKNOWN: HarnessProviderCallStatus.UNKNOWN,
}
_PROVIDER_CLEAR_EVENTS = frozenset(
    {
        HARNESS_RUN_RECORDED,
        HARNESS_RUN_SNAPSHOT_RECORDED,
        HARNESS_TOOL_STEP_PREPARED,
    }
)


@dataclass(frozen=True, slots=True)
class HistoryValidation:
    events: int
    task_streams: int
    semantic_references: int
    semantic_link_checks: int
    provider_semantic_link_checks: int

    def to_dict(self) -> dict[str, int]:
        return {
            "events": self.events,
            "taskStreams": self.task_streams,
            "semanticReferences": self.semantic_references,
            "semanticLinkChecks": self.semantic_link_checks,
            "providerSemanticLinkChecks": self.provider_semantic_link_checks,
        }


@dataclass(frozen=True, slots=True)
class _HistoricalProviderHead:
    record: HarnessProviderCallRecord
    record_object_digest: str
    state: HarnessRunState
    failure: HarnessProviderCallFailureReceipt | None


def validate_history(storage: HostStorage) -> HistoryValidation:
    """Validate every historical Event payload and known semantic cross-link."""
    exact_start = storage.journal.event_object_refs_start_sequence()
    admitted = {item.digest for item in storage.journal.legacy_object_refs()}
    rows = storage.journal.connection.execute(
        "SELECT sequence, event_id, stream_id, stream_kind, stream_revision, "
        "event_kind, payload_digest, recorded_at_ms FROM events ORDER BY sequence"
    )
    events = 0
    task_streams: set[str] = set()
    semantic_references = 0
    semantic_link_checks = 0
    provider_semantic_link_checks = 0
    provider_heads: dict[str, _HistoricalProviderHead] = {}
    recovery_provider_resolutions: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        events += 1
        sequence = int(row["sequence"])
        event_id = str(row["event_id"])
        stream_id = str(row["stream_id"])
        event_references: set[str] | None = None
        if sequence >= exact_start:
            edges = storage.journal.event_object_references(event_id)
            payload_edges = {item.digest for item in edges if item.role == "payload"}
            if payload_edges != {str(row["payload_digest"])}:
                raise JournalCorruption(
                    f"historical Event payload edge differs: {event_id}"
                )
            event_references = {
                item.digest for item in edges if item.role == "reference"
            }
            admitted.update(payload_edges)
            admitted.update(event_references)
        if row["stream_kind"] != "task":
            raise JournalCorruption(
                f"unsupported historical stream kind at {event_id}: {row['stream_kind']}"
            )
        task_streams.add(stream_id)
        value = storage.objects.get(
            str(row["payload_digest"]), expected_kind="host-event-payload"
        )
        if not isinstance(value, dict) or set(value) != _EVENT_FIELDS:
            raise ObjectCorrupt(f"historical Event payload fields differ: {event_id}")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.host-task-event":
            raise ObjectCorrupt(f"historical Event payload version differs: {event_id}")
        try:
            event_kind = EventKind(str(value["eventKind"]))
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical Event kind is invalid: {event_id}"
            ) from error
        if event_kind.value != row["event_kind"]:
            raise JournalCorruption(
                f"historical Event kind differs from row: {event_id}"
            )
        raw_projection = value["projection"]
        if not isinstance(raw_projection, dict):
            raise ObjectCorrupt(
                f"historical Event projection is not an object: {event_id}"
            )
        try:
            projection = TaskProjection.from_dict(raw_projection)
        except (TypeError, ValueError) as error:
            raise ObjectCorrupt(
                f"historical Event projection is invalid: {event_id}"
            ) from error
        if (
            projection.task_id != stream_id
            or projection.revision != int(row["stream_revision"])
            or projection.updated_at_ms != int(row["recorded_at_ms"])
        ):
            raise JournalCorruption(
                f"historical Event projection differs from row: {event_id}"
            )
        data = value["data"]
        validate_json_value(data)
        _require_event_owned_evidence(
            data,
            event_id=event_id,
            event_kind=event_kind,
            event_references=event_references,
        )
        references = _known_references(data)
        semantic_references += len(references)
        for key, digest in references:
            if digest not in admitted:
                raise JournalCorruption(
                    f"historical {key} is not admitted in object_refs: {event_id}"
                )
        semantic_link_checks += _validate_semantic_links(
            storage, data, event_id
        )
        semantic_link_checks += _validate_completion_semantic_links(
            storage,
            data=data,
            event_id=event_id,
            event_kind=event_kind,
            projection=projection,
        )
        provider_checks, provider_head = _validate_provider_semantic_links(
            storage,
            admitted=admitted,
            event_references=event_references,
            data=data,
            event_id=event_id,
            event_kind=event_kind,
            stream_id=stream_id,
            previous=provider_heads.get(stream_id),
        )
        provider_semantic_link_checks += provider_checks
        semantic_link_checks += provider_checks
        if provider_head is None:
            provider_heads.pop(stream_id, None)
        else:
            provider_heads[stream_id] = provider_head
        resolution_checks, resolution = _validate_recovery_provider_resolution(
            storage,
            admitted=admitted,
            data=data,
            event_id=event_id,
            event_kind=event_kind,
            provider_head=provider_head,
            previous=recovery_provider_resolutions.get(stream_id),
        )
        semantic_link_checks += resolution_checks
        provider_semantic_link_checks += resolution_checks
        if resolution is None:
            recovery_provider_resolutions.pop(stream_id, None)
        else:
            recovery_provider_resolutions[stream_id] = resolution
    return HistoryValidation(
        events=events,
        task_streams=len(task_streams),
        semantic_references=semantic_references,
        semantic_link_checks=semantic_link_checks,
        provider_semantic_link_checks=provider_semantic_link_checks,
    )


def _known_references(value: JsonValue) -> tuple[tuple[str, str], ...]:
    found: list[tuple[str, str]] = []

    def visit(current: JsonValue) -> None:
        if isinstance(current, dict):
            for key, item in current.items():
                paired_object_key = _SEMANTIC_DIGEST_OBJECT_PAIRS.get(key)
                paired_object_digest = (
                    None
                    if paired_object_key is None
                    else current.get(paired_object_key)
                )
                if (
                    key in _CAS_DIGEST_KEYS
                    and isinstance(item, str)
                    and not isinstance(paired_object_digest, str)
                ):
                    found.append((key, item))
                if key in _CAS_DIGEST_LIST_KEYS and isinstance(item, list):
                    for digest in item:
                        if isinstance(digest, str):
                            found.append((key, digest))
                if isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    visit(item)

    visit(value)
    return tuple(found)


def _require_event_owned_evidence(
    data: JsonValue,
    *,
    event_id: str,
    event_kind: EventKind,
    event_references: set[str] | None,
) -> None:
    if event_references is None or not isinstance(data, dict):
        return
    required: dict[str, str] = {}
    if event_kind is HARNESS_TOOL_STEP_PREPARED:
        for label, key in (
            ("Tool Intent", "harnessToolStepIntentObjectDigest"),
            ("Dispatch Fence", "harnessDispatchFenceObjectDigest"),
            ("Run Snapshot", "harnessRunSnapshotObjectDigest"),
            ("Run state", "harnessRunStateObjectDigest"),
        ):
            value = data.get(key)
            if isinstance(value, str):
                required[label] = value
    elif event_kind is HARNESS_TOOL_STEP_RECORDED:
        for label, key in (
            ("Tool Receipt", "harnessToolStepReceiptObjectDigest"),
            ("Tool Observation", "harnessToolStepObservationObjectDigest"),
            ("previous Tool Receipt", "harnessToolStepPreviousReceiptObjectDigest"),
        ):
            value = data.get(key)
            if isinstance(value, str):
                required[label] = value
    elif event_kind is HARNESS_RUN_SNAPSHOT_RECORDED:
        for label, key in (
            ("Run Snapshot", "harnessRunSnapshotObjectDigest"),
            ("Run state", "harnessRunStateObjectDigest"),
        ):
            value = data.get(key)
            if isinstance(value, str):
                required[label] = value
    elif event_kind is HARNESS_RUN_RECORDED:
        for label, key in (
            ("Run Receipt", "harnessRunObjectDigest"),
            ("Run Trace", "harnessTraceObjectDigest"),
            ("Run Conclusion", "runConclusionObjectDigest"),
        ):
            value = data.get(key)
            if isinstance(value, str):
                required[label] = value
        observations = data.get("toolObservationObjectDigests", [])
        if isinstance(observations, list):
            for index, value in enumerate(observations):
                if isinstance(value, str):
                    required[f"Run Observation {index}"] = value
    elif event_kind is COMPLETION_PROPOSED:
        value = data.get("completionProposalObjectDigest")
        if isinstance(value, str):
            required["Completion Proposal"] = value
    elif event_kind is COMPLETION_DECIDED:
        for label, key in (
            ("Completion Proposal", "completionProposalObjectDigest"),
            ("Completion Verification", "completionVerificationObjectDigest"),
            ("Completion Decision", "completionDecisionObjectDigest"),
            ("Task Outcome", "outcomeObjectDigest"),
        ):
            value = data.get(key)
            if isinstance(value, str):
                required[label] = value
    _require_exact_event_references(
        event_references, required, event_id=event_id
    )


def _require_exact_event_references(
    event_references: set[str],
    required: dict[str, str],
    *,
    event_id: str,
) -> None:
    for label, digest in required.items():
        if digest not in event_references:
            raise JournalCorruption(
                f"historical {label} is not admitted by its Event: {event_id}"
            )


def _validate_provider_semantic_links(
    storage: HostStorage,
    *,
    admitted: set[str],
    event_references: set[str] | None,
    data: JsonValue,
    event_id: str,
    event_kind: EventKind,
    stream_id: str,
    previous: _HistoricalProviderHead | None,
) -> tuple[int, _HistoricalProviderHead | None]:
    if not isinstance(data, dict):
        return 0, None
    present_head_fields = _PROVIDER_HEAD_FIELDS.intersection(data)
    provider_event = event_kind in _PROVIDER_EVENT_STATUSES
    if present_head_fields and present_head_fields != _PROVIDER_HEAD_FIELDS:
        raise JournalCorruption(
            f"historical Harness Provider Call head fields are incomplete: {event_id}"
        )
    if not present_head_fields:
        if provider_event:
            raise JournalCorruption(
                f"historical Provider lifecycle Event omitted its active head: {event_id}"
            )
        if previous is not None:
            allowed_statuses = {
                HARNESS_RUN_SNAPSHOT_RECORDED: {
                    HarnessProviderCallStatus.COMPLETED
                },
                HARNESS_TOOL_STEP_PREPARED: {
                    HarnessProviderCallStatus.COMPLETED
                },
                HARNESS_RUN_RECORDED: {
                    HarnessProviderCallStatus.COMPLETED,
                    HarnessProviderCallStatus.FAILED,
                    HarnessProviderCallStatus.UNKNOWN,
                },
            }.get(event_kind)
            if (
                event_kind not in _PROVIDER_CLEAR_EVENTS
                or allowed_statuses is None
                or previous.record.status not in allowed_statuses
                or (
                    event_kind is HARNESS_RUN_RECORDED
                    and previous.record.status
                    is HarnessProviderCallStatus.UNKNOWN
                    and data.get("harnessRunTerminationCode")
                    not in {"provider_state_unknown", "cancel_unknown"}
                )
            ):
                raise JournalCorruption(
                    f"historical Event illegally cleared an active Provider Call: {event_id}"
                )
        return 0, None

    record_object_digest = data["activeHarnessProviderCallObjectDigest"]
    if not isinstance(record_object_digest, str):
        raise JournalCorruption(
            f"historical Harness Provider Call object reference is invalid: {event_id}"
        )
    _require_provider_object_admitted(
        admitted,
        record_object_digest,
        "Provider Call Record",
        event_id,
    )
    raw_record = storage.objects.get(
        record_object_digest,
        expected_kind="harness-provider-call-record",
    )
    if not isinstance(raw_record, dict):
        raise ObjectCorrupt(
            f"historical Harness Provider Call Record is not an object: {event_id}"
        )
    try:
        record = HarnessProviderCallRecord.from_dict(raw_record)
    except (TypeError, ValueError) as error:
        raise ObjectCorrupt(
            f"historical Harness Provider Call Record is invalid: {event_id}"
        ) from error
    expected_head: dict[str, JsonValue] = {
        "activeHarnessProviderCallDigest": record.digest,
        "activeHarnessProviderCallObjectDigest": record_object_digest,
        "activeHarnessProviderCallId": record.provider_call_id,
        "activeHarnessProviderCallStatus": record.status.value,
        "activeHarnessProviderCallExpiresAtMs": record.expires_at_ms,
        "activeHarnessProviderCallGeneration": record.claim_generation,
    }
    if any(data.get(field) != value for field, value in expected_head.items()):
        raise JournalCorruption(
            f"historical Harness Provider Call head differs from its Record: {event_id}"
        )
    if provider_event and event_references is not None:
        required_provider_objects = {
            "Provider Call Record": record_object_digest,
            "Provider Call state": record.state_object_digest,
        }
        if record.status is HarnessProviderCallStatus.COMPLETED:
            assert record.result_object_digest is not None
            required_provider_objects["Provider Call result"] = (
                record.result_object_digest
            )
        elif record.status in {
            HarnessProviderCallStatus.FAILED,
            HarnessProviderCallStatus.UNKNOWN,
        }:
            assert record.failure_object_digest is not None
            required_provider_objects["Provider Call failure"] = (
                record.failure_object_digest
            )
        _require_exact_event_references(
            event_references,
            required_provider_objects,
            event_id=event_id,
        )

    assignment_object_digest = data.get("assignmentObjectDigest")
    native_object_digest = data.get("nativeHarnessRunContractObjectDigest")
    if not isinstance(assignment_object_digest, str) or not isinstance(
        native_object_digest, str
    ):
        raise JournalCorruption(
            f"historical Harness Provider Call has no native Assignment: {event_id}"
        )
    raw_assignment = storage.objects.get(
        assignment_object_digest,
        expected_kind="harness-assignment",
    )
    raw_native = storage.objects.get(
        native_object_digest,
        expected_kind="native-harness-run-contract",
    )
    if not isinstance(raw_assignment, dict) or not isinstance(raw_native, dict):
        raise ObjectCorrupt(
            f"historical Harness Provider Call Assignment is invalid: {event_id}"
        )
    try:
        assignment = HarnessAssignment.from_dict(raw_assignment)
        native = NativeHarnessRunContract.from_dict(raw_native)
    except (TypeError, ValueError) as error:
        raise ObjectCorrupt(
            f"historical Harness Provider Call Assignment is invalid: {event_id}"
        ) from error
    if (
        record.task_id != stream_id
        or record.task_id != assignment.task_id
        or record.harness_run_id != native.harness_run_id
        or record.harness_run_id != data.get("harnessRunId")
        or record.assignment_id != assignment.assignment_id
        or record.assignment_generation != assignment.generation
        or record.assignment_digest != assignment.digest
        or data.get("assignmentDigest") != assignment.digest
    ):
        raise JournalCorruption(
            f"historical Harness Provider Call identities differ: {event_id}"
        )

    _require_provider_object_admitted(
        admitted,
        record.source_object_digest,
        "Provider Call source",
        event_id,
    )
    if record.source_kind is HarnessProviderCallSource.ASSIGNMENT:
        if (
            record.source_digest != assignment.digest
            or record.source_object_digest != assignment_object_digest
        ):
            raise JournalCorruption(
                f"historical Provider Call Assignment source differs: {event_id}"
            )
    else:
        snapshot_object_digest = data.get("harnessRunSnapshotObjectDigest")
        if not isinstance(snapshot_object_digest, str):
            raise JournalCorruption(
                f"historical Provider Call Snapshot source is missing: {event_id}"
            )
        raw_snapshot = storage.objects.get(
            snapshot_object_digest,
            expected_kind="harness-run-snapshot",
        )
        if not isinstance(raw_snapshot, dict):
            raise ObjectCorrupt(
                f"historical Provider Call Snapshot source is invalid: {event_id}"
            )
        try:
            snapshot = HarnessRunSnapshot.from_dict(raw_snapshot)
        except (TypeError, ValueError) as error:
            raise ObjectCorrupt(
                f"historical Provider Call Snapshot source is invalid: {event_id}"
            ) from error
        if (
            record.source_digest != snapshot.digest
            or record.source_object_digest != snapshot_object_digest
            or data.get("harnessRunSnapshotDigest") != snapshot.digest
            or snapshot.harness_run_id != record.harness_run_id
            or snapshot.assignment_digest != record.assignment_digest
        ):
            raise JournalCorruption(
                f"historical Provider Call Snapshot source differs: {event_id}"
            )

    _require_provider_object_admitted(
        admitted,
        record.state_object_digest,
        "Provider Call state",
        event_id,
    )
    storage.objects.get(
        record.state_object_digest,
        expected_kind="harness-run-state",
    )
    try:
        provider_state = load_state_object(
            storage.objects,
            record.state_object_digest,
            harness_run_id=record.harness_run_id,
        )
    except (TypeError, ValueError) as error:
        raise ObjectCorrupt(
            f"historical Provider Call state is invalid: {event_id}"
        ) from error
    assignment_max_model_calls = assignment.budget.get("maxModelCalls")
    remaining_model_calls = provider_state.remaining_budget.get("modelCalls")
    if (
        provider_state.requested_model_id != record.requested_model_id
        or not _active_time_budget_is_consistent(assignment, provider_state)
        or type(assignment_max_model_calls) is not int
        or type(remaining_model_calls) is not int
        or assignment_max_model_calls - remaining_model_calls + 1
        != record.turn_sequence
    ):
        raise JournalCorruption(
            f"historical Provider Call saved Run state differs: {event_id}"
        )

    failure: HarnessProviderCallFailureReceipt | None = None
    outcome_checks = 0
    if record.status is HarnessProviderCallStatus.COMPLETED:
        assert record.result_digest is not None
        assert record.result_object_digest is not None
        _require_provider_object_admitted(
            admitted,
            record.result_object_digest,
            "Provider Call result",
            event_id,
        )
        raw_result = storage.objects.get(
            record.result_object_digest,
            expected_kind="agent-turn-result",
        )
        if not isinstance(raw_result, dict):
            raise ObjectCorrupt(
                f"historical Provider Call result is not an object: {event_id}"
            )
        try:
            result = AgentTurnResult.from_dict(raw_result)
        except (TypeError, ValueError) as error:
            raise ObjectCorrupt(
                f"historical Provider Call result is invalid: {event_id}"
            ) from error
        if result.digest != record.result_digest:
            raise JournalCorruption(
                f"historical Provider Call result digest differs: {event_id}"
            )
        outcome_checks = 1
    elif record.status in {
        HarnessProviderCallStatus.FAILED,
        HarnessProviderCallStatus.UNKNOWN,
    }:
        assert record.failure_digest is not None
        assert record.failure_object_digest is not None
        _require_provider_object_admitted(
            admitted,
            record.failure_object_digest,
            "Provider Call failure",
            event_id,
        )
        raw_failure = storage.objects.get(
            record.failure_object_digest,
            expected_kind="harness-provider-call-failure",
        )
        if not isinstance(raw_failure, dict):
            raise ObjectCorrupt(
                f"historical Provider Call failure is not an object: {event_id}"
            )
        try:
            failure = HarnessProviderCallFailureReceipt.from_dict(raw_failure)
        except (TypeError, ValueError) as error:
            raise ObjectCorrupt(
                f"historical Provider Call failure is invalid: {event_id}"
            ) from error
        if (
            failure.digest != record.failure_digest
            or failure.provider_call_id != record.provider_call_id
            or failure.request_digest != record.request_digest
            or failure.provider_request_digest != record.provider_request_digest
            or (
                record.status is HarnessProviderCallStatus.UNKNOWN
                and failure.dispatch_safety != "dispatch_ambiguous"
            )
            or (
                record.status is HarnessProviderCallStatus.FAILED
                and failure.dispatch_safety == "dispatch_ambiguous"
            )
        ):
            raise JournalCorruption(
                f"historical Provider Call failure digest differs: {event_id}"
            )
        outcome_checks = 1

    current = _HistoricalProviderHead(
        record,
        record_object_digest,
        provider_state,
        failure,
    )
    transition_checks = _validate_provider_transition(
        event_id=event_id,
        event_kind=event_kind,
        previous=previous,
        current=current,
    )
    return 4 + outcome_checks + transition_checks, current



_RECOVERY_PROVIDER_RESOLUTION_FIELDS = frozenset(
    {
        "harnessRunRecoveryResolvedProviderCallDigest",
        "harnessRunRecoveryResolvedProviderCallObjectDigest",
        "harnessRunRecoveryResolvedPreviousProviderCallDigest",
    }
)


def _validate_recovery_provider_resolution(
    storage: HostStorage,
    *,
    admitted: set[str],
    data: JsonValue,
    event_id: str,
    event_kind: EventKind,
    provider_head: _HistoricalProviderHead | None,
    previous: tuple[str, str, str] | None,
) -> tuple[int, tuple[str, str, str] | None]:
    if not isinstance(data, dict):
        return 0, None
    present = _RECOVERY_PROVIDER_RESOLUTION_FIELDS.intersection(data)
    if present and present != _RECOVERY_PROVIDER_RESOLUTION_FIELDS:
        raise JournalCorruption(
            f"historical Recovery Provider resolution is incomplete: {event_id}"
        )
    if not present:
        if previous is not None and event_kind is not HARNESS_RUN_RECORDED:
            raise JournalCorruption(
                f"historical Event cleared Recovery Provider resolution: {event_id}"
            )
        return 0, None

    resolved_digest = data["harnessRunRecoveryResolvedProviderCallDigest"]
    resolved_object_digest = data[
        "harnessRunRecoveryResolvedProviderCallObjectDigest"
    ]
    previous_digest = data[
        "harnessRunRecoveryResolvedPreviousProviderCallDigest"
    ]
    if not all(
        isinstance(value, str)
        for value in (resolved_digest, resolved_object_digest, previous_digest)
    ):
        raise JournalCorruption(
            f"historical Recovery Provider resolution is invalid: {event_id}"
        )
    _require_provider_object_admitted(
        admitted,
        resolved_object_digest,
        "Recovery-resolved Provider Call Record",
        event_id,
    )
    raw_record = storage.objects.get(
        resolved_object_digest,
        expected_kind="harness-provider-call-record",
    )
    if not isinstance(raw_record, dict):
        raise ObjectCorrupt(
            f"historical Recovery-resolved Provider Call is not an object: {event_id}"
        )
    try:
        record = HarnessProviderCallRecord.from_dict(raw_record)
    except (TypeError, ValueError) as error:
        raise ObjectCorrupt(
            f"historical Recovery-resolved Provider Call is invalid: {event_id}"
        ) from error
    recovery_object_digest = data.get("harnessRunRecoveryAssessmentObjectDigest")
    if not isinstance(recovery_object_digest, str):
        raise JournalCorruption(
            f"historical Recovery Provider resolution has no Recovery: {event_id}"
        )
    raw_recovery = storage.objects.get(
        recovery_object_digest,
        expected_kind="native-run-recovery-assessment",
    )
    if not isinstance(raw_recovery, dict):
        raise ObjectCorrupt(
            f"historical Recovery Provider resolution Recovery is invalid: {event_id}"
        )
    try:
        recovery = NativeRunRecoveryAssessment.from_dict(raw_recovery)
    except (TypeError, ValueError) as error:
        raise ObjectCorrupt(
            f"historical Recovery Provider resolution Recovery is invalid: {event_id}"
        ) from error
    evidence = recovery.workspace_evidence.get("providerCallReconciliation")
    resolution = (resolved_digest, resolved_object_digest, previous_digest)
    if (
        record.digest != resolved_digest
        or record.previous_record_digest != previous_digest
        or record.status
        not in {
            HarnessProviderCallStatus.COMPLETED,
            HarnessProviderCallStatus.FAILED,
            HarnessProviderCallStatus.UNKNOWN,
        }
        or not isinstance(evidence, dict)
        or evidence.get("status") != "dispatching"
        or evidence.get("recordDigest") != previous_digest
        or evidence.get("providerCallId") != record.provider_call_id
        or evidence.get("claimGeneration") != record.claim_generation
        or evidence.get("sourceKind") != record.source_kind.value
        or evidence.get("sourceDigest") != record.source_digest
        or evidence.get("sourceObjectDigest") != record.source_object_digest
        or recovery.assignment_id != record.assignment_id
        or recovery.assignment_generation != record.assignment_generation
        or recovery.assignment_digest != record.assignment_digest
        or recovery.harness_run_id != record.harness_run_id
    ):
        raise JournalCorruption(
            f"historical Recovery Provider resolution identities differ: {event_id}"
        )
    if previous is None:
        if (
            event_kind
            not in {
                HARNESS_PROVIDER_CALL_COMPLETED,
                HARNESS_PROVIDER_CALL_FAILED,
                HARNESS_PROVIDER_CALL_UNKNOWN,
            }
            or provider_head is None
            or provider_head.record != record
            or provider_head.record_object_digest != resolved_object_digest
        ):
            raise JournalCorruption(
                f"historical Recovery Provider resolution was not introduced by "
                f"its terminal Provider Event: {event_id}"
            )
    elif resolution != previous:
        raise JournalCorruption(
            f"historical Recovery Provider resolution changed: {event_id}"
        )
    return 2, resolution

def _require_provider_object_admitted(
    admitted: set[str],
    digest: str,
    label: str,
    event_id: str,
) -> None:
    if digest not in admitted:
        raise JournalCorruption(
            f"historical {label} is not admitted in object_refs: {event_id}"
        )


def _validate_provider_transition(
    *,
    event_id: str,
    event_kind: EventKind,
    previous: _HistoricalProviderHead | None,
    current: _HistoricalProviderHead,
) -> int:
    record = current.record
    expected_status = _PROVIDER_EVENT_STATUSES.get(event_kind)
    if expected_status is None:
        if previous is None:
            raise JournalCorruption(
                f"historical Event introduced a Provider Call head: {event_id}"
            )
        if (
            current.record != previous.record
            or current.record_object_digest != previous.record_object_digest
        ):
            raise JournalCorruption(
                f"historical non-Provider Event changed the Provider Call head: {event_id}"
            )
        return 1
    if record.status is not expected_status:
        raise JournalCorruption(
            f"historical Provider lifecycle Event status differs: {event_id}"
        )
    if previous is None:
        if (
            event_kind is not HARNESS_PROVIDER_CALL_CLAIMED
            or record.claim_generation != 1
            or record.previous_record_digest is not None
        ):
            raise JournalCorruption(
                f"historical Provider Call chain has an invalid root: {event_id}"
            )
        return 1
    if record.previous_record_digest != previous.record.digest:
        raise JournalCorruption(
            f"historical Provider Call predecessor digest differs: {event_id}"
        )

    prior = previous.record
    if event_kind is HARNESS_PROVIDER_CALL_CLAIMED:
        if (
            prior.status is not HarnessProviderCallStatus.COMPLETED
            or record.provider_call_id == prior.provider_call_id
            or record.claim_generation != 1
            or record.turn_sequence != prior.turn_sequence + 1
            or not _same_provider_source(prior, record)
            or not _same_provider_assignment(prior, record)
            or record.adapter_id != prior.adapter_id
            or record.requested_model_id != prior.requested_model_id
            or record.recorded_at_ms < prior.recorded_at_ms
            or not _provider_time_is_monotonic(previous.state, current.state)
        ):
            raise JournalCorruption(
                f"historical next-turn Provider Call transition differs: {event_id}"
            )
        return 1
    if event_kind is HARNESS_PROVIDER_CALL_SUPERSEDED:
        safe_failure_retry = (
            prior.status is HarnessProviderCallStatus.FAILED
            and previous.failure is not None
            and previous.failure.dispatch_safety == "pre_dispatch_safe"
            and _valid_safe_retry_state(previous.state, current.state)
        )
        expired_claim = (
            prior.status is HarnessProviderCallStatus.CLAIMED
            and record.issued_at_ms > prior.expires_at_ms
            and record.holder_id != prior.holder_id
            and _valid_provider_outcome_state(previous.state, current.state)
        )
        if (
            not (safe_failure_retry or expired_claim)
            or not _same_provider_attempt(prior, record)
            or record.claim_generation != prior.claim_generation + 1
            or record.recorded_at_ms < prior.recorded_at_ms
        ):
            raise JournalCorruption(
                f"historical Provider Call supersession differs: {event_id}"
            )
        return 1
    if event_kind is HARNESS_PROVIDER_CALL_DISPATCHING:
        if (
            prior.status is not HarnessProviderCallStatus.CLAIMED
            or not _same_provider_generation_identity(prior, record)
            or not _valid_provider_outcome_state(previous.state, current.state)
        ):
            raise JournalCorruption(
                f"historical Provider Call dispatch transition differs: {event_id}"
            )
        return 1
    if event_kind in {
        HARNESS_PROVIDER_CALL_COMPLETED,
        HARNESS_PROVIDER_CALL_FAILED,
        HARNESS_PROVIDER_CALL_UNKNOWN,
    }:
        dispatched_outcome = (
            prior.status is HarnessProviderCallStatus.DISPATCHING
        )
        safe_pre_dispatch_failure = (
            event_kind is HARNESS_PROVIDER_CALL_FAILED
            and prior.status is HarnessProviderCallStatus.CLAIMED
            and current.failure is not None
            and current.failure.dispatch_safety == "pre_dispatch_safe"
        )
        if (
            not (dispatched_outcome or safe_pre_dispatch_failure)
            or not _same_provider_generation_identity(prior, record)
            or not _valid_provider_outcome_state(previous.state, current.state)
        ):
            raise JournalCorruption(
                f"historical Provider Call outcome transition differs: {event_id}"
            )
        return 1
    raise JournalCorruption(
        f"historical Provider lifecycle Event is unsupported: {event_id}"
    )


def _same_provider_assignment(
    previous: HarnessProviderCallRecord,
    current: HarnessProviderCallRecord,
) -> bool:
    return (
        previous.task_id == current.task_id
        and previous.harness_run_id == current.harness_run_id
        and previous.assignment_id == current.assignment_id
        and previous.assignment_generation == current.assignment_generation
        and previous.assignment_digest == current.assignment_digest
    )


def _same_provider_source(
    previous: HarnessProviderCallRecord,
    current: HarnessProviderCallRecord,
) -> bool:
    return (
        previous.source_kind is current.source_kind
        and previous.source_digest == current.source_digest
        and previous.source_object_digest == current.source_object_digest
    )


def _same_provider_attempt(
    previous: HarnessProviderCallRecord,
    current: HarnessProviderCallRecord,
) -> bool:
    return (
        _same_provider_assignment(previous, current)
        and _same_provider_source(previous, current)
        and previous.provider_call_id == current.provider_call_id
        and previous.turn_id == current.turn_id
        and previous.turn_sequence == current.turn_sequence
        and previous.request_digest == current.request_digest
        and previous.provider_request_digest == current.provider_request_digest
        and previous.adapter_id == current.adapter_id
        and previous.requested_model_id == current.requested_model_id
    )


def _same_provider_generation(
    previous: HarnessProviderCallRecord,
    current: HarnessProviderCallRecord,
) -> bool:
    return (
        _same_provider_generation_identity(previous, current)
        and previous.state_object_digest == current.state_object_digest
    )


def _same_provider_generation_identity(
    previous: HarnessProviderCallRecord,
    current: HarnessProviderCallRecord,
) -> bool:
    return (
        _same_provider_attempt(previous, current)
        and previous.holder_id == current.holder_id
        and previous.claim_generation == current.claim_generation
        and previous.issued_at_ms == current.issued_at_ms
        and previous.expires_at_ms == current.expires_at_ms
        and current.recorded_at_ms >= previous.recorded_at_ms
    )


def _valid_safe_retry_state(
    previous: HarnessRunState,
    current: HarnessRunState,
) -> bool:
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
        or not _provider_time_is_monotonic(previous, current)
    ):
        return False
    previous_retries = previous.remaining_budget.get("modelRetries")
    current_retries = current.remaining_budget.get("modelRetries")
    if (
        type(previous_retries) is not int
        or type(current_retries) is not int
        or current_retries != previous_retries - 1
    ):
        return False
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
                return False
        elif current_value != previous_value:
            return False
    return True


def _valid_provider_outcome_state(
    previous: HarnessRunState,
    current: HarnessRunState,
) -> bool:
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
        or not _provider_time_is_monotonic(previous, current)
    ):
        return False
    for field, previous_value in previous.remaining_budget.items():
        current_value = current.remaining_budget[field]
        if field == "wallTimeMs":
            if (
                type(previous_value) is not int
                or type(current_value) is not int
                or current_value > previous_value
            ):
                return False
        elif current_value != previous_value:
            return False
    return True


def _provider_time_is_monotonic(
    previous: HarnessRunState,
    current: HarnessRunState,
) -> bool:
    previous_elapsed = previous.active_elapsed_ms
    current_elapsed = current.active_elapsed_ms
    if previous_elapsed is not None and (
        current_elapsed is None or current_elapsed < previous_elapsed
    ):
        return False
    previous_wall = previous.remaining_budget.get("wallTimeMs")
    current_wall = current.remaining_budget.get("wallTimeMs")
    return (
        type(previous_wall) is int
        and type(current_wall) is int
        and current_wall <= previous_wall
    )


def _active_time_budget_is_consistent(
    assignment: HarnessAssignment,
    state: HarnessRunState,
) -> bool:
    if state.active_elapsed_ms is None:
        return True
    max_wall_time_ms = assignment.budget.get("maxWallTimeMs")
    if max_wall_time_ms is None:
        return True
    remaining_wall_time_ms = state.remaining_budget.get("wallTimeMs")
    return (
        type(max_wall_time_ms) is int
        and max_wall_time_ms >= 1
        and type(remaining_wall_time_ms) is int
        and remaining_wall_time_ms
        == max(0, max_wall_time_ms - state.active_elapsed_ms)
    )


def _validate_completion_semantic_links(
    storage: HostStorage,
    *,
    data: JsonValue,
    event_id: str,
    event_kind: EventKind,
    projection: TaskProjection,
) -> int:
    if not isinstance(data, dict):
        return 0
    proposal_object_digest = data.get("completionProposalObjectDigest")
    proposal_digest = data.get("completionProposalDigest")
    proposal_id = data.get("completionProposalId")
    proposal_fields = (proposal_object_digest, proposal_digest, proposal_id)
    if not any(value is not None for value in proposal_fields):
        if event_kind in {COMPLETION_PROPOSED, COMPLETION_DECIDED}:
            raise JournalCorruption(
                f"historical completion Event omitted its Proposal: {event_id}"
            )
        return 0
    if not all(isinstance(value, str) for value in proposal_fields):
        raise JournalCorruption(
            f"historical CompletionProposal references are incomplete: {event_id}"
        )
    assert isinstance(proposal_object_digest, str)
    assert isinstance(proposal_digest, str)
    assert isinstance(proposal_id, str)
    proposal = _load_history_semantic_object(
        storage,
        object_digest=proposal_object_digest,
        semantic_digest=proposal_digest,
        kind="completion-proposal",
        decoder=CompletionProposal.from_dict,
        label="CompletionProposal",
        event_id=event_id,
    )
    if (
        proposal.completion_proposal_id != proposal_id
        or proposal.task_id != projection.task_id
    ):
        raise JournalCorruption(
            f"historical CompletionProposal identities differ: {event_id}"
        )
    checks = 1

    decision_object_digest = data.get("completionDecisionObjectDigest")
    decision_digest = data.get("completionDecisionDigest")
    decision_id = data.get("completionDecisionId")
    verification_object_digest = data.get(
        "completionVerificationObjectDigest"
    )
    completion_verification_digest = data.get(
        "completionVerificationDigest"
    )
    verification_digest = data.get("verificationDigest")
    decision_fields = (
        decision_object_digest,
        decision_digest,
        decision_id,
        verification_object_digest,
        completion_verification_digest,
        verification_digest,
    )
    if not any(value is not None for value in decision_fields):
        if event_kind is COMPLETION_DECIDED:
            raise JournalCorruption(
                f"historical CompletionDecision references are missing: {event_id}"
            )
        return checks
    if not all(isinstance(value, str) for value in decision_fields):
        raise JournalCorruption(
            f"historical CompletionDecision references are incomplete: {event_id}"
        )
    assert isinstance(decision_object_digest, str)
    assert isinstance(decision_digest, str)
    assert isinstance(decision_id, str)
    assert isinstance(verification_object_digest, str)
    assert isinstance(completion_verification_digest, str)
    assert isinstance(verification_digest, str)
    verification = _load_history_semantic_object(
        storage,
        object_digest=verification_object_digest,
        semantic_digest=completion_verification_digest,
        kind="completion-verification",
        decoder=CompletionVerification.from_dict,
        label="CompletionVerification",
        event_id=event_id,
    )
    decision = _load_history_semantic_object(
        storage,
        object_digest=decision_object_digest,
        semantic_digest=decision_digest,
        kind="completion-decision",
        decoder=CompletionDecision.from_dict,
        label="CompletionDecision",
        event_id=event_id,
    )
    accepted = data.get("completionAccepted")
    reason_code = data.get("completionReasonCode")
    if (
        type(accepted) is not bool
        or not isinstance(reason_code, str)
        or verification_digest != completion_verification_digest
        or verification.digest != completion_verification_digest
        or verification.completion_proposal_id != proposal_id
        or verification.accepted is not accepted
        or decision.completion_decision_id != decision_id
        or decision.completion_proposal_id != proposal_id
        or decision.task_id != projection.task_id
        or decision.accepted is not accepted
        or decision.reason_code != reason_code
        or decision.verification_digest != verification.digest
    ):
        raise JournalCorruption(
            f"historical CompletionDecision identities differ: {event_id}"
        )
    checks += 2

    outcome_object_digest = data.get("outcomeObjectDigest")
    outcome_digest = data.get("outcomeDigest")
    if accepted:
        if not isinstance(outcome_object_digest, str) or not isinstance(
            outcome_digest, str
        ):
            raise JournalCorruption(
                f"historical accepted CompletionDecision omitted TaskOutcome: {event_id}"
            )
        outcome = _load_history_semantic_object(
            storage,
            object_digest=outcome_object_digest,
            semantic_digest=outcome_digest,
            kind="task-outcome",
            decoder=TaskOutcome.from_dict,
            label="TaskOutcome",
            event_id=event_id,
        )
        if (
            projection.state is not TaskState.COMPLETED
            or projection.ready_frontier
            or outcome.task_id != projection.task_id
            or outcome.goal_id != projection.goal_id
            or outcome.status != "completed"
            or outcome.verification_digest != verification.digest
            or outcome.artifact_refs != proposal.artifact_refs
        ):
            raise JournalCorruption(
                f"historical TaskOutcome identities differ: {event_id}"
            )
        checks += 1
    elif outcome_object_digest is not None or outcome_digest is not None:
        raise JournalCorruption(
            f"historical rejected CompletionDecision retained TaskOutcome: {event_id}"
        )
    return checks


def _load_history_semantic_object(
    storage: HostStorage,
    *,
    object_digest: str,
    semantic_digest: str,
    kind: str,
    decoder,
    label: str,
    event_id: str,
):
    raw = storage.objects.get(object_digest, expected_kind=kind)
    if not isinstance(raw, dict):
        raise ObjectCorrupt(
            f"historical {label} is not an object: {event_id}"
        )
    try:
        decoded = decoder(raw)
    except (TypeError, ValueError) as error:
        raise ObjectCorrupt(
            f"historical {label} is invalid: {event_id}"
        ) from error
    to_dict = getattr(decoded, "to_dict", None)
    if not callable(to_dict) or canonical_digest(to_dict()) != semantic_digest:
        raise JournalCorruption(
            f"historical {label} semantic digest differs: {event_id}"
        )
    return decoded


def _validate_semantic_links(
    storage: HostStorage,
    data: JsonValue,
    event_id: str,
) -> int:
    if not isinstance(data, dict):
        return 0
    effect_key = data.get("effectDigest")
    binding_key = data.get("bindingDigest")
    authority_key = data.get("authorityDecisionDigest")
    checks = 0
    assignment: HarnessAssignment | None = None
    tool_grant: ToolGrant | None = None
    tool_catalog: NativeToolCatalogSnapshot | None = None
    native_contract: NativeHarnessRunContract | None = None
    assignment_object_key = data.get("assignmentObjectDigest")
    native_object_key = data.get("nativeHarnessRunContractObjectDigest")
    if isinstance(assignment_object_key, str):
        raw_assignment = storage.objects.get(
            assignment_object_key, expected_kind="harness-assignment"
        )
        if not isinstance(raw_assignment, dict):
            raise ObjectCorrupt(
                f"historical Harness Assignment is not an object: {event_id}"
            )
        try:
            assignment = HarnessAssignment.from_dict(raw_assignment)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical Harness Assignment is invalid: {event_id}"
            ) from error
        if data.get("assignmentDigest") != assignment.digest:
            raise JournalCorruption(
                f"historical Harness Assignment digest differs: {event_id}"
            )
        checks += 1
    if isinstance(native_object_key, str):
        if assignment is None:
            raise JournalCorruption(
                f"historical native Run Contract has no Assignment: {event_id}"
            )
        raw_native = storage.objects.get(
            native_object_key, expected_kind="native-harness-run-contract"
        )
        if not isinstance(raw_native, dict):
            raise ObjectCorrupt(
                f"historical native Run Contract is not an object: {event_id}"
            )
        try:
            native_contract = NativeHarnessRunContract.from_dict(raw_native)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical native Run Contract is invalid: {event_id}"
            ) from error
        grant_object_key = data.get("toolGrantObjectDigest")
        if not isinstance(grant_object_key, str):
            raise JournalCorruption(
                f"historical native Run Contract has no Tool Grant: {event_id}"
            )
        raw_grant = storage.objects.get(grant_object_key, expected_kind="tool-grant")
        if not isinstance(raw_grant, dict):
            raise ObjectCorrupt(f"historical Tool Grant is not an object: {event_id}")
        try:
            tool_grant = ToolGrant.from_dict(raw_grant)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical Tool Grant is invalid: {event_id}"
            ) from error
        catalog_object_key = data.get("toolCatalogObjectDigest")
        if native_contract.tool_catalog_object_digest is None:
            if catalog_object_key is not None:
                raise JournalCorruption(
                    f"historical v1 native Run unexpectedly references a catalog: {event_id}"
                )
            try:
                legacy_grant_recovery_consequence(tool_grant.allowed_tools)
            except ValueError as error:
                raise JournalCorruption(
                    f"historical legacy Tool Grant is not closed: {event_id}"
                ) from error
        else:
            if (
                not isinstance(catalog_object_key, str)
                or catalog_object_key != native_contract.tool_catalog_object_digest
            ):
                raise JournalCorruption(
                    f"historical native Tool catalog reference differs: {event_id}"
                )
            raw_catalog = storage.objects.get(
                catalog_object_key, expected_kind="harness-runtime-catalog"
            )
            if not isinstance(raw_catalog, dict):
                raise ObjectCorrupt(
                    f"historical native Tool catalog is not an object: {event_id}"
                )
            try:
                tool_catalog = NativeToolCatalogSnapshot.from_dict(raw_catalog)
            except ValueError as error:
                raise ObjectCorrupt(
                    f"historical native Tool catalog is invalid: {event_id}"
                ) from error
            if tool_catalog.digest != assignment.tool_catalog_digest:
                raise JournalCorruption(
                    f"historical native Tool catalog digest differs: {event_id}"
                )
            try:
                tool_catalog.aggregate_recovery_consequence(tool_grant.allowed_tools)
            except KeyError as error:
                raise JournalCorruption(
                    f"historical Tool Grant is not covered by its catalog: {event_id}"
                ) from error
        if (
            data.get("nativeHarnessRunContractDigest") != native_contract.digest
            or data.get("harnessRunId") != native_contract.harness_run_id
            or native_contract.assignment_id != assignment.assignment_id
            or native_contract.assignment_generation != assignment.generation
            or native_contract.assignment_digest != assignment.digest
            or native_contract.harness_manifest_digest
            != assignment.harness_manifest_digest
            or native_contract.context_object_digest != assignment.context_object_digest
            or native_contract.task_contract_digest != data.get("taskContractDigest")
            or native_contract.task_contract_object_digest
            != data.get("taskContractObjectDigest")
            or native_contract.tool_catalog_digest != assignment.tool_catalog_digest
            or native_contract.tool_grant_digest != tool_grant.digest
            or data.get("toolGrantDigest") != tool_grant.digest
            or native_contract.tool_grant_object_digest != grant_object_key
        ):
            raise JournalCorruption(
                f"historical native Run Contract identities differ: {event_id}"
            )
        checks += 3 if tool_catalog is not None else 2
    tool_step_intent: HarnessToolStepIntent | None = None
    tool_step_intent_object_key = data.get("harnessToolStepIntentObjectDigest")
    if isinstance(tool_step_intent_object_key, str):
        if assignment is None or native_contract is None:
            raise JournalCorruption(
                f"historical Harness Tool Step Intent has no native Assignment: {event_id}"
            )
        raw_intent = storage.objects.get(
            tool_step_intent_object_key, expected_kind="harness-tool-step-intent"
        )
        if not isinstance(raw_intent, dict):
            raise ObjectCorrupt(
                f"historical Harness Tool Step Intent is not an object: {event_id}"
            )
        try:
            tool_step_intent = HarnessToolStepIntent.from_dict(raw_intent)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical Harness Tool Step Intent is invalid: {event_id}"
            ) from error
        if (
            data.get("harnessToolStepIntentDigest") != tool_step_intent.digest
            or tool_step_intent.harness_run_id != native_contract.harness_run_id
            or tool_step_intent.assignment_id != assignment.assignment_id
            or tool_step_intent.assignment_generation != assignment.generation
            or tool_step_intent.assignment_digest != assignment.digest
        ):
            raise JournalCorruption(
                f"historical Harness Tool Step Intent identities differ: {event_id}"
            )
        active_intent = data.get("activeHarnessToolStepIntentDigest")
        if active_intent is not None and active_intent != tool_step_intent.digest:
            raise JournalCorruption(
                f"historical active Harness Tool Step Intent differs: {event_id}"
            )
        checks += 1

    dispatch_fence_object_key = data.get("harnessDispatchFenceObjectDigest")
    dispatch_fence_digest = data.get("harnessDispatchFenceDigest")
    if dispatch_fence_object_key is not None or dispatch_fence_digest is not None:
        if (
            not isinstance(dispatch_fence_object_key, str)
            or not isinstance(dispatch_fence_digest, str)
            or tool_step_intent is None
            or assignment is None
            or native_contract is None
        ):
            raise JournalCorruption(
                f"historical Harness Dispatch Fence references are incomplete: {event_id}"
            )
        raw_fence = storage.objects.get(
            dispatch_fence_object_key, expected_kind="harness-dispatch-fence"
        )
        if not isinstance(raw_fence, dict):
            raise ObjectCorrupt(
                f"historical Harness Dispatch Fence is not an object: {event_id}"
            )
        try:
            dispatch_fence = HarnessDispatchFence.from_dict(raw_fence)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical Harness Dispatch Fence is invalid: {event_id}"
            ) from error
        if (
            dispatch_fence_digest != dispatch_fence.digest
            or dispatch_fence.task_id != assignment.task_id
            or dispatch_fence.harness_run_id != native_contract.harness_run_id
            or dispatch_fence.assignment_id != assignment.assignment_id
            or dispatch_fence.assignment_generation != assignment.generation
            or dispatch_fence.assignment_digest != assignment.digest
            or dispatch_fence.intent_digest != tool_step_intent.digest
            or dispatch_fence.runtime_operation != tool_step_intent.runtime_operation
            or dispatch_fence.client_request_id != tool_step_intent.client_request_id
        ):
            raise JournalCorruption(
                f"historical Harness Dispatch Fence identities differ: {event_id}"
            )
        checks += 1

    tool_step_receipt_object_key = data.get("harnessToolStepReceiptObjectDigest")
    if isinstance(tool_step_receipt_object_key, str):
        raw_receipt = storage.objects.get(
            tool_step_receipt_object_key, expected_kind="harness-tool-step-receipt"
        )
        if not isinstance(raw_receipt, dict):
            raise ObjectCorrupt(
                f"historical Harness Tool Step Receipt is not an object: {event_id}"
            )
        try:
            tool_step_receipt = HarnessToolStepReceipt.from_dict(raw_receipt)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical Harness Tool Step Receipt is invalid: {event_id}"
            ) from error
        if (
            data.get("harnessToolStepReceiptDigest") != tool_step_receipt.digest
            or native_contract is None
            or tool_step_receipt.harness_run_id != native_contract.harness_run_id
            or tool_step_intent is None
            or tool_step_receipt.intent_digest != tool_step_intent.digest
            or tool_step_receipt.tool_call_id != tool_step_intent.tool_call_id
        ):
            raise JournalCorruption(
                f"historical Harness Tool Step Receipt identities differ: {event_id}"
            )
        observation_object_key = data.get("harnessToolStepObservationObjectDigest")
        if not isinstance(observation_object_key, str):
            raise JournalCorruption(
                f"historical Harness Tool Step Receipt omitted its Observation object: {event_id}"
            )
        raw_observation = storage.objects.get(
            observation_object_key, expected_kind="harness-tool-observation"
        )
        if not isinstance(raw_observation, dict):
            raise ObjectCorrupt(
                f"historical Harness Tool Step Observation is not an object: {event_id}"
            )
        validate_json_value(raw_observation)
        if canonical_digest(raw_observation) != tool_step_receipt.observation_digest:
            raise JournalCorruption(
                f"historical Harness Tool Step Observation digest differs: {event_id}"
            )
        current_receipt_schema = "previousReceiptDigest" in raw_receipt
        previous_receipt_object_key = data.get(
            "harnessToolStepPreviousReceiptObjectDigest"
        )
        if current_receipt_schema:
            if tool_step_receipt.previous_receipt_digest is None:
                if previous_receipt_object_key is not None:
                    raise JournalCorruption(
                        f"historical initial Tool Step Receipt has a predecessor: {event_id}"
                    )
            else:
                if not isinstance(previous_receipt_object_key, str):
                    raise JournalCorruption(
                        f"historical Tool Step Receipt predecessor is missing: {event_id}"
                    )
                raw_previous_receipt = storage.objects.get(
                    previous_receipt_object_key,
                    expected_kind="harness-tool-step-receipt",
                )
                if not isinstance(raw_previous_receipt, dict):
                    raise ObjectCorrupt(
                        f"historical Tool Step Receipt predecessor is invalid: {event_id}"
                    )
                try:
                    previous_receipt = HarnessToolStepReceipt.from_dict(
                        raw_previous_receipt
                    )
                except ValueError as error:
                    raise ObjectCorrupt(
                        f"historical Tool Step Receipt predecessor is invalid: {event_id}"
                    ) from error
                if (
                    previous_receipt.digest != tool_step_receipt.previous_receipt_digest
                    or previous_receipt.intent_digest != tool_step_intent.digest
                    or previous_receipt.terminal
                ):
                    raise JournalCorruption(
                        f"historical Tool Step Receipt predecessor chain differs: {event_id}"
                    )
                checks += 1
            active_intent = data.get("activeHarnessToolStepIntentDigest")
            if tool_step_receipt.terminal:
                if active_intent is not None:
                    raise JournalCorruption(
                        f"historical terminal Tool Step retained an active Intent: {event_id}"
                    )
            elif active_intent != tool_step_intent.digest:
                raise JournalCorruption(
                    f"historical non-terminal Tool Step lost its active Intent: {event_id}"
                )
        checks += 2

    snapshot_object_key = data.get("harnessRunSnapshotObjectDigest")
    state_object_key = data.get("harnessRunStateObjectDigest")
    if isinstance(snapshot_object_key, str) or isinstance(state_object_key, str):
        if (
            not isinstance(snapshot_object_key, str)
            or not isinstance(state_object_key, str)
            or assignment is None
            or native_contract is None
        ):
            raise JournalCorruption(
                f"historical Harness Run Snapshot references are incomplete: {event_id}"
            )
        raw_snapshot = storage.objects.get(
            snapshot_object_key, expected_kind="harness-run-snapshot"
        )
        if not isinstance(raw_snapshot, dict):
            raise ObjectCorrupt(
                f"historical Harness Run Snapshot is not an object: {event_id}"
            )
        try:
            snapshot = HarnessRunSnapshot.from_dict(raw_snapshot)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical Harness Run Snapshot is invalid: {event_id}"
            ) from error
        try:
            state = load_state_object(
                storage.objects,
                state_object_key,
                harness_run_id=snapshot.harness_run_id,
            )
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical Harness Run state chain is invalid: {event_id}"
            ) from error
        if (
            data.get("harnessRunSnapshotDigest") != snapshot.digest
            or snapshot.harness_run_id != native_contract.harness_run_id
            or snapshot.assignment_id != assignment.assignment_id
            or snapshot.assignment_generation != assignment.generation
            or snapshot.assignment_digest != assignment.digest
            or snapshot.tool_catalog_digest != assignment.tool_catalog_digest
            or snapshot.messages_digest != state.messages_digest
            or snapshot.observation_digests != state.observation_digests
            or snapshot.remaining_budget != state.remaining_budget
            or snapshot.requested_model_id != state.requested_model_id
            or snapshot.effective_model_id != state.effective_model_id
            or not _active_time_budget_is_consistent(assignment, state)
        ):
            raise JournalCorruption(
                f"historical Harness Run Snapshot identities differ: {event_id}"
            )
        active_intent = data.get("activeHarnessToolStepIntentDigest")
        if (
            active_intent is not None
            and active_intent not in snapshot.active_tool_step_intent_digests
        ):
            raise JournalCorruption(
                f"historical Harness Run Snapshot active intent differs: {event_id}"
            )
        checks += 2

    effect: EffectEnvelope | None = None
    if isinstance(effect_key, str):
        raw_effect = storage.objects.get(effect_key, expected_kind="effect")
        if not isinstance(raw_effect, dict):
            raise ObjectCorrupt(f"historical Effect is not an object: {event_id}")
        try:
            effect = EffectEnvelope.from_dict(raw_effect)
        except ValueError as error:
            raise ObjectCorrupt(f"historical Effect is invalid: {event_id}") from error
        checks += 1
    if isinstance(binding_key, str):
        raw_binding = storage.objects.get(binding_key, expected_kind="effect-binding")
        if not isinstance(raw_binding, dict):
            raise ObjectCorrupt(f"historical Binding is not an object: {event_id}")
        try:
            binding = EffectBinding.from_dict(raw_binding)
        except ValueError as error:
            raise ObjectCorrupt(f"historical Binding is invalid: {event_id}") from error
        if effect is not None and (
            binding.effect_id != effect.effect_id
            or binding.effect_digest != effect_digest(effect)
        ):
            raise JournalCorruption(
                f"historical Effect and Binding identities differ: {event_id}"
            )
        checks += 1
    recovery: NativeRunRecoveryAssessment | None = None
    recovery_object_key = data.get("harnessRunRecoveryAssessmentObjectDigest")
    if isinstance(recovery_object_key, str):
        raw_recovery = storage.objects.get(
            recovery_object_key, expected_kind="native-run-recovery-assessment"
        )
        if not isinstance(raw_recovery, dict):
            raise ObjectCorrupt(
                f"historical native Run Recovery is not an object: {event_id}"
            )
        try:
            recovery = NativeRunRecoveryAssessment.from_dict(raw_recovery)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical native Run Recovery is invalid: {event_id}"
            ) from error
        if (
            data.get("harnessRunRecoveryAssessmentDigest") != recovery.digest
            or data.get("harnessRunRecoveryAssessmentId") != recovery.assessment_id
            or data.get("harnessRunRecoverySafeToAbandon")
            is not recovery.safe_to_abandon
        ):
            raise JournalCorruption(
                f"historical native Run Recovery identities differ: {event_id}"
            )
        if tool_grant is None:
            raise JournalCorruption(
                f"historical native Run Recovery has no Tool Grant: {event_id}"
            )
        expected_consequence = (
            tool_catalog.aggregate_recovery_consequence(tool_grant.allowed_tools)
            if tool_catalog is not None
            else legacy_grant_recovery_consequence(tool_grant.allowed_tools)
        )
        if recovery_consequence_from_persisted(
            recovery.grant_effect_class
        ) is not expected_consequence or recovery.unresolved_unknowns != tuple(
            dict.fromkeys(
                (
                    *recovery_unknowns(
                        expected_consequence,
                        workspace_status=recovery.workspace_status,
                    ),
                    *tuple(
                        recovery.workspace_evidence.get(
                            "toolStepUnresolvedUnknowns", []
                        )
                    ),
                    *tuple(
                        recovery.workspace_evidence.get(
                            "providerCallUnresolvedUnknowns", []
                        )
                    ),
                )
            )
        ):
            raise JournalCorruption(
                f"historical native Run Recovery semantics differ: {event_id}"
            )
        disposition = derive_native_run_disposition(
            NativeRunFacts(
                NativeRunPhase.RECOVERY_RECORDED,
                expected_consequence,
                recovery_safe_to_abandon=recovery.safe_to_abandon,
                unresolved_unknowns=recovery.unresolved_unknowns,
            )
        )
        if disposition.abandonment_allowed is not recovery.safe_to_abandon:
            raise JournalCorruption(
                f"historical native Run Recovery disposition differs: {event_id}"
            )
        checks += 2
    run_object_key = data.get("harnessRunObjectDigest")
    if isinstance(run_object_key, str) and native_contract is not None:
        if assignment is None or tool_grant is None:
            raise JournalCorruption(
                f"historical native Harness Run has incomplete Assignment: {event_id}"
            )
        raw_run = storage.objects.get(
            run_object_key, expected_kind="harness-run-receipt"
        )
        if not isinstance(raw_run, dict):
            raise ObjectCorrupt(
                f"historical native Harness Run is not an object: {event_id}"
            )
        try:
            receipt = HarnessRunReceipt.from_dict(raw_run)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical native Harness Run is invalid: {event_id}"
            ) from error
        observation_keys = data.get("toolObservationObjectDigests", [])
        if not isinstance(observation_keys, list) or any(
            not isinstance(item, str) for item in observation_keys
        ):
            raise JournalCorruption(
                f"historical native Harness Observation refs differ: {event_id}"
            )
        observations: list[dict[str, JsonValue]] = []
        for key in observation_keys:
            raw_observation = storage.objects.get(
                key, expected_kind="harness-tool-observation"
            )
            if not isinstance(raw_observation, dict):
                raise ObjectCorrupt(
                    f"historical Harness Observation is not an object: {event_id}"
                )
            observations.append(dict(raw_observation))
        if receipt.termination_code is None:
            raise JournalCorruption(
                f"historical native Harness Run omitted termination: {event_id}"
            )
        consequence = (
            tool_catalog.aggregate_recovery_consequence(tool_grant.allowed_tools)
            if tool_catalog is not None
            else legacy_grant_recovery_consequence(tool_grant.allowed_tools)
        )
        disposition = derive_native_run_disposition(
            NativeRunFacts(
                NativeRunPhase.RUN_RECORDED,
                consequence,
                termination_code=receipt.termination_code,
                has_tool_observations=bool(observations),
                has_unknown_observation=any(
                    item.get("status") == "unknown" for item in observations
                ),
                has_candidate_conclusion=(
                    receipt.termination_code == "candidate_completed"
                ),
            )
        )
        if (
            disposition.completion_route is CompletionRoute.RECONCILE_UNKNOWN
            and receipt.termination_code
            not in {
                "runtime_unknown",
                "provider_state_unknown",
                "cancel_unknown",
            }
        ):
            raise JournalCorruption(
                f"historical native Harness Run UNKNOWN termination differs: {event_id}"
            )
        if (
            data.get("harnessRunDigest") != receipt.digest
            or data.get("harnessRunId") != receipt.harness_run_id
            or data.get("harnessRunTerminationCode") != receipt.termination_code
            or data.get("harnessRunReplacementAllowed")
            is not disposition.replacement_allowed
            or receipt.assignment_id != assignment.assignment_id
            or receipt.assignment_generation != assignment.generation
            or receipt.tool_catalog_digest != assignment.tool_catalog_digest
        ):
            raise JournalCorruption(
                f"historical native Harness Run projection differs: {event_id}"
            )
        checks += 2
    abandonment_object_key = data.get("harnessRunAbandonmentObjectDigest")
    if isinstance(abandonment_object_key, str):
        raw_abandonment = storage.objects.get(
            abandonment_object_key, expected_kind="native-run-abandonment"
        )
        if not isinstance(raw_abandonment, dict):
            raise ObjectCorrupt(
                f"historical native Run Abandonment is not an object: {event_id}"
            )
        try:
            abandonment = NativeRunAbandonment.from_dict(raw_abandonment)
        except ValueError as error:
            raise ObjectCorrupt(
                f"historical native Run Abandonment is invalid: {event_id}"
            ) from error
        if recovery is None:
            raise JournalCorruption(
                f"historical native Run Abandonment has no Recovery: {event_id}"
            )
        if (
            data.get("harnessRunAbandonmentDigest") != abandonment.digest
            or data.get("harnessRunAbandonmentId") != abandonment.abandonment_id
            or abandonment.recovery_assessment_digest != recovery.digest
            or abandonment.recovery_assessment_object_digest != recovery_object_key
            or abandonment.assignment_id != recovery.assignment_id
            or abandonment.assignment_generation != recovery.assignment_generation
            or abandonment.assignment_digest != recovery.assignment_digest
            or abandonment.harness_run_id != recovery.harness_run_id
            or abandonment.reason_code != recovery.trigger
        ):
            raise JournalCorruption(
                f"historical native Run Abandonment identities differ: {event_id}"
            )
        checks += 1
    if isinstance(authority_key, str):
        authority = storage.objects.get(
            authority_key, expected_kind="capability-decision"
        )
        if not isinstance(authority, dict):
            raise ObjectCorrupt(
                f"historical CapabilityDecision is not an object: {event_id}"
            )
        expected = {
            "schemaVersion",
            "kind",
            "principalId",
            "actionId",
            "objectScope",
            "policyId",
            "allowed",
            "reason",
        }
        if (
            set(authority) != expected
            or authority.get("schemaVersion") != 1
            or authority.get("kind") != "ordivon.capability-decision"
            or authority.get("allowed") is not True
        ):
            raise ObjectCorrupt(f"historical CapabilityDecision is invalid: {event_id}")
        if effect is not None and (
            authority.get("principalId") != effect.capability.principal_id
            or authority.get("actionId") != effect.capability.action_id
            or authority.get("objectScope") != effect.capability.object_scope
        ):
            raise JournalCorruption(
                f"historical Authority and Effect identities differ: {event_id}"
            )
        checks += 1
    return checks

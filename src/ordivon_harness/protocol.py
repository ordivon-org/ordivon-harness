from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from anc_canonical import (
    JsonValue,
    canonical_digest,
    validate_digest,
    validate_json_value,
)


class HarnessProtocolError(ValueError):
    pass


class HarnessRecoveryConsequence(StrEnum):
    OBSERVATION_ONLY = "observation-only"
    WORKSPACE_CHANGE_POSSIBLE = "workspace-change-possible"
    PROCESS_OR_EXTERNAL_EFFECT_POSSIBLE = "process-or-external-effect-possible"
    UNKNOWN = "unknown"


class HarnessToolStepStatus(StrEnum):
    OBSERVED = "observed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    CANCEL_REQUESTED = "cancel-requested"
    CANCELLED = "cancelled"


class HarnessRunPauseReason(StrEnum):
    NEEDS_INPUT = "needs-input"
    APPROVAL_REQUIRED = "approval-required"
    EFFECT_DISPATCH_PENDING = "effect-dispatch-pending"


class HarnessProviderCallSource(StrEnum):
    ASSIGNMENT = "assignment"
    SNAPSHOT = "snapshot"


class HarnessProviderCallStatus(StrEnum):
    CLAIMED = "claimed"
    DISPATCHING = "dispatching"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


_PROVIDER_FAILURE_CODES = frozenset(
    {
        "provider_failed",
        "provider_timeout",
        "provider_transport_failed",
        "provider_rejected",
        "provider_unavailable",
    }
)
_PROVIDER_DISPATCH_SAFETIES = frozenset(
    {
        "pre_dispatch_safe",
        "provider_rejected",
        "dispatch_ambiguous",
    }
)


_TERMINAL_TOOL_STEP_STATUSES = {
    HarnessToolStepStatus.OBSERVED,
    HarnessToolStepStatus.REJECTED,
    HarnessToolStepStatus.UNKNOWN,
    HarnessToolStepStatus.CANCELLED,
}


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise HarnessProtocolError(
            f"{label} fields differ: {sorted(set(value) ^ expected)}"
        )


def _text(
    value: Any,
    label: str,
    *,
    prefix: str | None = None,
    max_bytes: int = 512,
) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HarnessProtocolError(f"{label} must be a non-empty trimmed string")
    if prefix is not None and not value.startswith(prefix + ":"):
        raise HarnessProtocolError(f"{label} must start with {prefix}:")
    if len(value.encode("utf-8")) > max_bytes:
        raise HarnessProtocolError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _nullable_text(
    value: Any,
    label: str,
    *,
    prefix: str | None = None,
    max_bytes: int = 512,
) -> str | None:
    if value is None:
        return None
    return _text(value, label, prefix=prefix, max_bytes=max_bytes)


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise HarnessProtocolError(f"{label} must be a digest string")
    try:
        return validate_digest(value)
    except ValueError as error:
        raise HarnessProtocolError(f"{label} is invalid") from error


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise HarnessProtocolError(f"{label} must be an integer >= {minimum}")
    return value


def _digest_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise HarnessProtocolError(f"{label} must be a list")
    values = tuple(_digest(item, f"{label} item") for item in value)
    if len(values) != len(set(values)):
        raise HarnessProtocolError(f"{label} values must be unique")
    return values


@dataclass(frozen=True, slots=True)
class HarnessProviderCallFailureReceipt:
    provider_call_id: str
    request_digest: str
    provider_request_digest: str
    failure_code: str
    dispatch_safety: str
    detail: str

    def __post_init__(self) -> None:
        _text(
            self.provider_call_id,
            "Provider Call identity",
            prefix="provider-call",
        )
        _digest(self.request_digest, "Agent Turn request digest")
        _digest(self.provider_request_digest, "Provider request digest")
        if (
            not isinstance(self.failure_code, str)
            or self.failure_code not in _PROVIDER_FAILURE_CODES
        ):
            raise HarnessProtocolError("Provider Call failure code is invalid")
        if (
            not isinstance(self.dispatch_safety, str)
            or self.dispatch_safety not in _PROVIDER_DISPATCH_SAFETIES
        ):
            raise HarnessProtocolError("Provider Call dispatch safety is invalid")
        _text(self.detail, "Provider Call failure detail", max_bytes=2_048)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-provider-call-failure",
            "providerCallId": self.provider_call_id,
            "requestDigest": self.request_digest,
            "providerRequestDigest": self.provider_request_digest,
            "failureCode": self.failure_code,
            "dispatchSafety": self.dispatch_safety,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> HarnessProviderCallFailureReceipt:
        _exact(
            value,
            {
                "schemaVersion",
                "kind",
                "providerCallId",
                "requestDigest",
                "providerRequestDigest",
                "failureCode",
                "dispatchSafety",
                "detail",
            },
            "HarnessProviderCallFailureReceipt",
        )
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-provider-call-failure"
        ):
            raise HarnessProtocolError(
                "HarnessProviderCallFailureReceipt version or kind is invalid"
            )
        return cls(
            provider_call_id=value["providerCallId"],
            request_digest=value["requestDigest"],
            provider_request_digest=value["providerRequestDigest"],
            failure_code=value["failureCode"],
            dispatch_safety=value["dispatchSafety"],
            detail=value["detail"],
        )


@dataclass(frozen=True, slots=True)
class HarnessProviderCallRecord:
    record_id: str
    provider_call_id: str
    task_id: str
    harness_run_id: str
    assignment_id: str
    assignment_generation: int
    assignment_digest: str
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

    def __post_init__(self) -> None:
        _text(
            self.record_id,
            "Provider Call Record identity",
            prefix="harness-provider-call-record",
        )
        _text(
            self.provider_call_id,
            "Provider Call identity",
            prefix="provider-call",
        )
        _text(self.task_id, "Task identity", prefix="task")
        _text(self.harness_run_id, "Harness Run identity", prefix="harness-run")
        _text(self.assignment_id, "Assignment identity", prefix="assignment")
        _integer(self.assignment_generation, "Assignment generation", minimum=1)
        _digest(self.assignment_digest, "Assignment digest")
        if not isinstance(self.source_kind, HarnessProviderCallSource):
            raise HarnessProtocolError("Provider Call source kind is invalid")
        _digest(self.source_digest, "Provider Call source digest")
        _digest(self.source_object_digest, "Provider Call source object digest")
        _digest(self.state_object_digest, "Harness Run State object digest")
        _text(self.turn_id, "Turn identity", prefix="turn")
        _integer(self.turn_sequence, "Turn sequence", minimum=1)
        _digest(self.request_digest, "Agent Turn request digest")
        _digest(self.provider_request_digest, "Provider request digest")
        _text(self.adapter_id, "Provider adapter identity", max_bytes=300)
        _text(self.requested_model_id, "requested model identity", max_bytes=300)
        _text(self.holder_id, "Provider Call holder identity", max_bytes=300)
        _integer(self.claim_generation, "Provider Call claim generation", minimum=1)
        if not isinstance(self.status, HarnessProviderCallStatus):
            raise HarnessProtocolError("Provider Call status is invalid")
        if self.result_digest is not None:
            _digest(self.result_digest, "Agent Turn result digest")
        if self.result_object_digest is not None:
            _digest(self.result_object_digest, "Agent Turn result object digest")
        if self.failure_digest is not None:
            _digest(self.failure_digest, "Provider Call failure digest")
        if self.failure_object_digest is not None:
            _digest(
                self.failure_object_digest,
                "Provider Call failure object digest",
            )
        if self.previous_record_digest is not None:
            _digest(
                self.previous_record_digest,
                "previous Provider Call Record digest",
            )
        _integer(self.issued_at_ms, "Provider Call issue time")
        _integer(self.expires_at_ms, "Provider Call expiry time")
        _integer(self.recorded_at_ms, "Provider Call record time")
        if self.expires_at_ms <= self.issued_at_ms:
            raise HarnessProtocolError(
                "Provider Call expiry must follow issue time"
            )
        result_refs = (self.result_digest, self.result_object_digest)
        if self.status is HarnessProviderCallStatus.COMPLETED:
            if any(value is None for value in result_refs):
                raise HarnessProtocolError(
                    "completed Provider Call requires both result references"
                )
        elif any(value is not None for value in result_refs):
            raise HarnessProtocolError(
                "non-completed Provider Call cannot carry result references"
            )
        failure_statuses = {
            HarnessProviderCallStatus.FAILED,
            HarnessProviderCallStatus.UNKNOWN,
        }
        failure_refs = (self.failure_digest, self.failure_object_digest)
        if self.status in failure_statuses:
            if any(value is None for value in failure_refs):
                raise HarnessProtocolError(
                    "failed or unknown Provider Call requires both failure references"
                )
        elif any(value is not None for value in failure_refs):
            raise HarnessProtocolError(
                "non-failed Provider Call cannot carry failure references"
            )
        initial_claim = (
            self.status is HarnessProviderCallStatus.CLAIMED
            and self.claim_generation == 1
        )
        if not initial_claim and self.previous_record_digest is None:
            raise HarnessProtocolError(
                "Provider Call transition requires a previous record"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-provider-call-record",
            "recordId": self.record_id,
            "providerCallId": self.provider_call_id,
            "taskId": self.task_id,
            "harnessRunId": self.harness_run_id,
            "assignmentId": self.assignment_id,
            "assignmentGeneration": self.assignment_generation,
            "assignmentDigest": self.assignment_digest,
            "sourceKind": self.source_kind.value,
            "sourceDigest": self.source_digest,
            "sourceObjectDigest": self.source_object_digest,
            "stateObjectDigest": self.state_object_digest,
            "turnId": self.turn_id,
            "turnSequence": self.turn_sequence,
            "requestDigest": self.request_digest,
            "providerRequestDigest": self.provider_request_digest,
            "adapterId": self.adapter_id,
            "requestedModelId": self.requested_model_id,
            "holderId": self.holder_id,
            "claimGeneration": self.claim_generation,
            "status": self.status.value,
            "resultDigest": self.result_digest,
            "resultObjectDigest": self.result_object_digest,
            "failureDigest": self.failure_digest,
            "failureObjectDigest": self.failure_object_digest,
            "previousRecordDigest": self.previous_record_digest,
            "issuedAtMs": self.issued_at_ms,
            "expiresAtMs": self.expires_at_ms,
            "recordedAtMs": self.recorded_at_ms,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessProviderCallRecord:
        _exact(
            value,
            {
                "schemaVersion",
                "kind",
                "recordId",
                "providerCallId",
                "taskId",
                "harnessRunId",
                "assignmentId",
                "assignmentGeneration",
                "assignmentDigest",
                "sourceKind",
                "sourceDigest",
                "sourceObjectDigest",
                "stateObjectDigest",
                "turnId",
                "turnSequence",
                "requestDigest",
                "providerRequestDigest",
                "adapterId",
                "requestedModelId",
                "holderId",
                "claimGeneration",
                "status",
                "resultDigest",
                "resultObjectDigest",
                "failureDigest",
                "failureObjectDigest",
                "previousRecordDigest",
                "issuedAtMs",
                "expiresAtMs",
                "recordedAtMs",
            },
            "HarnessProviderCallRecord",
        )
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-provider-call-record"
        ):
            raise HarnessProtocolError(
                "HarnessProviderCallRecord version or kind is invalid"
            )
        try:
            source_kind = HarnessProviderCallSource(value["sourceKind"])
        except (TypeError, ValueError) as error:
            raise HarnessProtocolError(
                "HarnessProviderCallRecord source kind is invalid"
            ) from error
        try:
            status = HarnessProviderCallStatus(value["status"])
        except (TypeError, ValueError) as error:
            raise HarnessProtocolError(
                "HarnessProviderCallRecord status is invalid"
            ) from error
        return cls(
            record_id=value["recordId"],
            provider_call_id=value["providerCallId"],
            task_id=value["taskId"],
            harness_run_id=value["harnessRunId"],
            assignment_id=value["assignmentId"],
            assignment_generation=value["assignmentGeneration"],
            assignment_digest=value["assignmentDigest"],
            source_kind=source_kind,
            source_digest=value["sourceDigest"],
            source_object_digest=value["sourceObjectDigest"],
            state_object_digest=value["stateObjectDigest"],
            turn_id=value["turnId"],
            turn_sequence=value["turnSequence"],
            request_digest=value["requestDigest"],
            provider_request_digest=value["providerRequestDigest"],
            adapter_id=value["adapterId"],
            requested_model_id=value["requestedModelId"],
            holder_id=value["holderId"],
            claim_generation=value["claimGeneration"],
            status=status,
            result_digest=value["resultDigest"],
            result_object_digest=value["resultObjectDigest"],
            failure_digest=value["failureDigest"],
            failure_object_digest=value["failureObjectDigest"],
            previous_record_digest=value["previousRecordDigest"],
            issued_at_ms=value["issuedAtMs"],
            expires_at_ms=value["expiresAtMs"],
            recorded_at_ms=value["recordedAtMs"],
        )


@dataclass(frozen=True, slots=True)
class HarnessToolStepIntent:
    intent_id: str
    harness_run_id: str
    assignment_id: str
    assignment_generation: int
    assignment_digest: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    tool_call_digest: str
    runtime_operation: str
    runtime_arguments_digest: str
    client_request_id: str
    recovery_consequence: HarnessRecoveryConsequence
    created_at_ms: int

    def __post_init__(self) -> None:
        _text(
            self.intent_id,
            "Tool Step Intent identity",
            prefix="harness-tool-step-intent",
        )
        _text(self.harness_run_id, "Harness Run identity", prefix="harness-run")
        _text(self.assignment_id, "Assignment identity", prefix="assignment")
        _integer(self.assignment_generation, "Assignment generation", minimum=1)
        _digest(self.assignment_digest, "Assignment digest")
        _text(self.turn_id, "Turn identity", prefix="turn")
        _text(self.tool_call_id, "Tool Call identity", max_bytes=300)
        _text(self.tool_name, "Tool name", max_bytes=120)
        _digest(self.tool_call_digest, "Tool Call digest")
        _text(self.runtime_operation, "Runtime operation", max_bytes=160)
        _digest(self.runtime_arguments_digest, "Runtime arguments digest")
        _text(self.client_request_id, "Runtime client request identity", max_bytes=300)
        _integer(self.created_at_ms, "Tool Step Intent time")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-tool-step-intent",
            "intentId": self.intent_id,
            "harnessRunId": self.harness_run_id,
            "assignmentId": self.assignment_id,
            "assignmentGeneration": self.assignment_generation,
            "assignmentDigest": self.assignment_digest,
            "turnId": self.turn_id,
            "toolCallId": self.tool_call_id,
            "toolName": self.tool_name,
            "toolCallDigest": self.tool_call_digest,
            "runtimeOperation": self.runtime_operation,
            "runtimeArgumentsDigest": self.runtime_arguments_digest,
            "clientRequestId": self.client_request_id,
            "recoveryConsequence": self.recovery_consequence.value,
            "createdAtMs": self.created_at_ms,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessToolStepIntent:
        _exact(
            value,
            {
                "schemaVersion",
                "kind",
                "intentId",
                "harnessRunId",
                "assignmentId",
                "assignmentGeneration",
                "assignmentDigest",
                "turnId",
                "toolCallId",
                "toolName",
                "toolCallDigest",
                "runtimeOperation",
                "runtimeArgumentsDigest",
                "clientRequestId",
                "recoveryConsequence",
                "createdAtMs",
            },
            "HarnessToolStepIntent",
        )
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-tool-step-intent"
        ):
            raise HarnessProtocolError(
                "HarnessToolStepIntent version or kind is invalid"
            )
        try:
            consequence = HarnessRecoveryConsequence(value["recoveryConsequence"])
        except (TypeError, ValueError) as error:
            raise HarnessProtocolError(
                "HarnessToolStepIntent consequence is invalid"
            ) from error
        return cls(
            intent_id=value["intentId"],
            harness_run_id=value["harnessRunId"],
            assignment_id=value["assignmentId"],
            assignment_generation=value["assignmentGeneration"],
            assignment_digest=value["assignmentDigest"],
            turn_id=value["turnId"],
            tool_call_id=value["toolCallId"],
            tool_name=value["toolName"],
            tool_call_digest=value["toolCallDigest"],
            runtime_operation=value["runtimeOperation"],
            runtime_arguments_digest=value["runtimeArgumentsDigest"],
            client_request_id=value["clientRequestId"],
            recovery_consequence=consequence,
            created_at_ms=value["createdAtMs"],
        )


@dataclass(frozen=True, slots=True)
class HarnessToolStepReceipt:
    receipt_id: str
    intent_digest: str
    harness_run_id: str
    tool_call_id: str
    status: HarnessToolStepStatus
    runtime_job_ref: str | None
    observation_digest: str | None
    reconciled: bool
    created_at_ms: int
    previous_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        _text(
            self.receipt_id,
            "Tool Step Receipt identity",
            prefix="harness-tool-step-receipt",
        )
        _digest(self.intent_digest, "Tool Step Intent digest")
        _text(self.harness_run_id, "Harness Run identity", prefix="harness-run")
        _text(self.tool_call_id, "Tool Call identity", max_bytes=300)
        _nullable_text(self.runtime_job_ref, "Runtime Job reference")
        if self.observation_digest is not None:
            _digest(self.observation_digest, "Tool Observation digest")
        if self.previous_receipt_digest is not None:
            _digest(self.previous_receipt_digest, "previous Tool Step Receipt digest")
        if type(self.reconciled) is not bool:
            raise HarnessProtocolError("Tool Step Receipt reconciled must be boolean")
        _integer(self.created_at_ms, "Tool Step Receipt time")
        if (
            self.status is HarnessToolStepStatus.REJECTED
            and self.runtime_job_ref is not None
        ):
            raise HarnessProtocolError("rejected Tool Step cannot carry a Runtime Job")
        if (
            self.status in _TERMINAL_TOOL_STEP_STATUSES
            and self.observation_digest is None
        ):
            raise HarnessProtocolError(
                "terminal Tool Step Receipt requires an observation digest"
            )
        if (
            self.status is HarnessToolStepStatus.CANCEL_REQUESTED
            and self.runtime_job_ref is None
        ):
            raise HarnessProtocolError(
                "cancel-requested Tool Step requires a Runtime Job"
            )

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_TOOL_STEP_STATUSES

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-tool-step-receipt",
            "receiptId": self.receipt_id,
            "intentDigest": self.intent_digest,
            "harnessRunId": self.harness_run_id,
            "toolCallId": self.tool_call_id,
            "status": self.status.value,
            "runtimeJobRef": self.runtime_job_ref,
            "observationDigest": self.observation_digest,
            "reconciled": self.reconciled,
            "createdAtMs": self.created_at_ms,
            "previousReceiptDigest": self.previous_receipt_digest,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessToolStepReceipt:
        legacy_fields = {
            "schemaVersion",
            "kind",
            "receiptId",
            "intentDigest",
            "harnessRunId",
            "toolCallId",
            "status",
            "runtimeJobRef",
            "observationDigest",
            "reconciled",
            "createdAtMs",
        }
        current_fields = legacy_fields | {"previousReceiptDigest"}
        if set(value) not in {frozenset(legacy_fields), frozenset(current_fields)}:
            raise HarnessProtocolError(
                "HarnessToolStepReceipt fields differ: "
                f"{sorted(set(value) ^ current_fields)}"
            )
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-tool-step-receipt"
        ):
            raise HarnessProtocolError(
                "HarnessToolStepReceipt version or kind is invalid"
            )
        try:
            status = HarnessToolStepStatus(value["status"])
        except (TypeError, ValueError) as error:
            raise HarnessProtocolError(
                "HarnessToolStepReceipt status is invalid"
            ) from error
        return cls(
            receipt_id=value["receiptId"],
            intent_digest=value["intentDigest"],
            harness_run_id=value["harnessRunId"],
            tool_call_id=value["toolCallId"],
            status=status,
            runtime_job_ref=value["runtimeJobRef"],
            observation_digest=value["observationDigest"],
            reconciled=value["reconciled"],
            created_at_ms=value["createdAtMs"],
            previous_receipt_digest=value.get("previousReceiptDigest"),
        )


@dataclass(frozen=True, slots=True)
class HarnessDispatchFence:
    fence_id: str
    task_id: str
    task_revision: int
    harness_run_id: str
    assignment_id: str
    assignment_generation: int
    assignment_digest: str
    intent_digest: str
    runtime_operation: str
    client_request_id: str
    issued_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        _text(self.fence_id, "Dispatch Fence identity", prefix="harness-dispatch-fence")
        _text(self.task_id, "Task identity", prefix="task")
        _integer(self.task_revision, "Task revision", minimum=1)
        _text(self.harness_run_id, "Harness Run identity", prefix="harness-run")
        _text(self.assignment_id, "Assignment identity", prefix="assignment")
        _integer(self.assignment_generation, "Assignment generation", minimum=1)
        _digest(self.assignment_digest, "Assignment digest")
        _digest(self.intent_digest, "Tool Step Intent digest")
        _text(self.runtime_operation, "Runtime operation", max_bytes=160)
        _text(self.client_request_id, "Runtime client request identity", max_bytes=300)
        _integer(self.issued_at_ms, "Dispatch Fence issue time")
        _integer(self.expires_at_ms, "Dispatch Fence expiry time")
        if self.expires_at_ms <= self.issued_at_ms:
            raise HarnessProtocolError("Dispatch Fence expiry must follow issue time")

    @property
    def authority_namespace(self) -> str:
        return "ordivon.host"

    @property
    def authority_type(self) -> str:
        return "dispatch_fence"

    @property
    def authority_generation(self) -> int:
        return self.task_revision

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-dispatch-fence",
            "fenceId": self.fence_id,
            "taskId": self.task_id,
            "taskRevision": self.task_revision,
            "harnessRunId": self.harness_run_id,
            "assignmentId": self.assignment_id,
            "assignmentGeneration": self.assignment_generation,
            "assignmentDigest": self.assignment_digest,
            "intentDigest": self.intent_digest,
            "runtimeOperation": self.runtime_operation,
            "clientRequestId": self.client_request_id,
            "issuedAtMs": self.issued_at_ms,
            "expiresAtMs": self.expires_at_ms,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessDispatchFence:
        _exact(
            value,
            {
                "schemaVersion",
                "kind",
                "fenceId",
                "taskId",
                "taskRevision",
                "harnessRunId",
                "assignmentId",
                "assignmentGeneration",
                "assignmentDigest",
                "intentDigest",
                "runtimeOperation",
                "clientRequestId",
                "issuedAtMs",
                "expiresAtMs",
            },
            "HarnessDispatchFence",
        )
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-dispatch-fence"
        ):
            raise HarnessProtocolError(
                "HarnessDispatchFence version or kind is invalid"
            )
        return cls(
            fence_id=value["fenceId"],
            task_id=value["taskId"],
            task_revision=value["taskRevision"],
            harness_run_id=value["harnessRunId"],
            assignment_id=value["assignmentId"],
            assignment_generation=value["assignmentGeneration"],
            assignment_digest=value["assignmentDigest"],
            intent_digest=value["intentDigest"],
            runtime_operation=value["runtimeOperation"],
            client_request_id=value["clientRequestId"],
            issued_at_ms=value["issuedAtMs"],
            expires_at_ms=value["expiresAtMs"],
        )


@dataclass(frozen=True, slots=True)
class HarnessRunSnapshot:
    snapshot_id: str
    harness_run_id: str
    assignment_id: str
    assignment_generation: int
    assignment_digest: str
    sequence: int
    tool_catalog_digest: str
    requested_model_id: str
    effective_model_id: str | None
    messages_digest: str
    observation_digests: tuple[str, ...]
    active_tool_step_intent_digests: tuple[str, ...]
    remaining_budget: dict[str, JsonValue]
    pause_reason: HarnessRunPauseReason
    created_at_ms: int

    def __post_init__(self) -> None:
        _text(
            self.snapshot_id,
            "Harness Run Snapshot identity",
            prefix="harness-run-snapshot",
        )
        _text(self.harness_run_id, "Harness Run identity", prefix="harness-run")
        _text(self.assignment_id, "Assignment identity", prefix="assignment")
        _integer(self.assignment_generation, "Assignment generation", minimum=1)
        _digest(self.assignment_digest, "Assignment digest")
        _integer(self.sequence, "Harness Run Snapshot sequence", minimum=1)
        _digest(self.tool_catalog_digest, "Tool catalog digest")
        _text(self.requested_model_id, "requested model identity", max_bytes=300)
        _nullable_text(
            self.effective_model_id, "effective model identity", max_bytes=300
        )
        _digest(self.messages_digest, "Run-local messages digest")
        for digest in self.observation_digests:
            _digest(digest, "Tool Observation digest")
        if len(self.observation_digests) != len(set(self.observation_digests)):
            raise HarnessProtocolError("Tool Observation digests must be unique")
        for digest in self.active_tool_step_intent_digests:
            _digest(digest, "active Tool Step Intent digest")
        if len(self.active_tool_step_intent_digests) != len(
            set(self.active_tool_step_intent_digests)
        ):
            raise HarnessProtocolError("active Tool Step Intent digests must be unique")
        validate_json_value(self.remaining_budget)
        _integer(self.created_at_ms, "Harness Run Snapshot time")
        if (
            self.pause_reason is HarnessRunPauseReason.EFFECT_DISPATCH_PENDING
            and not self.active_tool_step_intent_digests
        ):
            raise HarnessProtocolError(
                "effect-dispatch-pending Snapshot requires an active Tool Step Intent"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-run-snapshot",
            "snapshotId": self.snapshot_id,
            "harnessRunId": self.harness_run_id,
            "assignmentId": self.assignment_id,
            "assignmentGeneration": self.assignment_generation,
            "assignmentDigest": self.assignment_digest,
            "sequence": self.sequence,
            "toolCatalogDigest": self.tool_catalog_digest,
            "requestedModelId": self.requested_model_id,
            "effectiveModelId": self.effective_model_id,
            "messagesDigest": self.messages_digest,
            "observationDigests": list(self.observation_digests),
            "activeToolStepIntentDigests": list(self.active_tool_step_intent_digests),
            "remainingBudget": self.remaining_budget,
            "pauseReason": self.pause_reason.value,
            "createdAtMs": self.created_at_ms,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessRunSnapshot:
        _exact(
            value,
            {
                "schemaVersion",
                "kind",
                "snapshotId",
                "harnessRunId",
                "assignmentId",
                "assignmentGeneration",
                "assignmentDigest",
                "sequence",
                "toolCatalogDigest",
                "requestedModelId",
                "effectiveModelId",
                "messagesDigest",
                "observationDigests",
                "activeToolStepIntentDigests",
                "remainingBudget",
                "pauseReason",
                "createdAtMs",
            },
            "HarnessRunSnapshot",
        )
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-run-snapshot"
        ):
            raise HarnessProtocolError("HarnessRunSnapshot version or kind is invalid")
        if not isinstance(value["remainingBudget"], dict):
            raise HarnessProtocolError(
                "HarnessRunSnapshot remainingBudget must be an object"
            )
        try:
            pause_reason = HarnessRunPauseReason(value["pauseReason"])
        except (TypeError, ValueError) as error:
            raise HarnessProtocolError(
                "HarnessRunSnapshot pause reason is invalid"
            ) from error
        return cls(
            snapshot_id=value["snapshotId"],
            harness_run_id=value["harnessRunId"],
            assignment_id=value["assignmentId"],
            assignment_generation=value["assignmentGeneration"],
            assignment_digest=value["assignmentDigest"],
            sequence=value["sequence"],
            tool_catalog_digest=value["toolCatalogDigest"],
            requested_model_id=value["requestedModelId"],
            effective_model_id=value["effectiveModelId"],
            messages_digest=value["messagesDigest"],
            observation_digests=_digest_list(
                value["observationDigests"], "observationDigests"
            ),
            active_tool_step_intent_digests=_digest_list(
                value["activeToolStepIntentDigests"],
                "activeToolStepIntentDigests",
            ),
            remaining_budget=dict(value["remainingBudget"]),
            pause_reason=pause_reason,
            created_at_ms=value["createdAtMs"],
        )

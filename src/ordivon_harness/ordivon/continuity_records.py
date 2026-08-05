from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from anc_canonical import JsonValue, canonical_digest

from ..protocol import (
    HarnessProtocolError,
    HarnessProviderCallSource,
    HarnessProviderCallStatus,
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise HarnessProtocolError(f"{label} fields differ: {sorted(set(value) ^ expected)}")


def _text(
    value: str,
    label: str,
    *,
    prefix: str | None = None,
    max_bytes: int = 300,
) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HarnessProtocolError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise HarnessProtocolError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    if prefix is not None and not value.startswith(prefix + ":"):
        raise HarnessProtocolError(f"{label} must start with {prefix}:")


def _digest(value: str, label: str) -> None:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise HarnessProtocolError(f"{label} must be sha256:<64 lowercase hex>")


def _integer(value: int, label: str, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise HarnessProtocolError(f"{label} must be an integer >= {minimum}")


@dataclass(frozen=True, slots=True)
class HarnessProviderCallRecordV2:
    """Caller-neutral durable Provider Call record for the independent Store.

    Version 1 remains the exact Host-backed historical codec. Version 2 binds
    the record to one Harness Run Store binding digest and contains no Host Task
    identity or Host Journal revision.
    """

    record_id: str
    provider_call_id: str
    harness_run_id: str
    binding_digest: str
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
        _text(self.harness_run_id, "Harness Run identity", prefix="harness-run")
        _digest(self.binding_digest, "Harness Run Store binding digest")
        if not isinstance(self.source_kind, HarnessProviderCallSource):
            raise HarnessProtocolError("Provider Call source kind is invalid")
        _digest(self.source_digest, "Provider Call source digest")
        _digest(self.source_object_digest, "Provider Call source object digest")
        _digest(self.state_object_digest, "Harness Run State object digest")
        _text(self.turn_id, "Turn identity", prefix="turn")
        _integer(self.turn_sequence, "Turn sequence", minimum=1)
        _digest(self.request_digest, "Agent Turn request digest")
        _digest(self.provider_request_digest, "Provider request digest")
        _text(self.adapter_id, "Provider adapter identity")
        _text(self.requested_model_id, "requested model identity")
        _text(self.holder_id, "Provider Call holder identity")
        _integer(self.claim_generation, "Provider Call claim generation", minimum=1)
        if not isinstance(self.status, HarnessProviderCallStatus):
            raise HarnessProtocolError("Provider Call status is invalid")
        for value, label in (
            (self.result_digest, "Agent Turn result digest"),
            (self.result_object_digest, "Agent Turn result object digest"),
            (self.failure_digest, "Provider Call failure digest"),
            (self.failure_object_digest, "Provider Call failure object digest"),
            (self.previous_record_digest, "previous Provider Call Record digest"),
        ):
            if value is not None:
                _digest(value, label)
        _integer(self.issued_at_ms, "Provider Call issue time")
        _integer(self.expires_at_ms, "Provider Call expiry time")
        _integer(self.recorded_at_ms, "Provider Call record time")
        if self.expires_at_ms <= self.issued_at_ms:
            raise HarnessProtocolError("Provider Call expiry must follow issue time")
        result_refs = (self.result_digest, self.result_object_digest)
        if self.status is HarnessProviderCallStatus.COMPLETED:
            if any(value is None for value in result_refs):
                raise HarnessProtocolError(
                    "completed Provider Call requires both result references"
                )
        elif any(value is not None for value in result_refs):
            raise HarnessProtocolError("non-completed Provider Call cannot carry result references")
        failure_refs = (self.failure_digest, self.failure_object_digest)
        if self.status in {
            HarnessProviderCallStatus.FAILED,
            HarnessProviderCallStatus.UNKNOWN,
        }:
            if any(value is None for value in failure_refs):
                raise HarnessProtocolError(
                    "failed or unknown Provider Call requires both failure references"
                )
        elif any(value is not None for value in failure_refs):
            raise HarnessProtocolError("non-failed Provider Call cannot carry failure references")
        initial_claim = (
            self.status is HarnessProviderCallStatus.CLAIMED and self.claim_generation == 1
        )
        if not initial_claim and self.previous_record_digest is None:
            raise HarnessProtocolError("Provider Call transition requires a previous record")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 2,
            "kind": "ordivon.harness-provider-call-record",
            "recordId": self.record_id,
            "providerCallId": self.provider_call_id,
            "harnessRunId": self.harness_run_id,
            "bindingDigest": self.binding_digest,
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
    def from_dict(cls, value: dict[str, Any]) -> HarnessProviderCallRecordV2:
        expected = {
            "schemaVersion",
            "kind",
            "recordId",
            "providerCallId",
            "harnessRunId",
            "bindingDigest",
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
        }
        _exact(value, expected, "HarnessProviderCallRecordV2")
        if value["schemaVersion"] != 2 or value["kind"] != "ordivon.harness-provider-call-record":
            raise HarnessProtocolError("HarnessProviderCallRecordV2 version or kind is invalid")
        try:
            source_kind = HarnessProviderCallSource(value["sourceKind"])
            status = HarnessProviderCallStatus(value["status"])
        except (TypeError, ValueError) as error:
            raise HarnessProtocolError(
                "HarnessProviderCallRecordV2 enum field is invalid"
            ) from error
        return cls(
            record_id=value["recordId"],
            provider_call_id=value["providerCallId"],
            harness_run_id=value["harnessRunId"],
            binding_digest=value["bindingDigest"],
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
class HarnessDispatchFenceV2:
    """Caller-neutral physical-dispatch fence for an independent Run Store."""

    fence_id: str
    harness_run_id: str
    run_revision: int
    binding_digest: str
    intent_digest: str
    runtime_operation: str
    client_request_id: str
    issued_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        _text(self.fence_id, "Dispatch Fence identity", prefix="harness-dispatch-fence")
        _text(self.harness_run_id, "Harness Run identity", prefix="harness-run")
        _integer(self.run_revision, "Harness Run revision", minimum=1)
        _digest(self.binding_digest, "Harness Run Store binding digest")
        _digest(self.intent_digest, "Tool Step Intent digest")
        _text(self.runtime_operation, "Runtime operation", max_bytes=160)
        _text(self.client_request_id, "Runtime client request identity")
        _integer(self.issued_at_ms, "Dispatch Fence issue time")
        _integer(self.expires_at_ms, "Dispatch Fence expiry time")
        if self.expires_at_ms <= self.issued_at_ms:
            raise HarnessProtocolError("Dispatch Fence expiry must follow issue time")

    @property
    def authority_generation(self) -> int:
        return self.run_revision

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 2,
            "kind": "ordivon.harness-dispatch-fence",
            "fenceId": self.fence_id,
            "harnessRunId": self.harness_run_id,
            "runRevision": self.run_revision,
            "bindingDigest": self.binding_digest,
            "intentDigest": self.intent_digest,
            "runtimeOperation": self.runtime_operation,
            "clientRequestId": self.client_request_id,
            "issuedAtMs": self.issued_at_ms,
            "expiresAtMs": self.expires_at_ms,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessDispatchFenceV2:
        _exact(
            value,
            {
                "schemaVersion",
                "kind",
                "fenceId",
                "harnessRunId",
                "runRevision",
                "bindingDigest",
                "intentDigest",
                "runtimeOperation",
                "clientRequestId",
                "issuedAtMs",
                "expiresAtMs",
            },
            "HarnessDispatchFenceV2",
        )
        if value["schemaVersion"] != 2 or value["kind"] != "ordivon.harness-dispatch-fence":
            raise HarnessProtocolError("HarnessDispatchFenceV2 version or kind is invalid")
        return cls(
            fence_id=value["fenceId"],
            harness_run_id=value["harnessRunId"],
            run_revision=value["runRevision"],
            binding_digest=value["bindingDigest"],
            intent_digest=value["intentDigest"],
            runtime_operation=value["runtimeOperation"],
            client_request_id=value["clientRequestId"],
            issued_at_ms=value["issuedAtMs"],
            expires_at_ms=value["expiresAtMs"],
        )

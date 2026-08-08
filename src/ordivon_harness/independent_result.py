from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .agent_tool_observation import HarnessArtifactReference, HarnessToolObservation
from .core_contracts import HarnessRunContract
from .ordivon.events import HarnessRunEvent, HarnessTrace
from .ordivon.loop import AgentLoopResult, RunStopCode
from .ordivon.model import AgentRunConclusion
from .ordivon.run_store_port import HarnessRunStoreBinding
from .recovery import NativeRunRecoveryAssessment
from .store import (
    HarnessEventAdmission,
    HarnessStore,
    StoredHarnessObject,
    new_execution_owner_id,
)

_STORE_LEASE_TTL_MS = 30_000
_TRACE_EVENT_KIND = "harness.trace-recorded"
_RECOVERY_EVENT_KIND = "harness.run-recovery-recorded"
_TERMINAL_EVENT_KINDS = frozenset(
    {"harness.run-completed", "harness.run-stopped", "harness.run-failed"}
)
_PAUSED_CODES = frozenset({RunStopCode.NEEDS_INPUT, RunStopCode.NO_PROGRESS})
_FAILED_CODES = frozenset(
    {
        RunStopCode.PROVIDER_FAILED,
        RunStopCode.PROVIDER_TIMEOUT,
        RunStopCode.PROVIDER_TRANSPORT_FAILED,
        RunStopCode.PROVIDER_REJECTED,
        RunStopCode.PROVIDER_UNAVAILABLE,
        RunStopCode.INVALID_TOOL_CALL,
        RunStopCode.INVALID_MODEL_OUTPUT,
        RunStopCode.HARNESS_FAILED,
    }
)
_UNKNOWN_CODES = frozenset(
    {
        RunStopCode.CANCEL_UNKNOWN,
        RunStopCode.PROVIDER_STATE_UNKNOWN,
        RunStopCode.RUNTIME_UNKNOWN,
    }
)


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields differ: {sorted(set(value) ^ expected)}")


def _text(value: str, label: str, *, max_bytes: int = 2_048) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _identity(value: str, prefix: str, label: str) -> str:
    _text(value, label, max_bytes=500)
    if not value.startswith(prefix + ":"):
        raise ValueError(f"{label} must start with {prefix}:")
    return value


def _digest(value: str, label: str) -> str:
    if (
        len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return value


def _unique_text(values: tuple[str, ...], label: str) -> None:
    for value in values:
        _text(value, label, max_bytes=1_024)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")


@dataclass(frozen=True, slots=True)
class IndependentHarnessRunReceipt:
    harness_run_id: str
    caller_id: str
    caller_run_ref: str
    contract_digest: str
    harness_implementation_id: str
    system_manifest_digest: str
    started_at_ms: int
    finished_at_ms: int
    stop_reason: str
    termination_code: str
    trace_digest: str
    context_digests: tuple[str, ...]
    tool_catalog_digest: str
    tool_grant_digest: str
    runtime_job_refs: tuple[str, ...]
    artifact_refs: tuple[HarnessArtifactReference, ...]
    usage: dict[str, JsonValue]
    conclusion_digest: str | None = None

    def __post_init__(self) -> None:
        _identity(self.harness_run_id, "harness-run", "Harness Run")
        _identity(self.caller_id, "caller", "Harness caller")
        _text(self.caller_run_ref, "caller Run reference", max_bytes=1_024)
        _digest(self.contract_digest, "Harness Run Contract digest")
        _text(self.harness_implementation_id, "Harness implementation identity", max_bytes=300)
        _digest(self.system_manifest_digest, "System Manifest digest")
        if self.started_at_ms < 0 or self.finished_at_ms < self.started_at_ms:
            raise ValueError("independent Harness Run times are invalid")
        if self.stop_reason not in {"completed", "stopped", "failed", "unknown"}:
            raise ValueError(f"unsupported independent Run stop reason: {self.stop_reason}")
        _text(self.termination_code, "Harness termination code", max_bytes=300)
        _digest(self.trace_digest, "Harness Trace digest")
        if not self.context_digests:
            raise ValueError("independent Harness Run requires Context digests")
        for digest in self.context_digests:
            _digest(digest, "Harness Context digest")
        if len(self.context_digests) != len(set(self.context_digests)):
            raise ValueError("Harness Context digests must be unique")
        _digest(self.tool_catalog_digest, "Harness Tool catalog digest")
        _digest(self.tool_grant_digest, "Harness Tool grant digest")
        _unique_text(self.runtime_job_refs, "Runtime Job reference")
        refs = [item.ref for item in self.artifact_refs]
        if len(refs) != len(set(refs)):
            raise ValueError("Harness Artifact references must be unique")
        validate_json_value(self.usage)
        if self.conclusion_digest is not None:
            _digest(self.conclusion_digest, "Harness conclusion digest")
        if self.stop_reason == "completed" and self.conclusion_digest is None:
            raise ValueError("completed independent Run requires a conclusion")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.independent-harness-run-receipt",
            "harnessRunId": self.harness_run_id,
            "callerId": self.caller_id,
            "callerRunRef": self.caller_run_ref,
            "contractDigest": self.contract_digest,
            "harnessImplementationId": self.harness_implementation_id,
            "systemManifestDigest": self.system_manifest_digest,
            "startedAtMs": self.started_at_ms,
            "finishedAtMs": self.finished_at_ms,
            "stopReason": self.stop_reason,
            "terminationCode": self.termination_code,
            "traceDigest": self.trace_digest,
            "contextDigests": list(self.context_digests),
            "toolCatalogDigest": self.tool_catalog_digest,
            "toolGrantDigest": self.tool_grant_digest,
            "runtimeJobRefs": list(self.runtime_job_refs),
            "artifactRefs": [item.to_dict() for item in self.artifact_refs],
            "usage": self.usage,
            "conclusionDigest": self.conclusion_digest,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> IndependentHarnessRunReceipt:
        expected = {
            "schemaVersion", "kind", "harnessRunId", "callerId", "callerRunRef",
            "contractDigest", "harnessImplementationId", "systemManifestDigest",
            "startedAtMs", "finishedAtMs", "stopReason", "terminationCode",
            "traceDigest", "contextDigests", "toolCatalogDigest", "toolGrantDigest",
            "runtimeJobRefs", "artifactRefs", "usage", "conclusionDigest",
        }
        _exact(value, expected, "IndependentHarnessRunReceipt")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.independent-harness-run-receipt":
            raise ValueError("IndependentHarnessRunReceipt version or kind is invalid")
        string_fields = (
            "harnessRunId", "callerId", "callerRunRef", "contractDigest",
            "harnessImplementationId", "systemManifestDigest", "stopReason",
            "terminationCode", "traceDigest", "toolCatalogDigest", "toolGrantDigest",
        )
        if any(not isinstance(value[field], str) for field in string_fields):
            raise ValueError("IndependentHarnessRunReceipt identity fields must be strings")
        for field in ("startedAtMs", "finishedAtMs"):
            if type(value[field]) is not int:
                raise ValueError(f"IndependentHarnessRunReceipt {field} must be an integer")
        for field in ("contextDigests", "runtimeJobRefs"):
            if not isinstance(value[field], list) or any(not isinstance(item, str) for item in value[field]):
                raise ValueError(f"IndependentHarnessRunReceipt {field} must contain strings")
        artifacts = value["artifactRefs"]
        if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
            raise ValueError("IndependentHarnessRunReceipt Artifact refs are invalid")
        if not isinstance(value["usage"], dict):
            raise ValueError("IndependentHarnessRunReceipt usage must be an object")
        conclusion_digest = value["conclusionDigest"]
        if conclusion_digest is not None and not isinstance(conclusion_digest, str):
            raise ValueError("IndependentHarnessRunReceipt conclusion digest is invalid")
        return cls(
            harness_run_id=value["harnessRunId"], caller_id=value["callerId"],
            caller_run_ref=value["callerRunRef"], contract_digest=value["contractDigest"],
            harness_implementation_id=value["harnessImplementationId"],
            system_manifest_digest=value["systemManifestDigest"],
            started_at_ms=value["startedAtMs"], finished_at_ms=value["finishedAtMs"],
            stop_reason=value["stopReason"], termination_code=value["terminationCode"],
            trace_digest=value["traceDigest"], context_digests=tuple(value["contextDigests"]),
            tool_catalog_digest=value["toolCatalogDigest"],
            tool_grant_digest=value["toolGrantDigest"],
            runtime_job_refs=tuple(value["runtimeJobRefs"]),
            artifact_refs=tuple(HarnessArtifactReference.from_dict(item) for item in artifacts),
            usage=dict(value["usage"]), conclusion_digest=conclusion_digest,
        )


@dataclass(frozen=True, slots=True)
class IndependentCompletionProposal:
    completion_proposal_id: str
    harness_run_id: str
    caller_id: str
    caller_run_ref: str
    contract_digest: str
    run_receipt_digest: str
    trace_digest: str
    summary: str
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    unresolved_unknowns: tuple[str, ...]
    usage: dict[str, JsonValue]
    created_at_ms: int

    def __post_init__(self) -> None:
        _identity(self.completion_proposal_id, "completion-proposal", "Completion Proposal")
        _identity(self.harness_run_id, "harness-run", "Harness Run")
        _identity(self.caller_id, "caller", "Harness caller")
        _text(self.caller_run_ref, "caller Run reference", max_bytes=1_024)
        _digest(self.contract_digest, "Harness Run Contract digest")
        _digest(self.run_receipt_digest, "Harness Run Receipt digest")
        _digest(self.trace_digest, "Harness Trace digest")
        _text(self.summary, "Completion Proposal summary", max_bytes=8_000)
        _unique_text(self.evidence_refs, "Completion evidence reference")
        _unique_text(self.artifact_refs, "Completion Artifact reference")
        _unique_text(self.unresolved_unknowns, "Completion unresolved unknown")
        validate_json_value(self.usage)
        if self.created_at_ms < 0:
            raise ValueError("Completion Proposal creation time must be non-negative")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 2,
            "kind": "ordivon.independent-completion-proposal",
            "completionProposalId": self.completion_proposal_id,
            "harnessRunId": self.harness_run_id,
            "callerId": self.caller_id,
            "callerRunRef": self.caller_run_ref,
            "contractDigest": self.contract_digest,
            "runReceiptDigest": self.run_receipt_digest,
            "traceDigest": self.trace_digest,
            "summary": self.summary,
            "evidenceRefs": list(self.evidence_refs),
            "artifactRefs": list(self.artifact_refs),
            "unresolvedUnknowns": list(self.unresolved_unknowns),
            "usage": self.usage,
            "createdAtMs": self.created_at_ms,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> IndependentCompletionProposal:
        version = value.get("schemaVersion")
        common = {
            "schemaVersion", "kind", "completionProposalId", "harnessRunId",
            "callerId", "callerRunRef", "contractDigest", "runReceiptDigest",
            "traceDigest", "summary", "evidenceRefs", "artifactRefs", "usage",
            "createdAtMs",
        }
        expected = common if version == 1 else common | {"unresolvedUnknowns"}
        _exact(value, expected, "IndependentCompletionProposal")
        if version not in {1, 2} or value["kind"] != "ordivon.independent-completion-proposal":
            raise ValueError("IndependentCompletionProposal version or kind is invalid")
        for field in (
            "completionProposalId", "harnessRunId", "callerId", "callerRunRef",
            "contractDigest", "runReceiptDigest", "traceDigest", "summary",
        ):
            if not isinstance(value[field], str):
                raise ValueError(f"IndependentCompletionProposal {field} must be a string")
        for field in ("evidenceRefs", "artifactRefs"):
            if not isinstance(value[field], list) or any(not isinstance(item, str) for item in value[field]):
                raise ValueError(f"IndependentCompletionProposal {field} must contain strings")
        unresolved = value.get("unresolvedUnknowns", [])
        if not isinstance(unresolved, list) or any(not isinstance(item, str) for item in unresolved):
            raise ValueError("IndependentCompletionProposal unresolvedUnknowns must contain strings")
        if not isinstance(value["usage"], dict) or type(value["createdAtMs"]) is not int:
            raise ValueError("IndependentCompletionProposal usage or time is invalid")
        return cls(
            completion_proposal_id=value["completionProposalId"],
            harness_run_id=value["harnessRunId"], caller_id=value["callerId"],
            caller_run_ref=value["callerRunRef"], contract_digest=value["contractDigest"],
            run_receipt_digest=value["runReceiptDigest"], trace_digest=value["traceDigest"],
            summary=value["summary"], evidence_refs=tuple(value["evidenceRefs"]),
            artifact_refs=tuple(value["artifactRefs"]),
            unresolved_unknowns=tuple(unresolved), usage=dict(value["usage"]),
            created_at_ms=value["createdAtMs"],
        )


@dataclass(frozen=True, slots=True)
class StoredIndependentRunResult:
    receipt: IndependentHarnessRunReceipt
    receipt_object: StoredHarnessObject
    trace: HarnessTrace
    trace_object: StoredHarnessObject
    observations: tuple[HarnessToolObservation, ...]
    observations_object: StoredHarnessObject
    conclusion: AgentRunConclusion | None
    conclusion_object: StoredHarnessObject | None
    completion_proposal: IndependentCompletionProposal | None
    completion_proposal_object: StoredHarnessObject | None


class IndependentRunRecorder:
    """Admit owner-native terminal and recovery evidence to one Harness Journal."""

    def __init__(
        self,
        store: HarnessStore,
        contract: HarnessRunContract,
        binding: HarnessRunStoreBinding,
        *,
        clock_ms: Callable[[], int],
    ) -> None:
        projection = store.load_run(contract.harness_run_id)
        if projection.contract_digest != contract.digest or binding.harness_run_id != contract.harness_run_id:
            raise ValueError("independent Run Recorder identities differ")
        self.store = store
        self.contract = contract
        self.binding = binding
        self.clock_ms = clock_ms
        self._execution_owner_id = new_execution_owner_id("independent-result")

    def _persistent_trace(self, trace: HarnessTrace) -> HarnessTrace:
        if self.contract.privacy.allow_model_content and self.contract.privacy.allow_tool_content:
            return trace
        events: list[HarnessRunEvent] = []
        for event in trace.events:
            payload = dict(event.payload)
            normalized_result = payload.get("normalizedResult")
            normalized_has_tool_calls = (
                isinstance(normalized_result, dict)
                and isinstance(normalized_result.get("toolCalls"), list)
                and bool(normalized_result["toolCalls"])
            )
            if (
                not self.contract.privacy.allow_model_content
                or not self.contract.privacy.allow_tool_content
                and normalized_has_tool_calls
            ):
                payload.pop("normalizedResult", None)
            if not self.contract.privacy.allow_tool_content:
                payload.pop("toolCall", None)
            if "detail" in payload and (
                not self.contract.privacy.allow_model_content
                or not self.contract.privacy.allow_tool_content
            ):
                detail = payload.pop("detail")
                payload["detailDigest"] = canonical_digest(detail)
            events.append(
                HarnessRunEvent(
                    sequence=event.sequence,
                    kind=event.kind,
                    occurred_at_ms=event.occurred_at_ms,
                    payload=payload,
                )
            )
        return HarnessTrace(trace.harness_run_id, tuple(events))

    def record_trace_segment(self, trace: HarnessTrace) -> HarnessEventAdmission:
        if trace.harness_run_id != self.contract.harness_run_id:
            raise ValueError("Harness Trace belongs to another Run")
        persistent_trace = self._persistent_trace(trace)
        events = self.store.list_run_events(self.contract.harness_run_id)
        existing = next(
            (
                event for event in events
                if event.event_kind == _TRACE_EVENT_KIND
                and event.data.get("traceDigest") == persistent_trace.digest
            ),
            None,
        )
        if existing is not None:
            raw = self.store.get_object(
                self._required_digest(existing.data, "traceObjectDigest"),
                expected_kind="harness-trace",
            )
            if not isinstance(raw, dict) or HarnessTrace.from_dict(raw) != persistent_trace:
                raise ValueError("existing Harness Trace segment differs")
            return HarnessEventAdmission.EXISTING
        now_ms = self._recorded_time(self.clock_ms())
        lease = self._acquire_lease("trace", persistent_trace.digest, now_ms=now_ms)
        try:
            stored = self.store.put_object(persistent_trace.to_dict(), kind="harness-trace")
            return self.store.append_event(
                event_id=self._event_id("trace", persistent_trace.digest),
                harness_run_id=self.contract.harness_run_id,
                event_kind=_TRACE_EVENT_KIND,
                data={
                    "traceDigest": persistent_trace.digest,
                    "traceObjectDigest": stored.digest,
                    "segmentIndex": 1 + sum(event.event_kind == _TRACE_EVENT_KIND for event in events),
                },
                expected_revision=lease.run_revision,
                recorded_at_ms=now_ms,
                lease=lease,
                lease_checked_at_ms=self.clock_ms(),
                caused_by_event_id=None if not events else events[-1].event_id,
                referenced_objects=(stored,),
            )
        finally:
            self.store.release_run_lease(lease)

    def record_result(
        self,
        result: AgentLoopResult,
        *,
        started_at_ms: int,
        finished_at_ms: int | None = None,
    ) -> StoredIndependentRunResult | None:
        if result.harness_run_id != self.contract.harness_run_id:
            raise ValueError("Agent Loop result belongs to another Harness Run")
        self.record_trace_segment(result.trace)
        if result.stop_code in _PAUSED_CODES:
            return None
        finished = self.clock_ms() if finished_at_ms is None else finished_at_ms
        if started_at_ms < 0 or finished < started_at_ms:
            raise ValueError("independent Run recording times are invalid")
        projection = self.store.load_run(self.contract.harness_run_id)
        if projection.status.terminal:
            existing = self.load_terminal_result()
            candidate = self._build_receipt(result, started_at_ms, finished, trace=existing.trace)
            if existing.receipt.digest != candidate.digest:
                raise ValueError("terminal Harness Run differs from replayed result")
            return existing

        trace = self._combined_trace()
        conclusion = result.conclusion
        conclusion_digest = None if conclusion is None else canonical_digest(conclusion.to_dict())
        receipt = self._build_receipt(
            result,
            started_at_ms,
            finished,
            trace=trace,
            conclusion_digest=conclusion_digest,
        )
        observations = tuple(
            HarnessToolObservation.from_dict(item.to_dict()) for item in result.observations
        )
        now_ms = self._recorded_time(finished)
        lease = self._acquire_lease("terminal", receipt.digest, now_ms=now_ms)
        try:
            trace_object = self.store.put_object(trace.to_dict(), kind="harness-trace")
            persistent_observations = (
                observations if self.contract.privacy.allow_tool_content else ()
            )
            observations_object = self.store.put_object(
                [item.to_dict() for item in persistent_observations],
                kind="harness-tool-observations",
            )
            conclusion_object = (
                None
                if conclusion is None or not self.contract.privacy.allow_model_content
                else self.store.put_object(conclusion.to_dict(), kind="harness-run-conclusion")
            )
            receipt_object = self.store.put_object(
                receipt.to_dict(), kind="independent-harness-run-receipt"
            )
            proposal = self._build_completion_proposal(receipt, result, now_ms)
            proposal_object = (
                None
                if proposal is None or not self.contract.privacy.allow_model_content
                else self.store.put_object(
                    proposal.to_dict(), kind="independent-completion-proposal"
                )
            )
            references = [trace_object, observations_object, receipt_object]
            if conclusion_object is not None:
                references.append(conclusion_object)
            if proposal_object is not None:
                references.append(proposal_object)
            events = self.store.list_run_events(self.contract.harness_run_id)
            self.store.append_event(
                event_id=self._event_id("terminal", receipt.digest),
                harness_run_id=self.contract.harness_run_id,
                event_kind=self._terminal_event_kind(result.stop_code),
                data=self._terminal_data(
                    result,
                    receipt,
                    receipt_object,
                    trace,
                    trace_object,
                    observations_object,
                    conclusion_digest,
                    conclusion_object,
                    proposal,
                    proposal_object,
                ),
                expected_revision=lease.run_revision,
                recorded_at_ms=now_ms,
                lease=lease,
                lease_checked_at_ms=self.clock_ms(),
                caused_by_event_id=None if not events else events[-1].event_id,
                referenced_objects=tuple(references),
            )
        finally:
            self.store.release_run_lease(lease)
        return self.load_terminal_result()

    def load_terminal_result(self) -> StoredIndependentRunResult:
        terminal = next(
            (
                event for event in reversed(self.store.list_run_events(self.contract.harness_run_id))
                if event.event_kind in _TERMINAL_EVENT_KINDS
            ),
            None,
        )
        if terminal is None:
            raise KeyError("Harness Run has no independent terminal result")
        data = terminal.data
        receipt_object_digest = self._required_digest(data, "runReceiptObjectDigest")
        trace_object_digest = self._required_digest(data, "traceObjectDigest")
        observations_object_digest = self._required_digest(data, "observationsObjectDigest")
        raw_receipt = self.store.get_object(
            receipt_object_digest, expected_kind="independent-harness-run-receipt"
        )
        raw_trace = self.store.get_object(trace_object_digest, expected_kind="harness-trace")
        raw_observations = self.store.get_object(
            observations_object_digest, expected_kind="harness-tool-observations"
        )
        if (
            not isinstance(raw_receipt, dict)
            or not isinstance(raw_trace, dict)
            or not isinstance(raw_observations, list)
            or any(not isinstance(item, dict) for item in raw_observations)
        ):
            raise ValueError("independent terminal objects are invalid")
        receipt = IndependentHarnessRunReceipt.from_dict(raw_receipt)
        trace = HarnessTrace.from_dict(raw_trace)
        observations = tuple(HarnessToolObservation.from_dict(item) for item in raw_observations)
        conclusion = None
        conclusion_object = None
        conclusion_object_digest = data.get("conclusionObjectDigest")
        if conclusion_object_digest is not None:
            if not isinstance(conclusion_object_digest, str):
                raise ValueError("Harness conclusion object reference is invalid")
            raw_conclusion = self.store.get_object(
                conclusion_object_digest, expected_kind="harness-run-conclusion"
            )
            if not isinstance(raw_conclusion, dict):
                raise ValueError("Harness conclusion object is invalid")
            conclusion = AgentRunConclusion.from_dict(raw_conclusion)
            conclusion_object = self.store.inspect_object(conclusion_object_digest)
        proposal = None
        proposal_object = None
        proposal_object_digest = data.get("completionProposalObjectDigest")
        if proposal_object_digest is not None:
            if not isinstance(proposal_object_digest, str):
                raise ValueError("Completion Proposal object reference is invalid")
            raw_proposal = self.store.get_object(
                proposal_object_digest, expected_kind="independent-completion-proposal"
            )
            if not isinstance(raw_proposal, dict):
                raise ValueError("Completion Proposal object is invalid")
            proposal = IndependentCompletionProposal.from_dict(raw_proposal)
            proposal_object = self.store.inspect_object(proposal_object_digest)
        conclusion_digest = data.get("conclusionDigest")
        if conclusion_digest is not None:
            if not isinstance(conclusion_digest, str):
                raise ValueError("Harness conclusion digest is invalid")
            _digest(conclusion_digest, "Harness conclusion digest")
        proposal_digest = data.get("completionProposalDigest")
        if proposal_digest is not None:
            if not isinstance(proposal_digest, str):
                raise ValueError("Completion Proposal digest is invalid")
            _digest(proposal_digest, "Completion Proposal digest")
        if (
            receipt.digest != data.get("runReceiptDigest")
            or trace.digest != data.get("traceDigest")
            or receipt.trace_digest != trace.digest
            or receipt.contract_digest != self.contract.digest
            or receipt.harness_run_id != self.contract.harness_run_id
            or receipt.conclusion_digest != conclusion_digest
            or (proposal_digest is not None) != (receipt.stop_reason == "completed")
        ):
            raise ValueError("independent terminal evidence bindings differ")
        if conclusion is not None and canonical_digest(conclusion.to_dict()) != conclusion_digest:
            raise ValueError("Harness conclusion differs from its digest")
        if (
            conclusion is None
            and conclusion_digest is not None
            and self.contract.privacy.allow_model_content
        ):
            raise ValueError("authorized Harness conclusion content is missing")
        if proposal is not None and (
            proposal.digest != proposal_digest
            or proposal.run_receipt_digest != receipt.digest
            or proposal.trace_digest != trace.digest
            or proposal.contract_digest != self.contract.digest
        ):
            raise ValueError("Completion Proposal bindings differ")
        if (
            proposal is None
            and proposal_digest is not None
            and self.contract.privacy.allow_model_content
        ):
            raise ValueError("authorized Completion Proposal content is missing")
        if not self.contract.privacy.allow_tool_content and observations:
            raise ValueError("metadata-only terminal evidence retained Tool content")
        if terminal.event_kind != self._terminal_event_kind(RunStopCode(receipt.termination_code)):
            raise ValueError("terminal Event kind differs from Run Receipt")
        return StoredIndependentRunResult(
            receipt=receipt,
            receipt_object=self.store.inspect_object(receipt_object_digest),
            trace=trace,
            trace_object=self.store.inspect_object(trace_object_digest),
            observations=observations,
            observations_object=self.store.inspect_object(observations_object_digest),
            conclusion=conclusion,
            conclusion_object=conclusion_object,
            completion_proposal=proposal,
            completion_proposal_object=proposal_object,
        )

    def record_recovery_assessment(
        self,
        *,
        trigger: str,
        grant_effect_class: str,
        catalog_status: str,
        workspace_status: str,
        workspace_evidence: dict[str, JsonValue],
        unresolved_unknowns: tuple[str, ...],
        created_at_ms: int | None = None,
    ) -> NativeRunRecoveryAssessment:
        events = self.store.list_run_events(self.contract.harness_run_id)
        sequence = 1 + sum(event.event_kind == _RECOVERY_EVENT_KIND for event in events)
        created = self.clock_ms() if created_at_ms is None else created_at_ms
        token = canonical_digest(
            {
                "harnessRunId": self.contract.harness_run_id,
                "sequence": sequence,
                "trigger": trigger,
                "bindingDigest": self.binding.digest,
            }
        )[7:31]
        assessment = NativeRunRecoveryAssessment(
            assessment_id=f"harness-run-recovery:{token}",
            sequence=sequence,
            harness_run_id=self.contract.harness_run_id,
            assignment_id=self.binding.assignment_id,
            assignment_generation=self.binding.assignment_generation,
            assignment_digest=self.binding.assignment_digest,
            trigger=trigger,
            grant_effect_class=grant_effect_class,
            catalog_status=catalog_status,
            workspace_status=workspace_status,
            workspace_evidence=workspace_evidence,
            unresolved_unknowns=unresolved_unknowns,
            created_at_ms=created,
        )
        now_ms = self._recorded_time(created)
        lease = self._acquire_lease("recovery", assessment.digest, now_ms=now_ms)
        try:
            stored = self.store.put_object(
                assessment.to_dict(), kind="native-run-recovery-assessment"
            )
            self.store.append_event(
                event_id=self._event_id("recovery", assessment.digest),
                harness_run_id=self.contract.harness_run_id,
                event_kind=_RECOVERY_EVENT_KIND,
                data={
                    "assessmentDigest": assessment.digest,
                    "assessmentObjectDigest": stored.digest,
                    "sequence": assessment.sequence,
                },
                expected_revision=lease.run_revision,
                recorded_at_ms=now_ms,
                lease=lease,
                lease_checked_at_ms=self.clock_ms(),
                caused_by_event_id=None if not events else events[-1].event_id,
                referenced_objects=(stored,),
            )
        finally:
            self.store.release_run_lease(lease)
        return assessment

    def load_latest_recovery_assessment(self) -> NativeRunRecoveryAssessment:
        event = next(
            (
                event
                for event in reversed(self.store.list_run_events(self.contract.harness_run_id))
                if event.event_kind == _RECOVERY_EVENT_KIND
            ),
            None,
        )
        if event is None:
            raise KeyError("Harness Run has no Recovery Assessment")
        raw = self.store.get_object(
            self._required_digest(event.data, "assessmentObjectDigest"),
            expected_kind="native-run-recovery-assessment",
        )
        if not isinstance(raw, dict):
            raise ValueError("Recovery Assessment object is invalid")
        assessment = NativeRunRecoveryAssessment.from_dict(raw)
        if (
            assessment.digest != event.data.get("assessmentDigest")
            or assessment.harness_run_id != self.contract.harness_run_id
            or assessment.assignment_id != self.binding.assignment_id
            or assessment.assignment_generation != self.binding.assignment_generation
            or assessment.assignment_digest != self.binding.assignment_digest
        ):
            raise ValueError("Recovery Assessment bindings differ")
        return assessment

    def doctor(self) -> dict[str, JsonValue]:
        trace_segments = 0
        recovery_assessments = 0
        terminal_results = 0
        for event in self.store.list_run_events(self.contract.harness_run_id):
            if event.event_kind == _TRACE_EVENT_KIND:
                raw = self.store.get_object(
                    self._required_digest(event.data, "traceObjectDigest"),
                    expected_kind="harness-trace",
                )
                if not isinstance(raw, dict):
                    raise ValueError("Harness Trace object is invalid")
                trace = HarnessTrace.from_dict(raw)
                if trace.digest != event.data.get("traceDigest"):
                    raise ValueError("Harness Trace Event digest differs")
                trace_segments += 1
            elif event.event_kind == _RECOVERY_EVENT_KIND:
                raw = self.store.get_object(
                    self._required_digest(event.data, "assessmentObjectDigest"),
                    expected_kind="native-run-recovery-assessment",
                )
                if not isinstance(raw, dict):
                    raise ValueError("Recovery Assessment object is invalid")
                assessment = NativeRunRecoveryAssessment.from_dict(raw)
                if assessment.digest != event.data.get("assessmentDigest"):
                    raise ValueError("Recovery Assessment Event digest differs")
                recovery_assessments += 1
            elif event.event_kind in _TERMINAL_EVENT_KINDS:
                self.load_terminal_result()
                terminal_results += 1
        return {
            "schemaVersion": 1,
            "kind": "ordivon.independent-run-doctor",
            "healthy": True,
            "harnessRunId": self.contract.harness_run_id,
            "traceSegments": trace_segments,
            "recoveryAssessments": recovery_assessments,
            "terminalResults": terminal_results,
        }

    def _combined_trace(self) -> HarnessTrace:
        combined: list[HarnessRunEvent] = []
        for event in self.store.list_run_events(self.contract.harness_run_id):
            if event.event_kind != _TRACE_EVENT_KIND:
                continue
            raw = self.store.get_object(
                self._required_digest(event.data, "traceObjectDigest"),
                expected_kind="harness-trace",
            )
            if not isinstance(raw, dict):
                raise ValueError("Harness Trace segment object is invalid")
            segment = HarnessTrace.from_dict(raw)
            if segment.digest != event.data.get("traceDigest"):
                raise ValueError("Harness Trace segment digest differs")
            for item in segment.events:
                combined.append(
                    HarnessRunEvent(
                        sequence=len(combined) + 1,
                        kind=item.kind,
                        occurred_at_ms=item.occurred_at_ms,
                        payload=item.payload,
                    )
                )
        if not combined:
            raise ValueError("independent terminal Run has no retained Trace segment")
        return HarnessTrace(self.contract.harness_run_id, tuple(combined))

    def _build_receipt(
        self,
        result: AgentLoopResult,
        started_at_ms: int,
        finished_at_ms: int,
        *,
        trace: HarnessTrace | None = None,
        conclusion_digest: str | None = None,
    ) -> IndependentHarnessRunReceipt:
        retained_trace = result.trace if trace is None else trace
        artifacts: dict[str, HarnessArtifactReference] = {}
        jobs: set[str] = set()
        for observation in result.observations:
            if observation.runtime_job_ref is not None:
                jobs.add(observation.runtime_job_ref)
            for item in observation.artifact_refs:
                converted = HarnessArtifactReference(item.ref, item.kind, item.digest)
                existing = artifacts.get(converted.ref)
                if existing is not None and existing != converted:
                    raise ValueError("one Artifact reference resolves to conflicting evidence")
                artifacts[converted.ref] = converted
        return IndependentHarnessRunReceipt(
            harness_run_id=self.contract.harness_run_id,
            caller_id=self.contract.caller_id,
            caller_run_ref=self.contract.caller_run_ref,
            contract_digest=self.contract.digest,
            harness_implementation_id=self.contract.harness_implementation_id,
            system_manifest_digest=self.contract.system_manifest_ref.digest,
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
            stop_reason=self._stop_reason(result.stop_code),
            termination_code=result.stop_code.value,
            trace_digest=retained_trace.digest,
            context_digests=tuple(item.digest for item in self.contract.context_refs),
            tool_catalog_digest=self.contract.tool_catalog_digest,
            tool_grant_digest=self.contract.tool_grant_digest,
            runtime_job_refs=tuple(sorted(jobs)),
            artifact_refs=tuple(artifacts[key] for key in sorted(artifacts)),
            usage=result.usage,
            conclusion_digest=(
                conclusion_digest
                if conclusion_digest is not None
                else None if result.conclusion is None
                else canonical_digest(result.conclusion.to_dict())
            ),
        )

    def _build_completion_proposal(
        self,
        receipt: IndependentHarnessRunReceipt,
        result: AgentLoopResult,
        created_at_ms: int,
    ) -> IndependentCompletionProposal | None:
        if result.stop_code is not RunStopCode.CANDIDATE_COMPLETED:
            return None
        conclusion = result.conclusion
        if conclusion is None or conclusion.status != "candidate_completed":
            raise ValueError("candidate-completed Run omitted its candidate conclusion")
        token = canonical_digest(
            {
                "harnessRunId": self.contract.harness_run_id,
                "contractDigest": self.contract.digest,
                "runReceiptDigest": receipt.digest,
                "traceDigest": receipt.trace_digest,
            }
        )[7:31]
        return IndependentCompletionProposal(
            completion_proposal_id=f"completion-proposal:{token}",
            harness_run_id=self.contract.harness_run_id,
            caller_id=self.contract.caller_id,
            caller_run_ref=self.contract.caller_run_ref,
            contract_digest=self.contract.digest,
            run_receipt_digest=receipt.digest,
            trace_digest=receipt.trace_digest,
            summary=conclusion.summary,
            evidence_refs=conclusion.evidence_refs,
            artifact_refs=conclusion.artifact_refs,
            unresolved_unknowns=conclusion.unresolved_unknowns,
            usage=result.usage,
            created_at_ms=created_at_ms,
        )

    @staticmethod
    def _terminal_data(
        result: AgentLoopResult,
        receipt: IndependentHarnessRunReceipt,
        receipt_object: StoredHarnessObject,
        trace: HarnessTrace,
        trace_object: StoredHarnessObject,
        observations_object: StoredHarnessObject,
        conclusion_digest: str | None,
        conclusion_object: StoredHarnessObject | None,
        proposal: IndependentCompletionProposal | None,
        proposal_object: StoredHarnessObject | None,
    ) -> dict[str, JsonValue]:
        return {
            "stopCode": result.stop_code.value,
            "runReceiptDigest": receipt.digest,
            "runReceiptObjectDigest": receipt_object.digest,
            "traceDigest": trace.digest,
            "traceObjectDigest": trace_object.digest,
            "observationsObjectDigest": observations_object.digest,
            "conclusionDigest": conclusion_digest,
            "conclusionObjectDigest": None if conclusion_object is None else conclusion_object.digest,
            "completionProposalDigest": None if proposal is None else proposal.digest,
            "completionProposalObjectDigest": (
                None if proposal_object is None else proposal_object.digest
            ),
        }

    @staticmethod
    def _terminal_event_kind(code: RunStopCode) -> str:
        if code is RunStopCode.CANDIDATE_COMPLETED:
            return "harness.run-completed"
        if code in _FAILED_CODES:
            return "harness.run-failed"
        return "harness.run-stopped"

    @staticmethod
    def _stop_reason(code: RunStopCode) -> str:
        if code is RunStopCode.CANDIDATE_COMPLETED:
            return "completed"
        if code in _FAILED_CODES:
            return "failed"
        if code in _UNKNOWN_CODES:
            return "unknown"
        return "stopped"

    def _acquire_lease(self, operation: str, token: str, *, now_ms: int):
        owner = canonical_digest(
            {
                "harnessRunId": self.contract.harness_run_id,
                "operation": operation,
                "token": token,
            }
        )[7:31]
        return self.store.acquire_run_lease(
            self.contract.harness_run_id,
            owner_id=f"{self._execution_owner_id}:{operation}:{owner}",
            ttl_ms=_STORE_LEASE_TTL_MS,
            now_ms=now_ms,
        )

    def _recorded_time(self, proposed: int) -> int:
        events = self.store.list_run_events(self.contract.harness_run_id)
        return max(proposed, events[-1].recorded_at_ms if events else proposed)

    @staticmethod
    def _event_id(label: str, digest: str) -> str:
        return f"event:independent-{label}:{digest[7:31]}"

    @staticmethod
    def _required_digest(data: dict[str, JsonValue], field: str) -> str:
        value = data.get(field)
        if not isinstance(value, str):
            raise ValueError(f"Harness Event {field} is missing")
        return _digest(value, f"Harness Event {field}")


__all__ = [
    "IndependentCompletionProposal",
    "IndependentHarnessRunReceipt",
    "IndependentRunRecorder",
    "StoredIndependentRunResult",
]

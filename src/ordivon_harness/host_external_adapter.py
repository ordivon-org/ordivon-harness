from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .core_contracts import HarnessRunContract
from .independent_result import IndependentRunRecorder
from .ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from .sqlite_store import SQLiteHarnessStore
from .standalone import StandaloneHarnessExecution
from .store import HarnessRunProjection, HarnessRunStatus


class HostExternalRequestView(Protocol):
    request_id: str
    adapter_id: str
    task_id: str
    task_attempt_ref: str
    contract_digest: str
    correlation_context: dict[str, JsonValue]
    created_at_ms: int


class HarnessExternalRunDriver(Protocol):
    def execute(self) -> StandaloneHarnessExecution: ...


class HarnessExternalContractResolver(Protocol):
    def __call__(self, request: HostExternalRequestView) -> HarnessRunContract: ...


class HarnessExternalDriverFactory(Protocol):
    def __call__(
        self,
        contract: HarnessRunContract,
        continuity: SQLiteHarnessRunContinuityStore,
    ) -> HarnessExternalRunDriver: ...


class HarnessExternalStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OrdivonHarnessExternalObservation:
    foreign_run_ref: str
    status: HarnessExternalStatus
    revision: int
    evidence_refs: tuple[str, ...]
    observed_at_ms: int
    metadata: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if not self.foreign_run_ref or self.foreign_run_ref != self.foreign_run_ref.strip():
            raise ValueError("foreign Harness Run reference must be non-empty and trimmed")
        if self.revision < 0 or self.observed_at_ms < 0:
            raise ValueError("foreign Harness observation revision and time are invalid")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("foreign Harness evidence references must be unique")
        validate_json_value(self.metadata)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.external-run-observation",
            "foreignRunRef": self.foreign_run_ref,
            "status": self.status.value,
            "revision": self.revision,
            "evidenceRefs": list(self.evidence_refs),
            "observedAtMs": self.observed_at_ms,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class OrdivonHarnessExternalCompletionProposal:
    proposal_id: str
    foreign_run_ref: str
    contract_digest: str
    summary: str
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    created_at_ms: int
    metadata: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if not self.proposal_id.startswith("completion-proposal:"):
            raise ValueError("Completion Proposal identity is invalid")
        if not self.foreign_run_ref or self.foreign_run_ref != self.foreign_run_ref.strip():
            raise ValueError("Completion Proposal foreign Run reference is invalid")
        if len(self.contract_digest) != 71 or not self.contract_digest.startswith("sha256:"):
            raise ValueError("Completion Proposal contract digest is invalid")
        if not self.summary or self.summary != self.summary.strip():
            raise ValueError("Completion Proposal summary is invalid")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("Completion Proposal evidence references must be unique")
        if len(self.artifact_refs) != len(set(self.artifact_refs)):
            raise ValueError("Completion Proposal Artifact references must be unique")
        if self.created_at_ms < 0:
            raise ValueError("Completion Proposal creation time is invalid")
        validate_json_value(self.metadata)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.external-completion-proposal",
            "proposalId": self.proposal_id,
            "foreignRunRef": self.foreign_run_ref,
            "contractDigest": self.contract_digest,
            "summary": self.summary,
            "evidenceRefs": list(self.evidence_refs),
            "artifactRefs": list(self.artifact_refs),
            "createdAtMs": self.created_at_ms,
            "metadata": self.metadata,
        }


class OrdivonHarnessExternalExecutorAdapter:
    """Expose independent Harness authority through Host's foreign-Run port.

    The adapter is deliberately duck-typed against the Host protocol so the base
    Harness package remains Host-free. It writes only the Harness Journal/CAS and
    returns external observation/proposal wire values; Host retains its own request
    and binding history independently.
    """

    adapter_id = "external-executor:ordivon-harness"

    def __init__(
        self,
        state_root: str | Path,
        *,
        contract_resolver: HarnessExternalContractResolver,
        driver_factory: HarnessExternalDriverFactory,
        clock_ms,
    ) -> None:
        self.state_root = Path(state_root)
        self.contract_resolver = contract_resolver
        self.driver_factory = driver_factory
        self.clock_ms = clock_ms

    def start(self, request: HostExternalRequestView) -> OrdivonHarnessExternalObservation:
        self._validate_request(request)
        contract = self.contract_resolver(request)
        self._validate_contract(request, contract)
        with self._open_store() as store:
            try:
                projection = store.load_run(contract.harness_run_id)
            except KeyError:
                store.create_run(contract)
                projection = store.load_run(contract.harness_run_id)
            else:
                if (
                    projection.contract_digest != contract.digest
                    or projection.caller_id != contract.caller_id
                    or projection.caller_run_ref != contract.caller_run_ref
                ):
                    raise ValueError(
                        "existing Harness Run differs from resolved Host request contract"
                    )
            if not projection.status.terminal and projection.status is not HarnessRunStatus.PAUSED:
                continuity = SQLiteHarnessRunContinuityStore.open(
                    store,
                    contract.harness_run_id,
                    clock_ms=self.clock_ms,
                )
                self.driver_factory(contract, continuity).execute()
                projection = store.load_run(contract.harness_run_id)
            return self._observation(store, projection)

    def observe(self, foreign_run_ref: str) -> OrdivonHarnessExternalObservation:
        with self._open_store(existing=True) as store:
            projection = store.load_run(foreign_run_ref)
            return self._observation(store, projection)

    def cancel(
        self,
        foreign_run_ref: str,
        request_id: str,
    ) -> OrdivonHarnessExternalObservation:
        with self._open_store(existing=True) as store:
            projection = store.load_run(foreign_run_ref)
            continuity = SQLiteHarnessRunContinuityStore.open(
                store,
                foreign_run_ref,
                clock_ms=self.clock_ms,
            )
            if continuity.contract.caller_run_ref != request_id:
                raise ValueError("Host cancellation request differs from Harness caller binding")
            if not projection.status.terminal:
                recorder = IndependentRunRecorder(
                    store,
                    continuity.contract,
                    continuity.binding,
                    clock_ms=self.clock_ms,
                )
                assessment = recorder.record_recovery_assessment(
                    trigger="operator_cancelled",
                    grant_effect_class="unknown",
                    catalog_status="matched",
                    workspace_status="unknown",
                    workspace_evidence={"cancellationRequested": True},
                    unresolved_unknowns=(
                        "cancellation intent is retained; foreign work may still require reconciliation",
                    ),
                )
                projection = store.load_run(foreign_run_ref)
                observation = self._observation(store, projection)
                return OrdivonHarnessExternalObservation(
                    foreign_run_ref=observation.foreign_run_ref,
                    status=HarnessExternalStatus.UNKNOWN,
                    revision=observation.revision,
                    evidence_refs=tuple(
                        sorted(set(observation.evidence_refs + (assessment.digest,)))
                    ),
                    observed_at_ms=projection.updated_at_ms,
                    metadata={
                        **observation.metadata,
                        "cancellationRequested": True,
                        "recoveryAssessmentDigest": assessment.digest,
                    },
                )
            return self._observation(store, projection)

    def recover(
        self,
        request: HostExternalRequestView,
        foreign_run_ref: str | None,
    ) -> OrdivonHarnessExternalObservation:
        self._validate_request(request)
        contract = self.contract_resolver(request)
        self._validate_contract(request, contract)
        if foreign_run_ref is not None and foreign_run_ref != contract.harness_run_id:
            raise ValueError("Host foreign Run binding differs from resolved Harness Run")
        with self._open_store(existing=True) as store:
            projection = store.load_run(contract.harness_run_id)
            if not projection.status.terminal:
                continuity = SQLiteHarnessRunContinuityStore.open(
                    store,
                    contract.harness_run_id,
                    clock_ms=self.clock_ms,
                )
                recorder = IndependentRunRecorder(
                    store,
                    contract,
                    continuity.binding,
                    clock_ms=self.clock_ms,
                )
                assessment = recorder.record_recovery_assessment(
                    trigger="host_restart",
                    grant_effect_class="unknown",
                    catalog_status="matched",
                    workspace_status="unknown",
                    workspace_evidence={
                        "hostRequestId": request.request_id,
                        "foreignRunRef": foreign_run_ref,
                    },
                    unresolved_unknowns=(
                        "foreign Run recovery has not reconciled Provider, Tool, or Workspace state",
                    ),
                )
                projection = store.load_run(contract.harness_run_id)
                observation = self._observation(store, projection)
                return OrdivonHarnessExternalObservation(
                    foreign_run_ref=observation.foreign_run_ref,
                    status=observation.status,
                    revision=observation.revision,
                    evidence_refs=tuple(
                        sorted(set(observation.evidence_refs + (assessment.digest,)))
                    ),
                    observed_at_ms=projection.updated_at_ms,
                    metadata={
                        **observation.metadata,
                        "recoveryAssessmentDigest": assessment.digest,
                    },
                )
            return self._observation(store, projection)

    def collect_completion(
        self,
        foreign_run_ref: str,
    ) -> OrdivonHarnessExternalCompletionProposal | None:
        with self._open_store(existing=True) as store:
            projection = store.load_run(foreign_run_ref)
            if not projection.status.terminal:
                return None
            continuity = SQLiteHarnessRunContinuityStore.open(
                store,
                foreign_run_ref,
                clock_ms=self.clock_ms,
            )
            retained = IndependentRunRecorder(
                store,
                continuity.contract,
                continuity.binding,
                clock_ms=self.clock_ms,
            ).load_terminal_result()
            proposal = retained.completion_proposal
            if proposal is None:
                return None
            return OrdivonHarnessExternalCompletionProposal(
                proposal_id=proposal.completion_proposal_id,
                foreign_run_ref=foreign_run_ref,
                contract_digest=proposal.contract_digest,
                summary=proposal.summary,
                evidence_refs=tuple(
                    sorted(
                        set(
                            proposal.evidence_refs
                            + (retained.receipt.digest, retained.trace.digest)
                        )
                    )
                ),
                artifact_refs=proposal.artifact_refs,
                created_at_ms=proposal.created_at_ms,
                metadata={
                    "harnessRunReceiptDigest": retained.receipt.digest,
                    "harnessTraceDigest": retained.trace.digest,
                    "harnessCompletionProposalDigest": proposal.digest,
                },
            )

    def _observation(
        self,
        store: SQLiteHarnessStore,
        projection: HarnessRunProjection,
    ) -> OrdivonHarnessExternalObservation:
        evidence: list[str] = [projection.contract_digest]
        metadata: dict[str, JsonValue] = {
            "harnessRunId": projection.harness_run_id,
            "harnessStatus": projection.status.value,
            "contractDigest": projection.contract_digest,
            "terminalEventId": projection.terminal_event_id,
        }
        if projection.status.terminal:
            continuity = SQLiteHarnessRunContinuityStore.open(
                store,
                projection.harness_run_id,
                clock_ms=self.clock_ms,
            )
            try:
                retained = IndependentRunRecorder(
                    store,
                    continuity.contract,
                    continuity.binding,
                    clock_ms=self.clock_ms,
                ).load_terminal_result()
            except KeyError:
                pass
            else:
                evidence.extend((retained.receipt.digest, retained.trace.digest))
                metadata["runReceiptDigest"] = retained.receipt.digest
                metadata["traceDigest"] = retained.trace.digest
                if retained.completion_proposal is not None:
                    metadata["completionProposalDigest"] = retained.completion_proposal.digest
        return OrdivonHarnessExternalObservation(
            foreign_run_ref=projection.harness_run_id,
            status=self._status(projection.status),
            revision=projection.revision,
            evidence_refs=tuple(sorted(set(evidence))),
            observed_at_ms=projection.updated_at_ms,
            metadata=metadata,
        )

    def _open_store(self, *, existing: bool = False) -> SQLiteHarnessStore:
        database = self.state_root / "harness.sqlite3"
        if database.exists():
            return SQLiteHarnessStore(self.state_root)
        if existing:
            raise FileNotFoundError(
                f"Harness state root is not initialized: {self.state_root}"
            )
        return SQLiteHarnessStore.initialize(self.state_root)

    def _validate_request(self, request: HostExternalRequestView) -> None:
        if request.adapter_id != self.adapter_id:
            raise ValueError(
                f"Host external Adapter is {request.adapter_id}, expected {self.adapter_id}"
            )
        validate_json_value(request.correlation_context)

    @staticmethod
    def _validate_contract(
        request: HostExternalRequestView,
        contract: HarnessRunContract,
    ) -> None:
        if contract.digest != request.contract_digest:
            raise ValueError("resolved Harness Run Contract digest differs from Host request")
        if contract.caller_run_ref != request.request_id:
            raise ValueError("Harness caller Run reference must equal Host external request")

    @staticmethod
    def _status(status: HarnessRunStatus) -> HarnessExternalStatus:
        return {
            HarnessRunStatus.CREATED: HarnessExternalStatus.STARTING,
            HarnessRunStatus.ACTIVE: HarnessExternalStatus.RUNNING,
            HarnessRunStatus.PAUSED: HarnessExternalStatus.WAITING,
            HarnessRunStatus.STOPPED: HarnessExternalStatus.UNKNOWN,
            HarnessRunStatus.COMPLETED: HarnessExternalStatus.COMPLETED,
            HarnessRunStatus.FAILED: HarnessExternalStatus.FAILED,
        }[status]


__all__ = [
    "HarnessExternalContractResolver",
    "HarnessExternalDriverFactory",
    "HarnessExternalRunDriver",
    "HarnessExternalStatus",
    "HostExternalRequestView",
    "OrdivonHarnessExternalCompletionProposal",
    "OrdivonHarnessExternalExecutorAdapter",
    "OrdivonHarnessExternalObservation",
]

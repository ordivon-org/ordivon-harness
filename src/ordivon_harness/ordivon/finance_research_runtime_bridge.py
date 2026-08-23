"""Finance-owned semantic research lowered through one source-fenced Runtime owner Job.

Finance owns ResearchRunSpec meaning, point-in-time materialization, contained experiment
execution and research-result admission. Harness owns durable Agent/Tool continuity and the
outer source fence. Runtime remains the generic physical execution/recovery substrate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from ..agent_tool_observation import HarnessToolObservation
from ..core_contracts import HarnessRunContract
from ..execution_binding import HarnessExecutionBinding, build_harness_workspace_exec_request_from_binding
from ..protocol import HarnessRecoveryConsequence
from ..runtime_port import HarnessRuntimeClient
from .model import AgentToolCall, AgentToolDefinition
from .run_store_port import HarnessRunContinuityStore
from .sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind

_MAX_OWNER_STDOUT_BYTES = 2_000_000
_MAX_PROJECTED_RESULT_BYTES = 128_000

_RESEARCH_RUN_SPEC_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "required": ["schemaVersion", "experimentId", "question", "program", "inputs", "parameters", "extensions"],
    "properties": {
        "schemaVersion": {"const": 0},
        "experimentId": {"type": "string", "minLength": 1},
        "question": {"type": "string", "minLength": 1},
        "program": {"type": "string", "minLength": 1},
        "inputs": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "required": ["alias", "dataset", "datasetVersion"],
                "properties": {
                    "alias": {"type": "string", "minLength": 1},
                    "dataset": {"type": "string", "minLength": 1},
                    "datasetVersion": {"type": "integer", "minimum": 0},
                    "asOf": {"type": ["string", "null"]},
                    "knowledgeTimeField": {"type": "string"},
                    "latestBy": {"type": "array", "items": {"type": "string"}},
                    "latestOrderField": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "parameters": {"type": "object"},
        "extensions": {"type": "object"},
    },
    "additionalProperties": False,
}

FINANCE_RESEARCH_DEFINITION = AgentToolDefinition(
    name="finance_research",
    description=(
        "Finance owner research: run one point-in-time, evidence-bound Finance experiment. "
        "Supply only ResearchRunSpec v0. Runtime, immutable-input authority, trusted Runner, "
        "source revision and admission machinery remain environment-owned and are not Tool arguments."
    ),
    input_schema={
        "type": "object",
        "required": ["researchRunSpec"],
        "properties": {"researchRunSpec": _RESEARCH_RUN_SPEC_SCHEMA},
        "additionalProperties": False,
    },
)

FINANCE_RESEARCH_TOOL_SURFACE: dict[str, JsonValue] = {
    "schemaVersion": 0,
    "kind": "ordivon.finance-research-tool-surface-experimental",
    "owner": "ordivon-finance",
    "tools": [FINANCE_RESEARCH_DEFINITION.to_dict()],
}
FINANCE_RESEARCH_TOOL_SURFACE_DIGEST = canonical_digest(FINANCE_RESEARCH_TOOL_SURFACE)


def _text(value: Any, label: str, *, max_bytes: int = 2048) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _digest(value: Any, label: str) -> str:
    text = _text(value, label, max_bytes=80)
    if len(text) != 71 or not text.startswith("sha256:") or any(c not in "0123456789abcdef" for c in text[7:]):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return text


def _absolute_path(value: Any, label: str) -> str:
    text = _text(value, label)
    path = PurePosixPath(text)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be an absolute normalized POSIX path")
    return text


@dataclass(frozen=True, slots=True)
class FinanceResearchRuntimeGrant:
    """Caller-fenced outer Finance source plus deployment-owned inner research equipment."""

    workspace_ref: str
    source_revision: str
    source_state_digest: str
    finance_state_root: str
    finance_state_db: str
    finance_app_python: str
    research_runner_workspace_ref: str
    research_input_authority: str
    research_materialization_root: str
    research_runner_executable: str
    research_trusted_implementation_digest: str

    def __post_init__(self) -> None:
        _text(self.workspace_ref, "Finance owner Runtime Workspace")
        _text(self.source_revision, "Finance source revision")
        _digest(self.source_state_digest, "Finance source-state digest")
        _absolute_path(self.finance_state_root, "Finance state root")
        _absolute_path(self.finance_state_db, "Finance state DB")
        _absolute_path(self.finance_app_python, "Finance application Python")
        _text(self.research_runner_workspace_ref, "Finance research Runner Workspace")
        if self.research_runner_workspace_ref == self.workspace_ref:
            raise ValueError("Finance owner and research Runner Workspaces must be distinct")
        _text(self.research_input_authority, "Finance research InputAuthority")
        _absolute_path(self.research_materialization_root, "Finance research materialization root")
        _absolute_path(self.research_runner_executable, "Finance research Runner executable")
        _digest(self.research_trusted_implementation_digest, "Finance trusted research implementation digest")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 0,
            "kind": "ordivon.finance-research-runtime-grant-experimental",
            "owner": "ordivon-finance",
            "tools": [FINANCE_RESEARCH_DEFINITION.name],
            "runtimeOperations": ["workspace.exec"],
            "effectClass": "canonical-research-evidence-no-capital-effect",
            "progressClass": "research-evidence",
            "workspaceRef": self.workspace_ref,
            "sourceRevision": self.source_revision,
            "sourceStateDigest": self.source_state_digest,
            "financeStateRoot": self.finance_state_root,
            "financeStateDb": self.finance_state_db,
            "financeAppPython": self.finance_app_python,
            "researchRunnerWorkspaceRef": self.research_runner_workspace_ref,
            "researchInputAuthority": self.research_input_authority,
            "researchMaterializationRoot": self.research_materialization_root,
            "researchRunnerExecutable": self.research_runner_executable,
            "researchTrustedImplementationDigest": self.research_trusted_implementation_digest,
            "providerCredentialAllowed": False,
            "externalNetworkAllowedFromExperiment": False,
            "financialWriteAllowed": False,
            "decisionMutationAllowed": False,
            "authorityExpansionAllowed": False,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


class SQLiteHarnessFinanceResearchRuntimeBridge(SQLiteHarnessRuntimeBridge):
    """Compile one Finance semantic research Tool call into exact durable Runtime execution."""

    recovery_consequence = HarnessRecoveryConsequence.PROCESS_OR_EXTERNAL_EFFECT_POSSIBLE
    observation_only_tool_names = frozenset()

    def __init__(
        self,
        contract: HarnessRunContract,
        run_store: HarnessRunContinuityStore,
        execution_binding: HarnessExecutionBinding,
        runtime: HarnessRuntimeClient,
        grant: FinanceResearchRuntimeGrant,
        *,
        provider_source=None,
        provider_holder_id: str | None = None,
    ) -> None:
        if execution_binding.workspace_ref != grant.workspace_ref:
            raise ValueError("Finance research grant Workspace differs from Harness Execution Binding")
        super().__init__(
            contract, run_store, execution_binding, runtime,
            provider_source=provider_source,
            provider_holder_id=provider_holder_id,
            tool_definitions=(FINANCE_RESEARCH_DEFINITION,),
            tool_surface_digest=FINANCE_RESEARCH_TOOL_SURFACE_DIGEST,
            tool_grant_digest=grant.digest,
        )
        self.finance_grant = grant

    def _lower_runtime_tool_call(self, call: AgentToolCall, *, step_id: str) -> tuple[str, dict[str, JsonValue], str | None]:
        if call.name != FINANCE_RESEARCH_DEFINITION.name:
            raise ToolBridgeError(f"Finance research bridge does not expose {call.name}", kind=ToolBridgeErrorKind.MODEL_CORRECTABLE)
        arguments = dict(call.arguments)
        if set(arguments) != {"researchRunSpec"} or not isinstance(arguments.get("researchRunSpec"), dict):
            raise ToolBridgeError("finance_research requires only one researchRunSpec object", kind=ToolBridgeErrorKind.MODEL_CORRECTABLE)
        research_spec = arguments["researchRunSpec"]
        validate_json_value(research_spec)
        semantic_call_id = "harness-finance-research:" + canonical_digest({
            "harnessRunId": self.contract.harness_run_id,
            "stepId": step_id,
            "toolCallDigest": call.digest,
        })[7:39]
        owner_arguments = json.dumps({"researchRunSpec": research_spec}, sort_keys=True, separators=(",", ":"))
        try:
            request = build_harness_workspace_exec_request_from_binding(
                self.execution_binding,
                step_id=step_id,
                executable="/usr/bin/node",
                args=("scripts/finance-domain.mjs", "call", "--operation", "finance.research", "--arguments-json", owner_arguments),
                cwd_relative=".",
                env={
                    "ORDIVON_FINANCE_STATE_ROOT": self.finance_grant.finance_state_root,
                    "ORDIVON_FINANCE_STATE_DB": self.finance_grant.finance_state_db,
                    "ORDIVON_FINANCE_APP_PYTHON": self.finance_grant.finance_app_python,
                    "ORDIVON_FINANCE_RESEARCH_OWNER_WORKSPACE": self.finance_grant.workspace_ref,
                    "ORDIVON_FINANCE_RESEARCH_RUNNER_WORKSPACE": self.finance_grant.research_runner_workspace_ref,
                    "ORDIVON_FINANCE_RESEARCH_TRUSTED_SOURCE_REVISION": self.finance_grant.source_revision,
                    "ORDIVON_FINANCE_RESEARCH_TRUSTED_IMPLEMENTATION_DIGEST": self.finance_grant.research_trusted_implementation_digest,
                    "ORDIVON_FINANCE_RESEARCH_RUNNER_EXECUTABLE": self.finance_grant.research_runner_executable,
                    "ORDIVON_FINANCE_RESEARCH_CALL_ID": semantic_call_id,
                    "ORDIVON_FINANCE_RESEARCH_INPUT_AUTHORITY": self.finance_grant.research_input_authority,
                    "ORDIVON_FINANCE_RESEARCH_MATERIALIZATION_ROOT": self.finance_grant.research_materialization_root,
                },
                timeout_ms=300_000,
                stdout_limit_bytes=_MAX_OWNER_STDOUT_BYTES,
                stderr_limit_bytes=524_288,
                wait_ms=0,
                stdout_tail_bytes=65_536,
                stderr_tail_bytes=16_384,
            )
        except ValueError as error:
            raise ToolBridgeError(str(error), kind=ToolBridgeErrorKind.PROTOCOL_INVALID) from error
        request_id = request.get("clientRequestId")
        if not isinstance(request_id, str):
            raise ToolBridgeError("Finance research Runtime request omitted clientRequestId", kind=ToolBridgeErrorKind.PROTOCOL_INVALID)
        return "workspace.exec", request, request_id

    def _owner_stdout(self, payload: dict[str, JsonValue]) -> str:
        tail = payload.get("stdoutTail")
        if not isinstance(tail, str):
            raise TypeError("Runtime result omitted Finance research stdoutTail")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            return tail
        candidates = [x for x in artifacts if isinstance(x, dict) and x.get("kind") == "stdout"]
        if len(candidates) != 1:
            return tail
        artifact = candidates[0]
        if artifact.get("truncated") is True:
            raise ValueError("Finance research owner stdout was truncated by Runtime")
        retained = artifact.get("retainedBytes")
        if type(retained) is not int or retained <= len(tail.encode("utf-8")):
            return tail
        if retained > _MAX_OWNER_STDOUT_BYTES:
            raise ValueError("Finance research owner stdout exceeded the bridge retention bound")
        artifact_id, digest, job_id = artifact.get("artifactId"), artifact.get("digest"), payload.get("jobId")
        if not all(isinstance(v, str) for v in (artifact_id, digest, job_id)):
            raise ValueError("Finance research stdout Artifact identity is incomplete")
        chunks: list[str] = []
        offset = 0
        while offset < retained:
            read = self.runtime.call_tool("artifact.read", {
                "schemaVersion": 1, "jobId": job_id, "artifactId": artifact_id,
                "offset": offset, "maxBytes": min(262_144, retained - offset),
            })
            content, next_offset = read.get("content"), read.get("nextOffset")
            if not isinstance(content, str) or type(next_offset) is not int or next_offset <= offset:
                raise ValueError("Finance research stdout Artifact read did not advance")
            chunks.append(content); offset = next_offset
            if read.get("eof") is True:
                break
        content = "".join(chunks)
        if offset != retained or read.get("eof") is not True or read.get("digest") != digest:
            raise ValueError("Finance research stdout Artifact read did not verify")
        return content

    @staticmethod
    def _project_result(value: Any) -> tuple[Any, bool, str | None]:
        if value is None:
            return None, False, None
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        if len(encoded) > _MAX_PROJECTED_RESULT_BYTES:
            return None, True, digest
        return value, False, digest

    def _observation_from_payload(
        self, *, tool_call_id: str, tool_name: str, payload: dict[str, JsonValue],
        query: str | None, relative_path: str | None, reconciled: bool,
    ) -> HarnessToolObservation:
        if tool_name != FINANCE_RESEARCH_DEFINITION.name:
            return super()._observation_from_payload(
                tool_call_id=tool_call_id, tool_name=tool_name, payload=payload,
                query=query, relative_path=relative_path, reconciled=reconciled,
            )
        job_id = payload.get("jobId")
        runtime_job_ref = job_id if isinstance(job_id, str) else None
        try:
            owner_stdout = self._owner_stdout(payload)
            finance = json.loads(owner_stdout)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            return self._invalid(tool_call_id, tool_name, str(error), payload, reconciled)
        if not isinstance(finance, dict):
            return self._invalid(tool_call_id, tool_name, "Finance research owner result was not an object", payload, reconciled)
        envelope_digest = "sha256:" + hashlib.sha256(owner_stdout.encode("utf-8")).hexdigest()
        if finance.get("ok") is False:
            error = finance.get("error")
            if finance.get("kind") != "ordivon.finance.runtime-domain-error" or finance.get("externalFinancialWriteAttempted") is not False or not isinstance(error, dict):
                return self._invalid(tool_call_id, tool_name, "Finance research owner error violated fail-closed contract", payload, reconciled)
            structured: dict[str, JsonValue] = {
                "schemaVersion": 0, "kind": "ordivon.harness-finance-research-owner-outcome-experimental",
                "truthRole": "bounded-projection-of-source-fenced-finance-research-owner-outcome",
                "owner": "ordivon-finance", "ownerOutcome": "blocked", "ownerEnvelopeDigest": envelope_digest,
                "ownerError": {k: error.get(k) for k in ("code", "type", "message")},
                "effectBoundary": {"externalFinancialWriteAttempted": False, "financialSubmissionAttempted": False, "authorityExpanded": False},
                "runtime": {"jobId": runtime_job_ref, "executionDisposition": payload.get("executionDisposition"), "deliveryDisposition": payload.get("deliveryDisposition"), "recoveryRequired": payload.get("recoveryRequired")},
            }
            validate_json_value(structured)
            return HarnessToolObservation(tool_call_id=tool_call_id, tool_name=tool_name, status="observed", structured_content=structured, runtime_job_ref=runtime_job_ref, artifact_refs=self._extract_artifacts(payload), reconciled=reconciled)

        effect, result = finance.get("effectContract"), finance.get("result")
        valid = (
            finance.get("kind") == "ordivon.finance.runtime-domain-result"
            and finance.get("domain") == "finance" and finance.get("operation") == "finance.research"
            and finance.get("interfaceVersion") == 3 and finance.get("ok") is True
            and isinstance(effect, dict) and effect.get("owner") == "ordivon-finance"
            and effect.get("effectClass") == "CANONICAL_RESEARCH" and effect.get("credentialAccess") == "none"
            and effect.get("externalWorldRead") is False and effect.get("externalFinancialWrite") is False
            and effect.get("financialSubmission") is False and effect.get("authorityMutation") is False
            and isinstance(result, dict) and result.get("kind") == "ordivon.finance.semantic-research-result"
            and result.get("status") in {"observed", "rejected", "unknown"}
        )
        if not valid:
            return self._invalid(tool_call_id, tool_name, "Finance research result violated its owner/effect contract", payload, reconciled)
        consumer = result.get("consumerStanding")
        if not isinstance(consumer, dict) or any(consumer.get(k) is not False for k in (
            "decisionMutation", "proposalMutation", "externalEffectMutation", "capitalLedgerMutation",
            "externalWorldRead", "venueCredentialAccess", "externalFinancialWriteAttempted",
            "financialSubmissionAttempted", "authorityMutation",
        )):
            return self._invalid(tool_call_id, tool_name, "Finance research consumer standing violated the no-capital/no-external-effect boundary", payload, reconciled)

        projected_result, omitted, result_digest = self._project_result(result.get("result"))
        projection: dict[str, JsonValue] = {
            "status": result.get("status"), "evidenceRef": result.get("evidenceRef"),
            "experimentId": result.get("experimentId"), "semanticResultDigest": result.get("semanticResultDigest"),
            "sourceStateVersion": result.get("sourceStateVersion"), "materializationId": result.get("materializationId"),
            "innerRuntimeJobId": result.get("runtimeJobId"), "innerRuntimeAttemptId": result.get("runtimeAttemptId"),
            "admissionCapability": result.get("admissionCapability"), "replayed": result.get("replayed"),
            "stateVersionBefore": result.get("stateVersionBefore"), "stateVersionAfter": result.get("stateVersionAfter"),
            "result": projected_result, "resultOmittedByHarnessBound": omitted, "resultDigest": result_digest,
        }
        structured = {
            "schemaVersion": 0, "kind": "ordivon.harness-finance-research-observation-experimental",
            "truthRole": "bounded-projection-of-source-fenced-finance-owner-research",
            "owner": "ordivon-finance",
            "sourceFence": {"workspaceRef": self.finance_grant.workspace_ref, "sourceRevisionExpected": self.finance_grant.source_revision, "sourceStateDigestExpected": self.finance_grant.source_state_digest},
            "ownerEnvelopeDigest": envelope_digest, "financeProjection": projection,
            "effectBoundary": {
                "canonicalResearchStateMayMutate": True, "decisionMutation": False, "proposalMutation": False,
                "externalEffectMutation": False, "capitalLedgerMutation": False, "externalWorldRead": False,
                "externalFinancialWrite": False, "financialSubmission": False, "authorityMutation": False,
            },
            "runtime": {"jobId": runtime_job_ref, "executionDisposition": payload.get("executionDisposition"), "deliveryDisposition": payload.get("deliveryDisposition"), "recoveryRequired": payload.get("recoveryRequired")},
        }
        validate_json_value(structured)
        harness_status = "unknown" if result.get("status") == "unknown" else "observed"
        return HarnessToolObservation(tool_call_id=tool_call_id, tool_name=tool_name, status=harness_status, structured_content=structured, runtime_job_ref=runtime_job_ref, artifact_refs=self._extract_artifacts(payload), reconciled=reconciled)

    def _invalid(self, tool_call_id: str, tool_name: str, reason: str, payload: dict[str, JsonValue], reconciled: bool) -> HarnessToolObservation:
        job_id = payload.get("jobId")
        return HarnessToolObservation(
            tool_call_id=tool_call_id, tool_name=tool_name, status="unknown",
            structured_content={"type": "FinanceResearchProtocolInvalid", "reason": reason[:2048], "safeToCorrect": False, "sourceRevisionExpected": self.finance_grant.source_revision, "sourceStateDigestExpected": self.finance_grant.source_state_digest},
            runtime_job_ref=job_id if isinstance(job_id, str) else None,
            artifact_refs=self._extract_artifacts(payload), reconciled=reconciled,
        )


__all__ = [
    "FINANCE_RESEARCH_DEFINITION", "FINANCE_RESEARCH_TOOL_SURFACE",
    "FINANCE_RESEARCH_TOOL_SURFACE_DIGEST", "FinanceResearchRuntimeGrant",
    "SQLiteHarnessFinanceResearchRuntimeBridge",
]

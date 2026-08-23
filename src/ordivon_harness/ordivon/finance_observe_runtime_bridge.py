"""Finance-owned current observation lowered through exact Runtime execution.

Finance owns observation semantics and canonical Finance-state recording. Harness
owns the durable Agent/Tool lifecycle and response-loss fencing. Runtime owns only
physical execution/recovery. This bridge grants no provider plumbing, Workstation
mutation, proposal, execution, or external-financial-write authority.
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
from ..execution_binding import (
    HarnessExecutionBinding,
    build_harness_workspace_exec_request_from_binding,
)
from ..runtime_port import HarnessRuntimeClient
from .model import AgentToolCall, AgentToolDefinition
from .run_store_port import HarnessRunContinuityStore
from .sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind

_GOAL_PREFIX = "goal:"
_MAX_OWNER_STDOUT_BYTES = 1_048_576

FINANCE_OBSERVE_DEFINITION = AgentToolDefinition(
    name="finance_observe",
    description=(
        "Finance owner observation: refresh current owner-capital and portfolio standing. "
        "This may read the external venue and record canonical observation/evidence state, "
        "but grants no financial write, proposal, execution, provider-plumbing, or "
        "Workstation mutation authority."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "goalId": {
                "type": "string",
                "pattern": r"^goal:[A-Za-z0-9._:-]+$",
            }
        },
        "additionalProperties": False,
    },
)

FINANCE_OBSERVE_TOOL_SURFACE: dict[str, JsonValue] = {
    "schemaVersion": 0,
    "kind": "ordivon.finance-observe-tool-surface-experimental",
    "owner": "ordivon-finance",
    "tools": [FINANCE_OBSERVE_DEFINITION.to_dict()],
}
FINANCE_OBSERVE_TOOL_SURFACE_DIGEST = canonical_digest(FINANCE_OBSERVE_TOOL_SURFACE)


def _text(value: Any, label: str, *, max_bytes: int = 1024) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return value


def _absolute_path(value: Any, label: str) -> str:
    text = _text(value, label, max_bytes=2048)
    path = PurePosixPath(text)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be an absolute normalized POSIX path")
    return text


def _goal_id(value: Any) -> str:
    text = _text(value, "Finance goalId", max_bytes=300)
    if not text.startswith(_GOAL_PREFIX) or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
        for character in text[len(_GOAL_PREFIX) :]
    ):
        raise ValueError("Finance goalId must be a canonical goal:<id> reference")
    if text == _GOAL_PREFIX:
        raise ValueError("Finance goalId must include an identity")
    return text


@dataclass(frozen=True, slots=True)
class FinanceObserveRuntimeGrant:
    """Caller-fenced physical lowering authority for one exact Finance source/state."""

    workspace_ref: str
    source_revision: str
    source_state_digest: str
    finance_state_root: str
    finance_state_db: str
    finance_app_python: str

    def __post_init__(self) -> None:
        _text(self.workspace_ref, "Finance Runtime Workspace reference")
        _text(self.source_revision, "Finance source revision")
        _digest(self.source_state_digest, "Finance source-state digest")
        _absolute_path(self.finance_state_root, "Finance state root")
        _absolute_path(self.finance_state_db, "Finance state DB")
        _absolute_path(self.finance_app_python, "Finance application Python")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 0,
            "kind": "ordivon.finance-observe-runtime-grant-experimental",
            "owner": "ordivon-finance",
            "tools": [FINANCE_OBSERVE_DEFINITION.name],
            "runtimeOperations": ["workspace.exec"],
            "effectClass": "canonical-observation-external-read-no-financial-write",
            "progressClass": "observation-no-capital-effect",
            "workspaceRef": self.workspace_ref,
            "sourceRevision": self.source_revision,
            "sourceStateDigest": self.source_state_digest,
            "financeStateRoot": self.finance_state_root,
            "financeStateDb": self.finance_state_db,
            "financeAppPython": self.finance_app_python,
            "execution": {
                "executable": "/usr/bin/node",
                "script": "scripts/finance-domain.mjs",
                "cwdRelative": ".",
            },
            "providerPlumbingAllowed": False,
            "workstationMutationAllowed": False,
            "financialWriteAllowed": False,
            "authorityExpansionAllowed": False,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


class SQLiteHarnessFinanceObserveRuntimeBridge(SQLiteHarnessRuntimeBridge):
    """Compile one Finance semantic observation into durable exact Runtime execution."""

    observation_only_tool_names = frozenset({FINANCE_OBSERVE_DEFINITION.name})

    def __init__(
        self,
        contract: HarnessRunContract,
        run_store: HarnessRunContinuityStore,
        execution_binding: HarnessExecutionBinding,
        runtime: HarnessRuntimeClient,
        grant: FinanceObserveRuntimeGrant,
        *,
        provider_source=None,
        provider_holder_id: str | None = None,
    ) -> None:
        if execution_binding.workspace_ref != grant.workspace_ref:
            raise ValueError("Finance grant Workspace differs from Harness Execution Binding")
        super().__init__(
            contract,
            run_store,
            execution_binding,
            runtime,
            provider_source=provider_source,
            provider_holder_id=provider_holder_id,
            tool_definitions=(FINANCE_OBSERVE_DEFINITION,),
            tool_surface_digest=FINANCE_OBSERVE_TOOL_SURFACE_DIGEST,
            tool_grant_digest=grant.digest,
        )
        self.finance_grant = grant

    def _lower_runtime_tool_call(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
    ) -> tuple[str, dict[str, JsonValue], str | None]:
        if call.name != FINANCE_OBSERVE_DEFINITION.name:
            raise ToolBridgeError(
                f"Finance observe bridge does not expose {call.name}",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        arguments = dict(call.arguments)
        if set(arguments) - {"goalId"}:
            raise ToolBridgeError(
                "finance_observe received unknown fields",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        owner_arguments: dict[str, JsonValue] = {}
        if "goalId" in arguments:
            try:
                owner_arguments["goalId"] = _goal_id(arguments["goalId"])
            except ValueError as error:
                raise ToolBridgeError(
                    str(error),
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                ) from error
        try:
            request = build_harness_workspace_exec_request_from_binding(
                self.execution_binding,
                step_id=step_id,
                executable="/usr/bin/node",
                args=(
                    "scripts/finance-domain.mjs",
                    "call",
                    "--operation",
                    "finance.observe",
                    "--arguments-json",
                    json.dumps(owner_arguments, sort_keys=True, separators=(",", ":")),
                ),
                cwd_relative=".",
                env={
                    "ORDIVON_FINANCE_STATE_ROOT": self.finance_grant.finance_state_root,
                    "ORDIVON_FINANCE_STATE_DB": self.finance_grant.finance_state_db,
                    "ORDIVON_FINANCE_APP_PYTHON": self.finance_grant.finance_app_python,
                },
                timeout_ms=60_000,
                stdout_limit_bytes=_MAX_OWNER_STDOUT_BYTES,
                stderr_limit_bytes=262_144,
                wait_ms=0,
                stdout_tail_bytes=65_536,
                stderr_tail_bytes=16_384,
            )
        except ValueError as error:
            raise ToolBridgeError(
                str(error),
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            ) from error
        request_id = request.get("clientRequestId")
        if not isinstance(request_id, str):
            raise ToolBridgeError(
                "Finance Runtime request omitted clientRequestId",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return "workspace.exec", request, request_id

    def _owner_stdout(self, payload: dict[str, JsonValue]) -> str:
        stdout = payload.get("stdoutTail")
        if not isinstance(stdout, str):
            raise TypeError("Runtime result omitted Finance stdoutTail")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            return stdout
        candidates = [
            item
            for item in artifacts
            if isinstance(item, dict) and item.get("kind") == "stdout"
        ]
        if len(candidates) != 1:
            return stdout
        artifact = candidates[0]
        if artifact.get("truncated") is True:
            raise ValueError("Finance owner stdout exceeded the bounded Runtime capture")
        retained = artifact.get("retainedBytes")
        if type(retained) is not int or retained <= len(stdout.encode("utf-8")):
            return stdout
        artifact_id = artifact.get("artifactId")
        digest = artifact.get("digest")
        job_id = payload.get("jobId")
        if not all(isinstance(value, str) for value in (artifact_id, digest, job_id)):
            raise ValueError("Finance stdout Artifact identity is incomplete")
        read = self.runtime.call_tool(
            "artifact.read",
            {
                "schemaVersion": 1,
                "jobId": job_id,
                "artifactId": artifact_id,
                "offset": 0,
                "maxBytes": _MAX_OWNER_STDOUT_BYTES,
            },
        )
        content = read.get("content")
        if (
            read.get("eof") is not True
            or read.get("digest") != digest
            or not isinstance(content, str)
        ):
            raise ValueError("Finance stdout Artifact read did not verify")
        return content

    @staticmethod
    def _owner_envelope_digest(owner_stdout: str) -> str:
        return "sha256:" + hashlib.sha256(owner_stdout.encode("utf-8")).hexdigest()

    @staticmethod
    def _compact_finance_result(result: dict[str, Any]) -> dict[str, JsonValue]:
        observation = result.get("observation")
        observation = observation if isinstance(observation, dict) else {}
        context = result.get("contextStanding")
        context = context if isinstance(context, dict) else {}
        portfolio = context.get("portfolioStatus")
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        provider = result.get("providerStanding")
        provider = provider if isinstance(provider, dict) else {}
        consumer = result.get("consumerStanding")
        consumer = consumer if isinstance(consumer, dict) else {}
        obligations = context.get("obligations")
        compact_obligations: list[JsonValue] = []
        if isinstance(obligations, list):
            for item in obligations[:32]:
                if not isinstance(item, dict):
                    continue
                summary: dict[str, JsonValue] = {}
                for key in ("kind", "need", "status"):
                    value = item.get(key)
                    if isinstance(value, str):
                        summary[key] = value
                if summary:
                    compact_obligations.append(summary)
        errors = observation.get("errors")
        error_count = len(errors) if isinstance(errors, list) else None
        value: dict[str, JsonValue] = {
            "status": result.get("status") if isinstance(result.get("status"), str) else None,
            "goalId": result.get("goalId") if isinstance(result.get("goalId"), str) else None,
            "portfolioId": (
                result.get("portfolioId") if isinstance(result.get("portfolioId"), str) else None
            ),
            "stateVersionBefore": (
                result.get("stateVersionBefore")
                if isinstance(result.get("stateVersionBefore"), str)
                else None
            ),
            "stateVersionAfter": (
                result.get("stateVersionAfter")
                if isinstance(result.get("stateVersionAfter"), str)
                else None
            ),
            "observation": {
                "status": (
                    observation.get("status")
                    if isinstance(observation.get("status"), str)
                    else None
                ),
                "attemptId": (
                    observation.get("attemptId")
                    if isinstance(observation.get("attemptId"), str)
                    else None
                ),
                "evidenceRef": (
                    observation.get("evidenceRef")
                    if isinstance(observation.get("evidenceRef"), str)
                    else None
                ),
                "snapshotRef": (
                    observation.get("snapshotRef")
                    if isinstance(observation.get("snapshotRef"), str)
                    else None
                ),
                "errorCount": error_count,
            },
            "contextStanding": {
                "decision": (
                    context.get("decision") if isinstance(context.get("decision"), str) else None
                ),
                "obligations": compact_obligations,
                "portfolioStatus": {
                    "portfolioId": (
                        portfolio.get("portfolioId")
                        if isinstance(portfolio.get("portfolioId"), str)
                        else None
                    ),
                    "snapshotRef": (
                        portfolio.get("snapshotRef")
                        if isinstance(portfolio.get("snapshotRef"), str)
                        else None
                    ),
                    "snapshotObservedAt": (
                        portfolio.get("snapshotObservedAt")
                        if isinstance(portfolio.get("snapshotObservedAt"), str)
                        else None
                    ),
                    "observationHealth": (
                        portfolio.get("observationHealth")
                        if isinstance(portfolio.get("observationHealth"), str)
                        else None
                    ),
                    "exposureProjectionCurrent": (
                        portfolio.get("exposureProjectionCurrent")
                        if type(portfolio.get("exposureProjectionCurrent")) is bool
                        else None
                    ),
                    "latestAttemptFailedAfterSnapshot": (
                        portfolio.get("latestAttemptFailedAfterSnapshot")
                        if type(portfolio.get("latestAttemptFailedAfterSnapshot")) is bool
                        else None
                    ),
                },
            },
            "providerStanding": {
                "venue": provider.get("venue") if isinstance(provider.get("venue"), str) else None,
                "sourceRef": (
                    provider.get("sourceRef")
                    if isinstance(provider.get("sourceRef"), str)
                    else None
                ),
                "providerSurface": (
                    provider.get("providerSurface")
                    if isinstance(provider.get("providerSurface"), str)
                    else None
                ),
                "egressAdmitted": (
                    provider.get("egressAdmitted")
                    if type(provider.get("egressAdmitted")) is bool
                    else None
                ),
            },
            "consumerStanding": {
                "canonicalStateMutation": (
                    consumer.get("canonicalStateMutation")
                    if type(consumer.get("canonicalStateMutation")) is bool
                    else None
                ),
                "externalWorldRead": (
                    consumer.get("externalWorldRead")
                    if type(consumer.get("externalWorldRead")) is bool
                    else None
                ),
                "credentialAccess": (
                    consumer.get("credentialAccess")
                    if isinstance(consumer.get("credentialAccess"), str)
                    else None
                ),
                "externalFinancialWrite": (
                    consumer.get("externalFinancialWrite")
                    if type(consumer.get("externalFinancialWrite")) is bool
                    else None
                ),
                "financialSubmission": (
                    consumer.get("financialSubmission")
                    if type(consumer.get("financialSubmission")) is bool
                    else None
                ),
                "authorityMutation": (
                    consumer.get("authorityMutation")
                    if type(consumer.get("authorityMutation")) is bool
                    else None
                ),
            },
        }
        validate_json_value(value)
        return value

    def _observation_from_payload(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        payload: dict[str, JsonValue],
        query: str | None,
        relative_path: str | None,
        reconciled: bool,
    ) -> HarnessToolObservation:
        if tool_name != FINANCE_OBSERVE_DEFINITION.name:
            return super()._observation_from_payload(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                payload=payload,
                query=query,
                relative_path=relative_path,
                reconciled=reconciled,
            )
        job_id = payload.get("jobId")
        runtime_job_ref = job_id if isinstance(job_id, str) else None
        try:
            owner_stdout = self._owner_stdout(payload)
            finance = json.loads(owner_stdout)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            return self._invalid_finance_result(
                tool_call_id, tool_name, str(error), payload, reconciled
            )
        if not isinstance(finance, dict):
            return self._invalid_finance_result(
                tool_call_id,
                tool_name,
                "Finance owner result was not an object",
                payload,
                reconciled,
            )
        envelope_digest = self._owner_envelope_digest(owner_stdout)

        if finance.get("ok") is False:
            error = finance.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            error_type = error.get("type") if isinstance(error, dict) else None
            if (
                finance.get("kind") != "ordivon.finance.runtime-domain-error"
                or not isinstance(code, str)
                or finance.get("externalFinancialWriteAttempted") is not False
            ):
                return self._invalid_finance_result(
                    tool_call_id,
                    tool_name,
                    "Finance owner error violated its fail-closed contract",
                    payload,
                    reconciled,
                )
            structured: dict[str, JsonValue] = {
                "schemaVersion": 0,
                "kind": "ordivon.harness-finance-observe-owner-outcome-experimental",
                "truthRole": "bounded-projection-of-caller-fenced-finance-owner-outcome",
                "owner": "ordivon-finance",
                "ownerOutcome": "blocked",
                "ownerEnvelopeDigest": envelope_digest,
                "ownerError": {
                    "code": code,
                    "type": error_type if isinstance(error_type, str) else None,
                    "message": message if isinstance(message, str) else None,
                },
                "effectBoundary": {
                    "externalFinancialWriteAttempted": False,
                    "authorityExpanded": False,
                },
                "runtime": {
                    "jobId": runtime_job_ref,
                    "executionDisposition": payload.get("executionDisposition"),
                    "deliveryDisposition": payload.get("deliveryDisposition"),
                    "recoveryRequired": payload.get("recoveryRequired"),
                },
            }
            validate_json_value(structured)
            return HarnessToolObservation(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="observed",
                structured_content=structured,
                runtime_job_ref=runtime_job_ref,
                artifact_refs=self._extract_artifacts(payload),
                reconciled=reconciled,
            )

        effect = finance.get("effectContract")
        result = finance.get("result")
        if (
            finance.get("kind") != "ordivon.finance.runtime-domain-result"
            or finance.get("domain") != "finance"
            or finance.get("operation") != "finance.observe"
            or finance.get("ok") is not True
            or not isinstance(effect, dict)
            or effect.get("owner") != "ordivon-finance"
            or effect.get("effectClass") != "CANONICAL_OBSERVATION"
            or effect.get("externalWorldRead") is not True
            or effect.get("externalFinancialWrite") is not False
            or effect.get("financialSubmission") is not False
            or effect.get("authorityMutation") is not False
            or not isinstance(result, dict)
            or result.get("status") != "refreshed"
        ):
            return self._invalid_finance_result(
                tool_call_id,
                tool_name,
                "Finance observe result violated its owner/effect contract",
                payload,
                reconciled,
            )
        structured = {
            "schemaVersion": 0,
            "kind": "ordivon.harness-finance-observe-observation-experimental",
            "truthRole": "bounded-projection-of-caller-fenced-finance-owner-observation",
            "owner": "ordivon-finance",
            "sourceFence": {
                "workspaceRef": self.finance_grant.workspace_ref,
                "sourceRevisionExpected": self.finance_grant.source_revision,
                "sourceStateDigestExpected": self.finance_grant.source_state_digest,
                "verifiedByBridge": False,
            },
            "ownerEnvelopeDigest": envelope_digest,
            "financeProjection": self._compact_finance_result(result),
            "effectBoundary": {
                "externalWorldRead": True,
                "canonicalObservationStateMayMutate": True,
                "externalFinancialWrite": False,
                "financialSubmission": False,
                "authorityMutation": False,
            },
            "runtime": {
                "jobId": runtime_job_ref,
                "executionDisposition": payload.get("executionDisposition"),
                "deliveryDisposition": payload.get("deliveryDisposition"),
                "recoveryRequired": payload.get("recoveryRequired"),
            },
        }
        validate_json_value(structured)
        return HarnessToolObservation(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status="observed",
            structured_content=structured,
            runtime_job_ref=runtime_job_ref,
            artifact_refs=self._extract_artifacts(payload),
            reconciled=reconciled,
        )

    def _invalid_finance_result(
        self,
        tool_call_id: str,
        tool_name: str,
        reason: str,
        payload: dict[str, JsonValue],
        reconciled: bool,
    ) -> HarnessToolObservation:
        job_id = payload.get("jobId")
        return HarnessToolObservation(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status="unknown",
            structured_content={
                "type": "FinanceObserveProtocolInvalid",
                "reason": reason[:2048],
                "safeToCorrect": False,
                "sourceRevisionExpected": self.finance_grant.source_revision,
                "sourceStateDigestExpected": self.finance_grant.source_state_digest,
            },
            runtime_job_ref=job_id if isinstance(job_id, str) else None,
            artifact_refs=self._extract_artifacts(payload),
            reconciled=reconciled,
        )


__all__ = [
    "FINANCE_OBSERVE_DEFINITION",
    "FINANCE_OBSERVE_TOOL_SURFACE",
    "FINANCE_OBSERVE_TOOL_SURFACE_DIGEST",
    "FinanceObserveRuntimeGrant",
    "SQLiteHarnessFinanceObserveRuntimeBridge",
]

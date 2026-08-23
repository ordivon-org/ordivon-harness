"""Experimental Atlas-owned prior-result Tool lowered through exact Runtime execution.

Atlas owns prior-result candidate semantics. Harness owns the durable Agent/Tool
loop and response-loss fencing. Runtime owns only physical source-bound execution
and recovery. This bridge deliberately does not teach generic Runtime lowering
what an Atlas result means.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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

ATLAS_FIRST_LOOK_DEFINITION = AgentToolDefinition(
    name="atlas_first_look",
    description=(
        "Atlas owner read: return bounded prior-result candidates and projection "
        "currentness. It does not decide semantic equivalence, novelty, or research "
        "admission. Missing/direct-match absence in this bounded result is not evidence "
        "of semantic non-equivalence or novelty."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": 32, "default": 8},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)

ATLAS_FIRST_LOOK_TOOL_SURFACE: dict[str, JsonValue] = {
    "schemaVersion": 0,
    "kind": "ordivon.atlas-first-look-tool-surface-experimental",
    "owner": "ordivon-atlas",
    "tools": [ATLAS_FIRST_LOOK_DEFINITION.to_dict()],
}
ATLAS_FIRST_LOOK_TOOL_SURFACE_DIGEST = canonical_digest(ATLAS_FIRST_LOOK_TOOL_SURFACE)


def _text(value: Any, label: str, *, max_bytes: int = 512) -> str:
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


@dataclass(frozen=True, slots=True)
class AtlasFirstLookRuntimeGrant:
    """Caller-fenced physical lowering authority for one exact Atlas Workspace."""

    workspace_ref: str
    source_revision: str
    source_state_digest: str

    def __post_init__(self) -> None:
        _text(self.workspace_ref, "Atlas Runtime Workspace reference")
        _text(self.source_revision, "Atlas source revision")
        _digest(self.source_state_digest, "Atlas source-state digest")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 0,
            "kind": "ordivon.atlas-first-look-runtime-grant-experimental",
            "owner": "ordivon-atlas",
            "tools": [ATLAS_FIRST_LOOK_DEFINITION.name],
            "runtimeOperations": ["workspace.exec"],
            "effectClass": "read_only",
            "progressClass": "observation-only",
            "workspaceRef": self.workspace_ref,
            "sourceRevision": self.source_revision,
            "sourceStateDigest": self.source_state_digest,
            "execution": {
                "executable": "/usr/bin/python3",
                "module": "ordivon_atlas.cli",
                "cwdRelative": ".",
                "env": {"PYTHONPATH": "src"},
            },
            "workspaceMutationAllowed": False,
            "authorityExpansionAllowed": False,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


class SQLiteHarnessAtlasFirstLookRuntimeBridge(SQLiteHarnessRuntimeBridge):
    """Compile one Atlas semantic read into durable exact Runtime execution."""

    observation_only_tool_names = frozenset({ATLAS_FIRST_LOOK_DEFINITION.name})

    def __init__(
        self,
        contract: HarnessRunContract,
        run_store: HarnessRunContinuityStore,
        execution_binding: HarnessExecutionBinding,
        runtime: HarnessRuntimeClient,
        grant: AtlasFirstLookRuntimeGrant,
        *,
        provider_source=None,
        provider_holder_id: str | None = None,
    ) -> None:
        if execution_binding.workspace_ref != grant.workspace_ref:
            raise ValueError("Atlas grant Workspace differs from Harness Execution Binding")
        super().__init__(
            contract,
            run_store,
            execution_binding,
            runtime,
            provider_source=provider_source,
            provider_holder_id=provider_holder_id,
            tool_definitions=(ATLAS_FIRST_LOOK_DEFINITION,),
            tool_surface_digest=ATLAS_FIRST_LOOK_TOOL_SURFACE_DIGEST,
            tool_grant_digest=grant.digest,
        )
        self.atlas_grant = grant

    def _lower_runtime_tool_call(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
    ) -> tuple[str, dict[str, JsonValue], str | None]:
        if call.name != ATLAS_FIRST_LOOK_DEFINITION.name:
            raise ToolBridgeError(
                f"Atlas first-look bridge does not expose {call.name}",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        arguments = dict(call.arguments)
        if set(arguments) - {"query", "limit"}:
            raise ToolBridgeError(
                "atlas_first_look received unknown fields",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        query = arguments.get("query")
        if not isinstance(query, str) or not query or query != query.strip():
            raise ToolBridgeError(
                "atlas_first_look requires trimmed string query",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        if len(query.encode("utf-8")) > 2_048:
            raise ToolBridgeError(
                "atlas_first_look query exceeds 2048 UTF-8 bytes",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        limit = arguments.get("limit", 8)
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ToolBridgeError(
                "atlas_first_look limit must be an integer from 1 to 32",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        try:
            request = build_harness_workspace_exec_request_from_binding(
                self.execution_binding,
                step_id=step_id,
                executable="/usr/bin/python3",
                args=(
                    "-m",
                    "ordivon_atlas.cli",
                    "first-look",
                    query,
                    "--limit",
                    str(limit),
                ),
                cwd_relative=".",
                env={"PYTHONPATH": "src"},
                timeout_ms=30_000,
                stdout_limit_bytes=65_536,
                stderr_limit_bytes=16_384,
                wait_ms=0,
                stdout_tail_bytes=65_536,
                stderr_tail_bytes=16_384,
            )
        except ValueError as error:
            raise ToolBridgeError(
                str(error),
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            ) from error
        client_request_id = request.get("clientRequestId")
        if not isinstance(client_request_id, str):
            raise ToolBridgeError(
                "Atlas Runtime request omitted clientRequestId",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return "workspace.exec", request, client_request_id

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
        if tool_name != ATLAS_FIRST_LOOK_DEFINITION.name:
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
        if payload.get("executionDisposition") != "succeeded":
            return HarnessToolObservation(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="unknown",
                structured_content={
                    "type": "AtlasFirstLookExecutionFailed",
                    "safeToCorrect": False,
                    "executionDisposition": payload.get("executionDisposition"),
                    "deliveryDisposition": payload.get("deliveryDisposition"),
                    "sourceRevisionExpected": self.atlas_grant.source_revision,
                    "sourceStateDigestExpected": self.atlas_grant.source_state_digest,
                },
                runtime_job_ref=runtime_job_ref,
                artifact_refs=self._extract_artifacts(payload),
                reconciled=reconciled,
            )
        stdout = payload.get("stdoutTail")
        if not isinstance(stdout, str):
            return self._invalid_atlas_result(
                tool_call_id,
                tool_name,
                "Runtime result omitted stdoutTail",
                payload,
                reconciled,
            )
        try:
            atlas_result = json.loads(stdout)
        except json.JSONDecodeError as error:
            return self._invalid_atlas_result(
                tool_call_id,
                tool_name,
                f"Atlas stdout was not one JSON result: {error}",
                payload,
                reconciled,
            )
        if not isinstance(atlas_result, dict):
            return self._invalid_atlas_result(
                tool_call_id,
                tool_name,
                "Atlas result was not an object",
                payload,
                reconciled,
            )
        try:
            validate_json_value(atlas_result)
        except (TypeError, ValueError) as error:
            return self._invalid_atlas_result(
                tool_call_id,
                tool_name,
                f"Atlas result was not canonical JSON data: {error}",
                payload,
                reconciled,
            )
        claims = atlas_result.get("claims")
        if (
            atlas_result.get("kind")
            != "ordivon.atlas-prior-result-first-look-experimental"
            or not isinstance(claims, dict)
            or claims.get("semanticEquivalenceInferred") is not False
            or claims.get("researchAdmissionGranted") is not False
            or claims.get("ownerTruthMinted") is not False
        ):
            return self._invalid_atlas_result(
                tool_call_id,
                tool_name,
                "Atlas first-look result violated its non-authoritative contract",
                payload,
                reconciled,
            )
        structured: dict[str, JsonValue] = {
            "schemaVersion": 0,
            "kind": "ordivon.harness-atlas-first-look-observation-experimental",
            "truthRole": "caller-fenced-atlas-owner-read-via-runtime",
            "owner": "ordivon-atlas",
            "sourceFence": {
                "workspaceRef": self.atlas_grant.workspace_ref,
                "sourceRevisionExpected": self.atlas_grant.source_revision,
                "sourceStateDigestExpected": self.atlas_grant.source_state_digest,
                "verifiedByBridge": False,
            },
            "epistemicGuard": {
                "candidateSetExhaustive": False,
                "absenceDoesNotEstablishSemanticNonEquivalence": True,
                "absenceDoesNotEstablishNovelty": True,
                "directTextMatchDoesNotEstablishSemanticEquivalence": True,
                "requiredCallerAdjudication": [
                    "semantic equivalence",
                    "research admission",
                ],
            },
            "atlasResult": atlas_result,
            "runtime": {
                "jobId": runtime_job_ref,
                "clientRequestId": payload.get("clientRequestId"),
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

    def _invalid_atlas_result(
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
                "type": "AtlasFirstLookProtocolInvalid",
                "reason": reason[:2_048],
                "safeToCorrect": False,
                "sourceRevisionExpected": self.atlas_grant.source_revision,
                "sourceStateDigestExpected": self.atlas_grant.source_state_digest,
            },
            runtime_job_ref=job_id if isinstance(job_id, str) else None,
            artifact_refs=self._extract_artifacts(payload),
            reconciled=reconciled,
        )


__all__ = [
    "ATLAS_FIRST_LOOK_DEFINITION",
    "ATLAS_FIRST_LOOK_TOOL_SURFACE",
    "ATLAS_FIRST_LOOK_TOOL_SURFACE_DIGEST",
    "AtlasFirstLookRuntimeGrant",
    "SQLiteHarnessAtlasFirstLookRuntimeBridge",
]

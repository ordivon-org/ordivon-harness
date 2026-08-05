from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, replace
from typing import Protocol

from anc_canonical import (
    JsonValue,
    canonical_bytes,
    canonical_digest,
    validate_json_value,
)
from .._host_compat.effects import ArtifactRef
from .._host_compat.runtime import (
    RuntimeClient,
    RuntimeClientError,
    RuntimeProtocolError,
    RuntimeToolRejected,
    find_jobs_by_client_request,
)
from ..protocol import (
    HarnessProviderCallFailureReceipt,
    HarnessProviderCallStatus,
    HarnessRecoveryConsequence,
    HarnessRunPauseReason,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
    HarnessToolStepStatus,
)

from ..host import CommittedHarnessAssignment
from ..tool_semantics import (
    NativeToolCatalogSnapshot,
    build_native_tool_catalog_snapshot,
)
from .control import ExecutionControl
from .model import (
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnAdapterError,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
    AgentTurnRequest,
    AgentTurnResult,
)
from ..run_state import HarnessRunState
from .run_store_port import (
    HarnessDispatchFenceView,
    HarnessProviderCallRecoveryRequired,
    HarnessProviderCallSourceRef,
    HarnessRunContinuityStore,
    StoredHarnessProviderCall,
    StoredHarnessRunSnapshot,
)
from .runtime_lowering import lower_runtime_tool, _read_workspace_byte_offset
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind

_MAX_PROVIDER_CLAIM_TTL_MS = 15_000






@dataclass(frozen=True, slots=True)
class ToolObservation:
    tool_call_id: str
    tool_name: str
    status: str
    structured_content: dict[str, JsonValue]
    runtime_job_ref: str | None = None
    artifact_refs: tuple[ArtifactRef, ...] = ()
    reconciled: bool = False

    def __post_init__(self) -> None:
        if not self.tool_call_id or self.tool_call_id != self.tool_call_id.strip():
            raise ValueError("Tool Observation Call identity must be trimmed")
        if not self.tool_name or self.tool_name != self.tool_name.strip():
            raise ValueError("Tool Observation name must be trimmed")
        if self.status not in {
            "observed",
            "rejected",
            "unknown",
            "cancel-requested",
            "cancelled",
        }:
            raise ValueError(f"unsupported Tool Observation status: {self.status}")
        validate_json_value(self.structured_content)
        if self.runtime_job_ref is not None and (
            not self.runtime_job_ref
            or self.runtime_job_ref != self.runtime_job_ref.strip()
        ):
            raise ValueError("Runtime Job reference must be trimmed")
        refs = [item.ref for item in self.artifact_refs]
        if len(refs) != len(set(refs)):
            raise ValueError("Tool Observation Artifact refs must be unique")
        if self.status == "rejected" and self.runtime_job_ref is not None:
            raise ValueError("pre-admission rejection cannot carry a Runtime Job")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.tool-observation",
            "toolCallId": self.tool_call_id,
            "toolName": self.tool_name,
            "status": self.status,
            "structuredContent": self.structured_content,
            "runtimeJobRef": self.runtime_job_ref,
            "artifactRefs": [item.to_dict() for item in self.artifact_refs],
            "reconciled": self.reconciled,
        }

    @classmethod
    def from_dict(cls, value: dict[str, JsonValue]) -> ToolObservation:
        expected = {
            "schemaVersion",
            "kind",
            "toolCallId",
            "toolName",
            "status",
            "structuredContent",
            "runtimeJobRef",
            "artifactRefs",
            "reconciled",
        }
        if set(value) != expected:
            raise ValueError("Tool Observation fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.tool-observation":
            raise ValueError("Tool Observation version or kind is invalid")
        artifacts = value["artifactRefs"]
        content = value["structuredContent"]
        if not isinstance(artifacts, list) or any(
            not isinstance(item, dict) for item in artifacts
        ):
            raise ValueError("Tool Observation Artifact refs are invalid")
        if not isinstance(content, dict):
            raise TypeError("Tool Observation structured content must be an object")
        if (
            not isinstance(value["toolCallId"], str)
            or not isinstance(value["toolName"], str)
            or not isinstance(value["status"], str)
            or (
                value["runtimeJobRef"] is not None
                and not isinstance(value["runtimeJobRef"], str)
            )
            or type(value["reconciled"]) is not bool
        ):
            raise ValueError("Tool Observation scalar fields are invalid")
        return cls(
            tool_call_id=value["toolCallId"],
            tool_name=value["toolName"],
            status=value["status"],
            structured_content=dict(content),
            runtime_job_ref=value["runtimeJobRef"],
            artifact_refs=tuple(ArtifactRef.from_dict(item) for item in artifacts),
            reconciled=value["reconciled"],
        )

    def to_model_message(self) -> dict[str, JsonValue]:
        return {
            "role": "tool",
            "toolCallId": self.tool_call_id,
            "name": self.tool_name,
            "observation": {
                "status": self.status,
                "content": self.structured_content,
                "runtimeJobRef": self.runtime_job_ref,
                "artifactRefs": [item.to_dict() for item in self.artifact_refs],
                "reconciled": self.reconciled,
            },
        }

    def bounded(self, max_bytes: int) -> ToolObservation:
        if max_bytes < 1:
            return self
        if len(canonical_bytes(self.to_dict())) <= max_bytes:
            return self
        original_content = dict(self.structured_content)
        bounded_content: dict[str, JsonValue] = {
            "truncated": True,
            "originalContentDigest": canonical_digest(original_content),
            "originalContentBytes": len(canonical_bytes(original_content)),
            "runtimeJobRef": self.runtime_job_ref,
            "artifactRefs": [item.to_dict() for item in self.artifact_refs],
        }
        retained_keys = (
            "relativePath",
            "digest",
            "contentDigest",
            "query",
            "matchCount",
            "matchesTruncated",
            "effectiveByteRange",
            "sourceRange",
            "locationSemantics",
        )
        for key in retained_keys:
            if key not in original_content:
                continue
            bounded_content[key] = original_content[key]
            candidate = ToolObservation(
                tool_call_id=self.tool_call_id,
                tool_name=self.tool_name,
                status=self.status,
                structured_content=bounded_content,
                runtime_job_ref=self.runtime_job_ref,
                artifact_refs=self.artifact_refs,
                reconciled=self.reconciled,
            )
            if len(canonical_bytes(candidate.to_dict())) > max_bytes:
                del bounded_content[key]
        return ToolObservation(
            tool_call_id=self.tool_call_id,
            tool_name=self.tool_name,
            status=self.status,
            structured_content=bounded_content,
            runtime_job_ref=self.runtime_job_ref,
            artifact_refs=self.artifact_refs,
            reconciled=self.reconciled,
        )


class ToolBridge(Protocol):
    catalog_digest: str

    def definitions(self) -> tuple[AgentToolDefinition, ...]: ...

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation: ...


HarnessRuntimeCatalog = NativeToolCatalogSnapshot


_REQUIRED_RUNTIME_OPERATIONS = (
    "artifact.read",
    "task.list",
    "task.observe",
    "workspace.diff",
    "workspace.exec",
    "workspace.mutate",
    "workspace.read",
)
_OPTIONAL_PATCH_OPERATIONS = ("workspace.patch", "workspace.patch.get")


def _object_schema(
    properties: dict[str, JsonValue], required: tuple[str, ...] = ()
) -> dict[str, JsonValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


def model_tool_definitions() -> tuple[AgentToolDefinition, ...]:
    integer = {"type": "integer", "minimum": 0}
    string = {"type": "string", "minLength": 1}
    return (
        AgentToolDefinition(
            "read_workspace",
            (
                "Read bounded UTF-8 content from the Assignment Workspace. "
                "For SLICE reads, byteOffset is a zero-based UTF-8 byte offset."
            ),
            _object_schema(
                {
                    "relativePath": string,
                    "mode": {"type": "string", "enum": ["FULL", "SLICE"]},
                    "byteOffset": integer,
                    "maxBytes": {"type": "integer", "minimum": 1},
                },
                ("relativePath",),
            ),
        ),
        AgentToolDefinition(
            "search_workspace",
            (
                "Find fixed UTF-8 text in one granted Workspace file or directory. "
                "Results include lineNumber, column, and byteOffset; use byteOffset "
                "for a follow-up read_workspace SLICE offset."
            ),
            _object_schema(
                {
                    "query": {"type": "string", "minLength": 1, "maxLength": 512},
                    "relativePath": string,
                    "maxMatches": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                ("query", "relativePath"),
            ),
        ),
        AgentToolDefinition(
            "mutate_workspace",
            "Apply an atomic validated WRITE, APPEND, or REPLACE_EXACT mutation batch.",
            _object_schema(
                {"mutations": {"type": "array", "minItems": 1, "maxItems": 32}},
                ("mutations",),
            ),
        ),
        AgentToolDefinition(
            "patch_workspace",
            "Apply one digest-guarded text patch under a durable Runtime request identity.",
            _object_schema(
                {
                    "files": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 32,
                        "items": _object_schema(
                            {
                                "relativePath": string,
                                "expectedDigest": {"type": ["string", "null"]},
                                "edits": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": 128,
                                    "items": _object_schema(
                                        {
                                            "range": _object_schema(
                                                {
                                                    "start": _object_schema(
                                                        {
                                                            "line": {
                                                                "type": "integer",
                                                                "minimum": 1,
                                                            },
                                                            "column": integer,
                                                        },
                                                        ("line", "column"),
                                                    ),
                                                    "end": _object_schema(
                                                        {
                                                            "line": {
                                                                "type": "integer",
                                                                "minimum": 1,
                                                            },
                                                            "column": integer,
                                                        },
                                                        ("line", "column"),
                                                    ),
                                                },
                                                ("start", "end"),
                                            ),
                                            "expectedText": {"type": "string"},
                                            "replacement": {"type": "string"},
                                        },
                                        ("range", "expectedText", "replacement"),
                                    ),
                                },
                            },
                            ("relativePath", "edits"),
                        ),
                    },
                    "maxDiffBytes": {"type": "integer", "minimum": 1},
                },
                ("files",),
            ),
        ),
        AgentToolDefinition(
            "diff_workspace",
            "Read a bounded structured Git diff for the Assignment Workspace.",
            _object_schema(
                {"maxBytes": {"type": "integer", "minimum": 1}},
            ),
        ),
        AgentToolDefinition(
            "run_check",
            "Run one Assignment-prebound verification Check by identity.",
            _object_schema(
                {
                    "checkId": string,
                    "waitMs": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 30_000,
                    },
                    "stdoutTailBytes": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 65_536,
                    },
                    "stderrTailBytes": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 65_536,
                    },
                },
                ("checkId",),
            ),
        ),
        AgentToolDefinition(
            "run_in_workspace",
            "Run one absolute executable only when opaque execution is explicitly granted.",
            _object_schema(
                {
                    "executable": string,
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 128,
                    },
                    "cwdRelative": {"type": "string"},
                    "env": {"type": "object"},
                    "timeoutMs": integer,
                    "stdoutLimitBytes": integer,
                    "stderrLimitBytes": integer,
                    "waitMs": integer,
                    "stdoutTailBytes": integer,
                    "stderrTailBytes": integer,
                },
                ("executable",),
            ),
        ),
        AgentToolDefinition(
            "observe_job",
            "Observe one known Runtime Job without creating another execution.",
            _object_schema(
                {
                    "jobId": string,
                    "waitMs": integer,
                    "stdoutTailBytes": integer,
                    "stderrTailBytes": integer,
                },
                ("jobId",),
            ),
        ),
        AgentToolDefinition(
            "read_artifact",
            "Read bounded bytes from one Runtime Artifact by identity.",
            _object_schema(
                {
                    "jobId": string,
                    "artifactId": string,
                    "offset": integer,
                    "maxBytes": {"type": "integer", "minimum": 1},
                },
                ("jobId", "artifactId"),
            ),
        ),
    )


def discover_harness_runtime_catalog(runtime: RuntimeClient) -> HarnessRuntimeCatalog:
    runtime.initialize()
    raw_catalog: dict[str, dict[str, JsonValue]] = {}
    for raw in runtime.list_tools():
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise RuntimeProtocolError("Runtime Tool descriptor has no operation name")
        if name in raw_catalog:
            raise RuntimeProtocolError(
                f"Runtime Tool catalog repeats operation: {name}"
            )
        selected: dict[str, JsonValue] = {
            "name": name,
            "inputSchema": raw.get("inputSchema"),
            "outputSchema": raw.get("outputSchema"),
            "execution": raw.get("execution"),
        }
        validate_json_value(selected)
        raw_catalog[name] = selected
    missing = [
        operation
        for operation in _REQUIRED_RUNTIME_OPERATIONS
        if operation not in raw_catalog
    ]
    if missing:
        raise RuntimeProtocolError(
            f"Runtime Harness catalog is missing operations: {missing}"
        )
    patch_presence = tuple(
        operation in raw_catalog for operation in _OPTIONAL_PATCH_OPERATIONS
    )
    if any(patch_presence) and not all(patch_presence):
        raise RuntimeProtocolError(
            "Runtime must expose workspace.patch and workspace.patch.get together"
        )
    operations = _REQUIRED_RUNTIME_OPERATIONS + (
        _OPTIONAL_PATCH_OPERATIONS if all(patch_presence) else ()
    )
    model_tools = model_tool_definitions()
    if not all(patch_presence):
        model_tools = tuple(
            tool for tool in model_tools if tool.name != "patch_workspace"
        )
    descriptors = tuple(raw_catalog[name] for name in operations)
    return build_native_tool_catalog_snapshot(descriptors, model_tools)


class RuntimeToolBridge:
    """Assignment-scoped ACI lowering. It owns no Workspace or Task lifecycle."""

    def __init__(
        self,
        committed: CommittedHarnessAssignment,
        *,
        harness_run_id: str,
        runtime: RuntimeClient,
        run_store: HarnessRunContinuityStore | None = None,
        provider_source: HarnessProviderCallSourceRef | None = None,
        provider_holder_id: str | None = None,
        defer_runtime_catalog_validation: bool = False,
    ) -> None:
        if not harness_run_id.startswith("harness-run:"):
            raise ValueError("Harness Run identity must start with harness-run:")
        if committed.assignment.workspace_ref is None:
            raise ValueError("Ordivon Harness requires an Assignment Workspace")
        self.committed = committed
        self.harness_run_id = harness_run_id
        self.runtime = runtime
        self.run_store = run_store
        if run_store is not None:
            binding = run_store.binding
            assignment = committed.assignment
            if (
                binding.harness_run_id != harness_run_id
                or binding.assignment_id != assignment.assignment_id
                or binding.assignment_generation != assignment.generation
                or binding.assignment_digest != assignment.digest
            ):
                raise ValueError("Harness Run Store differs from the Runtime bridge")
        if provider_source is not None and run_store is None:
            raise ValueError("Provider Call source requires a Harness Run Store")
        if run_store is not None and provider_source is None:
            try:
                provider_source = run_store.snapshot_provider_source(
                    run_store.load_current_snapshot()
                )
            except KeyError:
                provider_source = run_store.assignment_provider_source()
        self._provider_source = provider_source
        self._provider_holder_id = provider_holder_id or (
            f"harness-provider-holder:{uuid.uuid4().hex}"
        )
        self._provider_adapter_id: str | None = None
        self._provider_requested_model_id: str | None = None
        self._active_provider_call: StoredHarnessProviderCall | None = None
        self.clock_ms = (
            run_store.clock_ms
            if run_store is not None
            else lambda: time.time_ns() // 1_000_000
        )
        self.tool_grant = committed.tool_grant
        if committed.native_run_contract is not None:
            native = committed.native_run_contract
            if self.tool_grant is None:
                raise ValueError("native Harness Runtime bridge requires a Tool Grant")
            if native.harness_run_id != harness_run_id:
                raise ValueError(
                    "Runtime bridge Harness Run differs from native Run Contract"
                )
            if native.tool_catalog_object_digest is not None:
                if (
                    committed.tool_catalog is None
                    or committed.tool_catalog_object is None
                ):
                    raise ValueError(
                        "v2 native Harness Runtime bridge requires its retained Tool catalog"
                    )
                if (
                    committed.tool_catalog.digest
                    != committed.assignment.tool_catalog_digest
                    or committed.tool_catalog_object.digest
                    != native.tool_catalog_object_digest
                ):
                    raise ValueError(
                        "retained native Tool catalog differs from the Assignment"
                    )
            elif (
                committed.tool_catalog is not None
                or committed.tool_catalog_object is not None
            ):
                raise ValueError(
                    "v1 native Harness Run cannot retain a v2 Tool catalog"
                )
        self._known_job_ids: set[str] = set()
        self._known_artifacts: set[tuple[str, str]] = set()
        self._runtime_catalog_validated = False
        if defer_runtime_catalog_validation:
            self.catalog = committed.tool_catalog
            self.catalog_digest = committed.assignment.tool_catalog_digest
        else:
            self.catalog = self._load_validated_runtime_catalog()
            self._runtime_catalog_validated = True
            self.catalog_digest = self.catalog.digest
        self._seen_tool_calls: set[str] = set()
        self._tool_step_intents: dict[str, HarnessToolStepIntent] = {}
        self._complete_read_paths: set[str] = set()
        self._observed_read_ranges: dict[str, list[tuple[int, int]]] = {}
        self._workspace_observation_cache_restored = False

    @property
    def durable_provider_calls_enabled(self) -> bool:
        return self.run_store is not None and self._provider_source is not None

    def validate_runtime_catalog(self) -> None:
        if self._runtime_catalog_validated:
            return
        self.catalog = self._load_validated_runtime_catalog()
        self.catalog_digest = self.catalog.digest
        self._runtime_catalog_validated = True

    def _load_validated_runtime_catalog(self) -> NativeToolCatalogSnapshot:
        catalog = discover_harness_runtime_catalog(self.runtime)
        if catalog.digest != self.committed.assignment.tool_catalog_digest:
            raise RuntimeProtocolError(
                "Runtime Harness Tool catalog differs from the committed Assignment"
            )
        return catalog

    def bind_run_state(
        self,
        *,
        messages: tuple[dict[str, JsonValue], ...],
        observations: tuple[ToolObservation, ...],
        remaining_budget: dict[str, JsonValue],
        requested_model_id: str,
        effective_model_id: str | None,
        active_elapsed_ms: int | None = None,
        seen_model_call_ids: tuple[str, ...] = (),
        seen_tool_call_ids: tuple[str, ...] = (),
        provider_usage: tuple[dict[str, JsonValue], ...] = (),
        effective_model_ids: tuple[str, ...] = (),
    ) -> None:
        if not self._workspace_observation_cache_restored:
            self._restore_workspace_observation_cache(messages, observations)
            self._workspace_observation_cache_restored = True
        if self.run_store is None:
            return
        self.run_store.bind_state(
            HarnessRunState(
                messages=messages,
                observations=tuple(item.to_dict() for item in observations),
                remaining_budget=remaining_budget,
                requested_model_id=requested_model_id,
                effective_model_id=effective_model_id,
                active_elapsed_ms=active_elapsed_ms,
                seen_model_call_ids=seen_model_call_ids,
                seen_tool_call_ids=seen_tool_call_ids,
                provider_usage=provider_usage,
                effective_model_ids=effective_model_ids,
            )
        )

    def _refresh_caller_revision(self) -> None:
        if self.run_store is not None:
            self.committed = replace(
                self.committed,
                task_revision=self.run_store.caller_revision,
            )

    def restore_provider_replay_state(
        self,
        *,
        snapshot: StoredHarnessRunSnapshot,
        additional_messages: tuple[dict[str, JsonValue], ...],
    ) -> HarnessRunState | None:
        if self.run_store is None or self._provider_source is None:
            return None
        adapter_id, requested_model_id = self._require_provider_configuration()
        state = self.run_store.load_provider_replay_state(
            source=self._provider_source,
            snapshot=snapshot,
            additional_messages=additional_messages,
            adapter_id=adapter_id,
            requested_model_id=requested_model_id,
        )
        self._refresh_caller_revision()
        return state

    def begin_provider_call(
        self,
        request: AgentTurnRequest,
        *,
        provider_request_digest: str | None = None,
    ) -> AgentTurnResult | HarnessProviderCallFailureReceipt | None:
        if self.run_store is None or self._provider_source is None:
            return None
        if provider_request_digest is None:
            raise ToolBridgeError(
                "durable Provider Call requires an exact Provider request digest",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        adapter_id, requested_model_id = self._require_provider_configuration()
        retained = self.run_store.claim_provider_call(
            source=self._provider_source,
            turn_id=request.turn_id,
            turn_sequence=request.sequence,
            request_digest=request.dispatch_digest,
            provider_request_digest=provider_request_digest,
            adapter_id=adapter_id,
            requested_model_id=requested_model_id,
            holder_id=self._provider_holder_id,
            ttl_ms=self._provider_claim_ttl_ms(request),
        )
        self._refresh_caller_revision()
        self._active_provider_call = retained
        if retained.result is not None:
            return retained.result
        if retained.failure is not None:
            return retained.failure
        return None

    def admit_provider_call(
        self,
        request: AgentTurnRequest,
        *,
        control: ExecutionControl,
    ) -> bool:
        if self.run_store is None:
            return not self._execution_control_stopped(control)
        retained = self._require_active_provider_call(request)
        if self._execution_control_stopped(control):
            self._record_pre_dispatch_stop(request, retained)
            return False
        retained = self.run_store.mark_provider_call_dispatching(retained)
        self._active_provider_call = retained
        self._refresh_caller_revision()
        if self._execution_control_stopped(control):
            self._record_pre_dispatch_stop(request, retained)
            return False
        return True

    def configure_provider_call(
        self,
        *,
        adapter_id: str,
        requested_model_id: str,
    ) -> None:
        if (
            not adapter_id
            or adapter_id != adapter_id.strip()
            or not requested_model_id
            or requested_model_id != requested_model_id.strip()
        ):
            raise ValueError(
                "Provider Call identities must be non-empty and trimmed"
            )
        self._provider_adapter_id = adapter_id
        self._provider_requested_model_id = requested_model_id

    def complete_provider_call(
        self,
        request: AgentTurnRequest,
        result: AgentTurnResult,
    ) -> None:
        if self.run_store is None:
            return
        retained = self._require_active_provider_call(request)
        self._active_provider_call = self.run_store.complete_provider_call(
            retained,
            result,
        )
        self._refresh_caller_revision()
        if self.run_store.provider_outcome_requires_resume:
            raise HarnessProviderCallRecoveryRequired(
                "Provider outcome was admitted after Recovery; explicit resume is required"
            )

    def fail_provider_call(
        self,
        request: AgentTurnRequest,
        error: AgentTurnAdapterError,
        *,
        unknown: bool,
    ) -> None:
        if self.run_store is None:
            return
        retained = self._require_active_provider_call(request)
        expected_unknown = error.dispatch_safety.value == "dispatch_ambiguous"
        if unknown != expected_unknown:
            raise ToolBridgeError(
                "Provider failure status differs from its dispatch safety",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        failure = HarnessProviderCallFailureReceipt(
            provider_call_id=retained.record.provider_call_id,
            request_digest=request.dispatch_digest,
            provider_request_digest=retained.record.provider_request_digest,
            failure_code=error.failure_code.value,
            dispatch_safety=error.dispatch_safety.value,
            detail=_bounded_provider_failure_detail(error),
        )
        self._active_provider_call = self.run_store.fail_provider_call(
            retained,
            failure=failure,
        )
        self._refresh_caller_revision()
        if self.run_store.provider_outcome_requires_resume:
            raise HarnessProviderCallRecoveryRequired(
                "Provider outcome was admitted after Recovery; explicit resume is required"
            )

    def retry_provider_call(self, request: AgentTurnRequest) -> None:
        if self.run_store is None:
            return
        retained = self._require_active_provider_call(request)
        retained = self.run_store.retry_failed_provider_call(
            retained,
            holder_id=self._provider_holder_id,
            ttl_ms=self._provider_claim_ttl_ms(request),
        )
        self._active_provider_call = retained
        self._refresh_caller_revision()

    def _record_pre_dispatch_stop(
        self,
        request: AgentTurnRequest,
        retained: StoredHarnessProviderCall,
    ) -> None:
        assert self.run_store is not None
        failure = HarnessProviderCallFailureReceipt(
            provider_call_id=retained.record.provider_call_id,
            request_digest=request.dispatch_digest,
            provider_request_digest=retained.record.provider_request_digest,
            failure_code=AgentTurnFailureCode.TIMEOUT.value,
            dispatch_safety=AgentTurnDispatchSafety.PRE_DISPATCH_SAFE.value,
            detail=(
                "Provider dispatch admission closed before physical invocation"
            ),
        )
        if retained.record.status is HarnessProviderCallStatus.CLAIMED:
            retained = self.run_store.fail_claimed_provider_call(
                retained,
                failure=failure,
            )
        elif retained.record.status is HarnessProviderCallStatus.DISPATCHING:
            retained = self.run_store.fail_provider_call(
                retained,
                failure=failure,
            )
        else:
            raise ToolBridgeError(
                "Provider dispatch admission stopped from an invalid state",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        self._active_provider_call = retained
        self._refresh_caller_revision()

    def _execution_control_stopped(
        self,
        control: ExecutionControl | None,
    ) -> bool:
        if control is None:
            return False
        if control.stop_requested:
            return True
        assignment_deadline_ms = self.committed.assignment.deadline_ms
        return (
            assignment_deadline_ms is not None
            and self.clock_ms() >= assignment_deadline_ms
        )

    def _require_runtime_io_admitted(
        self,
        control: ExecutionControl | None,
        *,
        detail: str,
    ) -> None:
        if self._execution_control_stopped(control):
            raise ToolBridgeError(
                detail,
                kind=ToolBridgeErrorKind.CONTROL_STOPPED,
            )

    def _close_runtime_dispatch_if_stopped(
        self,
        call: AgentToolCall,
        *,
        intent: HarnessToolStepIntent | None,
        control: ExecutionControl | None,
    ) -> ToolObservation | None:
        if not self._execution_control_stopped(control):
            return None
        if intent is not None:
            observation = ToolObservation(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                status="rejected",
                structured_content={
                    "error": {
                        "type": "execution_control_stopped",
                        "message": (
                            "Runtime dispatch admission closed before physical "
                            "invocation"
                        ),
                        "commitState": "not_started",
                        "physicalDispatch": False,
                        "safeToCorrect": False,
                    }
                },
            )
            self._record_tool_step_receipt(intent, observation)
            return observation
        raise ToolBridgeError(
            "Runtime dispatch admission closed before physical invocation",
            kind=ToolBridgeErrorKind.CONTROL_STOPPED,
        )

    def _require_provider_configuration(self) -> tuple[str, str]:
        adapter_id = self._provider_adapter_id
        requested_model_id = self._provider_requested_model_id
        if adapter_id is None or requested_model_id is None:
            raise ToolBridgeError(
                "durable Provider Call was not configured with Adapter identities",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return adapter_id, requested_model_id

    def _require_active_provider_call(
        self,
        request: AgentTurnRequest,
    ) -> StoredHarnessProviderCall:
        retained = self._active_provider_call
        if retained is None or retained.record.request_digest != request.dispatch_digest:
            raise ToolBridgeError(
                "Provider Call state differs from the current Agent Turn",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return retained

    @staticmethod
    def _provider_claim_ttl_ms(request: AgentTurnRequest) -> int:
        remaining = request.remaining_budget.get("wallTimeMs")
        if type(remaining) is not int or remaining < 0:
            raise ToolBridgeError(
                "Agent Turn omitted a valid remaining wall-time budget",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return max(1_000, min(_MAX_PROVIDER_CLAIM_TTL_MS, remaining + 1_000))

    def _restore_workspace_observation_cache(
        self,
        messages: tuple[dict[str, JsonValue], ...],
        observations: tuple[ToolObservation, ...],
    ) -> None:
        calls: dict[str, AgentToolCall] = {}
        for message in messages:
            raw_calls = message.get("toolCalls")
            if not isinstance(raw_calls, list):
                continue
            for raw_call in raw_calls:
                if not isinstance(raw_call, dict):
                    continue
                tool_call_id = raw_call.get("toolCallId")
                name = raw_call.get("name")
                arguments = raw_call.get("arguments")
                if (
                    not isinstance(tool_call_id, str)
                    or not isinstance(name, str)
                    or not isinstance(arguments, dict)
                ):
                    continue
                try:
                    calls[tool_call_id] = AgentToolCall(
                        tool_call_id,
                        name,
                        dict(arguments),
                    )
                except (TypeError, ValueError):
                    continue
        self._complete_read_paths.clear()
        self._observed_read_ranges.clear()
        for observation in observations:
            call = calls.get(observation.tool_call_id)
            if call is not None:
                self._update_workspace_observation_cache(call, observation)

    def restore_seen_tool_calls(self, tool_call_ids: tuple[str, ...]) -> None:
        if len(tool_call_ids) != len(set(tool_call_ids)):
            raise ToolBridgeError(
                "restored Tool Call identities must be unique",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        self._seen_tool_calls.update(tool_call_ids)

    def record_pause(self, reason: str) -> None:
        if self.run_store is None:
            return
        mapping = {
            "needs_input": HarnessRunPauseReason.NEEDS_INPUT,
        }
        try:
            pause_reason = mapping[reason]
        except KeyError as error:
            raise ToolBridgeError(
                f"unsupported Harness pause reason: {reason}"
            ) from error
        self.run_store.record_pause(pause_reason)
        self._refresh_caller_revision()
        self._active_provider_call = None

    def current_tool_step_intent(self) -> HarnessToolStepIntent:
        if self.run_store is None:
            raise ToolBridgeError(
                "Tool Step intent recovery requires a Harness Run Store"
            )
        return self.run_store.load_current_tool_step().intent

    def reconcile_current_tool_step(
        self,
        *,
        control: ExecutionControl | None = None,
    ) -> ToolObservation:
        if self.run_store is None:
            raise ToolBridgeError(
                "Tool Step reconciliation requires a Harness Run Store"
            )
        self._require_runtime_io_admitted(
            control,
            detail="Runtime reconciliation stopped before observation",
        )
        step = self.run_store.load_current_tool_step()
        if step.receipt is not None and step.receipt.terminal:
            if step.observation is None:
                raise ToolBridgeError(
                    "stored Tool Step Receipt omitted its Observation"
                )
            return ToolObservation.from_dict(step.observation)
        intent = step.intent
        call = AgentToolCall(intent.tool_call_id, intent.tool_name, {})
        if intent.runtime_operation == "workspace.patch":
            observation = self._reconcile_workspace_patch(
                call,
                intent,
                control=control,
            )
        elif intent.runtime_operation == "workspace.exec":
            if step.receipt is not None:
                job_id = step.receipt.runtime_job_ref
                if job_id is None:
                    raise ToolBridgeError(
                        "non-terminal Tool Step Receipt omitted its Runtime Job"
                    )
                observation = self._reconcile_cancel_requested(
                    call,
                    job_id,
                    control=control,
                )
            else:
                observation = self._reconcile_unrecorded_dispatch(
                    call,
                    intent,
                    control=control,
                )
        else:
            raise ToolBridgeError(
                f"Runtime Tool Step is not reconciliable: {intent.runtime_operation}",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        self._record_tool_step_receipt(intent, observation)
        return observation

    def _reconcile_workspace_patch(
        self,
        call: AgentToolCall,
        intent: HarnessToolStepIntent,
        *,
        control: ExecutionControl | None,
    ) -> ToolObservation:
        self._require_runtime_io_admitted(
            control,
            detail="Runtime patch reconciliation stopped before observation",
        )
        try:
            payload = self.runtime.call_tool(
                "workspace.patch.get",
                {
                    "schemaVersion": 1,
                    "clientRequestId": intent.client_request_id,
                },
            )
        except RuntimeToolRejected as error:
            if error.detail.commit_state == "not_committed":
                return ToolObservation(
                    call.tool_call_id,
                    call.name,
                    "rejected",
                    {
                        "error": {
                            "type": "runtime_patch_not_admitted",
                            "message": str(error)[:2_048],
                            "clientRequestId": intent.client_request_id,
                            "commitState": error.detail.commit_state,
                        }
                    },
                    reconciled=True,
                )
            return self._unknown(
                call,
                error,
                client_request_id=intent.client_request_id,
                operation="workspace.patch.get",
                arguments={
                    "schemaVersion": 1,
                    "clientRequestId": intent.client_request_id,
                },
            )
        except RuntimeClientError as error:
            return ToolObservation(
                call.tool_call_id,
                call.name,
                "unknown",
                {
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error)[:2_048],
                        "clientRequestId": intent.client_request_id,
                    }
                },
                reconciled=True,
            )
        state = payload.get("state")
        if state == "unknown":
            return ToolObservation(
                call.tool_call_id,
                call.name,
                "unknown",
                dict(payload),
                reconciled=True,
            )
        if state == "prepared":
            return ToolObservation(
                call.tool_call_id,
                call.name,
                "rejected",
                {
                    **dict(payload),
                    "reason": "durable patch intent exists but no file effect was committed",
                },
                reconciled=True,
            )
        return self._observed(call, payload, reconciled=True)

    def _reconcile_unrecorded_dispatch(
        self,
        call: AgentToolCall,
        intent: HarnessToolStepIntent,
        *,
        control: ExecutionControl | None,
    ) -> ToolObservation:
        self._require_runtime_io_admitted(
            control,
            detail="Runtime dispatch reconciliation stopped before lookup",
        )
        try:
            jobs = find_jobs_by_client_request(self.runtime, intent.client_request_id)
        except RuntimeClientError as error:
            return ToolObservation(
                intent.tool_call_id,
                intent.tool_name,
                "unknown",
                {
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error)[:2_048],
                        "clientRequestId": intent.client_request_id,
                    }
                },
            )
        job_ids = {job.get("jobId") for job in jobs}
        if len(job_ids) != 1 or None in job_ids:
            return ToolObservation(
                intent.tool_call_id,
                intent.tool_name,
                "unknown",
                {
                    "error": {
                        "type": (
                            "runtime_dispatch_not_found"
                            if not job_ids
                            else "conflicting_runtime_jobs"
                        ),
                        "message": (
                            "no Runtime Job matches the durable Tool Step Intent"
                            if not job_ids
                            else "multiple Runtime Jobs match one durable Tool Step Intent"
                        ),
                        "clientRequestId": intent.client_request_id,
                        "jobIds": sorted(
                            item for item in job_ids if isinstance(item, str)
                        ),
                    }
                },
            )
        job_id = next(iter(job_ids))
        assert isinstance(job_id, str)
        self._require_runtime_io_admitted(
            control,
            detail="Runtime dispatch reconciliation stopped before observation",
        )
        try:
            payload = self.runtime.call_tool(
                "task.observe",
                {
                    "schemaVersion": 1,
                    "jobId": job_id,
                    "waitMs": 0,
                    "stdoutTailBytes": 8_192,
                    "stderrTailBytes": 8_192,
                },
            )
        except RuntimeClientError as error:
            return ToolObservation(
                intent.tool_call_id,
                intent.tool_name,
                "unknown",
                {
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error)[:2_048],
                        "clientRequestId": intent.client_request_id,
                        "jobId": job_id,
                    }
                },
                runtime_job_ref=job_id,
            )
        observation = self._observed(call, payload, reconciled=True)
        if self._runtime_job_terminal(observation):
            return observation
        return self._cancel_job(call, observation, control=control)

    def _reconcile_cancel_requested(
        self,
        call: AgentToolCall,
        job_id: str,
        *,
        control: ExecutionControl | None,
    ) -> ToolObservation:
        self._require_runtime_io_admitted(
            control,
            detail="Runtime cancellation reconciliation stopped before observation",
        )
        try:
            payload = self.runtime.call_tool(
                "task.observe",
                {
                    "schemaVersion": 1,
                    "jobId": job_id,
                    "waitMs": 0,
                    "stdoutTailBytes": 8_192,
                    "stderrTailBytes": 8_192,
                },
            )
        except RuntimeClientError as error:
            return ToolObservation(
                call.tool_call_id,
                call.name,
                "cancel-requested",
                {
                    "jobId": job_id,
                    "cancellation": {
                        "confirmed": False,
                        "errorType": type(error).__name__,
                        "message": str(error)[:2_048],
                    },
                },
                runtime_job_ref=job_id,
                reconciled=True,
            )
        status = payload.get("status")
        if status == "cancelled":
            return self._cancelled_observation(call, payload)
        if status in {"succeeded", "failed", "timed_out"}:
            return self._observed(call, payload, reconciled=True)
        return self._cancel_job(
            call,
            self._observed(call, payload, reconciled=True),
            control=control,
        )

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        if not self._runtime_catalog_validated or self.catalog is None:
            raise RuntimeProtocolError(
                "Runtime Harness Tool catalog was not validated before use"
            )
        if self.tool_grant is None:
            if self.run_store is None:
                return self.catalog.model_tools
            return tuple(
                tool
                for tool in self.catalog.model_tools
                if tool.name != "mutate_workspace"
            )
        retained: list[AgentToolDefinition] = []
        for tool in self.catalog.model_tools:
            if self.run_store is not None and tool.name == "mutate_workspace":
                continue
            if not self.tool_grant.allows_tool(tool.name):
                continue
            if tool.name == "run_check":
                schema = dict(tool.input_schema)
                properties = dict(schema["properties"])
                properties["checkId"] = {
                    "type": "string",
                    "enum": [
                        item.check_id for item in self.tool_grant.execution_checks
                    ],
                }
                schema["properties"] = properties
                retained.append(
                    AgentToolDefinition(tool.name, tool.description, schema)
                )
            else:
                retained.append(tool)
        return tuple(retained)

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        return self._execute(call, step_id=step_id, turn_id=None, control=None)

    def execute_with_control(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
        turn_id: str,
        control: ExecutionControl,
    ) -> ToolObservation:
        self._require_runtime_io_admitted(
            control,
            detail="Run control stopped before Runtime dispatch",
        )
        return self._execute(call, step_id=step_id, turn_id=turn_id, control=control)

    def _execute(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
        turn_id: str | None,
        control: ExecutionControl | None,
    ) -> ToolObservation:
        if self.tool_grant is not None and not self.tool_grant.allows_tool(call.name):
            raise ToolBridgeError(
                f"Tool is not granted for this Assignment: {call.name}",
                kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
            )
        if call.tool_call_id in self._seen_tool_calls:
            raise ToolBridgeError(
                f"duplicate Tool Call identity: {call.tool_call_id}",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        self._seen_tool_calls.add(call.tool_call_id)
        if call.name == "read_workspace":
            relative_path = call.arguments.get("relativePath")
            if (
                isinstance(relative_path, str)
                and relative_path in self._complete_read_paths
            ):
                raise ToolBridgeError(
                    (
                        "read_workspace already returned the complete current content "
                        f"for {relative_path}; use that Observation to advance the Run"
                    ),
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            offset = _read_workspace_byte_offset(call.arguments)
            max_bytes = call.arguments.get("maxBytes", 262_144)
            if (
                isinstance(relative_path, str)
                and type(offset) is int
                and offset >= 0
                and type(max_bytes) is int
                and max_bytes > 0
                and _covered_bytes(
                    self._observed_read_ranges.get(relative_path, ()),
                    offset,
                    offset + max_bytes,
                )
                * 5
                >= max_bytes * 4
            ):
                raise ToolBridgeError(
                    (
                        "read_workspace requested a range whose current content is "
                        f"at least 80% present in prior Observations for {relative_path}; "
                        "use the retained evidence or read a materially new range"
                    ),
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
        operation, arguments, client_request_id = self._lower(call, step_id=step_id)
        desired_wait_ms = 0
        if control is not None and operation == "workspace.exec":
            arguments = dict(arguments)
            configured_timeout = arguments.get("timeoutMs")
            if type(configured_timeout) is int:
                arguments["timeoutMs"] = max(
                    1, min(configured_timeout, control.remaining_ms)
                )
            configured_wait = arguments.get("waitMs")
            if type(configured_wait) is int:
                desired_wait_ms = max(0, min(configured_wait, control.remaining_ms))
                arguments["waitMs"] = desired_wait_ms

        intent: HarnessToolStepIntent | None = None
        fence: HarnessDispatchFenceView | None = None
        if self.run_store is not None:
            if operation == "workspace.mutate":
                raise ToolBridgeError(
                    "durable native Harness mode does not dispatch workspace.mutate "
                    "without a reconciliable Runtime dispatch identity"
                )
            if operation in {"workspace.exec", "workspace.patch"}:
                if client_request_id is None or turn_id is None:
                    raise ToolBridgeError(
                        "durable Runtime effect requires turn and client request identities"
                    )
                arguments = dict(arguments)
                if operation == "workspace.exec":
                    assert control is not None
                    desired_wait_ms = control.remaining_ms
                    arguments["waitMs"] = 0
                intent, fence = self._prepare_tool_step_intent(
                    call,
                    step_id=step_id,
                    turn_id=turn_id,
                    operation=operation,
                    arguments=arguments,
                    client_request_id=client_request_id,
                )
                if operation == "workspace.exec":
                    arguments = self._with_dispatch_fence(arguments, fence)
                self.run_store.assert_dispatch_fence_current(fence)

        stopped_observation = self._close_runtime_dispatch_if_stopped(
            call,
            intent=intent,
            control=control,
        )
        if stopped_observation is not None:
            return stopped_observation
        try:
            payload = self.runtime.call_tool(operation, arguments)
        except RuntimeToolRejected as error:
            if error.detail.commit_state in {"not_started", "not_committed"}:
                observation = ToolObservation(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.name,
                    status="rejected",
                    structured_content={"error": _runtime_error_value(error)},
                )
            else:
                observation = self._unknown(
                    call,
                    error,
                    client_request_id=client_request_id,
                    operation=operation,
                    arguments=arguments,
                )
            self._record_tool_step_receipt(intent, observation)
            return observation
        except RuntimeClientError as error:
            observation = self._unknown(
                call,
                error,
                client_request_id=client_request_id,
                operation=operation,
                arguments=arguments,
            )
            self._record_tool_step_receipt(intent, observation)
            return observation

        observation = self._observed(call, payload, reconciled=False)
        if fence is not None:
            assert self.run_store is not None
            try:
                self.run_store.assert_dispatch_fence_current(
                    fence, require_unexpired=False
                )
            except Exception:
                if observation.runtime_job_ref is not None:
                    self._cancel_job(call, observation)
                raise
        if (
            operation == "workspace.exec"
            and observation.runtime_job_ref is not None
            and control is not None
        ):
            observation = self._wait_for_runtime_job(
                call, observation, desired_wait_ms=desired_wait_ms, control=control
            )
        if call.name == "read_workspace":
            observation = _normalize_read_observation(call, observation)
        elif call.name == "search_workspace":
            observation = _normalize_search_observation(observation)
        self._update_workspace_observation_cache(call, observation)
        self._record_tool_step_receipt(intent, observation)
        return observation

    def _update_workspace_observation_cache(
        self,
        call: AgentToolCall,
        observation: ToolObservation,
    ) -> None:
        if observation.status != "observed":
            return
        if call.name in {"mutate_workspace", "patch_workspace"}:
            self._complete_read_paths.clear()
            self._observed_read_ranges.clear()
            return
        if call.name != "read_workspace":
            return
        relative_path = call.arguments.get("relativePath")
        mode = call.arguments.get("mode", "FULL")
        max_bytes = call.arguments.get("maxBytes", 262_144)
        offset = _read_workspace_byte_offset(call.arguments)
        content = observation.structured_content.get("content")
        truncated = observation.structured_content.get("truncated")
        if (
            isinstance(relative_path, str)
            and type(offset) is int
            and offset >= 0
            and isinstance(content, str)
        ):
            ranges = self._observed_read_ranges.setdefault(relative_path, [])
            ranges.append((offset, offset + len(content.encode("utf-8"))))
            self._observed_read_ranges[relative_path] = _merge_ranges(ranges)
        if (
            isinstance(relative_path, str)
            and mode == "FULL"
            and isinstance(content, str)
            and type(max_bytes) is int
            and (
                truncated is False
                or len(content.encode("utf-8")) < max_bytes
            )
        ):
            self._complete_read_paths.add(relative_path)

    @staticmethod
    def _with_dispatch_fence(
        arguments: dict[str, JsonValue], fence: HarnessDispatchFenceView
    ) -> dict[str, JsonValue]:
        retained = dict(arguments)
        execution = retained.get("execution")
        if not isinstance(execution, dict):
            raise ToolBridgeError("Runtime execution request omitted execution")
        execution = dict(execution)
        raw_references = execution.get("foreignReferences", [])
        if not isinstance(raw_references, list) or any(
            not isinstance(item, dict) for item in raw_references
        ):
            raise ToolBridgeError("Runtime execution foreign references are invalid")
        references = [dict(item) for item in raw_references]
        references.append(
            {
                "namespace": fence.authority_namespace,
                "type": fence.authority_type,
                "id": fence.fence_id,
                "generation": str(fence.authority_generation),
                "digest": fence.digest,
            }
        )
        execution["foreignReferences"] = references
        retained["execution"] = execution
        validate_json_value(retained)
        return retained

    def _wait_for_runtime_job(
        self,
        call: AgentToolCall,
        observation: ToolObservation,
        *,
        desired_wait_ms: int,
        control: ExecutionControl,
    ) -> ToolObservation:
        if self._runtime_job_terminal(observation):
            return observation
        if desired_wait_ms <= 0:
            return self._cancel_job(call, observation)
        job_id = observation.runtime_job_ref
        assert job_id is not None
        wait_deadline_ns = time.monotonic_ns() + desired_wait_ms * 1_000_000
        current = observation
        while not self._runtime_job_terminal(current):
            if control.stop_requested:
                return self._cancel_job(call, current)
            remaining_wait_ms = max(
                0, (wait_deadline_ns - time.monotonic_ns()) // 1_000_000
            )
            wait_ms = min(250, remaining_wait_ms, control.remaining_ms)
            if wait_ms <= 0:
                return self._cancel_job(call, current)
            try:
                payload = self.runtime.call_tool(
                    "task.observe",
                    {
                        "schemaVersion": 1,
                        "jobId": job_id,
                        "waitMs": wait_ms,
                        "stdoutTailBytes": (
                            65_536 if call.name == "search_workspace" else 8_192
                        ),
                        "stderrTailBytes": 8_192,
                    },
                )
            except RuntimeClientError as error:
                return ToolObservation(
                    call.tool_call_id,
                    call.name,
                    "unknown",
                    {
                        "error": {
                            "type": type(error).__name__,
                            "message": str(error)[:2_048],
                            "jobId": job_id,
                        }
                    },
                    runtime_job_ref=job_id,
                    artifact_refs=current.artifact_refs,
                )
            current = self._observed(call, payload, reconciled=True)
        return current

    @staticmethod
    def _runtime_job_terminal(observation: ToolObservation) -> bool:
        return observation.structured_content.get("status") in {
            "succeeded",
            "failed",
            "timed_out",
            "cancelled",
        }

    def _prepare_tool_step_intent(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
        turn_id: str,
        operation: str,
        arguments: dict[str, JsonValue],
        client_request_id: str,
    ) -> tuple[HarnessToolStepIntent, HarnessDispatchFenceView]:
        assert self.run_store is not None
        token = canonical_digest(
            {
                "harnessRunId": self.harness_run_id,
                "stepId": step_id,
                "toolCallDigest": call.digest,
            }
        )[7:31]
        assignment = self.committed.assignment
        consequence = HarnessRecoveryConsequence(
            self.catalog.tool(call.name).recovery_consequence.value
        )
        intent = HarnessToolStepIntent(
            intent_id=(
                f"harness-tool-step-intent:"
                f"{self.harness_run_id.removeprefix('harness-run:')}:{token}"
            ),
            harness_run_id=self.harness_run_id,
            assignment_id=assignment.assignment_id,
            assignment_generation=assignment.generation,
            assignment_digest=assignment.digest,
            turn_id=turn_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            tool_call_digest=call.digest,
            runtime_operation=operation,
            runtime_arguments_digest=canonical_digest(arguments),
            client_request_id=client_request_id,
            recovery_consequence=consequence,
            created_at_ms=self.clock_ms(),
        )
        snapshot = self.run_store.prepare_tool_step(intent)
        self._refresh_caller_revision()
        self._provider_source = self.run_store.snapshot_provider_source(snapshot)
        self._active_provider_call = None
        retained = self.run_store.load_current_tool_step()
        if retained.fence is None:
            raise ToolBridgeError(
                "durable Runtime execution omitted its Dispatch Fence"
            )
        self._tool_step_intents[call.tool_call_id] = intent
        return intent, retained.fence

    def _record_tool_step_receipt(
        self,
        intent: HarnessToolStepIntent | None,
        observation: ToolObservation,
    ) -> None:
        if self.run_store is None or intent is None:
            return
        current = self.run_store.load_current_tool_step()
        previous_receipt_digest = (
            None if current.receipt is None else current.receipt.digest
        )
        token = canonical_digest(
            {
                "intentDigest": intent.digest,
                "observationDigest": observation.digest,
                "previousReceiptDigest": previous_receipt_digest,
            }
        )[7:31]
        receipt = HarnessToolStepReceipt(
            receipt_id=(
                f"harness-tool-step-receipt:"
                f"{self.harness_run_id.removeprefix('harness-run:')}:{token}"
            ),
            intent_digest=intent.digest,
            harness_run_id=self.harness_run_id,
            tool_call_id=intent.tool_call_id,
            status=HarnessToolStepStatus(observation.status),
            runtime_job_ref=observation.runtime_job_ref,
            observation_digest=observation.digest,
            reconciled=observation.reconciled,
            created_at_ms=self.clock_ms(),
            previous_receipt_digest=previous_receipt_digest,
        )
        self.run_store.record_tool_step_receipt(receipt, observation.to_dict())
        self._refresh_caller_revision()

    def _cancelled_observation(
        self, call: AgentToolCall, payload: dict[str, JsonValue]
    ) -> ToolObservation:
        cancelled = self._observed(call, payload, reconciled=True)
        return ToolObservation(
            tool_call_id=cancelled.tool_call_id,
            tool_name=cancelled.tool_name,
            status="cancelled",
            structured_content=cancelled.structured_content,
            runtime_job_ref=cancelled.runtime_job_ref,
            artifact_refs=cancelled.artifact_refs,
            reconciled=True,
        )

    def _cancel_job(
        self,
        call: AgentToolCall,
        observation: ToolObservation,
        *,
        control: ExecutionControl | None = None,
    ) -> ToolObservation:
        job_id = observation.runtime_job_ref
        if job_id is None:
            return observation
        self._require_runtime_io_admitted(
            control,
            detail="Runtime cancellation stopped before dispatch",
        )
        try:
            payload = self.runtime.call_tool(
                "task.cancel",
                {"schemaVersion": 1, "jobId": job_id},
            )
        except RuntimeClientError as error:
            return ToolObservation(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                status="cancel-requested",
                structured_content={
                    "jobId": job_id,
                    "cancellation": {
                        "confirmed": False,
                        "errorType": type(error).__name__,
                        "message": str(error)[:2_048],
                    },
                },
                runtime_job_ref=job_id,
                artifact_refs=observation.artifact_refs,
            )
        status = payload.get("status")
        if status == "cancelled":
            return self._cancelled_observation(call, payload)
        if status in {"succeeded", "failed", "timed_out"}:
            return self._observed(call, payload, reconciled=True)
        return ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="cancel-requested",
            structured_content=dict(payload),
            runtime_job_ref=job_id,
            artifact_refs=_extract_artifacts(payload),
            reconciled=True,
        )

    def cancel_observation(
        self,
        call: AgentToolCall,
        observation: ToolObservation,
        *,
        step_id: str,
        control: ExecutionControl,
        record_receipt: bool = True,
    ) -> ToolObservation:
        del step_id, control
        result = self._cancel_job(call, observation)
        if record_receipt:
            self._record_tool_step_receipt(
                self._tool_step_intents.get(call.tool_call_id), result
            )
        return result


    def _lower(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
    ) -> tuple[str, dict[str, JsonValue], str | None]:
        return lower_runtime_tool(
            call,
            step_id=step_id,
            committed=self.committed,
            harness_run_id=self.harness_run_id,
            tool_grant=self.tool_grant,
            known_job_ids=frozenset(self._known_job_ids),
            known_artifacts=frozenset(self._known_artifacts),
        )

    def _unknown(
        self,
        call: AgentToolCall,
        error: RuntimeClientError,
        *,
        client_request_id: str | None,
        operation: str | None = None,
        arguments: dict[str, JsonValue] | None = None,
    ) -> ToolObservation:
        if operation == "workspace.patch" and arguments is not None:
            try:
                payload = self.runtime.call_tool("workspace.patch", arguments)
                return self._observed(call, payload, reconciled=True)
            except RuntimeClientError as reconciliation_error:
                error = reconciliation_error
        elif client_request_id is not None:
            try:
                jobs = find_jobs_by_client_request(self.runtime, client_request_id)
                job_ids = {job.get("jobId") for job in jobs}
                if len(job_ids) == 1 and None not in job_ids:
                    job_id = next(iter(job_ids))
                    if isinstance(job_id, str):
                        payload = self.runtime.call_tool(
                            "task.observe",
                            {
                                "schemaVersion": 1,
                                "jobId": job_id,
                                "waitMs": 0,
                                "stdoutTailBytes": 8_192,
                                "stderrTailBytes": 8_192,
                            },
                        )
                        return self._observed(call, payload, reconciled=True)
                if len(job_ids) > 1:
                    return ToolObservation(
                        call.tool_call_id,
                        call.name,
                        "unknown",
                        {
                            "error": {
                                "type": "conflicting_runtime_jobs",
                                "message": "one Tool Call resolved to multiple Runtime Jobs",
                                "clientRequestId": client_request_id,
                            }
                        },
                    )
            except RuntimeClientError as reconciliation_error:
                error = reconciliation_error
        return ToolObservation(
            call.tool_call_id,
            call.name,
            "unknown",
            {
                "error": {
                    "type": type(error).__name__,
                    "message": str(error)[:2_048],
                    "clientRequestId": client_request_id,
                }
            },
        )

    def _observed(
        self,
        call: AgentToolCall,
        payload: dict[str, JsonValue],
        *,
        reconciled: bool,
    ) -> ToolObservation:
        validate_json_value(payload)
        job_id = payload.get("jobId")
        runtime_job_ref = job_id if isinstance(job_id, str) and job_id else None
        if runtime_job_ref is not None:
            self._known_job_ids.add(runtime_job_ref)
            raw_artifacts = payload.get("artifacts")
            if isinstance(raw_artifacts, list):
                for item in raw_artifacts:
                    if isinstance(item, dict) and isinstance(
                        item.get("artifactId"), str
                    ):
                        self._known_artifacts.add((runtime_job_ref, item["artifactId"]))
        return ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="observed",
            structured_content=dict(payload),
            runtime_job_ref=runtime_job_ref,
            artifact_refs=_extract_artifacts(payload),
            reconciled=reconciled,
        )


def _merge_ranges(
    ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _covered_bytes(
    ranges: list[tuple[int, int]] | tuple[tuple[int, int], ...],
    start: int,
    end: int,
) -> int:
    return sum(
        max(0, min(end, range_end) - max(start, range_start))
        for range_start, range_end in ranges
    )


def _normalize_read_observation(
    call: AgentToolCall,
    observation: ToolObservation,
) -> ToolObservation:
    structured = dict(observation.structured_content)
    content = structured.get("content")
    if not isinstance(content, str):
        return observation
    start = _read_workspace_byte_offset(call.arguments)
    structured["effectiveByteRange"] = {
        "startInclusive": start,
        "endExclusive": start + len(content.encode("utf-8")),
        "unit": "utf8-bytes",
    }
    structured["locationSemantics"] = (
        "effectiveByteRange uses zero-based, end-exclusive UTF-8 byte offsets."
    )
    return ToolObservation(
        tool_call_id=observation.tool_call_id,
        tool_name=observation.tool_name,
        status=observation.status,
        structured_content=structured,
        runtime_job_ref=observation.runtime_job_ref,
        artifact_refs=observation.artifact_refs,
        reconciled=observation.reconciled,
    )


def _normalize_search_observation(
    observation: ToolObservation,
) -> ToolObservation:
    structured = dict(observation.structured_content)
    stdout = structured.get("stdoutTail")
    matches: list[dict[str, JsonValue]] = []
    if isinstance(stdout, str):
        for raw_line in stdout.splitlines():
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "match":
                continue
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            path = data.get("path")
            lines = data.get("lines")
            line_number = data.get("line_number")
            absolute_offset = data.get("absolute_offset")
            submatches = data.get("submatches")
            path_text = path.get("text") if isinstance(path, dict) else None
            line_text = lines.get("text") if isinstance(lines, dict) else None
            if (
                not isinstance(path_text, str)
                or type(line_number) is not int
                or type(absolute_offset) is not int
                or not isinstance(submatches, list)
            ):
                continue
            for submatch in submatches:
                if not isinstance(submatch, dict):
                    continue
                start = submatch.get("start")
                end = submatch.get("end")
                if type(start) is not int or type(end) is not int:
                    continue
                matches.append(
                    {
                        "relativePath": path_text,
                        "lineNumber": line_number,
                        "column": start + 1,
                        "byteOffset": absolute_offset + start,
                        "matchBytes": end - start,
                        "lineText": (
                            None
                            if not isinstance(line_text, str)
                            else line_text[:2_048]
                        ),
                    }
                )
                if len(matches) >= 200:
                    break
            if len(matches) >= 200:
                break
    structured["matches"] = matches
    structured["matchCount"] = len(matches)
    structured["locationSemantics"] = (
        "Use match.byteOffset as read_workspace SLICE offset; lineNumber and "
        "column are one-based display locations."
    )
    return ToolObservation(
        tool_call_id=observation.tool_call_id,
        tool_name=observation.tool_name,
        status=observation.status,
        structured_content=structured,
        runtime_job_ref=observation.runtime_job_ref,
        artifact_refs=observation.artifact_refs,
        reconciled=observation.reconciled,
    )


def _runtime_error_value(error: RuntimeToolRejected) -> dict[str, JsonValue]:
    detail = error.detail
    return {
        "type": type(error).__name__,
        "operation": error.operation,
        "code": detail.code,
        "message": detail.message,
        "field": detail.field,
        "retryable": detail.retryable,
        "retryClass": detail.retry_class,
        "commitState": detail.commit_state,
        "origin": detail.origin,
        "traceId": detail.trace_id,
    }


def _extract_artifacts(payload: dict[str, JsonValue]) -> tuple[ArtifactRef, ...]:
    raw = payload.get("artifacts")
    if not isinstance(raw, list):
        return ()
    refs: list[ArtifactRef] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        artifact_id = item.get("artifactId")
        digest = item.get("digest")
        kind = item.get("kind")
        if (
            isinstance(artifact_id, str)
            and isinstance(digest, str)
            and isinstance(kind, str)
        ):
            try:
                refs.append(ArtifactRef(ref=artifact_id, kind=kind, digest=digest))
            except ValueError:
                continue
    unique: dict[str, ArtifactRef] = {item.ref: item for item in refs}
    return tuple(unique[key] for key in sorted(unique))










def _bounded_provider_failure_detail(error: AgentTurnAdapterError) -> str:
    detail = str(error).strip() or type(error).__name__
    encoded = detail.encode("utf-8")
    if len(encoded) <= 2_048:
        return detail
    return encoded[:2_048].decode("utf-8", errors="ignore").strip()

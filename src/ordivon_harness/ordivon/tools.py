from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Protocol

from anc_canonical import (
    JsonValue,
    canonical_bytes,
    canonical_digest,
    validate_json_value,
)

from ordivon_host.effects import ArtifactRef
from ordivon_protocol import (
    HarnessRecoveryConsequence,
    HarnessRunPauseReason,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
    HarnessToolStepStatus,
)
from ordivon_host.runtime import (
    RuntimeClient,
    RuntimeClientError,
    RuntimeProtocolError,
    RuntimeToolRejected,
)
from ordivon_host.runtime.jobs import find_jobs_by_client_request
from ..host import CommittedHarnessAssignment
from ..runtime_refs import build_harness_workspace_exec_request
from ..tool_semantics import (
    NativeToolCatalogSnapshot,
    build_native_tool_catalog_snapshot,
)
from .control import ExecutionControl
from .model import AgentToolCall, AgentToolDefinition
from .run_store import HarnessRunState, HostHarnessRunStore


class ToolBridgeError(RuntimeError):
    pass


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
            raise ValueError("Tool Observation structured content must be an object")
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


_RUNTIME_OPERATIONS = (
    "artifact.read",
    "task.list",
    "task.observe",
    "workspace.diff",
    "workspace.exec",
    "workspace.mutate",
    "workspace.read",
)


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
            "Read bounded UTF-8 content from the Assignment Workspace.",
            _object_schema(
                {
                    "relativePath": string,
                    "mode": {"type": "string", "enum": ["FULL", "SLICE"]},
                    "offset": integer,
                    "maxBytes": {"type": "integer", "minimum": 1},
                },
                ("relativePath",),
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
                    "waitMs": integer,
                    "stdoutTailBytes": integer,
                    "stderrTailBytes": integer,
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
        operation for operation in _RUNTIME_OPERATIONS if operation not in raw_catalog
    ]
    if missing:
        raise RuntimeProtocolError(
            f"Runtime Harness catalog is missing operations: {missing}"
        )
    model_tools = model_tool_definitions()
    descriptors = tuple(raw_catalog[name] for name in _RUNTIME_OPERATIONS)
    return build_native_tool_catalog_snapshot(descriptors, model_tools)


class RuntimeToolBridge:
    """Assignment-scoped ACI lowering. It owns no Workspace or Task lifecycle."""

    def __init__(
        self,
        committed: CommittedHarnessAssignment,
        *,
        harness_run_id: str,
        runtime: RuntimeClient,
        run_store: HostHarnessRunStore | None = None,
    ) -> None:
        if not harness_run_id.startswith("harness-run:"):
            raise ValueError("Harness Run identity must start with harness-run:")
        if committed.assignment.workspace_ref is None:
            raise ValueError("Ordivon Harness requires an Assignment Workspace")
        self.committed = committed
        self.harness_run_id = harness_run_id
        self.runtime = runtime
        self.run_store = run_store
        if run_store is not None and (
            run_store.harness_run_id != harness_run_id
            or run_store.committed.assignment != committed.assignment
        ):
            raise ValueError("Harness Run Store differs from the Runtime bridge")
        self.clock_ms = (
            run_store.host.kernel.clock_ms
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
        self.catalog = discover_harness_runtime_catalog(runtime)
        if self.catalog.digest != committed.assignment.tool_catalog_digest:
            raise RuntimeProtocolError(
                "Runtime Harness Tool catalog differs from the committed Assignment"
            )
        self.catalog_digest = self.catalog.digest
        self._seen_tool_calls: set[str] = set()
        self._tool_step_intents: dict[str, HarnessToolStepIntent] = {}

    def bind_run_state(
        self,
        *,
        messages: tuple[dict[str, JsonValue], ...],
        observations: tuple[ToolObservation, ...],
        remaining_budget: dict[str, JsonValue],
        requested_model_id: str,
        effective_model_id: str | None,
    ) -> None:
        if self.run_store is None:
            return
        self.run_store.bind_state(
            HarnessRunState(
                messages=messages,
                observations=tuple(item.to_dict() for item in observations),
                remaining_budget=remaining_budget,
                requested_model_id=requested_model_id,
                effective_model_id=effective_model_id,
            )
        )

    def record_pause(self, reason: str) -> None:
        if self.run_store is None:
            return
        mapping = {
            "needs_input": HarnessRunPauseReason.NEEDS_INPUT,
            "approval_required": HarnessRunPauseReason.APPROVAL_REQUIRED,
        }
        try:
            pause_reason = mapping[reason]
        except KeyError as error:
            raise ToolBridgeError(f"unsupported Harness pause reason: {reason}") from error
        self.run_store.record_pause(pause_reason)
        self.committed = self.run_store.committed

    def reconcile_current_tool_step(self) -> ToolObservation:
        if self.run_store is None:
            raise ToolBridgeError("Tool Step reconciliation requires a Harness Run Store")
        step = self.run_store.load_current_tool_step()
        if step.receipt is not None:
            if step.observation is None:
                raise ToolBridgeError("stored Tool Step Receipt omitted its Observation")
            return ToolObservation.from_dict(step.observation)
        intent = step.intent
        if intent.runtime_operation != "workspace.exec":
            raise ToolBridgeError(
                "only Runtime workspace.exec Tool Steps are currently reconciliable"
            )
        call = AgentToolCall(intent.tool_call_id, intent.tool_name, {})
        try:
            jobs = find_jobs_by_client_request(
                self.runtime, intent.client_request_id
            )
        except RuntimeClientError as error:
            observation = ToolObservation(
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
        else:
            job_ids = {job.get("jobId") for job in jobs}
            if len(job_ids) == 1 and None not in job_ids:
                job_id = next(iter(job_ids))
                assert isinstance(job_id, str)
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
                    observation = ToolObservation(
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
                else:
                    observation = self._observed(call, payload, reconciled=True)
            else:
                observation = ToolObservation(
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
        self._record_tool_step_receipt(intent, observation)
        return observation

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        if self.tool_grant is None:
            return self.catalog.model_tools
        retained: list[AgentToolDefinition] = []
        for tool in self.catalog.model_tools:
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
        if control.stop_requested:
            raise ToolBridgeError("Run control stopped before Runtime dispatch")
        return self._execute(
            call, step_id=step_id, turn_id=turn_id, control=control
        )

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
                f"Tool is not granted for this Assignment: {call.name}"
            )
        if call.tool_call_id in self._seen_tool_calls:
            raise ToolBridgeError(f"duplicate Tool Call identity: {call.tool_call_id}")
        self._seen_tool_calls.add(call.tool_call_id)
        operation, arguments, client_request_id = self._lower(call, step_id=step_id)
        if control is not None and operation == "workspace.exec":
            arguments = dict(arguments)
            configured_timeout = arguments.get("timeoutMs")
            if type(configured_timeout) is int:
                arguments["timeoutMs"] = max(1, min(configured_timeout, control.remaining_ms))
            configured_wait = arguments.get("waitMs")
            if type(configured_wait) is int:
                arguments["waitMs"] = max(0, min(configured_wait, control.remaining_ms))
        intent: HarnessToolStepIntent | None = None
        if self.run_store is not None:
            if operation == "workspace.mutate":
                raise ToolBridgeError(
                    "durable native Harness mode does not dispatch workspace.mutate "
                    "without a reconciliable Runtime dispatch identity"
                )
            if operation == "workspace.exec":
                if client_request_id is None or turn_id is None:
                    raise ToolBridgeError(
                        "durable Runtime execution requires turn and client request identities"
                    )
                intent = self._prepare_tool_step_intent(
                    call,
                    step_id=step_id,
                    turn_id=turn_id,
                    operation=operation,
                    arguments=arguments,
                    client_request_id=client_request_id,
                )
        try:
            payload = self.runtime.call_tool(operation, arguments)
        except RuntimeToolRejected as error:
            if error.detail.commit_state == "not_committed":
                observation = ToolObservation(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.name,
                    status="rejected",
                    structured_content={"error": _runtime_error_value(error)},
                )
            else:
                observation = self._unknown(
                    call, error, client_request_id=client_request_id
                )
            self._record_tool_step_receipt(intent, observation)
            return observation
        except RuntimeClientError as error:
            observation = self._unknown(
                call, error, client_request_id=client_request_id
            )
            self._record_tool_step_receipt(intent, observation)
            return observation
        observation = self._observed(call, payload, reconciled=False)
        if (
            control is not None
            and control.cancellation.cancelled
            and observation.runtime_job_ref is not None
        ):
            observation = self.cancel_observation(
                call,
                observation,
                step_id=step_id,
                control=control,
                record_receipt=False,
            )
        self._record_tool_step_receipt(intent, observation)
        return observation

    def _prepare_tool_step_intent(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
        turn_id: str,
        operation: str,
        arguments: dict[str, JsonValue],
        client_request_id: str,
    ) -> HarnessToolStepIntent:
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
        self.run_store.prepare_tool_step(intent)
        self.committed = self.run_store.committed
        self._tool_step_intents[call.tool_call_id] = intent
        return intent

    def _record_tool_step_receipt(
        self,
        intent: HarnessToolStepIntent | None,
        observation: ToolObservation,
    ) -> None:
        if self.run_store is None or intent is None:
            return
        token = canonical_digest(
            {
                "intentDigest": intent.digest,
                "observationDigest": observation.digest,
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
        )
        self.run_store.record_tool_step_receipt(receipt, observation.to_dict())
        self.committed = self.run_store.committed

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
        job_id = observation.runtime_job_ref
        if job_id is None:
            return observation
        try:
            payload = self.runtime.call_tool(
                "task.cancel",
                {"schemaVersion": 1, "jobId": job_id},
            )
        except RuntimeClientError as error:
            result = ToolObservation(
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
        else:
            status = payload.get("status")
            if status == "cancelled":
                cancelled = self._observed(call, payload, reconciled=True)
                result = ToolObservation(
                    tool_call_id=cancelled.tool_call_id,
                    tool_name=cancelled.tool_name,
                    status="cancelled",
                    structured_content=cancelled.structured_content,
                    runtime_job_ref=cancelled.runtime_job_ref,
                    artifact_refs=cancelled.artifact_refs,
                    reconciled=True,
                )
            elif status in {"succeeded", "failed", "timed_out"}:
                result = self._observed(call, payload, reconciled=True)
            else:
                result = ToolObservation(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.name,
                    status="cancel-requested",
                    structured_content=dict(payload),
                    runtime_job_ref=job_id,
                    artifact_refs=_extract_artifacts(payload),
                    reconciled=True,
                )
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
        arguments = dict(call.arguments)
        workspace_id = self.committed.assignment.workspace_ref
        assert workspace_id is not None
        if call.name == "read_workspace":
            _only(arguments, {"relativePath", "mode", "offset", "maxBytes"}, call.name)
            relative_path = _required_string(arguments, "relativePath", call.name)
            if self.tool_grant is not None:
                try:
                    allowed_path = self.tool_grant.allows_path(call.name, relative_path)
                except ValueError as error:
                    raise ToolBridgeError(str(error)) from error
                if not allowed_path:
                    raise ToolBridgeError(
                        f"read_workspace path is outside the Tool Grant: {relative_path}"
                    )
            return (
                "workspace.read",
                {
                    "schemaVersion": 1,
                    "workspaceId": workspace_id,
                    "relativePath": relative_path,
                    "mode": _optional_string(arguments, "mode", "FULL"),
                    "offset": _optional_int(arguments, "offset", 0),
                    "maxBytes": _optional_int(
                        arguments, "maxBytes", 262_144, positive=True
                    ),
                },
                None,
            )
        if call.name == "mutate_workspace":
            _only(arguments, {"mutations"}, call.name)
            mutations = arguments.get("mutations")
            if not isinstance(mutations, list) or not mutations:
                raise ToolBridgeError(
                    "mutate_workspace mutations must be a non-empty list"
                )
            if self.tool_grant is not None:
                for mutation in mutations:
                    if not isinstance(mutation, dict):
                        raise ToolBridgeError(
                            "mutate_workspace mutations must be objects"
                        )
                    relative_path = mutation.get("relativePath")
                    if not isinstance(relative_path, str):
                        raise ToolBridgeError(
                            "mutate_workspace mutation omitted relativePath"
                        )
                    try:
                        allowed_path = self.tool_grant.allows_path(
                            call.name, relative_path
                        )
                    except ValueError as error:
                        raise ToolBridgeError(str(error)) from error
                    if not allowed_path:
                        raise ToolBridgeError(
                            f"mutate_workspace path is outside the Tool Grant: {relative_path}"
                        )
            request: dict[str, JsonValue] = {
                "schemaVersion": 1,
                "workspaceId": workspace_id,
                "mutations": mutations,
            }
            validate_json_value(request)
            return "workspace.mutate", request, None
        if call.name == "diff_workspace":
            _only(arguments, {"maxBytes"}, call.name)
            return (
                "workspace.diff",
                {
                    "schemaVersion": 1,
                    "workspaceId": workspace_id,
                    "maxBytes": _optional_int(
                        arguments, "maxBytes", 1_048_576, positive=True
                    ),
                },
                None,
            )
        if call.name == "run_check":
            _only(
                arguments,
                {"checkId", "waitMs", "stdoutTailBytes", "stderrTailBytes"},
                call.name,
            )
            if self.tool_grant is None:
                raise ToolBridgeError("run_check requires a Tool Grant")
            check_id = _required_string(arguments, "checkId", call.name)
            try:
                check = self.tool_grant.execution_check(check_id)
            except KeyError as error:
                raise ToolBridgeError(str(error)) from error
            try:
                request = build_harness_workspace_exec_request(
                    self.committed,
                    harness_run_id=self.harness_run_id,
                    step_id=step_id,
                    executable=check.executable,
                    args=check.args,
                    cwd_relative=check.cwd_relative,
                    env=dict(check.env),
                    timeout_ms=check.timeout_ms,
                    stdout_limit_bytes=check.stdout_limit_bytes,
                    stderr_limit_bytes=check.stderr_limit_bytes,
                    wait_ms=_optional_int(arguments, "waitMs", 0),
                    stdout_tail_bytes=_optional_int(
                        arguments, "stdoutTailBytes", 8_192
                    ),
                    stderr_tail_bytes=_optional_int(
                        arguments, "stderrTailBytes", 8_192
                    ),
                )
            except ValueError as error:
                raise ToolBridgeError(str(error)) from error
            client_request_id = request.get("clientRequestId")
            if not isinstance(client_request_id, str):
                raise ToolBridgeError("Runtime request omitted clientRequestId")
            return "workspace.exec", request, client_request_id
        if call.name == "run_in_workspace":
            if self.tool_grant is not None and not self.tool_grant.allow_opaque_exec:
                raise ToolBridgeError("opaque Runtime execution is not granted")
            allowed = {
                "executable",
                "args",
                "cwdRelative",
                "env",
                "timeoutMs",
                "stdoutLimitBytes",
                "stderrLimitBytes",
                "waitMs",
                "stdoutTailBytes",
                "stderrTailBytes",
            }
            _only(arguments, allowed, call.name)
            executable = _required_string(arguments, "executable", call.name)
            raw_args = arguments.get("args", [])
            if not isinstance(raw_args, list) or any(
                not isinstance(item, str) for item in raw_args
            ):
                raise ToolBridgeError("run_in_workspace args must be strings")
            raw_env = arguments.get("env", {})
            if not isinstance(raw_env, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in raw_env.items()
            ):
                raise ToolBridgeError("run_in_workspace env must contain string values")
            try:
                request = build_harness_workspace_exec_request(
                    self.committed,
                    harness_run_id=self.harness_run_id,
                    step_id=step_id,
                    executable=executable,
                    args=tuple(raw_args),
                    cwd_relative=_optional_string(arguments, "cwdRelative", "."),
                    env=dict(raw_env),
                    timeout_ms=_optional_int(arguments, "timeoutMs", 30_000),
                    stdout_limit_bytes=_optional_int(
                        arguments, "stdoutLimitBytes", 262_144
                    ),
                    stderr_limit_bytes=_optional_int(
                        arguments, "stderrLimitBytes", 262_144
                    ),
                    wait_ms=_optional_int(arguments, "waitMs", 0),
                    stdout_tail_bytes=_optional_int(
                        arguments, "stdoutTailBytes", 8_192
                    ),
                    stderr_tail_bytes=_optional_int(
                        arguments, "stderrTailBytes", 8_192
                    ),
                )
            except ValueError as error:
                raise ToolBridgeError(str(error)) from error
            client_request_id = request.get("clientRequestId")
            if not isinstance(client_request_id, str):
                raise ToolBridgeError("Runtime request omitted clientRequestId")
            return "workspace.exec", request, client_request_id
        if call.name == "observe_job":
            _only(
                arguments,
                {"jobId", "waitMs", "stdoutTailBytes", "stderrTailBytes"},
                call.name,
            )
            job_id = _required_string(arguments, "jobId", call.name)
            if self.tool_grant is not None and job_id not in self._known_job_ids:
                raise ToolBridgeError(
                    "observe_job may only observe a Job created by this Run"
                )
            return (
                "task.observe",
                {
                    "schemaVersion": 1,
                    "jobId": job_id,
                    "waitMs": _optional_int(arguments, "waitMs", 0),
                    "stdoutTailBytes": _optional_int(
                        arguments, "stdoutTailBytes", 8_192
                    ),
                    "stderrTailBytes": _optional_int(
                        arguments, "stderrTailBytes", 8_192
                    ),
                },
                None,
            )
        if call.name == "read_artifact":
            _only(arguments, {"jobId", "artifactId", "offset", "maxBytes"}, call.name)
            job_id = _required_string(arguments, "jobId", call.name)
            artifact_id = _required_string(arguments, "artifactId", call.name)
            if (
                self.tool_grant is not None
                and (job_id, artifact_id) not in self._known_artifacts
            ):
                raise ToolBridgeError(
                    "read_artifact may only read an Artifact observed in this Run"
                )
            return (
                "artifact.read",
                {
                    "schemaVersion": 1,
                    "jobId": job_id,
                    "artifactId": artifact_id,
                    "offset": _optional_int(arguments, "offset", 0),
                    "maxBytes": _optional_int(
                        arguments, "maxBytes", 262_144, positive=True
                    ),
                },
                None,
            )
        raise ToolBridgeError(f"Tool is not in the Ordivon Harness ACI: {call.name}")

    def _unknown(
        self,
        call: AgentToolCall,
        error: RuntimeClientError,
        *,
        client_request_id: str | None,
    ) -> ToolObservation:
        if client_request_id is not None:
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


def _only(arguments: dict[str, JsonValue], allowed: set[str], tool_name: str) -> None:
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise ToolBridgeError(f"{tool_name} received unknown fields: {unknown}")


def _required_string(
    arguments: dict[str, JsonValue], field: str, tool_name: str
) -> str:
    value = arguments.get(field)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ToolBridgeError(f"{tool_name} requires trimmed string {field}")
    return value


def _optional_string(arguments: dict[str, JsonValue], field: str, default: str) -> str:
    value = arguments.get(field, default)
    if not isinstance(value, str) or value != value.strip():
        raise ToolBridgeError(f"{field} must be a trimmed string")
    return value


def _optional_int(
    arguments: dict[str, JsonValue],
    field: str,
    default: int,
    *,
    positive: bool = False,
) -> int:
    value = arguments.get(field, default)
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise ToolBridgeError(f"{field} must be a {qualifier} integer")
    return value

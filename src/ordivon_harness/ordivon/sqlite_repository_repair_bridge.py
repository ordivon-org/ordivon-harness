from __future__ import annotations

from dataclasses import dataclass

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from ..agent_tool_observation import HarnessToolObservation
from ..core_contracts import HarnessRunContract
from ..execution_binding import HarnessExecutionBinding
from ..protocol import (
    HarnessRecoveryConsequence,
    HarnessToolStepIntent,
)
from ..runtime_port import (
    HarnessRuntimeClient,
    HarnessRuntimeClientError,
    HarnessRuntimeToolRejected,
    runtime_error_value,
)
from .control import ExecutionControl
from .model import AgentRunConclusion, AgentToolCall, AgentToolDefinition
from .runtime_lowering import lower_runtime_tool
from .run_store_port import HarnessRunContinuityStore
from .sqlite_agent_bridge import SQLiteHarnessAgentBridge
from .sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind


def _object_schema(
    properties: dict[str, JsonValue], required: tuple[str, ...] = ()
) -> dict[str, JsonValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


_INTEGER = {"type": "integer", "minimum": 0}
_STRING = {"type": "string", "minLength": 1}

READ_WORKSPACE_DEFINITION = AgentToolDefinition(
    "read_workspace",
    "Read bounded UTF-8 content from one frozen repository-repair Workspace path.",
    _object_schema(
        {
            "relativePath": _STRING,
            "mode": {"type": "string", "enum": ["FULL", "SLICE"]},
            "byteOffset": _INTEGER,
            "maxBytes": {"type": "integer", "minimum": 1},
        },
        ("relativePath",),
    ),
)
PATCH_WORKSPACE_DEFINITION = AgentToolDefinition(
    "patch_workspace",
    "Apply a digest-guarded text patch to allocation.py or artifacts/completion.json.",
    _object_schema(
        {
            "files": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": _object_schema(
                    {
                        "relativePath": _STRING,
                        "expectedDigest": {"type": ["string", "null"]},
                        "edits": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 16,
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
                                                    "column": _INTEGER,
                                                },
                                                ("line", "column"),
                                            ),
                                            "end": _object_schema(
                                                {
                                                    "line": {
                                                        "type": "integer",
                                                        "minimum": 1,
                                                    },
                                                    "column": _INTEGER,
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
)
RUN_CHECK_DEFINITION = AgentToolDefinition(
    "run_check",
    "Run the frozen visible unittest check by the exact checkId visible-tests.",
    _object_schema(
        {
            "checkId": _STRING,
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
)
DIFF_WORKSPACE_DEFINITION = AgentToolDefinition(
    "diff_workspace",
    "Read a bounded structured Git diff for the repository-repair Workspace.",
    _object_schema({"maxBytes": {"type": "integer", "minimum": 1}}),
)

INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS = (
    READ_WORKSPACE_DEFINITION,
    PATCH_WORKSPACE_DEFINITION,
    RUN_CHECK_DEFINITION,
    DIFF_WORKSPACE_DEFINITION,
)
INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE: dict[str, JsonValue] = {
    "schemaVersion": 1,
    "kind": "ordivon.independent-repository-repair-tool-surface",
    "taskId": "HARNESS-REPO-REPAIR-001",
    "tools": [item.to_dict() for item in INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS],
}
INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST = canonical_digest(
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE
)
INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT: dict[str, JsonValue] = {
    "schemaVersion": 1,
    "kind": "ordivon.independent-repository-repair-tool-grant",
    "taskId": "HARNESS-REPO-REPAIR-001",
    "tools": [
        "read_workspace",
        "patch_workspace",
        "run_check",
        "diff_workspace",
    ],
    "runtimeOperations": [
        "workspace.read",
        "workspace.patch",
        "workspace.patch.get",
        "workspace.exec",
        "workspace.diff",
        "task.list",
        "task.observe",
    ],
    "readPaths": [
        "SPEC.md",
        "allocation.py",
        "test_allocation.py",
        "artifacts/completion.json",
    ],
    "patchPaths": ["allocation.py", "artifacts/completion.json"],
    "executionChecks": ["visible-tests"],
    "opaqueExecutionAllowed": False,
}
INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST = canonical_digest(
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT
)


@dataclass(frozen=True, slots=True)
class _ExecutionCheck:
    executable: str
    args: tuple[str, ...]
    cwd_relative: str
    env: tuple[tuple[str, str], ...]
    timeout_ms: int
    stdout_limit_bytes: int
    stderr_limit_bytes: int


class _RepositoryRepairGrant:
    allow_opaque_exec = False
    _read_paths = frozenset(
        {
            "SPEC.md",
            "allocation.py",
            "test_allocation.py",
            "artifacts/completion.json",
        }
    )
    _patch_paths = frozenset({"allocation.py", "artifacts/completion.json"})
    _visible_check = _ExecutionCheck(
        executable="/usr/bin/python3",
        args=("-m", "unittest", "-v", "test_allocation.py"),
        cwd_relative=".",
        env=(("PYTHONDONTWRITEBYTECODE", "1"),),
        timeout_ms=60_000,
        stdout_limit_bytes=65_536,
        stderr_limit_bytes=65_536,
    )

    def allows_path(self, name: str, relative_path: str) -> bool:
        if relative_path.startswith("/") or ".." in relative_path.split("/"):
            return False
        if name == "read_workspace":
            return relative_path in self._read_paths
        if name == "patch_workspace":
            return relative_path in self._patch_paths
        return False

    def execution_check(self, check_id: str) -> _ExecutionCheck:
        if check_id != "visible-tests":
            raise KeyError(f"repository-repair Tool Grant has no Check: {check_id}")
        return self._visible_check


_REPOSITORY_REPAIR_GRANT = _RepositoryRepairGrant()
_RECOVERY_CONSEQUENCES = {
    "read_workspace": HarnessRecoveryConsequence.OBSERVATION_ONLY,
    "diff_workspace": HarnessRecoveryConsequence.OBSERVATION_ONLY,
    "patch_workspace": HarnessRecoveryConsequence.WORKSPACE_CHANGE_POSSIBLE,
    "run_check": HarnessRecoveryConsequence.PROCESS_OR_EXTERNAL_EFFECT_POSSIBLE,
}
_EFFECT_OPERATIONS = frozenset({"workspace.exec", "workspace.patch"})


class SQLiteHarnessRepositoryRepairRuntimeBridge(SQLiteHarnessRuntimeBridge):
    """Independent Runtime bridge for the frozen repository-repair Trial only.

    The surface is deliberately closed to read, digest-fenced patch, one named
    visible Check, and diff. Every effect receives a durable Intent and Dispatch
    Fence. Response loss is reconciled by the original Runtime identity without
    blind redispatch.
    """

    def __init__(
        self,
        contract: HarnessRunContract,
        run_store: HarnessRunContinuityStore,
        execution_binding: HarnessExecutionBinding,
        runtime: HarnessRuntimeClient,
        *,
        provider_source=None,
        provider_holder_id: str | None = None,
    ) -> None:
        SQLiteHarnessAgentBridge.__init__(
            self,
            contract,
            run_store,
            provider_source=provider_source,
            provider_holder_id=provider_holder_id,
            expected_tool_catalog_digest=(
                INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST
            ),
        )
        binding = run_store.binding
        if (
            execution_binding.harness_run_id != contract.harness_run_id
            or execution_binding.assignment_id != binding.assignment_id
            or execution_binding.assignment_generation != binding.assignment_generation
            or execution_binding.assignment_digest != binding.assignment_digest
        ):
            raise ValueError(
                "Harness Execution Binding differs from the independent Run binding"
            )
        if (
            execution_binding.tool_catalog_digest
            != INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST
            or contract.tool_catalog_digest
            != INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST
        ):
            raise ValueError("repository-repair Tool catalog differs")
        if (
            execution_binding.tool_grant_digest
            != INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST
            or contract.tool_grant_digest
            != INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST
        ):
            raise ValueError("repository-repair Tool Grant differs")
        if execution_binding.deadline_ms != contract.deadline_ms:
            raise ValueError("Harness Execution Binding deadline differs")
        if not execution_binding.runtime_references:
            raise ValueError("independent Runtime execution requires foreign references")
        if any(
            reference.namespace != "ordivon.harness"
            for reference in execution_binding.runtime_references
        ):
            raise ValueError(
                "independent Runtime execution may reference only ordivon.harness authority"
            )
        self.execution_binding = execution_binding
        self.runtime = runtime
        self._seen_tool_call_ids: set[str] = set()

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        return INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS

    def validate_conclusion(self, conclusion: AgentRunConclusion) -> None:
        if conclusion.status != "candidate_completed":
            return
        try:
            retained = self.run_store.load_current_snapshot()
        except KeyError:
            observations: list[HarnessToolObservation] = []
        else:
            observations = [
                HarnessToolObservation.from_dict(value)
                for value in retained.state.observations
            ]
        try:
            current = self.run_store.load_current_tool_step()
        except KeyError:
            current = None
        if (
            current is not None
            and current.receipt is not None
            and current.receipt.terminal
            and current.observation is not None
        ):
            latest = HarnessToolObservation.from_dict(current.observation)
            if latest.digest not in {item.digest for item in observations}:
                observations.append(latest)
        observed = tuple(item for item in observations if item.status == "observed")
        read_paths = [
            item.structured_content.get("relativePath")
            for item in observed
            if item.tool_name == "read_workspace"
        ]
        patch_paths = [
            item.structured_content.get("relativePath")
            for item in observed
            if item.tool_name == "patch_workspace"
        ]
        check_passed = any(
            item.tool_name == "run_check"
            and item.structured_content.get("status") == "succeeded"
            for item in observed
        )
        diff_observed = any(
            item.tool_name == "diff_workspace" for item in observed
        )
        expected_artifact_ref = (
            f"workspace-artifact:{self.execution_binding.workspace_ref}:"
            "artifacts/completion.json"
        )
        missing: list[str] = []
        if read_paths.count("allocation.py") < 2:
            missing.append("allocation.py must be read before and after mutation")
        if "allocation.py" not in patch_paths:
            missing.append("allocation.py patch is not observed")
        if not check_passed:
            missing.append("visible-tests has no successful Runtime receipt")
        if not diff_observed:
            missing.append("final Workspace diff is not observed")
        if expected_artifact_ref not in conclusion.artifact_refs:
            missing.append("required completion Artifact reference is absent")
        if missing:
            raise ToolBridgeError(
                "; ".join(missing),
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )

    def validate_runtime_catalog(self) -> None:
        if (
            self.contract.tool_catalog_digest
            != INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST
            or self.execution_binding.tool_catalog_digest
            != INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST
        ):
            raise ToolBridgeError(
                "repository-repair Runtime Tool catalog drifted",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )

    def reconcile_current_tool_step(
        self,
        *,
        control: ExecutionControl,
    ) -> HarnessToolObservation:
        current = self.run_store.load_current_tool_step()
        if current.receipt is not None and current.receipt.terminal:
            if current.observation is None:
                raise ToolBridgeError(
                    "terminal Tool Receipt omitted its Observation",
                    kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
                )
            return HarnessToolObservation.from_dict(current.observation)
        if control.stop_requested:
            raise ToolBridgeError(
                "execution control stopped before Tool reconciliation",
                kind=ToolBridgeErrorKind.CONTROL_STOPPED,
            )
        if current.intent.runtime_operation == "workspace.patch":
            observation = self._reconcile_workspace_patch(
                current.intent,
                control=control,
            )
        elif current.intent.runtime_operation == "workspace.exec":
            observation = self._reconcile_by_client_request(
                tool_call_id=current.intent.tool_call_id,
                tool_name=current.intent.tool_name,
                client_request_id=current.intent.client_request_id,
                query=None,
                relative_path=None,
                control=control,
            )
        else:
            observation = self._unknown_observation(
                current.intent.tool_call_id,
                current.intent.tool_name,
                reason=(
                    "synchronous observation response was lost; the operation is "
                    "not blindly repeated during recovery"
                ),
                client_request_id=current.intent.client_request_id,
                query=None,
                relative_path=None,
                reconciled=True,
            )
        return self._record_observation(
            current.intent,
            observation,
            previous_receipt=current.receipt,
        )

    def _execute(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
        turn_id: str,
        control: ExecutionControl | None,
    ) -> HarnessToolObservation:
        allowed = {item.name for item in INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS}
        if call.name not in allowed:
            raise ToolBridgeError(
                f"repository-repair Runtime surface does not expose {call.name}",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        if call.tool_call_id in self._seen_tool_call_ids:
            raise ToolBridgeError(
                f"duplicate Tool Call identity: {call.tool_call_id}",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        if control is not None and control.stop_requested:
            raise ToolBridgeError(
                "execution control stopped before Tool preparation",
                kind=ToolBridgeErrorKind.CONTROL_STOPPED,
            )
        operation, request, external_request_id = lower_runtime_tool(
            call,
            step_id=step_id,
            execution_binding=self.execution_binding,
            tool_grant=_REPOSITORY_REPAIR_GRANT,
            known_job_ids=frozenset(),
            known_artifacts=frozenset(),
        )
        internal_request_id = external_request_id or (
            "request:harness-observation:"
            + canonical_digest(
                {
                    "harnessRunId": self.contract.harness_run_id,
                    "stepId": step_id,
                    "toolCallDigest": call.digest,
                    "runtimeOperation": operation,
                }
            )[7:39]
        )
        binding = self.run_store.binding
        intent = HarnessToolStepIntent(
            intent_id=(
                "harness-tool-step-intent:"
                f"{self.contract.harness_run_id.removeprefix('harness-run:')}:"
                f"{call.digest[7:31]}"
            ),
            harness_run_id=self.contract.harness_run_id,
            assignment_id=binding.assignment_id,
            assignment_generation=binding.assignment_generation,
            assignment_digest=binding.assignment_digest,
            turn_id=self._durable_turn_id(turn_id, step_id),
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            tool_call_digest=call.digest,
            runtime_operation=operation,
            runtime_arguments_digest=canonical_digest(request),
            client_request_id=internal_request_id,
            recovery_consequence=_RECOVERY_CONSEQUENCES[call.name],
            created_at_ms=self.run_store.clock_ms(),
        )
        self.run_store.prepare_tool_step(intent)
        current = self.run_store.load_current_tool_step()
        if current.intent != intent or current.fence is None:
            raise ToolBridgeError(
                "repository-repair Tool preparation omitted its durable Fence",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        self.run_store.assert_dispatch_fence_current(current.fence)
        dispatch_request = (
            self._with_dispatch_fence(request, current.fence)
            if operation == "workspace.exec"
            else request
        )
        relative_path = self._relative_path(call)
        if control is not None and control.stop_requested:
            observation = HarnessToolObservation(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                status="rejected",
                structured_content={
                    "type": "ExecutionControlStopped",
                    "safeToCorrect": True,
                    "clientRequestId": internal_request_id,
                },
            )
            return self._record_observation(intent, observation)
        try:
            payload = self.runtime.call_tool(operation, dispatch_request)
            validate_json_value(payload)
            if operation == "workspace.exec":
                observation = self._terminal_observation(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.name,
                    payload=payload,
                    query=None,
                    relative_path=relative_path,
                    reconciled=False,
                    control=control,
                )
            else:
                observation = self._observation_from_payload(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.name,
                    payload=payload,
                    query=None,
                    relative_path=relative_path,
                    reconciled=False,
                )
        except HarnessRuntimeToolRejected as error:
            observation = self._recover_after_error(
                call,
                intent,
                error,
                relative_path=relative_path,
                control=control,
            )
        except HarnessRuntimeClientError as error:
            observation = self._recover_after_error(
                call,
                intent,
                error,
                relative_path=relative_path,
                control=control,
            )
        return self._record_observation(intent, observation)

    def _recover_after_error(
        self,
        call: AgentToolCall,
        intent: HarnessToolStepIntent,
        error: HarnessRuntimeClientError,
        *,
        relative_path: str | None,
        control: ExecutionControl | None,
    ) -> HarnessToolObservation:
        if isinstance(error, HarnessRuntimeToolRejected) and error.detail.commit_state in {
            "not_started",
            "not_committed",
        }:
            return HarnessToolObservation(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                status="rejected",
                structured_content={
                    **runtime_error_value(error),
                    "clientRequestId": intent.client_request_id,
                    "relativePath": relative_path,
                },
            )
        if intent.runtime_operation == "workspace.patch":
            return self._reconcile_workspace_patch(intent, control=control)
        if intent.runtime_operation == "workspace.exec":
            return self._reconcile_by_client_request(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                client_request_id=intent.client_request_id,
                query=None,
                relative_path=relative_path,
                control=control,
            )
        return self._unknown_observation(
            call.tool_call_id,
            call.name,
            reason=(
                "synchronous observation failed and was not blindly redispatched: "
                f"{type(error).__name__}: {error}"
            ),
            client_request_id=intent.client_request_id,
            query=None,
            relative_path=relative_path,
            reconciled=True,
        )

    def _reconcile_workspace_patch(
        self,
        intent: HarnessToolStepIntent,
        *,
        control: ExecutionControl | None,
    ) -> HarnessToolObservation:
        if control is not None and control.stop_requested:
            return self._unknown_observation(
                intent.tool_call_id,
                intent.tool_name,
                reason="execution control stopped before Runtime Patch reconciliation",
                client_request_id=intent.client_request_id,
                query=None,
                relative_path=None,
                reconciled=True,
            )
        try:
            payload = self.runtime.call_tool(
                "workspace.patch.get",
                {
                    "schemaVersion": 1,
                    "clientRequestId": intent.client_request_id,
                },
            )
            validate_json_value(payload)
        except HarnessRuntimeToolRejected as error:
            if error.detail.commit_state == "not_committed":
                return HarnessToolObservation(
                    intent.tool_call_id,
                    intent.tool_name,
                    "rejected",
                    {
                        **runtime_error_value(error),
                        "clientRequestId": intent.client_request_id,
                    },
                    reconciled=True,
                )
            return self._unknown_observation(
                intent.tool_call_id,
                intent.tool_name,
                reason=f"Runtime Patch reconciliation rejected: {error}",
                client_request_id=intent.client_request_id,
                query=None,
                relative_path=None,
                reconciled=True,
            )
        except HarnessRuntimeClientError as error:
            return self._unknown_observation(
                intent.tool_call_id,
                intent.tool_name,
                reason=f"Runtime Patch reconciliation failed: {error}",
                client_request_id=intent.client_request_id,
                query=None,
                relative_path=None,
                reconciled=True,
            )
        state = payload.get("state")
        if state == "unknown":
            status = "unknown"
        elif state == "prepared":
            status = "rejected"
        else:
            status = "observed"
        return HarnessToolObservation(
            intent.tool_call_id,
            intent.tool_name,
            status,
            dict(payload),
            reconciled=True,
        )

    @staticmethod
    def _relative_path(call: AgentToolCall) -> str | None:
        value = call.arguments.get("relativePath")
        if isinstance(value, str):
            return value
        files = call.arguments.get("files")
        if isinstance(files, list) and files and isinstance(files[0], dict):
            path = files[0].get("relativePath")
            return path if isinstance(path, str) else None
        return None


__all__ = [
    "DIFF_WORKSPACE_DEFINITION",
    "INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS",
    "INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT",
    "INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST",
    "INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE",
    "INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST",
    "PATCH_WORKSPACE_DEFINITION",
    "READ_WORKSPACE_DEFINITION",
    "RUN_CHECK_DEFINITION",
    "SQLiteHarnessRepositoryRepairRuntimeBridge",
]

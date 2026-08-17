from __future__ import annotations

import json

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from ..agent_tool_observation import (
    HarnessArtifactReference,
    HarnessToolObservation,
)
from ..core_contracts import HarnessRunContract
from ..execution_binding import HarnessExecutionBinding
from ..protocol import (
    HarnessRecoveryConsequence,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
    HarnessToolStepStatus,
)
from ..run_state import HarnessRunState
from ..runtime_port import (
    HarnessRuntimeClient,
    HarnessRuntimeClientError,
    HarnessRuntimeToolRejected,
    find_runtime_jobs_by_client_request,
    runtime_error_value,
)
from .control import ExecutionControl
from .model import AgentToolCall, AgentToolDefinition
from .runtime_lowering import lower_runtime_tool
from .run_store_port import HarnessRunContinuityStore
from .sqlite_agent_bridge import SQLiteHarnessAgentBridge
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind

SEARCH_WORKSPACE_DEFINITION = AgentToolDefinition(
    name="search_workspace",
    description=(
        "Search UTF-8 workspace text with bounded ripgrep JSON output. "
        "This operation is observation-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "relativePath": {"type": "string", "default": "."},
            "maxMatches": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 50,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)
INDEPENDENT_SEARCH_TOOL_SURFACE: dict[str, JsonValue] = {
    "schemaVersion": 1,
    "kind": "ordivon.independent-search-tool-surface",
    "tools": [SEARCH_WORKSPACE_DEFINITION.to_dict()],
}
INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST = canonical_digest(INDEPENDENT_SEARCH_TOOL_SURFACE)
INDEPENDENT_SEARCH_TOOL_GRANT: dict[str, JsonValue] = {
    "schemaVersion": 1,
    "kind": "ordivon.independent-search-tool-grant",
    "tools": ["search_workspace"],
    "runtimeOperations": ["workspace.exec"],
    "workspaceMutationAllowed": False,
}
INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST = canonical_digest(INDEPENDENT_SEARCH_TOOL_GRANT)

_RUNTIME_DELIVERY_DISPOSITIONS = frozenset(
    {"in_progress", "committed", "reconciliation_required", "unknown"}
)


def _runtime_delivery_state(payload: dict[str, JsonValue]) -> str:
    """Return the safe Harness observation action from exact Runtime semantics.

    Runtime ``status`` is a compatibility summary and cannot decide whether physical
    execution has mechanically converged.  In particular, a succeeded resolution may
    still carry ``deliveryDisposition=reconciliation_required``.
    """

    execution_terminal = payload.get("executionTerminal")
    execution_disposition = payload.get("executionDisposition")
    delivery_disposition = payload.get("deliveryDisposition")
    recovery_required = payload.get("recoveryRequired")
    result_available = payload.get("resultAvailable")
    semantic_completion_evaluated = payload.get("semanticCompletionEvaluated")

    if not isinstance(execution_terminal, bool):
        raise HarnessRuntimeClientError("Runtime observation omitted executionTerminal")
    if execution_disposition is not None and not isinstance(execution_disposition, str):
        raise HarnessRuntimeClientError("Runtime executionDisposition is invalid")
    if delivery_disposition not in _RUNTIME_DELIVERY_DISPOSITIONS:
        raise HarnessRuntimeClientError("Runtime deliveryDisposition is invalid")
    if not isinstance(recovery_required, bool):
        raise HarnessRuntimeClientError("Runtime observation omitted recoveryRequired")
    if not isinstance(result_available, bool):
        raise HarnessRuntimeClientError("Runtime observation omitted resultAvailable")
    if semantic_completion_evaluated is not False:
        raise HarnessRuntimeClientError(
            "Runtime must not claim Harness/domain semantic completion"
        )

    if recovery_required or delivery_disposition == "reconciliation_required":
        return "reconcile"
    if delivery_disposition == "unknown":
        if not execution_terminal or execution_disposition != "lost" or not result_available:
            raise HarnessRuntimeClientError("Runtime unknown delivery projection is inconsistent")
        return "unknown"
    if delivery_disposition == "in_progress":
        if execution_terminal or execution_disposition is not None or result_available:
            raise HarnessRuntimeClientError("Runtime in-progress projection is inconsistent")
        return "reconcile"
    if not execution_terminal or execution_disposition is None or not result_available:
        raise HarnessRuntimeClientError("Runtime committed terminal projection is incomplete")
    return "terminal"


class SQLiteHarnessRuntimeBridge(SQLiteHarnessAgentBridge):
    """Independent Provider + observation-only Runtime bridge.

    P0 supports exactly ``search_workspace`` lowered to one ``workspace.exec``.
    The Runtime request is fenced by Harness-owned authority. Transport response
    loss is reconciled by the original ``clientRequestId`` and is never repaired
    through blind redispatch.
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
        super().__init__(
            contract,
            run_store,
            provider_source=provider_source,
            provider_holder_id=provider_holder_id,
            expected_tool_catalog_digest=INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
            expected_tool_grant_digest=INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
        )
        binding = run_store.binding
        if (
            execution_binding.harness_run_id != contract.harness_run_id
            or execution_binding.assignment_id != binding.assignment_id
            or execution_binding.assignment_generation != binding.assignment_generation
            or execution_binding.assignment_digest != binding.assignment_digest
        ):
            raise ValueError("Harness Execution Binding differs from the independent Run binding")
        if (
            execution_binding.tool_catalog_digest != INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST
            or execution_binding.tool_catalog_digest != contract.tool_catalog_digest
        ):
            raise ValueError("Harness Execution Binding Tool catalog differs")
        if (
            execution_binding.tool_grant_digest != INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST
            or contract.tool_grant_digest != INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST
        ):
            raise ValueError("Harness Execution Binding Tool Grant differs")
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
        return (SEARCH_WORKSPACE_DEFINITION,)

    def validate_runtime_catalog(self) -> None:
        if (
            self.contract.tool_catalog_digest != INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST
            or self.execution_binding.tool_catalog_digest != INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST
        ):
            raise ToolBridgeError(
                "independent Runtime Tool catalog drifted",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )

    def bind_run_state(
        self,
        *,
        messages: tuple[dict[str, JsonValue], ...],
        observations: tuple[HarnessToolObservation, ...],
        remaining_budget: dict[str, JsonValue],
        requested_model_id: str,
        effective_model_id: str | None,
        active_elapsed_ms: int | None = None,
        seen_model_call_ids: tuple[str, ...] = (),
        seen_tool_call_ids: tuple[str, ...] = (),
        provider_usage: tuple[dict[str, JsonValue], ...] = (),
        effective_model_ids: tuple[str, ...] = (),
    ) -> None:
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

    def restore_seen_tool_calls(self, tool_call_ids: tuple[str, ...]) -> None:
        if len(tool_call_ids) != len(set(tool_call_ids)):
            raise ValueError("restored Tool Call identities must be unique")
        self._seen_tool_call_ids = set(tool_call_ids)

    def restore_current_attempt_tool_exchanges(
        self,
        observations: tuple[HarnessToolObservation, ...],
    ) -> tuple[dict[str, JsonValue], ...]:
        restorer = getattr(
            self.run_store,
            "load_current_attempt_tool_exchange_messages",
            None,
        )
        if not callable(restorer):
            raise ToolBridgeError(
                "Runtime continuity store cannot reconstruct current-attempt Tool exchanges",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return restorer(observations)

    def execute(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
    ) -> HarnessToolObservation:
        turn_token = canonical_digest(
            {"harnessRunId": self.contract.harness_run_id, "stepId": step_id}
        )[7:31]
        return self._execute(
            call,
            step_id=step_id,
            turn_id=f"turn:independent-runtime:{turn_token}",
            control=None,
        )

    def execute_with_control(
        self,
        call: AgentToolCall,
        *,
        step_id: str,
        turn_id: str,
        control: ExecutionControl,
    ) -> HarnessToolObservation:
        return self._execute(
            call,
            step_id=step_id,
            turn_id=turn_id,
            control=control,
        )

    def current_tool_step_intent(self) -> HarnessToolStepIntent:
        return self.run_store.load_current_tool_step().intent

    def reconcile_current_tool_step(
        self,
        *,
        control: ExecutionControl,
    ) -> HarnessToolObservation:
        current = self.run_store.load_current_tool_step()
        if current.receipt is not None and current.receipt.terminal:
            if current.observation is None:
                raise ToolBridgeError(
                    "terminal Tool Observation content was not retained by the Privacy policy; "
                    "caller-authorized Tool content rehydration is required",
                    kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
                )
            return HarnessToolObservation.from_dict(current.observation)
        if control.stop_requested:
            raise ToolBridgeError(
                "execution control stopped before Tool reconciliation",
                kind=ToolBridgeErrorKind.CONTROL_STOPPED,
            )
        observation = self._reconcile_by_client_request(
            tool_call_id=current.intent.tool_call_id,
            tool_name=current.intent.tool_name,
            client_request_id=current.intent.client_request_id,
            query=None,
            relative_path=None,
            control=control,
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
        if call.name != "search_workspace":
            raise ToolBridgeError(
                f"independent Runtime surface does not expose {call.name}",
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
        operation, request, client_request_id = lower_runtime_tool(
            call,
            step_id=step_id,
            execution_binding=self.execution_binding,
            tool_grant=None,
            known_job_ids=frozenset(),
            known_artifacts=frozenset(),
        )
        if operation != "workspace.exec":
            raise ToolBridgeError(
                "independent search Tool did not lower to workspace.exec",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        binding = self.run_store.binding
        durable_turn_id = self._durable_turn_id(turn_id, step_id)
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
            turn_id=durable_turn_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            tool_call_digest=call.digest,
            runtime_operation=operation,
            runtime_arguments_digest=canonical_digest(request),
            client_request_id=client_request_id,
            recovery_consequence=HarnessRecoveryConsequence.OBSERVATION_ONLY,
            created_at_ms=self.run_store.clock_ms(),
        )
        self.run_store.prepare_tool_step(intent)
        current = self.run_store.load_current_tool_step()
        if current.intent != intent or current.fence is None:
            raise ToolBridgeError(
                "independent Tool preparation omitted its durable Fence",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        self.run_store.assert_dispatch_fence_current(current.fence)
        fenced_request = self._with_dispatch_fence(request, current.fence)
        query = call.arguments.get("query")
        relative_path = call.arguments.get("relativePath", ".")
        if not isinstance(query, str) or not isinstance(relative_path, str):
            raise ToolBridgeError(
                "search_workspace arguments differ from the lowered request",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        if control is not None and control.stop_requested:
            observation = HarnessToolObservation(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                status="rejected",
                structured_content={
                    "type": "ExecutionControlStopped",
                    "safeToCorrect": True,
                    "clientRequestId": client_request_id,
                },
            )
            return self._record_observation(intent, observation)
        try:
            payload = self.runtime.call_tool(operation, fenced_request)
            validate_json_value(payload)
            observation = self._terminal_observation(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                payload=payload,
                query=query,
                relative_path=relative_path,
                reconciled=False,
                control=control,
            )
        except HarnessRuntimeToolRejected as error:
            if error.detail.commit_state in {"not_started", "not_committed"}:
                observation = HarnessToolObservation(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.name,
                    status="rejected",
                    structured_content={
                        **runtime_error_value(error),
                        "clientRequestId": client_request_id,
                        "query": query,
                        "relativePath": relative_path,
                    },
                )
            else:
                observation = self._reconcile_by_client_request(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.name,
                    client_request_id=client_request_id,
                    query=query,
                    relative_path=relative_path,
                    control=control,
                )
        except HarnessRuntimeClientError:
            observation = self._reconcile_by_client_request(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                client_request_id=client_request_id,
                query=query,
                relative_path=relative_path,
                control=control,
            )
        return self._record_observation(intent, observation)

    def _terminal_observation(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        payload: dict[str, JsonValue],
        query: str | None,
        relative_path: str | None,
        reconciled: bool,
        control: ExecutionControl | None,
    ) -> HarnessToolObservation:
        current = dict(payload)
        for _ in range(20):
            try:
                delivery_state = _runtime_delivery_state(current)
            except HarnessRuntimeClientError as error:
                return self._unknown_observation(
                    tool_call_id,
                    tool_name,
                    reason=f"Runtime observation semantics invalid: {error}",
                    client_request_id=None,
                    query=query,
                    relative_path=relative_path,
                    reconciled=reconciled,
                    runtime_job_ref=(
                        current.get("jobId")
                        if isinstance(current.get("jobId"), str)
                        else None
                    ),
                )
            if delivery_state == "terminal":
                return self._observation_from_payload(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    payload=current,
                    query=query,
                    relative_path=relative_path,
                    reconciled=reconciled,
                )
            if delivery_state == "unknown":
                return self._unknown_observation(
                    tool_call_id,
                    tool_name,
                    reason="Runtime terminal delivery is unknown",
                    client_request_id=None,
                    query=query,
                    relative_path=relative_path,
                    reconciled=reconciled,
                    runtime_job_ref=(
                        current.get("jobId")
                        if isinstance(current.get("jobId"), str)
                        else None
                    ),
                )
            job_id = current.get("jobId")
            if not isinstance(job_id, str):
                return self._unknown_observation(
                    tool_call_id,
                    tool_name,
                    reason="Runtime response was non-terminal and omitted jobId",
                    client_request_id=None,
                    query=query,
                    relative_path=relative_path,
                    reconciled=reconciled,
                )
            if control is not None and control.stop_requested:
                return self._unknown_observation(
                    tool_call_id,
                    tool_name,
                    reason="execution control stopped before Runtime became terminal",
                    client_request_id=None,
                    query=query,
                    relative_path=relative_path,
                    reconciled=reconciled,
                    runtime_job_ref=job_id,
                )
            wait_ms = 30_000 if control is None else min(30_000, control.remaining_ms)
            try:
                current = self.runtime.call_tool(
                    "task.observe",
                    {
                        "schemaVersion": 1,
                        "jobId": job_id,
                        "waitMs": max(0, wait_ms),
                        "stdoutTailBytes": 65_536,
                        "stderrTailBytes": 65_536,
                    },
                )
                validate_json_value(current)
            except HarnessRuntimeClientError as error:
                return self._unknown_observation(
                    tool_call_id,
                    tool_name,
                    reason=f"Runtime observation failed: {type(error).__name__}: {error}",
                    client_request_id=None,
                    query=query,
                    relative_path=relative_path,
                    reconciled=True,
                    runtime_job_ref=job_id,
                )
        return self._unknown_observation(
            tool_call_id,
            tool_name,
            reason="Runtime remained non-terminal after the bounded observation loop",
            client_request_id=None,
            query=query,
            relative_path=relative_path,
            reconciled=True,
            runtime_job_ref=(
                current.get("jobId") if isinstance(current.get("jobId"), str) else None
            ),
        )

    def _reconcile_by_client_request(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        client_request_id: str,
        query: str | None,
        relative_path: str | None,
        control: ExecutionControl | None,
    ) -> HarnessToolObservation:
        try:
            matches = find_runtime_jobs_by_client_request(
                self.runtime,
                client_request_id,
            )
        except HarnessRuntimeClientError as error:
            return self._unknown_observation(
                tool_call_id,
                tool_name,
                reason=f"Runtime Job lookup failed: {type(error).__name__}: {error}",
                client_request_id=client_request_id,
                query=query,
                relative_path=relative_path,
                reconciled=True,
            )
        if len(matches) != 1:
            return self._unknown_observation(
                tool_call_id,
                tool_name,
                reason=(
                    "Runtime response loss did not reconcile to exactly one Job; "
                    f"matches={len(matches)}"
                ),
                client_request_id=client_request_id,
                query=query,
                relative_path=relative_path,
                reconciled=True,
            )
        job_id = matches[0].get("jobId")
        if not isinstance(job_id, str):
            return self._unknown_observation(
                tool_call_id,
                tool_name,
                reason="reconciled Runtime Job omitted jobId",
                client_request_id=client_request_id,
                query=query,
                relative_path=relative_path,
                reconciled=True,
            )
        try:
            payload = self.runtime.call_tool(
                "task.observe",
                {
                    "schemaVersion": 1,
                    "jobId": job_id,
                    "waitMs": (
                        30_000 if control is None else max(0, min(30_000, control.remaining_ms))
                    ),
                    "stdoutTailBytes": 65_536,
                    "stderrTailBytes": 65_536,
                },
            )
            validate_json_value(payload)
        except HarnessRuntimeClientError as error:
            return self._unknown_observation(
                tool_call_id,
                tool_name,
                reason=f"reconciled Runtime Job could not be observed: {error}",
                client_request_id=client_request_id,
                query=query,
                relative_path=relative_path,
                reconciled=True,
                runtime_job_ref=job_id,
            )
        return self._terminal_observation(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            payload=payload,
            query=query,
            relative_path=relative_path,
            reconciled=True,
            control=control,
        )

    def _record_observation(
        self,
        intent: HarnessToolStepIntent,
        observation: HarnessToolObservation,
        *,
        previous_receipt=None,
    ) -> HarnessToolObservation:
        status = {
            "observed": HarnessToolStepStatus.OBSERVED,
            "rejected": HarnessToolStepStatus.REJECTED,
            "unknown": HarnessToolStepStatus.UNKNOWN,
            "cancel-requested": HarnessToolStepStatus.CANCEL_REQUESTED,
            "cancelled": HarnessToolStepStatus.CANCELLED,
        }[observation.status]
        receipt_token = canonical_digest(
            {
                "intentDigest": intent.digest,
                "observationDigest": observation.digest,
                "previousReceiptDigest": (
                    None if previous_receipt is None else previous_receipt.digest
                ),
            }
        )[7:31]
        receipt = HarnessToolStepReceipt(
            receipt_id=f"harness-tool-step-receipt:{receipt_token}",
            intent_digest=intent.digest,
            harness_run_id=self.contract.harness_run_id,
            tool_call_id=intent.tool_call_id,
            status=status,
            runtime_job_ref=observation.runtime_job_ref,
            observation_digest=observation.digest,
            reconciled=observation.reconciled,
            created_at_ms=self.run_store.clock_ms(),
            previous_receipt_digest=(None if previous_receipt is None else previous_receipt.digest),
        )
        self.run_store.record_tool_step_receipt(
            receipt,
            observation.to_dict(),
        )
        retained_snapshot = self.run_store.load_current_snapshot()
        self._provider_source = self.run_store.snapshot_provider_source(retained_snapshot)
        self._seen_tool_call_ids.add(intent.tool_call_id)
        return observation

    def _durable_turn_id(self, turn_id: str, step_id: str) -> str:
        if turn_id.startswith("turn:"):
            return turn_id
        token = canonical_digest(
            {
                "harnessRunId": self.contract.harness_run_id,
                "displayTurnId": turn_id,
                "stepId": step_id,
            }
        )[7:39]
        return f"turn:{token}"

    @staticmethod
    def _with_dispatch_fence(
        arguments: dict[str, JsonValue],
        fence,
    ) -> dict[str, JsonValue]:
        execution = arguments.get("execution")
        if not isinstance(execution, dict):
            raise ToolBridgeError(
                "Runtime execution request omitted execution object",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        existing = execution.get("foreignReferences")
        if not isinstance(existing, list):
            raise ToolBridgeError(
                "Runtime execution request omitted foreign references",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        references = [dict(item) for item in existing if isinstance(item, dict)]
        references.append(
            {
                "namespace": fence.authority_namespace,
                "type": fence.authority_type,
                "id": fence.fence_id,
                "generation": str(fence.authority_generation),
                "digest": fence.digest,
            }
        )
        request = dict(arguments)
        request["execution"] = {
            **execution,
            "foreignReferences": references,
        }
        validate_json_value(request)
        return request

    @classmethod
    def _observation_from_payload(
        cls,
        *,
        tool_call_id: str,
        tool_name: str,
        payload: dict[str, JsonValue],
        query: str | None,
        relative_path: str | None,
        reconciled: bool,
    ) -> HarnessToolObservation:
        status_value = payload.get("status")
        observation_status = "cancelled" if status_value == "cancelled" else "observed"
        structured = dict(payload)
        if query is not None:
            structured["query"] = query
        if relative_path is not None:
            structured["relativePath"] = relative_path
        if tool_name == "search_workspace":
            cls._normalize_search(structured)
        job_id = payload.get("jobId")
        return HarnessToolObservation(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status=observation_status,
            structured_content=structured,
            runtime_job_ref=(job_id if isinstance(job_id, str) else None),
            artifact_refs=cls._extract_artifacts(payload),
            reconciled=reconciled,
        )

    @staticmethod
    def _unknown_observation(
        tool_call_id: str,
        tool_name: str,
        *,
        reason: str,
        client_request_id: str | None,
        query: str | None,
        relative_path: str | None,
        reconciled: bool,
        runtime_job_ref: str | None = None,
    ) -> HarnessToolObservation:
        content: dict[str, JsonValue] = {
            "reason": reason[:2_048],
            "clientRequestId": client_request_id,
            "query": query,
            "relativePath": relative_path,
            "safeToCorrect": False,
        }
        return HarnessToolObservation(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status="unknown",
            structured_content=content,
            runtime_job_ref=runtime_job_ref,
            reconciled=reconciled,
        )

    @staticmethod
    def _extract_artifacts(
        payload: dict[str, JsonValue],
    ) -> tuple[HarnessArtifactReference, ...]:
        raw = payload.get("artifacts")
        if not isinstance(raw, list):
            return ()
        retained: dict[str, HarnessArtifactReference] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            artifact_id = item.get("artifactId")
            kind = item.get("kind")
            digest = item.get("digest")
            if not all(isinstance(value, str) for value in (artifact_id, kind, digest)):
                continue
            try:
                reference = HarnessArtifactReference(
                    ref=artifact_id,
                    kind=kind,
                    digest=digest,
                )
            except ValueError:
                continue
            retained[reference.ref] = reference
        return tuple(retained[key] for key in sorted(retained))

    @staticmethod
    def _normalize_search(structured: dict[str, JsonValue]) -> None:
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
                                None if not isinstance(line_text, str) else line_text[:2_048]
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
            "Use match.byteOffset as a read slice offset; lineNumber and column "
            "are one-based display locations."
        )

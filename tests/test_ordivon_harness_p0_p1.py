from __future__ import annotations

import itertools
import subprocess
import tempfile
import threading
import time
import unittest

from anc_canonical import canonical_digest
from ordivon_host import HostStorage

from ordivon_harness import GrantedExecutionCheck, ToolGrant
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnResult,
    CancellationToken,
    DeepSeekSettings,
    DeepSeekTurnAdapter,
    ExecutionControl,
    HostHarnessRunStore,
    NativeRunTimes,
    OrdivonAgentLoop,
    RunBudget,
    RunDeadline,
    RunStopCode,
    RuntimeToolBridge,
    ScriptedTurnAdapter,
    ToolBridgeError,
    ToolObservation,
    record_native_run_result,
)
from ordivon_harness.subprocess_lifecycle import close_owned_process

from test_ordivon_harness_oh3 import _Transport, _response
from test_ordivon_harness_oh5 import (
    _RecoveryRuntime,
    _assign,
    _create_task,
)


class _SleepingConclusionAdapter:
    adapter_id = "ordivon.test-sleeping.v1"
    model_id = "ordivon.test-model.v1"

    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds

    def invoke(self, request):
        time.sleep(self.delay_seconds)
        return AgentTurnResult(
            model_call_id="model-call:sleeping",
            model_id=self.model_id,
            content=None,
            tool_calls=(),
            conclusion=AgentRunConclusion(
                status="candidate_completed",
                summary="late candidate",
            ),
            usage={},
            finish_reason="tool_calls",
            raw_response_digest=canonical_digest({"late": True}),
        )


class _NoopBridge:
    catalog_digest = canonical_digest({"catalog": "p0"})

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        return ()

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        raise AssertionError((call, step_id))


class _HugeObservationBridge:
    catalog_digest = canonical_digest({"catalog": "huge"})

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        return (
            AgentToolDefinition(
                "huge",
                "Return a deliberately large observation.",
                {"type": "object", "additionalProperties": False, "properties": {}},
            ),
        )

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        del step_id
        return ToolObservation(
            call.tool_call_id,
            call.name,
            "observed",
            {"payload": "x" * 50_000},
        )


class _IntentOrderRuntime(_RecoveryRuntime):
    def __init__(self, storage: HostStorage) -> None:
        super().__init__()
        self.storage = storage
        self.intent_seen_before_dispatch = False

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name == "workspace.exec":
            snapshot = self.storage.read_task_event("task:oh5-native")
            data = snapshot.data
            assert isinstance(data, dict)
            self.intent_seen_before_dispatch = isinstance(
                data.get("activeHarnessToolStepIntentDigest"), str
            )
        if name == "task.cancel":
            return {
                "jobId": arguments["jobId"],
                "status": "cancelled",
                "artifacts": [],
            }
        return super().call_tool(name, arguments)


class _ReconcileRuntime(_IntentOrderRuntime):
    def __init__(self, storage: HostStorage) -> None:
        super().__init__(storage)
        self.client_request_id: str | None = None

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, dict(arguments)))
        if name == "task.list":
            jobs: list[dict[str, object]] = []
            if self.client_request_id is not None:
                jobs.append(
                    {
                        "jobId": "job:oh5-reconciled",
                        "clientRequestId": self.client_request_id,
                        "status": "working",
                    }
                )
            return {"jobs": jobs, "nextCursor": None}
        if name == "task.observe":
            return {
                "jobId": arguments["jobId"],
                "status": "working",
                "artifacts": [],
            }
        return super().call_tool(name, arguments)


class HarnessP0ControlTests(unittest.TestCase):
    def test_wall_deadline_rejects_late_candidate(self) -> None:
        result = OrdivonAgentLoop(
            _SleepingConclusionAdapter(0.04),
            _NoopBridge(),
            budget=RunBudget(2, 2, 4_096, 10),
        ).run(
            harness_run_id="harness-run:p0-deadline",
            assignment_id="assignment:p0-deadline:g1",
            context_digest=canonical_digest({"context": "deadline"}),
            initial_messages=({"role": "user", "content": "work"},),
        )
        self.assertEqual(result.stop_code, RunStopCode.BUDGET_EXHAUSTED)
        self.assertFalse(result.candidate_completed)
        self.assertGreaterEqual(result.usage["deadlineOverrunMs"], 1)

    def test_mid_provider_cancellation_rejects_candidate(self) -> None:
        token = CancellationToken()
        timer = threading.Timer(0.01, token.cancel)
        timer.start()
        try:
            result = OrdivonAgentLoop(
                _SleepingConclusionAdapter(0.04),
                _NoopBridge(),
                budget=RunBudget(2, 2, 4_096, 2_000),
            ).run(
                harness_run_id="harness-run:p0-cancel",
                assignment_id="assignment:p0-cancel:g1",
                context_digest=canonical_digest({"context": "cancel"}),
                initial_messages=({"role": "user", "content": "work"},),
                cancellation=token,
            )
        finally:
            timer.cancel()
        self.assertEqual(result.stop_code, RunStopCode.CANCELLED)
        self.assertFalse(result.candidate_completed)

    def test_large_observation_is_bounded_before_model_history(self) -> None:
        adapter = ScriptedTurnAdapter(
            (
                AgentTurnResult(
                    model_call_id="model-call:huge:1",
                    model_id="ordivon.scripted-model.v1",
                    content=None,
                    tool_calls=(AgentToolCall("tool-call:huge", "huge", {}),),
                    conclusion=None,
                    usage={},
                    finish_reason="tool_calls",
                    raw_response_digest=canonical_digest({"turn": 1}),
                ),
                AgentTurnResult(
                    model_call_id="model-call:huge:2",
                    model_id="ordivon.scripted-model.v1",
                    content=None,
                    tool_calls=(),
                    conclusion=AgentRunConclusion(
                        status="candidate_completed",
                        summary="bounded",
                    ),
                    usage={},
                    finish_reason="tool_calls",
                    raw_response_digest=canonical_digest({"turn": 2}),
                ),
            )
        )
        result = OrdivonAgentLoop(
            adapter,
            _HugeObservationBridge(),
            budget=RunBudget(3, 2, 1_024, 2_000),
        ).run(
            harness_run_id="harness-run:p0-observation",
            assignment_id="assignment:p0-observation:g1",
            context_digest=canonical_digest({"context": "observation"}),
            initial_messages=({"role": "user", "content": "work"},),
        )
        self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertTrue(result.observations[0].structured_content["truncated"])
        self.assertLessEqual(result.observation_bytes, 1_024)
        sent = adapter.requests[1].messages[-1]
        self.assertTrue(sent["observation"]["content"]["truncated"])

    def test_effective_provider_model_mismatch_is_rejected(self) -> None:
        response = _response(
            "call-conclusion-model",
            "submit_run_conclusion",
            {
                "status": "candidate_completed",
                "summary": "candidate",
                "artifact_refs": [],
                "evidence_refs": [],
                "unresolved_unknowns": [],
            },
            response_id="chatcmpl-p0-model",
        )
        response["model"] = "unexpected-routed-model"
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="sk-" + "m" * 40),
            transport=_Transport((response,)),
        )
        result = OrdivonAgentLoop(
            adapter,
            _NoopBridge(),
            budget=RunBudget(2, 2, 4_096, 2_000),
        ).run(
            harness_run_id="harness-run:p0-model",
            assignment_id="assignment:p0-model:g1",
            context_digest=canonical_digest({"context": "model"}),
            initial_messages=({"role": "user", "content": "work"},),
        )
        self.assertEqual(result.stop_code, RunStopCode.INVALID_MODEL_OUTPUT)
        self.assertEqual(
            result.usage["effectiveModelIds"], ["unexpected-routed-model"]
        )

    def test_owned_provider_process_is_terminated(self) -> None:
        process = subprocess.Popen(
            ["/usr/bin/python3", "-c", "import time; time.sleep(30)"],
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        close_owned_process(process, graceful_timeout_seconds=0.2)
        self.assertIsNotNone(process.poll())


class HarnessP1DurabilityTests(unittest.TestCase):
    def test_exec_intent_precedes_runtime_dispatch_and_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(100_000).__next__
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _IntentOrderRuntime(storage)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:oh5:run-check",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:oh5:python-version",
                            executable="/usr/bin/python3",
                            args=("-V",),
                            timeout_ms=30_000,
                        ),
                    ),
                )
                host, committed, context_digest, _ = _assign(
                    storage, clock, runtime, grant=grant
                )
                assert committed.native_run_contract is not None
                run_store = HostHarnessRunStore(host, committed)
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=run_store,
                )
                adapter = ScriptedTurnAdapter(
                    (
                        AgentTurnResult(
                            model_call_id="model-call:p1:1",
                            model_id="ordivon.scripted-model.v1",
                            content=None,
                            tool_calls=(
                                AgentToolCall(
                                    "tool-call:p1:check",
                                    "run_check",
                                    {"checkId": "check:oh5:python-version"},
                                ),
                            ),
                            conclusion=None,
                            usage={},
                            finish_reason="tool_calls",
                            raw_response_digest=canonical_digest({"p1": 1}),
                        ),
                        AgentTurnResult(
                            model_call_id="model-call:p1:2",
                            model_id="ordivon.scripted-model.v1",
                            content=None,
                            tool_calls=(),
                            conclusion=AgentRunConclusion(
                                status="candidate_completed",
                                summary="execution observed",
                            ),
                            usage={},
                            finish_reason="tool_calls",
                            raw_response_digest=canonical_digest({"p1": 2}),
                        ),
                    )
                )
                result = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=RunBudget(4, 4, 65_536, 30_000),
                    clock_ms=clock,
                ).run(
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    assignment_id=committed.assignment.assignment_id,
                    context_digest=context_digest,
                    initial_messages=({"role": "user", "content": "run check"},),
                )
                self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
                self.assertTrue(runtime.intent_seen_before_dispatch)
                current = storage.read_task_event(committed.assignment.task_id)
                data = current.data
                assert isinstance(data, dict)
                self.assertIsInstance(data["harnessToolStepIntentObjectDigest"], str)
                self.assertIsInstance(data["harnessToolStepReceiptObjectDigest"], str)
                self.assertNotIn("activeHarnessToolStepIntentDigest", data)
                restarted_store = HostHarnessRunStore(
                    host, host.load_current_assignment(committed.assignment.task_id)
                )
                snapshot = restarted_store.load_current_snapshot()
                self.assertEqual(
                    snapshot.snapshot.pause_reason.value,
                    "effect-dispatch-pending",
                )
                step = restarted_store.load_current_tool_step()
                self.assertIsNotNone(step.receipt)
                self.assertIsNotNone(step.observation)
                assert step.receipt is not None and step.observation is not None
                self.assertEqual(
                    step.receipt.observation_digest,
                    canonical_digest(step.observation),
                )
                recorded = record_native_run_result(
                    host,
                    committed,
                    result,
                    times=NativeRunTimes(100_000, 100_100),
                )
                self.assertEqual(recorded.receipt.harness_run_id, result.harness_run_id)
                validation = validate_history(storage)
                self.assertGreaterEqual(validation.semantic_link_checks, 1)

    def test_prepared_exec_is_reconciled_by_client_request_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(150_000).__next__
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _ReconcileRuntime(storage)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:oh5:reconcile-check",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:oh5:reconcile",
                            executable="/usr/bin/python3",
                            args=("-V",),
                        ),
                    ),
                )
                host, committed, _, _ = _assign(
                    storage, clock, runtime, grant=grant
                )
                assert committed.native_run_contract is not None
                store = HostHarnessRunStore(host, committed)
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=store,
                )
                bridge.bind_run_state(
                    messages=({"role": "user", "content": "run check"},),
                    observations=(),
                    remaining_budget={
                        "modelCalls": 2,
                        "toolCalls": 2,
                        "observationBytes": 65_536,
                        "wallTimeMs": 30_000,
                    },
                    requested_model_id="ordivon.scripted-model.v1",
                    effective_model_id=None,
                )
                call = AgentToolCall(
                    "tool-call:p1:reconcile",
                    "run_check",
                    {"checkId": "check:oh5:reconcile"},
                )
                operation, arguments, client_request_id = bridge._lower(
                    call, step_id="turn-1-tool-1"
                )
                assert client_request_id is not None
                bridge._prepare_tool_step_intent(
                    call,
                    step_id="turn-1-tool-1",
                    turn_id="turn:p1-reconcile:1",
                    operation=operation,
                    arguments=arguments,
                    client_request_id=client_request_id,
                )
                runtime.client_request_id = client_request_id

                current = host.load_current_assignment(committed.assignment.task_id)
                restarted_store = HostHarnessRunStore(host, current)
                restarted_bridge = RuntimeToolBridge(
                    current,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=restarted_store,
                )
                observation = restarted_bridge.reconcile_current_tool_step()
                self.assertEqual(observation.status, "observed")
                self.assertTrue(observation.reconciled)
                self.assertEqual(
                    observation.runtime_job_ref, "job:oh5-reconciled"
                )
                self.assertFalse(
                    any(name == "workspace.exec" for name, _ in runtime.calls)
                )
                retained = restarted_store.load_current_tool_step()
                self.assertIsNotNone(retained.receipt)
                validate_history(storage)

    def test_durable_mode_refuses_unreconciliable_workspace_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(200_000).__next__
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _IntentOrderRuntime(storage)
                host, committed, _, _ = _assign(
                    storage,
                    clock,
                    runtime,
                    grant=ToolGrant(
                        tool_grant_id="tool-grant:oh5:durable-mutation",
                        allowed_tools=("mutate_workspace",),
                        mutate_path_rules=("README.md",),
                    ),
                )
                assert committed.native_run_contract is not None
                store = HostHarnessRunStore(host, committed)
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=store,
                )
                bridge.bind_run_state(
                    messages=({"role": "user", "content": "mutate"},),
                    observations=(),
                    remaining_budget={
                        "modelCalls": 1,
                        "toolCalls": 1,
                        "observationBytes": 1024,
                        "wallTimeMs": 1000,
                    },
                    requested_model_id="ordivon.scripted-model.v1",
                    effective_model_id=None,
                )
                control = ExecutionControl(
                    CancellationToken(), RunDeadline.after(1_000)
                )
                with self.assertRaisesRegex(
                    ToolBridgeError, "reconciliable Runtime dispatch identity"
                ):
                    bridge.execute_with_control(
                        AgentToolCall(
                            "tool-call:p1:mutation",
                            "mutate_workspace",
                            {
                                "mutations": [
                                    {
                                        "relativePath": "README.md",
                                        "mode": "WRITE",
                                        "content": "changed",
                                    }
                                ]
                            },
                        ),
                        step_id="turn-1-tool-1",
                        turn_id="turn:p1-mutation:1",
                        control=control,
                    )
                self.assertFalse(
                    any(name == "workspace.mutate" for name, _ in runtime.calls)
                )


if __name__ == "__main__":
    unittest.main()

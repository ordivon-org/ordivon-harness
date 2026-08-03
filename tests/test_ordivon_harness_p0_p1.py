from __future__ import annotations

import itertools
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from anc_canonical import canonical_digest
from ordivon_host import HostStorage
from test_ordivon_harness_oh3 import _response, _Transport
from test_ordivon_harness_oh5 import (
    _assign,
    _create_task,
    _RecoveryRuntime,
)

from ordivon_harness import GrantedExecutionCheck, ToolGrant
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnAdapterError,
    AgentTurnResult,
    CancellationToken,
    DeepSeekSettings,
    DeepSeekTurnAdapter,
    ExecutionControl,
    HostHarnessRunStore,
    HttpClientDeepSeekTransport,
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
from ordivon_harness.recovery_controller import NativeRunRecoveryController
from ordivon_harness.subprocess_lifecycle import close_owned_process


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


class _BlockingPostHandle:
    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self.poll_count = 0

    def poll(self, timeout_seconds: float) -> bytes | None:
        self.poll_count += 1
        self.cancelled.wait(timeout_seconds)
        if self.cancelled.is_set():
            raise AgentTurnAdapterError("cancelled transport handle")
        return None

    def cancel(self) -> None:
        self.cancelled.set()


class _CancellableTransport:
    def __init__(self) -> None:
        self.handle = _BlockingPostHandle()

    def start_post(self, *args, **kwargs):
        del args, kwargs
        return self.handle

    def post(self, *args, **kwargs):
        raise AssertionError((args, kwargs))


class _StalledResponseHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    request_seen = threading.Event()
    release = threading.Event()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length:
            self.rfile.read(content_length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "65536")
        self.end_headers()
        self.wfile.flush()
        type(self).request_seen.set()
        type(self).release.wait(5)
        try:
            self.wfile.write(b"x" * 65536)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format: str, *args) -> None:
        del format, args


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
        payload = super().call_tool(name, arguments)
        if name == "workspace.exec" and payload.get("status") == "working":
            return {**payload, "status": "succeeded"}
        return payload


class _MutableMonotonic:
    def __init__(self, value_ms: int) -> None:
        self.value_ms = value_ms

    def __call__(self) -> int:
        return self.value_ms

    def advance(self, delta_ms: int) -> None:
        self.value_ms += delta_ms


class _ExpireAfterPrepareBridge(RuntimeToolBridge):
    def __init__(
        self,
        *args,
        monotonic: _MutableMonotonic,
        deadline_advance_ms: int,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._monotonic = monotonic
        self._deadline_advance_ms = deadline_advance_ms

    def _prepare_tool_step_intent(
        self,
        call,
        *,
        step_id,
        turn_id,
        operation,
        arguments,
        client_request_id,
    ):
        prepared = super()._prepare_tool_step_intent(
            call,
            step_id=step_id,
            turn_id=turn_id,
            operation=operation,
            arguments=arguments,
            client_request_id=client_request_id,
        )
        self._monotonic.advance(self._deadline_advance_ms)
        return prepared


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
                "status": "succeeded",
                "artifacts": [],
            }
        return super().call_tool(name, arguments)


class _WorkingReconcileRuntime(_ReconcileRuntime):
    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name == "task.observe":
            self.calls.append((name, dict(arguments)))
            return {
                "jobId": arguments["jobId"],
                "status": "working",
                "artifacts": [],
            }
        return super().call_tool(name, arguments)


class _WorkingThenSucceededRuntime(_IntentOrderRuntime):
    def __init__(self, storage: HostStorage) -> None:
        super().__init__(storage)
        self.observe_calls = 0

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name == "workspace.exec":
            super().call_tool(name, arguments)
            return {
                "jobId": "job:oh5-working-then-succeeded",
                "status": "working",
                "artifacts": [],
            }
        if name == "task.observe":
            self.observe_calls += 1
            return {
                "jobId": arguments["jobId"],
                "status": "succeeded",
                "artifacts": [],
            }
        return super().call_tool(name, arguments)


class _DeferredCancelRuntime(_IntentOrderRuntime):
    def __init__(self, storage: HostStorage, token: CancellationToken) -> None:
        super().__init__(storage)
        self.token = token
        self.cancel_calls = 0
        self.finish_cancellation = False
        self.dispatch_fence_seen = False

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name == "workspace.exec":
            snapshot = self.storage.read_task_event("task:oh5-native")
            data = snapshot.data
            assert isinstance(data, dict)
            self.intent_seen_before_dispatch = isinstance(
                data.get("activeHarnessToolStepIntentDigest"), str
            )
            execution = arguments.get("execution")
            assert isinstance(execution, dict)
            references = execution.get("foreignReferences")
            assert isinstance(references, list)
            self.dispatch_fence_seen = any(
                isinstance(item, dict)
                and item.get("type") == "dispatch_fence"
                and item.get("digest") == data.get("harnessDispatchFenceDigest")
                for item in references
            )
            self.token.cancel()
            return {
                "jobId": "job:oh5-deferred-cancel",
                "status": "working",
                "artifacts": [],
            }
        if name == "task.cancel":
            self.cancel_calls += 1
            return {
                "jobId": arguments["jobId"],
                "status": "cancelled" if self.finish_cancellation else "working",
                "artifacts": [],
            }
        if name == "task.observe":
            return {
                "jobId": arguments["jobId"],
                "status": "cancelled" if self.finish_cancellation else "working",
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
        self.assertEqual(result.usage["effectiveModelIds"], ["unexpected-routed-model"])

    def test_deepseek_cancellable_transport_stops_provider_call_in_flight(self) -> None:
        token = CancellationToken()
        transport = _CancellableTransport()
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-test",
                model="deepseek-v4-flash",
                timeout_seconds=10,
            ),
            transport=transport,
        )
        timer = threading.Timer(0.05, token.cancel)
        timer.start()
        started = time.monotonic()
        try:
            result = OrdivonAgentLoop(
                adapter,
                _NoopBridge(),
                budget=RunBudget(2, 1, 65_536, 5_000),
            ).run(
                harness_run_id="harness-run:p0-provider-cancel",
                assignment_id="assignment:p0-provider-cancel",
                context_digest=canonical_digest({"context": "provider-cancel"}),
                initial_messages=({"role": "user", "content": "work"},),
                cancellation=token,
            )
        finally:
            timer.cancel()
        self.assertEqual(result.stop_code, RunStopCode.CANCEL_UNKNOWN)
        self.assertTrue(transport.handle.cancelled.is_set())
        self.assertGreaterEqual(transport.handle.poll_count, 1)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_http_client_transport_closes_a_stalled_response_socket(self) -> None:
        _StalledResponseHandler.request_seen.clear()
        _StalledResponseHandler.release.clear()
        server = ThreadingHTTPServer(("127.0.0.1", 0), _StalledResponseHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        handle = HttpClientDeepSeekTransport().start_post(
            f"http://127.0.0.1:{server.server_port}/chat/completions",
            headers={"Content-Type": "application/json"},
            body=b"{}",
            timeout_seconds=10,
            max_response_bytes=131_072,
        )
        try:
            self.assertTrue(_StalledResponseHandler.request_seen.wait(1.0))
            started = time.monotonic()
            handle.cancel()
            with self.assertRaises(AgentTurnAdapterError):
                handle.poll(1.0)
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            _StalledResponseHandler.release.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=1.0)

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
    def test_deadline_after_durable_prepare_closes_runtime_dispatch_admission(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(90_000).__next__
            monotonic = _MutableMonotonic(10_000)
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _IntentOrderRuntime(storage)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:p1:dispatch-admission",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:p1:dispatch-admission",
                            executable="/usr/bin/python3",
                            args=("-V",),
                            timeout_ms=30_000,
                        ),
                    ),
                )
                host, committed, context_digest, _ = _assign(
                    storage,
                    clock,
                    runtime,
                    grant=grant,
                )
                assert committed.native_run_contract is not None
                run_store = HostHarnessRunStore(host, committed)
                bridge = _ExpireAfterPrepareBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=run_store,
                    monotonic=monotonic,
                    deadline_advance_ms=1_001,
                )
                adapter = ScriptedTurnAdapter(
                    (
                        AgentTurnResult(
                            model_call_id="model-call:p1:dispatch-admission",
                            model_id="ordivon.scripted-model.v1",
                            content=None,
                            tool_calls=(
                                AgentToolCall(
                                    "tool-call:p1:dispatch-admission",
                                    "run_check",
                                    {"checkId": "check:p1:dispatch-admission"},
                                ),
                            ),
                            conclusion=None,
                            usage={},
                            finish_reason="tool_calls",
                            raw_response_digest=canonical_digest(
                                {"p1": "dispatch-admission"}
                            ),
                        ),
                    )
                )

                result = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=RunBudget(4, 4, 65_536, 1_000),
                    clock_ms=clock,
                    monotonic_ms=monotonic,
                ).run(
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    assignment_id=committed.assignment.assignment_id,
                    context_digest=context_digest,
                    initial_messages=(
                        {"role": "user", "content": "run the granted check"},
                    ),
                )

                self.assertEqual(result.stop_code, RunStopCode.BUDGET_EXHAUSTED)
                self.assertFalse(
                    any(name == "workspace.exec" for name, _ in runtime.calls)
                )
                self.assertEqual(len(result.observations), 1)
                observation = result.observations[0]
                self.assertEqual(observation.status, "rejected")
                error = observation.structured_content["error"]
                assert isinstance(error, dict)
                self.assertEqual(error["type"], "execution_control_stopped")
                self.assertEqual(error["commitState"], "not_started")
                self.assertIs(error["physicalDispatch"], False)
                self.assertEqual(result.usage["toolCorrections"], 0)

                retained = run_store.load_current_tool_step()
                self.assertIsNotNone(retained.fence)
                self.assertIsNotNone(retained.receipt)
                self.assertIsNotNone(retained.observation)
                assert retained.receipt is not None
                self.assertTrue(retained.receipt.terminal)
                self.assertEqual(
                    retained.receipt.observation_digest,
                    observation.digest,
                )
                current = storage.read_task_event(committed.assignment.task_id)
                assert isinstance(current.data, dict)
                self.assertNotIn(
                    "activeHarnessToolStepIntentDigest",
                    current.data,
                )

                recorded = record_native_run_result(
                    host,
                    run_store.committed,
                    result,
                    times=NativeRunTimes(90_000, 91_001),
                )
                self.assertEqual(
                    recorded.receipt.termination_code,
                    RunStopCode.BUDGET_EXHAUSTED.value,
                )
                validate_history(storage)

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
                    restarted_store.committed,
                    result,
                    times=NativeRunTimes(100_000, 100_100),
                )
                self.assertEqual(recorded.receipt.harness_run_id, result.harness_run_id)
                validation = validate_history(storage)
                self.assertGreaterEqual(validation.semantic_link_checks, 1)

    def test_durable_wait_zero_observes_job_to_terminal_before_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(140_000).__next__
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _WorkingThenSucceededRuntime(storage)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:oh5:terminal-wait",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:oh5:terminal-wait",
                            executable="/usr/bin/python3",
                            args=("-V",),
                        ),
                    ),
                )
                host, committed, _, _ = _assign(storage, clock, runtime, grant=grant)
                assert committed.native_run_contract is not None
                store = HostHarnessRunStore(host, committed)
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=store,
                )
                bridge.bind_run_state(
                    messages=({"role": "user", "content": "run"},),
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
                observation = bridge.execute_with_control(
                    AgentToolCall(
                        "tool-call:p1:terminal-wait",
                        "run_check",
                        {
                            "checkId": "check:oh5:terminal-wait",
                            "waitMs": 0,
                        },
                    ),
                    step_id="turn-1-tool-1",
                    turn_id="turn:p1-terminal-wait:1",
                    control=ExecutionControl(
                        CancellationToken(), RunDeadline.after(30_000)
                    ),
                )
                self.assertEqual(observation.status, "observed")
                self.assertEqual(observation.structured_content["status"], "succeeded")
                self.assertEqual(runtime.observe_calls, 1)
                retained = store.load_current_tool_step()
                assert retained.receipt is not None
                self.assertTrue(retained.receipt.terminal)
                current = storage.read_task_event(committed.assignment.task_id)
                assert isinstance(current.data, dict)
                self.assertNotIn("activeHarnessToolStepIntentDigest", current.data)
                validate_history(storage)

    def test_working_unrecorded_dispatch_is_cancelled_during_reconciliation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(145_000).__next__
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _WorkingReconcileRuntime(storage)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:oh5:working-reconcile",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:oh5:working-reconcile",
                            executable="/usr/bin/python3",
                            args=("-V",),
                        ),
                    ),
                )
                host, committed, _, _ = _assign(storage, clock, runtime, grant=grant)
                assert committed.native_run_contract is not None
                store = HostHarnessRunStore(host, committed)
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=store,
                )
                bridge.bind_run_state(
                    messages=({"role": "user", "content": "run"},),
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
                    "tool-call:p1:working-reconcile",
                    "run_check",
                    {"checkId": "check:oh5:working-reconcile"},
                )
                operation, arguments, client_request_id = bridge._lower(
                    call, step_id="turn-1-tool-1"
                )
                assert client_request_id is not None
                bridge._prepare_tool_step_intent(
                    call,
                    step_id="turn-1-tool-1",
                    turn_id="turn:p1-working-reconcile:1",
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
                self.assertEqual(observation.status, "cancelled")
                retained = restarted_store.load_current_tool_step()
                assert retained.receipt is not None
                self.assertTrue(retained.receipt.terminal)
                self.assertTrue(any(name == "task.cancel" for name, _ in runtime.calls))
                validate_history(storage)

    def test_prepared_exec_is_reconciled_by_client_request_without_redispatch(
        self,
    ) -> None:
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
                host, committed, _, _ = _assign(storage, clock, runtime, grant=grant)
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
                self.assertEqual(observation.runtime_job_ref, "job:oh5-reconciled")
                self.assertFalse(
                    any(name == "workspace.exec" for name, _ in runtime.calls)
                )
                retained = restarted_store.load_current_tool_step()
                self.assertIsNotNone(retained.receipt)
                validate_history(storage)

    def test_cancel_requested_receipt_remains_active_until_final_reconciliation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(175_000).__next__
            token = CancellationToken()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _DeferredCancelRuntime(storage, token)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:oh5:deferred-cancel",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:oh5:deferred-cancel",
                            executable="/usr/bin/python3",
                            args=("-V",),
                        ),
                    ),
                )
                host, committed, _, _ = _assign(storage, clock, runtime, grant=grant)
                assert committed.native_run_contract is not None
                store = HostHarnessRunStore(host, committed)
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=store,
                )
                bridge.bind_run_state(
                    messages=({"role": "user", "content": "cancel"},),
                    observations=(),
                    remaining_budget={
                        "modelCalls": 1,
                        "toolCalls": 1,
                        "observationBytes": 65_536,
                        "wallTimeMs": 30_000,
                    },
                    requested_model_id="ordivon.scripted-model.v1",
                    effective_model_id=None,
                )
                observation = bridge.execute_with_control(
                    AgentToolCall(
                        "tool-call:p1:deferred-cancel",
                        "run_check",
                        {
                            "checkId": "check:oh5:deferred-cancel",
                            "waitMs": 30_000,
                        },
                    ),
                    step_id="turn-1-tool-1",
                    turn_id="turn:p1-deferred-cancel:1",
                    control=ExecutionControl(token, RunDeadline.after(30_000)),
                )
                self.assertEqual(observation.status, "cancel-requested")
                self.assertTrue(runtime.intent_seen_before_dispatch)
                self.assertTrue(runtime.dispatch_fence_seen)
                retained = store.load_current_tool_step()
                self.assertIsNotNone(retained.fence)
                self.assertIsNotNone(retained.receipt)
                assert retained.receipt is not None
                self.assertFalse(retained.receipt.terminal)
                current_data = storage.read_task_event(
                    committed.assignment.task_id
                ).data
                assert isinstance(current_data, dict)
                self.assertEqual(
                    current_data["activeHarnessToolStepIntentDigest"],
                    retained.intent.digest,
                )

                runtime.finish_cancellation = True
                current = host.load_current_assignment(committed.assignment.task_id)
                restarted_store = HostHarnessRunStore(host, current)
                restarted_bridge = RuntimeToolBridge(
                    current,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=restarted_store,
                )
                final = restarted_bridge.reconcile_current_tool_step()
                self.assertEqual(final.status, "cancelled")
                final_step = restarted_store.load_current_tool_step()
                assert final_step.receipt is not None
                self.assertTrue(final_step.receipt.terminal)
                self.assertEqual(
                    final_step.receipt.previous_receipt_digest,
                    retained.receipt.digest,
                )
                final_data = storage.read_task_event(committed.assignment.task_id).data
                assert isinstance(final_data, dict)
                self.assertNotIn("activeHarnessToolStepIntentDigest", final_data)
                validate_history(storage)

    def test_recovery_reconciles_active_tool_step_before_workspace_assessment(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(190_000).__next__
            token = CancellationToken()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _DeferredCancelRuntime(storage, token)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:oh5:recovery-cancel",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:oh5:recovery-cancel",
                            executable="/usr/bin/python3",
                            args=("-V",),
                        ),
                    ),
                )
                host, committed, _, _ = _assign(storage, clock, runtime, grant=grant)
                assert committed.native_run_contract is not None
                store = HostHarnessRunStore(host, committed)
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=store,
                )
                bridge.bind_run_state(
                    messages=({"role": "user", "content": "cancel"},),
                    observations=(),
                    remaining_budget={
                        "modelCalls": 1,
                        "toolCalls": 1,
                        "observationBytes": 65_536,
                        "wallTimeMs": 30_000,
                    },
                    requested_model_id="ordivon.scripted-model.v1",
                    effective_model_id=None,
                )
                first = bridge.execute_with_control(
                    AgentToolCall(
                        "tool-call:p1:recovery-cancel",
                        "run_check",
                        {"checkId": "check:oh5:recovery-cancel"},
                    ),
                    step_id="turn-1-tool-1",
                    turn_id="turn:p1-recovery-cancel:1",
                    control=ExecutionControl(token, RunDeadline.after(30_000)),
                )
                self.assertEqual(first.status, "cancel-requested")
                runtime.finish_cancellation = True
                result = NativeRunRecoveryController(host, runtime).recover(
                    committed.assignment.task_id, auto_abandon=False
                )
                evidence = result.recovery.assessment.workspace_evidence
                reconciliation = evidence["toolStepReconciliation"]
                assert isinstance(reconciliation, dict)
                self.assertEqual(reconciliation["resultStatus"], "cancelled")
                self.assertEqual(evidence["toolStepUnresolvedUnknowns"], [])
                current = host.load_current_assignment(committed.assignment.task_id)
                final_step = HostHarnessRunStore(host, current).load_current_tool_step()
                assert final_step.receipt is not None
                self.assertTrue(final_step.receipt.terminal)
                validate_history(storage)

    def test_needs_input_snapshot_resumes_with_cumulative_budget_and_history(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(195_000).__next__
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _IntentOrderRuntime(storage)
                host, committed, context_digest, _ = _assign(
                    storage,
                    clock,
                    runtime,
                    grant=ToolGrant(
                        tool_grant_id="tool-grant:oh5:resume-input",
                        allowed_tools=("read_workspace",),
                        read_path_rules=("README.md",),
                    ),
                )
                assert committed.native_run_contract is not None
                first_store = HostHarnessRunStore(host, committed)
                first_bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=first_store,
                )
                first = OrdivonAgentLoop(
                    ScriptedTurnAdapter(
                        (
                            AgentTurnResult(
                                model_call_id="model-call:p1:resume:1",
                                model_id="ordivon.scripted-model.v1",
                                content="Need a decision",
                                tool_calls=(),
                                conclusion=AgentRunConclusion(
                                    status="needs_input",
                                    summary="Choose the next action",
                                    unresolved_unknowns=("operator decision",),
                                ),
                                usage={"inputTokens": 10},
                                finish_reason="tool_calls",
                                raw_response_digest=canonical_digest({"resume": 1}),
                            ),
                        )
                    ),
                    first_bridge,
                    budget=RunBudget(4, 4, 65_536, 30_000),
                    clock_ms=clock,
                ).run(
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    assignment_id=committed.assignment.assignment_id,
                    context_digest=context_digest,
                    initial_messages=({"role": "user", "content": "start"},),
                )
                self.assertEqual(first.stop_code, RunStopCode.NEEDS_INPUT)

                current = host.load_current_assignment(committed.assignment.task_id)
                second_store = HostHarnessRunStore(host, current)
                retained = second_store.load_current_snapshot()
                self.assertEqual(retained.snapshot.pause_reason.value, "needs-input")
                second_bridge = RuntimeToolBridge(
                    current,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=second_store,
                )
                resumed = OrdivonAgentLoop(
                    ScriptedTurnAdapter(
                        (
                            AgentTurnResult(
                                model_call_id="model-call:p1:resume:2",
                                model_id="ordivon.scripted-model.v1",
                                content=None,
                                tool_calls=(),
                                conclusion=AgentRunConclusion(
                                    status="candidate_completed",
                                    summary="continued after operator input",
                                ),
                                usage={"inputTokens": 12},
                                finish_reason="tool_calls",
                                raw_response_digest=canonical_digest({"resume": 2}),
                            ),
                        )
                    ),
                    second_bridge,
                    budget=RunBudget(4, 4, 65_536, 30_000),
                    clock_ms=clock,
                ).resume(
                    retained=retained,
                    assignment_id=committed.assignment.assignment_id,
                    context_digest=context_digest,
                    additional_messages=(
                        {"role": "user", "content": "continue with option A"},
                    ),
                )
                self.assertEqual(resumed.stop_code, RunStopCode.CANDIDATE_COMPLETED)
                self.assertEqual(resumed.model_calls, 2)
                self.assertEqual(len(resumed.usage["providerUsage"]), 2)
                self.assertTrue(
                    any(
                        message.get("content") == "continue with option A"
                        for message in resumed.messages
                    )
                )
                validate_history(storage)

    def test_effect_dispatch_snapshot_reconciles_then_resumes_model_loop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(198_000).__next__
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _ReconcileRuntime(storage)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:oh5:resume-dispatch",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:oh5:resume-dispatch",
                            executable="/usr/bin/python3",
                            args=("-V",),
                        ),
                    ),
                )
                host, committed, context_digest, _ = _assign(
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
                call = AgentToolCall(
                    "tool-call:p1:resume-dispatch",
                    "run_check",
                    {"checkId": "check:oh5:resume-dispatch"},
                )
                bridge.bind_run_state(
                    messages=(
                        {"role": "user", "content": "run"},
                        {
                            "role": "assistant",
                            "content": None,
                            "toolCalls": [call.to_dict()],
                        },
                    ),
                    observations=(),
                    remaining_budget={
                        "modelCalls": 3,
                        "toolCalls": 4,
                        "observationBytes": 65_536,
                        "wallTimeMs": 29_900,
                    },
                    requested_model_id="ordivon.scripted-model.v1",
                    effective_model_id="ordivon.scripted-model.v1",
                    seen_model_call_ids=("model-call:p1:resume-dispatch:1",),
                    seen_tool_call_ids=(call.tool_call_id,),
                    provider_usage=({"inputTokens": 9},),
                    effective_model_ids=("ordivon.scripted-model.v1",),
                )
                operation, arguments, client_request_id = bridge._lower(
                    call, step_id="turn-1-tool-1"
                )
                assert client_request_id is not None
                bridge._prepare_tool_step_intent(
                    call,
                    step_id="turn-1-tool-1",
                    turn_id="turn:p1-resume-dispatch:1",
                    operation=operation,
                    arguments=arguments,
                    client_request_id=client_request_id,
                )
                runtime.client_request_id = client_request_id

                current = host.load_current_assignment(committed.assignment.task_id)
                restarted_store = HostHarnessRunStore(host, current)
                retained = restarted_store.load_current_snapshot()
                restarted_bridge = RuntimeToolBridge(
                    current,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=restarted_store,
                )
                resumed = OrdivonAgentLoop(
                    ScriptedTurnAdapter(
                        (
                            AgentTurnResult(
                                model_call_id="model-call:p1:resume-dispatch:2",
                                model_id="ordivon.scripted-model.v1",
                                content=None,
                                tool_calls=(),
                                conclusion=AgentRunConclusion(
                                    status="candidate_completed",
                                    summary="dispatch reconciled and continued",
                                ),
                                usage={"inputTokens": 11},
                                finish_reason="tool_calls",
                                raw_response_digest=canonical_digest(
                                    {"resume-dispatch": 2}
                                ),
                            ),
                        )
                    ),
                    restarted_bridge,
                    budget=RunBudget(4, 4, 65_536, 30_000),
                    clock_ms=clock,
                ).resume(
                    retained=retained,
                    assignment_id=committed.assignment.assignment_id,
                    context_digest=context_digest,
                )
                self.assertEqual(resumed.stop_code, RunStopCode.CANDIDATE_COMPLETED)
                self.assertEqual(resumed.model_calls, 2)
                self.assertEqual(resumed.tool_calls, 1)
                self.assertTrue(resumed.observations[-1].reconciled)
                self.assertFalse(
                    any(name == "workspace.exec" for name, _ in runtime.calls)
                )
                validate_history(storage)

    def test_consecutive_effect_dispatch_uses_bounded_state_delta_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = itertools.count(199_000).__next__
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _IntentOrderRuntime(storage)
                grant = ToolGrant(
                    tool_grant_id="tool-grant:oh5:delta-state",
                    allowed_tools=("run_check",),
                    execution_checks=(
                        GrantedExecutionCheck(
                            check_id="check:oh5:delta-state",
                            executable="/usr/bin/python3",
                            args=("-V",),
                        ),
                    ),
                )
                host, committed, _, _ = _assign(storage, clock, runtime, grant=grant)
                assert committed.native_run_contract is not None
                store = HostHarnessRunStore(host, committed)
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=committed.native_run_contract.harness_run_id,
                    runtime=runtime,
                    run_store=store,
                )
                large_message = {
                    "role": "user",
                    "content": "x" * 50_000,
                }
                bridge.bind_run_state(
                    messages=(large_message,),
                    observations=(),
                    remaining_budget={
                        "modelCalls": 3,
                        "toolCalls": 3,
                        "observationBytes": 65_536,
                        "wallTimeMs": 29_900,
                    },
                    requested_model_id="ordivon.scripted-model.v1",
                    effective_model_id="ordivon.scripted-model.v1",
                    seen_model_call_ids=("model-call:delta:1",),
                    seen_tool_call_ids=("tool-call:delta:1",),
                    provider_usage=({"inputTokens": 100},),
                    effective_model_ids=("ordivon.scripted-model.v1",),
                )
                first_call = AgentToolCall(
                    "tool-call:delta:1",
                    "run_check",
                    {"checkId": "check:oh5:delta-state"},
                )
                operation, arguments, request_id = bridge._lower(
                    first_call, step_id="turn-1-tool-1"
                )
                assert request_id is not None
                first_intent, _ = bridge._prepare_tool_step_intent(
                    first_call,
                    step_id="turn-1-tool-1",
                    turn_id="turn:delta:1",
                    operation=operation,
                    arguments=arguments,
                    client_request_id=request_id,
                )
                first_snapshot = store.load_current_snapshot()
                self.assertEqual(first_snapshot.state_object.kind, "harness-run-state")
                first_observation = ToolObservation(
                    first_call.tool_call_id,
                    first_call.name,
                    "observed",
                    {
                        "jobId": "job:delta:1",
                        "status": "succeeded",
                        "artifacts": [],
                    },
                    runtime_job_ref="job:delta:1",
                )
                bridge._record_tool_step_receipt(first_intent, first_observation)

                second_messages = (
                    large_message,
                    {
                        "role": "assistant",
                        "content": None,
                        "toolCalls": [first_call.to_dict()],
                    },
                    first_observation.to_model_message(),
                )
                bridge.bind_run_state(
                    messages=second_messages,
                    observations=(first_observation,),
                    remaining_budget={
                        "modelCalls": 2,
                        "toolCalls": 2,
                        "observationBytes": 64_000,
                        "wallTimeMs": 29_500,
                    },
                    requested_model_id="ordivon.scripted-model.v1",
                    effective_model_id="ordivon.scripted-model.v1",
                    seen_model_call_ids=(
                        "model-call:delta:1",
                        "model-call:delta:2",
                    ),
                    seen_tool_call_ids=(
                        "tool-call:delta:1",
                        "tool-call:delta:2",
                    ),
                    provider_usage=(
                        {"inputTokens": 100},
                        {"inputTokens": 12},
                    ),
                    effective_model_ids=("ordivon.scripted-model.v1",),
                )
                second_call = AgentToolCall(
                    "tool-call:delta:2",
                    "run_check",
                    {"checkId": "check:oh5:delta-state"},
                )
                operation, arguments, request_id = bridge._lower(
                    second_call, step_id="turn-2-tool-2"
                )
                assert request_id is not None
                bridge._prepare_tool_step_intent(
                    second_call,
                    step_id="turn-2-tool-2",
                    turn_id="turn:delta:2",
                    operation=operation,
                    arguments=arguments,
                    client_request_id=request_id,
                )
                second_snapshot = store.load_current_snapshot()
                self.assertEqual(
                    second_snapshot.state_object.kind,
                    "harness-run-state-delta",
                )
                self.assertLess(
                    second_snapshot.state_object.byte_length,
                    first_snapshot.state_object.byte_length // 4,
                )
                self.assertEqual(second_snapshot.state.messages, second_messages)
                self.assertEqual(
                    second_snapshot.state.observations,
                    (first_observation.to_dict(),),
                )
                self.assertEqual(
                    second_snapshot.state.seen_model_call_ids,
                    ("model-call:delta:1", "model-call:delta:2"),
                )
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

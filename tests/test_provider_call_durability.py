from __future__ import annotations

import tempfile
import threading
import time
import unittest

from anc_canonical import canonical_digest
from ordivon_host import HostStorage
from test_ordivon_harness_oh5 import (
    TASK_ID,
    _RecoveryRuntime,
    _assign,
    _create_task,
)
from test_runner_r0_r1 import _plan, _turn

from ordivon_harness import (
    GrantedExecutionCheck,
    HarnessHost,
    HarnessProviderCallClaimHeld,
    HarnessProviderCallRecoveryRequired,
    HarnessProviderCallRequestMismatch,
    HarnessRunner,
    HarnessSuperseded,
    ToolGrant,
)
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnAdapterError,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
    AgentTurnRequest,
    AgentTurnResult,
    HarnessRunState,
    HostHarnessRunStore,
    OrdivonAgentLoop,
    RunBudget,
    RunStopCode,
    RuntimeToolBridge,
    ScriptedTurnAdapter,
    static_provider_request_digest,
)
from ordivon_harness.ordivon.loop import _recover_tool_batch
from ordivon_harness.protocol import (
    HarnessRecoveryConsequence,
    HarnessToolStepIntent,
)


def _needs_input() -> AgentTurnResult:
    return _turn(
        "provider-claim-needs-input",
        conclusion=AgentRunConclusion(
            status="needs_input",
            summary="Pause before Provider claim contention.",
        ),
    )


def _completed() -> AgentTurnResult:
    return _turn(
        "provider-claim-completed",
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="The Provider claim fixture completed.",
        ),
    )


def _tool_step_intent(call: AgentToolCall) -> HarnessToolStepIntent:
    return HarnessToolStepIntent(
        intent_id="harness-tool-step-intent:provider-batch",
        harness_run_id="harness-run:provider-batch",
        assignment_id="assignment:provider-batch",
        assignment_generation=1,
        assignment_digest=canonical_digest({"assignment": "provider-batch"}),
        turn_id="turn:provider-batch:1",
        tool_call_id=call.tool_call_id,
        tool_name=call.name,
        tool_call_digest=call.digest,
        runtime_operation="workspace.exec",
        runtime_arguments_digest=canonical_digest({"runtime": call.arguments}),
        client_request_id=f"runtime-client:{call.tool_call_id}",
        recovery_consequence=(
            HarnessRecoveryConsequence.PROCESS_OR_EXTERNAL_EFFECT_POSSIBLE
        ),
        created_at_ms=1,
    )


class _RaceAdapter:
    adapter_id = "ordivon.provider-claim-race.v1"
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(
        self,
        invoked: threading.Event,
        release: threading.Event,
        counter: list[int],
        lock: threading.Lock,
    ) -> None:
        self.invoked = invoked
        self.release = release
        self.counter = counter
        self.lock = lock

    def invoke(self, request):
        del request
        with self.lock:
            self.counter[0] += 1
        self.invoked.set()
        if not self.release.wait(5):
            raise RuntimeError("Provider race fixture timed out")
        return _completed()


class _ReplayAdapter:
    adapter_id = "ordivon.provider-result-replay.v1"
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(self, calls: list[int], *, fail_if_invoked: bool = False) -> None:
        self.calls = calls
        self.fail_if_invoked = fail_if_invoked

    def invoke(self, request):
        del request
        if self.fail_if_invoked:
            raise AssertionError("durable Provider result was not replayed")
        self.calls[0] += 1
        return _completed()


class _FailureAdapter:
    adapter_id = "ordivon.provider-failure-replay.v1"
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(
        self,
        calls: list[int],
        *,
        failure_code: AgentTurnFailureCode = AgentTurnFailureCode.TRANSPORT_FAILED,
        dispatch_safety: AgentTurnDispatchSafety = (
            AgentTurnDispatchSafety.PRE_DISPATCH_SAFE
        ),
        detail: str = "fixture Provider failure",
        result: AgentTurnResult | None = None,
        fail_if_invoked: bool = False,
    ) -> None:
        self.calls = calls
        self.failure_code = failure_code
        self.dispatch_safety = dispatch_safety
        self.detail = detail
        self.result = result
        self.fail_if_invoked = fail_if_invoked

    def invoke(self, request):
        del request
        if self.fail_if_invoked:
            raise AssertionError("durable Provider failure was not replayed")
        self.calls[0] += 1
        if self.result is not None:
            return self.result
        raise AgentTurnAdapterError(
            self.detail,
            failure_code=self.failure_code,
            dispatch_safety=self.dispatch_safety,
        )


class _MultiTurnReplayAdapter:
    adapter_id = "ordivon.provider-multi-turn-replay.v1"
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(
        self,
        calls: list[int],
        results: tuple[AgentTurnResult, ...],
        *,
        fail_if_invoked: bool = False,
    ) -> None:
        self.calls = calls
        self.results = list(results)
        self.fail_if_invoked = fail_if_invoked

    def invoke(self, request):
        del request
        if self.fail_if_invoked:
            raise AssertionError("durable later-turn Provider result was not replayed")
        self.calls[0] += 1
        return self.results.pop(0)


class _CrashAfterProviderResult(RuntimeToolBridge):
    def complete_provider_call(self, request, result) -> None:
        super().complete_provider_call(request, result)
        raise RuntimeError("injected crash after durable Provider result")


class _CrashBeforeDurableProviderResult(RuntimeToolBridge):
    def complete_provider_call(self, request, result) -> None:
        del request, result
        raise RuntimeError("injected crash before durable Provider result")


class _CrashAfterProviderResultNumber(RuntimeToolBridge):
    def __init__(self, *args, crash_after: int, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._crash_after = crash_after
        self._completed_results = 0

    def complete_provider_call(self, request, result) -> None:
        super().complete_provider_call(request, result)
        self._completed_results += 1
        if self._completed_results == self._crash_after:
            raise RuntimeError("injected crash after later durable Provider result")


class _CrashAfterProviderFailure(RuntimeToolBridge):
    def fail_provider_call(self, request, error, *, unknown: bool) -> None:
        super().fail_provider_call(request, error, unknown=unknown)
        raise RuntimeError("injected crash after durable Provider failure")


class _CrashAfterProviderRetryClaim(RuntimeToolBridge):
    def retry_provider_call(self, request: AgentTurnRequest) -> None:
        if self.run_store is None:
            raise AssertionError("retry claim crash fixture requires a Run Store")
        retained = self._require_active_provider_call(request)
        retained = self.run_store.retry_failed_provider_call(
            retained,
            holder_id=self._provider_holder_id,
            ttl_ms=self._provider_claim_ttl_ms(request),
        )
        self._active_provider_call = retained
        self.committed = self.run_store.committed
        raise RuntimeError("injected crash after durable Provider retry claim")


class _InjectedToolBatchCrash(BaseException):
    pass


class _CrashAfterFirstToolReceipt(RuntimeToolBridge):
    def __init__(
        self,
        *args,
        crash_tool_call_id: str,
        order: list[str],
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._crash_tool_call_id = crash_tool_call_id
        self._order = order

    def _record_tool_step_receipt(self, intent, observation) -> None:
        super()._record_tool_step_receipt(intent, observation)
        if (
            intent is not None
            and intent.tool_call_id == self._crash_tool_call_id
        ):
            self._order.append(f"crash:{intent.tool_call_id}")
            raise _InjectedToolBatchCrash


class _OrderedEffectRuntime(_RecoveryRuntime):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self.order = order

    def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        if name == "workspace.exec":
            self.calls.append((name, dict(arguments)))
            execution = arguments.get("execution")
            if not isinstance(execution, dict):
                raise AssertionError("workspace.exec omitted execution")
            args = execution.get("args")
            if not isinstance(args, list) or len(args) != 1:
                raise AssertionError("workspace.exec fixture args differ")
            label = args[0]
            if not isinstance(label, str):
                raise AssertionError("workspace.exec fixture label is invalid")
            self.order.append(f"runtime:{label}")
            return {
                "jobId": f"job:provider-tool-batch:{label}",
                "status": "succeeded",
                "artifacts": [],
            }
        return super().call_tool(name, arguments)


class _OrderedTurnAdapter:
    adapter_id = "ordivon.provider-tool-batch.v1"
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(
        self,
        order: list[str],
        phase: str,
        results: tuple[AgentTurnResult, ...],
        *,
        required_runtime_label: str | None = None,
    ) -> None:
        self.order = order
        self.phase = phase
        self.results = list(results)
        self.required_runtime_label = required_runtime_label
        self.requests: list[AgentTurnRequest] = []

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        self.order.append(f"provider:{self.phase}")
        if (
            self.required_runtime_label is not None
            and self.order.count(f"runtime:{self.required_runtime_label}") != 1
        ):
            raise AssertionError(
                "Provider was invoked before the pending Tool batch completed"
            )
        return self.results.pop(0)


class _MutableClock:
    def __init__(self, value: int = 100_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class _DeadlineClosingProviderStore(HostHarnessRunStore):
    def __init__(
        self,
        *args,
        clock: _MutableClock,
        close_after: str,
        advance_ms: int,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._clock = clock
        self._close_after = close_after
        self._advance_ms = advance_ms
        self._closed = False

    def _close_deadline(self, phase: str) -> None:
        if not self._closed and self._close_after == phase:
            self._clock.value += self._advance_ms
            self._closed = True

    def claim_provider_call(self, **kwargs):
        retained = super().claim_provider_call(**kwargs)
        self._close_deadline("claimed")
        return retained

    def mark_provider_call_dispatching(self, retained):
        dispatching = super().mark_provider_call_dispatching(retained)
        self._close_deadline("dispatching")
        return dispatching


class ProviderCallDurabilityTests(unittest.TestCase):
    def _prepare_pause(
        self,
        directory: str,
        *,
        budget: RunBudget | None = None,
    ) -> None:
        with HostStorage(directory) as storage:
            clock = _MutableClock()
            _create_task(storage, clock)
            paused = HarnessRunner(
                HarnessHost(storage, clock_ms=clock),
                runtime=_RecoveryRuntime(),
                adapter=ScriptedTurnAdapter((_needs_input(),)),
            ).run(_plan(budget=budget))
            self.assertTrue(paused.paused)

    def test_two_resumers_dispatch_the_provider_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._prepare_pause(directory)
            invoked = threading.Event()
            release = threading.Event()
            start = threading.Barrier(2)
            calls = [0]
            calls_lock = threading.Lock()
            outcomes: list[tuple[str, object]] = []
            outcomes_lock = threading.Lock()

            def contender(label: str) -> None:
                try:
                    with HostStorage(directory) as storage:
                        runner = HarnessRunner(
                            HarnessHost(storage, clock_ms=_MutableClock()),
                            runtime=_RecoveryRuntime(),
                            adapter=_RaceAdapter(
                                invoked,
                                release,
                                calls,
                                calls_lock,
                            ),
                        )
                        start.wait(5)
                        result = runner.resume(
                            TASK_ID,
                            additional_messages=(
                                {"role": "user", "content": "Resume exactly once."},
                            ),
                        )
                        outcome: tuple[str, object] = (label, result)
                except Exception as error:  # noqa: BLE001 - assert exact race outcome.
                    outcome = (label, error)
                with outcomes_lock:
                    outcomes.append(outcome)

            threads = [
                threading.Thread(target=contender, args=(label,))
                for label in ("a", "b")
            ]
            for thread in threads:
                thread.start()
            self.assertTrue(invoked.wait(5))
            deadline = time.monotonic() + 5
            while len(outcomes) < 1 and time.monotonic() < deadline:
                time.sleep(0.01)
            release.set()
            for thread in threads:
                thread.join(5)
                self.assertFalse(thread.is_alive())

            self.assertEqual(calls, [1])
            self.assertEqual(len(outcomes), 2)
            errors = [value for _, value in outcomes if isinstance(value, Exception)]
            results = [value for _, value in outcomes if not isinstance(value, Exception)]
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(
                errors[0],
                (
                    HarnessProviderCallClaimHeld,
                    HarnessProviderCallRecoveryRequired,
                    HarnessSuperseded,
                ),
            )
            self.assertEqual(len(results), 1)
            with HostStorage(directory) as storage:
                rows = storage.journal.connection.execute(
                    "SELECT event_kind FROM events WHERE stream_id = ? "
                    "ORDER BY stream_revision",
                    (TASK_ID,),
                ).fetchall()
                kinds = [str(row["event_kind"]) for row in rows]
                # One initial call created the pause; the race adds exactly one more.
                self.assertEqual(kinds.count("harness.provider-call-claimed"), 2)
                self.assertEqual(kinds.count("harness.provider-call-dispatching"), 2)
                self.assertEqual(kinds.count("harness.provider-call-completed"), 2)
                self.assertEqual(kinds.count("harness.run-recorded"), 1)
                self.assertGreater(validate_history(storage).events, 0)

    def test_completed_provider_result_replays_without_another_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._prepare_pause(directory)
            calls = [0]
            additional = ({"role": "user", "content": "Replay this exact turn."},)
            with HostStorage(directory) as storage:
                clock = _MutableClock()
                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                bridge = _CrashAfterProviderResult(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=_RecoveryRuntime(),
                    run_store=run_store,
                    provider_source=run_store.snapshot_provider_source(retained),
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected crash after durable Provider result",
                ):
                    OrdivonAgentLoop(
                        _ReplayAdapter(calls),
                        bridge,
                        budget=RunBudget(4, 4, 262_144, 120_000),
                        clock_ms=clock,
                    ).resume(
                        retained=retained,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=committed.assignment.context_object_digest,
                        additional_messages=additional,
                    )
                self.assertEqual(
                    HarnessRunner(host).status(TASK_ID).provider_call_status,
                    "completed",
                )

            with HostStorage(directory) as storage:
                replayed = HarnessRunner(
                    HarnessHost(storage, clock_ms=_MutableClock()),
                    runtime=_RecoveryRuntime(),
                    adapter=_ReplayAdapter(calls, fail_if_invoked=True),
                ).resume(
                    TASK_ID,
                    additional_messages=additional,
                )
                self.assertIsNotNone(replayed.recorded)
                self.assertEqual(replayed.loop_result.usage["providerAttempts"], 2)
                self.assertEqual(
                    replayed.loop_result.usage["providerResultsReplayed"],
                    1,
                )
                self.assertEqual(calls, [1])

    def test_returned_provider_result_without_durable_completion_never_redispatches(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._prepare_pause(directory)
            calls = [0]
            additional = (
                {
                    "role": "user",
                    "content": "Do not repeat a possibly completed Provider call.",
                },
            )
            with HostStorage(directory) as storage:
                clock = _MutableClock()
                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                bridge = _CrashBeforeDurableProviderResult(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=_RecoveryRuntime(),
                    run_store=run_store,
                    provider_source=run_store.snapshot_provider_source(retained),
                )

                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected crash before durable Provider result",
                ):
                    OrdivonAgentLoop(
                        _ReplayAdapter(calls),
                        bridge,
                        budget=RunBudget(4, 4, 262_144, 120_000),
                        clock_ms=clock,
                    ).resume(
                        retained=retained,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=committed.assignment.context_object_digest,
                        additional_messages=additional,
                    )

                active = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_provider_call()
                self.assertEqual(calls, [1])
                self.assertEqual(active.record.status.value, "dispatching")
                self.assertIsNone(active.result)
                self.assertIsNone(active.failure)
                validate_history(storage)

            with HostStorage(directory) as storage:
                runtime = _RecoveryRuntime()
                host = HarnessHost(storage, clock_ms=_MutableClock())
                runner = HarnessRunner(
                    host,
                    runtime=runtime,
                    adapter=_ReplayAdapter(calls, fail_if_invoked=True),
                )
                with self.assertRaises(HarnessProviderCallRecoveryRequired):
                    runner.resume(
                        TASK_ID,
                        additional_messages=additional,
                    )
                self.assertEqual(calls, [1])

                recovery = runner.recover(TASK_ID)

                self.assertEqual(calls, [1])
                self.assertFalse(recovery.safe_to_replace)
                provider = recovery.recovery.assessment.workspace_evidence[
                    "providerCallReconciliation"
                ]
                assert isinstance(provider, dict)
                self.assertEqual(provider["status"], "dispatching")
                active = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_provider_call()
                self.assertEqual(active.record.status.value, "dispatching")
                validate_history(storage)

    def _assert_deadline_closes_provider_admission(
        self,
        *,
        close_after: str,
        expected_dispatch_events: int,
    ) -> None:
        clock = _MutableClock()
        calls = [0]
        budget = RunBudget(4, 4, 262_144, 50)
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _RecoveryRuntime()
                host, committed, context_digest, _ = _assign(
                    storage,
                    clock,
                    runtime,
                )
                run_store = _DeadlineClosingProviderStore(
                    host,
                    committed,
                    clock=clock,
                    close_after=close_after,
                    advance_ms=51,
                )
                result = OrdivonAgentLoop(
                    _ReplayAdapter(calls),
                    RuntimeToolBridge(
                        committed,
                        harness_run_id=run_store.harness_run_id,
                        runtime=runtime,
                        run_store=run_store,
                    ),
                    budget=budget,
                    clock_ms=clock,
                    monotonic_ms=clock,
                ).run(
                    harness_run_id=run_store.harness_run_id,
                    assignment_id=committed.assignment.assignment_id,
                    context_digest=context_digest,
                    initial_messages=(
                        {
                            "role": "user",
                            "content": "Stop before physical Provider dispatch.",
                        },
                    ),
                )

                self.assertEqual(result.stop_code, RunStopCode.BUDGET_EXHAUSTED)
                self.assertEqual(calls, [0])
                failed = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_provider_call()
                self.assertEqual(failed.record.status.value, "failed")
                self.assertIsNone(failed.result)
                self.assertIsNotNone(failed.failure)
                assert failed.failure is not None
                self.assertEqual(
                    failed.failure.failure_code,
                    AgentTurnFailureCode.TIMEOUT.value,
                )
                self.assertEqual(
                    failed.failure.dispatch_safety,
                    AgentTurnDispatchSafety.PRE_DISPATCH_SAFE.value,
                )
                rows = storage.journal.connection.execute(
                    "SELECT event_kind FROM events WHERE stream_id = ? "
                    "ORDER BY stream_revision",
                    (TASK_ID,),
                ).fetchall()
                kinds = [str(row["event_kind"]) for row in rows]
                self.assertEqual(
                    kinds.count("harness.provider-call-claimed"),
                    1,
                )
                self.assertEqual(
                    kinds.count("harness.provider-call-dispatching"),
                    expected_dispatch_events,
                )
                self.assertEqual(
                    kinds.count("harness.provider-call-failed"),
                    1,
                )
                validate_history(storage)

    def test_claimed_provider_is_failed_when_first_admission_gate_closes(
        self,
    ) -> None:
        self._assert_deadline_closes_provider_admission(
            close_after="claimed",
            expected_dispatch_events=0,
        )

    def test_dispatching_provider_is_failed_when_second_admission_gate_closes(
        self,
    ) -> None:
        self._assert_deadline_closes_provider_admission(
            close_after="dispatching",
            expected_dispatch_events=1,
        )

    def test_later_completed_provider_result_replays_from_its_bound_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._prepare_pause(directory)
            calls = [0]
            additional = (
                {"role": "user", "content": "Correct the malformed Tool Call."},
            )
            malformed = _turn(
                "provider-local-correction",
                calls=(
                    AgentToolCall(
                        "tool-call:provider-local-correction",
                        "read_workspace",
                        {},
                        argument_error="invalid_json",
                        raw_arguments_digest=canonical_digest(
                            {"rawArguments": '{"relativePath":'}
                        ),
                        raw_arguments_preview='{"relativePath":',
                    ),
                ),
            )
            with HostStorage(directory) as storage:
                clock = _MutableClock()
                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                bridge = _CrashAfterProviderResultNumber(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=_RecoveryRuntime(),
                    run_store=run_store,
                    provider_source=run_store.snapshot_provider_source(retained),
                    crash_after=2,
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected crash after later durable Provider result",
                ):
                    OrdivonAgentLoop(
                        _MultiTurnReplayAdapter(
                            calls,
                            (malformed, _completed()),
                        ),
                        bridge,
                        budget=RunBudget(4, 4, 262_144, 120_000),
                        clock_ms=clock,
                    ).resume(
                        retained=retained,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=committed.assignment.context_object_digest,
                        additional_messages=additional,
                    )
                provider_call = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_provider_call()
                self.assertEqual(provider_call.record.turn_sequence, 3)
                self.assertEqual(provider_call.record.status.value, "completed")

            with HostStorage(directory) as storage:
                replayed = HarnessRunner(
                    HarnessHost(storage, clock_ms=_MutableClock()),
                    runtime=_RecoveryRuntime(),
                    adapter=_MultiTurnReplayAdapter(
                        calls,
                        (),
                        fail_if_invoked=True,
                    ),
                ).resume(
                    TASK_ID,
                    additional_messages=additional,
                )
                self.assertIsNotNone(replayed.recorded)
                self.assertEqual(replayed.loop_result.usage["providerAttempts"], 3)
                self.assertEqual(
                    replayed.loop_result.usage["providerResultsReplayed"],
                    1,
                )
                self.assertEqual(
                    replayed.loop_result.observations[-1].status,
                    "rejected",
                )
                replay_event = next(
                    event
                    for event in replayed.loop_result.trace.events
                    if event.kind == "model_call_started"
                )
                self.assertTrue(replay_event.payload["replayedProviderResult"])
                self.assertEqual(calls, [2])

    def test_resume_completes_pending_multi_tool_batch_before_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            order: list[str] = []
            clock = _MutableClock()
            runtime = _OrderedEffectRuntime(order)
            call_a = AgentToolCall(
                "tool-call:provider-batch:a",
                "run_check",
                {"checkId": "check:provider-batch:a"},
            )
            call_b = AgentToolCall(
                "tool-call:provider-batch:b",
                "run_check",
                {"checkId": "check:provider-batch:b"},
            )
            grant = ToolGrant(
                tool_grant_id="tool-grant:provider-batch",
                allowed_tools=("run_check",),
                execution_checks=(
                    GrantedExecutionCheck(
                        check_id="check:provider-batch:a",
                        executable="/usr/bin/printf",
                        args=("A",),
                    ),
                    GrantedExecutionCheck(
                        check_id="check:provider-batch:b",
                        executable="/usr/bin/printf",
                        args=("B",),
                    ),
                ),
            )
            first_turn = _turn(
                "provider-tool-batch",
                calls=(call_a, call_b),
            )

            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, context_digest, _ = _assign(
                    storage,
                    clock,
                    runtime,
                    grant=grant,
                )
                run_store = HostHarnessRunStore(host, committed)
                bridge = _CrashAfterFirstToolReceipt(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=runtime,
                    run_store=run_store,
                    crash_tool_call_id=call_a.tool_call_id,
                    order=order,
                )
                with self.assertRaises(_InjectedToolBatchCrash):
                    OrdivonAgentLoop(
                        _OrderedTurnAdapter(
                            order,
                            "first",
                            (first_turn,),
                        ),
                        bridge,
                        budget=RunBudget(4, 4, 262_144, 120_000),
                        clock_ms=clock,
                    ).run(
                        harness_run_id=run_store.harness_run_id,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=context_digest,
                        initial_messages=(
                            {"role": "user", "content": "Run A, then B."},
                        ),
                    )

                retained_step = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_tool_step()
                self.assertEqual(
                    retained_step.intent.tool_call_id,
                    call_a.tool_call_id,
                )
                self.assertIsNotNone(retained_step.receipt)
                self.assertEqual(
                    order,
                    [
                        "provider:first",
                        "runtime:A",
                        f"crash:{call_a.tool_call_id}",
                    ],
                )

            with HostStorage(directory) as storage:
                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                adapter = _OrderedTurnAdapter(
                    order,
                    "resume",
                    (_completed(),),
                    required_runtime_label="B",
                )
                resumed = OrdivonAgentLoop(
                    adapter,
                    RuntimeToolBridge(
                        committed,
                        harness_run_id=run_store.harness_run_id,
                        runtime=runtime,
                        run_store=run_store,
                        provider_source=run_store.snapshot_provider_source(
                            retained
                        ),
                    ),
                    budget=RunBudget(4, 4, 262_144, 120_000),
                    clock_ms=clock,
                ).resume(
                    retained=retained,
                    assignment_id=committed.assignment.assignment_id,
                    context_digest=committed.assignment.context_object_digest,
                )

                self.assertEqual(
                    resumed.stop_code,
                    RunStopCode.CANDIDATE_COMPLETED,
                )
                self.assertEqual(
                    order,
                    [
                        "provider:first",
                        "runtime:A",
                        f"crash:{call_a.tool_call_id}",
                        "runtime:B",
                        "provider:resume",
                    ],
                )
                self.assertEqual(resumed.tool_calls, 2)
                self.assertEqual(resumed.model_calls, 2)
                self.assertEqual(
                    [
                        message["toolCallId"]
                        for message in resumed.messages
                        if message.get("role") == "tool"
                    ],
                    [call_a.tool_call_id, call_b.tool_call_id],
                )
                self.assertEqual(
                    [
                        arguments["execution"]["args"]
                        for name, arguments in runtime.calls
                        if name == "workspace.exec"
                    ],
                    [["A"], ["B"]],
                )
                self.assertGreater(validate_history(storage).events, 0)

    def test_recovery_rejects_non_contiguous_seen_tool_cursor(self) -> None:
        call_a = AgentToolCall(
            "tool-call:provider-cursor:a",
            "run_check",
            {"checkId": "check:provider-cursor:a"},
        )
        call_b = AgentToolCall(
            "tool-call:provider-cursor:b",
            "run_check",
            {"checkId": "check:provider-cursor:b"},
        )
        messages = [
            {
                "role": "assistant",
                "content": None,
                "toolCalls": [call_a.to_dict(), call_b.to_dict()],
            }
        ]

        with self.assertRaisesRegex(ValueError, "contiguous seen prefix"):
            _recover_tool_batch(
                messages,
                [],
                {call_b.tool_call_id},
                _tool_step_intent(call_b),
            )

    def test_recovery_rejects_ambiguous_or_drifted_active_call(self) -> None:
        call = AgentToolCall(
            "tool-call:provider-cursor:active",
            "run_check",
            {"checkId": "check:provider-cursor:active"},
        )
        intent = _tool_step_intent(call)
        message = {
            "role": "assistant",
            "content": None,
            "toolCalls": [call.to_dict()],
        }
        with self.subTest("active identity appears in multiple batches"):
            with self.assertRaisesRegex(ValueError, "repeats a Tool Call identity"):
                _recover_tool_batch(
                    [message, dict(message)],
                    [],
                    {call.tool_call_id},
                    intent,
                )

        drifted = AgentToolCall(
            call.tool_call_id,
            call.name,
            {"checkId": "check:provider-cursor:drifted"},
        )
        with self.subTest("active call digest differs from intent"):
            with self.assertRaisesRegex(
                ValueError,
                "differs from its durable assistant call",
            ):
                _recover_tool_batch(
                    [
                        {
                            "role": "assistant",
                            "content": None,
                            "toolCalls": [drifted.to_dict()],
                        }
                    ],
                    [],
                    {call.tool_call_id},
                    intent,
                )

    def test_bridge_provider_claim_ttl_is_short_and_bounded(self) -> None:
        request = AgentTurnRequest(
            harness_run_id="harness-run:provider-claim-ttl",
            turn_id="turn:provider-claim-ttl:1",
            sequence=1,
            assignment_id="assignment:provider-claim-ttl",
            context_digest=canonical_digest({"context": "provider-claim-ttl"}),
            tool_catalog_digest=canonical_digest(
                {"toolCatalog": "provider-claim-ttl"}
            ),
            messages=({"role": "user", "content": "Bound the claim window."},),
            tools=(),
            remaining_budget={
                "modelCalls": 4,
                "toolCalls": 4,
                "observationBytes": 65_536,
                "wallTimeMs": 86_400_000,
            },
        )
        self.assertEqual(RuntimeToolBridge._provider_claim_ttl_ms(request), 15_000)

    def test_only_an_expired_undispatched_claim_can_be_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, committed, _, _ = _assign(
                    storage,
                    clock,
                    _RecoveryRuntime(),
                )
                first = HostHarnessRunStore(host, committed)
                state = HarnessRunState(
                    messages=({"role": "user", "content": "claim"},),
                    observations=(),
                    remaining_budget={
                        "modelCalls": 4,
                        "toolCalls": 4,
                        "observationBytes": 65_536,
                        "wallTimeMs": 30_000,
                    },
                    requested_model_id=ScriptedTurnAdapter.model_id,
                    effective_model_id=None,
                )
                first.bind_state(state)
                source = first.assignment_provider_source()
                claimed = first.claim_provider_call(
                    source=source,
                    turn_id="turn:provider-claim:1",
                    turn_sequence=1,
                    request_digest=canonical_digest({"request": 1}),
                    provider_request_digest=canonical_digest(
                        {"providerRequest": 1}
                    ),
                    adapter_id="ordivon.provider-claim-fixture.v1",
                    requested_model_id=ScriptedTurnAdapter.model_id,
                    holder_id="holder:first",
                    ttl_ms=10,
                )
                clock.value += 11
                second = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                )
                second.bind_state(state)
                reclaimed = second.claim_provider_call(
                    source=source,
                    turn_id="turn:provider-claim:1",
                    turn_sequence=1,
                    request_digest=canonical_digest({"request": 1}),
                    provider_request_digest=canonical_digest(
                        {"providerRequest": 1}
                    ),
                    adapter_id="ordivon.provider-claim-fixture.v1",
                    requested_model_id=ScriptedTurnAdapter.model_id,
                    holder_id="holder:second",
                    ttl_ms=10,
                )
                self.assertEqual(reclaimed.record.claim_generation, 2)
                with self.assertRaises(HarnessSuperseded):
                    first.mark_provider_call_dispatching(claimed)

                dispatching = second.mark_provider_call_dispatching(reclaimed)
                clock.value += 100
                third = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                )
                third.bind_state(state)
                with self.assertRaises(HarnessProviderCallRecoveryRequired):
                    third.claim_provider_call(
                        source=source,
                        turn_id=dispatching.record.turn_id,
                        turn_sequence=dispatching.record.turn_sequence,
                        request_digest=dispatching.record.request_digest,
                        provider_request_digest=(
                            dispatching.record.provider_request_digest
                        ),
                        adapter_id=dispatching.record.adapter_id,
                        requested_model_id=dispatching.record.requested_model_id,
                        holder_id="holder:third",
                        ttl_ms=10,
                    )

    def test_safe_failure_recovery_consumes_retry_budget_across_crashes(self) -> None:
        budget = RunBudget(
            4,
            4,
            262_144,
            120_000,
            max_model_retries=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            self._prepare_pause(directory, budget=budget)
            calls = [0]
            additional = (
                {"role": "user", "content": "Retry only within the durable budget."},
            )

            for expected_generation in (1, 2):
                with HostStorage(directory) as storage:
                    clock = _MutableClock()
                    host = HarnessHost(storage, clock_ms=clock)
                    committed = host.load_current_assignment(TASK_ID)
                    run_store = HostHarnessRunStore(host, committed)
                    retained = run_store.load_current_snapshot()
                    bridge = _CrashAfterProviderFailure(
                        committed,
                        harness_run_id=run_store.harness_run_id,
                        runtime=_RecoveryRuntime(),
                        run_store=run_store,
                        provider_source=run_store.snapshot_provider_source(retained),
                    )
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "injected crash after durable Provider failure",
                    ):
                        OrdivonAgentLoop(
                            _FailureAdapter(calls),
                            bridge,
                            budget=budget,
                            clock_ms=clock,
                        ).resume(
                            retained=retained,
                            assignment_id=committed.assignment.assignment_id,
                            context_digest=committed.assignment.context_object_digest,
                            additional_messages=additional,
                        )
                    failed = HostHarnessRunStore(
                        host,
                        host.load_current_assignment(TASK_ID),
                    ).load_current_provider_call()
                    self.assertEqual(failed.record.status.value, "failed")
                    self.assertEqual(
                        failed.record.claim_generation,
                        expected_generation,
                    )
                    self.assertIsNotNone(failed.failure)
                    self.assertEqual(
                        failed.failure.failure_code,
                        AgentTurnFailureCode.TRANSPORT_FAILED.value,
                    )
                    self.assertEqual(
                        failed.failure.dispatch_safety,
                        AgentTurnDispatchSafety.PRE_DISPATCH_SAFE.value,
                    )
                    self.assertEqual(
                        failed.record.failure_digest,
                        failed.failure.digest,
                    )
                    self.assertEqual(
                        failed.record.failure_object_digest,
                        failed.failure_object.digest,
                    )
                    if expected_generation == 2:
                        self.assertEqual(
                            failed.state.remaining_budget["modelRetries"],
                            0,
                        )

            with HostStorage(directory) as storage:
                replayed = HarnessRunner(
                    HarnessHost(storage, clock_ms=_MutableClock()),
                    runtime=_RecoveryRuntime(),
                    adapter=_FailureAdapter(calls, fail_if_invoked=True),
                ).resume(
                    TASK_ID,
                    additional_messages=additional,
                )

                self.assertEqual(
                    replayed.loop_result.stop_code,
                    RunStopCode.PROVIDER_TRANSPORT_FAILED,
                )
                self.assertIn(
                    "fixture Provider failure",
                    replayed.loop_result.trace.events[-1].payload["detail"],
                )

    def test_expired_retry_claim_preserves_consumed_retry_budget(self) -> None:
        budget = RunBudget(
            4,
            4,
            262_144,
            120_000,
            max_model_retries=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            self._prepare_pause(directory, budget=budget)
            calls = [0]
            clock = _MutableClock()
            additional = (
                {"role": "user", "content": "Preserve the claimed retry budget."},
            )

            with HostStorage(directory) as storage:
                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                bridge = _CrashAfterProviderRetryClaim(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=_RecoveryRuntime(),
                    run_store=run_store,
                    provider_source=run_store.snapshot_provider_source(retained),
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected crash after durable Provider retry claim",
                ):
                    OrdivonAgentLoop(
                        _FailureAdapter(calls),
                        bridge,
                        budget=budget,
                        clock_ms=clock,
                    ).resume(
                        retained=retained,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=committed.assignment.context_object_digest,
                        additional_messages=additional,
                    )

                retry_claim = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_provider_call()
                self.assertEqual(retry_claim.record.status.value, "claimed")
                self.assertEqual(retry_claim.record.claim_generation, 2)
                self.assertEqual(
                    retry_claim.state.remaining_budget["modelRetries"],
                    0,
                )
                retry_state_object_digest = retry_claim.record.state_object_digest
                clock.value = retry_claim.record.expires_at_ms + 1

            with HostStorage(directory) as storage:
                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                stale_state = HarnessRunState(
                    messages=retained.state.messages + additional,
                    observations=retained.state.observations,
                    remaining_budget=retained.state.remaining_budget,
                    requested_model_id=retained.state.requested_model_id,
                    effective_model_id=retained.state.effective_model_id,
                    seen_model_call_ids=retained.state.seen_model_call_ids,
                    seen_tool_call_ids=retained.state.seen_tool_call_ids,
                    provider_usage=retained.state.provider_usage,
                    effective_model_ids=retained.state.effective_model_ids,
                )
                run_store.bind_state(stale_state)
                with self.assertRaises(HarnessProviderCallRequestMismatch):
                    run_store.claim_provider_call(
                        source=run_store.snapshot_provider_source(retained),
                        turn_id=retry_claim.record.turn_id,
                        turn_sequence=retry_claim.record.turn_sequence,
                        request_digest=retry_claim.record.request_digest,
                        provider_request_digest=(
                            retry_claim.record.provider_request_digest
                        ),
                        adapter_id=retry_claim.record.adapter_id,
                        requested_model_id=retry_claim.record.requested_model_id,
                        holder_id="holder:stale-snapshot",
                        ttl_ms=1_000,
                    )
                still_claimed = run_store.load_current_provider_call()
                self.assertEqual(
                    still_claimed.record.state_object_digest,
                    retry_state_object_digest,
                )
                bridge = RuntimeToolBridge(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=_RecoveryRuntime(),
                    run_store=run_store,
                    provider_source=run_store.snapshot_provider_source(retained),
                )
                resumed = OrdivonAgentLoop(
                    _FailureAdapter(calls),
                    bridge,
                    budget=budget,
                    clock_ms=clock,
                ).resume(
                    retained=retained,
                    assignment_id=committed.assignment.assignment_id,
                    context_digest=committed.assignment.context_object_digest,
                    additional_messages=additional,
                )

                self.assertEqual(
                    resumed.stop_code,
                    RunStopCode.PROVIDER_TRANSPORT_FAILED,
                )
                self.assertEqual(resumed.usage["modelRetries"], 1)
                self.assertEqual(resumed.usage["providerAttempts"], 3)
                self.assertEqual(calls, [2])
                failed = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_provider_call()
                self.assertEqual(failed.record.status.value, "failed")
                self.assertEqual(failed.record.claim_generation, 3)
                self.assertEqual(
                    failed.state.remaining_budget["modelRetries"],
                    0,
                )
                self.assertIsNotNone(failed.state.active_elapsed_ms)
                self.assertGreaterEqual(
                    failed.state.active_elapsed_ms,
                    retry_claim.state.active_elapsed_ms,
                )
                self.assertLessEqual(
                    failed.state.remaining_budget["wallTimeMs"],
                    retry_claim.state.remaining_budget["wallTimeMs"],
                )
                self.assertEqual(
                    failed.record.state_object_digest,
                    failed.state_object.digest,
                )

    def test_provider_rejection_replays_original_stop_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._prepare_pause(directory)
            calls = [0]
            additional = (
                {"role": "user", "content": "Do not repeat a rejected request."},
            )
            with HostStorage(directory) as storage:
                clock = _MutableClock()
                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                bridge = _CrashAfterProviderFailure(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=_RecoveryRuntime(),
                    run_store=run_store,
                    provider_source=run_store.snapshot_provider_source(retained),
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected crash after durable Provider failure",
                ):
                    OrdivonAgentLoop(
                        _FailureAdapter(
                            calls,
                            failure_code=AgentTurnFailureCode.REJECTED,
                            dispatch_safety=(
                                AgentTurnDispatchSafety.PROVIDER_REJECTED
                            ),
                            detail="fixture quota rejection",
                        ),
                        bridge,
                        budget=RunBudget(4, 4, 262_144, 120_000),
                        clock_ms=clock,
                    ).resume(
                        retained=retained,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=committed.assignment.context_object_digest,
                        additional_messages=additional,
                    )

            with HostStorage(directory) as storage:
                replayed = HarnessRunner(
                    HarnessHost(storage, clock_ms=_MutableClock()),
                    runtime=_RecoveryRuntime(),
                    adapter=_FailureAdapter(calls, fail_if_invoked=True),
                ).resume(
                    TASK_ID,
                    additional_messages=additional,
                )

                self.assertEqual(
                    replayed.loop_result.stop_code,
                    RunStopCode.PROVIDER_REJECTED,
                )
                self.assertEqual(calls, [1])

    def test_ambiguous_failure_stays_unknown_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._prepare_pause(directory)
            calls = [0]
            additional = (
                {"role": "user", "content": "Never guess whether dispatch happened."},
            )
            with HostStorage(directory) as storage:
                clock = _MutableClock()
                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                bridge = _CrashAfterProviderFailure(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=_RecoveryRuntime(),
                    run_store=run_store,
                    provider_source=run_store.snapshot_provider_source(retained),
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected crash after durable Provider failure",
                ):
                    OrdivonAgentLoop(
                        _FailureAdapter(
                            calls,
                            failure_code=AgentTurnFailureCode.TIMEOUT,
                            dispatch_safety=(
                                AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS
                            ),
                            detail="fixture timeout after possible dispatch",
                        ),
                        bridge,
                        budget=RunBudget(4, 4, 262_144, 120_000),
                        clock_ms=clock,
                    ).resume(
                        retained=retained,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=committed.assignment.context_object_digest,
                        additional_messages=additional,
                    )
                unknown = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_provider_call()
                self.assertEqual(unknown.record.status.value, "unknown")

            with HostStorage(directory) as storage:
                replayed = HarnessRunner(
                    HarnessHost(storage, clock_ms=_MutableClock()),
                    runtime=_RecoveryRuntime(),
                    adapter=_FailureAdapter(calls, fail_if_invoked=True),
                ).resume(
                    TASK_ID,
                    additional_messages=additional,
                )

                self.assertEqual(
                    replayed.loop_result.stop_code,
                    RunStopCode.PROVIDER_STATE_UNKNOWN,
                )
                self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()

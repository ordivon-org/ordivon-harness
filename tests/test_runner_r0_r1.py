from __future__ import annotations

import itertools
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO

from anc_canonical import canonical_digest
from ordivon_host import HostStorage
from ordivon_host.cognition import BlockKind, ContextBlock, Freshness
from test_ordivon_harness_oh5 import (
    TASK_ID,
    _assign,
    _contract,
    _create_task,
    _grant,
    _RecoveryRuntime,
)

from ordivon_harness import (
    CompletionMode,
    HarnessHost,
    HarnessLifecycleError,
    HarnessRunner,
    HarnessRunPlan,
)
from ordivon_harness.cli import main as cli_main
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnAdapterError,
    AgentTurnResult,
    HostHarnessRunStore,
    RunBudget,
    RunStopCode,
    RuntimeToolBridge,
    ScriptedTurnAdapter,
    ToolBridgeError,
)


def _clock():
    return itertools.count(10_000).__next__


def _block() -> ContextBlock:
    return ContextBlock(
        block_id="context-block:runner-r0-r1:readme",
        kind=BlockKind.TASK,
        priority=100,
        required=True,
        freshness=Freshness.CURRENT,
        source_digest=canonical_digest({"source": "runner-r0-r1"}),
        payload={"relativePath": "README.md", "mode": "FULL"},
    )


def _plan(
    *,
    completion_mode: CompletionMode = CompletionMode.RECORD,
) -> HarnessRunPlan:
    return HarnessRunPlan(
        task_contract=_contract(),
        context_blocks=(_block(),),
        workspace_ref="workspace:runner-r0-r1",
        tool_grant=_grant(),
        token_budget=4_000,
        budget=RunBudget(4, 4, 262_144, 120_000),
        source_ref="repository:ordivon-harness@fixture",
        source_digest=canonical_digest({"revision": "fixture"}),
        completion_mode=completion_mode,
    )


def _turn(
    suffix: str,
    *,
    calls: tuple[AgentToolCall, ...] = (),
    conclusion: AgentRunConclusion | None = None,
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:runner:{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=calls,
        conclusion=conclusion,
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="tool_calls" if calls else "stop",
        raw_response_digest=canonical_digest({"runnerResponse": suffix}),
    )


def _completion(suffix: str = "completed") -> AgentTurnResult:
    return _turn(
        suffix,
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Runner completed the fixture Task.",
        ),
    )


class _BlockingCallHandle:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.cancelled = threading.Event()

    def poll(self, timeout_seconds: float) -> AgentTurnResult | None:
        self.started.set()
        if self.cancelled.wait(timeout_seconds):
            raise AgentTurnAdapterError("blocking fixture call was cancelled")
        return None

    def cancel(self) -> None:
        self.cancelled.set()


class _BlockingAdapter:
    adapter_id = "ordivon.test-blocking-adapter.v1"
    model_id = "ordivon.test-blocking-model.v1"
    supports_call_handle = True

    def __init__(self) -> None:
        self.handle = _BlockingCallHandle()

    def start_invoke(self, request, control):
        del request, control
        return self.handle

    def invoke(self, request):
        raise AssertionError(request)


class HarnessRunnerR0R1Tests(unittest.TestCase):
    def test_runner_prepares_records_and_proposes_candidate_completion(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            HostStorage(directory) as storage,
        ):
            clock = _clock()
            _create_task(storage, clock)
            runtime = _RecoveryRuntime()
            adapter = ScriptedTurnAdapter(
                (
                    _turn(
                        "read",
                        calls=(
                            AgentToolCall(
                                "tool-call:runner:read",
                                "read_workspace",
                                {"relativePath": "README.md"},
                            ),
                        ),
                    ),
                    _completion(),
                )
            )
            runner = HarnessRunner(
                HarnessHost(storage, clock_ms=clock),
                runtime=runtime,
                adapter=adapter,
            )

            result = runner.run(_plan(completion_mode=CompletionMode.PROPOSE))

            self.assertEqual(
                result.loop_result.stop_code, RunStopCode.CANDIDATE_COMPLETED
            )
            self.assertIsNotNone(result.recorded)
            self.assertIsNotNone(result.proposal)
            self.assertIsNone(result.decision)
            self.assertEqual(runner.status(TASK_ID).phase, "completion-proposed")
            self.assertGreater(validate_history(storage).events, 0)

    def test_runner_pauses_and_resumes_from_public_run_state(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            HostStorage(directory) as storage,
        ):
            clock = _clock()
            _create_task(storage, clock)
            runtime = _RecoveryRuntime()
            first = HarnessRunner(
                HarnessHost(storage, clock_ms=clock),
                runtime=runtime,
                adapter=ScriptedTurnAdapter(
                    (
                        _turn(
                            "needs-input",
                            conclusion=AgentRunConclusion(
                                status="needs_input",
                                summary="Provide the missing operator detail.",
                            ),
                        ),
                    )
                ),
            )

            paused = first.run(_plan())
            self.assertTrue(paused.paused)
            status = first.status(TASK_ID)
            self.assertEqual(status.phase, "paused")
            self.assertEqual(status.pause_reason, "needs-input")
            with self.assertRaisesRegex(HarnessLifecycleError, "use resume"):
                first.run_current(TASK_ID)

            adapter = ScriptedTurnAdapter((_completion("resumed"),))
            resumed = HarnessRunner(
                first.host,
                runtime=runtime,
                adapter=adapter,
            ).resume(
                TASK_ID,
                additional_messages=(
                    {"role": "user", "content": "The missing detail is fixture-ready."},
                ),
            )

            self.assertEqual(
                resumed.loop_result.stop_code, RunStopCode.CANDIDATE_COMPLETED
            )
            self.assertIsNotNone(resumed.recorded)
            self.assertEqual(
                adapter.requests[0].messages[-1],
                {"role": "user", "content": "The missing detail is fixture-ready."},
            )
            self.assertEqual(first.status(TASK_ID).phase, "run-recorded")
            with self.assertRaisesRegex(HarnessLifecycleError, "already recorded"):
                first.run_current(TASK_ID)
            self.assertGreater(validate_history(storage).events, 0)

    def test_run_handle_cancels_active_provider_call_and_records_result(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            HostStorage(directory) as storage,
        ):
            clock = _clock()
            _create_task(storage, clock)
            runtime = _RecoveryRuntime()
            adapter = _BlockingAdapter()
            runner = HarnessRunner(
                HarnessHost(storage, clock_ms=clock),
                runtime=runtime,
                adapter=adapter,
            )
            runner.prepare(_plan())

            handle = runner.start_current(TASK_ID)
            self.assertTrue(adapter.handle.started.wait(2))
            cancellation = runner.cancel(TASK_ID)
            result = handle.result(5)

            self.assertTrue(cancellation.requested)
            self.assertEqual(
                cancellation.status,
                "in-process-cancellation-requested",
            )
            self.assertEqual(result.loop_result.stop_code, RunStopCode.CANCELLED)
            self.assertIsNotNone(result.recorded)
            self.assertTrue(adapter.handle.cancelled.is_set())
            self.assertEqual(runner.status(TASK_ID).termination_code, "cancelled")

    def test_durable_tool_surface_hides_mutation_and_approval_pause(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            HostStorage(directory) as storage,
        ):
            clock = _clock()
            _create_task(storage, clock)
            runtime = _RecoveryRuntime()
            host, prepared, _, _ = _assign(
                storage,
                clock,
                runtime,
                grant=_grant("mutation"),
                workspace_id="workspace:runner-mutation",
            )
            assert prepared.native_run_contract is not None
            bridge = RuntimeToolBridge(
                prepared,
                harness_run_id=prepared.native_run_contract.harness_run_id,
                runtime=runtime,
                run_store=HostHarnessRunStore(host, prepared),
            )

            self.assertNotIn(
                "mutate_workspace",
                {definition.name for definition in bridge.definitions()},
            )
            with self.assertRaisesRegex(ToolBridgeError, "unsupported Harness pause"):
                bridge.record_pause("approval_required")
            with self.assertRaisesRegex(ValueError, "cannot grant mutate_workspace"):
                HarnessRunPlan(
                    task_contract=_contract(),
                    context_blocks=(_block(),),
                    workspace_ref="workspace:runner-mutation",
                    tool_grant=_grant("mutation"),
                )

    def test_adjudication_configuration_fails_before_preparing_attempt(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            HostStorage(directory) as storage,
        ):
            clock = _clock()
            _create_task(storage, clock)
            runner = HarnessRunner(
                HarnessHost(storage, clock_ms=clock),
                runtime=_RecoveryRuntime(),
                adapter=ScriptedTurnAdapter((_completion(),)),
            )

            with self.assertRaisesRegex(
                HarnessLifecycleError, "requires artifact_exists"
            ):
                runner.run(_plan(completion_mode=CompletionMode.ADJUDICATE))

            self.assertEqual(runner.status(TASK_ID).phase, "task")

    def test_cli_status_reads_host_state_without_runtime_or_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                _create_task(storage, _clock())
            output = StringIO()
            with redirect_stdout(output):
                exit_code = cli_main(["--state-root", directory, "status", TASK_ID])

            self.assertEqual(exit_code, 0)
            value = json.loads(output.getvalue())
            self.assertTrue(value["ok"])
            self.assertEqual(value["phase"], "task")
            self.assertEqual(value["taskId"], TASK_ID)


if __name__ == "__main__":
    unittest.main()

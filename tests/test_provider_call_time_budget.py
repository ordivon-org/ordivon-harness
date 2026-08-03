from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace

from ordivon_host import HostStorage
from test_ordivon_harness_oh5 import TASK_ID, _RecoveryRuntime, _create_task
from test_provider_call_durability import (
    _CrashAfterProviderResult,
    _MutableClock,
    _ReplayAdapter,
    _completed,
    _needs_input,
)
from test_runner_r0_r1 import _plan

from ordivon_harness import HarnessHost, HarnessLifecycleError, HarnessRunner
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentTurnRequest,
    AgentTurnResult,
    OrdivonAgentLoop,
    RunBudget,
    RunStopCode,
    ScriptedTurnAdapter,
    static_provider_request_digest,
)
from ordivon_harness.ordivon.run_store import HostHarnessRunStore
from ordivon_harness.run_state import (
    build_state_delta,
    load_state_object,
)


class _TimedCompletionAdapter:
    adapter_id = "ordivon.provider-time-budget.v1"
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(
        self,
        monotonic: _MutableClock,
        calls: list[int],
        *,
        advance_ms: int,
        wall: _MutableClock | None = None,
        rolled_back_wall_ms: int | None = None,
        fail_if_invoked: bool = False,
    ) -> None:
        self.monotonic = monotonic
        self.calls = calls
        self.advance_ms = advance_ms
        self.wall = wall
        self.rolled_back_wall_ms = rolled_back_wall_ms
        self.fail_if_invoked = fail_if_invoked

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        del request
        if self.fail_if_invoked:
            raise AssertionError("durable timed Provider result was not replayed")
        self.calls[0] += 1
        self.monotonic.value += self.advance_ms
        if self.wall is not None and self.rolled_back_wall_ms is not None:
            self.wall.value = self.rolled_back_wall_ms
        return _completed()


class _CatalogCountingRuntime(_RecoveryRuntime):
    def __init__(self, *, reject_catalog: bool = False) -> None:
        super().__init__()
        self.catalog_reads = 0
        self.reject_catalog = reject_catalog

    def list_tools(self):
        self.catalog_reads += 1
        if self.reject_catalog:
            raise AssertionError("expired execution touched the Runtime catalog")
        return super().list_tools()


class _DeadlineConsumingIdentityAdapter:
    adapter_id = "ordivon.provider-identity-deadline.v1"
    model_id = ScriptedTurnAdapter.model_id

    def __init__(
        self,
        monotonic: _MutableClock,
        physical_calls: list[int],
        identity_calls: list[int],
        *,
        advance_monotonic_ms: int = 0,
        wall: _MutableClock | None = None,
        advance_wall_ms: int = 0,
        fail_if_touched: bool = False,
    ) -> None:
        self.monotonic = monotonic
        self.physical_calls = physical_calls
        self.identity_calls = identity_calls
        self.advance_monotonic_ms = advance_monotonic_ms
        self.wall = wall
        self.advance_wall_ms = advance_wall_ms
        self.fail_if_touched = fail_if_touched

    def provider_request_digest(self, request: AgentTurnRequest) -> str:
        if self.fail_if_touched:
            raise AssertionError("budget mismatch touched the Provider adapter")
        self.identity_calls[0] += 1
        self.monotonic.value += self.advance_monotonic_ms
        if self.wall is not None:
            self.wall.value += self.advance_wall_ms
        return static_provider_request_digest(self, request)

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        del request
        if self.fail_if_touched:
            raise AssertionError("budget mismatch physically invoked the Provider")
        self.physical_calls[0] += 1
        return _completed()


class ProviderCallTimeBudgetTests(unittest.TestCase):
    def test_provider_identity_cannot_dispatch_after_active_deadline(self) -> None:
        budget = RunBudget(4, 4, 262_144, 50)
        wall = _MutableClock()
        monotonic = _MutableClock(0)
        physical_calls = [0]
        identity_calls = [0]
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                _create_task(storage, wall)
                execution = HarnessRunner(
                    HarnessHost(storage, clock_ms=wall),
                    runtime=_RecoveryRuntime(),
                    adapter=_DeadlineConsumingIdentityAdapter(
                        monotonic,
                        physical_calls,
                        identity_calls,
                        advance_monotonic_ms=51,
                    ),
                    monotonic_ms=monotonic,
                ).run(_plan(budget=budget))

                self.assertEqual(identity_calls, [1])
                self.assertEqual(physical_calls, [0])
                self.assertEqual(
                    execution.loop_result.stop_code,
                    RunStopCode.BUDGET_EXHAUSTED,
                )
                self.assertEqual(execution.loop_result.usage["wallTimeMs"], 51)
                self.assertIsNotNone(execution.recorded)
                self.assertGreater(validate_history(storage).events, 0)

    def test_provider_identity_cannot_dispatch_after_assignment_deadline(self) -> None:
        budget = RunBudget(4, 4, 262_144, 10_000)
        wall = _MutableClock()
        monotonic = _MutableClock(0)
        physical_calls = [0]
        identity_calls = [0]
        plan = replace(
            _plan(budget=budget),
            deadline_ms=wall.value + 10,
        )
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                _create_task(storage, wall)
                execution = HarnessRunner(
                    HarnessHost(storage, clock_ms=wall),
                    runtime=_RecoveryRuntime(),
                    adapter=_DeadlineConsumingIdentityAdapter(
                        monotonic,
                        physical_calls,
                        identity_calls,
                        wall=wall,
                        advance_wall_ms=10,
                    ),
                    monotonic_ms=monotonic,
                ).run(plan)

                self.assertEqual(identity_calls, [1])
                self.assertEqual(physical_calls, [0])
                self.assertEqual(wall.value, plan.deadline_ms)
                self.assertEqual(
                    execution.loop_result.stop_code,
                    RunStopCode.BUDGET_EXHAUSTED,
                )
                self.assertIsNotNone(execution.recorded)
                self.assertGreater(validate_history(storage).events, 0)

    def test_run_current_rejects_budget_replacement_before_dependencies(self) -> None:
        committed_budget = RunBudget(4, 4, 262_144, 10_000)
        replacement_budget = RunBudget(4, 4, 262_144, 9_999)
        wall = _MutableClock()
        monotonic = _MutableClock(0)
        physical_calls = [0]
        identity_calls = [0]
        runtime = _CatalogCountingRuntime()
        adapter = _DeadlineConsumingIdentityAdapter(
            monotonic,
            physical_calls,
            identity_calls,
            fail_if_touched=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                _create_task(storage, wall)
                runner = HarnessRunner(
                    HarnessHost(storage, clock_ms=wall),
                    runtime=runtime,
                    adapter=adapter,
                    monotonic_ms=monotonic,
                )
                runner.prepare(_plan(budget=committed_budget))
                catalog_reads = runtime.catalog_reads
                runtime_calls = list(runtime.calls)
                runtime.reject_catalog = True

                with self.assertRaisesRegex(
                    HarnessLifecycleError,
                    "cannot replace its committed Run budget",
                ):
                    runner.run_current(
                        TASK_ID,
                        budget=replacement_budget,
                    )

                self.assertEqual(runtime.catalog_reads, catalog_reads)
                self.assertEqual(runtime.calls, runtime_calls)
                self.assertEqual(identity_calls, [0])
                self.assertEqual(physical_calls, [0])

    def test_completed_overrun_is_checkpointed_before_crash_and_replay(self) -> None:
        budget = RunBudget(4, 4, 262_144, 50)
        wall = _MutableClock()
        monotonic = _MutableClock(0)
        calls = [0]
        additional = ({"role": "user", "content": "Finish within the budget."},)
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                _create_task(storage, wall)
                paused = HarnessRunner(
                    HarnessHost(storage, clock_ms=wall),
                    runtime=_RecoveryRuntime(),
                    adapter=ScriptedTurnAdapter((_needs_input(),)),
                    monotonic_ms=monotonic,
                ).run(_plan(budget=budget))
                self.assertTrue(paused.paused)

                host = HarnessHost(storage, clock_ms=wall)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                assert retained.state.active_elapsed_ms is not None
                inconsistent = replace(
                    retained.state,
                    active_elapsed_ms=retained.state.active_elapsed_ms + 1,
                )
                with self.assertRaisesRegex(ValueError, "wall-time budget"):
                    run_store.bind_state(inconsistent)

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
                        _TimedCompletionAdapter(
                            monotonic,
                            calls,
                            advance_ms=75,
                        ),
                        bridge,
                        budget=budget,
                        clock_ms=wall,
                        monotonic_ms=monotonic,
                    ).resume(
                        retained=retained,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=committed.assignment.context_object_digest,
                        additional_messages=additional,
                    )

                completed = HostHarnessRunStore(
                    host,
                    host.load_current_assignment(TASK_ID),
                ).load_current_provider_call()
                self.assertEqual(completed.record.status.value, "completed")
                self.assertEqual(completed.state.active_elapsed_ms, 75)
                self.assertEqual(
                    completed.state.remaining_budget["wallTimeMs"],
                    0,
                )
                self.assertEqual(
                    completed.record.state_object_digest,
                    completed.state_object.digest,
                )

            with HostStorage(directory) as storage:
                runtime = _CatalogCountingRuntime(reject_catalog=True)
                replayed = HarnessRunner(
                    HarnessHost(storage, clock_ms=wall),
                    runtime=runtime,
                    adapter=_TimedCompletionAdapter(
                        monotonic,
                        calls,
                        advance_ms=0,
                        fail_if_invoked=True,
                    ),
                    monotonic_ms=monotonic,
                ).resume(TASK_ID, additional_messages=additional)

                self.assertEqual(
                    replayed.loop_result.stop_code,
                    RunStopCode.BUDGET_EXHAUSTED,
                )
                self.assertEqual(replayed.loop_result.usage["wallTimeMs"], 75)
                self.assertEqual(replayed.loop_result.usage["deadlineOverrunMs"], 25)
                self.assertEqual(calls, [1])
                self.assertEqual(runtime.catalog_reads, 0)
                self.assertEqual(runtime.calls, [])

    def test_assignment_deadline_survives_pause_without_runtime_or_provider(self) -> None:
        budget = RunBudget(4, 4, 262_144, 10_000)
        wall = _MutableClock()
        monotonic = _MutableClock(0)
        runtime = _CatalogCountingRuntime()
        calls = [0]
        plan = replace(
            _plan(budget=budget),
            deadline_ms=wall.value + 100,
        )
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                _create_task(storage, wall)
                paused = HarnessRunner(
                    HarnessHost(storage, clock_ms=wall),
                    runtime=runtime,
                    adapter=ScriptedTurnAdapter((_needs_input(),)),
                    monotonic_ms=monotonic,
                ).run(plan)
                self.assertTrue(paused.paused)
                catalog_reads = runtime.catalog_reads
                runtime_calls = list(runtime.calls)
                wall.value = int(plan.deadline_ms) + 1

                resumed = HarnessRunner(
                    HarnessHost(storage, clock_ms=wall),
                    runtime=runtime,
                    adapter=_ReplayAdapter(calls, fail_if_invoked=True),
                    monotonic_ms=monotonic,
                ).resume(TASK_ID)

                self.assertEqual(
                    resumed.loop_result.stop_code,
                    RunStopCode.BUDGET_EXHAUSTED,
                )
                self.assertEqual(calls, [0])
                self.assertEqual(runtime.catalog_reads, catalog_reads)
                self.assertEqual(runtime.calls, runtime_calls)

    def test_wall_clock_rollback_cannot_evade_monotonic_budget(self) -> None:
        wall = _MutableClock(1_000)
        monotonic = _MutableClock(500)
        calls = [0]
        budget = RunBudget(1, 1, 1_024, 50)
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                _create_task(storage, wall)
                execution = HarnessRunner(
                    HarnessHost(storage, clock_ms=wall),
                    runtime=_RecoveryRuntime(),
                    adapter=_TimedCompletionAdapter(
                        monotonic,
                        calls,
                        advance_ms=75,
                        wall=wall,
                        rolled_back_wall_ms=100,
                    ),
                    monotonic_ms=monotonic,
                ).run(_plan(budget=budget))

                self.assertEqual(
                    execution.loop_result.stop_code,
                    RunStopCode.BUDGET_EXHAUSTED,
                )
                self.assertEqual(execution.loop_result.usage["wallTimeMs"], 75)
                self.assertEqual(
                    execution.loop_result.usage["deadlineOverrunMs"],
                    25,
                )
                self.assertEqual(calls, [1])
                self.assertEqual(wall.value, 100)
                self.assertIsNotNone(execution.recorded)
                assert execution.recorded is not None
                self.assertEqual(execution.recorded.receipt.started_at_ms, 1_000)
                self.assertEqual(execution.recorded.receipt.finished_at_ms, 1_001)
                self.assertGreater(validate_history(storage).events, 0)

    def test_legacy_v1_full_and_delta_upgrade_to_exact_v2_elapsed(self) -> None:
        harness_run_id = "harness-run:legacy-time-budget"
        legacy_value = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-run-state",
            "harnessRunId": harness_run_id,
            "messages": [{"role": "user", "content": "x" * 10_000}],
            "observations": [],
            "remainingBudget": {
                "modelCalls": 2,
                "toolCalls": 2,
                "observationBytes": 10_000,
                "wallTimeMs": 100,
            },
            "requestedModelId": ScriptedTurnAdapter.model_id,
            "effectiveModelId": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                full_object = storage.put_object(
                    legacy_value,
                    kind="harness-run-state",
                )
                full = load_state_object(
                    storage.objects,
                    full_object.digest,
                    harness_run_id=harness_run_id,
                )
                self.assertIsNone(full.active_elapsed_ms)

                legacy_delta_state = replace(
                    full,
                    messages=full.messages
                    + ({"role": "assistant", "content": "legacy delta"},),
                    remaining_budget={
                        **full.remaining_budget,
                        "wallTimeMs": 99,
                    },
                )
                legacy_delta = build_state_delta(
                    harness_run_id=harness_run_id,
                    previous_state_object_digest=full_object.digest,
                    previous=full,
                    current=legacy_delta_state,
                )
                self.assertIsNotNone(legacy_delta)
                assert legacy_delta is not None
                self.assertEqual(legacy_delta["schemaVersion"], 1)
                legacy_delta_object = storage.put_object(
                    legacy_delta,
                    kind="harness-run-state-delta",
                )
                loaded_delta = load_state_object(
                    storage.objects,
                    legacy_delta_object.digest,
                    harness_run_id=harness_run_id,
                )
                self.assertEqual(loaded_delta, legacy_delta_state)
                self.assertIsNone(loaded_delta.active_elapsed_ms)

                upgraded = replace(
                    loaded_delta,
                    active_elapsed_ms=25,
                    remaining_budget={
                        **loaded_delta.remaining_budget,
                        "wallTimeMs": 75,
                    },
                )
                upgraded_delta = build_state_delta(
                    harness_run_id=harness_run_id,
                    previous_state_object_digest=legacy_delta_object.digest,
                    previous=loaded_delta,
                    current=upgraded,
                )
                self.assertIsNotNone(upgraded_delta)
                assert upgraded_delta is not None
                self.assertEqual(upgraded_delta["schemaVersion"], 2)
                upgraded_object = storage.put_object(
                    upgraded_delta,
                    kind="harness-run-state-delta",
                )
                self.assertEqual(
                    load_state_object(
                        storage.objects,
                        upgraded_object.digest,
                        harness_run_id=harness_run_id,
                    ),
                    upgraded,
                )


if __name__ == "__main__":
    unittest.main()

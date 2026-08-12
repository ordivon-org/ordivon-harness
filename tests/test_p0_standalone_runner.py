from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import unittest

from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.independent_result import (
    IndependentCompletionProposal,
    IndependentRunRecorder,
)
from ordivon_harness.ordivon.loop import RunStopCode
from ordivon_harness.ordivon.model import AgentRunConclusion, ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_agent_bridge import SQLiteHarnessAgentBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.standalone import StandaloneHarnessRunner
from ordivon_harness.store import HarnessRunStatus

from tests.test_p0_sqlite_agent_loop import (
    FixedClock,
    budget,
    completed_result,
    contract,
    needs_input_result,
)


class StandaloneHarnessRunnerTests(unittest.TestCase):
    @staticmethod
    def initialize(root: Path, suffix: str, clock: FixedClock, run_contract=None):
        run_contract = contract(suffix) if run_contract is None else run_contract
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        continuity = SQLiteHarnessRunContinuityStore(
            store,
            run_contract,
            clock_ms=clock,
        )
        return run_contract, store, continuity

    @staticmethod
    def runner(run_contract, continuity, adapter, bridge, clock):
        return StandaloneHarnessRunner(
            run_contract,
            continuity,
            adapter,
            bridge,
            budget=budget(),
            clock_ms=clock,
            monotonic_ms=clock,
        )

    def test_concurrent_workers_dispatch_one_physical_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = contract("same-run-race")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)

            workers = 12
            barrier = threading.Barrier(workers)
            physical_calls: list[int] = []
            physical_lock = threading.Lock()

            class CountingAdapter(ScriptedTurnAdapter):
                def __init__(self, worker: int) -> None:
                    super().__init__((completed_result("same-run-race"),))
                    self.worker = worker

                def invoke(self, request):
                    with physical_lock:
                        physical_calls.append(self.worker)
                    time.sleep(0.03)
                    return super().invoke(request)

            def execute(worker: int) -> str:
                clock = FixedClock()
                try:
                    with SQLiteHarnessStore(root) as store:
                        continuity = SQLiteHarnessRunContinuityStore.open(
                            store, run_contract.harness_run_id, clock_ms=clock
                        )
                        adapter = CountingAdapter(worker)
                        bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
                        runner = self.runner(
                            run_contract, continuity, adapter, bridge, clock
                        )
                        barrier.wait()
                        runner.run(({"role": "user", "content": "complete"},))
                    return "ok"
                except Exception as error:  # concurrency losers must not reach Provider
                    return type(error).__name__

            with ThreadPoolExecutor(max_workers=workers) as pool:
                outcomes = list(pool.map(execute, range(workers)))

            self.assertEqual(len(physical_calls), 1)
            self.assertEqual(outcomes.count("ok"), 1)
            with SQLiteHarnessStore(root) as store:
                report = store.doctor(full=True)
                projection = store.load_run(run_contract.harness_run_id)
                events = store.list_run_events(run_contract.harness_run_id)
                event_kinds = [event.event_kind for event in events]
                self.assertTrue(report["healthy"] )
                self.assertEqual(projection.status, HarnessRunStatus.COMPLETED)
                self.assertEqual(event_kinds.count("harness.provider-call-claimed"), 1)
                self.assertEqual(event_kinds.count("harness.provider-call-dispatching"), 1)
                self.assertEqual(event_kinds.count("harness.provider-call-completed"), 1)
                self.assertEqual(event_kinds.count("harness.run-completed"), 1)


    def test_structured_completion_requires_adapter_binding_to_exact_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            base = contract("structured-binding")
            run_contract = replace(
                base,
                completion_contract={
                    "mode": "structured-result-v1",
                    "resultSchema": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                    },
                },
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=clock
            )
            adapter = ScriptedTurnAdapter((completed_result("structured-binding"),))
            bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            with self.assertRaisesRegex(ValueError, "structured completion differs"):
                StandaloneHarnessRunner(
                    run_contract,
                    continuity,
                    adapter,
                    bridge,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                )
            store.close()


    def test_completed_run_preserves_unresolved_unknowns_for_caller(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = replace(
                contract("completed-with-unknowns"),
                privacy=HarnessPrivacyPolicy(
                    content_policy="bounded-private-content",
                    allow_model_content=True,
                    allow_tool_content=False,
                ),
            )
            run_contract, store, continuity = self.initialize(
                root, "completed-with-unknowns", clock, run_contract
            )
            unknowns = (
                "A later Run must observe the current repository before executing the plan.",
            )
            candidate = replace(
                completed_result("completed-with-unknowns"),
                conclusion=AgentRunConclusion(
                    status="candidate_completed",
                    summary="The bounded planning Run produced a usable strategy.",
                    unresolved_unknowns=unknowns,
                ),
            )
            runner = self.runner(
                run_contract,
                continuity,
                ScriptedTurnAdapter((candidate,)),
                SQLiteHarnessAgentBridge(run_contract, continuity),
                clock,
            )
            execution = runner.run(({"role": "user", "content": "plan"},))
            self.assertEqual(
                execution.loop_result.stop_code, RunStopCode.CANDIDATE_COMPLETED
            )
            assert execution.terminal_result is not None
            terminal = execution.terminal_result
            assert terminal.conclusion is not None
            assert terminal.completion_proposal is not None
            self.assertEqual(terminal.conclusion.unresolved_unknowns, unknowns)
            self.assertEqual(
                terminal.completion_proposal.unresolved_unknowns, unknowns
            )
            encoded = terminal.completion_proposal.to_dict()
            self.assertEqual(encoded["schemaVersion"], 2)
            self.assertEqual(encoded["unresolvedUnknowns"], list(unknowns))

            legacy = dict(encoded)
            legacy["schemaVersion"] = 1
            legacy.pop("unresolvedUnknowns")
            decoded_legacy = IndependentCompletionProposal.from_dict(legacy)
            self.assertEqual(decoded_legacy.unresolved_unknowns, ())
            store.close()

    def test_candidate_completion_is_terminal_and_restart_inspectable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = replace(
                contract("standalone"),
                privacy=HarnessPrivacyPolicy(
                    content_policy="bounded-private-content",
                    allow_model_content=True,
                    allow_tool_content=False,
                ),
            )
            run_contract, store, continuity = self.initialize(
                root, "standalone", clock, run_contract
            )
            adapter = ScriptedTurnAdapter((completed_result("standalone"),))
            bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            runner = self.runner(run_contract, continuity, adapter, bridge, clock)

            execution = runner.run(
                ({"role": "user", "content": "complete independently"},)
            )

            self.assertEqual(execution.loop_result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertFalse(execution.paused)
            assert execution.terminal_result is not None
            terminal = execution.terminal_result
            self.assertEqual(terminal.receipt.stop_reason, "completed")
            self.assertEqual(terminal.receipt.contract_digest, run_contract.digest)
            self.assertEqual(terminal.receipt.trace_digest, terminal.trace.digest)
            self.assertIsNotNone(terminal.completion_proposal)
            self.assertEqual(
                terminal.completion_proposal.run_receipt_digest,
                terminal.receipt.digest,
            )
            self.assertEqual(
                store.load_run(run_contract.harness_run_id).status,
                HarnessRunStatus.COMPLETED,
            )
            self.assertEqual(runner.doctor()["result"]["terminalResults"], 1)
            receipt_digest = terminal.receipt.digest
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                recorder = IndependentRunRecorder(
                    reopened_store,
                    run_contract,
                    reopened.binding,
                    clock_ms=clock,
                )
                loaded = recorder.load_terminal_result()
                self.assertEqual(loaded.receipt.digest, receipt_digest)
                self.assertEqual(recorder.doctor()["traceSegments"], 1)
                self.assertTrue(reopened_store.doctor(full=True)["healthy"])

    def test_pause_resume_retains_two_trace_segments_and_one_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = replace(
                contract("standalone-resume"),
                privacy=HarnessPrivacyPolicy(
                    content_policy="bounded-private-content",
                    allow_model_content=True,
                    allow_tool_content=False,
                ),
            )
            run_contract, store, continuity = self.initialize(
                root, "standalone-resume", clock, run_contract
            )
            first_adapter = ScriptedTurnAdapter((needs_input_result("standalone-pause"),))
            first_bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            first = self.runner(
                run_contract,
                continuity,
                first_adapter,
                first_bridge,
                clock,
            ).run(({"role": "user", "content": "start"},))
            self.assertTrue(first.paused)
            self.assertEqual(first.loop_result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(
                store.load_run(run_contract.harness_run_id).status,
                HarnessRunStatus.PAUSED,
            )
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                adapter = ScriptedTurnAdapter((completed_result("standalone-resume"),))
                bridge = SQLiteHarnessAgentBridge(
                    run_contract,
                    reopened,
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                resumed = self.runner(
                    run_contract,
                    reopened,
                    adapter,
                    bridge,
                    clock,
                ).resume(
                    additional_messages=(
                        {"role": "user", "content": "the bounded answer is yes"},
                    )
                )
                self.assertFalse(resumed.paused)
                assert resumed.terminal_result is not None
                terminal = resumed.terminal_result
                self.assertGreater(
                    len(terminal.trace.events),
                    len(resumed.loop_result.trace.events),
                )
                self.assertEqual(
                    [
                        event.event_kind
                        for event in reopened_store.list_run_events(
                            run_contract.harness_run_id
                        )
                        if event.event_kind == "harness.trace-recorded"
                    ],
                    ["harness.trace-recorded", "harness.trace-recorded"],
                )
                recorder = IndependentRunRecorder(
                    reopened_store,
                    run_contract,
                    reopened.binding,
                    clock_ms=clock,
                )
                self.assertEqual(recorder.doctor()["traceSegments"], 2)

    def test_contract_budget_claims_exactly_bind_every_execution_limit(self) -> None:
        execution = budget()
        complete = execution.to_contract_dict()
        StandaloneHarnessRunner._validate_budget(complete, execution)

        for field, value in complete.items():
            with self.subTest(field=field):
                drifted = dict(complete)
                drifted[field] = value + 1
                with self.assertRaisesRegex(ValueError, field):
                    StandaloneHarnessRunner._validate_budget(drifted, execution)

        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            StandaloneHarnessRunner._validate_budget(
                {**complete, "futureUnimplementedBudget": 1},
                execution,
            )
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            StandaloneHarnessRunner._validate_budget(
                {"maxModelCalls": True},
                execution,
            )

    def test_schema_v1_partial_budget_remains_compatible_but_bound(self) -> None:
        execution = budget()
        historical = {
            "maxModelCalls": execution.max_model_calls,
            "maxToolCalls": execution.max_tool_calls,
            "maxWallTimeMs": execution.max_wall_time_ms,
        }
        StandaloneHarnessRunner._validate_budget(historical, execution)
        drifted = dict(historical)
        drifted["maxToolCalls"] += 1
        with self.assertRaisesRegex(ValueError, "maxToolCalls"):
            StandaloneHarnessRunner._validate_budget(drifted, execution)

    def test_recovery_assessment_is_authoritative_and_status_preserving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract, store, continuity = self.initialize(root, "recovery", clock)
            recorder = IndependentRunRecorder(
                store,
                run_contract,
                continuity.binding,
                clock_ms=clock,
            )
            assessment = recorder.record_recovery_assessment(
                trigger="process_lost",
                grant_effect_class="observation-only",
                catalog_status="matched",
                workspace_status="not_applicable",
                workspace_evidence={"runtimeJobs": 0},
                unresolved_unknowns=(),
            )
            self.assertTrue(assessment.safe_to_abandon)
            self.assertEqual(
                store.load_run(run_contract.harness_run_id).status,
                HarnessRunStatus.CREATED,
            )
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                recovered = IndependentRunRecorder(
                    reopened_store,
                    run_contract,
                    reopened.binding,
                    clock_ms=clock,
                ).load_latest_recovery_assessment()
                self.assertEqual(recovered.digest, assessment.digest)
                self.assertTrue(reopened_store.doctor(full=True)["healthy"])

    def test_new_terminal_modules_do_not_import_host(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "ordivon_harness"
        for relative in ("independent_result.py", "standalone.py", "ordivon/events.py"):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("ordivon_host", source)
            self.assertNotIn("_host_compat", source)
            self.assertNotIn("CommittedHarnessAssignment", source)


if __name__ == "__main__":
    unittest.main()

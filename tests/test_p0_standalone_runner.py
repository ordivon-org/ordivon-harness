from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ordivon_harness.independent_result import IndependentRunRecorder
from ordivon_harness.ordivon.loop import RunStopCode
from ordivon_harness.ordivon.model import ScriptedTurnAdapter
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
    def initialize(root: Path, suffix: str, clock: FixedClock):
        run_contract = contract(suffix)
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

    def test_candidate_completion_is_terminal_and_restart_inspectable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract, store, continuity = self.initialize(root, "standalone", clock)
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
            run_contract, store, continuity = self.initialize(root, "standalone-resume", clock)
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

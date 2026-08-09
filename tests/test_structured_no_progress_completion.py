from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.completion import structured_completion_contract_digest
from ordivon_harness.ordivon.loop import RunBudget, RunStopCode
from ordivon_harness.ordivon.model import ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.standalone import (
    StandaloneCognitionProfile,
    StandaloneCognitionSeed,
    StandaloneCognitionSeedSource,
    StandaloneHarnessRunner,
)
from ordivon_harness.working_view import (
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingViewSource,
)

from tests.test_p0_sqlite_runtime_bridge import (
    FakeRuntime,
    FixedClock,
    execution_binding,
)
from tests.test_pc14_candidate_discovery_overlay import transition_turn
from tests.test_pc15_epistemic_control import private_contract, tool_call, tool_turn


COMPLETION = {
    "mode": "structured-result-v1",
    "resultKind": "structured-no-progress-test",
    "resultSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"choice": {"type": "string", "enum": ["done", "unknown"]}},
        "required": ["choice"],
    },
}


class StructuredNoProgressCompletionTests(unittest.TestCase):
    def test_harness_no_progress_does_not_synthesize_agent_conclusion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = FakeRuntime("structured-no-progress")
            base = private_contract("structured-no-progress", max_model_calls=3, max_tool_calls=3)
            contract_budget = dict(base.budget)
            contract_budget["maxObservationOnlyTurns"] = 1
            run_contract = replace(
                base,
                completion_contract=COMPLETION,
                budget=contract_budget,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            clock = FixedClock()
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
            )

            source = HarnessWorkingViewSource(
                logical_ref="source://structured-no-progress/a",
                logical_generation="generation:a",
                messages=(
                    {
                        "role": "user",
                        "content": "Use bounded evidence and do not invent facts.",
                    },
                ),
            )
            stored_source = continuity.store_working_view_source(source)
            pin = HarnessWorkingSetPin(
                slot="primary",
                logical_ref=source.logical_ref,
                logical_generation=source.logical_generation,
                resolved_digest=stored_source.digest,
            )
            seed = StandaloneCognitionSeed(
                attempt_id="working-attempt:structured-no-progress-a",
                sources=(StandaloneCognitionSeedSource(slot="primary", source=source),),
                basis="Seed one exact source.",
            )
            same_selection = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:structured-no-progress-b",
                pins=(pin,),
                basis="Reset attempt-local state without selecting new evidence.",
            )
            adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "structured-no-progress-search-1",
                        (
                            tool_call(
                                "tool-call:structured-no-progress-1",
                                "HarnessExecutionBinding",
                            ),
                        ),
                    ),
                    transition_turn("structured-no-progress-reset", same_selection),
                    tool_turn(
                        "structured-no-progress-search-2",
                        (
                            tool_call(
                                "tool-call:structured-no-progress-2",
                                "Runtime",
                            ),
                        ),
                    ),
                )
            )
            adapter.structured_completion_contract_digest = structured_completion_contract_digest(
                COMPLETION
            )
            runner = StandaloneHarnessRunner(
                run_contract,
                continuity,
                adapter,
                bridge,
                budget=RunBudget.from_contract_dict(run_contract.budget),
                clock_ms=clock,
                monotonic_ms=clock,
                cognition_profile=StandaloneCognitionProfile(
                    working_set_transitions=True,
                    caller_ingress_promotions=False,
                    working_set_history=False,
                ),
            )

            execution = runner.run(
                (
                    {
                        "role": "user",
                        "content": "Exercise the bounded observation gate.",
                    },
                ),
                cognition_seed=seed,
            )
            result = execution.loop_result

            self.assertEqual(result.stop_code, RunStopCode.NO_PROGRESS)
            self.assertIsNone(result.conclusion)
            self.assertTrue(execution.paused)
            self.assertIsNone(execution.terminal_result)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(result.tool_calls, 1)
            self.assertEqual(result.model_calls, 3)
            self.assertEqual([len(request.tools) for request in adapter.requests], [1, 0, 0])
            stopped = [event for event in result.trace.events if event.kind == "run_stopped"]
            self.assertEqual(len(stopped), 1)
            self.assertIn(
                "requested another admitted external Tool after the gate closed",
                str(stopped[0].payload.get("detail")),
            )
            self.assertTrue(runner.doctor()["healthy"])
            store.close()


if __name__ == "__main__":
    unittest.main()

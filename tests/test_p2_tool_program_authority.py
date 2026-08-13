from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import AgentTurnResult, ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_repository_repair_bridge import SQLiteHarnessRepositoryRepairRuntimeBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.tool_program import HarnessToolProgram, HarnessToolProgramAction, HarnessToolProgramStep

from tests.test_p1_repository_repair_runtime_bridge import FakeRuntime, bound_state, budget, contract, execution_binding


class ToolProgramAuthorityP2Tests(unittest.TestCase):
    def test_program_cannot_expand_exact_turn_tool_authority(self) -> None:
        runtime = FakeRuntime()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = contract("p2-hidden-program-tool")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=lambda: 1_000)
            bridge = SQLiteHarnessRepositoryRepairRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
            )
            action = HarnessToolProgramAction(
                "program-action:p2:hidden-tool",
                HarnessToolProgram(
                    steps=(HarnessToolProgramStep("hidden", "not_admitted", {}),),
                    outputs={},
                ),
            )
            adapter = ScriptedTurnAdapter(
                (
                    AgentTurnResult(
                        model_call_id="model-call:p2:hidden-tool",
                        model_id=ScriptedTurnAdapter.model_id,
                        content="attempt non-admitted tool",
                        tool_calls=(),
                        conclusion=None,
                        usage={},
                        finish_reason="tool_calls",
                        raw_response_digest=canonical_digest({"hiddenTool": True}),
                        tool_program_action=action,
                    ),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=budget(),
                clock_ms=lambda: 1_000,
                monotonic_ms=lambda: 1_000,
                tool_program_actions=True,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=bound_state().messages,
            )
            self.assertEqual(result.stop_code, RunStopCode.INVALID_MODEL_OUTPUT)
            self.assertEqual(runtime.calls, [])
            store.close()


if __name__ == "__main__":
    unittest.main()

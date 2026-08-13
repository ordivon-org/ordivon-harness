from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.api import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentToolDefinition,
    AgentTurnCapabilities,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_repository_repair_bridge import SQLiteHarnessRepositoryRepairRuntimeBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.tool_program import HarnessToolProgramAction

from tests.test_p1_repository_repair_runtime_bridge import (
    FakeRuntime,
    bound_state,
    budget,
    complete_turn,
    contract,
    execution_binding,
)
from tests.test_deepseek_mixed_turn import SequenceTransport, response
from tests.test_p2_tool_program_runtime_bridge import UnreconciledPatchRuntime, repair_program


class ToolProgramNativeActionP2Tests(unittest.TestCase):
    @staticmethod
    def program_turn(suffix: str) -> AgentTurnResult:
        action = HarnessToolProgramAction(
            action_call_id=f"program-action:p2:{suffix}:1",
            program=repair_program(),
        )
        return AgentTurnResult(
            model_call_id=f"model-call:p2:{suffix}:program",
            model_id=ScriptedTurnAdapter.model_id,
            content="Plan one bounded repository-repair ToolProgram.",
            tool_calls=(),
            conclusion=None,
            usage={"inputTokens": 10, "outputTokens": 5},
            finish_reason="tool_calls",
            raw_response_digest=canonical_digest({"suffix": suffix, "program": action.to_dict()}),
            tool_program_action=action,
        )

    @staticmethod
    def initialize(root: Path, suffix: str, runtime: FakeRuntime):
        run_contract = contract(suffix)
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=lambda: 1_000)
        bridge = SQLiteHarnessRepositoryRepairRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
        )
        return store, run_contract, continuity, bridge

    def test_native_action_round_trip_is_opt_in(self) -> None:
        capabilities = AgentTurnCapabilities(tool_program=True)
        self.assertEqual(AgentTurnCapabilities.from_dict(capabilities.to_dict()), capabilities)
        result = self.program_turn("round-trip")
        self.assertEqual(
            AgentTurnResult.from_dict(result.to_dict()).tool_program_action,
            result.tool_program_action,
        )

    def test_agent_authored_program_uses_two_model_calls_for_five_physical_tools(self) -> None:
        runtime = FakeRuntime()
        with tempfile.TemporaryDirectory() as directory:
            store, run_contract, continuity, bridge = self.initialize(
                Path(directory) / "state", "p2-treatment", runtime
            )
            adapter = ScriptedTurnAdapter(
                (self.program_turn("p2-treatment"), complete_turn("p2-treatment"))
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
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.tool_calls, 5)
            self.assertEqual(
                [name for name, _arguments in runtime.calls],
                ["workspace.read", "workspace.patch", "workspace.exec", "workspace.diff", "workspace.read"],
            )
            self.assertEqual(len(adapter.requests), 2)
            self.assertTrue(adapter.requests[0].capabilities.tool_program)
            self.assertIn("Harness ToolProgram result:", adapter.requests[1].messages[-1]["content"])
            self.assertIn("tool_program_completed", {event.kind for event in result.trace.events})
            store.close()

    def test_unknown_program_effect_stops_before_second_provider_turn(self) -> None:
        runtime = UnreconciledPatchRuntime()
        with tempfile.TemporaryDirectory() as directory:
            store, run_contract, continuity, bridge = self.initialize(
                Path(directory) / "state", "p2-unknown", runtime
            )
            adapter = ScriptedTurnAdapter(
                (self.program_turn("p2-unknown"), complete_turn("p2-unknown"))
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
            self.assertEqual(result.stop_code, RunStopCode.RUNTIME_UNKNOWN)
            self.assertEqual(result.model_calls, 1)
            self.assertEqual(len(adapter.requests), 1)
            self.assertEqual(
                [name for name, _arguments in runtime.calls],
                ["workspace.read", "workspace.patch", "workspace.patch.get"],
            )
            store.close()


    def test_deepseek_exposes_and_decodes_tool_program_control_only_when_admitted(self) -> None:
        tool = AgentToolDefinition(
            name="observe_fact",
            description="Observe one bounded fact.",
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        )
        program_arguments = {
            "steps": [
                {
                    "step_id": "observe",
                    "tool_name": "observe_fact",
                    "arguments": {"key": "x"},
                }
            ],
            "outputs": {
                "value": {
                    "$harnessObservationRef": {
                        "stepId": "observe",
                        "path": ["value"],
                    }
                }
            },
        }
        provider_response = response(
            ("program-call:deepseek", "compose_tool_program", program_arguments)
        )
        transport = SequenceTransport([provider_response])
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=transport,
        )
        request = AgentTurnRequest(
            harness_run_id="harness-run:p2-deepseek",
            turn_id="turn:p2-deepseek:1",
            sequence=1,
            assignment_id="assignment:p2-deepseek",
            context_digest="sha256:" + "a" * 64,
            tool_catalog_digest="sha256:" + "b" * 64,
            messages=({"role": "user", "content": "compose the dependent observation"},),
            tools=(tool,),
            capabilities=AgentTurnCapabilities(tool_program=True),
            remaining_budget={"modelCalls": 2, "toolCalls": 1, "totalTokens": 4096},
        )
        result = adapter.invoke(request)
        assert result.tool_program_action is not None
        self.assertEqual(result.tool_program_action.action_call_id, "program-call:deepseek")
        self.assertEqual(result.tool_program_action.program.steps[0].tool_name, "observe_fact")
        body = transport.requests[0]
        tools = body["tools"]
        names = [item["function"]["name"] for item in tools]
        self.assertIn("compose_tool_program", names)
        program_schema = next(
            item["function"]["parameters"]
            for item in tools
            if item["function"]["name"] == "compose_tool_program"
        )
        self.assertEqual(
            program_schema["properties"]["steps"]["items"]["properties"]["tool_name"]["enum"],
            ["observe_fact"],
        )
        self.assertIn("compose_tool_program", body["messages"][0]["content"])

        disabled = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=SequenceTransport([provider_response]),
        )
        with self.assertRaisesRegex(ValueError, "unavailable ToolProgram control"):
            disabled.invoke(
                AgentTurnRequest(
                    harness_run_id=request.harness_run_id,
                    turn_id=request.turn_id,
                    sequence=request.sequence,
                    assignment_id=request.assignment_id,
                    context_digest=request.context_digest,
                    tool_catalog_digest=request.tool_catalog_digest,
                    messages=request.messages,
                    tools=request.tools,
                    remaining_budget=request.remaining_budget,
                )
            )

    def test_deepseek_can_reproject_retained_program_action_and_compact_result(self) -> None:
        action = self.program_turn("deepseek-history").tool_program_action
        assert action is not None
        adapter = DeepSeekTurnAdapter(DeepSeekSettings(api_key="k" * 40, max_output_tokens=512))
        tool = AgentToolDefinition(
            name="observe_fact",
            description="Observe one bounded fact.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        )
        request = AgentTurnRequest(
            harness_run_id="harness-run:p2-history",
            turn_id="turn:p2-history:2",
            sequence=2,
            assignment_id="assignment:p2-history",
            context_digest="sha256:" + "c" * 64,
            tool_catalog_digest="sha256:" + "d" * 64,
            messages=(
                {
                    "role": "assistant",
                    "content": "planned bounded program",
                    "toolProgramAction": action.to_dict(),
                },
                {
                    "role": "user",
                    "content": "Harness ToolProgram result: {\"status\":\"completed\"}",
                },
            ),
            tools=(tool,),
            remaining_budget={"modelCalls": 1, "toolCalls": 0, "totalTokens": 2048},
        )
        _allowed, _digest, _headers, body = adapter._prepare_request(request)
        import json

        payload = json.loads(body)
        self.assertIn("Retained Harness ToolProgram action:", payload["messages"][1]["content"])
        self.assertIn("Harness ToolProgram result:", payload["messages"][2]["content"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import unittest

from anc_canonical import canonical_bytes

from ordivon_harness.api import DeepSeekSettings, DeepSeekTurnAdapter, RunBudget
from ordivon_harness.domain_tools import (
    AgentToolCall,
    AgentToolDefinition,
    DomainToolCatalog,
    DomainToolLoopPlan,
    DomainToolLoopRunner,
    ToolObservation,
)


TOOL = AgentToolDefinition(
    name="observe_fact",
    description="Observe one harmless test fact.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    },
)
COMPLETION = {
    "mode": "structured-result-v1",
    "resultKind": "mixed-turn-test",
    "resultSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    },
}


class SequenceTransport:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        self.requests.append(json.loads(body))
        if not self.responses:
            raise AssertionError("unexpected Provider call")
        return self.responses.pop(0)


class CountingBridge:
    catalog = DomainToolCatalog(
        domain_id="domain:mixed-turn-test",
        revision="mixed-turn-test-v1",
        tools=(TOOL,),
    )
    bridge_identity = {
        "schemaVersion": 1,
        "kind": "mixed-turn-counting-bridge",
    }

    def __init__(self) -> None:
        self.executions = 0

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        self.executions += 1
        return ToolObservation(
            call.tool_call_id, call.name, "observed", {"value": "physical-observation"}
        )


def response(*calls: tuple[str, str, dict[str, object]]) -> bytes:
    return canonical_bytes(
        {
            "id": "provider-call:" + hashlib.sha256(repr(calls).encode()).hexdigest()[:12],
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments, separators=(",", ":")),
                                },
                            }
                            for call_id, name, arguments in calls
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
    )


class DeepSeekMixedTurnTests(unittest.TestCase):
    def test_adapter_marks_mixed_tool_and_conclusion_as_model_correctable(self) -> None:
        mixed = response(
            ("call:observe", "observe_fact", {"key": "x"}),
            (
                "call:conclude",
                "submit_run_conclusion",
                {
                    "status": "candidate_completed",
                    "result": {"answer": "premature"},
                    "artifact_refs": [],
                    "evidence_refs": [],
                    "unresolved_unknowns": [],
                },
            ),
        )
        transport = SequenceTransport([mixed])
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=transport,
            completion_contract=COMPLETION,
        )
        from ordivon_harness.core import AgentTurnRequest

        result = adapter.invoke(
            AgentTurnRequest(
                harness_run_id="harness-run:mixed-adapter",
                turn_id="turn:mixed-adapter:1",
                sequence=1,
                assignment_id="assignment:mixed-adapter",
                context_digest="sha256:" + "a" * 64,
                tool_catalog_digest="sha256:" + "b" * 64,
                messages=({"role": "user", "content": "test"},),
                tools=(TOOL,),
                remaining_budget={"modelCalls": 2, "toolCalls": 1, "totalTokens": 4096},
            )
        )
        self.assertIsNone(result.conclusion)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].name, "observe_fact")
        self.assertEqual(result.tool_calls[0].argument_error, "mixed_with_conclusion")

    def test_loop_corrects_mixed_turn_without_executing_physical_tool(self) -> None:
        mixed = response(
            ("call:observe", "observe_fact", {"key": "x"}),
            (
                "call:conclude",
                "submit_run_conclusion",
                {
                    "status": "candidate_completed",
                    "result": {"answer": "premature"},
                    "artifact_refs": [],
                    "evidence_refs": [],
                    "unresolved_unknowns": [],
                },
            ),
        )
        corrected = response(
            (
                "call:conclude:corrected",
                "submit_run_conclusion",
                {
                    "status": "candidate_completed",
                    "result": {"answer": "corrected"},
                    "artifact_refs": [],
                    "evidence_refs": [],
                    "unresolved_unknowns": [],
                },
            )
        )
        transport = SequenceTransport([mixed, corrected])
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=transport,
            completion_contract=COMPLETION,
        )
        bridge = CountingBridge()
        result = DomainToolLoopRunner(adapter, bridge).run(
            DomainToolLoopPlan(
                harness_run_id="harness-run:mixed-loop",
                assignment_id="assignment:mixed-loop",
                context_digest="sha256:" + "c" * 64,
                initial_messages=({"role": "user", "content": "choose one action"},),
                allowed_tools=("observe_fact",),
                budget=RunBudget(
                    max_model_calls=3,
                    max_tool_calls=2,
                    max_observation_bytes=32768,
                    max_wall_time_ms=30000,
                    max_total_tokens=8192,
                    max_tool_corrections=2,
                ),
            )
        )
        self.assertEqual(result.stop_code.value, "candidate_completed")
        self.assertEqual(bridge.executions, 0)
        self.assertEqual(result.tool_calls, 1)
        self.assertEqual(result.observations[0].status, "rejected")
        error = result.observations[0].structured_content["error"]
        self.assertEqual(error["kind"], "model_correctable")
        self.assertTrue(error["safeToCorrect"])
        self.assertIsNotNone(result.conclusion)
        assert result.conclusion is not None
        assert result.conclusion.structured_result is not None
        self.assertEqual(
            result.conclusion.structured_result.value,
            {"answer": "corrected"},
        )
        self.assertTrue(result.conclusion.summary.startswith("Structured result sha256:"))
        self.assertEqual(len(transport.requests), 2)


if __name__ == "__main__":
    unittest.main()

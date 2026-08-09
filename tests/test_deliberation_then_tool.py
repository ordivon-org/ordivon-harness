from __future__ import annotations

import unittest

from anc_canonical import canonical_digest

from ordivon_harness.deliberation import DeliberationThenToolRunner
from ordivon_harness.domain_tools import (
    AgentToolDefinition,
    DomainToolCatalog,
    DomainToolLoopPlan,
    ToolObservation,
)
from ordivon_harness.ordivon.loop import RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
)


TOOL = AgentToolDefinition(
    "submit_choice",
    "Record a caller-owned choice without external effect.",
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {"choice": {"type": "string"}},
        "required": ["choice"],
    },
)
CONTEXT = canonical_digest({"context": "h1"})


def conclusion(suffix: str, summary: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:h1-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=(),
        conclusion=AgentRunConclusion("candidate_completed", summary),
        usage={"total_tokens": 10},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"h1": suffix}),
    )


def tool_result(choice: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:h1-tool",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=(
            AgentToolCall("tool-call:h1-choice", "submit_choice", {"choice": choice}),
        ),
        conclusion=None,
        usage={"total_tokens": 10},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"h1": "tool"}),
    )


class Bridge:
    catalog = DomainToolCatalog("domain:h1-test", "1", (TOOL,))
    bridge_identity = {
        "schemaVersion": 1,
        "kind": "h1-test-bridge",
        "externalEffect": False,
    }

    def __init__(self) -> None:
        self.choices: list[str] = []

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        choice = call.arguments["choice"]
        assert isinstance(choice, str)
        self.choices.append(choice)
        return ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="observed",
            structured_content={
                "recorded": True,
                "externalEffect": False,
                "stepId": step_id,
            },
        )


def deliberation_request(*, context: str = CONTEXT, tools=()) -> AgentTurnRequest:
    return AgentTurnRequest(
        harness_run_id="harness-run:h1-deliberation",
        turn_id="turn:h1-deliberation:1",
        sequence=1,
        assignment_id="assignment:h1",
        context_digest=context,
        tool_catalog_digest=canonical_digest({"tools": []}),
        messages=(
            {"role": "system", "content": "Deliberate only."},
            {"role": "user", "content": "Choose carefully."},
        ),
        tools=tools,
        remaining_budget={"modelCalls": 1, "toolCalls": 0, "totalTokens": 1000},
    )


def tool_plan(*, context: str = CONTEXT) -> DomainToolLoopPlan:
    return DomainToolLoopPlan(
        harness_run_id="harness-run:h1-tool",
        assignment_id="assignment:h1",
        context_digest=context,
        initial_messages=(
            {"role": "system", "content": "Use caller-owned Tools."},
            {"role": "user", "content": "Same bounded task."},
        ),
        allowed_tools=("submit_choice",),
        budget=RunBudget(
            max_model_calls=2,
            max_tool_calls=2,
            max_observation_bytes=16384,
            max_wall_time_ms=10000,
            max_total_tokens=10000,
            max_model_retries=0,
            max_tool_corrections=0,
            max_observation_only_turns=0,
            max_no_progress_turns=1,
        ),
    )


class DeliberationThenToolTests(unittest.TestCase):
    def test_composes_no_tool_cognition_with_same_adapter_and_caller_bridge(self) -> None:
        adapter = ScriptedTurnAdapter(
            (
                conclusion("deliberation", "I choose cobalt after checking feasibility."),
                tool_result("cobalt"),
                conclusion("done", "Recorded cobalt."),
            )
        )
        bridge = Bridge()
        execution = DeliberationThenToolRunner(adapter, bridge).run(
            deliberation_request(), tool_plan()
        )

        self.assertEqual(bridge.choices, ["cobalt"])
        self.assertEqual(execution.tool_result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertEqual(len(adapter.requests), 3)
        self.assertEqual(adapter.requests[0].tools, ())
        self.assertEqual(adapter.requests[1].tools[0].name, "submit_choice")
        injected = adapter.requests[1].messages[-1]
        self.assertEqual(injected["role"], "user")
        self.assertIn("PRIOR_NON_AUTHORITATIVE_SELF_DELIBERATION_RECORD", injected["content"])
        self.assertIn("not world truth", injected["content"])
        self.assertIn("not domain Tool intent", injected["content"])
        self.assertEqual(execution.deliberation.context_digest, CONTEXT)
        self.assertEqual(execution.deliberation.adapter_id, adapter.adapter_id)
        self.assertEqual(execution.deliberation.requested_model_id, adapter.model_id)
        self.assertTrue(execution.deliberation.digest.startswith("sha256:"))
        self.assertTrue(execution.execution_digest.startswith("sha256:"))

    def test_rejects_tool_bearing_deliberation_before_provider_dispatch(self) -> None:
        adapter = ScriptedTurnAdapter((conclusion("unused", "unused"),))
        bridge = Bridge()
        with self.assertRaisesRegex(ValueError, "must not expose domain Tools"):
            DeliberationThenToolRunner(adapter, bridge).run(
                deliberation_request(tools=(TOOL,)), tool_plan()
            )
        self.assertEqual(adapter.requests, [])

    def test_rejects_context_mismatch_before_provider_dispatch(self) -> None:
        adapter = ScriptedTurnAdapter((conclusion("unused", "unused"),))
        bridge = Bridge()
        with self.assertRaisesRegex(ValueError, "same Context digest"):
            DeliberationThenToolRunner(adapter, bridge).run(
                deliberation_request(),
                tool_plan(context=canonical_digest({"context": "other"})),
            )
        self.assertEqual(adapter.requests, [])

    def test_rejects_non_completed_deliberation(self) -> None:
        result = AgentTurnResult(
            model_call_id="model-call:h1-needs-input",
            model_id=ScriptedTurnAdapter.model_id,
            content=None,
            tool_calls=(),
            conclusion=AgentRunConclusion("needs_input", "Need more facts."),
            usage={},
            finish_reason="stop",
            raw_response_digest=canonical_digest({"h1": "needs-input"}),
        )
        adapter = ScriptedTurnAdapter((result,))
        with self.assertRaisesRegex(ValueError, "candidate_completed"):
            DeliberationThenToolRunner(adapter, Bridge()).run(
                deliberation_request(), tool_plan()
            )
        self.assertEqual(len(adapter.requests), 1)


if __name__ == "__main__":
    unittest.main()

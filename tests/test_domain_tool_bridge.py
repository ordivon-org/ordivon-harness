from __future__ import annotations

import unittest

from anc_canonical import canonical_digest

from ordivon_harness.domain_tools import (
    AgentRunConclusion,
    AgentToolCall,
    AgentToolDefinition,
    DomainToolCatalog,
    DomainToolLoopPlan,
    DomainToolLoopRunner,
    RunBudget,
    RunStopCode,
    ToolObservation,
)
from ordivon_harness.ordivon import AgentTurnResult, ScriptedTurnAdapter


class _SecurityPlanBridge:
    catalog = DomainToolCatalog(
        domain_id="domain:security-test",
        revision="team-plans-v1",
        tools=(
            AgentToolDefinition(
                "select_team_plan",
                "Select one admitted side-level plan for this Contest tick.",
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "plan": {
                            "type": "string",
                            "enum": ["native-policy", "sleep"],
                        }
                    },
                    "required": ["plan"],
                },
            ),
            AgentToolDefinition(
                "inspect_hidden_truth",
                "Test-only Tool that must not be granted to the Actor.",
                {"type": "object", "additionalProperties": False},
            ),
        ),
    )
    bridge_identity = {
        "bridgeId": "bridge:security-plan-test",
        "revision": "1",
    }

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        self.calls.append((step_id, call.name))
        return ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="observed",
            structured_content={
                "admitted": True,
                "plan": call.arguments["plan"],
            },
        )


def _result(
    suffix: str,
    *,
    calls: tuple[AgentToolCall, ...] = (),
    conclusion: AgentRunConclusion | None = None,
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:domain:{suffix}",
        model_id="ordivon.scripted-model.v1",
        content=None,
        tool_calls=calls,
        conclusion=conclusion,
        usage={"total_tokens": 10},
        finish_reason="tool_calls" if calls else "stop",
        raw_response_digest=canonical_digest({"result": suffix}),
    )


class DomainToolBridgeTests(unittest.TestCase):
    def _plan(self, *, allowed_tools: tuple[str, ...] = ("select_team_plan",)):
        return DomainToolLoopPlan(
            harness_run_id="harness-run:security:test",
            assignment_id="assignment:security:test",
            context_digest=canonical_digest({"context": "actor-specific-observation"}),
            initial_messages=(
                {"role": "system", "content": "Choose one granted plan."},
                {"role": "user", "content": "The current observation is bounded."},
            ),
            allowed_tools=allowed_tools,
            budget=RunBudget(4, 2, 100_000, 60_000),
        )

    def test_generic_domain_bridge_runs_through_harness_loop(self) -> None:
        bridge = _SecurityPlanBridge()
        adapter = ScriptedTurnAdapter(
            (
                _result(
                    "tool",
                    calls=(
                        AgentToolCall(
                            "tool-call:security:1",
                            "select_team_plan",
                            {"plan": "sleep"},
                        ),
                    ),
                ),
                _result(
                    "done",
                    conclusion=AgentRunConclusion(
                        "candidate_completed",
                        "Submitted the admitted side-level plan.",
                    ),
                ),
            )
        )
        runner = DomainToolLoopRunner(adapter, bridge)
        plan = self._plan()

        result = runner.run(plan)

        self.assertIs(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertEqual(result.tool_calls, 1)
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(bridge.calls[0][1], "select_team_plan")
        self.assertEqual(
            tuple(tool.name for tool in adapter.requests[0].tools),
            ("select_team_plan",),
        )
        identity = runner.execution_identity(plan)
        self.assertEqual(identity["domain"]["domainId"], "domain:security-test")
        self.assertEqual(
            identity["provider"]["requestedModelId"],
            "ordivon.scripted-model.v1",
        )

    def test_unknown_granted_tool_is_rejected_before_provider_call(self) -> None:
        bridge = _SecurityPlanBridge()
        adapter = ScriptedTurnAdapter(
            (
                _result(
                    "unused",
                    conclusion=AgentRunConclusion(
                        "candidate_completed",
                        "This result must not be consumed.",
                    ),
                ),
            )
        )
        runner = DomainToolLoopRunner(adapter, bridge)

        with self.assertRaisesRegex(ValueError, "unknown Tools"):
            runner.run(self._plan(allowed_tools=("missing_tool",)))
        self.assertEqual(adapter.requests, [])

    def test_catalog_digest_binds_revision_and_tool_shape(self) -> None:
        first = _SecurityPlanBridge.catalog
        second = DomainToolCatalog(
            domain_id=first.domain_id,
            revision="team-plans-v2",
            tools=first.tools,
        )
        self.assertNotEqual(first.digest, second.digest)
        self.assertNotEqual(
            first.granted_digest(("select_team_plan",)),
            second.granted_digest(("select_team_plan",)),
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from ordivon_harness.api import DELIBERATE_THEN_ACT_LOOP_DRIVER, SEQUENTIAL_LOOP_DRIVER
from ordivon_harness.domain_tools import (
    DomainToolLoopRunner,
    RunStopCode,
    ToolObservation,
)
from ordivon_harness.ordivon.model import AgentRunConclusion, AgentToolCall, ScriptedTurnAdapter
from tests.test_domain_tool_bridge import _SecurityPlanBridge, _result


class _UnknownSecurityBridge(_SecurityPlanBridge):
    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        self.calls.append((step_id, call.name))
        return ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="unknown",
            structured_content={"error": {"type": "response_loss"}},
            runtime_job_ref="job:unknown",
        )


def tool_result(suffix: str):
    return _result(
        suffix,
        calls=(
            AgentToolCall(
                f"tool-call:{suffix}",
                "select_team_plan",
                {"plan": "sleep"},
            ),
        ),
    )


def final_result(suffix: str):
    return _result(
        suffix,
        conclusion=AgentRunConclusion(
            "candidate_completed",
            "Submitted the admitted plan.",
        ),
    )


class E3E4BuiltinMorphologyTests(unittest.TestCase):
    def _plan(self):
        # Reuse the exact tested domain plan shape without coupling production code to test helpers.
        from tests.test_domain_tool_bridge import DomainToolBridgeTests
        return DomainToolBridgeTests()._plan()

    def test_deliberate_then_act_changes_scheduling_not_tool_authority(self) -> None:
        bridge = _SecurityPlanBridge()
        adapter = ScriptedTurnAdapter((
            final_result("deliberate"),
            tool_result("act"),
            final_result("done"),
        ))
        runner = DomainToolLoopRunner(
            adapter,
            bridge,
            loop_driver_ref=DELIBERATE_THEN_ACT_LOOP_DRIVER,
        )
        plan = self._plan()
        result = runner.run(plan)

        self.assertIs(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertEqual(result.model_calls, 3)
        self.assertEqual(result.tool_calls, 1)
        self.assertEqual(len(bridge.calls), 1)
        self.assertEqual(adapter.requests[0].tools, ())
        self.assertEqual(
            tuple(tool.name for tool in adapter.requests[1].tools),
            ("select_team_plan",),
        )
        self.assertEqual(
            runner.execution_identity(plan)["harness"]["schedulingMode"],
            "deliberate_then_act",
        )
        kinds = [event.kind for event in result.trace.events]
        self.assertIn("deliberation_phase_completed", kinds)

    def test_sequential_and_deliberate_share_same_exact_granted_tool_surface(self) -> None:
        plan = self._plan()
        seq_bridge = _SecurityPlanBridge()
        seq_adapter = ScriptedTurnAdapter((tool_result("seq-act"), final_result("seq-done")))
        seq = DomainToolLoopRunner(seq_adapter, seq_bridge).run(plan)

        del_bridge = _SecurityPlanBridge()
        del_adapter = ScriptedTurnAdapter((
            final_result("del-plan"),
            tool_result("del-act"),
            final_result("del-done"),
        ))
        deliberate = DomainToolLoopRunner(
            del_adapter,
            del_bridge,
            loop_driver_ref=DELIBERATE_THEN_ACT_LOOP_DRIVER,
        ).run(plan)

        self.assertIs(seq.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertIs(deliberate.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertEqual(seq.tool_calls, deliberate.tool_calls)
        self.assertEqual(seq_bridge.calls[0][1], del_bridge.calls[0][1])
        self.assertEqual(
            tuple(tool.name for tool in seq_adapter.requests[0].tools),
            tuple(tool.name for tool in del_adapter.requests[1].tools),
        )

    def test_unknown_external_effect_stops_both_morphologies_without_later_provider_turn(self) -> None:
        plan = self._plan()
        for mode, scripted in (
            (SEQUENTIAL_LOOP_DRIVER, (tool_result("seq-unknown"), final_result("must-not-run-a"))),
            (DELIBERATE_THEN_ACT_LOOP_DRIVER, (
                final_result("plan-unknown"),
                tool_result("del-unknown"),
                final_result("must-not-run-b"),
            )),
        ):
            with self.subTest(driver=mode.driver_id):
                bridge = _UnknownSecurityBridge()
                adapter = ScriptedTurnAdapter(scripted)
                result = DomainToolLoopRunner(adapter, bridge, loop_driver_ref=mode).run(plan)
                self.assertIs(result.stop_code, RunStopCode.RUNTIME_UNKNOWN)
                expected_requests = 1 if mode == SEQUENTIAL_LOOP_DRIVER else 2
                self.assertEqual(len(adapter.requests), expected_requests)
                self.assertEqual(len(bridge.calls), 1)

    def test_deliberation_record_is_explicitly_non_authoritative(self) -> None:
        bridge = _SecurityPlanBridge()
        adapter = ScriptedTurnAdapter((
            final_result("record-plan"),
            final_result("record-done"),
        ))
        result = DomainToolLoopRunner(
            adapter, bridge, loop_driver_ref=DELIBERATE_THEN_ACT_LOOP_DRIVER
        ).run(self._plan())
        notes = [
            message.get("content")
            for message in result.messages
            if message.get("role") == "user" and isinstance(message.get("content"), str)
        ]
        self.assertTrue(any("non-authoritative deliberation" in note for note in notes))
        self.assertEqual(result.tool_calls, 0)


if __name__ == "__main__":
    unittest.main()

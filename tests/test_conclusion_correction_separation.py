from __future__ import annotations

from dataclasses import replace
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.tool_errors import ToolBridgeError, ToolBridgeErrorKind


class ConclusionGateBridge:
    catalog_digest = canonical_digest({"surface": "conclusion-only"})

    def __init__(self, rejected_summaries: set[str]) -> None:
        self.rejected_summaries = set(rejected_summaries)
        self.validated: list[str] = []

    def definitions(self):
        return ()

    def execute(self, call, *, step_id: str):
        raise AssertionError(f"no Tool call expected: {call.name} at {step_id}")

    def validate_conclusion(self, conclusion: AgentRunConclusion) -> None:
        self.validated.append(conclusion.summary)
        if conclusion.summary in self.rejected_summaries:
            raise ToolBridgeError(
                "owner admission denied: delegated notional exceeds current authority",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )


def turn(suffix: str, summary: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:conclusion-correction:{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content=f"candidate {suffix}",
        tool_calls=(),
        conclusion=AgentRunConclusion(status="candidate_completed", summary=summary),
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"turn": suffix, "summary": summary}),
    )


def budget(*, conclusion_corrections: int) -> RunBudget:
    return RunBudget(
        max_model_calls=3,
        max_tool_calls=0,
        max_observation_bytes=16_384,
        max_wall_time_ms=10_000,
        max_total_tokens=10_000,
        max_model_retries=0,
        max_tool_corrections=0,
        max_conclusion_corrections=conclusion_corrections,
    )


def run(adapter: ScriptedTurnAdapter, bridge: ConclusionGateBridge, run_budget: RunBudget):
    return OrdivonAgentLoop(adapter, bridge, budget=run_budget).run(
        harness_run_id="harness-run:conclusion-correction-separation",
        assignment_id="assignment:conclusion-correction-separation",
        context_digest=canonical_digest({"context": "conclusion-correction-separation"}),
        initial_messages=({"role": "user", "content": "produce one owner-admissible candidate"},),
    )


class ConclusionCorrectionSeparationTests(unittest.TestCase):
    def test_conclusion_correction_does_not_consume_tool_budget(self) -> None:
        bridge = ConclusionGateBridge({"bad"})
        adapter = ScriptedTurnAdapter((turn("bad", "bad"), turn("good", "good")))

        result = run(adapter, bridge, budget(conclusion_corrections=1))

        self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
        self.assertEqual(
            result.conclusion,
            AgentRunConclusion(status="candidate_completed", summary="good"),
        )
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(result.tool_calls, 0)
        self.assertEqual(result.usage["toolCorrections"], 0)
        self.assertEqual(result.usage["conclusionCorrections"], 1)
        self.assertEqual(result.usage["conclusionCorrectionLimit"], 1)
        self.assertEqual(adapter.requests[1].remaining_budget["toolCorrections"], 0)
        self.assertEqual(adapter.requests[1].remaining_budget["conclusionCorrections"], 0)
        feedback = [
            message["content"]
            for message in result.messages
            if message.get("role") == "user"
            and isinstance(message.get("content"), str)
            and "conclusion gate rejected" in message["content"]
        ]
        self.assertEqual(len(feedback), 1)
        self.assertIn("owner admission denied", feedback[0])
        self.assertNotIn("missing evidence", feedback[0].lower())
        self.assertNotIn("as incomplete", feedback[0].lower())
        rejected = [event for event in result.trace.events if event.kind == "conclusion_rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].payload["conclusionCorrection"], 1)
        self.assertEqual(bridge.validated, ["bad", "good"])

    def test_conclusion_budget_exhaustion_is_independent(self) -> None:
        bridge = ConclusionGateBridge({"bad-a", "bad-b"})
        adapter = ScriptedTurnAdapter((turn("bad-a", "bad-a"), turn("bad-b", "bad-b")))

        result = run(adapter, bridge, budget(conclusion_corrections=1))

        self.assertEqual(result.stop_code, RunStopCode.INVALID_MODEL_OUTPUT)
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(result.tool_calls, 0)
        self.assertEqual(result.usage["toolCorrections"], 0)
        self.assertEqual(result.usage["conclusionCorrections"], 1)
        stopped = [event.payload for event in result.trace.events if event.kind == "run_stopped"]
        self.assertTrue(stopped)
        self.assertIn("Conclusion correction budget exhausted", stopped[-1].get("detail", ""))

    def test_legacy_contract_without_new_field_materializes_default(self) -> None:
        legacy = {
            "maxModelCalls": 2,
            "maxToolCalls": 0,
            "maxWallTimeMs": 10_000,
            "maxToolCorrections": 0,
        }
        materialized = RunBudget.from_contract_dict(legacy)
        self.assertEqual(materialized.max_tool_corrections, 0)
        self.assertEqual(materialized.max_conclusion_corrections, 3)
        materialized.require_contract_match(legacy)
        self.assertEqual(materialized.to_contract_dict()["maxConclusionCorrections"], 3)
        remaining = materialized.remaining(
            model_calls=0,
            tool_calls=0,
            observation_bytes=0,
            elapsed_ms=0,
        )
        self.assertEqual(remaining["toolCorrections"], 0)
        self.assertEqual(remaining["conclusionCorrections"], 3)

    def test_explicit_conclusion_budget_is_contract_authority(self) -> None:
        contract = {
            "maxModelCalls": 2,
            "maxToolCalls": 0,
            "maxWallTimeMs": 10_000,
            "maxConclusionCorrections": 0,
        }
        materialized = RunBudget.from_contract_dict(contract)
        self.assertEqual(materialized.max_conclusion_corrections, 0)
        mismatched = replace(materialized, max_conclusion_corrections=1)
        with self.assertRaisesRegex(ValueError, "maxConclusionCorrections"):
            mismatched.require_contract_match(contract)


if __name__ == "__main__":
    unittest.main()

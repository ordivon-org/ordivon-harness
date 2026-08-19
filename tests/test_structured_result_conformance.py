from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.completion import (
    decode_structured_completion_result,
    encode_structured_completion_result,
    structured_completion_contract_digest,
)
from ordivon_harness.core_contracts import HarnessRunContract
from ordivon_harness.ordivon.loop import RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_agent_bridge import SQLiteHarnessAgentBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.standalone import StandaloneHarnessRunner
from ordivon_harness.structured_result_conformance import (
    LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1,
    validate_structured_result_instance,
)

from tests.test_p0_sqlite_agent_loop import FixedClock, contract as base_contract
from tests.test_p1_procedural_capital import PROCEDURE_RESULT_SCHEMA


POLICY = LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1

CHOICE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "choice": {"type": "string", "enum": ["observe"]},
        "rationale": {"type": "string", "minLength": 1, "maxLength": 80},
    },
    "required": ["choice", "rationale"],
}


def completion(schema=CHOICE_SCHEMA, *, policy: str | None = POLICY):
    value = {
        "mode": "structured-result-v1",
        "resultKind": "conformance-test",
        "resultSchema": schema,
    }
    if policy is not None:
        value["conformancePolicy"] = policy
    return value


def contract(suffix: str, completion_contract) -> HarnessRunContract:
    base = base_contract(f"structured-conformance-{suffix}")
    budget = dict(base.budget)
    budget.update(
        {
            "maxModelCalls": 2,
            "maxToolCalls": 0,
            "maxWallTimeMs": 10_000,
            "maxTotalTokens": 10_000,
            "maxConclusionCorrections": 1,
            "maxToolCorrections": 0,
        }
    )
    return replace(base, completion_contract=completion_contract, budget=budget)


def turn(suffix: str, completion_contract, value) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:structured-conformance-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content=f"candidate {suffix}",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary=encode_structured_completion_result(completion_contract, value),
        ),
        usage={"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"structured-conformance": suffix}),
    )


class CountingDomainGateBridge(SQLiteHarnessAgentBridge):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.validated_summaries: list[str] = []

    def validate_conclusion(self, conclusion: AgentRunConclusion) -> None:
        self.validated_summaries.append(conclusion.summary)


class StructuredResultConformanceTests(unittest.TestCase):
    def test_legacy_policy_absent_remains_unverified_and_decode_compatible(self) -> None:
        legacy = completion(policy=None)
        run_contract = contract("legacy", legacy)
        invalid = {"choice": "observe", "rationale": ""}
        conclusion = turn("legacy", legacy, invalid).conclusion
        assert conclusion is not None
        self.assertEqual(decode_structured_completion_result(run_contract, conclusion), invalid)

    def test_policy_rejects_unknown_profile_and_unsupported_schema_features(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported structured completion conformancePolicy"):
            contract("unknown-policy", completion(policy="other-profile"))
        with self.assertRaisesRegex(ValueError, "unsupported schema keywords"):
            contract(
                "ref",
                completion(
                    {
                        "type": "object",
                        "properties": {"choice": {"$ref": "#/$defs/choice"}},
                    }
                ),
            )
        with self.assertRaisesRegex(ValueError, "additionalProperties.*must be boolean"):
            contract(
                "additional-schema",
                completion(
                    {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    }
                ),
            )
        with self.assertRaisesRegex(ValueError, "requires structured-result-v1"):
            replace(
                base_contract("policy-on-record"),
                completion_contract={"mode": "record", "conformancePolicy": POLICY},
            )

    def test_policy_decode_rejects_f1_style_nested_objects_and_length_overflow(self) -> None:
        f1_schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "problemReformulation": {"type": "string", "maxLength": 8},
                "candidateMechanisms": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 2,
                    "items": {"type": "string", "maxLength": 20},
                },
            },
            "required": ["problemReformulation", "candidateMechanisms"],
        }
        structured = completion(f1_schema)
        run_contract = contract("f1-shape", structured)
        nested = {
            "problemReformulation": "short",
            "candidateMechanisms": [
                {"hypothesis": "embedded", "predictedObservation": "detail"}
            ],
        }
        nested_conclusion = turn("f1-nested", structured, nested).conclusion
        assert nested_conclusion is not None
        with self.assertRaisesRegex(ValueError, "not of type 'string'"):
            decode_structured_completion_result(run_contract, nested_conclusion)

        too_long = {
            "problemReformulation": "123456789",
            "candidateMechanisms": ["mechanism"],
        }
        long_conclusion = turn("f1-long", structured, too_long).conclusion
        assert long_conclusion is not None
        with self.assertRaisesRegex(ValueError, "too long"):
            decode_structured_completion_result(run_contract, long_conclusion)

    def test_policy_rejects_procedural_capital_partial_manual_bypass_shape(self) -> None:
        structured = completion(PROCEDURE_RESULT_SCHEMA)
        invalid = {
            "taskClass": "bounded-repository-repair",
            "procedure": "safe-looking procedure",
            "validityConditions": 42,
            "claimedBenefit": ["wrong-type"],
            "falsifier": {"wrong": "type"},
        }
        with self.assertRaisesRegex(ValueError, "does not conform|violates bound schema"):
            validate_structured_result_instance(structured, invalid)

    def test_policy_rejects_selector_numeric_string_coercion_shape(self) -> None:
        selector_schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "profileId": {"type": "string", "enum": ["profile:partial-evidence"]},
                "maxTotalTokens": {"type": "integer", "minimum": 1, "maximum": 65_536},
                "maxWallTimeMs": {"type": "integer", "minimum": 1, "maximum": 120_000},
                "maxOutputTokens": {"type": "integer", "minimum": 1, "maximum": 8_192},
                "adoptPriorCompletionProposal": {"type": "boolean"},
                "adoptIndependentVerification": {"type": "boolean"},
                "rationale": {"type": "string", "minLength": 1},
            },
            "required": [
                "profileId",
                "maxTotalTokens",
                "maxWallTimeMs",
                "maxOutputTokens",
                "adoptPriorCompletionProposal",
                "adoptIndependentVerification",
                "rationale",
            ],
        }
        invalid = {
            "profileId": "profile:partial-evidence",
            "maxTotalTokens": "16000",
            "maxWallTimeMs": "60000",
            "maxOutputTokens": "1024",
            "adoptPriorCompletionProposal": False,
            "adoptIndependentVerification": False,
            "rationale": "schema-invalid numeric strings",
        }
        with self.assertRaisesRegex(ValueError, "not of type 'integer'"):
            validate_structured_result_instance(completion(selector_schema), invalid)

    def test_mechanical_gate_runs_before_and_preserves_domain_gate(self) -> None:
        completion_contract = completion()
        run_contract = contract("gate-order", completion_contract)
        invalid = {"choice": "observe", "rationale": ""}
        valid = {"choice": "observe", "rationale": "inspect first"}
        adapter = ScriptedTurnAdapter(
            (
                turn("gate-invalid", completion_contract, invalid),
                turn("gate-valid", completion_contract, valid),
            )
        )
        adapter.structured_completion_contract_digest = structured_completion_contract_digest(
            completion_contract
        )
        clock = FixedClock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            bridge = CountingDomainGateBridge(run_contract, continuity)
            runner = StandaloneHarnessRunner(
                run_contract,
                continuity,
                adapter,
                bridge,
                budget=RunBudget.from_contract_dict(run_contract.budget),
                clock_ms=clock,
                monotonic_ms=clock,
            )
            execution = runner.run(
                ({"role": "user", "content": "return one valid structured result"},)
            )
            self.assertEqual(execution.loop_result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(len(bridge.validated_summaries), 1)
            self.assertEqual(
                bridge.validated_summaries[0],
                encode_structured_completion_result(completion_contract, valid),
            )
            store.close()

    def test_runner_rejects_invalid_result_then_accepts_corrected_result(self) -> None:
        completion_contract = completion()
        run_contract = contract("correction", completion_contract)
        invalid = {"choice": "observe", "rationale": ""}
        valid = {"choice": "observe", "rationale": "inspect first"}
        adapter = ScriptedTurnAdapter(
            (
                turn("invalid", completion_contract, invalid),
                turn("corrected", completion_contract, valid),
            )
        )
        adapter.structured_completion_contract_digest = structured_completion_contract_digest(
            completion_contract
        )
        clock = FixedClock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            runner = StandaloneHarnessRunner(
                run_contract,
                continuity,
                adapter,
                bridge,
                budget=RunBudget.from_contract_dict(run_contract.budget),
                clock_ms=clock,
                monotonic_ms=clock,
            )
            execution = runner.run(
                ({"role": "user", "content": "return one valid structured result"},)
            )
            result = execution.loop_result
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.usage["conclusionCorrections"], 1)
            self.assertEqual(len(adapter.requests), 2)
            assert result.conclusion is not None
            self.assertEqual(decode_structured_completion_result(run_contract, result.conclusion), valid)
            rejected = [event for event in result.trace.events if event.kind == "conclusion_rejected"]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0].payload["errorKind"], "model_correctable")
            store.close()


if __name__ == "__main__":
    unittest.main()

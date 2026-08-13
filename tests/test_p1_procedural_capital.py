from __future__ import annotations

from dataclasses import replace
import unittest

from ordivon_harness.completion import (
    decode_structured_completion_result,
    encode_structured_completion_result,
)
from ordivon_harness.core_contracts import STRUCTURED_COMPLETION_MODE
from ordivon_harness.knowledge_topology import (
    HarnessReusableCognitionReference,
    HarnessReusableCognitionSelection,
    compile_reusable_cognition_seed,
    effective_knowledge_topology,
)
from ordivon_harness.ordivon.model import AgentRunConclusion
from ordivon_harness.working_view import HarnessWorkingViewSource

from tests.test_p0_core_contracts import contract
from tests.test_p1_reusable_cognition import StaticResolver


PROCEDURE_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "taskClass": {"type": "string", "minLength": 1},
        "procedure": {"type": "string", "minLength": 1},
        "validityConditions": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "claimedBenefit": {"type": "string", "minLength": 1},
        "falsifier": {"type": "string", "minLength": 1},
    },
    "required": [
        "taskClass",
        "procedure",
        "validityConditions",
        "claimedBenefit",
        "falsifier",
    ],
}


def procedure_candidate_contract(suffix: str):
    return replace(
        contract(),
        harness_run_id=f"harness-run:p1-procedure-{suffix}",
        completion_contract={
            "mode": STRUCTURED_COMPLETION_MODE,
            "resultKind": "procedure-candidate",
            "resultSchema": PROCEDURE_RESULT_SCHEMA,
        },
    )


def candidate_result() -> dict[str, object]:
    return {
        "taskClass": "bounded-repository-repair",
        "procedure": (
            "Inspect exact evidence before mutation; make the minimum admitted change; "
            "run the required checks; reconcile ambiguous effects instead of redispatching."
        ),
        "validityConditions": [
            "the task has an exact bounded mutation surface",
            "required verification checks are independently observable",
        ],
        "claimedBenefit": "reduce repeated unsafe or redundant repair attempts",
        "falsifier": "a held-out repair succeeds less often or creates more ambiguous effects",
    }


def external_promote(
    contract_value,
    conclusion: AgentRunConclusion,
) -> tuple[HarnessWorkingViewSource, HarnessReusableCognitionReference]:
    """Fixture for an external evaluator/promoter, intentionally not Harness code."""

    if conclusion.status != "candidate_completed" or conclusion.unresolved_unknowns:
        raise ValueError("external evaluator refuses unresolved procedure candidate")
    if not conclusion.evidence_refs:
        raise ValueError("external evaluator requires independent procedure evidence")
    result = decode_structured_completion_result(contract_value, conclusion)
    if not isinstance(result, dict):
        raise TypeError("procedure candidate result must be an object")
    procedure = result.get("procedure")
    task_class = result.get("taskClass")
    if not isinstance(procedure, str) or not isinstance(task_class, str):
        raise ValueError("procedure candidate lacks external promotion fields")

    source = HarnessWorkingViewSource(
        logical_ref=f"procedure://{task_class}/promoted-v1",
        logical_generation="procedure-generation:promoted-1",
        messages=(
            {
                "role": "user",
                "content": "PROMOTED PROCEDURE: " + procedure,
            },
        ),
    )
    reference = HarnessReusableCognitionReference(
        role="procedure",
        logical_ref=source.logical_ref,
        logical_generation=source.logical_generation,
        source_digest=source.digest,
    )
    return source, reference


class ProceduralCapitalP1Tests(unittest.TestCase):
    def test_existing_structured_completion_is_sufficient_candidate_outlet(self) -> None:
        run_contract = procedure_candidate_contract("accepted")
        result = candidate_result()
        conclusion = AgentRunConclusion(
            status="candidate_completed",
            summary=encode_structured_completion_result(
                run_contract.completion_contract,
                result,
            ),
            evidence_refs=("evidence:held-out-repair-acceptance",),
        )

        self.assertEqual(
            decode_structured_completion_result(run_contract, conclusion),
            result,
        )
        source, reference = external_promote(run_contract, conclusion)
        seed = compile_reusable_cognition_seed(
            attempt_id="working-attempt:p1-future",
            selections=(
                HarnessReusableCognitionSelection(
                    slot="procedure",
                    reference=reference,
                ),
            ),
            basis="external evaluator promoted one evidence-backed procedure candidate",
            resolver=StaticResolver(source),
        )
        self.assertEqual(seed.sources[0].source, source)
        self.assertEqual(reference.source_digest, source.digest)

    def test_unresolved_candidate_is_not_automatically_promoted(self) -> None:
        run_contract = procedure_candidate_contract("unresolved")
        conclusion = AgentRunConclusion(
            status="candidate_completed",
            summary=encode_structured_completion_result(
                run_contract.completion_contract,
                candidate_result(),
            ),
            evidence_refs=("evidence:partial",),
            unresolved_unknowns=("held-out repair effect remains unknown",),
        )
        with self.assertRaisesRegex(ValueError, "refuses unresolved"):
            external_promote(run_contract, conclusion)

    def test_candidate_without_external_evidence_is_not_promoted(self) -> None:
        run_contract = procedure_candidate_contract("no-evidence")
        conclusion = AgentRunConclusion(
            status="candidate_completed",
            summary=encode_structured_completion_result(
                run_contract.completion_contract,
                candidate_result(),
            ),
        )
        with self.assertRaisesRegex(ValueError, "requires independent procedure evidence"):
            external_promote(run_contract, conclusion)

    def test_topology_assigns_candidate_evaluation_and_promotion_outside_harness(self) -> None:
        topology = effective_knowledge_topology()
        by_id = {layer["layerId"]: layer for layer in topology["layers"]}
        procedure = by_id["procedural-capital"]
        self.assertEqual(procedure["owner"], "external-procedure-owner-and-evaluator")
        self.assertFalse(procedure["harnessSemanticEvaluation"])


if __name__ == "__main__":
    unittest.main()

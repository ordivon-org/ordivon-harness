from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "finance_current_state_application.py"
spec = importlib.util.spec_from_file_location("finance_current_state_application", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def context_result():
    return {
        "stateVersion": "v2",
        "contextId": "ctx-2",
        "goal": {"goalId": "goal:capital"},
        "portfolio": {"portfolioId": "portfolio:primary"},
        "portfolioState": {
            "status": {
                "snapshotRef": "snapshot://2",
                "snapshotObservedAt": "2026-08-23T19:00:00Z",
                "observationHealth": "ok",
                "latestAttempt": {"status": "success"},
                "latestAttemptFailedAfterSnapshot": False,
                "exposureProjectionCurrent": True,
            },
            "latestSnapshot": {
                "totalEquity": {
                    "value": 35.0,
                    "currency": "USD",
                    "basis": "owner-valuation",
                    "sourceField": "totalEq",
                }
            },
            "currentCapitalRationalityEvaluation": {
                "verdict": "clear",
                "hardBlockingReasons": [],
                "attentionItems": [],
            },
        },
        "decisionState": {
            "latestDecision": {"decisionId": "decision:1", "decision": "abstain"},
            "currentEvaluation": {
                "verdict": "needs_revision",
                "proposalEligibility": "not_applicable",
                "researchNeeds": ["review-decision-epoch"],
                "governanceNeeds": [],
            },
        },
        "obligations": [
            {
                "kind": "decision",
                "need": "review-decision-epoch",
                "status": "open",
                "candidateOperationRefs": ["agent-operation://finance.decide"],
            }
        ],
        "agentOperations": [
            {
                "operationId": "finance.observe",
                "operationRef": "agent-operation://finance.observe",
                "semanticRole": "observe",
                "purpose": "observe",
                "authorityModel": "owner-native",
                "effectBoundary": "canonical-state",
                "externalFinancialWritePotential": False,
                "governanceBoundary": False,
            },
            {
                "operationId": "finance.decide",
                "operationRef": "agent-operation://finance.decide",
                "semanticRole": "decide",
                "purpose": "record current capital conclusion",
                "authorityModel": "owner-native",
                "effectBoundary": "canonical-state",
                "externalFinancialWritePotential": False,
                "governanceBoundary": False,
            },
            {
                "operationId": "finance.execute",
                "operationRef": "agent-operation://finance.execute",
                "semanticRole": "execute",
                "purpose": "external effect capable",
                "authorityModel": "owner-native",
                "effectBoundary": "external-capital-capable",
                "externalFinancialWritePotential": True,
                "governanceBoundary": False,
            },
        ],
    }


class FakeComposition:
    def __init__(self, status="completed"):
        self.status = status
        self.domain_calls = []

    def run_finance_workstation_composition(self, client, **kwargs):
        return {
            "schemaVersion": 1,
            "kind": "ordivon.first-interface.finance-workstation-composition-receipt",
            "status": self.status,
            "ownerCalls": [],
            "interactionStages": [],
            "invariants": {
                "environmentMutationAuthorityGranted": False,
                "toolAuthorityExpanded": False,
            },
        }

    @staticmethod
    def _finance_env(state_root, app_python):
        return {"ORDIVON_FINANCE_STATE_ROOT": state_root}

    def _domain_exec(self, client, **kwargs):
        self.domain_calls.append(kwargs)
        return SimpleNamespace(
            envelope={"ok": True, "result": context_result()},
            runtime_job_id="job-current-context",
            runtime_attempt_id="attempt-current-context",
        )


class FinanceCurrentStateApplicationTests(unittest.TestCase):
    def test_projection_exposes_only_obligation_backed_current_affordance(self):
        value = module.compact_current_finance_context(context_result())
        self.assertEqual(value["decision"]["standing"], "abstain")
        self.assertEqual(value["decision"]["verdict"], "needs_revision")
        self.assertEqual(value["portfolioStanding"]["observationHealth"], "ok")
        self.assertEqual(value["portfolioStanding"]["totalEquity"]["value"], 35.0)
        self.assertEqual(
            [item["operationId"] for item in value["currentAffordances"]],
            ["finance.decide"],
        )
        self.assertFalse(value["currentAffordances"][0]["externalFinancialWritePotential"])
        self.assertFalse(value["claims"]["ownerTruthMinted"])

    def test_success_recompiles_after_observation_before_exposing_current_state(self):
        composition = FakeComposition()
        receipt = module.run_finance_current_state_application(
            object(),
            composition,
            finance_workspace_id="finance-ws",
            workstation_workspace_id="workstation-ws",
            finance_state_root="/tmp/state",
            finance_app_python=None,
            request_prefix="ordinary-finance-current-state",
            consumer_episode_ref="consumer-episode:test-finance-current-state",
            consumer_class="test",
        )
        self.assertEqual(receipt["status"], "completed_current_state")
        self.assertEqual(receipt["currentContextRuntimeJobId"], "job-current-context")
        self.assertEqual(receipt["modelView"]["currentState"], receipt["currentState"])
        self.assertTrue(receipt["modelView"]["claims"]["diagnosticCompositionOmitted"])
        self.assertNotIn("researchNeeds", receipt["currentState"]["decision"])
        self.assertEqual(len(composition.domain_calls), 1)
        call = composition.domain_calls[0]
        self.assertEqual(call["operation"], "finance.context.compile")
        self.assertEqual(call["arguments"], {})
        self.assertEqual(
            [item["operationId"] for item in receipt["currentState"]["currentAffordances"]],
            ["finance.decide"],
        )

    def test_blocked_composition_does_not_invent_or_recompile_current_state(self):
        composition = FakeComposition(status="blocked_environment")
        receipt = module.run_finance_current_state_application(
            object(),
            composition,
            finance_workspace_id="finance-ws",
            workstation_workspace_id="workstation-ws",
            finance_state_root="/tmp/state",
            finance_app_python=None,
            request_prefix="ordinary-finance-current-state",
            consumer_episode_ref="consumer-episode:test-finance-current-state",
            consumer_class="test",
        )
        self.assertEqual(receipt["status"], "blocked_environment")
        self.assertIsNone(receipt["currentState"])
        self.assertEqual(composition.domain_calls, [])

    def test_application_foreign_references_are_explicit_and_bounded(self):
        refs = module.application_foreign_references(
            "consumer-episode:test-finance-current-state", "test"
        )
        self.assertEqual(
            {(item["type"], item["id"]) for item in refs},
            {
                ("application", "finance-current-state"),
                ("consumer_class", "test"),
                ("consumer_episode", "consumer-episode:test-finance-current-state"),
            },
        )
        with self.assertRaises(ValueError):
            module.application_foreign_references("consumer-episode:x", "unknown")

    def test_provenance_client_injects_only_workspace_exec(self):
        class Delegate:
            def __init__(self):
                self.calls = []

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                return {"ok": True}

        delegate = Delegate()
        refs = module.application_foreign_references("consumer-episode:x", "audit")
        client = module.ProvenanceRuntimeClient(delegate, refs)
        client.call_tool(
            "workspace.exec",
            {"clientRequestId": "r1", "execution": {"workspaceId": "w"}},
        )
        execution = delegate.calls[0][1]["execution"]
        self.assertEqual(execution["foreignReferences"], sorted(refs, key=lambda item: (item["namespace"], item["type"], item["id"])))
        client.call_tool("artifact.read", {"jobId": "j"})
        self.assertNotIn("foreignReferences", delegate.calls[1][1])


if __name__ == "__main__":
    unittest.main()

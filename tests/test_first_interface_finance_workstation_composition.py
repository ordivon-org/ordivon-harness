from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "first_interface_finance_workstation_composition.py"
)
spec = importlib.util.spec_from_file_location("first_interface_finance_workstation_composition", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def owner(ok: bool, operation: str, *, result=None, error=None, effect=None):
    value = {"ok": ok, "operation": operation}
    if result is not None:
        value["result"] = result
    if error is not None:
        value["error"] = error
    if effect is not None:
        value["effectContract"] = effect
    return value


FINANCE_EFFECT = {
    "effectClass": "CANONICAL_OBSERVATION",
    "externalFinancialWrite": False,
    "financialSubmission": False,
    "authorityMutation": False,
}
WORKSTATION_EFFECT = {
    "effectClass": "READ_ONLY",
    "credentialAccess": "none",
    "environmentMutation": False,
    "externalFinancialWrite": False,
}


class FakeRuntime:
    def __init__(self, envelopes):
        self.envelopes = list(envelopes)
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        envelope = self.envelopes.pop(0)
        index = len(self.calls)
        status = "succeeded" if envelope.get("ok") is not False else "failed"
        return {
            "jobId": f"job-{index}",
            "attemptId": f"attempt-{index}",
            "status": status,
            "semanticCompletionEvaluated": False,
            "stdoutTail": json.dumps(envelope),
        }


def run(fake):
    return module.run_finance_workstation_composition(
        fake,
        finance_workspace_id="finance-ws",
        workstation_workspace_id="workstation-ws",
        finance_state_root="/tmp/finance-state",
        finance_app_python="/tmp/python",
        request_prefix="fixture",
    )


class FinanceWorkstationCompositionTests(unittest.TestCase):
    def test_healthy_path_exposes_only_finance_and_never_observes_or_mutates_workstation(self):
        fake = FakeRuntime(
            [
                owner(True, "finance.context.compile", result={"stateVersion": "v1"}),
                owner(
                    True,
                    "finance.observe",
                    result={"status": "refreshed"},
                    effect=FINANCE_EFFECT,
                ),
            ]
        )
        receipt = run(fake)
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(
            [row[1]["execution"]["args"][3] for row in fake.calls],
            ["finance.context.compile", "finance.observe"],
        )
        self.assertEqual(receipt["interactionStages"][0]["selectedTools"], ["finance_observe"])
        self.assertFalse(receipt["invariants"]["environmentMutationAuthorityGranted"])
        self.assertFalse(receipt["invariants"]["toolAuthorityExpanded"])

    def test_egress_failure_recovers_read_only_then_retries_finance(self):
        fake = FakeRuntime(
            [
                owner(True, "finance.context.compile", result={"stateVersion": "v1"}),
                owner(False, "finance.observe", error={"code": "EGRESS_NOT_CURRENT"}),
                owner(
                    True,
                    "workstation.egress.observe",
                    result={
                        "status": "AVAILABLE",
                        "profileDigest": "sha256:" + "a" * 64,
                        "listenerReachable": True,
                    },
                    effect=WORKSTATION_EFFECT,
                ),
                owner(
                    True,
                    "finance.observe",
                    result={"status": "refreshed"},
                    effect=FINANCE_EFFECT,
                ),
            ]
        )
        receipt = run(fake)
        self.assertEqual(receipt["status"], "completed_after_egress_recovery")
        self.assertEqual(
            [row[1]["execution"]["args"][3] for row in fake.calls],
            [
                "finance.context.compile",
                "finance.observe",
                "workstation.egress.observe",
                "finance.observe",
            ],
        )
        self.assertEqual(
            [stage["selectedTools"] for stage in receipt["interactionStages"]],
            [["finance_observe"], ["workstation_egress_observe"], ["finance_observe"]],
        )
        for stage in receipt["interactionStages"]:
            self.assertNotIn("workstation_egress_pool_ensure", stage["selectedTools"])
            self.assertFalse(stage["toolWorkingSet"]["canExpandAuthority"])


    def test_captured_egress_failure_replays_read_only_recovery_without_refiring_failure(self):
        fake = FakeRuntime(
            [
                owner(
                    True,
                    "workstation.egress.observe",
                    result={
                        "status": "AVAILABLE",
                        "profileDigest": "sha256:" + "d" * 64,
                        "listenerReachable": True,
                    },
                    effect=WORKSTATION_EFFECT,
                ),
                owner(
                    True,
                    "finance.observe",
                    result={"status": "refreshed"},
                    effect=FINANCE_EFFECT,
                ),
            ]
        )
        captured = owner(
            False,
            "finance.observe",
            error={"code": "EGRESS_NOT_CURRENT"},
        )
        receipt = module.run_finance_workstation_composition(
            fake,
            finance_workspace_id="finance-ws",
            workstation_workspace_id="workstation-ws",
            finance_state_root="/tmp/finance-state",
            finance_app_python="/tmp/python",
            request_prefix="captured",
            initial_finance_envelope=captured,
            initial_finance_runtime_job_id="job-captured-finance-failure",
        )
        self.assertEqual(receipt["status"], "completed_after_egress_recovery")
        self.assertEqual(
            [row[1]["execution"]["args"][3] for row in fake.calls],
            ["workstation.egress.observe", "finance.observe"],
        )
        self.assertEqual(
            [stage["selectedTools"] for stage in receipt["interactionStages"]],
            [["workstation_egress_observe"], ["finance_observe"]],
        )
        self.assertEqual(receipt["ownerCalls"][0]["runtimeJobId"], "job-captured-finance-failure")
        self.assertEqual(receipt["ownerCalls"][0]["ownerErrorCode"], "EGRESS_NOT_CURRENT")
        self.assertFalse(receipt["invariants"]["environmentMutationAuthorityGranted"])

    def test_unavailable_egress_stops_without_environment_mutation(self):
        fake = FakeRuntime(
            [
                owner(True, "finance.context.compile", result={"stateVersion": "v1"}),
                owner(False, "finance.observe", error={"code": "EGRESS_NOT_CURRENT"}),
                owner(
                    True,
                    "workstation.egress.observe",
                    result={
                        "status": "UNAVAILABLE",
                        "profileDigest": "sha256:" + "b" * 64,
                        "listenerReachable": False,
                    },
                    effect=WORKSTATION_EFFECT,
                ),
            ]
        )
        receipt = run(fake)
        self.assertEqual(receipt["status"], "blocked_environment")
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual(receipt["interactionStages"][-1]["selectedTools"], [])
        self.assertFalse(receipt["invariants"]["environmentMutationAuthorityGranted"])

    def test_workstation_read_only_contract_is_enforced(self):
        fake = FakeRuntime(
            [
                owner(True, "finance.context.compile", result={"stateVersion": "v1"}),
                owner(False, "finance.observe", error={"code": "EGRESS_NOT_CURRENT"}),
                owner(
                    True,
                    "workstation.egress.observe",
                    result={
                        "status": "AVAILABLE",
                        "profileDigest": "sha256:" + "c" * 64,
                        "listenerReachable": True,
                    },
                    effect={**WORKSTATION_EFFECT, "environmentMutation": True},
                ),
            ]
        )
        with self.assertRaisesRegex(RuntimeError, "environmentMutation"):
            run(fake)


if __name__ == "__main__":
    unittest.main()

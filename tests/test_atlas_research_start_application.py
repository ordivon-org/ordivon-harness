from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "atlas_research_start_application.py"
spec = importlib.util.spec_from_file_location("atlas_research_start_application", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeRuntime:
    def __init__(self, *, candidates: bool = True, invalid_claims: bool = False):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.candidates = candidates
        self.invalid_claims = invalid_claims

    @staticmethod
    def _claims() -> dict[str, Any]:
        return {
            "semanticEquivalenceInferred": False,
            "noveltyStanding": "UNKNOWN_CALLER_MUST_ADJUDICATE",
            "researchAdmissionGranted": False,
            "ownerTruthMinted": False,
        }

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name != "workspace.exec":
            raise AssertionError(f"unexpected Runtime Tool {name}")
        execution = arguments["execution"]
        args = execution["args"]
        phase = "inspect-candidate" if "inspect-candidate" in args else "first-look"
        claims = self._claims()
        if self.invalid_claims and phase == "first-look":
            claims["semanticEquivalenceInferred"] = True
        if phase == "first-look":
            candidates = (
                [
                    {
                        "path": "synthesis/result-value/README.md",
                        "locator": "$file",
                        "sourceClass": "curated-synthesis",
                        "truthRole": "non-authoritative-cross-owner-synthesis",
                        "score": 42,
                        "matchedTerms": ["consumer", "benefit"],
                        "excerpt": "Value != Consumption != RealizedBenefit.",
                    },
                    {
                        "path": "synthesis/other.md",
                        "locator": "$file",
                        "sourceClass": "curated-synthesis",
                        "truthRole": "non-authoritative-cross-owner-synthesis",
                        "score": 20,
                        "matchedTerms": ["research"],
                        "excerpt": "Adjacent research history.",
                    },
                ]
                if self.candidates
                else []
            )
            value = {
                "schemaVersion": 0,
                "kind": "ordivon.atlas-prior-result-first-look-experimental",
                "truthRole": "non-authoritative-prior-result-candidate-projection",
                "query": "result consumer benefit",
                "candidateCount": len(candidates),
                "candidates": candidates,
                "projectionHealth": {"available": False, "currentness": "UNKNOWN", "counts": {}},
                "claims": claims,
            }
        else:
            value = {
                "schemaVersion": 0,
                "kind": "ordivon.atlas-prior-result-candidate-inspection-experimental",
                "truthRole": "non-authoritative-first-look-candidate-content",
                "query": "result consumer benefit",
                "candidate": {
                    "path": "synthesis/result-value/README.md",
                    "locator": "$file",
                    "sourceClass": "curated-synthesis",
                    "truthRole": "non-authoritative-cross-owner-synthesis",
                    "score": 42,
                    "matchedTerms": ["consumer", "benefit"],
                    "excerpt": "Value != Consumption != RealizedBenefit.",
                },
                "contentBytes": 12345,
                "contentDigest": "sha256:" + "a" * 64,
                "content": {
                    "encoding": "text/markdown-sections; charset=utf-8",
                    "projectedBytes": 120,
                    "sections": [
                        {
                            "heading": "Consumption",
                            "text": "## Consumption\n\nValue != Consumption != RealizedBenefit.\n",
                        }
                    ],
                },
                "projectionHealth": {"available": False, "currentness": "UNKNOWN", "counts": {}},
                "claims": self._claims(),
            }
        return {
            "jobId": f"job:{phase}",
            "attemptId": f"attempt:{phase}",
            "status": "succeeded",
            "executionTerminal": True,
            "executionDisposition": "succeeded",
            "deliveryDisposition": "committed",
            "semanticCompletionEvaluated": False,
            "stdoutTail": json.dumps(value),
            "artifacts": [],
        }


class AtlasResearchStartApplicationTests(unittest.TestCase):
    def run_app(self, runtime: FakeRuntime):
        return module.run_atlas_research_start_application(
            runtime,
            atlas_workspace_id="atlas-current",
            query="result consumer benefit",
            limit=8,
            request_prefix="ordinary-atlas-research-start",
            consumer_episode_ref="consumer-episode:atlas-test",
            consumer_class="test",
        )

    def test_first_look_then_inspects_only_rank1_candidate(self):
        runtime = FakeRuntime()
        receipt = self.run_app(runtime)
        self.assertEqual(receipt["status"], "completed_rank1_candidate_inspected")
        self.assertEqual([item[0] for item in runtime.calls], ["workspace.exec", "workspace.exec"])
        first = runtime.calls[0][1]["execution"]
        inspect = runtime.calls[1][1]["execution"]
        self.assertEqual(first["args"], ["-m", "ordivon_atlas.cli", "first-look", "result consumer benefit", "--limit", "8"])
        self.assertEqual(
            inspect["args"],
            [
                "-m",
                "ordivon_atlas.cli",
                "inspect-candidate",
                "result consumer benefit",
                "synthesis/result-value/README.md",
                "$file",
                "--limit",
                "8",
            ],
        )
        self.assertEqual(receipt["inspection"]["selectedBy"], "owner-first-look-rank-1-policy")
        self.assertEqual(receipt["inspection"]["content"]["sections"][0]["heading"], "Consumption")
        view = receipt["modelView"]
        self.assertEqual(view["firstLook"]["topCandidate"]["path"], "synthesis/result-value/README.md")
        self.assertEqual(view["firstLook"]["alternatives"], [{"rank": 2, "path": "synthesis/other.md", "score": 20}])
        self.assertTrue(view["firstLook"]["fullCandidateDetailsRetainedInReceipt"])
        self.assertNotIn("candidate", view["inspection"])
        self.assertNotIn("claims", view["inspection"])
        self.assertNotIn("projectionHealth", view["inspection"])
        self.assertFalse(receipt["modelView"]["claims"]["semanticEquivalenceInferred"])
        self.assertEqual(receipt["modelView"]["claims"]["noveltyStanding"], "UNKNOWN_CALLER_MUST_ADJUDICATE")
        self.assertTrue(receipt["modelView"]["claims"]["requeryFreedomWithdrawnAfterFirstLook"])

    def test_runtime_jobs_are_bound_to_application_provenance_and_phase(self):
        runtime = FakeRuntime()
        self.run_app(runtime)
        for index, expected_phase in enumerate(("first-look", "inspect-candidate")):
            refs = runtime.calls[index][1]["execution"]["foreignReferences"]
            keyed = {(item["type"], item["id"]) for item in refs}
            self.assertIn(("application", "atlas-research-start"), keyed)
            self.assertIn(("consumer_class", "test"), keyed)
            self.assertIn(("consumer_episode", "consumer-episode:atlas-test"), keyed)
            self.assertIn(("application_phase", expected_phase), keyed)
        receipt = self.run_app(FakeRuntime())
        self.assertFalse(receipt["consumerProvenance"]["adoptionProven"])
        self.assertFalse(receipt["consumerProvenance"]["benefitProven"])

    def test_no_candidate_does_not_infer_novelty_or_inspect(self):
        runtime = FakeRuntime(candidates=False)
        receipt = self.run_app(runtime)
        self.assertEqual(receipt["status"], "completed_no_bounded_candidate")
        self.assertEqual(len(runtime.calls), 1)
        self.assertIsNone(receipt["inspection"])
        self.assertIsNone(receipt["modelView"]["firstLook"]["topCandidate"])
        self.assertEqual(receipt["modelView"]["firstLook"]["alternatives"], [])
        self.assertEqual(receipt["modelView"]["claims"]["noveltyStanding"], "UNKNOWN_CALLER_MUST_ADJUDICATE")
        self.assertFalse(receipt["modelView"]["claims"]["researchAdmissionGranted"])

    def test_owner_authority_inflation_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "non-authoritative standing"):
            self.run_app(FakeRuntime(invalid_claims=True))

    def test_invalid_limit_and_consumer_class_fail_before_dispatch(self):
        runtime = FakeRuntime()
        with self.assertRaisesRegex(ValueError, "limit"):
            module.run_atlas_research_start_application(
                runtime,
                atlas_workspace_id="atlas-current",
                query="result consumer benefit",
                limit=0,
                request_prefix="bad",
                consumer_episode_ref="consumer-episode:atlas-test",
                consumer_class="test",
            )
        self.assertEqual(runtime.calls, [])
        with self.assertRaisesRegex(ValueError, "consumer class"):
            module.application_foreign_references(
                "consumer-episode:atlas-test", "unknown", phase="first-look"
            )


if __name__ == "__main__":
    unittest.main()

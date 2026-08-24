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
        if "retrieval-authoring-context" in args:
            phase = "retrieval-authoring-context"
        elif "inspect-candidate" in args:
            phase = "inspect-candidate"
        elif "first-look-many" in args:
            phase = "first-look-many"
        else:
            phase = "first-look"
        claims = self._claims()
        if self.invalid_claims and phase in {"first-look", "first-look-many", "retrieval-authoring-context"}:
            claims["semanticEquivalenceInferred"] = True
        if phase == "retrieval-authoring-context":
            value = {
                "schemaVersion": 0,
                "kind": "ordivon.atlas-retrieval-authoring-context-experimental",
                "truthRole": "mechanical-retrieval-authoring-context-not-query-or-semantic-truth",
                "representationProfile": {
                    "schemaVersion": 0,
                    "kind": "ordivon.atlas-retrieval-representation-profile-experimental",
                    "truthRole": "mechanical-retrieval-environment-profile-not-semantic-truth",
                    "retrieval": {
                        "mode": "lexical-substring-and-path-match",
                        "queryExpansionByAtlas": False,
                        "crossLanguageTranslationByAtlas": False,
                        "semanticSimilarityByAtlas": False,
                        "callerAuthoredQueryVariantsSupported": True,
                        "maxCallerAuthoredQueryVariants": 4,
                    },
                    "curatedSynthesisCorpus": {
                        "markdownFileCount": 115,
                        "dominantObservedScript": "latin",
                        "dominantObservedScriptShareOfLatinPlusCjk": "0.999731238824",
                    },
                    "claims": {
                        **self._claims(),
                        "callerIntentTranslated": False,
                        "queryVariantGenerated": False,
                        "queryVariantsSemanticallyEquivalent": False,
                    },
                },
                "coordinateProfile": {
                    "schemaVersion": 0,
                    "kind": "ordivon.atlas-retrieval-coordinate-profile-experimental",
                    "truthRole": "mechanical-source-grounded-retrieval-coordinates-not-query-translation",
                    "source": {
                        "path": "synthesis/research-process-lineage/SOURCE-INDEX.md",
                        "contentDigest": "sha256:" + "b" * 64,
                    },
                    "selection": {
                        "method": "first-alias-per-retrieval-section-in-source-order",
                        "taskConditioned": False,
                        "semanticRankingPerformed": False,
                    },
                    "coordinates": [
                        {
                            "sectionHeading": "Episode 8 — Theory-to-Engineering Expansion / Contraction / Rejection",
                            "retrievalAlias": "theory to engineering / research-to-engineering bridge / theory does not compile to code",
                        }
                    ],
                    "claims": {
                        **self._claims(),
                        "callerIntentTranslated": False,
                        "queryVariantGenerated": False,
                        "coordinatesSemanticallyEquivalentToIntent": False,
                    },
                },
                "claims": {
                    **claims,
                    "callerIntentTranslated": False,
                    "queryVariantGenerated": False,
                },
            }
        elif phase in {"first-look", "first-look-many"}:
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
            if phase == "first-look-many":
                for index, candidate in enumerate(candidates):
                    candidate["bestVariantIndex"] = 1 if index == 0 else 0
                    candidate["bestVariantRank"] = index + 1
                    candidate["matchedVariantIndexes"] = [0, 1] if index == 0 else [0]
                value = {
                    "schemaVersion": 0,
                    "kind": "ordivon.atlas-prior-result-first-look-many-experimental",
                    "truthRole": "non-authoritative-prior-result-candidate-projection",
                    "queryVariants": [
                        "研究成果未转化工程能力",
                        "research engineering capability consequences",
                    ],
                    "candidateCount": len(candidates),
                    "candidates": candidates,
                    "projectionHealth": {"available": False, "currentness": "UNKNOWN", "counts": {}},
                    "claims": {
                        **claims,
                        "callerIntentTranslated": False,
                        "queryVariantGenerated": False,
                        "queryVariantsSemanticallyEquivalent": False,
                    },
                }
            else:
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
                "query": args[args.index("inspect-candidate") + 1],
                "candidate": {
                    "path": args[args.index("inspect-candidate") + 2],
                    "locator": args[args.index("inspect-candidate") + 3],
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
                    "projectionByteLimit": 8192,
                    "fullContentAvailableViaRawEscape": True,
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
                "--max-projection-bytes",
                "8192",
            ],
        )
        self.assertEqual(receipt["inspection"]["selectedBy"], "owner-first-look-rank-1-policy")
        self.assertEqual(receipt["inspection"]["content"]["sections"][0]["heading"], "Consumption")
        self.assertEqual(receipt["inspection"]["content"]["projectionByteLimit"], 8192)
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

    def test_first_look_stage_preserves_agent_candidate_selection(self):
        runtime = FakeRuntime()
        receipt = module.run_atlas_first_look_stage_application(
            runtime,
            atlas_workspace_id="atlas-current",
            queries=[
                "研究成果未转化工程能力",
                "research engineering capability consequences",
            ],
            limit=4,
            request_prefix="ordinary-atlas-stage",
            consumer_episode_ref="consumer-episode:atlas-stage-test",
            consumer_class="test",
        )
        self.assertEqual(len(runtime.calls), 1)
        self.assertEqual(receipt["status"], "bounded_candidates_available")
        view = receipt["modelView"]
        self.assertEqual(view["nextSemanticAffordance"]["selectionAuthority"], "caller-agent")
        self.assertIn("exact inspection", view["nextSemanticAffordance"]["selectionObjective"])
        self.assertIn("materially change", view["nextSemanticAffordance"]["rankZeroCondition"])
        self.assertTrue(
            view["nextSemanticAffordance"]["nonAuthoritativeRoleDoesNotDisqualifyInspection"]
        )
        self.assertTrue(
            view["nextSemanticAffordance"]["historicalOrProcessRoleDoesNotDisqualifyInspection"]
        )
        self.assertFalse(view["nextSemanticAffordance"]["arbitraryPathAuthority"])
        self.assertFalse(view["nextSemanticAffordance"]["requeryAvailable"])
        self.assertFalse(view["claims"]["candidateSelectedByApplication"])
        self.assertEqual(view["nextSemanticAffordance"]["candidateRanks"], [1, 2])
        self.assertEqual(view["candidates"][0]["bestVariantIndex"], 1)
        self.assertIn("excerpt", view["candidates"][1])

    def test_candidate_inspection_stage_uses_agent_rank_and_owner_best_variant(self):
        runtime = FakeRuntime()
        first = module.run_atlas_first_look_stage_application(
            runtime,
            atlas_workspace_id="atlas-current",
            queries=[
                "研究成果未转化工程能力",
                "research engineering capability consequences",
            ],
            limit=4,
            request_prefix="ordinary-atlas-stage-select",
            consumer_episode_ref="consumer-episode:atlas-stage-select-test",
            consumer_class="test",
        )
        inspected = module.run_atlas_candidate_inspection_stage_application(
            runtime,
            atlas_workspace_id="atlas-current",
            first_look_receipt=first,
            selected_rank=2,
            request_prefix="ordinary-atlas-stage-select",
            consumer_episode_ref="consumer-episode:atlas-stage-select-test",
            consumer_class="test",
        )
        self.assertEqual(len(runtime.calls), 2)
        execution = runtime.calls[1][1]["execution"]
        self.assertEqual(
            execution["args"],
            [
                "-m",
                "ordivon_atlas.cli",
                "inspect-candidate",
                "研究成果未转化工程能力",
                "synthesis/other.md",
                "$file",
                "--limit",
                "32",
                "--max-projection-bytes",
                "8192",
            ],
        )
        self.assertEqual(inspected["selection"]["rank"], 2)
        self.assertEqual(inspected["selection"]["selectedBy"], "caller-agent-bounded-candidate-selection")
        self.assertFalse(inspected["selection"]["arbitraryPathAuthority"])
        self.assertEqual(inspected["inspection"]["content"]["projectionByteLimit"], 8192)
        self.assertFalse(inspected["modelView"]["claims"]["candidateSelectedByApplication"])
        self.assertFalse(inspected["modelView"]["claims"]["arbitraryPathAuthorityGranted"])

    def test_candidate_inspection_stage_rejects_unbounded_rank_before_dispatch(self):
        runtime = FakeRuntime()
        first = module.run_atlas_first_look_stage_application(
            runtime,
            atlas_workspace_id="atlas-current",
            query="result consumer benefit",
            limit=4,
            request_prefix="ordinary-atlas-stage-bad-rank",
            consumer_episode_ref="consumer-episode:atlas-stage-bad-rank",
            consumer_class="test",
        )
        before = len(runtime.calls)
        with self.assertRaisesRegex(ValueError, "outside the bounded first-look set"):
            module.run_atlas_candidate_inspection_stage_application(
                runtime,
                atlas_workspace_id="atlas-current",
                first_look_receipt=first,
                selected_rank=3,
                request_prefix="ordinary-atlas-stage-bad-rank",
                consumer_episode_ref="consumer-episode:atlas-stage-bad-rank",
                consumer_class="test",
            )
        self.assertEqual(len(runtime.calls), before)

    def test_candidate_inspection_rejects_owner_projection_bound_mismatch(self):
        class WrongProjectionBoundRuntime(FakeRuntime):
            def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                result = super().call_tool(name, arguments)
                args = arguments["execution"]["args"] if name == "workspace.exec" else []
                if "inspect-candidate" in args:
                    value = json.loads(result["stdoutTail"])
                    value["content"]["projectionByteLimit"] = 12288
                    result["stdoutTail"] = json.dumps(value)
                return result

        runtime = WrongProjectionBoundRuntime()
        first = module.run_atlas_first_look_stage_application(
            runtime,
            atlas_workspace_id="atlas-current",
            query="result consumer benefit",
            limit=4,
            request_prefix="wrong-projection-bound",
            consumer_episode_ref="consumer-episode:atlas-bound-test",
            consumer_class="test",
        )
        with self.assertRaisesRegex(RuntimeError, "projection bound"):
            module.run_atlas_candidate_inspection_stage_application(
                runtime,
                atlas_workspace_id="atlas-current",
                first_look_receipt=first,
                selected_rank=1,
                request_prefix="wrong-projection-bound",
                consumer_episode_ref="consumer-episode:atlas-bound-test",
                consumer_class="test",
            )

    def test_query_authoring_context_is_one_mechanical_owner_read(self):
        runtime = FakeRuntime()
        receipt = module.run_atlas_query_authoring_context_application(
            runtime,
            atlas_workspace_id="atlas-current",
            request_prefix="ordinary-atlas-authoring",
            consumer_episode_ref="consumer-episode:atlas-authoring-test",
            consumer_class="test",
        )
        self.assertEqual(len(runtime.calls), 1)
        execution = runtime.calls[0][1]["execution"]
        self.assertEqual(
            execution["args"],
            ["-m", "ordivon_atlas.cli", "retrieval-authoring-context"],
        )
        refs = {(item["type"], item["id"]) for item in execution["foreignReferences"]}
        self.assertIn(("application_phase", "retrieval-authoring-context"), refs)
        view = receipt["modelView"]
        self.assertFalse(view["representationProfile"]["retrieval"]["crossLanguageTranslationByAtlas"])
        self.assertFalse(view["representationProfile"]["retrieval"]["semanticSimilarityByAtlas"])
        self.assertFalse(view["coordinateProfile"]["selection"]["taskConditioned"])
        self.assertFalse(view["coordinateProfile"]["selection"]["semanticRankingPerformed"])
        self.assertFalse(view["claims"]["callerIntentTranslated"])
        self.assertFalse(view["claims"]["queryVariantGeneratedByApplication"])
        self.assertFalse(view["claims"]["semanticEquivalenceInferred"])

    def test_batch_first_look_inspects_rank1_with_owner_best_variant(self):
        runtime = FakeRuntime()
        receipt = module.run_atlas_research_start_application(
            runtime,
            atlas_workspace_id="atlas-current",
            queries=[
                "研究成果未转化工程能力",
                "research engineering capability consequences",
            ],
            limit=4,
            request_prefix="ordinary-atlas-batch",
            consumer_episode_ref="consumer-episode:atlas-batch-test",
            consumer_class="test",
        )
        self.assertEqual(len(runtime.calls), 2)
        first = runtime.calls[0][1]["execution"]
        inspect = runtime.calls[1][1]["execution"]
        self.assertEqual(
            first["args"],
            [
                "-m",
                "ordivon_atlas.cli",
                "first-look-many",
                "研究成果未转化工程能力",
                "research engineering capability consequences",
                "--limit",
                "4",
            ],
        )
        self.assertEqual(
            inspect["args"],
            [
                "-m",
                "ordivon_atlas.cli",
                "inspect-candidate",
                "research engineering capability consequences",
                "synthesis/result-value/README.md",
                "$file",
                "--limit",
                "32",
                "--max-projection-bytes",
                "8192",
            ],
        )
        self.assertEqual(receipt["ownerCalls"][0]["phase"], "first-look-many")
        self.assertEqual(receipt["inspection"]["inspectionQuery"], "research engineering capability consequences")
        self.assertEqual(receipt["inspection"]["inspectionLimit"], 32)
        self.assertEqual(
            receipt["modelView"]["firstLook"]["queryVariants"],
            ["研究成果未转化工程能力", "research engineering capability consequences"],
        )
        self.assertFalse(receipt["modelView"]["claims"]["queryVariantsGeneratedByApplication"])
        self.assertFalse(receipt["modelView"]["claims"]["queryVariantsSemanticallyEquivalent"])

    def test_batch_query_variants_are_bounded_and_not_mixed_with_single_query(self):
        runtime = FakeRuntime()
        with self.assertRaisesRegex(ValueError, "either query or queries"):
            module.run_atlas_research_start_application(
                runtime,
                atlas_workspace_id="atlas-current",
                query="one",
                queries=["two"],
                limit=4,
                request_prefix="bad-mixed",
                consumer_episode_ref="consumer-episode:atlas-test",
                consumer_class="test",
            )
        with self.assertRaisesRegex(ValueError, "one to four"):
            module.run_atlas_research_start_application(
                runtime,
                atlas_workspace_id="atlas-current",
                queries=["a", "b", "c", "d", "e"],
                limit=4,
                request_prefix="bad-width",
                consumer_episode_ref="consumer-episode:atlas-test",
                consumer_class="test",
            )
        self.assertEqual(runtime.calls, [])

    def test_nested_authoring_profile_authority_inflation_fails_closed(self):
        class InflatedRuntime(FakeRuntime):
            def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                result = super().call_tool(name, arguments)
                args = arguments["execution"]["args"] if name == "workspace.exec" else []
                if "retrieval-authoring-context" in args:
                    value = json.loads(result["stdoutTail"])
                    value["coordinateProfile"]["claims"]["coordinatesSemanticallyEquivalentToIntent"] = True
                    result["stdoutTail"] = json.dumps(value)
                return result

        with self.assertRaisesRegex(RuntimeError, "exceeded mechanical authority"):
            module.run_atlas_query_authoring_context_application(
                InflatedRuntime(),
                atlas_workspace_id="atlas-current",
                request_prefix="bad-nested-authoring",
                consumer_episode_ref="consumer-episode:atlas-test",
                consumer_class="test",
            )

    def test_authoring_context_authority_inflation_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "non-authoritative standing"):
            module.run_atlas_query_authoring_context_application(
                FakeRuntime(invalid_claims=True),
                atlas_workspace_id="atlas-current",
                request_prefix="bad-authoring",
                consumer_episode_ref="consumer-episode:atlas-test",
                consumer_class="test",
            )

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

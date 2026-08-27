from __future__ import annotations

import unittest

from ordivon_harness.capability_discovery import (
    CapabilityDescriptor,
    CapabilityDiscoveryQuery,
    CapabilityStanding,
    compile_capability_affordances,
    descriptors_from_effective_catalog,
    discover_capabilities,
    inspect_capability,
)
from ordivon_harness.interaction_context import (
    InteractionSourceRef,
    compile_capability_interaction_context,
)
from ordivon_harness.ordivon.model import AgentToolDefinition


def descriptor(
    capability_id: str,
    owner: str,
    action_name: str,
    *,
    summary: str,
    tags: tuple[str, ...] = (),
    action_kind: str = "tool",
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=capability_id,
        owner=owner,
        summary=summary,
        source_ref=f"owner://{owner}/{capability_id}",
        source_version=f"{owner}:revision:7",
        action_kind=action_kind,
        action_name=action_name,
        effect_class="READ_ONLY" if "observe" in action_name else "OWNER_DEFINED",
        tags=tags,
        authority_requirements=("owner admission remains required",),
        currentness_requirements=("current owner standing required",),
    )


def tool(name: str) -> AgentToolDefinition:
    return AgentToolDefinition(
        name=name,
        description=f"{name} fixture",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


class CapabilityDiscoveryTests(unittest.TestCase):
    def test_discovery_is_progressive_and_does_not_grant_authority(self) -> None:
        corpus = (
            descriptor(
                "atlas.prior-result.inspect",
                "ordivon-atlas",
                "atlas_inspect",
                summary="Inspect bounded prior research result candidates.",
                tags=("research", "prior result", "atlas"),
            ),
            descriptor(
                "workstation.egress.observe",
                "ordivon-workstation",
                "workstation_egress_observe",
                summary="Observe current scoped egress health without mutation.",
                tags=("network", "egress", "health"),
            ),
        )
        candidates = discover_capabilities(
            corpus,
            CapabilityDiscoveryQuery(
                "recover stale egress health",
                terms=("egress", "health"),
            ),
        )
        self.assertEqual(
            [item.capability_id for item in candidates.candidates],
            ["workstation.egress.observe"],
        )
        candidate = candidates.candidates[0].to_dict()
        self.assertNotIn("authorityRequirements", candidate)
        self.assertFalse(candidate["claims"]["authorityGranted"])
        self.assertFalse(candidate["claims"]["executionAdmitted"])

        inspection = inspect_capability(corpus, candidates.candidates[0])
        self.assertEqual(inspection["stage"], "inspected")
        self.assertIn("authorityRequirements", inspection["descriptor"])
        self.assertFalse(inspection["claims"]["authorityGranted"])

    def test_descriptor_change_after_discovery_fails_exact_inspection(self) -> None:
        original = descriptor(
            "security.range.inspect",
            "ordivon-security",
            "security_range_inspect",
            summary="Inspect an authorized experiment range.",
            tags=("security", "range"),
        )
        candidates = discover_capabilities(
            (original,),
            CapabilityDiscoveryQuery("inspect security range"),
        )
        changed = descriptor(
            "security.range.inspect",
            "ordivon-security",
            "security_range_inspect",
            summary="Changed descriptor bytes.",
            tags=("security", "range"),
        )
        with self.assertRaisesRegex(ValueError, "changed after candidate discovery"):
            inspect_capability((changed,), candidates.candidates[0])

    def test_explicit_terms_gate_text_admission_against_generic_intent_tokens(self) -> None:
        item = descriptor(
            "generic.capability.inspect",
            "owner",
            "generic_inspect",
            summary="Inspect one generic capability.",
            tags=("capability", "inspect"),
        )
        result = discover_capabilities(
            (item,),
            CapabilityDiscoveryQuery(
                "find capability inspection",
                terms=("zzzxxyy",),
            ),
        )
        self.assertEqual(result.candidates, ())

    def test_retrieval_does_not_make_an_unadmitted_action_invokable(self) -> None:
        item = descriptor(
            "computer.toolchain.inspect",
            "ordivon-computer",
            "computer_toolchain_inspect",
            summary="Inspect current compiler and local toolchain capability.",
            tags=("computer", "toolchain", "compiler"),
        )
        candidates = discover_capabilities(
            (item,),
            CapabilityDiscoveryQuery("inspect compiler toolchain"),
        )
        compiled = compile_capability_affordances(
            candidates,
            (item,),
            (CapabilityStanding(item.capability_id, "AVAILABLE"),),
            admitted_action_names=(),
        )
        affordance = compiled.affordances[0]
        self.assertFalse(affordance.action_admitted)
        self.assertFalse(affordance.can_invoke_now)
        self.assertEqual(compiled.selected_action_names, ())
        self.assertFalse(compiled.to_dict()["claims"]["authorityExpanded"])

    def test_available_and_admitted_is_positive_current_affordance(self) -> None:
        observe = descriptor(
            "workstation.egress.observe",
            "ordivon-workstation",
            "workstation_egress_observe",
            summary="Observe current scoped egress health without mutation.",
            tags=("egress", "health"),
        )
        repair = descriptor(
            "workstation.egress.ensure",
            "ordivon-workstation",
            "workstation_egress_ensure",
            summary="Ensure one scoped egress member using environment mutation authority.",
            tags=("egress", "repair"),
        )
        corpus = (observe, repair)
        candidates = discover_capabilities(
            corpus,
            CapabilityDiscoveryQuery("egress health repair", terms=("egress",)),
        )
        compiled = compile_capability_affordances(
            candidates,
            corpus,
            (
                CapabilityStanding(
                    observe.capability_id,
                    "AVAILABLE",
                    evidence_refs=("workstation://egress/current",),
                ),
                CapabilityStanding(
                    repair.capability_id,
                    "BLOCKED",
                    reasons=("environment mutation authority absent",),
                ),
            ),
            admitted_action_names=(
                "workstation_egress_observe",
                "workstation_egress_ensure",
            ),
        )
        self.assertEqual(compiled.selected_action_names, ("workstation_egress_observe",))
        by_id = {item.candidate.capability_id: item for item in compiled.affordances}
        self.assertTrue(by_id[observe.capability_id].can_invoke_now)
        self.assertFalse(by_id[repair.capability_id].can_invoke_now)

    def test_missing_owner_standing_remains_unknown(self) -> None:
        item = descriptor(
            "security.range.inspect",
            "ordivon-security",
            "security_range_inspect",
            summary="Inspect an authorized experiment range.",
            tags=("security", "range"),
        )
        candidates = discover_capabilities(
            (item,), CapabilityDiscoveryQuery("security range")
        )
        compiled = compile_capability_affordances(
            candidates,
            (item,),
            (),
            admitted_action_names=("security_range_inspect",),
        )
        affordance = compiled.affordances[0]
        self.assertEqual(affordance.standing.standing, "UNKNOWN")
        self.assertFalse(affordance.can_invoke_now)
        self.assertIn("owning authority", affordance.standing.reasons[0])

    def test_large_corpus_is_bounded_without_loading_full_descriptors(self) -> None:
        corpus = tuple(
            descriptor(
                f"owner.capability.{index:04d}",
                "owner",
                f"action_{index:04d}",
                summary=(
                    "Target repository repair inspection."
                    if index in {17, 221, 907}
                    else "Unrelated capability."
                ),
                tags=(("repository", "repair") if index in {17, 221, 907} else ("noise",)),
            )
            for index in range(1000)
        )
        first = discover_capabilities(
            corpus,
            CapabilityDiscoveryQuery(
                "repository repair", terms=("repository", "repair"), max_candidates=2
            ),
        )
        second = discover_capabilities(
            tuple(reversed(corpus)),
            CapabilityDiscoveryQuery(
                "repository repair", terms=("repository", "repair"), max_candidates=2
            ),
        )
        self.assertEqual(first.matched_count, 3)
        self.assertEqual(len(first.candidates), 2)
        self.assertEqual(first.to_dict()["omittedMatchedCount"], 1)
        self.assertEqual(first.digest, second.digest)

    def test_effective_harness_catalog_can_be_searched_without_full_catalog_dump(self) -> None:
        corpus = descriptors_from_effective_catalog()
        result = discover_capabilities(
            corpus,
            CapabilityDiscoveryQuery(
                "search workspace observation",
                terms=("search", "workspace", "observation"),
                max_candidates=4,
            ),
        )
        ids = [candidate.capability_id for candidate in result.candidates]
        self.assertIn(
            "harness.execution.runtime-search.v1.tool.search_workspace",
            ids,
        )
        self.assertLess(result.to_dict()["returnedCount"], len(corpus))

    def test_four_owner_queries_retrieve_different_capability_positions(self) -> None:
        corpus = (
            descriptor(
                "atlas.prior-result.inspect",
                "ordivon-atlas",
                "atlas_prior_result_inspect",
                summary="Inspect bounded prior research candidates before new research.",
                tags=("atlas", "research", "prior result"),
            ),
            descriptor(
                "workstation.egress.observe",
                "ordivon-workstation",
                "workstation_egress_observe",
                summary="Observe current machine egress standing.",
                tags=("workstation", "egress", "machine"),
            ),
            descriptor(
                "security.range.inspect",
                "ordivon-security",
                "security_range_inspect",
                summary="Inspect current authority and experiment range.",
                tags=("security", "authority", "range"),
            ),
            descriptor(
                "computer.toolchain.inspect",
                "ordivon-computer",
                "computer_toolchain_inspect",
                summary="Inspect local software toolchain capability.",
                tags=("computer", "software", "toolchain"),
            ),
        )
        cases = (
            ("prior research atlas", "atlas.prior-result.inspect"),
            ("machine egress workstation", "workstation.egress.observe"),
            ("security authority range", "security.range.inspect"),
            ("computer software toolchain", "computer.toolchain.inspect"),
        )
        for intent, expected in cases:
            with self.subTest(intent=intent):
                result = discover_capabilities(
                    corpus, CapabilityDiscoveryQuery(intent, max_candidates=1)
                )
                self.assertEqual(result.candidates[0].capability_id, expected)

    def test_discovery_to_first_interface_selects_only_current_admitted_tool(self) -> None:
        observe = descriptor(
            "workstation.egress.observe",
            "ordivon-workstation",
            "workstation_egress_observe",
            summary="Observe current egress health.",
            tags=("egress", "health"),
        )
        ensure = descriptor(
            "workstation.egress.ensure",
            "ordivon-workstation",
            "workstation_egress_ensure",
            summary="Repair egress by environment mutation.",
            tags=("egress", "repair"),
        )
        corpus = (observe, ensure)
        candidate_set = discover_capabilities(
            corpus,
            CapabilityDiscoveryQuery("egress health repair", terms=("egress",)),
        )
        materialized = compile_capability_interaction_context(
            intent="recover current egress",
            sources=(
                InteractionSourceRef(
                    "ordivon-workstation",
                    "workstation://egress/state",
                    "profile:7",
                    "CURRENT",
                ),
            ),
            candidate_set=candidate_set,
            descriptors=corpus,
            standings=(
                CapabilityStanding(observe.capability_id, "AVAILABLE"),
                CapabilityStanding(
                    ensure.capability_id,
                    "BLOCKED",
                    reasons=("mutation authority absent",),
                ),
            ),
            admitted_tools=(
                tool("workstation_egress_observe"),
                tool("workstation_egress_ensure"),
            ),
            logical_ref="interaction://workstation/discovery/r1",
            logical_generation="profile:7",
        )
        self.assertEqual(
            materialized.selected_tool_names, ("workstation_egress_observe",)
        )
        text = str(materialized.source.messages[0]["content"])
        self.assertIn("capabilityAffordances", text)
        self.assertIn("mutation authority absent", text)
        self.assertIn("authorityExpanded", text)


if __name__ == "__main__":
    unittest.main()

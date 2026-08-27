#!/usr/bin/env python3
"""Bounded real-owner capability discovery dogfood.

The fixture is a source-fenced capture, not live owner truth. This evaluator asks
only whether Harness can progressively disclose the already-observed owner
capability positions without converting retrieval into authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ordivon_harness.capability_discovery import (
    CapabilityDescriptor,
    CapabilityDiscoveryQuery,
    CapabilityStanding,
    compile_capability_affordances,
    discover_capabilities,
    inspect_capability,
)

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "capability-environment-owner-dogfood-20260827.json"
)


def _descriptor(value: dict[str, Any]) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=str(value["capabilityId"]),
        owner=str(value["owner"]),
        summary=str(value["summary"]),
        source_ref=str(value["sourceRef"]),
        source_version=str(value["sourceVersion"]),
        action_kind=str(value["actionKind"]),
        action_name=str(value["actionName"]),
        effect_class=str(value["effectClass"]),
        tags=tuple(str(item) for item in value.get("tags", [])),
        requirements=tuple(str(item) for item in value.get("requirements", [])),
        authority_requirements=tuple(
            str(item) for item in value.get("authorityRequirements", [])
        ),
        currentness_requirements=tuple(
            str(item) for item in value.get("currentnessRequirements", [])
        ),
        visibility=str(value.get("visibility", "discoverable")),
    )


def evaluate(fixture_path: Path) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text())
    if fixture.get("kind") != "ordivon.harness-capability-environment-owner-dogfood-v1":
        raise ValueError("unexpected owner dogfood fixture kind")
    descriptors = tuple(_descriptor(item) for item in fixture["descriptors"])
    full_payload = json.dumps(
        [descriptor.to_dict() for descriptor in descriptors],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    rows: list[dict[str, Any]] = []
    for case in fixture["queries"]:
        query = CapabilityDiscoveryQuery(
            str(case["intent"]),
            terms=tuple(str(item) for item in case.get("terms", [])),
            max_candidates=3,
        )
        candidates = discover_capabilities(descriptors, query)
        returned = [item.capability_id for item in candidates.candidates]
        expected = str(case["expectedFirst"])
        if not returned or returned[0] != expected:
            raise AssertionError(
                f"{case['intent']!r} expected first {expected}, got {returned}"
            )
        inspection = inspect_capability(descriptors, candidates.candidates[0])
        candidate_bytes = len(
            json.dumps(
                candidates.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
        inspection_bytes = len(
            json.dumps(
                inspection,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
        compiled_without_owner_standing = compile_capability_affordances(
            candidates,
            descriptors,
            (),
            admitted_action_names=(),
        )
        if any(
            item.standing.standing != "UNKNOWN" or item.can_invoke_now
            for item in compiled_without_owner_standing.affordances
        ):
            raise AssertionError("missing owner standing must remain UNKNOWN and non-invokable")
        compiled_available_references = compile_capability_affordances(
            candidates,
            descriptors,
            tuple(
                CapabilityStanding(item.capability_id, "AVAILABLE")
                for item in candidates.candidates
            ),
            admitted_action_names=tuple(
                item.action_name for item in candidates.candidates
            ),
        )
        if any(item.can_invoke_now for item in compiled_available_references.affordances):
            raise AssertionError(
                "reference discovery must not become direct Harness execution authority"
            )
        rows.append(
            {
                "intent": case["intent"],
                "expectedFirst": expected,
                "returned": returned,
                "candidateBytes": candidate_bytes,
                "inspectionBytes": inspection_bytes,
                "fullDescriptorBytes": len(full_payload),
                "candidateToFullRatio": round(candidate_bytes / len(full_payload), 4),
                "authorityExpanded": False,
                "missingStandingPreservedUnknown": True,
            }
        )

    no_match = discover_capabilities(
        descriptors,
        CapabilityDiscoveryQuery(
            "zzzxxyy capability absent control",
            terms=("zzzxxyy",),
            max_candidates=3,
        ),
    )
    if no_match.candidates:
        raise AssertionError("absent capability control unexpectedly returned candidates")

    return {
        "schemaVersion": 1,
        "kind": "ordivon.harness-capability-environment-owner-dogfood-result-v1",
        "fixtureTruthRole": fixture["truthRole"],
        "fixtureObservedDate": fixture["observedDate"],
        "sourceCount": len(fixture["sources"]),
        "descriptorCount": len(descriptors),
        "queryCount": len(rows),
        "fullDescriptorBytes": len(full_payload),
        "queries": rows,
        "negativeControls": {
            "absentQueryReturnsZero": True,
            "missingOwnerStandingRemainsUnknown": True,
            "retrievedReferenceNeverBecomesExecutionAuthority": True,
        },
        "claims": {
            "ownerTruthMinted": False,
            "liveCurrentnessAfterFixtureCutProven": False,
            "semanticRankingQualityProven": False,
            "freshAgentBehaviorImprovementProvenByThisEvaluator": False,
            "mechanicalProgressiveDisclosureSupported": True,
        },
        "status": "passed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.fixture)
    text = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json

from anc_canonical import canonical_digest

import ordivon_harness.api as api


EXPERIMENT = "E5-v2 Shared-Q / Subject-Local Standing Direct Dogfood"


def bound_ref(name: str, kind: str, content: dict | None = None) -> api.HarnessBoundReference:
    payload = content if content is not None else {"e5v2": name, "kind": kind}
    return api.HarnessBoundReference(ref=name, kind=kind, digest=canonical_digest(payload))


def main() -> int:
    owner = bound_ref("owner:runtime:e5v2", "semantic-owner")
    claim_contract = bound_ref(
        "claim-contract:runtime:e5v2:operation-realized",
        "claim-contract",
        {"owner": owner.ref, "proposition": "bounded fake operation realized", "scope": "e5v2"},
    )
    q = api.OperationalClaimRef(
        claim_id="claim:e5v2:shared-operation-realized",
        semantic_owner_ref=owner,
        claim_contract_ref=claim_contract,
        generation=1,
    )
    use_contract = bound_ref(
        "use-contract:e5v2:shared-evaluation",
        "claim-use-contract",
        {"use": "evaluate bounded E5-v2 evidence standing"},
    )

    ea_content = {
        "sourceSubject": "subject:e5v2:a",
        "claimDigest": q.digest,
        "ownerRef": owner.ref,
        "evidence": "bounded owner-grounded supporting fixture evidence",
    }
    ea = api.HarnessBoundReference(
        ref="evidence:e5v2:a:ea",
        kind="owner-grounded-claim-evidence",
        digest=canonical_digest(ea_content),
    )
    ea_supporting = api.OperationalClaimEvidenceRole(ea, "supporting")

    a1 = api.project_operational_claim_standing_view(
        claim=q,
        subject_ref="subject:e5v2:a",
        use_contract_ref=use_contract,
        evidence_roles=(ea_supporting,),
        generation=1,
    )
    b1 = api.project_operational_claim_standing_view(
        claim=q,
        subject_ref="subject:e5v2:b",
        use_contract_ref=use_contract,
        evidence_roles=(),
        generation=1,
    )

    q_digest_before_visibility = q.digest
    a1_digest_before_visibility = a1.digest
    b1_digest_before_visibility = b1.digest

    # Fixture-owned visibility only. EA is addressable by B but is deliberately not
    # supplied to Harness as an admitted evidence role.
    visible_to_b = (ea,)
    b1_after_visibility = api.project_operational_claim_standing_view(
        claim=q,
        subject_ref="subject:e5v2:b",
        use_contract_ref=use_contract,
        evidence_roles=(),
        generation=1,
    )

    # Explicit B admission: now the exact EA reference is supplied with its
    # already-classified local evidential role, producing a later projection.
    b2 = api.project_operational_claim_standing_view(
        claim=q,
        subject_ref="subject:e5v2:b",
        use_contract_ref=use_contract,
        evidence_roles=(ea_supporting,),
        generation=2,
    )

    checks = {
        "sameQForAAndB": a1.claim.digest == b1.claim.digest == b2.claim.digest == q.digest,
        "aSupported": a1.standing == "SUPPORTED",
        "bInitiallyUnderdetermined": b1.standing == "UNDERDETERMINED",
        "visibilityExists": visible_to_b == (ea,),
        "visibilityDoesNotChangeB": (
            b1_after_visibility == b1 and b1_after_visibility.digest == b1_digest_before_visibility
        ),
        "explicitAdmissionSupportsB2": (
            b2.standing == "SUPPORTED"
            and b2.generation == 2
            and [item.reference.ref for item in b2.evidence_roles] == [ea.ref]
        ),
        "qUnchanged": q.digest == q_digest_before_visibility,
        "aUnchanged": a1.digest == a1_digest_before_visibility,
        "oldBPreserved": b1.digest == b1_digest_before_visibility and b1.generation == 1,
        "newBDistinct": b2.digest != b1.digest,
        "noGlobalRegistrySurface": not hasattr(api, "OperationalClaimRegistry"),
    }

    success = all(checks.values())
    result = {
        "schemaVersion": 1,
        "experiment": EXPERIMENT,
        "classification": (
            "E5V2_DIRECT_SUPPORT_IN_SCOPE" if success else "E5V2_DIRECT_FALSIFIER_FOUND"
        ),
        "checks": checks,
        "claim": {"claimId": q.claim_id, "digest": q.digest, "generation": q.generation},
        "views": {
            "a1": {"standing": a1.standing, "generation": a1.generation, "digest": a1.digest},
            "b1": {"standing": b1.standing, "generation": b1.generation, "digest": b1.digest},
            "b1AfterVisibility": {
                "standing": b1_after_visibility.standing,
                "generation": b1_after_visibility.generation,
                "digest": b1_after_visibility.digest,
            },
            "b2": {"standing": b2.standing, "generation": b2.generation, "digest": b2.digest},
        },
        "visibleEvidenceRefs": [item.ref for item in visible_to_b],
        "admittedB2EvidenceRefs": [item.reference.ref for item in b2.evidence_roles],
        "registryUsed": False,
    }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())

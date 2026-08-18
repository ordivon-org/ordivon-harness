from __future__ import annotations

import hashlib
import json

import ordivon_harness.api as api


def digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def ref(name: str, kind: str) -> api.HarnessBoundReference:
    return api.HarnessBoundReference(name, kind, digest({"ref": name, "kind": kind}))


def main() -> int:
    q = api.OperationalClaimRef(
        claim_id="claim:campaign4:rebuttal:q",
        semantic_owner_ref=ref("owner:fixture:campaign4", "semantic-owner"),
        claim_contract_ref=ref("claim-contract:fixture:campaign4:q", "claim-contract"),
        generation=1,
    )
    use = ref("use-contract:campaign4:rebuttal", "claim-use-contract")
    es = ref("evidence:campaign4:support", "owner-grounded-evidence")
    ec = ref("evidence:campaign4:counter", "owner-grounded-evidence")
    ru = ref("unknown:campaign4:required", "required-unknown")
    support = api.OperationalClaimEvidenceRole(es, "supporting")
    counter = api.OperationalClaimEvidenceRole(ec, "counterevidence")
    unknown = api.OperationalClaimEvidenceRole(ru, "required_unknown")

    a1 = api.project_operational_claim_standing_view(
        claim=q, subject_ref="subject:campaign4:a", use_contract_ref=use,
        evidence_roles=(support,), generation=1,
    )
    q0, a10 = q.digest, a1.digest

    visible_counter = (ec,)
    a1_visible = api.project_operational_claim_standing_view(
        claim=q, subject_ref="subject:campaign4:a", use_contract_ref=use,
        evidence_roles=(support,), generation=1,
    )

    a2 = api.project_operational_claim_standing_view(
        claim=q, subject_ref="subject:campaign4:a", use_contract_ref=use,
        evidence_roles=(support, counter), generation=2,
    )
    b1 = api.project_operational_claim_standing_view(
        claim=q, subject_ref="subject:campaign4:b", use_contract_ref=use,
        evidence_roles=(counter,), generation=1,
    )
    c1 = api.project_operational_claim_standing_view(
        claim=q, subject_ref="subject:campaign4:c", use_contract_ref=use,
        evidence_roles=(support, unknown), generation=1,
    )

    alias_failed_closed = False
    try:
        same = ref("evidence:campaign4:same-ref", "owner-grounded-evidence")
        api.project_operational_claim_standing_view(
            claim=q, subject_ref="subject:campaign4:alias", use_contract_ref=use,
            evidence_roles=(
                api.OperationalClaimEvidenceRole(same, "supporting"),
                api.OperationalClaimEvidenceRole(same, "counterevidence"),
            ),
            generation=1,
        )
    except ValueError:
        alias_failed_closed = True

    q_fields = set(q.to_dict())
    forbidden_global_fields = {"standing", "status", "truth", "contested"}
    checks = {
        "RBD1_initialSupport": a1.standing == "SUPPORTED",
        "RBD2_visibilityExists": visible_counter == (ec,),
        "RBD2_visibilityNoAdmissionNoChange": a1_visible == a1 and a1_visible.digest == a10,
        "RBD3_explicitRebuttalConflict": (
            a2.standing == "CONFLICTED"
            and [x.reference.ref for x in a2.evidence_roles] == [es.ref, ec.ref]
        ),
        "RBD4_qUnchanged": q.digest == q0,
        "RBD4_priorSupportViewUnchanged": a1.digest == a10 and a1.generation == 1,
        "RBD4_newGenerationDistinct": a2.generation == 2 and a2.digest != a1.digest,
        "RBD4_evidenceRefsPreserved": (
            a1.evidence_roles[0].reference == es
            and a2.evidence_roles[0].reference == es
            and a2.evidence_roles[1].reference == ec
        ),
        "RBD5_counterOnlyContradicted": b1.standing == "CONTRADICTED" and b1.claim.digest == q.digest,
        "RBD6_requiredUnknownFirstClass": c1.standing == "UNDERDETERMINED",
        "RBD7_noGlobalClaimStateFields": not (q_fields & forbidden_global_fields),
        "RBD7_noRegistrySurface": not hasattr(api, "OperationalClaimRegistry"),
        "RBD8_sameRefAliasFailsClosed": alias_failed_closed,
    }
    success = all(checks.values())
    result = {
        "schemaVersion": 1,
        "experiment": "Campaign-4 Counterevidence / Rebuttal Direct Dogfood v1",
        "classification": "CAMPAIGN4_REBUTTAL_DIRECT_SUPPORT_IN_SCOPE" if success else "REBUTTAL_DIRECT_FALSIFIER_FOUND",
        "checks": checks,
        "claim": {"id": q.claim_id, "digest": q.digest, "generation": q.generation},
        "views": {
            "A1": {"standing": a1.standing, "generation": a1.generation, "digest": a1.digest},
            "A1AfterVisibility": {"standing": a1_visible.standing, "generation": a1_visible.generation, "digest": a1_visible.digest},
            "A2": {"standing": a2.standing, "generation": a2.generation, "digest": a2.digest},
            "B1": {"standing": b1.standing, "generation": b1.generation, "digest": b1.digest},
            "C1": {"standing": c1.standing, "generation": c1.generation, "digest": c1.digest},
        },
        "visibleCounterevidenceRefs": [x.ref for x in visible_counter],
        "registryUsed": False,
        "productionPatchRequired": False,
    }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from anc_canonical import canonical_digest
from ordivon_harness.api import (
    HarnessBoundReference,
    OperationalClaimEvidenceRole,
    OperationalClaimRef,
    project_operational_claim_standing_view,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha(value: Any) -> str:
    digest = canonical_digest(value)
    require(digest.startswith("sha256:") and len(digest) == 71, "invalid canonical digest")
    return digest


def evidence_ref(name: str, owner_facts: dict[str, Any]) -> HarnessBoundReference:
    return HarnessBoundReference(
        ref=f"runtime-owner-evidence:c3-rich:{name}",
        kind="runtime-owner-fact-capture",
        digest=sha(owner_facts),
    )


def contract_ref(name: str, value: dict[str, Any]) -> HarnessBoundReference:
    return HarnessBoundReference(
        ref=f"claim-contract:c3-rich:{name}",
        kind="claim-contract",
        digest=sha(value),
    )


def claim(name: str, owner: HarnessBoundReference, contract: HarnessBoundReference) -> OperationalClaimRef:
    return OperationalClaimRef(
        claim_id=f"claim:c3-rich:{name}",
        semantic_owner_ref=owner,
        claim_contract_ref=contract,
        generation=1,
    )


def role(ref: HarnessBoundReference, role_name: str) -> OperationalClaimEvidenceRole:
    return OperationalClaimEvidenceRole(reference=ref, role=role_name)


def view(*, q: OperationalClaimRef, subject: str, use: HarnessBoundReference, roles: tuple[OperationalClaimEvidenceRole, ...], generation: int):
    return project_operational_claim_standing_view(
        claim=q,
        subject_ref=subject,
        use_contract_ref=use,
        evidence_roles=roles,
        generation=generation,
    )


def main(path: str) -> int:
    capture = json.loads(Path(path).read_text(encoding="utf-8"))
    require(capture.get("schemaVersion") == 1, "capture schemaVersion differs")
    require(capture.get("kind") == "ordivon.harness.campaign3-rich-effect-owner-v1", "capture kind differs")

    owner = HarnessBoundReference(
        ref="owner:ordivon-runtime:c3-rich-effect-dogfood-v1",
        kind="semantic-owner",
        digest=sha({"owner": "Ordivon Runtime", "scope": "mechanical execution/workspace facts"}),
    )
    use = HarnessBoundReference(
        ref="use-contract:c3-rich-effect-owner-dogfood-v1",
        kind="claim-use-contract",
        digest=sha({"use": "Campaign-3 bounded direct rich-effect dogfood v1"}),
    )

    outputs: dict[str, Any] = {}

    # RED1 — partial multi-step realization from concrete Runtime fields.
    red1 = capture["red1Partial"]
    require(red1["terminalStatus"] == "failed", "RED1 overall Runtime Job must fail")
    require(red1["completedSteps"] == 1, "RED1 must have exactly one completed step")
    require(red1["failedStepId"] == "effect-2", "RED1 must fail at effect-2")
    require(red1["step1Content"] == "step1\n", "RED1 step-1 bytes differ")
    require(red1["step1Digest"].startswith("sha256:"), "RED1 step-1 digest missing")
    e1 = evidence_ref("red1", red1)
    q_prefix = claim("partial-prefix-realized", owner, contract_ref("partial-prefix", {"claim": "effect-1 exact file mutation realized"}))
    q_whole = claim("partial-whole-plan-succeeded", owner, contract_ref("partial-whole", {"claim": "both planned Runtime steps completed successfully"}))
    v_prefix = view(q=q_prefix, subject="runtime-job:" + red1["jobId"], use=use, roles=(role(e1, "supporting"),), generation=1)
    v_whole = view(q=q_whole, subject="runtime-job:" + red1["jobId"], use=use, roles=(role(e1, "counterevidence"),), generation=1)
    require(v_prefix.standing == "SUPPORTED", "RED1 prefix standing differs")
    require(v_whole.standing == "CONTRADICTED", "RED1 whole standing differs")
    outputs["red1"] = {"prefix": v_prefix.to_dict(), "whole": v_whole.to_dict()}

    # RED2 — earlier uncertainty, later support, immutable prior view.
    red2 = capture["red2Delayed"]
    require(red2["preStatus"] in {"working", "accepted"}, "RED2 pre-boundary Runtime status is not nonterminal")
    require(red2["preDeliveryDisposition"] == "in_progress", "RED2 pre-boundary delivery is not in_progress")
    require(red2["prePathAbsent"] is True, "RED2 target must be absent at pre-boundary observation")
    require(red2["terminalStatus"] == "succeeded", "RED2 Runtime Job must later succeed")
    require(red2["postContent"] == "arrived-v1\n", "RED2 final output bytes differ")
    require(red2["postDigest"].startswith("sha256:"), "RED2 final digest missing")
    pre_facts = {"jobId": red2["jobId"], "status": red2["preStatus"], "deliveryDisposition": red2["preDeliveryDisposition"], "pathAbsent": red2["prePathAbsent"]}
    post_facts = {"jobId": red2["jobId"], "status": red2["terminalStatus"], "content": red2["postContent"], "digest": red2["postDigest"], "terminalEvidenceDigest": red2["terminalEvidenceDigest"]}
    e2_pre = evidence_ref("red2-pre", pre_facts)
    e2_post = evidence_ref("red2-post", post_facts)
    q_delayed = claim("delayed-output-realized", owner, contract_ref("delayed-output", {"claim": "named delayed output file realized"}))
    v2_pre = view(q=q_delayed, subject="runtime-job:" + red2["jobId"], use=use, roles=(role(e2_pre, "required_unknown"),), generation=1)
    pre_digest = v2_pre.digest
    v2_post = view(q=q_delayed, subject="runtime-job:" + red2["jobId"], use=use, roles=(role(e2_post, "supporting"),), generation=2)
    require(v2_pre.standing == "UNDERDETERMINED", "RED2 pre standing differs")
    require(v2_post.standing == "SUPPORTED", "RED2 post standing differs")
    require(v2_pre.digest == pre_digest, "RED2 prior StandingView mutated")
    outputs["red2"] = {"pre": v2_pre.to_dict(), "post": v2_post.to_dict(), "preDigestStable": True}

    # RED3 — exact CAS/currentness conflict, no generic causal inference.
    red3 = capture["red3Interference"]
    require(red3["initialContent"] == "A\n", "RED3 initial bytes differ")
    require(red3["m1State"] == "committed", "RED3 M1 must commit")
    require(red3["afterM1Content"] == "B\n", "RED3 M1 current bytes differ")
    require(red3["staleRejected"] is True, "RED3 M2 stale mutation must be rejected")
    require(red3["staleErrorCode"] == "REVISION_MISMATCH", "RED3 stale rejection code differs")
    require(red3["staleCommitState"] == "not_committed", "RED3 stale mutation must be not_committed")
    require(red3["afterM2Content"] == "B\n", "RED3 stale rejection changed current bytes")
    e3_m1 = evidence_ref("red3-m1", {k: red3[k] for k in ("m1ClientRequestId", "m1State", "m1RequestDigest", "m1AfterDigest", "afterM1Content")})
    e3_m2 = evidence_ref("red3-m2", {k: red3[k] for k in ("m2ClientRequestId", "staleRejected", "staleErrorCode", "staleCommitState", "afterM2Content")})
    q_m1 = claim("interference-m1-committed", owner, contract_ref("interference-m1", {"claim": "M1 A-to-B mutation committed"}))
    q_m2 = claim("interference-m2-committed", owner, contract_ref("interference-m2", {"claim": "M2 stale A-to-C mutation committed"}))
    v3_m1 = view(q=q_m1, subject=red3["workspaceId"], use=use, roles=(role(e3_m1, "supporting"),), generation=1)
    v3_m2 = view(q=q_m2, subject=red3["workspaceId"], use=use, roles=(role(e3_m2, "counterevidence"),), generation=1)
    require(v3_m1.standing == "SUPPORTED", "RED3 M1 standing differs")
    require(v3_m2.standing == "CONTRADICTED", "RED3 M2 standing differs")
    outputs["red3"] = {"m1": v3_m1.to_dict(), "m2": v3_m2.to_dict()}

    # RED4 — restoration/current-state claim coexists with original operation history.
    red4 = capture["red4Compensation"]
    require(red4["m3State"] == "committed", "RED4 M3 must commit")
    require(red4["finalContent"] == "A\n", "RED4 final bytes must restore A")
    require(red4["finalDigest"] == red4["originalDigest"], "RED4 final digest must equal original digest")
    require(red4["m1ReceiptStillState"] == "committed", "RED4 prior M1 receipt must remain committed")
    require(red4["m1OperationId"] != red4["m3OperationId"], "RED4 M1/M3 operation identities must remain distinct")
    e4_original = evidence_ref("red4-original", {"operationId": red4["m1OperationId"], "state": red4["m1ReceiptStillState"], "requestDigest": red4["m1RequestDigest"]})
    e4_restored = evidence_ref("red4-restored", {"operationId": red4["m3OperationId"], "state": red4["m3State"], "finalContent": red4["finalContent"], "finalDigest": red4["finalDigest"], "originalDigest": red4["originalDigest"]})
    q_original = claim("original-a-to-b-realized", owner, contract_ref("original-a-to-b", {"claim": "original M1 A-to-B mutation realized"}))
    q_restored = claim("current-state-restored-a", owner, contract_ref("current-restored-a", {"claim": "current file state is A after M3 restoration"}))
    v4_original = view(q=q_original, subject=red4["workspaceId"], use=use, roles=(role(e4_original, "supporting"),), generation=1)
    original_view_digest = v4_original.digest
    v4_restored = view(q=q_restored, subject=red4["workspaceId"], use=use, roles=(role(e4_restored, "supporting"),), generation=1)
    require(v4_original.standing == "SUPPORTED" and v4_restored.standing == "SUPPORTED", "RED4 simultaneous support differs")
    require(v4_original.digest == original_view_digest, "RED4 original StandingView mutated")
    outputs["red4"] = {"original": v4_original.to_dict(), "restored": v4_restored.to_dict(), "originalViewDigestStable": True}

    result = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.campaign3-rich-effect-owner-v1-result",
        "classification": "CAMPAIGN3_RICH_EFFECT_DIRECT_SUPPORT_IN_SCOPE",
        "captureDigest": sha(capture),
        "gates": {
            "partialMixedClaimStanding": True,
            "noScalarPartialStatus": True,
            "delayedUnderdeterminedThenSupported": True,
            "priorDelayedViewImmutable": True,
            "staleCompetingMutationContradicted": True,
            "compensationRestoresCurrentBytes": True,
            "priorCommittedOperationHistoryPreserved": True,
            "sameFinalBytesDoNotCollapseHistory": True,
            "claimStandingProductionModificationRequired": False,
            "globalClaimOrEffectRegistryRequired": False,
        },
        "views": outputs,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: campaign3_rich_effect_owner_v1.py <capture.json>")
    raise SystemExit(main(sys.argv[1]))

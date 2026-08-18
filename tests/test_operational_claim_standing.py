from __future__ import annotations

from dataclasses import fields
import unittest

from anc_canonical import canonical_digest

import ordivon_harness.api as api
from ordivon_harness.claim_standing import (
    OperationalClaimEvidenceRole,
    OperationalClaimRef,
    OperationalClaimStandingView,
    project_operational_claim_standing_view,
)
from ordivon_harness.core_contracts import HarnessBoundReference


def ref(name: str, kind: str) -> HarnessBoundReference:
    return HarnessBoundReference(
        ref=name,
        kind=kind,
        digest=canonical_digest({"operationalClaimStandingTest": name, "kind": kind}),
    )


def claim() -> OperationalClaimRef:
    return OperationalClaimRef(
        claim_id="claim:test:deployment-realized",
        semantic_owner_ref=ref("owner:runtime:test", "semantic-owner"),
        claim_contract_ref=ref("claim-contract:runtime:test:deployment", "claim-contract"),
        generation=1,
    )


def use() -> HarnessBoundReference:
    return ref("use-contract:test:recovery", "claim-use-contract")


class OperationalClaimStandingTests(unittest.TestCase):
    def test_u1_claim_ref_round_trip_and_digest_are_stable(self) -> None:
        value = claim()
        decoded = OperationalClaimRef.from_dict(value.to_dict())
        self.assertEqual(decoded, value)
        self.assertEqual(decoded.digest, value.digest)

    def test_u2_claim_ref_rejects_invalid_identity_bound_refs_and_generation(self) -> None:
        with self.assertRaisesRegex(ValueError, "must start with claim"):
            OperationalClaimRef("not-a-claim", ref("owner:x", "owner"), ref("contract:x", "contract"), 1)
        with self.assertRaises(TypeError):
            OperationalClaimRef("claim:x", object(), ref("contract:x", "contract"), 1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            OperationalClaimRef("claim:x", ref("owner:x", "owner"), object(), 1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "positive integer"):
            OperationalClaimRef("claim:x", ref("owner:x", "owner"), ref("contract:x", "contract"), 0)

    def test_u3_evidence_role_round_trip_and_role_validation(self) -> None:
        value = OperationalClaimEvidenceRole(ref("evidence:s", "receipt"), "supporting")
        self.assertEqual(OperationalClaimEvidenceRole.from_dict(value.to_dict()), value)
        with self.assertRaisesRegex(ValueError, "unsupported Operational Claim evidence role"):
            OperationalClaimEvidenceRole(ref("evidence:x", "receipt"), "truth")

    def test_u4_standing_view_round_trip_and_digest_are_stable(self) -> None:
        evidence = (OperationalClaimEvidenceRole(ref("evidence:s", "receipt"), "supporting"),)
        value = project_operational_claim_standing_view(
            claim=claim(),
            subject_ref="subject:test:a",
            use_contract_ref=use(),
            evidence_roles=evidence,
            generation=1,
        )
        decoded = OperationalClaimStandingView.from_dict(value.to_dict())
        self.assertEqual(decoded, value)
        self.assertEqual(decoded.digest, value.digest)

    def test_u5_duplicate_or_cross_role_evidence_ref_is_rejected(self) -> None:
        same = ref("evidence:same", "receipt")
        with self.assertRaisesRegex(ValueError, "evidence references must be unique"):
            OperationalClaimStandingView(
                claim=claim(),
                subject_ref="subject:test:a",
                use_contract_ref=use(),
                evidence_roles=(
                    OperationalClaimEvidenceRole(same, "supporting"),
                    OperationalClaimEvidenceRole(same, "counterevidence"),
                ),
                standing="CONFLICTED",
                generation=1,
            )

    def test_u6_empty_basis_is_underdetermined(self) -> None:
        value = project_operational_claim_standing_view(
            claim=claim(), subject_ref="subject:test:a", use_contract_ref=use(), generation=1
        )
        self.assertEqual(value.standing, "UNDERDETERMINED")

    def test_u7_supporting_only_is_supported(self) -> None:
        value = project_operational_claim_standing_view(
            claim=claim(),
            subject_ref="subject:test:a",
            use_contract_ref=use(),
            evidence_roles=(OperationalClaimEvidenceRole(ref("evidence:s", "receipt"), "supporting"),),
            generation=1,
        )
        self.assertEqual(value.standing, "SUPPORTED")

    def test_u8_counter_only_is_contradicted(self) -> None:
        value = project_operational_claim_standing_view(
            claim=claim(),
            subject_ref="subject:test:a",
            use_contract_ref=use(),
            evidence_roles=(OperationalClaimEvidenceRole(ref("evidence:c", "receipt"), "counterevidence"),),
            generation=1,
        )
        self.assertEqual(value.standing, "CONTRADICTED")

    def test_u9_support_and_counter_are_conflicted(self) -> None:
        value = project_operational_claim_standing_view(
            claim=claim(),
            subject_ref="subject:test:a",
            use_contract_ref=use(),
            evidence_roles=(
                OperationalClaimEvidenceRole(ref("evidence:s", "receipt"), "supporting"),
                OperationalClaimEvidenceRole(ref("evidence:c", "receipt"), "counterevidence"),
            ),
            generation=1,
        )
        self.assertEqual(value.standing, "CONFLICTED")

    def test_u10_required_unknown_dominates(self) -> None:
        value = project_operational_claim_standing_view(
            claim=claim(),
            subject_ref="subject:test:a",
            use_contract_ref=use(),
            evidence_roles=(
                OperationalClaimEvidenceRole(ref("evidence:s", "receipt"), "supporting"),
                OperationalClaimEvidenceRole(ref("unknown:x", "required-unknown"), "required_unknown"),
            ),
            generation=1,
        )
        self.assertEqual(value.standing, "UNDERDETERMINED")

    def test_u11_inconsistent_supplied_standing_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "differs from evidence-role projection"):
            OperationalClaimStandingView(
                claim=claim(),
                subject_ref="subject:test:a",
                use_contract_ref=use(),
                evidence_roles=(),
                standing="SUPPORTED",
                generation=1,
            )

    def test_u12_claim_ref_has_no_subject_status_evidence_or_registry_field(self) -> None:
        self.assertEqual(
            [item.name for item in fields(OperationalClaimRef)],
            ["claim_id", "semantic_owner_ref", "claim_contract_ref", "generation"],
        )

    def test_u13_public_api_exports_minimal_claim_standing_surface(self) -> None:
        for name in (
            "OperationalClaimEvidenceRole",
            "OperationalClaimRef",
            "OperationalClaimStandingView",
            "project_operational_claim_standing_view",
        ):
            self.assertIn(name, api.__all__)
            self.assertIsNotNone(getattr(api, name))


if __name__ == "__main__":
    unittest.main()

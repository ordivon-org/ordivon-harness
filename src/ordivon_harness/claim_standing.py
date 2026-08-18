"""Minimal evidence-relative standing projections for owner-grounded claims.

This module intentionally provides no claim registry, persistence plane, owner
truth lookup, or global mutable claim status. It materializes only the value
layer admitted by the Operational Claim Standing reference contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anc_canonical import JsonValue, canonical_digest

from .core_contracts import HarnessBoundReference


_EVIDENCE_ROLES = {"supporting", "counterevidence", "required_unknown"}
_STANDINGS = {"SUPPORTED", "CONTRADICTED", "CONFLICTED", "UNDERDETERMINED"}


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields differ: {sorted(set(value) ^ expected)}")


def _text(value: str, label: str, *, max_bytes: int = 2_048) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _positive_int(value: int, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class OperationalClaimRef:
    """Exact reference to one bounded claim whose meaning remains owner-defined."""

    claim_id: str
    semantic_owner_ref: HarnessBoundReference
    claim_contract_ref: HarnessBoundReference
    generation: int

    def __post_init__(self) -> None:
        _text(self.claim_id, "Operational Claim identity", max_bytes=1_024)
        if not self.claim_id.startswith("claim:"):
            raise ValueError("Operational Claim identity must start with claim:")
        if not isinstance(self.semantic_owner_ref, HarnessBoundReference):
            raise TypeError("Operational Claim semantic owner reference is invalid")
        if not isinstance(self.claim_contract_ref, HarnessBoundReference):
            raise TypeError("Operational Claim contract reference is invalid")
        _positive_int(self.generation, "Operational Claim generation")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-operational-claim-ref",
            "claimId": self.claim_id,
            "semanticOwnerRef": self.semantic_owner_ref.to_dict(),
            "claimContractRef": self.claim_contract_ref.to_dict(),
            "generation": self.generation,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OperationalClaimRef:
        _exact(
            value,
            {
                "schemaVersion",
                "kind",
                "claimId",
                "semanticOwnerRef",
                "claimContractRef",
                "generation",
            },
            "OperationalClaimRef",
        )
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-operational-claim-ref"
        ):
            raise ValueError("OperationalClaimRef version or kind is invalid")
        owner = value["semanticOwnerRef"]
        contract = value["claimContractRef"]
        if not isinstance(owner, dict) or not isinstance(contract, dict):
            raise ValueError("OperationalClaimRef bound references are invalid")
        return cls(
            claim_id=value["claimId"],
            semantic_owner_ref=HarnessBoundReference.from_dict(owner),
            claim_contract_ref=HarnessBoundReference.from_dict(contract),
            generation=value["generation"],
        )


@dataclass(frozen=True, slots=True)
class OperationalClaimEvidenceRole:
    """One already-admitted evidence/unknown reference with local evidential role."""

    reference: HarnessBoundReference
    role: str

    def __post_init__(self) -> None:
        if not isinstance(self.reference, HarnessBoundReference):
            raise TypeError("Operational Claim evidence reference is invalid")
        if self.role not in _EVIDENCE_ROLES:
            raise ValueError(f"unsupported Operational Claim evidence role: {self.role}")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"reference": self.reference.to_dict(), "role": self.role}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OperationalClaimEvidenceRole:
        _exact(value, {"reference", "role"}, "OperationalClaimEvidenceRole")
        reference = value["reference"]
        role = value["role"]
        if not isinstance(reference, dict) or not isinstance(role, str):
            raise ValueError("OperationalClaimEvidenceRole values are invalid")
        return cls(reference=HarnessBoundReference.from_dict(reference), role=role)


def _derive_standing(evidence_roles: tuple[OperationalClaimEvidenceRole, ...]) -> str:
    roles = {item.role for item in evidence_roles}
    if "required_unknown" in roles:
        return "UNDERDETERMINED"
    if "supporting" in roles and "counterevidence" in roles:
        return "CONFLICTED"
    if "supporting" in roles:
        return "SUPPORTED"
    if "counterevidence" in roles:
        return "CONTRADICTED"
    return "UNDERDETERMINED"


@dataclass(frozen=True, slots=True)
class OperationalClaimStandingView:
    """Immutable subject/use/evidence-relative standing projection about one claim."""

    claim: OperationalClaimRef
    subject_ref: str
    use_contract_ref: HarnessBoundReference
    evidence_roles: tuple[OperationalClaimEvidenceRole, ...]
    standing: str
    generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.claim, OperationalClaimRef):
            raise TypeError("Operational Claim Standing claim reference is invalid")
        _text(self.subject_ref, "Operational Claim Standing subject", max_bytes=1_024)
        if not isinstance(self.use_contract_ref, HarnessBoundReference):
            raise TypeError("Operational Claim Standing use contract reference is invalid")
        if not isinstance(self.evidence_roles, tuple) or any(
            not isinstance(item, OperationalClaimEvidenceRole) for item in self.evidence_roles
        ):
            raise TypeError("Operational Claim Standing evidence roles are invalid")
        refs = [item.reference.ref for item in self.evidence_roles]
        if len(refs) != len(set(refs)):
            raise ValueError("Operational Claim Standing evidence references must be unique")
        if self.standing not in _STANDINGS:
            raise ValueError(f"unsupported Operational Claim standing: {self.standing}")
        expected = _derive_standing(self.evidence_roles)
        if self.standing != expected:
            raise ValueError(
                f"Operational Claim standing {self.standing} differs from evidence-role projection {expected}"
            )
        _positive_int(self.generation, "Operational Claim Standing generation")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-operational-claim-standing-view",
            "claim": self.claim.to_dict(),
            "subjectRef": self.subject_ref,
            "useContractRef": self.use_contract_ref.to_dict(),
            "evidenceRoles": [item.to_dict() for item in self.evidence_roles],
            "standing": self.standing,
            "generation": self.generation,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OperationalClaimStandingView:
        _exact(
            value,
            {
                "schemaVersion",
                "kind",
                "claim",
                "subjectRef",
                "useContractRef",
                "evidenceRoles",
                "standing",
                "generation",
            },
            "OperationalClaimStandingView",
        )
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-operational-claim-standing-view"
        ):
            raise ValueError("OperationalClaimStandingView version or kind is invalid")
        claim = value["claim"]
        use_contract = value["useContractRef"]
        evidence_roles = value["evidenceRoles"]
        if (
            not isinstance(claim, dict)
            or not isinstance(use_contract, dict)
            or not isinstance(evidence_roles, list)
            or any(not isinstance(item, dict) for item in evidence_roles)
            or not isinstance(value["standing"], str)
        ):
            raise ValueError("OperationalClaimStandingView values are invalid")
        return cls(
            claim=OperationalClaimRef.from_dict(claim),
            subject_ref=value["subjectRef"],
            use_contract_ref=HarnessBoundReference.from_dict(use_contract),
            evidence_roles=tuple(
                OperationalClaimEvidenceRole.from_dict(item) for item in evidence_roles
            ),
            standing=value["standing"],
            generation=value["generation"],
        )


def project_operational_claim_standing_view(
    *,
    claim: OperationalClaimRef,
    subject_ref: str,
    use_contract_ref: HarnessBoundReference,
    evidence_roles: tuple[OperationalClaimEvidenceRole, ...] = (),
    generation: int,
) -> OperationalClaimStandingView:
    """Project evidence standing from already-admitted typed evidence roles only."""

    if not isinstance(evidence_roles, tuple):
        raise TypeError("Operational Claim projection evidence roles must be a tuple")
    return OperationalClaimStandingView(
        claim=claim,
        subject_ref=subject_ref,
        use_contract_ref=use_contract_ref,
        evidence_roles=evidence_roles,
        standing=_derive_standing(evidence_roles),
        generation=generation,
    )


__all__ = [
    "OperationalClaimEvidenceRole",
    "OperationalClaimRef",
    "OperationalClaimStandingView",
    "project_operational_claim_standing_view",
]

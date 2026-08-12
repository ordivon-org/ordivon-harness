from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anc_canonical import JsonValue, canonical_digest

from .core_contracts import HarnessBoundReference, HarnessRunContract


class HarnessProviderUsePolicyError(ValueError):
    """Exact bound input/provider route is not admitted by the supplied policy."""


@dataclass(frozen=True, slots=True, order=True)
class HarnessProviderRoute:
    provider_id: str
    adapter_id: str
    requested_model_id: str

    def __post_init__(self) -> None:
        for label, value in (
            ("provider", self.provider_id),
            ("adapter", self.adapter_id),
            ("model", self.requested_model_id),
        ):
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or len(value.encode("utf-8")) > 300
            ):
                raise ValueError(f"Harness Provider Use Policy {label} identity is invalid")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "providerId": self.provider_id,
            "adapterId": self.adapter_id,
            "requestedModelId": self.requested_model_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessProviderRoute:
        if set(value) != {"providerId", "adapterId", "requestedModelId"}:
            raise ValueError("HarnessProviderRoute fields differ")
        return cls(
            provider_id=value["providerId"],
            adapter_id=value["adapterId"],
            requested_model_id=value["requestedModelId"],
        )


@dataclass(frozen=True, slots=True)
class HarnessProviderUsePolicy:
    """Caller-owned exact data-use constraint consumed before Provider construction.

    Harness does not classify a Provider as local/hosted or interpret a platform's
    prose rules. The caller binds this policy as a Run source reference and names
    exact input references plus exact Provider/Adapter/Model routes that may see
    those bytes. Harness only verifies the immutable binding and refuses all other
    routes before a Provider factory can run.
    """

    policy_id: str
    restricted_inputs: tuple[HarnessBoundReference, ...]
    allowed_routes: tuple[HarnessProviderRoute, ...]

    REFERENCE_KIND = "provider-use-policy-v1"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.policy_id, str)
            or not self.policy_id.startswith("provider-use-policy:")
            or self.policy_id != self.policy_id.strip()
        ):
            raise ValueError("Harness Provider Use Policy identity is invalid")
        if not self.restricted_inputs:
            raise ValueError("Harness Provider Use Policy requires restricted inputs")
        if not self.allowed_routes:
            raise ValueError("Harness Provider Use Policy requires at least one allowed route")
        input_keys = [(item.ref, item.kind, item.digest) for item in self.restricted_inputs]
        if len(input_keys) != len(set(input_keys)):
            raise ValueError("Harness Provider Use Policy restricted inputs must be unique")
        if tuple(sorted(self.restricted_inputs, key=lambda item: (item.ref, item.kind, item.digest))) != self.restricted_inputs:
            raise ValueError("Harness Provider Use Policy restricted inputs must be sorted")
        if len(self.allowed_routes) != len(set(self.allowed_routes)):
            raise ValueError("Harness Provider Use Policy routes must be unique")
        if tuple(sorted(self.allowed_routes)) != self.allowed_routes:
            raise ValueError("Harness Provider Use Policy routes must be sorted")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @property
    def bound_reference(self) -> HarnessBoundReference:
        return HarnessBoundReference(self.policy_id, self.REFERENCE_KIND, self.digest)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-provider-use-policy",
            "policyId": self.policy_id,
            "restrictedInputs": [item.to_dict() for item in self.restricted_inputs],
            "allowedRoutes": [item.to_dict() for item in self.allowed_routes],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessProviderUsePolicy:
        expected = {"schemaVersion", "kind", "policyId", "restrictedInputs", "allowedRoutes"}
        if set(value) != expected:
            raise ValueError("HarnessProviderUsePolicy fields differ")
        raw_inputs = value["restrictedInputs"]
        raw_routes = value["allowedRoutes"]
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-provider-use-policy"
            or not isinstance(raw_inputs, list)
            or not isinstance(raw_routes, list)
            or any(not isinstance(item, dict) for item in raw_inputs)
            or any(not isinstance(item, dict) for item in raw_routes)
        ):
            raise ValueError("HarnessProviderUsePolicy is invalid")
        return cls(
            policy_id=value["policyId"],
            restricted_inputs=tuple(HarnessBoundReference.from_dict(item) for item in raw_inputs),
            allowed_routes=tuple(HarnessProviderRoute.from_dict(item) for item in raw_routes),
        )


def validate_provider_use_policy(
    contract: HarnessRunContract,
    policy: HarnessProviderUsePolicy | None,
) -> None:
    policy_refs = tuple(
        item for item in contract.source_refs if item.kind == HarnessProviderUsePolicy.REFERENCE_KIND
    )
    if len(policy_refs) > 1:
        raise HarnessProviderUsePolicyError("Harness Run Contract binds multiple Provider Use Policies")
    if not policy_refs:
        if policy is not None:
            raise HarnessProviderUsePolicyError(
                "Harness Provider Use Policy is supplied but not bound by the Run Contract"
            )
        return
    if policy is None:
        raise HarnessProviderUsePolicyError(
            "Harness Run Contract requires its exact Provider Use Policy"
        )
    if policy_refs[0] != policy.bound_reference:
        raise HarnessProviderUsePolicyError(
            "Harness Provider Use Policy differs from its Run Contract reference"
        )
    content_refs = {
        (item.ref, item.kind, item.digest)
        for item in (*contract.context_refs, *contract.source_refs, *contract.prior_artifact_refs)
        if item.kind != HarnessProviderUsePolicy.REFERENCE_KIND
    }
    missing = [
        item.ref
        for item in policy.restricted_inputs
        if (item.ref, item.kind, item.digest) not in content_refs
    ]
    if missing:
        raise HarnessProviderUsePolicyError(
            "Harness Provider Use Policy restricts inputs not bound by the Run Contract: "
            + ", ".join(missing)
        )
    route = HarnessProviderRoute(
        provider_id=contract.provider_id,
        adapter_id=contract.adapter_id,
        requested_model_id=contract.requested_model_id,
    )
    if route not in policy.allowed_routes:
        raise HarnessProviderUsePolicyError(
            "Harness Provider route is not admitted for the Contract's restricted inputs"
        )


__all__ = [
    "HarnessProviderRoute",
    "HarnessProviderUsePolicy",
    "HarnessProviderUsePolicyError",
    "validate_provider_use_policy",
]

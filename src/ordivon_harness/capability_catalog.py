"""Derived capability/composition projections for Agent-facing discovery.

This module does not grant authority and does not own Tool schemas, Run authority,
or current turn policy.  It projects those facts from their existing owners so an
Agent can discover the installed surface without reconstructing it from source.
"""

from __future__ import annotations

from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .core_contracts import HarnessRunContract
from .execution_binding import HarnessExecutionBinding
from .ordivon.model import AgentTurnRequest
from .ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_GRANT,
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE,
    NO_TOOL_AGENT_SURFACE_DIGEST,
)
from .ordivon.sqlite_repository_repair_bridge import (
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT,
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE,
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST,
)
from .ordivon.sqlite_runtime_bridge import (
    INDEPENDENT_SEARCH_TOOL_GRANT,
    INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
    INDEPENDENT_SEARCH_TOOL_SURFACE,
    INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
)
from .knowledge_topology import effective_knowledge_topology
from .provider_use_policy import HarnessProviderUsePolicy
from .standalone import HarnessCognitionProfile

_INSTALLED = "installed"
_RUN_ADMITTED = "run-admitted"
_TURN_ADMITTED = "turn-admitted"


def _surface(
    *,
    surface_id: str,
    summary: str,
    source_surface_symbol: str,
    source_grant_symbol: str,
    catalog_digest: str,
    grant_digest: str,
    surface: dict[str, JsonValue],
    grant: dict[str, JsonValue],
    runtime_required: bool,
    supported: bool,
    visibility: str,
) -> dict[str, JsonValue]:
    requirements: dict[str, JsonValue] = {
        "adapter": "required-and-contract-matching",
        "executionBinding": (
            "required-and-contract-matching" if runtime_required else "forbidden"
        ),
        "runtimeClient": (
            "required-but-liveness-not-implied" if runtime_required else "forbidden"
        ),
        "providerUsePolicy": "required-only-if-contract-binds-policy",
    }
    if not supported:
        requirements["explicitRunToolSurface"] = "required"
    return {
        "surfaceId": surface_id,
        "owner": "ordivon-harness",
        "stage": _INSTALLED,
        "visibility": visibility,
        "summary": summary,
        "source": {
            "surfaceSymbol": source_surface_symbol,
            "grantSymbol": source_grant_symbol,
        },
        "toolCatalogDigest": catalog_digest,
        "toolGrantDigest": grant_digest,
        "tools": list(surface["tools"]),
        "grant": dict(grant),
        "requirements": requirements,
        "supportedByHarnessAgentRun": supported,
        "authorityRole": (
            "installed-mechanism-only"
            if supported
            else "installed-specialized-mechanism-only"
        ),
    }


def _execution_surfaces() -> list[dict[str, JsonValue]]:
    return [
        _surface(
            surface_id="harness.execution.no-tool.v1",
            summary="Provider-only Agent Run with no external Tool surface.",
            source_surface_symbol=(
                "ordivon_harness.ordivon.sqlite_agent_bridge:NO_TOOL_AGENT_SURFACE"
            ),
            source_grant_symbol=(
                "ordivon_harness.ordivon.sqlite_agent_bridge:NO_TOOL_AGENT_GRANT"
            ),
            catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
            grant_digest=NO_TOOL_AGENT_GRANT_DIGEST,
            surface=NO_TOOL_AGENT_SURFACE,
            grant=NO_TOOL_AGENT_GRANT,
            runtime_required=False,
            supported=True,
            visibility="recommended",
        ),
        _surface(
            surface_id="harness.execution.runtime-search.v1",
            summary=(
                "Observation-only workspace search lowered through an exact Runtime "
                "execution binding."
            ),
            source_surface_symbol=(
                "ordivon_harness.ordivon.sqlite_runtime_bridge:"
                "INDEPENDENT_SEARCH_TOOL_SURFACE"
            ),
            source_grant_symbol=(
                "ordivon_harness.ordivon.sqlite_runtime_bridge:"
                "INDEPENDENT_SEARCH_TOOL_GRANT"
            ),
            catalog_digest=INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
            grant_digest=INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
            surface=INDEPENDENT_SEARCH_TOOL_SURFACE,
            grant=INDEPENDENT_SEARCH_TOOL_GRANT,
            runtime_required=True,
            supported=True,
            visibility="recommended-api",
        ),
        _surface(
            surface_id="harness.execution.repository-repair.v1",
            summary="Frozen repository-repair surface with durable Runtime reconciliation.",
            source_surface_symbol=(
                "ordivon_harness.ordivon.sqlite_repository_repair_bridge:"
                "INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE"
            ),
            source_grant_symbol=(
                "ordivon_harness.ordivon.sqlite_repository_repair_bridge:"
                "INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT"
            ),
            catalog_digest=INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST,
            grant_digest=INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST,
            surface=INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE,
            grant=INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT,
            runtime_required=True,
            supported=False,
            visibility="specialized-advanced",
        ),
        _surface(
            surface_id="harness.execution.repository-repair-edit.v2",
            summary="Agent-friendly repository-repair edit surface over durable Runtime Patch.",
            source_surface_symbol=(
                "ordivon_harness.ordivon.sqlite_repository_repair_bridge:"
                "INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE"
            ),
            source_grant_symbol=(
                "ordivon_harness.ordivon.sqlite_repository_repair_bridge:"
                "INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT"
            ),
            catalog_digest=INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST,
            grant_digest=INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST,
            surface=INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE,
            grant=INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT,
            runtime_required=True,
            supported=False,
            visibility="specialized-advanced",
        ),
    ]


def _cognition_mechanisms() -> list[dict[str, JsonValue]]:
    return [
        {
            "capabilityId": "harness.action.conclusion",
            "owner": "ordivon-harness",
            "stage": _INSTALLED,
            "summary": "Submit one bounded Run conclusion candidate.",
            "requestField": "conclusion",
            "profileField": None,
            "runRequirements": ["Harness invariant"],
            "turnRequirements": ["always admitted by AgentTurnCapabilities"],
            "authorityRole": "mechanism-only-until-request-bound",
        },
        {
            "capabilityId": "harness.cognition.working-set-transition",
            "owner": "ordivon-harness",
            "stage": _INSTALLED,
            "summary": "Propose an explicit successor durable WorkingSet.",
            "requestField": "working_set_transition",
            "profileField": "working_set_transitions",
            "runRequirements": [
                "HarnessCognitionProfile.working_set_transitions",
                "Run privacy allowModelContent",
            ],
            "turnRequirements": ["projector admits a transition on this exact turn"],
            "authorityRole": "mechanism-only-until-request-bound",
        },
        {
            "capabilityId": "harness.cognition.caller-ingress-promotion",
            "owner": "ordivon-harness",
            "stage": _INSTALLED,
            "summary": "Promote exact addressable caller ingress into durable cognition.",
            "requestField": "caller_ingress_promotion",
            "profileField": "caller_ingress_promotions",
            "runRequirements": [
                "HarnessCognitionProfile.caller_ingress_promotions",
                "Run privacy allowModelContent",
            ],
            "turnRequirements": ["exact promotable callerIngressRefs are addressable"],
            "authorityRole": "mechanism-only-until-request-bound",
        },
        {
            "capabilityId": "harness.cognition.working-set-history",
            "owner": "ordivon-harness",
            "stage": _INSTALLED,
            "summary": "Inspect bounded identities of prior committed WorkingSets.",
            "requestField": "working_set_history",
            "profileField": "working_set_history",
            "runRequirements": [
                "HarnessCognitionProfile.working_set_history",
                "Run privacy allowModelContent",
                "Run privacy allowToolContent",
            ],
            "turnRequirements": ["history reader is present for this exact turn"],
            "authorityRole": "mechanism-only-until-request-bound",
        },
    ]


def effective_capability_catalog() -> dict[str, JsonValue]:
    """Return the package-resolved installed capability surface.

    The result is a projection of source-owned definitions.  It says what this
    package knows how to compose; it does not say that a caller has granted those
    mechanisms to a Run, that a Runtime/Provider is live, or that a current turn
    may use them.
    """

    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-effective-capability-catalog",
        "truthRole": "derived-installed-capability-projection",
        "stages": [_INSTALLED, _RUN_ADMITTED, _TURN_ADMITTED],
        "stageLaw": (
            "installed capability does not imply Run authority; Run authority does not "
            "imply exact turn addressability"
        ),
        "executionSurfaces": _execution_surfaces(),
        "cognitionMechanisms": _cognition_mechanisms(),
        "knowledgeTopology": effective_knowledge_topology(),
    }
    validate_json_value(value)
    return value


def effective_capability_catalog_digest() -> str:
    return canonical_digest(effective_capability_catalog())


def resolve_builtin_execution_surface(
    tool_catalog_digest: str,
    tool_grant_digest: str,
) -> dict[str, JsonValue] | None:
    for surface in _execution_surfaces():
        if (
            surface["toolCatalogDigest"] == tool_catalog_digest
            and surface["toolGrantDigest"] == tool_grant_digest
        ):
            return surface
    return None


def project_run_capabilities(contract: HarnessRunContract) -> dict[str, JsonValue]:
    """Project contract-bound Run capability facts without process-local guesses."""

    surface = resolve_builtin_execution_surface(
        contract.tool_catalog_digest,
        contract.tool_grant_digest,
    )
    tool_surface: dict[str, JsonValue]
    if surface is None:
        tool_surface = {
            "resolution": "custom-or-unrecognized",
            "toolCatalogDigest": contract.tool_catalog_digest,
            "toolGrantDigest": contract.tool_grant_digest,
            "supportedByHarnessAgentRun": False,
        }
    else:
        tool_surface = {
            "resolution": "recognized-built-in",
            "surfaceId": surface["surfaceId"],
            "toolCatalogDigest": contract.tool_catalog_digest,
            "toolGrantDigest": contract.tool_grant_digest,
            "tools": surface["tools"],
            "supportedByHarnessAgentRun": surface["supportedByHarnessAgentRun"],
        }
    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-run-capability-projection",
        "truthRole": "derived-from-harness-run-contract",
        "stage": _RUN_ADMITTED,
        "harnessRunId": contract.harness_run_id,
        "provider": {
            "providerId": contract.provider_id,
            "adapterId": contract.adapter_id,
            "requestedModelId": contract.requested_model_id,
        },
        "toolSurface": tool_surface,
        "cognitionMechanisms": {
            "status": "process-local-not-bound-by-run-contract",
            "reason": (
                "HarnessCognitionProfile is structural process composition; exact native "
                "actions are bound only on AgentTurnRequest"
            ),
        },
        "privacy": contract.privacy.to_dict(),
        "budget": dict(contract.budget),
    }
    validate_json_value(value)
    return value


def project_turn_capabilities(request: AgentTurnRequest) -> dict[str, JsonValue]:
    """Project the exact action surface already bound into one AgentTurnRequest."""

    native: list[str] = []
    if request.capabilities.conclusion:
        native.append("conclusion")
    if request.capabilities.working_set_transition:
        native.append("working-set-transition")
    if request.capabilities.caller_ingress_promotion:
        native.append("caller-ingress-promotion")
    if request.capabilities.working_set_history:
        native.append("working-set-history")
    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-turn-capability-projection",
        "truthRole": "derived-from-exact-agent-turn-request",
        "stage": _TURN_ADMITTED,
        "harnessRunId": request.harness_run_id,
        "turnId": request.turn_id,
        "sequence": request.sequence,
        "toolCatalogDigest": request.tool_catalog_digest,
        "tools": [tool.to_dict() for tool in request.tools],
        "nativeActions": native,
        "callerIngressAddressable": bool(request.caller_ingress_refs),
        "workingSetSources": [ref.pin.slot for ref in request.working_set_refs],
        "requestDigest": request.digest,
        "dispatchDigest": request.dispatch_digest,
    }
    validate_json_value(value)
    return value


def project_process_composition(
    contract: HarnessRunContract,
    *,
    adapter: Any,
    cognition_profile: HarnessCognitionProfile | None,
    execution_binding: HarnessExecutionBinding | None,
    runtime_supplied: bool,
    provider_use_policy: HarnessProviderUsePolicy | None,
) -> dict[str, JsonValue]:
    """Explain the inputs wired into one validated in-process HarnessAgentRun.

    Runtime/Provider liveness is deliberately not probed here.  Supplied means the
    process has an object; it does not mean the external owner is healthy/current.
    """

    cognition: dict[str, JsonValue]
    if cognition_profile is None:
        cognition = {
            "supplied": False,
            "mechanisms": [],
            "proofRole": "process-local",
        }
    else:
        mechanisms = []
        if cognition_profile.working_set_transitions:
            mechanisms.append("working-set-transition")
        if cognition_profile.caller_ingress_promotions:
            mechanisms.append("caller-ingress-promotion")
        if cognition_profile.working_set_history:
            mechanisms.append("working-set-history")
        cognition = {
            "supplied": True,
            "mechanisms": mechanisms,
            "profile": {
                "workingSetTransitions": cognition_profile.working_set_transitions,
                "callerIngressPromotions": cognition_profile.caller_ingress_promotions,
                "workingSetHistory": cognition_profile.working_set_history,
            },
            "proofRole": "process-local",
        }
    binding: dict[str, JsonValue]
    if execution_binding is None:
        binding = {"supplied": False, "proofRole": "process-local"}
    else:
        binding = {
            "supplied": True,
            "proofRole": "process-local-and-contract-checked",
            "bindingDigest": canonical_digest(execution_binding.to_dict()),
            "toolCatalogDigest": execution_binding.tool_catalog_digest,
            "toolGrantDigest": execution_binding.tool_grant_digest,
            "runtimeReferenceCount": len(execution_binding.runtime_references),
        }
    policy: dict[str, JsonValue]
    if provider_use_policy is None:
        policy = {"supplied": False, "proofRole": "process-local"}
    else:
        policy = {
            "supplied": True,
            "proofRole": "process-local-and-contract-checked",
            "policyId": provider_use_policy.policy_id,
            "policyDigest": provider_use_policy.digest,
        }
    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-process-composition-projection",
        "truthRole": "derived-read-only-composition-projection",
        "run": project_run_capabilities(contract),
        "processLocal": {
            "adapter": {
                "supplied": True,
                "proofRole": "process-local-and-contract-checked",
                "adapterId": getattr(adapter, "adapter_id", "unknown"),
                "modelId": getattr(adapter, "model_id", "unknown"),
                "liveness": "not-probed",
            },
            "cognition": cognition,
            "executionBinding": binding,
            "runtimeClient": {
                "supplied": runtime_supplied,
                "proofRole": "process-local",
                "liveness": "not-probed",
            },
            "providerUsePolicy": policy,
        },
        "proofBoundary": (
            "process-local objects are reported as supplied/validated only; this projection "
            "does not grant authority or prove Provider/Runtime liveness"
        ),
    }
    validate_json_value(value)
    return value


__all__ = [
    "effective_capability_catalog",
    "effective_capability_catalog_digest",
    "project_process_composition",
    "project_run_capabilities",
    "project_turn_capabilities",
    "resolve_builtin_execution_surface",
]

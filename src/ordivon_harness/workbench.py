"""Read-only Agent/operator projections over existing Harness truth owners."""

from __future__ import annotations

from anc_canonical import JsonValue, validate_json_value

from .capability_catalog import project_run_capabilities, project_turn_capabilities
from .core_contracts import HarnessRunContract
from .ordivon.model import AgentTurnRequest


def build_durable_workbench_projection(
    *,
    run: dict[str, JsonValue],
    contract: HarnessRunContract,
    provider_call: dict[str, JsonValue] | None,
    provider_request: AgentTurnRequest | None,
    snapshot: dict[str, JsonValue] | None,
    recovery: dict[str, JsonValue] | None,
    run_receipt: dict[str, JsonValue] | None,
    completion_proposal: dict[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    """Build one compact projection without adding a second durable state model."""

    if provider_request is not None:
        action_surface: dict[str, JsonValue] = {
            "status": "retained-exact-request",
            "projection": project_turn_capabilities(provider_request),
        }
    elif provider_call is not None:
        action_surface = {
            "status": "unavailable",
            "reason": (
                "the current Provider Call is durable but its AgentTurnRequest content is "
                "not retained/available under this privacy and continuity state"
            ),
        }
    else:
        action_surface = {
            "status": "not-observed",
            "reason": "no current Provider Call exists",
        }

    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-workbench-projection",
        "truthRole": "derived-read-only-projection",
        "run": {
            "harnessRunId": contract.harness_run_id,
            "status": run.get("status", "unknown"),
            "contractDigest": contract.digest,
        },
        "composition": project_run_capabilities(contract),
        "currentActionSurface": action_surface,
        "provider": {
            "status": "not-observed" if provider_call is None else provider_call.get("status", "unknown"),
            "record": provider_call,
        },
        "continuity": {
            "snapshot": snapshot,
            "recovery": recovery,
        },
        "completion": {
            "runReceipt": run_receipt,
            "completionProposal": completion_proposal,
            "semanticCompletionAuthority": "caller-or-domain",
        },
        "proofBoundaries": {
            "durable": "Run/Contract/Provider/Snapshot/Recovery objects come from Harness Journal/CAS",
            "processLocal": (
                "Adapter factory, Runtime client and other application objects are not inferred "
                "by a fresh durable-state inspection"
            ),
            "external": "Provider/Runtime/domain liveness and world truth are not claimed",
        },
    }
    validate_json_value(value)
    return value


__all__ = ["build_durable_workbench_projection"]

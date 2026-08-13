from __future__ import annotations

from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value


class HarnessTelemetryProjectionError(ValueError):
    pass


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HarnessTelemetryProjectionError(f"{label} must be an object")
    return value


def _non_negative(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return value


def _remaining_from_budget(
    budget: dict[str, Any],
    usage: dict[str, Any],
) -> dict[str, JsonValue]:
    pairs = {
        "modelCalls": "maxModelCalls",
        "toolCalls": "maxToolCalls",
        "observationBytes": "maxObservationBytes",
        "totalTokens": "maxTotalTokens",
        "wallTimeMs": "maxWallTimeMs",
        "modelRetries": "maxModelRetries",
        "toolCorrections": "maxToolCorrections",
        "conclusionCorrections": "maxConclusionCorrections",
        "observationOnlyTurns": "maxObservationOnlyTurns",
        "noProgressTurns": "maxNoProgressTurns",
    }
    remaining: dict[str, JsonValue] = {}
    for usage_key, budget_key in pairs.items():
        limit = _non_negative(budget.get(budget_key))
        used = _non_negative(usage.get(usage_key))
        if limit is None or used is None:
            continue
        remaining[usage_key] = max(0, limit - used)
    return remaining


def _cache_projection(usage: dict[str, Any]) -> dict[str, JsonValue]:
    raw = usage.get("providerUsage")
    if not isinstance(raw, list):
        raw = []
    hit = 0
    miss = 0
    observed = False
    request_modes: set[str] = set()
    provider_models: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        hit_value = _non_negative(item.get("prompt_cache_hit_tokens"))
        miss_value = _non_negative(item.get("prompt_cache_miss_tokens"))
        if hit_value is not None:
            hit += int(hit_value)
            observed = True
        if miss_value is not None:
            miss += int(miss_value)
            observed = True
        mode = item.get("providerRequestMode")
        if isinstance(mode, str) and mode:
            request_modes.add(mode)
        model = item.get("providerModel")
        if isinstance(model, str) and model:
            provider_models.add(model)
    denominator = hit + miss
    return {
        "available": observed,
        "hitTokens": hit if observed else None,
        "missTokens": miss if observed else None,
        "prefixTokens": denominator if observed else None,
        "hitRatio": (
            {"numerator": hit, "denominator": denominator}
            if observed and denominator > 0
            else None
        ),
        "providerRequestModes": sorted(request_modes),
        "providerModels": sorted(provider_models),
        "policyRole": "measurement-only",
    }


def build_harness_telemetry_projection(
    inspected: dict[str, Any],
) -> dict[str, JsonValue]:
    """Compress one exact Harness inspect projection without creating new authority."""

    root = _object(inspected, "Harness inspect projection")
    run = _object(root.get("run"), "Harness Run projection")
    contract = _object(root.get("contract"), "Harness Run Contract")
    budget = _object(contract.get("budget"), "Harness Run budget")
    receipt_value = root.get("runReceipt")
    receipt = receipt_value if isinstance(receipt_value, dict) else None
    snapshot_value = root.get("snapshot")
    snapshot = snapshot_value if isinstance(snapshot_value, dict) else None
    recovery_value = root.get("recovery")
    recovery = recovery_value if isinstance(recovery_value, dict) else None
    provider_value = root.get("providerCall")
    provider_call = provider_value if isinstance(provider_value, dict) else None

    usage: dict[str, Any] = {}
    if receipt is not None:
        raw_usage = receipt.get("usage")
        if isinstance(raw_usage, dict):
            usage = dict(raw_usage)

    if snapshot is not None and isinstance(snapshot.get("remainingBudget"), dict):
        remaining_budget: dict[str, JsonValue] = dict(snapshot["remainingBudget"])
        remaining_basis = "durable-run-snapshot"
    elif usage:
        remaining_budget = _remaining_from_budget(budget, usage)
        remaining_basis = "terminal-receipt-and-contract"
    else:
        remaining_budget = {}
        remaining_basis = "unavailable"

    started_at = receipt.get("startedAtMs") if receipt is not None else None
    finished_at = receipt.get("finishedAtMs") if receipt is not None else None
    duration = (
        finished_at - started_at
        if type(started_at) is int
        and type(finished_at) is int
        and finished_at >= started_at
        else None
    )

    usage_projection: dict[str, JsonValue] = {
        key: usage[key]
        for key in (
            "modelCalls",
            "toolCalls",
            "observationBytes",
            "totalTokens",
            "wallTimeMs",
            "modelRetries",
            "toolCorrections",
            "conclusionCorrections",
            "providerAttempts",
            "providerResultsReplayed",
            "requestedModelId",
            "effectiveModelIds",
        )
        if key in usage
    }

    recovery_projection: dict[str, JsonValue] | None = None
    if recovery is not None:
        recovery_projection = {
            key: recovery[key]
            for key in (
                "trigger",
                "grantEffectClass",
                "catalogStatus",
                "workspaceStatus",
                "safeToAbandon",
                "unresolvedUnknowns",
            )
            if key in recovery
        }

    provider_status = None if provider_call is None else provider_call.get("status")
    projection: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-telemetry-projection",
        "truthRole": "derived-read-only-projection",
        "authority": root.get("authority", "independent-harness-run"),
        "run": {
            "harnessRunId": run.get("harnessRunId"),
            "status": run.get("status"),
            "revision": run.get("revision"),
            "createdAtMs": run.get("createdAtMs"),
            "updatedAtMs": run.get("updatedAtMs"),
            "terminalEventId": run.get("terminalEventId"),
        },
        "profile": {
            "adapterId": contract.get("adapterId"),
            "providerId": contract.get("providerId"),
            "requestedModelId": contract.get("requestedModelId"),
            "toolCatalogDigest": contract.get("toolCatalogDigest"),
            "toolGrantDigest": contract.get("toolGrantDigest"),
        },
        "termination": {
            "stopReason": None if receipt is None else receipt.get("stopReason"),
            "terminationCode": None if receipt is None else receipt.get("terminationCode"),
            "startedAtMs": started_at,
            "finishedAtMs": finished_at,
            "durationMs": duration,
        },
        "usage": usage_projection,
        "budget": {
            "limits": dict(budget),
            "remaining": remaining_budget,
            "remainingBasis": remaining_basis,
        },
        "cache": _cache_projection(usage),
        "continuity": {
            "providerCallStatus": provider_status,
            "pauseReason": None if snapshot is None else snapshot.get("pauseReason"),
            "recoveryAssessment": recovery_projection,
            "unknownsRemain": bool(
                recovery_projection
                and recovery_projection.get("unresolvedUnknowns")
            ),
        },
        "evidence": {
            "contractDigest": run.get("contractDigest"),
            "runReceiptDigest": None if receipt is None else canonical_digest(receipt),
            "traceDigest": None if receipt is None else receipt.get("traceDigest"),
            "runtimeJobRefs": [] if receipt is None else receipt.get("runtimeJobRefs", []),
        },
        "interpretationBoundary": {
            "cache": "measurement-only; cache locality is not cognition or semantic policy",
            "completion": "Harness terminality and CompletionProposal do not imply domain semantic completion",
            "currentness": "this projection is derived from the exact Harness state read used to build it",
            "escapeHatch": "ordivon-harness inspect <harness-run-id>",
        },
    }
    validate_json_value(projection)
    return projection


__all__ = [
    "HarnessTelemetryProjectionError",
    "build_harness_telemetry_projection",
]

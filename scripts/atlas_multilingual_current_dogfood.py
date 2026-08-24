#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from anc_canonical import JsonValue, canonical_digest, loads_strict, validate_json_value

from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.model import AgentTurnRequest
from ordivon_harness.structured_result_conformance import (
    LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1,
    validate_structured_result_instance,
    validate_structured_result_schema_policy,
)

APPLICATION = Path(__file__).resolve().parent / "atlas_research_start_application.py"
spec = importlib.util.spec_from_file_location("atlas_research_start_application_live", APPLICATION)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load Atlas application from {APPLICATION}")
atlas_app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = atlas_app
spec.loader.exec_module(atlas_app)

NO_TOOL_CATALOG_DIGEST = canonical_digest({"tools": []})

QUERY_COMPLETION: dict[str, JsonValue] = {
    "mode": "structured-result-v1",
    "resultKind": "atlas-retrieval-query-authorship",
    "conformancePolicy": LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1,
    "resultSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "queries": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {"type": "string", "minLength": 1, "maxLength": 2048},
            },
            "reason": {"type": "string", "minLength": 1, "maxLength": 2000},
        },
        "required": ["queries", "reason"],
    },
}

ADJUDICATION_COMPLETION: dict[str, JsonValue] = {
    "mode": "structured-result-v1",
    "resultKind": "atlas-prior-work-adjudication",
    "conformancePolicy": LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1,
    "resultSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["consume_prior", "needs_input"]},
            "coverage": {"type": "string", "enum": ["substantial", "partial", "insufficient"]},
            "reason": {"type": "string", "minLength": 1, "maxLength": 4000},
            "semanticEquivalenceEstablished": {"type": "boolean", "enum": [False]},
            "noveltyEstablished": {"type": "boolean", "enum": [False]},
            "researchAdmissionGranted": {"type": "boolean", "enum": [False]},
        },
        "required": [
            "decision",
            "coverage",
            "reason",
            "semanticEquivalenceEstablished",
            "noveltyEstablished",
            "researchAdmissionGranted",
        ],
    },
}


def _structured_turn(
    settings: DeepSeekSettings,
    *,
    label: str,
    sequence: int,
    context: JsonValue,
    messages: tuple[dict[str, JsonValue], ...],
    completion: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    validate_structured_result_schema_policy(completion)
    adapter = DeepSeekTurnAdapter(settings, completion_contract=completion)
    request = AgentTurnRequest(
        harness_run_id=f"harness-run:atlas-multilingual-current-{label}",
        turn_id=f"turn:atlas-multilingual-current-{label}-{sequence}",
        sequence=sequence,
        assignment_id=f"assignment:atlas-multilingual-current-{label}",
        context_digest=canonical_digest(context),
        tool_catalog_digest=NO_TOOL_CATALOG_DIGEST,
        messages=messages,
        tools=(),
        remaining_budget={"modelCalls": 1, "toolCalls": 0, "totalTokens": 12000},
    )
    result = adapter.invoke(request)
    if result.tool_calls:
        raise RuntimeError("query/adjudication Agent emitted a Domain Tool call")
    if result.conclusion is None:
        raise RuntimeError("query/adjudication Agent omitted structured conclusion")
    value = loads_strict(result.conclusion.summary.encode("utf-8"))
    validate_json_value(value)
    validate_structured_result_instance(completion, value)
    if not isinstance(value, dict):
        raise TypeError("structured result must be an object")
    telemetry: dict[str, JsonValue] = {
        "modelCallId": result.model_call_id,
        "modelId": result.model_id,
        "finishReason": result.finish_reason,
        "conclusionStatus": result.conclusion.status,
        "usage": result.usage,
        "rawResponseDigest": result.raw_response_digest,
        "requestDigest": request.digest,
        "providerRequestDigest": adapter.provider_request_digest(request),
        "domainToolCalls": 0,
    }
    validate_json_value(telemetry)
    return dict(value), telemetry


def _owner_job_ids(receipt: dict[str, Any]) -> list[str]:
    rows: list[Any] = []
    owner_call = receipt.get("ownerCall")
    if isinstance(owner_call, dict):
        rows.append(owner_call)
    owner_calls = receipt.get("ownerCalls")
    if isinstance(owner_calls, list):
        rows.extend(owner_calls)
    return [
        str(row["runtimeJobId"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("runtimeJobId"), str)
    ]


def run_episode(
    *,
    intent: str,
    label: str,
    atlas_workspace: str,
    secret: Path,
    runtime_scripts: Path,
    runtime_environment_file: Path,
    runtime_endpoint: str,
) -> dict[str, JsonValue]:
    settings = DeepSeekSettings.from_secret_file(
        secret,
        timeout_seconds=90.0,
        max_output_tokens=2048,
    )
    runtime = atlas_app._runtime_client(runtime_scripts, runtime_environment_file, runtime_endpoint)
    episode_ref = f"consumer-episode:atlas-multilingual-current-{label}"

    authoring_receipt = atlas_app.run_atlas_query_authoring_context_application(
        runtime,
        atlas_workspace_id=atlas_workspace,
        request_prefix=f"atlas-multilingual-current-{label}",
        consumer_episode_ref=episode_ref,
        consumer_class="dogfood",
    )
    authoring_view = authoring_receipt["modelView"]
    query_result, query_telemetry = _structured_turn(
        settings,
        label=f"{label}-query",
        sequence=1,
        context={"intent": intent, "ownerAuthoringContext": authoring_view},
        completion=QUERY_COMPLETION,
        messages=(
            {
                "role": "system",
                "content": (
                    "You are a fresh Ordivon research consumer. Author one to four lexical retrieval "
                    "query variants for the caller's research intent using the Atlas owner environment "
                    "facts and task-neutral retrieval coordinates below. You own the wording. Atlas and "
                    "the application did not translate the intent or generate a query. Do not claim that "
                    "any coordinate or variant is semantically equivalent to the intent. Submit only the "
                    "structured query-authorship result; no Runtime or domain Tools are available."
                ),
            },
            {"role": "user", "content": "CALLER_RESEARCH_INTENT:\n" + intent},
            {
                "role": "user",
                "content": "ATLAS_OWNER_QUERY_AUTHORING_CONTEXT:\n"
                + json.dumps(authoring_view, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
        ),
    )
    queries = query_result.get("queries")
    if not isinstance(queries, list) or not all(isinstance(item, str) for item in queries):
        raise TypeError("query Agent result omitted query strings")

    research_receipt = atlas_app.run_atlas_research_start_application(
        runtime,
        atlas_workspace_id=atlas_workspace,
        queries=queries,
        limit=4,
        request_prefix=f"atlas-multilingual-current-{label}",
        consumer_episode_ref=episode_ref,
        consumer_class="dogfood",
    )
    research_view = research_receipt["modelView"]
    adjudication, adjudication_telemetry = _structured_turn(
        settings,
        label=f"{label}-adjudication",
        sequence=2,
        context={
            "intent": intent,
            "agentAuthoredQueries": queries,
            "ownerResearchStartView": research_view,
        },
        completion=ADJUDICATION_COMPLETION,
        messages=(
            {
                "role": "system",
                "content": (
                    "You are the caller-side research consumer after one bounded Atlas research-start "
                    "episode. Judge only whether the returned non-authoritative prior-work evidence is "
                    "substantial enough to consume before opening new research, or whether more input is "
                    "needed. Candidate presence does not establish semantic equivalence; candidate absence "
                    "does not establish novelty. You may not grant research admission. Submit only the "
                    "structured adjudication result; no Runtime or domain Tools are available."
                ),
            },
            {"role": "user", "content": "CALLER_RESEARCH_INTENT:\n" + intent},
            {
                "role": "user",
                "content": "AGENT_AUTHORED_QUERY_VARIANTS:\n"
                + json.dumps(queries, ensure_ascii=False, separators=(",", ":")),
            },
            {
                "role": "user",
                "content": "ATLAS_RESEARCH_START_MODEL_VIEW:\n"
                + json.dumps(research_view, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
        ),
    )
    if (
        adjudication.get("semanticEquivalenceEstablished") is not False
        or adjudication.get("noveltyEstablished") is not False
        or adjudication.get("researchAdmissionGranted") is not False
    ):
        raise RuntimeError("caller adjudication inflated Atlas epistemic standing")

    first_look = research_receipt.get("firstLook")
    candidates = first_look.get("candidates") if isinstance(first_look, dict) else None
    top = candidates[0] if isinstance(candidates, list) and candidates else None
    owner_jobs = _owner_job_ids(authoring_receipt) + _owner_job_ids(research_receipt)
    receipt: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.atlas-multilingual-current-dogfood",
        "label": label,
        "intent": intent,
        "agentAuthoredQueries": list(queries),
        "queryAuthorshipReason": query_result["reason"],
        "queryAuthorshipTelemetry": query_telemetry,
        "ownerAuthoringContext": {
            "kind": authoring_view["kind"],
            "truthRole": authoring_view["truthRole"],
            "coordinateCount": len(authoring_view["coordinateProfile"]["coordinates"]),
            "representationMode": authoring_view["representationProfile"]["retrieval"]["mode"],
            "crossLanguageTranslationByAtlas": authoring_view["representationProfile"]["retrieval"]["crossLanguageTranslationByAtlas"],
            "semanticSimilarityByAtlas": authoring_view["representationProfile"]["retrieval"]["semanticSimilarityByAtlas"],
        },
        "researchStart": {
            "status": research_receipt["status"],
            "candidateCount": first_look["candidateCount"] if isinstance(first_look, dict) else 0,
            "topCandidate": top,
            "inspection": research_view.get("inspection"),
            "epistemicGuard": research_view["epistemicGuard"],
            "claims": research_view["claims"],
        },
        "adjudication": adjudication,
        "adjudicationTelemetry": adjudication_telemetry,
        "runtimeJobIds": owner_jobs,
        "ownerReadCount": len(owner_jobs),
        "providerModelCallCount": 2,
        "providerDomainToolCallCount": 0,
        "applicationGeneratedQueryVariant": False,
        "atlasGeneratedQueryVariant": False,
        "semanticSimilarityUsed": False,
        "crossLanguageTranslationByAtlas": False,
        "externalWritePerformed": False,
    }
    validate_json_value(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--atlas-workspace", required=True)
    parser.add_argument("--secret", type=Path, default=Path("/root/.config/ordivon/secrets/deepseek.json"))
    parser.add_argument("--runtime-endpoint", default="http://127.0.0.1:8897/mcp")
    parser.add_argument("--runtime-environment-file", type=Path, default=Path("/etc/ordivon/ordivon-runtime.env"))
    parser.add_argument("--runtime-scripts", type=Path, default=Path("/root/projects/ordivon-runtime/scripts"))
    args = parser.parse_args()
    receipt = run_episode(
        intent=args.intent,
        label=args.label,
        atlas_workspace=args.atlas_workspace,
        secret=args.secret,
        runtime_scripts=args.runtime_scripts,
        runtime_environment_file=args.runtime_environment_file,
        runtime_endpoint=args.runtime_endpoint,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

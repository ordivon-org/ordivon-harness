#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from ordivon_harness.api import (
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    HarnessAgentRun,
    HarnessBoundReference,
    HarnessPrivacyPolicy,
    HarnessRunContract,
    decode_structured_completion_result,
)
from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.structured_result_conformance import (
    LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1,
    validate_structured_result_schema_policy,
)

APPLICATION = Path(__file__).resolve().parent / "atlas_research_start_application.py"
spec = importlib.util.spec_from_file_location("atlas_research_start_application_live", APPLICATION)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load Atlas application from {APPLICATION}")
atlas_app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = atlas_app
spec.loader.exec_module(atlas_app)

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

CANDIDATE_SELECTION_COMPLETION: dict[str, JsonValue] = {
    "mode": "structured-result-v1",
    "resultKind": "atlas-bounded-candidate-selection",
    "conformancePolicy": LOCAL_JSON_SCHEMA_DRAFT_2020_12_PROFILE_V1,
    "resultSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "selectedRank": {"type": "integer", "minimum": 0, "maximum": 4},
            "reason": {"type": "string", "minLength": 1, "maxLength": 3000},
        },
        "required": ["selectedRank", "reason"],
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
    created_at_ms = time.time_ns() // 1_000_000
    context_digest = canonical_digest(context)
    contract = HarnessRunContract(
        harness_run_id=f"harness-run:atlas-multilingual-current-{label}",
        harness_implementation_id="ordivon-harness@atlas-multilingual-current-dogfood",
        caller_id="caller:atlas-multilingual-current-dogfood",
        caller_run_ref=f"episode:{label}:sequence:{sequence}",
        objective_ref=HarnessBoundReference(
            f"objective:atlas-multilingual-current-{label}",
            "objective",
            canonical_digest({"label": label, "sequence": sequence, "messages": list(messages[:1])}),
        ),
        context_refs=(
            HarnessBoundReference(
                f"context:atlas-multilingual-current-{label}",
                "context",
                context_digest,
            ),
        ),
        provider_id="provider:deepseek",
        adapter_id=DeepSeekTurnAdapter.adapter_id,
        requested_model_id=settings.model,
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=NO_TOOL_AGENT_GRANT_DIGEST,
        budget={
            "maxModelCalls": 3,
            "maxToolCalls": 0,
            "maxObservationBytes": 0,
            "maxWallTimeMs": 120000,
            "maxTotalTokens": 24000,
            "maxModelRetries": 1,
            "maxToolCorrections": 0,
            "maxConclusionCorrections": 2,
            "maxObservationOnlyTurns": 0,
            "maxNoProgressTurns": 2,
        },
        completion_contract=completion,
        system_manifest_ref=HarnessBoundReference(
            f"manifest:atlas-multilingual-current-{label}",
            "system-manifest",
            canonical_digest(
                {
                    "surface": "no-domain-tools-structured-result",
                    "completionKind": completion.get("resultKind"),
                    "conclusionCorrection": "harness-native-bounded",
                }
            ),
        ),
        created_at_ms=created_at_ms,
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=False,
        ),
    )
    with tempfile.TemporaryDirectory(prefix=f"atlas-{sequence}-") as directory:
        run = HarnessAgentRun.create(
            Path(directory) / "state",
            contract,
            lambda active_contract: DeepSeekTurnAdapter(
                settings,
                completion_contract=active_contract.completion_contract,
            ),
        )
        execution = run.run(messages)
        result = execution.loop_result
        if result.conclusion is None:
            raise RuntimeError(
                f"structured Harness Agent Run omitted conclusion: {result.stop_code.value}"
            )
        value = decode_structured_completion_result(contract, result.conclusion)
        if not isinstance(value, dict):
            raise TypeError("structured result must be an object")
        telemetry: dict[str, JsonValue] = {
            "executionMode": "supported-harness-agent-run",
            "harnessRunId": contract.harness_run_id,
            "stopCode": result.stop_code.value,
            "modelCalls": result.model_calls,
            "toolCalls": result.tool_calls,
            "conclusionCorrections": result.usage.get("conclusionCorrections", 0),
            "toolCorrections": result.usage.get("toolCorrections", 0),
            "usage": result.usage,
            "traceDigest": canonical_digest(result.trace.to_dict()),
            "domainToolCalls": 0,
            "completionContractDigest": canonical_digest(dict(contract.completion_contract)),
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
    fixed_queries: list[str] | None = None,
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
    if fixed_queries is None:
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
        query_authorship_source = "fresh-agent"
        provider_model_calls = 3
    else:
        queries = list(atlas_app._query_variants(query=None, queries=fixed_queries))
        query_result = {
            "queries": queries,
            "reason": "Frozen caller-supplied variants from a prior source-fenced episode isolate candidate-selection behavior.",
        }
        query_telemetry = {
            "source": "caller-frozen-prior-episode",
            "domainToolCalls": 0,
            "providerModelCallPerformed": False,
        }
        query_authorship_source = "caller-frozen-prior-episode"
        provider_model_calls = 2

    first_look_receipt = atlas_app.run_atlas_first_look_stage_application(
        runtime,
        atlas_workspace_id=atlas_workspace,
        queries=queries,
        limit=4,
        request_prefix=f"atlas-multilingual-current-{label}",
        consumer_episode_ref=episode_ref,
        consumer_class="dogfood",
    )
    first_look_view = first_look_receipt["modelView"]
    selection, selection_telemetry = _structured_turn(
        settings,
        label=f"{label}-candidate-selection",
        sequence=2,
        context={
            "intent": intent,
            "agentAuthoredQueries": queries,
            "boundedFirstLook": first_look_view,
        },
        completion=CANDIDATE_SELECTION_COMPLETION,
        messages=(
            {
                "role": "system",
                "content": (
                    "You are a fresh caller-side research consumer after one bounded Atlas first-look. "
                    "Choose the single bounded candidate most worth exact inspection for the caller's "
                    "research intent, using only the candidate metadata/excerpts shown. Return rank 0 only "
                    "if no bounded candidate is worth inspecting. Ranking is lexical and non-authoritative; "
                    "you own this semantic selection. Do not infer semantic equivalence or novelty, do not "
                    "request requery, and do not invent paths or candidate identities."
                ),
            },
            {"role": "user", "content": "CALLER_RESEARCH_INTENT:\n" + intent},
            {
                "role": "user",
                "content": "ATLAS_BOUNDED_FIRST_LOOK:\n"
                + json.dumps(first_look_view, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
        ),
    )
    selected_rank = selection.get("selectedRank")
    candidates = first_look_view.get("candidates")
    if type(selected_rank) is not int or not isinstance(candidates, list):
        raise TypeError("candidate selection result or first-look candidate list is invalid")
    if selected_rank < 0 or selected_rank > len(candidates):
        raise RuntimeError("candidate selection escaped the bounded first-look set")
    inspection_receipt = None
    inspection_view = None
    if selected_rank:
        inspection_receipt = atlas_app.run_atlas_candidate_inspection_stage_application(
            runtime,
            atlas_workspace_id=atlas_workspace,
            first_look_receipt=first_look_receipt,
            selected_rank=selected_rank,
            request_prefix=f"atlas-multilingual-current-{label}",
            consumer_episode_ref=episode_ref,
            consumer_class="dogfood",
        )
        inspection_view = inspection_receipt["modelView"]
    adjudication, adjudication_telemetry = _structured_turn(
        settings,
        label=f"{label}-adjudication",
        sequence=3,
        context={
            "intent": intent,
            "agentAuthoredQueries": queries,
            "boundedFirstLook": first_look_view,
            "agentCandidateSelection": selection,
            "ownerCandidateInspection": inspection_view,
        },
        completion=ADJUDICATION_COMPLETION,
        messages=(
            {
                "role": "system",
                "content": (
                    "You are the caller-side research consumer after a bounded Atlas first-look and, "
                    "when selected, one exact owner candidate inspection. Judge only whether the available "
                    "non-authoritative prior-work evidence is substantial enough to consume before opening "
                    "new research, or whether more input is needed. Candidate presence/inspection does not "
                    "establish semantic equivalence; absence does not establish novelty. You may not grant "
                    "research admission. Submit only the structured adjudication result."
                ),
            },
            {"role": "user", "content": "CALLER_RESEARCH_INTENT:\n" + intent},
            {
                "role": "user",
                "content": "ATLAS_BOUNDED_FIRST_LOOK:\n"
                + json.dumps(first_look_view, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
            {
                "role": "user",
                "content": "AGENT_CANDIDATE_SELECTION:\n"
                + json.dumps(selection, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
            {
                "role": "user",
                "content": "ATLAS_SELECTED_CANDIDATE_INSPECTION:\n"
                + json.dumps(inspection_view, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
        ),
    )
    if (
        adjudication.get("semanticEquivalenceEstablished") is not False
        or adjudication.get("noveltyEstablished") is not False
        or adjudication.get("researchAdmissionGranted") is not False
    ):
        raise RuntimeError("caller adjudication inflated Atlas epistemic standing")

    top = candidates[0] if candidates else None
    selected_candidate = (
        candidates[selected_rank - 1]
        if selected_rank and selected_rank <= len(candidates)
        else None
    )
    owner_jobs = (
        _owner_job_ids(authoring_receipt)
        + _owner_job_ids(first_look_receipt)
        + ([] if inspection_receipt is None else _owner_job_ids(inspection_receipt))
    )
    receipt: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.atlas-multilingual-current-dogfood",
        "label": label,
        "intent": intent,
        "agentAuthoredQueries": list(queries),
        "queryAuthorshipReason": query_result["reason"],
        "queryAuthorshipSource": query_authorship_source,
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
            "status": first_look_receipt["status"],
            "candidateCount": len(candidates),
            "topCandidate": top,
            "candidateSelection": selection,
            "candidateSelectionTelemetry": selection_telemetry,
            "selectedCandidate": selected_candidate,
            "inspection": inspection_view,
            "epistemicGuard": first_look_view["epistemicGuard"],
            "claims": first_look_view["claims"],
        },
        "adjudication": adjudication,
        "adjudicationTelemetry": adjudication_telemetry,
        "runtimeJobIds": owner_jobs,
        "ownerReadCount": len(owner_jobs),
        "providerModelCallCount": provider_model_calls,
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
    parser.add_argument("--fixed-query-variant", action="append", dest="fixed_queries")
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
        fixed_queries=args.fixed_queries,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

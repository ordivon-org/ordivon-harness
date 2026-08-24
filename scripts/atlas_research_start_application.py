#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Protocol

from anc_canonical import validate_json_value

APPLICATION_REVISION = "atlas-research-start-application-v2"
CONSUMER_CLASSES = frozenset({"ordinary", "audit", "dogfood", "test"})
_OWNER_STDOUT_LIMIT_BYTES = 262_144
_ARTIFACT_READ_MAX_BYTES = 1_048_576


class RuntimeClient(Protocol):
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


def _text(value: object, label: str, *, max_bytes: int = 2_048) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def application_foreign_references(
    consumer_episode_ref: str,
    consumer_class: str,
    *,
    phase: str,
) -> list[dict[str, str]]:
    episode = _text(consumer_episode_ref, "consumer episode ref", max_bytes=300)
    if consumer_class not in CONSUMER_CLASSES:
        raise ValueError(f"consumer class must be one of {sorted(CONSUMER_CLASSES)}")
    phase_id = _text(phase, "application phase", max_bytes=120)
    return [
        {
            "namespace": "ordivon.application",
            "type": "application",
            "id": "atlas-research-start",
            "generation": APPLICATION_REVISION,
        },
        {
            "namespace": "ordivon.application",
            "type": "application_phase",
            "id": phase_id,
        },
        {
            "namespace": "ordivon.application",
            "type": "consumer_class",
            "id": consumer_class,
        },
        {
            "namespace": "ordivon.application",
            "type": "consumer_episode",
            "id": episode,
        },
    ]


def _complete_stdout(
    client: RuntimeClient,
    result: dict[str, Any],
    *,
    phase: str,
) -> str:
    stdout = result.get("stdoutTail")
    artifacts = result.get("artifacts")
    stdout_artifacts = (
        [
            artifact
            for artifact in artifacts
            if isinstance(artifact, dict) and artifact.get("kind") == "stdout"
        ]
        if isinstance(artifacts, list)
        else []
    )
    if len(stdout_artifacts) > 1:
        raise RuntimeError(f"Atlas {phase} Runtime result has multiple stdout artifacts")
    if not stdout_artifacts:
        if not isinstance(stdout, str) or not stdout.strip():
            raise RuntimeError(f"Atlas {phase} Runtime result omitted owner stdout")
        return stdout

    artifact = stdout_artifacts[0]
    dropped_bytes = artifact.get("droppedBytes")
    if artifact.get("truncated") is True or (
        isinstance(dropped_bytes, int) and dropped_bytes > 0
    ):
        raise RuntimeError(f"Atlas {phase} stdout exceeded runner retention bound")
    retained_bytes = artifact.get("retainedBytes")
    tail_bytes = len(stdout.encode("utf-8")) if isinstance(stdout, str) else 0
    if (
        isinstance(retained_bytes, int)
        and retained_bytes <= tail_bytes
        and isinstance(stdout, str)
        and stdout.strip()
    ):
        return stdout

    job_id = result.get("jobId")
    artifact_id = artifact.get("artifactId")
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError(f"Atlas {phase} Runtime result omitted Job identity")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise RuntimeError(f"Atlas {phase} Runtime result omitted stdout Artifact identity")
    chunks: list[str] = []
    offset = 0
    while True:
        chunk = client.call_tool(
            "artifact.read",
            {
                "jobId": job_id,
                "artifactId": artifact_id,
                "offset": offset,
                "maxBytes": _ARTIFACT_READ_MAX_BYTES,
            },
        )
        content = chunk.get("content")
        if not isinstance(content, str):
            raise TypeError(f"Atlas {phase} stdout Artifact read omitted content")
        chunks.append(content)
        if chunk.get("eof") is True:
            break
        next_offset = chunk.get("nextOffset")
        if not isinstance(next_offset, int) or next_offset <= offset:
            raise RuntimeError(f"Atlas {phase} stdout Artifact read did not advance")
        offset = next_offset
    complete = "".join(chunks)
    if not complete.strip():
        raise RuntimeError(f"Atlas {phase} stdout Artifact was empty")
    if isinstance(retained_bytes, int) and len(complete.encode("utf-8")) != retained_bytes:
        raise RuntimeError(f"Atlas {phase} stdout Artifact byte length mismatched Runtime")
    return complete


def _terminal_result(
    client: RuntimeClient,
    request: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    result = client.call_tool("workspace.exec", request)
    if result.get("executionTerminal") is not True:
        job_id = result.get("jobId")
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeError(f"Atlas {phase} Runtime dispatch omitted Job identity")
        result = client.call_tool(
            "task.observe",
            {
                "jobId": job_id,
                "waitMs": 30000,
                "waitUntil": "terminal",
                "stdoutTailBytes": 65536,
                "stderrTailBytes": 16384,
            },
        )
    if result.get("executionTerminal") is not True:
        raise RuntimeError(f"Atlas {phase} Runtime Job did not reach terminal state")
    if result.get("executionDisposition") != "succeeded":
        raise RuntimeError(
            f"Atlas {phase} Runtime execution did not succeed: "
            f"{result.get('executionDisposition')}"
        )
    if result.get("semanticCompletionEvaluated") is not False:
        raise RuntimeError("Runtime must not claim Atlas semantic completion")
    return result


def _owner_json_exec(
    client: RuntimeClient,
    *,
    atlas_workspace_id: str,
    args: list[str],
    request_id: str,
    phase: str,
    references: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = {
        "clientRequestId": request_id,
        "execution": {
            "workspaceId": _text(atlas_workspace_id, "Atlas Workspace", max_bytes=300),
            "cwdRelative": ".",
            "executable": "/usr/bin/python3",
            "args": args,
            "env": {"PYTHONPATH": "src"},
            "timeoutMs": 30000,
            "stdoutLimitBytes": _OWNER_STDOUT_LIMIT_BYTES,
            "stderrLimitBytes": 16384,
            "foreignReferences": references,
        },
        "waitMs": 30000,
        "stdoutTailBytes": 65536,
        "stderrTailBytes": 16384,
    }
    result = _terminal_result(client, request, phase=phase)
    stdout = _complete_stdout(client, result, phase=phase)
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Atlas {phase} emitted non-JSON owner stdout") from error
    if not isinstance(value, dict):
        raise TypeError(f"Atlas {phase} owner result must be an object")
    return value, result


def _require_non_authoritative_claims(value: dict[str, Any], *, phase: str) -> None:
    claims = value.get("claims")
    if not isinstance(claims, dict):
        raise TypeError(f"Atlas {phase} result omitted claims")
    if (
        claims.get("semanticEquivalenceInferred") is not False
        or claims.get("noveltyStanding") != "UNKNOWN_CALLER_MUST_ADJUDICATE"
        or claims.get("researchAdmissionGranted") is not False
        or claims.get("ownerTruthMinted") is not False
        or ("callerIntentTranslated" in claims and claims.get("callerIntentTranslated") is not False)
        or ("queryVariantGenerated" in claims and claims.get("queryVariantGenerated") is not False)
        or (
            "queryVariantsSemanticallyEquivalent" in claims
            and claims.get("queryVariantsSemanticallyEquivalent") is not False
        )
    ):
        raise RuntimeError(f"Atlas {phase} result violated non-authoritative standing")


def _compact_candidate(value: object, rank: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Atlas first-look candidate must be an object")
    path = _text(value.get("path"), "Atlas candidate path", max_bytes=2_048)
    locator = _text(value.get("locator"), "Atlas candidate locator", max_bytes=2_048)
    excerpt = value.get("excerpt")
    result = {
        "rank": rank,
        "path": path,
        "locator": locator,
        "sourceClass": value.get("sourceClass"),
        "truthRole": value.get("truthRole"),
        "score": value.get("score"),
        "excerpt": excerpt if isinstance(excerpt, str) else None,
    }
    for field in ("bestVariantIndex", "bestVariantRank", "matchedVariantIndexes"):
        if field in value:
            result[field] = value.get(field)
    return result


def _query_variants(
    *,
    query: str | None,
    queries: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    if query is not None and queries is not None:
        raise ValueError("provide either query or queries, not both")
    if query is not None:
        return (_text(query, "research-start query"),)
    if not isinstance(queries, (list, tuple)) or not 1 <= len(queries) <= 4:
        raise ValueError("research-start queries must contain one to four variants")
    normalized: list[str] = []
    for value in queries:
        item = _text(value, "research-start query variant")
        if item not in normalized:
            normalized.append(item)
    if not normalized:
        raise ValueError("research-start requires at least one distinct query variant")
    return tuple(normalized)


def run_atlas_query_authoring_context_application(
    client: RuntimeClient,
    *,
    atlas_workspace_id: str,
    request_prefix: str,
    consumer_episode_ref: str,
    consumer_class: str,
) -> dict[str, Any]:
    request_prefix = _text(request_prefix, "request prefix", max_bytes=300)
    context, runtime = _owner_json_exec(
        client,
        atlas_workspace_id=atlas_workspace_id,
        args=["-m", "ordivon_atlas.cli", "retrieval-authoring-context"],
        request_id=f"{request_prefix}-atlas-retrieval-authoring-context",
        phase="retrieval-authoring-context",
        references=application_foreign_references(
            consumer_episode_ref, consumer_class, phase="retrieval-authoring-context"
        ),
    )
    if context.get("kind") != "ordivon.atlas-retrieval-authoring-context-experimental":
        raise RuntimeError("Atlas retrieval authoring context kind differs")
    _require_non_authoritative_claims(context, phase="retrieval-authoring-context")
    if context.get("truthRole") != "mechanical-retrieval-authoring-context-not-query-or-semantic-truth":
        raise RuntimeError("Atlas retrieval authoring context truth role differs")
    representation = context.get("representationProfile")
    coordinates = context.get("coordinateProfile")
    if not isinstance(representation, dict) or not isinstance(coordinates, dict):
        raise TypeError("Atlas retrieval authoring context omitted owner profiles")
    retrieval = representation.get("retrieval")
    representation_claims = representation.get("claims")
    coordinate_selection = coordinates.get("selection")
    coordinate_rows = coordinates.get("coordinates")
    coordinate_claims = coordinates.get("claims")
    if (
        not isinstance(retrieval, dict)
        or not isinstance(representation_claims, dict)
        or not isinstance(coordinate_selection, dict)
        or not isinstance(coordinate_rows, list)
        or not isinstance(coordinate_claims, dict)
    ):
        raise TypeError("Atlas retrieval authoring context profile shape differs")
    if (
        retrieval.get("queryExpansionByAtlas") is not False
        or retrieval.get("crossLanguageTranslationByAtlas") is not False
        or retrieval.get("semanticSimilarityByAtlas") is not False
        or representation_claims.get("callerIntentTranslated") is not False
        or representation_claims.get("queryVariantGenerated") is not False
        or representation_claims.get("queryVariantsSemanticallyEquivalent") is not False
        or representation_claims.get("semanticEquivalenceInferred") is not False
        or representation_claims.get("researchAdmissionGranted") is not False
        or representation_claims.get("ownerTruthMinted") is not False
        or coordinate_selection.get("taskConditioned") is not False
        or coordinate_selection.get("semanticRankingPerformed") is not False
        or coordinate_claims.get("callerIntentTranslated") is not False
        or coordinate_claims.get("queryVariantGenerated") is not False
        or coordinate_claims.get("coordinatesSemanticallyEquivalentToIntent") is not False
        or coordinate_claims.get("semanticEquivalenceInferred") is not False
        or coordinate_claims.get("researchAdmissionGranted") is not False
        or coordinate_claims.get("ownerTruthMinted") is not False
    ):
        raise RuntimeError("Atlas retrieval authoring context exceeded mechanical authority")
    receipt = {
        "schemaVersion": 1,
        "kind": "ordivon.application.atlas-query-authoring-context-receipt",
        "revision": APPLICATION_REVISION,
        "consumerProvenance": {
            "truthRole": "caller-application-provenance-claim",
            "episodeRef": consumer_episode_ref,
            "consumerClass": consumer_class,
        },
        "ownerCall": {
            "phase": "retrieval-authoring-context",
            "runtimeJobId": runtime.get("jobId"),
            "runtimeAttemptId": runtime.get("attemptId"),
            "runtimeStatus": runtime.get("status"),
        },
        "modelView": {
            "schemaVersion": 0,
            "kind": "ordivon.application.atlas-query-authoring-context-model-view",
            "truthRole": "mechanical-owner-environment-for-caller-query-authoring",
            "representationProfile": representation,
            "coordinateProfile": coordinates,
            "authoringConstraints": [
                "Caller/Agent authors retrieval variants; Atlas did not translate the intent or generate queries.",
                "Use at most four distinct trimmed query variants.",
                "Retrieval coordinates are task-neutral handles, not semantic-equivalence claims.",
                "Search results remain candidates; absence does not establish novelty.",
            ],
            "claims": {
                "callerIntentTranslated": False,
                "queryVariantGeneratedByApplication": False,
                "semanticEquivalenceInferred": False,
                "researchAdmissionGranted": False,
                "ownerTruthMinted": False,
            },
        },
    }
    validate_json_value(receipt)
    return receipt


def run_atlas_research_start_application(
    client: RuntimeClient,
    *,
    atlas_workspace_id: str,
    query: str | None = None,
    queries: list[str] | tuple[str, ...] | None = None,
    limit: int,
    request_prefix: str,
    consumer_episode_ref: str,
    consumer_class: str,
) -> dict[str, Any]:
    variants = _query_variants(query=query, queries=queries)
    request_prefix = _text(request_prefix, "request prefix", max_bytes=300)
    if type(limit) is not int or not 1 <= limit <= 32:
        raise ValueError("Atlas first-look limit must be an integer from 1 to 32")
    batch = len(variants) > 1
    first_phase = "first-look-many" if batch else "first-look"
    first_args = (
        ["-m", "ordivon_atlas.cli", "first-look-many", *variants, "--limit", str(limit)]
        if batch
        else ["-m", "ordivon_atlas.cli", "first-look", variants[0], "--limit", str(limit)]
    )
    first, first_runtime = _owner_json_exec(
        client,
        atlas_workspace_id=atlas_workspace_id,
        args=first_args,
        request_id=f"{request_prefix}-atlas-{first_phase}",
        phase=first_phase,
        references=application_foreign_references(
            consumer_episode_ref, consumer_class, phase=first_phase
        ),
    )
    expected_kind = (
        "ordivon.atlas-prior-result-first-look-many-experimental"
        if batch
        else "ordivon.atlas-prior-result-first-look-experimental"
    )
    if first.get("kind") != expected_kind:
        raise RuntimeError("Atlas first-look result kind differs")
    _require_non_authoritative_claims(first, phase="first-look")
    candidates_raw = first.get("candidates")
    if not isinstance(candidates_raw, list):
        raise TypeError("Atlas first-look candidates must be an array")
    candidate_count = first.get("candidateCount")
    if type(candidate_count) is not int or candidate_count != len(candidates_raw):
        raise RuntimeError("Atlas first-look candidate count differs")
    candidates = [
        _compact_candidate(candidate, rank)
        for rank, candidate in enumerate(candidates_raw, start=1)
    ]

    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": "ordivon.application.atlas-research-start-receipt",
        "revision": APPLICATION_REVISION,
        "status": "completed_no_bounded_candidate",
        "consumerProvenance": {
            "truthRole": "caller-application-provenance-claim",
            "episodeRef": consumer_episode_ref,
            "consumerClass": consumer_class,
            "adoptionProven": False,
            "benefitProven": False,
        },
        "ownerCalls": [
            {
                "phase": first_phase,
                "runtimeJobId": first_runtime.get("jobId"),
                "runtimeAttemptId": first_runtime.get("attemptId"),
                "runtimeStatus": first_runtime.get("status"),
            }
        ],
        "firstLook": {
            "query": first.get("query") if not batch else None,
            "queryVariants": first.get("queryVariants") if batch else [first.get("query")],
            "candidateCount": candidate_count,
            "candidates": candidates,
            "projectionHealth": first.get("projectionHealth"),
            "claims": first.get("claims"),
        },
        "inspection": None,
    }

    if candidates:
        top_raw = candidates_raw[0]
        top = candidates[0]
        inspection_query = variants[0]
        inspection_limit = limit
        if batch:
            best_variant_index = top_raw.get("bestVariantIndex")
            if type(best_variant_index) is not int or not 0 <= best_variant_index < len(variants):
                raise RuntimeError("Atlas batch rank-1 candidate omitted valid bestVariantIndex")
            inspection_query = variants[best_variant_index]
            inspection_limit = 32
        inspection, inspection_runtime = _owner_json_exec(
            client,
            atlas_workspace_id=atlas_workspace_id,
            args=[
                "-m",
                "ordivon_atlas.cli",
                "inspect-candidate",
                inspection_query,
                top["path"],
                top["locator"],
                "--limit",
                str(inspection_limit),
            ],
            request_id=f"{request_prefix}-atlas-inspect-candidate",
            phase="inspect-candidate",
            references=application_foreign_references(
                consumer_episode_ref, consumer_class, phase="inspect-candidate"
            ),
        )
        if inspection.get("kind") != "ordivon.atlas-prior-result-candidate-inspection-experimental":
            raise RuntimeError("Atlas candidate inspection result kind differs")
        _require_non_authoritative_claims(inspection, phase="inspect-candidate")
        inspected_candidate = inspection.get("candidate")
        if not isinstance(inspected_candidate, dict):
            raise TypeError("Atlas candidate inspection omitted candidate identity")
        for field in ("path", "locator"):
            if inspected_candidate.get(field) != top_raw.get(field):
                raise RuntimeError(f"Atlas inspected candidate {field} differs from rank-1 first-look")
        receipt["status"] = "completed_rank1_candidate_inspected"
        receipt["inspection"] = {
            "selectedBy": "owner-first-look-rank-1-policy",
            "inspectionQuery": inspection_query,
            "inspectionLimit": inspection_limit,
            "rank": 1,
            "candidate": top,
            "contentBytes": inspection.get("contentBytes"),
            "contentDigest": inspection.get("contentDigest"),
            "content": inspection.get("content"),
            "projectionHealth": inspection.get("projectionHealth"),
            "claims": inspection.get("claims"),
        }
        receipt["ownerCalls"].append(
            {
                "phase": "inspect-candidate",
                "runtimeJobId": inspection_runtime.get("jobId"),
                "runtimeAttemptId": inspection_runtime.get("attemptId"),
                "runtimeStatus": inspection_runtime.get("status"),
            }
        )

    top_candidate = candidates[0] if candidates else None
    alternatives = [
        {"rank": item["rank"], "path": item["path"], "score": item["score"]}
        for item in candidates[1:]
    ]
    inspection_view = None
    if receipt["inspection"] is not None:
        inspection_receipt = receipt["inspection"]
        inspection_view = {
            "rank": inspection_receipt["rank"],
            "inspectionQuery": inspection_receipt["inspectionQuery"],
            "contentBytes": inspection_receipt["contentBytes"],
            "contentDigest": inspection_receipt["contentDigest"],
            "content": inspection_receipt["content"],
        }
    receipt["modelView"] = {
        "schemaVersion": 0,
        "kind": "ordivon.application.atlas-research-start-model-view",
        "intent": "atlas.prior-result-recovery-and-caller-adjudication",
        "firstLook": {
            "query": receipt["firstLook"]["query"],
            "queryVariants": receipt["firstLook"]["queryVariants"],
            "candidateCount": receipt["firstLook"]["candidateCount"],
            "topCandidate": top_candidate,
            "alternatives": alternatives,
            "projectionHealth": receipt["firstLook"]["projectionHealth"],
            "fullCandidateDetailsRetainedInReceipt": True,
        },
        "inspection": inspection_view,
        "epistemicGuard": {
            "candidateSetExhaustive": False,
            "candidatePresenceDoesNotEstablishSemanticEquivalence": True,
            "candidateAbsenceDoesNotEstablishNovelty": True,
            "rank1InspectionDoesNotEstablishSemanticEquivalence": True,
            "requiredCallerAdjudication": ["semantic equivalence", "research admission"],
        },
        "claims": {
            "ownerTruthMinted": False,
            "candidateRankingChanged": False,
            "semanticEquivalenceInferred": False,
            "researchAdmissionGranted": False,
            "noveltyStanding": "UNKNOWN_CALLER_MUST_ADJUDICATE",
            "requeryFreedomWithdrawnAfterFirstLook": True,
            "queryVariantsGeneratedByApplication": False,
            "queryVariantsSemanticallyEquivalent": False,
        },
    }
    validate_json_value(receipt)
    return receipt


def _runtime_client(runtime_scripts: Path, environment_file: Path, endpoint: str) -> RuntimeClient:
    probe = runtime_scripts / "mcp_probe.py"
    spec = importlib.util.spec_from_file_location("ordivon_runtime_mcp_probe_atlas_app", probe)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Runtime MCP client from {probe}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    environment = module.load_environment_file(environment_file)
    token = module.load_bearer_token(environment)
    return module.connect_compatible(
        endpoint,
        token,
        client_name="ordivon-atlas-research-start-application",
        timeout=10.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas-workspace", required=True)
    parser.add_argument("--query")
    parser.add_argument("--query-variant", action="append", dest="query_variants")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--request-prefix", required=True)
    parser.add_argument("--consumer-episode-ref", required=True)
    parser.add_argument("--consumer-class", choices=sorted(CONSUMER_CLASSES), required=True)
    parser.add_argument("--runtime-endpoint", default="http://127.0.0.1:8897/mcp")
    parser.add_argument("--runtime-environment-file", default="/etc/ordivon/ordivon-runtime.env")
    parser.add_argument("--runtime-scripts", default="/root/projects/ordivon-runtime/scripts")
    args = parser.parse_args()
    client = _runtime_client(
        Path(args.runtime_scripts), Path(args.runtime_environment_file), args.runtime_endpoint
    )
    receipt = run_atlas_research_start_application(
        client,
        atlas_workspace_id=args.atlas_workspace,
        query=args.query,
        queries=args.query_variants,
        limit=args.limit,
        request_prefix=args.request_prefix,
        consumer_episode_ref=args.consumer_episode_ref,
        consumer_class=args.consumer_class,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

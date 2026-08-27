#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
from typing import Any

from anc_canonical import canonical_digest

from ordivon_harness.capability_discovery import (
    CapabilityDescriptor,
    CapabilityDiscoveryQuery,
    CapabilityStanding,
    compile_capability_affordances,
    discover_capabilities,
)
from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.model import AgentToolDefinition, AgentTurnRequest

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus-v2-currentness.json"
EXPECTED_CORPUS_SHA256 = "6c0d95872fe57dff5334fe04ec570ea71a0f18c1d998553d24240b485d26378d"
COMMON_SYSTEM = (
    "Fresh Agent current-capability benchmark. Choose exactly one provided Runtime "
    "Tool as the first action; do not call submit_run_conclusion. Tool names are "
    "opaque. Static Tool descriptions establish capability semantics but not carrier "
    "currentness. Only an explicit current-standing projection, when supplied, may "
    "establish which otherwise-equivalent carrier is currently usable. Do not infer "
    "currentness from opaque identity or Tool order."
)


def load_corpus() -> dict[str, Any]:
    raw = CORPUS.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_CORPUS_SHA256:
        raise RuntimeError(f"v2 corpus digest differs: {actual}")
    value = json.loads(raw)
    if value.get("kind") != "ordivon.harness-fresh-agent-currentness-ab-corpus-v2":
        raise RuntimeError("unexpected v2 corpus kind")
    return value


def tools_for(case: dict[str, Any]) -> tuple[AgentToolDefinition, ...]:
    return tuple(
        AgentToolDefinition(
            name=item["toolName"],
            description=item["summary"],
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
        for item in case["tools"]
    )


def descriptors_for(case: dict[str, Any]) -> tuple[CapabilityDescriptor, ...]:
    return tuple(
        CapabilityDescriptor(
            capability_id=f"benchmark.{item['toolName']}",
            owner=f"owner:benchmark:{item['toolName']}",
            summary=item["summary"],
            source_ref=f"benchmark://source/{item['toolName']}",
            source_version="v2-frozen",
            action_kind="tool",
            action_name=item["toolName"],
            effect_class="BENCHMARK_SELECTION_ONLY",
            tags=tuple(item["tags"]),
            authority_requirements=("benchmark standing must be AVAILABLE",),
            currentness_requirements=("explicit benchmark standing required",),
            visibility="benchmark",
        )
        for item in case["tools"]
    )


def standings_for(case: dict[str, Any]) -> tuple[CapabilityStanding, ...]:
    return tuple(
        CapabilityStanding(
            f"benchmark.{item['toolName']}",
            item["standing"],
            evidence_refs=(f"benchmark-standing://{item['toolName']}",),
            reasons=(f"frozen v2 standing={item['standing']}",),
        )
        for item in case["tools"]
    )


def compile_trial(case: dict[str, Any], treatment: str) -> dict[str, Any]:
    all_tools = tools_for(case)
    descriptors = descriptors_for(case)
    query = CapabilityDiscoveryQuery(
        case["prompt"],
        terms=tuple(case["queryTerms"]),
        max_candidates=8,
    )
    candidates = discover_capabilities(descriptors, query)
    if len(candidates.candidates) != 8:
        raise AssertionError((case["caseId"], candidates.matched_count, len(candidates.candidates)))

    metadata = {item["toolName"]: item for item in case["tools"]}
    candidate_names = tuple(candidate.action_name for candidate in candidates.candidates)
    if case["targetTool"] not in candidate_names or case["twinTool"] not in candidate_names:
        raise AssertionError(f"target/twin not both retrieved: {case['caseId']}")
    if any(metadata[name]["semanticRole"].startswith("neutral-") for name in candidate_names):
        raise AssertionError(f"neutral candidate entered Top-8: {case['caseId']}")

    messages: list[dict[str, str]] = [{"role": "system", "content": COMMON_SYSTEM}]
    visible_tools = all_tools
    affordances = None

    if treatment == "B":
        compact = {
            "schemaVersion": 1,
            "kind": "candidate-navigation",
            "candidateTools": list(candidate_names),
            "claims": {
                "currentnessProven": False,
                "authorityGranted": False,
                "executionAdmitted": False,
            },
        }
        messages.append(
            {
                "role": "system",
                "content": (
                    "Task-conditioned candidate navigation follows. Candidate membership "
                    "does not establish currentness or availability. Choose from the full "
                    "admitted Tool surface using static semantics only. "
                    + json.dumps(compact, sort_keys=True, separators=(",", ":"))
                ),
            }
        )
    elif treatment == "C":
        standings = standings_for(case)
        affordances = compile_capability_affordances(
            candidates,
            descriptors,
            standings,
            admitted_action_names=tuple(tool.name for tool in all_tools),
        )
        selected = set(affordances.selected_action_names)
        visible_tools = tuple(tool for tool in all_tools if tool.name in selected)
        if case["targetTool"] not in selected:
            raise AssertionError(f"target not current-invokable: {case['caseId']}")
        if case["twinTool"] in selected:
            raise AssertionError(f"stale twin became current-invokable: {case['caseId']}")
        if len(visible_tools) < 2:
            raise AssertionError(f"C became one-Tool giveaway: {case['caseId']}")

        compact_rows = [
            {
                "tool": item.candidate.action_name,
                "standing": item.standing.standing,
                "canInvokeNow": item.can_invoke_now,
            }
            for item in affordances.affordances
        ]
        compact = {
            "schemaVersion": 1,
            "kind": "current-affordance",
            "candidates": compact_rows,
            "claims": {
                "authorityExpanded": False,
                "currentnessMintedByHarness": False,
                "candidateImpliesAvailability": False,
            },
        }
        messages.append(
            {
                "role": "system",
                "content": (
                    "Current standing supplied by the frozen benchmark follows. "
                    "Use standing and canInvokeNow to distinguish semantically equivalent "
                    "carriers. BLOCKED/UNKNOWN candidates are context only and are not "
                    "Provider-visible Runtime Tools. "
                    + json.dumps(compact, sort_keys=True, separators=(",", ":"))
                ),
            }
        )
    elif treatment != "A":
        raise ValueError(treatment)

    messages.append({"role": "user", "content": case["prompt"]})
    request = AgentTurnRequest(
        harness_run_id=f"harness-run:fresh-v2:{case['caseId']}:{treatment}",
        turn_id=f"turn:fresh-v2:{case['caseId']}:{treatment}:1",
        sequence=1,
        assignment_id=f"assignment:fresh-v2:{case['caseId']}:{treatment}",
        context_digest=canonical_digest(messages),
        tool_catalog_digest=canonical_digest([tool.to_dict() for tool in visible_tools]),
        messages=tuple(messages),
        tools=visible_tools,
        remaining_budget={
            "modelCalls": 1,
            "modelRetries": 0,
            "toolCalls": 1,
            "wallTimeMs": 90_000,
            "observationOnlyTurns": 1,
            "noProgressTurns": 1,
        },
    )
    return {
        "request": request,
        "candidates": candidates,
        "affordances": affordances,
        "candidateNames": candidate_names,
        "visibleToolNames": tuple(tool.name for tool in visible_tools),
        "allTools": all_tools,
    }


def validate_corpus(value: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    target_lower = 0
    for case in value["cases"]:
        a = compile_trial(case, "A")
        b = compile_trial(case, "B")
        c = compile_trial(case, "C")
        if tuple(tool.to_dict() for tool in a["allTools"]) != tuple(
            tool.to_dict() for tool in b["allTools"]
        ):
            raise AssertionError("A/B Tool definitions differ")
        if a["visibleToolNames"] != b["visibleToolNames"]:
            raise AssertionError("A/B Tool authority differs")
        if not set(c["visibleToolNames"]).issubset(a["visibleToolNames"]):
            raise AssertionError("C expands authority")
        if case["targetTool"] not in c["visibleToolNames"]:
            raise AssertionError("C hides target")
        if case["twinTool"] in c["visibleToolNames"]:
            raise AssertionError("C exposes stale twin")
        if len(c["visibleToolNames"]) < 2:
            raise AssertionError("C one-Tool giveaway")
        metadata = {item["toolName"]: item for item in case["tools"]}
        if any(metadata[name]["standing"] != "AVAILABLE" for name in c["visibleToolNames"]):
            raise AssertionError("C exposes non-AVAILABLE Tool")
        target = metadata[case["targetTool"]]
        twin = metadata[case["twinTool"]]
        if target["summary"] != twin["summary"]:
            raise AssertionError("target/twin static semantics differ")
        if (case["targetTool"] < case["twinTool"]) != case["targetHasLowerOpaqueId"]:
            raise AssertionError("target order marker differs")
        target_lower += int(case["targetHasLowerOpaqueId"])
        rows.append(
            {
                "caseId": case["caseId"],
                "targetTool": case["targetTool"],
                "twinTool": case["twinTool"],
                "twinStanding": twin["standing"],
                "candidateCount": len(c["candidateNames"]),
                "cVisibleToolCount": len(c["visibleToolNames"]),
                "targetHasLowerOpaqueId": case["targetHasLowerOpaqueId"],
            }
        )
    if target_lower != 6:
        raise AssertionError("target/twin opaque ordering is not 6/6 balanced")
    for case in value["cases"]:
        treatments = sorted(
            item["treatment"]
            for item in value["trialOrder"]
            if item["caseId"] == case["caseId"]
        )
        if treatments != ["A", "B", "C"]:
            raise AssertionError(f"trial treatment coverage differs: {case['caseId']}")
    return {
        "status": "passed",
        "caseCount": len(rows),
        "trialCount": len(value["trialOrder"]),
        "targetLowerOpaqueIdCount": target_lower,
        "cases": rows,
    }


def run_live(output: Path) -> dict[str, Any]:
    value = load_corpus()
    validation = validate_corpus(value)
    settings = DeepSeekSettings.from_secret_file(
        timeout_seconds=60.0,
        max_output_tokens=128,
    )
    case_by_id = {case["caseId"]: case for case in value["cases"]}
    trials: list[dict[str, Any]] = []
    for ordinal, item in enumerate(value["trialOrder"], 1):
        case = case_by_id[item["caseId"]]
        treatment = item["treatment"]
        compiled = compile_trial(case, treatment)
        request = compiled["request"]
        adapter = DeepSeekTurnAdapter(settings)
        _, _, _, body = adapter._prepare_request(request)
        row: dict[str, Any] = {
            "ordinal": ordinal,
            "caseId": case["caseId"],
            "treatment": treatment,
            "targetTool": case["targetTool"],
            "twinTool": case["twinTool"],
            "targetHasLowerOpaqueId": case["targetHasLowerOpaqueId"],
            "candidateCount": len(compiled["candidateNames"]),
            "visibleToolCount": len(request.tools),
            "providerRequestBytes": len(body),
            "requestTokenUpperBound": adapter.request_token_upper_bound(request),
            "providerRequestDigest": adapter.provider_request_digest(request),
        }
        started = time.monotonic()
        try:
            result = adapter.invoke(request)
            row["latencyMs"] = round((time.monotonic() - started) * 1000, 3)
            row["status"] = "completed"
            row["modelCallId"] = result.model_call_id
            row["modelId"] = result.model_id
            row["rawResponseDigest"] = result.raw_response_digest
            row["finishReason"] = result.finish_reason
            row["usage"] = result.usage
            row["toolCallCount"] = len(result.tool_calls)
            row["selectedTools"] = [call.name for call in result.tool_calls]
            first = result.tool_calls[0].name if result.tool_calls else None
            row["firstTool"] = first
            row["currentTargetCorrect"] = first == case["targetTool"]
            row["staleTwinSelected"] = first == case["twinTool"]
            row["otherWrongSelection"] = first is not None and first not in {
                case["targetTool"],
                case["twinTool"],
            }
            row["noToolOrConclusion"] = first is None
            metadata = {tool["toolName"]: tool for tool in case["tools"]}
            row["selectedStanding"] = None if first is None else metadata[first]["standing"]
        except Exception as error:
            row["latencyMs"] = round((time.monotonic() - started) * 1000, 3)
            row["status"] = "provider_error"
            row["errorType"] = type(error).__name__
            row["error"] = str(error)[:1000]
        trials.append(row)
        partial = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-fresh-agent-currentness-ab-result-v2",
            "corpusSha256": EXPECTED_CORPUS_SHA256,
            "preregistrationSha256": value["preregistrationSha256"],
            "providerModel": settings.model,
            "status": "in_progress",
            "trials": trials,
        }
        output.write_text(json.dumps(partial, indent=2, sort_keys=True) + "\n")
    result = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-fresh-agent-currentness-ab-result-v2",
        "corpusSha256": EXPECTED_CORPUS_SHA256,
        "preregistrationSha256": value["preregistrationSha256"],
        "providerModel": settings.model,
        "validation": validation,
        "status": "completed",
        "trials": trials,
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    rows = result["trials"]
    treatments: dict[str, Any] = {}
    total_completed = sum(row["status"] == "completed" for row in rows)
    for treatment in ("A", "B", "C"):
        selected = [row for row in rows if row["treatment"] == treatment]
        completed = [row for row in selected if row["status"] == "completed"]

        def rate(key: str) -> float | None:
            if not completed:
                return None
            return round(sum(bool(row.get(key)) for row in completed) / len(completed), 6)

        def mean_usage(key: str) -> float | None:
            if not completed:
                return None
            return round(statistics.mean(row["usage"].get(key, 0) for row in completed), 3)

        treatments[treatment] = {
            "trials": len(selected),
            "completed": len(completed),
            "providerErrors": len(selected) - len(completed),
            "currentTargetAccuracy": rate("currentTargetCorrect"),
            "staleTwinSelectionRate": rate("staleTwinSelected"),
            "otherWrongSelectionRate": rate("otherWrongSelection"),
            "noToolOrConclusionRate": rate("noToolOrConclusion"),
            "meanProviderRequestBytes": (
                None
                if not completed
                else round(statistics.mean(row["providerRequestBytes"] for row in completed), 3)
            ),
            "meanPromptTokens": mean_usage("prompt_tokens"),
            "meanCompletionTokens": mean_usage("completion_tokens"),
            "meanTotalTokens": mean_usage("total_tokens"),
            "meanPromptCacheHitTokens": mean_usage("prompt_cache_hit_tokens"),
            "meanPromptCacheMissTokens": mean_usage("prompt_cache_miss_tokens"),
            "medianLatencyMs": (
                None
                if not completed
                else round(statistics.median(row["latencyMs"] for row in completed), 3)
            ),
            "meanLatencyMs": (
                None
                if not completed
                else round(statistics.mean(row["latencyMs"] for row in completed), 3)
            ),
            "zeroOrMultipleToolCallCount": sum(
                row.get("toolCallCount") != 1 for row in completed
            ),
        }

    a = treatments["A"]
    c = treatments["C"]
    accuracy_delta = (
        None
        if a["currentTargetAccuracy"] is None or c["currentTargetAccuracy"] is None
        else round(c["currentTargetAccuracy"] - a["currentTargetAccuracy"], 6)
    )
    complete_enough = total_completed >= 30
    positive = (
        complete_enough
        and c["completed"] >= 10
        and c["currentTargetAccuracy"] is not None
        and c["currentTargetAccuracy"] >= (10 / 12)
        and accuracy_delta is not None
        and accuracy_delta >= 0.25
        and c["staleTwinSelectionRate"] is not None
        and a["staleTwinSelectionRate"] is not None
        and c["staleTwinSelectionRate"] <= a["staleTwinSelectionRate"]
        and c["zeroOrMultipleToolCallCount"] == 0
    )
    classification = (
        "positive_currentness_dependent_gain"
        if positive
        else ("incomplete" if not complete_enough else "negative_or_insufficient")
    )
    return {
        "classification": classification,
        "completedCalls": total_completed,
        "requiredCompletedCalls": 30,
        "accuracyDeltaCMinusA": accuracy_delta,
        "thresholds": {
            "cCurrentTargetAccuracyMin": round(10 / 12, 6),
            "cAccuracyAdvantageMin": 0.25,
            "cCompletedMin": 10,
            "totalCompletedMin": 30,
            "cStaleTwinMustNotExceedA": True,
        },
        "treatments": treatments,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path, default=HERE / "result-v2-currentness.json")
    args = parser.parse_args()
    value = load_corpus()
    if args.validate_only:
        print(json.dumps(validate_corpus(value), indent=2, sort_keys=True))
        return 0
    result = run_live(args.output)
    summary = summarize(result)
    summary_path = args.output.with_name("summary-v2-currentness.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

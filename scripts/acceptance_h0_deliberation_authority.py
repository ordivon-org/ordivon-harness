from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value

from ordivon_harness.api import DeepSeekSettings, DeepSeekTurnAdapter, RunBudget
from ordivon_harness.domain_tools import (
    AgentToolDefinition,
    DomainToolCatalog,
    DomainToolLoopPlan,
    DomainToolLoopRunner,
    ToolObservation,
)
from ordivon_harness.ordivon.model import AgentTurnRequest


SCHEMA_VERSION = 1
EXPERIMENT_REVISION = "harness-native-deliberation-authority-h0-v1"
MODEL_REPLICATES_PER_TREATMENT = 2
CHOICES = ("atlas", "birch", "cobalt", "delta")
TASK: dict[str, JsonValue] = {
    "schemaVersion": 1,
    "kind": "ordivon.harness.h0-neutral-choice-task",
    "objective": "Choose the feasible candidate with the highest score.",
    "feasibilityRules": {
        "memoryMax": 16,
        "dependenciesMax": 2,
    },
    "scoreRule": "throughput - 3*latency - 2*retries",
    "candidates": [
        {
            "id": "atlas",
            "throughput": 98,
            "latency": 4,
            "retries": 3,
            "memory": 24,
            "dependencies": 1,
        },
        {
            "id": "birch",
            "throughput": 76,
            "latency": 5,
            "retries": 2,
            "memory": 12,
            "dependencies": 3,
        },
        {
            "id": "cobalt",
            "throughput": 68,
            "latency": 2,
            "retries": 2,
            "memory": 14,
            "dependencies": 2,
        },
        {
            "id": "delta",
            "throughput": 74,
            "latency": 5,
            "retries": 1,
            "memory": 15,
            "dependencies": 2,
        },
    ],
}
validate_json_value(TASK)


def _git_revision(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _candidate_rows(task: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    rows = task["candidates"]
    if not isinstance(rows, list):
        raise ValueError("H0 candidates must be a list")
    parsed: list[dict[str, JsonValue]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("H0 candidate must be an object")
        parsed.append(cast(dict[str, JsonValue], raw))
    return parsed


def score_table(task: dict[str, JsonValue] = TASK) -> list[dict[str, JsonValue]]:
    rules = task["feasibilityRules"]
    if not isinstance(rules, dict):
        raise ValueError("H0 feasibility rules must be an object")
    memory_max = int(cast(int, rules["memoryMax"]))
    dependencies_max = int(cast(int, rules["dependenciesMax"]))
    result: list[dict[str, JsonValue]] = []
    for row in _candidate_rows(task):
        candidate_id = str(row["id"])
        memory = int(cast(int, row["memory"]))
        dependencies = int(cast(int, row["dependencies"]))
        feasible = memory <= memory_max and dependencies <= dependencies_max
        score = (
            int(cast(int, row["throughput"]))
            - 3 * int(cast(int, row["latency"]))
            - 2 * int(cast(int, row["retries"]))
        )
        value: dict[str, JsonValue] = {
            "id": candidate_id,
            "feasible": feasible,
            "score": score,
        }
        validate_json_value(value)
        result.append(value)
    return result


def oracle_choice(task: dict[str, JsonValue] = TASK) -> str:
    feasible = [row for row in score_table(task) if row["feasible"] is True]
    if not feasible:
        raise ValueError("H0 has no feasible candidate")
    best_score = max(int(cast(int, row["score"])) for row in feasible)
    best = [str(row["id"]) for row in feasible if int(cast(int, row["score"])) == best_score]
    if len(best) != 1:
        raise ValueError(f"H0 oracle is not unique: {best}")
    return best[0]


CHOICE_TOOL = AgentToolDefinition(
    name="submit_choice",
    description=(
        "Record or replace your pending candidate choice for this neutral evaluation. "
        "This Tool reveals no evaluator score and performs no external effect."
    ),
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"choice": {"type": "string", "enum": list(CHOICES)}},
        "required": ["choice"],
    },
)


class ChoiceBridge:
    catalog = DomainToolCatalog(
        domain_id="domain:harness-native-deliberation-authority-h0",
        revision=EXPERIMENT_REVISION,
        tools=(CHOICE_TOOL,),
    )
    bridge_identity: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.h0-record-only-choice-bridge",
        "externalEffect": False,
        "evaluatorScoreVisible": False,
    }

    def __init__(self) -> None:
        self.revisions: list[str] = []

    def execute(self, call: Any, *, step_id: str) -> ToolObservation:
        if call.name != "submit_choice":
            raise ValueError(f"H0 unexpected Tool: {call.name}")
        arguments = call.arguments
        if not isinstance(arguments, dict) or set(arguments) != {"choice"}:
            raise ValueError("H0 submit_choice arguments differ from exact schema")
        choice = arguments.get("choice")
        if choice not in CHOICES:
            raise ValueError(f"H0 choice is invalid: {choice}")
        self.revisions.append(cast(str, choice))
        return ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="observed",
            structured_content={
                "choiceRecorded": True,
                "choiceRevision": len(self.revisions),
                "replacementAllowed": True,
                "externalEffectPerformed": False,
                "evaluatorScoreRevealed": False,
                "stepId": step_id,
            },
        )


@dataclass(frozen=True, slots=True)
class Equipment:
    secret: Path


def _settings(equipment: Equipment) -> DeepSeekSettings:
    return DeepSeekSettings.from_secret_file(
        equipment.secret,
        timeout_seconds=90.0,
        max_output_tokens=2048,
    )


def _task_message() -> str:
    return json.dumps(TASK, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _run_authority_phase(
    *,
    equipment: Equipment,
    label: str,
    prior_deliberation: dict[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    settings = _settings(equipment)
    adapter = DeepSeekTurnAdapter(settings)
    bridge = ChoiceBridge()
    runner = DomainToolLoopRunner(adapter, bridge)
    messages: list[dict[str, JsonValue]] = [
        {
            "role": "system",
            "content": (
                "This is a neutral Harness evaluation. Choose the unique feasible candidate with "
                "the highest score under the supplied rules. Carefully apply feasibility before "
                "comparing scores. submit_choice only records a pending choice; it reveals no score "
                "and has no external effect. You may call it again to replace an earlier choice. "
                "When your final recorded choice matches your considered decision, submit a concise "
                "candidate_completed conclusion."
            ),
        },
        {"role": "user", "content": _task_message()},
    ]
    if prior_deliberation is not None:
        messages.append(
            {
                "role": "user",
                "content": (
                    "PRIOR_NON_AUTHORITATIVE_SELF_DELIBERATION_RECORD\n"
                    + canonical_bytes(prior_deliberation).decode("utf-8")
                    + "\n\nThe record is your own earlier cognition, not evaluator truth and not a Tool choice. "
                    + "Re-check it against the unchanged task and now submit the choice you endorse."
                ),
            }
        )
    context_digest = canonical_digest(TASK)
    plan = DomainToolLoopPlan(
        harness_run_id=f"harness-run:h0-{label}",
        assignment_id=f"assignment:h0-{label}",
        context_digest=context_digest,
        initial_messages=tuple(messages),
        allowed_tools=("submit_choice",),
        budget=RunBudget(
            max_model_calls=3,
            max_tool_calls=3,
            max_observation_bytes=32768,
            max_wall_time_ms=120000,
            max_total_tokens=100000,
            max_model_retries=1,
            max_tool_corrections=1,
            max_observation_only_turns=1,
            max_no_progress_turns=2,
            max_model_observation_bytes=131072,
        ),
    )
    result = runner.run(plan)
    stop_code = str(getattr(result.stop_code, "value", result.stop_code))
    if stop_code != "candidate_completed":
        raise RuntimeError(f"H0 authority phase did not candidate_complete: {stop_code}")
    if result.conclusion is None:
        raise RuntimeError("H0 authority phase lacks conclusion")
    if not bridge.revisions:
        raise RuntimeError("H0 authority phase did not submit a choice")
    usage = cast(dict[str, JsonValue], dict(result.usage))
    effective = usage.get("effectiveModelIds")
    if isinstance(effective, list) and effective and any(x != adapter.model_id for x in effective):
        raise RuntimeError("H0 effective model differs from requested model")
    record: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.h0-authority-phase",
        "label": label,
        "contextDigest": context_digest,
        "priorDeliberationPresent": prior_deliberation is not None,
        "choiceRevisions": list(bridge.revisions),
        "finalChoice": bridge.revisions[-1],
        "trace": result.trace.to_dict(),
        "traceDigest": canonical_digest(result.trace.to_dict()),
        "usage": usage,
        "requestedModelId": str(adapter.model_id),
        "credentialScopeId": str(settings.credential_scope_id),
        "conclusionStatus": str(result.conclusion.status),
        "conclusionSummary": str(result.conclusion.summary),
        "externalEffectPerformed": False,
    }
    validate_json_value(record)
    return record


def _run_deliberation(
    *,
    equipment: Equipment,
    label: str,
) -> dict[str, JsonValue]:
    settings = _settings(equipment)
    adapter = DeepSeekTurnAdapter(settings)
    request = AgentTurnRequest(
        harness_run_id=f"harness-run:h0-deliberation-{label}",
        turn_id=f"turn:h0-deliberation-{label}:1",
        sequence=1,
        assignment_id=f"assignment:h0-deliberation-{label}",
        context_digest=canonical_digest(TASK),
        tool_catalog_digest=canonical_digest(
            {
                "schemaVersion": 1,
                "kind": "ordivon.harness.h0-no-domain-tools",
                "tools": [],
                "revision": EXPERIMENT_REVISION,
            }
        ),
        messages=(
            {
                "role": "system",
                "content": (
                    "This is a deliberation-only neutral evaluation. No domain Tool is available. "
                    "Apply feasibility rules first, calculate the score of each feasible candidate, "
                    "and state the one candidate you would choose later if submit_choice becomes "
                    "available. This conclusion is cognition only and records no choice."
                ),
            },
            {"role": "user", "content": _task_message()},
        ),
        tools=(),
        remaining_budget={"modelCalls": 1, "toolCalls": 0, "totalTokens": 100000},
    )
    result = adapter.invoke(request)
    if result.tool_calls:
        raise RuntimeError("H0 no-tool deliberation unexpectedly returned domain Tool calls")
    if result.conclusion is None or result.conclusion.status != "candidate_completed":
        raise RuntimeError("H0 no-tool deliberation did not candidate_complete")
    record: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.h0-non-authoritative-deliberation",
        "truthRole": "model-self-deliberation-not-evaluator-truth",
        "contextDigest": canonical_digest(TASK),
        "requestDigest": request.dispatch_digest,
        "resultDigest": result.digest,
        "summary": str(result.conclusion.summary),
        "summaryDigest": canonical_digest({"summary": str(result.conclusion.summary)}),
        "unresolvedUnknowns": [str(x) for x in result.conclusion.unresolved_unknowns],
        "domainToolsAvailable": False,
        "choiceRecorded": False,
        "externalEffectPerformed": False,
        "requestedModelId": str(adapter.model_id),
        "effectiveModelId": str(result.effective_model_id or adapter.model_id),
        "credentialScopeId": str(settings.credential_scope_id),
        "providerUsage": cast(dict[str, JsonValue], result.usage),
    }
    validate_json_value(record)
    return record


def _run_replicate(
    *,
    equipment: Equipment,
    treatment: str,
    replicate: int,
) -> dict[str, JsonValue]:
    label = f"{treatment}-r{replicate}"
    deliberation: dict[str, JsonValue] | None = None
    if treatment == "deliberation-first":
        deliberation = _run_deliberation(equipment=equipment, label=label)
    elif treatment != "immediate-tool":
        raise ValueError(f"unknown H0 treatment: {treatment}")
    authority = _run_authority_phase(
        equipment=equipment,
        label=label,
        prior_deliberation=deliberation,
    )
    record: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "treatment": treatment,
        "replicate": replicate,
        "deliberation": deliberation,
        "authority": authority,
        "correct": authority["finalChoice"] == oracle_choice(),
    }
    validate_json_value(record)
    return record


def _classify(baseline: list[dict[str, JsonValue]], treatment: list[dict[str, JsonValue]]) -> str:
    baseline_correct = [bool(x["correct"]) for x in baseline]
    treatment_correct = [bool(x["correct"]) for x in treatment]
    if all(baseline_correct) and all(treatment_correct):
        return "ordering-pressure-not-reproduced"
    if not all(baseline_correct) and all(treatment_correct):
        return "ordering-pressure-reproduced-in-sample"
    if not all(treatment_correct):
        return "deliberation-first-not-sufficient-in-sample"
    return "mixed"


def run(*, equipment: Equipment) -> dict[str, JsonValue]:
    oracle = oracle_choice()
    table = score_table()
    baseline = [
        _run_replicate(equipment=equipment, treatment="immediate-tool", replicate=i)
        for i in range(1, MODEL_REPLICATES_PER_TREATMENT + 1)
    ]
    treatment = [
        _run_replicate(equipment=equipment, treatment="deliberation-first", replicate=i)
        for i in range(1, MODEL_REPLICATES_PER_TREATMENT + 1)
    ]
    all_records = baseline + treatment
    requested_models = {
        str(cast(dict[str, JsonValue], x["authority"])["requestedModelId"])
        for x in all_records
    }
    scopes = {
        str(cast(dict[str, JsonValue], x["authority"])["credentialScopeId"])
        for x in all_records
    }
    gates = {
        "oracleUnique": oracle == "cobalt",
        "predeclaredReplicatesComplete": len(baseline) == len(treatment) == 2,
        "allAuthorityPhasesCompleted": all(
            cast(dict[str, JsonValue], x["authority"])["conclusionStatus"] == "candidate_completed"
            for x in all_records
        ),
        "noExternalEffects": all(
            cast(dict[str, JsonValue], x["authority"])["externalEffectPerformed"] is False
            for x in all_records
        ),
        "sameRequestedModelAcrossAllSamples": len(requested_models) == 1,
        "sameCredentialScopeAcrossAllSamples": len(scopes) == 1,
        "treatmentHasNoToolDeliberation": all(
            isinstance(x["deliberation"], dict)
            and cast(dict[str, JsonValue], x["deliberation"])["domainToolsAvailable"] is False
            and cast(dict[str, JsonValue], x["deliberation"])["choiceRecorded"] is False
            for x in treatment
        ),
        "baselineHasNoPriorDeliberation": all(x["deliberation"] is None for x in baseline),
    }
    if not all(gates.values()):
        raise RuntimeError(f"H0 mechanical gate failed: {gates}")
    receipt: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.deliberation-authority-h0",
        "status": "completed",
        "researchOutcome": _classify(baseline, treatment),
        "implementationRevision": _git_revision(Path.cwd()),
        "experimentRevision": EXPERIMENT_REVISION,
        "question": (
            "Does prior no-domain-Tool deliberation change choice correctness/stability on a neutral "
            "mechanically scored Harness task compared with immediate Tool availability?"
        ),
        "task": TASK,
        "taskDigest": canonical_digest(TASK),
        "scoreTable": table,
        "oracleChoice": oracle,
        "replicatesPerTreatment": MODEL_REPLICATES_PER_TREATMENT,
        "baseline": baseline,
        "deliberationFirst": treatment,
        "gates": gates,
        "interpretation": {
            "deliberationIsChoiceAuthority": False,
            "toolChoiceHasExternalEffect": False,
            "securitySemanticsConsumed": False,
            "genericHarnessPrimitiveForced": _classify(baseline, treatment)
            == "ordering-pressure-reproduced-in-sample",
            "populationLevelCausalityEstablished": False,
        },
    }
    validate_json_value(receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Harness-native H0 deliberation/Tool sequencing experiment")
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    receipt = run(equipment=Equipment(secret=args.secret))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(canonical_bytes(receipt) + b"\n")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

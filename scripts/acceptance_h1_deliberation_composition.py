from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import cast

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value

from ordivon_harness.api import DeepSeekSettings, DeepSeekTurnAdapter, RunBudget
from ordivon_harness.deliberation import DeliberationThenToolRunner
from ordivon_harness.domain_tools import DomainToolLoopPlan
from ordivon_harness.ordivon.model import AgentTurnRequest


REPLICATES = 2
REVISION = "harness-deliberation-composition-h1-v1"


def _load_h0():
    path = Path(__file__).with_name("acceptance_h0_deliberation_authority.py")
    spec = importlib.util.spec_from_file_location("h1_h0_fixture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("H1 cannot load H0 neutral fixture")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


H0 = _load_h0()
TASK = H0.TASK
TASK_DIGEST = canonical_digest(TASK)
ORACLE = H0.oracle_choice()


def _git_revision(path: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _task_message() -> str:
    return json.dumps(TASK, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _deliberation_request(label: str) -> AgentTurnRequest:
    return AgentTurnRequest(
        harness_run_id=f"harness-run:h1-deliberation-{label}",
        turn_id=f"turn:h1-deliberation-{label}:1",
        sequence=1,
        assignment_id=f"assignment:h1-{label}",
        context_digest=TASK_DIGEST,
        tool_catalog_digest=canonical_digest(
            {
                "schemaVersion": 1,
                "kind": "ordivon.harness.h1-no-domain-tools",
                "tools": [],
                "revision": REVISION,
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


def _tool_plan(label: str) -> DomainToolLoopPlan:
    return DomainToolLoopPlan(
        harness_run_id=f"harness-run:h1-tool-{label}",
        assignment_id=f"assignment:h1-{label}",
        context_digest=TASK_DIGEST,
        initial_messages=(
            {
                "role": "system",
                "content": (
                    "This is a neutral Harness evaluation. Choose the unique feasible candidate with "
                    "the highest score under the supplied rules. Carefully apply feasibility before "
                    "comparing scores. submit_choice only records a pending choice; it reveals no "
                    "score and has no external effect. You may call it again to replace an earlier "
                    "choice. When your final recorded choice matches your considered decision, submit "
                    "a concise candidate_completed conclusion."
                ),
            },
            {"role": "user", "content": _task_message()},
        ),
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


def _replicate(*, secret: Path, replicate: int) -> dict[str, JsonValue]:
    label = f"r{replicate}"
    settings = DeepSeekSettings.from_secret_file(
        secret,
        timeout_seconds=90.0,
        max_output_tokens=2048,
    )
    adapter = DeepSeekTurnAdapter(settings)
    bridge = H0.ChoiceBridge()
    execution = DeliberationThenToolRunner(adapter, bridge).run(
        _deliberation_request(label),
        _tool_plan(label),
    )
    stop_code = str(
        getattr(execution.tool_result.stop_code, "value", execution.tool_result.stop_code)
    )
    if stop_code != "candidate_completed":
        raise RuntimeError(f"H1 Tool phase did not candidate_complete: {stop_code}")
    if not bridge.revisions:
        raise RuntimeError("H1 Tool phase recorded no choice")
    injected = execution.tool_plan.initial_messages[-1]
    if injected.get("role") != "user":
        raise RuntimeError("H1 cognition record is not injected as user-role context")
    content = injected.get("content")
    if not isinstance(content, str) or "PRIOR_NON_AUTHORITATIVE_SELF_DELIBERATION_RECORD" not in content:
        raise RuntimeError("H1 cognition envelope marker is absent")
    result: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "replicate": replicate,
        "contextDigest": TASK_DIGEST,
        "deliberation": execution.deliberation.to_dict(),
        "deliberationDigest": execution.deliberation.digest,
        "executionDigest": execution.execution_digest,
        "cognitionEnvelopeDigest": canonical_digest(injected),
        "cognitionEnvelopeRole": "user",
        "choiceRevisions": list(bridge.revisions),
        "finalChoice": bridge.revisions[-1],
        "correct": bridge.revisions[-1] == ORACLE,
        "toolStopCode": stop_code,
        "toolTrace": execution.tool_result.trace.to_dict(),
        "toolTraceDigest": canonical_digest(execution.tool_result.trace.to_dict()),
        "toolUsage": cast(dict[str, JsonValue], execution.tool_result.usage),
        "requestedModelId": str(adapter.model_id),
        "credentialScopeId": str(settings.credential_scope_id),
        "callerBridgeKind": str(bridge.bridge_identity["kind"]),
        "externalEffectPerformed": False,
    }
    validate_json_value(result)
    return result


def _incomplete(
    *,
    completed: list[dict[str, JsonValue]],
    failed_replicate: int,
    error: Exception,
) -> dict[str, JsonValue]:
    receipt: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.deliberation-composition-h1",
        "status": "incomplete",
        "researchOutcome": "incomplete-equipment-or-protocol",
        "implementationRevision": _git_revision(Path.cwd()),
        "experimentRevision": REVISION,
        "taskDigest": TASK_DIGEST,
        "oracleChoice": ORACLE,
        "replicatesPlanned": REPLICATES,
        "replicates": completed,
        "failedReplicate": failed_replicate,
        "failure": {
            "errorType": type(error).__name__,
            "message": str(error),
        },
        "interpretation": {
            "genericCompositionValidated": False,
            "productApiForced": False,
        },
    }
    validate_json_value(receipt)
    return receipt


def run(*, secret: Path) -> dict[str, JsonValue]:
    completed: list[dict[str, JsonValue]] = []
    for replicate in range(1, REPLICATES + 1):
        try:
            completed.append(_replicate(secret=secret, replicate=replicate))
        except Exception as error:
            return _incomplete(
                completed=completed,
                failed_replicate=replicate,
                error=error,
            )
    models = {str(x["requestedModelId"]) for x in completed}
    scopes = {str(x["credentialScopeId"]) for x in completed}
    gates = {
        "h0TaskUnchanged": TASK_DIGEST
        == "sha256:b402b3066ebd0fa64c4e464fd4f1640a3cd1cc08b0164426f2a39805f56e223f",
        "oracleUnchanged": ORACLE == "cobalt",
        "predeclaredReplicatesComplete": len(completed) == REPLICATES == 2,
        "allReplicatesCorrect": all(bool(x["correct"]) for x in completed),
        "allCognitionRecordsUserRole": all(x["cognitionEnvelopeRole"] == "user" for x in completed),
        "allDeliberationRecordsNonAuthoritative": all(
            cast(dict[str, JsonValue], x["deliberation"])["domainToolIntent"] is False
            and cast(dict[str, JsonValue], x["deliberation"])["domainAdmission"] is False
            and cast(dict[str, JsonValue], x["deliberation"])["externalEffect"] is False
            for x in completed
        ),
        "sameRequestedModelAcrossReplicates": len(models) == 1,
        "sameCredentialScopeAcrossReplicates": len(scopes) == 1,
        "callerBridgeRemainsDomainOwned": all(
            x["callerBridgeKind"] == "ordivon.harness.h0-record-only-choice-bridge"
            for x in completed
        ),
        "noExternalEffects": all(x["externalEffectPerformed"] is False for x in completed),
    }
    status = "accepted" if all(gates.values()) else "falsified"
    receipt: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.deliberation-composition-h1",
        "status": status,
        "researchOutcome": (
            "generic-composition-accepted-in-h0-consumer"
            if status == "accepted"
            else "generic-composition-falsified-in-h0-consumer"
        ),
        "implementationRevision": _git_revision(Path.cwd()),
        "experimentRevision": REVISION,
        "question": (
            "Can a narrow Harness-owned deliberation-before-Tools composition replace H0 application "
            "glue while preserving the same neutral task, caller-owned bridge and correct Tool choices?"
        ),
        "h0Evidence": {
            "receiptSha256": "sha256:2398be1ddba7b9433557fed8bb30ce7920fcacb24fd48e269dec7f5511ee0425",
            "researchOutcome": "ordering-pressure-reproduced-in-sample",
        },
        "taskDigest": TASK_DIGEST,
        "oracleChoice": ORACLE,
        "replicatesPlanned": REPLICATES,
        "replicates": completed,
        "gates": gates,
        "interpretation": {
            "genericCompositionValidated": status == "accepted",
            "domainScoringOwnedByPrimitive": False,
            "domainStrategyOwnedByPrimitive": False,
            "domainAdmissionOwnedByPrimitive": False,
            "externalEffectOwnedByPrimitive": False,
            "aggregateCrossPhaseBudgetClaimed": False,
            "recommendedPublicApiForced": False,
            "populationLevelCausalityEstablished": False,
        },
    }
    validate_json_value(receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run H1 generic deliberation composition acceptance")
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    receipt = run(secret=args.secret)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(canonical_bytes(receipt) + b"\n")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    if receipt.get("status") != "accepted":
        raise SystemExit(2 if receipt.get("status") == "falsified" else 3)


if __name__ == "__main__":
    main()

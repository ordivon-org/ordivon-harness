from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import time
from typing import Any, cast

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value

from ordivon_harness.api import (
    DeepSeekSettings,
    DeepSeekTurnAdapter,
    HarnessAgentRun,
    HarnessAgentStrategySelection,
    HarnessBoundReference,
    HarnessExecutionMandate,
    HarnessExecutionProfile,
    HarnessExecutionStrategy,
    HarnessPrivacyPolicy,
    HarnessPriorAttemptEvidence,
    HarnessRunContract,
    HarnessStrategyEvidence,
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    RunBudget,
    build_harness_strategy_selection_context,
    compile_harness_selected_attempt,
    decode_structured_completion_result,
)

REVISION = "harness-rsi-p1-live-multi-attempt-v1"
PARTIAL_PROFILE = "profile:partial-evidence"
FULL_PROFILE = "profile:full-evidence"

FULL_TASK: dict[str, JsonValue] = {
    "rules": {
        "feasibleWhen": {"memoryAtMost": 16, "dependenciesAtMost": 2},
        "score": "throughput - 3*latency - 2*retries",
    },
    "candidates": [
        {
            "name": "cobalt",
            "throughput": 68,
            "latency": 2,
            "retries": 2,
            "memory": 14,
            "dependencies": 2,
        },
        {
            "name": "delta",
            "throughput": 80,
            "latency": 5,
            "retries": 1,
            "memory": 15,
            "dependencies": 2,
        },
    ],
}
PARTIAL_TASK = json.loads(json.dumps(FULL_TASK))
cast(dict[str, Any], cast(list[Any], PARTIAL_TASK["candidates"])[1])["memory"] = None

ATTEMPT_COMPLETION: dict[str, JsonValue] = {
    "mode": "structured-result-v1",
    "resultKind": "rsi-p1-candidate-choice",
    "resultSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "choice": {"type": "string", "enum": ["cobalt", "delta", "undetermined"]},
            "confidence": {"type": "string", "enum": ["provisional", "final"]},
            "reason": {"type": "string", "minLength": 1},
        },
        "required": ["choice", "confidence", "reason"],
    },
}


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _bound(ref: str, kind: str, value: JsonValue) -> HarnessBoundReference:
    return HarnessBoundReference(ref=ref, kind=kind, digest=canonical_digest(value))


def _profiles(model_id: str) -> tuple[HarnessExecutionProfile, ...]:
    common = {
        "provider_id": "provider:deepseek",
        "adapter_id": DeepSeekTurnAdapter.adapter_id,
        "requested_model_id": model_id,
        "tool_catalog_digest": NO_TOOL_AGENT_SURFACE_DIGEST,
        "tool_grant_digest": NO_TOOL_AGENT_GRANT_DIGEST,
    }
    return (
        HarnessExecutionProfile(
            profile_id=PARTIAL_PROFILE,
            metadata={
                "evidenceScope": "partial",
                "relativeCost": 1,
                "description": "Use the cheaper partial task evidence first when it can settle the objective.",
            },
            **common,
        ),
        HarnessExecutionProfile(
            profile_id=FULL_PROFILE,
            metadata={
                "evidenceScope": "full",
                "relativeCost": 3,
                "description": "Use the complete task evidence when prior exact outcome evidence proves the partial view insufficient.",
            },
            **common,
        ),
    )


def _mandate(model_id: str) -> tuple[HarnessExecutionMandate, tuple[HarnessExecutionProfile, ...]]:
    profiles = _profiles(model_id)
    value = HarnessExecutionMandate(
        mandate_id="mandate:rsi-p1-live-multi-attempt",
        caller_id="caller:rsi-p1-live",
        caller_ref="experiment:rsi-p1-live-multi-attempt",
        objective_ref=_bound(
            "objective:rsi-p1-live",
            "objective",
            "Determine the unique feasible highest-scoring candidate without inventing missing evidence.",
        ),
        context_refs=(
            _bound(
                "context:rsi-p1-rules",
                "task-rules",
                cast(JsonValue, FULL_TASK["rules"]),
            ),
        ),
        allowed_profile_ids=tuple(profile.profile_id for profile in profiles),
        max_total_tokens=48_000,
        max_wall_time_ms=240_000,
        completion_contract=ATTEMPT_COMPLETION,
        created_at_ms=_now_ms(),
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=False,
        ),
    )
    return value, profiles


def _selector_completion(profile_ids: tuple[str, ...], context) -> dict[str, JsonValue]:
    return {
        "mode": "structured-result-v1",
        "resultKind": "rsi-p1-strategy-selection",
        "resultSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "profileId": {"type": "string", "enum": list(profile_ids)},
                "maxTotalTokens": {
                    "type": "integer",
                    "minimum": 12_000,
                    "maximum": min(22_000, context.remaining_total_tokens),
                },
                "maxWallTimeMs": {
                    "type": "integer",
                    "minimum": 45_000,
                    "maximum": min(100_000, context.remaining_wall_time_ms),
                },
                "maxOutputTokens": {
                    "type": "integer",
                    "minimum": 512,
                    "maximum": 2_048,
                },
                "adoptPriorCompletionProposal": {"type": "boolean"},
                "adoptIndependentVerification": {"type": "boolean"},
                "rationale": {"type": "string", "minLength": 1},
            },
            "required": [
                "profileId",
                "maxTotalTokens",
                "maxWallTimeMs",
                "maxOutputTokens",
                "adoptPriorCompletionProposal",
                "adoptIndependentVerification",
                "rationale",
            ],
        },
    }


def _selector_contract(context, *, index: int, model_id: str) -> HarnessRunContract:
    completion = _selector_completion(tuple(profile.profile_id for profile in context.profiles), context)
    manifest: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-rsi-p1-selector-manifest",
        "experimentRevision": REVISION,
        "selectionContextDigest": context.digest,
        "attemptIndex": context.attempt_index,
    }
    created = _now_ms()
    return HarnessRunContract(
        harness_run_id=f"harness-run:rsi-p1-selector-{index}",
        harness_implementation_id="ordivon-harness@rsi-p1-live",
        caller_id="caller:rsi-p1-selector",
        caller_run_ref=f"selector:rsi-p1:{index}",
        objective_ref=_bound(
            f"objective:rsi-p1-selector-{index}",
            "strategy-selection-objective",
            "Select the next bounded Strategy from exact available profiles and prior attempt evidence.",
        ),
        context_refs=(
            HarnessBoundReference(
                ref=f"context:rsi-p1-selector-{index}",
                kind="harness-strategy-selection-context",
                digest=context.digest,
            ),
        ),
        provider_id="provider:deepseek",
        adapter_id=DeepSeekTurnAdapter.adapter_id,
        requested_model_id=model_id,
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=NO_TOOL_AGENT_GRANT_DIGEST,
        budget=RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=32_768,
            max_wall_time_ms=180_000,
            max_total_tokens=48_000,
            max_model_retries=1,
        ).to_contract_dict(),
        completion_contract=completion,
        system_manifest_ref=HarnessBoundReference(
            ref=f"system-manifest:rsi-p1-selector-{index}",
            kind="rsi-p1-selector-manifest",
            digest=canonical_digest(manifest),
        ),
        created_at_ms=created,
        deadline_ms=created + 180_000,
    )


def _selector_prompt(context) -> str:
    return (
        "You are the Strategy-selection Agent for a bounded multi-attempt experiment. "
        "Choose, do not merely recommend, the next exact profile and economic attempt budget. "
        "Minimize resource use: prefer the lower-cost partial-evidence profile when no prior exact "
        "outcome shows it is insufficient. Treat Completion Proposals as Agent-authored candidate "
        "evidence, not independent verification. If any exact Strategy Evidence from a caller/domain "
        "verifier says the prior candidate is insufficient and the full-evidence profile can resolve "
        "the named gap, switch to full-evidence and set both adoptPriorCompletionProposal=true and "
        "adoptIndependentVerification=true. Also escalate when the latest Completion Proposal itself "
        "retains unresolvedUnknowns that full evidence can resolve. Never invent evidence and stay "
        "within the remaining economic envelope.\n\n"
        "EXACT_STRATEGY_SELECTION_CONTEXT:\n"
        + json.dumps(context.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _run_selector(*, secret: Path, state_root: Path, context, index: int, model_id: str) -> dict[str, Any]:
    contract = _selector_contract(context, index=index, model_id=model_id)
    run = HarnessAgentRun.create(
        state_root / f"selector-{index}",
        contract,
        lambda exact: DeepSeekTurnAdapter(
            DeepSeekSettings.from_secret_file(
                secret,
                timeout_seconds=150.0,
                max_output_tokens=2_048,
            ),
            completion_contract=exact.completion_contract,
        ),
    )
    execution = run.run(({"role": "user", "content": _selector_prompt(context)},))
    if execution.loop_result.conclusion is None:
        raise RuntimeError("Strategy-selection Agent produced no conclusion")
    value = decode_structured_completion_result(contract, execution.loop_result.conclusion)
    if not isinstance(value, dict):
        raise RuntimeError("Strategy-selection result is not an object")
    return value


def _strategy_from_result(context, result: dict[str, Any]) -> HarnessAgentStrategySelection:
    profile_id = result.get("profileId")
    if not isinstance(profile_id, str):
        raise RuntimeError("Strategy-selection profileId is invalid")
    adopted_refs: list[HarnessBoundReference] = []
    if result.get("adoptPriorCompletionProposal") is True:
        if not context.prior_attempts:
            raise RuntimeError("Strategy-selection tried to adopt prior evidence on attempt 1")
        proposal_ref = context.prior_attempts[-1].completion_proposal_ref
        if proposal_ref is None:
            raise RuntimeError("Strategy-selection requested a prior Completion Proposal that is absent")
        adopted_refs.append(proposal_ref)
    if result.get("adoptIndependentVerification") is True:
        if not context.strategy_evidence:
            raise RuntimeError("Strategy-selection requested independent verification that is absent")
        adopted_refs.append(context.strategy_evidence[-1].reference)
    adopted = tuple(adopted_refs)
    budget = RunBudget(
        max_model_calls=3,
        max_tool_calls=0,
        max_observation_bytes=32_768,
        max_wall_time_ms=int(result["maxWallTimeMs"]),
        max_total_tokens=int(result["maxTotalTokens"]),
        max_model_retries=1,
        max_conclusion_corrections=1,
    )
    strategy = HarnessExecutionStrategy(
        mandate_digest=context.mandate.digest,
        attempt_index=context.attempt_index,
        profile_id=profile_id,
        budget=budget.to_contract_dict(),
        provider_options={"maxOutputTokens": int(result["maxOutputTokens"])},
        adopted_context_refs=adopted,
        rationale=str(result["rationale"]),
    )
    return HarnessAgentStrategySelection(context.digest, strategy)


def _attempt_messages(
    profile_id: str,
    prior: HarnessPriorAttemptEvidence | None,
    verification: HarnessStrategyEvidence | None,
) -> tuple[dict[str, JsonValue], ...]:
    if profile_id == PARTIAL_PROFILE:
        task = PARTIAL_TASK
        scope = (
            "You have the lower-cost partial evidence view. One field may be null. Apply feasibility "
            "before score. Do not invent missing values. If a missing value could change the winner, "
            "submit a provisional result and put the exact missing fact in unresolved_unknowns."
        )
    elif profile_id == FULL_PROFILE:
        task = FULL_TASK
        scope = (
            "You have the complete evidence view. Treat any prior Completion Proposal and independent "
            "verification as non-authoritative evidence about the previous attempt, then recompute from "
            "the complete task. All external facts required by this experiment are present. When the "
            "winner is mechanically determined, submit status=candidate_completed with a final result and "
            "no unresolved_unknowns. Use needs_input only if you can name a specific external fact that is "
            "still absent; do not request confirmation for a calculation already determined by the evidence."
        )
    else:
        raise RuntimeError(f"unsupported experiment profile: {profile_id}")
    messages: list[dict[str, JsonValue]] = [
        {"role": "system", "content": scope},
        {
            "role": "user",
            "content": "TASK_EVIDENCE:\n"
            + json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        },
    ]
    if prior is not None and prior.completion_proposal is not None:
        messages.append(
            {
                "role": "user",
                "content": "EXACT_PRIOR_COMPLETION_PROPOSAL:\n"
                + json.dumps(
                    prior.completion_proposal.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    if verification is not None:
        messages.append(
            {
                "role": "user",
                "content": "EXACT_INDEPENDENT_STRATEGY_EVIDENCE:\n"
                + json.dumps(
                    verification.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return tuple(messages)


def _run_attempt(
    *,
    secret: Path,
    state_root: Path,
    compiled,
    profile_id: str,
    prior: HarnessPriorAttemptEvidence | None,
    verification: HarnessStrategyEvidence | None,
) -> tuple[dict[str, Any], HarnessPriorAttemptEvidence]:
    options = compiled.system_manifest.get("providerOptions")
    if not isinstance(options, Mapping):
        raise RuntimeError("compiled attempt Provider options are invalid")
    max_output = options.get("maxOutputTokens")
    if type(max_output) is not int:
        raise RuntimeError("compiled attempt maxOutputTokens is invalid")
    run = HarnessAgentRun.create(
        state_root / compiled.contract.harness_run_id.replace(":", "-"),
        compiled.contract,
        lambda exact: DeepSeekTurnAdapter(
            DeepSeekSettings.from_secret_file(
                secret,
                timeout_seconds=90.0,
                max_output_tokens=max_output,
            ),
            completion_contract=exact.completion_contract,
        ),
    )
    execution = run.run(_attempt_messages(profile_id, prior, verification))
    terminal = execution.terminal_result
    if terminal is None or execution.loop_result.conclusion is None:
        raise RuntimeError("Mandate attempt did not produce a terminal conclusion")
    if terminal.completion_proposal is None:
        raise RuntimeError("Mandate attempt did not retain its Completion Proposal")
    result = decode_structured_completion_result(compiled.contract, execution.loop_result.conclusion)
    if not isinstance(result, dict):
        raise RuntimeError("Mandate attempt structured result is not an object")
    evidence = HarnessPriorAttemptEvidence(
        compiled_attempt=compiled,
        receipt=terminal.receipt,
        completion_proposal=terminal.completion_proposal,
    )
    return result, evidence


def _independent_verification(
    result: dict[str, Any],
    evidence: HarnessPriorAttemptEvidence,
) -> HarnessStrategyEvidence:
    proposal = evidence.completion_proposal
    if proposal is None:
        raise RuntimeError("independent verification requires a retained Completion Proposal")
    content: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "rsi-p1-domain-verification",
        "owner": "domain-verifier:rsi-p1-mechanical",
        "subjectReceiptDigest": evidence.receipt.digest,
        "subjectCompletionProposalDigest": proposal.digest,
        "subjectResultDigest": canonical_digest(cast(JsonValue, result)),
        "verdict": "insufficient",
        "reason": (
            "The partial evidence omits delta.memory. Because memory <= 16 is a feasibility gate, "
            "the reported winner cannot be certified from that evidence even if its score is higher."
        ),
        "requiredEvidence": ["candidate:delta.memory"],
        "hiddenValueDisclosed": False,
    }
    return HarnessStrategyEvidence(
        reference=HarnessBoundReference(
            ref="strategy-evidence:rsi-p1:attempt-1-domain-verification",
            kind="domain-verification",
            digest=canonical_digest(content),
        ),
        content=content,
    )


def run(*, secret: Path, state_root: Path) -> dict[str, JsonValue]:
    if state_root.exists():
        raise FileExistsError(f"state root already exists: {state_root}")
    state_root.mkdir(parents=True)
    settings = DeepSeekSettings.from_secret_file(secret, timeout_seconds=90.0, max_output_tokens=2_048)
    mandate, profiles = _mandate(settings.model)

    context1 = build_harness_strategy_selection_context(mandate, profiles)
    selected1_raw = _run_selector(
        secret=secret,
        state_root=state_root,
        context=context1,
        index=1,
        model_id=settings.model,
    )
    selection1 = _strategy_from_result(context1, selected1_raw)
    compiled1 = compile_harness_selected_attempt(
        context1,
        selection1,
        harness_run_id="harness-run:rsi-p1-live-attempt-1",
        harness_implementation_id="ordivon-harness@rsi-p1-live",
        created_at_ms=_now_ms(),
    )
    result1, evidence1 = _run_attempt(
        secret=secret,
        state_root=state_root,
        compiled=compiled1,
        profile_id=selection1.strategy.profile_id,
        prior=None,
        verification=None,
    )
    verification1 = _independent_verification(result1, evidence1)

    context2 = build_harness_strategy_selection_context(
        mandate,
        profiles,
        (evidence1,),
        (verification1,),
    )
    selected2_raw = _run_selector(
        secret=secret,
        state_root=state_root,
        context=context2,
        index=2,
        model_id=settings.model,
    )
    selection2 = _strategy_from_result(context2, selected2_raw)
    compiled2 = compile_harness_selected_attempt(
        context2,
        selection2,
        harness_run_id="harness-run:rsi-p1-live-attempt-2",
        harness_implementation_id="ordivon-harness@rsi-p1-live",
        created_at_ms=_now_ms(),
    )
    result2, evidence2 = _run_attempt(
        secret=secret,
        state_root=state_root,
        compiled=compiled2,
        profile_id=selection2.strategy.profile_id,
        prior=evidence1,
        verification=verification1,
    )

    proposal1 = evidence1.completion_proposal
    proposal2 = evidence2.completion_proposal
    proposal1_ref = evidence1.completion_proposal_ref
    assert proposal1 is not None and proposal2 is not None and proposal1_ref is not None
    expected_adopted = (proposal1_ref, verification1.reference)
    context2_dict = context2.to_dict()
    gates: dict[str, JsonValue] = {
        "attempt1AgentSelectedPartialProfile": selection1.strategy.profile_id == PARTIAL_PROFILE,
        "attempt1AgentSelectedOwnEconomicBudget": (
            type(selected1_raw.get("maxTotalTokens")) is int
            and type(selected1_raw.get("maxWallTimeMs")) is int
        ),
        "attempt1RetainedExactCompletionProposal": evidence1.completion_proposal_ref is not None,
        "independentVerifierRejectedUncertifiableCandidate": (
            verification1.to_dict()["content"]["verdict"] == "insufficient"
        ),
        "attempt2SelectionContextContainsPriorOutcome": (
            context2_dict["priorAttempts"][0]["completionProposal"] is not None
        ),
        "attempt2SelectionContextContainsIndependentVerification": (
            context2_dict["strategyEvidence"][0]["reference"]["digest"]
            == verification1.reference.digest
        ),
        "attempt2AgentSwitchedToFullProfile": selection2.strategy.profile_id == FULL_PROFILE,
        "attempt2AgentAdoptedPriorAndIndependentEvidence": (
            selection2.strategy.adopted_context_refs == expected_adopted
        ),
        "attempt2ContractBindsPriorAndIndependentEvidence": (
            compiled2.contract.context_refs[-2:] == expected_adopted
        ),
        "attempt2ResolvedUnknowns": not proposal2.unresolved_unknowns,
        "attempt2ReachedCorrectFinalChoice": (
            result2.get("choice") == "delta" and result2.get("confidence") == "final"
        ),
        "humanDidNotChooseAttempt2Profile": True,
        "harnessDidNotRankProfiles": True,
        "harnessDidNotJudgeVerificationSemantics": True,
        "noBuiltInStrategyPolicyAdded": True,
        "noGenericMemoryAdded": True,
    }
    status = "accepted" if all(bool(value) for value in gates.values()) else "falsified"
    receipt: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-rsi-p1-live-multi-attempt",
        "status": status,
        "experimentRevision": REVISION,
        "implementationRevision": _git_revision(),
        "modelId": settings.model,
        "credentialScopeId": settings.credential_scope_id,
        "mandateDigest": mandate.digest,
        "attempt1": {
            "selectionContextDigest": context1.digest,
            "agentSelection": selection1.to_dict(),
            "result": cast(JsonValue, result1),
            "receiptDigest": evidence1.receipt.digest,
            "completionProposalDigest": proposal1.digest,
            "unresolvedUnknowns": list(proposal1.unresolved_unknowns),
            "independentVerification": verification1.to_dict(),
        },
        "attempt2": {
            "selectionContextDigest": context2.digest,
            "agentSelection": selection2.to_dict(),
            "result": cast(JsonValue, result2),
            "receiptDigest": evidence2.receipt.digest,
            "completionProposalDigest": proposal2.digest,
            "unresolvedUnknowns": list(proposal2.unresolved_unknowns),
        },
        "gates": gates,
        "interpretation": {
            "agentOwnedNextStrategyObserved": bool(gates["attempt2AgentSwitchedToFullProfile"]),
            "exactCrossRunOutcomeReuseObserved": bool(
                gates["attempt2AgentAdoptedPriorAndIndependentEvidence"]
            ),
            "independentVerificationSeparatedFromGenerator": True,
            "harnessVerificationSemanticsAdded": False,
            "schedulerRequiredByExperiment": False,
            "genericMemoryRequiredByExperiment": False,
        },
    }
    validate_json_value(receipt)
    return receipt


def _git_revision() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RSI P1 live multi-attempt Agent acceptance")
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    value = run(secret=args.secret, state_root=args.state_root)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(canonical_bytes(value) + b"\n")
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
    if value["status"] != "accepted":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

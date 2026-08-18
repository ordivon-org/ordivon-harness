from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from anc_canonical import canonical_digest

import ordivon_harness.api as harness_api
from ordivon_harness.api import (
    HarnessAgentRun,
    HarnessAgentStrategySelection,
    HarnessBoundReference,
    HarnessExecutionBinding,
    HarnessExecutionMandate,
    HarnessExecutionProfile,
    HarnessExecutionStrategy,
    HarnessPrivacyPolicy,
    HarnessRunContract,
    HarnessRuntimeReference,
    HarnessStrategyEvidence,
    INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
    INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    RunBudget,
    build_harness_strategy_selection_context,
    compile_harness_selected_attempt,
)
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnResult,
    ScriptedTurnAdapter,
)


EXPERIMENT = "FOR Direct Destructive Dogfood v1"
IMPLEMENTATION_ID = "ordivon-harness@for-direct-dogfood-v1"
SHARED_OBJECTIVE = HarnessBoundReference(
    ref="objective:for-direct:shared-q",
    kind="objective",
    digest=canonical_digest({"forDirect": "shared-objective-q"}),
)
SHARED_CLAIM_REF = "claim:for-direct:shared-realization-q"


class FixedClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def digest(label: str) -> str:
    return canonical_digest({"forDirect": label})


def run_contract(subject: str, *, tools: bool = False) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f"harness-run:for-direct:{subject}",
        harness_implementation_id=IMPLEMENTATION_ID,
        caller_id=f"caller:for-direct:{subject}",
        caller_run_ref=f"subject:for-direct:{subject}",
        objective_ref=SHARED_OBJECTIVE,
        context_refs=(
            HarnessBoundReference(
                ref=f"context:for-direct:{subject}",
                kind="context",
                digest=digest(f"context:{subject}"),
            ),
        ),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=(
            INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST
            if tools
            else NO_TOOL_AGENT_SURFACE_DIGEST
        ),
        tool_grant_digest=(
            INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST
            if tools
            else NO_TOOL_AGENT_GRANT_DIGEST
        ),
        budget={
            "maxModelCalls": 4,
            "maxToolCalls": 2 if tools else 0,
            "maxObservationBytes": 65_536,
            "maxWallTimeMs": 10_000,
            "maxTotalTokens": 10_000,
            "maxModelRetries": 1,
            "maxToolCorrections": 2,
            "maxConclusionCorrections": 3,
            "maxObservationOnlyTurns": 4,
            "maxNoProgressTurns": 3,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            ref=f"manifest:for-direct:{subject}",
            kind="system-manifest",
            digest=digest(f"manifest:{subject}"),
        ),
        created_at_ms=1_000,
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=tools,
        ),
    )


def completed_result(subject: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:for-direct:{subject}:completed",
        model_id=ScriptedTurnAdapter.model_id,
        content=f"{subject} local candidate complete",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary=f"{subject} completed its bounded local work.",
        ),
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="stop",
        raw_response_digest=digest(f"completed:{subject}"),
    )


def needs_input_result(subject: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:for-direct:{subject}:needs-input",
        model_id=ScriptedTurnAdapter.model_id,
        content=f"{subject} still needs local input",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="needs_input",
            summary=f"{subject} remains locally unresolved.",
            unresolved_unknowns=(f"{subject} local reply",),
        ),
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="stop",
        raw_response_digest=digest(f"needs-input:{subject}"),
    )


def tool_turn(subject: str) -> AgentTurnResult:
    call = AgentToolCall(
        tool_call_id=f"tool-call:for-direct:{subject}:shared-search",
        name="search_workspace",
        arguments={"query": "for-direct-shared-safe-query"},
    )
    return AgentTurnResult(
        model_call_id=f"model-call:for-direct:{subject}:tool",
        model_id=ScriptedTurnAdapter.model_id,
        content="perform the same safe fake external capability",
        tool_calls=(call,),
        conclusion=None,
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="tool_calls",
        raw_response_digest=digest(f"tool-turn:{subject}"),
    )


def execution_binding(contract: HarnessRunContract, subject: str) -> HarnessExecutionBinding:
    token = contract.digest[7:31]
    return HarnessExecutionBinding(
        harness_run_id=contract.harness_run_id,
        workspace_ref="workspace:for-direct:fake-shared-target",
        assignment_id=f"assignment:external:{token}",
        assignment_generation=1,
        assignment_digest=contract.digest,
        runtime_binding_digest=digest("runtime-binding:shared-fake"),
        tool_catalog_digest=contract.tool_catalog_digest,
        tool_grant_digest=contract.tool_grant_digest,
        deadline_ms=contract.deadline_ms,
        runtime_references=(
            HarnessRuntimeReference(
                namespace="ordivon.harness",
                reference_type="harness_run",
                reference_id=contract.harness_run_id,
                generation="1",
                digest=contract.digest,
            ),
        ),
    )


class CountingRuntime:
    """Fixture-owned fake Runtime; records Harness client calls and causes no external effect."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def call_tool(self, name, arguments):
        index = len(self.calls) + 1
        self.calls.append({"index": index, "name": name, "arguments": dict(arguments)})
        return {
            "status": "succeeded",
            "jobId": f"job:for-direct:fake:{index}",
            "attemptId": f"attempt:for-direct:fake:{index}",
            "executionTerminal": True,
            "executionDisposition": "succeeded",
            "deliveryDisposition": "committed",
            "recoveryRequired": False,
            "semanticCompletionEvaluated": False,
            "exitCode": 0,
            "stdoutTail": "for-direct-shared-safe-result",
            "stderrTail": "",
            "resultAvailable": True,
            "artifactsAvailable": False,
        }

    def find_jobs_by_client_request_id(self, client_request_id):
        return ()


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(path.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def mandate_b() -> HarnessExecutionMandate:
    return HarnessExecutionMandate(
        mandate_id="mandate:for-direct:subject-b",
        caller_id="caller:for-direct:b",
        caller_ref="subject:for-direct:b",
        objective_ref=SHARED_OBJECTIVE,
        context_refs=(
            HarnessBoundReference(
                ref="context:for-direct:b:strategy",
                kind="context",
                digest=digest("context:b:strategy"),
            ),
        ),
        allowed_profile_ids=("profile:for-direct:b",),
        max_total_tokens=10_000,
        max_wall_time_ms=20_000,
        completion_contract={"mode": "record-candidate"},
        created_at_ms=2_000,
    )


def profile_b() -> HarnessExecutionProfile:
    return HarnessExecutionProfile(
        profile_id="profile:for-direct:b",
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=NO_TOOL_AGENT_GRANT_DIGEST,
        metadata={"experiment": EXPERIMENT},
    )


def b_strategy(context, *, adopted_context_refs=()) -> HarnessExecutionStrategy:
    return HarnessExecutionStrategy(
        mandate_digest=context.mandate.digest,
        attempt_index=context.attempt_index,
        profile_id="profile:for-direct:b",
        budget=RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=32_768,
            max_wall_time_ms=4_000,
            max_total_tokens=2_000,
            max_model_retries=1,
        ).to_contract_dict(),
        provider_options={"temperature": 0},
        adopted_context_refs=tuple(adopted_context_refs),
        rationale="FOR direct dogfood subject B selection.",
    )


def classify(condition: bool, *, support: str, falsifier: str, details: dict) -> dict:
    return {
        "classification": "DIRECT_SUPPORT" if condition else "DIRECT_FALSIFIER",
        "interpretation": support if condition else falsifier,
        "details": details,
    }


def run_experiment() -> dict:
    cases: dict[str, dict] = {}

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        # E1/E2: two actual bounded Runs share one objective but retain local identity/state.
        clock_a = FixedClock()
        clock_b = FixedClock()
        contract_a = run_contract("a")
        contract_b = run_contract("b")
        run_a = HarnessAgentRun.create(
            root / "subject-a",
            contract_a,
            lambda _contract: ScriptedTurnAdapter((completed_result("a"),)),
            clock_ms=clock_a,
            monotonic_ms=clock_a,
        )
        run_b = HarnessAgentRun.create(
            root / "subject-b",
            contract_b,
            lambda _contract: ScriptedTurnAdapter((needs_input_result("b"),)),
            clock_ms=clock_b,
            monotonic_ms=clock_b,
        )

        result_b = run_b.run(({"role": "user", "content": "shared experimental work"},))
        b_before_a_completion = tree_digest(root / "subject-b")
        result_a = run_a.run(({"role": "user", "content": "shared experimental work"},))
        b_after_a_completion = tree_digest(root / "subject-b")

        e1_condition = (
            contract_a.objective_ref == contract_b.objective_ref
            and contract_a.harness_run_id != contract_b.harness_run_id
            and (root / "subject-a") != (root / "subject-b")
        )
        cases["E1"] = classify(
            e1_condition,
            support="same shared objective coexists with distinct local Harness Runs/state roots",
            falsifier="Harness collapsed or required shared Run identity for shared work",
            details={
                "objectiveRef": contract_a.objective_ref.ref,
                "objectiveDigest": contract_a.objective_ref.digest,
                "runA": contract_a.harness_run_id,
                "runB": contract_b.harness_run_id,
            },
        )

        e2_condition = (
            result_a.loop_result.stop_code.value == "candidate_completed"
            and result_b.loop_result.stop_code.value == "needs_input"
            and b_before_a_completion == b_after_a_completion
        )
        cases["E2"] = classify(
            e2_condition,
            support="subject A local completion leaves subject B unresolved and does not mutate B durable state",
            falsifier="subject A local completion collapsed peer state/completion scope",
            details={
                "aStop": result_a.loop_result.stop_code.value,
                "bStop": result_b.loop_result.stop_code.value,
                "bStateBeforeACompletion": b_before_a_completion,
                "bStateAfterACompletion": b_after_a_completion,
            },
        )

        # E3/E4: A-derived immutable evidence becomes visible to B, then is separately adopted.
        peer_evidence_content = {
            "sourceRunId": contract_a.harness_run_id,
            "sourceContractDigest": contract_a.digest,
            "sourceStopCode": result_a.loop_result.stop_code.value,
            "sharedClaimRef": SHARED_CLAIM_REF,
        }
        peer_evidence = HarnessStrategyEvidence(
            reference=HarnessBoundReference(
                ref="peer-evidence:for-direct:a-result",
                kind="peer-run-evidence",
                digest=canonical_digest(peer_evidence_content),
            ),
            content=peer_evidence_content,
        )
        context_b = build_harness_strategy_selection_context(
            mandate_b(),
            (profile_b(),),
            (),
            (peer_evidence,),
        )

        selection_visible_only = HarnessAgentStrategySelection(
            context_b.digest,
            b_strategy(context_b, adopted_context_refs=()),
        )
        compiled_visible_only = compile_harness_selected_attempt(
            context_b,
            selection_visible_only,
            harness_run_id="harness-run:for-direct:b-visible-only",
            harness_implementation_id=IMPLEMENTATION_ID,
            created_at_ms=3_000,
        )
        e3_condition = (
            context_b.strategy_evidence == (peer_evidence,)
            and peer_evidence.reference not in compiled_visible_only.contract.context_refs
        )
        cases["E3"] = classify(
            e3_condition,
            support="A-derived evidence can be visible in B selection Context without automatic adoption into B compiled contract",
            falsifier="evidence visibility automatically became B adoption",
            details={
                "sourceRunId": peer_evidence.content["sourceRunId"],
                "evidenceRef": peer_evidence.reference.ref,
                "visibleEvidenceCount": len(context_b.strategy_evidence),
                "adoptedIntoVisibleOnlyContract": peer_evidence.reference
                in compiled_visible_only.contract.context_refs,
            },
        )

        selection_adopted = HarnessAgentStrategySelection(
            context_b.digest,
            b_strategy(context_b, adopted_context_refs=(peer_evidence.reference,)),
        )
        compiled_adopted = compile_harness_selected_attempt(
            context_b,
            selection_adopted,
            harness_run_id="harness-run:for-direct:b-adopted",
            harness_implementation_id=IMPLEMENTATION_ID,
            created_at_ms=4_000,
        )
        adopted_digests = tuple(compiled_adopted.system_manifest.get("adoptedContextDigests", ()))
        e4_condition = (
            peer_evidence.reference in compiled_adopted.contract.context_refs
            and peer_evidence.reference.digest in adopted_digests
            and peer_evidence.content["sourceRunId"] == contract_a.harness_run_id
        )
        cases["E4"] = classify(
            e4_condition,
            support="B explicit adoption binds exact A-derived evidence while preserving A source provenance",
            falsifier="explicit adoption was indistinguishable from visibility or rewrote source provenance",
            details={
                "evidenceRef": peer_evidence.reference.ref,
                "evidenceDigest": peer_evidence.reference.digest,
                "sourceRunId": peer_evidence.content["sourceRunId"],
                "compiledContextRefs": [ref.ref for ref in compiled_adopted.contract.context_refs],
                "adoptedContextDigests": list(adopted_digests),
            },
        )

        # E5: do not fabricate a generic claim-standing object if Harness does not expose one.
        public_realization_claim_surfaces = sorted(
            name
            for name in dir(harness_api)
            if "RealizationClaim" in name or "RealizationStanding" in name
        )
        if public_realization_claim_surfaces:
            cases["E5"] = {
                "classification": "FIXTURE_ONLY_PRESSURE",
                "interpretation": "a possible public realization-claim surface exists and requires separate prebound review before direct use",
                "details": {
                    "sharedClaimRef": SHARED_CLAIM_REF,
                    "publicSurfaces": public_realization_claim_surfaces,
                },
            }
        else:
            cases["E5"] = {
                "classification": "ENGINEERING_GAP",
                "gapCode": "ENGINEERING_GAP_SHARED_REALIZATION_CLAIM_SURFACE",
                "interpretation": "current public Harness API has no generic first-class shared RealizationClaim/per-subject standing surface; metadata-only simulation is not counted as direct evidence",
                "details": {
                    "sharedClaimRef": SHARED_CLAIM_REF,
                    "aEvidenceCarriesClaimRef": peer_evidence.content["sharedClaimRef"]
                    == SHARED_CLAIM_REF,
                    "publicSurfaces": [],
                },
            }

        # E6: two actual Tool-bearing Runs issue distinct Invocations to one safe fake Runtime.
        counting_runtime = CountingRuntime()
        tool_contract_a = run_contract("tool-a", tools=True)
        tool_contract_b = run_contract("tool-b", tools=True)
        tool_run_a = HarnessAgentRun.create(
            root / "tool-subject-a",
            tool_contract_a,
            lambda _contract: ScriptedTurnAdapter(
                (tool_turn("tool-a"), completed_result("tool-a"))
            ),
            execution_binding=execution_binding(tool_contract_a, "tool-a"),
            runtime=counting_runtime,
            clock_ms=FixedClock(),
            monotonic_ms=FixedClock(),
        )
        tool_run_b = HarnessAgentRun.create(
            root / "tool-subject-b",
            tool_contract_b,
            lambda _contract: ScriptedTurnAdapter(
                (tool_turn("tool-b"), completed_result("tool-b"))
            ),
            execution_binding=execution_binding(tool_contract_b, "tool-b"),
            runtime=counting_runtime,
            clock_ms=FixedClock(),
            monotonic_ms=FixedClock(),
        )
        tool_result_a = tool_run_a.run(
            ({"role": "user", "content": "execute same safe fake capability"},)
        )
        tool_result_b = tool_run_b.run(
            ({"role": "user", "content": "execute same safe fake capability"},)
        )
        e6_condition = (
            tool_contract_a.harness_run_id != tool_contract_b.harness_run_id
            and tool_result_a.loop_result.usage["toolCalls"] == 1
            and tool_result_b.loop_result.usage["toolCalls"] == 1
            and len(counting_runtime.calls) == 2
        )
        cases["E6"] = classify(
            e6_condition,
            support="two subject-local Invocations against the same safe fake capability remain distinct and produce two Runtime client calls",
            falsifier="Harness deduplicated distinct cross-subject Invocations solely from shared work/capability",
            details={
                "runA": tool_contract_a.harness_run_id,
                "runB": tool_contract_b.harness_run_id,
                "aToolCalls": tool_result_a.loop_result.usage["toolCalls"],
                "bToolCalls": tool_result_b.loop_result.usage["toolCalls"],
                "runtimeClientCallCount": len(counting_runtime.calls),
                "runtimeCallNames": [call["name"] for call in counting_runtime.calls],
            },
        )

    classifications = [case["classification"] for case in cases.values()]
    if "DIRECT_FALSIFIER" in classifications:
        branch_classification = "FOR_DIRECT_FALSIFIER_FOUND"
        exit_code = 2
    elif "ENGINEERING_GAP" in classifications:
        branch_classification = "MIXED_DIRECT_EVIDENCE"
        exit_code = 0
    else:
        branch_classification = "FOR_DIRECT_SUPPORT_IN_SCOPE"
        exit_code = 0

    return {
        "schemaVersion": 1,
        "experiment": EXPERIMENT,
        "branchClassification": branch_classification,
        "directSupportCases": [
            key for key, value in cases.items() if value["classification"] == "DIRECT_SUPPORT"
        ],
        "directFalsifierCases": [
            key for key, value in cases.items() if value["classification"] == "DIRECT_FALSIFIER"
        ],
        "engineeringGapCases": [
            key for key, value in cases.items() if value["classification"] == "ENGINEERING_GAP"
        ],
        "fixtureOnlyCases": [
            key
            for key, value in cases.items()
            if value["classification"] == "FIXTURE_ONLY_PRESSURE"
        ],
        "cases": cases,
        "exitCode": exit_code,
    }


def main() -> int:
    result = run_experiment()
    print(json.dumps(result, sort_keys=True, indent=2))
    return int(result["exitCode"])


if __name__ == "__main__":
    raise SystemExit(main())

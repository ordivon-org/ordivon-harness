from __future__ import annotations

from dataclasses import replace
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.api import (
    HarnessAgentStrategySelection,
    HarnessBoundReference,
    HarnessExecutionMandate,
    HarnessExecutionProfile,
    HarnessExecutionStrategy,
    HarnessPriorAttemptEvidence,
    HarnessStrategySelectionContext,
    IndependentHarnessRunReceipt,
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    RunBudget,
    build_harness_strategy_selection_context,
    compile_harness_selected_attempt,
    derive_harness_mandate_consumption,
)


D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64


def bound(ref: str, kind: str, digest: str) -> HarnessBoundReference:
    return HarnessBoundReference(ref=ref, kind=kind, digest=digest)


def mandate() -> HarnessExecutionMandate:
    return HarnessExecutionMandate(
        mandate_id="mandate:rsi-p0",
        caller_id="caller:rsi-p0",
        caller_ref="task:rsi-p0",
        objective_ref=bound("objective:rsi-p0", "objective", D1),
        context_refs=(bound("context:rsi-p0", "context", D2),),
        allowed_profile_ids=("profile:cheap", "profile:observe"),
        max_total_tokens=10_000,
        max_wall_time_ms=20_000,
        completion_contract={"mode": "record-candidate"},
        created_at_ms=1_000,
    )


def profile(profile_id: str) -> HarnessExecutionProfile:
    return HarnessExecutionProfile(
        profile_id=profile_id,
        provider_id="provider:scripted",
        adapter_id="adapter:scripted-v1",
        requested_model_id="model:scripted-v1",
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=NO_TOOL_AGENT_GRANT_DIGEST,
        metadata={
            "strategyClass": "initial" if profile_id == "profile:cheap" else "evidence-review"
        },
    )


def strategy(
    context: HarnessStrategySelectionContext,
    *,
    profile_id: str,
    adopted_context_refs: tuple[HarnessBoundReference, ...] = (),
    max_total_tokens: int = 2_000,
    max_wall_time_ms: int = 4_000,
) -> HarnessExecutionStrategy:
    return HarnessExecutionStrategy(
        mandate_digest=context.mandate.digest,
        attempt_index=context.attempt_index,
        profile_id=profile_id,
        budget=RunBudget(
            max_model_calls=3,
            max_tool_calls=0,
            max_observation_bytes=32_768,
            max_wall_time_ms=max_wall_time_ms,
            max_total_tokens=max_total_tokens,
            max_model_retries=1,
        ).to_contract_dict(),
        provider_options={"temperature": 0},
        adopted_context_refs=adopted_context_refs,
        rationale="Agent selected the next attempt from exact prior-attempt evidence.",
    )


def receipt(
    compiled,
    *,
    total_tokens: int,
    wall_time_ms: int,
    stop_reason: str = "failed",
    termination_code: str = "provider_failed",
) -> IndependentHarnessRunReceipt:
    conclusion_digest = D3 if stop_reason == "completed" else None
    contract = compiled.contract
    return IndependentHarnessRunReceipt(
        harness_run_id=contract.harness_run_id,
        caller_id=contract.caller_id,
        caller_run_ref=contract.caller_run_ref,
        contract_digest=contract.digest,
        harness_implementation_id=contract.harness_implementation_id,
        system_manifest_digest=contract.system_manifest_ref.digest,
        started_at_ms=contract.created_at_ms,
        finished_at_ms=contract.created_at_ms + wall_time_ms,
        stop_reason=stop_reason,
        termination_code=termination_code,
        trace_digest=canonical_digest({"run": contract.harness_run_id, "trace": 1}),
        context_digests=tuple(item.digest for item in contract.context_refs),
        tool_catalog_digest=contract.tool_catalog_digest,
        tool_grant_digest=contract.tool_grant_digest,
        runtime_job_refs=(),
        artifact_refs=(),
        usage={
            "modelCalls": 1,
            "toolCalls": 0,
            "observationBytes": 0,
            "totalTokens": total_tokens,
            "wallTimeMs": wall_time_ms,
        },
        conclusion_digest=conclusion_digest,
    )


def evidence(compiled, **receipt_kwargs) -> HarnessPriorAttemptEvidence:
    return HarnessPriorAttemptEvidence(
        compiled_attempt=compiled,
        receipt=receipt(compiled, **receipt_kwargs),
    )


def agent_select(context: HarnessStrategySelectionContext) -> HarnessAgentStrategySelection:
    """Tiny deterministic Agent stand-in: only the selection context is visible."""
    if not context.prior_attempts:
        selected = strategy(context, profile_id="profile:cheap")
    else:
        selected = strategy(
            context,
            profile_id="profile:observe",
            adopted_context_refs=(context.consumption.receipt_refs[-1],),
            max_total_tokens=min(3_000, context.remaining_total_tokens),
            max_wall_time_ms=min(5_000, context.remaining_wall_time_ms),
        )
    return HarnessAgentStrategySelection(context.digest, selected)


class HarnessStrategySelectionP0Tests(unittest.TestCase):
    def test_prior_attempt_evidence_round_trip_binds_manifest_contract_and_receipt(self) -> None:
        value = mandate()
        first = build_harness_strategy_selection_context(
            value,
            (profile("profile:cheap"), profile("profile:observe")),
        )
        compiled = compile_harness_selected_attempt(
            first,
            agent_select(first),
            harness_run_id="harness-run:rsi-p0-round-trip",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        prior = evidence(compiled, total_tokens=700, wall_time_ms=1_500)
        decoded = HarnessPriorAttemptEvidence.from_dict(prior.to_dict())
        self.assertEqual(decoded, prior)
        self.assertEqual(decoded.attempt_index, 1)

    def test_exact_attempt_evidence_mechanically_derives_consumption(self) -> None:
        value = mandate()
        first = build_harness_strategy_selection_context(
            value,
            (profile("profile:cheap"), profile("profile:observe")),
        )
        compiled = compile_harness_selected_attempt(
            first,
            agent_select(first),
            harness_run_id="harness-run:rsi-p0-1",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        prior = evidence(compiled, total_tokens=700, wall_time_ms=1_500)
        consumption = derive_harness_mandate_consumption(value, (prior,))
        self.assertEqual(consumption.completed_attempts, 1)
        self.assertEqual(consumption.consumed_total_tokens, 700)
        self.assertEqual(consumption.consumed_wall_time_ms, 1_500)
        self.assertEqual(consumption.receipt_refs[0].digest, prior.receipt.digest)
        self.assertEqual(
            consumption.receipt_refs[0].ref,
            "receipt:harness-run:rsi-p0-1",
        )

    def test_same_named_changed_mandate_cannot_reuse_old_receipt(self) -> None:
        value = mandate()
        first = build_harness_strategy_selection_context(value, (profile("profile:cheap"),))
        compiled = compile_harness_selected_attempt(
            first,
            agent_select(first),
            harness_run_id="harness-run:rsi-p0-old-mandate",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        prior = evidence(compiled, total_tokens=100, wall_time_ms=200)
        changed = replace(value, max_total_tokens=value.max_total_tokens + 1)
        self.assertEqual(changed.mandate_id, value.mandate_id)
        self.assertNotEqual(changed.digest, value.digest)
        with self.assertRaisesRegex(ValueError, "different Mandate digest"):
            derive_harness_mandate_consumption(changed, (prior,))

    def test_agent_selects_second_attempt_from_receipt_without_caller_profile_resolution(self) -> None:
        value = mandate()
        profiles = (profile("profile:cheap"), profile("profile:observe"))
        context1 = build_harness_strategy_selection_context(value, profiles)
        compiled1 = compile_harness_selected_attempt(
            context1,
            agent_select(context1),
            harness_run_id="harness-run:rsi-p0-loop-1",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        self.assertEqual(compiled1.system_manifest["profileId"], "profile:cheap")
        prior = evidence(compiled1, total_tokens=800, wall_time_ms=1_000)

        context2 = build_harness_strategy_selection_context(value, profiles, (prior,))
        selection2 = agent_select(context2)
        compiled2 = compile_harness_selected_attempt(
            context2,
            selection2,
            harness_run_id="harness-run:rsi-p0-loop-2",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=4_000,
        )
        self.assertEqual(context2.attempt_index, 2)
        self.assertEqual(compiled2.system_manifest["profileId"], "profile:observe")
        self.assertEqual(
            compiled2.contract.context_refs[-1].digest,
            prior.receipt.digest,
        )
        self.assertEqual(
            compiled2.system_manifest["priorReceiptDigests"],
            (prior.receipt.digest,),
        )
        self.assertEqual(
            compiled2.system_manifest["adoptedContextDigests"],
            (prior.receipt.digest,),
        )

    def test_selection_is_fenced_to_exact_context_digest(self) -> None:
        value = mandate()
        profiles = (profile("profile:cheap"), profile("profile:observe"))
        context1 = build_harness_strategy_selection_context(value, profiles)
        stale_selection = agent_select(context1)
        compiled1 = compile_harness_selected_attempt(
            context1,
            stale_selection,
            harness_run_id="harness-run:rsi-p0-stale-1",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        context2 = build_harness_strategy_selection_context(
            value,
            profiles,
            (evidence(compiled1, total_tokens=100, wall_time_ms=200),),
        )
        with self.assertRaisesRegex(ValueError, "stale context"):
            compile_harness_selected_attempt(
                context2,
                stale_selection,
                harness_run_id="harness-run:rsi-p0-stale-2",
                harness_implementation_id="ordivon-harness@test",
                created_at_ms=3_000,
            )

    def test_attempt_evidence_binding_and_accounting_fail_closed(self) -> None:
        value = mandate()
        context = build_harness_strategy_selection_context(
            value, (profile("profile:cheap"),)
        )
        compiled = compile_harness_selected_attempt(
            context,
            agent_select(context),
            harness_run_id="harness-run:rsi-p0-bad-receipt",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        good = receipt(compiled, total_tokens=100, wall_time_ms=200)
        with self.subTest("contract"):
            with self.assertRaisesRegex(ValueError, "Contract digest differs"):
                HarnessPriorAttemptEvidence(
                    compiled,
                    replace(good, contract_digest=D3),
                )
        with self.subTest("manifest"):
            with self.assertRaisesRegex(ValueError, "System Manifest digest differs"):
                HarnessPriorAttemptEvidence(
                    compiled,
                    replace(good, system_manifest_digest=D3),
                )
        with self.subTest("usage"):
            prior = HarnessPriorAttemptEvidence(
                compiled,
                replace(good, usage={"wallTimeMs": 200}),
            )
            with self.assertRaisesRegex(ValueError, "usage.totalTokens"):
                derive_harness_mandate_consumption(value, (prior,))

    def test_agent_can_only_adopt_receipts_visible_in_selection_context(self) -> None:
        value = mandate()
        context = build_harness_strategy_selection_context(
            value,
            (profile("profile:cheap"), profile("profile:observe")),
        )
        invented = bound("receipt:invented", "independent-harness-run-receipt", D3)
        selection = HarnessAgentStrategySelection(
            context.digest,
            strategy(
                context,
                profile_id="profile:cheap",
                adopted_context_refs=(invented,),
            ),
        )
        with self.assertRaisesRegex(ValueError, "not an exact prior receipt"):
            compile_harness_selected_attempt(
                context,
                selection,
                harness_run_id="harness-run:rsi-p0-invented",
                harness_implementation_id="ordivon-harness@test",
                created_at_ms=2_000,
            )

    def test_agent_cannot_select_unavailable_profile_even_if_mandate_allows_it(self) -> None:
        value = mandate()
        context = build_harness_strategy_selection_context(
            value,
            (profile("profile:cheap"),),
        )
        selection = HarnessAgentStrategySelection(
            context.digest,
            strategy(context, profile_id="profile:observe"),
        )
        with self.assertRaisesRegex(ValueError, "unavailable profile"):
            compile_harness_selected_attempt(
                context,
                selection,
                harness_run_id="harness-run:rsi-p0-unavailable",
                harness_implementation_id="ordivon-harness@test",
                created_at_ms=2_000,
            )

    def test_context_round_trip_recomputes_all_derived_authority(self) -> None:
        value = mandate()
        profiles = (profile("profile:cheap"), profile("profile:observe"))
        context1 = build_harness_strategy_selection_context(value, profiles)
        compiled1 = compile_harness_selected_attempt(
            context1,
            agent_select(context1),
            harness_run_id="harness-run:rsi-p0-context-round-trip",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        context2 = build_harness_strategy_selection_context(
            value,
            profiles,
            (evidence(compiled1, total_tokens=100, wall_time_ms=200),),
        )
        decoded = HarnessStrategySelectionContext.from_dict(context2.to_dict())
        self.assertEqual(decoded, context2)
        self.assertEqual(decoded.digest, context2.digest)


if __name__ == "__main__":
    unittest.main()

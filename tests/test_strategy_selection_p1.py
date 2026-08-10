from __future__ import annotations

from dataclasses import replace
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.api import (
    HarnessAgentStrategySelection,
    HarnessBoundReference,
    HarnessPriorAttemptEvidence,
    HarnessPrivacyPolicy,
    HarnessStrategyEvidence,
    IndependentCompletionProposal,
    build_harness_strategy_selection_context,
    compile_harness_selected_attempt,
)
from tests.test_strategy_selection_p0 import (
    D3,
    agent_select,
    mandate,
    profile,
    receipt,
    strategy,
)


def completed_evidence(compiled) -> HarnessPriorAttemptEvidence:
    run_receipt = receipt(
        compiled,
        total_tokens=700,
        wall_time_ms=900,
        stop_reason="completed",
        termination_code="candidate_completed",
    )
    proposal = IndependentCompletionProposal(
        completion_proposal_id=f"completion-proposal:{run_receipt.harness_run_id}",
        harness_run_id=run_receipt.harness_run_id,
        caller_id=run_receipt.caller_id,
        caller_run_ref=run_receipt.caller_run_ref,
        contract_digest=run_receipt.contract_digest,
        run_receipt_digest=run_receipt.digest,
        trace_digest=run_receipt.trace_digest,
        summary='{"decision":"provisional","reason":"missing exact memory"}',
        evidence_refs=(),
        artifact_refs=(),
        unresolved_unknowns=("Exact memory for candidate delta remains unknown.",),
        usage=dict(run_receipt.usage),
        created_at_ms=run_receipt.finished_at_ms,
    )
    return HarnessPriorAttemptEvidence(compiled, run_receipt, proposal)


def verification_evidence(*, ref: str = "strategy-evidence:verification:attempt-1") -> HarnessStrategyEvidence:
    content = {
        "verdict": "insufficient",
        "reason": "The previous candidate cannot be certified while exact memory remains unknown.",
        "requiredEvidence": ["complete candidate memory"],
        "owner": "domain-verifier:test",
    }
    return HarnessStrategyEvidence(
        reference=HarnessBoundReference(
            ref=ref,
            kind="domain-verification",
            digest=canonical_digest(content),
        ),
        content=content,
    )


class HarnessStrategySelectionP1Tests(unittest.TestCase):
    def _first_attempt(self):
        value = mandate()
        profiles = (profile("profile:cheap"), profile("profile:observe"))
        context = build_harness_strategy_selection_context(value, profiles)
        compiled = compile_harness_selected_attempt(
            context,
            agent_select(context),
            harness_run_id="harness-run:rsi-p1-prior-result-1",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        return value, profiles, compiled

    def test_completion_proposal_is_exact_prior_attempt_evidence(self) -> None:
        value, profiles, compiled = self._first_attempt()
        prior = completed_evidence(compiled)
        decoded = HarnessPriorAttemptEvidence.from_dict(prior.to_dict())
        self.assertEqual(decoded, prior)
        assert prior.completion_proposal_ref is not None
        self.assertEqual(
            prior.completion_proposal_ref.digest,
            prior.completion_proposal.digest,
        )
        context = build_harness_strategy_selection_context(value, profiles, (prior,))
        encoded = context.to_dict()
        prior_encoded = encoded["priorAttempts"]
        self.assertIsInstance(prior_encoded, list)
        assert isinstance(prior_encoded, list)
        self.assertEqual(
            prior_encoded[0]["completionProposal"]["unresolvedUnknowns"],
            ["Exact memory for candidate delta remains unknown."],
        )

    def test_agent_may_adopt_exact_prior_completion_proposal(self) -> None:
        value, profiles, compiled = self._first_attempt()
        prior = completed_evidence(compiled)
        context = build_harness_strategy_selection_context(value, profiles, (prior,))
        proposal_ref = prior.completion_proposal_ref
        assert proposal_ref is not None
        selection = HarnessAgentStrategySelection(
            context.digest,
            strategy(
                context,
                profile_id="profile:observe",
                adopted_context_refs=(proposal_ref,),
                max_total_tokens=2_000,
                max_wall_time_ms=4_000,
            ),
        )
        second = compile_harness_selected_attempt(
            context,
            selection,
            harness_run_id="harness-run:rsi-p1-prior-result-2",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=4_000,
        )
        self.assertEqual(second.contract.context_refs[-1], proposal_ref)
        self.assertEqual(
            second.system_manifest["adoptedContextDigests"],
            (proposal_ref.digest,),
        )

    def test_completion_proposal_receipt_binding_fails_closed(self) -> None:
        _, _, compiled = self._first_attempt()
        prior = completed_evidence(compiled)
        assert prior.completion_proposal is not None
        with self.assertRaisesRegex(ValueError, "Receipt digest differs"):
            HarnessPriorAttemptEvidence(
                prior.compiled_attempt,
                prior.receipt,
                replace(prior.completion_proposal, run_receipt_digest=D3),
            )

    def test_noncompleted_attempt_cannot_carry_completion_proposal(self) -> None:
        _, _, compiled = self._first_attempt()
        completed = completed_evidence(compiled)
        assert completed.completion_proposal is not None
        failed_receipt = receipt(compiled, total_tokens=100, wall_time_ms=200)
        proposal = replace(
            completed.completion_proposal,
            run_receipt_digest=failed_receipt.digest,
            trace_digest=failed_receipt.trace_digest,
        )
        with self.assertRaisesRegex(ValueError, "non-completed"):
            HarnessPriorAttemptEvidence(compiled, failed_receipt, proposal)

    def test_legacy_p0_prior_evidence_without_proposal_remains_readable(self) -> None:
        _, _, compiled = self._first_attempt()
        failed_receipt = receipt(compiled, total_tokens=100, wall_time_ms=200)
        legacy = {
            "compiledAttempt": compiled.to_dict(),
            "receipt": failed_receipt.to_dict(),
        }
        decoded = HarnessPriorAttemptEvidence.from_dict(legacy)
        self.assertIsNone(decoded.completion_proposal)
        self.assertEqual(decoded.to_dict(), legacy)

    def test_strategy_evidence_is_digest_bound_immutable_snapshot(self) -> None:
        raw = {
            "verdict": "insufficient",
            "details": {"missing": ["candidate memory"]},
        }
        evidence = HarnessStrategyEvidence(
            HarnessBoundReference(
                ref="strategy-evidence:immutable",
                kind="domain-verification",
                digest=canonical_digest(raw),
            ),
            raw,
        )
        raw["details"]["missing"].append("invented later")
        self.assertEqual(
            evidence.to_dict()["content"]["details"]["missing"],
            ["candidate memory"],
        )
        self.assertEqual(HarnessStrategyEvidence.from_dict(evidence.to_dict()), evidence)
        with self.assertRaisesRegex(ValueError, "digest differs"):
            HarnessStrategyEvidence(
                HarnessBoundReference(
                    ref="strategy-evidence:wrong-digest",
                    kind="domain-verification",
                    digest=D3,
                ),
                {"verdict": "insufficient"},
            )

    def test_agent_may_adopt_exact_independent_strategy_evidence(self) -> None:
        value, profiles, compiled = self._first_attempt()
        prior = completed_evidence(compiled)
        verification = verification_evidence()
        context = build_harness_strategy_selection_context(
            value,
            profiles,
            (prior,),
            (verification,),
        )
        proposal_ref = prior.completion_proposal_ref
        assert proposal_ref is not None
        selection = HarnessAgentStrategySelection(
            context.digest,
            strategy(
                context,
                profile_id="profile:observe",
                adopted_context_refs=(proposal_ref, verification.reference),
                max_total_tokens=2_000,
                max_wall_time_ms=4_000,
            ),
        )
        second = compile_harness_selected_attempt(
            context,
            selection,
            harness_run_id="harness-run:rsi-p1-independent-verification",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=4_000,
        )
        self.assertEqual(second.contract.context_refs[-2:], (proposal_ref, verification.reference))
        encoded = context.to_dict()
        self.assertEqual(encoded["strategyEvidence"][0]["content"]["verdict"], "insufficient")

    def test_strategy_evidence_reference_cannot_alias_prior_attempt_evidence(self) -> None:
        value, profiles, compiled = self._first_attempt()
        prior = completed_evidence(compiled)
        conflicting = verification_evidence(ref=prior.receipt_ref.ref)
        with self.assertRaisesRegex(ValueError, "conflicts with prior attempt evidence"):
            build_harness_strategy_selection_context(
                value,
                profiles,
                (prior,),
                (conflicting,),
            )

    def test_legacy_selection_context_without_strategy_evidence_preserves_digest(self) -> None:
        value = mandate()
        profiles = (profile("profile:cheap"),)
        context = build_harness_strategy_selection_context(value, profiles)
        encoded = context.to_dict()
        self.assertNotIn("strategyEvidence", encoded)
        original_digest = canonical_digest(encoded)
        decoded = type(context).from_dict(encoded)
        self.assertEqual(decoded.strategy_evidence, ())
        self.assertEqual(decoded.digest, original_digest)

    def test_mandate_privacy_authority_flows_to_compiled_attempt(self) -> None:
        value = replace(
            mandate(),
            privacy=HarnessPrivacyPolicy(
                content_policy="bounded-private-content",
                allow_model_content=True,
                allow_tool_content=False,
            ),
        )
        profiles = (profile("profile:cheap"),)
        context = build_harness_strategy_selection_context(value, profiles)
        compiled = compile_harness_selected_attempt(
            context,
            agent_select(context),
            harness_run_id="harness-run:rsi-p1-private-attempt",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        self.assertEqual(compiled.contract.privacy, value.privacy)
        self.assertTrue(compiled.contract.privacy.allow_model_content)

    def test_legacy_mandate_without_privacy_preserves_digest_and_defaults_metadata_only(self) -> None:
        value = mandate()
        encoded = value.to_dict()
        self.assertNotIn("privacy", encoded)
        original_digest = canonical_digest(encoded)
        decoded = type(value).from_dict(encoded)
        self.assertIsNone(decoded.privacy)
        self.assertFalse(decoded.effective_privacy.allow_model_content)
        self.assertEqual(decoded.digest, original_digest)


if __name__ == "__main__":
    unittest.main()

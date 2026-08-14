from __future__ import annotations

from dataclasses import replace
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.api import (
    CompiledHarnessAttempt,
    HarnessBoundReference,
    HarnessExecutionMandate,
    HarnessMandateConsumption,
    HarnessExecutionProfile,
    HarnessExecutionStrategy,
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    RunBudget,
    compile_harness_attempt,
)


D1 = "sha256:" + "a" * 64
D2 = "sha256:" + "b" * 64
D3 = "sha256:" + "c" * 64


def bound(name: str, kind: str, digest: str) -> HarnessBoundReference:
    return HarnessBoundReference(name, kind, digest)


def mandate() -> HarnessExecutionMandate:
    return HarnessExecutionMandate(
        mandate_id="mandate:test-agent-first",
        caller_id="caller:test-agent-first",
        caller_ref="task:test-agent-first",
        objective_ref=bound("objective:test-agent-first", "objective", D1),
        context_refs=(bound("context:test-agent-first", "context", D2),),
        allowed_profile_ids=("profile:no-tool", "profile:observe"),
        max_total_tokens=65_536,
        max_wall_time_ms=120_000,
        completion_contract={"mode": "record-candidate"},
        created_at_ms=1_000,
    )


def profile(profile_id: str = "profile:no-tool") -> HarnessExecutionProfile:
    return HarnessExecutionProfile(
        profile_id=profile_id,
        provider_id="provider:scripted",
        adapter_id="adapter:scripted-v1",
        requested_model_id="model:scripted-v1",
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=NO_TOOL_AGENT_GRANT_DIGEST,
        metadata={"effectClass": "none" if profile_id == "profile:no-tool" else "observation-only"},
    )


def strategy(
    value: HarnessExecutionMandate,
    *,
    profile_id: str = "profile:no-tool",
    attempt_index: int = 1,
    max_model_calls: int = 8,
    max_tool_calls: int = 0,
    max_total_tokens: int = 65_536,
    max_wall_time_ms: int = 120_000,
    adopted_context_refs: tuple[HarnessBoundReference, ...] = (),
) -> HarnessExecutionStrategy:
    budget = RunBudget(
        max_model_calls=max_model_calls,
        max_tool_calls=max_tool_calls,
        max_observation_bytes=131_072,
        max_wall_time_ms=max_wall_time_ms,
        max_total_tokens=max_total_tokens,
        max_model_retries=1,
    )
    return HarnessExecutionStrategy(
        mandate_digest=value.digest,
        attempt_index=attempt_index,
        profile_id=profile_id,
        budget=budget.to_contract_dict(),
        provider_options={"maxOutputTokens": 2_048},
        adopted_context_refs=adopted_context_refs,
        rationale="Agent selected one bounded attempt strategy.",
    )


class ExecutionMandateTests(unittest.TestCase):
    def test_mandate_round_trip_and_snapshot_are_stable(self) -> None:
        completion = {"mode": "structured-result-v1", "resultSchema": {"type": "object"}}
        value = replace(mandate(), completion_contract=completion)
        digest = value.digest
        completion["resultSchema"]["type"] = "array"
        self.assertEqual(value.digest, digest)
        self.assertEqual(HarnessExecutionMandate.from_dict(value.to_dict()), value)
        self.assertEqual(value.to_dict()["completionContract"]["resultSchema"]["type"], "object")
        p = profile()
        self.assertEqual(HarnessExecutionProfile.from_dict(p.to_dict()), p)
        selected = strategy(value)
        self.assertEqual(HarnessExecutionStrategy.from_dict(selected.to_dict()), selected)

    def test_mandate_rejects_non_string_completion_contract_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "authority object keys must be strings"):
            replace(mandate(), completion_contract={1: "must-not-be-coerced"})  # type: ignore[dict-item]

    def test_delegated_digest_authority_rejects_non_hex_payloads(self) -> None:
        invalid = "sha256:" + "g" * 64
        with self.subTest("consumption"):
            with self.assertRaisesRegex(ValueError, "must be a sha256 digest"):
                HarnessMandateConsumption(
                    mandate_digest=invalid,
                    completed_attempts=0,
                    consumed_total_tokens=0,
                    consumed_wall_time_ms=0,
                )
        with self.subTest("execution-profile"):
            with self.assertRaisesRegex(ValueError, "must be a sha256 digest"):
                replace(profile(), tool_catalog_digest=invalid)

    def test_compiler_separates_aggregate_mandate_from_attempt_step_limits(self) -> None:
        value = mandate()
        selected = strategy(
            value,
            max_model_calls=8,
            max_tool_calls=7,
            max_total_tokens=65_536,
            max_wall_time_ms=120_000,
        )
        compiled = compile_harness_attempt(
            value,
            profile(),
            selected,
            harness_run_id="harness-run:mandate-attempt-1",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        self.assertIsInstance(compiled, CompiledHarnessAttempt)
        self.assertEqual(compiled.contract.caller_run_ref, value.mandate_id)
        self.assertEqual(compiled.contract.budget["maxModelCalls"], 8)
        self.assertEqual(compiled.contract.budget["maxToolCalls"], 7)
        self.assertEqual(compiled.contract.budget["maxTotalTokens"], value.max_total_tokens)
        self.assertEqual(compiled.system_manifest["mandateDigest"], value.digest)
        self.assertEqual(compiled.system_manifest["strategyDigest"], selected.digest)

    def test_replan_attempt_can_adopt_prior_receipt_evidence_and_switch_profile(self) -> None:
        value = mandate()
        prior = bound("receipt:attempt-1", "run-receipt", D3)
        selected = strategy(
            value,
            profile_id="profile:no-tool",
            attempt_index=2,
            max_total_tokens=32_768,
            max_wall_time_ms=60_000,
            adopted_context_refs=(prior,),
        )
        consumption = HarnessMandateConsumption(
            mandate_digest=value.digest,
            completed_attempts=1,
            consumed_total_tokens=5_000,
            consumed_wall_time_ms=10_000,
            receipt_refs=(prior,),
        )
        self.assertEqual(
            HarnessMandateConsumption.from_dict(consumption.to_dict()), consumption
        )
        compiled = compile_harness_attempt(
            value,
            profile("profile:no-tool"),
            selected,
            consumption=consumption,
            harness_run_id="harness-run:mandate-attempt-2",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=3_000,
        )
        self.assertEqual(compiled.contract.context_refs[-1], prior)
        self.assertEqual(compiled.system_manifest["attemptIndex"], 2)
        self.assertEqual(compiled.system_manifest["mandateConsumptionDigest"], consumption.digest)
        self.assertEqual(compiled.system_manifest["priorReceiptDigests"], (D3,))
        self.assertEqual(compiled.system_manifest["adoptedContextDigests"], (D3,))
        self.assertEqual(
            compiled.to_dict()["systemManifest"]["adoptedContextDigests"], [D3]
        )

    def test_profile_outside_capability_envelope_is_rejected(self) -> None:
        value = mandate()
        selected = strategy(value, profile_id="profile:mutation")
        with self.assertRaisesRegex(ValueError, "outside the Mandate capability envelope"):
            compile_harness_attempt(
                value,
                profile("profile:mutation"),
                selected,
                harness_run_id="harness-run:disallowed-profile",
                harness_implementation_id="ordivon-harness@test",
                created_at_ms=2_000,
            )

    def test_strategy_cannot_exceed_aggregate_economic_envelope(self) -> None:
        value = mandate()
        with self.subTest("tokens"):
            selected = strategy(value, max_total_tokens=65_537)
            with self.assertRaisesRegex(ValueError, "remaining Mandate total-token envelope"):
                compile_harness_attempt(
                    value,
                    profile(),
                    selected,
                    harness_run_id="harness-run:too-many-tokens",
                    harness_implementation_id="ordivon-harness@test",
                    created_at_ms=2_000,
                )
        with self.subTest("wall-time"):
            selected = strategy(value, max_wall_time_ms=120_001)
            with self.assertRaisesRegex(ValueError, "remaining Mandate wall-time envelope"):
                compile_harness_attempt(
                    value,
                    profile(),
                    selected,
                    harness_run_id="harness-run:too-much-time",
                    harness_implementation_id="ordivon-harness@test",
                    created_at_ms=2_000,
                )


    def test_later_attempt_requires_consumption_and_reserves_only_remaining_envelope(self) -> None:
        value = mandate()
        selected = strategy(
            value,
            attempt_index=2,
            max_total_tokens=55_000,
            max_wall_time_ms=70_000,
        )
        with self.assertRaisesRegex(ValueError, "require explicit consumption"):
            compile_harness_attempt(
                value, profile(), selected,
                harness_run_id="harness-run:missing-consumption",
                harness_implementation_id="ordivon-harness@test", created_at_ms=2_000,
            )
        consumption = HarnessMandateConsumption(
            mandate_digest=value.digest,
            completed_attempts=1,
            consumed_total_tokens=10_000,
            consumed_wall_time_ms=40_000,
        )
        compiled = compile_harness_attempt(
            value, profile(), selected, consumption=consumption,
            harness_run_id="harness-run:remaining-envelope",
            harness_implementation_id="ordivon-harness@test", created_at_ms=2_000,
        )
        self.assertEqual(
            compiled.system_manifest["remainingEconomicEnvelope"]["maxTotalTokens"],
            55_536,
        )
        too_large = replace(
            selected,
            budget=RunBudget(
                max_model_calls=8, max_tool_calls=0,
                max_observation_bytes=131_072, max_wall_time_ms=70_000,
                max_total_tokens=56_000, max_model_retries=1,
            ).to_contract_dict(),
        )
        with self.assertRaisesRegex(ValueError, "remaining Mandate total-token envelope"):
            compile_harness_attempt(
                value, profile(), too_large, consumption=consumption,
                harness_run_id="harness-run:remaining-envelope-too-large",
                harness_implementation_id="ordivon-harness@test", created_at_ms=2_000,
            )

    def test_strategy_must_bind_exact_mandate_and_complete_run_budget(self) -> None:
        value = mandate()
        selected = strategy(value)
        stale = replace(selected, mandate_digest=canonical_digest({"other": "mandate"}))
        with self.assertRaisesRegex(ValueError, "different Mandate"):
            compile_harness_attempt(
                value,
                profile(),
                stale,
                harness_run_id="harness-run:stale-mandate",
                harness_implementation_id="ordivon-harness@test",
                created_at_ms=2_000,
            )
        incomplete_budget = dict(selected.budget)
        incomplete_budget.pop("maxNoProgressTurns")
        with self.assertRaisesRegex(ValueError, "every current RunBudget field"):
            replace(selected, budget=incomplete_budget)


    def test_am1_loop_driver_is_attempt_bound_without_contract_schema_expansion(self) -> None:
        value = mandate()
        selected = strategy(value)
        driver_digest = "sha256:" + "d" * 64
        selected_profile = replace(
            profile(),
            metadata={
                "effectClass": "none",
                "loopDriver": {
                    "driverId": "loop-driver:sequential-v1",
                    "driverDigest": driver_digest,
                },
            },
        )
        compiled = compile_harness_attempt(
            value,
            selected_profile,
            selected,
            harness_run_id="harness-run:am1-loop-driver",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )
        self.assertEqual(
            compiled.system_manifest["loopDriver"],
            {
                "driverId": "loop-driver:sequential-v1",
                "driverDigest": driver_digest,
            },
        )
        manifest_value = compiled.to_dict()["systemManifest"]
        assert isinstance(manifest_value, dict)
        self.assertEqual(
            compiled.contract.system_manifest_ref.digest,
            canonical_digest(manifest_value),
        )
        round_trip = CompiledHarnessAttempt.from_dict(compiled.to_dict())
        self.assertEqual(round_trip, compiled)

        invalid_profile = replace(
            profile(),
            metadata={"loopDriver": {"driverId": "loop-driver:broken"}},
        )
        with self.assertRaisesRegex(ValueError, "loopDriver must contain"):
            compile_harness_attempt(
                value,
                invalid_profile,
                selected,
                harness_run_id="harness-run:am1-invalid-loop-driver",
                harness_implementation_id="ordivon-harness@test",
                created_at_ms=2_000,
            )


if __name__ == "__main__":
    unittest.main()

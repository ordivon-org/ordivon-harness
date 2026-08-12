from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from anc_canonical import canonical_digest
from ordivon_harness.api import (
    AgentTurnResult,
    HarnessAgentRun,
    HarnessAgentRunCompositionError,
    HarnessBoundReference,
    HarnessPrivacyPolicy,
    HarnessProviderRoute,
    HarnessProviderUsePolicy,
    HarnessRunContract,
)
from ordivon_harness.ordivon.model import AgentRunConclusion, ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
)


def digest(label: str) -> str:
    return canonical_digest({"gva4": label})


def restricted() -> HarnessBoundReference:
    return HarnessBoundReference(
        "dataset:lost-in-transcription:synthetic-fixture",
        "restricted-dataset",
        digest("restricted-bytes"),
    )


def policy(*, provider: str = "provider:local-open-weight") -> HarnessProviderUsePolicy:
    return HarnessProviderUsePolicy(
        policy_id="provider-use-policy:gva4-lost-in-transcription",
        restricted_inputs=(restricted(),),
        allowed_routes=(
            HarnessProviderRoute(
                provider_id=provider,
                adapter_id=ScriptedTurnAdapter.adapter_id,
                requested_model_id=ScriptedTurnAdapter.model_id,
            ),
        ),
    )


def contract(*, provider: str, bound_policy: HarnessProviderUsePolicy | None) -> HarnessRunContract:
    source_refs = (restricted(),)
    if bound_policy is not None:
        source_refs += (bound_policy.bound_reference,)
    return HarnessRunContract(
        harness_run_id="harness-run:gva4-policy",
        harness_implementation_id="ordivon-harness@gva4",
        caller_id="caller:gva4",
        caller_run_ref="experiment:gva4",
        objective_ref=HarnessBoundReference("objective:gva4", "objective", digest("objective")),
        context_refs=(HarnessBoundReference("context:gva4", "context", digest("context")),),
        source_refs=source_refs,
        provider_id=provider,
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=NO_TOOL_AGENT_GRANT_DIGEST,
        budget={
            "maxModelCalls": 1,
            "maxToolCalls": 0,
            "maxObservationBytes": 65536,
            "maxWallTimeMs": 10000,
            "maxTotalTokens": 10000,
            "maxModelRetries": 0,
            "maxToolCorrections": 0,
            "maxConclusionCorrections": 1,
            "maxObservationOnlyTurns": 1,
            "maxNoProgressTurns": 1,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference("manifest:gva4", "system-manifest", digest("manifest")),
        created_at_ms=1000,
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=False,
        ),
    )


def result() -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:gva4",
        model_id=ScriptedTurnAdapter.model_id,
        content="local-only synthetic result",
        tool_calls=(),
        conclusion=AgentRunConclusion(status="candidate_completed", summary="done"),
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="stop",
        raw_response_digest=digest("response"),
    )


class GVA4ProviderUsePolicyTests(unittest.TestCase):
    def test_restricted_input_rejects_unlisted_hosted_route_before_provider_factory_and_state(self):
        p = policy()
        value = contract(provider="provider:deepseek", bound_policy=p)
        calls = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            def factory(_contract):
                nonlocal calls
                calls += 1
                raise AssertionError("provider factory must not run")
            with self.assertRaisesRegex(
                HarnessAgentRunCompositionError,
                "Provider route is not admitted",
            ):
                HarnessAgentRun.create(root, value, factory, provider_use_policy=p)
            self.assertEqual(calls, 0)
            self.assertFalse(root.exists())

    def test_exact_allowed_route_runs_without_weakening_existing_provider_identity(self):
        p = policy()
        value = contract(provider="provider:local-open-weight", bound_policy=p)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            adapter = ScriptedTurnAdapter((result(),))
            run = HarnessAgentRun.create(
                root,
                value,
                lambda _contract: adapter,
                provider_use_policy=p,
                clock_ms=lambda: 1000,
                monotonic_ms=lambda: 1000,
            )
            execution = run.run(({"role": "user", "content": "synthetic restricted bytes"},))
            self.assertEqual(execution.loop_result.stop_code.value, "candidate_completed")

    def test_policy_is_required_when_contract_binds_it(self):
        p = policy()
        value = contract(provider="provider:local-open-weight", bound_policy=p)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            with self.assertRaisesRegex(HarnessAgentRunCompositionError, "requires its exact"):
                HarnessAgentRun.create(root, value, lambda _: ScriptedTurnAdapter((result(),)))
            self.assertFalse(root.exists())

    def test_policy_cannot_be_supplied_without_contract_binding(self):
        p = policy()
        value = contract(provider="provider:local-open-weight", bound_policy=None)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            with self.assertRaisesRegex(HarnessAgentRunCompositionError, "not bound"):
                HarnessAgentRun.create(
                    root, value, lambda _: ScriptedTurnAdapter((result(),)), provider_use_policy=p
                )
            self.assertFalse(root.exists())

    def test_policy_rejects_digest_substitution_for_restricted_input(self):
        p = HarnessProviderUsePolicy(
            policy_id="provider-use-policy:gva4-lost-in-transcription",
            restricted_inputs=(
                HarnessBoundReference(
                    restricted().ref,
                    restricted().kind,
                    digest("different-bytes"),
                ),
            ),
            allowed_routes=policy().allowed_routes,
        )
        # Contract binds the exact policy digest, but does not bind the different input bytes.
        value = contract(provider="provider:local-open-weight", bound_policy=p)
        raw = value.to_dict()
        raw["sourceRefs"][0] = restricted().to_dict()
        value = HarnessRunContract.from_dict(raw)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            with self.assertRaisesRegex(HarnessAgentRunCompositionError, "inputs not bound"):
                HarnessAgentRun.create(
                    root, value, lambda _: ScriptedTurnAdapter((result(),)), provider_use_policy=p
                )
            self.assertFalse(root.exists())

    def test_unrestricted_run_behavior_remains_unchanged(self):
        value = contract(provider="provider:scripted", bound_policy=None)
        with tempfile.TemporaryDirectory() as directory:
            run = HarnessAgentRun.create(
                Path(directory) / "state",
                value,
                lambda _: ScriptedTurnAdapter((result(),)),
                clock_ms=lambda: 1000,
                monotonic_ms=lambda: 1000,
            )
            self.assertEqual(
                run.run(({"role": "user", "content": "ordinary"}, )).loop_result.stop_code.value,
                "candidate_completed",
            )


if __name__ == "__main__":
    unittest.main()

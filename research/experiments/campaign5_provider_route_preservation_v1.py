from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from anc_canonical import canonical_bytes, canonical_digest
from ordivon_harness.api import (
    AgentTurnResult,
    DeepSeekSettings,
    DeepSeekTurnAdapter,
    HarnessAgentRun,
    HarnessAgentRunCompositionError,
    HarnessBoundReference,
    HarnessPrivacyPolicy,
    HarnessProviderRoute,
    HarnessProviderUsePolicy,
    HarnessRunContract,
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
)
from ordivon_harness.core import AgentRunConclusion, ScriptedTurnAdapter


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(label: str) -> str:
    return canonical_digest({"campaign5ProviderRouteV1": label})


def restricted(*, byte_label: str = "restricted-bytes-v1") -> HarnessBoundReference:
    return HarnessBoundReference(
        "dataset:c5-provider-route:restricted",
        "restricted-dataset",
        digest(byte_label),
    )


def route_scripted() -> HarnessProviderRoute:
    return HarnessProviderRoute(
        provider_id="provider:scripted-local",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
    )


def route_deepseek() -> HarnessProviderRoute:
    return HarnessProviderRoute(
        provider_id="provider:deepseek-controlled",
        adapter_id=DeepSeekTurnAdapter.adapter_id,
        requested_model_id="deepseek-v4-flash",
    )


def route_unlisted() -> HarnessProviderRoute:
    return HarnessProviderRoute(
        provider_id="provider:unlisted-hosted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
    )


def policy_both() -> HarnessProviderUsePolicy:
    return HarnessProviderUsePolicy(
        policy_id="provider-use-policy:c5-provider-route-v1",
        restricted_inputs=(restricted(),),
        allowed_routes=tuple(sorted((route_scripted(), route_deepseek()))),
    )


def policy_scripted_only() -> HarnessProviderUsePolicy:
    return HarnessProviderUsePolicy(
        policy_id="provider-use-policy:c5-provider-route-scripted-only-v1",
        restricted_inputs=(restricted(),),
        allowed_routes=(route_scripted(),),
    )


def contract(
    *,
    suffix: str,
    route: HarnessProviderRoute,
    bound_policy: HarnessProviderUsePolicy | None,
    bound_input: HarnessBoundReference | None = None,
) -> HarnessRunContract:
    source_refs: tuple[HarnessBoundReference, ...] = (bound_input or restricted(),)
    if bound_policy is not None:
        source_refs += (bound_policy.bound_reference,)
    return HarnessRunContract(
        harness_run_id=f"harness-run:c5-provider-route:{suffix}",
        harness_implementation_id="ordivon-harness@c5-provider-route-v1",
        caller_id="caller:c5-provider-route-v1",
        caller_run_ref=f"experiment:c5-provider-route-v1:{suffix}",
        objective_ref=HarnessBoundReference(
            f"objective:c5-provider-route:{suffix}", "objective", digest("objective:" + suffix)
        ),
        context_refs=(
            HarnessBoundReference(
                f"context:c5-provider-route:{suffix}", "context", digest("context:" + suffix)
            ),
        ),
        source_refs=source_refs,
        provider_id=route.provider_id,
        adapter_id=route.adapter_id,
        requested_model_id=route.requested_model_id,
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
        system_manifest_ref=HarnessBoundReference(
            "manifest:c5-provider-route-v1", "system-manifest", digest("manifest")
        ),
        created_at_ms=1000,
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=False,
        ),
    )


def scripted_result() -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:c5-provider-route:scripted",
        model_id=ScriptedTurnAdapter.model_id,
        content="scripted route admitted",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed", summary="scripted route completed"
        ),
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="stop",
        raw_response_digest=digest("scripted-response"),
    )


def deepseek_conclusion_response() -> bytes:
    return canonical_bytes(
        {
            "id": "provider-call:c5-provider-route:deepseek",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "controlled DeepSeek adapter route",
                        "tool_calls": [
                            {
                                "id": "control-call:c5-provider-route:deepseek",
                                "type": "function",
                                "function": {
                                    "name": "submit_run_conclusion",
                                    "arguments": json.dumps(
                                        {
                                            "status": "candidate_completed",
                                            "summary": "deepseek route completed",
                                            "artifact_refs": [],
                                            "evidence_refs": [],
                                            "unresolved_unknowns": [],
                                        },
                                        separators=(",", ":"),
                                    ),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
        }
    )


class ControlledDeepSeekTransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        self.requests.append(json.loads(body))
        return deepseek_conclusion_response()


def expect_pre_state_rejection(
    *,
    value: HarnessRunContract,
    supplied_policy: HarnessProviderUsePolicy | None,
    expected_error: str,
) -> dict[str, Any]:
    factory_calls = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "state"

        def factory(_contract: HarnessRunContract):
            nonlocal factory_calls
            factory_calls += 1
            raise AssertionError("adapter factory must not run before provider-use rejection")

        rejected = False
        error_text = ""
        try:
            HarnessAgentRun.create(
                root,
                value,
                factory,
                provider_use_policy=supplied_policy,
            )
        except HarnessAgentRunCompositionError as error:
            rejected = True
            error_text = str(error)
        require(rejected, f"expected rejection containing {expected_error!r}")
        require(expected_error in error_text, f"unexpected rejection text: {error_text}")
        require(factory_calls == 0, "adapter factory ran before provider-use rejection")
        require(not root.exists(), "durable state root exists after pre-state rejection")
        return {
            "rejected": True,
            "error": error_text,
            "adapterFactoryCalls": factory_calls,
            "stateRootCreated": root.exists(),
        }


def main() -> int:
    u = policy_both()
    r0 = route_scripted()
    r1 = route_deepseek()
    require(r0 != r1, "R0/R1 routes must differ")
    require(r0.adapter_id != r1.adapter_id, "R0/R1 must exercise distinct adapter identities")
    require(r0.requested_model_id != r1.requested_model_id, "R0/R1 must exercise distinct model identities")

    # PR1 — exact U + allowed scripted route.
    c0 = contract(suffix="r0", route=r0, bound_policy=u)
    scripted_factory_calls = 0
    with tempfile.TemporaryDirectory() as directory:
        root0 = Path(directory) / "state"
        scripted_adapter = ScriptedTurnAdapter((scripted_result(),))

        def scripted_factory(_contract: HarnessRunContract):
            nonlocal scripted_factory_calls
            scripted_factory_calls += 1
            return scripted_adapter

        run0 = HarnessAgentRun.create(
            root0,
            c0,
            scripted_factory,
            provider_use_policy=u,
            clock_ms=lambda: 1000,
            monotonic_ms=lambda: 1000,
        )
        out0 = run0.run(({"role": "user", "content": "exact restricted input D"},))
        require(out0.loop_result.stop_code.value == "candidate_completed", "PR1 did not complete")
        require(scripted_factory_calls == 1, "PR1 adapter factory count differs")
        require(root0.exists(), "PR1 durable state root was not created")
        pr1 = {
            "standing": "R0_ADMITTED_UNDER_U",
            "adapterFactoryCalls": scripted_factory_calls,
            "stateRootCreated": root0.exists(),
            "stopCode": out0.loop_result.stop_code.value,
            "adapterClass": type(scripted_adapter).__name__,
            "policyDigest": u.digest,
            "policyRef": u.bound_reference.to_dict(),
            "route": r0.to_dict(),
        }

    # PR2 — same exact U + production DeepSeek adapter route under controlled transport.
    c1 = contract(suffix="r1", route=r1, bound_policy=u)
    deepseek_factory_calls = 0
    transport = ControlledDeepSeekTransport()
    with tempfile.TemporaryDirectory() as directory:
        root1 = Path(directory) / "state"
        deepseek_adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=transport,
            completion_contract={"mode": "record"},
        )

        def deepseek_factory(_contract: HarnessRunContract):
            nonlocal deepseek_factory_calls
            deepseek_factory_calls += 1
            return deepseek_adapter

        run1 = HarnessAgentRun.create(
            root1,
            c1,
            deepseek_factory,
            provider_use_policy=u,
            clock_ms=lambda: 1000,
            monotonic_ms=lambda: 1000,
        )
        out1 = run1.run(({"role": "user", "content": "exact restricted input D"},))
        require(out1.loop_result.stop_code.value == "candidate_completed", "PR2 did not complete")
        require(deepseek_factory_calls == 1, "PR2 adapter factory count differs")
        require(len(transport.requests) == 1, "PR2 controlled DeepSeek transport call count differs")
        require(root1.exists(), "PR2 durable state root was not created")
        require(type(deepseek_adapter) is DeepSeekTurnAdapter, "PR2 did not use production DeepSeekTurnAdapter")
        pr2 = {
            "standing": "R1_ADMITTED_UNDER_SAME_U",
            "adapterFactoryCalls": deepseek_factory_calls,
            "transportRequests": len(transport.requests),
            "stateRootCreated": root1.exists(),
            "stopCode": out1.loop_result.stop_code.value,
            "adapterClass": type(deepseek_adapter).__name__,
            "policyDigest": u.digest,
            "policyRef": u.bound_reference.to_dict(),
            "route": r1.to_dict(),
        }

    require(c0.source_refs[-1] == c1.source_refs[-1] == u.bound_reference, "PR1/PR2 do not bind same exact U")
    require(pr1["policyDigest"] == pr2["policyDigest"] == u.digest, "PR1/PR2 policy digest drifted")
    require(pr1["adapterClass"] != pr2["adapterClass"], "PR1/PR2 adapter implementations did not differ")

    # PR3 — exact U but unlisted route.
    pr3 = expect_pre_state_rejection(
        value=contract(suffix="r2-unlisted", route=route_unlisted(), bound_policy=u),
        supplied_policy=u,
        expected_error="Provider route is not admitted",
    )

    # PR4 — policy binds different bytes while Contract still binds original D.
    u_bad_bytes = HarnessProviderUsePolicy(
        policy_id="provider-use-policy:c5-provider-route-bad-bytes-v1",
        restricted_inputs=(restricted(byte_label="restricted-bytes-v2"),),
        allowed_routes=u.allowed_routes,
    )
    pr4 = expect_pre_state_rejection(
        value=contract(suffix="bad-bytes", route=r0, bound_policy=u_bad_bytes, bound_input=restricted()),
        supplied_policy=u_bad_bytes,
        expected_error="inputs not bound",
    )

    # PR5-A — Contract binds U but caller omits the exact policy object.
    pr5_missing = expect_pre_state_rejection(
        value=contract(suffix="missing-policy", route=r0, bound_policy=u),
        supplied_policy=None,
        expected_error="requires its exact Provider Use Policy",
    )

    # PR5-B — caller supplies U but Contract did not bind it.
    pr5_unbound = expect_pre_state_rejection(
        value=contract(suffix="unbound-policy", route=r0, bound_policy=None),
        supplied_policy=u,
        expected_error="supplied but not bound",
    )

    # PR6 — use-relative non-global equivalence: same R1 denied under another exact U'.
    u_scripted = policy_scripted_only()
    pr6 = expect_pre_state_rejection(
        value=contract(suffix="r1-under-scripted-only", route=r1, bound_policy=u_scripted),
        supplied_policy=u_scripted,
        expected_error="Provider route is not admitted",
    )

    result = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.campaign5-provider-route-preservation-v1-result",
        "classification": "CAMPAIGN5_PROVIDER_ROUTE_PRESERVATION_DIRECT_SUPPORT_IN_SCOPE",
        "policy": u.to_dict(),
        "policyDigest": u.digest,
        "cases": {
            "pr1AllowedScripted": pr1,
            "pr2AllowedDeepSeekAdapter": pr2,
            "pr3UnlistedRoute": pr3,
            "pr4RestrictedDigestSubstitution": pr4,
            "pr5MissingPolicy": pr5_missing,
            "pr5UnboundPolicy": pr5_unbound,
            "pr6UseRelativeNonGlobal": {
                **pr6,
                "admittedUnderBroadPolicyDigest": u.digest,
                "rejectedUnderNarrowPolicyDigest": u_scripted.digest,
            },
        },
        "gates": {
            "sameExactPolicyAcrossR0R1": True,
            "distinctAdapterImplementationsExercised": True,
            "scriptedRouteAdmitted": True,
            "deepSeekAdapterRouteAdmitted": True,
            "controlledDeepSeekTransportOnly": True,
            "unlistedRouteRejectedPreAdapterPreState": True,
            "restrictedDigestSubstitutionRejectedPreAdapterPreState": True,
            "missingBoundPolicyRejectedPreAdapterPreState": True,
            "unboundPolicyInjectionRejectedPreAdapterPreState": True,
            "routeAdmissionUseRelativeNotGlobal": True,
            "genericPreservesURequired": False,
            "productionSourceModificationRequired": False,
            "providerSemanticEquivalenceClaimed": False,
            "locusPreservationClaimed": False,
            "crossImplementationInvarianceClaimed": False,
        },
        "evidenceLimits": [
            "Controlled DeepSeek transport exercises production DeepSeekTurnAdapter mechanics but is not live-provider semantic evidence.",
            "This proves exact provider-route policy preservation under one bounded U, not general provider implementation equivalence.",
            "The current ProviderUsePolicy is route-membership based and does not itself materialize a directional reconfiguration transition object.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

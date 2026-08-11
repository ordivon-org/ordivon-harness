from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_bytes, canonical_digest

from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.loop import RunBudget
from ordivon_harness.ordivon.run_store_port import HarnessProviderCallRequestMismatch
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.ordivon.model import (
    AgentCallerIngressRef,
    AgentTurnCapabilities,
    AgentTurnRequest,
)
from ordivon_harness.working_view import (
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSourceRef,
)

from tests.test_pc15_epistemic_control import CaptureTransport
from tests.test_p0_sqlite_provider_store import MutableClock, contract as provider_contract, state as provider_state


def budget() -> dict[str, object]:
    return RunBudget(
        max_model_calls=2,
        max_tool_calls=0,
        max_observation_bytes=1024,
        max_wall_time_ms=10_000,
        max_total_tokens=4096,
        max_model_retries=0,
    ).remaining(
        model_calls=0,
        tool_calls=0,
        observation_bytes=0,
        elapsed_ms=0,
    )


def request(*, capabilities: AgentTurnCapabilities = AgentTurnCapabilities()) -> AgentTurnRequest:
    pin = HarnessWorkingSetPin(
        slot="task",
        logical_ref="source://r1/task",
        logical_generation="generation:r1-task",
        resolved_digest=canonical_digest({"r1": "task"}),
    )
    return AgentTurnRequest(
        harness_run_id="harness-run:r1-capability",
        turn_id="turn:r1-capability:1",
        sequence=1,
        assignment_id="assignment:r1-capability",
        context_digest=canonical_digest({"r1": "context"}),
        tool_catalog_digest=canonical_digest({"r1": "tools"}),
        messages=({"role": "user", "content": "same exact cognition"},),
        tools=(),
        remaining_budget=budget(),
        capabilities=capabilities,
        working_set_refs=(
            HarnessWorkingSetSourceRef(
                pin=pin,
                request_message_start_index=0,
                request_message_end_index=1,
            ),
        ),
    )


def transition_response() -> bytes:
    proposal = AgentWorkingSetTransitionProposal(
        next_attempt_id="working-attempt:r1-b",
        pins=(),
        basis="exercise request-bound capability admission",
    )
    return canonical_bytes(
        {
            "id": "provider-call:r1-transition",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call:r1-transition",
                                "type": "function",
                                "function": {
                                    "name": "propose_working_set_transition",
                                    "arguments": json.dumps(
                                        {
                                            "next_attempt_id": proposal.next_attempt_id,
                                            "pins": [],
                                            "basis": proposal.basis,
                                        },
                                        separators=(",", ":"),
                                    ),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        }
    )


class R1SingleCapabilityTruthTests(unittest.TestCase):
    def test_default_capability_keeps_legacy_request_shape(self) -> None:
        legacy = request()
        raw = legacy.to_dict()
        self.assertNotIn("capabilities", raw)
        self.assertEqual(AgentTurnRequest.from_dict(raw), legacy)
        self.assertTrue(legacy.capabilities.conclusion)

    def test_capability_changes_bind_dispatch_and_deepseek_surface(self) -> None:
        hidden = request()
        admitted = replace(
            hidden,
            capabilities=AgentTurnCapabilities(working_set_transition=True),
        )
        self.assertNotEqual(hidden.dispatch_digest, admitted.dispatch_digest)

        adapter = DeepSeekTurnAdapter(DeepSeekSettings(api_key="r1-test-secret"))
        hidden_digest = adapter.provider_request_digest(hidden)
        admitted_digest = adapter.provider_request_digest(admitted)
        self.assertNotEqual(hidden_digest, admitted_digest)

        hidden_body = json.loads(adapter._prepare_request(hidden)[3])
        admitted_body = json.loads(adapter._prepare_request(admitted)[3])
        hidden_names = [tool["function"]["name"] for tool in hidden_body["tools"]]
        admitted_names = [tool["function"]["name"] for tool in admitted_body["tools"]]
        self.assertEqual(hidden_names, ["submit_run_conclusion"])
        self.assertEqual(
            admitted_names,
            ["propose_working_set_transition", "submit_run_conclusion"],
        )
        self.assertIn(
            "ordivon_harness_turn_control",
            admitted_body["messages"][0]["content"],
        )
        admitted_control = admitted_body["messages"][-1]
        self.assertEqual(admitted_control["role"], "user")
        self.assertEqual(admitted_control["name"], "ordivon_harness_turn_control")
        self.assertIn("propose_working_set_transition", admitted_control["content"])

    def test_same_adapter_rejects_native_action_not_granted_by_request(self) -> None:
        raw = transition_response()
        denied_transport = CaptureTransport(raw)
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="r1-test-secret"), transport=denied_transport
        )
        with self.assertRaisesRegex(
            ValueError, "unavailable Working Set transition control"
        ):
            adapter.invoke(request())

        admitted_transport = CaptureTransport(raw)
        same_adapter_class = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="r1-test-secret"), transport=admitted_transport
        )
        result = same_adapter_class.invoke(
            request(
                capabilities=AgentTurnCapabilities(working_set_transition=True)
            )
        )
        self.assertIsNotNone(result.working_set_transition)

    def test_continuity_rejects_same_provider_call_with_changed_capability_truth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            value = provider_contract()
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(value)
            clock = MutableClock()
            continuity = SQLiteHarnessRunContinuityStore(store, value, clock_ms=clock)
            continuity.bind_state(provider_state())
            base = AgentTurnRequest(
                harness_run_id=value.harness_run_id,
                turn_id="turn:p0-provider:1",
                sequence=1,
                assignment_id=continuity.binding.assignment_id,
                context_digest=value.context_refs[0].digest,
                tool_catalog_digest=value.tool_catalog_digest,
                messages=provider_state().messages,
                tools=(),
                remaining_budget=provider_state().remaining_budget,
            )
            source = continuity.assignment_provider_source()
            continuity.claim_provider_call(
                source=source,
                turn_id=base.turn_id,
                turn_sequence=base.sequence,
                request_digest=base.dispatch_digest,
                provider_request_digest=canonical_digest({"r1": "provider-base"}),
                adapter_id=value.adapter_id,
                requested_model_id=value.requested_model_id,
                holder_id="holder:r1",
                ttl_ms=10,
                request=base,
            )
            changed = replace(
                base,
                capabilities=AgentTurnCapabilities(working_set_transition=True),
            )
            with self.assertRaises(HarnessProviderCallRequestMismatch):
                continuity.claim_provider_call(
                    source=source,
                    turn_id=changed.turn_id,
                    turn_sequence=changed.sequence,
                    request_digest=changed.dispatch_digest,
                    provider_request_digest=canonical_digest({"r1": "provider-changed"}),
                    adapter_id=value.adapter_id,
                    requested_model_id=value.requested_model_id,
                    holder_id="holder:r1",
                    ttl_ms=10,
                    request=changed,
                )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_promotion_capability_requires_exact_addressable_caller_ref(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "promotion capability requires exact promotable refs"
        ):
            request(
                capabilities=AgentTurnCapabilities(caller_ingress_promotion=True)
            )

        base = request()
        promotable = replace(
            base,
            capabilities=AgentTurnCapabilities(caller_ingress_promotion=True),
            caller_ingress_refs=(
                AgentCallerIngressRef(
                    caller_message_index=0, request_message_index=0
                ),
            ),
        )
        body = json.loads(
            DeepSeekTurnAdapter(
                DeepSeekSettings(api_key="r1-test-secret")
            )._prepare_request(promotable)[3]
        )
        names = [tool["function"]["name"] for tool in body["tools"]]
        self.assertIn("promote_caller_ingress", names)
        self.assertIn(
            "ordivon_harness_turn_control",
            body["messages"][0]["content"],
        )
        control = body["messages"][-1]
        self.assertEqual(control["role"], "user")
        self.assertEqual(control["name"], "ordivon_harness_turn_control")
        self.assertIn('"callerMessageIndex":0', control["content"])


if __name__ == "__main__":
    unittest.main()

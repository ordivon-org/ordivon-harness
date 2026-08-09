from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
    static_provider_request_digest,
)
from ordivon_harness.ordivon.run_store_port import HarnessProviderCallRequestMismatch
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.working_view import (
    AgentCallerIngressPromotionProposal,
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSourceRef,
    HarnessWorkingSetSpec,
    HarnessWorkingView,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
)

from tests.test_p0_sqlite_runtime_bridge import FakeRuntime, FixedClock, execution_binding
from tests.test_pc111_interaction_durable_promotion import (
    deepseek_needs_input_response,
    promotion_turn,
)
from tests.test_pc14_candidate_discovery_overlay import transition_turn
from tests.test_pc15_epistemic_control import CaptureTransport, needs_input_turn, private_contract, run_budget


class CorrectionAdapter:
    adapter_id = ScriptedTurnAdapter.adapter_id
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(self) -> None:
        self.requests: list[AgentTurnRequest] = []
        self.index = 0

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        self.index += 1
        if self.index == 1:
            return promotion_turn(
                "pc112-correction",
                AgentCallerIngressPromotionProposal(
                    next_attempt_id="working-attempt:pc112-b",
                    promotion_slot="corrected-code",
                    caller_message_indexes=(0,),
                    basis="preserve exact authoritative correction GREEN-42",
                ),
            )
        if self.index == 2:
            by_slot = {ref.pin.slot: ref.pin for ref in request.working_set_refs}
            if set(by_slot) != {"corrected-code", "launch-code", "task"}:
                raise ValueError(f"unexpected current durable slots: {sorted(by_slot)}")
            return transition_turn(
                "pc112-drop-stale",
                AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc112-c",
                    pins=tuple(sorted((by_slot["corrected-code"], by_slot["task"]), key=lambda pin: pin.slot)),
                    basis="GREEN-42 supersedes stale RED-9 while task context remains selected",
                ),
            )
        if self.index == 3:
            return needs_input_turn(
                "pc112-verification-boundary",
                "correction complete; start a later interaction",
            )
        raise AssertionError("unexpected correction adapter turn")


class ForgedWorkingSetProjector:
    def __init__(self, real: WorkingSetViewProjector) -> None:
        self.real = real

    def project_with_refs(self):
        view, refs = self.real.project_with_refs()
        first = refs[0]
        forged_pin = HarnessWorkingSetPin(
            slot=first.pin.slot,
            logical_ref=first.pin.logical_ref,
            logical_generation=first.pin.logical_generation,
            resolved_digest=canonical_digest({"forged": "pc112-working-set-ref"}),
        )
        forged = (
            HarnessWorkingSetSourceRef(
                pin=forged_pin,
                request_message_start_index=first.request_message_start_index,
                request_message_end_index=first.request_message_end_index,
            ),
            *refs[1:],
        )
        return view, forged

    def project(self) -> HarnessWorkingView:
        return self.real.project()


class DurableCognitionSupersessionTests(unittest.TestCase):
    @staticmethod
    def initialize(root: Path, suffix: str):
        run_contract = private_contract(
            f"pc112-{suffix}",
            max_model_calls=8,
            max_tool_calls=0,
        )
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        clock = FixedClock()
        continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
        task = HarnessWorkingViewSource(
            logical_ref=f"source://pc112/{suffix}/task",
            logical_generation="generation:task",
            messages=(
                {"role": "user", "content": "PC112_TASK durable task instruction."},
                {"role": "user", "content": "PC112_TASK_SECOND_MESSAGE exact range test."},
            ),
        )
        stale = HarnessWorkingViewSource(
            logical_ref=f"source://pc112/{suffix}/stale",
            logical_generation="generation:red-9",
            messages=({"role": "user", "content": "Current durable launch code: RED-9."},),
        )
        task_object = continuity.store_working_view_source(task)
        stale_object = continuity.store_working_view_source(stale)
        task_pin = HarnessWorkingSetPin(
            slot="task",
            logical_ref=task.logical_ref,
            logical_generation=task.logical_generation,
            resolved_digest=task_object.digest,
        )
        stale_pin = HarnessWorkingSetPin(
            slot="launch-code",
            logical_ref=stale.logical_ref,
            logical_generation=stale.logical_generation,
            resolved_digest=stale_object.digest,
        )
        initial = HarnessWorkingSetSpec.initial(
            f"working-attempt:pc112-{suffix}-a",
            pins=tuple(sorted((task_pin, stale_pin), key=lambda pin: pin.slot)),
        )
        continuity.record_working_set(initial)
        continuity.record_working_set(initial.commit("seed task plus stale durable code"))
        runtime = FakeRuntime("direct")
        bridge = SQLiteHarnessRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
        )
        projector = WorkingSetViewProjector(store, continuity)
        return (
            store, clock, run_contract, continuity, bridge, projector, task, stale, task_pin, stale_pin
        )

    @staticmethod
    def pause(*, run_contract, continuity, bridge, projector, clock):
        adapter = ScriptedTurnAdapter((needs_input_turn("pc112-pause", "authoritative correction required"),))
        result = OrdivonAgentLoop(
            adapter,
            bridge,
            budget=run_budget(max_model_calls=8, max_tool_calls=0),
            clock_ms=clock,
            monotonic_ms=clock,
            working_view_projector=projector,
        ).run(
            harness_run_id=run_contract.harness_run_id,
            assignment_id=continuity.binding.assignment_id,
            context_digest=run_contract.context_refs[0].digest,
            initial_messages=({"role": "user", "content": "canonical pc112 root"},),
        )
        if result.stop_code is not RunStopCode.NEEDS_INPUT:
            raise AssertionError(result.stop_code)
        return continuity.load_current_snapshot()

    def test_current_working_set_refs_align_exact_pins_to_message_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (
                store, _clock, _contract, continuity, _bridge, projector, _task, _stale,
                task_pin, stale_pin,
            ) = self.initialize(Path(directory) / "state", "ranges")
            view, refs = projector.project_with_refs()
            self.assertEqual(view.messages[0]["content"], "Current durable launch code: RED-9.")
            self.assertEqual(view.messages[1]["content"], "PC112_TASK durable task instruction.")
            self.assertEqual(view.messages[2]["content"], "PC112_TASK_SECOND_MESSAGE exact range test.")
            self.assertEqual(
                refs,
                (
                    HarnessWorkingSetSourceRef(
                        pin=stale_pin, request_message_start_index=0, request_message_end_index=1
                    ),
                    HarnessWorkingSetSourceRef(
                        pin=task_pin, request_message_start_index=1, request_message_end_index=3
                    ),
                ),
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_deepseek_exposes_current_selection_only_when_transition_surface_is_granted(self) -> None:
        stale_pin = HarnessWorkingSetPin(
            slot="launch-code",
            logical_ref="source://pc112/deepseek/stale",
            logical_generation="generation:red-9",
            resolved_digest=canonical_digest({"pc112": "stale-source"}),
        )
        request = AgentTurnRequest(
            harness_run_id="harness-run:pc112-deepseek",
            turn_id="turn:pc112-deepseek:1",
            sequence=1,
            assignment_id="assignment:pc112-deepseek",
            context_digest=canonical_digest({"pc112": "context"}),
            tool_catalog_digest=canonical_digest({"pc112": "tools"}),
            messages=({"role": "user", "content": "Current durable launch code: RED-9."},),
            tools=(),
            remaining_budget=run_budget(max_model_calls=2, max_tool_calls=0).remaining(
                model_calls=0, tool_calls=0, observation_bytes=0, elapsed_ms=0
            ),
            working_set_refs=(
                HarnessWorkingSetSourceRef(
                    pin=stale_pin, request_message_start_index=0, request_message_end_index=1
                ),
            ),
        )
        transport = CaptureTransport(deepseek_needs_input_response("inspect current selection"))
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="pc112-test-secret"),
            transport=transport,
            working_set_transitions=True,
        )
        adapter.invoke(request)
        control = transport.requests[0]["messages"][0]["content"]
        self.assertIn('\"workingSetSelection\"', control)
        self.assertIn(stale_pin.resolved_digest, control)
        self.assertIn('\"providerMessageStartIndex\":1', control)
        self.assertIn('\"providerMessageEndExclusiveIndex\":2', control)
        transition_tool = next(
            tool
            for tool in transport.requests[0]["tools"]
            if tool["function"]["name"] == "propose_working_set_transition"
        )
        transition_description = transition_tool["function"]["description"]
        self.assertIn("attempt reset, not progress", transition_description)
        self.assertIn("needs_input conclusion", transition_description)

        hidden_transport = CaptureTransport(deepseek_needs_input_response("selection not disclosed"))
        hidden = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="pc112-test-secret"),
            transport=hidden_transport,
            working_set_transitions=False,
        )
        hidden.invoke(request)
        self.assertNotIn("workingSetSelection", hidden_transport.requests[0]["messages"][0]["content"])

    def test_forged_current_source_identity_is_rejected_before_provider_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (
                store, clock, run_contract, continuity, bridge, projector, *_rest
            ) = self.initialize(Path(directory) / "state", "forged-ref")
            adapter = ScriptedTurnAdapter((needs_input_turn("pc112-forged", "should not dispatch"),))
            with self.assertRaisesRegex(
                HarnessProviderCallRequestMismatch,
                "current WorkingSet provenance differs",
            ):
                OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=run_budget(max_model_calls=8, max_tool_calls=0),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=ForgedWorkingSetProjector(projector),
                ).run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical pc112 forged root"},
                    ),
                )
            self.assertEqual(adapter.requests, [])
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_correction_is_promotion_plus_ordinary_selection_and_stale_pin_remains_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            (
                store, clock, run_contract, continuity, bridge, projector, _task, _stale,
                task_pin, stale_pin,
            ) = self.initialize(root, "correction")
            retained = self.pause(
                run_contract=run_contract, continuity=continuity, bridge=bridge,
                projector=projector, clock=clock,
            )
            adapter = CorrectionAdapter()
            resume_bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                FakeRuntime("direct"),
                provider_source=continuity.snapshot_provider_source(retained),
            )
            result = OrdivonAgentLoop(
                adapter,
                resume_bridge,
                budget=run_budget(max_model_calls=8, max_tool_calls=0),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                working_set_transition_handler=continuity,
                caller_ingress_promotion_handler=continuity,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(
                    {
                        "role": "user",
                        "content": "Authoritative correction: GREEN-42 supersedes RED-9.",
                    },
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            current = continuity.load_current_working_set()
            self.assertEqual({pin.slot for pin in current.pins}, {"corrected-code", "task"})
            self.assertEqual(next(pin for pin in current.pins if pin.slot == "task"), task_pin)
            self.assertNotIn(stale_pin, current.pins)
            final_request_text = str(adapter.requests[2].messages)
            self.assertIn("GREEN-42", final_request_text)
            self.assertNotIn("Current durable launch code: RED-9.", final_request_text)
            self.assertEqual(
                {ref.pin.slot for ref in adapter.requests[2].working_set_refs},
                {"corrected-code", "task"},
            )
            history = continuity.inspect_working_set_history(limit=16)
            history_text = str(history)
            self.assertIn(stale_pin.resolved_digest, history_text)
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_agent_turn_request_without_working_set_refs_keeps_legacy_shape(self) -> None:
        request = AgentTurnRequest(
            harness_run_id="harness-run:pc112-legacy",
            turn_id="turn:pc112-legacy:1",
            sequence=1,
            assignment_id="assignment:pc112-legacy",
            context_digest=canonical_digest({"pc112": "legacy-context"}),
            tool_catalog_digest=canonical_digest({"pc112": "legacy-tools"}),
            messages=({"role": "user", "content": "legacy request"},),
            tools=(),
            remaining_budget=run_budget(max_model_calls=2, max_tool_calls=0).remaining(
                model_calls=0, tool_calls=0, observation_bytes=0, elapsed_ms=0
            ),
        )
        raw = request.to_dict()
        self.assertNotIn("workingSetRefs", raw)
        self.assertEqual(AgentTurnRequest.from_dict(raw), request)


if __name__ == "__main__":
    unittest.main()

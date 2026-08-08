from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.working_view import (
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
)

from tests.test_p0_sqlite_runtime_bridge import FakeRuntime, FixedClock, execution_binding
from tests.test_pc14_candidate_discovery_overlay import (
    MaterializingDiscoveryRuntimeBridge,
    RawCandidateRuntime,
    transition_turn,
)
from tests.test_pc15_epistemic_control import (
    needs_input_turn,
    private_contract,
    run_budget,
    tool_call,
    tool_turn,
)


class PromotionDecisionAdapter(ScriptedTurnAdapter):
    """Agent that chooses whether a materialized source becomes successor cognition."""

    def __init__(
        self,
        *,
        suffix: str,
        primary_pin: HarnessWorkingSetPin,
        promote: bool,
    ) -> None:
        self.suffix = suffix
        self.primary_pin = primary_pin
        self.promote = promote
        self.requests = []
        self.materialized_pin: HarnessWorkingSetPin | None = None
        self.proposal: AgentWorkingSetTransitionProposal | None = None

    def invoke(self, request):
        self.requests.append(request)
        if request.sequence == 1:
            return tool_turn(
                f"pc17-{self.suffix}-discover",
                (tool_call(f"tool-call:pc17-{self.suffix}-discover", "PROMOTABLE_KNOWLEDGE"),),
            )
        if request.sequence == 2:
            overlay = request.messages[-1]
            observation = overlay.get("observation")
            if not isinstance(observation, dict):
                raise ValueError("promotion observation is invalid")
            content = observation.get("content")
            if not isinstance(content, dict):
                raise ValueError("promotion observation content is invalid")
            materialization = content.get("candidateMaterialization")
            if not isinstance(materialization, dict):
                raise ValueError("promotion observation lacks materialization evidence")
            raw_pins = materialization.get("candidatePins")
            if not isinstance(raw_pins, list) or len(raw_pins) != 1:
                raise ValueError("promotion experiment requires one exact candidate pin")
            raw_pin = raw_pins[0]
            if not isinstance(raw_pin, dict):
                raise ValueError("promotion candidate pin is invalid")
            candidate = HarnessWorkingSetPin.from_dict(raw_pin)
            self.materialized_pin = candidate
            pins = (self.primary_pin,)
            if self.promote:
                knowledge_pin = HarnessWorkingSetPin(
                    slot="retained-knowledge",
                    logical_ref=candidate.logical_ref,
                    logical_generation=candidate.logical_generation,
                    resolved_digest=candidate.resolved_digest,
                )
                pins = (self.primary_pin, knowledge_pin)
            self.proposal = AgentWorkingSetTransitionProposal(
                next_attempt_id=f"working-attempt:pc17-{self.suffix}-b",
                pins=pins,
                basis=(
                    "I explicitly retain the observed knowledge beside my primary source"
                    if self.promote
                    else "I explicitly continue with only my primary source"
                ),
            )
            return transition_turn(f"pc17-{self.suffix}-select", self.proposal)
        if request.sequence == 3:
            return needs_input_turn(
                f"pc17-{self.suffix}-pause",
                "Pause after the successor WorkingSet is committed.",
            )
        raise AssertionError(f"unexpected model turn sequence: {request.sequence}")


class DurableKnowledgePromotionTests(unittest.TestCase):
    @staticmethod
    def seed(
        continuity: SQLiteHarnessRunContinuityStore,
        *,
        suffix: str,
    ) -> tuple[HarnessWorkingViewSource, HarnessWorkingSetPin]:
        source = HarnessWorkingViewSource(
            logical_ref=f"source://pc17/{suffix}/primary",
            logical_generation="generation:a",
            messages=(
                {
                    "role": "user",
                    "content": f"PC17_PRIMARY_{suffix.upper()}",
                },
            ),
        )
        stored = continuity.store_working_view_source(source)
        pin = HarnessWorkingSetPin(
            slot="primary",
            logical_ref=source.logical_ref,
            logical_generation=source.logical_generation,
            resolved_digest=stored.digest,
        )
        initial = HarnessWorkingSetSpec.initial(
            f"working-attempt:pc17-{suffix}-a",
            pins=(pin,),
        )
        continuity.record_working_set(initial)
        continuity.record_working_set(initial.commit("seed primary cognition"))
        return source, pin

    def test_agent_promotion_survives_attempt_and_process_until_agent_drops_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc17-promote-drop",
                max_model_calls=6,
                max_tool_calls=1,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store,
                run_contract,
                clock_ms=clock,
            )
            source_a, pin_a = self.seed(continuity, suffix="promote")
            knowledge_source = HarnessWorkingViewSource(
                logical_ref="knowledge://pc17/promote/tool-derived-k",
                logical_generation="generation:1",
                messages=(
                    {
                        "role": "user",
                        "content": "PC17_PROMOTED_KNOWLEDGE_K",
                    },
                ),
            )
            runtime = RawCandidateRuntime("direct", (knowledge_source,))
            bridge = MaterializingDiscoveryRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
            )
            adapter = PromotionDecisionAdapter(
                suffix="promote",
                primary_pin=pin_a,
                promote=True,
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(max_model_calls=6, max_tool_calls=1),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
                working_set_transition_handler=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc17 promotion root"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertIsNotNone(adapter.materialized_pin)
            assert adapter.materialized_pin is not None
            materialized_digest = adapter.materialized_pin.resolved_digest
            self.assertIsNotNone(adapter.proposal)
            assert adapter.proposal is not None
            self.assertEqual(
                [pin.slot for pin in continuity.load_current_working_set().pins],
                ["primary", "retained-knowledge"],
            )
            # The Tool exchange is transient; after the transition, turn 3 sees
            # only durable selected source material A + K.
            self.assertEqual(
                adapter.requests[2].messages,
                source_a.messages + knowledge_source.messages,
            )
            retained_b = continuity.load_current_snapshot()
            store.close()

            with SQLiteHarnessStore(root) as second_store:
                second = SQLiteHarnessRunContinuityStore.open(
                    second_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained_b = second.load_current_snapshot()
                drop = AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc17-promote-c",
                    pins=(pin_a,),
                    basis="The retained knowledge is no longer relevant, so I drop it explicitly.",
                )
                drop_adapter = ScriptedTurnAdapter(
                    (
                        transition_turn("pc17-promote-drop", drop),
                        needs_input_turn(
                            "pc17-promote-drop-pause",
                            "Pause after explicit knowledge removal.",
                        ),
                    )
                )
                second_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    second,
                    execution_binding(run_contract, second),
                    FakeRuntime("direct"),
                    provider_source=second.snapshot_provider_source(retained_b),
                )
                second_result = OrdivonAgentLoop(
                    drop_adapter,
                    second_bridge,
                    budget=run_budget(max_model_calls=6, max_tool_calls=1),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        second_store,
                        second,
                    ),
                    working_set_transition_handler=second,
                ).resume(
                    retained=retained_b,
                    assignment_id=second.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(second_result.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(drop_adapter.requests[0].messages, source_a.messages + knowledge_source.messages)
                self.assertEqual(drop_adapter.requests[1].messages, source_a.messages)
                self.assertEqual(second.load_current_working_set().pins, (pin_a,))
                retained_c = second.load_current_snapshot()

            with SQLiteHarnessStore(root) as third_store:
                third = SQLiteHarnessRunContinuityStore.open(
                    third_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained_c = third.load_current_snapshot()
                final_adapter = ScriptedTurnAdapter(
                    (
                        needs_input_turn(
                            "pc17-promote-final",
                            "Final inspection after explicit knowledge removal.",
                        ),
                    )
                )
                third_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    third,
                    execution_binding(run_contract, third),
                    FakeRuntime("direct"),
                    provider_source=third.snapshot_provider_source(retained_c),
                )
                final_result = OrdivonAgentLoop(
                    final_adapter,
                    third_bridge,
                    budget=run_budget(max_model_calls=6, max_tool_calls=1),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(third_store, third),
                ).resume(
                    retained=retained_c,
                    assignment_id=third.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(final_result.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(final_adapter.requests[0].messages, source_a.messages)
                self.assertNotIn("PC17_PROMOTED_KNOWLEDGE_K", str(final_adapter.requests[0].messages))
                # Physical source bytes remain in CAS, but they no longer have
                # current cognition authority after the Agent drops their pin.
                self.assertEqual(
                    third_store.get_object(
                        materialized_digest,
                        expected_kind="harness-working-view-source",
                    ),
                    knowledge_source.to_dict(),
                )
                self.assertTrue(third.doctor()["healthy"])

    def test_materialized_but_unselected_source_never_becomes_later_cognition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc17-unselected",
                max_model_calls=4,
                max_tool_calls=1,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store,
                run_contract,
                clock_ms=clock,
            )
            source_a, pin_a = self.seed(continuity, suffix="unselected")
            knowledge_source = HarnessWorkingViewSource(
                logical_ref="knowledge://pc17/unselected/tool-derived-k",
                logical_generation="generation:1",
                messages=(
                    {
                        "role": "user",
                        "content": "PC17_MATERIALIZED_BUT_UNSELECTED_K",
                    },
                ),
            )
            runtime = RawCandidateRuntime("direct", (knowledge_source,))
            bridge = MaterializingDiscoveryRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
            )
            adapter = PromotionDecisionAdapter(
                suffix="unselected",
                primary_pin=pin_a,
                promote=False,
            )
            first = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(max_model_calls=4, max_tool_calls=1),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
                working_set_transition_handler=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc17 unselected root"},
                ),
            )
            self.assertEqual(first.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertIsNotNone(adapter.materialized_pin)
            assert adapter.materialized_pin is not None
            materialized_digest = adapter.materialized_pin.resolved_digest
            self.assertEqual(continuity.load_current_working_set().pins, (pin_a,))
            self.assertEqual(adapter.requests[2].messages, source_a.messages)
            retained = continuity.load_current_snapshot()
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                final_adapter = ScriptedTurnAdapter(
                    (
                        needs_input_turn(
                            "pc17-unselected-final",
                            "Inspect the successor that never promoted K.",
                        ),
                    )
                )
                replay_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    FakeRuntime("direct"),
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                final = OrdivonAgentLoop(
                    final_adapter,
                    replay_bridge,
                    budget=run_budget(max_model_calls=4, max_tool_calls=1),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        reopened_store,
                        reopened,
                    ),
                ).resume(
                    retained=retained,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(final.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(final_adapter.requests[0].messages, source_a.messages)
                self.assertNotIn(
                    "PC17_MATERIALIZED_BUT_UNSELECTED_K",
                    str(final_adapter.requests[0].messages),
                )
                self.assertEqual(
                    reopened_store.get_object(
                        materialized_digest,
                        expected_kind="harness-working-view-source",
                    ),
                    knowledge_source.to_dict(),
                )
                self.assertTrue(reopened.doctor()["healthy"])


    def test_transient_knowledge_survives_clean_pause_within_attempt_then_expires_at_successor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc17-attempt-local",
                max_model_calls=4,
                max_tool_calls=1,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store,
                run_contract,
                clock_ms=clock,
            )
            source_a, pin_a = self.seed(continuity, suffix="attempt-local")
            knowledge_source = HarnessWorkingViewSource(
                logical_ref="knowledge://pc17/attempt-local/k",
                logical_generation="generation:1",
                messages=(
                    {
                        "role": "user",
                        "content": "PC17_ATTEMPT_LOCAL_K",
                    },
                ),
            )
            call = tool_call("tool-call:pc17-attempt-local", "PROMOTABLE_KNOWLEDGE")
            runtime = RawCandidateRuntime("direct", (knowledge_source,))
            bridge = MaterializingDiscoveryRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
            )
            first_adapter = ScriptedTurnAdapter(
                (
                    tool_turn("pc17-attempt-local", (call,)),
                    needs_input_turn(
                        "pc17-attempt-local-pause",
                        "Pause without promoting the transient knowledge.",
                    ),
                )
            )
            first = OrdivonAgentLoop(
                first_adapter,
                bridge,
                budget=run_budget(max_model_calls=4, max_tool_calls=1),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
                working_set_transition_handler=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc17 attempt-local root"},
                ),
            )
            self.assertEqual(first.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertIn(call.tool_call_id, str(first_adapter.requests[1].messages))
            retained = continuity.load_current_snapshot()
            self.assertEqual(retained.snapshot.active_tool_step_intent_digests, ())
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                continue_without_promotion = AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc17-attempt-local-b",
                    pins=(pin_a,),
                    basis="I keep the Tool knowledge transient and do not promote it.",
                )
                second_adapter = ScriptedTurnAdapter(
                    (
                        transition_turn(
                            "pc17-attempt-local-transition",
                            continue_without_promotion,
                        ),
                        needs_input_turn(
                            "pc17-attempt-local-final",
                            "Inspect the successor after transient knowledge expires.",
                        ),
                    )
                )
                second_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    FakeRuntime("direct"),
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                second = OrdivonAgentLoop(
                    second_adapter,
                    second_bridge,
                    budget=run_budget(max_model_calls=4, max_tool_calls=1),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        reopened_store,
                        reopened,
                    ),
                    working_set_transition_handler=reopened,
                ).resume(
                    retained=retained,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(second.stop_code, RunStopCode.NEEDS_INPUT)
                # Same attempt after a clean process pause: transient evidence must
                # still be available to the Agent even though it was never selected.
                self.assertEqual(second_adapter.requests[0].messages[:1], source_a.messages)
                self.assertIn(call.tool_call_id, str(second_adapter.requests[0].messages))
                self.assertIn("PC17_ATTEMPT_LOCAL_K", str(second_adapter.requests[0].messages))
                # Crossing the explicit successor boundary without K expires the
                # transient exchange. It does not become implicit memory.
                self.assertEqual(second_adapter.requests[1].messages, source_a.messages)
                self.assertNotIn(call.tool_call_id, str(second_adapter.requests[1].messages))
                self.assertNotIn("PC17_ATTEMPT_LOCAL_K", str(second_adapter.requests[1].messages))
                self.assertTrue(reopened.doctor()["healthy"])

    def test_model_only_privacy_rejects_structured_tool_channel_but_not_semantic_taint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = replace(
                private_contract(
                    "pc17-semantic-taint-boundary",
                    max_model_calls=1,
                    max_tool_calls=0,
                ),
                privacy=HarnessPrivacyPolicy(
                    content_policy="bounded-private-content",
                    allow_model_content=True,
                    allow_tool_content=False,
                ),
            )
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store,
                    run_contract,
                    clock_ms=clock,
                )
                direct_tool_source = HarnessWorkingViewSource(
                    logical_ref="knowledge://pc17/direct-tool-channel",
                    logical_generation="generation:1",
                    messages=(
                        {
                            "role": "tool",
                            "toolCallId": "tool-call:pc17-taint",
                            "name": "search_workspace",
                            "content": "PC17_TOOL_SECRET_FACT",
                        },
                    ),
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "Tool content without Contract permission",
                ):
                    continuity.store_working_view_source(direct_tool_source)

                # The exact same semantic fact wrapped as ordinary model-visible
                # text is structurally indistinguishable from any other caller or
                # domain-authored source. Harness deliberately does not pretend to
                # infer semantic taint from bytes alone.
                wrapped_source = HarnessWorkingViewSource(
                    logical_ref="knowledge://pc17/wrapped-tool-derived-fact",
                    logical_generation="generation:1",
                    messages=(
                        {
                            "role": "user",
                            "content": "PC17_TOOL_SECRET_FACT",
                        },
                    ),
                )
                stored = continuity.store_working_view_source(wrapped_source)
                self.assertEqual(
                    store.get_object(
                        stored.digest,
                        expected_kind="harness-working-view-source",
                    ),
                    wrapped_source.to_dict(),
                )
                self.assertTrue(continuity.doctor()["healthy"])


if __name__ == "__main__":
    unittest.main()

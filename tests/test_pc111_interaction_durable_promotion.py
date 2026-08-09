from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_bytes, canonical_digest

from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentTurnCapabilities,
    AgentCallerIngressRef,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_agent_bridge import SQLiteHarnessAgentBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.working_view import (
    AgentCallerIngressPromotionProposal,
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
)

from tests.test_p0_sqlite_runtime_bridge import FakeRuntime, FixedClock, execution_binding
from tests.test_pc13_agent_owned_working_set import cognition_budget, cognition_contract
from tests.test_pc14_candidate_discovery_overlay import transition_turn
from tests.test_pc15_epistemic_control import (
    CaptureTransport,
    needs_input_turn,
    private_contract,
    run_budget,
)


def promotion_turn(
    suffix: str,
    proposal: AgentCallerIngressPromotionProposal,
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:pc111-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content="Promote the exact selected caller ingress into durable cognition.",
        tool_calls=(),
        conclusion=None,
        usage={"inputTokens": 12, "outputTokens": 6},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"pc111": suffix}),
        caller_ingress_promotion=proposal,
    )


class LosePromotionCompletionBridge(SQLiteHarnessRuntimeBridge):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.injected = False

    def complete_provider_call(
        self,
        request: AgentTurnRequest,
        result: AgentTurnResult,
    ) -> None:
        super().complete_provider_call(request, result)
        if result.caller_ingress_promotion is not None and not self.injected:
            self.injected = True
            raise RuntimeError(
                "injected P-C1.11 response loss after durable promotion proposal"
            )


def deepseek_promotion_response(
    proposal: AgentCallerIngressPromotionProposal,
    *,
    mixed_conclusion: bool = False,
) -> bytes:
    arguments = {
        "next_attempt_id": proposal.next_attempt_id,
        "promotion_slot": proposal.promotion_slot,
        "caller_message_indexes": list(proposal.caller_message_indexes),
        "basis": proposal.basis,
    }
    calls = [
        {
            "id": "call:pc111-promotion",
            "type": "function",
            "function": {
                "name": "promote_caller_ingress",
                "arguments": canonical_bytes(arguments).decode("utf-8"),
            },
        }
    ]
    if mixed_conclusion:
        calls.append(
            {
                "id": "call:pc111-conclusion",
                "type": "function",
                "function": {
                    "name": "submit_run_conclusion",
                    "arguments": canonical_bytes(
                        {
                            "status": "candidate_completed",
                            "summary": "mixed conclusion must not be selected by Harness",
                            "artifact_refs": [],
                            "evidence_refs": [],
                            "unresolved_unknowns": [],
                        }
                    ).decode("utf-8"),
                },
            }
        )
    return canonical_bytes(
        {
            "id": "provider-call:pc111-promotion",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "I will preserve the exact caller fact.",
                        "tool_calls": calls,
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 8,
                "total_tokens": 28,
            },
        }
    )


def deepseek_needs_input_response(summary: str = "no promotable caller ingress") -> bytes:
    return canonical_bytes(
        {
            "id": "provider-call:pc111-needs-input",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call:pc111-needs-input",
                                "type": "function",
                                "function": {
                                    "name": "submit_run_conclusion",
                                    "arguments": canonical_bytes(
                                        {
                                            "status": "needs_input",
                                            "summary": summary,
                                            "artifact_refs": [],
                                            "evidence_refs": [],
                                            "unresolved_unknowns": [],
                                        }
                                    ).decode("utf-8"),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 16,
                "completion_tokens": 7,
                "total_tokens": 23,
            },
        }
    )


class InteractionDurablePromotionTests(unittest.TestCase):
    @staticmethod
    def initialize(
        root: Path,
        suffix: str,
        *,
        max_model_calls: int = 8,
        max_tool_calls: int = 2,
    ):
        runtime = FakeRuntime("direct")
        run_contract = private_contract(
            f"pc111-{suffix}",
            max_model_calls=max_model_calls,
            max_tool_calls=max_tool_calls,
        )
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        clock = FixedClock()
        continuity = SQLiteHarnessRunContinuityStore(
            store,
            run_contract,
            clock_ms=clock,
        )
        source_a = HarnessWorkingViewSource(
            logical_ref=f"source://pc111/{suffix}/a",
            logical_generation="generation:a",
            messages=(
                {
                    "role": "user",
                    "content": "PC111_SOURCE_A: durable baseline cognition.",
                },
            ),
        )
        stored_a = continuity.store_working_view_source(source_a)
        pin_a = HarnessWorkingSetPin(
            slot="primary",
            logical_ref=source_a.logical_ref,
            logical_generation=source_a.logical_generation,
            resolved_digest=stored_a.digest,
        )
        initial = HarnessWorkingSetSpec.initial(
            f"working-attempt:pc111-{suffix}-a",
            pins=(pin_a,),
        )
        continuity.record_working_set(initial)
        continuity.record_working_set(initial.commit("seed PC111 source A"))
        bridge = SQLiteHarnessRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
        )
        projector = WorkingSetViewProjector(store, continuity)
        return (
            store,
            clock,
            run_contract,
            continuity,
            bridge,
            projector,
            runtime,
            source_a,
            pin_a,
        )

    @staticmethod
    def pause(*, run_contract, continuity, bridge, projector, clock):
        adapter = ScriptedTurnAdapter(
            (needs_input_turn("pc111-pause", "caller interaction is required"),)
        )
        result = OrdivonAgentLoop(
            adapter,
            bridge,
            budget=run_budget(max_model_calls=8, max_tool_calls=2),
            clock_ms=clock,
            monotonic_ms=clock,
            working_view_projector=projector,
        ).run(
            harness_run_id=run_contract.harness_run_id,
            assignment_id=continuity.binding.assignment_id,
            context_digest=run_contract.context_refs[0].digest,
            initial_messages=({"role": "user", "content": "canonical pc111 root"},),
        )
        if result.stop_code is not RunStopCode.NEEDS_INPUT:
            raise AssertionError(result.stop_code)
        return continuity.load_current_snapshot()

    def test_agent_promotes_exact_subset_then_only_promoted_bytes_survive_next_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _runtime,
                source_a,
                pin_a,
            ) = self.initialize(root, "subset")
            retained = self.pause(
                run_contract=run_contract,
                continuity=continuity,
                bridge=bridge,
                projector=projector,
                clock=clock,
            )
            caller_x = {"role": "user", "content": "CALLER_X_BLUE_17"}
            caller_y = {"role": "user", "content": "CALLER_Y_EPHEMERAL"}
            proposal = AgentCallerIngressPromotionProposal(
                next_attempt_id="working-attempt:pc111-subset-b",
                promotion_slot="retained-caller",
                caller_message_indexes=(0,),
                basis="X is useful beyond this caller interaction; Y is not.",
            )
            adapter = ScriptedTurnAdapter(
                (
                    promotion_turn("subset", proposal),
                    needs_input_turn(
                        "pc111-after-promotion-pause",
                        "start a new interaction after promotion",
                    ),
                )
            )
            resume_bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                FakeRuntime("direct"),
                provider_source=continuity.snapshot_provider_source(retained),
            )
            promoted = OrdivonAgentLoop(
                adapter,
                resume_bridge,
                budget=run_budget(max_model_calls=8, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                caller_ingress_promotion_handler=continuity,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(caller_x, caller_y),
            )
            self.assertEqual(promoted.stop_code, RunStopCode.NEEDS_INPUT)
            current = continuity.load_current_working_set()
            self.assertEqual(len(current.pins), 2)
            promoted_pin = next(pin for pin in current.pins if pin.slot == "retained-caller")
            raw_source = store.get_object(
                promoted_pin.resolved_digest,
                expected_kind="harness-working-view-source",
            )
            promoted_source = HarnessWorkingViewSource.from_dict(raw_source)
            self.assertEqual(promoted_source.messages, (caller_x,))
            self.assertEqual(
                tuple(ref.caller_message_index for ref in adapter.requests[0].caller_ingress_refs),
                (0, 1),
            )
            self.assertEqual(
                tuple(
                    ref.caller_message_index
                    for ref in adapter.requests[1].caller_ingress_refs
                ),
                (1,),
            )
            second_request_text = str(adapter.requests[1].messages)
            self.assertIn("CALLER_X_BLUE_17", second_request_text)
            self.assertIn("CALLER_Y_EPHEMERAL", second_request_text)
            # X has both caller and durable authority, but provenance-aware
            # projection suppresses the caller-layer duplicate while the promoted
            # source remains selected. Y remains ordinary caller interaction cognition.
            self.assertEqual(second_request_text.count("CALLER_X_BLUE_17"), 1)
            next_snapshot = continuity.load_current_snapshot()
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                next_snapshot = reopened.load_current_snapshot()
                caller_z = {"role": "user", "content": "CALLER_Z_NEW_INTERACTION"}
                final_adapter = ScriptedTurnAdapter(
                    (needs_input_turn("pc111-final-pause", "inspect durable result"),)
                )
                final_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    FakeRuntime("direct"),
                    provider_source=reopened.snapshot_provider_source(next_snapshot),
                )
                final = OrdivonAgentLoop(
                    final_adapter,
                    final_bridge,
                    budget=run_budget(max_model_calls=8, max_tool_calls=2),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(reopened_store, reopened),
                    caller_ingress_promotion_handler=reopened,
                ).resume(
                    retained=next_snapshot,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    additional_messages=(caller_z,),
                )
                self.assertEqual(final.stop_code, RunStopCode.NEEDS_INPUT)
                final_text = str(final_adapter.requests[0].messages)
                self.assertIn(source_a.messages[0]["content"], final_text)
                self.assertIn("CALLER_X_BLUE_17", final_text)
                self.assertNotIn("CALLER_Y_EPHEMERAL", final_text)
                self.assertIn("CALLER_Z_NEW_INTERACTION", final_text)
                self.assertEqual(final_text.count("CALLER_X_BLUE_17"), 1)
                self.assertTrue(reopened.doctor()["healthy"])

    def test_caller_ingress_is_not_materialized_or_selected_without_agent_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _runtime,
                _source_a,
                pin_a,
            ) = self.initialize(Path(directory) / "state", "no-auto")
            retained = self.pause(
                run_contract=run_contract,
                continuity=continuity,
                bridge=bridge,
                projector=projector,
                clock=clock,
            )
            caller = {"role": "user", "content": "CALLER_NOT_AUTO_PROMOTED"}
            adapter = ScriptedTurnAdapter(
                (needs_input_turn("pc111-no-auto-next-pause", "do not promote caller input"),)
            )
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
                budget=run_budget(max_model_calls=8, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                caller_ingress_promotion_handler=continuity,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(caller,),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(continuity.load_current_working_set().pins, (pin_a,))
            working_events = [
                event
                for event in store.list_run_events(run_contract.harness_run_id)
                if event.event_kind == "harness.working-set-recorded"
            ]
            self.assertEqual(len(working_events), 2)
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_out_of_range_promotion_is_rejected_without_working_set_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _runtime,
                _source_a,
                pin_a,
            ) = self.initialize(Path(directory) / "state", "bad-index")
            retained = self.pause(
                run_contract=run_contract,
                continuity=continuity,
                bridge=bridge,
                projector=projector,
                clock=clock,
            )
            proposal = AgentCallerIngressPromotionProposal(
                next_attempt_id="working-attempt:pc111-bad-index-b",
                promotion_slot="retained-caller",
                caller_message_indexes=(7,),
                basis="malformed attempt to select absent caller bytes",
            )
            adapter = ScriptedTurnAdapter((promotion_turn("bad-index", proposal),))
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
                budget=run_budget(max_model_calls=8, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                caller_ingress_promotion_handler=continuity,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=({"role": "user", "content": "ONLY_INDEX_ZERO"},),
            )
            self.assertEqual(result.stop_code, RunStopCode.INVALID_MODEL_OUTPUT)
            self.assertEqual(continuity.load_current_working_set().pins, (pin_a,))
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_promotion_provider_response_loss_replays_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _runtime,
                _source_a,
                pin_a,
            ) = self.initialize(root, "response-loss")
            retained = self.pause(
                run_contract=run_contract,
                continuity=continuity,
                bridge=bridge,
                projector=projector,
                clock=clock,
            )
            caller = {"role": "user", "content": "CALLER_PROMOTE_AFTER_LOSS"}
            proposal = AgentCallerIngressPromotionProposal(
                next_attempt_id="working-attempt:pc111-response-loss-b",
                promotion_slot="retained-caller",
                caller_message_indexes=(0,),
                basis="preserve the exact caller fact after response loss",
            )
            losing_bridge = LosePromotionCompletionBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                FakeRuntime("direct"),
                provider_source=continuity.snapshot_provider_source(retained),
            )
            first_adapter = ScriptedTurnAdapter((promotion_turn("response-loss", proposal),))
            with self.assertRaisesRegex(RuntimeError, "P-C1.11 response loss"):
                OrdivonAgentLoop(
                    first_adapter,
                    losing_bridge,
                    budget=run_budget(max_model_calls=8, max_tool_calls=2),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=projector,
                    caller_ingress_promotion_handler=continuity,
                ).resume(
                    retained=retained,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    additional_messages=(caller,),
                )
            self.assertEqual(continuity.load_current_working_set().pins, (pin_a,))
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                replay_adapter = ScriptedTurnAdapter(
                    (needs_input_turn(
                        "pc111-response-loss-after-replay",
                        "promotion replayed; inspect the successor cognition",
                    ),)
                )
                replay_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    FakeRuntime("direct"),
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                replayed = OrdivonAgentLoop(
                    replay_adapter,
                    replay_bridge,
                    budget=run_budget(max_model_calls=8, max_tool_calls=2),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(reopened_store, reopened),
                    caller_ingress_promotion_handler=reopened,
                ).resume(
                    retained=retained,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                # The completed promotion proposal is replayed without redispatch,
                # applied exactly once, and the Loop then legitimately starts a new
                # successor-cognition Provider turn. The Scripted adapter is invoked
                # only for that new turn.
                self.assertEqual(replayed.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(len(replay_adapter.requests), 1)
                self.assertEqual(replay_adapter.requests[0].sequence, 3)
                self.assertEqual(
                    str(replay_adapter.requests[0].messages).count(
                        "CALLER_PROMOTE_AFTER_LOSS"
                    ),
                    1,
                )
                current = reopened.load_current_working_set()
                self.assertEqual(len(current.pins), 2)
                promoted_pin = next(pin for pin in current.pins if pin.slot == "retained-caller")
                source = HarnessWorkingViewSource.from_dict(
                    reopened_store.get_object(
                        promoted_pin.resolved_digest,
                        expected_kind="harness-working-view-source",
                    )
                )
                self.assertEqual(source.messages, (caller,))
                self.assertEqual(replayed.usage["providerResultsReplayed"], 1)
                self.assertTrue(reopened.doctor()["healthy"])

    def test_dropping_promoted_pin_reexposes_same_interaction_caller_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _runtime,
                _source_a,
                pin_a,
            ) = self.initialize(Path(directory) / "state", "drop-reexposes")
            retained = self.pause(
                run_contract=run_contract,
                continuity=continuity,
                bridge=bridge,
                projector=projector,
                clock=clock,
            )
            caller = {"role": "user", "content": "CALLER_REEXPOSE_AFTER_DROP"}
            promotion = AgentCallerIngressPromotionProposal(
                next_attempt_id="working-attempt:pc111-drop-reexposes-b",
                promotion_slot="retained-caller",
                caller_message_indexes=(0,),
                basis="preserve caller fact temporarily",
            )
            drop = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc111-drop-reexposes-c",
                pins=(pin_a,),
                basis="drop the promoted durable pin while caller interaction remains active",
            )
            adapter = ScriptedTurnAdapter(
                (
                    promotion_turn("drop-reexposes", promotion),
                    transition_turn("pc111-drop-promoted", drop),
                    needs_input_turn(
                        "pc111-drop-reexposed-pause",
                        "caller authority should still be visible after durable drop",
                    ),
                )
            )
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
                budget=run_budget(max_model_calls=8, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                working_set_transition_handler=continuity,
                caller_ingress_promotion_handler=continuity,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(caller,),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(
                str(adapter.requests[1].messages).count("CALLER_REEXPOSE_AFTER_DROP"),
                1,
            )
            self.assertEqual(
                str(adapter.requests[2].messages).count("CALLER_REEXPOSE_AFTER_DROP"),
                1,
            )
            self.assertEqual(continuity.load_current_working_set().pins, (pin_a,))
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_repromoting_already_durable_caller_index_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _runtime,
                _source_a,
                _pin_a,
            ) = self.initialize(Path(directory) / "state", "repeat-promotion")
            retained = self.pause(
                run_contract=run_contract,
                continuity=continuity,
                bridge=bridge,
                projector=projector,
                clock=clock,
            )
            caller = {"role": "user", "content": "CALLER_REPEAT_PROMOTION"}
            first = AgentCallerIngressPromotionProposal(
                next_attempt_id="working-attempt:pc111-repeat-b",
                promotion_slot="retained-caller",
                caller_message_indexes=(0,),
                basis="first exact promotion",
            )
            second = AgentCallerIngressPromotionProposal(
                next_attempt_id="working-attempt:pc111-repeat-c",
                promotion_slot="duplicate-caller",
                caller_message_indexes=(0,),
                basis="duplicate promotion should fail",
            )
            adapter = ScriptedTurnAdapter(
                (promotion_turn("repeat-first", first), promotion_turn("repeat-second", second))
            )
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
                budget=run_budget(max_model_calls=8, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                caller_ingress_promotion_handler=continuity,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(caller,),
            )
            self.assertEqual(result.stop_code, RunStopCode.INVALID_MODEL_OUTPUT)
            current = continuity.load_current_working_set()
            self.assertEqual(len(current.pins), 2)
            self.assertEqual(
                str(adapter.requests[1].messages).count("CALLER_REPEAT_PROMOTION"),
                1,
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_model_only_privacy_can_promote_caller_ingress_without_tool_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = cognition_contract("pc111-model-only-promotion")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store,
                run_contract,
                clock_ms=clock,
            )
            source = HarnessWorkingViewSource(
                logical_ref="source://pc111/model-only/base",
                logical_generation="generation:1",
                messages=({"role": "user", "content": "model-only durable base"},),
            )
            stored = continuity.store_working_view_source(source)
            pin = HarnessWorkingSetPin(
                slot="primary",
                logical_ref=source.logical_ref,
                logical_generation=source.logical_generation,
                resolved_digest=stored.digest,
            )
            initial = HarnessWorkingSetSpec.initial(
                "working-attempt:pc111-model-only-a",
                pins=(pin,),
            )
            continuity.record_working_set(initial)
            continuity.record_working_set(initial.commit("seed model-only base"))
            self.assertTrue(run_contract.privacy.allow_model_content)
            self.assertFalse(run_contract.privacy.allow_tool_content)
            first_bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            first = OrdivonAgentLoop(
                ScriptedTurnAdapter(
                    (needs_input_turn("pc111-model-only-pause", "caller fact required"),)
                ),
                first_bridge,
                budget=cognition_budget(),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "canonical model-only root"},),
            )
            self.assertEqual(first.stop_code, RunStopCode.NEEDS_INPUT)
            retained = continuity.load_current_snapshot()
            caller = {"role": "user", "content": "MODEL_ONLY_PROMOTED_CALLER"}
            proposal = AgentCallerIngressPromotionProposal(
                next_attempt_id="working-attempt:pc111-model-only-b",
                promotion_slot="retained-caller",
                caller_message_indexes=(0,),
                basis="promote exact caller model content",
            )
            adapter = ScriptedTurnAdapter(
                (
                    promotion_turn("model-only", proposal),
                    needs_input_turn("pc111-model-only-final", "promotion complete"),
                )
            )
            second_bridge = SQLiteHarnessAgentBridge(
                run_contract,
                continuity,
                provider_source=continuity.snapshot_provider_source(retained),
            )
            second = OrdivonAgentLoop(
                adapter,
                second_bridge,
                budget=cognition_budget(),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
                caller_ingress_promotion_handler=continuity,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(caller,),
            )
            self.assertEqual(second.stop_code, RunStopCode.BUDGET_EXHAUSTED)
            current = continuity.load_current_working_set()
            self.assertEqual(len(current.pins), 2)
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()


    def test_deepseek_promotion_control_is_separate_from_runtime_tool_budget(self) -> None:
        proposal = AgentCallerIngressPromotionProposal(
            next_attempt_id="working-attempt:pc111-deepseek-b",
            promotion_slot="retained-caller",
            caller_message_indexes=(0,),
            basis="retain exact caller message zero",
        )
        request = AgentTurnRequest(
            harness_run_id="harness-run:pc111-deepseek",
            turn_id="turn:pc111-deepseek:1",
            sequence=1,
            assignment_id="assignment:pc111-deepseek",
            context_digest=canonical_digest({"pc111": "context"}),
            tool_catalog_digest=canonical_digest({"pc111": "no-runtime-tools"}),
            messages=(
                {"role": "user", "content": "Caller message zero should persist."},
            ),
            tools=(),
            capabilities=AgentTurnCapabilities(caller_ingress_promotion=True),
            remaining_budget=run_budget(
                max_model_calls=2,
                max_tool_calls=0,
            ).remaining(
                model_calls=0,
                tool_calls=0,
                observation_bytes=0,
                elapsed_ms=0,
            ),
            caller_ingress_refs=(
                AgentCallerIngressRef(
                    caller_message_index=0,
                    request_message_index=0,
                ),
            ),
        )
        transport = CaptureTransport(deepseek_promotion_response(proposal))
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="pc111-test-secret"),
            transport=transport,
        )
        result = adapter.invoke(request)
        self.assertEqual(result.tool_calls, ())
        self.assertIsNone(result.conclusion)
        self.assertIsNone(result.working_set_transition)
        self.assertEqual(result.caller_ingress_promotion, proposal)
        body = transport.requests[0]
        tools = body.get("tools")
        self.assertIsInstance(tools, list)
        names = [item["function"]["name"] for item in tools]
        self.assertIn("promote_caller_ingress", names)
        self.assertNotIn("propose_working_set_transition", names)
        self.assertEqual(body.get("tool_choice"), "required")
        self.assertIn('"admittedRuntimeTools":[]', body["messages"][0]["content"])
        self.assertIn('"toolCalls":0', body["messages"][0]["content"])
        self.assertIn('"callerMessageIndex":0', body["messages"][0]["content"])
        self.assertIn('"providerMessageIndex":1', body["messages"][0]["content"])

        disabled_request = replace(
            request, capabilities=AgentTurnCapabilities()
        )
        disabled = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="pc111-test-secret"),
            transport=CaptureTransport(deepseek_promotion_response(proposal)),
        )
        with self.assertRaisesRegex(
            ValueError,
            "unavailable caller ingress promotion control",
        ):
            disabled.invoke(disabled_request)

    def test_deepseek_withdraws_promotion_control_when_no_caller_ingress_is_promotable(self) -> None:
        request = AgentTurnRequest(
            harness_run_id="harness-run:pc111-no-promotable",
            turn_id="turn:pc111-no-promotable:1",
            sequence=1,
            assignment_id="assignment:pc111-no-promotable",
            context_digest=canonical_digest({"pc111": "no-promotable-context"}),
            tool_catalog_digest=canonical_digest({"pc111": "no-promotable-tools"}),
            messages=(
                {
                    "role": "user",
                    "content": "This user-role message is durable selected cognition, not current caller ingress.",
                },
            ),
            tools=(),
            remaining_budget=run_budget(
                max_model_calls=2,
                max_tool_calls=0,
            ).remaining(
                model_calls=0,
                tool_calls=0,
                observation_bytes=0,
                elapsed_ms=0,
            ),
            caller_ingress_refs=(),
        )
        transport = CaptureTransport(deepseek_needs_input_response())
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="pc111-test-secret"),
            transport=transport,
        )
        result = adapter.invoke(request)
        self.assertIsNotNone(result.conclusion)
        self.assertIsNone(result.caller_ingress_promotion)
        body = transport.requests[0]
        tools = body.get("tools")
        self.assertIsInstance(tools, list)
        names = [item["function"]["name"] for item in tools]
        self.assertNotIn("promote_caller_ingress", names)
        self.assertIn("submit_run_conclusion", names)
        control = body["messages"][0]["content"]
        self.assertNotIn('"callerIngress"', control)

    def test_deepseek_rejects_promotion_mixed_with_conclusion(self) -> None:
        proposal = AgentCallerIngressPromotionProposal(
            next_attempt_id="working-attempt:pc111-deepseek-mixed-b",
            promotion_slot="retained-caller",
            caller_message_indexes=(0,),
            basis="mixed action should be rejected",
        )
        request = AgentTurnRequest(
            harness_run_id="harness-run:pc111-deepseek-mixed",
            turn_id="turn:pc111-deepseek-mixed:1",
            sequence=1,
            assignment_id="assignment:pc111-deepseek-mixed",
            context_digest=canonical_digest({"pc111": "mixed-context"}),
            tool_catalog_digest=canonical_digest({"pc111": "mixed-no-tools"}),
            messages=({"role": "user", "content": "do one cognition action"},),
            tools=(),
            capabilities=AgentTurnCapabilities(caller_ingress_promotion=True),
            remaining_budget=run_budget(
                max_model_calls=2,
                max_tool_calls=0,
            ).remaining(
                model_calls=0,
                tool_calls=0,
                observation_bytes=0,
                elapsed_ms=0,
            ),
            caller_ingress_refs=(
                AgentCallerIngressRef(
                    caller_message_index=0, request_message_index=0
                ),
            ),
        )
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="pc111-test-secret"),
            transport=CaptureTransport(
                deepseek_promotion_response(proposal, mixed_conclusion=True)
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "caller ingress promotion cannot be mixed",
        ):
            adapter.invoke(request)


if __name__ == "__main__":
    unittest.main()

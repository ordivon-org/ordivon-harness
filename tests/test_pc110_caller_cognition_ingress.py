from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_agent_bridge import SQLiteHarnessAgentBridge
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

from tests.test_p0_sqlite_agent_loop import FailIfInvokedAdapter
from tests.test_p0_sqlite_runtime_bridge import FakeRuntime, FixedClock, execution_binding
from tests.test_pc13_agent_owned_working_set import cognition_budget, cognition_contract
from tests.test_pc14_candidate_discovery_overlay import transition_turn
from tests.test_pc15_epistemic_control import (
    needs_input_turn,
    private_contract,
    run_budget,
    tool_call,
    tool_turn,
)
from tests.test_pc16_cross_process_tool_exchange import (
    CrashAfterFirstDurableObservationBridge,
    ProcessLost,
)


class LoseCompletionResponseRuntimeBridge(SQLiteHarnessRuntimeBridge):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.injected = False

    def complete_provider_call(self, request, result) -> None:
        super().complete_provider_call(request, result)
        if not self.injected:
            self.injected = True
            raise RuntimeError(
                "injected P-C1.10 response loss after durable Provider completion"
            )


class ForgedCallerIngressRuntimeBridge(SQLiteHarnessRuntimeBridge):
    def restore_current_attempt_cognition_overlay(self, messages, observations):
        restored = super().restore_current_attempt_cognition_overlay(
            messages,
            observations,
        )
        forged = dict(restored)
        caller = list(forged["callerMessages"])
        caller.append(
            {
                "role": "user",
                "content": "FORGED_CALLER_INGRESS_NOT_PRESENT_IN_RUN_STATE",
            }
        )
        forged["callerMessages"] = caller
        return forged


class CallerCognitionIngressTests(unittest.TestCase):
    @staticmethod
    def initialize(
        root: Path,
        suffix: str,
        *,
        max_model_calls: int = 6,
        max_tool_calls: int = 3,
        runtime: FakeRuntime | None = None,
    ):
        runtime = runtime or FakeRuntime("direct")
        run_contract = private_contract(
            f"pc110-{suffix}",
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
            logical_ref=f"source://pc110/{suffix}/a",
            logical_generation="generation:a",
            messages=(
                {
                    "role": "user",
                    "content": "PC110_SOURCE_A: resolve only from current lawful cognition.",
                },
            ),
        )
        source_b = HarnessWorkingViewSource(
            logical_ref=f"source://pc110/{suffix}/b",
            logical_generation="generation:b",
            messages=(
                {
                    "role": "user",
                    "content": "PC110_SOURCE_B: newly selected durable cognition.",
                },
            ),
        )
        stored_a = continuity.store_working_view_source(source_a)
        stored_b = continuity.store_working_view_source(source_b)
        pin_a = HarnessWorkingSetPin(
            slot="primary",
            logical_ref=source_a.logical_ref,
            logical_generation=source_a.logical_generation,
            resolved_digest=stored_a.digest,
        )
        pin_b = HarnessWorkingSetPin(
            slot="secondary",
            logical_ref=source_b.logical_ref,
            logical_generation=source_b.logical_generation,
            resolved_digest=stored_b.digest,
        )
        initial = HarnessWorkingSetSpec.initial(
            f"working-attempt:pc110-{suffix}-a",
            pins=(pin_a,),
        )
        continuity.record_working_set(initial)
        continuity.record_working_set(initial.commit("seed PC110 source A"))
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
            source_b,
            pin_a,
            pin_b,
        )

    @staticmethod
    def pause_after_search(
        *,
        run_contract,
        continuity,
        bridge,
        projector,
        clock,
        max_observation_only_turns: int = 1,
    ):
        adapter = ScriptedTurnAdapter(
            (
                tool_turn(
                    "pc110-pause-search",
                    (tool_call("tool-call:pc110-pause-search", "HarnessExecutionBinding"),),
                ),
                needs_input_turn(
                    "pc110-pause-needs-input",
                    "Caller must supply one new authoritative fact.",
                ),
            )
        )
        result = OrdivonAgentLoop(
            adapter,
            bridge,
            budget=run_budget(
                max_model_calls=6,
                max_tool_calls=3,
                max_observation_only_turns=max_observation_only_turns,
            ),
            clock_ms=clock,
            monotonic_ms=clock,
            working_view_projector=projector,
        ).run(
            harness_run_id=run_contract.harness_run_id,
            assignment_id=continuity.binding.assignment_id,
            context_digest=run_contract.context_refs[0].digest,
            initial_messages=(
                {"role": "user", "content": "canonical pc110 root"},
            ),
        )
        if result.stop_code is not RunStopCode.NEEDS_INPUT:
            raise AssertionError(result.stop_code)
        return adapter, continuity.load_current_snapshot()

    def test_projected_resume_caller_input_is_visible_and_reopens_soft_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                runtime,
                _source_a,
                _source_b,
                _pin_a,
                _pin_b,
            ) = self.initialize(Path(directory) / "state", "visible-soft-gate")
            first_adapter, retained = self.pause_after_search(
                run_contract=run_contract,
                continuity=continuity,
                bridge=bridge,
                projector=projector,
                clock=clock,
            )
            self.assertEqual(first_adapter.requests[1].tools, ())
            self.assertEqual(runtime.workspace_exec_count, 1)

            caller = {
                "role": "user",
                "content": "CALLER_INGRESS_BLUE_17: the authoritative current code is BLUE-17.",
            }
            second_adapter = ScriptedTurnAdapter(
                (
                    needs_input_turn(
                        "pc110-visible-close",
                        "Inspect caller-authorized cognition ingress.",
                    ),
                )
            )
            resume_bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
                provider_source=continuity.snapshot_provider_source(retained),
            )
            second = OrdivonAgentLoop(
                second_adapter,
                resume_bridge,
                budget=run_budget(
                    max_model_calls=6,
                    max_tool_calls=3,
                    max_observation_only_turns=1,
                ),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(caller,),
            )
            self.assertEqual(second.stop_code, RunStopCode.NEEDS_INPUT)
            request = second_adapter.requests[0]
            self.assertIn(caller, request.messages)
            self.assertEqual(request.messages[-1], caller)
            self.assertNotEqual(request.tools, ())
            self.assertEqual(request.remaining_budget["observationOnlyTurns"], 1)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_caller_ingress_survives_agent_working_set_transition(self) -> None:
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
                _source_b,
                pin_a,
                pin_b,
            ) = self.initialize(Path(directory) / "state", "survive-transition")
            pause_adapter = ScriptedTurnAdapter(
                (
                    needs_input_turn(
                        "pc110-transition-pause",
                        "Caller should provide one new premise.",
                    ),
                )
            )
            paused = OrdivonAgentLoop(
                pause_adapter,
                bridge,
                budget=run_budget(max_model_calls=6, max_tool_calls=3),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "canonical pc110 transition root"},),
            )
            self.assertEqual(paused.stop_code, RunStopCode.NEEDS_INPUT)
            retained = continuity.load_current_snapshot()
            caller = {
                "role": "user",
                "content": "CALLER_INGRESS_TRANSITION: retain this premise across your replan.",
            }
            proposal = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc110-survive-transition-b",
                pins=(pin_a, pin_b),
                basis="Select B while retaining caller-authorized interaction cognition.",
            )
            adapter = ScriptedTurnAdapter(
                (
                    transition_turn("pc110-caller-transition", proposal),
                    needs_input_turn(
                        "pc110-caller-after-transition",
                        "Caller ingress should remain visible after the WorkingSet transition.",
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
                budget=run_budget(max_model_calls=6, max_tool_calls=3),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                working_set_transition_handler=continuity,
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(caller,),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertIn(caller, adapter.requests[0].messages)
            self.assertIn(caller, adapter.requests[1].messages)
            self.assertEqual(continuity.load_current_working_set().pins, (pin_a, pin_b))
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_next_needs_input_consumes_old_ingress_and_admits_only_new_reply(self) -> None:
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
                _source_b,
                _pin_a,
                _pin_b,
            ) = self.initialize(root, "consume-at-pause")
            first_pause = ScriptedTurnAdapter(
                (needs_input_turn("pc110-consume-pause-1", "first caller reply required"),)
            )
            first = OrdivonAgentLoop(
                first_pause,
                bridge,
                budget=run_budget(max_model_calls=6, max_tool_calls=3),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "canonical pc110 consume root"},),
            )
            self.assertEqual(first.stop_code, RunStopCode.NEEDS_INPUT)
            first_snapshot = continuity.load_current_snapshot()
            old = {"role": "user", "content": "CALLER_INGRESS_OLD"}
            second_adapter = ScriptedTurnAdapter(
                (needs_input_turn("pc110-consume-pause-2", "second caller reply required"),)
            )
            second_bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                FakeRuntime("direct"),
                provider_source=continuity.snapshot_provider_source(first_snapshot),
            )
            second = OrdivonAgentLoop(
                second_adapter,
                second_bridge,
                budget=run_budget(max_model_calls=6, max_tool_calls=3),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).resume(
                retained=first_snapshot,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(old,),
            )
            self.assertEqual(second.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertIn(old, second_adapter.requests[0].messages)
            second_snapshot = continuity.load_current_snapshot()
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                second_snapshot = reopened.load_current_snapshot()
                new = {"role": "user", "content": "CALLER_INGRESS_NEW"}
                third_adapter = ScriptedTurnAdapter(
                    (needs_input_turn("pc110-consume-final", "inspect only the latest reply"),)
                )
                replay_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    FakeRuntime("direct"),
                    provider_source=reopened.snapshot_provider_source(second_snapshot),
                )
                third = OrdivonAgentLoop(
                    third_adapter,
                    replay_bridge,
                    budget=run_budget(max_model_calls=6, max_tool_calls=3),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(reopened_store, reopened),
                ).resume(
                    retained=second_snapshot,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    additional_messages=(new,),
                )
                self.assertEqual(third.stop_code, RunStopCode.NEEDS_INPUT)
                request_text = str(third_adapter.requests[0].messages)
                self.assertIn("CALLER_INGRESS_NEW", request_text)
                self.assertNotIn("CALLER_INGRESS_OLD", request_text)
                self.assertTrue(reopened.doctor()["healthy"])

    def test_caller_ingress_reconstructs_after_tool_snapshot_and_process_loss(self) -> None:
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
                _source_b,
                _pin_a,
                _pin_b,
            ) = self.initialize(root, "cross-process")
            first_pause_adapter = ScriptedTurnAdapter(
                (needs_input_turn("pc110-cross-pause", "caller reply required"),)
            )
            paused = OrdivonAgentLoop(
                first_pause_adapter,
                bridge,
                budget=run_budget(max_model_calls=6, max_tool_calls=3),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "canonical pc110 cross root"},),
            )
            self.assertEqual(paused.stop_code, RunStopCode.NEEDS_INPUT)
            pause_snapshot = continuity.load_current_snapshot()
            caller = {"role": "user", "content": "CALLER_INGRESS_CROSS_PROCESS"}
            crash_runtime = FakeRuntime("direct")
            crash_bridge = CrashAfterFirstDurableObservationBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                crash_runtime,
                provider_source=continuity.snapshot_provider_source(pause_snapshot),
            )
            crash_adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "pc110-cross-tool",
                        (tool_call("tool-call:pc110-cross-tool", "HarnessExecutionBinding"),),
                    ),
                )
            )
            with self.assertRaisesRegex(ProcessLost, "after durable Tool observation"):
                OrdivonAgentLoop(
                    crash_adapter,
                    crash_bridge,
                    budget=run_budget(max_model_calls=6, max_tool_calls=3),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=projector,
                ).resume(
                    retained=pause_snapshot,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    additional_messages=(caller,),
                )
            self.assertEqual(crash_runtime.workspace_exec_count, 1)
            retained_after_crash = continuity.load_current_snapshot()
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained_after_crash = reopened.load_current_snapshot()
                adapter = ScriptedTurnAdapter(
                    (needs_input_turn("pc110-cross-resumed", "inspect restored cognition"),)
                )
                replay_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    FakeRuntime("direct"),
                    provider_source=reopened.snapshot_provider_source(retained_after_crash),
                )
                result = OrdivonAgentLoop(
                    adapter,
                    replay_bridge,
                    budget=run_budget(max_model_calls=6, max_tool_calls=3),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(reopened_store, reopened),
                ).resume(
                    retained=retained_after_crash,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
                messages = adapter.requests[0].messages
                self.assertEqual(messages[0], source_a.messages[0])
                caller_index = messages.index(caller)
                tool_assistant_index = next(
                    index
                    for index, message in enumerate(messages)
                    if message.get("role") == "assistant" and "toolCalls" in message
                )
                self.assertLess(caller_index, tool_assistant_index)
                self.assertEqual(messages[tool_assistant_index + 1]["role"], "tool")
                self.assertTrue(reopened.doctor()["healthy"])

    def test_projected_resume_rejects_non_user_cognition_ingress(self) -> None:
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
                _source_b,
                _pin_a,
                _pin_b,
            ) = self.initialize(Path(directory) / "state", "reject-role")
            adapter = ScriptedTurnAdapter(
                (needs_input_turn("pc110-reject-pause", "caller reply required"),)
            )
            paused = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(max_model_calls=6, max_tool_calls=3),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "canonical pc110 reject root"},),
            )
            self.assertEqual(paused.stop_code, RunStopCode.NEEDS_INPUT)
            retained = continuity.load_current_snapshot()
            forbidden = {"role": "system", "content": "FORGED_CALLER_SYSTEM_OVERRIDE"}
            should_not_run = ScriptedTurnAdapter(
                (needs_input_turn("pc110-reject-should-not-run", "must not dispatch"),)
            )
            resume_bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                FakeRuntime("direct"),
                provider_source=continuity.snapshot_provider_source(retained),
            )
            with self.assertRaisesRegex(ValueError, "caller cognition ingress"):
                OrdivonAgentLoop(
                    should_not_run,
                    resume_bridge,
                    budget=run_budget(max_model_calls=6, max_tool_calls=3),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=projector,
                ).resume(
                    retained=retained,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    additional_messages=(forbidden,),
                )
            self.assertEqual(should_not_run.requests, [])
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()


    def test_forged_caller_ingress_is_rejected_before_provider_dispatch(self) -> None:
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
                _source_b,
                _pin_a,
                _pin_b,
            ) = self.initialize(root, "forged-ingress")
            pause_adapter = ScriptedTurnAdapter(
                (needs_input_turn("pc110-forged-pause", "caller reply required"),)
            )
            paused = OrdivonAgentLoop(
                pause_adapter,
                bridge,
                budget=run_budget(max_model_calls=6, max_tool_calls=3),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "canonical pc110 forged root"},),
            )
            self.assertEqual(paused.stop_code, RunStopCode.NEEDS_INPUT)
            retained = continuity.load_current_snapshot()
            caller = {"role": "user", "content": "LEGITIMATE_CALLER_INGRESS"}
            forged_bridge = ForgedCallerIngressRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                FakeRuntime("direct"),
                provider_source=continuity.snapshot_provider_source(retained),
            )
            should_not_run = ScriptedTurnAdapter(
                (needs_input_turn("pc110-forged-should-not-run", "must not dispatch"),)
            )
            with self.assertRaisesRegex(
                Exception,
                "durable Tool/caller cognition authority",
            ):
                OrdivonAgentLoop(
                    should_not_run,
                    forged_bridge,
                    budget=run_budget(max_model_calls=6, max_tool_calls=3),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=projector,
                ).resume(
                    retained=retained,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    additional_messages=(caller,),
                )
            self.assertEqual(should_not_run.requests, [])
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_caller_ingress_provider_response_loss_replays_without_resend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                runtime,
                _source_a,
                _source_b,
                _pin_a,
                _pin_b,
            ) = self.initialize(root, "provider-response-loss")
            _pause_adapter, retained = self.pause_after_search(
                run_contract=run_contract,
                continuity=continuity,
                bridge=bridge,
                projector=projector,
                clock=clock,
            )
            self.assertEqual(runtime.workspace_exec_count, 1)
            caller = {
                "role": "user",
                "content": "CALLER_INGRESS_RESPONSE_LOSS: authoritative reply.",
            }
            lost_result = needs_input_turn(
                "pc110-response-loss-result",
                "The caller ingress was visible before Provider response loss.",
            )
            losing_bridge = LoseCompletionResponseRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                FakeRuntime("direct"),
                provider_source=continuity.snapshot_provider_source(retained),
            )
            first_adapter = ScriptedTurnAdapter((lost_result,))
            with self.assertRaisesRegex(RuntimeError, "P-C1.10 response loss"):
                OrdivonAgentLoop(
                    first_adapter,
                    losing_bridge,
                    budget=run_budget(
                        max_model_calls=6,
                        max_tool_calls=3,
                        max_observation_only_turns=1,
                    ),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=projector,
                ).resume(
                    retained=retained,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    additional_messages=(caller,),
                )
            self.assertEqual(len(first_adapter.requests), 1)
            self.assertIn(caller, first_adapter.requests[0].messages)
            retained_source = continuity.load_current_snapshot()
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained_source = reopened.load_current_snapshot()
                fail_if_invoked = FailIfInvokedAdapter()
                replay_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    FakeRuntime("direct"),
                    provider_source=reopened.snapshot_provider_source(retained_source),
                )
                replayed = OrdivonAgentLoop(
                    fail_if_invoked,
                    replay_bridge,
                    budget=run_budget(
                        max_model_calls=6,
                        max_tool_calls=3,
                        max_observation_only_turns=1,
                    ),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(reopened_store, reopened),
                ).resume(
                    retained=retained_source,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(replayed.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(fail_if_invoked.requests, [])
                self.assertEqual(replayed.usage["providerResultsReplayed"], 1)
                self.assertIn(caller, replayed.messages)
                self.assertTrue(reopened.doctor()["healthy"])


    def test_caller_ingress_needs_model_content_but_not_tool_content_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = cognition_contract("pc110-model-only-caller")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store,
                run_contract,
                clock_ms=clock,
            )
            source = HarnessWorkingViewSource(
                logical_ref="source://pc110/model-only/base",
                logical_generation="generation:1",
                messages=(
                    {
                        "role": "user",
                        "content": "Wait for an exact caller-authorized fact before answering.",
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
                "working-attempt:pc110-model-only-a",
                pins=(pin,),
            )
            continuity.record_working_set(initial)
            continuity.record_working_set(initial.commit("seed model-only caller ingress"))
            self.assertTrue(run_contract.privacy.allow_model_content)
            self.assertFalse(run_contract.privacy.allow_tool_content)

            first_adapter = ScriptedTurnAdapter(
                (needs_input_turn("pc110-model-only-pause", "caller fact required"),)
            )
            first_bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            first = OrdivonAgentLoop(
                first_adapter,
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
            caller = {
                "role": "user",
                "content": "MODEL_ONLY_CALLER_INGRESS_BLUE_17",
            }
            second_adapter = ScriptedTurnAdapter(
                (needs_input_turn("pc110-model-only-final", "inspect caller ingress"),)
            )
            second_bridge = SQLiteHarnessAgentBridge(
                run_contract,
                continuity,
                provider_source=continuity.snapshot_provider_source(retained),
            )
            second = OrdivonAgentLoop(
                second_adapter,
                second_bridge,
                budget=cognition_budget(),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
            ).resume(
                retained=retained,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                additional_messages=(caller,),
            )
            self.assertEqual(second.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(second_adapter.requests[0].messages, source.messages + (caller,))
            self.assertEqual(second_adapter.requests[0].tools, ())
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()


if __name__ == "__main__":
    unittest.main()

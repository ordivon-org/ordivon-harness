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
from tests.test_pc13_agent_owned_working_set import transition_result
from tests.test_pc15_epistemic_control import (
    needs_input_turn,
    private_contract,
    run_budget,
    tool_call,
    tool_turn,
)


class ProcessLost(BaseException):
    pass


class CrashAfterFirstDurableObservationBridge(SQLiteHarnessRuntimeBridge):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.completed_runtime_calls = 0

    def execute_with_control(self, call, *, step_id, turn_id, control):
        observation = super().execute_with_control(
            call,
            step_id=step_id,
            turn_id=turn_id,
            control=control,
        )
        self.completed_runtime_calls += 1
        if self.completed_runtime_calls == 1:
            raise ProcessLost("process disappeared after durable Tool observation")
        return observation


class CrossProcessToolExchangeTests(unittest.TestCase):
    def test_fresh_process_rebuilds_complete_current_attempt_tool_exchange(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc16-cross-process-exchange",
                max_model_calls=2,
                max_tool_calls=2,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store,
                run_contract,
                clock_ms=clock,
            )

            # Reuse the P-C1.5 base-view setup without depending on any transient
            # in-memory exchange state.
            source = HarnessWorkingViewSource(
                logical_ref="source://pc16/current/base",
                logical_generation="generation:1",
                messages=(
                    {
                        "role": "user",
                        "content": "Resolve the fact after the bounded Tool observations.",
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
                "working-attempt:pc16-a",
                pins=(pin,),
            )
            continuity.record_working_set(initial)
            continuity.record_working_set(initial.commit("seed P-C1.6 base view"))

            first_runtime = FakeRuntime("direct")
            first_bridge = CrashAfterFirstDurableObservationBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                first_runtime,
            )
            calls = (
                tool_call("tool-call:pc16-a", "HarnessExecutionBinding"),
                tool_call("tool-call:pc16-b", "Runtime"),
            )
            first_adapter = ScriptedTurnAdapter((tool_turn("pc16-crash", calls),))
            first_loop = OrdivonAgentLoop(
                first_adapter,
                first_bridge,
                budget=run_budget(max_model_calls=2, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
            )
            with self.assertRaisesRegex(
                ProcessLost,
                "after durable Tool observation",
            ):
                first_loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical pc16 root"},
                    ),
                )
            self.assertEqual(first_runtime.workspace_exec_count, 1)
            retained_before_close = continuity.load_current_snapshot()
            self.assertEqual(len(retained_before_close.snapshot.active_tool_step_intent_digests), 1)
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                second_runtime = FakeRuntime("direct")
                replay_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    second_runtime,
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                unknown = "No further fact is available after the recovered Tool exchange."
                second_adapter = ScriptedTurnAdapter(
                    (needs_input_turn("pc16-resumed", unknown),)
                )
                second_loop = OrdivonAgentLoop(
                    second_adapter,
                    replay_bridge,
                    budget=run_budget(max_model_calls=2, max_tool_calls=2),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        reopened_store,
                        reopened,
                    ),
                )
                result = second_loop.resume(
                    retained=retained,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )

                self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(result.conclusion.unresolved_unknowns, (unknown,))
                # Tool A was already physically completed before process loss. The
                # fresh process reconciles A from its durable receipt and executes
                # only the pending Tool B.
                self.assertEqual(second_runtime.workspace_exec_count, 1)
                self.assertEqual(len(second_adapter.requests), 1)
                resumed_request = second_adapter.requests[0]
                self.assertEqual(resumed_request.sequence, 2)
                self.assertEqual(resumed_request.messages[:1], source.messages)
                self.assertEqual(resumed_request.messages[1]["role"], "assistant")
                self.assertEqual(
                    [item["toolCallId"] for item in resumed_request.messages[1]["toolCalls"]],
                    [call.tool_call_id for call in calls],
                )
                self.assertEqual(
                    [message["toolCallId"] for message in resumed_request.messages[2:]],
                    [call.tool_call_id for call in calls],
                )
                self.assertTrue(
                    all(message["role"] == "tool" for message in resumed_request.messages[2:])
                )
                self.assertTrue(reopened.doctor()["healthy"])


    def test_successor_attempt_does_not_restore_predecessor_tool_exchange(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc16-attempt-boundary",
                max_model_calls=4,
                max_tool_calls=2,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store,
                run_contract,
                clock_ms=clock,
            )
            source_a = HarnessWorkingViewSource(
                logical_ref="source://pc16/boundary/current",
                logical_generation="generation:a",
                messages=({"role": "user", "content": "PC16_VIEW_A"},),
            )
            source_b = HarnessWorkingViewSource(
                logical_ref="source://pc16/boundary/current",
                logical_generation="generation:b",
                messages=({"role": "user", "content": "PC16_VIEW_B"},),
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
                slot="primary",
                logical_ref=source_b.logical_ref,
                logical_generation=source_b.logical_generation,
                resolved_digest=stored_b.digest,
            )
            initial = HarnessWorkingSetSpec.initial(
                "working-attempt:pc16-boundary-a",
                pins=(pin_a,),
            )
            continuity.record_working_set(initial)
            continuity.record_working_set(initial.commit("seed A"))

            runtime_a = FakeRuntime("direct")
            bridge_a = CrashAfterFirstDurableObservationBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime_a,
            )
            call_a = tool_call("tool-call:pc16-boundary-a", "HarnessExecutionBinding")
            loop_a = OrdivonAgentLoop(
                ScriptedTurnAdapter((tool_turn("pc16-boundary-a", (call_a,)),)),
                bridge_a,
                budget=run_budget(max_model_calls=4, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
            )
            with self.assertRaises(ProcessLost):
                loop_a.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical pc16 boundary"},
                    ),
                )
            self.assertEqual(
                len(continuity.load_current_snapshot().snapshot.active_tool_step_intent_digests),
                1,
            )
            store.close()

            with SQLiteHarnessStore(root) as store_b:
                continuity_b = SQLiteHarnessRunContinuityStore.open(
                    store_b,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained_a = continuity_b.load_current_snapshot()
                proposal = AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc16-boundary-b",
                    pins=(pin_b,),
                    basis="Agent moves from recovered A evidence to exact B",
                )
                call_b = tool_call("tool-call:pc16-boundary-b", "Runtime")
                adapter_b = ScriptedTurnAdapter(
                    (
                        transition_result(proposal),
                        tool_turn("pc16-boundary-b", (call_b,)),
                    )
                )
                runtime_b = FakeRuntime("direct")
                bridge_b = CrashAfterFirstDurableObservationBridge(
                    run_contract,
                    continuity_b,
                    execution_binding(run_contract, continuity_b),
                    runtime_b,
                    provider_source=continuity_b.snapshot_provider_source(retained_a),
                )
                loop_b = OrdivonAgentLoop(
                    adapter_b,
                    bridge_b,
                    budget=run_budget(max_model_calls=4, max_tool_calls=2),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        store_b,
                        continuity_b,
                    ),
                    working_set_transition_handler=continuity_b,
                )
                with self.assertRaises(ProcessLost):
                    loop_b.resume(
                        retained=retained_a,
                        assignment_id=continuity_b.binding.assignment_id,
                        context_digest=run_contract.context_refs[0].digest,
                    )
                self.assertEqual(runtime_b.workspace_exec_count, 1)
                self.assertEqual(len(adapter_b.requests), 2)
                # The Agent sees A's recovered exchange when deciding to transition.
                self.assertIn(call_a.tool_call_id, str(adapter_b.requests[0].messages))
                # Once B commits, in-process transient A cognition is cleared.
                self.assertEqual(adapter_b.requests[1].messages, source_b.messages)
                self.assertNotIn(call_a.tool_call_id, str(adapter_b.requests[1].messages))
                snapshot_b = continuity_b.load_current_snapshot()
                self.assertEqual(
                    continuity_b.load_current_working_set().attempt_id,
                    proposal.next_attempt_id,
                )

            with SQLiteHarnessStore(root) as store_c:
                continuity_c = SQLiteHarnessRunContinuityStore.open(
                    store_c,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained_b = continuity_c.load_current_snapshot()
                self.assertEqual(retained_b.snapshot.digest, snapshot_b.snapshot.digest)
                runtime_c = FakeRuntime("direct")
                bridge_c = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    continuity_c,
                    execution_binding(run_contract, continuity_c),
                    runtime_c,
                    provider_source=continuity_c.snapshot_provider_source(retained_b),
                )
                unknown = "B evidence is exhausted after recovery."
                adapter_c = ScriptedTurnAdapter(
                    (needs_input_turn("pc16-boundary-final", unknown),)
                )
                loop_c = OrdivonAgentLoop(
                    adapter_c,
                    bridge_c,
                    budget=run_budget(max_model_calls=4, max_tool_calls=2),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        store_c,
                        continuity_c,
                    ),
                )
                result = loop_c.resume(
                    retained=retained_b,
                    assignment_id=continuity_c.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(runtime_c.workspace_exec_count, 0)
                final_request = adapter_c.requests[0]
                self.assertEqual(final_request.messages[:1], source_b.messages)
                self.assertIn(call_b.tool_call_id, str(final_request.messages))
                self.assertNotIn(call_a.tool_call_id, str(final_request.messages))
                restored_events = [
                    event
                    for event in result.trace.events
                    if event.kind == "transient_tool_exchange_restored"
                ]
                self.assertEqual(len(restored_events), 1)
                self.assertTrue(continuity_c.doctor()["healthy"])


    def test_cross_process_tool_exchange_recovery_fails_without_tool_content_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = replace(
                private_contract(
                    "pc16-tool-content-authority",
                    max_model_calls=2,
                    max_tool_calls=1,
                ),
                privacy=HarnessPrivacyPolicy(
                    content_policy="bounded-private-content",
                    allow_model_content=True,
                    allow_tool_content=False,
                ),
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store,
                run_contract,
                clock_ms=clock,
            )
            source = HarnessWorkingViewSource(
                logical_ref="source://pc16/privacy/base",
                logical_generation="generation:1",
                messages=({"role": "user", "content": "PC16_PRIVACY_BASE"},),
            )
            stored = continuity.store_working_view_source(source)
            pin = HarnessWorkingSetPin(
                slot="primary",
                logical_ref=source.logical_ref,
                logical_generation=source.logical_generation,
                resolved_digest=stored.digest,
            )
            initial = HarnessWorkingSetSpec.initial(
                "working-attempt:pc16-privacy-a",
                pins=(pin,),
            )
            continuity.record_working_set(initial)
            continuity.record_working_set(initial.commit("seed privacy view"))

            first_runtime = FakeRuntime("direct")
            first_bridge = CrashAfterFirstDurableObservationBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                first_runtime,
            )
            call = tool_call("tool-call:pc16-privacy", "HarnessExecutionBinding")
            first_loop = OrdivonAgentLoop(
                ScriptedTurnAdapter((tool_turn("pc16-privacy", (call,)),)),
                first_bridge,
                budget=run_budget(max_model_calls=2, max_tool_calls=1),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
            )
            with self.assertRaises(ProcessLost):
                first_loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical pc16 privacy"},
                    ),
                )
            self.assertEqual(first_runtime.workspace_exec_count, 1)
            retained = continuity.load_current_snapshot()
            self.assertFalse(retained.state.messages_retained)
            current_tool = continuity.load_current_tool_step()
            self.assertTrue(current_tool.receipt.terminal)
            self.assertIsNone(current_tool.observation)
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                second_runtime = FakeRuntime("direct")
                replay_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    second_runtime,
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                second_loop = OrdivonAgentLoop(
                    ScriptedTurnAdapter(
                        (needs_input_turn("pc16-privacy-final", "rehydration required"),)
                    ),
                    replay_bridge,
                    budget=run_budget(max_model_calls=2, max_tool_calls=1),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        reopened_store,
                        reopened,
                    ),
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "resume content was not retained",
                ):
                    second_loop.resume(
                        retained=retained,
                        assignment_id=reopened.binding.assignment_id,
                        context_digest=run_contract.context_refs[0].digest,
                    )
                self.assertEqual(second_runtime.workspace_exec_count, 0)
                self.assertTrue(reopened.doctor()["healthy"])


if __name__ == "__main__":
    unittest.main()

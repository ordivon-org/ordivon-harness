from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

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
from tests.test_pc14_candidate_discovery_overlay import transition_turn
from tests.test_pc15_epistemic_control import (
    needs_input_turn,
    private_contract,
    run_budget,
    tool_call,
    tool_turn,
)


class CognitionTransitionProgressTests(unittest.TestCase):
    @staticmethod
    def initialize(
        root: Path,
        suffix: str,
        *,
        max_model_calls: int,
        max_tool_calls: int,
        runtime: FakeRuntime,
    ):
        run_contract = private_contract(
            f"pc19-{suffix}",
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
            logical_ref=f"source://pc19/{suffix}/a",
            logical_generation="generation:a",
            messages=(
                {
                    "role": "user",
                    "content": "PC19_SOURCE_A: use bounded evidence and do not invent facts.",
                },
            ),
        )
        source_b = HarnessWorkingViewSource(
            logical_ref=f"source://pc19/{suffix}/b",
            logical_generation="generation:b",
            messages=(
                {
                    "role": "user",
                    "content": "PC19_SOURCE_B: this is an explicitly selected new cognition source.",
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
            f"working-attempt:pc19-{suffix}-a",
            pins=(pin_a,),
        )
        continuity.record_working_set(initial)
        continuity.record_working_set(initial.commit("seed PC19 source A"))
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
            source_a,
            source_b,
            pin_a,
            pin_b,
        )

    def test_same_selection_attempt_reset_does_not_reopen_closed_soft_effect_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _source_a,
                _source_b,
                pin_a,
                _pin_b,
            ) = self.initialize(
                Path(directory) / "state",
                "same-selection-gate",
                max_model_calls=3,
                max_tool_calls=3,
                runtime=runtime,
            )
            same = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc19-same-selection-gate-b",
                pins=(pin_a,),
                basis="Discard attempt-local cognition but retain the exact selected source.",
            )
            adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "pc19-same-gate-search-1",
                        (tool_call("tool-call:pc19-same-gate-1", "HarnessExecutionBinding"),),
                    ),
                    transition_turn("pc19-same-gate-reset", same),
                    tool_turn(
                        "pc19-same-gate-search-2",
                        (tool_call("tool-call:pc19-same-gate-2", "Runtime"),),
                    ),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(
                    max_model_calls=3,
                    max_tool_calls=3,
                    max_observation_only_turns=1,
                ),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                working_set_transition_handler=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc19 same-selection gate"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NO_PROGRESS)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(result.tool_calls, 1)
            self.assertEqual(len(adapter.requests), 3)
            self.assertEqual(adapter.requests[1].tools, ())
            self.assertEqual(adapter.requests[2].tools, ())
            self.assertEqual(
                continuity.load_current_working_set().attempt_id,
                same.next_attempt_id,
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_selection_change_reopens_closed_soft_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _source_a,
                _source_b,
                pin_a,
                pin_b,
            ) = self.initialize(
                Path(directory) / "state",
                "changed-selection-gate",
                max_model_calls=4,
                max_tool_calls=3,
                runtime=runtime,
            )
            changed = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc19-changed-selection-gate-b",
                pins=(pin_a, pin_b),
                basis="Select an additional exact source before another bounded observation.",
            )
            adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "pc19-change-gate-search-1",
                        (tool_call("tool-call:pc19-change-gate-1", "HarnessExecutionBinding"),),
                    ),
                    transition_turn("pc19-change-gate-select", changed),
                    tool_turn(
                        "pc19-change-gate-search-2",
                        (tool_call("tool-call:pc19-change-gate-2", "Runtime"),),
                    ),
                    needs_input_turn(
                        "pc19-change-gate-close",
                        "No further bounded evidence resolves the requested fact.",
                    ),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(
                    max_model_calls=4,
                    max_tool_calls=3,
                    max_observation_only_turns=1,
                ),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                working_set_transition_handler=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc19 changed-selection gate"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(runtime.workspace_exec_count, 2)
            self.assertEqual(result.tool_calls, 2)
            self.assertEqual(adapter.requests[1].tools, ())
            self.assertNotEqual(adapter.requests[2].tools, ())
            self.assertEqual(
                continuity.load_current_working_set().pins,
                (pin_a, pin_b),
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_same_selection_attempt_reset_still_discards_transient_tool_exchange(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                source_a,
                _source_b,
                pin_a,
                _pin_b,
            ) = self.initialize(
                Path(directory) / "state",
                "same-selection-transient",
                max_model_calls=3,
                max_tool_calls=2,
                runtime=runtime,
            )
            same = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc19-same-selection-transient-b",
                pins=(pin_a,),
                basis="Restart cognition from the same durable source without old Tool exchange.",
            )
            adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "pc19-same-transient-search",
                        (tool_call("tool-call:pc19-same-transient-1", "HarnessExecutionBinding"),),
                    ),
                    transition_turn("pc19-same-transient-reset", same),
                    needs_input_turn(
                        "pc19-same-transient-close",
                        "The reset attempt intentionally discarded transient Tool evidence.",
                    ),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(
                    max_model_calls=3,
                    max_tool_calls=2,
                    max_observation_only_turns=6,
                ),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                working_set_transition_handler=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc19 same-selection transient"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(adapter.requests[1].messages[0], source_a.messages[0])
            self.assertGreater(len(adapter.requests[1].messages), 1)
            self.assertEqual(adapter.requests[2].messages, source_a.messages)
            self.assertEqual(
                continuity.load_current_working_set().attempt_id,
                same.next_attempt_id,
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_fresh_resume_reconstructs_closed_soft_gate_without_new_caller_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _source_a,
                _source_b,
                _pin_a,
                _pin_b,
            ) = self.initialize(
                root,
                "resume-soft-gate",
                max_model_calls=4,
                max_tool_calls=3,
                runtime=runtime,
            )
            first_adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "pc19-resume-gate-search",
                        (tool_call("tool-call:pc19-resume-gate-1", "HarnessExecutionBinding"),),
                    ),
                    needs_input_turn(
                        "pc19-resume-gate-pause",
                        "Caller input may later add genuinely new information.",
                    ),
                )
            )
            first = OrdivonAgentLoop(
                first_adapter,
                bridge,
                budget=run_budget(
                    max_model_calls=4,
                    max_tool_calls=3,
                    max_observation_only_turns=1,
                ),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc19 resume gate"},
                ),
            )
            self.assertEqual(first.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(first_adapter.requests[1].tools, ())
            retained = continuity.load_current_snapshot()
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                replay_runtime = FakeRuntime("direct")
                replay_bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    replay_runtime,
                    provider_source=reopened.snapshot_provider_source(retained),
                )
                second_adapter = ScriptedTurnAdapter(
                    (
                        needs_input_turn(
                            "pc19-resume-gate-still-closed",
                            "No new caller information was supplied on resume.",
                        ),
                    )
                )
                second = OrdivonAgentLoop(
                    second_adapter,
                    replay_bridge,
                    budget=run_budget(
                        max_model_calls=4,
                        max_tool_calls=3,
                        max_observation_only_turns=1,
                    ),
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
                self.assertEqual(second.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(second_adapter.requests[0].tools, ())
                self.assertEqual(replay_runtime.workspace_exec_count, 0)
                self.assertTrue(reopened.doctor()["healthy"])

    def test_projected_resume_input_resets_gate_once_model_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _source_a,
                _source_b,
                _pin_a,
                _pin_b,
            ) = self.initialize(
                root,
                "resume-new-input",
                max_model_calls=4,
                max_tool_calls=3,
                runtime=runtime,
            )
            first_adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "pc19-resume-input-search",
                        (tool_call("tool-call:pc19-resume-input-1", "HarnessExecutionBinding"),),
                    ),
                    needs_input_turn(
                        "pc19-resume-input-pause",
                        "A caller-supplied fact could change what observation is useful.",
                    ),
                )
            )
            first = OrdivonAgentLoop(
                first_adapter,
                bridge,
                budget=run_budget(
                    max_model_calls=4,
                    max_tool_calls=3,
                    max_observation_only_turns=1,
                ),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc19 new-input gate"},
                ),
            )
            self.assertEqual(first.stop_code, RunStopCode.NEEDS_INPUT)
            retained = continuity.load_current_snapshot()
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                second_adapter = ScriptedTurnAdapter(
                    (
                        needs_input_turn(
                            "pc19-resume-input-open",
                            "The new caller message makes another bounded observation admissible.",
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
                second = OrdivonAgentLoop(
                    second_adapter,
                    replay_bridge,
                    budget=run_budget(
                        max_model_calls=4,
                        max_tool_calls=3,
                        max_observation_only_turns=1,
                    ),
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
                    additional_messages=(
                        {
                            "role": "user",
                            "content": "New caller evidence: inspect again under this changed premise.",
                        },
                    ),
                )
                self.assertEqual(second.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertNotEqual(second_adapter.requests[0].tools, ())
                self.assertEqual(
                    second_adapter.requests[0].remaining_budget["observationOnlyTurns"],
                    1,
                )
                self.assertIn(
                    "New caller evidence: inspect again under this changed premise.",
                    str(second_adapter.requests[0].messages),
                )
                self.assertTrue(reopened.doctor()["healthy"])


    def test_same_selection_reset_does_not_clear_soft_progress_before_gate_closes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _source_a,
                _source_b,
                pin_a,
                _pin_b,
            ) = self.initialize(
                Path(directory) / "state",
                "same-selection-counter",
                max_model_calls=4,
                max_tool_calls=3,
                runtime=runtime,
            )
            same = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc19-same-selection-counter-b",
                pins=(pin_a,),
                basis="Reset attempt-local cognition without changing selected sources.",
            )
            adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "pc19-same-counter-search-1",
                        (tool_call("tool-call:pc19-same-counter-1", "HarnessExecutionBinding"),),
                    ),
                    transition_turn("pc19-same-counter-reset", same),
                    tool_turn(
                        "pc19-same-counter-search-2",
                        (tool_call("tool-call:pc19-same-counter-2", "Runtime"),),
                    ),
                    needs_input_turn(
                        "pc19-same-counter-close",
                        "Two observation-only turns exhausted the soft effect allowance.",
                    ),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(
                    max_model_calls=4,
                    max_tool_calls=3,
                    max_observation_only_turns=2,
                ),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                working_set_transition_handler=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc19 same-selection counter"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(runtime.workspace_exec_count, 2)
            self.assertEqual(adapter.requests[1].remaining_budget["observationOnlyTurns"], 1)
            self.assertEqual(adapter.requests[2].remaining_budget["observationOnlyTurns"], 1)
            self.assertEqual(adapter.requests[3].remaining_budget["observationOnlyTurns"], 0)
            self.assertEqual(adapter.requests[3].tools, ())
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_selection_change_never_reopens_exhausted_hard_tool_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _source_a,
                _source_b,
                pin_a,
                pin_b,
            ) = self.initialize(
                Path(directory) / "state",
                "hard-budget-selection-change",
                max_model_calls=3,
                max_tool_calls=1,
                runtime=runtime,
            )
            changed = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc19-hard-budget-selection-b",
                pins=(pin_a, pin_b),
                basis="Change selected cognition after the one admitted external Tool effect.",
            )
            adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "pc19-hard-budget-search-1",
                        (tool_call("tool-call:pc19-hard-budget-1", "HarnessExecutionBinding"),),
                    ),
                    transition_turn("pc19-hard-budget-select", changed),
                    tool_turn(
                        "pc19-hard-budget-search-2",
                        (tool_call("tool-call:pc19-hard-budget-2", "Runtime"),),
                    ),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(max_model_calls=3, max_tool_calls=1),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
                working_set_transition_handler=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc19 hard budget selection"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NO_PROGRESS)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(result.tool_calls, 1)
            self.assertEqual(adapter.requests[1].tools, ())
            self.assertEqual(adapter.requests[2].tools, ())
            self.assertEqual(adapter.requests[2].remaining_budget["toolCalls"], 0)
            self.assertEqual(
                continuity.load_current_working_set().pins,
                (pin_a, pin_b),
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()


if __name__ == "__main__":
    unittest.main()

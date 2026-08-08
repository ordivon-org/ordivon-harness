from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentTurnResult,
    ScriptedTurnAdapter,
    static_provider_request_digest,
)
from ordivon_harness.ordivon.run_store_port import HarnessProviderCallRequestMismatch
from ordivon_harness.ordivon.sqlite_agent_bridge import SQLiteHarnessAgentBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.tool_errors import ToolBridgeError, ToolBridgeErrorKind
from ordivon_harness.protocol import HarnessProviderCallStatus
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.working_view import (
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingView,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
    compile_working_view,
)

from tests.test_p0_sqlite_agent_loop import FixedClock, budget, contract


def private_contract(suffix: str):
    return replace(
        contract(suffix),
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=False,
        ),
    )


def candidate_result(suffix: str, summary: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:pc12b-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content=f"candidate:{suffix}",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary=summary,
        ),
        usage={"inputTokens": 11, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"response": f"pc12b:{suffix}"}),
    )


class ReplanAfterFirstConclusionBridge(SQLiteHarnessAgentBridge):
    def __init__(
        self,
        contract,
        run_store: SQLiteHarnessRunContinuityStore,
        *,
        next_pin: HarnessWorkingSetPin,
        lose_second_completion: bool = False,
    ) -> None:
        super().__init__(contract, run_store)
        self.next_pin = next_pin
        self.lose_second_completion = lose_second_completion
        self.validation_count = 0
        self.completion_count = 0
        self.injected_loss = False
        self.replanned: HarnessWorkingSetSpec | None = None

    def validate_conclusion(self, conclusion: AgentRunConclusion) -> None:
        self.validation_count += 1
        if self.validation_count != 1:
            return
        current = self.run_store.load_current_working_set()
        replanned = current.replan("working-attempt:pc12b-b")
        self.run_store.record_working_set(replanned)
        selected = replanned.replace_pin(self.next_pin)
        self.run_store.record_working_set(selected)
        committed = selected.commit("explicit replan selects source B")
        self.run_store.record_working_set(committed)
        self.replanned = committed
        raise ToolBridgeError(
            "explicit caller/domain replan requires another bounded model turn",
            kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
        )

    def complete_provider_call(self, request, result) -> None:
        super().complete_provider_call(request, result)
        self.completion_count += 1
        if (
            self.lose_second_completion
            and self.completion_count == 2
            and not self.injected_loss
        ):
            self.injected_loss = True
            raise RuntimeError(
                "injected P-C1.2b response loss after second durable completion"
            )


class MutatingProjector:
    """Return A, but advance durable head to B before Provider claim."""

    def __init__(
        self,
        store: SQLiteHarnessStore,
        continuity: SQLiteHarnessRunContinuityStore,
        next_pin: HarnessWorkingSetPin,
    ) -> None:
        self.store = store
        self.continuity = continuity
        self.next_pin = next_pin
        self.used = False

    def project(self):
        current = self.continuity.load_current_working_set()
        view = compile_working_view(current, self.store)
        if not self.used:
            self.used = True
            replanned = current.replan("working-attempt:pc12b-race-b")
            self.continuity.record_working_set(replanned)
            selected = replanned.replace_pin(self.next_pin)
            self.continuity.record_working_set(selected)
            self.continuity.record_working_set(
                selected.commit("advance head after stale A projection")
            )
        return view


class StaticEphemeralProjector:
    def __init__(self, sentinel: str) -> None:
        self.view = HarnessWorkingView(
            attempt_id="working-attempt:pc12b-ephemeral",
            working_set_digest=canonical_digest(
                {"workingSet": "pc12b-ephemeral"}
            ),
            messages=(
                {"role": "user", "content": sentinel},
            ),
        )

    def project(self) -> HarnessWorkingView:
        return self.view


class MultiTurnWorkingViewProjectionTests(unittest.TestCase):
    @staticmethod
    def prepare_sources(
        continuity: SQLiteHarnessRunContinuityStore,
    ) -> tuple[
        HarnessWorkingSetSpec,
        HarnessWorkingSetPin,
        HarnessWorkingViewSource,
        HarnessWorkingViewSource,
    ]:
        source_a = HarnessWorkingViewSource(
            logical_ref="source://pc12b/current",
            logical_generation="source:a",
            messages=(
                {"role": "system", "content": "Use only projection A."},
                {"role": "user", "content": "PROJECTION_A_ONLY"},
            ),
        )
        source_b = HarnessWorkingViewSource(
            logical_ref="source://pc12b/current",
            logical_generation="source:b",
            messages=(
                {"role": "system", "content": "Use only projection B."},
                {"role": "user", "content": "PROJECTION_B_ONLY"},
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
            slot="primary",
            logical_ref=source_b.logical_ref,
            logical_generation=source_b.logical_generation,
            resolved_digest=stored_b.digest,
        )
        initial = HarnessWorkingSetSpec.initial(
            "working-attempt:pc12b-a",
            pins=(pin_a,),
        )
        continuity.record_working_set(initial)
        committed = initial.commit("projection A is sufficient for attempt A")
        continuity.record_working_set(committed)
        return committed, pin_b, source_a, source_b

    def test_mature_loop_projects_a_then_b_without_replaying_canonical_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract("pc12b-multiturn")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                committed_a, pin_b, source_a, source_b = self.prepare_sources(
                    continuity
                )
                view_a = compile_working_view(committed_a, store)
                first = candidate_result("first", "first candidate triggers replan")
                second = candidate_result("second", "second candidate is accepted")
                adapter = ScriptedTurnAdapter((first, second))
                bridge = ReplanAfterFirstConclusionBridge(
                    run_contract,
                    continuity,
                    next_pin=pin_b,
                )
                projector = WorkingSetViewProjector(store, continuity)
                loop = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=projector,
                )
                result = loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "CANONICAL_HISTORY_ROOT"},
                    ),
                )

                self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
                self.assertEqual(result.model_calls, 2)
                self.assertEqual(len(adapter.requests), 2)
                self.assertEqual(adapter.requests[0].messages, source_a.messages)
                self.assertEqual(adapter.requests[0].context_digest, view_a.digest)
                self.assertIsNotNone(bridge.replanned)
                assert bridge.replanned is not None
                view_b = compile_working_view(bridge.replanned, store)
                self.assertEqual(adapter.requests[1].messages, source_b.messages)
                self.assertEqual(adapter.requests[1].context_digest, view_b.digest)
                self.assertNotIn("PROJECTION_A_ONLY", str(adapter.requests[1].messages))
                self.assertNotIn("CANONICAL_HISTORY_ROOT", str(adapter.requests[1].messages))
                self.assertNotIn("conclusion gate rejected", str(adapter.requests[1].messages))

                # Canonical execution history remains complete even though turn 2
                # receives only Working View B.
                self.assertIn("CANONICAL_HISTORY_ROOT", str(result.messages))
                self.assertIn(first.content, str(result.messages))
                self.assertIn("conclusion gate rejected", str(result.messages))
                self.assertIn(second.content, str(result.messages))

                working_events = [
                    event
                    for event in store.list_run_events(run_contract.harness_run_id)
                    if event.event_kind == "harness.working-set-recorded"
                ]
                self.assertEqual(len(working_events), 5)
                projected_events = [
                    event
                    for event in result.trace.events
                    if event.kind == "model_view_projected"
                ]
                self.assertEqual(len(projected_events), 2)
                self.assertEqual(
                    projected_events[0].payload["workingSetDigest"], committed_a.digest
                )
                self.assertEqual(
                    projected_events[1].payload["workingSetDigest"], bridge.replanned.digest
                )
                self.assertTrue(continuity.doctor()["healthy"])

    def test_metadata_only_ephemeral_projection_does_not_persist_view_content(self) -> None:
        sentinel = "PRIVATE-PC12B-EPHEMERAL-PROJECTION-SENTINEL"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = contract("pc12b-metadata-projection")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=clock
            )
            adapter = ScriptedTurnAdapter(
                (candidate_result("metadata-projection", "ephemeral projection completed"),)
            )
            loop = OrdivonAgentLoop(
                adapter,
                SQLiteHarnessAgentBridge(run_contract, continuity),
                budget=budget(),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=StaticEphemeralProjector(sentinel),
            )
            result = loop.run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical metadata root"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(adapter.requests[0].messages[0]["content"], sentinel)
            retained = continuity.load_current_provider_call()
            self.assertIsNone(retained.request)
            self.assertIsNone(retained.result)
            self.assertFalse(retained.state.messages_retained)
            store.close()

            hits = [
                str(path.relative_to(root))
                for path in root.rglob("*")
                if path.is_file() and sentinel.encode() in path.read_bytes()
            ]
            self.assertEqual(hits, [])

    def test_provider_claim_rejects_view_that_became_stale_after_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract("pc12b-stale-view")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                _, pin_b, _, _ = self.prepare_sources(continuity)
                adapter = ScriptedTurnAdapter(
                    (candidate_result("stale", "must never physically dispatch"),)
                )
                loop = OrdivonAgentLoop(
                    adapter,
                    SQLiteHarnessAgentBridge(run_contract, continuity),
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=MutatingProjector(
                        store, continuity, pin_b
                    ),
                )
                with self.assertRaisesRegex(
                    HarnessProviderCallRequestMismatch,
                    "current committed Working View",
                ):
                    loop.run(
                        harness_run_id=run_contract.harness_run_id,
                        assignment_id=continuity.binding.assignment_id,
                        context_digest=run_contract.context_refs[0].digest,
                        initial_messages=(
                            {"role": "user", "content": "canonical root"},
                        ),
                    )
                self.assertEqual(adapter.requests, [])
                self.assertTrue(continuity.load_current_working_set().committed)
                self.assertTrue(continuity.doctor()["healthy"])

    def test_second_turn_response_loss_replays_b_without_third_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract("pc12b-response-loss")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=clock
            )
            _, pin_b, _, source_b = self.prepare_sources(continuity)
            first = candidate_result("loss-first", "first candidate triggers replan")
            second = candidate_result("loss-second", "second result is durable")
            adapter = ScriptedTurnAdapter((first, second))
            bridge = ReplanAfterFirstConclusionBridge(
                run_contract,
                continuity,
                next_pin=pin_b,
                lose_second_completion=True,
            )
            loop = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=budget(),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
            )
            with self.assertRaisesRegex(RuntimeError, "second durable completion"):
                loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical response-loss root"},
                    ),
                )
            self.assertEqual(len(adapter.requests), 2)
            second_request = adapter.requests[1]
            self.assertEqual(second_request.messages, source_b.messages)
            retained = continuity.load_current_provider_call()
            self.assertEqual(retained.record.status, HarnessProviderCallStatus.COMPLETED)
            self.assertEqual(retained.record.turn_sequence, 2)
            self.assertEqual(retained.result, second)
            self.assertEqual(retained.request, second_request)
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_provider_call()
                self.assertEqual(retained.record.status, HarnessProviderCallStatus.COMPLETED)
                self.assertEqual(retained.record.turn_sequence, 2)
                self.assertEqual(retained.result, second)
                self.assertEqual(retained.request, second_request)
                reopened.bind_state(retained.state)
                replay_bridge = SQLiteHarnessAgentBridge(run_contract, reopened)
                replay_bridge.configure_provider_call(
                    adapter_id=ScriptedTurnAdapter.adapter_id,
                    requested_model_id=ScriptedTurnAdapter.model_id,
                )
                replayed = replay_bridge.begin_provider_call(
                    second_request,
                    provider_request_digest=static_provider_request_digest(
                        ScriptedTurnAdapter((second,)), second_request
                    ),
                )
                self.assertEqual(replayed, second)
                # The two original physical dispatches are the whole trajectory;
                # replay reads the durable turn-2 result and creates no third call.
                self.assertEqual(len(adapter.requests), 2)
                self.assertTrue(reopened.doctor()["healthy"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_bytes, canonical_digest

from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentTurnCapabilities,
    AgentToolCall,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.run_store_port import HarnessProviderCallRequestMismatch
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.working_view import (
    WORKING_SET_HISTORY_CONTROL_NAME,
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
    compile_working_view,
)

from tests.test_p0_sqlite_runtime_bridge import FakeRuntime, FixedClock, execution_binding
from tests.test_pc14_candidate_discovery_overlay import transition_turn
from tests.test_pc15_epistemic_control import (
    CaptureTransport,
    needs_input_turn,
    private_contract,
    run_budget,
)


def history_turn(suffix: str, *, limit: int = 8, before_sequence: int | None = None) -> AgentTurnResult:
    arguments = {"limit": limit}
    if before_sequence is not None:
        arguments["before_sequence"] = before_sequence
    return AgentTurnResult(
        model_call_id=f"model-call:pc18-{suffix}-history",
        model_id=ScriptedTurnAdapter.model_id,
        content="I need to inspect my own prior selected cognition identities.",
        tool_calls=(
            AgentToolCall(
                tool_call_id=f"tool-call:pc18-{suffix}-history",
                name=WORKING_SET_HISTORY_CONTROL_NAME,
                arguments=arguments,
            ),
        ),
        conclusion=None,
        usage={"inputTokens": 11, "outputTokens": 7},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"pc18": suffix, "kind": "history"}),
    )


def history_provider_response() -> bytes:
    return canonical_bytes(
        {
            "id": "provider-call:pc18-history",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "I will inspect only my prior selected source identities.",
                        "tool_calls": [
                            {
                                "id": "call:pc18-history",
                                "type": "function",
                                "function": {
                                    "name": WORKING_SET_HISTORY_CONTROL_NAME,
                                    "arguments": '{"limit":4}',
                                },
                            }
                        ],
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


class RecallAdapter(ScriptedTurnAdapter):
    def __init__(self, *, primary_pin: HarnessWorkingSetPin, knowledge_ref: str) -> None:
        self.primary_pin = primary_pin
        self.knowledge_ref = knowledge_ref
        self.requests = []
        self.recalled_pin: HarnessWorkingSetPin | None = None

    def invoke(self, request):
        self.requests.append(request)
        if request.sequence == 1:
            return history_turn("recall")
        if request.sequence == 2:
            observation = request.messages[-1].get("observation")
            if not isinstance(observation, dict):
                raise ValueError("history observation is missing")
            content = observation.get("content")
            if not isinstance(content, dict):
                raise ValueError("history observation content is missing")
            selections = content.get("selections")
            if not isinstance(selections, list):
                raise ValueError("history selections are missing")
            for selection in selections:
                if not isinstance(selection, dict):
                    continue
                pins = selection.get("pins")
                if not isinstance(pins, list):
                    continue
                for raw_pin in pins:
                    if not isinstance(raw_pin, dict):
                        continue
                    pin = HarnessWorkingSetPin.from_dict(raw_pin)
                    if pin.logical_ref == self.knowledge_ref:
                        self.recalled_pin = pin
                        break
                if self.recalled_pin is not None:
                    break
            if self.recalled_pin is None:
                raise ValueError("historical cognition catalog did not expose the selected K pin")
            proposal = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc18-recalled",
                pins=(self.primary_pin, self.recalled_pin),
                basis="I explicitly recall the previously selected exact K source.",
            )
            return transition_turn("pc18-recall-select", proposal)
        if request.sequence == 3:
            return needs_input_turn(
                "pc18-recall-final",
                "Pause after verifying recalled source content.",
            )
        raise AssertionError(f"unexpected sequence: {request.sequence}")


class ForgedHistoryReader:
    def __init__(self, forged_pin: HarnessWorkingSetPin) -> None:
        self.forged_pin = forged_pin

    def inspect_working_set_history(self, *, limit: int, before_sequence: int | None = None):
        del limit, before_sequence
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-working-set-history",
            "currentAttemptId": "forged-current",
            "currentWorkingSetDigest": "sha256:" + "0" * 64,
            "currentWorkingSetEventSequence": 1,
            "selections": [
                {
                    "eventSequence": 1,
                    "attemptId": "forged-attempt",
                    "workingSetDigest": "sha256:" + "1" * 64,
                    "pins": [self.forged_pin.to_dict()],
                }
            ],
            "nextBeforeSequence": None,
        }


class HistoricalCognitionRecallTests(unittest.TestCase):
    @staticmethod
    def seed_history(
        store: SQLiteHarnessStore,
        continuity: SQLiteHarnessRunContinuityStore,
    ) -> tuple[
        HarnessWorkingViewSource,
        HarnessWorkingViewSource,
        HarnessWorkingViewSource,
        HarnessWorkingSetPin,
        HarnessWorkingSetPin,
        HarnessWorkingSetPin,
    ]:
        source_a = HarnessWorkingViewSource(
            logical_ref="source://pc18/current-task",
            logical_generation="generation:a",
            messages=({"role": "user", "content": "PC18_CURRENT_TASK_NEEDS_PRIOR_K"},),
        )
        source_k = HarnessWorkingViewSource(
            logical_ref="knowledge://pc18/authoritative-launch-code",
            logical_generation="generation:k1",
            messages=({"role": "user", "content": "PC18_RECALLED_K_BLUE_17"},),
        )
        source_u = HarnessWorkingViewSource(
            logical_ref="knowledge://pc18/materialized-never-selected",
            logical_generation="generation:u1",
            messages=({"role": "user", "content": "PC18_UNSELECTED_U"},),
        )
        stored_a = continuity.store_working_view_source(source_a)
        stored_k = continuity.store_working_view_source(source_k)
        stored_u = continuity.store_working_view_source(source_u)
        pin_a = HarnessWorkingSetPin(
            slot="primary",
            logical_ref=source_a.logical_ref,
            logical_generation=source_a.logical_generation,
            resolved_digest=stored_a.digest,
        )
        pin_k = HarnessWorkingSetPin(
            slot="retained-knowledge",
            logical_ref=source_k.logical_ref,
            logical_generation=source_k.logical_generation,
            resolved_digest=stored_k.digest,
        )
        pin_u = HarnessWorkingSetPin(
            slot="never-selected",
            logical_ref=source_u.logical_ref,
            logical_generation=source_u.logical_generation,
            resolved_digest=stored_u.digest,
        )
        initial = HarnessWorkingSetSpec.initial("working-attempt:pc18-a", pins=(pin_a,))
        continuity.record_working_set(initial)
        continuity.record_working_set(initial.commit("seed A"))

        current = continuity.load_current_working_set()
        proposal_b = AgentWorkingSetTransitionProposal(
            next_attempt_id="working-attempt:pc18-b",
            pins=(pin_a, pin_k),
            basis="Agent explicitly retained K.",
        )
        continuity.apply_working_set_transition(
            proposal_b,
            source_working_set_digest=current.digest,
            source_model_view_digest=compile_working_view(current, store).digest,
        )
        current = continuity.load_current_working_set()
        proposal_c = AgentWorkingSetTransitionProposal(
            next_attempt_id="working-attempt:pc18-c",
            pins=(pin_a,),
            basis="Agent explicitly dropped K from current cognition.",
        )
        continuity.apply_working_set_transition(
            proposal_c,
            source_working_set_digest=current.digest,
            source_model_view_digest=compile_working_view(current, store).digest,
        )
        return source_a, source_k, source_u, pin_a, pin_k, pin_u

    def test_deepseek_history_control_is_separate_from_runtime_tool_surface(self) -> None:
        request = AgentTurnRequest(
            harness_run_id="harness-run:pc18-deepseek",
            turn_id="turn:pc18-deepseek:1",
            sequence=1,
            assignment_id="assignment:pc18-deepseek",
            context_digest=canonical_digest({"pc18": "context"}),
            tool_catalog_digest=canonical_digest({"pc18": "no-runtime-tools"}),
            messages=(
                {
                    "role": "user",
                    "content": "The current view is insufficient; inspect prior selected cognition.",
                },
            ),
            tools=(),
            capabilities=AgentTurnCapabilities(working_set_history=True),
            remaining_budget=run_budget(
                max_model_calls=2,
                max_tool_calls=0,
            ).remaining(
                model_calls=0,
                tool_calls=0,
                observation_bytes=0,
                elapsed_ms=0,
            ),
        )
        transport = CaptureTransport(history_provider_response())
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="pc18-test-secret"),
            transport=transport,
        )
        result = adapter.invoke(request)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(
            result.tool_calls[0].name,
            WORKING_SET_HISTORY_CONTROL_NAME,
        )
        self.assertIsNone(result.tool_calls[0].argument_error)
        body = transport.requests[0]
        tools = body.get("tools")
        self.assertIsInstance(tools, list)
        names = [item["function"]["name"] for item in tools]
        self.assertIn(WORKING_SET_HISTORY_CONTROL_NAME, names)
        self.assertNotIn("propose_working_set_transition", names)
        self.assertEqual(body.get("tool_choice"), "required")
        control_text = body["messages"][0]["content"]
        self.assertIn('"admittedRuntimeTools":[]', control_text)
        self.assertIn('"toolCalls":0', control_text)

        disabled_request = replace(
            request, capabilities=AgentTurnCapabilities()
        )
        disabled = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="pc18-test-secret"),
            transport=CaptureTransport(history_provider_response()),
        )
        with self.assertRaisesRegex(
            ValueError,
            "unavailable Working Set history control",
        ):
            disabled.invoke(disabled_request)

    def test_agent_recalls_prior_selected_pin_without_runtime_effect_or_tool_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc18-recall",
                max_model_calls=4,
                max_tool_calls=0,
            )
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
                source_a, source_k, source_u, pin_a, pin_k, pin_u = self.seed_history(
                    store, continuity
                )
                runtime = FakeRuntime("direct")
                bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(run_contract, continuity),
                    runtime,
                )
                adapter = RecallAdapter(
                    primary_pin=pin_a,
                    knowledge_ref=source_k.logical_ref,
                )
                result = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=run_budget(max_model_calls=4, max_tool_calls=0),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(store, continuity),
                    working_set_transition_handler=continuity,
                    working_set_history_reader=continuity,
                ).run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical pc18 recall root"},
                    ),
                )
                self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(result.tool_calls, 0)
                self.assertEqual(runtime.workspace_exec_count, 0)
                self.assertEqual(adapter.requests[0].tools, ())
                self.assertIsNotNone(adapter.recalled_pin)
                self.assertEqual(adapter.recalled_pin, pin_k)

                history_text = str(adapter.requests[1].messages[-1])
                self.assertIn(pin_k.resolved_digest, history_text)
                self.assertNotIn(pin_u.resolved_digest, history_text)
                self.assertNotIn(source_u.messages[0]["content"], history_text)
                # History inspection exposes exact identities, not historical source bytes.
                self.assertNotIn(source_k.messages[0]["content"], history_text)
                # After Agent selection, source content becomes visible through the
                # ordinary successor WorkingView and the transient history exchange expires.
                self.assertEqual(
                    adapter.requests[2].messages,
                    source_a.messages + source_k.messages,
                )
                self.assertEqual(
                    continuity.load_current_working_set().pins,
                    (pin_a, pin_k),
                )
                observed = [
                    event
                    for event in result.trace.events
                    if event.kind == "working_set_history_observed"
                ]
                self.assertEqual(len(observed), 1)
                self.assertIs(observed[0].payload["physicalDispatch"], False)
                self.assertTrue(continuity.doctor()["healthy"])

    def test_history_query_survives_clean_pause_and_is_reconstructed_from_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc18-pause",
                max_model_calls=4,
                max_tool_calls=0,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            source_a, _source_k, _source_u, _pin_a, pin_k, _pin_u = self.seed_history(
                store, continuity
            )
            runtime = FakeRuntime("direct")
            bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                runtime,
            )
            first_adapter = ScriptedTurnAdapter(
                (
                    history_turn("pause", limit=1),
                    needs_input_turn("pc18-pause-stop", "Pause after history inspection."),
                )
            )
            first = OrdivonAgentLoop(
                first_adapter,
                bridge,
                budget=run_budget(max_model_calls=4, max_tool_calls=0),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
                working_set_history_reader=continuity,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc18 pause root"},
                ),
            )
            self.assertEqual(first.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(first.tool_calls, 0)
            self.assertIn(pin_k.resolved_digest, str(first_adapter.requests[1].messages))
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
                            "pc18-pause-resumed",
                            "Inspect restored historical cognition transcript.",
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
                    budget=run_budget(max_model_calls=4, max_tool_calls=0),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(reopened_store, reopened),
                    working_set_history_reader=reopened,
                ).resume(
                    retained=retained,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                )
                self.assertEqual(second.stop_code, RunStopCode.NEEDS_INPUT)
                self.assertEqual(second.tool_calls, 0)
                resumed_messages = second_adapter.requests[0].messages
                self.assertEqual(resumed_messages[:1], source_a.messages)
                self.assertIn(WORKING_SET_HISTORY_CONTROL_NAME, str(resumed_messages))
                self.assertIn(pin_k.resolved_digest, str(resumed_messages))
                self.assertTrue(reopened.doctor()["healthy"])

    def test_forged_history_reader_is_rejected_before_second_provider_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc18-forged",
                max_model_calls=3,
                max_tool_calls=0,
            )
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
                _source_a, _source_k, _source_u, _pin_a, _pin_k, pin_u = self.seed_history(
                    store, continuity
                )
                adapter = ScriptedTurnAdapter(
                    (
                        history_turn("forged"),
                        needs_input_turn("pc18-forged-should-not-run", "must not dispatch"),
                    )
                )
                runtime = FakeRuntime("direct")
                bridge = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(run_contract, continuity),
                    runtime,
                )
                with self.assertRaisesRegex(
                    HarnessProviderCallRequestMismatch,
                    "differs from deterministic Journal projection",
                ):
                    OrdivonAgentLoop(
                        adapter,
                        bridge,
                        budget=run_budget(max_model_calls=3, max_tool_calls=0),
                        clock_ms=clock,
                        monotonic_ms=clock,
                        working_view_projector=WorkingSetViewProjector(store, continuity),
                        working_set_history_reader=ForgedHistoryReader(pin_u),
                    ).run(
                        harness_run_id=run_contract.harness_run_id,
                        assignment_id=continuity.binding.assignment_id,
                        context_digest=run_contract.context_refs[0].digest,
                        initial_messages=(
                            {"role": "user", "content": "canonical pc18 forged root"},
                        ),
                    )
                self.assertEqual(len(adapter.requests), 1)
                self.assertEqual(runtime.workspace_exec_count, 0)


    def test_history_catalog_paginates_committed_cognition_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract(
                "pc18-pagination",
                max_model_calls=1,
                max_tool_calls=0,
            )
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store,
                    run_contract,
                    clock_ms=clock,
                )
                _source_a, _source_k, _source_u, _pin_a, pin_k, pin_u = (
                    self.seed_history(store, continuity)
                )
                page_one = continuity.inspect_working_set_history(limit=1)
                selections_one = page_one["selections"]
                self.assertIsInstance(selections_one, list)
                self.assertEqual(len(selections_one), 1)
                self.assertIn(pin_k.resolved_digest, str(selections_one[0]))
                self.assertNotIn(pin_u.resolved_digest, str(page_one))
                cursor = page_one["nextBeforeSequence"]
                self.assertIsInstance(cursor, int)

                page_two = continuity.inspect_working_set_history(
                    limit=1,
                    before_sequence=cursor,
                )
                selections_two = page_two["selections"]
                self.assertIsInstance(selections_two, list)
                self.assertEqual(len(selections_two), 1)
                self.assertNotIn(pin_k.resolved_digest, str(selections_two[0]))
                self.assertNotIn(pin_u.resolved_digest, str(page_two))
                self.assertIsNone(page_two["nextBeforeSequence"])

    def test_history_control_requires_tool_content_authority_for_provider_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = replace(
                private_contract(
                    "pc18-history-privacy",
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
                self.seed_history(store, continuity)
                with self.assertRaisesRegex(
                    ValueError,
                    "requires Tool-content authority",
                ):
                    continuity.inspect_working_set_history(limit=4)


if __name__ == "__main__":
    unittest.main()

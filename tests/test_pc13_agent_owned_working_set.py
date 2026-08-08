from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest

from anc_canonical import canonical_bytes, canonical_digest, loads_strict

from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_agent_bridge import SQLiteHarnessAgentBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.store import HarnessEventWrite
from ordivon_harness.working_view import (
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
    compile_working_view,
)

from tests.test_p0_sqlite_agent_loop import FixedClock
from tests.test_pc12b_multiturn_projection import private_contract


def cognition_budget() -> RunBudget:
    return RunBudget(
        max_model_calls=2,
        max_tool_calls=0,
        max_observation_bytes=16_384,
        max_wall_time_ms=10_000,
        max_total_tokens=10_000,
        max_model_retries=1,
    )


def cognition_contract(suffix: str):
    current = private_contract(suffix)
    claimed = dict(current.budget)
    claimed["maxToolCalls"] = 0
    return replace(current, budget=claimed)


class RecordingTransport:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.body: bytes | None = None

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        self.body = body
        return self.response


class SequenceTransport:
    def __init__(self, responses: tuple[bytes, ...]) -> None:
        self.responses = list(responses)
        self.bodies: list[bytes] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        self.bodies.append(body)
        if not self.responses:
            raise AssertionError("unexpected DeepSeek dispatch")
        return self.responses.pop(0)


class ReplayBoundaryBridge(SQLiteHarnessAgentBridge):
    """Simulate losing the in-process return after durable Provider completion."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.injected = False

    def complete_provider_call(self, request, result) -> None:
        super().complete_provider_call(request, result)
        if not self.injected:
            self.injected = True
            raise RuntimeError(
                "P-C1.3 boundary unavailable after durable Provider completion"
            )


def deepseek_transition_response(proposal: AgentWorkingSetTransitionProposal) -> bytes:
    arguments = {
        "next_attempt_id": proposal.next_attempt_id,
        "pins": [
            {
                "slot": pin.slot,
                "logical_ref": pin.logical_ref,
                "logical_generation": pin.logical_generation,
                "resolved_digest": pin.resolved_digest,
            }
            for pin in proposal.pins
        ],
        "basis": proposal.basis,
    }
    return canonical_bytes(
        {
            "id": "provider-call:pc13-transition",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "I want the successor view.",
                        "tool_calls": [
                            {
                                "id": "control-call:pc13-transition",
                                "type": "function",
                                "function": {
                                    "name": "propose_working_set_transition",
                                    "arguments": json.dumps(arguments, separators=(",", ":")),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
    )


def deepseek_conclusion_response() -> bytes:
    return canonical_bytes(
        {
            "id": "provider-call:pc13-conclusion",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "B is sufficient.",
                        "tool_calls": [
                            {
                                "id": "control-call:pc13-conclusion",
                                "type": "function",
                                "function": {
                                    "name": "submit_run_conclusion",
                                    "arguments": json.dumps(
                                        {
                                            "status": "candidate_completed",
                                            "summary": "successor B was sufficient",
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
            "usage": {"prompt_tokens": 18, "completion_tokens": 8, "total_tokens": 26},
        }
    )


def completed_result(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:pc13-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content="completed after cognition transition",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="successor Working View was sufficient",
        ),
        usage={"inputTokens": 9, "outputTokens": 3},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"response": f"pc13:{suffix}"}),
    )


def transition_result(proposal: AgentWorkingSetTransitionProposal) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:pc13-transition",
        model_id=ScriptedTurnAdapter.model_id,
        content="replace my Working View with the exact successor",
        tool_calls=(),
        conclusion=None,
        usage={"inputTokens": 12, "outputTokens": 6},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"response": "pc13-transition"}),
        working_set_transition=proposal,
    )


class AgentOwnedWorkingSetTests(unittest.TestCase):
    @staticmethod
    def prepare(
        continuity: SQLiteHarnessRunContinuityStore,
    ) -> tuple[
        HarnessWorkingSetSpec,
        HarnessWorkingSetPin,
        HarnessWorkingSetPin,
        HarnessWorkingViewSource,
        HarnessWorkingViewSource,
        HarnessWorkingViewSource,
    ]:
        source_a = HarnessWorkingViewSource(
            logical_ref="source://pc13/current",
            logical_generation="generation:a",
            messages=(
                {
                    "role": "user",
                    "content": "View A. Exact successor source identities are already known.",
                },
            ),
        )
        source_b = HarnessWorkingViewSource(
            logical_ref="source://pc13/current",
            logical_generation="generation:b",
            messages=({"role": "user", "content": "VIEW_B_SELECTED_BY_AGENT"},),
        )
        source_c = HarnessWorkingViewSource(
            logical_ref="source://pc13/current",
            logical_generation="generation:c",
            messages=({"role": "user", "content": "VIEW_C_COMPETING_AGENT"},),
        )
        stored_a = continuity.store_working_view_source(source_a)
        stored_b = continuity.store_working_view_source(source_b)
        stored_c = continuity.store_working_view_source(source_c)
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
        pin_c = HarnessWorkingSetPin(
            slot="primary",
            logical_ref=source_c.logical_ref,
            logical_generation=source_c.logical_generation,
            resolved_digest=stored_c.digest,
        )
        initial = HarnessWorkingSetSpec.initial(
            "working-attempt:pc13-a",
            pins=(pin_a,),
        )
        continuity.record_working_set(initial)
        committed_a = initial.commit("initial caller-selected view")
        continuity.record_working_set(committed_a)
        return committed_a, pin_b, pin_c, source_a, source_b, source_c

    def test_deepseek_control_tool_normalizes_to_cognition_not_runtime_tool(self) -> None:
        pin = HarnessWorkingSetPin(
            slot="primary",
            logical_ref="source://pc13/provider",
            logical_generation="generation:b",
            resolved_digest="sha256:" + "b" * 64,
        )
        proposal = AgentWorkingSetTransitionProposal(
            next_attempt_id="working-attempt:pc13-provider-b",
            pins=(pin,),
            basis="the successor source is the exact context I need next",
        )
        transport = RecordingTransport(deepseek_transition_response(proposal))
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=transport,
            working_set_transitions=True,
        )
        request = AgentTurnRequest(
            harness_run_id="harness-run:pc13-provider",
            turn_id="turn:pc13-provider:1",
            sequence=1,
            assignment_id="assignment:pc13-provider",
            context_digest="sha256:" + "a" * 64,
            tool_catalog_digest="sha256:" + "c" * 64,
            messages=({"role": "user", "content": "choose your next view"},),
            tools=(),
            remaining_budget={"modelCalls": 2, "toolCalls": 0, "totalTokens": 4096},
        )
        result = adapter.invoke(request)

        self.assertEqual(result.working_set_transition, proposal)
        self.assertEqual(result.tool_calls, ())
        self.assertIsNone(result.conclusion)
        self.assertEqual(AgentTurnResult.from_dict(result.to_dict()), result)
        assert transport.body is not None
        body = loads_strict(transport.body)
        assert isinstance(body, dict)
        tools = body["tools"]
        assert isinstance(tools, list)
        names = [
            item["function"]["name"]
            for item in tools
            if isinstance(item, dict) and isinstance(item.get("function"), dict)
        ]
        self.assertIn("propose_working_set_transition", names)
        self.assertIn("submit_run_conclusion", names)

    def test_deepseek_wire_transition_drives_mature_loop_to_successor_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = replace(
                cognition_contract("pc13-deepseek-loop"),
                provider_id="provider:deepseek",
                adapter_id=DeepSeekTurnAdapter.adapter_id,
                requested_model_id="deepseek-v4-flash",
            )
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                _, pin_b, _, source_a, source_b, _ = self.prepare(continuity)
                proposal = AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc13-deepseek-b",
                    pins=(pin_b,),
                    basis="Provider Agent selected exact successor B",
                )
                transport = SequenceTransport(
                    (
                        deepseek_transition_response(proposal),
                        deepseek_conclusion_response(),
                    )
                )
                adapter = DeepSeekTurnAdapter(
                    DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
                    transport=transport,
                    working_set_transitions=True,
                )
                loop = OrdivonAgentLoop(
                    adapter,
                    SQLiteHarnessAgentBridge(run_contract, continuity),
                    budget=cognition_budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(store, continuity),
                    working_set_transition_handler=continuity,
                )
                result = loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical deepseek root"},
                    ),
                )

                self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
                self.assertEqual(run_contract.budget["maxToolCalls"], 0)
                self.assertEqual(result.tool_calls, 0)
                self.assertEqual(len(transport.bodies), 2)
                first_body = loads_strict(transport.bodies[0])
                second_body = loads_strict(transport.bodies[1])
                assert isinstance(first_body, dict) and isinstance(second_body, dict)
                first_messages = first_body["messages"]
                second_messages = second_body["messages"]
                self.assertEqual(first_messages[0]["role"], "system")
                self.assertEqual(second_messages[0]["role"], "system")
                self.assertIn('"admittedRuntimeTools":[]', first_messages[0]["content"])
                self.assertIn('"toolCalls":0', first_messages[0]["content"])
                self.assertEqual(first_messages[1:], list(source_a.messages))
                self.assertEqual(second_messages[1:], list(source_b.messages))
                self.assertNotIn("View A", str(second_messages[1:]))
                current = continuity.load_current_working_set()
                self.assertEqual(current.attempt_id, proposal.next_attempt_id)
                self.assertEqual(current.pins, proposal.pins)
                self.assertTrue(current.committed)
                self.assertTrue(continuity.doctor()["healthy"])

    def test_mature_loop_applies_agent_proposal_and_next_turn_sees_b(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = cognition_contract("pc13-agent-transition")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                committed_a, pin_b, _, source_a, source_b, _ = self.prepare(
                    continuity
                )
                proposal = AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc13-b",
                    pins=(pin_b,),
                    basis="Agent chose the exact successor B source",
                )
                adapter = ScriptedTurnAdapter(
                    (transition_result(proposal), completed_result("after-transition"))
                )
                loop = OrdivonAgentLoop(
                    adapter,
                    SQLiteHarnessAgentBridge(run_contract, continuity),
                    budget=cognition_budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(store, continuity),
                    working_set_transition_handler=continuity,
                )
                result = loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical root"},
                    ),
                )

                self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
                self.assertEqual(len(adapter.requests), 2)
                self.assertEqual(adapter.requests[0].messages, source_a.messages)
                self.assertEqual(adapter.requests[1].messages, source_b.messages)
                self.assertNotIn("View A", str(adapter.requests[1].messages))
                current = continuity.load_current_working_set()
                self.assertTrue(current.committed)
                self.assertEqual(current.attempt_id, proposal.next_attempt_id)
                self.assertEqual(current.pins, proposal.pins)
                self.assertEqual(current.commit_basis, proposal.basis)
                self.assertEqual(current.revision, 3)
                self.assertEqual(
                    compile_working_view(committed_a, store).digest,
                    adapter.requests[0].context_digest,
                )
                self.assertEqual(
                    compile_working_view(current, store).digest,
                    adapter.requests[1].context_digest,
                )
                self.assertIn("workingSetTransition", str(result.messages))
                transition_events = [
                    event
                    for event in result.trace.events
                    if event.kind == "working_set_transition_applied"
                ]
                self.assertEqual(len(transition_events), 1)
                self.assertEqual(
                    transition_events[0].payload["proposalDigest"], proposal.digest
                )
                working_events = [
                    event
                    for event in store.list_run_events(run_contract.harness_run_id)
                    if event.event_kind == "harness.working-set-recorded"
                ]
                self.assertEqual(len(working_events), 5)
                successor_events = working_events[-3:]
                self.assertEqual(
                    [event.data["workingSetRevision"] for event in successor_events],
                    [1, 2, 3],
                )
                self.assertTrue(
                    all(
                        event.data.get("transitionProposalDigest") == proposal.digest
                        for event in successor_events
                    )
                )
                self.assertTrue(continuity.doctor()["healthy"])

    def test_provider_completion_replay_applies_agent_transition_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = cognition_contract("pc13-provider-replay")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=clock
            )
            _, pin_b, _, _, source_b, _ = self.prepare(continuity)
            proposal = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc13-provider-replay-b",
                pins=(pin_b,),
                basis="replayed Provider result still selects exact B",
            )
            first_adapter = ScriptedTurnAdapter((transition_result(proposal),))
            first_loop = OrdivonAgentLoop(
                first_adapter,
                ReplayBoundaryBridge(run_contract, continuity),
                budget=cognition_budget(),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=WorkingSetViewProjector(store, continuity),
                working_set_transition_handler=continuity,
            )
            initial_messages = (
                {"role": "user", "content": "canonical provider replay root"},
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "after durable Provider completion",
            ):
                first_loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=initial_messages,
                )
            self.assertEqual(len(first_adapter.requests), 1)
            self.assertEqual(
                continuity.load_current_working_set().attempt_id,
                "working-attempt:pc13-a",
            )
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                second_adapter = ScriptedTurnAdapter(
                    (completed_result("provider-replay-finish"),)
                )
                second_loop = OrdivonAgentLoop(
                    second_adapter,
                    SQLiteHarnessAgentBridge(run_contract, reopened),
                    budget=cognition_budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=WorkingSetViewProjector(
                        reopened_store, reopened
                    ),
                    working_set_transition_handler=reopened,
                )
                result = second_loop.run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=initial_messages,
                )
                self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
                self.assertEqual(result.usage["providerResultsReplayed"], 1)
                self.assertEqual(len(second_adapter.requests), 1)
                self.assertEqual(second_adapter.requests[0].sequence, 2)
                self.assertEqual(second_adapter.requests[0].messages, source_b.messages)
                current = reopened.load_current_working_set()
                self.assertEqual(current.attempt_id, proposal.next_attempt_id)
                self.assertTrue(current.committed)
                self.assertEqual(current.pins, proposal.pins)
                self.assertTrue(reopened.doctor()["healthy"])

    def test_exact_transition_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract("pc13-idempotent")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                committed_a, pin_b, _, _, _, _ = self.prepare(continuity)
                source_view_digest = compile_working_view(committed_a, store).digest
                proposal = AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc13-idempotent-b",
                    pins=(pin_b,),
                    basis="replay must not create another cognition branch",
                )
                first = continuity.apply_working_set_transition(
                    proposal,
                    source_working_set_digest=committed_a.digest,
                    source_model_view_digest=source_view_digest,
                )
                event_count = len(store.list_run_events(run_contract.harness_run_id))

            # A fresh Store/Continuity instance must recognize the exact durable
            # transition as replay rather than inventing another cognition branch.
            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                second = reopened.apply_working_set_transition(
                    proposal,
                    source_working_set_digest=committed_a.digest,
                    source_model_view_digest=source_view_digest,
                )
                self.assertEqual(second, first)
                self.assertEqual(
                    len(reopened_store.list_run_events(run_contract.harness_run_id)),
                    event_count,
                )
                self.assertEqual(reopened.load_current_working_set(), first)
                self.assertTrue(reopened.doctor()["healthy"])

    def test_continuity_doctor_rejects_forged_transition_proposal_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract("pc13-doctor")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                committed_a, pin_b, _, _, _, _ = self.prepare(continuity)
                source_view_digest = compile_working_view(committed_a, store).digest
                good = AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc13-doctor-b",
                    pins=(pin_b,),
                    basis="real Agent basis",
                )
                forged = AgentWorkingSetTransitionProposal(
                    next_attempt_id=good.next_attempt_id,
                    pins=good.pins,
                    basis="forged different basis",
                )
                replanned = committed_a.replan(good.next_attempt_id)
                selected = replanned.select_pins(good.pins)
                committed = selected.commit(good.basis)
                chain = (replanned, selected, committed)
                proposal_object = store.put_object(
                    forged.to_dict(), kind="agent-working-set-transition-proposal"
                )
                spec_objects = tuple(
                    store.put_object(spec.to_dict(), kind="harness-working-set-spec")
                    for spec in chain
                )
                source_object = store.inspect_object(pin_b.resolved_digest)
                prior = store.list_run_events(run_contract.harness_run_id)[-1].event_id
                lease = store.acquire_run_lease(
                    run_contract.harness_run_id,
                    owner_id="test:pc13-forged-transition",
                    ttl_ms=5_000,
                    now_ms=clock(),
                )
                writes: list[HarnessEventWrite] = []
                caused_by = prior
                for index, (spec, spec_object) in enumerate(
                    zip(chain, spec_objects, strict=True), start=1
                ):
                    event_id = f"event:pc13-forged-transition:{index}"
                    references = (spec_object, proposal_object)
                    if spec.pins:
                        references += (source_object,)
                    writes.append(
                        HarnessEventWrite(
                            event_id=event_id,
                            event_kind="harness.working-set-recorded",
                            data={
                                "workingSetDigest": spec.digest,
                                "workingSetObjectDigest": spec_object.digest,
                                "attemptId": spec.attempt_id,
                                "workingSetRevision": spec.revision,
                                "committed": spec.committed,
                                "transitionProposalDigest": forged.digest,
                                "transitionProposalObjectDigest": proposal_object.digest,
                                "sourceWorkingViewDigest": source_view_digest,
                            },
                            recorded_at_ms=clock(),
                            caused_by_event_id=caused_by,
                            referenced_objects=references,
                        )
                    )
                    caused_by = event_id
                store.append_events(
                    harness_run_id=run_contract.harness_run_id,
                    events=tuple(writes),
                    expected_revision=lease.run_revision,
                    lease=lease,
                    lease_checked_at_ms=clock(),
                )
                self.assertTrue(store.doctor(full=True)["healthy"])
                with self.assertRaisesRegex(
                    ValueError,
                    "transition commit revision is invalid",
                ):
                    continuity.doctor()

    def test_competing_agent_transitions_from_one_view_have_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_contract("pc13-concurrent")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                committed_a, pin_b, pin_c, _, _, _ = self.prepare(continuity)
                source_view_digest = compile_working_view(committed_a, store).digest

            proposals = (
                AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc13-concurrent-b",
                    pins=(pin_b,),
                    basis="Agent branch B",
                ),
                AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc13-concurrent-c",
                    pins=(pin_c,),
                    basis="Agent branch C",
                ),
            )
            barrier = threading.Barrier(2)

            def writer(proposal: AgentWorkingSetTransitionProposal):
                with SQLiteHarnessStore(root) as thread_store:
                    thread_continuity = SQLiteHarnessRunContinuityStore.open(
                        thread_store,
                        run_contract.harness_run_id,
                        clock_ms=clock,
                    )
                    barrier.wait()
                    try:
                        value = thread_continuity.apply_working_set_transition(
                            proposal,
                            source_working_set_digest=committed_a.digest,
                            source_model_view_digest=source_view_digest,
                        )
                    except Exception as error:  # noqa: BLE001 - competing branch must fail closed somehow.
                        return ("rejected", type(error).__name__, str(error))
                    return ("committed", value.attempt_id, value.digest)

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = tuple(pool.map(writer, proposals))

            committed = [item for item in outcomes if item[0] == "committed"]
            rejected = [item for item in outcomes if item[0] == "rejected"]
            self.assertEqual(len(committed), 1, outcomes)
            self.assertEqual(len(rejected), 1, outcomes)
            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                current = reopened.load_current_working_set()
                self.assertEqual(current.attempt_id, committed[0][1])
                working_events = [
                    event
                    for event in reopened_store.list_run_events(
                        run_contract.harness_run_id
                    )
                    if event.event_kind == "harness.working-set-recorded"
                ]
                # Initial A has two events; exactly one successor transaction adds three.
                self.assertEqual(len(working_events), 5)
                self.assertTrue(reopened.doctor()["healthy"])

    def test_deepseek_rejects_mixed_cognition_and_external_tool_before_effect(self) -> None:
        pin = HarnessWorkingSetPin(
            slot="primary",
            logical_ref="source://pc13/mixed",
            logical_generation="generation:b",
            resolved_digest="sha256:" + "d" * 64,
        )
        proposal = AgentWorkingSetTransitionProposal(
            next_attempt_id="working-attempt:pc13-mixed-b",
            pins=(pin,),
            basis="choose B",
        )
        transition_arguments = {
            "next_attempt_id": proposal.next_attempt_id,
            "pins": [
                {
                    "slot": pin.slot,
                    "logical_ref": pin.logical_ref,
                    "logical_generation": pin.logical_generation,
                    "resolved_digest": pin.resolved_digest,
                }
            ],
            "basis": proposal.basis,
        }
        raw = canonical_bytes(
            {
                "id": "provider-call:pc13-mixed",
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "control:transition",
                                    "type": "function",
                                    "function": {
                                        "name": "propose_working_set_transition",
                                        "arguments": json.dumps(
                                            transition_arguments, separators=(",", ":")
                                        ),
                                    },
                                },
                                {
                                    "id": "tool:external",
                                    "type": "function",
                                    "function": {
                                        "name": "observe_fact",
                                        "arguments": "{}",
                                    },
                                },
                            ],
                        },
                    }
                ],
                "usage": {"total_tokens": 3},
            }
        )
        transport = RecordingTransport(raw)
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=128),
            transport=transport,
            working_set_transitions=True,
        )
        from ordivon_harness.ordivon.model import AgentToolDefinition

        request = AgentTurnRequest(
            harness_run_id="harness-run:pc13-mixed",
            turn_id="turn:pc13-mixed:1",
            sequence=1,
            assignment_id="assignment:pc13-mixed",
            context_digest="sha256:" + "a" * 64,
            tool_catalog_digest="sha256:" + "b" * 64,
            messages=({"role": "user", "content": "choose one action"},),
            tools=(
                AgentToolDefinition(
                    name="observe_fact",
                    description="observe a harmless fact",
                    input_schema={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {},
                    },
                ),
            ),
            remaining_budget={"modelCalls": 1, "toolCalls": 1},
        )
        with self.assertRaisesRegex(
            ValueError,
            "Working Set transition cannot be mixed",
        ):
            adapter.invoke(request)
        # Decode failed before an AgentToolCall reached any ToolBridge.
        self.assertIsNotNone(transport.body)


if __name__ == "__main__":
    unittest.main()

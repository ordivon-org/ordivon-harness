from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from anc_canonical import JsonValue, canonical_digest

from ordivon_harness.agent_tool_observation import HarnessToolObservation
from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.continuity_records import (
    HarnessProviderCallRecordV3,
    HarnessProviderCallStatus,
)
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.run_store_port import HarnessProviderCallRequestMismatch
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.run_state import HarnessRunState
from ordivon_harness.sqlite_store import HarnessObjectMissing, SQLiteHarnessStore
from ordivon_harness.working_view import (
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingView,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
    compile_working_view,
    overlay_working_view,
)

from tests.test_p0_sqlite_runtime_bridge import (
    FakeRuntime,
    FixedClock,
    budget,
    contract,
    execution_binding,
)


def private_discovery_contract(suffix: str):
    return replace(
        contract(suffix),
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=True,
        ),
    )


def discovery_turn(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:pc14-{suffix}-discover",
        model_id=ScriptedTurnAdapter.model_id,
        content="The current view is insufficient; discover candidate sources.",
        tool_calls=(
            AgentToolCall(
                tool_call_id=f"tool-call:pc14-{suffix}-discover",
                name="search_workspace",
                arguments={
                    "query": "CANDIDATE_SOURCE",
                    "relativePath": "candidate-index",
                    "maxMatches": 20,
                },
            ),
        ),
        conclusion=None,
        usage={"inputTokens": 13, "outputTokens": 7},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"pc14": suffix, "turn": "discover"}),
    )


def transition_turn(
    suffix: str, proposal: AgentWorkingSetTransitionProposal
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:pc14-{suffix}-select",
        model_id=ScriptedTurnAdapter.model_id,
        content="Candidate B is the exact successor I choose.",
        tool_calls=(),
        conclusion=None,
        usage={"inputTokens": 17, "outputTokens": 8},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"pc14": suffix, "turn": "select"}),
        working_set_transition=proposal,
    )


def completed_turn(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:pc14-{suffix}-complete",
        model_id=ScriptedTurnAdapter.model_id,
        content="The selected successor view is sufficient.",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Discovery exposed candidates and the Agent selected B.",
        ),
        usage={"inputTokens": 11, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"pc14": suffix, "turn": "complete"}),
    )


class DiscoverMaterializeSelectAdapter(ScriptedTurnAdapter):
    """Deterministic Agent that selects the exact pin it actually sees in turn 2."""

    def __init__(self, suffix: str) -> None:
        self.suffix = suffix
        self.requests = []
        self.proposal: AgentWorkingSetTransitionProposal | None = None

    def invoke(self, request):
        self.requests.append(request)
        if request.sequence == 1:
            return discovery_turn(self.suffix)
        if request.sequence == 2:
            overlay = request.messages[-1]
            observation = overlay.get("observation")
            if not isinstance(observation, dict):
                raise ValueError("materialized candidate overlay observation is invalid")
            content = observation.get("content")
            if not isinstance(content, dict):
                raise ValueError("materialized candidate overlay content is invalid")
            materialization = content.get("candidateMaterialization")
            if not isinstance(materialization, dict):
                raise ValueError("materialized candidate overlay omitted provenance")
            raw_pins = materialization.get("candidatePins")
            if not isinstance(raw_pins, list) or not raw_pins or not isinstance(raw_pins[0], dict):
                raise ValueError("materialized candidate overlay omitted exact pins")
            pin = HarnessWorkingSetPin.from_dict(raw_pins[0])
            self.proposal = AgentWorkingSetTransitionProposal(
                next_attempt_id="working-attempt:pc14-raw-b",
                pins=(pin,),
                basis="I select the first exact pin exposed after domain materialization",
            )
            return transition_turn(self.suffix, self.proposal)
        if request.sequence == 3:
            return completed_turn(self.suffix)
        raise AssertionError(f"unexpected model turn sequence: {request.sequence}")


class CandidateRuntime(FakeRuntime):
    def __init__(self, mode: str, pins: tuple[HarnessWorkingSetPin, ...]) -> None:
        super().__init__(mode)
        self.pins = pins

    def terminal(self) -> dict[str, JsonValue]:
        assert self.client_request_id is not None
        candidate_line = "CANDIDATE_SOURCE " + json.dumps(
            [pin.to_dict() for pin in self.pins],
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "schemaVersion": 1,
            "jobId": self.job_id,
            "clientRequestId": self.client_request_id,
            "status": "succeeded",
            "artifacts": [],
            "stdoutTail": (
                '{"type":"match","data":{"path":{"text":"candidate-index/sources.jsonl"},'
                + '"lines":{"text":'
                + json.dumps(candidate_line + "\n")
                + '},"line_number":1,"absolute_offset":0,'
                + '"submatches":[{"start":0,"end":16}]}}\n'
            ),
            "stderrTail": "",
        }


class RawCandidateRuntime(FakeRuntime):
    def __init__(self, mode: str, sources: tuple[HarnessWorkingViewSource, ...]) -> None:
        super().__init__(mode)
        self.sources = sources

    def terminal(self) -> dict[str, JsonValue]:
        assert self.client_request_id is not None
        raw_candidates = [
            {
                "logicalRef": source.logical_ref,
                "logicalGeneration": source.logical_generation,
                "messages": list(source.messages),
            }
            for source in self.sources
        ]
        candidate_line = "RAW_CANDIDATE_SOURCE " + json.dumps(
            raw_candidates,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "schemaVersion": 1,
            "jobId": self.job_id,
            "clientRequestId": self.client_request_id,
            "status": "succeeded",
            "artifacts": [],
            "stdoutTail": (
                '{"type":"match","data":{"path":{"text":"candidate-index/raw.jsonl"},'
                + '"lines":{"text":'
                + json.dumps(candidate_line + "\n")
                + '},"line_number":1,"absolute_offset":0,'
                + '"submatches":[{"start":0,"end":20}]}}\n'
            ),
            "stderrTail": "",
        }


class MaterializingDiscoveryRuntimeBridge(SQLiteHarnessRuntimeBridge):
    """Domain adapter that turns discovered raw content into exact Harness sources."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.overlay_message: dict[str, JsonValue] | None = None
        self.overlay_working_set_digest: str | None = None
        self.materialized_pins: tuple[HarnessWorkingSetPin, ...] = ()

    def _materialize(self, observation: HarnessToolObservation) -> HarnessToolObservation:
        if observation.status != "observed" or observation.tool_name != "search_workspace":
            return observation
        matches = observation.structured_content.get("matches")
        if not isinstance(matches, list) or not matches:
            return observation
        first = matches[0]
        if not isinstance(first, dict):
            return observation
        line = first.get("lineText")
        prefix = "RAW_CANDIDATE_SOURCE "
        if not isinstance(line, str) or not line.startswith(prefix):
            return observation
        raw_candidates = json.loads(line[len(prefix) :])
        if not isinstance(raw_candidates, list):
            raise TypeError("raw candidate discovery payload must be a list")
        pins: list[HarnessWorkingSetPin] = []
        for index, raw in enumerate(raw_candidates):
            if not isinstance(raw, dict):
                raise TypeError("raw candidate must be an object")
            source = HarnessWorkingViewSource(
                logical_ref=raw["logicalRef"],
                logical_generation=raw["logicalGeneration"],
                messages=tuple(dict(message) for message in raw["messages"]),
            )
            stored = self.run_store.store_working_view_source(source)
            pins.append(
                HarnessWorkingSetPin(
                    slot=f"candidate-{index + 1}",
                    logical_ref=source.logical_ref,
                    logical_generation=source.logical_generation,
                    resolved_digest=stored.digest,
                )
            )
        self.materialized_pins = tuple(pins)
        structured = dict(observation.structured_content)
        structured["candidateMaterialization"] = {
            "sourceObservationDigest": observation.digest,
            "candidatePins": [pin.to_dict() for pin in self.materialized_pins],
        }
        return HarnessToolObservation(
            tool_call_id=observation.tool_call_id,
            tool_name=observation.tool_name,
            status=observation.status,
            structured_content=structured,
            runtime_job_ref=observation.runtime_job_ref,
            artifact_refs=observation.artifact_refs,
            reconciled=observation.reconciled,
        )

    def _record_observation(self, intent, observation, *, previous_receipt=None):
        enriched = self._materialize(observation)
        retained = super()._record_observation(
            intent,
            enriched,
            previous_receipt=previous_receipt,
        )
        if retained.status == "observed" and self.materialized_pins:
            self.overlay_message = retained.to_model_message()
            self.overlay_working_set_digest = (
                self.run_store.load_current_working_set().digest
            )
        return retained


class DiscoveryOverlayRuntimeBridge(SQLiteHarnessRuntimeBridge):
    """Test domain adapter: discovery semantics stay outside generic Harness."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.overlay_message: dict[str, JsonValue] | None = None
        self.overlay_working_set_digest: str | None = None

    def _capture(self, observation):
        if observation.status == "observed" and observation.tool_name == "search_workspace":
            self.overlay_message = observation.to_model_message()
            self.overlay_working_set_digest = self.run_store.load_current_working_set().digest
        return observation

    def execute(self, call, *, step_id):
        return self._capture(super().execute(call, step_id=step_id))

    def execute_with_control(self, call, *, step_id, turn_id, control):
        return self._capture(
            super().execute_with_control(
                call,
                step_id=step_id,
                turn_id=turn_id,
                control=control,
            )
        )


class CandidateOverlayProjector:
    """Append a discovery observation only while its source WorkingSet is current."""

    def __init__(
        self,
        store: SQLiteHarnessStore,
        continuity: SQLiteHarnessRunContinuityStore,
        bridge: DiscoveryOverlayRuntimeBridge,
    ) -> None:
        self.base = WorkingSetViewProjector(store, continuity)
        self.bridge = bridge

    def project(self) -> HarnessWorkingView:
        base = self.base.project()
        if (
            self.bridge.overlay_message is None
            or self.bridge.overlay_working_set_digest != base.working_set_digest
        ):
            return base
        return overlay_working_view(base, (self.bridge.overlay_message,))


class ArbitraryAppendingProjector:
    """Invalid projector that appends content with no bound Tool Observation."""

    def __init__(
        self,
        store: SQLiteHarnessStore,
        continuity: SQLiteHarnessRunContinuityStore,
    ) -> None:
        self.base = WorkingSetViewProjector(store, continuity)

    def project(self) -> HarnessWorkingView:
        return overlay_working_view(
            self.base.project(),
            ({"role": "user", "content": "UNBOUND_OVERLAY_INJECTION"},),
        )


class ReplacingProjector:
    """Invalid projector that drops the committed base WorkingView entirely."""

    def __init__(
        self,
        store: SQLiteHarnessStore,
        continuity: SQLiteHarnessRunContinuityStore,
    ) -> None:
        self.base = WorkingSetViewProjector(store, continuity)

    def project(self) -> HarnessWorkingView:
        base = self.base.project()
        return HarnessWorkingView(
            attempt_id=base.attempt_id,
            working_set_digest=base.working_set_digest,
            messages=({"role": "user", "content": "ILLEGAL_REPLACEMENT_OVERLAY"},),
        )


class CandidateDiscoveryOverlayTests(unittest.TestCase):
    @staticmethod
    def prepare_sources(
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
            logical_ref="source://pc14/current",
            logical_generation="generation:a",
            messages=(
                {
                    "role": "user",
                    "content": "VIEW_A_INSUFFICIENT. Discover another exact source before answering.",
                },
            ),
        )
        source_b = HarnessWorkingViewSource(
            logical_ref="source://pc14/candidate-b",
            logical_generation="generation:b",
            messages=({"role": "user", "content": "VIEW_B_DISCOVERED_AND_SELECTED"},),
        )
        source_c = HarnessWorkingViewSource(
            logical_ref="source://pc14/candidate-c",
            logical_generation="generation:c",
            messages=({"role": "user", "content": "VIEW_C_DISCOVERED_NOT_SELECTED"},),
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
            "working-attempt:pc14-a",
            pins=(pin_a,),
        )
        continuity.record_working_set(initial)
        committed_a = initial.commit("A is the caller-seeded initial view")
        continuity.record_working_set(committed_a)
        return committed_a, pin_b, pin_c, source_a, source_b, source_c

    def run_discovery_case(self, mode: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_discovery_contract(f"pc14-{mode}")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                committed_a, pin_b, pin_c, source_a, source_b, source_c = (
                    self.prepare_sources(continuity)
                )
                self.assertEqual(run_contract.source_refs, ())
                self.assertEqual(committed_a.pins[0].logical_ref, source_a.logical_ref)
                self.assertNotIn(pin_b, committed_a.pins)
                self.assertNotIn(pin_c, committed_a.pins)

                runtime = CandidateRuntime(mode, (pin_b, pin_c))
                bridge = DiscoveryOverlayRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(run_contract, continuity),
                    runtime,
                )
                proposal = AgentWorkingSetTransitionProposal(
                    next_attempt_id=f"working-attempt:pc14-{mode}-b",
                    pins=(pin_b,),
                    basis="discovery exposed B and C; B is the exact successor I choose",
                )
                adapter = ScriptedTurnAdapter(
                    (
                        discovery_turn(mode),
                        transition_turn(mode, proposal),
                        completed_turn(mode),
                    )
                )
                projector = CandidateOverlayProjector(store, continuity, bridge)
                result = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=projector,
                    working_set_transition_handler=continuity,
                ).run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical pc14 root"},
                    ),
                )

                self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
                self.assertEqual(result.model_calls, 3)
                self.assertEqual(result.tool_calls, 1)
                self.assertEqual(runtime.workspace_exec_count, 1)
                self.assertEqual(len(adapter.requests), 3)

                base_a = compile_working_view(committed_a, store)
                self.assertEqual(adapter.requests[0].messages, source_a.messages)
                self.assertEqual(adapter.requests[0].context_digest, base_a.digest)

                request_two = adapter.requests[1]
                self.assertEqual(
                    request_two.messages[: len(source_a.messages)], source_a.messages
                )
                self.assertEqual(request_two.messages[-1]["role"], "tool")
                candidate_text = str(request_two.messages[-1])
                self.assertIn(pin_b.resolved_digest, candidate_text)
                self.assertIn(pin_c.resolved_digest, candidate_text)
                self.assertNotEqual(request_two.context_digest, base_a.digest)
                expected_overlay = overlay_working_view(
                    base_a, (bridge.overlay_message,) if bridge.overlay_message else ()
                )
                self.assertEqual(request_two.context_digest, expected_overlay.digest)

                current = continuity.load_current_working_set()
                self.assertTrue(current.committed)
                self.assertEqual(current.pins, (pin_b,))
                self.assertEqual(current.attempt_id, proposal.next_attempt_id)
                self.assertEqual(adapter.requests[2].messages, source_b.messages)
                self.assertNotIn(source_a.messages[0]["content"], str(adapter.requests[2].messages))
                self.assertNotIn(pin_c.resolved_digest, str(adapter.requests[2].messages))
                self.assertNotIn("tool", str(adapter.requests[2].messages))
                self.assertNotIn(source_c.messages[0]["content"], str(adapter.requests[2].messages))

                successor_events = [
                    event
                    for event in store.list_run_events(run_contract.harness_run_id)
                    if event.event_kind == "harness.working-set-recorded"
                    and event.data.get("attemptId") == proposal.next_attempt_id
                ]
                self.assertEqual(len(successor_events), 3)
                self.assertTrue(
                    all(
                        event.data.get("sourceWorkingSetDigest") == committed_a.digest
                        and event.data.get("sourceModelViewDigest")
                        == request_two.context_digest
                        and "sourceWorkingViewDigest" not in event.data
                        for event in successor_events
                    )
                )
                self.assertTrue(continuity.doctor()["healthy"])
                if mode == "loss":
                    self.assertIn("task.list", [name for name, _ in runtime.calls])
                    self.assertIn("task.observe", [name for name, _ in runtime.calls])

    def test_raw_discovery_is_materialized_by_domain_before_agent_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_discovery_contract("pc14-raw-materialization")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                source_a = HarnessWorkingViewSource(
                    logical_ref="source://pc14/raw/current",
                    logical_generation="generation:a",
                    messages=(
                        {
                            "role": "user",
                            "content": "RAW_VIEW_A_INSUFFICIENT. Discover candidates.",
                        },
                    ),
                )
                source_b = HarnessWorkingViewSource(
                    logical_ref="source://pc14/raw/candidate-b",
                    logical_generation="generation:b",
                    messages=(
                        {"role": "user", "content": "RAW_VIEW_B_SELECTED"},
                    ),
                )
                source_c = HarnessWorkingViewSource(
                    logical_ref="source://pc14/raw/candidate-c",
                    logical_generation="generation:c",
                    messages=(
                        {"role": "user", "content": "RAW_VIEW_C_NOT_SELECTED"},
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
                    "working-attempt:pc14-raw-a", pins=(pin_a,)
                )
                continuity.record_working_set(initial)
                committed_a = initial.commit("raw discovery starts from A")
                continuity.record_working_set(committed_a)

                # B/C are genuine domain data but are not Harness cognition objects yet.
                expected_b_cas = canonical_digest(
                    {
                        "schemaVersion": 1,
                        "kind": "harness-working-view-source",
                        "payload": source_b.to_dict(),
                    }
                )
                expected_c_cas = canonical_digest(
                    {
                        "schemaVersion": 1,
                        "kind": "harness-working-view-source",
                        "payload": source_c.to_dict(),
                    }
                )
                with self.assertRaises(HarnessObjectMissing):
                    store.get_object(
                        expected_b_cas,
                        expected_kind="harness-working-view-source",
                    )
                with self.assertRaises(HarnessObjectMissing):
                    store.get_object(
                        expected_c_cas,
                        expected_kind="harness-working-view-source",
                    )

                runtime = RawCandidateRuntime("direct", (source_b, source_c))
                bridge = MaterializingDiscoveryRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(run_contract, continuity),
                    runtime,
                )
                adapter = DiscoverMaterializeSelectAdapter("raw-materialization")
                result = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=CandidateOverlayProjector(
                        store, continuity, bridge
                    ),
                    working_set_transition_handler=continuity,
                ).run(
                    harness_run_id=run_contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    initial_messages=(
                        {"role": "user", "content": "canonical raw discovery root"},
                    ),
                )

                self.assertEqual(
                    result.stop_code,
                    RunStopCode.CANDIDATE_COMPLETED,
                    result.trace.to_dict(),
                )
                self.assertEqual(runtime.workspace_exec_count, 1)
                self.assertEqual(len(adapter.requests), 3)
                self.assertEqual(adapter.requests[0].messages, source_a.messages)
                self.assertEqual(len(bridge.materialized_pins), 2)
                materialized_b, materialized_c = bridge.materialized_pins
                self.assertEqual(materialized_b.logical_ref, source_b.logical_ref)
                self.assertEqual(
                    materialized_b.logical_generation, source_b.logical_generation
                )
                self.assertEqual(materialized_b.resolved_digest, expected_b_cas)
                self.assertEqual(materialized_c.resolved_digest, expected_c_cas)
                self.assertIsNotNone(adapter.proposal)
                assert adapter.proposal is not None
                self.assertEqual(adapter.proposal.pins, (materialized_b,))
                # Runtime itself did not know the Harness CAS identities. The
                # domain adapter crossed the privacy/materialization boundary before
                # the Tool Receipt was recorded, and the resulting exact Observation
                # is the same object projected to the Agent.
                self.assertNotIn(expected_b_cas, str(runtime.terminal()))
                self.assertNotIn(expected_c_cas, str(runtime.terminal()))
                enriched_observation = result.observations[0]
                self.assertIn(expected_b_cas, str(enriched_observation.to_dict()))
                self.assertIn(expected_c_cas, str(enriched_observation.to_dict()))
                self.assertEqual(
                    adapter.requests[1].messages[-1],
                    enriched_observation.to_model_message(),
                )
                retained_tool = continuity.load_current_tool_step()
                self.assertEqual(retained_tool.observation, enriched_observation.to_dict())
                self.assertEqual(
                    store.get_object(
                        expected_b_cas,
                        expected_kind="harness-working-view-source",
                    ),
                    source_b.to_dict(),
                )
                self.assertEqual(
                    store.get_object(
                        expected_c_cas,
                        expected_kind="harness-working-view-source",
                    ),
                    source_c.to_dict(),
                )
                current = continuity.load_current_working_set()
                self.assertEqual(current.pins, (materialized_b,))
                self.assertEqual(adapter.requests[2].messages, source_b.messages)
                self.assertNotIn(expected_c_cas, str(adapter.requests[2].messages))
                self.assertTrue(continuity.doctor()["healthy"])

    def test_runtime_discovery_overlay_then_agent_selection(self) -> None:
        self.run_discovery_case("direct")

    def test_runtime_discovery_response_loss_reconciles_before_selection(self) -> None:
        self.run_discovery_case("loss")

    def test_doctor_rejects_low_level_provider_overlay_without_observation_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_discovery_contract("pc14-forged-overlay-history")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                committed_a, _, _, _, _, _ = self.prepare_sources(continuity)
                base = compile_working_view(committed_a, store)
                forged_view = overlay_working_view(
                    base,
                    ({"role": "user", "content": "FORGED_UNBOUND_HISTORY_OVERLAY"},),
                )
                request = AgentTurnRequest(
                    harness_run_id=run_contract.harness_run_id,
                    turn_id="turn:pc14-forged-overlay:1",
                    sequence=1,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=forged_view.digest,
                    tool_catalog_digest=run_contract.tool_catalog_digest,
                    messages=forged_view.messages,
                    tools=(),
                    remaining_budget={
                        "modelCalls": 3,
                        "toolCalls": 3,
                        "wallTimeMs": 10_000,
                    },
                )
                forged_state = HarnessRunState(
                    messages=forged_view.messages,
                    observations=(),
                    remaining_budget={
                        "modelCalls": 3,
                        "toolCalls": 3,
                        "wallTimeMs": 10_000,
                    },
                    requested_model_id=ScriptedTurnAdapter.model_id,
                    effective_model_id=None,
                )
                state_object = store.put_object(
                    forged_state.to_dict(run_contract.harness_run_id),
                    kind="harness-run-state",
                )
                request_object = store.put_object(
                    request.to_dict(), kind="agent-turn-request"
                )
                source = continuity.assignment_provider_source()
                record = HarnessProviderCallRecordV3(
                    record_id="harness-provider-call-record:pc14-forged-overlay",
                    provider_call_id="provider-call:pc14-forged-overlay",
                    harness_run_id=run_contract.harness_run_id,
                    binding_digest=continuity.binding.digest,
                    source_kind=source.kind,
                    source_digest=source.digest,
                    source_object_digest=source.object_digest,
                    state_object_digest=state_object.digest,
                    turn_id=request.turn_id,
                    turn_sequence=request.sequence,
                    request_digest=request.dispatch_digest,
                    provider_request_digest=canonical_digest(
                        {"providerRequest": "pc14-forged-overlay"}
                    ),
                    adapter_id=ScriptedTurnAdapter.adapter_id,
                    requested_model_id=ScriptedTurnAdapter.model_id,
                    holder_id="holder:pc14-forged-overlay",
                    claim_generation=1,
                    status=HarnessProviderCallStatus.CLAIMED,
                    result_digest=None,
                    result_object_digest=None,
                    failure_digest=None,
                    failure_object_digest=None,
                    previous_record_digest=None,
                    issued_at_ms=clock(),
                    expires_at_ms=clock() + 5_000,
                    recorded_at_ms=clock(),
                    request_object_digest=request_object.digest,
                )
                record_object = store.put_object(
                    record.to_dict(), kind="harness-provider-call-record"
                )
                lease = store.acquire_run_lease(
                    run_contract.harness_run_id,
                    owner_id="test:pc14-forged-overlay-history",
                    ttl_ms=5_000,
                    now_ms=clock(),
                )
                prior = store.list_run_events(run_contract.harness_run_id)[-1].event_id
                try:
                    store.append_event(
                        event_id="event:pc14-forged-overlay-provider-claim",
                        harness_run_id=run_contract.harness_run_id,
                        event_kind="harness.provider-call-claimed",
                        data={
                            "providerCallRecordDigest": record.digest,
                            "providerCallRecordObjectDigest": record_object.digest,
                            "stateObjectDigest": state_object.digest,
                            "requestObjectDigest": request_object.digest,
                            "resultObjectDigest": None,
                            "failureObjectDigest": None,
                        },
                        expected_revision=lease.run_revision,
                        recorded_at_ms=clock(),
                        lease=lease,
                        lease_checked_at_ms=clock(),
                        caused_by_event_id=prior,
                        referenced_objects=(
                            record_object,
                            state_object,
                            request_object,
                        ),
                    )
                finally:
                    store.release_run_lease(lease)

                # Mechanical Store integrity is intact; only semantic continuity
                # can see that the appended model content has no Tool Observation.
                self.assertTrue(store.doctor(full=True)["healthy"])
                with self.assertRaisesRegex(
                    HarnessProviderCallRequestMismatch,
                    "not an exact bound Tool Observation projection",
                ):
                    continuity.doctor()

    def test_unbound_append_overlay_is_rejected_before_provider_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_discovery_contract("pc14-unbound-overlay")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                self.prepare_sources(continuity)
                runtime = CandidateRuntime("direct", ())
                bridge = DiscoveryOverlayRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(run_contract, continuity),
                    runtime,
                )
                adapter = ScriptedTurnAdapter((completed_turn("must-not-dispatch-unbound"),))
                loop = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=ArbitraryAppendingProjector(
                        store, continuity
                    ),
                )
                with self.assertRaisesRegex(
                    HarnessProviderCallRequestMismatch,
                    "not an exact bound Tool Observation projection",
                ):
                    loop.run(
                        harness_run_id=run_contract.harness_run_id,
                        assignment_id=continuity.binding.assignment_id,
                        context_digest=run_contract.context_refs[0].digest,
                        initial_messages=(
                            {"role": "user", "content": "canonical root"},
                        ),
                    )
                self.assertEqual(len(adapter.requests), 0)
                self.assertEqual(runtime.workspace_exec_count, 0)

    def test_replacing_overlay_is_rejected_before_provider_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_discovery_contract("pc14-replace-rejected")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                self.prepare_sources(continuity)
                runtime = CandidateRuntime("direct", ())
                bridge = DiscoveryOverlayRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(run_contract, continuity),
                    runtime,
                )
                adapter = ScriptedTurnAdapter((completed_turn("must-not-dispatch"),))
                loop = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    working_view_projector=ReplacingProjector(store, continuity),
                )
                with self.assertRaisesRegex(
                    HarnessProviderCallRequestMismatch,
                    "preserve the current committed Working View prefix",
                ):
                    loop.run(
                        harness_run_id=run_contract.harness_run_id,
                        assignment_id=continuity.binding.assignment_id,
                        context_digest=run_contract.context_refs[0].digest,
                        initial_messages=(
                            {"role": "user", "content": "canonical root"},
                        ),
                    )
                self.assertEqual(len(adapter.requests), 0)
                self.assertEqual(runtime.workspace_exec_count, 0)

    def test_overlay_digest_cannot_be_used_without_provider_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = private_discovery_contract("pc14-no-provider")
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=clock
                )
                committed_a, pin_b, _, _, _, _ = self.prepare_sources(continuity)
                base = compile_working_view(committed_a, store)
                overlay = overlay_working_view(
                    base,
                    ({"role": "tool", "name": "discover", "content": "candidate B"},),
                )
                proposal = AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:pc14-no-provider-b",
                    pins=(pin_b,),
                    basis="must not trust a fabricated overlay digest",
                )
                with self.assertRaisesRegex(
                    HarnessProviderCallRequestMismatch,
                    "requires exact Provider evidence",
                ):
                    continuity.apply_working_set_transition(
                        proposal,
                        source_working_set_digest=committed_a.digest,
                        source_model_view_digest=overlay.digest,
                    )
                self.assertEqual(continuity.load_current_working_set(), committed_a)


if __name__ == "__main__":
    unittest.main()

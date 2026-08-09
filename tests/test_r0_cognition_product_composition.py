from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.loop import RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
    static_provider_request_digest,
)
from ordivon_harness.ordivon.sqlite_agent_bridge import SQLiteHarnessAgentBridge
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.standalone import (
    StandaloneCognitionProfile,
    StandaloneCognitionSeed,
    StandaloneCognitionSeedSource,
    StandaloneHarnessRunner,
)
from ordivon_harness.working_view import (
    AgentCallerIngressPromotionProposal,
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
)

from tests.test_p0_sqlite_agent_loop import FixedClock, contract
from tests.test_p0_sqlite_runtime_bridge import FakeRuntime, execution_binding
from tests.test_pc15_epistemic_control import private_contract, run_budget


def cognition_budget(*, max_model_calls: int = 4) -> RunBudget:
    return RunBudget(
        max_model_calls=max_model_calls,
        max_tool_calls=1,
        max_observation_bytes=16_384,
        max_wall_time_ms=10_000,
        max_total_tokens=10_000,
        max_model_retries=1,
    )


def cognition_contract(suffix: str, *, max_model_calls: int = 4):
    return replace(
        contract(f"r0-{suffix}"),
        budget={
            "maxModelCalls": max_model_calls,
            "maxToolCalls": 1,
            "maxWallTimeMs": 10_000,
        },
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=False,
        ),
    )


def needs_input(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:r0-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content="bounded caller input required",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="needs_input",
            summary="R0 product composition reached an interaction boundary.",
        ),
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"r0": suffix, "kind": "needs-input"}),
    )


class CaptureNeedsInputAdapter:
    adapter_id = ScriptedTurnAdapter.adapter_id
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(self, suffix: str) -> None:
        self.suffix = suffix
        self.requests: list[AgentTurnRequest] = []

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        return needs_input(self.suffix)


class PromotionThenTransitionAdapter:
    adapter_id = ScriptedTurnAdapter.adapter_id
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(self) -> None:
        self.requests: list[AgentTurnRequest] = []

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        index = len(self.requests)
        if index == 1:
            if tuple(ref.caller_message_index for ref in request.caller_ingress_refs) != (0,):
                raise AssertionError("product Runner did not expose exact caller ingress provenance")
            return AgentTurnResult(
                model_call_id="model-call:r0-promotion",
                model_id=self.model_id,
                content="retain the exact caller correction",
                tool_calls=(),
                conclusion=None,
                usage={"inputTokens": 12, "outputTokens": 6},
                finish_reason="tool_calls",
                raw_response_digest=canonical_digest({"r0": "promotion"}),
                caller_ingress_promotion=AgentCallerIngressPromotionProposal(
                    next_attempt_id="working-attempt:r0-b",
                    promotion_slot="caller-fact",
                    caller_message_indexes=(0,),
                    basis="retain the exact caller fact across interactions",
                ),
            )
        if index == 2:
            by_slot = {ref.pin.slot: ref.pin for ref in request.working_set_refs}
            if set(by_slot) != {"caller-fact", "task"}:
                raise AssertionError(f"unexpected product WorkingSet: {sorted(by_slot)}")
            return AgentTurnResult(
                model_call_id="model-call:r0-transition",
                model_id=self.model_id,
                content="the retained caller fact is sufficient for the next attempt",
                tool_calls=(),
                conclusion=None,
                usage={"inputTokens": 13, "outputTokens": 6},
                finish_reason="tool_calls",
                raw_response_digest=canonical_digest({"r0": "transition"}),
                working_set_transition=AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:r0-c",
                    pins=(by_slot["caller-fact"],),
                    basis="drop the bootstrap task after its purpose is complete",
                ),
            )
        if index == 3:
            if tuple(ref.pin.slot for ref in request.working_set_refs) != ("caller-fact",):
                raise AssertionError("ordinary WorkingSet transition was not applied")
            return needs_input("post-transition")
        raise AssertionError("unexpected R0 Provider turn")




class HistoryProductAdapter:
    adapter_id = ScriptedTurnAdapter.adapter_id
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(self) -> None:
        self.requests: list[AgentTurnRequest] = []

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        index = len(self.requests)
        if index == 1:
            pins = tuple(ref.pin for ref in request.working_set_refs)
            return AgentTurnResult(
                model_call_id="model-call:r0-history-reset",
                model_id=self.model_id,
                content="start a fresh cognition attempt without changing selected sources",
                tool_calls=(),
                conclusion=None,
                usage={"inputTokens": 10, "outputTokens": 5},
                finish_reason="tool_calls",
                raw_response_digest=canonical_digest({"r0": "history-reset"}),
                working_set_transition=AgentWorkingSetTransitionProposal(
                    next_attempt_id="working-attempt:r0-history-b",
                    pins=pins,
                    basis="create a fresh attempt while preserving the exact selection",
                ),
            )
        if index == 2:
            return AgentTurnResult(
                model_call_id="model-call:r0-history-inspect",
                model_id=self.model_id,
                content="inspect prior committed cognition identities",
                tool_calls=(
                    AgentToolCall(
                        tool_call_id="tool-call:r0-history",
                        name="inspect_working_set_history",
                        arguments={"limit": 5},
                    ),
                ),
                conclusion=None,
                usage={"inputTokens": 11, "outputTokens": 5},
                finish_reason="tool_calls",
                raw_response_digest=canonical_digest({"r0": "history-inspect"}),
            )
        if index == 3:
            history_messages = [
                message
                for message in request.messages
                if message.get("role") == "tool"
            ]
            if not history_messages or "working-set-history" not in str(history_messages[-1]):
                raise AssertionError("product Runner did not restore history cognition result")
            return needs_input("history-observed")
        raise AssertionError("unexpected R0 history turn")


class R0CognitionProductCompositionTests(unittest.TestCase):
    @staticmethod
    def seed() -> StandaloneCognitionSeed:
        return StandaloneCognitionSeed(
            attempt_id="working-attempt:r0-a",
            sources=(
                StandaloneCognitionSeedSource(
                    slot="task",
                    source=HarnessWorkingViewSource(
                        logical_ref="source://r0/task",
                        logical_generation="generation:r0-task-v1",
                        messages=(
                            {
                                "role": "user",
                                "content": "R0_TASK: use exact Agent-owned cognition, not canonical transcript replay.",
                            },
                        ),
                    ),
                ),
            ),
            basis="caller supplied the exact initial task cognition",
        )

    @staticmethod
    def runner(run_contract, continuity, adapter, bridge, clock):
        return StandaloneHarnessRunner(
            run_contract,
            continuity,
            adapter,
            bridge,
            budget=cognition_budget(),
            clock_ms=clock,
            monotonic_ms=clock,
            cognition_profile=StandaloneCognitionProfile(
                working_set_transitions=True,
                caller_ingress_promotions=True,
                working_set_history=False,
            ),
        )

    def test_product_runner_bootstraps_and_projects_without_manual_cognition_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = cognition_contract("bootstrap")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            clock = FixedClock()
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            adapter = CaptureNeedsInputAdapter("bootstrap")
            bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            execution = self.runner(
                run_contract, continuity, adapter, bridge, clock
            ).run((), cognition_seed=self.seed())

            self.assertEqual(execution.loop_result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(len(adapter.requests), 1)
            request = adapter.requests[0]
            self.assertEqual(
                request.messages,
                self.seed().sources[0].source.messages,
            )
            self.assertEqual(tuple(ref.pin.slot for ref in request.working_set_refs), ("task",))
            current = continuity.load_current_working_set()
            self.assertTrue(current.committed)
            self.assertEqual(tuple(pin.slot for pin in current.pins), ("task",))
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_product_bootstrap_recovers_after_only_initial_working_set_was_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = cognition_contract("bootstrap-recovery")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            clock = FixedClock()
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            seed = self.seed()
            stored = continuity.store_working_view_source(seed.sources[0].source)
            initial = HarnessWorkingSetSpec.initial(
                seed.attempt_id,
                pins=(
                    HarnessWorkingSetPin(
                        slot=seed.sources[0].slot,
                        logical_ref=seed.sources[0].source.logical_ref,
                        logical_generation=seed.sources[0].source.logical_generation,
                        resolved_digest=stored.digest,
                    ),
                ),
            )
            continuity.record_working_set(initial)
            adapter = CaptureNeedsInputAdapter("bootstrap-recovery")
            bridge = SQLiteHarnessAgentBridge(run_contract, continuity)

            execution = self.runner(
                run_contract, continuity, adapter, bridge, clock
            ).run((), cognition_seed=seed)

            self.assertEqual(execution.loop_result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(continuity.load_current_working_set(), initial.commit(seed.basis))
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_product_runner_composes_promotion_and_transition_across_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = cognition_contract("resume")
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            clock = FixedClock()
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            first_adapter = CaptureNeedsInputAdapter("first-boundary")
            first_bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            first = self.runner(
                run_contract, continuity, first_adapter, first_bridge, clock
            ).run((), cognition_seed=self.seed())
            self.assertEqual(first.loop_result.stop_code, RunStopCode.NEEDS_INPUT)

            retained = continuity.load_current_snapshot()
            adapter = PromotionThenTransitionAdapter()
            bridge = SQLiteHarnessAgentBridge(
                run_contract,
                continuity,
                provider_source=continuity.snapshot_provider_source(retained),
            )
            resumed = self.runner(
                run_contract, continuity, adapter, bridge, clock
            ).resume(
                additional_messages=(
                    {"role": "user", "content": "CALLER_FACT_BLUE_17"},
                )
            )

            self.assertEqual(resumed.loop_result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(len(adapter.requests), 3)
            current = continuity.load_current_working_set()
            self.assertEqual(current.attempt_id, "working-attempt:r0-c")
            self.assertEqual(tuple(pin.slot for pin in current.pins), ("caller-fact",))
            raw = store.get_object(
                current.pins[0].resolved_digest, expected_kind="harness-working-view-source"
            )
            self.assertEqual(
                HarnessWorkingViewSource.from_dict(raw).messages,
                ({"role": "user", "content": "CALLER_FACT_BLUE_17"},),
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_full_product_profile_composes_history_without_manual_reader_wiring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = private_contract(
                "r0-history-product", max_model_calls=4, max_tool_calls=2
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            clock = FixedClock()
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            bridge = SQLiteHarnessRuntimeBridge(
                run_contract,
                continuity,
                execution_binding(run_contract, continuity),
                FakeRuntime("direct"),
            )
            adapter = HistoryProductAdapter()
            runner = StandaloneHarnessRunner(
                run_contract,
                continuity,
                adapter,
                bridge,
                budget=run_budget(max_model_calls=4, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                cognition_profile=StandaloneCognitionProfile.full(),
            )
            execution = runner.run((), cognition_seed=self.seed())

            self.assertEqual(execution.loop_result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(len(adapter.requests), 3)
            self.assertEqual(
                continuity.load_current_working_set().attempt_id,
                "working-attempt:r0-history-b",
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_product_runner_rejects_provider_capability_mismatch_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            base = cognition_contract("capability-mismatch")
            adapter = DeepSeekTurnAdapter(DeepSeekSettings(api_key="r0-test-secret"))
            run_contract = replace(
                base,
                provider_id="provider:deepseek",
                adapter_id=adapter.adapter_id,
                requested_model_id=adapter.model_id,
            )
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            clock = FixedClock()
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
            bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            with self.assertRaisesRegex(
                ValueError, "working_set_transitions differs from Standalone composition"
            ):
                StandaloneHarnessRunner(
                    run_contract,
                    continuity,
                    adapter,
                    bridge,
                    budget=cognition_budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                    cognition_profile=StandaloneCognitionProfile(
                        working_set_transitions=True,
                        caller_ingress_promotions=True,
                        working_set_history=False,
                    ),
                )

            provider_exposes_cognition = DeepSeekTurnAdapter(
                DeepSeekSettings(api_key="r0-test-secret"),
                working_set_transitions=True,
                caller_ingress_promotions=True,
                working_set_history=False,
            )
            with self.assertRaisesRegex(
                ValueError, "working_set_transitions differs from Standalone composition"
            ):
                StandaloneHarnessRunner(
                    run_contract,
                    continuity,
                    provider_exposes_cognition,
                    bridge,
                    budget=cognition_budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                )
            store.close()


if __name__ == "__main__":
    unittest.main()

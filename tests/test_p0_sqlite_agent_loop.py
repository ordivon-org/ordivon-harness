from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
    static_provider_request_digest,
)
from ordivon_harness.ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_SURFACE_DIGEST,
    SQLiteHarnessAgentBridge,
)
from ordivon_harness.ordivon.sqlite_run_store import (
    SQLiteHarnessRunContinuityStore,
)
from ordivon_harness.protocol import HarnessProviderCallStatus
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class FixedClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class FailIfInvokedAdapter:
    adapter_id = ScriptedTurnAdapter.adapter_id
    model_id = ScriptedTurnAdapter.model_id
    provider_request_digest = static_provider_request_digest

    def __init__(self) -> None:
        self.requests: list[AgentTurnRequest] = []

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        raise AssertionError("durable Provider result should have replayed")


class LoseCompletionResponseBridge(SQLiteHarnessAgentBridge):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.injected = False

    def complete_provider_call(
        self,
        request: AgentTurnRequest,
        result: AgentTurnResult,
    ) -> None:
        super().complete_provider_call(request, result)
        if not self.injected:
            self.injected = True
            raise RuntimeError("injected Bridge response loss after durable completion")


def contract(suffix: str) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f"harness-run:p0-agent-loop-{suffix}",
        harness_implementation_id="ordivon-harness@0.7.0-dev",
        caller_id="caller:p0-independent-agent-loop",
        caller_run_ref=f"trial:p0-agent-loop-{suffix}",
        objective_ref=HarnessBoundReference(
            f"objective:p0-agent-loop-{suffix}", "objective", DIGEST_A
        ),
        context_refs=(
            HarnessBoundReference(f"context:p0-agent-loop-{suffix}", "context", DIGEST_B),
        ),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=canonical_digest(
            {
                "schemaVersion": 1,
                "kind": "ordivon.no-tool-grant",
                "tools": [],
            }
        ),
        budget={
            "maxModelCalls": 2,
            "maxToolCalls": 1,
            "maxWallTimeMs": 10_000,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            f"system-manifest:p0-agent-loop-{suffix}",
            "system-manifest",
            DIGEST_A,
        ),
        created_at_ms=1_000,
    )


def budget() -> RunBudget:
    return RunBudget(
        max_model_calls=2,
        max_tool_calls=1,
        max_observation_bytes=16_384,
        max_wall_time_ms=10_000,
        max_total_tokens=10_000,
        max_model_retries=1,
    )


def completed_result(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:p0-agent-loop-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content="completed",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Independent Agent Loop completed without Host state.",
        ),
        usage={"inputTokens": 12, "outputTokens": 4},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"response": suffix}),
    )


def needs_input_result(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:p0-agent-loop-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content="need one bounded answer",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="needs_input",
            summary="One bounded caller answer is required.",
        ),
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"response": suffix}),
    )


class SQLiteHarnessAgentLoopTests(unittest.TestCase):
    def initialize(self, root: Path, run_contract: HarnessRunContract, clock: FixedClock):
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        continuity = SQLiteHarnessRunContinuityStore(
            store,
            run_contract,
            clock_ms=clock,
        )
        return store, continuity

    @staticmethod
    def run_loop(
        run_contract: HarnessRunContract,
        continuity: SQLiteHarnessRunContinuityStore,
        adapter,
        clock: FixedClock,
        *,
        bridge_type=SQLiteHarnessAgentBridge,
    ):
        bridge = bridge_type(run_contract, continuity)
        loop = OrdivonAgentLoop(
            adapter,
            bridge,
            budget=budget(),
            clock_ms=clock,
            monotonic_ms=clock,
            assignment_deadline_ms=run_contract.deadline_ms,
        )
        result = loop.run(
            harness_run_id=run_contract.harness_run_id,
            assignment_id=continuity.binding.assignment_id,
            context_digest=run_contract.context_refs[0].digest,
            initial_messages=({"role": "user", "content": "complete this independent Run"},),
        )
        return bridge, result

    def test_real_agent_loop_completes_with_only_independent_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = contract("complete")
            store, continuity = self.initialize(root, run_contract, clock)
            adapter = ScriptedTurnAdapter((completed_result("complete"),))
            bridge, result = self.run_loop(
                run_contract,
                continuity,
                adapter,
                clock,
            )
            self.assertTrue(result.candidate_completed)
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 1)
            self.assertEqual(result.tool_calls, 0)
            self.assertEqual(len(adapter.requests), 1)
            self.assertEqual(adapter.requests[0].tools, ())
            self.assertEqual(bridge.definitions(), ())
            retained = continuity.load_current_provider_call()
            self.assertEqual(
                retained.record.status,
                HarnessProviderCallStatus.COMPLETED,
            )
            self.assertEqual(retained.result, completed_result("complete"))
            self.assertEqual(continuity.doctor()["providerRecords"], 3)
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                self.assertEqual(
                    reopened.load_current_provider_call().result,
                    completed_result("complete"),
                )

    def test_durable_completion_replays_after_bridge_response_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = contract("response-loss")
            store, continuity = self.initialize(root, run_contract, clock)
            first_adapter = ScriptedTurnAdapter((completed_result("response-loss"),))
            with self.assertRaisesRegex(RuntimeError, "response loss"):
                self.run_loop(
                    run_contract,
                    continuity,
                    first_adapter,
                    clock,
                    bridge_type=LoseCompletionResponseBridge,
                )
            self.assertEqual(len(first_adapter.requests), 1)
            self.assertEqual(
                continuity.load_current_provider_call().record.status,
                HarnessProviderCallStatus.COMPLETED,
            )
            revision = continuity.caller_revision
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                replay_adapter = FailIfInvokedAdapter()
                _, result = self.run_loop(
                    run_contract,
                    reopened,
                    replay_adapter,
                    clock,
                )
                self.assertTrue(result.candidate_completed)
                self.assertEqual(replay_adapter.requests, [])
                self.assertEqual(result.usage["providerResultsReplayed"], 1)
                self.assertEqual(reopened.caller_revision, revision)

    def test_needs_input_snapshot_resumes_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = contract("pause-resume")
            store, continuity = self.initialize(root, run_contract, clock)
            first_adapter = ScriptedTurnAdapter((needs_input_result("pause"),))
            _, paused = self.run_loop(
                run_contract,
                continuity,
                first_adapter,
                clock,
            )
            self.assertEqual(paused.stop_code, RunStopCode.NEEDS_INPUT)
            retained = continuity.load_current_snapshot()
            self.assertEqual(retained.snapshot.pause_reason.value, "needs-input")
            self.assertEqual(retained.snapshot.sequence, 1)
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store,
                    run_contract.harness_run_id,
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                source = reopened.snapshot_provider_source(retained)
                adapter = ScriptedTurnAdapter((completed_result("resume"),))
                bridge = SQLiteHarnessAgentBridge(
                    run_contract,
                    reopened,
                    provider_source=source,
                )
                loop = OrdivonAgentLoop(
                    adapter,
                    bridge,
                    budget=budget(),
                    clock_ms=clock,
                    monotonic_ms=clock,
                )
                completed = loop.resume(
                    retained=retained,
                    assignment_id=reopened.binding.assignment_id,
                    context_digest=run_contract.context_refs[0].digest,
                    additional_messages=({"role": "user", "content": "the bounded answer is yes"},),
                )
                self.assertTrue(completed.candidate_completed)
                self.assertEqual(completed.model_calls, 2)
                self.assertEqual(len(adapter.requests), 1)
                self.assertEqual(adapter.requests[0].sequence, 2)
                self.assertEqual(
                    reopened.load_current_provider_call().record.source_kind.value,
                    "snapshot",
                )
                self.assertEqual(reopened.doctor()["snapshots"], 1)

    def test_bridge_rejects_noncanonical_tool_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = contract("wrong-surface")
            value = run_contract.to_dict()
            value["toolCatalogDigest"] = DIGEST_A
            wrong = HarnessRunContract.from_dict(value)
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(wrong)
                continuity = SQLiteHarnessRunContinuityStore(
                    store,
                    wrong,
                    clock_ms=clock,
                )
                with self.assertRaisesRegex(ValueError, "no-Tool"):
                    SQLiteHarnessAgentBridge(wrong, continuity)

    def test_bridge_rejects_noncanonical_no_tool_grant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = FixedClock()
            run_contract = contract("wrong-grant")
            value = run_contract.to_dict()
            value["toolGrantDigest"] = DIGEST_A
            wrong = HarnessRunContract.from_dict(value)
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(wrong)
                continuity = SQLiteHarnessRunContinuityStore(
                    store,
                    wrong,
                    clock_ms=clock,
                )
                with self.assertRaisesRegex(ValueError, "Tool Grant"):
                    SQLiteHarnessAgentBridge(wrong, continuity)

    def test_independent_agent_bridge_has_no_host_or_runtime_imports(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ordivon_harness"
            / "ordivon"
            / "sqlite_agent_bridge.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "ordivon_host",
            "_host_compat",
            "CommittedHarnessAssignment",
            "RuntimeClient",
            "HostHarnessRunStore",
            "from .tools import",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

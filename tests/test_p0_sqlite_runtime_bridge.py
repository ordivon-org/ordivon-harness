from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from anc_canonical import JsonValue, canonical_digest

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.execution_binding import (
    HarnessExecutionBinding,
    HarnessRuntimeReference,
)
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_run_store import (
    SQLiteHarnessRunContinuityStore,
)
from ordivon_harness.ordivon.sqlite_runtime_bridge import (
    INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
    INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
    SQLiteHarnessRuntimeBridge,
)
from ordivon_harness.protocol import HarnessToolStepStatus
from ordivon_harness.run_state import HarnessRunState
from ordivon_harness.runtime_port import (
    HarnessRuntimeClientError,
    HarnessRuntimeErrorDetail,
    HarnessRuntimeToolRejected,
)
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


class FixedClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value

    def advance(self, delta: int = 1) -> int:
        self.value += delta
        return self.value


class FakeRuntime:
    def __init__(self, mode: str = "direct") -> None:
        self.mode = mode
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []
        self.workspace_exec_count = 0
        self.job_id = "job:p0-independent-search-001"
        self.client_request_id: str | None = None

    def terminal(self) -> dict[str, JsonValue]:
        assert self.client_request_id is not None
        return {
            "schemaVersion": 1,
            "jobId": self.job_id,
            "clientRequestId": self.client_request_id,
            "status": "succeeded",
            "artifacts": [],
            "stdoutTail": (
                '{"type":"match","data":{"path":{"text":"src/demo.py"},'
                '"lines":{"text":"class HarnessExecutionBinding:\\n"},'
                '"line_number":12,"absolute_offset":180,'
                '"submatches":[{"start":6,"end":29}]}}\n'
            ),
            "stderrTail": "",
        }

    @staticmethod
    def assert_task_list_arguments(arguments: dict[str, JsonValue]) -> None:
        if set(arguments) - {"limit", "clientRequestId", "cursor"}:
            raise AssertionError(f"task.list received unsupported fields: {arguments}")
        if arguments.get("limit") != 100:
            raise AssertionError("task.list limit differs")
        if not isinstance(arguments.get("clientRequestId"), str):
            raise AssertionError("task.list clientRequestId differs")

    def call_tool(
        self,
        name: str,
        arguments: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        self.calls.append((name, arguments))
        if name == "workspace.exec":
            self.workspace_exec_count += 1
            request_id = arguments.get("clientRequestId")
            assert isinstance(request_id, str)
            self.client_request_id = request_id
            if self.mode == "loss":
                raise HarnessRuntimeClientError(
                    "injected transport response loss after Runtime admission"
                )
            if self.mode == "reject":
                raise HarnessRuntimeToolRejected(
                    name,
                    HarnessRuntimeErrorDetail(
                        code="invalid_argument",
                        message="scripted request rejection",
                        commit_state="not_committed",
                        retryable=False,
                        field="execution.args",
                    ),
                )
            return self.terminal()
        if name == "task.list":
            self.assert_task_list_arguments(arguments)
            request_id = arguments.get("clientRequestId")
            assert isinstance(request_id, str)
            if self.mode == "zero":
                jobs: list[JsonValue] = []
            elif self.mode == "multiple":
                jobs = [
                    {
                        "jobId": self.job_id,
                        "clientRequestId": request_id,
                        "status": "succeeded",
                    },
                    {
                        "jobId": "job:p0-independent-search-duplicate",
                        "clientRequestId": request_id,
                        "status": "succeeded",
                    },
                ]
            else:
                jobs = [
                    {
                        "jobId": self.job_id,
                        "clientRequestId": request_id,
                        "status": "succeeded",
                    }
                ]
            return {
                "schemaVersion": 1,
                "jobs": jobs,
                "nextCursor": None,
            }
        if name == "task.observe":
            return self.terminal()
        raise AssertionError(f"unexpected Runtime tool: {name}")


def contract(suffix: str) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f"harness-run:p0-runtime-{suffix}",
        harness_implementation_id="ordivon-harness@0.7.0-dev",
        caller_id="caller:p0-independent-runtime",
        caller_run_ref=f"trial:p0-runtime-{suffix}",
        objective_ref=HarnessBoundReference(
            f"objective:p0-runtime-{suffix}", "objective", DIGEST_A
        ),
        context_refs=(HarnessBoundReference(f"context:p0-runtime-{suffix}", "context", DIGEST_B),),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
        tool_grant_digest=INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
        budget={
            "maxModelCalls": 3,
            "maxToolCalls": 2,
            "maxWallTimeMs": 10_000,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            f"system-manifest:p0-runtime-{suffix}",
            "system-manifest",
            DIGEST_C,
        ),
        created_at_ms=1_000,
    )


def execution_binding(
    run_contract: HarnessRunContract,
    continuity: SQLiteHarnessRunContinuityStore,
) -> HarnessExecutionBinding:
    binding = continuity.binding
    references = (
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="harness_run",
            reference_id=run_contract.harness_run_id,
            generation=str(binding.assignment_generation),
            digest=binding.digest,
        ),
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="run_contract",
            reference_id=f"harness-run-contract:{run_contract.digest[7:31]}",
            generation="1",
            digest=run_contract.digest,
        ),
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="tool_grant",
            reference_id=f"tool-grant:{run_contract.tool_grant_digest[7:31]}",
            generation="1",
            digest=run_contract.tool_grant_digest,
        ),
    )
    return HarnessExecutionBinding(
        harness_run_id=run_contract.harness_run_id,
        workspace_ref=f"workspace:{run_contract.harness_run_id.removeprefix('harness-run:')}",
        assignment_id=binding.assignment_id,
        assignment_generation=binding.assignment_generation,
        assignment_digest=binding.assignment_digest,
        runtime_binding_digest=canonical_digest(
            {
                "harnessRunId": run_contract.harness_run_id,
                "workspaceRef": "workspace:p0-independent-runtime",
            }
        ),
        tool_catalog_digest=run_contract.tool_catalog_digest,
        tool_grant_digest=run_contract.tool_grant_digest,
        deadline_ms=run_contract.deadline_ms,
        runtime_references=references,
    )


def budget() -> RunBudget:
    return RunBudget(
        max_model_calls=3,
        max_tool_calls=2,
        max_observation_bytes=16_384,
        max_wall_time_ms=10_000,
        max_total_tokens=10_000,
        max_model_retries=1,
    )


def tool_turn(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:p0-runtime-{suffix}-1",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=(
            AgentToolCall(
                tool_call_id=f"tool-call:p0-runtime-{suffix}-search",
                name="search_workspace",
                arguments={
                    "query": "HarnessExecutionBinding",
                    "relativePath": "src",
                    "maxMatches": 20,
                },
            ),
        ),
        conclusion=None,
        usage={"inputTokens": 12, "outputTokens": 8},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"turn": suffix, "kind": "tool"}),
    )


def completed_turn(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:p0-runtime-{suffix}-2",
        model_id=ScriptedTurnAdapter.model_id,
        content="located the execution binding",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Independent Runtime search completed.",
        ),
        usage={"inputTokens": 24, "outputTokens": 7},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"turn": suffix, "kind": "completed"}),
    )


def bound_state() -> HarnessRunState:
    return HarnessRunState(
        messages=({"role": "user", "content": "search the workspace"},),
        observations=(),
        remaining_budget={
            "modelCalls": 3,
            "modelRetries": 1,
            "toolCalls": 2,
            "wallTimeMs": 10_000,
            "observationOnlyTurns": 3,
            "noProgressTurns": 3,
        },
        requested_model_id=ScriptedTurnAdapter.model_id,
        effective_model_id=None,
        active_elapsed_ms=0,
    )


class SQLiteHarnessRuntimeBridgeTests(unittest.TestCase):
    def initialize(self, root: Path, suffix: str, runtime: FakeRuntime):
        run_contract = contract(suffix)
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        clock = FixedClock()
        continuity = SQLiteHarnessRunContinuityStore(
            store,
            run_contract,
            clock_ms=clock,
        )
        bridge = SQLiteHarnessRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
        )
        return store, clock, run_contract, continuity, bridge

    def test_real_agent_loop_searches_runtime_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            store, clock, run_contract, continuity, bridge = self.initialize(
                Path(directory) / "state",
                "direct",
                runtime,
            )
            adapter = ScriptedTurnAdapter((tool_turn("direct"), completed_turn("direct")))
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=budget(),
                clock_ms=clock,
                monotonic_ms=clock,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "search the workspace"},),
            )
            self.assertTrue(result.candidate_completed)
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.tool_calls, 1)
            self.assertEqual(runtime.workspace_exec_count, 1)
            request = next(
                arguments for name, arguments in runtime.calls if name == "workspace.exec"
            )
            references = request["execution"]["foreignReferences"]
            self.assertEqual(
                {item["namespace"] for item in references},
                {"ordivon.harness"},
            )
            self.assertIn("dispatch_fence", {item["type"] for item in references})
            retained = continuity.load_current_tool_step()
            self.assertEqual(retained.receipt.status, HarnessToolStepStatus.OBSERVED)
            self.assertFalse(retained.receipt.reconciled)
            self.assertEqual(retained.observation["structuredContent"]["matchCount"], 1)
            store.close()

    def test_transport_response_loss_reconciles_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("loss")
            store, clock, run_contract, continuity, bridge = self.initialize(
                Path(directory) / "state",
                "loss",
                runtime,
            )
            adapter = ScriptedTurnAdapter((tool_turn("loss"), completed_turn("loss")))
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=budget(),
                clock_ms=clock,
                monotonic_ms=clock,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "search after response loss"},),
            )
            self.assertTrue(result.candidate_completed)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(
                [name for name, _ in runtime.calls].count("workspace.exec"),
                1,
            )
            self.assertIn("task.list", [name for name, _ in runtime.calls])
            self.assertIn("task.observe", [name for name, _ in runtime.calls])
            retained = continuity.load_current_tool_step()
            self.assertTrue(retained.receipt.reconciled)
            self.assertEqual(retained.receipt.status, HarnessToolStepStatus.OBSERVED)
            store.close()

    def test_zero_or_multiple_reconciliation_matches_are_unknown(self) -> None:
        for mode in ("zero", "multiple"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                runtime = FakeRuntime(mode)
                _, _, _, continuity, bridge = self.initialize(
                    Path(directory) / "state",
                    mode,
                    runtime,
                )
                bridge.bind_run_state(
                    messages=bound_state().messages,
                    observations=(),
                    remaining_budget=bound_state().remaining_budget,
                    requested_model_id=bound_state().requested_model_id,
                    effective_model_id=None,
                    active_elapsed_ms=0,
                )
                call = tool_turn(mode).tool_calls[0]
                runtime.mode = "loss"
                # Preserve the requested reconciliation cardinality after response loss.
                original = runtime.call_tool

                def call_tool(name, arguments):
                    if name == "workspace.exec":
                        runtime.workspace_exec_count += 1
                        request_id = arguments.get("clientRequestId")
                        assert isinstance(request_id, str)
                        runtime.client_request_id = request_id
                        raise HarnessRuntimeClientError("injected response loss")
                    runtime.mode = mode
                    return original(name, arguments)

                runtime.call_tool = call_tool  # type: ignore[method-assign]
                observation = bridge.execute(call, step_id=f"turn-1-tool-{mode}")
                self.assertEqual(observation.status, "unknown")
                self.assertEqual(runtime.workspace_exec_count, 1)
                retained = continuity.load_current_tool_step()
                self.assertEqual(retained.receipt.status, HarnessToolStepStatus.UNKNOWN)
                self.assertTrue(retained.receipt.reconciled)

    def test_precommit_runtime_rejection_is_model_correctable_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("reject")
            _, _, _, continuity, bridge = self.initialize(
                Path(directory) / "state",
                "reject",
                runtime,
            )
            value = bound_state()
            bridge.bind_run_state(
                messages=value.messages,
                observations=(),
                remaining_budget=value.remaining_budget,
                requested_model_id=value.requested_model_id,
                effective_model_id=None,
                active_elapsed_ms=0,
            )
            observation = bridge.execute(
                tool_turn("reject").tool_calls[0],
                step_id="turn-1-tool-reject",
            )
            self.assertEqual(observation.status, "rejected")
            self.assertTrue(observation.structured_content["safeToCorrect"])
            self.assertEqual(runtime.workspace_exec_count, 1)
            retained = continuity.load_current_tool_step()
            self.assertEqual(retained.receipt.status, HarnessToolStepStatus.REJECTED)
            self.assertIsNone(retained.receipt.runtime_job_ref)

    def test_modules_have_no_host_compatibility_imports(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "ordivon_harness"
        for relative in (
            "runtime_port.py",
            "agent_tool_observation.py",
            "ordivon/sqlite_runtime_bridge.py",
        ):
            source = (root / relative).read_text(encoding="utf-8")
            for forbidden in (
                "ordivon_host",
                "_host_compat",
                "CommittedHarnessAssignment",
                "HostHarnessRunStore",
                "from .._host_compat.effects import ArtifactRef",
            ):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

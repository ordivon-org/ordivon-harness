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
from ordivon_harness.ordivon.sqlite_repository_repair_bridge import (
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST,
    SQLiteHarnessRepositoryRepairRuntimeBridge,
)
from ordivon_harness.ordivon.sqlite_run_store import (
    SQLiteHarnessRunContinuityStore,
)
from ordivon_harness.ordivon.tool_errors import (
    ToolBridgeError,
    ToolBridgeErrorKind,
)
from ordivon_harness.protocol import HarnessRecoveryConsequence, HarnessToolStepStatus
from ordivon_harness.run_state import HarnessRunState
from ordivon_harness.runtime_port import HarnessRuntimeClientError
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
SOURCE = "def allocate(items):\n    return []\n"
PATCHED = "def allocate(items):\n    return list(items)\n"


class FixedClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class FakeRuntime:
    def __init__(
        self,
        *,
        patch_loss: bool = False,
        exec_loss: bool = False,
    ) -> None:
        self.patch_loss = patch_loss
        self.exec_loss = exec_loss
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []
        self.patch_count = 0
        self.exec_count = 0
        self.patch_request_id: str | None = None
        self.exec_request_id: str | None = None
        self.job_id = "job:p1-repository-repair-check"

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
        if name == "workspace.read":
            return {
                "schemaVersion": 1,
                "content": SOURCE,
                "truncated": False,
                "digest": canonical_digest({"content": SOURCE}),
            }
        if name == "workspace.patch":
            self.patch_count += 1
            request_id = arguments.get("clientRequestId")
            assert isinstance(request_id, str)
            self.patch_request_id = request_id
            if self.patch_loss:
                raise HarnessRuntimeClientError(
                    "injected Patch response loss after commit"
                )
            return {
                "schemaVersion": 1,
                "state": "applied",
                "clientRequestId": request_id,
                "changedPaths": ["allocation.py"],
                "diff": "-    return []\n+    return list(items)\n",
            }
        if name == "workspace.patch.get":
            assert arguments.get("clientRequestId") == self.patch_request_id
            return {
                "schemaVersion": 1,
                "state": "applied",
                "clientRequestId": self.patch_request_id,
                "changedPaths": ["allocation.py"],
                "diff": "-    return []\n+    return list(items)\n",
            }
        if name == "workspace.exec":
            self.exec_count += 1
            request_id = arguments.get("clientRequestId")
            assert isinstance(request_id, str)
            self.exec_request_id = request_id
            if self.exec_loss:
                raise HarnessRuntimeClientError(
                    "injected Check response loss after admission"
                )
            return self.terminal()
        if name == "task.list":
            self.assert_task_list_arguments(arguments)
            assert arguments.get("clientRequestId") == self.exec_request_id
            return {
                "schemaVersion": 1,
                "jobs": [
                    {
                        "jobId": self.job_id,
                        "clientRequestId": self.exec_request_id,
                        "status": "succeeded",
                    }
                ],
                "nextCursor": None,
            }
        if name == "task.observe":
            return self.terminal()
        if name == "workspace.diff":
            return {
                "schemaVersion": 1,
                "diff": "-    return []\n+    return list(items)\n",
                "changedPaths": ["allocation.py"],
                "modifiedPaths": ["allocation.py"],
                "untrackedPaths": [],
            }
        raise AssertionError(f"unexpected Runtime Tool: {name}")

    def terminal(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "jobId": self.job_id,
            "clientRequestId": self.exec_request_id,
            "status": "succeeded",
            "executionTerminal": True,
            "executionDisposition": "succeeded",
            "deliveryDisposition": "committed",
            "recoveryRequired": False,
            "semanticCompletionEvaluated": False,
            "resultAvailable": True,
            "artifacts": [],
            "stdoutTail": "OK\n",
            "stderrTail": "",
        }


def contract(suffix: str) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f"harness-run:p1-repair-{suffix}",
        harness_implementation_id="ordivon-harness@repository-repair-v1",
        caller_id="caller:p1-formal-runner",
        caller_run_ref=f"trial:p1-repair-{suffix}",
        objective_ref=HarnessBoundReference(
            f"objective:p1-repair-{suffix}", "objective", DIGEST_A
        ),
        context_refs=(
            HarnessBoundReference(
                f"context:p1-repair-{suffix}", "context", DIGEST_B
            ),
        ),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST,
        tool_grant_digest=INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST,
        budget={
            "maxModelCalls": 7,
            "maxToolCalls": 5,
            "maxWallTimeMs": 60_000,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            f"system-manifest:p1-repair-{suffix}",
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
                "workspaceRef": "workspace:p1-repository-repair",
            }
        ),
        tool_catalog_digest=run_contract.tool_catalog_digest,
        tool_grant_digest=run_contract.tool_grant_digest,
        deadline_ms=run_contract.deadline_ms,
        runtime_references=references,
    )


def bound_state() -> HarnessRunState:
    return HarnessRunState(
        messages=({"role": "user", "content": "repair allocation.py"},),
        observations=(),
        remaining_budget={
            "modelCalls": 7,
            "modelRetries": 1,
            "toolCalls": 5,
            "wallTimeMs": 60_000,
            "observationOnlyTurns": 6,
            "noProgressTurns": 6,
        },
        requested_model_id=ScriptedTurnAdapter.model_id,
        effective_model_id=None,
        active_elapsed_ms=0,
    )


def budget() -> RunBudget:
    return RunBudget(
        max_model_calls=7,
        max_tool_calls=5,
        max_observation_bytes=262_144,
        max_wall_time_ms=60_000,
        max_total_tokens=100_000,
        max_model_retries=1,
    )


def tool_turn(suffix: str, sequence: int, call: AgentToolCall) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:p1-repair-{suffix}-{sequence}",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=(call,),
        conclusion=None,
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest(
            {"suffix": suffix, "sequence": sequence, "call": call.to_dict()}
        ),
    )


def premature_turn(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:p1-repair-{suffix}-premature",
        model_id=ScriptedTurnAdapter.model_id,
        content="premature completion",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Attempted completion without evidence.",
        ),
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest(
            {"suffix": suffix, "premature": True}
        ),
    )


def complete_turn(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:p1-repair-{suffix}-7",
        model_id=ScriptedTurnAdapter.model_id,
        content="repository repair completed",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Patched allocation.py and passed the visible Check.",
            artifact_refs=(
                f"workspace-artifact:workspace:p1-repair-{suffix}:"
                "artifacts/completion.json",
            ),
        ),
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"suffix": suffix, "complete": True}),
    )


class RepositoryRepairRuntimeBridgeTests(unittest.TestCase):
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
        bridge = SQLiteHarnessRepositoryRepairRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
        )
        return store, clock, run_contract, continuity, bridge

    def test_premature_conclusion_is_corrected_before_five_tool_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime()
            store, clock, run_contract, continuity, bridge = self.initialize(
                Path(directory) / "state",
                "loop",
                runtime,
            )
            calls = (
                AgentToolCall(
                    "tool-call:p1-repair:read",
                    "read_workspace",
                    {"relativePath": "allocation.py", "mode": "FULL"},
                ),
                AgentToolCall(
                    "tool-call:p1-repair:patch",
                    "patch_workspace",
                    {
                        "files": [
                            {
                                "relativePath": "allocation.py",
                                "expectedDigest": None,
                                "edits": [
                                    {
                                        "range": {
                                            "start": {"line": 1, "column": 0},
                                            "end": {"line": 2, "column": 13},
                                        },
                                        "expectedText": SOURCE.rstrip("\n"),
                                        "replacement": PATCHED.rstrip("\n"),
                                    }
                                ],
                            }
                        ]
                    },
                ),
                AgentToolCall(
                    "tool-call:p1-repair:check",
                    "run_check",
                    {"checkId": "visible-tests", "waitMs": 30_000},
                ),
                AgentToolCall(
                    "tool-call:p1-repair:diff",
                    "diff_workspace",
                    {"maxBytes": 65_536},
                ),
                AgentToolCall(
                    "tool-call:p1-repair:reread",
                    "read_workspace",
                    {"relativePath": "allocation.py", "mode": "FULL"},
                ),
            )
            turns = (premature_turn("loop"),) + tuple(
                tool_turn("loop", sequence, call)
                for sequence, call in enumerate(calls, start=2)
            ) + (complete_turn("loop"),)
            result = OrdivonAgentLoop(
                ScriptedTurnAdapter(turns),
                bridge,
                budget=budget(),
                clock_ms=clock,
                monotonic_ms=clock,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=bound_state().messages,
            )
            self.assertTrue(result.candidate_completed)
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 7)
            self.assertEqual(result.tool_calls, 5)
            self.assertEqual(result.usage["toolCorrections"], 0)
            self.assertEqual(result.usage["conclusionCorrections"], 1)
            self.assertIn(
                "conclusion_rejected",
                {event.kind for event in result.trace.events},
            )
            self.assertEqual(
                [name for name, _ in runtime.calls],
                [
                    "workspace.read",
                    "workspace.patch",
                    "workspace.exec",
                    "workspace.diff",
                    "workspace.read",
                ],
            )
            self.assertEqual(
                continuity.load_current_tool_step().receipt.status,
                HarnessToolStepStatus.OBSERVED,
            )
            store.close()

    def test_patch_response_loss_reconciles_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime(patch_loss=True)
            store, _, _, continuity, bridge = self.initialize(
                Path(directory) / "state",
                "patch-loss",
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
            observation = bridge.execute(
                AgentToolCall(
                    "tool-call:p1-repair:patch-loss",
                    "patch_workspace",
                    {
                        "files": [
                            {
                                "relativePath": "allocation.py",
                                "edits": [
                                    {
                                        "range": {
                                            "start": {"line": 1, "column": 0},
                                            "end": {"line": 2, "column": 13},
                                        },
                                        "expectedText": SOURCE.rstrip("\n"),
                                        "replacement": PATCHED.rstrip("\n"),
                                    }
                                ],
                            }
                        ]
                    },
                ),
                step_id="turn-1-tool-patch",
            )
            self.assertEqual(observation.status, "observed")
            self.assertTrue(observation.reconciled)
            self.assertEqual(runtime.patch_count, 1)
            self.assertEqual(
                [name for name, _ in runtime.calls],
                ["workspace.patch", "workspace.patch.get"],
            )
            retained = continuity.load_current_tool_step()
            self.assertTrue(retained.receipt.reconciled)
            self.assertEqual(
                retained.intent.recovery_consequence,
                HarnessRecoveryConsequence.WORKSPACE_CHANGE_POSSIBLE,
            )
            store.close()

    def test_run_check_response_loss_reconciles_one_job_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime(exec_loss=True)
            store, _, _, continuity, bridge = self.initialize(
                Path(directory) / "state",
                "exec-loss",
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
            observation = bridge.execute(
                AgentToolCall(
                    "tool-call:p1-repair:check-loss",
                    "run_check",
                    {"checkId": "visible-tests"},
                ),
                step_id="turn-1-tool-check",
            )
            self.assertEqual(observation.status, "observed")
            self.assertTrue(observation.reconciled)
            self.assertEqual(runtime.exec_count, 1)
            self.assertEqual(
                [name for name, _ in runtime.calls],
                ["workspace.exec", "task.list", "task.observe"],
            )
            retained = continuity.load_current_tool_step()
            self.assertEqual(
                retained.intent.recovery_consequence,
                HarnessRecoveryConsequence.PROCESS_OR_EXTERNAL_EFFECT_POSSIBLE,
            )
            store.close()

    def test_paths_and_checks_outside_the_frozen_grant_fail_before_runtime(self) -> None:
        for call in (
            AgentToolCall(
                "tool-call:p1-repair:hidden-read",
                "read_workspace",
                {"relativePath": "hidden_verifier.py"},
            ),
            AgentToolCall(
                "tool-call:p1-repair:spec-patch",
                "patch_workspace",
                {
                    "files": [
                        {
                            "relativePath": "SPEC.md",
                            "edits": [
                                {
                                    "range": {
                                        "start": {"line": 1, "column": 0},
                                        "end": {"line": 1, "column": 0},
                                    },
                                    "expectedText": "",
                                    "replacement": "tamper",
                                }
                            ],
                        }
                    ]
                },
            ),
            AgentToolCall(
                "tool-call:p1-repair:unknown-check",
                "run_check",
                {"checkId": "hidden-tests"},
            ),
        ):
            with self.subTest(call=call.name), tempfile.TemporaryDirectory() as directory:
                runtime = FakeRuntime()
                store, _, _, _, bridge = self.initialize(
                    Path(directory) / "state",
                    call.tool_call_id.rsplit(":", 1)[-1],
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
                with self.assertRaises(ToolBridgeError) as caught:
                    bridge.execute(call, step_id="turn-1-tool-denied")
                self.assertEqual(
                    caught.exception.kind,
                    ToolBridgeErrorKind.AUTHORITY_DENIED,
                )
                self.assertEqual(runtime.calls, [])
                store.close()

    def test_module_has_no_host_compatibility_imports(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ordivon_harness"
            / "ordivon"
            / "sqlite_repository_repair_bridge.py"
        )
        source = path.read_text(encoding="utf-8")
        for forbidden in (
            "ordivon_host",
            "_host_compat",
            "HostHarnessRunStore",
            "CommittedHarnessAssignment",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

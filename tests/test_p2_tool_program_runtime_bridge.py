from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from anc_canonical import JsonValue, canonical_digest

from ordivon_harness.ordivon.sqlite_repository_repair_bridge import (
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS,
    SQLiteHarnessRepositoryRepairRuntimeBridge,
)
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.protocol import HarnessToolStepStatus
from ordivon_harness.runtime_port import HarnessRuntimeClientError
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.tool_program import (
    HarnessToolProgram,
    HarnessToolProgramExecutor,
    HarnessToolProgramStep,
    observation_ref,
)

from tests.test_p1_repository_repair_runtime_bridge import (
    PATCHED,
    SOURCE,
    FakeRuntime,
    bound_state,
    contract,
    execution_binding,
)


class UnreconciledPatchRuntime(FakeRuntime):
    def __init__(self) -> None:
        super().__init__(patch_loss=True)

    def call_tool(
        self,
        name: str,
        arguments: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        if name == "workspace.patch.get":
            self.calls.append((name, arguments))
            raise HarnessRuntimeClientError("P2 injected missing Patch reconciliation evidence")
        return super().call_tool(name, arguments)


def repair_program() -> HarnessToolProgram:
    return HarnessToolProgram(
        steps=(
            HarnessToolProgramStep(
                "read-before",
                "read_workspace",
                {"relativePath": "allocation.py", "mode": "FULL"},
            ),
            HarnessToolProgramStep(
                "patch",
                "patch_workspace",
                {
                    "files": [
                        {
                            "relativePath": "allocation.py",
                            "expectedDigest": observation_ref("read-before", "digest"),
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
            HarnessToolProgramStep(
                "check",
                "run_check",
                {"checkId": "visible-tests", "waitMs": 30_000},
            ),
            HarnessToolProgramStep(
                "diff",
                "diff_workspace",
                {"maxBytes": 65_536},
            ),
            HarnessToolProgramStep(
                "read-after",
                "read_workspace",
                {"relativePath": "allocation.py", "mode": "FULL"},
            ),
        ),
        outputs={
            "sourceDigest": observation_ref("read-before", "digest"),
            "patchChangedPaths": observation_ref("patch", "changedPaths"),
            "checkStatus": observation_ref("check", "status"),
            "diff": observation_ref("diff", "diff"),
            "finalDigest": observation_ref("read-after", "digest"),
        },
    )


class ToolProgramRuntimeBridgeP2Tests(unittest.TestCase):
    def initialize(self, root: Path, suffix: str, runtime: FakeRuntime):
        run_contract = contract(suffix)
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=lambda: 1_000)
        bridge = SQLiteHarnessRepositoryRepairRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
        )
        state = bound_state()
        bridge.bind_run_state(
            messages=state.messages,
            observations=(),
            remaining_budget=state.remaining_budget,
            requested_model_id=state.requested_model_id,
            effective_model_id=None,
            active_elapsed_ms=0,
        )
        return store, continuity, bridge

    def execute(self, root: Path, suffix: str, runtime: FakeRuntime):
        store, continuity, bridge = self.initialize(root, suffix, runtime)
        result = HarnessToolProgramExecutor(
            bridge,
            INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS,
        ).execute(
            repair_program(),
            remaining_tool_calls=5,
            step_prefix=f"turn-p2-{suffix}",
        )
        return store, continuity, result

    def test_real_repository_repair_bridge_executes_dynamic_program_through_durable_tool_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime()
            store, continuity, result = self.execute(
                Path(directory) / "state", "program-real", runtime
            )
            self.assertEqual(result.status, "completed")
            self.assertEqual(len(result.observations), 5)
            self.assertEqual(result.output["checkStatus"], "succeeded")
            self.assertEqual(result.output["patchChangedPaths"], ["allocation.py"])
            expected_source_digest = canonical_digest({"content": SOURCE})
            self.assertEqual(result.output["sourceDigest"], expected_source_digest)

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
            patch_request = next(
                arguments for name, arguments in runtime.calls if name == "workspace.patch"
            )
            files = patch_request["files"]
            assert isinstance(files, list) and isinstance(files[0], dict)
            self.assertEqual(files[0]["expectedDigest"], expected_source_digest)

            events = store.list_run_events(continuity.harness_run_id)
            prepared = [event for event in events if event.event_kind == "harness.tool-step-prepared"]
            terminal = [
                event
                for event in events
                if event.event_kind
                in {"harness.tool-step-recorded", "harness.tool-step-reconciled"}
            ]
            self.assertEqual(len(prepared), 5)
            self.assertEqual(len(terminal), 5)
            self.assertTrue(all(event.data.get("toolStepIntentObjectDigest") for event in terminal))
            self.assertEqual(
                continuity.load_current_tool_step().receipt.status,
                HarnessToolStepStatus.OBSERVED,
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_patch_response_loss_reconciles_inside_program_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime(patch_loss=True)
            store, continuity, result = self.execute(
                Path(directory) / "state", "program-patch-loss", runtime
            )
            self.assertEqual(result.status, "completed")
            patch_observation = result.observations[1]
            self.assertEqual(patch_observation.tool_name, "patch_workspace")
            self.assertTrue(patch_observation.reconciled)
            self.assertEqual(runtime.patch_count, 1)
            self.assertEqual(
                [name for name, _ in runtime.calls],
                [
                    "workspace.read",
                    "workspace.patch",
                    "workspace.patch.get",
                    "workspace.exec",
                    "workspace.diff",
                    "workspace.read",
                ],
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_check_response_loss_reconciles_one_runtime_job_and_program_continues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime(exec_loss=True)
            store, continuity, result = self.execute(
                Path(directory) / "state", "program-check-loss", runtime
            )
            self.assertEqual(result.status, "completed")
            check_observation = result.observations[2]
            self.assertEqual(check_observation.tool_name, "run_check")
            self.assertTrue(check_observation.reconciled)
            self.assertEqual(runtime.exec_count, 1)
            names = [name for name, _ in runtime.calls]
            self.assertEqual(names.count("workspace.exec"), 1)
            self.assertEqual(names.count("task.list"), 1)
            self.assertEqual(names.count("task.observe"), 1)
            self.assertEqual(names[-2:], ["workspace.diff", "workspace.read"])
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_unreconciled_patch_unknown_stops_program_before_later_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = UnreconciledPatchRuntime()
            store, continuity, result = self.execute(
                Path(directory) / "state", "program-patch-unknown", runtime
            )
            self.assertEqual(result.status, "unknown")
            self.assertEqual(len(result.observations), 2)
            self.assertEqual(result.observations[-1].tool_name, "patch_workspace")
            self.assertTrue(result.observations[-1].reconciled)
            self.assertEqual(result.output, {})
            self.assertEqual(runtime.patch_count, 1)
            self.assertEqual(
                [name for name, _ in runtime.calls],
                ["workspace.read", "workspace.patch", "workspace.patch.get"],
            )
            current = continuity.load_current_tool_step()
            self.assertEqual(current.receipt.status, HarnessToolStepStatus.UNKNOWN)
            self.assertTrue(current.receipt.reconciled)
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()


if __name__ == "__main__":
    unittest.main()

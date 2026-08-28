from __future__ import annotations

import json
import subprocess
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.ordivon.control import CancellationToken, ExecutionControl, RunDeadline
from ordivon_harness.ordivon.model import AgentToolCall
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.ordivon.tool_errors import ToolBridgeError
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from tests.test_p0_sqlite_runtime_bridge import (
    FakeRuntime,
    FixedClock,
    bound_state,
    contract,
    execution_binding,
)


def batch_call(suffix: str = "batch") -> AgentToolCall:
    return AgentToolCall(
        tool_call_id=f"tool-call:{suffix}",
        name="search_workspace",
        arguments={
            "queries": ["ToolProgram", "__NO_SUCH_LITERAL__"],
            "relativePath": "src",
            "maxMatchesPerQuery": 8,
        },
    )


def match_event(text: str = "ToolProgram") -> str:
    return json.dumps(
        {
            "type": "match",
            "data": {
                "path": {"text": "src/demo.py"},
                "lines": {"text": f"class {text}:\n"},
                "line_number": 7,
                "absolute_offset": 120,
                "submatches": [{"start": 6, "end": 6 + len(text)}],
            },
        },
        separators=(",", ":"),
    )


class BatchRuntime(FakeRuntime):
    def __init__(self, mode: str = "direct", *, hard_error: bool = False) -> None:
        super().__init__(mode)
        self.hard_error = hard_error

    def terminal(self):
        value = super().terminal()
        if self.hard_error:
            value.update(
                {
                    "status": "failed",
                    "executionDisposition": "failed",
                    "exitCode": 2,
                    "stdoutTail": (
                        "@@ORDIVON_SEARCH_BATCH:BEGIN\t0\n"
                        + '{"type":"summary","data":{}}\n'
                        + "@@ORDIVON_SEARCH_BATCH:END\t0\t2\n"
                        + "@@ORDIVON_SEARCH_BATCH:BEGIN\t1\n"
                        + '{"type":"summary","data":{}}\n'
                        + "@@ORDIVON_SEARCH_BATCH:END\t1\t2\n"
                    ),
                    "stderrTail": "rg: source path is unavailable\n",
                }
            )
            return value
        value["stdoutTail"] = (
            "@@ORDIVON_SEARCH_BATCH:BEGIN\t0\n"
            + match_event()
            + "\n@@ORDIVON_SEARCH_BATCH:END\t0\t0\n"
            + "@@ORDIVON_SEARCH_BATCH:BEGIN\t1\n"
            + '{"type":"summary","data":{}}\n'
            + "@@ORDIVON_SEARCH_BATCH:END\t1\t1\n"
        )
        value["stderrTail"] = ""
        return value


class CrashOnceBatchRuntime(BatchRuntime):
    def __init__(self) -> None:
        super().__init__("direct")
        self.crash_once = True

    def call_tool(self, name, arguments):
        if name == "workspace.exec" and self.crash_once:
            self.calls.append((name, arguments))
            self.workspace_exec_count += 1
            request_id = arguments.get("clientRequestId")
            assert isinstance(request_id, str)
            self.client_request_id = request_id
            self.crash_once = False
            raise KeyboardInterrupt("simulated process loss after Runtime admission")
        return super().call_tool(name, arguments)


class SearchWorkspaceBatchTests(unittest.TestCase):
    def initialize(self, root: Path, suffix: str, runtime: FakeRuntime):
        run_contract = contract(suffix)
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        clock = FixedClock()
        continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
        bridge = SQLiteHarnessRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
        )
        state = bound_state()
        bridge.bind_run_state(
            messages=state.messages,
            observations=state.observations,
            remaining_budget=state.remaining_budget,
            requested_model_id=state.requested_model_id,
            effective_model_id=state.effective_model_id,
            active_elapsed_ms=state.active_elapsed_ms,
        )
        return store, clock, run_contract, continuity, bridge

    def test_batch_search_uses_one_runtime_job_and_preserves_query_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = BatchRuntime()
            store, _, _, _, bridge = self.initialize(Path(directory) / "state", "batch-direct", runtime)
            try:
                observation = bridge.execute(batch_call(), step_id="turn-1-batch")
                self.assertEqual(runtime.workspace_exec_count, 1)
                request = next(arguments for name, arguments in runtime.calls if name == "workspace.exec")
                self.assertEqual(request["execution"]["executable"], "/bin/bash")
                self.assertIn("/usr/bin/awk", request["execution"]["args"][1])
                self.assertNotIn("ToolProgram", request["execution"]["args"][1])
                self.assertIn("ToolProgram", request["execution"]["args"])
                self.assertIn("__NO_SUCH_LITERAL__", request["execution"]["args"])
                results = observation.structured_content["queryResults"]
                self.assertEqual([row["status"] for row in results], ["matched", "no_hits"])
                self.assertEqual([row["exitCode"] for row in results], [0, 1])
                self.assertEqual([row["matchCount"] for row in results], [1, 0])
                self.assertEqual(observation.structured_content["matchCount"], 1)
                self.assertEqual(observation.runtime_job_ref, runtime.job_id)
            finally:
                store.close()

    def test_batch_search_hard_error_remains_observed_per_query_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = BatchRuntime(hard_error=True)
            store, _, _, _, bridge = self.initialize(Path(directory) / "state", "batch-error", runtime)
            try:
                observation = bridge.execute(batch_call("hard"), step_id="turn-1-hard")
                self.assertEqual(observation.status, "observed")
                self.assertEqual(observation.structured_content["executionDisposition"], "failed")
                results = observation.structured_content["queryResults"]
                self.assertEqual([row["status"] for row in results], ["error", "error"])
                self.assertEqual([row["exitCode"] for row in results], [2, 2])
                self.assertTrue(all("source path is unavailable" in row["errorSummary"] for row in results))
            finally:
                store.close()

    def test_batch_response_loss_reconciles_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = BatchRuntime("loss")
            store, _, _, continuity, bridge = self.initialize(Path(directory) / "state", "batch-loss", runtime)
            try:
                observation = bridge.execute(batch_call("loss"), step_id="turn-1-loss")
                self.assertTrue(observation.reconciled)
                self.assertEqual(runtime.workspace_exec_count, 1)
                self.assertEqual([row["status"] for row in observation.structured_content["queryResults"]], ["matched", "no_hits"])
                self.assertEqual([name for name, _ in runtime.calls].count("workspace.exec"), 1)
                self.assertIn("task.list", [name for name, _ in runtime.calls])
                self.assertIn("task.observe", [name for name, _ in runtime.calls])
                retained = continuity.load_current_tool_step()
                self.assertTrue(retained.receipt.reconciled)
                self.assertEqual(retained.receipt.status.value, "observed")
            finally:
                store.close()

    def test_exact_recovered_call_restores_batch_metadata_after_process_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = CrashOnceBatchRuntime()
            store, clock, run_contract, continuity, bridge = self.initialize(root, "batch-restart", runtime)
            call = batch_call("restart")
            try:
                with self.assertRaises(KeyboardInterrupt):
                    bridge.execute(call, step_id="turn-1-restart")
                self.assertEqual(runtime.workspace_exec_count, 1)
                active = continuity.load_current_tool_step()
                self.assertIsNone(active.receipt)
            finally:
                store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore.open(
                    reopened_store, run_contract.harness_run_id, clock_ms=clock
                )
                fresh = SQLiteHarnessRuntimeBridge(
                    run_contract,
                    reopened,
                    execution_binding(run_contract, reopened),
                    runtime,
                )
                control = ExecutionControl(
                    CancellationToken(monotonic_ms=clock),
                    RunDeadline.after(10_000, monotonic_ms=clock),
                )
                observation = fresh.reconcile_current_tool_step_with_call(call, control=control)
                self.assertTrue(observation.reconciled)
                self.assertEqual(runtime.workspace_exec_count, 1)
                self.assertEqual(observation.structured_content["queries"], ["ToolProgram", "__NO_SUCH_LITERAL__"])
                self.assertEqual([row["status"] for row in observation.structured_content["queryResults"]], ["matched", "no_hits"])

    def test_batch_physical_wrapper_globally_caps_each_query_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = BatchRuntime()
            store, _, _, _, bridge = self.initialize(
                Path(directory) / "state", "batch-cap", runtime
            )
            call = AgentToolCall(
                tool_call_id="tool-call:cap",
                name="search_workspace",
                arguments={
                    "queries": ["alpha", "beta"],
                    "relativePath": "src",
                    "maxMatchesPerQuery": 5,
                },
            )
            try:
                bridge.execute(call, step_id="turn-1-cap")
                request = next(
                    arguments
                    for name, arguments in runtime.calls
                    if name == "workspace.exec"
                )
            finally:
                store.close()

            physical_root = Path(directory) / "physical"
            (physical_root / "src").mkdir(parents=True)
            (physical_root / "src" / "many.txt").write_text(
                "alpha beta\n" * 100, encoding="utf-8"
            )
            execution = request["execution"]
            completed = subprocess.run(
                [execution["executable"], *execution["args"]],
                cwd=physical_root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            counts = [0, 0]
            exit_codes: list[int | None] = [None, None]
            active: int | None = None
            for line in completed.stdout.splitlines():
                if line.startswith("@@ORDIVON_SEARCH_BATCH:BEGIN\t"):
                    active = int(line.split("\t")[1])
                    continue
                if line.startswith("@@ORDIVON_SEARCH_BATCH:END\t"):
                    _, index, code = line.split("\t")
                    exit_codes[int(index)] = int(code)
                    active = None
                    continue
                if active is not None and '"type":"match"' in line:
                    counts[active] += 1
            self.assertEqual(counts, [5, 5])
            self.assertEqual(exit_codes, [0, 0])
            self.assertLess(len(completed.stdout.encode("utf-8")), 16_384)

    def test_batch_runtime_stdout_truncation_becomes_unknown(self) -> None:
        class TruncatedBatchRuntime(BatchRuntime):
            def terminal(self):
                value = super().terminal()
                value["stdoutTruncated"] = True
                value["stdoutTail"] = (
                    "@@ORDIVON_SEARCH_BATCH:BEGIN\t0\n" + match_event() + "\n"
                )
                return value

        with tempfile.TemporaryDirectory() as directory:
            runtime = TruncatedBatchRuntime()
            store, _, _, _, bridge = self.initialize(
                Path(directory) / "state", "batch-truncated", runtime
            )
            try:
                observation = bridge.execute(
                    batch_call("truncated"), step_id="turn-1-truncated"
                )
                self.assertEqual(observation.status, "unknown")
                self.assertIn(
                    "truncated", observation.structured_content["reason"]
                )
                self.assertNotIn("queryResults", observation.structured_content)
                self.assertEqual(runtime.workspace_exec_count, 1)
            finally:
                store.close()

    def test_batch_incomplete_framing_becomes_unknown(self) -> None:
        class IncompleteBatchRuntime(BatchRuntime):
            def terminal(self):
                value = super().terminal()
                value["stdoutTail"] = (
                    "@@ORDIVON_SEARCH_BATCH:BEGIN\t0\n"
                    + match_event()
                    + "\n@@ORDIVON_SEARCH_BATCH:END\t0\t0\n"
                    + "@@ORDIVON_SEARCH_BATCH:BEGIN\t1\n"
                )
                return value

        with tempfile.TemporaryDirectory() as directory:
            runtime = IncompleteBatchRuntime()
            store, _, _, _, bridge = self.initialize(
                Path(directory) / "state", "batch-incomplete", runtime
            )
            try:
                observation = bridge.execute(
                    batch_call("incomplete"), step_id="turn-1-incomplete"
                )
                self.assertEqual(observation.status, "unknown")
                self.assertIn(
                    "framing", observation.structured_content["reason"]
                )
                self.assertEqual(runtime.workspace_exec_count, 1)
            finally:
                store.close()

    def test_batch_argument_bounds_fail_before_runtime_dispatch(self) -> None:
        cases = (
            {"query": "one", "queries": ["two"]},
            {},
            {"queries": [str(index) for index in range(9)]},
            {"queries": ["one"], "maxMatches": 5},
            {"query": "one", "maxMatchesPerQuery": 5},
            {"queries": ["x" * 2_049]},
            {"queries": ["one"], "maxMatchesPerQuery": 26},
        )
        for index, arguments in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                runtime = BatchRuntime()
                store, _, _, _, bridge = self.initialize(
                    Path(directory) / "state", f"batch-invalid-{index}", runtime
                )
                try:
                    call = AgentToolCall(
                        tool_call_id=f"tool-call:invalid-{index}",
                        name="search_workspace",
                        arguments=arguments,
                    )
                    with self.assertRaises(ToolBridgeError):
                        bridge.execute(call, step_id=f"turn-invalid-{index}")
                    self.assertEqual(runtime.workspace_exec_count, 0)
                finally:
                    store.close()


if __name__ == "__main__":
    unittest.main()

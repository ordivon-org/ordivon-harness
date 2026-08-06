from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from anc_canonical import JsonValue, canonical_digest
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget, RunStopCode
from ordivon_harness.ordivon.model import AgentToolCall, ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_repository_repair_bridge import (
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_DEFINITIONS,
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST,
    SQLiteHarnessRepositoryRepairEditRuntimeBridge,
)
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.tool_errors import ToolBridgeError, ToolBridgeErrorKind
from ordivon_harness.protocol import HarnessRecoveryConsequence
from ordivon_harness.run_state import HarnessRunState
from ordivon_harness.runtime_port import HarnessRuntimeClientError
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from tests.test_p1_repository_repair_runtime_bridge import (
    SOURCE,
    FakeRuntime,
    FixedClock,
    complete_turn,
    contract,
    execution_binding,
    tool_turn,
)


class EditFakeRuntime(FakeRuntime):
    def __init__(self, *, source: str = SOURCE, patch_loss: bool = False) -> None:
        super().__init__(patch_loss=patch_loss)
        self.source = source
        self.changed_paths: list[str] = []
        self.patch_diff = ""

    @property
    def source_digest(self) -> str:
        return canonical_digest({"content": self.source})

    def call_tool(self, name: str, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if name == "workspace.read":
            if arguments.get("mode") != "FULL" or arguments.get("offset") != 0:
                raise AssertionError(
                    "V2 preflight read must use Runtime FULL mode at offset zero"
                )
            self.calls.append((name, arguments))
            return {"schemaVersion": 1, "content": self.source, "truncated": False, "digest": self.source_digest}
        if name == "workspace.patch":
            self.calls.append((name, arguments))
            self.patch_count += 1
            request_id = arguments.get("clientRequestId")
            assert isinstance(request_id, str)
            self.patch_request_id = request_id
            files = arguments.get("files")
            assert isinstance(files, list) and files
            self.changed_paths = [item["relativePath"] for item in files if isinstance(item, dict) and isinstance(item.get("relativePath"), str)]
            self.patch_diff = "\n".join(f"changed {path}" for path in self.changed_paths)
            if self.patch_loss:
                raise HarnessRuntimeClientError("injected Patch response loss after commit")
            return {"schemaVersion": 1, "state": "applied", "clientRequestId": request_id, "changedPaths": list(self.changed_paths), "diff": self.patch_diff}
        if name == "workspace.patch.get":
            self.calls.append((name, arguments))
            assert arguments.get("clientRequestId") == self.patch_request_id
            return {"schemaVersion": 1, "state": "applied", "clientRequestId": self.patch_request_id, "changedPaths": list(self.changed_paths), "diff": self.patch_diff}
        return super().call_tool(name, arguments)


def edit_contract(suffix: str):
    return replace(
        contract(suffix),
        harness_implementation_id="ordivon-harness@repository-repair-edit-v2",
        tool_catalog_digest=INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST,
        tool_grant_digest=INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST,
        budget={"maxModelCalls": 8, "maxToolCalls": 6, "maxWallTimeMs": 60_000},
    )


def edit_state() -> HarnessRunState:
    return HarnessRunState(
        messages=({"role": "user", "content": "repair allocation.py"},),
        observations=(),
        remaining_budget={"modelCalls": 8, "modelRetries": 1, "toolCalls": 6, "wallTimeMs": 60_000, "observationOnlyTurns": 6, "noProgressTurns": 6},
        requested_model_id=ScriptedTurnAdapter.model_id,
        effective_model_id=None,
        active_elapsed_ms=0,
    )


def edit_budget() -> RunBudget:
    return RunBudget(max_model_calls=8, max_tool_calls=6, max_observation_bytes=262_144, max_wall_time_ms=60_000, max_total_tokens=100_000, max_model_retries=1)


class RepositoryRepairEditRuntimeBridgeTests(unittest.TestCase):
    def initialize(self, root: Path, suffix: str, runtime: EditFakeRuntime):
        run_contract = edit_contract(suffix)
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        clock = FixedClock()
        continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=clock)
        bridge = SQLiteHarnessRepositoryRepairEditRuntimeBridge(run_contract, continuity, execution_binding(run_contract, continuity), runtime)
        return store, clock, run_contract, continuity, bridge

    @staticmethod
    def bind(bridge: SQLiteHarnessRepositoryRepairEditRuntimeBridge) -> None:
        state = edit_state()
        bridge.bind_run_state(messages=state.messages, observations=state.observations, remaining_budget=state.remaining_budget, requested_model_id=state.requested_model_id, effective_model_id=state.effective_model_id, active_elapsed_ms=state.active_elapsed_ms)

    def test_v1_digests_remain_frozen_and_v2_is_distinct(self) -> None:
        self.assertEqual(INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST, "sha256:3e2f2db6f5d8f453dff92ff0c7846002df3d4adfa73073693e4bb5c036deb8b7")
        self.assertEqual(INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST, "sha256:8f1ba6554fa72f450bd3d880784bc965c516948f26c62688cbf6fe85a113ad65")
        self.assertNotEqual(INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST, INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST)
        self.assertNotEqual(INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST, INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST)
        self.assertEqual([item.name for item in INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_DEFINITIONS], ["read_workspace", "replace_workspace_text", "create_workspace_file", "run_check", "diff_workspace"])

    def test_exact_replace_derives_unicode_range_and_durable_patch(self) -> None:
        runtime = EditFakeRuntime(source="éé return []\n")
        with tempfile.TemporaryDirectory() as directory:
            store, _, _, continuity, bridge = self.initialize(Path(directory) / "state", "replace", runtime)
            self.bind(bridge)
            observation = bridge.execute(AgentToolCall("tool-call:p2-repair:replace", "replace_workspace_text", {"relativePath": "allocation.py", "expectedDigest": runtime.source_digest, "expectedText": "return []", "replacement": "return list(items)", "maxDiffBytes": 65_536}), step_id="turn-1-tool-replace")
            self.assertEqual(observation.status, "observed")
            self.assertEqual([name for name, _ in runtime.calls], ["workspace.read", "workspace.patch"])
            request = runtime.calls[1][1]
            self.assertEqual(
                request["workspaceId"],
                execution_binding(edit_contract("replace"), continuity).workspace_ref,
            )
            edit = request["files"][0]["edits"][0]
            self.assertEqual(edit["range"]["start"], {"line": 1, "column": 3})
            self.assertEqual(edit["range"]["end"], {"line": 1, "column": 12})
            retained = continuity.load_current_tool_step()
            self.assertEqual(retained.intent.runtime_operation, "workspace.patch")
            self.assertEqual(retained.intent.recovery_consequence, HarnessRecoveryConsequence.WORKSPACE_CHANGE_POSSIBLE)
            self.assertEqual(retained.intent.client_request_id, request["clientRequestId"])
            store.close()


    def test_create_completion_file_uses_zero_length_durable_patch(self) -> None:
        runtime = EditFakeRuntime()
        with tempfile.TemporaryDirectory() as directory:
            store, _, _, continuity, bridge = self.initialize(Path(directory) / "state", "create", runtime)
            self.bind(bridge)
            content = '{"schemaVersion":1,"status":"complete"}\n'
            observation = bridge.execute(AgentToolCall("tool-call:p2-repair:create", "create_workspace_file", {"relativePath": "artifacts/completion.json", "content": content}), step_id="turn-1-tool-create")
            self.assertEqual(observation.status, "observed")
            self.assertEqual([name for name, _ in runtime.calls], ["workspace.patch"])
            file = runtime.calls[0][1]["files"][0]
            edit = file["edits"][0]
            self.assertIsNone(file["expectedDigest"])
            self.assertEqual(edit["range"]["start"], {"line": 1, "column": 0})
            self.assertEqual(edit["range"]["end"], {"line": 1, "column": 0})
            self.assertEqual(edit["expectedText"], "")
            self.assertEqual(edit["replacement"], content)
            self.assertEqual(continuity.load_current_tool_step().intent.runtime_operation, "workspace.patch")
            store.close()

    def test_stale_missing_and_duplicate_text_reject_before_patch(self) -> None:
        cases = (
            ("stale", SOURCE, "sha256:" + "a" * 64, "return []", "stale"),
            ("missing", SOURCE, None, "missing text", "not found"),
            ("duplicate", "token token\n", None, "token", "not unique"),
        )
        for suffix, source, digest, expected_text, message in cases:
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                runtime = EditFakeRuntime(source=source)
                store, _, _, _, bridge = self.initialize(Path(directory) / "state", suffix, runtime)
                self.bind(bridge)
                with self.assertRaisesRegex(ToolBridgeError, message) as caught:
                    bridge.execute(AgentToolCall(f"tool-call:p2-repair:{suffix}", "replace_workspace_text", {"relativePath": "allocation.py", "expectedDigest": digest or runtime.source_digest, "expectedText": expected_text, "replacement": "replacement"}), step_id=f"turn-1-tool-{suffix}")
                self.assertEqual(caught.exception.kind, ToolBridgeErrorKind.MODEL_CORRECTABLE)
                self.assertEqual([name for name, _ in runtime.calls], ["workspace.read"])
                self.assertEqual(runtime.patch_count, 0)
                store.close()

    def test_replace_response_loss_reconciles_without_redispatch(self) -> None:
        runtime = EditFakeRuntime(patch_loss=True)
        with tempfile.TemporaryDirectory() as directory:
            store, _, _, continuity, bridge = self.initialize(Path(directory) / "state", "loss", runtime)
            self.bind(bridge)
            observation = bridge.execute(AgentToolCall("tool-call:p2-repair:loss", "replace_workspace_text", {"relativePath": "allocation.py", "expectedDigest": runtime.source_digest, "expectedText": "    return []", "replacement": "    return list(items)"}), step_id="turn-1-tool-loss")
            self.assertEqual(observation.status, "observed")
            self.assertTrue(observation.reconciled)
            self.assertEqual(runtime.patch_count, 1)
            self.assertEqual([name for name, _ in runtime.calls], ["workspace.read", "workspace.patch", "workspace.patch.get"])
            self.assertTrue(continuity.load_current_tool_step().receipt.reconciled)
            store.close()

    def test_edit_tool_path_bindings_fail_before_runtime(self) -> None:
        calls = (
            AgentToolCall("tool-call:p2-repair:replace-completion", "replace_workspace_text", {"relativePath": "artifacts/completion.json", "expectedDigest": "sha256:" + "a" * 64, "expectedText": "old", "replacement": "new"}),
            AgentToolCall("tool-call:p2-repair:create-source", "create_workspace_file", {"relativePath": "allocation.py", "content": "source"}),
        )
        for call in calls:
            with self.subTest(call=call.name), tempfile.TemporaryDirectory() as directory:
                runtime = EditFakeRuntime()
                store, _, _, _, bridge = self.initialize(Path(directory) / "state", call.tool_call_id[-8:], runtime)
                self.bind(bridge)
                with self.assertRaises(ToolBridgeError) as caught:
                    bridge.execute(call, step_id="turn-1-tool-denied")
                self.assertEqual(caught.exception.kind, ToolBridgeErrorKind.AUTHORITY_DENIED)
                self.assertEqual(runtime.calls, [])
                store.close()


    def test_v2_conclusion_requires_both_mutations_and_runtime_evidence(self) -> None:
        runtime = EditFakeRuntime()
        with tempfile.TemporaryDirectory() as directory:
            store, clock, run_contract, continuity, bridge = self.initialize(Path(directory) / "state", "loop", runtime)
            calls = (
                AgentToolCall("tool-call:p2-repair:read", "read_workspace", {"relativePath": "allocation.py", "mode": "FULL"}),
                AgentToolCall("tool-call:p2-repair:replace", "replace_workspace_text", {"relativePath": "allocation.py", "expectedDigest": runtime.source_digest, "expectedText": "    return []", "replacement": "    return list(items)"}),
                AgentToolCall("tool-call:p2-repair:create", "create_workspace_file", {"relativePath": "artifacts/completion.json", "content": '{"schemaVersion":1,"status":"complete"}\n'}),
                AgentToolCall("tool-call:p2-repair:check", "run_check", {"checkId": "visible-tests", "waitMs": 30_000}),
                AgentToolCall("tool-call:p2-repair:diff", "diff_workspace", {"maxBytes": 65_536}),
                AgentToolCall("tool-call:p2-repair:reread", "read_workspace", {"relativePath": "allocation.py", "mode": "FULL"}),
            )
            turns = tuple(tool_turn("loop", sequence, call) for sequence, call in enumerate(calls, start=1)) + (complete_turn("loop"),)
            state = edit_state()
            result = OrdivonAgentLoop(ScriptedTurnAdapter(turns), bridge, budget=edit_budget(), clock_ms=clock, monotonic_ms=clock).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=state.messages,
            )
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertTrue(result.candidate_completed)
            self.assertEqual(result.tool_calls, 6)
            self.assertEqual([name for name, _ in runtime.calls], ["workspace.read", "workspace.read", "workspace.patch", "workspace.patch", "workspace.exec", "workspace.diff", "workspace.read"])
            self.assertEqual(runtime.patch_count, 2)
            store.close()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.execution_binding import (
    HarnessExecutionBinding,
    HarnessRuntimeReference,
    build_harness_workspace_exec_request_from_binding,
)
from ordivon_harness.ordivon.model import AgentToolCall
from ordivon_harness.ordivon.runtime_lowering import lower_runtime_tool

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64


def binding() -> HarnessExecutionBinding:
    return HarnessExecutionBinding(
        harness_run_id="harness-run:p0-execution-binding-001",
        workspace_ref="workspace:p0-execution-binding-001",
        assignment_id="assignment:external:p0-execution-binding-001",
        assignment_generation=1,
        assignment_digest=DIGEST_A,
        runtime_binding_digest=DIGEST_B,
        tool_catalog_digest=DIGEST_C,
        tool_grant_digest=DIGEST_D,
        deadline_ms=20_000,
        runtime_references=(
            HarnessRuntimeReference(
                namespace="ordivon.harness",
                reference_type="harness_run",
                reference_id="harness-run:p0-execution-binding-001",
                generation="1",
                digest=DIGEST_B,
            ),
            HarnessRuntimeReference(
                namespace="ordivon.harness",
                reference_type="run_contract",
                reference_id="harness-run-contract:p0-execution-binding-001",
                generation="1",
                digest=DIGEST_A,
            ),
            HarnessRuntimeReference(
                namespace="ordivon.harness",
                reference_type="tool_grant",
                reference_id="tool-grant:p0-execution-binding-001",
                generation="1",
                digest=DIGEST_D,
            ),
        ),
    )


class HarnessExecutionBindingTests(unittest.TestCase):
    def test_round_trip_digest_and_request_identity_are_deterministic(self) -> None:
        value = binding()
        self.assertEqual(HarnessExecutionBinding.from_dict(value.to_dict()), value)
        self.assertEqual(
            HarnessExecutionBinding.from_dict(value.to_dict()).digest,
            value.digest,
        )
        self.assertEqual(
            value.client_request_id("turn-1-tool-1"),
            binding().client_request_id("turn-1-tool-1"),
        )
        self.assertNotEqual(
            value.client_request_id("turn-1-tool-1"),
            value.client_request_id("turn-1-tool-2"),
        )

    def test_independent_workspace_exec_request_has_only_harness_references(self) -> None:
        request = build_harness_workspace_exec_request_from_binding(
            binding(),
            step_id="turn-1-tool-1",
            executable="/usr/bin/python3",
            args=("-c", "print('p0')"),
            wait_ms=30_000,
        )
        self.assertEqual(request["execution"]["workspaceId"], binding().workspace_ref)
        references = request["execution"]["foreignReferences"]
        self.assertEqual(
            [item["type"] for item in references],
            ["harness_run", "run_contract", "tool_grant"],
        )
        self.assertEqual(
            {item["namespace"] for item in references},
            {"ordivon.harness"},
        )
        rendered = str(request)
        self.assertNotIn("task:", rendered)
        self.assertNotIn("task_attempt", rendered)
        self.assertNotIn("ordivon.host", rendered)

    def test_generic_search_lowering_uses_execution_binding(self) -> None:
        call = AgentToolCall(
            tool_call_id="tool-call:p0-execution-binding-search",
            name="search_workspace",
            arguments={
                "query": "HarnessExecutionBinding",
                "relativePath": "src",
                "maxMatches": 12,
            },
        )
        operation, request, client_request_id = lower_runtime_tool(
            call,
            step_id="turn-1-tool-search",
            execution_binding=binding(),
            tool_grant=None,
            known_job_ids=frozenset(),
            known_artifacts=frozenset(),
        )
        self.assertEqual(operation, "workspace.exec")
        self.assertEqual(client_request_id, request["clientRequestId"])
        self.assertEqual(
            client_request_id,
            binding().client_request_id("turn-1-tool-search"),
        )
        execution = request["execution"]
        self.assertEqual(execution["executable"], "/usr/bin/rg")
        self.assertEqual(execution["workspaceId"], binding().workspace_ref)
        self.assertEqual(
            {item["namespace"] for item in execution["foreignReferences"]},
            {"ordivon.harness"},
        )

    def test_patch_identity_is_binding_and_tool_call_bound(self) -> None:
        value = binding()
        first = value.patch_request_id("turn-1-tool-patch", DIGEST_E)
        self.assertEqual(
            first,
            binding().patch_request_id("turn-1-tool-patch", DIGEST_E),
        )
        self.assertNotEqual(
            first,
            value.patch_request_id(
                "turn-1-tool-patch",
                canonical_digest({"different": True}),
            ),
        )

    def test_references_must_be_unique_and_sorted(self) -> None:
        value = binding().to_dict()
        value["runtimeReferences"] = list(reversed(value["runtimeReferences"]))
        with self.assertRaisesRegex(ValueError, "uniquely sorted"):
            HarnessExecutionBinding.from_dict(value)

    def test_generic_binding_and_lowering_have_no_host_imports(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "ordivon_harness"
        for relative in ("execution_binding.py", "ordivon/runtime_lowering.py"):
            source = (root / relative).read_text(encoding="utf-8")
            for forbidden in (
                "ordivon_host",
                "_host_compat",
                "CommittedHarnessAssignment",
                "HostHarnessRunStore",
            ):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

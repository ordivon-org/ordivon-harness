#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import replace
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from anc_canonical import JsonValue, canonical_digest
from ordivon_host import EventKind, HostKernel, HostStorage, StateRef, TaskState
from ordivon_host.cognition import BlockKind, ContextBlock, Freshness
from ordivon_host.effects import ArtifactRef
from ordivon_host.runtime import McpRuntimeClient
from ordivon_harness import (
    CompletionMode,
    GrantedExecutionCheck,
    HarnessHost,
    HarnessRunPlan,
    HarnessRunner,
    TaskContract,
    ToolGrant,
)
from ordivon_harness.ordivon import (
    DEFAULT_DEEPSEEK_SECRET_PATH,
    DeepSeekSettings,
    DeepSeekTurnAdapter,
    RunBudget,
    UrllibDeepSeekTransport,
    ordivon_harness_manifest,
)

TASK_ID = "task:host-harness-provenance-repair-001"
GOAL_ID = "goal:host-harness-dogfood"
FRONTIER = "node:host-harness-provenance-repair-001:work"
TARGET_PATH = "scripts/live_ordivon_harness_oh4_deepseek.py"
REJECTION_TASK_ID = "task:host-harness-rejection-classification-repair-001"
REJECTION_IMPLEMENTATION_TASK_ID = (
    "task:host-harness-rejection-classification-implementation-001"
)
REJECTION_FRONTIER = "node:host-harness-rejection-classification-repair-001:work"
REJECTION_TARGET_PATH = "src/ordivon_harness/ordivon/tools.py"
REJECTION_TEST_PATH = "tests/test_ordivon_harness_oh2.py"
HANDOFF_TASK_ID = "task:host-operator-handoff-issue-2-001"
HANDOFF_FRONTIER = "node:host-operator-handoff-issue-2-001:work"
HANDOFF_PATHS = (
    "src/ordivon_host/handoff.py",
    "src/ordivon_host/cli.py",
    "tests/test_handoff.py",
    "tests/test_cli.py",
    "README.md",
)
ISSUE4_TASK_ID = "task:host-harness-historical-tool-step-issue-4-001"
ISSUE4_FRONTIER = "node:host-harness-historical-tool-step-issue-4-001:work"
ISSUE4_PATHS = (
    "ordivon-host/src/ordivon_host/journal/sqlite.py",
    "ordivon-host/src/ordivon_host/storage.py",
    "ordivon-host/src/ordivon_host/extensions.py",
    "ordivon-host/tests/test_storage.py",
    "ordivon-harness/src/ordivon_harness/ordivon/run_store.py",
    "ordivon-harness/tests/test_ordivon_harness_p0_p1.py",
    "ordivon-harness/scripts/live_host_harness_cancel_stress.py",
)
ISSUE7_TASK_ID = "task:harness-read-workspace-location-issue-7-001"
ISSUE7_FRONTIER = "node:harness-read-workspace-location-issue-7-001:work"
ISSUE7_PATHS = (
    "src/ordivon_harness/ordivon/tools.py",
    "tests/test_ordivon_harness_oh2.py",
)
ISSUE7_SOLUTION_ROOT = Path(
    "/root/.local/share/ordivon/fixtures/harness-issue7-solution"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a retained Host/Harness dogfood repair trial through DeepSeek."
    )
    parser.add_argument(
        "--source-repo",
        type=Path,
        default=Path("/root/projects/ordivon-harness"),
    )
    parser.add_argument("--source-revision")
    parser.add_argument("--runtime-endpoint")
    parser.add_argument(
        "--deepseek-secret",
        type=Path,
        default=DEFAULT_DEEPSEEK_SECRET_PATH,
    )
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--evidence-out", type=Path, required=True)
    parser.add_argument("--max-model-calls", type=int, default=8)
    parser.add_argument("--max-tool-calls", type=int, default=16)
    parser.add_argument("--token-hard-limit", type=int, default=262_144)
    parser.add_argument("--max-tool-corrections", type=int, default=6)
    parser.add_argument(
        "--workload",
        choices=(
            "provenance",
            "rejection-classification",
            "rejection-implementation",
            "handoff-issue2",
            "historical-tool-step-issue4",
            "read-location-issue7",
        ),
        default="provenance",
    )
    parser.add_argument(
        "--model",
        choices=("deepseek-v4-flash", "deepseek-v4-pro"),
        help="Override only the model identity loaded from the secret file.",
    )
    parser.add_argument(
        "--capture-provider-diagnostics",
        action="store_true",
        help="Retain bounded Provider tool-call diagnostics without credentials.",
    )
    return parser.parse_args()


def _clock_ms() -> int:
    return time.time_ns() // 1_000_000


def _runtime_endpoint(explicit: str | None) -> str:
    if explicit:
        return explicit
    bind = os.environ.get("ORDIVON_BIND", "127.0.0.1:8897")
    return f"http://127.0.0.1:{bind.rsplit(':', 1)[-1]}/mcp"


def _git_revision(repo: Path, revision: str | None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", revision or "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    value = completed.stdout.strip()
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise RuntimeError(f"Git returned an invalid revision: {value!r}")
    return value


def _git_file(repo: Path, revision: str, relative_path: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{relative_path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout


def _excerpt(content: str, start_line: int, end_line: int) -> str:
    lines = content.splitlines()
    return "\n".join(
        f"{number:5d} {lines[number - 1]}"
        for number in range(start_line, min(end_line, len(lines)) + 1)
    )


def _byte_offset(content: str, line: int) -> int:
    return len("".join(content.splitlines(keepends=True)[: line - 1]).encode("utf-8"))


def _file_digest(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _replace_once(content: str, old: str, new: str, *, path: str) -> str:
    if content.count(old) != 1:
        raise RuntimeError(f"handoff patch anchor differs in {path}: {old!r}")
    return content.replace(old, new, 1)


def _handoff_patch_arguments(
    source_repo: Path,
    source_revision: str,
) -> dict[str, JsonValue]:
    replacements: dict[str, tuple[tuple[str, str], ...]] = {
        HANDOFF_PATHS[0]: (
            (
                (
                    "def operator_handoff(storage: HostStorage, task_id: str) "
                    "-> OperatorHandoffCapsule:\n"
                ),
                (
                    "def operator_handoff(\n"
                    "    storage: HostStorage,\n"
                    "    task_id: str,\n"
                    "    *,\n"
                    "    expected_revision: int | None = None,\n"
                    ") -> OperatorHandoffCapsule:\n"
                    "    if expected_revision is not None and (\n"
                    "        type(expected_revision) is not int "
                    "or expected_revision < 1\n"
                    "    ):\n"
                    "        raise ValueError(\n"
                    '            "expected Operator Handoff revision must be a '\
                    'positive integer"\n'
                    "        )\n"
                ),
            ),
            (
                "    snapshot = storage.read_task_event(task_id)\n",
                (
                    "    snapshot = storage.read_task_event(task_id)\n"
                    "    if (\n"
                    "        expected_revision is not None\n"
                    "        and snapshot.projection.revision != expected_revision\n"
                    "    ):\n"
                    "        raise ValueError(\n"
                    '            "stale Operator Handoff revision: "\n'
                    "            f\"expected {expected_revision}, current "
                    "{snapshot.projection.revision}\"\n"
                    "        )\n"
                ),
            ),
        ),
        HANDOFF_PATHS[1]: (
            (
                "from .domain import StaticRepositoryResolver, TaskState\n",
                (
                    "from .domain import StaticRepositoryResolver, TaskState\n"
                    "from .handoff import operator_handoff\n"
                ),
            ),
            (
                '    task_show.add_argument("task_id")\n',
                (
                    '    task_show.add_argument("task_id")\n'
                    '    task_handoff = task_commands.add_parser("handoff")\n'
                    '    task_handoff.add_argument("task_id")\n'
                    '    task_handoff.add_argument("--expected-revision", type=int)\n'
                ),
            ),
            (
                '        if args.task_command == "assess":\n',
                (
                    '        if args.task_command == "handoff":\n'
                    "            capsule = operator_handoff(\n"
                    "                storage,\n"
                    "                args.task_id,\n"
                    "                expected_revision=args.expected_revision,\n"
                    "            )\n"
                    "            return {\n"
                    '                "capsule": capsule.to_dict(),\n'
                    '                "capsuleDigest": capsule.digest,\n'
                    "            }\n"
                    '        if args.task_command == "assess":\n'
                ),
            ),
        ),
        HANDOFF_PATHS[2]: (
            (
                (
                    "                self.assertEqual("
                    "capsule.must_not_repeat_object_digests, ())\n"
                ),
                (
                    "                self.assertEqual("
                    "capsule.must_not_repeat_object_digests, ())\n"
                    "                pinned = operator_handoff(\n"
                    "                    storage,\n"
                    '                    "task:handoff",\n'
                    "                    expected_revision=created.revision + 1,\n"
                    "                )\n"
                    "                self.assertEqual(pinned, capsule)\n"
                    "                with self.assertRaisesRegex(\n"
                    "                    ValueError,\n"
                    "                    r\"stale Operator Handoff revision: "
                    "expected 1, current 2\",\n"
                    "                ):\n"
                    "                    operator_handoff(\n"
                    "                        storage,\n"
                    '                        "task:handoff",\n'
                    "                        expected_revision=created.revision,\n"
                    "                    )\n"
                    "                self.assertEqual(\n"
                    '                    storage.read_task_event("task:handoff")'
                    ".payload_digest,\n"
                    "                    capsule.event_payload_digest,\n"
                    "                )\n"
                ),
            ),
        ),
        HANDOFF_PATHS[3]: (
            (
                "    def test_missing_state_fails_cleanly(self) -> None:\n",
                (
                    "    def test_task_handoff_is_deterministic_and_revision_pinned("
                    "self) -> None:\n"
                    "        with tempfile.TemporaryDirectory() as directory:\n"
                    '            state = Path(directory) / "state"\n'
                    "            with HostStorage(state) as storage:\n"
                    "                storage.record_task_event(\n"
                    '                    event_id="event:cli-handoff:r1",\n'
                    "                    kind=EventKind.TASK_CREATED,\n"
                    '                    payload={"descriptorDigest": "sha256:" '
                    '+ ("a" * 64)},\n'
                    "                    projection=TaskProjection(\n"
                    '                        task_id="task:cli-handoff",\n'
                    '                        goal_id="goal:cli-handoff",\n'
                    "                        state=TaskState.READY,\n"
                    "                        active_node_id=None,\n"
                    '                        ready_frontier=("node:cli-handoff",),\n'
                    "                        revision=1,\n"
                    "                        updated_at_ms=1,\n"
                    "                    ),\n"
                    "                    expected_revision=0,\n"
                    "                )\n"
                    "            arguments = (\n"
                    '                "--state-root", str(state), "task", "handoff",\n'
                    '                "task:cli-handoff", "--expected-revision", "1",\n'
                    "            )\n"
                    "            first_code, first = self.invoke(*arguments)\n"
                    "            second_code, second = self.invoke(*arguments)\n"
                    "            self.assertEqual((first_code, second_code), (0, 0))\n"
                    "            self.assertEqual(first, second)\n"
                    '            self.assertEqual(first["capsule"]["taskRevision"], 1)\n'
                    "            with HostStorage(state) as storage:\n"
                    "                self.assertEqual(\n"
                    '                    storage.read_task_event("task:cli-handoff")'
                    ".projection.revision,\n"
                    "                    1,\n"
                    "                )\n"
                    "            stale_code, stale = self.invoke(\n"
                    '                "--state-root", str(state), "task", "handoff",\n'
                    '                "task:cli-handoff", "--expected-revision", "2",\n'
                    "            )\n"
                    "            self.assertEqual(stale_code, 1)\n"
                    "            self.assertIn(\"expected 2, current 1\", "
                    'stale["message"])\n'
                    "\n"
                    "    def test_missing_state_fails_cleanly(self) -> None:\n"
                ),
            ),
        ),
        HANDOFF_PATHS[4]: (
            (
                (
                    "ordivon-host --state-root /var/lib/ordivon/host "
                    "task assess TASK_ID\n"
                ),
                (
                    "ordivon-host --state-root /var/lib/ordivon/host "
                    "task handoff TASK_ID --expected-revision REVISION\n"
                    "ordivon-host --state-root /var/lib/ordivon/host "
                    "task assess TASK_ID\n"
                ),
            ),
        ),
    }
    files: list[JsonValue] = []
    for relative_path in HANDOFF_PATHS:
        baseline = _git_file(source_repo, source_revision, relative_path)
        desired = baseline
        for old, new in replacements[relative_path]:
            desired = _replace_once(desired, old, new, path=relative_path)
        baseline_lines = baseline.splitlines(keepends=True)
        desired_lines = desired.splitlines(keepends=True)
        edits: list[JsonValue] = []
        for tag, old_start, old_end, new_start, new_end in difflib.SequenceMatcher(
            a=baseline_lines,
            b=desired_lines,
            autojunk=False,
        ).get_opcodes():
            if tag == "equal":
                continue
            edits.append(
                {
                    "range": {
                        "start": {"line": old_start + 1, "column": 0},
                        "end": {"line": old_end + 1, "column": 0},
                    },
                    "expectedText": "".join(baseline_lines[old_start:old_end]),
                    "replacement": "".join(desired_lines[new_start:new_end]),
                }
            )
        files.append(
            {
                "relativePath": relative_path,
                "expectedDigest": _file_digest(baseline),
                "edits": edits,
            }
        )
    return {"files": files, "maxDiffBytes": 262_144}


def _desired_patch_arguments(
    source_repo: Path,
    source_revision: str,
    *,
    desired_root: Path,
    relative_paths: tuple[str, ...],
) -> dict[str, JsonValue]:
    files: list[JsonValue] = []
    for relative_path in relative_paths:
        baseline = _git_file(source_repo, source_revision, relative_path)
        desired = (desired_root / relative_path).read_text(encoding="utf-8")
        baseline_lines = baseline.splitlines(keepends=True)
        desired_lines = desired.splitlines(keepends=True)
        edits: list[JsonValue] = []
        for tag, old_start, old_end, new_start, new_end in difflib.SequenceMatcher(
            a=baseline_lines,
            b=desired_lines,
            autojunk=False,
        ).get_opcodes():
            if tag == "equal":
                continue
            edits.append(
                {
                    "range": {
                        "start": {"line": old_start + 1, "column": 0},
                        "end": {"line": old_end + 1, "column": 0},
                    },
                    "expectedText": "".join(baseline_lines[old_start:old_end]),
                    "replacement": "".join(desired_lines[new_start:new_end]),
                }
            )
        files.append(
            {
                "relativePath": relative_path,
                "expectedDigest": _file_digest(baseline),
                "edits": edits,
            }
        )
    return {"files": files, "maxDiffBytes": 262_144}


def _create_task(
    storage: HostStorage,
    *,
    task_id: str,
    frontier: str,
    workload_id: str,
) -> None:
    HostKernel(
        storage,
        clock_ms=_clock_ms,
        owner_id="host:provenance-repair-task-create",
    ).create_task(
        event_id=f"event:{workload_id}:create",
        kind=EventKind.TASK_CREATED,
        task_id=task_id,
        goal_id=GOAL_ID,
        payload={"workloadId": workload_id},
        frontier=(frontier,),
    )


def _contract(
    workload: str,
    source_ref: str,
    source_revision: str,
    source_digest: str,
) -> TaskContract:
    if workload == "read-location-issue7":
        return TaskContract(
            contract_id="task-contract:harness-read-workspace-location-issue-7-001:v1",
            task_id=ISSUE7_TASK_ID,
            objective={
                "summary": (
                    "Resolve Harness GitHub issue #7 by making the model-facing "
                    "read_workspace location explicitly UTF-8 byte based while "
                    "preserving deterministic compatibility for retained legacy calls."
                ),
                "target": {
                    "kind": "repository-files",
                    "relativePaths": list(ISSUE7_PATHS),
                    "sourceRevision": source_revision,
                },
            },
            acceptance_criteria={
                "checks": [
                    "The model-facing schema and description expose byteOffset, not ambiguous offset.",
                    "A legacy offset-only AgentToolCall still lowers to Runtime workspace.read.",
                    "Supplying byteOffset and offset together is rejected as model-correctable before Runtime dispatch.",
                    "Duplicate-read coverage and cache restoration use the effective byte offset.",
                    "Every observed read includes its effective UTF-8 byte range.",
                    "Non-ASCII content has byte-accurate range coverage.",
                    "Focused and full Harness unittests pass.",
                ]
            },
            constraints=(
                "Change only tools.py and the focused OH2 test module.",
                "Keep Runtime workspace.read arguments unchanged: it still receives offset.",
                "Do not guess whether a number was intended as a line number.",
                "Use patch_workspace for all edits.",
                "Run all three granted checks and inspect the Workspace diff.",
            ),
            resource_refs=(StateRef(ref=source_ref, digest=source_digest),),
            consequence_policy_ref="policy:bounded-source-repair-v1",
        )
    if workload == "historical-tool-step-issue4":
        return TaskContract(
            contract_id=(
                "task-contract:host-harness-historical-tool-step-issue-4-001:v1"
            ),
            task_id=ISSUE4_TASK_ID,
            objective={
                "summary": (
                    "Resolve Harness GitHub issue #4. After harness.run-recorded, "
                    "provide one read-only Harness API that retrieves an exact "
                    "historical Tool Step receipt by Harness Run and Tool Call identity "
                    "without a caller scanning Host journal or CAS internals."
                ),
                "target": {
                    "kind": "cross-repository-files",
                    "relativePaths": list(ISSUE4_PATHS),
                    "sourceRevision": source_revision,
                },
            },
            acceptance_criteria={
                "checks": [
                    "The public query is bound to the exact Harness Run and Tool Call identity.",
                    "Receipt, Intent, Assignment generation, Observation, and Runtime Job links are validated before return.",
                    "A terminal cancelled Run remains queryable after harness.run-recorded.",
                    "A Run with multiple Tool Steps returns the exact requested step.",
                    "load_current_tool_step retains active-reconciliation semantics.",
                    "The live cancellation driver uses the public API and does not scan journal.object_refs.",
                    "Focused Host and Harness unittest checks pass.",
                ]
            },
            constraints=(
                "Use the smallest read-only Host primitive required by the Harness-owned query.",
                "Do not add a generic event query service, transcript replay, database, receipt store, duplicated receipt model, or mutable receipt projection.",
                "Do not change Runtime cancellation semantics.",
                "Use patch_workspace for all changes and remain inside the bounded paths.",
                "Run every granted check and inspect the Workspace diff.",
            ),
            resource_refs=(StateRef(ref=source_ref, digest=source_digest),),
            consequence_policy_ref="policy:bounded-cross-repository-repair-v1",
        )
    if workload == "handoff-issue2":
        return TaskContract(
            contract_id="task-contract:host-operator-handoff-issue-2-001:v1",
            task_id=HANDOFF_TASK_ID,
            objective={
                "summary": (
                    "Resolve GitHub issue #2 by exposing the existing "
                    "operator_handoff projection through a simple read-only CLI. "
                    "The command must return a deterministic capsule plus its digest, "
                    "optionally pin the expected Task revision, and reject a stale "
                    "revision without changing Host state."
                ),
                "target": {
                    "kind": "repository-files",
                    "relativePaths": list(HANDOFF_PATHS),
                    "sourceRevision": source_revision,
                },
            },
            acceptance_criteria={
                "checks": [
                    "One public CLI command exports OperatorHandoffCapsule data and its digest.",
                    "An optional expected revision succeeds only at the current Task revision.",
                    "A stale expected revision fails with the expected and current revisions.",
                    "Repeated reads are deterministic and leave the Task revision unchanged.",
                    "Focused and full Host unittest suites pass.",
                    "Only the bounded handoff, CLI, test, and README files may change.",
                ]
            },
            constraints=(
                "Use the existing OperatorHandoffCapsule and operator_handoff projection.",
                "Do not create a second store, capsule model, or import/write command.",
                "Do not include transcripts, provider secrets, or unrelated artifacts.",
                "Use patch_workspace for all changes.",
                "Run all granted checks and inspect the Workspace diff.",
                "Do not weaken UNKNOWN or no-redispatch semantics.",
            ),
            resource_refs=(StateRef(ref=source_ref, digest=source_digest),),
            consequence_policy_ref="policy:read-only-operator-handoff-v1",
        )
    if workload == "rejection-implementation":
        return TaskContract(
            contract_id=(
                "task-contract:host-harness-rejection-classification-"
                "implementation-001:v1"
            ),
            task_id=REJECTION_IMPLEMENTATION_TASK_ID,
            objective={
                "summary": (
                    f"Make the minimal implementation repair in {REJECTION_TARGET_PATH}. "
                    "At the RuntimeToolRejected handler, classify both commitState "
                    "not_committed and not_started as a rejected ToolObservation. Change "
                    "only that condition; preserve ambiguous-effect handling in the else "
                    "branch."
                ),
                "target": {
                    "kind": "repository-file",
                    "relativePath": REJECTION_TARGET_PATH,
                    "sourceRevision": source_revision,
                },
            },
            acceptance_criteria={
                "checks": [
                    "The condition explicitly accepts not_committed and not_started.",
                    "Ambiguous commit states still flow to _unknown.",
                    "Focused OH2 and OH4 tests pass.",
                    "Only the implementation file is modified.",
                ]
            },
            constraints=(
                "The compiled context is sufficient; do not perform exploratory reads.",
                "Use one patch_workspace call for the one-line condition repair.",
                "Run both granted checks and inspect the Workspace diff.",
                "Do not modify tests or any other file.",
            ),
            resource_refs=(StateRef(ref=source_ref, digest=source_digest),),
            consequence_policy_ref="policy:bounded-source-repair-v1",
        )
    if workload == "rejection-classification":
        return TaskContract(
            contract_id="task-contract:host-harness-rejection-classification-001:v1",
            task_id=REJECTION_TASK_ID,
            objective={
                "summary": (
                    f"Repair {REJECTION_TARGET_PATH}. Runtime rejects invalid requests "
                    "before dispatch with commitState=not_started, but RuntimeToolBridge "
                    "only treats not_committed as a deterministic rejection. This turns "
                    "model-correctable invalid read arguments into runtime_unknown and "
                    "terminates the Run. Treat both explicit no-effect commit states as "
                    "rejected, and add a regression test in "
                    f"{REJECTION_TEST_PATH}."
                ),
                "target": {
                    "kind": "repository-files",
                    "relativePaths": [REJECTION_TARGET_PATH, REJECTION_TEST_PATH],
                    "sourceRevision": source_revision,
                },
            },
            acceptance_criteria={
                "checks": [
                    "commitState=not_started yields a rejected ToolObservation.",
                    "The correction remains model-recoverable instead of runtime_unknown.",
                    "Existing not_committed behavior remains unchanged.",
                    "Focused OH2 and OH4 tests pass.",
                    "Only the implementation and focused test file are modified.",
                ]
            },
            constraints=(
                "Read the implementation and focused tests before editing.",
                "Use patch_workspace for all changes.",
                "Add a focused regression test for commitState=not_started.",
                "Run both granted checks and inspect the Workspace diff.",
                "Do not weaken effect-unknown handling for ambiguous commit states.",
                "Use the compiled excerpts and targeted byte offsets; do not read either file in FULL mode.",
            ),
            resource_refs=(StateRef(ref=source_ref, digest=source_digest),),
            consequence_policy_ref="policy:bounded-source-repair-v1",
        )
    return TaskContract(
        contract_id="task-contract:host-harness-provenance-repair-001:v1",
        task_id=TASK_ID,
        objective={
            "summary": (
                f"Repair {TARGET_PATH}. Its --source-repo default is ordivon-harness, "
                "but both the TaskContract resource ref and Host Assignment source_ref "
                "are hard-coded as repository:ordivon-host@<revision>. Derive one "
                "repository source ref from the actual source_repo identity and revision, "
                "then use that exact value in both places."
            ),
            "target": {
                "kind": "repository-file",
                "relativePath": TARGET_PATH,
                "sourceRevision": source_revision,
            },
        },
        acceptance_criteria={
            "checks": [
                "The hard-coded repository:ordivon-host@ provenance is absent.",
                "One source ref derived from source_repo and source_revision is used by both TaskContract and Host Assignment.",
                "The script compiles and the focused provenance check passes.",
                "Only the target script is modified.",
            ]
        },
        constraints=(
            "Read the target before editing it.",
            "Use patch_workspace for the repair.",
            "Run both granted checks and inspect the Workspace diff.",
            "Do not change tests or any file other than the target.",
            "Do not invent completion or evidence identities.",
        ),
        resource_refs=(StateRef(ref=source_ref, digest=source_digest),),
        consequence_policy_ref="policy:bounded-source-repair-v1",
    )


def _grant(workload: str) -> ToolGrant:
    python = "/root/projects/ordivon-harness/.venv/bin/python"
    if workload == "read-location-issue7":
        pythonpath = "src:/root/projects/ordivon-host/src"
        return ToolGrant(
            tool_grant_id="tool-grant:harness-read-workspace-location-issue-7-001:v1",
            allowed_tools=(
                "read_workspace",
                "search_workspace",
                "patch_workspace",
                "diff_workspace",
                "run_check",
                "observe_job",
                "read_artifact",
            ),
            read_path_rules=ISSUE7_PATHS,
            mutate_path_rules=ISSUE7_PATHS,
            execution_checks=(
                GrantedExecutionCheck(
                    check_id="check:read-location-contract",
                    executable="/usr/bin/python3",
                    args=(
                        "-c",
                        (
                            "from pathlib import Path; "
                            "p=Path('src/ordivon_harness/ordivon/tools.py').read_text(); "
                            "t=Path('tests/test_ordivon_harness_oh2.py').read_text(); "
                            "assert 'byteOffset' in p; "
                            "assert 'effectiveByteRange' in p; "
                            "assert 'model_correctable' in t; "
                            "assert 'legacy' in t.lower(); "
                            "assert 'non-ascii' in t.lower() or 'utf-8' in t.lower()"
                        ),
                    ),
                    timeout_ms=60_000,
                ),
                GrantedExecutionCheck(
                    check_id="check:read-location-focused",
                    executable=python,
                    args=(
                        "-m",
                        "unittest",
                        "-v",
                        "tests.test_ordivon_harness_oh2",
                    ),
                    env=(("PYTHONPATH", pythonpath),),
                    timeout_ms=180_000,
                ),
                GrantedExecutionCheck(
                    check_id="check:read-location-full",
                    executable=python,
                    args=("-m", "unittest", "discover", "-s", "tests"),
                    env=(("PYTHONPATH", pythonpath),),
                    timeout_ms=300_000,
                ),
            ),
        )
    if workload == "historical-tool-step-issue4":
        pythonpath = (
            "ordivon-harness/src:ordivon-harness/tests:"
            "ordivon-host/src:ordivon-host/tests:"
            "/root/projects/ordivon-harness/.venv/lib/python3.12/site-packages"
        )
        return ToolGrant(
            tool_grant_id=(
                "tool-grant:host-harness-historical-tool-step-issue-4-001:v1"
            ),
            allowed_tools=(
                "read_workspace",
                "search_workspace",
                "patch_workspace",
                "diff_workspace",
                "run_check",
                "observe_job",
                "read_artifact",
            ),
            read_path_rules=ISSUE4_PATHS,
            mutate_path_rules=ISSUE4_PATHS,
            execution_checks=(
                GrantedExecutionCheck(
                    check_id="check:historical-tool-step-compile",
                    executable=python,
                    args=("-m", "py_compile", *ISSUE4_PATHS),
                    env=(("PYTHONPATH", pythonpath),),
                    timeout_ms=120_000,
                ),
                GrantedExecutionCheck(
                    check_id="check:historical-tool-step-host",
                    executable=python,
                    args=(
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        "ordivon-host/tests",
                        "-p",
                        "test_storage.py",
                    ),
                    env=(("PYTHONPATH", pythonpath),),
                    timeout_ms=180_000,
                ),
                GrantedExecutionCheck(
                    check_id="check:historical-tool-step-harness",
                    executable=python,
                    args=(
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        "ordivon-harness/tests",
                        "-p",
                        "test_ordivon_harness_p0_p1.py",
                    ),
                    env=(("PYTHONPATH", pythonpath),),
                    timeout_ms=240_000,
                ),
            ),
        )
    if workload == "handoff-issue2":
        pythonpath = (
            "src:/root/projects/ordivon-harness/.venv/lib/python3.12/site-packages"
        )
        return ToolGrant(
            tool_grant_id="tool-grant:host-operator-handoff-issue-2-001:v1",
            allowed_tools=(
                "read_workspace",
                "search_workspace",
                "patch_workspace",
                "diff_workspace",
                "run_check",
                "observe_job",
                "read_artifact",
            ),
            read_path_rules=HANDOFF_PATHS,
            mutate_path_rules=HANDOFF_PATHS,
            execution_checks=(
                GrantedExecutionCheck(
                    check_id="check:handoff-issue2-contract",
                    executable="/usr/bin/python3",
                    args=(
                        "-c",
                        (
                            "from pathlib import Path; "
                            "h=Path('src/ordivon_host/handoff.py').read_text(); "
                            "c=Path('src/ordivon_host/cli.py').read_text(); "
                            "t=(Path('tests/test_handoff.py').read_text()+"
                            "Path('tests/test_cli.py').read_text()); "
                            "r=Path('README.md').read_text(); "
                            "assert 'expected_revision' in h; "
                            "assert 'stale Operator Handoff revision' in h; "
                            "assert 'task_commands.add_parser(\"handoff\")' in c; "
                            "assert 'capsuleDigest' in c; "
                            "assert '--expected-revision' in c; "
                            "assert 'deterministic' in t; "
                            "assert 'task handoff' in r"
                        ),
                    ),
                    timeout_ms=60_000,
                ),
                GrantedExecutionCheck(
                    check_id="check:handoff-issue2-focused",
                    executable=python,
                    args=(
                        "-m",
                        "unittest",
                        "-v",
                        "tests.test_handoff",
                        "tests.test_cli",
                    ),
                    env=(("PYTHONPATH", pythonpath),),
                    timeout_ms=120_000,
                ),
                GrantedExecutionCheck(
                    check_id="check:handoff-issue2-full",
                    executable=python,
                    args=("-m", "unittest", "discover", "-s", "tests"),
                    env=(("PYTHONPATH", pythonpath),),
                    timeout_ms=240_000,
                ),
            ),
        )
    if workload == "rejection-implementation":
        return ToolGrant(
            tool_grant_id=(
                "tool-grant:host-harness-rejection-classification-"
                "implementation-001:v1"
            ),
            allowed_tools=(
                "patch_workspace",
                "diff_workspace",
                "run_check",
                "observe_job",
                "read_artifact",
            ),
            mutate_path_rules=(REJECTION_TARGET_PATH,),
            execution_checks=(
                GrantedExecutionCheck(
                    check_id="check:rejection-implementation-compile",
                    executable=python,
                    args=("-m", "py_compile", REJECTION_TARGET_PATH),
                    env=(("PYTHONPATH", "src"),),
                    timeout_ms=60_000,
                ),
                GrantedExecutionCheck(
                    check_id="check:rejection-implementation-tests",
                    executable=python,
                    args=(
                        "-m",
                        "unittest",
                        "-v",
                        "tests.test_ordivon_harness_oh2",
                        "tests.test_ordivon_harness_oh4",
                    ),
                    env=(("PYTHONPATH", "src"),),
                    timeout_ms=180_000,
                ),
            ),
        )
    if workload == "rejection-classification":
        return ToolGrant(
            tool_grant_id="tool-grant:host-harness-rejection-classification-001:v1",
            allowed_tools=(
                "read_workspace",
                "patch_workspace",
                "diff_workspace",
                "run_check",
                "observe_job",
                "read_artifact",
            ),
            read_path_rules=(
                REJECTION_TARGET_PATH,
                REJECTION_TEST_PATH,
                "tests/test_ordivon_harness_oh4.py",
            ),
            mutate_path_rules=(REJECTION_TARGET_PATH, REJECTION_TEST_PATH),
            execution_checks=(
                GrantedExecutionCheck(
                    check_id="check:rejection-classification-compile",
                    executable=python,
                    args=(
                        "-m",
                        "py_compile",
                        REJECTION_TARGET_PATH,
                        REJECTION_TEST_PATH,
                    ),
                    env=(("PYTHONPATH", "src"),),
                    timeout_ms=60_000,
                ),
                GrantedExecutionCheck(
                    check_id="check:rejection-classification-tests",
                    executable=python,
                    args=(
                        "-m",
                        "unittest",
                        "-v",
                        "tests.test_ordivon_harness_oh2",
                        "tests.test_ordivon_harness_oh4",
                    ),
                    env=(("PYTHONPATH", "src"),),
                    timeout_ms=180_000,
                ),
            ),
        )
    return ToolGrant(
        tool_grant_id="tool-grant:host-harness-provenance-repair-001:v1",
        allowed_tools=(
            "read_workspace",
            "patch_workspace",
            "diff_workspace",
            "run_check",
            "observe_job",
            "read_artifact",
        ),
        read_path_rules=(
            TARGET_PATH,
            "tests/test_ordivon_harness_oh4.py",
        ),
        mutate_path_rules=(TARGET_PATH,),
        execution_checks=(
            GrantedExecutionCheck(
                check_id="check:provenance-repair-compile",
                executable=python,
                args=("-m", "py_compile", TARGET_PATH),
                env=(("PYTHONPATH", "src"),),
                timeout_ms=60_000,
            ),
            GrantedExecutionCheck(
                check_id="check:provenance-repair-static",
                executable="/usr/bin/python3",
                args=(
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"p=Path({TARGET_PATH!r}); "
                        "s=p.read_text(encoding='utf-8'); "
                        "compile(s, str(p), 'exec'); "
                        "assert 'repository:ordivon-host@' not in s; "
                        "assert 'source_repo.name' in s; "
                        "assert 'ref=source_ref' in s; "
                        "assert 'source_ref=source_ref' in s"
                    ),
                ),
                timeout_ms=60_000,
            ),
        ),
    )


def _write_json(path: Path, value: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class _CapturingTransport:
    def __init__(self) -> None:
        self._inner = UrllibDeepSeekTransport()
        self.responses: list[bytes] = []

    def post(self, url: str, **kwargs) -> bytes:
        raw = self._inner.post(url, **kwargs)
        self.responses.append(raw)
        return raw

    def diagnostics(self) -> list[dict[str, JsonValue]]:
        values: list[dict[str, JsonValue]] = []
        for raw in self.responses:
            response = json.loads(raw)
            choice = response["choices"][0]
            message = choice["message"]
            calls: list[dict[str, JsonValue]] = []
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                arguments = function.get("arguments")
                valid = False
                if isinstance(arguments, str):
                    try:
                        valid = isinstance(json.loads(arguments), dict)
                    except json.JSONDecodeError:
                        pass
                calls.append(
                    {
                        "name": function.get("name"),
                        "arguments": (
                            arguments[:16_384]
                            if isinstance(arguments, str)
                            else arguments
                        ),
                        "argumentsValidJson": valid,
                    }
                )
            content = message.get("content")
            values.append(
                {
                    "responseId": response.get("id"),
                    "model": response.get("model"),
                    "finishReason": choice.get("finish_reason"),
                    "assistantContentDigest": (
                        canonical_digest(content)
                        if isinstance(content, str)
                        else None
                    ),
                    "toolCalls": calls,
                }
            )
        return values


def run(args: argparse.Namespace) -> dict[str, JsonValue]:
    issue7_workload = args.workload == "read-location-issue7"
    issue4_workload = args.workload == "historical-tool-step-issue4"
    handoff_workload = args.workload == "handoff-issue2"
    rejection_workload = args.workload in {
        "rejection-classification",
        "rejection-implementation",
    }
    implementation_only = args.workload == "rejection-implementation"
    task_id = (
        ISSUE7_TASK_ID
        if issue7_workload
        else ISSUE4_TASK_ID
        if issue4_workload
        else HANDOFF_TASK_ID
        if handoff_workload
        else REJECTION_IMPLEMENTATION_TASK_ID
        if implementation_only
        else REJECTION_TASK_ID
        if rejection_workload
        else TASK_ID
    )
    frontier = (
        ISSUE7_FRONTIER
        if issue7_workload
        else ISSUE4_FRONTIER
        if issue4_workload
        else HANDOFF_FRONTIER
        if handoff_workload
        else REJECTION_FRONTIER
        if rejection_workload
        else FRONTIER
    )
    workload_id = (
        "harness-read-workspace-location-issue-7-001"
        if issue7_workload
        else "host-harness-historical-tool-step-issue-4-001"
        if issue4_workload
        else "host-operator-handoff-issue-2-001"
        if handoff_workload
        else "host-harness-rejection-classification-implementation-001"
        if implementation_only
        else
        "host-harness-rejection-classification-repair-001"
        if rejection_workload
        else "host-harness-provenance-repair-001"
    )
    target_path = (
        ISSUE7_PATHS[0]
        if issue7_workload
        else ISSUE4_PATHS[4]
        if issue4_workload
        else HANDOFF_PATHS[0]
        if handoff_workload
        else REJECTION_TARGET_PATH
        if rejection_workload
        else TARGET_PATH
    )
    source_repo = args.source_repo.expanduser().resolve()
    source_revision = _git_revision(source_repo, args.source_revision)
    repository_id = source_repo.name
    source_ref = f"repository:{repository_id}@{source_revision}"
    source_digest = canonical_digest(
        {
            "sourceRepositoryId": repository_id,
            "sourceRevision": source_revision,
        }
    )
    focused_context: dict[str, JsonValue] = {}
    if issue7_workload:
        implementation = _git_file(source_repo, source_revision, ISSUE7_PATHS[0])
        tests = _git_file(source_repo, source_revision, ISSUE7_PATHS[1])
        combined_patch = _desired_patch_arguments(
            source_repo,
            source_revision,
            desired_root=ISSUE7_SOLUTION_ROOT,
            relative_paths=ISSUE7_PATHS,
        )
        raw_files = combined_patch["files"]
        assert isinstance(raw_files, list)
        focused_context = {
            "githubIssue": {
                "number": 7,
                "title": "P1: Make read_workspace location units unambiguous",
                "observedFailure": (
                    "DeepSeek passed source line numbers to read_workspace.offset "
                    "instead of supplied UTF-8 byte offsets, exhausting eight "
                    "model-correctable duplicate-read corrections."
                ),
            },
            "implementationDigest": _file_digest(implementation),
            "testDigest": _file_digest(tests),
            "sourceSlices": [
                {
                    "relativePath": ISSUE7_PATHS[0],
                    "byteOffset": _byte_offset(implementation, 235),
                    "excerpt": _excerpt(implementation, 235, 270),
                },
                {
                    "relativePath": ISSUE7_PATHS[0],
                    "byteOffset": _byte_offset(implementation, 925),
                    "excerpt": _excerpt(implementation, 925, 975),
                },
                {
                    "relativePath": ISSUE7_PATHS[0],
                    "byteOffset": _byte_offset(implementation, 1070),
                    "excerpt": _excerpt(implementation, 1070, 1110),
                },
                {
                    "relativePath": ISSUE7_PATHS[0],
                    "byteOffset": _byte_offset(implementation, 1365),
                    "excerpt": _excerpt(implementation, 1365, 1410),
                },
                {
                    "relativePath": ISSUE7_PATHS[1],
                    "byteOffset": _byte_offset(tests, 350),
                    "excerpt": _excerpt(tests, 350, 475),
                },
            ],
            "requiredDesign": [
                "Advertise byteOffset in model_tool_definitions and name UTF-8 byte units in the read description.",
                "Accept byteOffset or legacy offset internally, never both; ambiguous calls raise MODEL_CORRECTABLE before runtime.call_tool.",
                "Lower the selected value to Runtime workspace.read offset.",
                "Use the same selected value in overlap detection and observation-cache ranges.",
                "Normalize observed reads with effectiveByteRange startInclusive/endExclusive and UTF-8 semantics.",
                "Add focused tests for schema, legacy compatibility, ambiguous rejection, non-ASCII range length, and overlap accounting.",
            ],
            "minimalPatchArgumentsByFile": [
                {"files": [item], "maxDiffBytes": 262_144}
                for item in raw_files
            ],
            "executionInstruction": (
                "The prior focused trial spent 14 calls reading without a patch. "
                "Do not perform exploratory reads. Apply each supplied "
                "minimalPatchArgumentsByFile item as its own patch_workspace call, "
                "run all checks, inspect the diff, and conclude."
            ),
        }
    elif issue4_workload:
        slice_specs = (
            (ISSUE4_PATHS[0], 405, 440),
            (ISSUE4_PATHS[1], 180, 230),
            (ISSUE4_PATHS[2], 25, 70),
            (ISSUE4_PATHS[4], 215, 350),
            (ISSUE4_PATHS[5], 1230, 1320),
            (ISSUE4_PATHS[6], 300, 325),
        )
        source_slices: list[dict[str, JsonValue]] = []
        for relative_path, start_line, end_line in slice_specs:
            source = _git_file(source_repo, source_revision, relative_path)
            source_slices.append(
                {
                    "relativePath": relative_path,
                    "digest": _file_digest(source),
                    "byteOffset": _byte_offset(source, start_line),
                    "startLine": start_line,
                    "endLine": end_line,
                    "excerpt": _excerpt(source, start_line, end_line),
                }
            )
        focused_context = {
            "githubIssue": {
                "number": 4,
                "title": (
                    "P1: Expose post-Run Tool Step receipt lookup for evidence "
                    "collection"
                ),
                "observedFailure": (
                    "After harness.run-recorded, load_current_tool_step raises "
                    "KeyError even though the terminal receipt remains durable in "
                    "Host CAS."
                ),
            },
            "ownershipBoundary": {
                "host": (
                    "Owns append-only Task event history and CAS admission; its "
                    "extension port currently exposes only the Task head."
                ),
                "harness": (
                    "Owns Tool Step Intent and Receipt schemas and must validate "
                    "their semantic linkage."
                ),
            },
            "boundedPaths": list(ISSUE4_PATHS),
            "requiredScenarios": [
                "terminal cancelled receipt queried after harness.run-recorded",
                "two Tool Steps queried independently by exact toolCallId",
                "wrong Harness Run or Tool Call identity rejected",
                "active load_current_tool_step behavior unchanged",
                "live driver no longer calls storage.journal.object_refs",
            ],
            "designWarnings": [
                "Keeping only the last receipt in the current Task projection loses earlier Tool Steps.",
                "A new mutable receipt index or second receipt store violates the issue boundary.",
                "Host must not validate Harness-owned receipt semantics.",
            ],
            "recommendedBoundary": {
                "journal": (
                    "Add an exact task+revision TaskHead lookup; do not expose an "
                    "open-ended event query."
                ),
                "storage": (
                    "Load and validate one Task event payload from that exact head, "
                    "sharing the current-head validation path."
                ),
                "extension": (
                    "Expose one exact-revision HostExtensionSnapshot read."
                ),
                "harness": (
                    "Add an exact tool_call_id historical lookup bound to this "
                    "HostHarnessRunStore.harness_run_id. Scan only exact Task revisions "
                    "through the public extension port, select tool-step-recorded "
                    "events, and reuse/refactor the full Intent, Assignment generation, "
                    "Receipt, Observation, predecessor, and Runtime Job validation from "
                    "load_current_tool_step."
                ),
            },
            "sourceSlices": source_slices,
            "executionInstruction": (
                "The unconstrained full-read trial exhausted 558k tokens without a "
                "patch. Do not repeat full-file reads. Use the supplied excerpts and "
                "digest-bound SLICE offsets, implement the recommended minimal "
                "boundary and focused tests, run all three checks, inspect the diff, "
                "then conclude."
            ),
        }
    elif handoff_workload:
        combined_patch = _handoff_patch_arguments(source_repo, source_revision)
        raw_files = combined_patch["files"]
        assert isinstance(raw_files, list)
        focused_context = {
            "githubIssue": {
                "number": 2,
                "title": (
                    "P1 acceptance: Expose operator handoff as a simple "
                    "cross-session boundary"
                ),
                "closeCondition": (
                    "A real Task can be handed from one fresh process to another "
                    "with exact revision and evidence linkage."
                ),
            },
            "existingProjection": {
                "module": HANDOFF_PATHS[0],
                "symbols": ["OperatorHandoffCapsule", "operator_handoff"],
            },
            "boundedPaths": list(HANDOFF_PATHS),
            "requiredScenarios": [
                "same current revision succeeds deterministically",
                "stale revision reports expected and current values",
                "UNKNOWN retains reconcile-existing-dispatch",
                "Task journal head is unchanged by handoff reads",
            ],
            "executionInstruction": (
                "The prior unconstrained trials exhausted their budgets without "
                "editing, and one five-file Tool Call exceeded the Provider's reliable "
                "JSON size. Apply each supplied digest-guarded "
                "minimalPatchArgumentsByFile item as its own patch_workspace call, "
                "then run all checks and inspect the diff."
            ),
            "minimalPatchArgumentsByFile": [
                {"files": [item], "maxDiffBytes": 262_144}
                for item in raw_files
            ],
        }
    elif rejection_workload:
        implementation = _git_file(
            source_repo,
            source_revision,
            REJECTION_TARGET_PATH,
        )
        tests = _git_file(source_repo, source_revision, REJECTION_TEST_PATH)
        focused_context = {
            "implementationDigest": _file_digest(implementation),
            "implementationOffset": _byte_offset(implementation, 895),
            "implementationExcerpt": _excerpt(implementation, 895, 925),
            "testDigest": _file_digest(tests),
            "testRuntimeOffset": _byte_offset(tests, 108),
            "testRuntimeExcerpt": _excerpt(tests, 108, 130),
            "testCaseOffset": _byte_offset(tests, 258),
            "testCaseExcerpt": _excerpt(tests, 258, 282),
            "readInstruction": (
                "Use read_workspace mode=SLICE at the supplied byte offsets with "
                "maxBytes around 4096. FULL reads are unnecessary."
            ),
            "minimalPatchArguments": {
                "files": [
                    {
                        "relativePath": REJECTION_TARGET_PATH,
                        "expectedDigest": _file_digest(implementation),
                        "edits": [
                            {
                                "range": {
                                    "start": {"line": 904, "column": 0},
                                    "end": {"line": 905, "column": 0},
                                },
                                "expectedText": (
                                    "            if error.detail.commit_state == "
                                    '"not_committed":\n'
                                ),
                                "replacement": (
                                    "            if error.detail.commit_state in "
                                    '{"not_started", "not_committed"}:\n'
                                ),
                            }
                        ],
                    }
                ],
                "maxDiffBytes": 65536,
            },
        }
    else:
        implementation = _git_file(source_repo, source_revision, TARGET_PATH)
        focused_context = {
            "targetDigest": _file_digest(implementation),
            "defectLocations": [
                {
                    "line": 179,
                    "current": (
                        '                ref=f"repository:ordivon-host@'
                        '{source_revision}",\n'
                    ),
                },
                {
                    "line": 352,
                    "current": (
                        '                source_ref=f"repository:ordivon-host@'
                        '{source_revision}",\n'
                    ),
                },
            ],
            "executionInstruction": (
                "After the required target read, use these digest-guarded minimal "
                "patch arguments directly. Then run both checks, inspect the diff, "
                "and submit the Run conclusion."
            ),
            "minimalPatchArguments": {
                "files": [
                    {
                        "relativePath": TARGET_PATH,
                        "expectedDigest": _file_digest(implementation),
                        "edits": [
                            {
                                "range": {
                                    "start": {"line": 144, "column": 0},
                                    "end": {"line": 145, "column": 0},
                                },
                                "expectedText": (
                                    "def _task_contract(source_revision: str, "
                                    "source_digest: str) -> TaskContract:\n"
                                ),
                                "replacement": (
                                    "def _task_contract(\n"
                                    "    source_ref: str,\n"
                                    "    source_revision: str,\n"
                                    "    source_digest: str,\n"
                                    ") -> TaskContract:\n"
                                ),
                            },
                            {
                                "range": {
                                    "start": {"line": 179, "column": 0},
                                    "end": {"line": 180, "column": 0},
                                },
                                "expectedText": (
                                    '                ref=f"repository:ordivon-host@'
                                    '{source_revision}",\n'
                                ),
                                "replacement": "                ref=source_ref,\n",
                            },
                            {
                                "range": {
                                    "start": {"line": 274, "column": 0},
                                    "end": {"line": 275, "column": 0},
                                },
                                "expectedText": (
                                    "    source_revision = _git_revision("
                                    "source_repo, args.source_revision)\n"
                                ),
                                "replacement": (
                                    "    source_revision = _git_revision("
                                    "source_repo, args.source_revision)\n"
                                    "    source_ref = (\n"
                                    '        f"repository:{source_repo.name}@'
                                    '{source_revision}"\n'
                                    "    )\n"
                                ),
                            },
                            {
                                "range": {
                                    "start": {"line": 302, "column": 0},
                                    "end": {"line": 303, "column": 0},
                                },
                                "expectedText": (
                                    "        contract = _task_contract("
                                    "source_revision, source_digest)\n"
                                ),
                                "replacement": (
                                    "        contract = _task_contract(\n"
                                    "            source_ref, source_revision, "
                                    "source_digest\n"
                                    "        )\n"
                                ),
                            },
                            {
                                "range": {
                                    "start": {"line": 352, "column": 0},
                                    "end": {"line": 353, "column": 0},
                                },
                                "expectedText": (
                                    '                source_ref=f"repository:'
                                    'ordivon-host@{source_revision}",\n'
                                ),
                                "replacement": (
                                    "                source_ref=source_ref,\n"
                                ),
                            },
                        ],
                    }
                ],
                "maxDiffBytes": 65536,
            },
        }
    state_root = args.state_root.expanduser().resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    if any(state_root.iterdir()):
        raise RuntimeError("state root must be empty")
    runtime_token = os.environ.get("ORDIVON_BEARER_TOKEN")
    if not runtime_token:
        raise RuntimeError("ORDIVON_BEARER_TOKEN is not set")
    runtime = McpRuntimeClient(
        _runtime_endpoint(args.runtime_endpoint),
        runtime_token,
        client_name="ordivon-host-harness-provenance-repair",
        client_version="0.1.0",
    )
    runtime.initialize()
    opened = runtime.call_tool(
        "workspace.open",
        {
            "schemaVersion": 1,
            "sourceRepo": str(source_repo),
            "sourceRevision": source_revision,
        },
    )
    workspace_id = opened.get("workspaceId")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise RuntimeError("workspace.open omitted Workspace identity")

    verification: dict[str, JsonValue] = {}
    started_at_ms = _clock_ms()
    try:
        with HostStorage(state_root) as storage:
            _create_task(
                storage,
                task_id=task_id,
                frontier=frontier,
                workload_id=workload_id,
            )
            host = HarnessHost(storage, clock_ms=_clock_ms)
            contract = _contract(
                args.workload,
                source_ref,
                source_revision,
                source_digest,
            )
            context_block = ContextBlock(
                block_id=f"context-block:{workload_id}:task",
                kind=BlockKind.TASK,
                priority=100,
                required=True,
                freshness=Freshness.CURRENT,
                source_digest=source_digest,
                payload={
                    "relativePath": target_path,
                    "defect": (
                        (
                            "The model-facing read_workspace offset has no explicit "
                            "unit and differs from search result byteOffset naming."
                        )
                        if issue7_workload
                        else
                        (
                            "Historical Harness Tool Step receipts are durable but "
                            "lack a public exact-identity read path after Run recording."
                        )
                        if issue4_workload
                        else
                        (
                            "The existing Operator Handoff projection has no public "
                            "revision-pinned operator CLI."
                        )
                        if handoff_workload
                        else
                        (
                            "Runtime reports pre-dispatch validation rejection as "
                            "commitState=not_started, which must remain model-correctable."
                        )
                        if rejection_workload
                        else (
                            "The repository identity is currently hard-coded to "
                            "ordivon-host at the TaskContract and Assignment call sites."
                        )
                    ),
                    "expectedRepositoryId": (
                        None
                        if issue7_workload
                        or issue4_workload
                        or handoff_workload
                        or rejection_workload
                        else repository_id
                    ),
                    "expectedSourceRef": (
                        None
                        if issue7_workload
                        or issue4_workload
                        or handoff_workload
                        or rejection_workload
                        else source_ref
                    ),
                    "focusedContext": focused_context,
                },
            )

            def verify(_proposal):
                read = runtime.call_tool(
                    "workspace.read",
                    {
                        "schemaVersion": 1,
                        "workspaceId": workspace_id,
                        "relativePath": target_path,
                        "mode": "FULL",
                        "offset": 0,
                        "maxBytes": 262_144,
                    },
                )
                diff = runtime.call_tool(
                    "workspace.diff",
                    {
                        "schemaVersion": 1,
                        "workspaceId": workspace_id,
                        "maxBytes": 1_048_576,
                    },
                )
                content = read.get("content")
                diff_text = diff.get("diff")
                untracked = diff.get("untrackedPaths")
                if not isinstance(content, str):
                    raise RuntimeError("independent verifier could not read target")
                if not isinstance(diff_text, str) or not isinstance(untracked, list):
                    raise RuntimeError("independent verifier received invalid diff")
                if issue7_workload:
                    test_read = runtime.call_tool(
                        "workspace.read",
                        {
                            "schemaVersion": 1,
                            "workspaceId": workspace_id,
                            "relativePath": ISSUE7_PATHS[1],
                            "mode": "FULL",
                            "offset": 0,
                            "maxBytes": 524_288,
                        },
                    )
                    test_content = test_read.get("content")
                    if not isinstance(test_content, str):
                        raise RuntimeError(
                            "independent verifier could not read issue #7 tests"
                        )
                    changed_paths = {
                        line.split(" b/", 1)[1]
                        for line in diff_text.splitlines()
                        if line.startswith("diff --git a/") and " b/" in line
                    }
                    checks = {
                        "pythonCompiles": True,
                        "modelSchemaUsesByteOffset": (
                            '"byteOffset": integer' in content
                            and "UTF-8 byte" in content
                        ),
                        "legacyAndAmbiguousCovered": (
                            "legacy" in test_content.lower()
                            and "model_correctable" in test_content
                        ),
                        "effectiveRangeExposed": (
                            "effectiveByteRange" in content
                            and "startInclusive" in content
                            and "endExclusive" in content
                        ),
                        "nonAsciiCovered": (
                            "non-ascii" in test_content.lower()
                            or "utf-8" in test_content.lower()
                        ),
                        "boundedTrackedChanges": (
                            bool(changed_paths)
                            and changed_paths.issubset(set(ISSUE7_PATHS))
                        ),
                        "noUntrackedFiles": not untracked,
                    }
                    try:
                        compile(content, ISSUE7_PATHS[0], "exec")
                        compile(test_content, ISSUE7_PATHS[1], "exec")
                    except SyntaxError:
                        checks["pythonCompiles"] = False
                elif issue4_workload:
                    retained = {target_path: content}
                    for relative_path in ISSUE4_PATHS:
                        if relative_path == target_path:
                            continue
                        path_read = runtime.call_tool(
                            "workspace.read",
                            {
                                "schemaVersion": 1,
                                "workspaceId": workspace_id,
                                "relativePath": relative_path,
                                "mode": "FULL",
                                "offset": 0,
                                "maxBytes": 524_288,
                            },
                        )
                        path_content = path_read.get("content")
                        if not isinstance(path_content, str):
                            raise RuntimeError(
                                "independent verifier could not read "
                                f"{relative_path}"
                            )
                        retained[relative_path] = path_content
                    run_store_source = retained[ISSUE4_PATHS[4]]
                    harness_tests = retained[ISSUE4_PATHS[5]]
                    cancel_driver = retained[ISSUE4_PATHS[6]]
                    changed_paths = {
                        line.split(" b/", 1)[1]
                        for line in diff_text.splitlines()
                        if line.startswith("diff --git a/") and " b/" in line
                    }
                    checks = {
                        "pythonCompiles": True,
                        "publicHistoricalQuery": (
                            "tool_call_id" in run_store_source
                            and "harness_run_id" in run_store_source
                            and "load_" in run_store_source
                        ),
                        "harnessDoesNotUseHostInternals": (
                            ".journal" not in run_store_source
                            and ".objects" not in run_store_source
                        ),
                        "cancelDriverUsesPublicQuery": (
                            "_historical_tool_step_receipt" not in cancel_driver
                            and "journal.object_refs" not in cancel_driver
                            and "HostHarnessRunStore" in cancel_driver
                        ),
                        "cancelledAndMultipleStepsCovered": (
                            "cancel" in harness_tests.lower()
                            and "multiple" in harness_tests.lower()
                            and "tool_call_id" in harness_tests
                        ),
                        "boundedTrackedChanges": (
                            bool(changed_paths)
                            and changed_paths.issubset(set(ISSUE4_PATHS))
                        ),
                        "noUntrackedFiles": not untracked,
                    }
                    try:
                        for relative_path, source in retained.items():
                            compile(source, relative_path, "exec")
                    except SyntaxError:
                        checks["pythonCompiles"] = False
                elif handoff_workload:
                    retained: dict[str, str] = {target_path: content}
                    for relative_path in HANDOFF_PATHS[1:]:
                        path_read = runtime.call_tool(
                            "workspace.read",
                            {
                                "schemaVersion": 1,
                                "workspaceId": workspace_id,
                                "relativePath": relative_path,
                                "mode": "FULL",
                                "offset": 0,
                                "maxBytes": 262_144,
                            },
                        )
                        path_content = path_read.get("content")
                        if not isinstance(path_content, str):
                            raise RuntimeError(
                                "independent verifier could not read "
                                f"{relative_path}"
                            )
                        retained[relative_path] = path_content
                    handoff_source = retained[HANDOFF_PATHS[0]]
                    cli_source = retained[HANDOFF_PATHS[1]]
                    tests_source = (
                        retained[HANDOFF_PATHS[2]]
                        + retained[HANDOFF_PATHS[3]]
                    )
                    readme = retained[HANDOFF_PATHS[4]]
                    changed_paths = {
                        line.split(" b/", 1)[1]
                        for line in diff_text.splitlines()
                        if line.startswith("diff --git a/") and " b/" in line
                    }
                    checks = {
                        "pythonCompiles": True,
                        "expectedRevisionSupported": (
                            "expected_revision" in handoff_source
                        ),
                        "staleRevisionDetected": (
                            "stale Operator Handoff revision" in handoff_source
                            and "current" in handoff_source
                        ),
                        "cliExportsCapsule": (
                            '"handoff"' in cli_source
                            and "operator_handoff" in cli_source
                            and "capsuleDigest" in cli_source
                        ),
                        "cliRevisionPin": "--expected-revision" in cli_source,
                        "determinismAndReadOnlyCovered": (
                            "deterministic" in tests_source
                            and "revision" in tests_source
                        ),
                        "operatorCommandDocumented": "task handoff" in readme,
                        "boundedTrackedChanges": (
                            bool(changed_paths)
                            and changed_paths.issubset(set(HANDOFF_PATHS))
                        ),
                        "noUntrackedFiles": not untracked,
                    }
                    try:
                        compile(handoff_source, HANDOFF_PATHS[0], "exec")
                        compile(cli_source, HANDOFF_PATHS[1], "exec")
                        compile(
                            retained[HANDOFF_PATHS[2]],
                            HANDOFF_PATHS[2],
                            "exec",
                        )
                        compile(
                            retained[HANDOFF_PATHS[3]],
                            HANDOFF_PATHS[3],
                            "exec",
                        )
                    except SyntaxError:
                        checks["pythonCompiles"] = False
                elif rejection_workload:
                    checks = {
                        "pythonCompiles": True,
                        "implementationHandlesNotStarted": (
                            '"not_started"' in content
                            and '"not_committed"' in content
                        ),
                        "implementationDiffPresent": (
                            f"diff --git a/{REJECTION_TARGET_PATH} "
                            f"b/{REJECTION_TARGET_PATH}" in diff_text
                        ),
                        "noUntrackedFiles": not untracked,
                        "noOtherTrackedFilesChanged": (
                            diff_text.count("diff --git ")
                            == (1 if implementation_only else 2)
                        ),
                    }
                    if not implementation_only:
                        test_read = runtime.call_tool(
                            "workspace.read",
                            {
                                "schemaVersion": 1,
                                "workspaceId": workspace_id,
                                "relativePath": REJECTION_TEST_PATH,
                                "mode": "FULL",
                                "offset": 0,
                                "maxBytes": 262_144,
                            },
                        )
                        test_content = test_read.get("content")
                        if not isinstance(test_content, str):
                            raise RuntimeError(
                                "independent verifier could not read regression test"
                            )
                        checks["regressionCoversNotStarted"] = (
                            '"not_started"' in test_content
                        )
                        checks["testDiffPresent"] = (
                            f"diff --git a/{REJECTION_TEST_PATH} "
                            f"b/{REJECTION_TEST_PATH}" in diff_text
                        )
                else:
                    checks = {
                        "pythonCompiles": True,
                        "hardCodedHostRefAbsent": (
                            "repository:ordivon-host@" not in content
                        ),
                        "sourceRepoIdentityDerived": "source_repo.name" in content,
                        "contractUsesDerivedRef": "ref=source_ref" in content,
                        "assignmentUsesDerivedRef": "source_ref=source_ref" in content,
                        "targetDiffPresent": (
                            f"diff --git a/{TARGET_PATH} b/{TARGET_PATH}"
                            in diff_text
                        ),
                        "noUntrackedFiles": not untracked,
                        "noOtherTrackedFilesChanged": (
                            diff_text.count("diff --git ") == 1
                        ),
                    }
                try:
                    compile(content, target_path, "exec")
                    if rejection_workload and not implementation_only:
                        compile(test_content, REJECTION_TEST_PATH, "exec")
                except SyntaxError:
                    checks["pythonCompiles"] = False
                accepted = all(checks.values())
                verification.update(
                    {
                        "method": "external-runtime-read-and-diff-v1",
                        "checks": checks,
                        "targetDigest": read.get("digest"),
                        "diffDigest": canonical_digest(diff_text),
                        "diff": diff_text,
                        "untrackedPaths": untracked,
                    }
                )
                failed = [name for name, passed in checks.items() if not passed]
                return (
                    accepted,
                    None if accepted else f"independent checks failed: {failed}",
                    verification,
                )

            def artifact_exists(reference: ArtifactRef) -> bool:
                try:
                    current = host.load_current_run(task_id)
                except (KeyError, RuntimeError):
                    return False
                for retained in current.observation_objects:
                    observation = storage.objects.get(
                        retained.digest,
                        expected_kind="harness-tool-observation",
                    )
                    if not isinstance(observation, dict):
                        continue
                    job_id = observation.get("runtimeJobRef")
                    refs = observation.get("artifactRefs")
                    if not isinstance(job_id, str) or not isinstance(refs, list):
                        continue
                    if not any(
                        isinstance(item, dict)
                        and item.get("ref") == reference.ref
                        and item.get("kind") == reference.kind
                        and item.get("digest") == reference.digest
                        for item in refs
                    ):
                        continue
                    try:
                        runtime.call_tool(
                            "artifact.read",
                            {
                                "schemaVersion": 1,
                                "jobId": job_id,
                                "artifactId": reference.ref,
                                "offset": 0,
                                "maxBytes": 1,
                            },
                        )
                    except Exception:
                        return False
                    return True
                return False

            settings = DeepSeekSettings.from_secret_file(args.deepseek_secret)
            if args.model is not None:
                settings = replace(settings, model=args.model)
            capture = (
                _CapturingTransport() if args.capture_provider_diagnostics else None
            )
            runner = HarnessRunner(
                host,
                runtime=runtime,
                adapter=DeepSeekTurnAdapter(settings, transport=capture),
                artifact_exists=artifact_exists,
                acceptance_verifier=verify,
                verification_method="external-runtime-read-and-diff-v1",
            )
            result = runner.run(
                HarnessRunPlan(
                    task_contract=contract,
                    context_blocks=(context_block,),
                    workspace_ref=workspace_id,
                    tool_grant=_grant(args.workload),
                    token_budget=16_000,
                    budget=RunBudget(
                        args.max_model_calls,
                        args.max_tool_calls,
                        1_048_576,
                        600_000,
                        args.token_hard_limit,
                        2,
                        args.max_tool_corrections,
                    ),
                    source_ref=source_ref,
                    source_digest=source_digest,
                    completion_mode=CompletionMode.ADJUDICATE,
                )
            )
            if result.recorded is None:
                head = storage.read_task_event(task_id)
                data = head.data if isinstance(head.data, dict) else {}
                current_assignment = host.load_current_assignment(task_id)
                paused_evidence: dict[str, JsonValue] = {
                    "schemaVersion": 1,
                    "kind": "ordivon.host-harness-dogfood-evidence",
                    "taskId": task_id,
                    "workloadId": workload_id,
                    "sourceRepositoryId": repository_id,
                    "sourceRevision": source_revision,
                    "sourceRef": source_ref,
                    "workspaceId": workspace_id,
                    "startedAtMs": started_at_ms,
                    "completedAtMs": _clock_ms(),
                    "assignmentId": result.assignment_id,
                    "assignmentDigest": current_assignment.assignment.digest,
                    "harnessRunId": result.harness_run_id,
                    "harnessManifestDigest": ordivon_harness_manifest().digest,
                    "runReceiptDigest": None,
                    "runReceiptObjectDigest": None,
                    "traceDigest": result.loop_result.trace.digest,
                    "traceObjectDigest": None,
                    "traceEventCount": len(result.loop_result.trace.events),
                    "observationObjectDigests": [],
                    "completionDecisionDigest": None,
                    "completionAccepted": False,
                    "finalTaskState": head.projection.state.value,
                    "finalTaskRevision": head.projection.revision,
                    "stopCode": result.loop_result.stop_code.value,
                    "paused": result.paused,
                    "pauseSnapshotObjectDigest": data.get(
                        "harnessRunSnapshotObjectDigest"
                    ),
                    "pauseStateObjectDigest": data.get(
                        "harnessRunStateObjectDigest"
                    ),
                    "conclusion": (
                        None
                        if result.loop_result.conclusion is None
                        else result.loop_result.conclusion.to_dict()
                    ),
                    "modelCalls": result.loop_result.model_calls,
                    "toolCalls": result.loop_result.tool_calls,
                    "observationBytes": result.loop_result.observation_bytes,
                    "usage": result.loop_result.usage,
                    "providerDiagnostics": (
                        [] if capture is None else capture.diagnostics()
                    ),
                    "independentVerification": verification,
                }
                paused_evidence["integrity"] = {
                    "algorithm": "sha256",
                    "canonicalization": "ordivon-canonical-json-v1",
                    "payloadDigest": canonical_digest(paused_evidence),
                }
                return paused_evidence
            recorded = result.recorded
            decision = result.decision
            head = storage.read_task_event(task_id)
            native = recorded.assignment.native_run_contract
            if native is None or recorded.trace_object is None:
                raise RuntimeError("native evidence objects are incomplete")
            evidence: dict[str, JsonValue] = {
                "schemaVersion": 1,
                "kind": "ordivon.host-harness-dogfood-evidence",
                "taskId": task_id,
                "workloadId": workload_id,
                "sourceRepositoryId": repository_id,
                "sourceRevision": source_revision,
                "sourceRef": source_ref,
                "workspaceId": workspace_id,
                "startedAtMs": started_at_ms,
                "completedAtMs": _clock_ms(),
                "assignmentId": result.assignment_id,
                "assignmentDigest": recorded.assignment.assignment.digest,
                "harnessRunId": result.harness_run_id,
                "harnessManifestDigest": ordivon_harness_manifest().digest,
                "runReceiptDigest": recorded.receipt.digest,
                "runReceiptObjectDigest": recorded.receipt_object.digest,
                "traceDigest": recorded.receipt.event_digest,
                "traceObjectDigest": recorded.trace_object.digest,
                "traceEventCount": len(result.loop_result.trace.events),
                "observationObjectDigests": [
                    item.digest for item in recorded.observation_objects
                ],
                "completionDecisionDigest": (
                    None if decision is None else decision.decision.digest
                ),
                "completionAccepted": (
                    False if decision is None else decision.decision.accepted
                ),
                "finalTaskState": head.projection.state.value,
                "finalTaskRevision": head.projection.revision,
                "stopCode": result.loop_result.stop_code.value,
                "modelCalls": result.loop_result.model_calls,
                "toolCalls": result.loop_result.tool_calls,
                "observationBytes": result.loop_result.observation_bytes,
                "usage": result.loop_result.usage,
                "providerDiagnostics": (
                    [] if capture is None else capture.diagnostics()
                ),
                "independentVerification": verification,
            }
            evidence["integrity"] = {
                "algorithm": "sha256",
                "canonicalization": "ordivon-canonical-json-v1",
                "payloadDigest": canonical_digest(evidence),
            }
            return evidence
    finally:
        runtime.call_tool(
            "workspace.close",
            {"schemaVersion": 1, "workspaceId": workspace_id, "force": True},
        )


def main() -> int:
    args = parse_args()
    try:
        evidence = run(args)
        _write_json(args.evidence_out.expanduser().resolve(), evidence)
        print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
        return (
            0
            if evidence["completionAccepted"] is True
            and evidence["finalTaskState"] == TaskState.COMPLETED.value
            else 2
        )
    except Exception as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

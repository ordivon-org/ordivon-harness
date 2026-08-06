#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any

from anc_canonical import JsonValue, canonical_digest
from ordivon_host.runtime import McpRuntimeClient
from ordivon_host.testing import workspace_absent

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.execution_binding import (
    HarnessExecutionBinding,
    HarnessRuntimeReference,
)
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget
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
from ordivon_harness.sqlite_store import SQLiteHarnessStore

HARNESS_RUN_ID = "harness-run:repository-repair-runtime-acceptance"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "harness-replacement-repository-repair-v1"
)
ORIGINAL_FRAGMENT = (
    "    weight_total = sum(weights)\n"
    "    return [(total * weight) // weight_total for weight in weights]"
)
REPLACEMENT_FRAGMENT = (
    "    weight_total = sum(weights)\n"
    "    floors = [(total * weight) // weight_total for weight in weights]\n"
    "    remainders = [(total * weight) % weight_total for weight in weights]\n"
    "    remaining = total - sum(floors)\n"
    "    order = sorted(\n"
    "        range(len(weights)),\n"
    "        key=lambda index: (-remainders[index], index),\n"
    "    )\n"
    "    for index in order[:remaining]:\n"
    "        floors[index] += 1\n"
    "    return floors"
)


class RuntimeRecorder:
    def __init__(self, delegate: McpRuntimeClient) -> None:
        self.delegate = delegate
        self.calls: list[str] = []
        self.job_ids: set[str] = set()

    def call_tool(
        self, name: str, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls.append(name)
        result = self.delegate.call_tool(name, arguments)
        job_id = result.get("jobId")
        if isinstance(job_id, str):
            self.job_ids.add(job_id)
        jobs = result.get("jobs")
        if isinstance(jobs, list):
            for job in jobs:
                if isinstance(job, dict) and isinstance(job.get("jobId"), str):
                    self.job_ids.add(job["jobId"])
        return result


class FixedClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        self.value += 1
        return self.value


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen independent repository-repair Runtime bridge acceptance"
    )
    parser.add_argument(
        "--runtime-endpoint",
        default="http://127.0.0.1:8897/mcp",
    )
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _initialize_source(root: Path) -> str:
    shutil.copytree(FIXTURE, root)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "acceptance@ordivon.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Ordivon Acceptance"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "freeze repository repair fixture"],
        check=True,
    )
    return _git(root, "rev-parse", "HEAD")


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _contract(created_at_ms: int) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=HARNESS_RUN_ID,
        harness_implementation_id="ordivon-harness@repository-repair-runtime-acceptance",
        caller_id="caller:formal-runner-acceptance",
        caller_run_ref="trial:repository-repair-runtime-acceptance",
        objective_ref=HarnessBoundReference(
            "objective:repository-repair-runtime-acceptance", "objective", DIGEST_A
        ),
        context_refs=(
            HarnessBoundReference(
                "context:repository-repair-runtime-acceptance", "context", DIGEST_B
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
            "maxWallTimeMs": 120_000,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            "system-manifest:repository-repair-runtime-acceptance",
            "system-manifest",
            DIGEST_C,
        ),
        created_at_ms=created_at_ms,
    )


def _binding(
    contract: HarnessRunContract,
    continuity: SQLiteHarnessRunContinuityStore,
    workspace_id: str,
) -> HarnessExecutionBinding:
    binding = continuity.binding
    references = (
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="harness_run",
            reference_id=contract.harness_run_id,
            generation=str(binding.assignment_generation),
            digest=binding.digest,
        ),
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="run_contract",
            reference_id=f"harness-run-contract:{contract.digest[7:31]}",
            generation="1",
            digest=contract.digest,
        ),
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="tool_grant",
            reference_id=f"tool-grant:{contract.tool_grant_digest[7:31]}",
            generation="1",
            digest=contract.tool_grant_digest,
        ),
    )
    return HarnessExecutionBinding(
        harness_run_id=contract.harness_run_id,
        workspace_ref=workspace_id,
        assignment_id=binding.assignment_id,
        assignment_generation=binding.assignment_generation,
        assignment_digest=binding.assignment_digest,
        runtime_binding_digest=canonical_digest(
            {
                "harnessRunId": contract.harness_run_id,
                "workspaceRef": workspace_id,
            }
        ),
        tool_catalog_digest=contract.tool_catalog_digest,
        tool_grant_digest=contract.tool_grant_digest,
        deadline_ms=contract.deadline_ms,
        runtime_references=references,
    )


def _turn(
    sequence: int,
    call: AgentToolCall,
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:repository-repair-acceptance:{sequence}",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=(call,),
        conclusion=None,
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest(
            {"sequence": sequence, "toolCall": call.to_dict()}
        ),
    )


def _premature_completion_turn() -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:repository-repair-acceptance:premature",
        model_id=ScriptedTurnAdapter.model_id,
        content="premature repository repair completion",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Attempted completion before collecting required evidence.",
        ),
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"prematureCompletion": True}),
    )


def _completion_turn(workspace_id: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:repository-repair-acceptance:7",
        model_id=ScriptedTurnAdapter.model_id,
        content="repository repair completed",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Patched allocation.py and passed the visible Check.",
            artifact_refs=(
                f"workspace-artifact:{workspace_id}:artifacts/completion.json",
            ),
        ),
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"candidateCompleted": True}),
    )


def _with_integrity(value: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        **value,
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "ordivon-evidence-json-v1",
            "payloadDigest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get("ORDIVON_BEARER_TOKEN")
    if not token:
        raise RuntimeError("ORDIVON_BEARER_TOKEN is not set")
    repo = Path(__file__).resolve().parents[1]
    revision = _git(repo, "rev-parse", "HEAD")
    dirty = bool(_git(repo, "status", "--porcelain"))
    if dirty and not args.allow_dirty:
        raise RuntimeError("Harness repository must be clean")

    client = McpRuntimeClient(
        args.runtime_endpoint,
        token,
        client_name="ordivon-harness-repository-repair-acceptance",
        client_version="0.1.0",
    )
    client.initialize()
    recorder = RuntimeRecorder(client)
    workspace_id: str | None = None
    workspace_closed = False
    with tempfile.TemporaryDirectory(
        prefix="ordivon-repository-repair-runtime-acceptance-"
    ) as directory:
        root = Path(directory)
        source = root / "source"
        state = root / "harness"
        source_revision = _initialize_source(source)
        source_digest = _file_digest(source / "allocation.py")
        initial_source = (source / "allocation.py").read_text(encoding="utf-8")
        final_source = initial_source.replace(ORIGINAL_FRAGMENT, REPLACEMENT_FRAGMENT)
        if final_source == initial_source:
            raise RuntimeError("reference repair fragment was not found")
        final_source_digest = "sha256:" + hashlib.sha256(
            final_source.encode("utf-8")
        ).hexdigest()
        completion_text = json.dumps(
            {
                "schemaVersion": 1,
                "kind": "ordivon.evaluation-completion-artifact",
                "taskId": "HARNESS-REPO-REPAIR-001",
                "taskVersion": 1,
                "sourceRevision": source_revision,
                "changedPaths": ["allocation.py"],
                "visibleCheck": {
                    "checkId": "visible-tests",
                    "status": "passed",
                },
                "finalSourceDigest": final_source_digest,
                "summary": "Applied largest-remainder allocation with stable tie-breaking.",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        opened = client.call_tool(
            "workspace.open",
            {
                "schemaVersion": 1,
                "sourceRepo": str(source),
                "sourceRevision": source_revision,
            },
        )
        observed_workspace = opened.get("workspaceId")
        if not isinstance(observed_workspace, str) or not observed_workspace:
            raise RuntimeError("workspace.open omitted Workspace identity")
        workspace_id = observed_workspace
        try:
            clock = FixedClock(int(time.time_ns() // 1_000_000))
            contract = _contract(clock())
            with SQLiteHarnessStore.initialize(state) as store:
                store.create_run(contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store,
                    contract,
                    clock_ms=clock,
                )
                bridge = SQLiteHarnessRepositoryRepairRuntimeBridge(
                    contract,
                    continuity,
                    _binding(contract, continuity, workspace_id),
                    recorder,
                )
                calls = (
                    AgentToolCall(
                        "tool-call:repository-repair-acceptance:read",
                        "read_workspace",
                        {"relativePath": "allocation.py", "mode": "FULL"},
                    ),
                    AgentToolCall(
                        "tool-call:repository-repair-acceptance:patch",
                        "patch_workspace",
                        {
                            "files": [
                                {
                                    "relativePath": "allocation.py",
                                    "expectedDigest": source_digest,
                                    "edits": [
                                        {
                                            "range": {
                                                "start": {"line": 16, "column": 0},
                                                "end": {
                                                    "line": 17,
                                                    "column": len(
                                                        "    return [(total * weight) // weight_total for weight in weights]"
                                                    ),
                                                },
                                            },
                                            "expectedText": ORIGINAL_FRAGMENT,
                                            "replacement": REPLACEMENT_FRAGMENT,
                                        }
                                    ],
                                },
                                {
                                    "relativePath": "artifacts/completion.json",
                                    "expectedDigest": None,
                                    "edits": [
                                        {
                                            "range": {
                                                "start": {"line": 1, "column": 0},
                                                "end": {"line": 1, "column": 0},
                                            },
                                            "expectedText": "",
                                            "replacement": completion_text,
                                        }
                                    ],
                                },
                            ],
                            "maxDiffBytes": 65_536,
                        },
                    ),
                    AgentToolCall(
                        "tool-call:repository-repair-acceptance:check",
                        "run_check",
                        {
                            "checkId": "visible-tests",
                            "waitMs": 30_000,
                            "stdoutTailBytes": 65_536,
                            "stderrTailBytes": 65_536,
                        },
                    ),
                    AgentToolCall(
                        "tool-call:repository-repair-acceptance:diff",
                        "diff_workspace",
                        {"maxBytes": 65_536},
                    ),
                    AgentToolCall(
                        "tool-call:repository-repair-acceptance:reread",
                        "read_workspace",
                        {"relativePath": "allocation.py", "mode": "FULL"},
                    ),
                )
                turns = (_premature_completion_turn(),) + tuple(
                    _turn(sequence, call)
                    for sequence, call in enumerate(calls, start=2)
                ) + (_completion_turn(workspace_id),)
                result = OrdivonAgentLoop(
                    ScriptedTurnAdapter(turns),
                    bridge,
                    budget=RunBudget(
                        max_model_calls=7,
                        max_tool_calls=5,
                        max_observation_bytes=262_144,
                        max_wall_time_ms=120_000,
                        max_total_tokens=100_000,
                        max_model_retries=1,
                    ),
                    clock_ms=clock,
                    monotonic_ms=clock,
                ).run(
                    harness_run_id=contract.harness_run_id,
                    assignment_id=continuity.binding.assignment_id,
                    context_digest=contract.context_refs[0].digest,
                    initial_messages=(
                        {
                            "role": "user",
                            "content": (
                                "Repair allocation.py according to SPEC.md, run the visible "
                                "Check, and inspect the final diff."
                            ),
                        },
                    ),
                )
                doctor = store.doctor(full=True)
                event_count = len(store.list_run_events(contract.harness_run_id))
                observations = {item.tool_name: item for item in result.observations}
                checks = {
                    "candidateCompleted": result.candidate_completed,
                    "fiveToolCalls": result.tool_calls == 5,
                    "sevenModelCalls": result.model_calls == 7,
                    "prematureConclusionCorrected": (
                        result.usage.get("toolCorrections") == 1
                        and "conclusion_rejected"
                        in {event.kind for event in result.trace.events}
                    ),
                    "allToolObservationsObserved": all(
                        item.status == "observed" for item in result.observations
                    ),
                    "visibleCheckSucceeded": (
                        observations["run_check"].status == "observed"
                        and observations["run_check"].runtime_job_ref is not None
                        and observations["run_check"].structured_content.get("status")
                        == "succeeded"
                    ),
                    "patchApplied": observations["patch_workspace"].status
                    == "observed",
                    "diffObserved": observations["diff_workspace"].status
                    == "observed",
                    "harnessDoctorHealthy": doctor["healthy"] is True,
                    "oneRuntimeJob": len(recorder.job_ids) == 1,
                    "runtimeOperationsExact": recorder.calls
                    in (
                        [
                            "workspace.read",
                            "workspace.patch",
                            "workspace.exec",
                            "workspace.diff",
                            "workspace.read",
                        ],
                        [
                            "workspace.read",
                            "workspace.patch",
                            "workspace.exec",
                            "task.observe",
                            "workspace.diff",
                            "workspace.read",
                        ],
                    ),
                }
                if not all(checks.values()):
                    raise RuntimeError(f"repository-repair acceptance checks failed: {checks}")
        finally:
            if workspace_id is not None:
                client.call_tool(
                    "workspace.close",
                    {
                        "schemaVersion": 1,
                        "workspaceId": workspace_id,
                        "force": True,
                    },
                )
                workspace_closed = workspace_absent(client, workspace_id)
        if not workspace_closed:
            raise RuntimeError("Runtime Workspace remained present after close")

        return _with_integrity(
            {
                "schemaVersion": 1,
                "kind": "ordivon.harness-repository-repair-runtime-acceptance",
                "implementationRevision": revision,
                "harnessRevision": revision,
                "harnessClean": not dirty,
                "toolSurfaceDigest": (
                    INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST
                ),
                "toolGrantDigest": INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST,
                "sourceRevision": source_revision,
                "sourceAllocationDigest": source_digest,
                "modelCalls": result.model_calls,
                "toolCalls": result.tool_calls,
                "runtimeJobCount": len(recorder.job_ids),
                "harnessEventCount": event_count,
                "traceDigest": result.trace.digest,
                "workspaceClosed": workspace_closed,
                "checks": checks,
                "productionActivated": False,
                "b6Implemented": False,
                "knownLimits": [
                    "This acceptance proves only the frozen repository-repair Tool surface",
                    "The Provider is scripted and the acceptance does not claim model capability",
                    "Hidden verification and Host semantic acceptance remain B4 responsibilities",
                ],
            }
        )


def main() -> int:
    args = _args()
    try:
        receipt = run(args)
    except Exception as error:
        print(f"repository-repair Runtime acceptance: {type(error).__name__}: {error}")
        return 1
    if args.evidence_out is not None:
        path = args.evidence_out.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(path, 0o600)
    print(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

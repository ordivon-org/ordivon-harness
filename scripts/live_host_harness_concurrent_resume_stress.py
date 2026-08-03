#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from anc_canonical import JsonValue, canonical_digest
from ordivon_host import EventKind, HostKernel, HostStorage, StateRef
from ordivon_host.cognition import BlockKind, ContextBlock, Freshness
from ordivon_host.runtime import McpRuntimeClient
from ordivon_harness import (
    CompletionMode,
    HarnessHost,
    HarnessProviderCallClaimHeld,
    HarnessProviderCallRecoveryRequired,
    HarnessRunPlan,
    HarnessRunner,
    HarnessSuperseded,
    TaskContract,
    ToolGrant,
)
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentTurnResult,
    RunBudget,
    ScriptedTurnAdapter,
    ordivon_harness_manifest,
    static_provider_request_digest,
)

TASK_ID = "task:host-harness-concurrent-resume-stress-001"
GOAL_ID = "goal:host-harness-dogfood"
FRONTIER = "node:host-harness-concurrent-resume-stress-001:work"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Race two fresh Harness processes against one needs_input Snapshot and "
            "verify that only one physical Provider call can begin."
        )
    )
    parser.add_argument(
        "--phase",
        choices=("all", "prepare", "contender"),
        default="all",
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--label", choices=("a", "b"))
    parser.add_argument(
        "--source-repo",
        type=Path,
        default=Path("/root/projects/ordivon-harness"),
    )
    parser.add_argument("--source-revision")
    parser.add_argument("--runtime-endpoint")
    parser.add_argument("--evidence-out", type=Path)
    return parser.parse_args()


def _clock_ms() -> int:
    return time.time_ns() // 1_000_000


def _runtime(args: argparse.Namespace, client_name: str) -> McpRuntimeClient:
    token = os.environ.get("ORDIVON_BEARER_TOKEN")
    if not token:
        raise RuntimeError("ORDIVON_BEARER_TOKEN is not set")
    bind = os.environ.get("ORDIVON_BIND", "127.0.0.1:8897")
    endpoint = args.runtime_endpoint or (
        f"http://127.0.0.1:{bind.rsplit(':', 1)[-1]}/mcp"
    )
    runtime = McpRuntimeClient(
        endpoint,
        token,
        client_name=client_name,
        client_version="0.1.0",
    )
    runtime.initialize()
    return runtime


def _git_revision(repo: Path, revision: str | None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", revision or "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    value = completed.stdout.strip()
    if len(value) != 40:
        raise RuntimeError(f"Git returned an invalid revision: {value!r}")
    return value


def _git_worktree_state(repo: Path) -> tuple[bool, str]:
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout
    tracked_diff = subprocess.run(
        ["git", "-C", str(repo), "diff", "--binary", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    untracked = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    untracked_digests: dict[str, JsonValue] = {}
    for raw_path in untracked.split(b"\0"):
        if not raw_path:
            continue
        relative = raw_path.decode("utf-8")
        untracked_digests[relative] = (
            "sha256:" + hashlib.sha256((repo / relative).read_bytes()).hexdigest()
        )
    digest = canonical_digest(
        {
            "status": status,
            "trackedDiffSha256": (
                "sha256:" + hashlib.sha256(tracked_diff).hexdigest()
            ),
            "untrackedDigests": untracked_digests,
        }
    )
    return bool(status), digest


def _write_json(path: Path, value: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, JsonValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return value


def _result(
    label: str,
    *,
    status: str,
) -> AgentTurnResult:
    conclusion = AgentRunConclusion(
        status=status,
        summary=(
            "Pause before the concurrent resume race."
            if status == "needs_input"
            else f"Concurrent contender {label} completed the retained task."
        ),
        unresolved_unknowns=(
            ("release the concurrent contenders",)
            if status == "needs_input"
            else ()
        ),
    )
    return AgentTurnResult(
        model_call_id=f"model-call:concurrent-resume:{label}",
        model_id="ordivon.scripted-model.v1",
        content=None,
        tool_calls=(),
        conclusion=conclusion,
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest(
            {"concurrentResume": label, "status": status}
        ),
    )


def _create_task(storage: HostStorage) -> None:
    HostKernel(
        storage,
        clock_ms=_clock_ms,
        owner_id="host:concurrent-resume-create",
    ).create_task(
        event_id="event:host-harness-concurrent-resume-stress-001:create",
        kind=EventKind.TASK_CREATED,
        task_id=TASK_ID,
        goal_id=GOAL_ID,
        payload={"workloadId": "host-harness-concurrent-resume-stress-001"},
        frontier=(FRONTIER,),
    )


def _phase_prepare(args: argparse.Namespace) -> dict[str, JsonValue]:
    root = args.root.resolve()
    state_root = root / "state"
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise RuntimeError("concurrent resume root must be empty")
    state_root.mkdir()
    source_repo = args.source_repo.resolve()
    source_revision = _git_revision(source_repo, args.source_revision)
    source_worktree_dirty, source_worktree_digest = _git_worktree_state(
        source_repo
    )
    source_digest = canonical_digest(
        {
            "sourceRepo": str(source_repo),
            "sourceRevision": source_revision,
            "sourceWorktreeDigest": source_worktree_digest,
        }
    )
    runtime = _runtime(args, "ordivon-concurrent-resume-prepare")
    opened = runtime.call_tool(
        "workspace.open",
        {
            "schemaVersion": 1,
            "sourceRepo": str(source_repo),
            "sourceRevision": source_revision,
        },
    )
    workspace_id = opened.get("workspaceId")
    if not isinstance(workspace_id, str):
        raise RuntimeError("workspace.open omitted Workspace identity")
    with HostStorage(state_root) as storage:
        _create_task(storage)
        host = HarnessHost(storage, clock_ms=_clock_ms)
        contract = TaskContract(
            contract_id="task-contract:concurrent-resume-stress-001:v1",
            task_id=TASK_ID,
            objective={
                "summary": (
                    "Pause once, then admit at most one result when two fresh "
                    "Harness processes resume the same Snapshot concurrently."
                )
            },
            acceptance_criteria={
                "checks": [
                    "exactly one physical Provider call begins",
                    "the losing contender stops before Provider dispatch",
                    "exactly one logical Run receipt commits",
                    "the Task event history remains valid",
                ]
            },
            constraints=(
                "Both contenders use the same Assignment and Snapshot.",
                "No Runtime Tool effect is required.",
            ),
            resource_refs=(
                StateRef(
                    ref=f"repository:ordivon-harness@{source_revision}",
                    digest=source_digest,
                ),
            ),
            consequence_policy_ref="policy:concurrent-resume-stress-v1",
        )
        result = HarnessRunner(
            host,
            runtime=runtime,
            adapter=ScriptedTurnAdapter((_result("prepare", status="needs_input"),)),
        ).run(
            HarnessRunPlan(
                task_contract=contract,
                context_blocks=(
                    ContextBlock(
                        block_id="context-block:concurrent-resume-stress",
                        kind=BlockKind.TASK,
                        priority=100,
                        required=True,
                        freshness=Freshness.CURRENT,
                        source_digest=source_digest,
                        payload={"instruction": "Pause before the race."},
                    ),
                ),
                workspace_ref=workspace_id,
                tool_grant=ToolGrant(
                    tool_grant_id="tool-grant:concurrent-resume-stress",
                    allowed_tools=("read_workspace",),
                    read_path_rules=("README.md",),
                ),
                token_budget=4_000,
                budget=RunBudget(4, 2, 65_536, 120_000),
                source_ref=f"repository:ordivon-harness@{source_revision}",
                source_digest=source_digest,
            )
        )
        if not result.paused:
            raise RuntimeError("prepare phase did not retain needs_input")
        head = storage.read_task_event(TASK_ID)
        value: dict[str, JsonValue] = {
            "taskId": TASK_ID,
            "workspaceId": workspace_id,
            "sourceRevision": source_revision,
            "sourceDigest": source_digest,
            "sourceWorktreeDirty": source_worktree_dirty,
            "sourceWorktreeDigest": source_worktree_digest,
            "prepareRevision": head.projection.revision,
            "harnessRunId": result.harness_run_id,
            "harnessManifestDigest": ordivon_harness_manifest().digest,
        }
    _write_json(root / "control.json", value)
    return value


class _BarrierAdapter:
    adapter_id = "ordivon.concurrent-resume-barrier.v1"
    model_id = "ordivon.scripted-model.v1"
    provider_request_digest = static_provider_request_digest

    def __init__(self, root: Path, label: str) -> None:
        self.root = root
        self.label = label

    def invoke(self, request):
        provider_request_digest = self.provider_request_digest(request)
        _write_json(
            self.root / f"provider-invoked-{self.label}.json",
            {
                "label": self.label,
                "pid": os.getpid(),
                "turnId": request.turn_id,
                "requestDigest": request.dispatch_digest,
                "providerRequestDigest": provider_request_digest,
                "observedAtMs": _clock_ms(),
            },
        )
        deadline = time.monotonic() + 30
        while not (self.root / "go").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("concurrent resume barrier timed out")
            time.sleep(0.01)
        if self.label == "b":
            time.sleep(0.3)
        return _result(self.label, status="candidate_completed")


def _phase_contender(args: argparse.Namespace) -> dict[str, JsonValue]:
    if args.label is None:
        raise ValueError("contender phase requires --label")
    root = args.root.resolve()
    _write_json(
        root / f"contender-ready-{args.label}.json",
        {
            "label": args.label,
            "pid": os.getpid(),
            "readyAtMs": _clock_ms(),
        },
    )
    start_deadline = time.monotonic() + 30
    while not (root / "start").exists():
        if time.monotonic() >= start_deadline:
            raise RuntimeError("concurrent resume start barrier timed out")
        time.sleep(0.01)
    runtime = _runtime(args, f"ordivon-concurrent-resume-{args.label}")
    started = _clock_ms()
    retry_deadline = time.monotonic() + 30
    transient_failures: list[JsonValue] = []
    while True:
        try:
            with HostStorage(root / "state") as storage:
                host = HarnessHost(storage, clock_ms=_clock_ms)
                result = HarnessRunner(
                    host,
                    runtime=runtime,
                    adapter=_BarrierAdapter(root, args.label),
                ).resume(
                    TASK_ID,
                    additional_messages=(
                        {
                            "role": "user",
                            "content": "Release the retained concurrent resume.",
                        },
                    ),
                    completion_mode=CompletionMode.RECORD,
                )
        except (HarnessSuperseded, HarnessProviderCallClaimHeld) as error:
            transient_failures.append(
                {
                    "errorType": type(error).__name__,
                    "error": str(error),
                    "observedAtMs": _clock_ms(),
                }
            )
            if time.monotonic() >= retry_deadline:
                value = {
                    "label": args.label,
                    "status": "raised",
                    "startedAtMs": started,
                    "completedAtMs": _clock_ms(),
                    "errorType": type(error).__name__,
                    "error": str(error),
                    "transientFailures": transient_failures,
                }
                break
            time.sleep(0.01)
            continue
        except Exception as error:
            value = {
                "label": args.label,
                "status": "raised",
                "startedAtMs": started,
                "completedAtMs": _clock_ms(),
                "errorType": type(error).__name__,
                "error": str(error),
                "transientFailures": transient_failures,
            }
            break
        value = {
            "label": args.label,
            "status": "returned",
            "startedAtMs": started,
            "completedAtMs": _clock_ms(),
            "result": result.to_dict(),
            "runReceiptDigest": (
                None if result.recorded is None else result.recorded.receipt.digest
            ),
            "transientFailures": transient_failures,
        }
        break
    _write_json(root / f"contender-{args.label}.json", value)
    return value


def _child_command(args: argparse.Namespace, label: str) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--phase",
        "contender",
        "--root",
        str(args.root.resolve()),
        "--label",
        label,
        "--source-repo",
        str(args.source_repo.resolve()),
    ]
    if args.runtime_endpoint:
        command.extend(("--runtime-endpoint", args.runtime_endpoint))
    return command


def _phase_all(args: argparse.Namespace) -> dict[str, JsonValue]:
    started = _clock_ms()
    control = _phase_prepare(args)
    processes = [
        subprocess.Popen(
            _child_command(args, label),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for label in ("a", "b")
    ]
    deadline = time.monotonic() + 30
    while not all(
        (args.root.resolve() / f"contender-ready-{label}.json").exists()
        for label in ("a", "b")
    ):
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("a contender exited before the start barrier")
        if time.monotonic() >= deadline:
            raise RuntimeError("contenders did not reach the start barrier")
        time.sleep(0.01)
    (args.root.resolve() / "start").touch()
    while True:
        invoked = [
            label
            for label in ("a", "b")
            if (
                args.root.resolve() / f"provider-invoked-{label}.json"
            ).exists()
        ]
        completed = [
            label
            for label in ("a", "b")
            if (args.root.resolve() / f"contender-{label}.json").exists()
        ]
        if len(invoked) == 1 and completed:
            break
        if len(invoked) > 1:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "one Provider invocation and one pre-dispatch loser were not observed"
            )
        time.sleep(0.01)
    with HostStorage(args.root.resolve() / "state") as storage:
        barrier_status = HarnessRunner(
            HarnessHost(storage, clock_ms=_clock_ms)
        ).status(TASK_ID)
        task_leases_while_provider_blocked: list[JsonValue] = [
            {
                "taskId": lease.task_id,
                "ownerId": lease.owner_id,
                "revision": lease.revision,
                "expiresAtMs": lease.expires_at_ms,
            }
            for lease in storage.journal.lease_records()
        ]
        provider_fence_while_blocked: dict[str, JsonValue] = {
            "taskRevision": barrier_status.task_revision,
            "providerCallStatus": barrier_status.provider_call_status,
            "providerCallGeneration": barrier_status.provider_call_generation,
        }
    (args.root.resolve() / "go").touch()
    child_output: list[dict[str, JsonValue]] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        child_output.append(
            {
                "returnCode": process.returncode,
                "stdout": stdout[-2_048:],
                "stderr": stderr[-2_048:],
            }
        )
    contenders = [
        _read_json(args.root.resolve() / f"contender-{label}.json")
        for label in ("a", "b")
    ]
    with HostStorage(args.root.resolve() / "state") as storage:
        host = HarnessHost(storage, clock_ms=_clock_ms)
        rows = storage.journal.connection.execute(
            "SELECT event_id, stream_revision, payload_digest FROM events "
            "WHERE stream_id = ? AND event_kind = ? ORDER BY stream_revision",
            (TASK_ID, "harness.run-recorded"),
        ).fetchall()
        run_events: list[JsonValue] = [
            {
                "eventId": str(row["event_id"]),
                "revision": int(row["stream_revision"]),
                "payloadDigest": str(row["payload_digest"]),
            }
            for row in rows
        ]
        current = host.load_current_run(TASK_ID)
        history = validate_history(storage)
        head = storage.read_task_event(TASK_ID)
    returned = [item for item in contenders if item["status"] == "returned"]
    raised = [item for item in contenders if item["status"] == "raised"]
    provider_invocations = [
        _read_json(
            args.root.resolve() / f"provider-invoked-{label}.json"
        )
        for label in ("a", "b")
        if (
            args.root.resolve() / f"provider-invoked-{label}.json"
        ).exists()
    ]
    accepted = (
        len(returned) == 1
        and len(raised) == 1
        and len(provider_invocations) == 1
        and len(run_events) == 1
        and raised[0].get("errorType")
        == HarnessProviderCallRecoveryRequired.__name__
        and provider_fence_while_blocked["providerCallStatus"] == "dispatching"
        and provider_fence_while_blocked["providerCallGeneration"] == 1
        and not task_leases_while_provider_blocked
        and history.provider_semantic_link_checks > 0
    )
    evidence: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.host-harness-concurrent-resume-stress-evidence",
        "taskId": TASK_ID,
        "harnessRunId": control["harnessRunId"],
        "harnessManifestDigest": control["harnessManifestDigest"],
        "sourceRevision": control["sourceRevision"],
        "sourceWorktreeDirty": control["sourceWorktreeDirty"],
        "sourceWorktreeDigest": control["sourceWorktreeDigest"],
        "workspaceId": control["workspaceId"],
        "startedAtMs": started,
        "completedAtMs": _clock_ms(),
        "prepareRevision": control["prepareRevision"],
        "contenders": contenders,
        "providerInvocations": provider_invocations,
        "providerFenceWhileBlocked": provider_fence_while_blocked,
        "taskLeasesWhileProviderBlocked": task_leases_while_provider_blocked,
        "childProcesses": child_output,
        "runRecordedEvents": run_events,
        "finalRunReceiptDigest": current.receipt.digest,
        "finalTaskRevision": head.projection.revision,
        "finalTaskState": head.projection.state.value,
        "historyValidation": history.to_dict(),
        "accepted": accepted,
        "failure": (
            None
            if accepted
            else (
                "concurrent resumes entered more than one physical Provider call, "
                "committed more than one result, retained a Host Task lease across "
                "Provider dispatch, lacked a durable dispatch fence, or failed "
                "Provider history semantic validation"
            )
        ),
    }
    if args.evidence_out is not None:
        _write_json(args.evidence_out.resolve(), evidence)
    runtime = _runtime(args, "ordivon-concurrent-resume-cleanup")
    runtime.call_tool(
        "workspace.close",
        {
            "schemaVersion": 1,
            "workspaceId": control["workspaceId"],
            "force": True,
        },
    )
    return evidence


def main() -> int:
    args = parse_args()
    try:
        value = {
            "all": _phase_all,
            "prepare": _phase_prepare,
            "contender": _phase_contender,
        }[args.phase](args)
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if args.phase != "all" or value["accepted"] is True else 1
    except Exception as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

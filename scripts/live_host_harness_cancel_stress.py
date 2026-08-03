#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from anc_canonical import JsonValue, canonical_digest
from ordivon_host import EventKind, HostKernel, HostStorage, StateRef
from ordivon_host.cognition import BlockKind, ContextBlock, Freshness
from ordivon_host.runtime import McpRuntimeClient
from ordivon_harness import (
    GrantedExecutionCheck,
    HarnessHost,
    HarnessRunPlan,
    HarnessRunner,
    TaskContract,
    ToolGrant,
)
from ordivon_harness.ordivon import (
    AgentToolCall,
    AgentTurnResult,
    CancellationToken,
    RunBudget,
    RunStopCode,
    ScriptedTurnAdapter,
)
from ordivon_harness.protocol import HarnessToolStepReceipt

TASK_ID = "task:host-harness-cancel-stress-001"
GOAL_ID = "goal:host-harness-dogfood"
FRONTIER = "node:host-harness-cancel-stress-001:work"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cancel a real in-flight Runtime Job through Harness and compare Runtime, "
            "Tool Step receipt, Run receipt and Host projection."
        )
    )
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument(
        "--source-repo",
        type=Path,
        default=Path("/root/projects/ordivon-harness"),
    )
    parser.add_argument("--source-revision")
    parser.add_argument("--runtime-endpoint")
    parser.add_argument("--evidence-out", type=Path, required=True)
    return parser.parse_args()


def _clock_ms() -> int:
    return time.time_ns() // 1_000_000


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


def _runtime(args: argparse.Namespace) -> McpRuntimeClient:
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
        client_name="ordivon-host-harness-cancel-stress",
        client_version="0.1.0",
    )
    runtime.initialize()
    return runtime


def _write_json(path: Path, value: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class _CancelAfterDispatchRuntime:
    def __init__(
        self,
        inner: McpRuntimeClient,
        cancellation: CancellationToken,
    ) -> None:
        self.inner = inner
        self.cancellation = cancellation
        self.dispatched = threading.Event()
        self.cancel_triggered = threading.Event()
        self.job_id: str | None = None

    def initialize(self):
        return self.inner.initialize()

    def list_tools(self):
        return self.inner.list_tools()

    def call_tool(
        self, name: str, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        value = self.inner.call_tool(name, arguments)
        if name == "workspace.exec":
            job_id = value.get("jobId")
            if isinstance(job_id, str):
                self.job_id = job_id
                self.dispatched.set()

                def trigger() -> None:
                    time.sleep(0.2)
                    self.cancellation.cancel()
                    self.cancel_triggered.set()

                threading.Thread(target=trigger, daemon=True).start()
        return value


def _historical_tool_step_receipt(
    storage: HostStorage,
    *,
    harness_run_id: str,
    tool_call_id: str,
) -> tuple[HarnessToolStepReceipt, str]:
    matches: list[tuple[HarnessToolStepReceipt, str]] = []
    for retained in storage.journal.object_refs():
        if retained.kind != "harness-tool-step-receipt":
            continue
        raw = storage.objects.get(
            retained.digest,
            expected_kind="harness-tool-step-receipt",
        )
        if not isinstance(raw, dict):
            continue
        receipt = HarnessToolStepReceipt.from_dict(raw)
        if (
            receipt.harness_run_id == harness_run_id
            and receipt.tool_call_id == tool_call_id
        ):
            matches.append((receipt, retained.digest))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one historical Tool Step receipt, found {len(matches)}"
        )
    return matches[0]


def run(args: argparse.Namespace) -> dict[str, JsonValue]:
    state_root = args.state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    if any(state_root.iterdir()):
        raise RuntimeError("cancel stress state root must be empty")
    source_repo = args.source_repo.resolve()
    source_revision = _git_revision(source_repo, args.source_revision)
    source_digest = canonical_digest(
        {"sourceRepo": str(source_repo), "sourceRevision": source_revision}
    )
    runtime = _runtime(args)
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
    cancellation = CancellationToken()
    instrumented = _CancelAfterDispatchRuntime(runtime, cancellation)
    started_at_ms = _clock_ms()
    try:
        with HostStorage(state_root) as storage:
            HostKernel(
                storage,
                clock_ms=_clock_ms,
                owner_id="host:cancel-stress-create",
            ).create_task(
                event_id="event:host-harness-cancel-stress-001:create",
                kind=EventKind.TASK_CREATED,
                task_id=TASK_ID,
                goal_id=GOAL_ID,
                payload={"workloadId": "host-harness-cancel-stress-001"},
                frontier=(FRONTIER,),
            )
            contract = TaskContract(
                contract_id="task-contract:host-harness-cancel-stress-001:v1",
                task_id=TASK_ID,
                objective={
                    "summary": (
                        "Start a 30-second Runtime check, cancel it only after a real "
                        "Job identity is returned, and retain matching terminal evidence."
                    )
                },
                acceptance_criteria={
                    "checks": [
                        "Cancellation is requested only after Runtime dispatch.",
                        "Runtime reports the exact Job as cancelled.",
                        "The terminal Harness Tool Step receipt binds that Job.",
                        "The recorded Run terminates as cancelled.",
                    ]
                },
                constraints=(
                    "Do not synthesize or replace the Runtime Job identity.",
                    "Do not close the Workspace before terminal observation.",
                ),
                resource_refs=(
                    StateRef(
                        ref=f"repository:ordivon-harness@{source_revision}",
                        digest=source_digest,
                    ),
                ),
                consequence_policy_ref="policy:cancel-stress-v1",
            )
            context = ContextBlock(
                block_id="context-block:cancel-stress",
                kind=BlockKind.TASK,
                priority=100,
                required=True,
                freshness=Freshness.CURRENT,
                source_digest=source_digest,
                payload={"instruction": "Run the granted long check once."},
            )
            adapter = ScriptedTurnAdapter(
                (
                    AgentTurnResult(
                        model_call_id="model-call:cancel-stress:dispatch",
                        model_id="ordivon.scripted-model.v1",
                        content=None,
                        tool_calls=(
                            AgentToolCall(
                                "tool-call:cancel-stress:run",
                                "run_check",
                                {
                                    "checkId": "check:cancel-stress:sleep",
                                    "waitMs": 30_000,
                                },
                            ),
                        ),
                        conclusion=None,
                        usage={"inputTokens": 1, "outputTokens": 1},
                        finish_reason="tool_calls",
                        raw_response_digest=canonical_digest(
                            {"cancelStress": "dispatch"}
                        ),
                    ),
                )
            )
            host = HarnessHost(storage, clock_ms=_clock_ms)
            result = HarnessRunner(
                host,
                runtime=instrumented,
                adapter=adapter,
            ).run(
                HarnessRunPlan(
                    task_contract=contract,
                    context_blocks=(context,),
                    workspace_ref=workspace_id,
                    tool_grant=ToolGrant(
                        tool_grant_id="tool-grant:cancel-stress:v1",
                        allowed_tools=("run_check",),
                        execution_checks=(
                            GrantedExecutionCheck(
                                check_id="check:cancel-stress:sleep",
                                executable="/usr/bin/sleep",
                                args=("30",),
                                timeout_ms=60_000,
                            ),
                        ),
                    ),
                    token_budget=8_000,
                    budget=RunBudget(3, 2, 262_144, 120_000),
                    source_ref=f"repository:ordivon-harness@{source_revision}",
                    source_digest=source_digest,
                ),
                cancellation=cancellation,
            )
            if instrumented.job_id is None:
                raise RuntimeError("Harness never received a Runtime Job identity")
            runtime_observation = runtime.call_tool(
                "task.observe",
                {
                    "schemaVersion": 1,
                    "jobId": instrumented.job_id,
                    "waitMs": 5_000,
                    "stdoutTailBytes": 8_192,
                    "stderrTailBytes": 8_192,
                },
            )
            recorded = host.load_current_run(TASK_ID)
            run_receipt = recorded.receipt
            receipt, receipt_object_digest = _historical_tool_step_receipt(
                storage,
                harness_run_id=run_receipt.harness_run_id,
                tool_call_id="tool-call:cancel-stress:run",
            )
            head = storage.read_task_event(TASK_ID)
            evidence: dict[str, JsonValue] = {
                "schemaVersion": 1,
                "kind": "ordivon.host-harness-cancel-stress-evidence",
                "taskId": TASK_ID,
                "workspaceId": workspace_id,
                "sourceRevision": source_revision,
                "startedAtMs": started_at_ms,
                "completedAtMs": _clock_ms(),
                "cancellationRequestedAtMs": cancellation.requested_at_ms,
                "cancelTriggeredAfterDispatch": (
                    instrumented.dispatched.is_set()
                    and instrumented.cancel_triggered.is_set()
                ),
                "runtimeJobId": instrumented.job_id,
                "runtimeObservation": runtime_observation,
                "toolStepIntentDigest": receipt.intent_digest,
                "toolStepReceipt": receipt.to_dict(),
                "toolStepReceiptObjectDigest": receipt_object_digest,
                "runReceiptDigest": run_receipt.digest,
                "runTerminationCode": run_receipt.termination_code,
                "loopStopCode": result.loop_result.stop_code.value,
                "finalTaskState": head.projection.state.value,
                "finalTaskRevision": head.projection.revision,
                "accepted": (
                    instrumented.dispatched.is_set()
                    and instrumented.cancel_triggered.is_set()
                    and runtime_observation.get("status") == "cancelled"
                    and receipt.runtime_job_ref == instrumented.job_id
                    and receipt.terminal
                    and result.loop_result.stop_code is RunStopCode.CANCELLED
                    and run_receipt.termination_code == "cancelled"
                ),
            }
        _write_json(args.evidence_out.resolve(), evidence)
        return evidence
    finally:
        try:
            runtime.call_tool(
                "workspace.close",
                {
                    "schemaVersion": 1,
                    "workspaceId": workspace_id,
                    "force": True,
                },
            )
        except Exception:
            pass


def main() -> int:
    args = parse_args()
    try:
        evidence = run(args)
        print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if evidence["accepted"] is True else 1
    except Exception as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from anc_canonical import JsonValue, canonical_digest
from ordivon_host import EventKind, HostKernel, HostStorage, StateRef, TaskState
from ordivon_host.cognition import BlockKind, ContextBlock, Freshness
from ordivon_host.runtime import McpRuntimeClient
from ordivon_harness import (
    CompletionMode,
    HarnessHost,
    HarnessRunPlan,
    HarnessRunner,
    TaskContract,
    ToolGrant,
)
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnResult,
    DeepSeekSettings,
    DeepSeekTurnAdapter,
    HostHarnessRunStore,
    RunBudget,
    ScriptedTurnAdapter,
    ordivon_harness_manifest,
)

TASK_ID = "task:host-harness-resume-stress-001"
GOAL_ID = "goal:host-harness-dogfood"
FRONTIER = "node:host-harness-resume-stress-001:work"
EXPECTED_HEADING = "# Ordivon Harness"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stress needs_input continuity across three fresh Host/Harness processes "
            "against a real Runtime and a final DeepSeek turn."
        )
    )
    parser.add_argument(
        "--phase",
        choices=("all", "prepare", "duplicate-probe", "resume"),
        default="all",
    )
    parser.add_argument("--root", type=Path, required=True)
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
        default=Path("/root/.config/ordivon/secrets/deepseek.json"),
    )
    parser.add_argument(
        "--model",
        choices=("deepseek-v4-flash", "deepseek-v4-pro"),
        default="deepseek-v4-pro",
    )
    parser.add_argument("--evidence-out", type=Path)
    return parser.parse_args()


def _clock_ms() -> int:
    return time.time_ns() // 1_000_000


def _runtime_endpoint(explicit: str | None) -> str:
    if explicit:
        return explicit
    bind = os.environ.get("ORDIVON_BIND", "127.0.0.1:8897")
    return f"http://127.0.0.1:{bind.rsplit(':', 1)[-1]}/mcp"


def _runtime(args: argparse.Namespace, client_name: str) -> McpRuntimeClient:
    token = os.environ.get("ORDIVON_BEARER_TOKEN")
    if not token:
        raise RuntimeError("ORDIVON_BEARER_TOKEN is not set")
    runtime = McpRuntimeClient(
        _runtime_endpoint(args.runtime_endpoint),
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


def _settings(args: argparse.Namespace) -> DeepSeekSettings:
    return replace(
        DeepSeekSettings.from_secret_file(args.deepseek_secret),
        model=args.model,
        max_output_tokens=4_096,
    )


def _scripted_adapter(
    model_id: str, results: tuple[AgentTurnResult, ...]
) -> ScriptedTurnAdapter:
    if any(result.model_id != model_id for result in results):
        raise ValueError("scripted result model identity differs from selected model")
    adapter = ScriptedTurnAdapter(results)
    adapter.model_id = model_id
    return adapter


def _result(
    model_id: str,
    suffix: str,
    *,
    calls: tuple[AgentToolCall, ...] = (),
    conclusion: AgentRunConclusion | None = None,
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:resume-stress:{suffix}",
        model_id=model_id,
        content=None,
        tool_calls=calls,
        conclusion=conclusion,
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"resumeStress": suffix}),
    )


def _contract(source_revision: str, source_digest: str) -> TaskContract:
    return TaskContract(
        contract_id="task-contract:host-harness-resume-stress-001:v1",
        task_id=TASK_ID,
        objective={
            "summary": (
                "Read README.md once, survive two needs_input process boundaries, "
                "and report the exact first Markdown heading from retained evidence."
            ),
            "target": {
                "kind": "repository-file",
                "relativePath": "README.md",
                "sourceRevision": source_revision,
            },
        },
        acceptance_criteria={
            "checks": [
                "Exactly one successful README read is retained as an Observation.",
                "A duplicate full read in a fresh process is rejected before Runtime dispatch.",
                "A third fresh process can complete from the retained Observation.",
                f"The retained first heading is exactly {EXPECTED_HEADING}.",
            ]
        },
        constraints=(
            "The workload is read-only.",
            "Do not discard or reconstruct the first read from transcript prose.",
            "Retain all pause snapshots and Tool Observations in Host state.",
        ),
        resource_refs=(
            StateRef(
                ref=f"repository:ordivon-harness@{source_revision}",
                digest=source_digest,
            ),
        ),
        consequence_policy_ref="policy:read-only-resume-stress-v1",
    )


def _context(source_revision: str) -> ContextBlock:
    return ContextBlock(
        block_id="context-block:resume-stress:readme",
        kind=BlockKind.TASK,
        priority=100,
        required=True,
        freshness=Freshness.CURRENT,
        source_digest=canonical_digest(
            {"sourceRevision": source_revision, "relativePath": "README.md"}
        ),
        payload={
            "instruction": (
                "Read README.md once. The run will cross multiple process boundaries; "
                "later turns must use the retained Tool Observation."
            ),
            "relativePath": "README.md",
        },
    )


def _create_task(storage: HostStorage) -> None:
    HostKernel(
        storage,
        clock_ms=_clock_ms,
        owner_id="host:resume-stress-create",
    ).create_task(
        event_id="event:host-harness-resume-stress-001:create",
        kind=EventKind.TASK_CREATED,
        task_id=TASK_ID,
        goal_id=GOAL_ID,
        payload={"workloadId": "host-harness-resume-stress-001"},
        frontier=(FRONTIER,),
    )


def _phase_prepare(args: argparse.Namespace) -> dict[str, JsonValue]:
    root = args.root.resolve()
    state_root = root / "state"
    root.mkdir(parents=True, exist_ok=True)
    if state_root.exists() and any(state_root.iterdir()):
        raise RuntimeError("resume stress state root must be empty")
    state_root.mkdir(parents=True, exist_ok=True)
    source_repo = args.source_repo.resolve()
    source_revision = _git_revision(source_repo, args.source_revision)
    source_digest = canonical_digest(
        {"sourceRepo": str(source_repo), "sourceRevision": source_revision}
    )
    runtime = _runtime(args, "ordivon-resume-stress-prepare")
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
    model_id = _settings(args).model
    with HostStorage(state_root) as storage:
        _create_task(storage)
        host = HarnessHost(storage, clock_ms=_clock_ms)
        adapter = _scripted_adapter(
            model_id,
            (
                _result(
                    model_id,
                    "prepare-read",
                    calls=(
                        AgentToolCall(
                            "tool-call:resume-stress:prepare-read",
                            "read_workspace",
                            {
                                "relativePath": "README.md",
                                "mode": "FULL",
                                "maxBytes": 65_536,
                            },
                        ),
                    ),
                ),
                _result(
                    model_id,
                    "prepare-pause",
                    conclusion=AgentRunConclusion(
                        status="needs_input",
                        summary="The README is retained; authorize continuity testing.",
                        unresolved_unknowns=("operator continuity authorization",),
                    ),
                ),
            ),
        )
        result = HarnessRunner(host, runtime=runtime, adapter=adapter).run(
            HarnessRunPlan(
                task_contract=_contract(source_revision, source_digest),
                context_blocks=(_context(source_revision),),
                workspace_ref=workspace_id,
                tool_grant=ToolGrant(
                    tool_grant_id="tool-grant:resume-stress:read-only",
                    allowed_tools=("read_workspace",),
                    read_path_rules=("README.md",),
                ),
                token_budget=12_000,
                budget=RunBudget(8, 6, 524_288, 300_000, 131_072, 2, 4),
                source_ref=f"repository:ordivon-harness@{source_revision}",
                source_digest=source_digest,
            )
        )
        if not result.paused or result.loop_result.tool_calls != 1:
            raise RuntimeError("prepare phase did not pause after one read")
        retained = HostHarnessRunStore(
            host, host.load_current_assignment(TASK_ID)
        ).load_current_snapshot()
        value: dict[str, JsonValue] = {
            "phase": "prepare",
            "taskId": TASK_ID,
            "workspaceId": workspace_id,
            "sourceRepo": str(source_repo),
            "sourceRevision": source_revision,
            "sourceDigest": source_digest,
            "modelId": model_id,
            "stopCode": result.loop_result.stop_code.value,
            "modelCalls": result.loop_result.model_calls,
            "toolCalls": result.loop_result.tool_calls,
            "observationCount": len(retained.state.observations),
            "snapshotDigest": retained.snapshot.digest,
            "snapshotObjectDigest": retained.snapshot_object.digest,
        }
    _write_json(root / "prepare.json", value)
    return value


def _phase_duplicate_probe(args: argparse.Namespace) -> dict[str, JsonValue]:
    root = args.root.resolve()
    control = _read_json(root / "prepare.json")
    runtime = _runtime(args, "ordivon-resume-stress-duplicate-probe")
    model_id = str(control["modelId"])
    with HostStorage(root / "state") as storage:
        host = HarnessHost(storage, clock_ms=_clock_ms)
        before = HostHarnessRunStore(
            host, host.load_current_assignment(TASK_ID)
        ).load_current_snapshot()
        existing = next(
            (
                item
                for item in reversed(before.state.observations)
                if item.get("toolCallId")
                == "tool-call:resume-stress:duplicate-read"
            ),
            None,
        )
        if existing is not None:
            value = {
                "phase": "duplicate-probe",
                "stopCode": "needs_input",
                "modelCalls": len(before.state.seen_model_call_ids),
                "toolCalls": len(before.state.seen_tool_call_ids),
                "addedObservation": existing,
                "rejectedBeforeDispatch": (
                    existing.get("status") == "rejected"
                    and existing.get("runtimeJobRef") is None
                    and isinstance(
                        existing.get("structuredContent", {}).get("error"),
                        dict,
                    )
                ),
                "snapshotDigest": before.snapshot.digest,
                "snapshotObjectDigest": before.snapshot_object.digest,
            }
            _write_json(root / "duplicate-probe.json", value)
            return value
        adapter = _scripted_adapter(
            model_id,
            (
                _result(
                    model_id,
                    "probe-duplicate-read",
                    calls=(
                        AgentToolCall(
                            "tool-call:resume-stress:duplicate-read",
                            "read_workspace",
                            {
                                "relativePath": "README.md",
                                "mode": "FULL",
                                "maxBytes": 65_536,
                            },
                        ),
                    ),
                ),
                _result(
                    model_id,
                    "probe-pause",
                    conclusion=AgentRunConclusion(
                        status="needs_input",
                        summary="The deliberate duplicate read probe completed.",
                        unresolved_unknowns=("authorize final provider turn",),
                    ),
                ),
            ),
        )
        result = HarnessRunner(host, runtime=runtime, adapter=adapter).resume(
            TASK_ID,
            additional_messages=(
                {
                    "role": "user",
                    "content": (
                        "Deliberately request the same FULL README.md read again. "
                        "This is a continuity guard probe."
                    ),
                },
            ),
        )
        after = HostHarnessRunStore(
            host, host.load_current_assignment(TASK_ID)
        ).load_current_snapshot()
        added = after.state.observations[len(before.state.observations) :]
        if not result.paused or len(added) != 1:
            raise RuntimeError("duplicate probe did not retain exactly one Observation")
        duplicate = added[0]
        value: dict[str, JsonValue] = {
            "phase": "duplicate-probe",
            "stopCode": result.loop_result.stop_code.value,
            "modelCalls": result.loop_result.model_calls,
            "toolCalls": result.loop_result.tool_calls,
            "addedObservation": duplicate,
            "rejectedBeforeDispatch": (
                duplicate.get("status") == "rejected"
                and duplicate.get("runtimeJobRef") is None
                and isinstance(
                    duplicate.get("structuredContent", {}).get("error"),
                    dict,
                )
            ),
            "snapshotDigest": after.snapshot.digest,
            "snapshotObjectDigest": after.snapshot_object.digest,
        }
    _write_json(root / "duplicate-probe.json", value)
    return value


def _first_heading(content: str) -> str | None:
    return next(
        (
            line.strip()
            for line in content.splitlines()
            if line.strip().startswith("# ")
        ),
        None,
    )


def _phase_resume(args: argparse.Namespace) -> dict[str, JsonValue]:
    root = args.root.resolve()
    control = _read_json(root / "prepare.json")
    probe = _read_json(root / "duplicate-probe.json")
    runtime = _runtime(args, "ordivon-resume-stress-deepseek")
    verification: dict[str, JsonValue] = {}
    with HostStorage(root / "state") as storage:
        host = HarnessHost(storage, clock_ms=_clock_ms)

        def verify(proposal):
            current = host.load_current_run(proposal.task_id)
            observed_reads = 0
            rejected_reads = 0
            runtime_job_refs: list[JsonValue] = []
            heading: str | None = None
            for retained in current.observation_objects:
                raw = storage.objects.get(
                    retained.digest,
                    expected_kind="harness-tool-observation",
                )
                if not isinstance(raw, dict) or raw.get("toolName") != "read_workspace":
                    continue
                if raw.get("status") == "observed":
                    observed_reads += 1
                    job_ref = raw.get("runtimeJobRef")
                    if isinstance(job_ref, str):
                        runtime_job_refs.append(job_ref)
                    structured = raw.get("structuredContent")
                    if isinstance(structured, dict):
                        content = structured.get("content")
                        if isinstance(content, str):
                            heading = _first_heading(content)
                elif raw.get("status") == "rejected":
                    rejected_reads += 1
            accepted = (
                observed_reads == 1
                and rejected_reads >= 1
                and heading == EXPECTED_HEADING
                and probe.get("rejectedBeforeDispatch") is True
            )
            verification.update(
                {
                    "method": "retained-observation-continuity-v1",
                    "observedReadCount": observed_reads,
                    "rejectedReadCount": rejected_reads,
                    "runtimeJobRefs": runtime_job_refs,
                    "observedHeading": heading,
                    "expectedHeading": EXPECTED_HEADING,
                    "accepted": accepted,
                }
            )
            return (
                accepted,
                None if accepted else "retained read continuity checks failed",
                dict(verification),
            )

        settings = _settings(args)
        runner = HarnessRunner(
            host,
            runtime=runtime,
            adapter=DeepSeekTurnAdapter(settings),
            artifact_exists=lambda _: False,
            acceptance_verifier=verify,
            verification_method="retained-observation-continuity-v1",
        )
        result = runner.resume(
            TASK_ID,
            additional_messages=(
                {
                    "role": "user",
                    "content": (
                        "Authorization granted. Do not call any Tool. Use the retained "
                        "successful README Observation, report its exact first Markdown "
                        f"heading ({EXPECTED_HEADING}), and submit candidate_completed now."
                    ),
                },
            ),
            completion_mode=CompletionMode.ADJUDICATE,
        )
        head = storage.read_task_event(TASK_ID)
        recorded = host.load_current_run(TASK_ID)
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.host-harness-resume-stress-evidence",
            "taskId": TASK_ID,
            "sourceRevision": control["sourceRevision"],
            "workspaceId": control["workspaceId"],
            "modelId": settings.model,
            "startedAtMs": recorded.receipt.started_at_ms,
            "completedAtMs": recorded.receipt.finished_at_ms,
            "harnessManifestDigest": ordivon_harness_manifest().digest,
            "prepare": control,
            "duplicateProbe": probe,
            "finalResult": result.to_dict(),
            "runReceiptDigest": recorded.receipt.digest,
            "traceDigest": result.loop_result.trace.digest,
            "traceEventCount": len(result.loop_result.trace.events),
            "verification": verification,
            "finalTaskState": head.projection.state.value,
            "finalTaskRevision": head.projection.revision,
            "accepted": (
                result.decision is not None
                and result.decision.decision.accepted
                and head.projection.state is TaskState.COMPLETED
            ),
        }
    _write_json(root / "resume.json", value)
    return value


def _child_command(args: argparse.Namespace, phase: str) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--phase",
        phase,
        "--root",
        str(args.root.resolve()),
        "--source-repo",
        str(args.source_repo.resolve()),
        "--deepseek-secret",
        str(args.deepseek_secret.resolve()),
        "--model",
        args.model,
    ]
    if args.source_revision:
        command.extend(("--source-revision", args.source_revision))
    if args.runtime_endpoint:
        command.extend(("--runtime-endpoint", args.runtime_endpoint))
    return command


def _phase_all(args: argparse.Namespace) -> dict[str, JsonValue]:
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise RuntimeError("resume stress root must be empty")
    for phase in ("prepare", "duplicate-probe", "resume"):
        subprocess.run(_child_command(args, phase), check=True)
    evidence = _read_json(root / "resume.json")
    if args.evidence_out is not None:
        _write_json(args.evidence_out.resolve(), evidence)
    workspace_id = evidence.get("workspaceId")
    if isinstance(workspace_id, str):
        runtime = _runtime(args, "ordivon-resume-stress-cleanup")
        runtime.call_tool(
            "workspace.close",
            {"schemaVersion": 1, "workspaceId": workspace_id, "force": True},
        )
    return evidence


def main() -> int:
    args = parse_args()
    try:
        value = {
            "prepare": _phase_prepare,
            "duplicate-probe": _phase_duplicate_probe,
            "resume": _phase_resume,
            "all": _phase_all,
        }[args.phase](args)
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if args.phase != "all" or value.get("accepted") is True else 1
    except Exception as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

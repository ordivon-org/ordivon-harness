#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ordivon_harness.interaction_context import (
    InteractionAffordance,
    InteractionContextInput,
    InteractionSourceRef,
    compile_interaction_context,
)
from ordivon_harness.ordivon.model import AgentToolDefinition

REVISION = "first-interface-finance-workstation-composition-v0"


class RuntimeClient(Protocol):
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class OwnerCall:
    owner: str
    operation: str
    runtime_job_id: str
    runtime_attempt_id: str | None
    runtime_status: str
    envelope: dict[str, Any]


def _tool(name: str, description: str) -> AgentToolDefinition:
    return AgentToolDefinition(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


ADMITTED_TOOLS = (
    _tool("finance_observe", "Run the Finance owner's canonical observation only."),
    _tool(
        "workstation_egress_observe",
        "Read the Workstation owner's current scoped-egress projection only.",
    ),
    _tool(
        "workstation_egress_pool_ensure",
        "Reconcile the Workstation loopback egress pool only when separately authorized.",
    ),
)

_OWNER_STDOUT_LIMIT_BYTES = 3_000_000
_ARTIFACT_READ_MAX_BYTES = 1_048_576


def _complete_owner_stdout(
    client: RuntimeClient,
    result: dict[str, Any],
    *,
    owner: str,
    operation: str,
) -> str:
    stdout = result.get("stdoutTail")
    artifacts = result.get("artifacts")
    stdout_artifacts = (
        [
            artifact
            for artifact in artifacts
            if isinstance(artifact, dict) and artifact.get("kind") == "stdout"
        ]
        if isinstance(artifacts, list)
        else []
    )
    if len(stdout_artifacts) > 1:
        raise RuntimeError(f"{owner} {operation} Runtime result has multiple stdout artifacts")
    if not stdout_artifacts:
        if not isinstance(stdout, str) or not stdout.strip():
            raise RuntimeError(f"{owner} {operation} Runtime result omitted owner stdout")
        return stdout

    artifact = stdout_artifacts[0]
    dropped_bytes = artifact.get("droppedBytes")
    if artifact.get("truncated") is True or (
        isinstance(dropped_bytes, int) and dropped_bytes > 0
    ):
        raise RuntimeError(f"{owner} {operation} stdout exceeded runner retention bound")

    retained_bytes = artifact.get("retainedBytes")
    tail_bytes = len(stdout.encode("utf-8")) if isinstance(stdout, str) else 0
    if (
        isinstance(retained_bytes, int)
        and retained_bytes <= tail_bytes
        and isinstance(stdout, str)
        and stdout.strip()
    ):
        return stdout

    job_id = result.get("jobId")
    artifact_id = artifact.get("artifactId")
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError(f"{owner} {operation} Runtime result omitted Job identity")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise RuntimeError(f"{owner} {operation} Runtime result omitted stdout Artifact identity")

    chunks: list[str] = []
    offset = 0
    while True:
        chunk = client.call_tool(
            "artifact.read",
            {
                "jobId": job_id,
                "artifactId": artifact_id,
                "offset": offset,
                "maxBytes": _ARTIFACT_READ_MAX_BYTES,
            },
        )
        content = chunk.get("content")
        if not isinstance(content, str):
            raise TypeError(f"{owner} {operation} stdout Artifact read omitted content")
        chunks.append(content)
        if chunk.get("eof") is True:
            break
        next_offset = chunk.get("nextOffset")
        if not isinstance(next_offset, int) or next_offset <= offset:
            raise RuntimeError(f"{owner} {operation} stdout Artifact read did not advance")
        offset = next_offset

    complete = "".join(chunks)
    if not complete.strip():
        raise RuntimeError(f"{owner} {operation} stdout Artifact was empty")
    if isinstance(retained_bytes, int) and len(complete.encode("utf-8")) != retained_bytes:
        raise RuntimeError(f"{owner} {operation} stdout Artifact byte length mismatched Runtime")
    return complete


def _domain_exec(
    client: RuntimeClient,
    *,
    owner: str,
    workspace_id: str,
    script: str,
    operation: str,
    arguments: dict[str, Any],
    client_request_id: str,
    env: dict[str, str] | None = None,
) -> OwnerCall:
    result = client.call_tool(
        "workspace.exec",
        {
            "clientRequestId": client_request_id,
            "execution": {
                "workspaceId": workspace_id,
                "cwdRelative": ".",
                "executable": "/usr/bin/node",
                "args": [
                    script,
                    "call",
                    "--operation",
                    operation,
                    "--arguments-json",
                    json.dumps(arguments, sort_keys=True, separators=(",", ":")),
                ],
                "env": dict(env or {}),
                "timeoutMs": 30000,
                "stdoutLimitBytes": _OWNER_STDOUT_LIMIT_BYTES,
                "stderrLimitBytes": 16384,
            },
            "waitMs": 30000,
            "stdoutTailBytes": 65536,
            "stderrTailBytes": 16384,
        },
    )
    if result.get("semanticCompletionEvaluated") is not False:
        raise RuntimeError("Runtime must not claim domain semantic completion")
    stdout = _complete_owner_stdout(client, result, owner=owner, operation=operation)
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{owner} {operation} emitted non-JSON owner stdout") from error
    if not isinstance(envelope, dict):
        raise TypeError(f"{owner} {operation} owner envelope must be an object")
    return OwnerCall(
        owner=owner,
        operation=operation,
        runtime_job_id=str(result.get("jobId")),
        runtime_attempt_id=(
            str(result.get("attemptId")) if result.get("attemptId") is not None else None
        ),
        runtime_status=str(result.get("status")),
        envelope=envelope,
    )


def _finance_env(state_root: str, app_python: str) -> dict[str, str]:
    root = Path(state_root)
    return {
        "ORDIVON_FINANCE_STATE_ROOT": str(root),
        "ORDIVON_FINANCE_STATE_DB": str(root / "control" / "finance.db"),
        "ORDIVON_FINANCE_APP_PYTHON": app_python,
    }


def _materialized_stage(label: str, context: InteractionContextInput) -> dict[str, Any]:
    materialized = compile_interaction_context(
        context,
        ADMITTED_TOOLS,
        logical_ref=f"interaction://finance-workstation/{label}",
        logical_generation=label,
    )
    source_dict = materialized.source.to_dict()
    return {
        "label": label,
        "selectedTools": list(materialized.selected_tool_names),
        "projectionDigest": materialized.projection_digest,
        "sourceBytes": len(
            json.dumps(source_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "toolWorkingSet": materialized.tool_working_set,
        "claims": materialized.to_dict()["claims"],
    }


def _initial_context(state_version: str) -> InteractionContextInput:
    return InteractionContextInput(
        intent="finance.current-state-and-next-action",
        sources=(
            InteractionSourceRef(
                "ordivon-finance",
                "finance://state/control",
                state_version,
                "OBSERVATION_CURRENTNESS_REQUIRED",
            ),
        ),
        affordances=(
            InteractionAffordance(
                "finance_observe",
                "ordivon-finance",
                "AVAILABLE",
                "CANONICAL_OBSERVATION_EXTERNAL_READ_NO_FINANCIAL_WRITE",
            ),
            InteractionAffordance(
                "workstation_egress_observe",
                "ordivon-workstation",
                "BLOCKED",
                "READ_ONLY",
                requires=("finance egress blocker observed",),
            ),
            InteractionAffordance(
                "workstation_egress_pool_ensure",
                "ordivon-workstation",
                "BLOCKED",
                "RECONCILABLE_ENVIRONMENT_MUTATION",
                requires=("repair proven necessary", "separate mutation authority"),
            ),
        ),
        raw_escape_available=True,
    )


def _recovery_context(error_code: str) -> InteractionContextInput:
    return InteractionContextInput(
        intent="finance.current-state-and-next-action",
        sources=(
            InteractionSourceRef(
                "ordivon-finance",
                "finance://observe/error",
                error_code,
                "CURRENT_FAILURE_EVIDENCE",
            ),
        ),
        affordances=(
            InteractionAffordance(
                "finance_observe",
                "ordivon-finance",
                "BLOCKED",
                "CANONICAL_OBSERVATION_EXTERNAL_READ_NO_FINANCIAL_WRITE",
                requires=("current scoped egress",),
            ),
            InteractionAffordance(
                "workstation_egress_observe",
                "ordivon-workstation",
                "AVAILABLE",
                "READ_ONLY",
                responds_to=(error_code,),
            ),
            InteractionAffordance(
                "workstation_egress_pool_ensure",
                "ordivon-workstation",
                "BLOCKED",
                "RECONCILABLE_ENVIRONMENT_MUTATION",
                requires=("read-only observation proves repair necessary", "separate mutation authority"),
                responds_to=(error_code,),
            ),
        ),
        blockers=(error_code,),
        raw_escape_available=True,
    )


def _after_egress_context(egress: dict[str, Any]) -> InteractionContextInput:
    result = egress.get("result")
    if not isinstance(result, dict):
        raise TypeError("Workstation egress observation omitted result")
    status = str(result.get("status"))
    profile_digest = str(result.get("profileDigest"))
    available = status == "AVAILABLE" and result.get("listenerReachable") is True
    return InteractionContextInput(
        intent="finance.current-state-and-next-action",
        sources=(
            InteractionSourceRef(
                "ordivon-workstation",
                "workstation://egress/finance-okx",
                profile_digest,
                "CURRENT_AVAILABLE" if available else f"CURRENT_{status}",
            ),
        ),
        affordances=(
            InteractionAffordance(
                "finance_observe",
                "ordivon-finance",
                "AVAILABLE" if available else "BLOCKED",
                "CANONICAL_OBSERVATION_EXTERNAL_READ_NO_FINANCIAL_WRITE",
                requires=("current scoped egress satisfied",),
            ),
            InteractionAffordance(
                "workstation_egress_observe",
                "ordivon-workstation",
                "BLOCKED",
                "READ_ONLY",
                requires=("fresh egress observation already consumed",),
            ),
            InteractionAffordance(
                "workstation_egress_pool_ensure",
                "ordivon-workstation",
                "BLOCKED",
                "RECONCILABLE_ENVIRONMENT_MUTATION",
                requires=("separate mutation authority not granted by this runner",),
            ),
        ),
        blockers=() if available else (f"EGRESS_{status}",),
        raw_escape_available=True,
    )


def _owner_error_code(call: OwnerCall) -> str | None:
    if call.envelope.get("ok") is not False:
        return None
    error = call.envelope.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return str(code) if isinstance(code, str) and code else None


def _validate_workstation_read_only(call: OwnerCall) -> None:
    effect = call.envelope.get("effectContract")
    if not isinstance(effect, dict):
        raise TypeError("Workstation egress observation omitted effect contract")
    required = {
        "effectClass": "READ_ONLY",
        "credentialAccess": "none",
        "environmentMutation": False,
        "externalFinancialWrite": False,
    }
    for key, value in required.items():
        if effect.get(key) != value:
            raise RuntimeError(f"Workstation egress observation violated {key}={value!r}")


def _validate_finance_observation(call: OwnerCall) -> None:
    if call.envelope.get("ok") is not True:
        raise RuntimeError("Finance observation did not succeed")
    effect = call.envelope.get("effectContract")
    if not isinstance(effect, dict):
        raise TypeError("Finance observation omitted effect contract")
    for key, value in {
        "effectClass": "CANONICAL_OBSERVATION",
        "externalFinancialWrite": False,
        "financialSubmission": False,
        "authorityMutation": False,
    }.items():
        if effect.get(key) != value:
            raise RuntimeError(f"Finance observation violated {key}={value!r}")


def run_finance_workstation_composition(
    client: RuntimeClient,
    *,
    finance_workspace_id: str,
    workstation_workspace_id: str,
    finance_state_root: str,
    finance_app_python: str,
    request_prefix: str,
    initial_finance_envelope: dict[str, Any] | None = None,
    initial_finance_runtime_job_id: str | None = None,
) -> dict[str, Any]:
    calls: list[OwnerCall] = []
    stages: list[dict[str, Any]] = []
    env = _finance_env(finance_state_root, finance_app_python)

    if initial_finance_envelope is None:
        context_call = _domain_exec(
            client,
            owner="ordivon-finance",
            workspace_id=finance_workspace_id,
            script="scripts/finance-domain.mjs",
            operation="finance.context.compile",
            arguments={},
            client_request_id=f"{request_prefix}-finance-context",
            env=env,
        )
        calls.append(context_call)
        if context_call.envelope.get("ok") is not True:
            raise RuntimeError("Finance context compile failed")
        context_result = context_call.envelope.get("result")
        if not isinstance(context_result, dict) or not isinstance(
            context_result.get("stateVersion"), str
        ):
            raise TypeError("Finance context compile omitted stateVersion")

        initial = _materialized_stage(
            "initial-finance-observe", _initial_context(str(context_result["stateVersion"]))
        )
        stages.append(initial)
        if initial["selectedTools"] != ["finance_observe"]:
            raise RuntimeError("initial interaction must expose only finance_observe")

        finance = _domain_exec(
            client,
            owner="ordivon-finance",
            workspace_id=finance_workspace_id,
            script="scripts/finance-domain.mjs",
            operation="finance.observe",
            arguments={},
            client_request_id=f"{request_prefix}-finance-observe-1",
            env=env,
        )
    else:
        if initial_finance_runtime_job_id is None:
            raise ValueError("captured Finance standing requires its Runtime Job identity")
        finance = OwnerCall(
            owner="ordivon-finance",
            operation="finance.observe",
            runtime_job_id=initial_finance_runtime_job_id,
            runtime_attempt_id=None,
            runtime_status="captured",
            envelope=dict(initial_finance_envelope),
        )
    calls.append(finance)
    error_code = _owner_error_code(finance)
    if error_code is None:
        _validate_finance_observation(finance)
        return _receipt("completed", calls, stages, finance)
    if error_code != "EGRESS_NOT_CURRENT":
        return _receipt("blocked_owner_error", calls, stages, finance)

    recovery = _materialized_stage("egress-recovery", _recovery_context(error_code))
    stages.append(recovery)
    if recovery["selectedTools"] != ["workstation_egress_observe"]:
        raise RuntimeError("egress recovery must expose only workstation_egress_observe")

    workstation = _domain_exec(
        client,
        owner="ordivon-workstation",
        workspace_id=workstation_workspace_id,
        script="scripts/workstation-domain.mjs",
        operation="workstation.egress.observe",
        arguments={"profile": "finance-okx"},
        client_request_id=f"{request_prefix}-workstation-egress-observe",
    )
    calls.append(workstation)
    if workstation.envelope.get("ok") is not True:
        return _receipt("blocked_workstation_error", calls, stages, workstation)
    _validate_workstation_read_only(workstation)

    after_egress = _materialized_stage(
        "after-egress-observe", _after_egress_context(workstation.envelope)
    )
    stages.append(after_egress)
    if "workstation_egress_pool_ensure" in after_egress["selectedTools"]:
        raise RuntimeError("composition runner must never grant egress mutation")
    if after_egress["selectedTools"] != ["finance_observe"]:
        return _receipt("blocked_environment", calls, stages, workstation)

    retry = _domain_exec(
        client,
        owner="ordivon-finance",
        workspace_id=finance_workspace_id,
        script="scripts/finance-domain.mjs",
        operation="finance.observe",
        arguments={},
        client_request_id=f"{request_prefix}-finance-observe-2",
        env=env,
    )
    calls.append(retry)
    retry_error = _owner_error_code(retry)
    if retry_error is not None:
        if retry_error == "EGRESS_NOT_CURRENT":
            recurrent = _materialized_stage(
                "recurrent-egress-recovery", _recovery_context(retry_error)
            )
            stages.append(recurrent)
            if recurrent["selectedTools"] != ["workstation_egress_observe"]:
                raise RuntimeError(
                    "recurrent egress recovery must expose only workstation_egress_observe"
                )
            return _receipt("blocked_recurrent_egress", calls, stages, retry)
        return _receipt("blocked_owner_error_after_egress_recovery", calls, stages, retry)
    _validate_finance_observation(retry)
    return _receipt("completed_after_egress_recovery", calls, stages, retry)


def _receipt(
    status: str,
    calls: list[OwnerCall],
    stages: list[dict[str, Any]],
    terminal: OwnerCall,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "kind": "ordivon.first-interface.finance-workstation-composition-receipt",
        "revision": REVISION,
        "status": status,
        "ownerCalls": [
            {
                "owner": call.owner,
                "operation": call.operation,
                "runtimeJobId": call.runtime_job_id,
                "runtimeAttemptId": call.runtime_attempt_id,
                "runtimeStatus": call.runtime_status,
                "ownerOk": call.envelope.get("ok"),
                "ownerErrorCode": _owner_error_code(call),
            }
            for call in calls
        ],
        "interactionStages": stages,
        "terminalOwner": terminal.owner,
        "terminalOperation": terminal.operation,
        "invariants": {
            "environmentMutationAuthorityGranted": False,
            "runtimeSemanticCompletionClaimed": False,
            "toolAuthorityExpanded": any(
                stage["toolWorkingSet"].get("canExpandAuthority") is True for stage in stages
            ),
            "rawRuntimeEscapePreserved": True,
        },
    }


def _runtime_client(runtime_scripts: Path, environment_file: Path, endpoint: str) -> RuntimeClient:
    probe = runtime_scripts / "mcp_probe.py"
    spec = importlib.util.spec_from_file_location("ordivon_runtime_mcp_probe", probe)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Runtime MCP client from {probe}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    environment = module.load_environment_file(environment_file)
    token = module.load_bearer_token(environment)
    return module.connect_compatible(
        endpoint,
        token,
        client_name="ordivon-first-interface-finance-workstation-composition",
        timeout=10.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finance-workspace", required=True)
    parser.add_argument("--workstation-workspace", required=True)
    parser.add_argument("--finance-state-root", required=True)
    parser.add_argument(
        "--finance-app-python", default="/root/projects/ordivon-finance/.venv/bin/python"
    )
    parser.add_argument("--request-prefix", required=True)
    parser.add_argument("--initial-finance-envelope", type=Path)
    parser.add_argument("--initial-finance-runtime-job-id")
    parser.add_argument("--runtime-endpoint", default="http://127.0.0.1:8897/mcp")
    parser.add_argument(
        "--runtime-environment-file", default="/etc/ordivon/ordivon-runtime.env"
    )
    parser.add_argument(
        "--runtime-scripts", default="/root/projects/ordivon-runtime/scripts"
    )
    args = parser.parse_args()
    client = _runtime_client(
        Path(args.runtime_scripts), Path(args.runtime_environment_file), args.runtime_endpoint
    )
    initial_finance_envelope = None
    if args.initial_finance_envelope is not None:
        initial_finance_envelope = json.loads(
            args.initial_finance_envelope.read_text(encoding="utf-8")
        )
        if not isinstance(initial_finance_envelope, dict):
            raise TypeError("captured Finance standing must be one JSON object")
    receipt = run_finance_workstation_composition(
        client,
        finance_workspace_id=args.finance_workspace,
        workstation_workspace_id=args.workstation_workspace,
        finance_state_root=args.finance_state_root,
        finance_app_python=args.finance_app_python,
        request_prefix=args.request_prefix,
        initial_finance_envelope=initial_finance_envelope,
        initial_finance_runtime_job_id=args.initial_finance_runtime_job_id,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"].startswith("completed") else 2


if __name__ == "__main__":
    raise SystemExit(main())

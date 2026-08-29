"""Pure model-Tool to Runtime request lowering for the Harness ACI."""

from __future__ import annotations

from typing import Protocol

from anc_canonical import JsonValue, validate_json_value
from ..execution_binding import (
    HarnessExecutionBinding,
    build_harness_workspace_exec_request_from_binding,
)
from .model import AgentToolCall
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind


RUNTIME_SEARCH_EXECUTABLES: dict[str, str] = {
    "bash": "/bin/bash",
    "awk": "/usr/bin/awk",
    "ripgrep": "/usr/bin/rg",
}


class RuntimeExecutionCheckView(Protocol):
    executable: str
    args: tuple[str, ...]
    cwd_relative: str
    env: tuple[tuple[str, str], ...]
    timeout_ms: int
    stdout_limit_bytes: int
    stderr_limit_bytes: int


class RuntimeToolGrantView(Protocol):
    allow_opaque_exec: bool

    def allows_path(self, name: str, relative_path: str) -> bool: ...

    def execution_check(self, check_id: str) -> RuntimeExecutionCheckView: ...


def lower_runtime_tool(
    call: AgentToolCall,
    *,
    step_id: str,
    execution_binding: HarnessExecutionBinding,
    tool_grant: RuntimeToolGrantView | None,
    known_job_ids: frozenset[str],
    known_artifacts: frozenset[tuple[str, str]],
) -> tuple[str, dict[str, JsonValue], str | None]:
    arguments = dict(call.arguments)
    workspace_id = execution_binding.workspace_ref
    if call.name == "read_workspace":
        _only(
            arguments,
            {"relativePath", "mode", "byteOffset", "offset", "maxBytes"},
            call.name,
        )
        relative_path = _required_string(arguments, "relativePath", call.name)
        if tool_grant is not None:
            try:
                allowed_path = tool_grant.allows_path(call.name, relative_path)
            except ValueError as error:
                raise ToolBridgeError(str(error)) from error
            if not allowed_path:
                raise ToolBridgeError(
                    f"read_workspace path is outside the Tool Grant: {relative_path}",
                    kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
                )
        return (
            "workspace.read",
            {
                "schemaVersion": 1,
                "workspaceId": workspace_id,
                "relativePath": relative_path,
                "mode": _optional_string(arguments, "mode", "FULL"),
                "offset": _read_workspace_byte_offset(arguments),
                "maxBytes": _optional_int(
                    arguments, "maxBytes", 262_144, positive=True
                ),
            },
            None,
        )
    if call.name == "search_workspace":
        _only(
            arguments,
            {"query", "queries", "relativePath", "maxMatches", "maxMatchesPerQuery"},
            call.name,
        )
        raw_query = arguments.get("query")
        raw_queries = arguments.get("queries")
        if (raw_query is None) == (raw_queries is None):
            raise ToolBridgeError(
                "search_workspace requires exactly one of query or queries",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        relative_path = _optional_string(arguments, "relativePath", ".")
        if tool_grant is not None:
            try:
                allowed_path = tool_grant.allows_path(call.name, relative_path)
            except ValueError as error:
                raise ToolBridgeError(str(error)) from error
            if not allowed_path:
                raise ToolBridgeError(
                    (
                        "search_workspace path is outside the Tool Grant: "
                        f"{relative_path}"
                    ),
                    kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
                )

        if raw_query is not None:
            if "maxMatchesPerQuery" in arguments:
                raise ToolBridgeError(
                    "scalar search_workspace does not accept maxMatchesPerQuery",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            query = _required_string(arguments, "query", call.name)
            if len(query.encode("utf-8")) > 2_048:
                raise ToolBridgeError(
                    "search_workspace query exceeds 2048 UTF-8 bytes",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            max_matches = _optional_int(
                arguments, "maxMatches", 50, positive=True
            )
            if max_matches > 200:
                raise ToolBridgeError(
                    "search_workspace maxMatches must not exceed 200",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            executable = RUNTIME_SEARCH_EXECUTABLES["ripgrep"]
            execution_args = (
                "--json",
                "--fixed-strings",
                "--line-number",
                "--column",
                "--no-heading",
                "--color=never",
                "--max-count",
                str(max_matches),
                "--",
                query,
                relative_path,
            )
            stdout_limit_bytes = 65_536
            stderr_limit_bytes = 8_192
        else:
            if "maxMatches" in arguments:
                raise ToolBridgeError(
                    "batch search_workspace does not accept maxMatches",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            if (
                not isinstance(raw_queries, list)
                or not 1 <= len(raw_queries) <= 8
                or any(
                    not isinstance(item, str) or not item or item != item.strip()
                    for item in raw_queries
                )
            ):
                raise ToolBridgeError(
                    "search_workspace queries must contain 1..8 non-empty trimmed strings",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            queries = tuple(raw_queries)
            if any(len(item.encode("utf-8")) > 2_048 for item in queries):
                raise ToolBridgeError(
                    "search_workspace query exceeds 2048 UTF-8 bytes",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            max_matches = _optional_int(
                arguments, "maxMatchesPerQuery", 25, positive=True
            )
            if max_matches > 25:
                raise ToolBridgeError(
                    "search_workspace maxMatchesPerQuery must not exceed 25",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            executable = RUNTIME_SEARCH_EXECUTABLES["bash"]
            rg_executable = RUNTIME_SEARCH_EXECUTABLES["ripgrep"]
            awk_executable = RUNTIME_SEARCH_EXECUTABLES["awk"]
            script = "".join(
                (
                    'path="$1"; max="$2"; shift 2; idx=0; hard=0; ',
                    'for q in "$@"; do ',
                    'printf "@@ORDIVON_SEARCH_BATCH:BEGIN\\t%s\\n" "$idx"; ',
                    f'{rg_executable} --json --fixed-strings --line-number --column --no-heading ',
                    '--color=never -- "$q" "$path" | ',
                    awk_executable
                    + " -v limit=\"$max\" 'index($0,\"\\\"type\\\":\\\"match\\\"\"){if(count<limit) print; count++}'; ",
                    'pipe_status=("${PIPESTATUS[@]}"); rc="${pipe_status[0]}"; ',
                    'printf "@@ORDIVON_SEARCH_BATCH:END\\t%s\\t%s\\n" "$idx" "$rc"; ',
                    'if [ "$rc" -gt 1 ]; then hard=1; fi; idx=$((idx+1)); done; ',
                    'if [ "$hard" -ne 0 ]; then exit 2; fi; exit 0',
                )
            )
            execution_args = (
                "-c",
                script,
                "ordivon-search-batch",
                relative_path,
                str(max_matches),
                *queries,
            )
            stdout_limit_bytes = 65_536
            stderr_limit_bytes = 16_384

        try:
            request = build_harness_workspace_exec_request_from_binding(
                execution_binding,
                step_id=step_id,
                executable=executable,
                args=execution_args,
                timeout_ms=30_000,
                stdout_limit_bytes=stdout_limit_bytes,
                stderr_limit_bytes=stderr_limit_bytes,
                wait_ms=0,
                stdout_tail_bytes=65_536,
                stderr_tail_bytes=stderr_limit_bytes,
            )
        except ValueError as error:
            raise ToolBridgeError(
                str(error),
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            ) from error
        client_request_id = request.get("clientRequestId")
        if not isinstance(client_request_id, str):
            raise ToolBridgeError("Runtime request omitted clientRequestId")
        return "workspace.exec", request, client_request_id
    if call.name == "mutate_workspace":
        _only(arguments, {"mutations"}, call.name)
        mutations = arguments.get("mutations")
        if not isinstance(mutations, list) or not mutations:
            raise ToolBridgeError(
                "mutate_workspace mutations must be a non-empty list"
            )
        if tool_grant is not None:
            for mutation in mutations:
                if not isinstance(mutation, dict):
                    raise ToolBridgeError(
                        "mutate_workspace mutations must be objects"
                    )
                relative_path = mutation.get("relativePath")
                if not isinstance(relative_path, str):
                    raise ToolBridgeError(
                        "mutate_workspace mutation omitted relativePath"
                    )
                try:
                    allowed_path = tool_grant.allows_path(
                        call.name, relative_path
                    )
                except ValueError as error:
                    raise ToolBridgeError(str(error)) from error
                if not allowed_path:
                    raise ToolBridgeError(
                        f"mutate_workspace path is outside the Tool Grant: {relative_path}",
                        kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
                    )
        request: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "workspaceId": workspace_id,
            "mutations": mutations,
        }
        validate_json_value(request)
        return "workspace.mutate", request, None
    if call.name == "patch_workspace":
        _only(arguments, {"files", "maxDiffBytes"}, call.name)
        files = arguments.get("files")
        if not isinstance(files, list) or not files:
            raise ToolBridgeError(
                "patch_workspace files must be a non-empty list",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        for file in files:
            if not isinstance(file, dict):
                raise ToolBridgeError(
                    "patch_workspace files must be objects",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            relative_path = file.get("relativePath")
            if not isinstance(relative_path, str):
                raise ToolBridgeError(
                    "patch_workspace file omitted relativePath",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            edits = file.get("edits")
            if not isinstance(edits, list) or not edits:
                raise ToolBridgeError(
                    "patch_workspace file edits must be a non-empty list",
                    kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                )
            if tool_grant is not None:
                try:
                    allowed_path = tool_grant.allows_path(
                        call.name, relative_path
                    )
                except ValueError as error:
                    raise ToolBridgeError(
                        str(error), kind=ToolBridgeErrorKind.AUTHORITY_DENIED
                    ) from error
                if not allowed_path:
                    raise ToolBridgeError(
                        f"patch_workspace path is outside the Tool Grant: {relative_path}",
                        kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
                    )
        client_request_id = execution_binding.patch_request_id(
            step_id,
            call.digest,
        )
        request: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "clientRequestId": client_request_id,
            "workspaceId": workspace_id,
            "files": files,
            "maxDiffBytes": _optional_int(
                arguments, "maxDiffBytes", 1_048_576, positive=True
            ),
        }
        validate_json_value(request)
        return "workspace.patch", request, client_request_id
    if call.name == "diff_workspace":
        _only(arguments, {"maxBytes"}, call.name)
        return (
            "workspace.diff",
            {
                "schemaVersion": 1,
                "workspaceId": workspace_id,
                "maxBytes": _optional_int(
                    arguments, "maxBytes", 1_048_576, positive=True
                ),
            },
            None,
        )
    if call.name == "run_check":
        _only(
            arguments,
            {"checkId", "waitMs", "stdoutTailBytes", "stderrTailBytes"},
            call.name,
        )
        if tool_grant is None:
            raise ToolBridgeError(
                "run_check requires a Tool Grant",
                kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
            )
        check_id = _required_string(arguments, "checkId", call.name)
        try:
            check = tool_grant.execution_check(check_id)
        except KeyError as error:
            raise ToolBridgeError(
                str(error),
                kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
            ) from error
        try:
            request = build_harness_workspace_exec_request_from_binding(
                execution_binding,
                step_id=step_id,
                executable=check.executable,
                args=check.args,
                cwd_relative=check.cwd_relative,
                env=dict(check.env),
                timeout_ms=check.timeout_ms,
                stdout_limit_bytes=check.stdout_limit_bytes,
                stderr_limit_bytes=check.stderr_limit_bytes,
                wait_ms=_optional_int(arguments, "waitMs", 0),
                stdout_tail_bytes=_optional_int(
                    arguments, "stdoutTailBytes", 8_192
                ),
                stderr_tail_bytes=_optional_int(
                    arguments, "stderrTailBytes", 8_192
                ),
            )
        except ValueError as error:
            raise ToolBridgeError(
                str(error),
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            ) from error
        client_request_id = request.get("clientRequestId")
        if not isinstance(client_request_id, str):
            raise ToolBridgeError("Runtime request omitted clientRequestId")
        return "workspace.exec", request, client_request_id
    if call.name == "run_in_workspace":
        if tool_grant is not None and not tool_grant.allow_opaque_exec:
            raise ToolBridgeError(
                "opaque Runtime execution is not granted",
                kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
            )
        allowed = {
            "executable",
            "args",
            "cwdRelative",
            "env",
            "timeoutMs",
            "stdoutLimitBytes",
            "stderrLimitBytes",
            "waitMs",
            "stdoutTailBytes",
            "stderrTailBytes",
        }
        _only(arguments, allowed, call.name)
        executable = _required_string(arguments, "executable", call.name)
        raw_args = arguments.get("args", [])
        if not isinstance(raw_args, list) or any(
            not isinstance(item, str) for item in raw_args
        ):
            raise ToolBridgeError(
                "run_in_workspace args must be strings",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        raw_env = arguments.get("env", {})
        if not isinstance(raw_env, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in raw_env.items()
        ):
            raise ToolBridgeError(
                "run_in_workspace env must contain string values",
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            )
        try:
            request = build_harness_workspace_exec_request_from_binding(
                execution_binding,
                step_id=step_id,
                executable=executable,
                args=tuple(raw_args),
                cwd_relative=_optional_string(arguments, "cwdRelative", "."),
                env=dict(raw_env),
                timeout_ms=_optional_int(arguments, "timeoutMs", 30_000),
                stdout_limit_bytes=_optional_int(
                    arguments, "stdoutLimitBytes", 262_144
                ),
                stderr_limit_bytes=_optional_int(
                    arguments, "stderrLimitBytes", 262_144
                ),
                wait_ms=_optional_int(arguments, "waitMs", 0),
                stdout_tail_bytes=_optional_int(
                    arguments, "stdoutTailBytes", 8_192
                ),
                stderr_tail_bytes=_optional_int(
                    arguments, "stderrTailBytes", 8_192
                ),
            )
        except ValueError as error:
            raise ToolBridgeError(
                str(error),
                kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
            ) from error
        client_request_id = request.get("clientRequestId")
        if not isinstance(client_request_id, str):
            raise ToolBridgeError("Runtime request omitted clientRequestId")
        return "workspace.exec", request, client_request_id
    if call.name == "observe_job":
        _only(
            arguments,
            {"jobId", "waitMs", "stdoutTailBytes", "stderrTailBytes"},
            call.name,
        )
        job_id = _required_string(arguments, "jobId", call.name)
        if tool_grant is not None and job_id not in known_job_ids:
            raise ToolBridgeError(
                "observe_job may only observe a Job created by this Run",
                kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
            )
        return (
            "task.observe",
            {
                "schemaVersion": 1,
                "jobId": job_id,
                "waitMs": _optional_int(arguments, "waitMs", 0),
                "stdoutTailBytes": _optional_int(
                    arguments, "stdoutTailBytes", 8_192
                ),
                "stderrTailBytes": _optional_int(
                    arguments, "stderrTailBytes", 8_192
                ),
            },
            None,
        )
    if call.name == "read_artifact":
        _only(arguments, {"jobId", "artifactId", "offset", "maxBytes"}, call.name)
        job_id = _required_string(arguments, "jobId", call.name)
        artifact_id = _required_string(arguments, "artifactId", call.name)
        if (
            tool_grant is not None
            and (job_id, artifact_id) not in known_artifacts
        ):
            raise ToolBridgeError(
                "read_artifact may only read an Artifact observed in this Run",
                kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
            )
        return (
            "artifact.read",
            {
                "schemaVersion": 1,
                "jobId": job_id,
                "artifactId": artifact_id,
                "offset": _optional_int(arguments, "offset", 0),
                "maxBytes": _optional_int(
                    arguments, "maxBytes", 262_144, positive=True
                ),
            },
            None,
        )
    raise ToolBridgeError(
        f"Tool is not in the Ordivon Harness ACI: {call.name}",
        kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
    )


def _only(arguments: dict[str, JsonValue], allowed: set[str], tool_name: str) -> None:
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise ToolBridgeError(
            f"{tool_name} received unknown fields: {unknown}",
            kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
        )


def _required_string(
    arguments: dict[str, JsonValue], field: str, tool_name: str
) -> str:
    value = arguments.get(field)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ToolBridgeError(
            f"{tool_name} requires trimmed string {field}",
            kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
        )
    return value


def _optional_string(arguments: dict[str, JsonValue], field: str, default: str) -> str:
    value = arguments.get(field, default)
    if not isinstance(value, str) or value != value.strip():
        raise ToolBridgeError(
            f"{field} must be a trimmed string",
            kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
        )
    return value


def _optional_int(
    arguments: dict[str, JsonValue],
    field: str,
    default: int,
    *,
    positive: bool = False,
) -> int:
    value = arguments.get(field, default)
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise ToolBridgeError(
            f"{field} must be a {qualifier} integer",
            kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
        )
    return value


def _read_workspace_byte_offset(arguments: dict[str, JsonValue]) -> int:
    if "byteOffset" in arguments and "offset" in arguments:
        raise ToolBridgeError(
            "read_workspace byteOffset and legacy offset are mutually exclusive",
            kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
        )
    field = "byteOffset" if "byteOffset" in arguments else "offset"
    return _optional_int(arguments, field, 0)


__all__ = ["RuntimeExecutionCheckView", "RuntimeToolGrantView", "lower_runtime_tool"]

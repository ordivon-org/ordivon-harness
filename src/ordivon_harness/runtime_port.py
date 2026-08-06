from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from anc_canonical import JsonValue, canonical_digest, validate_json_value


@runtime_checkable
class HarnessRuntimeClient(Protocol):
    def call_tool(
        self,
        name: str,
        arguments: dict[str, JsonValue],
    ) -> dict[str, JsonValue]: ...


class HarnessRuntimeClientError(RuntimeError):
    """Transport or protocol failure with unknown physical Runtime outcome."""


@dataclass(frozen=True, slots=True)
class HarnessRuntimeErrorDetail:
    code: str
    message: str
    commit_state: str
    retryable: bool = False
    field: str | None = None

    def __post_init__(self) -> None:
        if not self.code or self.code != self.code.strip():
            raise ValueError("Runtime error code must be non-empty and trimmed")
        if not self.message or self.message != self.message.strip():
            raise ValueError("Runtime error message must be non-empty and trimmed")
        if self.commit_state not in {
            "not_started",
            "not_committed",
            "committed",
            "unknown",
        }:
            raise ValueError("Runtime commit state is unsupported")
        if type(self.retryable) is not bool:
            raise ValueError("Runtime retryable must be boolean")
        if self.field is not None and (not self.field or self.field != self.field.strip()):
            raise ValueError("Runtime error field must be trimmed")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "code": self.code,
            "message": self.message,
            "commitState": self.commit_state,
            "retryable": self.retryable,
            "field": self.field,
        }


class HarnessRuntimeToolRejected(HarnessRuntimeClientError):
    def __init__(
        self,
        operation: str,
        detail: HarnessRuntimeErrorDetail,
    ) -> None:
        super().__init__(f"{operation} rejected [{detail.code}]: {detail.message}")
        self.operation = operation
        self.detail = detail


def find_runtime_jobs_by_client_request(
    runtime: HarnessRuntimeClient,
    client_request_id: str,
    *,
    max_pages: int = 100,
) -> list[dict[str, JsonValue]]:
    if not client_request_id or client_request_id != client_request_id.strip():
        raise ValueError("Runtime clientRequestId is required and trimmed")
    if max_pages < 1:
        raise ValueError("Runtime Job lookup page limit must be positive")
    cursor: dict[str, JsonValue] | None = None
    seen_cursors: set[str] = set()
    matches: list[dict[str, JsonValue]] = []
    for _ in range(max_pages):
        arguments: dict[str, JsonValue] = {
            "limit": 100,
            "clientRequestId": client_request_id,
        }
        if cursor is not None:
            arguments["cursor"] = cursor
        page = runtime.call_tool("task.list", arguments)
        validate_json_value(page)
        jobs = page.get("jobs")
        if not isinstance(jobs, list):
            raise HarnessRuntimeClientError("task.list omitted jobs")
        for item in jobs:
            if not isinstance(item, dict):
                raise HarnessRuntimeClientError("task.list returned a non-object Job")
            job = dict(item)
            observed = job.get("clientRequestId")
            if observed != client_request_id:
                raise HarnessRuntimeClientError(
                    "filtered task.list returned another clientRequestId"
                )
            matches.append(job)
        next_cursor = page.get("nextCursor")
        if next_cursor is None:
            return matches
        if not isinstance(next_cursor, dict):
            raise HarnessRuntimeClientError("task.list returned an invalid cursor")
        typed: dict[str, JsonValue] = {}
        for key, value in next_cursor.items():
            if not isinstance(key, str) or not isinstance(value, (str, int)):
                raise HarnessRuntimeClientError("task.list cursor fields are invalid")
            typed[key] = value
        digest = canonical_digest(typed)
        if digest in seen_cursors:
            raise HarnessRuntimeClientError("task.list repeated a pagination cursor")
        seen_cursors.add(digest)
        cursor = typed
    raise HarnessRuntimeClientError("task.list pagination exceeded the Harness bound")


def runtime_error_value(error: BaseException) -> dict[str, JsonValue]:
    if isinstance(error, HarnessRuntimeToolRejected):
        return {
            "type": type(error).__name__,
            "operation": error.operation,
            **error.detail.to_dict(),
            "safeToCorrect": error.detail.commit_state in {"not_started", "not_committed"},
        }
    return {
        "type": type(error).__name__,
        "message": str(error)[:2_048],
        "safeToCorrect": False,
    }

"""Application-local observation-only Tool surface for bounded source recovery.

This module composes existing HarnessAgentRun/Runtime mechanics.  It does not grant
semantic authority: callers bind exact readable bytes by path + digest and remain
responsible for choosing an owner/currentness-valid source fence.
"""

from __future__ import annotations

from dataclasses import dataclass

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .ordivon.model import AgentToolDefinition
from .ordivon.sqlite_runtime_bridge import (
    SEARCH_WORKSPACE_DEFINITION,
    SQLiteHarnessRuntimeBridge,
)
from .run_tool_surface import HarnessAgentRunToolSurface


def _safe_path(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if value.startswith("/") or len(value.encode("utf-8")) > 1024:
        raise ValueError(f"{label} must be a bounded relative path")
    parts: list[str] = []
    for part in value.split("/"):
        if part == "..":
            raise ValueError(f"{label} must be a bounded relative path")
        if part in {"", "."}:
            continue
        parts.append(part)
    normalized = "/".join(parts) or "."
    if len(normalized.encode("utf-8")) > 1024:
        raise ValueError(f"{label} exceeds 1024 UTF-8 bytes")
    return normalized


def _digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return value


READ_WORKSPACE_DEFINITION = AgentToolDefinition(
    name="read_workspace",
    description=(
        "Read bounded UTF-8 bytes from one caller-granted source-fenced Workspace path. "
        "When search_workspace locates a source-relevant candidate, pass that result's exact "
        "relativePath here to inspect the complete bounded source object rather than inferring "
        "its semantics from isolated match lines. The operation is observation-only and does "
        "not make the file semantic authority."
    ),
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "relativePath": {"type": "string", "minLength": 1},
            "mode": {"type": "string", "enum": ["FULL", "SLICE"]},
            "byteOffset": {"type": "integer", "minimum": 0},
            "maxBytes": {"type": "integer", "minimum": 1, "maximum": 262144},
        },
        "required": ["relativePath"],
    },
)

OBSERVATION_TOOL_DEFINITIONS = (
    SEARCH_WORKSPACE_DEFINITION,
    READ_WORKSPACE_DEFINITION,
)
OBSERVATION_TOOL_SURFACE: dict[str, JsonValue] = {
    "schemaVersion": 1,
    "kind": "ordivon.harness-observation-tool-surface",
    "tools": [definition.to_dict() for definition in OBSERVATION_TOOL_DEFINITIONS],
}
OBSERVATION_TOOL_SURFACE_DIGEST = canonical_digest(OBSERVATION_TOOL_SURFACE)


@dataclass(frozen=True, slots=True)
class HarnessObservationReadObject:
    relative_path: str
    expected_digest: str

    def __post_init__(self) -> None:
        normalized = _safe_path(self.relative_path, "Observation read path")
        if normalized != self.relative_path:
            raise ValueError("Observation read path must use canonical relative spelling")
        if normalized == ".":
            raise ValueError("Observation read path must name a file-like source object")
        _digest(self.expected_digest, "Observation read digest")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "relativePath": self.relative_path,
            "expectedDigest": self.expected_digest,
        }


@dataclass(frozen=True, slots=True)
class HarnessObservationToolGrant:
    """Exact observation authority for one application-local Harness Agent Run.

    Search scope and readable objects are explicit.  Reads are additionally fenced
    by the expected complete-file digest observed from Runtime.
    """

    search_paths: tuple[str, ...]
    read_objects: tuple[HarnessObservationReadObject, ...]

    allow_opaque_exec = False

    def __post_init__(self) -> None:
        if not self.search_paths:
            raise ValueError("Observation Tool Grant requires at least one search path")
        search_paths = tuple(_safe_path(path, "Observation search path") for path in self.search_paths)
        if search_paths != self.search_paths:
            raise ValueError("Observation search paths must use canonical relative spelling")
        if search_paths != tuple(sorted(set(search_paths))):
            raise ValueError("Observation search paths must be uniquely sorted")
        read_paths = tuple(item.relative_path for item in self.read_objects)
        if not read_paths:
            raise ValueError("Observation Tool Grant requires at least one readable object")
        if read_paths != tuple(sorted(set(read_paths))):
            raise ValueError("Observation read objects must be uniquely path-sorted")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-observation-tool-grant",
            "tools": ["search_workspace", "read_workspace"],
            "runtimeOperations": ["workspace.exec", "workspace.read"],
            "searchPaths": list(self.search_paths),
            "readObjects": [item.to_dict() for item in self.read_objects],
            "workspaceMutationAllowed": False,
            "opaqueExecutionAllowed": False,
            "authorityRole": "caller-bound-observation-only-source-fence",
        }
        validate_json_value(value)
        return value

    def allows_path(self, name: str, relative_path: str) -> bool:
        try:
            normalized = _safe_path(relative_path, "Observation Tool path")
        except ValueError:
            return False
        if name == "search_workspace":
            return normalized in self.search_paths
        if name == "read_workspace":
            return normalized in {item.relative_path for item in self.read_objects}
        return False

    def expected_digest(self, name: str, relative_path: str) -> str | None:
        if name != "read_workspace":
            return None
        try:
            normalized = _safe_path(relative_path, "Observation Tool path")
        except ValueError:
            return None
        for item in self.read_objects:
            if item.relative_path == normalized:
                return item.expected_digest
        return None

    def execution_check(self, check_id: str):
        raise KeyError(f"observation-only Tool Grant has no execution Check: {check_id}")


def build_observation_tool_surface(
    grant: HarnessObservationToolGrant,
) -> HarnessAgentRunToolSurface:
    """Return one exact application-local search+read surface bound to ``grant``."""

    def bridge_factory(contract, continuity, execution_binding, runtime, provider_source):
        return SQLiteHarnessRuntimeBridge(
            contract,
            continuity,
            execution_binding,
            runtime,
            provider_source=provider_source,
            tool_definitions=OBSERVATION_TOOL_DEFINITIONS,
            tool_surface_digest=OBSERVATION_TOOL_SURFACE_DIGEST,
            tool_grant_digest=grant.digest,
            tool_grant=grant,
        )

    return HarnessAgentRunToolSurface(
        surface_id=f"harness.execution.observation-read.v1:{grant.digest[7:23]}",
        tool_catalog_digest=OBSERVATION_TOOL_SURFACE_DIGEST,
        tool_grant_digest=grant.digest,
        bridge_factory=bridge_factory,
    )


__all__ = [
    "OBSERVATION_TOOL_DEFINITIONS",
    "OBSERVATION_TOOL_SURFACE",
    "OBSERVATION_TOOL_SURFACE_DIGEST",
    "READ_WORKSPACE_DEFINITION",
    "HarnessObservationReadObject",
    "HarnessObservationToolGrant",
    "build_observation_tool_surface",
]

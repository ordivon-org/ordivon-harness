"""Application-local observation-only Tool surface for bounded source recovery.

This module composes existing HarnessAgentRun/Runtime mechanics. It does not grant
semantic authority. Callers bind exact readable bytes by path + digest and may
also bind exact owner/currentness authority evidence. Harness verifies and
transports that caller-bound fence; it never mints owner truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .agent_tool_observation import HarnessToolObservation
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


def _text(value: str, label: str, *, max_bytes: int = 2048) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > max_bytes
    ):
        raise ValueError(f"{label} must be non-empty, trimmed and bounded")
    return value


READ_WORKSPACE_DEFINITION = AgentToolDefinition(
    name="read_workspace",
    description=(
        "Read bounded UTF-8 bytes from one caller-granted source-fenced Workspace path. "
        "When search_workspace locates a source-relevant candidate, pass that result's exact "
        "relativePath here to inspect the complete bounded source object rather than inferring "
        "its semantics from isolated match lines. The operation is observation-only. A returned "
        "source authority fence is caller-bound evidence; Harness does not make the source "
        "semantic authority."
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
class HarnessObservationSourceAuthority:
    """Caller-supplied authority/currentness evidence for one exact source object.

    Harness binds these bytes into the Tool Grant and requires a matching execution
    reference, but does not independently establish that the owner claim is true.
    """

    owner_research_ref: str
    authority_ref: str
    authority_version_ref: str
    source_transport_revision: str

    def __post_init__(self) -> None:
        _text(self.owner_research_ref, "Observation owner research reference")
        _text(self.authority_ref, "Observation authority reference")
        _digest(self.authority_version_ref, "Observation authority version reference")
        _text(
            self.source_transport_revision,
            "Observation source transport revision",
            max_bytes=512,
        )

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-observation-source-authority",
            "truthRole": "caller-bound-source-authority-evidence",
            "ownerResearchRef": self.owner_research_ref,
            "authorityRef": self.authority_ref,
            "authorityVersionRef": self.authority_version_ref,
            "sourceTransportRevision": self.source_transport_revision,
            "harnessMintsOwnerTruth": False,
        }
        validate_json_value(value)
        return value


@dataclass(frozen=True, slots=True)
class HarnessObservationAuthorityStatementProjection:
    """Deterministic bounded projection over one exact owner authority publication."""

    subject_ref: str

    def __post_init__(self) -> None:
        _text(self.subject_ref, "Observation authority projection subject", max_bytes=2048)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-authority-statements-by-subject",
            "subjectRef": self.subject_ref,
        }


@dataclass(frozen=True, slots=True)
class HarnessObservationReadObject:
    relative_path: str
    expected_digest: str
    source_authority: HarnessObservationSourceAuthority | None = None
    authority_statement_projection: HarnessObservationAuthorityStatementProjection | None = None

    def __post_init__(self) -> None:
        normalized = _safe_path(self.relative_path, "Observation read path")
        if normalized != self.relative_path:
            raise ValueError("Observation read path must use canonical relative spelling")
        if normalized == ".":
            raise ValueError("Observation read path must name a file-like source object")
        _digest(self.expected_digest, "Observation read digest")
        if self.source_authority is not None and not isinstance(
            self.source_authority, HarnessObservationSourceAuthority
        ):
            raise ValueError("Observation source authority must use the typed authority record")
        projection = self.authority_statement_projection
        if projection is not None:
            if not isinstance(projection, HarnessObservationAuthorityStatementProjection):
                raise ValueError("Observation authority projection must use the typed projection")
            if self.source_authority is None:
                raise ValueError("Observation authority projection requires source authority")
            if self.expected_digest != self.source_authority.authority_version_ref:
                raise ValueError(
                    "Observation authority projection requires source digest equal to "
                    "authorityVersionRef"
                )

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "relativePath": self.relative_path,
            "expectedDigest": self.expected_digest,
        }
        if self.source_authority is not None:
            value["sourceAuthority"] = self.source_authority.to_dict()
        if self.authority_statement_projection is not None:
            value["authorityStatementProjection"] = (
                self.authority_statement_projection.to_dict()
            )
        validate_json_value(value)
        return value

    def source_fence(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-observation-source-fence",
            "truthRole": (
                "caller-bound-source-authority-evidence"
                if self.source_authority is not None
                else "caller-bound-source-bytes"
            ),
            "relativePath": self.relative_path,
            "sourceDigest": self.expected_digest,
            "harnessMintsOwnerTruth": False,
        }
        if self.source_authority is not None:
            value["sourceAuthority"] = self.source_authority.to_dict()
        if self.authority_statement_projection is not None:
            value["authorityStatementProjection"] = (
                self.authority_statement_projection.to_dict()
            )
        validate_json_value(value)
        return value


@dataclass(frozen=True, slots=True)
class HarnessObservationToolGrant:
    """Exact observation authority for one application-local Harness Agent Run.

    Search scope and readable objects are explicit. Reads are fenced by the exact
    complete-file digest observed from Runtime. Optional source-authority evidence
    is caller-owned and participates in this Grant's immutable digest.
    """

    search_paths: tuple[str, ...]
    read_objects: tuple[HarnessObservationReadObject, ...]

    allow_opaque_exec = False

    def __post_init__(self) -> None:
        if not self.search_paths:
            raise ValueError("Observation Tool Grant requires at least one search path")
        search_paths = tuple(
            _safe_path(path, "Observation search path") for path in self.search_paths
        )
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
            "harnessMintsOwnerTruth": False,
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
            return self.read_object(name, normalized) is not None
        return False

    def read_object(
        self,
        name: str,
        relative_path: str,
    ) -> HarnessObservationReadObject | None:
        if name != "read_workspace":
            return None
        try:
            normalized = _safe_path(relative_path, "Observation Tool path")
        except ValueError:
            return None
        for item in self.read_objects:
            if item.relative_path == normalized:
                return item
        return None

    def expected_digest(self, name: str, relative_path: str) -> str | None:
        item = self.read_object(name, relative_path)
        return None if item is None else item.expected_digest

    def execution_check(self, check_id: str):
        raise KeyError(f"observation-only Tool Grant has no execution Check: {check_id}")


class _CompactObservationRuntimeBridge(SQLiteHarnessRuntimeBridge):
    """Project bounded observation semantics and caller-bound source fences."""

    def __init__(self, *args, tool_grant: HarnessObservationToolGrant, **kwargs) -> None:
        self._observation_grant = tool_grant
        super().__init__(*args, tool_grant=tool_grant, **kwargs)
        for read_object in tool_grant.read_objects:
            authority = read_object.source_authority
            if authority is None:
                continue
            if not any(
                reference.reference_type == "source_authority"
                and reference.reference_id == authority.authority_ref
                and reference.generation == authority.source_transport_revision
                and reference.digest == authority.authority_version_ref
                for reference in self.execution_binding.runtime_references
            ):
                raise ValueError(
                    "authority-qualified observation read requires an exact "
                    "source_authority execution reference"
                )

    @classmethod
    def _observation_from_payload(
        cls,
        *,
        tool_call_id: str,
        tool_name: str,
        payload: dict[str, JsonValue],
        query: str | None,
        relative_path: str | None,
        reconciled: bool,
    ) -> HarnessToolObservation:
        observation = super()._observation_from_payload(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            payload=payload,
            query=query,
            relative_path=relative_path,
            reconciled=reconciled,
        )
        if tool_name != "search_workspace" or observation.status != "observed":
            return observation
        source = observation.structured_content
        compact: dict[str, JsonValue] = {}
        for key in (
            "query",
            "relativePath",
            "matchCount",
            "matches",
            "matchesTruncated",
        ):
            if key in source:
                compact[key] = source[key]
        return HarnessToolObservation(
            tool_call_id=observation.tool_call_id,
            tool_name=observation.tool_name,
            status=observation.status,
            structured_content=compact,
            runtime_job_ref=observation.runtime_job_ref,
            artifact_refs=(),
            reconciled=observation.reconciled,
        )

    def _record_observation(
        self,
        intent,
        observation: HarnessToolObservation,
        *,
        previous_receipt=None,
    ) -> HarnessToolObservation:
        if observation.status == "observed" and intent.tool_name == "search_workspace":
            content = dict(observation.structured_content)
            raw_matches = content.get("matches")
            if isinstance(raw_matches, list):
                projected_by_path: dict[str, dict[str, JsonValue]] = {}
                admitted_line_count = 0
                for raw in raw_matches:
                    if not isinstance(raw, dict):
                        continue
                    relative_path = raw.get("relativePath")
                    read_object = (
                        self._observation_grant.read_object(
                            "read_workspace",
                            relative_path,
                        )
                        if isinstance(relative_path, str)
                        else None
                    )
                    if read_object is None:
                        continue
                    admitted_line_count += 1
                    existing = projected_by_path.get(read_object.relative_path)
                    if existing is not None:
                        count = existing.get("matchedLineCount", 1)
                        existing["matchedLineCount"] = (
                            count + 1 if type(count) is int else 2
                        )
                        continue
                    item: dict[str, JsonValue] = {
                        "relativePath": read_object.relative_path,
                        "readAdmitted": True,
                        "readRelativePath": read_object.relative_path,
                        "sourceAuthorityBound": read_object.source_authority is not None,
                        "authorityStatementProjectionBound": (
                            read_object.authority_statement_projection is not None
                        ),
                        "matchedLineCount": 1,
                    }
                    projected_by_path[read_object.relative_path] = item
                projected: list[JsonValue] = list(projected_by_path.values())
                total = content.get("matchCount")
                total_count = total if type(total) is int else len(raw_matches)
                content["totalMatchCount"] = total_count
                content["matchCount"] = len(projected)
                content["readAdmittedMatchCount"] = admitted_line_count
                content["readAdmittedObjectCount"] = len(projected)
                content["omittedUnadmittedMatchCount"] = max(
                    total_count - admitted_line_count,
                    0,
                )
                content["matches"] = projected
                if len(projected) == 1:
                    relative_path = projected[0].get("readRelativePath")
                    if isinstance(relative_path, str):
                        read_object = self._observation_grant.read_object(
                            "read_workspace",
                            relative_path,
                        )
                        assert read_object is not None
                        content["readRouting"] = {
                            "nextTool": "read_workspace",
                            "arguments": {
                                "relativePath": relative_path,
                                "mode": "FULL",
                                "maxBytes": 262144,
                            },
                            "reason": (
                                "Read the admitted exact source object so its complete-file "
                                "digest is verified before deriving bundled source semantics."
                            ),
                            "authorityStatementProjectionBound": (
                                read_object.authority_statement_projection is not None
                            ),
                        }
                observation = HarnessToolObservation(
                    tool_call_id=observation.tool_call_id,
                    tool_name=observation.tool_name,
                    status=observation.status,
                    structured_content=content,
                    runtime_job_ref=observation.runtime_job_ref,
                    artifact_refs=observation.artifact_refs,
                    reconciled=observation.reconciled,
                )
        elif observation.status == "observed" and intent.tool_name == "read_workspace":
            content = dict(observation.structured_content)
            relative_path = content.get("relativePath")
            read_object = (
                self._observation_grant.read_object("read_workspace", relative_path)
                if isinstance(relative_path, str)
                else None
            )
            if read_object is not None:
                projection = read_object.authority_statement_projection
                if projection is not None:
                    projection_result = self._authority_statement_projection(
                        read_object,
                        content,
                    )
                    if isinstance(projection_result, str):
                        observation = HarnessToolObservation(
                            tool_call_id=observation.tool_call_id,
                            tool_name=observation.tool_name,
                            status="rejected",
                            structured_content={
                                "type": "SourceProjectionInvalid",
                                "reason": projection_result,
                                "relativePath": read_object.relative_path,
                                "expectedDigest": read_object.expected_digest,
                                "sourceFence": read_object.source_fence(),
                                "safeToCorrect": False,
                            },
                            runtime_job_ref=observation.runtime_job_ref,
                            artifact_refs=observation.artifact_refs,
                            reconciled=observation.reconciled,
                        )
                    else:
                        bounded: dict[str, JsonValue] = {
                            key: content[key]
                            for key in ("digest", "eof", "fileByteLength")
                            if key in content
                        }
                        bounded["relativePath"] = read_object.relative_path
                        bounded["sourceFenceVerified"] = True
                        bounded["sourceFenceRole"] = (
                            "CALLER_BOUND_SOURCE_AUTHORITY_EVIDENCE"
                        )
                        bounded["sourceFence"] = read_object.source_fence()
                        bounded["sourceProjectionVerified"] = True
                        bounded["sourceProjection"] = projection_result
                        observation = HarnessToolObservation(
                            tool_call_id=observation.tool_call_id,
                            tool_name=observation.tool_name,
                            status=observation.status,
                            structured_content=bounded,
                            runtime_job_ref=observation.runtime_job_ref,
                            artifact_refs=observation.artifact_refs,
                            reconciled=observation.reconciled,
                        )
                else:
                    content["relativePath"] = read_object.relative_path
                    content["sourceFenceVerified"] = True
                    content["sourceFenceRole"] = (
                        "CALLER_BOUND_SOURCE_AUTHORITY_EVIDENCE"
                        if read_object.source_authority is not None
                        else "CALLER_BOUND_SOURCE_BYTES"
                    )
                    content["sourceFence"] = read_object.source_fence()
                    observation = HarnessToolObservation(
                        tool_call_id=observation.tool_call_id,
                        tool_name=observation.tool_name,
                        status=observation.status,
                        structured_content=content,
                        runtime_job_ref=observation.runtime_job_ref,
                        artifact_refs=observation.artifact_refs,
                        reconciled=observation.reconciled,
                    )
        return super()._record_observation(
            intent,
            observation,
            previous_receipt=previous_receipt,
        )

    @staticmethod
    def _authority_statement_projection(
        read_object: HarnessObservationReadObject,
        content: dict[str, JsonValue],
    ) -> dict[str, JsonValue] | str:
        projection = read_object.authority_statement_projection
        authority = read_object.source_authority
        if projection is None or authority is None:
            return "authority projection configuration is incomplete"
        raw_content = content.get("content")
        if not isinstance(raw_content, str):
            return "authority publication read omitted UTF-8 content"
        try:
            publication = json.loads(raw_content)
        except json.JSONDecodeError:
            return "authority publication is not valid JSON"
        if not isinstance(publication, dict):
            return "authority publication must be a JSON object"
        if publication.get("kind") != "ordivon.research-owner-publication":
            return "source object is not an Ordivon research-owner publication"
        if publication.get("ownerResearchRef") != authority.owner_research_ref:
            return "authority publication ownerResearchRef differs from the bound authority"
        if publication.get("authorityRef") != authority.authority_ref:
            return "authority publication authorityRef differs from the bound authority"
        statements = publication.get("statements")
        if not isinstance(statements, list):
            return "authority publication omitted statements"
        selected: list[JsonValue] = []
        for statement in statements:
            if not isinstance(statement, dict):
                continue
            if statement.get("subjectRef") == projection.subject_ref:
                selected.append(dict(statement))
        if not selected:
            return "authority publication contains no statement for the bound subjectRef"
        if len(selected) > 64:
            return "authority statement projection exceeds the bounded statement count"
        result: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-authority-statement-projection",
            "truthRole": "deterministic-exact-authority-publication-projection",
            "subjectRef": projection.subject_ref,
            "ownerResearchRef": authority.owner_research_ref,
            "authorityRef": authority.authority_ref,
            "authorityVersionRef": authority.authority_version_ref,
            "sourceTransportRevision": authority.source_transport_revision,
            "statementCount": len(selected),
            "statements": selected,
            "harnessMintsOwnerTruth": False,
        }
        validate_json_value(result)
        if len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 24576:
            return "authority statement projection exceeds the bounded model-visible size"
        return result


def build_observation_tool_surface(
    grant: HarnessObservationToolGrant,
) -> HarnessAgentRunToolSurface:
    """Return one exact application-local search+read surface bound to ``grant``."""

    def bridge_factory(contract, continuity, execution_binding, runtime, provider_source):
        return _CompactObservationRuntimeBridge(
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
    "HarnessObservationAuthorityStatementProjection",
    "HarnessObservationReadObject",
    "HarnessObservationSourceAuthority",
    "HarnessObservationToolGrant",
    "build_observation_tool_surface",
]

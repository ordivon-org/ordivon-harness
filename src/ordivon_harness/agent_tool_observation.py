from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value


@dataclass(frozen=True, slots=True)
class HarnessArtifactReference:
    ref: str
    kind: str
    digest: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.ref, "Artifact reference"),
            (self.kind, "Artifact kind"),
            (self.digest, "Artifact digest"),
        ):
            if not value or value != value.strip():
                raise ValueError(f"{label} must be non-empty and trimmed")
        if not self.digest.startswith("sha256:") or len(self.digest) != 71:
            raise ValueError("Artifact digest must be a sha256 digest")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"ref": self.ref, "kind": self.kind, "digest": self.digest}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessArtifactReference:
        if set(value) != {"ref", "kind", "digest"}:
            raise ValueError("HarnessArtifactReference fields differ")
        if any(not isinstance(value[field], str) for field in value):
            raise ValueError("HarnessArtifactReference fields must be strings")
        return cls(
            ref=value["ref"],
            kind=value["kind"],
            digest=value["digest"],
        )


@dataclass(frozen=True, slots=True)
class HarnessToolObservation:
    tool_call_id: str
    tool_name: str
    status: str
    structured_content: dict[str, JsonValue]
    runtime_job_ref: str | None = None
    artifact_refs: tuple[HarnessArtifactReference, ...] = ()
    reconciled: bool = False

    def __post_init__(self) -> None:
        if not self.tool_call_id or self.tool_call_id != self.tool_call_id.strip():
            raise ValueError("Tool Observation Call identity must be trimmed")
        if not self.tool_name or self.tool_name != self.tool_name.strip():
            raise ValueError("Tool Observation name must be trimmed")
        if self.status not in {
            "observed",
            "rejected",
            "unknown",
            "cancel-requested",
            "cancelled",
        }:
            raise ValueError(f"unsupported Tool Observation status: {self.status}")
        validate_json_value(self.structured_content)
        if self.runtime_job_ref is not None and (
            not self.runtime_job_ref or self.runtime_job_ref != self.runtime_job_ref.strip()
        ):
            raise ValueError("Runtime Job reference must be trimmed")
        refs = [item.ref for item in self.artifact_refs]
        if len(refs) != len(set(refs)):
            raise ValueError("Tool Observation Artifact refs must be unique")
        if self.status == "rejected" and self.runtime_job_ref is not None:
            raise ValueError("pre-admission rejection cannot carry a Runtime Job")
        if type(self.reconciled) is not bool:
            raise ValueError("Tool Observation reconciled must be boolean")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.tool-observation",
            "toolCallId": self.tool_call_id,
            "toolName": self.tool_name,
            "status": self.status,
            "structuredContent": self.structured_content,
            "runtimeJobRef": self.runtime_job_ref,
            "artifactRefs": [item.to_dict() for item in self.artifact_refs],
            "reconciled": self.reconciled,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessToolObservation:
        expected = {
            "schemaVersion",
            "kind",
            "toolCallId",
            "toolName",
            "status",
            "structuredContent",
            "runtimeJobRef",
            "artifactRefs",
            "reconciled",
        }
        if set(value) != expected:
            raise ValueError("Tool Observation fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.tool-observation":
            raise ValueError("Tool Observation version or kind is invalid")
        artifacts = value["artifactRefs"]
        content = value["structuredContent"]
        if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
            raise ValueError("Tool Observation Artifact refs are invalid")
        if not isinstance(content, dict):
            raise TypeError("Tool Observation structured content must be an object")
        if (
            not isinstance(value["toolCallId"], str)
            or not isinstance(value["toolName"], str)
            or not isinstance(value["status"], str)
            or (value["runtimeJobRef"] is not None and not isinstance(value["runtimeJobRef"], str))
            or type(value["reconciled"]) is not bool
        ):
            raise ValueError("Tool Observation scalar fields are invalid")
        return cls(
            tool_call_id=value["toolCallId"],
            tool_name=value["toolName"],
            status=value["status"],
            structured_content=dict(content),
            runtime_job_ref=value["runtimeJobRef"],
            artifact_refs=tuple(HarnessArtifactReference.from_dict(item) for item in artifacts),
            reconciled=value["reconciled"],
        )

    def to_model_message(self) -> dict[str, JsonValue]:
        return {
            "role": "tool",
            "toolCallId": self.tool_call_id,
            "name": self.tool_name,
            "observation": {
                "status": self.status,
                "content": self.structured_content,
                "runtimeJobRef": self.runtime_job_ref,
                "artifactRefs": [item.to_dict() for item in self.artifact_refs],
                "reconciled": self.reconciled,
            },
        }

    def bounded(self, max_bytes: int) -> HarnessToolObservation:
        if max_bytes < 1 or len(canonical_bytes(self.to_dict())) <= max_bytes:
            return self
        original_content = dict(self.structured_content)
        bounded_content: dict[str, JsonValue] = {
            "truncated": True,
            "originalContentDigest": canonical_digest(original_content),
            "originalContentBytes": len(canonical_bytes(original_content)),
            "runtimeJobRef": self.runtime_job_ref,
            "artifactRefs": [item.to_dict() for item in self.artifact_refs],
        }
        for key in (
            "relativePath",
            "digest",
            "contentDigest",
            "query",
            "matchCount",
            "matchesTruncated",
            "effectiveByteRange",
            "sourceRange",
            "locationSemantics",
        ):
            if key not in original_content:
                continue
            bounded_content[key] = original_content[key]
            candidate = HarnessToolObservation(
                tool_call_id=self.tool_call_id,
                tool_name=self.tool_name,
                status=self.status,
                structured_content=bounded_content,
                runtime_job_ref=self.runtime_job_ref,
                artifact_refs=self.artifact_refs,
                reconciled=self.reconciled,
            )
            if len(canonical_bytes(candidate.to_dict())) > max_bytes:
                del bounded_content[key]
        return HarnessToolObservation(
            tool_call_id=self.tool_call_id,
            tool_name=self.tool_name,
            status=self.status,
            structured_content=bounded_content,
            runtime_job_ref=self.runtime_job_ref,
            artifact_refs=self.artifact_refs,
            reconciled=self.reconciled,
        )

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from anc_canonical import JsonValue, canonical_digest, validate_json_value


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields differ: {sorted(set(value) ^ expected)}")


def _text(value: Any, label: str, *, max_bytes: int = 2_000) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return value


def _text_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} values must be a list")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} values must be strings")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class AgentToolDefinition:
    name: str
    description: str
    input_schema: dict[str, JsonValue]

    def __post_init__(self) -> None:
        _text(self.name, "Tool name", max_bytes=120)
        _text(self.description, "Tool description", max_bytes=1_000)
        validate_json_value(self.input_schema)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    tool_call_id: str
    name: str
    arguments: dict[str, JsonValue]
    argument_error: str | None = None
    raw_arguments_digest: str | None = None
    raw_arguments_preview: str | None = None

    def __post_init__(self) -> None:
        _text(self.tool_call_id, "Tool Call identity", max_bytes=300)
        _text(self.name, "Tool Call name", max_bytes=120)
        validate_json_value(self.arguments)
        diagnostics = (
            self.argument_error,
            self.raw_arguments_digest,
            self.raw_arguments_preview,
        )
        if any(item is not None for item in diagnostics):
            if not all(isinstance(item, str) for item in diagnostics):
                raise ValueError(
                    "invalid Tool Call arguments require complete diagnostics"
                )
            assert self.argument_error is not None
            assert self.raw_arguments_digest is not None
            assert self.raw_arguments_preview is not None
            _text(self.argument_error, "Tool Call argument error", max_bytes=300)
            _digest(self.raw_arguments_digest, "raw Tool Call arguments digest")
            if len(self.raw_arguments_preview.encode("utf-8")) > 2_048:
                raise ValueError("raw Tool Call arguments preview exceeds 2048 bytes")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "toolCallId": self.tool_call_id,
            "name": self.name,
            "arguments": self.arguments,
        }
        if self.argument_error is not None:
            value["providerArguments"] = {
                "error": self.argument_error,
                "rawDigest": self.raw_arguments_digest,
                "preview": self.raw_arguments_preview,
            }
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentToolCall:
        base_fields = {"toolCallId", "name", "arguments"}
        current_fields = base_fields | {"providerArguments"}
        if set(value) not in {frozenset(base_fields), frozenset(current_fields)}:
            raise ValueError(
                "AgentToolCall fields differ: "
                f"{sorted(set(value) ^ current_fields)}"
            )
        arguments = value["arguments"]
        if not isinstance(arguments, dict):
            raise ValueError("AgentToolCall arguments must be an object")
        provider_arguments = value.get("providerArguments")
        if provider_arguments is None and "providerArguments" in value:
            raise ValueError("AgentToolCall providerArguments must be an object")
        if provider_arguments is None:
            argument_error = None
            raw_arguments_digest = None
            raw_arguments_preview = None
        else:
            if not isinstance(provider_arguments, dict):
                raise ValueError("AgentToolCall providerArguments must be an object")
            _exact(
                provider_arguments,
                {"error", "rawDigest", "preview"},
                "AgentToolCall providerArguments",
            )
            argument_error = provider_arguments["error"]
            raw_arguments_digest = provider_arguments["rawDigest"]
            raw_arguments_preview = provider_arguments["preview"]
        return cls(
            tool_call_id=value["toolCallId"],
            name=value["name"],
            arguments=dict(arguments),
            argument_error=argument_error,
            raw_arguments_digest=raw_arguments_digest,
            raw_arguments_preview=raw_arguments_preview,
        )


_CONCLUSION_STATUSES = {"candidate_completed", "needs_input"}


@dataclass(frozen=True, slots=True)
class AgentRunConclusion:
    status: str
    summary: str
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    unresolved_unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _CONCLUSION_STATUSES:
            raise ValueError(f"unsupported Agent conclusion status: {self.status}")
        _text(self.summary, "Agent conclusion summary", max_bytes=8_000)
        for values, label in (
            (self.artifact_refs, "Artifact reference"),
            (self.evidence_refs, "evidence reference"),
            (self.unresolved_unknowns, "unresolved unknown"),
        ):
            for value in values:
                _text(value, label, max_bytes=500)
            if len(values) != len(set(values)):
                raise ValueError(f"{label} values must be unique")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "status": self.status,
            "summary": self.summary,
            "artifactRefs": list(self.artifact_refs),
            "evidenceRefs": list(self.evidence_refs),
            "unresolvedUnknowns": list(self.unresolved_unknowns),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentRunConclusion:
        _exact(
            value,
            {
                "status",
                "summary",
                "artifactRefs",
                "evidenceRefs",
                "unresolvedUnknowns",
            },
            "AgentRunConclusion",
        )
        return cls(
            status=value["status"],
            summary=value["summary"],
            artifact_refs=_text_tuple(value["artifactRefs"], "Artifact reference"),
            evidence_refs=_text_tuple(value["evidenceRefs"], "evidence reference"),
            unresolved_unknowns=_text_tuple(
                value["unresolvedUnknowns"],
                "unresolved unknown",
            ),
        )


@dataclass(frozen=True, slots=True)
class AgentTurnRequest:
    harness_run_id: str
    turn_id: str
    sequence: int
    assignment_id: str
    context_digest: str
    tool_catalog_digest: str
    messages: tuple[dict[str, JsonValue], ...]
    tools: tuple[AgentToolDefinition, ...]
    remaining_budget: dict[str, JsonValue]

    def __post_init__(self) -> None:
        _text(self.harness_run_id, "Harness Run identity", max_bytes=300)
        _text(self.turn_id, "Agent turn identity", max_bytes=300)
        _text(self.assignment_id, "Assignment identity", max_bytes=300)
        if self.sequence < 1:
            raise ValueError("Agent turn sequence must be positive")
        _digest(self.context_digest, "Agent turn Context digest")
        _digest(self.tool_catalog_digest, "Agent turn Tool catalog digest")
        for message in self.messages:
            validate_json_value(message)
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("Agent turn Tool names must be unique")
        validate_json_value(self.remaining_budget)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @property
    def dispatch_digest(self) -> str:
        value = self.to_dict()
        dispatch_budget = dict(self.remaining_budget)
        dispatch_budget.pop("wallTimeMs", None)
        dispatch_budget.pop("modelRetries", None)
        value["remainingBudget"] = dispatch_budget
        return canonical_digest(value)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.agent-turn-request",
            "harnessRunId": self.harness_run_id,
            "turnId": self.turn_id,
            "sequence": self.sequence,
            "assignmentId": self.assignment_id,
            "contextDigest": self.context_digest,
            "toolCatalogDigest": self.tool_catalog_digest,
            "messages": list(self.messages),
            "tools": [tool.to_dict() for tool in self.tools],
            "remainingBudget": self.remaining_budget,
        }


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    model_call_id: str
    model_id: str
    content: str | None
    tool_calls: tuple[AgentToolCall, ...]
    conclusion: AgentRunConclusion | None
    usage: dict[str, JsonValue]
    finish_reason: str
    raw_response_digest: str
    effective_model_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.model_call_id, "Model Call identity", max_bytes=300)
        _text(self.model_id, "model identity", max_bytes=300)
        if self.content is not None and len(self.content.encode("utf-8")) > 1_048_576:
            raise ValueError("Agent turn content exceeds one MiB")
        call_ids = [call.tool_call_id for call in self.tool_calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("Agent turn Tool Call identities must be unique")
        if self.conclusion is not None and self.tool_calls:
            raise ValueError(
                "Agent turn cannot request Tools and conclude simultaneously"
            )
        if not self.tool_calls and self.conclusion is None:
            raise ValueError("Agent turn must request a Tool or provide a conclusion")
        validate_json_value(self.usage)
        _text(self.finish_reason, "model finish reason", max_bytes=300)
        _digest(self.raw_response_digest, "raw model response digest")
        if self.effective_model_id is not None:
            _text(self.effective_model_id, "effective model identity", max_bytes=300)

    @property
    def effective_model(self) -> str:
        return self.effective_model_id or self.model_id

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.agent-turn-result",
            "modelCallId": self.model_call_id,
            "modelId": self.model_id,
            "content": self.content,
            "toolCalls": [call.to_dict() for call in self.tool_calls],
            "conclusion": None
            if self.conclusion is None
            else self.conclusion.to_dict(),
            "usage": self.usage,
            "finishReason": self.finish_reason,
            "rawResponseDigest": self.raw_response_digest,
        }
        if self.effective_model_id is not None:
            value["effectiveModelId"] = self.effective_model_id
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentTurnResult:
        base_fields = {
            "schemaVersion",
            "kind",
            "modelCallId",
            "modelId",
            "content",
            "toolCalls",
            "conclusion",
            "usage",
            "finishReason",
            "rawResponseDigest",
        }
        current_fields = base_fields | {"effectiveModelId"}
        if set(value) not in {frozenset(base_fields), frozenset(current_fields)}:
            raise ValueError(
                "AgentTurnResult fields differ: "
                f"{sorted(set(value) ^ current_fields)}"
            )
        if (
            type(value["schemaVersion"]) is not int
            or value["schemaVersion"] != 1
            or value["kind"] != "ordivon.agent-turn-result"
        ):
            raise ValueError("AgentTurnResult version or kind is invalid")
        content = value["content"]
        if content is not None and not isinstance(content, str):
            raise ValueError("AgentTurnResult content must be a string or null")
        raw_tool_calls = value["toolCalls"]
        if not isinstance(raw_tool_calls, list):
            raise ValueError("AgentTurnResult toolCalls must be a list")
        tool_calls: list[AgentToolCall] = []
        for raw_tool_call in raw_tool_calls:
            if not isinstance(raw_tool_call, dict):
                raise ValueError("AgentTurnResult Tool Call must be an object")
            tool_calls.append(AgentToolCall.from_dict(raw_tool_call))
        raw_conclusion = value["conclusion"]
        if raw_conclusion is not None and not isinstance(raw_conclusion, dict):
            raise ValueError("AgentTurnResult conclusion must be an object or null")
        raw_usage = value["usage"]
        if not isinstance(raw_usage, dict):
            raise ValueError("AgentTurnResult usage must be an object")
        return cls(
            model_call_id=value["modelCallId"],
            model_id=value["modelId"],
            content=content,
            tool_calls=tuple(tool_calls),
            conclusion=(
                None
                if raw_conclusion is None
                else AgentRunConclusion.from_dict(raw_conclusion)
            ),
            usage=dict(raw_usage),
            finish_reason=value["finishReason"],
            raw_response_digest=value["rawResponseDigest"],
            effective_model_id=value.get("effectiveModelId"),
        )


class AgentTurnFailureCode(str, Enum):
    FAILED = "provider_failed"
    TIMEOUT = "provider_timeout"
    TRANSPORT_FAILED = "provider_transport_failed"
    REJECTED = "provider_rejected"
    UNAVAILABLE = "provider_unavailable"


class AgentTurnDispatchSafety(str, Enum):
    PRE_DISPATCH_SAFE = "pre_dispatch_safe"
    PROVIDER_REJECTED = "provider_rejected"
    DISPATCH_AMBIGUOUS = "dispatch_ambiguous"


class AgentTurnAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_code: AgentTurnFailureCode = AgentTurnFailureCode.FAILED,
        dispatch_safety: AgentTurnDispatchSafety = (
            AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS
        ),
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.dispatch_safety = dispatch_safety


class AgentTurnCallHandle(Protocol):
    def poll(self, timeout_seconds: float) -> AgentTurnResult | None: ...

    def cancel(self) -> None: ...


class AgentTurnAdapter(Protocol):
    adapter_id: str
    model_id: str

    def provider_request_digest(self, request: AgentTurnRequest) -> str: ...

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult: ...


class _StaticProviderIdentity(Protocol):
    adapter_id: str
    model_id: str


def static_provider_request_digest(
    adapter: _StaticProviderIdentity,
    request: AgentTurnRequest,
) -> str:
    """Bind a configuration-free Adapter's Provider request identity."""
    _text(adapter.adapter_id, "Provider adapter identity", max_bytes=300)
    _text(adapter.model_id, "requested model identity", max_bytes=300)
    return canonical_digest(
        {
            "schemaVersion": 1,
            "kind": "ordivon.static-provider-request",
            "adapterId": adapter.adapter_id,
            "requestedModelId": adapter.model_id,
            "agentDispatchDigest": request.dispatch_digest,
        }
    )


class ScriptedTurnAdapter:
    """Deterministic OH1 adapter. It never calls a physical model provider."""

    adapter_id = "ordivon.scripted-turn-adapter.v1"
    model_id = "ordivon.scripted-model.v1"

    def __init__(self, results: tuple[AgentTurnResult, ...]) -> None:
        if not results:
            raise ValueError("ScriptedTurnAdapter requires at least one result")
        self._results = results
        self._index = 0
        self.requests: list[AgentTurnRequest] = []

    provider_request_digest = static_provider_request_digest

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        if self._index >= len(self._results):
            raise AgentTurnAdapterError("ScriptedTurnAdapter has no remaining result")
        result = self._results[self._index]
        self._index += 1
        return result

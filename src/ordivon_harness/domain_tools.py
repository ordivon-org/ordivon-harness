"""Public dependency-inverted Tool boundary for domain-owned Agent loops.

A domain bridge owns domain admission and effect semantics. Harness owns the
model loop, budgets, Provider adaptation, and observable Tool-call protocol.
This module does not create Task truth, persistence, Runtime authority, or a
universal domain Tool registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .ordivon.control import CancellationToken
from .ordivon.events import HarnessRunEvent
from .ordivon.loop import AgentLoopResult, OrdivonAgentLoop, RunBudget, RunStopCode
from .ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnAdapter,
)
from .ordivon.tool_errors import ToolBridgeError, ToolBridgeErrorKind
from .ordivon.tool_bridge import ToolObservation
from .version import package_version


def _text(value: str, label: str, *, prefix: str | None = None) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > 300:
        raise ValueError(f"{label} exceeds 300 UTF-8 bytes")
    if prefix is not None and not value.startswith(prefix + ":"):
        raise ValueError(f"{label} must start with {prefix}:")
    return value


def _digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return value


@dataclass(frozen=True, slots=True)
class DomainToolCatalog:
    """One immutable domain-owned model Tool surface."""

    domain_id: str
    revision: str
    tools: tuple[AgentToolDefinition, ...]

    def __post_init__(self) -> None:
        _text(self.domain_id, "domain identity", prefix="domain")
        _text(self.revision, "domain Tool catalog revision")
        names = [tool.name for tool in self.tools]
        if not names or len(names) != len(set(names)):
            raise ValueError("domain Tool names must be non-empty and unique")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def granted_digest(self, allowed_tools: tuple[str, ...]) -> str:
        selected = self.select(allowed_tools)
        return canonical_digest(
            {
                "schemaVersion": 1,
                "kind": "ordivon.domain-tool-catalog-grant",
                "catalogDigest": self.digest,
                "allowedTools": [tool.name for tool in selected],
            }
        )

    def select(self, allowed_tools: tuple[str, ...]) -> tuple[AgentToolDefinition, ...]:
        if not allowed_tools or len(allowed_tools) != len(set(allowed_tools)):
            raise ValueError("domain Tool grant must be non-empty and unique")
        available = {tool.name: tool for tool in self.tools}
        missing = sorted(set(allowed_tools) - set(available))
        if missing:
            raise ValueError(f"domain Tool grant references unknown Tools: {missing}")
        allowed = set(allowed_tools)
        return tuple(tool for tool in self.tools if tool.name in allowed)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.domain-tool-catalog",
            "domainId": self.domain_id,
            "revision": self.revision,
            "tools": [tool.to_dict() for tool in self.tools],
        }


class DomainToolBridge(Protocol):
    """Domain-owned admission and execution below the generic Harness loop."""

    catalog: DomainToolCatalog
    bridge_identity: dict[str, JsonValue]

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation: ...


@dataclass(frozen=True, slots=True)
class DomainToolLoopPlan:
    harness_run_id: str
    assignment_id: str
    context_digest: str
    initial_messages: tuple[dict[str, JsonValue], ...]
    allowed_tools: tuple[str, ...]
    budget: RunBudget
    assignment_deadline_ms: int | None = None

    def __post_init__(self) -> None:
        _text(self.harness_run_id, "Harness Run identity", prefix="harness-run")
        _text(self.assignment_id, "Assignment identity", prefix="assignment")
        _digest(self.context_digest, "domain loop Context digest")
        if not self.initial_messages:
            raise ValueError("domain loop requires at least one initial message")
        for message in self.initial_messages:
            validate_json_value(message)
        if not self.allowed_tools or len(self.allowed_tools) != len(set(self.allowed_tools)):
            raise ValueError("domain loop allowed Tools must be non-empty and unique")
        if self.assignment_deadline_ms is not None and self.assignment_deadline_ms < 0:
            raise ValueError("domain loop deadline must be non-negative")


class _GrantedDomainToolBridge:
    def __init__(self, bridge: DomainToolBridge, allowed_tools: tuple[str, ...]) -> None:
        validate_json_value(bridge.bridge_identity)
        if not bridge.bridge_identity:
            raise ValueError("domain Tool Bridge identity must be non-empty")
        self.bridge = bridge
        self._definitions = bridge.catalog.select(allowed_tools)
        self._allowed = frozenset(tool.name for tool in self._definitions)
        self.catalog_digest = bridge.catalog.granted_digest(allowed_tools)

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        return self._definitions

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        if call.name not in self._allowed:
            raise ToolBridgeError(
                f"domain Tool is not granted: {call.name}",
                kind=ToolBridgeErrorKind.AUTHORITY_DENIED,
            )
        return self.bridge.execute(call, step_id=step_id)


class DomainToolLoopRunner:
    """Run one bounded Provider-neutral loop through a domain-owned Tool bridge.

    Domain code remains responsible for durable Actor/Task state, admission,
    external effect truth, and result verification. Use HarnessRunner when Host
    Assignment and Runtime Tool durability are the owning boundary.
    """

    def __init__(
        self,
        adapter: AgentTurnAdapter,
        bridge: DomainToolBridge,
        *,
        clock_ms: Callable[[], int] | None = None,
        monotonic_ms: Callable[[], int] | None = None,
        event_sink: Callable[[HarnessRunEvent], None] | None = None,
    ) -> None:
        validate_json_value(bridge.bridge_identity)
        if not bridge.bridge_identity:
            raise ValueError("domain Tool Bridge identity must be non-empty")
        self.adapter = adapter
        self.bridge = bridge
        self.clock_ms = clock_ms
        self.monotonic_ms = monotonic_ms
        self.event_sink = event_sink

    def execution_identity(self, plan: DomainToolLoopPlan) -> dict[str, JsonValue]:
        granted = self.bridge.catalog.select(plan.allowed_tools)
        identity: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.domain-tool-loop-identity",
            "harness": {
                "package": "ordivon-harness",
                "version": package_version(),
                "loopRevision": "domain-tool-loop-v1",
            },
            "provider": {
                "adapterId": self.adapter.adapter_id,
                "requestedModelId": self.adapter.model_id,
            },
            "domain": {
                "domainId": self.bridge.catalog.domain_id,
                "catalogRevision": self.bridge.catalog.revision,
                "catalogDigest": self.bridge.catalog.digest,
                "grantedCatalogDigest": self.bridge.catalog.granted_digest(plan.allowed_tools),
                "allowedTools": [tool.name for tool in granted],
                "bridgeIdentity": self.bridge.bridge_identity,
            },
            "budget": {
                "maxModelCalls": plan.budget.max_model_calls,
                "maxToolCalls": plan.budget.max_tool_calls,
                "maxObservationBytes": plan.budget.max_observation_bytes,
                "maxWallTimeMs": plan.budget.max_wall_time_ms,
                "maxTotalTokens": plan.budget.max_total_tokens,
                "maxModelRetries": plan.budget.max_model_retries,
                "maxToolCorrections": plan.budget.max_tool_corrections,
                "maxObservationOnlyTurns": plan.budget.max_observation_only_turns,
                "maxNoProgressTurns": plan.budget.max_no_progress_turns,
                "maxModelObservationBytes": plan.budget.max_model_observation_bytes,
            },
        }
        validate_json_value(identity)
        return identity

    def run(
        self,
        plan: DomainToolLoopPlan,
        *,
        cancellation: CancellationToken | None = None,
    ) -> AgentLoopResult:
        bound_bridge = _GrantedDomainToolBridge(self.bridge, plan.allowed_tools)
        loop = OrdivonAgentLoop(
            self.adapter,
            bound_bridge,
            budget=plan.budget,
            clock_ms=self.clock_ms,
            monotonic_ms=self.monotonic_ms,
            assignment_deadline_ms=plan.assignment_deadline_ms,
            event_sink=self.event_sink,
        )
        return loop.run(
            harness_run_id=plan.harness_run_id,
            assignment_id=plan.assignment_id,
            context_digest=plan.context_digest,
            initial_messages=plan.initial_messages,
            cancellation=cancellation,
        )


__all__ = [
    "AgentLoopResult",
    "AgentRunConclusion",
    "AgentToolCall",
    "AgentToolDefinition",
    "AgentTurnAdapter",
    "CancellationToken",
    "DomainToolBridge",
    "DomainToolCatalog",
    "DomainToolLoopPlan",
    "DomainToolLoopRunner",
    "RunBudget",
    "RunStopCode",
    "ToolBridgeError",
    "ToolBridgeErrorKind",
    "ToolObservation",
]

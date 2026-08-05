"""Host-independent Agent Tool bridge values and protocol."""

from __future__ import annotations

from typing import Protocol

from ..agent_tool_observation import HarnessToolObservation
from .model import AgentToolCall, AgentToolDefinition

ToolObservation = HarnessToolObservation


class ToolBridge(Protocol):
    catalog_digest: str

    def definitions(self) -> tuple[AgentToolDefinition, ...]: ...

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation: ...


__all__ = ["ToolBridge", "ToolObservation"]

"""Experimental compact first-interface compilation over existing Harness carriers.

This module deliberately owns no discovery, ranking, priority, domain truth, or
Tool authority. Callers supply already-fenced owner facts and already-admitted
Tool definitions. The compiler only:

1. renders a compact ephemeral interaction source that can travel through the
   existing WorkingView/WorkingSet machinery; and
2. subtracts the Provider-visible Tool surface to affordances the caller has
   already established as available for this turn.

The schema is version 0 on purpose: this is a dogfood materialization, not a
frozen public contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value

from .ordivon.model import AgentToolDefinition
from .ordivon.turn_projection import (
    project_turn_tool_working_set,
    select_turn_tool_working_set,
)
from .working_view import HarnessWorkingViewSource

_ALLOWED_STANDINGS = frozenset({"AVAILABLE", "BLOCKED", "UNKNOWN"})


def _text(value: Any, label: str, *, max_bytes: int = 2048) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _texts(values: tuple[str, ...], label: str, *, max_items: int = 16) -> tuple[str, ...]:
    if len(values) > max_items:
        raise ValueError(f"{label} exceeds {max_items} items")
    return tuple(_text(value, label, max_bytes=512) for value in values)


@dataclass(frozen=True, slots=True)
class InteractionSourceRef:
    owner: str
    authority_ref: str
    authority_version: str
    currentness: str

    def __post_init__(self) -> None:
        _text(self.owner, "interaction source owner", max_bytes=256)
        _text(self.authority_ref, "interaction source authority ref", max_bytes=512)
        _text(self.authority_version, "interaction source authority version", max_bytes=512)
        _text(self.currentness, "interaction source currentness", max_bytes=160)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "owner": self.owner,
            "ref": self.authority_ref,
            "version": self.authority_version,
            "currentness": self.currentness,
        }


@dataclass(frozen=True, slots=True)
class InteractionAffordance:
    tool_name: str
    owner: str
    standing: str
    effect_class: str
    requires: tuple[str, ...] = ()
    responds_to: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.tool_name, "interaction affordance Tool name", max_bytes=160)
        _text(self.owner, "interaction affordance owner", max_bytes=256)
        if self.standing not in _ALLOWED_STANDINGS:
            raise ValueError(
                "interaction affordance standing must be AVAILABLE, BLOCKED, or UNKNOWN"
            )
        _text(self.effect_class, "interaction affordance effect class", max_bytes=160)
        _texts(self.requires, "interaction affordance requirement")
        _texts(self.responds_to, "interaction affordance blocker link")

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "tool": self.tool_name,
            "owner": self.owner,
            "standing": self.standing,
            "effect": self.effect_class,
        }
        if self.requires:
            value["requires"] = list(self.requires)
        if self.responds_to:
            value["respondsTo"] = list(self.responds_to)
        return value


@dataclass(frozen=True, slots=True)
class InteractionActionSlice:
    owner: str
    next_actions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.owner, "interaction action-slice owner", max_bytes=256)
        _texts(self.next_actions, "interaction next action")
        _texts(self.constraints, "interaction constraint")
        _texts(self.rejected, "interaction rejected action")

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {"owner": self.owner}
        if self.next_actions:
            value["next"] = list(self.next_actions)
        if self.constraints:
            value["constraints"] = list(self.constraints)
        if self.rejected:
            value["rejected"] = list(self.rejected)
        return value


@dataclass(frozen=True, slots=True)
class InteractionContextInput:
    intent: str
    sources: tuple[InteractionSourceRef, ...]
    affordances: tuple[InteractionAffordance, ...]
    action_slice: InteractionActionSlice | None = None
    blockers: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    raw_escape_available: bool = True

    def __post_init__(self) -> None:
        _text(self.intent, "interaction intent", max_bytes=512)
        if not self.sources:
            raise ValueError("interaction context requires at least one source fence")
        source_keys = [(item.owner, item.authority_ref) for item in self.sources]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("interaction context source fences must be unique")
        names = [item.tool_name for item in self.affordances]
        if len(names) != len(set(names)):
            raise ValueError("interaction context affordance Tool names must be unique")
        _texts(self.blockers, "interaction blocker")
        _texts(self.unknowns, "interaction unknown")


@dataclass(frozen=True, slots=True)
class InteractionContextMaterialization:
    source: HarnessWorkingViewSource
    selected_tool_names: tuple[str, ...]
    tool_working_set: dict[str, JsonValue]
    projection_digest: str

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 0,
            "kind": "ordivon.harness-interaction-context-materialization-experimental",
            "truthRole": "compiled-presentation-not-owner-truth",
            "sourceDigest": self.source.digest,
            "selectedTools": list(self.selected_tool_names),
            "toolWorkingSet": dict(self.tool_working_set),
            "projectionDigest": self.projection_digest,
            "claims": {
                "ownerTruthMinted": False,
                "priorityInferred": False,
                "toolAuthorityExpanded": False,
                "toolExecuted": False,
            },
        }
        validate_json_value(value)
        return value


def compile_interaction_context(
    context: InteractionContextInput,
    admitted_tools: tuple[AgentToolDefinition, ...],
    *,
    logical_ref: str,
    logical_generation: str,
) -> InteractionContextMaterialization:
    """Compile one compact source plus a subtractive per-turn Tool WorkingSet.

    AVAILABLE is not discovered here. It is a caller-supplied standing over an
    already-admitted Tool. BLOCKED/UNKNOWN affordances remain model-visible as
    context but are not Provider-callable on this turn.
    """

    _text(logical_ref, "interaction logical ref", max_bytes=500)
    _text(logical_generation, "interaction logical generation", max_bytes=500)

    admitted_by_name = {tool.name: tool for tool in admitted_tools}
    referenced = {item.tool_name for item in context.affordances}
    missing = sorted(referenced - set(admitted_by_name))
    if missing:
        raise ValueError(
            "interaction context references Tools outside the admitted surface: "
            f"{missing}"
        )

    available = {
        item.tool_name for item in context.affordances if item.standing == "AVAILABLE"
    }
    selected_names = tuple(tool.name for tool in admitted_tools if tool.name in available)
    selected = select_turn_tool_working_set(admitted_tools, selected_names)
    if tuple(tool.name for tool in selected) != selected_names:
        raise RuntimeError("interaction Tool WorkingSet selection is not stable")

    payload: dict[str, JsonValue] = {
        "v": 0,
        "kind": "ordivon.interaction-context-experimental",
        "truthRole": "compiled-presentation-not-owner-truth",
        "intent": context.intent,
        "sources": [item.to_dict() for item in context.sources],
        "affordances": [item.to_dict() for item in context.affordances],
        "rawEscape": {
            "available": context.raw_escape_available,
            "mode": "caller-may-expand-from-already-admitted-catalog",
        },
        "claims": {
            "ownerTruthMinted": False,
            "priorityInferred": False,
            "toolAuthorityExpanded": False,
        },
    }
    if context.action_slice is not None:
        payload["action"] = context.action_slice.to_dict()
    if context.blockers:
        payload["blockers"] = list(context.blockers)
    if context.unknowns:
        payload["unknowns"] = list(context.unknowns)
    validate_json_value(payload)

    compact = canonical_bytes(payload).decode("utf-8")
    source = HarnessWorkingViewSource(
        logical_ref=logical_ref,
        logical_generation=logical_generation,
        messages=(
            {
                "role": "system",
                "content": "ORDIVON_INTERACTION_CONTEXT " + compact,
            },
        ),
    )
    working_set = project_turn_tool_working_set(admitted_tools, selected_names)
    projection_digest = canonical_digest(
        {
            "sourceDigest": source.digest,
            "selectedDefinitionsDigest": working_set["selectedDefinitionsDigest"],
        }
    )
    return InteractionContextMaterialization(
        source=source,
        selected_tool_names=selected_names,
        tool_working_set=working_set,
        projection_digest=projection_digest,
    )


__all__ = [
    "InteractionActionSlice",
    "InteractionAffordance",
    "InteractionContextInput",
    "InteractionContextMaterialization",
    "InteractionSourceRef",
    "compile_interaction_context",
]

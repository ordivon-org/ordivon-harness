from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from anc_canonical import JsonValue, canonical_digest

from ..working_view import (
    HarnessWorkingSetSourceRef,
    HarnessWorkingView,
    WorkingViewProjector,
    overlay_working_view,
)
from .model import (
    AgentCallerIngressRef,
    AgentToolDefinition,
    AgentTurnCapabilities,
    AgentTurnRequest,
)


class AgentToolSurface(Protocol):
    catalog_digest: str

    def definitions(self) -> tuple[AgentToolDefinition, ...]: ...


class TurnToolWorkingSetProjector(Protocol):
    """Application-owned read-side projection of one turn-visible Tool subset.

    Implementations may consume already-fenced owner/application state, including
    an ``InteractionContextMaterialization`` compiled outside the generic loop.
    Returned names are not authority: Harness validates them as a strict subset of
    the exact Run-admitted Tool definitions before Provider admission. ``None``
    preserves the full admitted surface; an empty tuple intentionally exposes none.

    A projector must be reconstructible for replay of the same turn. If its source
    facts drift, the existing exact request/continuity fences fail closed rather
    than silently replaying a different Provider request.
    """

    def project_turn_tool_names(
        self,
        *,
        harness_run_id: str,
        assignment_id: str,
        sequence: int,
        remaining_budget: dict[str, JsonValue],
    ) -> tuple[str, ...] | None: ...


def select_turn_tool_working_set(
    definitions: tuple[AgentToolDefinition, ...],
    selected_names: tuple[str, ...] | None,
) -> tuple[AgentToolDefinition, ...]:
    """Select a Provider-visible subset from already admitted Tool definitions.

    ``None`` preserves the legacy exact admitted surface. An explicit tuple may
    only subtract definitions; it never discovers, ranks, or grants a Tool.
    """
    if selected_names is None:
        return definitions
    if len(selected_names) != len(set(selected_names)):
        raise ValueError("Turn Tool Working Set names must be unique")
    available = {tool.name for tool in definitions}
    missing = sorted(set(selected_names) - available)
    if missing:
        raise ValueError(
            "Turn Tool Working Set references Tools outside the admitted surface: "
            f"{missing}"
        )
    selected = set(selected_names)
    return tuple(tool for tool in definitions if tool.name in selected)


def project_turn_tool_working_set(
    definitions: tuple[AgentToolDefinition, ...],
    selected_names: tuple[str, ...] | None,
) -> dict[str, JsonValue]:
    selected = select_turn_tool_working_set(definitions, selected_names)
    value: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-turn-tool-working-set",
        "truthRole": "subset-of-already-admitted-tool-definitions",
        "availableCount": len(definitions),
        "selectedCount": len(selected),
        "omittedCount": len(definitions) - len(selected),
        "selectedNames": [tool.name for tool in selected],
        "selectedDefinitionsDigest": canonical_digest([tool.to_dict() for tool in selected]),
        "selectionAuthority": "caller/application-before-provider-admission",
        "canExpandAuthority": False,
    }
    return value


class CallerIngressProjector(Protocol):
    def project_current_caller_ingress(
        self,
        messages: tuple[dict[str, JsonValue], ...],
    ) -> tuple[tuple[int, dict[str, JsonValue]], ...]: ...


class AgentTurnProjectionError(RuntimeError):
    """A read-side projection dependency failed before Provider admission."""


@dataclass(frozen=True, slots=True)
class AgentTurnProjection:
    """Pure construction result for one exact Agent-visible turn.

    This object proves no durable authority. Continuity independently reconstructs
    and verifies the resulting request against Journal/CAS state before Provider
    dispatch.
    """

    request: AgentTurnRequest
    effective_working_view: HarnessWorkingView | None
    base_working_view_digest: str | None
    transient_tool_exchange_messages: int
    caller_cognition_ingress_messages: int
    canonical_messages_digest: str
    projected_messages_digest: str | None
    discarded_stale_transient_tool_exchange: bool = False


def project_agent_turn(
    *,
    harness_run_id: str,
    turn_id: str,
    sequence: int,
    assignment_id: str,
    canonical_context_digest: str,
    canonical_messages: tuple[dict[str, JsonValue], ...],
    tool_catalog_digest: str,
    runtime_tools: tuple[AgentToolDefinition, ...],
    remaining_budget: dict[str, JsonValue],
    working_set_transition_installed: bool,
    caller_ingress_promotion_installed: bool,
    working_set_history_installed: bool,
    tool_program_installed: bool = False,
    base_working_view: HarnessWorkingView | None = None,
    working_set_refs: tuple[HarnessWorkingSetSourceRef, ...] = (),
    caller_entries: tuple[tuple[int, dict[str, JsonValue]], ...] = (),
    pre_caller_tool_exchange_messages: tuple[dict[str, JsonValue], ...] = (),
    post_caller_tool_exchange_messages: tuple[dict[str, JsonValue], ...] = (),
) -> AgentTurnProjection:
    """Construct exact Provider-visible cognition and current action authority.

    All inputs must already be admitted by their owning authority. This function
    only performs deterministic structural composition; it does not discover,
    rank, retain, reconcile, or verify any source.
    """

    projected_only_inputs_present = bool(
        working_set_refs
        or caller_entries
        or pre_caller_tool_exchange_messages
        or post_caller_tool_exchange_messages
    )
    if base_working_view is None and projected_only_inputs_present:
        raise ValueError(
            "WorkingView refs and cognition overlays require a base WorkingView"
        )

    request_context_digest = canonical_context_digest
    request_messages = canonical_messages
    caller_ingress_refs: tuple[AgentCallerIngressRef, ...] = ()
    effective_working_view: HarnessWorkingView | None = None
    base_digest: str | None = None
    projected_messages_digest: str | None = None
    caller_messages = tuple(message for _index, message in caller_entries)
    transient_count = len(pre_caller_tool_exchange_messages) + len(
        post_caller_tool_exchange_messages
    )

    if base_working_view is not None:
        caller_message_offset = (
            len(base_working_view.messages) + len(pre_caller_tool_exchange_messages)
        )
        caller_ingress_refs = tuple(
            AgentCallerIngressRef(
                caller_message_index=caller_index,
                request_message_index=caller_message_offset + position,
            )
            for position, (caller_index, _message) in enumerate(caller_entries)
        )
        overlay = (
            pre_caller_tool_exchange_messages
            + caller_messages
            + post_caller_tool_exchange_messages
        )
        effective_working_view = overlay_working_view(base_working_view, overlay)
        request_context_digest = effective_working_view.digest
        request_messages = effective_working_view.messages
        base_digest = base_working_view.digest
        projected_messages_digest = canonical_digest(list(request_messages))

    request = AgentTurnRequest(
        harness_run_id=harness_run_id,
        turn_id=turn_id,
        sequence=sequence,
        assignment_id=assignment_id,
        context_digest=request_context_digest,
        tool_catalog_digest=tool_catalog_digest,
        messages=request_messages,
        tools=runtime_tools,
        capabilities=AgentTurnCapabilities(
            working_set_transition=working_set_transition_installed,
            caller_ingress_promotion=(
                caller_ingress_promotion_installed and bool(caller_ingress_refs)
            ),
            working_set_history=working_set_history_installed,
            tool_program=(
                tool_program_installed
                and bool(runtime_tools)
                and type(remaining_budget.get("toolCalls")) is int
                and int(remaining_budget["toolCalls"]) > 0
            ),
        ),
        remaining_budget=remaining_budget,
        caller_ingress_refs=caller_ingress_refs,
        working_set_refs=working_set_refs,
    )
    return AgentTurnProjection(
        request=request,
        effective_working_view=effective_working_view,
        base_working_view_digest=base_digest,
        transient_tool_exchange_messages=transient_count,
        caller_cognition_ingress_messages=len(caller_messages),
        canonical_messages_digest=canonical_digest(list(canonical_messages)),
        projected_messages_digest=projected_messages_digest,
    )


@dataclass(frozen=True, slots=True)
class AgentTurnProjector:
    """Read-side Agent Interface projection over already-owned authorities.

    It may read the current WorkingSet/caller projection and Tool definitions, but
    it performs no durable mutation and grants no semantic authority. Continuity
    remains the independent verifier of every exact request before dispatch.
    """

    tool_surface: AgentToolSurface
    working_view_projector: WorkingViewProjector | None = None
    caller_ingress_projector: CallerIngressProjector | None = None
    working_set_transition_installed: bool = False
    caller_ingress_promotion_installed: bool = False
    working_set_history_installed: bool = False
    tool_program_installed: bool = False

    def project(
        self,
        *,
        harness_run_id: str,
        turn_id: str,
        sequence: int,
        assignment_id: str,
        canonical_context_digest: str,
        canonical_messages: tuple[dict[str, JsonValue], ...],
        remaining_budget: dict[str, JsonValue],
        admit_runtime_tools: bool,
        transient_working_set_digest: str | None,
        caller_ingress_messages: tuple[dict[str, JsonValue], ...],
        pre_caller_tool_exchange_messages: tuple[dict[str, JsonValue], ...],
        post_caller_tool_exchange_messages: tuple[dict[str, JsonValue], ...],
        runtime_tool_names: tuple[str, ...] | None = None,
    ) -> AgentTurnProjection:
        if not admit_runtime_tools and runtime_tool_names not in (None, ()):
            raise ValueError(
                "Turn Tool Working Set cannot select Tools while Runtime Tool exposure is disabled"
            )

        base_working_view: HarnessWorkingView | None = None
        working_set_refs: tuple[HarnessWorkingSetSourceRef, ...] = ()
        caller_entries: tuple[tuple[int, dict[str, JsonValue]], ...] = ()
        discard_stale = False
        pre_messages = pre_caller_tool_exchange_messages
        post_messages = post_caller_tool_exchange_messages

        if self.working_view_projector is not None:
            try:
                project_with_refs = getattr(
                    self.working_view_projector, "project_with_refs", None
                )
                if callable(project_with_refs):
                    base_working_view, working_set_refs = project_with_refs()
                else:
                    base_working_view = self.working_view_projector.project()
            except Exception as error:
                raise AgentTurnProjectionError(
                    "Working View projection failed: "
                    f"{type(error).__name__}: {error}"
                ) from error

            if (
                transient_working_set_digest is not None
                and transient_working_set_digest
                != base_working_view.working_set_digest
            ):
                pre_messages = ()
                post_messages = ()
                discard_stale = True

            caller_entries = tuple(
                (index, dict(message))
                for index, message in enumerate(caller_ingress_messages)
            )
            if self.caller_ingress_projector is not None:
                try:
                    caller_entries = self.caller_ingress_projector.project_current_caller_ingress(
                        canonical_messages
                    )
                except Exception as error:
                    raise AgentTurnProjectionError(
                        "caller ingress projection failed: "
                        f"{type(error).__name__}: {error}"
                    ) from error

        projection = project_agent_turn(
            harness_run_id=harness_run_id,
            turn_id=turn_id,
            sequence=sequence,
            assignment_id=assignment_id,
            canonical_context_digest=canonical_context_digest,
            canonical_messages=canonical_messages,
            tool_catalog_digest=self.tool_surface.catalog_digest,
            runtime_tools=(
                select_turn_tool_working_set(
                    self.tool_surface.definitions(), runtime_tool_names
                )
                if admit_runtime_tools
                else ()
            ),
            remaining_budget=remaining_budget,
            working_set_transition_installed=self.working_set_transition_installed,
            caller_ingress_promotion_installed=self.caller_ingress_promotion_installed,
            working_set_history_installed=self.working_set_history_installed,
            tool_program_installed=self.tool_program_installed,
            base_working_view=base_working_view,
            working_set_refs=working_set_refs,
            caller_entries=caller_entries,
            pre_caller_tool_exchange_messages=pre_messages,
            post_caller_tool_exchange_messages=post_messages,
        )
        if not discard_stale:
            return projection
        return AgentTurnProjection(
            request=projection.request,
            effective_working_view=projection.effective_working_view,
            base_working_view_digest=projection.base_working_view_digest,
            transient_tool_exchange_messages=projection.transient_tool_exchange_messages,
            caller_cognition_ingress_messages=projection.caller_cognition_ingress_messages,
            canonical_messages_digest=projection.canonical_messages_digest,
            projected_messages_digest=projection.projected_messages_digest,
            discarded_stale_transient_tool_exchange=True,
        )


__all__ = [
    "AgentToolSurface",
    "AgentTurnProjection",
    "AgentTurnProjectionError",
    "AgentTurnProjector",
    "CallerIngressProjector",
    "TurnToolWorkingSetProjector",
    "project_agent_turn",
    "project_turn_tool_working_set",
    "select_turn_tool_working_set",
]

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from anc_canonical import JsonValue, canonical_digest, validate_json_value

WORKING_SET_HISTORY_CONTROL_NAME = "inspect_working_set_history"


def parse_working_set_history_query(
    arguments: dict[str, JsonValue],
) -> tuple[int, int | None]:
    """Parse one bounded mechanical historical WorkingSet catalog request."""
    if set(arguments) not in ({"limit"}, {"limit", "before_sequence"}):
        raise ValueError("Working Set history query fields differ")
    limit = arguments.get("limit")
    before_sequence = arguments.get("before_sequence")
    if type(limit) is not int or not 1 <= limit <= 32:
        raise ValueError("Working Set history query limit must be an integer from 1 to 32")
    if "before_sequence" in arguments and (
        type(before_sequence) is not int or before_sequence < 1
    ):
        raise ValueError("Working Set history before_sequence must be a positive integer")
    return limit, before_sequence if isinstance(before_sequence, int) else None


def _text(value: Any, label: str, *, max_bytes: int = 500) -> str:
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


@dataclass(frozen=True, slots=True)
class HarnessWorkingViewSource:
    """Exact model-visible source material addressable by one logical reference.

    This is not a Context World. Callers decide how source material is discovered
    and converted into model messages. Harness only preserves exact identity and
    provides deterministic projection for already selected sources.
    """

    logical_ref: str
    logical_generation: str
    messages: tuple[dict[str, JsonValue], ...]

    def __post_init__(self) -> None:
        _text(self.logical_ref, "Working View source logical reference")
        _text(self.logical_generation, "Working View source logical generation")
        if not self.messages:
            raise ValueError("Working View source requires at least one message")
        for message in self.messages:
            validate_json_value(message)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-working-view-source",
            "logicalRef": self.logical_ref,
            "logicalGeneration": self.logical_generation,
            "messages": list(self.messages),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessWorkingViewSource:
        expected = {
            "schemaVersion",
            "kind",
            "logicalRef",
            "logicalGeneration",
            "messages",
        }
        if set(value) != expected:
            raise ValueError("HarnessWorkingViewSource fields differ")
        raw_messages = value["messages"]
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-working-view-source"
            or not isinstance(raw_messages, list)
            or any(not isinstance(item, dict) for item in raw_messages)
        ):
            raise ValueError("HarnessWorkingViewSource is invalid")
        return cls(
            logical_ref=value["logicalRef"],
            logical_generation=value["logicalGeneration"],
            messages=tuple(dict(item) for item in raw_messages),
        )


@dataclass(frozen=True, slots=True)
class HarnessWorkingSetPin:
    slot: str
    logical_ref: str
    logical_generation: str
    resolved_digest: str

    def __post_init__(self) -> None:
        _text(self.slot, "Working Set slot", max_bytes=160)
        _text(self.logical_ref, "Working Set logical reference")
        _text(self.logical_generation, "Working Set logical generation")
        _digest(self.resolved_digest, "Working Set resolved source object digest")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "slot": self.slot,
            "logicalRef": self.logical_ref,
            "logicalGeneration": self.logical_generation,
            "resolvedDigest": self.resolved_digest,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessWorkingSetPin:
        if set(value) != {"slot", "logicalRef", "logicalGeneration", "resolvedDigest"}:
            raise ValueError("HarnessWorkingSetPin fields differ")
        return cls(
            slot=value["slot"],
            logical_ref=value["logicalRef"],
            logical_generation=value["logicalGeneration"],
            resolved_digest=value["resolvedDigest"],
        )


@dataclass(frozen=True, slots=True)
class HarnessWorkingSetSourceRef:
    """One exact current WorkingSet pin aligned to its model-message range."""

    pin: HarnessWorkingSetPin
    request_message_start_index: int
    request_message_end_index: int

    def __post_init__(self) -> None:
        if (
            type(self.request_message_start_index) is not int
            or self.request_message_start_index < 0
        ):
            raise ValueError(
                "WorkingSet source request start index must be a non-negative integer"
            )
        if (
            type(self.request_message_end_index) is not int
            or self.request_message_end_index <= self.request_message_start_index
        ):
            raise ValueError(
                "WorkingSet source request end index must be greater than its start"
            )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "pin": self.pin.to_dict(),
            "requestMessageStartIndex": self.request_message_start_index,
            "requestMessageEndIndex": self.request_message_end_index,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessWorkingSetSourceRef:
        if set(value) != {
            "pin",
            "requestMessageStartIndex",
            "requestMessageEndIndex",
        }:
            raise ValueError("HarnessWorkingSetSourceRef fields differ")
        raw_pin = value["pin"]
        if not isinstance(raw_pin, dict):
            raise ValueError("HarnessWorkingSetSourceRef pin must be an object")
        return cls(
            pin=HarnessWorkingSetPin.from_dict(raw_pin),
            request_message_start_index=value["requestMessageStartIndex"],
            request_message_end_index=value["requestMessageEndIndex"],
        )


@dataclass(frozen=True, slots=True)
class AgentWorkingSetTransitionProposal:
    """One Agent-authored proposal for the next committed cognition attempt.

    The Agent chooses exact already-known source pins and explains the transition.
    Harness does not rank, discover or repair those choices; it only validates
    that the proposal can legally extend the exact Working View that produced it.
    """

    next_attempt_id: str
    pins: tuple[HarnessWorkingSetPin, ...]
    basis: str

    def __post_init__(self) -> None:
        _text(self.next_attempt_id, "next Working Set attempt identity")
        _text(self.basis, "Working Set transition basis", max_bytes=2_048)
        slots = [pin.slot for pin in self.pins]
        if len(slots) != len(set(slots)):
            raise ValueError("Working Set transition slots must be unique")
        if tuple(sorted(self.pins, key=lambda pin: pin.slot)) != self.pins:
            raise ValueError("Working Set transition pins must be sorted by slot")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.agent-working-set-transition-proposal",
            "nextAttemptId": self.next_attempt_id,
            "pins": [pin.to_dict() for pin in self.pins],
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentWorkingSetTransitionProposal:
        expected = {"schemaVersion", "kind", "nextAttemptId", "pins", "basis"}
        if set(value) != expected:
            raise ValueError("AgentWorkingSetTransitionProposal fields differ")
        raw_pins = value["pins"]
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.agent-working-set-transition-proposal"
            or not isinstance(raw_pins, list)
            or any(not isinstance(item, dict) for item in raw_pins)
        ):
            raise ValueError("AgentWorkingSetTransitionProposal is invalid")
        return cls(
            next_attempt_id=value["nextAttemptId"],
            pins=tuple(HarnessWorkingSetPin.from_dict(item) for item in raw_pins),
            basis=value["basis"],
        )


@dataclass(frozen=True, slots=True)
class AgentCallerIngressPromotionProposal:
    """Agent-authored request to add exact current caller messages to cognition.

    Promotion is additive over the current committed WorkingSet. The Agent chooses
    exact caller-ingress message indexes, one new successor slot, and the next
    attempt identity. It does not need to restate source pins that are not normally
    model-visible, and it cannot supply or rewrite the promoted bytes.
    """

    next_attempt_id: str
    promotion_slot: str
    caller_message_indexes: tuple[int, ...]
    basis: str

    def __post_init__(self) -> None:
        _text(self.next_attempt_id, "next Working Set attempt identity")
        _text(self.promotion_slot, "caller ingress promotion slot", max_bytes=160)
        _text(self.basis, "caller ingress promotion basis", max_bytes=2_048)
        if not self.caller_message_indexes:
            raise ValueError("caller ingress promotion requires at least one message index")
        if any(type(index) is not int or index < 0 for index in self.caller_message_indexes):
            raise ValueError("caller ingress promotion indexes must be non-negative integers")
        if tuple(sorted(set(self.caller_message_indexes))) != self.caller_message_indexes:
            raise ValueError("caller ingress promotion indexes must be unique and sorted")
        if len(self.caller_message_indexes) > 32:
            raise ValueError("caller ingress promotion may select at most 32 messages")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.agent-caller-ingress-promotion-proposal",
            "nextAttemptId": self.next_attempt_id,
            "promotionSlot": self.promotion_slot,
            "callerMessageIndexes": list(self.caller_message_indexes),
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentCallerIngressPromotionProposal:
        expected = {
            "schemaVersion",
            "kind",
            "nextAttemptId",
            "promotionSlot",
            "callerMessageIndexes",
            "basis",
        }
        if set(value) != expected:
            raise ValueError("AgentCallerIngressPromotionProposal fields differ")
        raw_indexes = value["callerMessageIndexes"]
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.agent-caller-ingress-promotion-proposal"
            or not isinstance(raw_indexes, list)
        ):
            raise ValueError("AgentCallerIngressPromotionProposal is invalid")
        return cls(
            next_attempt_id=value["nextAttemptId"],
            promotion_slot=value["promotionSlot"],
            caller_message_indexes=tuple(raw_indexes),
            basis=value["basis"],
        )


@dataclass(frozen=True, slots=True)
class HarnessWorkingSetSpec:
    """Agent-owned current selection state, distinct from durable Run history."""

    attempt_id: str
    revision: int
    pins: tuple[HarnessWorkingSetPin, ...]
    previous_digest: str | None = None
    parent_attempt_id: str | None = None
    committed: bool = False
    commit_basis: str | None = None

    def __post_init__(self) -> None:
        _text(self.attempt_id, "Working Set attempt identity")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("Working Set revision must be positive")
        if self.previous_digest is not None:
            _digest(self.previous_digest, "previous Working Set digest")
        if self.parent_attempt_id is not None:
            _text(self.parent_attempt_id, "parent Working Set attempt identity")
        slots = [pin.slot for pin in self.pins]
        if len(slots) != len(set(slots)):
            raise ValueError("Working Set slots must be unique")
        if tuple(sorted(self.pins, key=lambda pin: pin.slot)) != self.pins:
            raise ValueError("Working Set pins must be sorted by slot")
        if self.committed:
            _text(self.commit_basis, "Working Set commit basis", max_bytes=2_048)
        elif self.commit_basis is not None:
            raise ValueError("uncommitted Working Set cannot carry a commit basis")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-working-set-spec",
            "attemptId": self.attempt_id,
            "revision": self.revision,
            "previousDigest": self.previous_digest,
            "parentAttemptId": self.parent_attempt_id,
            "pins": [pin.to_dict() for pin in self.pins],
            "committed": self.committed,
            "commitBasis": self.commit_basis,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessWorkingSetSpec:
        expected = {
            "schemaVersion",
            "kind",
            "attemptId",
            "revision",
            "previousDigest",
            "parentAttemptId",
            "pins",
            "committed",
            "commitBasis",
        }
        if set(value) != expected:
            raise ValueError("HarnessWorkingSetSpec fields differ")
        raw_pins = value["pins"]
        if (
            value["schemaVersion"] != 1
            or value["kind"] != "ordivon.harness-working-set-spec"
            or not isinstance(raw_pins, list)
            or any(not isinstance(item, dict) for item in raw_pins)
            or not isinstance(value["committed"], bool)
        ):
            raise ValueError("HarnessWorkingSetSpec is invalid")
        return cls(
            attempt_id=value["attemptId"],
            revision=value["revision"],
            pins=tuple(HarnessWorkingSetPin.from_dict(item) for item in raw_pins),
            previous_digest=value["previousDigest"],
            parent_attempt_id=value["parentAttemptId"],
            committed=value["committed"],
            commit_basis=value["commitBasis"],
        )

    @classmethod
    def initial(
        cls,
        attempt_id: str,
        *,
        pins: tuple[HarnessWorkingSetPin, ...] = (),
        parent_attempt_id: str | None = None,
    ) -> HarnessWorkingSetSpec:
        return cls(
            attempt_id=attempt_id,
            revision=1,
            pins=tuple(sorted(pins, key=lambda pin: pin.slot)),
            parent_attempt_id=parent_attempt_id,
        )

    def replace_pin(self, pin: HarnessWorkingSetPin) -> HarnessWorkingSetSpec:
        self._require_mutable()
        by_slot = {item.slot: item for item in self.pins}
        by_slot[pin.slot] = pin
        return HarnessWorkingSetSpec(
            attempt_id=self.attempt_id,
            revision=self.revision + 1,
            previous_digest=self.digest,
            parent_attempt_id=self.parent_attempt_id,
            pins=tuple(by_slot[key] for key in sorted(by_slot)),
        )

    def select_pins(
        self, pins: tuple[HarnessWorkingSetPin, ...]
    ) -> HarnessWorkingSetSpec:
        """Replace the complete mutable selection in one revision."""
        self._require_mutable()
        ordered = tuple(sorted(pins, key=lambda pin: pin.slot))
        if len({pin.slot for pin in ordered}) != len(ordered):
            raise ValueError("Working Set selection slots must be unique")
        return HarnessWorkingSetSpec(
            attempt_id=self.attempt_id,
            revision=self.revision + 1,
            previous_digest=self.digest,
            parent_attempt_id=self.parent_attempt_id,
            pins=ordered,
        )

    def remove_pin(self, slot: str) -> HarnessWorkingSetSpec:
        self._require_mutable()
        _text(slot, "Working Set slot", max_bytes=160)
        by_slot = {item.slot: item for item in self.pins}
        by_slot.pop(slot, None)
        return HarnessWorkingSetSpec(
            attempt_id=self.attempt_id,
            revision=self.revision + 1,
            previous_digest=self.digest,
            parent_attempt_id=self.parent_attempt_id,
            pins=tuple(by_slot[key] for key in sorted(by_slot)),
        )

    def commit(self, basis: str) -> HarnessWorkingSetSpec:
        self._require_mutable()
        return HarnessWorkingSetSpec(
            attempt_id=self.attempt_id,
            revision=self.revision + 1,
            previous_digest=self.digest,
            parent_attempt_id=self.parent_attempt_id,
            pins=self.pins,
            committed=True,
            commit_basis=basis,
        )

    def replan(self, attempt_id: str) -> HarnessWorkingSetSpec:
        if not self.committed:
            raise ValueError("Working Set replan requires a committed predecessor")
        return HarnessWorkingSetSpec(
            attempt_id=attempt_id,
            revision=1,
            previous_digest=self.digest,
            parent_attempt_id=self.attempt_id,
            pins=(),
        )

    def _require_mutable(self) -> None:
        if self.committed:
            raise ValueError("committed Working Set is frozen for this attempt")


@dataclass(frozen=True, slots=True)
class HarnessWorkingView:
    attempt_id: str
    working_set_digest: str
    messages: tuple[dict[str, JsonValue], ...]

    def __post_init__(self) -> None:
        _text(self.attempt_id, "Working View attempt identity")
        _digest(self.working_set_digest, "Working Set digest")
        for message in self.messages:
            validate_json_value(message)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-working-view",
            "attemptId": self.attempt_id,
            "workingSetDigest": self.working_set_digest,
            "messages": list(self.messages),
        }


class WorkingViewObjects(Protocol):
    def get_object(self, digest: str, *, expected_kind: str | None = None) -> JsonValue: ...


class WorkingSetReader(Protocol):
    def load_current_working_set(self) -> HarnessWorkingSetSpec: ...


class WorkingViewProjector(Protocol):
    """Project the exact model-visible view for the next Provider turn."""

    def project(self) -> HarnessWorkingView: ...


class CallerIngressPromotionHandler(Protocol):
    """Materialize exact current caller ingress and select it into a successor WorkingSet."""

    def load_current_working_set(self) -> HarnessWorkingSetSpec: ...

    def apply_caller_ingress_promotion(
        self,
        proposal: AgentCallerIngressPromotionProposal,
        *,
        source_working_set_digest: str,
        source_model_view_digest: str,
    ) -> HarnessWorkingSetSpec: ...

    def project_current_caller_ingress(
        self,
        messages: tuple[dict[str, JsonValue], ...],
    ) -> tuple[tuple[int, dict[str, JsonValue]], ...]: ...


class WorkingSetTransitionHandler(Protocol):
    """Admit one Agent-authored successor Working Set against its source model view."""

    def load_current_working_set(self) -> HarnessWorkingSetSpec: ...

    def apply_working_set_transition(
        self,
        proposal: AgentWorkingSetTransitionProposal,
        *,
        source_working_set_digest: str,
        source_model_view_digest: str,
    ) -> HarnessWorkingSetSpec: ...


class WorkingSetHistoryReader(Protocol):
    """Expose bounded exact identities from earlier committed Working Sets."""

    def inspect_working_set_history(
        self,
        *,
        limit: int,
        before_sequence: int | None = None,
    ) -> dict[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class WorkingSetViewProjector:
    """Compile each Provider turn from the current committed Working Set.

    The projector does not discover or rank Context and it does not mutate the
    Working Set. A caller/Agent transition must already have committed the exact
    selection that should become model-visible for the next turn.
    """

    objects: WorkingViewObjects
    working_sets: WorkingSetReader

    def project(self) -> HarnessWorkingView:
        view, _refs = self.project_with_refs()
        return view

    def project_with_refs(
        self,
    ) -> tuple[HarnessWorkingView, tuple[HarnessWorkingSetSourceRef, ...]]:
        spec = self.working_sets.load_current_working_set()
        if not spec.committed:
            raise ValueError(
                "Provider Working View requires a committed Working Set"
            )
        return compile_working_view_with_refs(spec, self.objects)


def overlay_working_view(
    base: HarnessWorkingView,
    overlay_messages: tuple[dict[str, JsonValue], ...],
) -> HarnessWorkingView:
    """Append already-bounded transient messages without replacing selected Context.

    This pure helper assigns no authority or discovery meaning to the appended
    messages. On the durable Continuity path, Provider admission separately
    requires appended messages to be exact projections of bound Tool
    Observations. The committed WorkingView remains an exact prefix.
    """
    for message in overlay_messages:
        validate_json_value(message)
    if not overlay_messages:
        return base
    return HarnessWorkingView(
        attempt_id=base.attempt_id,
        working_set_digest=base.working_set_digest,
        messages=base.messages + tuple(dict(message) for message in overlay_messages),
    )


def compile_working_view_with_refs(
    spec: HarnessWorkingSetSpec,
    objects: WorkingViewObjects,
) -> tuple[HarnessWorkingView, tuple[HarnessWorkingSetSourceRef, ...]]:
    messages: list[dict[str, JsonValue]] = []
    refs: list[HarnessWorkingSetSourceRef] = []
    for pin in spec.pins:
        raw = objects.get_object(
            pin.resolved_digest,
            expected_kind="harness-working-view-source",
        )
        if not isinstance(raw, dict):
            raise TypeError("Working View source object must be an object")
        source = HarnessWorkingViewSource.from_dict(raw)
        if (
            source.logical_ref != pin.logical_ref
            or source.logical_generation != pin.logical_generation
        ):
            raise ValueError("Working Set pin differs from its exact source object")
        start = len(messages)
        messages.extend(dict(message) for message in source.messages)
        refs.append(
            HarnessWorkingSetSourceRef(
                pin=pin,
                request_message_start_index=start,
                request_message_end_index=len(messages),
            )
        )
    return (
        HarnessWorkingView(
            attempt_id=spec.attempt_id,
            working_set_digest=spec.digest,
            messages=tuple(messages),
        ),
        tuple(refs),
    )


def compile_working_view(
    spec: HarnessWorkingSetSpec,
    objects: WorkingViewObjects,
) -> HarnessWorkingView:
    view, _refs = compile_working_view_with_refs(spec, objects)
    return view


__all__ = [
    "AgentCallerIngressPromotionProposal",
    "AgentWorkingSetTransitionProposal",
    "HarnessWorkingSetPin",
    "HarnessWorkingSetSourceRef",
    "HarnessWorkingSetSpec",
    "HarnessWorkingView",
    "HarnessWorkingViewSource",
    "WORKING_SET_HISTORY_CONTROL_NAME",
    "CallerIngressPromotionHandler",
    "WorkingSetHistoryReader",
    "WorkingSetTransitionHandler",
    "WorkingSetViewProjector",
    "WorkingViewProjector",
    "compile_working_view",
    "compile_working_view_with_refs",
    "overlay_working_view",
    "parse_working_set_history_query",
]

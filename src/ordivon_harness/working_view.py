from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from anc_canonical import JsonValue, canonical_digest, validate_json_value


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


def compile_working_view(
    spec: HarnessWorkingSetSpec,
    objects: WorkingViewObjects,
) -> HarnessWorkingView:
    messages: list[dict[str, JsonValue]] = []
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
        messages.extend(dict(message) for message in source.messages)
    return HarnessWorkingView(
        attempt_id=spec.attempt_id,
        working_set_digest=spec.digest,
        messages=tuple(messages),
    )


__all__ = [
    "HarnessWorkingSetPin",
    "HarnessWorkingSetSpec",
    "HarnessWorkingView",
    "HarnessWorkingViewSource",
    "compile_working_view",
]

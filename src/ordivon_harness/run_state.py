from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from anc_canonical import (
    JsonValue,
    canonical_bytes,
    canonical_digest,
    validate_json_value,
)
from ordivon_host.objects import StoredObject

_FULL_KIND = "ordivon.harness-run-state"
_DELTA_KIND = "ordivon.harness-run-state-delta"
_FULL_OBJECT_KIND = "harness-run-state"
_DELTA_OBJECT_KIND = "harness-run-state-delta"
_MAX_DELTA_DEPTH = 64


class RunStateObjects(Protocol):
    def inspect(self, digest: str) -> StoredObject: ...

    def get(self, digest: str, *, expected_kind: str | None = None) -> JsonValue: ...


@dataclass(frozen=True, slots=True)
class HarnessRunState:
    messages: tuple[dict[str, JsonValue], ...]
    observations: tuple[dict[str, JsonValue], ...]
    remaining_budget: dict[str, JsonValue]
    requested_model_id: str
    effective_model_id: str | None
    active_elapsed_ms: int | None = None
    seen_model_call_ids: tuple[str, ...] = ()
    seen_tool_call_ids: tuple[str, ...] = ()
    provider_usage: tuple[dict[str, JsonValue], ...] = ()
    effective_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_json_value(list(self.messages))
        validate_json_value(list(self.observations))
        validate_json_value(self.remaining_budget)
        if self.active_elapsed_ms is not None and (
            type(self.active_elapsed_ms) is not int or self.active_elapsed_ms < 0
        ):
            raise ValueError("active elapsed time must be a non-negative integer")
        if (
            not self.requested_model_id
            or self.requested_model_id != self.requested_model_id.strip()
        ):
            raise ValueError("requested model identity must be non-empty and trimmed")
        if self.effective_model_id is not None and (
            not self.effective_model_id
            or self.effective_model_id != self.effective_model_id.strip()
        ):
            raise ValueError("effective model identity must be trimmed")
        for label, values in (
            ("Model Call", self.seen_model_call_ids),
            ("Tool Call", self.seen_tool_call_ids),
            ("effective model", self.effective_model_ids),
        ):
            if len(values) != len(set(values)) or any(
                not value or value != value.strip() for value in values
            ):
                raise ValueError(
                    f"Harness Run {label} identities must be unique and trimmed"
                )
        validate_json_value(list(self.provider_usage))

    @property
    def messages_digest(self) -> str:
        return canonical_digest(list(self.messages))

    @property
    def observation_digests(self) -> tuple[str, ...]:
        return tuple(canonical_digest(item) for item in self.observations)

    def to_dict(self, harness_run_id: str) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "schemaVersion": 2 if self.active_elapsed_ms is not None else 1,
            "kind": _FULL_KIND,
            "harnessRunId": harness_run_id,
            "messages": list(self.messages),
            "observations": list(self.observations),
            "remainingBudget": self.remaining_budget,
            "requestedModelId": self.requested_model_id,
            "effectiveModelId": self.effective_model_id,
            "seenModelCallIds": list(self.seen_model_call_ids),
            "seenToolCallIds": list(self.seen_tool_call_ids),
            "providerUsage": list(self.provider_usage),
            "effectiveModelIds": list(self.effective_model_ids),
        }
        if self.active_elapsed_ms is not None:
            value["activeElapsedMs"] = self.active_elapsed_ms
        return value


def state_from_dict(value: dict[str, Any], *, harness_run_id: str) -> HarnessRunState:
    legacy_fields = {
        "schemaVersion",
        "kind",
        "harnessRunId",
        "messages",
        "observations",
        "remainingBudget",
        "requestedModelId",
        "effectiveModelId",
    }
    version_one_fields = legacy_fields | {
        "seenModelCallIds",
        "seenToolCallIds",
        "providerUsage",
        "effectiveModelIds",
    }
    version_two_fields = version_one_fields | {"activeElapsedMs"}
    fields = frozenset(value)
    version = value.get("schemaVersion")
    if not (
        version == 1 and fields in {frozenset(legacy_fields), frozenset(version_one_fields)}
        or version == 2 and fields == version_two_fields
    ):
        raise ValueError("Harness Run state fields differ")
    if (
        value["kind"] != _FULL_KIND
        or value["harnessRunId"] != harness_run_id
        or not isinstance(value["messages"], list)
        or not isinstance(value["observations"], list)
        or not isinstance(value["remainingBudget"], dict)
        or not isinstance(value["requestedModelId"], str)
        or value["effectiveModelId"] is not None
        and not isinstance(value["effectiveModelId"], str)
    ):
        raise ValueError("Harness Run state is invalid")
    active_elapsed_ms = value.get("activeElapsedMs")
    if active_elapsed_ms is not None and (
        type(active_elapsed_ms) is not int or active_elapsed_ms < 0
    ):
        raise ValueError("Harness Run active elapsed time is invalid")
    if any(not isinstance(item, dict) for item in value["messages"]):
        raise ValueError("Harness Run messages are invalid")
    if any(not isinstance(item, dict) for item in value["observations"]):
        raise ValueError("Harness Run observations are invalid")
    for field in ("seenModelCallIds", "seenToolCallIds", "effectiveModelIds"):
        raw = value.get(field, [])
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise ValueError(f"Harness Run {field} is invalid")
    provider_usage = value.get("providerUsage", [])
    if not isinstance(provider_usage, list) or any(
        not isinstance(item, dict) for item in provider_usage
    ):
        raise ValueError("Harness Run Provider usage is invalid")
    validate_json_value(value)
    return HarnessRunState(
        messages=tuple(dict(item) for item in value["messages"]),
        observations=tuple(dict(item) for item in value["observations"]),
        remaining_budget=dict(value["remainingBudget"]),
        requested_model_id=value["requestedModelId"],
        effective_model_id=value["effectiveModelId"],
        active_elapsed_ms=active_elapsed_ms,
        seen_model_call_ids=tuple(value.get("seenModelCallIds", [])),
        seen_tool_call_ids=tuple(value.get("seenToolCallIds", [])),
        provider_usage=tuple(dict(item) for item in provider_usage),
        effective_model_ids=tuple(value.get("effectiveModelIds", [])),
    )


def build_state_delta(
    *,
    harness_run_id: str,
    previous_state_object_digest: str,
    previous: HarnessRunState,
    current: HarnessRunState,
) -> dict[str, JsonValue] | None:
    if previous.requested_model_id != current.requested_model_id:
        return None
    if previous.active_elapsed_ms is not None and (
        current.active_elapsed_ms is None
        or current.active_elapsed_ms < previous.active_elapsed_ms
    ):
        raise ValueError("Harness Run active elapsed time cannot decrease")
    previous_wall_time = previous.remaining_budget.get("wallTimeMs")
    current_wall_time = current.remaining_budget.get("wallTimeMs")
    if (
        type(previous_wall_time) is int
        and type(current_wall_time) is int
        and current_wall_time > previous_wall_time
    ):
        raise ValueError("Harness Run remaining wall time cannot increase")
    sequences = (
        (previous.messages, current.messages),
        (previous.observations, current.observations),
        (previous.seen_model_call_ids, current.seen_model_call_ids),
        (previous.seen_tool_call_ids, current.seen_tool_call_ids),
        (previous.provider_usage, current.provider_usage),
        (previous.effective_model_ids, current.effective_model_ids),
    )
    if any(
        tuple(current_values[: len(previous_values)]) != previous_values
        for previous_values, current_values in sequences
    ):
        return None
    delta: dict[str, JsonValue] = {
        "schemaVersion": 2 if current.active_elapsed_ms is not None else 1,
        "kind": _DELTA_KIND,
        "harnessRunId": harness_run_id,
        "previousStateObjectDigest": previous_state_object_digest,
        "previousStateDigest": canonical_digest(previous.to_dict(harness_run_id)),
        "appendedMessages": list(current.messages[len(previous.messages) :]),
        "appendedObservations": list(
            current.observations[len(previous.observations) :]
        ),
        "remainingBudget": current.remaining_budget,
        "requestedModelId": current.requested_model_id,
        "effectiveModelId": current.effective_model_id,
        "appendedSeenModelCallIds": list(
            current.seen_model_call_ids[len(previous.seen_model_call_ids) :]
        ),
        "appendedSeenToolCallIds": list(
            current.seen_tool_call_ids[len(previous.seen_tool_call_ids) :]
        ),
        "appendedProviderUsage": list(
            current.provider_usage[len(previous.provider_usage) :]
        ),
        "appendedEffectiveModelIds": list(
            current.effective_model_ids[len(previous.effective_model_ids) :]
        ),
    }
    if current.active_elapsed_ms is not None:
        delta["activeElapsedMs"] = current.active_elapsed_ms
    validate_json_value(delta)
    if len(canonical_bytes(delta)) >= len(
        canonical_bytes(current.to_dict(harness_run_id))
    ):
        return None
    return delta


def load_state_object(
    objects: RunStateObjects,
    digest: str,
    *,
    harness_run_id: str,
    max_depth: int = _MAX_DELTA_DEPTH,
) -> HarnessRunState:
    if max_depth < 1:
        raise ValueError("Harness Run state delta chain exceeds the bounded depth")
    stored = objects.inspect(digest)
    if stored.kind == _FULL_OBJECT_KIND:
        raw = objects.get(digest, expected_kind=_FULL_OBJECT_KIND)
        if not isinstance(raw, dict):
            raise TypeError("Harness Run state object is invalid")
        return state_from_dict(raw, harness_run_id=harness_run_id)
    if stored.kind != _DELTA_OBJECT_KIND:
        raise ValueError(f"unsupported Harness Run state object kind: {stored.kind}")
    raw = objects.get(digest, expected_kind=_DELTA_OBJECT_KIND)
    if not isinstance(raw, dict):
        raise TypeError("Harness Run state delta object is invalid")
    return _apply_state_delta(
        objects,
        raw,
        harness_run_id=harness_run_id,
        max_depth=max_depth,
    )


def _apply_state_delta(
    objects: RunStateObjects,
    value: dict[str, Any],
    *,
    harness_run_id: str,
    max_depth: int,
) -> HarnessRunState:
    version_one_fields = {
        "schemaVersion",
        "kind",
        "harnessRunId",
        "previousStateObjectDigest",
        "previousStateDigest",
        "appendedMessages",
        "appendedObservations",
        "remainingBudget",
        "requestedModelId",
        "effectiveModelId",
        "appendedSeenModelCallIds",
        "appendedSeenToolCallIds",
        "appendedProviderUsage",
        "appendedEffectiveModelIds",
    }
    version_two_fields = version_one_fields | {"activeElapsedMs"}
    version = value.get("schemaVersion")
    fields = frozenset(value)
    if not (
        version == 1 and fields == version_one_fields
        or version == 2 and fields == version_two_fields
    ):
        raise ValueError("Harness Run state delta fields differ")
    list_fields = (
        "appendedMessages",
        "appendedObservations",
        "appendedSeenModelCallIds",
        "appendedSeenToolCallIds",
        "appendedProviderUsage",
        "appendedEffectiveModelIds",
    )
    if (
        value["kind"] != _DELTA_KIND
        or value["harnessRunId"] != harness_run_id
        or not isinstance(value["previousStateObjectDigest"], str)
        or not isinstance(value["previousStateDigest"], str)
        or not isinstance(value["remainingBudget"], dict)
        or not isinstance(value["requestedModelId"], str)
        or value["effectiveModelId"] is not None
        and not isinstance(value["effectiveModelId"], str)
        or any(not isinstance(value[field], list) for field in list_fields)
        or any(not isinstance(item, dict) for item in value["appendedMessages"])
        or any(not isinstance(item, dict) for item in value["appendedObservations"])
        or any(not isinstance(item, str) for item in value["appendedSeenModelCallIds"])
        or any(not isinstance(item, str) for item in value["appendedSeenToolCallIds"])
        or any(not isinstance(item, dict) for item in value["appendedProviderUsage"])
        or any(not isinstance(item, str) for item in value["appendedEffectiveModelIds"])
    ):
        raise ValueError("Harness Run state delta is invalid")
    active_elapsed_ms = value.get("activeElapsedMs")
    if active_elapsed_ms is not None and (
        type(active_elapsed_ms) is not int or active_elapsed_ms < 0
    ):
        raise ValueError("Harness Run state delta active elapsed time is invalid")
    validate_json_value(value)
    previous = load_state_object(
        objects,
        value["previousStateObjectDigest"],
        harness_run_id=harness_run_id,
        max_depth=max_depth - 1,
    )
    if (
        canonical_digest(previous.to_dict(harness_run_id))
        != value["previousStateDigest"]
    ):
        raise ValueError("Harness Run state delta predecessor differs")
    if previous.requested_model_id != value["requestedModelId"]:
        raise ValueError("Harness Run state delta requested model differs")
    if previous.active_elapsed_ms is not None and (
        active_elapsed_ms is None
        or active_elapsed_ms < previous.active_elapsed_ms
    ):
        raise ValueError("Harness Run state delta active elapsed time decreased")
    previous_wall_time = previous.remaining_budget.get("wallTimeMs")
    current_wall_time = value["remainingBudget"].get("wallTimeMs")
    if (
        type(previous_wall_time) is int
        and type(current_wall_time) is int
        and current_wall_time > previous_wall_time
    ):
        raise ValueError("Harness Run state delta remaining wall time increased")
    return HarnessRunState(
        messages=previous.messages
        + tuple(dict(item) for item in value["appendedMessages"]),
        observations=previous.observations
        + tuple(dict(item) for item in value["appendedObservations"]),
        remaining_budget=dict(value["remainingBudget"]),
        requested_model_id=value["requestedModelId"],
        effective_model_id=value["effectiveModelId"],
        active_elapsed_ms=active_elapsed_ms,
        seen_model_call_ids=previous.seen_model_call_ids
        + tuple(value["appendedSeenModelCallIds"]),
        seen_tool_call_ids=previous.seen_tool_call_ids
        + tuple(value["appendedSeenToolCallIds"]),
        provider_usage=previous.provider_usage
        + tuple(dict(item) for item in value["appendedProviderUsage"]),
        effective_model_ids=previous.effective_model_ids
        + tuple(value["appendedEffectiveModelIds"]),
    )

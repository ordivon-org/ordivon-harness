from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value

_EVENT_KINDS = {
    "run_started",
    "run_resumed",
    "run_progress_evaluated",
    "model_call_budget_checked",
    "model_call_budget_rejected",
    "model_view_projected",
    "model_call_started",
    "model_call_attempt_started",
    "model_call_attempt_failed",
    "model_call_retry_scheduled",
    "model_call_completed",
    "tool_call_proposed",
    "tool_call_dispatched",
    "tool_call_observed",
    "tool_call_rejected",
    "tool_call_unknown",
    "tool_call_cancel_requested",
    "tool_call_cancelled",
    "tool_call_reconciled",
    "conclusion_rejected",
    "run_stopped",
}


@dataclass(frozen=True, slots=True)
class HarnessRunEvent:
    sequence: int
    kind: str
    occurred_at_ms: int
    payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("Harness event sequence must be positive")
        if self.kind not in _EVENT_KINDS:
            raise ValueError(f"unsupported Harness event kind: {self.kind}")
        if self.occurred_at_ms < 0:
            raise ValueError("Harness event time must be non-negative")
        validate_json_value(self.payload)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "occurredAtMs": self.occurred_at_ms,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessRunEvent:
        if set(value) != {"sequence", "kind", "occurredAtMs", "payload"}:
            raise ValueError("HarnessRunEvent fields differ")
        if (
            type(value["sequence"]) is not int
            or not isinstance(value["kind"], str)
            or type(value["occurredAtMs"]) is not int
            or not isinstance(value["payload"], dict)
        ):
            raise ValueError("HarnessRunEvent fields are invalid")
        validate_json_value(value["payload"])
        return cls(
            sequence=value["sequence"],
            kind=value["kind"],
            occurred_at_ms=value["occurredAtMs"],
            payload=dict(value["payload"]),
        )


@dataclass(frozen=True, slots=True)
class HarnessTrace:
    harness_run_id: str
    events: tuple[HarnessRunEvent, ...]

    def __post_init__(self) -> None:
        if (
            not self.harness_run_id
            or self.harness_run_id != self.harness_run_id.strip()
        ):
            raise ValueError("Harness Run identity must be non-empty and trimmed")
        if tuple(event.sequence for event in self.events) != tuple(
            range(1, len(self.events) + 1)
        ):
            raise ValueError("Harness event sequence must be contiguous")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-trace",
            "harnessRunId": self.harness_run_id,
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessTrace:
        if set(value) != {"schemaVersion", "kind", "harnessRunId", "events"}:
            raise ValueError("HarnessTrace fields differ")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-trace":
            raise ValueError("HarnessTrace version or kind is invalid")
        if not isinstance(value["harnessRunId"], str):
            raise ValueError("HarnessTrace Run identity must be a string")
        events = value["events"]
        if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
            raise ValueError("HarnessTrace events must be objects")
        return cls(
            harness_run_id=value["harnessRunId"],
            events=tuple(HarnessRunEvent.from_dict(item) for item in events),
        )


class TraceRecorder:
    """Canonical in-memory Trace with a best-effort live projection."""

    def __init__(
        self,
        harness_run_id: str,
        *,
        clock_ms: Callable[[], int],
        event_sink: Callable[[HarnessRunEvent], None] | None = None,
    ) -> None:
        if not harness_run_id or harness_run_id != harness_run_id.strip():
            raise ValueError("Harness Run identity must be non-empty and trimmed")
        self.harness_run_id = harness_run_id
        self.clock_ms = clock_ms
        self.event_sink = event_sink
        self._events: list[HarnessRunEvent] = []
        self._last_time = -1

    def record(self, kind: str, payload: dict[str, JsonValue]) -> HarnessRunEvent:
        observed = self.clock_ms()
        if observed < 0:
            raise ValueError("Harness clock returned a negative time")
        occurred_at_ms = max(observed, self._last_time)
        event = HarnessRunEvent(
            sequence=len(self._events) + 1,
            kind=kind,
            occurred_at_ms=occurred_at_ms,
            payload=dict(payload),
        )
        self._events.append(event)
        self._last_time = occurred_at_ms
        if self.event_sink is not None:
            try:
                self.event_sink(event)
            except Exception:  # noqa: BLE001 - live projection cannot invalidate evidence.
                pass
        return event

    def freeze(self) -> HarnessTrace:
        return HarnessTrace(self.harness_run_id, tuple(self._events))

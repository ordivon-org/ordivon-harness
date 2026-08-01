from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


class CancellationToken:
    """Thread-safe cancellation request. Confirmation belongs to the active owner."""

    def __init__(self, *, monotonic_ms: Callable[[], int] | None = None) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._monotonic_ms = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)
        self._requested_at_ms: int | None = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def requested_at_ms(self) -> int | None:
        return self._requested_at_ms

    def cancel(self) -> None:
        with self._lock:
            if self._requested_at_ms is None:
                self._requested_at_ms = self._monotonic_ms()
            self._event.set()


@dataclass(frozen=True, slots=True)
class RunDeadline:
    expires_at_ms: int
    monotonic_ms: Callable[[], int]

    @classmethod
    def after(
        cls,
        timeout_ms: int,
        *,
        monotonic_ms: Callable[[], int] | None = None,
    ) -> RunDeadline:
        if timeout_ms < 1:
            raise ValueError("Run deadline must be positive")
        clock = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)
        return cls(clock() + timeout_ms, clock)

    @property
    def expired(self) -> bool:
        return self.remaining_ms <= 0

    @property
    def remaining_ms(self) -> int:
        return max(0, self.expires_at_ms - self.monotonic_ms())


@dataclass(frozen=True, slots=True)
class ExecutionControl:
    cancellation: CancellationToken
    deadline: RunDeadline

    @property
    def stop_requested(self) -> bool:
        return self.cancellation.cancelled or self.deadline.expired

    @property
    def remaining_ms(self) -> int:
        return self.deadline.remaining_ms

    def clamp_timeout_seconds(self, configured_seconds: float) -> float:
        if configured_seconds <= 0:
            raise ValueError("configured timeout must be positive")
        remaining = self.remaining_ms / 1_000
        if remaining <= 0:
            return 0.001
        return max(0.001, min(configured_seconds, remaining))

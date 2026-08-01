from __future__ import annotations

from ordivon_host.domain import EventKind

HARNESS_ASSIGNMENT_COMMITTED = EventKind("harness.assignment-committed")
HARNESS_RUN_RECOVERY_RECORDED = EventKind("harness.run-recovery-recorded")
HARNESS_RUN_ABANDONED = EventKind("harness.run-abandoned")
HARNESS_RUN_RECORDED = EventKind("harness.run-recorded")
COMPLETION_PROPOSED = EventKind("completion.proposed")
COMPLETION_DECIDED = EventKind("completion.decided")

HARNESS_EVENT_KINDS = frozenset(
    {
        HARNESS_ASSIGNMENT_COMMITTED,
        HARNESS_RUN_RECOVERY_RECORDED,
        HARNESS_RUN_ABANDONED,
        HARNESS_RUN_RECORDED,
        COMPLETION_PROPOSED,
        COMPLETION_DECIDED,
    }
)

__all__ = [
    "COMPLETION_DECIDED",
    "COMPLETION_PROPOSED",
    "HARNESS_ASSIGNMENT_COMMITTED",
    "HARNESS_EVENT_KINDS",
    "HARNESS_RUN_ABANDONED",
    "HARNESS_RUN_RECORDED",
    "HARNESS_RUN_RECOVERY_RECORDED",
]

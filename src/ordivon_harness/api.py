"""Recommended public facade for application code.

The package root retains historical exports during the pre-1.0 compatibility
window. New integrations should import from this module so internal persistence,
Provider-driver, and recovery implementation types can evolve independently.
"""

from .contracts import TaskContract, ToolGrant
from .runner import (
    CompletionMode,
    HarnessCancellationResult,
    HarnessExecutionResult,
    HarnessRunner,
    HarnessRunPlan,
    HarnessStatus,
    RunHandle,
)

__all__ = [
    "CompletionMode",
    "HarnessCancellationResult",
    "HarnessExecutionResult",
    "HarnessRunner",
    "HarnessRunPlan",
    "HarnessStatus",
    "RunHandle",
    "TaskContract",
    "ToolGrant",
]

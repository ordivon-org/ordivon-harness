"""Host-backed compatibility facade for the pre-1.0 production path.

New caller-neutral integrations should use :mod:`ordivon_harness.api`. This
module remains explicit so applications that intentionally bind a Harness Run
to Ordivon Host Task authority can keep the existing lifecycle unchanged.
"""

from .contracts import TaskContract, ToolGrant
from .domain_tools import (
    DomainToolBridge,
    DomainToolCatalog,
    DomainToolLoopPlan,
    DomainToolLoopRunner,
)
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
    "DomainToolBridge",
    "DomainToolCatalog",
    "DomainToolLoopPlan",
    "DomainToolLoopRunner",
    "HarnessCancellationResult",
    "HarnessExecutionResult",
    "HarnessRunner",
    "HarnessRunPlan",
    "HarnessStatus",
    "RunHandle",
    "TaskContract",
    "ToolGrant",
]

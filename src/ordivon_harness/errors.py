from __future__ import annotations


class HarnessLifecycleError(RuntimeError):
    """Base error for Harness-owned lifecycle admission and recovery failures."""


class HarnessSuperseded(HarnessLifecycleError):
    """The caller binding, Run, Provider Call, or Tool Step is no longer current."""

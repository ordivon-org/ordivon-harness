from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..protocol import HarnessProviderCallFailureReceipt
from .control import ExecutionControl
from .model import AgentTurnAdapter, AgentTurnAdapterError, AgentTurnRequest, AgentTurnResult


def _is_sha256_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


class ProviderLifecycleError(RuntimeError):
    """Local Provider lifecycle composition or identity is invalid."""


@dataclass(slots=True)
class ProviderCallLifecycle:
    """Internal port over optional durable Provider continuity capabilities.

    This layer owns no retry policy, Run stop semantics, token accounting, or
    Provider result interpretation. It only normalizes how the Loop addresses
    Provider continuity hooks exposed by its execution bridge.
    """

    bridge: object
    adapter: AgentTurnAdapter
    _begin: Callable[..., Any] | None = field(init=False, default=None, repr=False)
    _admit: Callable[..., Any] | None = field(init=False, default=None, repr=False)
    _complete: Callable[..., Any] | None = field(init=False, default=None, repr=False)
    _fail: Callable[..., Any] | None = field(init=False, default=None, repr=False)
    _retry: Callable[..., Any] | None = field(init=False, default=None, repr=False)
    durable: bool = field(init=False, default=False)
    records_failures: bool = field(init=False, default=False)
    records_completions: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        configure = getattr(self.bridge, "configure_provider_call", None)
        if callable(configure):
            configure(
                adapter_id=self.adapter.adapter_id,
                requested_model_id=self.adapter.model_id,
            )

        begin = getattr(self.bridge, "begin_provider_call", None)
        self._begin = begin if callable(begin) else None
        admit = getattr(self.bridge, "admit_provider_call", None)
        self._admit = admit if callable(admit) else None
        complete = getattr(self.bridge, "complete_provider_call", None)
        self._complete = complete if callable(complete) else None
        fail = getattr(self.bridge, "fail_provider_call", None)
        self._fail = fail if callable(fail) else None
        self.records_failures = self._fail is not None
        self.records_completions = self._complete is not None
        retry = getattr(self.bridge, "retry_provider_call", None)
        self._retry = retry if callable(retry) else None
        self.durable = self._begin is not None and bool(
            getattr(self.bridge, "durable_provider_calls_enabled", True)
        )

    def request_digest(self, request: AgentTurnRequest) -> str | None:
        if not self.durable:
            return None
        identity = getattr(self.adapter, "provider_request_digest", None)
        if not callable(identity):
            raise ProviderLifecycleError(
                "durable Provider Call Adapter omitted provider_request_digest"
            )
        try:
            digest = identity(request)
        except Exception as error:  # noqa: BLE001 - Adapter identity is a local boundary.
            raise ProviderLifecycleError(
                "Provider request identity failed before dispatch: "
                f"{type(error).__name__}: {error}"
            ) from error
        if not _is_sha256_digest(digest):
            raise ProviderLifecycleError(
                "Provider request identity must be sha256:<64 lowercase hex>"
            )
        return digest

    def begin(
        self,
        request: AgentTurnRequest,
        *,
        provider_request_digest: str | None,
    ) -> AgentTurnResult | HarnessProviderCallFailureReceipt | None:
        if self._begin is None:
            return None
        if self.durable:
            return self._begin(
                request, provider_request_digest=provider_request_digest
            )
        return self._begin(request)

    def admit(self, request: AgentTurnRequest, *, control: ExecutionControl) -> bool:
        if not self.durable:
            return True
        if self._admit is None:
            raise ProviderLifecycleError(
                "durable Provider Call bridge omitted dispatch admission"
            )
        try:
            return bool(self._admit(request, control=control))
        except Exception as error:  # noqa: BLE001 - local durable admission boundary.
            raise ProviderLifecycleError(
                "Provider dispatch admission failed: "
                f"{type(error).__name__}: {error}"
            ) from error

    def fail(
        self,
        request: AgentTurnRequest,
        error: AgentTurnAdapterError,
        *,
        unknown: bool,
    ) -> None:
        if self._fail is not None:
            self._fail(request, error, unknown=unknown)

    def retry(self, request: AgentTurnRequest) -> None:
        if self._retry is not None:
            self._retry(request)

    def complete(self, request: AgentTurnRequest, result: AgentTurnResult) -> None:
        if self._complete is not None:
            self._complete(request, result)


__all__ = ["ProviderCallLifecycle", "ProviderLifecycleError"]

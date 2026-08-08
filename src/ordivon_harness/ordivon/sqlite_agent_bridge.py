from __future__ import annotations

from typing import Protocol

from anc_canonical import JsonValue, canonical_digest

from ..core_contracts import HarnessRunContract
from ..protocol import (
    HarnessProviderCallFailureReceipt,
    HarnessProviderCallStatus,
    HarnessRunPauseReason,
)
from ..run_state import HarnessRunState
from ..store import new_execution_owner_id
from .control import ExecutionControl
from .model import (
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnAdapterError,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
    AgentTurnRequest,
    AgentTurnResult,
)
from .run_store_port import (
    HarnessProviderCallRecoveryRequired,
    HarnessProviderCallSourceRef,
    HarnessRunContinuityStore,
    StoredHarnessProviderCall,
    StoredHarnessRunSnapshot,
)
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind

_MAX_PROVIDER_CLAIM_TTL_MS = 15_000

NO_TOOL_AGENT_SURFACE: dict[str, JsonValue] = {
    "schemaVersion": 1,
    "kind": "ordivon.no-tool-agent-surface",
    "tools": [],
}
NO_TOOL_AGENT_SURFACE_DIGEST = canonical_digest(NO_TOOL_AGENT_SURFACE)
NO_TOOL_AGENT_GRANT: dict[str, JsonValue] = {
    "schemaVersion": 1,
    "kind": "ordivon.no-tool-grant",
    "tools": [],
}
NO_TOOL_AGENT_GRANT_DIGEST = canonical_digest(NO_TOOL_AGENT_GRANT)


class _ToolObservationView(Protocol):
    def to_dict(self) -> dict[str, JsonValue]: ...


class SQLiteHarnessAgentBridge:
    """Caller-neutral Agent Loop bridge for an independent no-Tool Run.

    It delegates durable Provider and Snapshot semantics to
    ``HarnessRunContinuityStore``. It deliberately exposes no Runtime Tool and
    no Host Assignment compatibility object.
    """

    durable_provider_calls_enabled = True

    def __init__(
        self,
        contract: HarnessRunContract,
        run_store: HarnessRunContinuityStore,
        *,
        provider_source: HarnessProviderCallSourceRef | None = None,
        provider_holder_id: str | None = None,
        expected_tool_catalog_digest: str = NO_TOOL_AGENT_SURFACE_DIGEST,
        expected_tool_grant_digest: str = NO_TOOL_AGENT_GRANT_DIGEST,
    ) -> None:
        if contract.harness_run_id != run_store.harness_run_id:
            raise ValueError("Harness Run Contract differs from its continuity Store")
        if run_store.binding.harness_run_id != contract.harness_run_id:
            raise ValueError("Harness Run binding differs from its Contract")
        if contract.tool_catalog_digest != expected_tool_catalog_digest:
            raise ValueError(
                "SQLiteHarnessAgentBridge no-Tool or expected Tool surface differs"
            )
        if contract.tool_grant_digest != expected_tool_grant_digest:
            raise ValueError(
                "SQLiteHarnessAgentBridge no-Tool or expected Tool Grant differs"
            )
        self.contract = contract
        self.run_store = run_store
        self.catalog_digest = contract.tool_catalog_digest
        self._provider_source = provider_source or run_store.assignment_provider_source()
        self._provider_holder_id = provider_holder_id or new_execution_owner_id(
            "agent-bridge"
        )
        self._provider_adapter_id: str | None = None
        self._provider_requested_model_id: str | None = None
        self._active_provider_call: StoredHarnessProviderCall | None = None

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        return ()

    def execute(self, call: AgentToolCall, *, step_id: str) -> None:
        raise ToolBridgeError(
            f"independent no-Tool Agent surface rejected {call.name} at {step_id}",
            kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
        )

    def bind_run_state(
        self,
        *,
        messages: tuple[dict[str, JsonValue], ...],
        observations: tuple[_ToolObservationView, ...],
        remaining_budget: dict[str, JsonValue],
        requested_model_id: str,
        effective_model_id: str | None,
        active_elapsed_ms: int | None = None,
        seen_model_call_ids: tuple[str, ...] = (),
        seen_tool_call_ids: tuple[str, ...] = (),
        provider_usage: tuple[dict[str, JsonValue], ...] = (),
        effective_model_ids: tuple[str, ...] = (),
    ) -> None:
        if observations or seen_tool_call_ids:
            raise ToolBridgeError(
                "no-Tool Agent Run cannot bind Tool observations or Tool Call identities",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        self.run_store.bind_state(
            HarnessRunState(
                messages=messages,
                observations=(),
                remaining_budget=remaining_budget,
                requested_model_id=requested_model_id,
                effective_model_id=effective_model_id,
                active_elapsed_ms=active_elapsed_ms,
                seen_model_call_ids=seen_model_call_ids,
                seen_tool_call_ids=(),
                provider_usage=provider_usage,
                effective_model_ids=effective_model_ids,
            )
        )

    def configure_provider_call(
        self,
        *,
        adapter_id: str,
        requested_model_id: str,
    ) -> None:
        if (
            not adapter_id
            or adapter_id != adapter_id.strip()
            or not requested_model_id
            or requested_model_id != requested_model_id.strip()
        ):
            raise ValueError("Provider Call identities must be non-empty and trimmed")
        if requested_model_id != self.contract.requested_model_id:
            raise ValueError("Provider model differs from the Harness Run Contract")
        if adapter_id != self.contract.adapter_id:
            raise ValueError("Provider Adapter differs from the Harness Run Contract")
        self._provider_adapter_id = adapter_id
        self._provider_requested_model_id = requested_model_id

    def restore_provider_replay_state(
        self,
        *,
        snapshot: StoredHarnessRunSnapshot,
        additional_messages: tuple[dict[str, JsonValue], ...],
    ) -> HarnessRunState | None:
        adapter_id, requested_model_id = self._require_provider_configuration()
        return self.run_store.load_provider_replay_state(
            source=self._provider_source,
            snapshot=snapshot,
            additional_messages=additional_messages,
            adapter_id=adapter_id,
            requested_model_id=requested_model_id,
        )

    def begin_provider_call(
        self,
        request: AgentTurnRequest,
        *,
        provider_request_digest: str | None = None,
    ) -> AgentTurnResult | HarnessProviderCallFailureReceipt | None:
        if provider_request_digest is None:
            raise ToolBridgeError(
                "durable Provider Call requires an exact Provider request digest",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        adapter_id, requested_model_id = self._require_provider_configuration()
        retained = self.run_store.claim_provider_call(
            source=self._provider_source,
            turn_id=request.turn_id,
            turn_sequence=request.sequence,
            request_digest=request.dispatch_digest,
            provider_request_digest=provider_request_digest,
            adapter_id=adapter_id,
            requested_model_id=requested_model_id,
            holder_id=self._provider_holder_id,
            ttl_ms=self._provider_claim_ttl_ms(request),
            request=(request if self.contract.privacy.allow_model_content else None),
        )
        self._active_provider_call = retained
        if retained.result is not None:
            return retained.result
        if retained.failure is not None:
            return retained.failure
        return None

    def admit_provider_call(
        self,
        request: AgentTurnRequest,
        *,
        control: ExecutionControl,
    ) -> bool:
        retained = self._require_active_provider_call(request)
        if control.stop_requested:
            self._record_pre_dispatch_stop(request, retained)
            return False
        retained = self.run_store.mark_provider_call_dispatching(retained)
        self._active_provider_call = retained
        if control.stop_requested:
            self._record_pre_dispatch_stop(request, retained)
            return False
        return True

    def complete_provider_call(
        self,
        request: AgentTurnRequest,
        result: AgentTurnResult,
    ) -> None:
        retained = self._require_active_provider_call(request)
        self._active_provider_call = self.run_store.complete_provider_call(
            retained,
            result,
        )
        if self.run_store.provider_outcome_requires_resume:
            raise HarnessProviderCallRecoveryRequired(
                "Provider outcome was admitted after Recovery; explicit resume is required"
            )

    def fail_provider_call(
        self,
        request: AgentTurnRequest,
        error: AgentTurnAdapterError,
        *,
        unknown: bool,
    ) -> None:
        retained = self._require_active_provider_call(request)
        expected_unknown = error.dispatch_safety is AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS
        if unknown != expected_unknown:
            raise ToolBridgeError(
                "Provider failure status differs from its dispatch safety",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        failure = HarnessProviderCallFailureReceipt(
            provider_call_id=retained.record.provider_call_id,
            request_digest=request.dispatch_digest,
            provider_request_digest=retained.record.provider_request_digest,
            failure_code=error.failure_code.value,
            dispatch_safety=error.dispatch_safety.value,
            detail=str(error)[:2_048],
        )
        self._active_provider_call = self.run_store.fail_provider_call(
            retained,
            failure=failure,
        )
        if self.run_store.provider_outcome_requires_resume:
            raise HarnessProviderCallRecoveryRequired(
                "Provider outcome was admitted after Recovery; explicit resume is required"
            )

    def retry_provider_call(self, request: AgentTurnRequest) -> None:
        retained = self._require_active_provider_call(request)
        self._active_provider_call = self.run_store.retry_failed_provider_call(
            retained,
            holder_id=self._provider_holder_id,
            ttl_ms=self._provider_claim_ttl_ms(request),
        )

    def record_pause(self, reason: str) -> None:
        try:
            pause_reason = {
                "needs_input": HarnessRunPauseReason.NEEDS_INPUT,
            }[reason]
        except KeyError as error:
            raise ToolBridgeError(
                f"unsupported Harness pause reason: {reason}",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            ) from error
        self.run_store.record_pause(pause_reason)
        self._active_provider_call = None

    def _record_pre_dispatch_stop(
        self,
        request: AgentTurnRequest,
        retained: StoredHarnessProviderCall,
    ) -> None:
        failure = HarnessProviderCallFailureReceipt(
            provider_call_id=retained.record.provider_call_id,
            request_digest=request.dispatch_digest,
            provider_request_digest=retained.record.provider_request_digest,
            failure_code=AgentTurnFailureCode.TIMEOUT.value,
            dispatch_safety=AgentTurnDispatchSafety.PRE_DISPATCH_SAFE.value,
            detail="Provider dispatch admission closed before physical invocation",
        )
        if retained.record.status is HarnessProviderCallStatus.CLAIMED:
            retained = self.run_store.fail_claimed_provider_call(
                retained,
                failure=failure,
            )
        elif retained.record.status is HarnessProviderCallStatus.DISPATCHING:
            retained = self.run_store.fail_provider_call(
                retained,
                failure=failure,
            )
        else:
            raise ToolBridgeError(
                "Provider dispatch admission stopped from an invalid state",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        self._active_provider_call = retained

    def _require_provider_configuration(self) -> tuple[str, str]:
        if self._provider_adapter_id is None or self._provider_requested_model_id is None:
            raise ToolBridgeError(
                "durable Provider Call was not configured with Adapter identities",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return self._provider_adapter_id, self._provider_requested_model_id

    def _require_active_provider_call(
        self,
        request: AgentTurnRequest,
    ) -> StoredHarnessProviderCall:
        retained = self._active_provider_call
        if retained is None or retained.record.request_digest != request.dispatch_digest:
            raise ToolBridgeError(
                "Provider Call state differs from the current Agent Turn",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return retained

    @staticmethod
    def _provider_claim_ttl_ms(request: AgentTurnRequest) -> int:
        remaining = request.remaining_budget.get("wallTimeMs")
        if type(remaining) is not int or remaining < 0:
            raise ToolBridgeError(
                "Agent Turn omitted a valid remaining wall-time budget",
                kind=ToolBridgeErrorKind.PROTOCOL_INVALID,
            )
        return max(1_000, min(_MAX_PROVIDER_CLAIM_TTL_MS, remaining + 1_000))

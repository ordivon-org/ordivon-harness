from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from anc_canonical import canonical_digest

from .core_contracts import HarnessRunContract
from .ordivon.control import CancellationToken, ExecutionControl, RunDeadline
from .ordivon.loop import RunBudget
from .ordivon.model import AgentTurnAdapter, AgentTurnRequest, AgentTurnResult
from .ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    SQLiteHarnessAgentBridge,
)
from .ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from .protocol import HarnessProviderCallFailureReceipt
from .run_state import HarnessRunState
from .sqlite_store import SQLiteHarnessStore
from .working_view import (
    HarnessWorkingSetSpec,
    HarnessWorkingView,
    compile_working_view,
)


@dataclass(frozen=True, slots=True)
class WorkingViewNoToolTurnExecution:
    working_set: HarnessWorkingSetSpec
    working_view: HarnessWorkingView
    request: AgentTurnRequest
    result: AgentTurnResult
    replayed_provider_result: bool


class WorkingViewNoToolTurnRunner:
    """P-C1.1 one-turn proof of History / Working View separation.

    The runner deliberately does not implement Context discovery, Tool use,
    multi-turn reasoning, retries, terminal Run recording, or domain admission.
    It proves one narrower property: model-visible messages may be projected from
    an Agent-owned Working Set while durable Run execution state keeps no copy of
    that transcript. Once a Provider Call is claimed, the exact AgentTurnRequest
    is frozen independently as Provider execution evidence.
    """

    def __init__(
        self,
        store: SQLiteHarnessStore,
        contract: HarnessRunContract,
        continuity: SQLiteHarnessRunContinuityStore,
        adapter: AgentTurnAdapter,
        *,
        budget: RunBudget,
        clock_ms: Callable[[], int],
        monotonic_ms: Callable[[], int] | None = None,
    ) -> None:
        if continuity.store is not store:
            raise ValueError("Working View runner Store differs from continuity Store")
        if continuity.harness_run_id != contract.harness_run_id:
            raise ValueError("Working View runner continuity belongs to another Run")
        if contract.tool_catalog_digest != NO_TOOL_AGENT_SURFACE_DIGEST:
            raise ValueError("Working View prototype requires the no-Tool surface")
        if contract.tool_grant_digest != NO_TOOL_AGENT_GRANT_DIGEST:
            raise ValueError("Working View prototype requires the no-Tool Grant")
        if not contract.privacy.allow_model_content:
            raise ValueError(
                "Working View prototype requires Contract permission to persist model content"
            )
        if adapter.adapter_id != contract.adapter_id or adapter.model_id != contract.requested_model_id:
            raise ValueError("Working View runner Provider differs from its Contract")
        budget.require_contract_match(contract.budget)
        self.store = store
        self.contract = contract
        self.continuity = continuity
        self.adapter = adapter
        self.budget = budget
        self.clock_ms = clock_ms
        self.monotonic_ms = monotonic_ms or clock_ms

    def _turn_sequence(self) -> int:
        try:
            current = self.continuity.load_current_provider_call()
        except KeyError:
            current = None
        if current is not None:
            return current.record.turn_sequence
        maximum = 0
        for event in self.store.list_run_events(self.contract.harness_run_id):
            object_digest = event.data.get("providerCallRecordObjectDigest")
            if not isinstance(object_digest, str):
                continue
            raw = self.store.get_object(
                object_digest, expected_kind="harness-provider-call-record"
            )
            if not isinstance(raw, dict):
                raise TypeError("historical Provider Call record is invalid")
            sequence = raw.get("turnSequence")
            if type(sequence) is not int or sequence < 1:
                raise ValueError("historical Provider Call turn sequence is invalid")
            maximum = max(maximum, sequence)
        return maximum + 1

    def run(self, working_set: HarnessWorkingSetSpec) -> WorkingViewNoToolTurnExecution:
        if not working_set.committed:
            raise ValueError("Working View Provider turn requires an Agent-committed Working Set")
        self.continuity.record_working_set(working_set)
        retained_spec = self.continuity.load_current_working_set()
        if retained_spec != working_set:
            raise ValueError("Working View runner did not retain the exact Working Set")
        view = compile_working_view(retained_spec, self.store)
        remaining = self.budget.remaining(
            model_calls=0,
            tool_calls=0,
            observation_bytes=0,
            elapsed_ms=0,
            total_tokens=0,
            model_retries=0,
            tool_corrections=0,
            observation_only_turns=0,
            no_progress_turns=0,
        )
        sequence = self._turn_sequence()
        token = canonical_digest(
            {
                "harnessRunId": self.contract.harness_run_id,
                "workingSetDigest": retained_spec.digest,
                "workingViewDigest": view.digest,
                "turnSequence": sequence,
            }
        )[7:31]
        request = AgentTurnRequest(
            harness_run_id=self.contract.harness_run_id,
            turn_id=f"turn:working-view:{token}",
            sequence=sequence,
            assignment_id=self.continuity.binding.assignment_id,
            context_digest=view.digest,
            tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
            messages=view.messages,
            tools=(),
            remaining_budget=remaining,
        )
        # Execution continuity intentionally excludes model-visible transcript.
        state = HarnessRunState(
            messages=(),
            observations=(),
            remaining_budget=remaining,
            requested_model_id=self.adapter.model_id,
            effective_model_id=None,
            active_elapsed_ms=0,
        )
        self.continuity.bind_state(state)
        bridge = SQLiteHarnessAgentBridge(self.contract, self.continuity)
        bridge.configure_provider_call(
            adapter_id=self.adapter.adapter_id,
            requested_model_id=self.adapter.model_id,
        )
        provider_request_digest = getattr(self.adapter, "provider_request_digest", None)
        if not callable(provider_request_digest):
            raise TypeError("durable Working View Provider requires provider_request_digest")
        exact_provider_digest = provider_request_digest(request)
        provider_outcome = bridge.begin_provider_call(
            request,
            provider_request_digest=exact_provider_digest,
        )
        if isinstance(provider_outcome, HarnessProviderCallFailureReceipt):
            raise RuntimeError(
                "Working View prototype encountered a retained Provider failure; "
                "retry policy belongs to a later multi-turn slice"
            )
        if provider_outcome is not None:
            return WorkingViewNoToolTurnExecution(
                working_set=retained_spec,
                working_view=view,
                request=request,
                result=provider_outcome,
                replayed_provider_result=True,
            )
        control = ExecutionControl(
            CancellationToken(monotonic_ms=self.monotonic_ms),
            RunDeadline.after(
                self.budget.max_wall_time_ms,
                monotonic_ms=self.monotonic_ms,
            ),
        )
        if not bridge.admit_provider_call(request, control=control):
            raise RuntimeError("Working View Provider dispatch was not admitted")
        controlled_invoke = getattr(self.adapter, "invoke_with_control", None)
        result = (
            controlled_invoke(request, control)
            if callable(controlled_invoke)
            else self.adapter.invoke(request)
        )
        # The exact request is already durable; completion changes Provider outcome only.
        bridge.complete_provider_call(request, result)
        return WorkingViewNoToolTurnExecution(
            working_set=retained_spec,
            working_view=view,
            request=request,
            result=result,
            replayed_provider_result=False,
        )


__all__ = [
    "WorkingViewNoToolTurnExecution",
    "WorkingViewNoToolTurnRunner",
]

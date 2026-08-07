from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Callable, Protocol

from anc_canonical import JsonValue

from .core_contracts import HarnessRunContract
from .independent_result import (
    IndependentRunRecorder,
    StoredIndependentRunResult,
)
from .ordivon.loop import (
    AgentLoopResult,
    CancellationToken,
    OrdivonAgentLoop,
    RunBudget,
)
from .ordivon.model import AgentTurnAdapter
from .ordivon.run_store_port import HarnessRunContinuityStore
from .store import HarnessRunStatus


class StandaloneToolBridge(Protocol):
    catalog_digest: str


@dataclass(frozen=True, slots=True)
class StandaloneHarnessExecution:
    loop_result: AgentLoopResult
    terminal_result: StoredIndependentRunResult | None

    @property
    def paused(self) -> bool:
        return self.terminal_result is None


class StandaloneHarnessRunner:
    """Explicit Host-free Runner over one independent Harness Run authority.

    The caller constructs the Provider adapter and Tool bridge. The Runner owns
    only the bounded Agent Loop and admission of Harness-native Trace, Receipt,
    Recovery and CompletionProposal evidence. It does not verify or accept the
    caller's task or domain outcome.
    """

    def __init__(
        self,
        contract: HarnessRunContract,
        continuity: HarnessRunContinuityStore,
        adapter: AgentTurnAdapter,
        tool_bridge: StandaloneToolBridge,
        *,
        budget: RunBudget,
        clock_ms: Callable[[], int],
        monotonic_ms: Callable[[], int] | None = None,
    ) -> None:
        if continuity.harness_run_id != contract.harness_run_id:
            raise ValueError("Standalone Runner continuity belongs to another Run")
        if continuity.binding.harness_run_id != contract.harness_run_id:
            raise ValueError("Standalone Runner binding belongs to another Run")
        if adapter.adapter_id != contract.adapter_id:
            raise ValueError("Standalone Runner Adapter differs from its Contract")
        if adapter.model_id != contract.requested_model_id:
            raise ValueError("Standalone Runner requested model differs from its Contract")
        if tool_bridge.catalog_digest != contract.tool_catalog_digest:
            raise ValueError("Standalone Runner Tool catalog differs from its Contract")
        self._validate_budget(contract.budget, budget)
        store = getattr(continuity, "store", None)
        if store is None:
            raise TypeError("Standalone Runner requires an independent continuity Store")
        self.contract = contract
        self.continuity = continuity
        self.adapter = adapter
        self.tool_bridge = tool_bridge
        self.budget = budget
        self.clock_ms = clock_ms
        self.monotonic_ms = monotonic_ms or clock_ms
        self.recorder = IndependentRunRecorder(
            store,
            contract,
            continuity.binding,
            clock_ms=clock_ms,
        )

    def run(
        self,
        initial_messages: tuple[dict[str, JsonValue], ...],
        *,
        cancellation: CancellationToken | None = None,
    ) -> StandaloneHarnessExecution:
        projection = self.recorder.store.load_run(self.contract.harness_run_id)
        if projection.status.terminal:
            raise RuntimeError("Standalone Harness Run is already terminal")
        if projection.status is HarnessRunStatus.PAUSED:
            raise RuntimeError("paused Standalone Harness Run requires resume")
        loop = self._loop()
        result = loop.run(
            harness_run_id=self.contract.harness_run_id,
            assignment_id=self.continuity.binding.assignment_id,
            context_digest=self.contract.context_refs[0].digest,
            initial_messages=initial_messages,
            cancellation=cancellation,
        )
        terminal = self.recorder.record_result(
            result,
            started_at_ms=self.contract.created_at_ms,
            finished_at_ms=result.trace.events[-1].occurred_at_ms,
        )
        return StandaloneHarnessExecution(result, terminal)

    def resume(
        self,
        *,
        additional_messages: tuple[dict[str, JsonValue], ...] = (),
        cancellation: CancellationToken | None = None,
    ) -> StandaloneHarnessExecution:
        projection = self.recorder.store.load_run(self.contract.harness_run_id)
        if projection.status.terminal:
            raise RuntimeError("Standalone Harness Run is already terminal")
        retained = self.continuity.load_current_snapshot()
        result = self._loop().resume(
            retained=retained,
            assignment_id=self.continuity.binding.assignment_id,
            context_digest=self.contract.context_refs[0].digest,
            additional_messages=additional_messages,
            cancellation=cancellation,
        )
        terminal = self.recorder.record_result(
            result,
            started_at_ms=self.contract.created_at_ms,
            finished_at_ms=result.trace.events[-1].occurred_at_ms,
        )
        return StandaloneHarnessExecution(result, terminal)

    def inspect_terminal(self) -> StoredIndependentRunResult:
        return self.recorder.load_terminal_result()

    def doctor(self) -> dict[str, JsonValue]:
        continuity_doctor = getattr(self.continuity, "doctor", None)
        if not callable(continuity_doctor):
            raise TypeError("Standalone continuity Store has no Doctor")
        return {
            "schemaVersion": 1,
            "kind": "ordivon.standalone-harness-doctor",
            "healthy": True,
            "harnessRunId": self.contract.harness_run_id,
            "continuity": continuity_doctor(),
            "result": self.recorder.doctor(),
        }

    def _loop(self) -> OrdivonAgentLoop:
        return OrdivonAgentLoop(
            self.adapter,
            self.tool_bridge,
            budget=self.budget,
            clock_ms=self.clock_ms,
            monotonic_ms=self.monotonic_ms,
            assignment_deadline_ms=self.contract.deadline_ms,
        )

    @staticmethod
    def _validate_budget(contract: Mapping[str, JsonValue], budget: RunBudget) -> None:
        budget.require_contract_match(contract)


__all__ = [
    "StandaloneHarnessExecution",
    "StandaloneHarnessRunner",
    "StandaloneToolBridge",
]

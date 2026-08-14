from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Callable, Protocol

from anc_canonical import JsonValue

from .completion import structured_completion_contract_digest
from .core_contracts import HarnessRunContract
from .independent_result import (
    IndependentRunRecorder,
    StoredIndependentRunResult,
)
from .loop_driver import HarnessLoopDriverBinding
from .ordivon.loop import (
    AgentLoopResult,
    CancellationToken,
    OrdivonAgentLoop,
    RunBudget,
)
from .ordivon.model import AgentTurnAdapter
from .ordivon.run_store_port import HarnessRunContinuityStore
from .store import HarnessRunStatus
from .working_view import (
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
)


class StandaloneToolBridge(Protocol):
    catalog_digest: str


@dataclass(frozen=True, slots=True)
class HarnessCognitionProfile:
    """Explicit cognition surfaces composed into one Harness Agent Run.

    This profile selects structural Harness mechanisms only. It does not choose
    sources, rank relevance, summarize content, or author Agent semantic policy.
    """

    working_set_transitions: bool = True
    caller_ingress_promotions: bool = True
    working_set_history: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("working_set_transitions", self.working_set_transitions),
            ("caller_ingress_promotions", self.caller_ingress_promotions),
            ("working_set_history", self.working_set_history),
        ):
            if type(value) is not bool:
                raise ValueError(f"Harness cognition {name} must be boolean")

    @classmethod
    def full(cls) -> "HarnessCognitionProfile":
        return cls(
            working_set_transitions=True,
            caller_ingress_promotions=True,
            working_set_history=True,
        )


@dataclass(frozen=True, slots=True)
class HarnessCognitionSeedSource:
    """One caller-selected exact source and the slot it should initially occupy."""

    slot: str
    source: HarnessWorkingViewSource

    def __post_init__(self) -> None:
        if not isinstance(self.source, HarnessWorkingViewSource):
            raise ValueError(
                "Harness cognition seed source must be a HarnessCognitionSource-compatible value"
            )
        if (
            not isinstance(self.slot, str)
            or not self.slot
            or self.slot != self.slot.strip()
            or len(self.slot.encode("utf-8")) > 160
        ):
            raise ValueError("Harness cognition seed slot must be non-empty and trimmed")


@dataclass(frozen=True, slots=True)
class HarnessCognitionSeed:
    """Exact caller-authored bootstrap for the first committed WorkingSet.

    Seed material is not discovered or ranked by Harness. The Agent Run only
    materializes the supplied exact sources, derives exact pins, and commits the
    initial selection through the existing Continuity authority.
    """

    attempt_id: str
    sources: tuple[HarnessCognitionSeedSource, ...]
    basis: str

    def __post_init__(self) -> None:
        for label, value, limit in (
            ("attempt identity", self.attempt_id, 500),
            ("basis", self.basis, 2_048),
        ):
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or len(value.encode("utf-8")) > limit
            ):
                raise ValueError(f"Harness cognition seed {label} is invalid")
        if not self.sources:
            raise ValueError("Harness cognition seed requires at least one source")
        slots = [item.slot for item in self.sources]
        if len(slots) != len(set(slots)):
            raise ValueError("Harness cognition seed slots must be unique")


@dataclass(frozen=True, slots=True)
class HarnessAgentExecution:
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
        cognition_profile: HarnessCognitionProfile | None = None,
        loop_driver_binding: HarnessLoopDriverBinding | None = None,
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
        expected_completion_digest = structured_completion_contract_digest(
            contract.completion_contract
        )
        if (
            expected_completion_digest is not None
            and getattr(adapter, "structured_completion_contract_digest", None)
            != expected_completion_digest
        ):
            raise ValueError("Standalone Runner structured completion differs from its Contract")
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
        self.store = store
        self.cognition_profile = cognition_profile
        self.loop_driver_binding = loop_driver_binding
        if loop_driver_binding is not None:
            loop_driver_binding.require_contract(contract.system_manifest_ref.digest)
        self._validate_cognition_composition()
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
        cognition_seed: HarnessCognitionSeed | None = None,
    ) -> HarnessAgentExecution:
        projection = self.recorder.store.load_run(self.contract.harness_run_id)
        if projection.status.terminal:
            raise RuntimeError("Standalone Harness Run is already terminal")
        if projection.status is HarnessRunStatus.PAUSED:
            raise RuntimeError("paused Standalone Harness Run requires resume")
        self._ensure_cognition_ready(cognition_seed)
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
        return HarnessAgentExecution(result, terminal)

    def resume(
        self,
        *,
        additional_messages: tuple[dict[str, JsonValue], ...] = (),
        cancellation: CancellationToken | None = None,
    ) -> HarnessAgentExecution:
        projection = self.recorder.store.load_run(self.contract.harness_run_id)
        if projection.status.terminal:
            raise RuntimeError("Standalone Harness Run is already terminal")
        self._ensure_cognition_ready(None)
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
        return HarnessAgentExecution(result, terminal)

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
        profile = self.cognition_profile
        kwargs: dict[str, object] = {
            "budget": self.budget,
            "clock_ms": self.clock_ms,
            "monotonic_ms": self.monotonic_ms,
            "assignment_deadline_ms": self.contract.deadline_ms,
        }
        if profile is not None:
            projector = WorkingSetViewProjector(self.store, self.continuity)
            kwargs.update(
                {
                    "working_view_projector": projector,
                    "working_set_transition_handler": (
                        self.continuity if profile.working_set_transitions else None
                    ),
                    "caller_ingress_promotion_handler": (
                        self.continuity if profile.caller_ingress_promotions else None
                    ),
                    "working_set_history_reader": (
                        self.continuity if profile.working_set_history else None
                    ),
                }
            )
        binding = self.loop_driver_binding
        if binding is not None:
            return binding.build(
                adapter=self.adapter,
                tool_bridge=self.tool_bridge,
                **kwargs,
            )
        return OrdivonAgentLoop(
            self.adapter,
            self.tool_bridge,
            **kwargs,
        )

    def _validate_cognition_composition(self) -> None:
        profile = self.cognition_profile
        if profile is None:
            return
        if not self.contract.privacy.allow_model_content:
            raise ValueError(
                "Standalone cognition requires Contract permission to retain model content"
            )
        if profile.working_set_history and not self.contract.privacy.allow_tool_content:
            raise ValueError(
                "Standalone cognition history requires Tool-content authority for its Provider-faithful result channel"
            )
        required = {
            "store_working_view_source",
            "record_working_set",
            "load_current_working_set",
        }
        if profile.working_set_transitions:
            required.add("apply_working_set_transition")
        if profile.caller_ingress_promotions:
            required.update({"apply_caller_ingress_promotion", "project_current_caller_ingress"})
        if profile.working_set_history:
            required.add("inspect_working_set_history")
        missing = sorted(
            name for name in required if not callable(getattr(self.continuity, name, None))
        )
        if missing:
            raise TypeError(
                "Standalone cognition Continuity lacks required mechanisms: " + ", ".join(missing)
            )

    def _ensure_cognition_ready(
        self, seed: HarnessCognitionSeed | None
    ) -> HarnessWorkingSetSpec | None:
        profile = self.cognition_profile
        if profile is None:
            if seed is not None:
                raise ValueError("Standalone cognition seed requires an enabled cognition profile")
            return None

        loader = getattr(self.continuity, "load_current_working_set")
        try:
            current = loader()
        except KeyError:
            current = None

        if seed is None:
            if current is None:
                raise ValueError(
                    "cognition-enabled Standalone Run requires an exact initial cognition seed"
                )
            if not current.committed:
                raise ValueError(
                    "cognition-enabled Standalone Run requires a committed current WorkingSet"
                )
            return current

        storer = getattr(self.continuity, "store_working_view_source")
        pins: list[HarnessWorkingSetPin] = []
        for item in seed.sources:
            stored = storer(item.source)
            pins.append(
                HarnessWorkingSetPin(
                    slot=item.slot,
                    logical_ref=item.source.logical_ref,
                    logical_generation=item.source.logical_generation,
                    resolved_digest=stored.digest,
                )
            )
        initial = HarnessWorkingSetSpec.initial(
            seed.attempt_id,
            pins=tuple(sorted(pins, key=lambda pin: pin.slot)),
        )
        committed = initial.commit(seed.basis)
        recorder = getattr(self.continuity, "record_working_set")
        if current is not None:
            if current == committed:
                return current
            if current == initial:
                recorder(committed)
                return committed
            raise ValueError(
                "Standalone cognition seed differs from the already-current WorkingSet"
            )
        recorder(initial)
        recorder(committed)
        return committed

    @staticmethod
    def _validate_budget(contract: Mapping[str, JsonValue], budget: RunBudget) -> None:
        budget.require_contract_match(contract)


# R0-R2 experimental names remain import-compatible while R3 promotes caller-facing names.
StandaloneCognitionProfile = HarnessCognitionProfile
StandaloneCognitionSeedSource = HarnessCognitionSeedSource
StandaloneCognitionSeed = HarnessCognitionSeed
StandaloneHarnessExecution = HarnessAgentExecution


__all__ = [
    "HarnessAgentExecution",
    "HarnessCognitionProfile",
    "HarnessCognitionSeed",
    "HarnessCognitionSeedSource",
    "StandaloneCognitionProfile",
    "StandaloneCognitionSeed",
    "StandaloneCognitionSeedSource",
    "StandaloneHarnessExecution",
    "StandaloneHarnessRunner",
    "StandaloneToolBridge",
]

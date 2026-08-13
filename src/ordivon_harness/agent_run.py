from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeAlias

from anc_canonical import JsonValue

from .capability_catalog import project_process_composition
from .completion import structured_completion_contract_digest
from .core_contracts import HarnessRunContract
from .execution_binding import HarnessExecutionBinding
from .ordivon.model import AgentTurnAdapter
from .provider_use_policy import (
    HarnessProviderUsePolicy,
    HarnessProviderUsePolicyError,
    validate_provider_use_policy,
)
from .ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    SQLiteHarnessAgentBridge,
)
from .ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from .ordivon.sqlite_runtime_bridge import (
    INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
    INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
    SQLiteHarnessRuntimeBridge,
)
from .runtime_port import HarnessRuntimeClient
from .sqlite_store import SQLiteHarnessStore
from .standalone import (
    HarnessAgentExecution,
    HarnessCognitionProfile,
    HarnessCognitionSeed,
    HarnessCognitionSeedSource,
    StandaloneHarnessRunner,
    StandaloneToolBridge,
)
from .store import HarnessRunStatus
from .working_view import HarnessWorkingViewSource
from .ordivon.loop import CancellationToken, RunBudget

HarnessCognitionSource = HarnessWorkingViewSource


HarnessAgentAdapterFactory: TypeAlias = Callable[[HarnessRunContract], AgentTurnAdapter]


class HarnessAgentRunCompositionError(ValueError):
    """The exact Run Contract cannot be composed by this supported surface."""


@dataclass(slots=True)
class HarnessAgentRun:
    """One caller-bound Agent Run over current independent Harness authority.

    This supported surface hides mechanical Store/Continuity/Bridge/Runner wiring.
    It does not author Contracts, choose Providers, infer Runtime bindings, discover
    cognition, rank sources, or admit caller/domain completion truth.
    """

    state_root: Path
    contract: HarnessRunContract
    adapter: AgentTurnAdapter
    clock_ms: Callable[[], int]
    monotonic_ms: Callable[[], int]
    cognition_profile: HarnessCognitionProfile | None = None
    execution_binding: HarnessExecutionBinding | None = None
    runtime: HarnessRuntimeClient | None = None
    provider_use_policy: HarnessProviderUsePolicy | None = None

    @classmethod
    def create(
        cls,
        state_root: str | Path,
        contract: HarnessRunContract,
        adapter_factory: HarnessAgentAdapterFactory,
        *,
        cognition_profile: HarnessCognitionProfile | None = None,
        execution_binding: HarnessExecutionBinding | None = None,
        runtime: HarnessRuntimeClient | None = None,
        provider_use_policy: HarnessProviderUsePolicy | None = None,
        clock_ms: Callable[[], int] | None = None,
        monotonic_ms: Callable[[], int] | None = None,
    ) -> HarnessAgentRun:
        cls._validate_structure(
            contract,
            cognition_profile=cognition_profile,
            execution_binding=execution_binding,
            runtime=runtime,
            provider_use_policy=provider_use_policy,
        )
        adapter = cls._resolve_adapter(contract, adapter_factory)
        root = Path(state_root).expanduser().resolve()
        with SQLiteHarnessStore.initialize(root) as store:
            try:
                projection = store.load_run(contract.harness_run_id)
            except KeyError:
                store.create_run(contract)
            else:
                if (
                    projection.contract_digest != contract.digest
                    or projection.caller_id != contract.caller_id
                    or projection.caller_run_ref != contract.caller_run_ref
                ):
                    raise HarnessAgentRunCompositionError(
                        "existing Harness Run differs from supplied Contract"
                    )
        return cls._bind(
            root,
            contract,
            adapter,
            cognition_profile=cognition_profile,
            execution_binding=execution_binding,
            runtime=runtime,
            provider_use_policy=provider_use_policy,
            clock_ms=clock_ms,
            monotonic_ms=monotonic_ms,
        )

    @classmethod
    def open(
        cls,
        state_root: str | Path,
        harness_run_id: str,
        adapter_factory: HarnessAgentAdapterFactory,
        *,
        cognition_profile: HarnessCognitionProfile | None = None,
        execution_binding: HarnessExecutionBinding | None = None,
        runtime: HarnessRuntimeClient | None = None,
        provider_use_policy: HarnessProviderUsePolicy | None = None,
        clock_ms: Callable[[], int] | None = None,
        monotonic_ms: Callable[[], int] | None = None,
    ) -> HarnessAgentRun:
        root = Path(state_root).expanduser().resolve()
        with SQLiteHarnessStore(root) as store:
            continuity = SQLiteHarnessRunContinuityStore.open(
                store, harness_run_id, clock_ms=clock_ms
            )
            contract = continuity.contract
        cls._validate_structure(
            contract,
            cognition_profile=cognition_profile,
            execution_binding=execution_binding,
            runtime=runtime,
            provider_use_policy=provider_use_policy,
        )
        adapter = cls._resolve_adapter(contract, adapter_factory)
        return cls._bind(
            root,
            contract,
            adapter,
            cognition_profile=cognition_profile,
            execution_binding=execution_binding,
            runtime=runtime,
            provider_use_policy=provider_use_policy,
            clock_ms=clock_ms,
            monotonic_ms=monotonic_ms,
        )

    @classmethod
    def _bind(
        cls,
        state_root: Path,
        contract: HarnessRunContract,
        adapter: AgentTurnAdapter,
        *,
        cognition_profile: HarnessCognitionProfile | None,
        execution_binding: HarnessExecutionBinding | None,
        runtime: HarnessRuntimeClient | None,
        provider_use_policy: HarnessProviderUsePolicy | None,
        clock_ms: Callable[[], int] | None,
        monotonic_ms: Callable[[], int] | None,
    ) -> HarnessAgentRun:
        wall_clock = clock_ms or (lambda: time.time_ns() // 1_000_000)
        mono_clock = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)
        value = cls(
            state_root=state_root,
            contract=contract,
            adapter=adapter,
            clock_ms=wall_clock,
            monotonic_ms=mono_clock,
            cognition_profile=cognition_profile,
            execution_binding=execution_binding,
            runtime=runtime,
            provider_use_policy=provider_use_policy,
        )
        return value

    @property
    def harness_run_id(self) -> str:
        return self.contract.harness_run_id

    def status(self) -> dict[str, JsonValue]:
        with SQLiteHarnessStore(self.state_root) as store:
            return store.load_run(self.harness_run_id).to_dict()

    def explain(self) -> dict[str, JsonValue]:
        """Project the validated in-process Harness composition."""
        value = project_process_composition(
            self.contract,
            adapter=self.adapter,
            cognition_profile=self.cognition_profile,
            execution_binding=self.execution_binding,
            runtime_supplied=self.runtime is not None,
            provider_use_policy=self.provider_use_policy,
        )
        value["durableRun"] = self.status()
        return value

    def run(
        self,
        initial_messages: tuple[dict[str, JsonValue], ...],
        *,
        cancellation: CancellationToken | None = None,
        cognition_seed: HarnessCognitionSeed | None = None,
    ) -> HarnessAgentExecution:
        with SQLiteHarnessStore(self.state_root) as store:
            projection = store.load_run(self.harness_run_id)
            if projection.status is HarnessRunStatus.PAUSED:
                raise RuntimeError("paused Harness Agent Run requires resume")
            return self._runner(store, provider_source=None).run(
                initial_messages,
                cancellation=cancellation,
                cognition_seed=cognition_seed,
            )

    def resume(
        self,
        *,
        additional_messages: tuple[dict[str, JsonValue], ...] = (),
        cancellation: CancellationToken | None = None,
    ) -> HarnessAgentExecution:
        with SQLiteHarnessStore(self.state_root) as store:
            continuity = self._continuity(store)
            retained = continuity.load_current_snapshot()
            provider_source = continuity.snapshot_provider_source(retained)
            return self._runner(
                store, continuity=continuity, provider_source=provider_source
            ).resume(
                additional_messages=additional_messages,
                cancellation=cancellation,
            )

    def inspect_terminal(self):
        with SQLiteHarnessStore(self.state_root) as store:
            return self._runner(store, provider_source=None).inspect_terminal()

    def doctor(self) -> dict[str, JsonValue]:
        with SQLiteHarnessStore(self.state_root) as store:
            projection = store.load_run(self.harness_run_id)
            provider_source = None
            if projection.status is HarnessRunStatus.PAUSED:
                continuity = self._continuity(store)
                retained = continuity.load_current_snapshot()
                provider_source = continuity.snapshot_provider_source(retained)
                return self._runner(
                    store, continuity=continuity, provider_source=provider_source
                ).doctor()
            return self._runner(store, provider_source=None).doctor()

    def _continuity(self, store: SQLiteHarnessStore) -> SQLiteHarnessRunContinuityStore:
        return SQLiteHarnessRunContinuityStore.open(
            store, self.harness_run_id, clock_ms=self.clock_ms
        )

    def _runner(
        self,
        store: SQLiteHarnessStore,
        *,
        continuity: SQLiteHarnessRunContinuityStore | None = None,
        provider_source=None,
    ) -> StandaloneHarnessRunner:
        active = continuity or self._continuity(store)
        bridge = self._bridge(active, provider_source=provider_source)
        return StandaloneHarnessRunner(
            self.contract,
            active,
            self.adapter,
            bridge,
            budget=RunBudget.from_contract_dict(self.contract.budget),
            clock_ms=self.clock_ms,
            monotonic_ms=self.monotonic_ms,
            cognition_profile=self.cognition_profile,
        )

    def _bridge(
        self,
        continuity: SQLiteHarnessRunContinuityStore,
        *,
        provider_source=None,
    ) -> StandaloneToolBridge:
        if self._no_tool_surface:
            return SQLiteHarnessAgentBridge(
                self.contract, continuity, provider_source=provider_source
            )
        assert self.execution_binding is not None
        assert self.runtime is not None
        return SQLiteHarnessRuntimeBridge(
            self.contract,
            continuity,
            self.execution_binding,
            self.runtime,
            provider_source=provider_source,
        )

    @property
    def _no_tool_surface(self) -> bool:
        return (
            self.contract.tool_catalog_digest == NO_TOOL_AGENT_SURFACE_DIGEST
            and self.contract.tool_grant_digest == NO_TOOL_AGENT_GRANT_DIGEST
        )

    @property
    def _runtime_search_surface(self) -> bool:
        return (
            self.contract.tool_catalog_digest == INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST
            and self.contract.tool_grant_digest == INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST
        )

    @staticmethod
    def _resolve_adapter(
        contract: HarnessRunContract,
        adapter_factory: HarnessAgentAdapterFactory,
    ) -> AgentTurnAdapter:
        adapter = adapter_factory(contract)
        if adapter.adapter_id != contract.adapter_id:
            raise HarnessAgentRunCompositionError(
                "Harness Agent Run Adapter differs from its Contract"
            )
        if adapter.model_id != contract.requested_model_id:
            raise HarnessAgentRunCompositionError(
                "Harness Agent Run requested model differs from its Contract"
            )
        expected_completion_digest = structured_completion_contract_digest(
            contract.completion_contract
        )
        if (
            expected_completion_digest is not None
            and getattr(adapter, "structured_completion_contract_digest", None)
            != expected_completion_digest
        ):
            raise HarnessAgentRunCompositionError(
                "Harness Agent Run structured completion differs from its Contract"
            )
        return adapter

    @staticmethod
    def _validate_structure(
        contract: HarnessRunContract,
        *,
        cognition_profile: HarnessCognitionProfile | None,
        execution_binding: HarnessExecutionBinding | None,
        runtime: HarnessRuntimeClient | None,
        provider_use_policy: HarnessProviderUsePolicy | None,
    ) -> None:
        """Admit every supported composition fact provable before state creation.

        This does not probe Provider or Runtime availability. It only rejects exact
        caller inputs that cannot lawfully compose the persisted Contract.
        """

        RunBudget.from_contract_dict(contract.budget)
        try:
            validate_provider_use_policy(contract, provider_use_policy)
        except HarnessProviderUsePolicyError as error:
            raise HarnessAgentRunCompositionError(str(error)) from error
        if cognition_profile is not None:
            if not contract.privacy.allow_model_content:
                raise HarnessAgentRunCompositionError(
                    "Harness cognition requires Contract permission to retain model content"
                )
            if (
                cognition_profile.working_set_history
                and not contract.privacy.allow_tool_content
            ):
                raise HarnessAgentRunCompositionError(
                    "Harness cognition history requires Tool-content authority"
                )

        no_tool = (
            contract.tool_catalog_digest == NO_TOOL_AGENT_SURFACE_DIGEST
            and contract.tool_grant_digest == NO_TOOL_AGENT_GRANT_DIGEST
        )
        runtime_search = (
            contract.tool_catalog_digest == INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST
            and contract.tool_grant_digest == INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST
        )
        if no_tool:
            if execution_binding is not None or runtime is not None:
                raise HarnessAgentRunCompositionError(
                    "no-Tool Harness Agent Run must not receive Runtime execution authority"
                )
            return
        if runtime_search:
            if execution_binding is None or runtime is None:
                raise HarnessAgentRunCompositionError(
                    "Runtime Tool Harness Agent Run requires exact execution binding and Runtime client"
                )
            HarnessAgentRun._validate_execution_binding(contract, execution_binding)
            return
        raise HarnessAgentRunCompositionError(
            "Harness Agent Run does not implement the Contract's exact Tool surface; "
            "use advanced core composition for custom Tool bridges"
        )

    @staticmethod
    def _validate_execution_binding(
        contract: HarnessRunContract,
        execution_binding: HarnessExecutionBinding,
    ) -> None:
        token = contract.digest[7:31]
        if (
            execution_binding.harness_run_id != contract.harness_run_id
            or execution_binding.assignment_id != f"assignment:external:{token}"
            or execution_binding.assignment_generation != 1
            or execution_binding.assignment_digest != contract.digest
        ):
            raise HarnessAgentRunCompositionError(
                "Harness Execution Binding differs from the independent Run binding"
            )
        if (
            execution_binding.tool_catalog_digest
            != INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST
            or execution_binding.tool_catalog_digest != contract.tool_catalog_digest
        ):
            raise HarnessAgentRunCompositionError(
                "Harness Execution Binding Tool catalog differs"
            )
        if (
            execution_binding.tool_grant_digest != INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST
            or contract.tool_grant_digest != INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST
        ):
            raise HarnessAgentRunCompositionError(
                "Harness Execution Binding Tool Grant differs"
            )
        if execution_binding.deadline_ms != contract.deadline_ms:
            raise HarnessAgentRunCompositionError(
                "Harness Execution Binding deadline differs"
            )
        if not execution_binding.runtime_references:
            raise HarnessAgentRunCompositionError(
                "independent Runtime execution requires foreign references"
            )
        if any(
            reference.namespace != "ordivon.harness"
            for reference in execution_binding.runtime_references
        ):
            raise HarnessAgentRunCompositionError(
                "independent Runtime execution may reference only ordivon.harness authority"
            )



__all__ = [
    "HarnessAgentAdapterFactory",
    "HarnessAgentExecution",
    "HarnessAgentRun",
    "HarnessAgentRunCompositionError",
    "HarnessCognitionProfile",
    "HarnessCognitionSeed",
    "HarnessCognitionSeedSource",
    "HarnessCognitionSource",
]

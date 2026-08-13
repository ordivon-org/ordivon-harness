"""Explicit application-local Tool-surface composition for HarnessAgentRun.

The descriptor binds one exact Runtime-backed Tool catalog/grant pair to a bridge
factory. It is not a registry, grants no authority, and cannot mutate an admitted
Run. Specialized surfaces opt into it explicitly while the normal HarnessAgentRun
API keeps its small built-in path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .core_contracts import HarnessRunContract
from .execution_binding import HarnessExecutionBinding
from .ordivon.loop import RunBudget
from .ordivon.run_store_port import HarnessRunContinuityStore
from .provider_use_policy import (
    HarnessProviderUsePolicy,
    HarnessProviderUsePolicyError,
    validate_provider_use_policy,
)
from .runtime_port import HarnessRuntimeClient
from .standalone import HarnessCognitionProfile, StandaloneToolBridge

if TYPE_CHECKING:
    from .agent_run import HarnessAgentAdapterFactory, HarnessAgentRun

HarnessAgentRunToolBridgeFactory = Callable[
    [
        HarnessRunContract,
        HarnessRunContinuityStore,
        HarnessExecutionBinding,
        HarnessRuntimeClient,
        object | None,
    ],
    StandaloneToolBridge,
]


def _text(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > 300
    ):
        raise ValueError(f"{label} must be non-empty and trimmed")


def _digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")


def _validate_runtime_binding(
    contract: HarnessRunContract,
    execution_binding: HarnessExecutionBinding,
) -> None:
    from .agent_run import HarnessAgentRunCompositionError

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
    if execution_binding.tool_catalog_digest != contract.tool_catalog_digest:
        raise HarnessAgentRunCompositionError(
            "Harness Execution Binding Tool catalog differs"
        )
    if execution_binding.tool_grant_digest != contract.tool_grant_digest:
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


@dataclass(frozen=True, slots=True)
class HarnessAgentRunToolSurface:
    """One explicit Runtime-backed Tool surface for a supported Agent Run.

    Exact surface digests, cognition/privacy requirements, and Runtime binding are
    checked before durable Run creation. The bridge factory is invoked only after
    Run continuity exists; its bridge remains subject to the existing Runner
    catalog check and workload-local recovery validation.
    """

    surface_id: str
    tool_catalog_digest: str
    tool_grant_digest: str
    bridge_factory: HarnessAgentRunToolBridgeFactory

    def __post_init__(self) -> None:
        _text(self.surface_id, "Harness Agent Run Tool surface identity")
        _digest(self.tool_catalog_digest, "Harness Agent Run Tool catalog digest")
        _digest(self.tool_grant_digest, "Harness Agent Run Tool Grant digest")
        if not callable(self.bridge_factory):
            raise TypeError("Harness Agent Run Tool bridge factory must be callable")

    def matches(self, contract: HarnessRunContract) -> bool:
        return (
            contract.tool_catalog_digest == self.tool_catalog_digest
            and contract.tool_grant_digest == self.tool_grant_digest
        )

    def build(
        self,
        contract: HarnessRunContract,
        continuity: HarnessRunContinuityStore,
        execution_binding: HarnessExecutionBinding,
        runtime: HarnessRuntimeClient,
        *,
        provider_source: object | None = None,
    ) -> StandaloneToolBridge:
        return self.bridge_factory(
            contract,
            continuity,
            execution_binding,
            runtime,
            provider_source,
        )

    def _run_type(self):
        from .agent_run import HarnessAgentRun, HarnessAgentRunCompositionError

        surface = self

        class ExplicitSurfaceAgentRun(HarnessAgentRun):
            @staticmethod
            def _validate_structure(
                contract: HarnessRunContract,
                *,
                cognition_profile: HarnessCognitionProfile | None,
                execution_binding: HarnessExecutionBinding | None,
                runtime: HarnessRuntimeClient | None,
                provider_use_policy: HarnessProviderUsePolicy | None,
            ) -> None:
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
                if not surface.matches(contract):
                    raise HarnessAgentRunCompositionError(
                        "explicit Harness Agent Run Tool surface differs from its Contract"
                    )
                if execution_binding is None or runtime is None:
                    raise HarnessAgentRunCompositionError(
                        "explicit Runtime Tool surface requires exact execution binding and Runtime client"
                    )
                _validate_runtime_binding(contract, execution_binding)

            def _bridge(
                self,
                continuity,
                *,
                provider_source=None,
            ) -> StandaloneToolBridge:
                assert self.execution_binding is not None
                assert self.runtime is not None
                return surface.build(
                    self.contract,
                    continuity,
                    self.execution_binding,
                    self.runtime,
                    provider_source=provider_source,
                )

            def explain(self):
                value = super().explain()
                run_projection = value["run"]
                assert isinstance(run_projection, dict)
                tool_projection = run_projection["toolSurface"]
                assert isinstance(tool_projection, dict)
                tool_projection["explicitRunToolSurfaceId"] = surface.surface_id
                tool_projection["supportedByHarnessAgentRun"] = True
                return value

        return ExplicitSurfaceAgentRun

    def create(
        self,
        state_root: str | Path,
        contract: HarnessRunContract,
        adapter_factory: "HarnessAgentAdapterFactory",
        *,
        cognition_profile: HarnessCognitionProfile | None = None,
        execution_binding: HarnessExecutionBinding | None = None,
        runtime: HarnessRuntimeClient | None = None,
        provider_use_policy: HarnessProviderUsePolicy | None = None,
        clock_ms=None,
        monotonic_ms=None,
    ) -> "HarnessAgentRun":
        return self._run_type().create(
            state_root,
            contract,
            adapter_factory,
            cognition_profile=cognition_profile,
            execution_binding=execution_binding,
            runtime=runtime,
            provider_use_policy=provider_use_policy,
            clock_ms=clock_ms,
            monotonic_ms=monotonic_ms,
        )

    def open(
        self,
        state_root: str | Path,
        harness_run_id: str,
        adapter_factory: "HarnessAgentAdapterFactory",
        *,
        cognition_profile: HarnessCognitionProfile | None = None,
        execution_binding: HarnessExecutionBinding | None = None,
        runtime: HarnessRuntimeClient | None = None,
        provider_use_policy: HarnessProviderUsePolicy | None = None,
        clock_ms=None,
        monotonic_ms=None,
    ) -> "HarnessAgentRun":
        return self._run_type().open(
            state_root,
            harness_run_id,
            adapter_factory,
            cognition_profile=cognition_profile,
            execution_binding=execution_binding,
            runtime=runtime,
            provider_use_policy=provider_use_policy,
            clock_ms=clock_ms,
            monotonic_ms=monotonic_ms,
        )


__all__ = [
    "HarnessAgentRunToolBridgeFactory",
    "HarnessAgentRunToolSurface",
]

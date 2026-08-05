#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from anc_canonical import canonical_digest
from ordivon_host import (
    EventKind,
    ExternalExecutionRequest,
    ExternalExecutorCoordinator,
    HostExtensionPort,
    HostKernel,
    HostStorage,
    TaskState,
)
from ordivon_host.ops import validate_history as validate_host_history

from ordivon_harness.core import (
    AgentRunConclusion,
    AgentTurnResult,
    HarnessBoundReference,
    HarnessRunContract,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    RunBudget,
    SQLiteHarnessAgentBridge,
    SQLiteHarnessRunContinuityStore,
    SQLiteHarnessStore,
    ScriptedTurnAdapter,
    StandaloneHarnessRunner,
)
from ordivon_harness.host_external_adapter import (
    OrdivonHarnessExternalExecutorAdapter,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class FixedClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> int:
        self.value += 1
        return self.value


@dataclass
class Driver:
    runner: StandaloneHarnessRunner

    def execute(self):
        return self.runner.run(({"role": "user", "content": "complete the external Run"},))


class LossyAdapter:
    def __init__(self, delegate: OrdivonHarnessExternalExecutorAdapter) -> None:
        self.delegate = delegate
        self.adapter_id = delegate.adapter_id
        self.start_calls = 0
        self.lost = False

    def start(self, request):
        self.start_calls += 1
        observed = self.delegate.start(request)
        if not self.lost:
            self.lost = True
            raise RuntimeError("injected Host delivery loss after Harness completion")
        return observed

    def observe(self, foreign_run_ref):
        return self.delegate.observe(foreign_run_ref)

    def cancel(self, foreign_run_ref, request_id):
        return self.delegate.cancel(foreign_run_ref, request_id)

    def recover(self, request, foreign_run_ref):
        return self.delegate.recover(request, foreign_run_ref)

    def collect_completion(self, foreign_run_ref):
        return self.delegate.collect_completion(foreign_run_ref)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ordivon-host-harness-p0-") as directory:
        root = Path(directory)
        host_root = root / "host"
        harness_root = root / "harness"
        host_clock = FixedClock(1_000)
        harness_clock = FixedClock(2_000)
        request_id = "external-request:host-harness-p0"
        budget = RunBudget(
            max_model_calls=1,
            max_tool_calls=1,
            max_observation_bytes=16_384,
            max_wall_time_ms=10_000,
            max_total_tokens=1_000,
            max_model_retries=0,
        )
        result = AgentTurnResult(
            model_call_id="model-call:host-harness-p0",
            model_id=ScriptedTurnAdapter.model_id,
            content="candidate complete",
            tool_calls=(),
            conclusion=AgentRunConclusion(
                status="candidate_completed",
                summary="Harness proposes completion; Host still owns acceptance.",
                evidence_refs=("evidence:harness-p0",),
            ),
            usage={"inputTokens": 8, "outputTokens": 5},
            finish_reason="stop",
            raw_response_digest=canonical_digest({"run": "host-harness-p0"}),
        )
        contract = HarnessRunContract(
            harness_run_id="harness-run:host-harness-p0",
            harness_implementation_id="ordivon-harness@p0",
            caller_id="caller:ordivon-host",
            caller_run_ref=request_id,
            objective_ref=HarnessBoundReference(
                "objective:host-harness-p0", "objective", DIGEST_A
            ),
            context_refs=(
                HarnessBoundReference(
                    "context:host-harness-p0", "context", DIGEST_B
                ),
            ),
            provider_id="provider:scripted",
            adapter_id=ScriptedTurnAdapter.adapter_id,
            requested_model_id=ScriptedTurnAdapter.model_id,
            tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
            tool_grant_digest=canonical_digest(
                {"schemaVersion": 1, "kind": "ordivon.no-tool-grant", "tools": []}
            ),
            budget={
                "maxModelCalls": 1,
                "maxToolCalls": 1,
                "maxWallTimeMs": 10_000,
            },
            completion_contract={"mode": "propose"},
            system_manifest_ref=HarnessBoundReference(
                "system-manifest:host-harness-p0", "system-manifest", DIGEST_A
            ),
            created_at_ms=2_001,
        )
        driver_creations = 0

        def resolve(request):
            if request.request_id != request_id:
                raise AssertionError("unexpected Host request")
            return contract

        def driver_factory(run_contract, continuity: SQLiteHarnessRunContinuityStore):
            nonlocal driver_creations
            driver_creations += 1
            adapter = ScriptedTurnAdapter((result,))
            bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            return Driver(
                StandaloneHarnessRunner(
                    run_contract,
                    continuity,
                    adapter,
                    bridge,
                    budget=budget,
                    clock_ms=harness_clock,
                    monotonic_ms=harness_clock,
                )
            )

        harness_adapter = OrdivonHarnessExternalExecutorAdapter(
            harness_root,
            contract_resolver=resolve,
            driver_factory=driver_factory,
            clock_ms=harness_clock,
        )
        lossy = LossyAdapter(harness_adapter)

        with HostStorage(host_root) as storage:
            kernel = HostKernel(
                storage,
                clock_ms=host_clock,
                owner_id="host:p0-external-roundtrip",
            )
            task = kernel.create_task(
                event_id="event:host-harness-p0:create",
                kind=EventKind.TASK_CREATED,
                task_id="task:host-harness-p0",
                goal_id="goal:host-harness-p0",
                payload={"purpose": "P0 cross-authority acceptance"},
                frontier=("node:host-harness-p0",),
            ).projection
            request = ExternalExecutionRequest(
                request_id=request_id,
                adapter_id=lossy.adapter_id,
                task_id=task.task_id,
                task_revision=task.revision,
                task_attempt_ref="task-attempt:host-harness-p0",
                contract_digest=contract.digest,
                correlation_context={"traceId": "3" * 32},
                created_at_ms=1_500,
            )
            coordinator = ExternalExecutorCoordinator(HostExtensionPort(storage, kernel))
            try:
                coordinator.start(request, lossy)
            except RuntimeError as error:
                if "delivery loss" not in str(error):
                    raise
            else:
                raise AssertionError("injected response loss was not observed")
            prepared = coordinator.load(task.task_id)
            if prepared.request != request or prepared.binding is not None:
                raise AssertionError("Host did not retain request-only commit gap")
            with SQLiteHarnessStore(harness_root) as harness_store:
                harness_projection = harness_store.load_run(contract.harness_run_id)
                if harness_projection.status.value != "completed":
                    raise AssertionError("Harness did not independently complete")
            bound = coordinator.start(request, lossy)
            if bound.binding is None or bound.binding.foreign_run_ref != contract.harness_run_id:
                raise AssertionError("Host did not bind the recovered Harness Run")
            completed = coordinator.collect_completion(task.task_id, lossy)
            if completed.completion_proposal is None:
                raise AssertionError("Host did not collect Harness CompletionProposal")
            if completed.projection.state is not TaskState.READY:
                raise AssertionError("foreign completion advanced Host Task")
            if completed.projection.state.terminal:
                raise AssertionError("foreign completion terminated Host Task")
            if driver_creations != 1 or lossy.start_calls != 2:
                raise AssertionError("response loss created another physical Harness execution")
            host_events = validate_host_history(storage).events

        with HostStorage(host_root) as reopened_host:
            reopened = ExternalExecutorCoordinator(
                HostExtensionPort(
                    reopened_host,
                    HostKernel(
                        reopened_host,
                        clock_ms=host_clock,
                        owner_id="host:p0-external-roundtrip-reopen",
                    ),
                )
            ).load("task:host-harness-p0")
            if reopened.binding is None or reopened.completion_proposal is None:
                raise AssertionError("Host foreign binding did not survive reopen")
            if reopened.projection.state is not TaskState.READY:
                raise AssertionError("Host reopen changed Task state")
        with SQLiteHarnessStore(harness_root) as reopened_harness:
            harness_projection = reopened_harness.load_run(contract.harness_run_id)
            harness_events = len(
                reopened_harness.list_run_events(contract.harness_run_id)
            )
            if not reopened_harness.doctor(full=True)["healthy"]:
                raise AssertionError("Harness Doctor failed after reopen")

        print(
            {
                "ok": True,
                "hostEvents": host_events,
                "harnessEvents": harness_events,
                "hostTaskState": reopened.projection.state.value,
                "harnessRunState": harness_projection.status.value,
                "physicalHarnessExecutions": driver_creations,
                "adapterStartCalls": lossy.start_calls,
                "foreignRunRef": reopened.binding.foreign_run_ref,
                "completionProposalDigest": reopened.completion_proposal.digest,
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

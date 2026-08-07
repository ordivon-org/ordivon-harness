from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from anc_canonical import JsonValue
from ._host_compat.context import CompiledContext, ContextBlock
from ._host_compat.effects import ArtifactRef
from ._host_compat.runtime import RuntimeClient
from ._host_compat.storage import HostStorage
from .protocol import HarnessRunSnapshot

from .contracts import TaskContract, ToolGrant
from .host import (
    AcceptanceVerifier,
    ArtifactExists,
    CommittedHarnessAssignment,
    HarnessHost,
    HarnessLifecycleError,
    ProposedCompletion,
    RecordedHarnessRun,
)
from .models import CompletionDecisionReceipt
from .ordivon.control import CancellationToken
from .ordivon.events import HarnessRunEvent
from .ordivon.input import (
    HarnessContextCompiler,
    HarnessContextRequest,
    OrdivonInputCompiler,
    harness_context_object_digest,
)
from .ordivon.loop import AgentLoopResult, OrdivonAgentLoop, RunBudget, RunStopCode
from .ordivon.manifest import ordivon_harness_manifest
from .ordivon.model import AgentTurnAdapter
from .ordivon.result import NativeRunTimes, record_native_run_result
from .ordivon.run_store import HostHarnessRunStore
from .ordivon.run_store_port import StoredHarnessRunSnapshot
from .ordivon.tools import (
    RuntimeToolBridge,
    discover_harness_runtime_catalog,
)
from .recovery_controller import NativeRunRecoveryController, NativeRunRecoveryResult

_DEFAULT_BUDGET = RunBudget(
    max_model_calls=8,
    max_tool_calls=16,
    max_observation_bytes=1_048_576,
    max_wall_time_ms=600_000,
    max_total_tokens=131_072,
    max_model_retries=2,
    max_tool_corrections=3,
)
_DURABLE_CAPABILITIES = (
    "tool_events",
    "usage",
    "checkpoint",
    "interrupt",
    "ordivon.run-state-resume.v1",
    "ordivon.effect-checkpoint.v1",
    "ordivon.provider-call-cancel.v1",
    "ordivon.provider-call-claim.v1",
    "ordivon.provider-result-replay.v1",
    "ordivon.provider-dispatch-outcome.v1",
    "ordivon.runtime-job-cancel.v1",
)


class CompletionMode(StrEnum):
    """How far the Runner advances a candidate-completed Run."""

    RECORD = "record"
    PROPOSE = "propose"
    ADJUDICATE = "adjudicate"


@dataclass(frozen=True, slots=True)
class HarnessRunPlan:
    """Complete input needed to prepare and execute one native Harness Run."""

    task_contract: TaskContract
    context_blocks: tuple[ContextBlock, ...]
    workspace_ref: str
    tool_grant: ToolGrant
    token_budget: int = 16_000
    budget: RunBudget = field(default_factory=lambda: _DEFAULT_BUDGET)
    source_ref: str | None = None
    source_digest: str | None = None
    prior_artifact_refs: tuple[ArtifactRef, ...] = ()
    required_capabilities: tuple[str, ...] = _DURABLE_CAPABILITIES
    deadline_ms: int | None = None
    completion_mode: CompletionMode = CompletionMode.RECORD

    def __post_init__(self) -> None:
        if not self.workspace_ref or self.workspace_ref != self.workspace_ref.strip():
            raise ValueError(
                "Harness Run Plan Workspace identity must be non-empty and trimmed"
            )
        if self.token_budget < 1:
            raise ValueError("Harness Run Plan token budget must be positive")
        if "mutate_workspace" in self.tool_grant.allowed_tools:
            raise ValueError(
                "durable Harness Run Plans cannot grant mutate_workspace until Runtime "
                "exposes a reconciliable mutation dispatch identity"
            )
        if len(self.required_capabilities) != len(set(self.required_capabilities)):
            raise ValueError("Harness Run Plan required capabilities must be unique")
        if self.deadline_ms is not None and self.deadline_ms < 0:
            raise ValueError("Harness Run Plan deadline must be non-negative")

    @property
    def task_id(self) -> str:
        return self.task_contract.task_id


@dataclass(frozen=True, slots=True)
class HarnessExecutionResult:
    task_id: str
    assignment_id: str
    harness_run_id: str
    loop_result: AgentLoopResult
    recorded: RecordedHarnessRun | None
    proposal: ProposedCompletion | None
    decision: CompletionDecisionReceipt | None

    @property
    def paused(self) -> bool:
        return self.loop_result.stop_code in {
            RunStopCode.NEEDS_INPUT,
            RunStopCode.NO_PROGRESS,
        }

    @property
    def candidate_completed(self) -> bool:
        return self.loop_result.candidate_completed

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "taskId": self.task_id,
            "assignmentId": self.assignment_id,
            "harnessRunId": self.harness_run_id,
            "stopCode": self.loop_result.stop_code.value,
            "candidateCompleted": self.candidate_completed,
            "paused": self.paused,
            "modelCalls": self.loop_result.model_calls,
            "toolCalls": self.loop_result.tool_calls,
            "observationBytes": self.loop_result.observation_bytes,
            "recordedTaskRevision": (
                None if self.recorded is None else self.recorded.task_revision
            ),
            "completionProposalId": (
                None
                if self.proposal is None
                else self.proposal.proposal.completion_proposal_id
            ),
            "completionAccepted": (
                None if self.decision is None else self.decision.decision.accepted
            ),
            "completionReasonCode": (
                None if self.decision is None else self.decision.decision.reason_code
            ),
            "usage": self.loop_result.usage,
        }


@dataclass(frozen=True, slots=True)
class HarnessStatus:
    task_id: str
    task_state: str
    task_revision: int
    phase: str
    assignment_id: str | None
    assignment_generation: int | None
    harness_run_id: str | None
    termination_code: str | None
    pause_reason: str | None
    active_tool_step: bool
    provider_call_status: str | None
    provider_call_generation: int | None
    provider_call_expires_at_ms: int | None
    completion_proposal_id: str | None
    completion_accepted: bool | None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "taskId": self.task_id,
            "taskState": self.task_state,
            "taskRevision": self.task_revision,
            "phase": self.phase,
            "assignmentId": self.assignment_id,
            "assignmentGeneration": self.assignment_generation,
            "harnessRunId": self.harness_run_id,
            "terminationCode": self.termination_code,
            "pauseReason": self.pause_reason,
            "activeToolStep": self.active_tool_step,
            "providerCallStatus": self.provider_call_status,
            "providerCallGeneration": self.provider_call_generation,
            "providerCallExpiresAtMs": self.provider_call_expires_at_ms,
            "completionProposalId": self.completion_proposal_id,
            "completionAccepted": self.completion_accepted,
        }


@dataclass(frozen=True, slots=True)
class HarnessCancellationResult:
    task_id: str
    requested: bool
    confirmed: bool
    status: str
    runtime_job_ref: str | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "taskId": self.task_id,
            "requested": self.requested,
            "confirmed": self.confirmed,
            "status": self.status,
            "runtimeJobRef": self.runtime_job_ref,
        }


class RunHandle:
    """One in-process Run with cooperative Provider and Runtime cancellation."""

    def __init__(
        self,
        task_id: str,
        worker: Callable[[CancellationToken], HarnessExecutionResult],
        *,
        event_queue: queue.Queue[HarnessRunEvent | object] | None = None,
        on_done: Callable[[RunHandle], None] | None = None,
    ) -> None:
        self.task_id = task_id
        self._worker = worker
        self._on_done = on_done
        self._events = event_queue or queue.Queue()
        self._event_end = object()
        self._cancellation = CancellationToken()
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._result: HarnessExecutionResult | None = None
        self._error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"ordivon-harness:{task_id}",
            daemon=False,
        )
        self._started = False

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def cancellation_requested(self) -> bool:
        return self._cancellation.cancelled

    def cancel(self) -> None:
        self._cancellation.cancel()

    def _start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("RunHandle is already started")
            self._started = True
        self._thread.start()

    def iter_events(self, timeout: float | None = None) -> Iterator[HarnessRunEvent]:
        """Yield live semantic events until the Run terminates.

        A timeout applies independently to each wait. Canonical evidence remains the
        final Harness Trace; this stream is a best-effort projection.
        """
        if timeout is not None and timeout < 0:
            raise ValueError("RunHandle event timeout must be non-negative")
        while True:
            try:
                item = self._events.get(timeout=timeout)
            except queue.Empty as error:
                if self.done:
                    return
                raise TimeoutError(
                    f"Harness Run emitted no event before timeout: {self.task_id}"
                ) from error
            if item is self._event_end:
                return
            assert isinstance(item, HarnessRunEvent)
            yield item

    def result(self, timeout: float | None = None) -> HarnessExecutionResult:
        if timeout is not None and timeout < 0:
            raise ValueError("RunHandle timeout must be non-negative")
        if not self._done.wait(timeout):
            raise TimeoutError(f"Harness Run is still active: {self.task_id}")
        with self._lock:
            error = self._error
            result = self._result
        if error is not None:
            raise error
        assert result is not None
        return result

    def _run(self) -> None:
        try:
            result = self._worker(self._cancellation)
        except BaseException as error:  # noqa: BLE001 - thread boundary preserves failure.
            with self._lock:
                self._error = error
        else:
            with self._lock:
                self._result = result
        finally:
            self._done.set()
            self._events.put(self._event_end)
            if self._on_done is not None:
                self._on_done(self)


class HarnessRunner:
    """Recommended native Harness entry point.

    The Runner only orchestrates existing Host, Harness and Runtime authorities. It
    does not create a second Task truth, database, daemon or workflow state machine.
    """

    def __init__(
        self,
        host: HarnessHost,
        *,
        runtime: RuntimeClient | None = None,
        adapter: AgentTurnAdapter | None = None,
        default_budget: RunBudget = _DEFAULT_BUDGET,
        artifact_exists: ArtifactExists | None = None,
        acceptance_verifier: AcceptanceVerifier | None = None,
        verification_method: str = "ordivon-harness-runner-v1",
        event_sink: Callable[[HarnessRunEvent], None] | None = None,
        monotonic_ms: Callable[[], int] | None = None,
    ) -> None:
        self.host = host
        self.runtime = runtime
        self.adapter = adapter
        self.default_budget = default_budget
        self.artifact_exists = artifact_exists
        self.acceptance_verifier = acceptance_verifier
        self.verification_method = verification_method
        self.event_sink = event_sink
        self.monotonic_ms = monotonic_ms or (
            lambda: time.monotonic_ns() // 1_000_000
        )
        self._handles: dict[str, RunHandle] = {}
        self._handles_lock = threading.Lock()

    def prepare(self, plan: HarnessRunPlan) -> CommittedHarnessAssignment:
        if (
            plan.deadline_ms is not None
            and plan.deadline_ms <= self.host.kernel.clock_ms()
        ):
            raise HarnessLifecycleError(
                "Harness Run Plan deadline expired before preparation"
            )
        runtime = self._require_runtime()
        catalog = discover_harness_runtime_catalog(runtime)
        attempt = self.host.start_attempt(
            plan.task_id,
            task_contract=plan.task_contract,
        )
        context = HarnessContextCompiler().compile(
            attempt.descriptor,
            HarnessContextRequest(
                task_contract=plan.task_contract,
                blocks=plan.context_blocks,
            ),
            token_budget=plan.token_budget,
        )
        context_object = self.host.storage.put_object(
            context.to_dict(), kind="compiled-context"
        )
        if context_object.digest != harness_context_object_digest(context):
            raise RuntimeError(
                "Host CAS Context identity differs from compiler identity"
            )
        return self.host.assign(
            attempt,
            manifest=ordivon_harness_manifest(),
            context_object_digest=context_object.digest,
            tool_catalog_digest=catalog.digest,
            tool_catalog=catalog,
            workspace_ref=plan.workspace_ref,
            source_ref=plan.source_ref,
            source_digest=plan.source_digest,
            prior_artifact_refs=plan.prior_artifact_refs,
            required_capabilities=plan.required_capabilities,
            budget=self._budget_to_assignment(plan.budget),
            deadline_ms=plan.deadline_ms,
            tool_grant=plan.tool_grant,
        )

    def run(
        self,
        plan: HarnessRunPlan,
        *,
        cancellation: CancellationToken | None = None,
    ) -> HarnessExecutionResult:
        self._validate_completion_mode(plan.completion_mode)
        committed = self.prepare(plan)
        return self._execute(
            committed,
            budget=plan.budget,
            completion_mode=plan.completion_mode,
            cancellation=cancellation,
        )

    def run_current(
        self,
        task_id: str,
        *,
        budget: RunBudget | None = None,
        completion_mode: CompletionMode = CompletionMode.RECORD,
        cancellation: CancellationToken | None = None,
    ) -> HarnessExecutionResult:
        self._validate_completion_mode(completion_mode)
        committed = self.host.load_current_assignment(task_id)
        committed_budget = self._budget_from_assignment(committed)
        if budget is not None and budget != committed_budget:
            raise HarnessLifecycleError(
                "Harness Run cannot replace its committed Run budget"
            )
        return self._execute(
            committed,
            budget=committed_budget if budget is None else budget,
            completion_mode=completion_mode,
            cancellation=cancellation,
        )

    def resume(
        self,
        task_id: str,
        *,
        additional_messages: tuple[dict[str, JsonValue], ...] = (),
        budget: RunBudget | None = None,
        completion_mode: CompletionMode = CompletionMode.RECORD,
        cancellation: CancellationToken | None = None,
    ) -> HarnessExecutionResult:
        self._validate_completion_mode(completion_mode)
        committed = self.host.load_current_assignment(task_id)
        native = committed.native_run_contract
        if native is None:
            raise HarnessLifecycleError(
                "current Assignment is not a native Harness Run"
            )
        run_store = HostHarnessRunStore(self.host, committed)
        retained = run_store.load_current_snapshot()
        if retained.snapshot.pause_reason.value not in {
            "needs-input",
            "effect-dispatch-pending",
        }:
            raise HarnessLifecycleError(
                f"Harness Run Snapshot cannot resume from {retained.snapshot.pause_reason.value}"
            )
        return self._execute(
            committed,
            budget=budget or self._budget_from_assignment(committed),
            completion_mode=completion_mode,
            cancellation=cancellation,
            retained=retained,
            additional_messages=additional_messages,
        )

    def recover(
        self,
        task_id: str,
        *,
        trigger: str = "host_restart",
        auto_abandon: bool = True,
    ) -> NativeRunRecoveryResult:
        return NativeRunRecoveryController(
            self.host,
            self._require_runtime(),
        ).recover(task_id, trigger=trigger, auto_abandon=auto_abandon)

    def status(self, task_id: str) -> HarnessStatus:
        snapshot = self.host.storage.read_task_event(task_id)
        if not isinstance(snapshot.data, dict):
            raise HarnessLifecycleError("Task head data is not an object")
        data = snapshot.data
        pause_reason: str | None = None
        snapshot_object_digest = data.get("harnessRunSnapshotObjectDigest")
        if isinstance(snapshot_object_digest, str):
            value = self.host.storage.objects.get(
                snapshot_object_digest,
                expected_kind="harness-run-snapshot",
            )
            if isinstance(value, dict):
                pause_reason = HarnessRunSnapshot.from_dict(value).pause_reason.value
        assignment_id = self._optional_string(data.get("assignmentId"))
        harness_run_id = self._optional_string(data.get("harnessRunId"))
        termination_code = self._optional_string(data.get("harnessRunTerminationCode"))
        proposal_id = self._optional_string(data.get("completionProposalId"))
        completion_accepted = data.get("completionAccepted")
        if type(completion_accepted) is not bool:
            completion_accepted = None
        active_tool_step = isinstance(
            data.get("activeHarnessToolStepIntentDigest"), str
        )
        provider_call_status = self._optional_string(
            data.get("activeHarnessProviderCallStatus")
        )
        provider_call_generation = data.get(
            "activeHarnessProviderCallGeneration"
        )
        provider_call_expires_at_ms = data.get(
            "activeHarnessProviderCallExpiresAtMs"
        )
        if snapshot.projection.state.terminal:
            phase = "completed" if completion_accepted is True else "terminal"
        elif completion_accepted is not None:
            phase = "completion-decided"
        elif proposal_id is not None:
            phase = "completion-proposed"
        elif termination_code is not None:
            phase = "run-recorded"
        elif provider_call_status is not None:
            phase = {
                "claimed": "provider-active",
                "dispatching": "provider-recovery-required",
                "completed": "provider-result-durable",
                "failed": "provider-failure-durable",
                "unknown": "provider-recovery-required",
            }.get(provider_call_status, "provider-active")
        elif active_tool_step:
            phase = "tool-active"
        elif pause_reason is not None:
            phase = "paused"
        elif harness_run_id is not None or assignment_id is not None:
            phase = "assigned"
        elif isinstance(data.get("taskAttemptId"), str):
            phase = "attempted"
        else:
            phase = "task"
        generation = data.get("assignmentGeneration")
        return HarnessStatus(
            task_id=task_id,
            task_state=snapshot.projection.state.value,
            task_revision=snapshot.projection.revision,
            phase=phase,
            assignment_id=assignment_id,
            assignment_generation=(generation if type(generation) is int else None),
            harness_run_id=harness_run_id,
            termination_code=termination_code,
            pause_reason=pause_reason,
            active_tool_step=active_tool_step,
            provider_call_status=provider_call_status,
            provider_call_generation=(
                provider_call_generation
                if type(provider_call_generation) is int
                else None
            ),
            provider_call_expires_at_ms=(
                provider_call_expires_at_ms
                if type(provider_call_expires_at_ms) is int
                else None
            ),
            completion_proposal_id=proposal_id,
            completion_accepted=completion_accepted,
        )

    def cancel(self, task_id: str) -> HarnessCancellationResult:
        with self._handles_lock:
            handle = self._handles.get(task_id)
        if handle is not None and not handle.done:
            handle.cancel()
            return HarnessCancellationResult(
                task_id,
                requested=True,
                confirmed=False,
                status="in-process-cancellation-requested",
            )

        committed = self.host.load_current_assignment(task_id)
        native = committed.native_run_contract
        if native is None:
            return HarnessCancellationResult(
                task_id,
                requested=False,
                confirmed=False,
                status="not-a-native-run",
            )
        run_store = HostHarnessRunStore(self.host, committed)
        try:
            step = run_store.load_current_tool_step()
        except KeyError:
            return HarnessCancellationResult(
                task_id,
                requested=False,
                confirmed=False,
                status="no-cancellable-runtime-effect",
            )
        if step.receipt is not None and step.receipt.terminal:
            return HarnessCancellationResult(
                task_id,
                requested=False,
                confirmed=True,
                status=f"tool-step-already-{step.receipt.status.value}",
                runtime_job_ref=step.receipt.runtime_job_ref,
            )
        bridge = RuntimeToolBridge(
            committed,
            harness_run_id=native.harness_run_id,
            runtime=self._require_runtime(),
            run_store=run_store,
        )
        observation = bridge.reconcile_current_tool_step()
        return HarnessCancellationResult(
            task_id,
            requested=True,
            confirmed=observation.status in {"cancelled", "observed"},
            status=observation.status,
            runtime_job_ref=observation.runtime_job_ref,
        )

    def start(self, plan: HarnessRunPlan) -> RunHandle:
        return self._start(
            plan.task_id,
            lambda runner, token: runner.run(plan, cancellation=token),
        )

    def start_current(
        self,
        task_id: str,
        *,
        budget: RunBudget | None = None,
        completion_mode: CompletionMode = CompletionMode.RECORD,
    ) -> RunHandle:
        return self._start(
            task_id,
            lambda runner, token: runner.run_current(
                task_id,
                budget=budget,
                completion_mode=completion_mode,
                cancellation=token,
            ),
        )

    def start_resume(
        self,
        task_id: str,
        *,
        additional_messages: tuple[dict[str, JsonValue], ...] = (),
        budget: RunBudget | None = None,
        completion_mode: CompletionMode = CompletionMode.RECORD,
    ) -> RunHandle:
        return self._start(
            task_id,
            lambda runner, token: runner.resume(
                task_id,
                additional_messages=additional_messages,
                budget=budget,
                completion_mode=completion_mode,
                cancellation=token,
            ),
        )

    def _start(
        self,
        task_id: str,
        operation: Callable[[HarnessRunner, CancellationToken], HarnessExecutionResult],
    ) -> RunHandle:
        self._require_runtime()
        self._require_adapter()
        with self._handles_lock:
            active = [handle for handle in self._handles.values() if not handle.done]
            if active:
                raise HarnessLifecycleError(
                    f"this Runner already owns an active Run: {active[0].task_id}"
                )

            event_queue: queue.Queue[HarnessRunEvent | object] = queue.Queue()

            def worker(token: CancellationToken) -> HarnessExecutionResult:
                with HostStorage(self.host.storage.root) as storage:
                    child = HarnessRunner(
                        HarnessHost(storage, clock_ms=self.host.kernel.clock_ms),
                        runtime=self.runtime,
                        adapter=self.adapter,
                        default_budget=self.default_budget,
                        artifact_exists=self.artifact_exists,
                        acceptance_verifier=self.acceptance_verifier,
                        verification_method=self.verification_method,
                        event_sink=event_queue.put,
                        monotonic_ms=self.monotonic_ms,
                    )
                    return operation(child, token)

            handle = RunHandle(
                task_id,
                worker,
                event_queue=event_queue,
                on_done=self._handle_done,
            )
            self._handles[task_id] = handle
            try:
                handle._start()
            except BaseException:
                self._handles.pop(task_id, None)
                raise
            return handle

    def _handle_done(self, handle: RunHandle) -> None:
        with self._handles_lock:
            if self._handles.get(handle.task_id) is handle:
                self._handles.pop(handle.task_id, None)

    def _execute(
        self,
        committed: CommittedHarnessAssignment,
        *,
        budget: RunBudget,
        completion_mode: CompletionMode,
        cancellation: CancellationToken | None,
        retained: StoredHarnessRunSnapshot | None = None,
        additional_messages: tuple[dict[str, JsonValue], ...] = (),
    ) -> HarnessExecutionResult:
        native = committed.native_run_contract
        if native is None:
            raise HarnessLifecycleError(
                "current Assignment is not a native Harness Run"
            )
        if budget != self._budget_from_assignment(committed):
            raise HarnessLifecycleError(
                "Harness Run cannot replace its committed Run budget"
            )
        runtime = self._require_runtime()
        adapter = self._require_adapter()
        self._validate_execution_entry(committed, retained=retained)
        context = self._load_context(committed)
        compiled_input = OrdivonInputCompiler().compile(committed, context)
        run_store = HostHarnessRunStore(self.host, committed)
        provider_source = (
            run_store.assignment_provider_source()
            if retained is None
            else run_store.snapshot_provider_source(retained)
        )
        bridge = RuntimeToolBridge(
            run_store.committed,
            harness_run_id=native.harness_run_id,
            runtime=runtime,
            run_store=run_store,
            provider_source=provider_source,
            defer_runtime_catalog_validation=True,
        )
        loop = OrdivonAgentLoop(
            adapter,
            bridge,
            budget=budget,
            clock_ms=self.host.kernel.clock_ms,
            monotonic_ms=self.monotonic_ms,
            assignment_deadline_ms=committed.assignment.deadline_ms,
            event_sink=self.event_sink,
        )
        started_at_ms = self.host.kernel.clock_ms()
        if retained is None:
            result = loop.run(
                harness_run_id=compiled_input.harness_run_id,
                assignment_id=committed.assignment.assignment_id,
                context_digest=committed.assignment.context_object_digest,
                initial_messages=compiled_input.initial_messages,
                cancellation=cancellation,
            )
        else:
            result = loop.resume(
                retained=retained,
                assignment_id=committed.assignment.assignment_id,
                context_digest=committed.assignment.context_object_digest,
                additional_messages=additional_messages,
                cancellation=cancellation,
            )
        if result.stop_code in {
            RunStopCode.NEEDS_INPUT,
            RunStopCode.NO_PROGRESS,
        }:
            return HarnessExecutionResult(
                task_id=committed.assignment.task_id,
                assignment_id=committed.assignment.assignment_id,
                harness_run_id=native.harness_run_id,
                loop_result=result,
                recorded=None,
                proposal=None,
                decision=None,
            )
        recorded = record_native_run_result(
            self.host,
            bridge.committed,
            result,
            times=NativeRunTimes(
                started_at_ms,
                self.host.kernel.timestamp(started_at_ms),
            ),
        )
        proposal: ProposedCompletion | None = None
        decision: CompletionDecisionReceipt | None = None
        if result.candidate_completed and completion_mode is not CompletionMode.RECORD:
            proposal = self.host.propose_native_completion(recorded)
        if proposal is not None and completion_mode is CompletionMode.ADJUDICATE:
            assert self.artifact_exists is not None
            assert self.acceptance_verifier is not None
            decision = self.host.adjudicate_completion(
                proposal,
                artifact_exists=self.artifact_exists,
                acceptance_verifier=self.acceptance_verifier,
                verification_method=self.verification_method,
            )
        return HarnessExecutionResult(
            task_id=committed.assignment.task_id,
            assignment_id=committed.assignment.assignment_id,
            harness_run_id=native.harness_run_id,
            loop_result=result,
            recorded=recorded,
            proposal=proposal,
            decision=decision,
        )

    def _validate_completion_mode(self, completion_mode: CompletionMode) -> None:
        if completion_mode is CompletionMode.ADJUDICATE and (
            self.artifact_exists is None or self.acceptance_verifier is None
        ):
            raise HarnessLifecycleError(
                "adjudicate completion mode requires artifact_exists and acceptance_verifier"
            )

    def _validate_execution_entry(
        self,
        committed: CommittedHarnessAssignment,
        *,
        retained: StoredHarnessRunSnapshot | None,
    ) -> None:
        snapshot = self.host.storage.read_task_event(committed.assignment.task_id)
        if not isinstance(snapshot.data, dict):
            raise HarnessLifecycleError("Task head data is not an object")
        if isinstance(snapshot.data.get("harnessRunTerminationCode"), str):
            raise HarnessLifecycleError(
                "current Harness Run is already recorded; create a replacement Assignment"
            )
        has_snapshot = isinstance(
            snapshot.data.get("harnessRunSnapshotObjectDigest"), str
        )
        if retained is None and has_snapshot:
            raise HarnessLifecycleError(
                "current Harness Run has a durable Snapshot; use resume instead of run"
            )
        if retained is not None and not has_snapshot:
            raise HarnessLifecycleError(
                "Harness Run resume Snapshot is no longer current"
            )
        if retained is not None and (
            snapshot.data.get("harnessRunSnapshotObjectDigest")
            != retained.snapshot_object.digest
            or snapshot.data.get("harnessRunSnapshotDigest")
            != retained.snapshot.digest
            or snapshot.data.get("harnessRunStateObjectDigest")
            != retained.state_object.digest
        ):
            raise HarnessLifecycleError(
                "Harness Run resume Snapshot is no longer the exact current Snapshot"
            )

    def _load_context(self, committed: CommittedHarnessAssignment) -> CompiledContext:
        value = self.host.storage.objects.get(
            committed.assignment.context_object_digest,
            expected_kind="compiled-context",
        )
        if not isinstance(value, dict):
            raise HarnessLifecycleError("persisted Harness Context is not an object")
        return CompiledContext.from_dict(value)

    def _budget_from_assignment(
        self, committed: CommittedHarnessAssignment
    ) -> RunBudget:
        raw = committed.assignment.budget
        defaults = self.default_budget

        def read(
            name: str,
            fallback: int,
            *,
            allow_zero: bool = False,
        ) -> int:
            value = raw.get(name)
            minimum = 0 if allow_zero else 1
            return value if type(value) is int and value >= minimum else fallback

        return RunBudget(
            read("maxModelCalls", defaults.max_model_calls),
            read("maxToolCalls", defaults.max_tool_calls),
            read("maxObservationBytes", defaults.max_observation_bytes),
            read("maxWallTimeMs", defaults.max_wall_time_ms),
            read("maxTotalTokens", defaults.max_total_tokens),
            read(
                "maxModelRetries",
                defaults.max_model_retries,
                allow_zero=True,
            ),
            read(
                "maxToolCorrections",
                defaults.max_tool_corrections,
                allow_zero=True,
            ),
            read(
                "maxObservationOnlyTurns",
                defaults.max_observation_only_turns,
                allow_zero=True,
            ),
            read(
                "maxNoProgressTurns",
                defaults.max_no_progress_turns,
                allow_zero=True,
            ),
            read(
                "maxModelObservationBytes",
                defaults.max_model_observation_bytes,
            ),
        )

    @staticmethod
    def _budget_to_assignment(budget: RunBudget) -> dict[str, JsonValue]:
        return budget.to_contract_dict()

    def _require_runtime(self) -> RuntimeClient:
        if self.runtime is None:
            raise HarnessLifecycleError(
                "Harness Runner operation requires a Runtime client"
            )
        return self.runtime

    def _require_adapter(self) -> AgentTurnAdapter:
        if self.adapter is None:
            raise HarnessLifecycleError(
                "Harness Runner operation requires a Provider adapter"
            )
        return self.adapter

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) else None


__all__ = [
    "CompletionMode",
    "HarnessCancellationResult",
    "HarnessExecutionResult",
    "HarnessRunPlan",
    "HarnessRunner",
    "HarnessStatus",
    "RunHandle",
]

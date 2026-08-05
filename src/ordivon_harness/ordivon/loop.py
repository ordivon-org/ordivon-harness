from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from anc_canonical import JsonValue, canonical_bytes

from ..protocol import HarnessProviderCallFailureReceipt
from .control import CancellationToken, ExecutionControl, RunDeadline
from .events import HarnessRunEvent, HarnessTrace, TraceRecorder
from .model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnAdapter,
    AgentTurnAdapterError,
    AgentTurnCallHandle,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
    AgentTurnRequest,
)
from .run_store_port import StoredHarnessRunSnapshot
from .run_recovery import (
    _observation_evidence_signature,
    _path_subsumes,
    _recover_tool_batch,
    _retained_tool_calls,
    _search_evidence,
)
from .tool_bridge import ToolBridge, ToolObservation
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind

_OBSERVATION_ONLY_TOOLS = frozenset(
    {
        "read_workspace",
        "search_workspace",
        "diff_workspace",
        "observe_job",
        "read_artifact",
    }
)


def _is_sha256_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


class RunStopCode(str, Enum):
    CANDIDATE_COMPLETED = "candidate_completed"
    NEEDS_INPUT = "needs_input"
    NO_PROGRESS = "no_progress"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    CANCEL_UNKNOWN = "cancel_unknown"
    PROVIDER_FAILED = "provider_failed"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_TRANSPORT_FAILED = "provider_transport_failed"
    PROVIDER_REJECTED = "provider_rejected"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_STATE_UNKNOWN = "provider_state_unknown"
    INVALID_TOOL_CALL = "invalid_tool_call"
    RUNTIME_UNKNOWN = "runtime_unknown"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    HARNESS_FAILED = "harness_failed"


@dataclass(frozen=True, slots=True)
class RunBudget:
    max_model_calls: int
    max_tool_calls: int
    max_observation_bytes: int
    max_wall_time_ms: int
    max_total_tokens: int = 131_072
    max_model_retries: int = 2
    max_tool_corrections: int = 3
    max_observation_only_turns: int = 6
    max_no_progress_turns: int = 3
    max_model_observation_bytes: int = 32_768

    def __post_init__(self) -> None:
        if (
            min(
                self.max_model_calls,
                self.max_tool_calls,
                self.max_observation_bytes,
                self.max_wall_time_ms,
                self.max_total_tokens,
            )
            < 1
        ):
            raise ValueError("Ordivon Harness primary budgets must be positive")
        if (
            self.max_model_retries < 0
            or self.max_tool_corrections < 0
            or self.max_observation_only_turns < 0
            or self.max_no_progress_turns < 0
        ):
            raise ValueError("Ordivon Harness secondary budgets must be non-negative")
        if self.max_model_observation_bytes < 1:
            raise ValueError("Ordivon Harness Observation message bound must be positive")

    def remaining(
        self,
        *,
        model_calls: int,
        tool_calls: int,
        observation_bytes: int,
        elapsed_ms: int,
        total_tokens: int = 0,
        model_retries: int = 0,
        tool_corrections: int = 0,
        observation_only_turns: int = 0,
        no_progress_turns: int = 0,
    ) -> dict[str, JsonValue]:
        return {
            "modelCalls": max(0, self.max_model_calls - model_calls),
            "toolCalls": max(0, self.max_tool_calls - tool_calls),
            "observationBytes": max(0, self.max_observation_bytes - observation_bytes),
            "wallTimeMs": max(0, self.max_wall_time_ms - elapsed_ms),
            "totalTokens": max(0, self.max_total_tokens - total_tokens),
            "modelRetries": max(0, self.max_model_retries - model_retries),
            "toolCorrections": max(0, self.max_tool_corrections - tool_corrections),
            "observationOnlyTurns": max(
                0, self.max_observation_only_turns - observation_only_turns
            ),
            "noProgressTurns": max(
                0, self.max_no_progress_turns - no_progress_turns
            ),
        }


@dataclass(frozen=True, slots=True)
class AgentLoopResult:
    harness_run_id: str
    stop_code: RunStopCode
    trace: HarnessTrace
    conclusion: AgentRunConclusion | None
    messages: tuple[dict[str, JsonValue], ...]
    observations: tuple[ToolObservation, ...]
    model_calls: int
    tool_calls: int
    observation_bytes: int
    usage: dict[str, JsonValue]

    @property
    def candidate_completed(self) -> bool:
        return self.stop_code is RunStopCode.CANDIDATE_COMPLETED


class OrdivonAgentLoop:
    """Thin sequential Loop. Host Task and Runtime Job lifecycles remain external."""

    def __init__(
        self,
        adapter: AgentTurnAdapter,
        tool_bridge: ToolBridge,
        *,
        budget: RunBudget,
        clock_ms: Callable[[], int] | None = None,
        monotonic_ms: Callable[[], int] | None = None,
        assignment_deadline_ms: int | None = None,
        event_sink: Callable[[HarnessRunEvent], None] | None = None,
    ) -> None:
        self.adapter = adapter
        self.tool_bridge = tool_bridge
        self.budget = budget
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic_ms = monotonic_ms or (
            lambda: time.monotonic_ns() // 1_000_000
        )
        if assignment_deadline_ms is not None and assignment_deadline_ms < 0:
            raise ValueError("Assignment deadline must be non-negative")
        self.assignment_deadline_ms = assignment_deadline_ms
        self.event_sink = event_sink
        configure_provider = getattr(
            self.tool_bridge,
            "configure_provider_call",
            None,
        )
        if callable(configure_provider):
            configure_provider(
                adapter_id=self.adapter.adapter_id,
                requested_model_id=self.adapter.model_id,
            )

    def run(
        self,
        *,
        harness_run_id: str,
        assignment_id: str,
        context_digest: str,
        initial_messages: tuple[dict[str, JsonValue], ...],
        cancellation: CancellationToken | None = None,
    ) -> AgentLoopResult:
        return self._run(
            harness_run_id=harness_run_id,
            assignment_id=assignment_id,
            context_digest=context_digest,
            initial_messages=initial_messages,
            cancellation=cancellation,
            retained=None,
        )

    def resume(
        self,
        *,
        retained: StoredHarnessRunSnapshot,
        assignment_id: str,
        context_digest: str,
        additional_messages: tuple[dict[str, JsonValue], ...] = (),
        cancellation: CancellationToken | None = None,
    ) -> AgentLoopResult:
        return self._run(
            harness_run_id=retained.snapshot.harness_run_id,
            assignment_id=assignment_id,
            context_digest=context_digest,
            initial_messages=additional_messages,
            cancellation=cancellation,
            retained=retained,
        )

    @staticmethod
    def _cancel_and_drain_model_call(handle: AgentTurnCallHandle) -> None:
        handle.cancel()
        try:
            handle.poll(0.5)
        except Exception:  # noqa: BLE001 - cancellation drain is best effort.
            return

    def _run(
        self,
        *,
        harness_run_id: str,
        assignment_id: str,
        context_digest: str,
        initial_messages: tuple[dict[str, JsonValue], ...],
        cancellation: CancellationToken | None,
        retained: StoredHarnessRunSnapshot | None,
    ) -> AgentLoopResult:
        cancellation = cancellation or CancellationToken(monotonic_ms=self.monotonic_ms)
        prior_elapsed_ms = 0
        provider_result_replays = 0
        if retained is None:
            remaining_wall_time_ms = self.budget.max_wall_time_ms
            messages = [dict(message) for message in initial_messages]
            observations: list[ToolObservation] = []
            provider_usage: list[dict[str, JsonValue]] = []
            effective_models: list[str] = []
            seen_model_call_ids: set[str] = set()
            seen_tool_call_ids: set[str] = set()
            model_calls = 0
            tool_calls = 0
            observation_bytes = 0
            total_tokens = 0
            model_retries = 0
            tool_corrections = 0
            observation_only_turns = 0
            no_progress_turns = 0
            provider_attempts = 0
        else:
            snapshot = retained.snapshot
            state = retained.state
            restore_provider_state = getattr(
                self.tool_bridge,
                "restore_provider_replay_state",
                None,
            )
            if callable(restore_provider_state):
                provider_state = restore_provider_state(
                    snapshot=retained,
                    additional_messages=initial_messages,
                )
                if provider_state is not None:
                    state = provider_state
                    initial_messages = ()
            if (
                snapshot.harness_run_id != harness_run_id
                or snapshot.assignment_id != assignment_id
                or snapshot.tool_catalog_digest != self.tool_bridge.catalog_digest
                or state.requested_model_id != self.adapter.model_id
            ):
                raise ValueError("Harness Run resume identities differ")
            remaining = state.remaining_budget
            required_budget_fields = {
                "modelCalls",
                "toolCalls",
                "observationBytes",
                "wallTimeMs",
            }
            optional_budget_fields = {
                "totalTokens",
                "modelRetries",
                "toolCorrections",
                "observationOnlyTurns",
                "noProgressTurns",
            }
            if (
                not required_budget_fields.issubset(remaining)
                or not set(remaining).issubset(
                    required_budget_fields | optional_budget_fields
                )
                or any(
                    type(remaining[field]) is not int or remaining[field] < 0
                    for field in remaining
                )
            ):
                raise ValueError("Harness Run resume budget is invalid")
            model_calls = self.budget.max_model_calls - int(remaining["modelCalls"])
            tool_calls = self.budget.max_tool_calls - int(remaining["toolCalls"])
            observation_bytes = self.budget.max_observation_bytes - int(
                remaining["observationBytes"]
            )
            retained_wall_time_ms = int(remaining["wallTimeMs"])
            if state.active_elapsed_ms is None:
                prior_elapsed_ms = (
                    self.budget.max_wall_time_ms - retained_wall_time_ms
                )
            else:
                prior_elapsed_ms = state.active_elapsed_ms
                expected_wall_time_ms = max(
                    0,
                    self.budget.max_wall_time_ms - prior_elapsed_ms,
                )
                if retained_wall_time_ms != expected_wall_time_ms:
                    raise ValueError(
                        "Harness Run active elapsed time differs from its wall budget"
                    )
            total_tokens = self.budget.max_total_tokens - int(
                remaining.get("totalTokens", self.budget.max_total_tokens)
            )
            model_retries = self.budget.max_model_retries - int(
                remaining.get("modelRetries", self.budget.max_model_retries)
            )
            tool_corrections = self.budget.max_tool_corrections - int(
                remaining.get("toolCorrections", self.budget.max_tool_corrections)
            )
            observation_only_turns = (
                self.budget.max_observation_only_turns
                - int(
                    remaining.get(
                        "observationOnlyTurns",
                        self.budget.max_observation_only_turns,
                    )
                )
            )
            no_progress_turns = self.budget.max_no_progress_turns - int(
                remaining.get(
                    "noProgressTurns",
                    self.budget.max_no_progress_turns,
                )
            )
            if initial_messages:
                observation_only_turns = 0
                no_progress_turns = 0
            provider_attempts = model_calls + model_retries
            if (
                min(
                    model_calls,
                    tool_calls,
                    observation_bytes,
                    prior_elapsed_ms,
                    total_tokens,
                    model_retries,
                    tool_corrections,
                    observation_only_turns,
                    no_progress_turns,
                )
                < 0
            ):
                raise ValueError("Harness Run resume budget exceeds configured limits")
            remaining_wall_time_ms = retained_wall_time_ms
            messages = [dict(message) for message in state.messages]
            messages.extend(dict(message) for message in initial_messages)
            observations = [
                ToolObservation.from_dict(item) for item in state.observations
            ]
            provider_usage = [dict(item) for item in state.provider_usage]
            effective_models = list(state.effective_model_ids)
            if not effective_models and state.effective_model_id is not None:
                effective_models.append(state.effective_model_id)
            seen_model_call_ids = set(state.seen_model_call_ids)
            seen_tool_call_ids = set(state.seen_tool_call_ids)
            restorer = getattr(self.tool_bridge, "restore_seen_tool_calls", None)
            if callable(restorer):
                restorer(tuple(sorted(seen_tool_call_ids)))

        retained_calls = _retained_tool_calls(messages)
        evidence_signatures: set[str] = set()
        search_evidence: dict[tuple[str, str], set[str]] = {}
        for observation in observations:
            if observation.status != "observed":
                continue
            call = retained_calls.get(observation.tool_call_id)
            if observation.tool_name == "search_workspace" and call is not None:
                search_key, matches = _search_evidence(call, observation)
                search_evidence.setdefault(search_key, set()).update(matches)
            else:
                evidence_signatures.add(
                    _observation_evidence_signature(observation)
                )

        observed_wall_time_ms = self.clock_ms()
        if observed_wall_time_ms < 0:
            raise ValueError("Harness wall clock returned a negative time")
        assignment_remaining_ms = (
            None
            if self.assignment_deadline_ms is None
            else max(0, self.assignment_deadline_ms - observed_wall_time_ms)
        )
        effective_remaining_ms = remaining_wall_time_ms
        deadline_source = "active_wall_time"
        if (
            assignment_remaining_ms is not None
            and assignment_remaining_ms <= effective_remaining_ms
        ):
            effective_remaining_ms = assignment_remaining_ms
            deadline_source = "assignment_deadline"
        started_at_ms = self.monotonic_ms()
        deadline = RunDeadline(
            started_at_ms + effective_remaining_ms,
            self.monotonic_ms,
        )
        control = ExecutionControl(cancellation, deadline)
        recorder = TraceRecorder(
            harness_run_id, clock_ms=self.clock_ms, event_sink=self.event_sink
        )
        recorder.record(
            "run_resumed" if retained is not None else "run_started",
            {
                "assignmentId": assignment_id,
                "contextDigest": context_digest,
                "toolCatalogDigest": self.tool_bridge.catalog_digest,
                "adapterId": self.adapter.adapter_id,
                "requestedModelId": self.adapter.model_id,
                "deadlineMonotonicMs": deadline.expires_at_ms,
                "deadlineSource": deadline_source,
                "assignmentDeadlineMs": self.assignment_deadline_ms,
                "assignmentRemainingMs": assignment_remaining_ms,
                "activeRemainingMs": remaining_wall_time_ms,
                "priorElapsedMs": prior_elapsed_ms,
                "snapshotDigest": (
                    None if retained is None else retained.snapshot.digest
                ),
            },
        )

        def elapsed_ms() -> int:
            return prior_elapsed_ms + max(0, self.monotonic_ms() - started_at_ms)

        def assignment_deadline_expired() -> bool:
            return (
                self.assignment_deadline_ms is not None
                and self.clock_ms() >= self.assignment_deadline_ms
            )

        def execution_deadline_expired() -> bool:
            return deadline.expired or assignment_deadline_expired()

        def bind_run_state() -> None:
            binder = getattr(self.tool_bridge, "bind_run_state", None)
            if not callable(binder):
                return
            active_elapsed_ms = elapsed_ms()
            binder(
                messages=tuple(messages),
                observations=tuple(observations),
                remaining_budget=self.budget.remaining(
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                    observation_bytes=observation_bytes,
                    elapsed_ms=active_elapsed_ms,
                    total_tokens=total_tokens,
                    model_retries=model_retries,
                    tool_corrections=tool_corrections,
                    observation_only_turns=observation_only_turns,
                    no_progress_turns=no_progress_turns,
                ),
                requested_model_id=self.adapter.model_id,
                effective_model_id=(effective_models[-1] if effective_models else None),
                active_elapsed_ms=active_elapsed_ms,
                seen_model_call_ids=tuple(sorted(seen_model_call_ids)),
                seen_tool_call_ids=tuple(sorted(seen_tool_call_ids)),
                provider_usage=tuple(provider_usage),
                effective_model_ids=tuple(dict.fromkeys(effective_models)),
            )

        def stop(
            code: RunStopCode,
            *,
            conclusion: AgentRunConclusion | None = None,
            detail: str | None = None,
        ) -> AgentLoopResult:
            elapsed = elapsed_ms()
            payload: dict[str, JsonValue] = {
                "stopCode": code.value,
                "modelCalls": model_calls,
                "toolCalls": tool_calls,
                "observationBytes": observation_bytes,
                "totalTokens": total_tokens,
                "modelRetries": model_retries,
                "toolCorrections": tool_corrections,
                "observationOnlyTurns": observation_only_turns,
                "noProgressTurns": no_progress_turns,
                "providerAttempts": provider_attempts,
                "providerResultsReplayed": provider_result_replays,
                "elapsedMs": elapsed,
                "deadlineOverrunMs": max(0, elapsed - self.budget.max_wall_time_ms),
            }
            if detail is not None:
                payload["detail"] = detail[:2_048]
            recorder.record("run_stopped", payload)
            return AgentLoopResult(
                harness_run_id=harness_run_id,
                stop_code=code,
                trace=recorder.freeze(),
                conclusion=conclusion,
                messages=tuple(messages),
                observations=tuple(observations),
                model_calls=model_calls,
                tool_calls=tool_calls,
                observation_bytes=observation_bytes,
                usage={
                    "modelCalls": model_calls,
                    "toolCalls": tool_calls,
                    "observationBytes": observation_bytes,
                    "totalTokens": total_tokens,
                    "tokenLimit": self.budget.max_total_tokens,
                    "modelRetries": model_retries,
                    "toolCorrections": tool_corrections,
                    "observationOnlyTurns": observation_only_turns,
                    "observationOnlyTurnLimit": self.budget.max_observation_only_turns,
                    "noProgressTurns": no_progress_turns,
                    "noProgressTurnLimit": self.budget.max_no_progress_turns,
                    "modelObservationByteLimit": (
                        self.budget.max_model_observation_bytes
                    ),
                    "providerAttempts": provider_attempts,
                    "providerResultsReplayed": provider_result_replays,
                    "wallTimeMs": elapsed,
                    "deadlineOverrunMs": max(0, elapsed - self.budget.max_wall_time_ms),
                    "requestedModelId": self.adapter.model_id,
                    "effectiveModelIds": list(dict.fromkeys(effective_models)),
                    "providerUsage": provider_usage,
                },
            )

        def retain_tool_observation(
            call: AgentToolCall,
            observation: ToolObservation,
            *,
            turn_observations: list[ToolObservation],
            step_id: str | None,
            reconciled: bool,
        ) -> AgentLoopResult | None:
            nonlocal observation_bytes, tool_calls, tool_corrections
            tool_calls += 1
            remaining_observation_bytes = (
                self.budget.max_observation_bytes - observation_bytes
            )
            bounded = getattr(observation, "bounded", None)
            if callable(bounded):
                observation = bounded(
                    min(
                        remaining_observation_bytes,
                        self.budget.max_model_observation_bytes,
                    )
                )
            encoded_size = len(canonical_bytes(observation.to_dict()))
            if encoded_size > remaining_observation_bytes:
                return stop(
                    RunStopCode.BUDGET_EXHAUSTED,
                    detail=(
                        "reconciled Tool Observation exceeds the remaining Run budget"
                        if reconciled
                        else "Tool Observation exceeds the remaining Run budget"
                    ),
                )
            observations.append(observation)
            turn_observations.append(observation)
            observation_bytes += encoded_size
            if reconciled:
                recorder.record(
                    "tool_call_reconciled",
                    {
                        "toolCallId": observation.tool_call_id,
                        "toolName": observation.tool_name,
                        "observationDigest": observation.digest,
                        "runtimeJobRef": observation.runtime_job_ref,
                        "status": observation.status,
                        "encodedBytes": encoded_size,
                    },
                )
            else:
                if observation.status != "rejected":
                    recorder.record(
                        "tool_call_dispatched",
                        {
                            "toolCallId": call.tool_call_id,
                            "toolName": call.name,
                            "stepId": step_id,
                            "runtimeJobRef": observation.runtime_job_ref,
                        },
                    )
                event_kind = {
                    "observed": "tool_call_observed",
                    "rejected": "tool_call_rejected",
                    "unknown": "tool_call_unknown",
                    "cancel-requested": "tool_call_cancel_requested",
                    "cancelled": "tool_call_cancelled",
                }[observation.status]
                recorder.record(
                    event_kind,
                    {
                        "toolCallId": call.tool_call_id,
                        "toolName": call.name,
                        "observationDigest": observation.digest,
                        "runtimeJobRef": observation.runtime_job_ref,
                        "reconciled": observation.reconciled,
                        "encodedBytes": encoded_size,
                    },
                )
            messages.append(observation.to_model_message())
            error_value = observation.structured_content.get("error")
            safe_to_correct = (
                error_value.get("safeToCorrect") is True
                if isinstance(error_value, dict)
                else False
            )
            control_stopped_before_dispatch = (
                error_value.get("type") == "execution_control_stopped"
                and error_value.get("physicalDispatch") is False
                and error_value.get("commitState") == "not_started"
                if isinstance(error_value, dict)
                else False
            )
            if (
                observation.status == "rejected"
                and not safe_to_correct
                and not control_stopped_before_dispatch
            ):
                if tool_corrections >= self.budget.max_tool_corrections:
                    return stop(
                        RunStopCode.INVALID_TOOL_CALL,
                        detail=(
                            "Tool correction budget exhausted after Runtime rejection"
                        ),
                    )
                tool_corrections += 1
            if observation.status == "unknown":
                return stop(
                    RunStopCode.RUNTIME_UNKNOWN,
                    detail=(
                        f"Tool Call {call.tool_call_id} has uncertain delivery or outcome"
                    ),
                )
            if observation.status == "cancel-requested":
                return stop(
                    RunStopCode.CANCEL_UNKNOWN,
                    detail=(
                        f"Tool Call {call.tool_call_id} cancellation is unconfirmed"
                    ),
                )
            if observation.status == "cancelled":
                return stop(RunStopCode.CANCELLED)
            return None

        def execute_tool_calls(
            calls: tuple[AgentToolCall, ...],
            *,
            turn_id: str,
            sequence: int,
            turn_observations: list[ToolObservation],
        ) -> AgentLoopResult | None:
            nonlocal tool_calls, tool_corrections
            for call in calls:
                if call.tool_call_id in seen_tool_call_ids:
                    return stop(
                        RunStopCode.INVALID_MODEL_OUTPUT,
                        detail=f"duplicate Tool Call identity: {call.tool_call_id}",
                    )
                seen_tool_call_ids.add(call.tool_call_id)
                if cancellation.cancelled:
                    return stop(RunStopCode.CANCELLED)
                if execution_deadline_expired():
                    return stop(RunStopCode.BUDGET_EXHAUSTED)
                recorder.record(
                    "tool_call_proposed",
                    {
                        "toolCallId": call.tool_call_id,
                        "toolName": call.name,
                        "toolCallDigest": call.digest,
                        "toolCall": call.to_dict(),
                    },
                )
                step_id = f"turn-{sequence}-tool-{tool_calls + 1}:{call.tool_call_id}"
                try:
                    if call.argument_error is not None:
                        raise ToolBridgeError(
                            (
                                f"Provider Tool Call {call.name} arguments were "
                                f"rejected ({call.argument_error}); raw digest "
                                f"{call.raw_arguments_digest}"
                            ),
                            kind=ToolBridgeErrorKind.MODEL_CORRECTABLE,
                        )
                    bind_run_state()
                    controlled_execute = getattr(
                        self.tool_bridge, "execute_with_control", None
                    )
                    observation = (
                        controlled_execute(
                            call,
                            step_id=step_id,
                            turn_id=turn_id,
                            control=control,
                        )
                        if callable(controlled_execute)
                        else self.tool_bridge.execute(call, step_id=step_id)
                    )
                except ToolBridgeError as error:
                    if error.kind is ToolBridgeErrorKind.CONTROL_STOPPED:
                        return stop(
                            (
                                RunStopCode.CANCELLED
                                if cancellation.cancelled
                                else RunStopCode.BUDGET_EXHAUSTED
                            ),
                            detail=str(error),
                        )
                    if not error.recoverable_by_model:
                        return stop(RunStopCode.INVALID_TOOL_CALL, detail=str(error))
                    if tool_corrections >= self.budget.max_tool_corrections:
                        return stop(
                            RunStopCode.INVALID_TOOL_CALL,
                            detail=(
                                "Tool correction budget exhausted after local rejection: "
                                f"{error}"
                            ),
                        )
                    tool_corrections += 1
                    observation = ToolObservation(
                        call.tool_call_id,
                        call.name,
                        "rejected",
                        {
                            "error": {
                                "type": "ToolBridgeError",
                                "kind": error.kind.value,
                                "message": str(error)[:2_048],
                                "safeToCorrect": True,
                                "correction": tool_corrections,
                            }
                        },
                    )
                except Exception as error:  # noqa: BLE001 - Tool implementation failure terminates the Run.
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=f"{type(error).__name__}: {error}",
                    )
                if (
                    cancellation.cancelled
                    and observation.runtime_job_ref is not None
                    and observation.status not in {"cancelled", "cancel-requested"}
                ):
                    cancel_observation = getattr(
                        self.tool_bridge, "cancel_observation", None
                    )
                    if callable(cancel_observation):
                        observation = cancel_observation(
                            call,
                            observation,
                            step_id=step_id,
                            control=control,
                        )
                    else:
                        tool_calls += 1
                        observations.append(observation)
                        return stop(
                            RunStopCode.CANCEL_UNKNOWN,
                            detail=(
                                "cancellation was requested after Runtime dispatch, but the "
                                "Tool Bridge cannot confirm physical cancellation"
                            ),
                        )
                stopped = retain_tool_observation(
                    call,
                    observation,
                    turn_observations=turn_observations,
                    step_id=step_id,
                    reconciled=False,
                )
                if stopped is not None:
                    return stopped
                if cancellation.cancelled:
                    return stop(RunStopCode.CANCELLED)
                if execution_deadline_expired():
                    return stop(RunStopCode.BUDGET_EXHAUSTED)
            return None

        def evaluate_turn_progress(
            calls: tuple[AgentToolCall, ...],
            turn_observations: list[ToolObservation],
            *,
            turn_id: str,
        ) -> AgentLoopResult | None:
            nonlocal no_progress_turns, observation_only_turns
            observed_tool_names = {
                observation.tool_name
                for observation in turn_observations
                if observation.status == "observed"
            }
            observation_only = bool(
                observed_tool_names
            ) and observed_tool_names.issubset(_OBSERVATION_ONLY_TOOLS)
            action_progress = bool(observed_tool_names - _OBSERVATION_ONLY_TOOLS)
            new_evidence = False
            calls_by_id = {call.tool_call_id: call for call in calls}
            for observation in turn_observations:
                if observation.status != "observed":
                    continue
                call = calls_by_id.get(observation.tool_call_id)
                if observation.tool_name == "search_workspace" and call is not None:
                    search_key, matches = _search_evidence(call, observation)
                    query, relative_path = search_key
                    subsuming = [
                        retained_matches
                        for (
                            retained_query,
                            retained_path,
                        ), retained_matches in search_evidence.items()
                        if retained_query == query
                        and _path_subsumes(retained_path, relative_path)
                    ]
                    if not subsuming or not any(
                        matches.issubset(retained_matches)
                        for retained_matches in subsuming
                    ):
                        new_evidence = True
                    search_evidence.setdefault(search_key, set()).update(matches)
                    continue
                signature = _observation_evidence_signature(observation)
                if signature not in evidence_signatures:
                    new_evidence = True
                    evidence_signatures.add(signature)
            observation_only_turns = (
                observation_only_turns + 1 if observation_only else 0
            )
            no_progress_turns = (
                0
                if action_progress or new_evidence
                else no_progress_turns + 1
            )
            recorder.record(
                "run_progress_evaluated",
                {
                    "turnId": turn_id,
                    "observationOnly": observation_only,
                    "actionProgress": action_progress,
                    "newEvidence": new_evidence,
                    "observationOnlyTurns": observation_only_turns,
                    "noProgressTurns": no_progress_turns,
                },
            )
            intervention: str | None = None
            if (
                self.budget.max_no_progress_turns > 0
                and no_progress_turns >= self.budget.max_no_progress_turns
            ):
                intervention = (
                    "Harness stopped after "
                    f"{no_progress_turns} consecutive turns without a mutation, "
                    "check, materially new bounded observation, or conclusion."
                )
            elif (
                self.budget.max_observation_only_turns > 0
                and observation_only_turns
                >= self.budget.max_observation_only_turns
            ):
                intervention = (
                    "Harness stopped after "
                    f"{observation_only_turns} consecutive observation-only turns "
                    "without a mutation, check, or conclusion."
                )
            if intervention is None:
                return None
            conclusion = AgentRunConclusion(
                "needs_input",
                intervention,
                unresolved_unknowns=(
                    "A revised plan or additional bounded input is required.",
                ),
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": f"Harness intervention: {intervention}",
                    "conclusion": conclusion.to_dict(),
                }
            )
            try:
                bind_run_state()
                pause_recorder = getattr(self.tool_bridge, "record_pause", None)
                if callable(pause_recorder):
                    pause_recorder("needs_input")
            except ToolBridgeError as error:
                return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(error))
            except Exception as error:  # noqa: BLE001 - pause persistence failure terminates the Run.
                return stop(
                    RunStopCode.HARNESS_FAILED,
                    detail=f"{type(error).__name__}: {error}",
                )
            return stop(
                RunStopCode.NO_PROGRESS,
                conclusion=conclusion,
                detail=intervention,
            )

        if remaining_wall_time_ms <= 0:
            return stop(
                RunStopCode.BUDGET_EXHAUSTED,
                detail="active wall-time budget was exhausted before execution",
            )
        if assignment_remaining_ms is not None and assignment_remaining_ms <= 0:
            return stop(
                RunStopCode.BUDGET_EXHAUSTED,
                detail="Assignment deadline expired before execution",
            )
        catalog_validator = getattr(
            self.tool_bridge,
            "validate_runtime_catalog",
            None,
        )
        if callable(catalog_validator):
            try:
                catalog_validator()
            except Exception as error:  # noqa: BLE001 - Runtime preflight becomes a Run receipt.
                return stop(
                    RunStopCode.HARNESS_FAILED,
                    detail=(
                        "Runtime Tool catalog validation failed: "
                        f"{type(error).__name__}: {error}"
                    ),
                )
        if execution_deadline_expired():
            return stop(
                RunStopCode.BUDGET_EXHAUSTED,
                detail="effective Run deadline expired during Runtime preflight",
            )

        if retained is not None and retained.snapshot.active_tool_step_intent_digests:
            intent_loader = getattr(
                self.tool_bridge,
                "current_tool_step_intent",
                None,
            )
            reconciler = getattr(self.tool_bridge, "reconcile_current_tool_step", None)
            if not callable(intent_loader) or not callable(reconciler):
                return stop(
                    RunStopCode.RUNTIME_UNKNOWN,
                    detail=(
                        "resumed Harness Run has an active Tool Step without "
                        "durable batch reconciliation"
                    ),
                )
            try:
                intent = intent_loader()
                if retained.snapshot.active_tool_step_intent_digests != (
                    intent.digest,
                ):
                    raise ValueError(
                        "active Tool Step intent differs from the retained Snapshot"
                    )
                recovered = _recover_tool_batch(
                    messages,
                    observations,
                    seen_tool_call_ids,
                    intent,
                )
            except ToolBridgeError as error:
                return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(error))
            except (KeyError, TypeError, ValueError) as error:
                return stop(
                    RunStopCode.HARNESS_FAILED,
                    detail=f"durable Tool batch recovery failed: {error}",
                )

            recovered_prior_ids = {
                observation.tool_call_id
                for observation in recovered.prior_observations
            }
            evidence_signatures.clear()
            search_evidence.clear()
            for retained_observation in observations:
                if (
                    retained_observation.status != "observed"
                    or retained_observation.tool_call_id in recovered_prior_ids
                ):
                    continue
                retained_call = retained_calls.get(
                    retained_observation.tool_call_id
                )
                if (
                    retained_observation.tool_name == "search_workspace"
                    and retained_call is not None
                ):
                    search_key, matches = _search_evidence(
                        retained_call,
                        retained_observation,
                    )
                    search_evidence.setdefault(search_key, set()).update(matches)
                else:
                    evidence_signatures.add(
                        _observation_evidence_signature(retained_observation)
                    )

            if execution_deadline_expired():
                return stop(
                    RunStopCode.BUDGET_EXHAUSTED,
                    detail="effective Run deadline expired before Tool reconciliation",
                )
            try:
                observation = reconciler(control=control)
            except ToolBridgeError as error:
                if error.kind is ToolBridgeErrorKind.CONTROL_STOPPED:
                    return stop(
                        (
                            RunStopCode.CANCELLED
                            if cancellation.cancelled
                            else RunStopCode.BUDGET_EXHAUSTED
                        ),
                        detail=str(error),
                    )
                return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(error))
            except Exception as error:  # noqa: BLE001 - Run boundary converts component failure to a receipt.
                return stop(
                    RunStopCode.HARNESS_FAILED,
                    detail=f"{type(error).__name__}: {error}",
                )
            if (
                observation.tool_call_id != recovered.active_call.tool_call_id
                or observation.tool_name != recovered.active_call.name
            ):
                return stop(
                    RunStopCode.RUNTIME_UNKNOWN,
                    detail=(
                        "reconciled Tool Observation differs from the durable "
                        "batch cursor"
                    ),
                )
            turn_observations = list(recovered.prior_observations)
            stopped = retain_tool_observation(
                recovered.active_call,
                observation,
                turn_observations=turn_observations,
                step_id=None,
                reconciled=True,
            )
            if stopped is not None:
                return stopped
            if (
                tool_calls + len(recovered.pending_calls)
                > self.budget.max_tool_calls
            ):
                return stop(RunStopCode.BUDGET_EXHAUSTED)
            stopped = execute_tool_calls(
                recovered.pending_calls,
                turn_id=intent.turn_id,
                sequence=model_calls,
                turn_observations=turn_observations,
            )
            if stopped is not None:
                return stopped
            stopped = evaluate_turn_progress(
                recovered.calls,
                turn_observations,
                turn_id=intent.turn_id,
            )
            if stopped is not None:
                return stopped

        while True:
            if cancellation.cancelled:
                return stop(RunStopCode.CANCELLED)
            if (
                model_calls >= self.budget.max_model_calls
                or total_tokens >= self.budget.max_total_tokens
                or execution_deadline_expired()
            ):
                return stop(RunStopCode.BUDGET_EXHAUSTED)
            sequence = model_calls + 1
            turn_id = f"turn:{harness_run_id.removeprefix('harness-run:')}:{sequence}"
            request = AgentTurnRequest(
                harness_run_id=harness_run_id,
                turn_id=turn_id,
                sequence=sequence,
                assignment_id=assignment_id,
                context_digest=context_digest,
                tool_catalog_digest=self.tool_bridge.catalog_digest,
                messages=tuple(messages),
                tools=self.tool_bridge.definitions(),
                remaining_budget=self.budget.remaining(
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                    observation_bytes=observation_bytes,
                    elapsed_ms=elapsed_ms(),
                    total_tokens=total_tokens,
                    model_retries=model_retries,
                    tool_corrections=tool_corrections,
                    observation_only_turns=observation_only_turns,
                    no_progress_turns=no_progress_turns,
                ),
            )
            token_bounder = getattr(
                self.adapter, "request_token_upper_bound", None
            )
            request_token_upper_bound: int | None = None
            if callable(token_bounder):
                try:
                    request_token_upper_bound = token_bounder(request)
                except Exception as error:  # noqa: BLE001 - Adapter boundary becomes a receipt.
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=(
                            "Provider request token preflight failed: "
                            f"{type(error).__name__}: {error}"
                        ),
                    )
                if (
                    type(request_token_upper_bound) is not int
                    or request_token_upper_bound < 1
                ):
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail="Provider request token preflight returned an invalid bound",
                    )
                remaining_total_tokens = (
                    self.budget.max_total_tokens - total_tokens
                )
                recorder.record(
                    "model_call_budget_checked",
                    {
                        "turnId": turn_id,
                        "requestDigest": request.digest,
                        "requestTokenUpperBound": request_token_upper_bound,
                        "remainingTotalTokens": remaining_total_tokens,
                    },
                )
                if request_token_upper_bound > remaining_total_tokens:
                    recorder.record(
                        "model_call_budget_rejected",
                        {
                            "turnId": turn_id,
                            "requestDigest": request.digest,
                            "requestTokenUpperBound": request_token_upper_bound,
                            "remainingTotalTokens": remaining_total_tokens,
                        },
                    )
                    return stop(
                        RunStopCode.BUDGET_EXHAUSTED,
                        detail=(
                            "Provider request cannot fit the remaining total-token "
                            "budget under the Adapter's conservative bound: "
                            f"{request_token_upper_bound}>{remaining_total_tokens}"
                        ),
                    )
            if execution_deadline_expired():
                return stop(
                    RunStopCode.BUDGET_EXHAUSTED,
                    detail="effective Run deadline expired before Provider dispatch",
                )
            begin_provider_call = getattr(
                self.tool_bridge,
                "begin_provider_call",
                None,
            )
            durable_provider_call = callable(begin_provider_call) and bool(
                getattr(
                    self.tool_bridge,
                    "durable_provider_calls_enabled",
                    True,
                )
            )
            provider_request_digest: str | None = None
            if durable_provider_call:
                provider_request_identity = getattr(
                    self.adapter,
                    "provider_request_digest",
                    None,
                )
                if not callable(provider_request_identity):
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=(
                            "durable Provider Call Adapter omitted "
                            "provider_request_digest"
                        ),
                    )
                try:
                    candidate_provider_request_digest = (
                        provider_request_identity(request)
                    )
                except Exception as error:  # noqa: BLE001 - Adapter identity failure is local.
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=(
                            "Provider request identity failed before dispatch: "
                            f"{type(error).__name__}: {error}"
                        ),
                    )
                if not _is_sha256_digest(candidate_provider_request_digest):
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=(
                            "Provider request identity must be "
                            "sha256:<64 lowercase hex>"
                        ),
                    )
                provider_request_digest = candidate_provider_request_digest
            if cancellation.cancelled:
                return stop(RunStopCode.CANCELLED)
            if execution_deadline_expired():
                return stop(
                    RunStopCode.BUDGET_EXHAUSTED,
                    detail=(
                        "effective Run deadline expired during Provider "
                        "request preparation"
                    ),
                )
            bind_run_state()
            if callable(begin_provider_call):
                provider_outcome = (
                    begin_provider_call(
                        request,
                        provider_request_digest=provider_request_digest,
                    )
                    if durable_provider_call
                    else begin_provider_call(request)
                )
            else:
                provider_outcome = None
            replayed_failure = (
                provider_outcome
                if isinstance(
                    provider_outcome,
                    HarnessProviderCallFailureReceipt,
                )
                else None
            )
            result = None if replayed_failure is not None else provider_outcome
            replayed_provider_result = result is not None
            if replayed_provider_result:
                provider_attempts += 1
                provider_result_replays += 1
            recorder.record(
                "model_call_started",
                {
                    "turnId": turn_id,
                    "requestDigest": request.digest,
                    "dispatchDigest": request.dispatch_digest,
                    "agentRequestDigest": request.digest,
                    "agentDispatchDigest": request.dispatch_digest,
                    "providerRequestDigest": provider_request_digest,
                    "remainingWallTimeMs": control.remaining_ms,
                    "replayedProviderResult": replayed_provider_result,
                    "replayedProviderFailure": replayed_failure is not None,
                },
            )
            provider_attempt = 0
            while result is None:
                failure_was_replayed = replayed_failure is not None
                provider_attempt += 1
                provider_attempts += 1
                recorder.record(
                    "model_call_attempt_started",
                    {
                        "turnId": turn_id,
                        "attempt": provider_attempt,
                        "requestDigest": request.digest,
                        "agentRequestDigest": request.digest,
                        "agentDispatchDigest": request.dispatch_digest,
                        "providerRequestDigest": provider_request_digest,
                        "replayedDurableFailure": replayed_failure is not None,
                    },
                )
                if not failure_was_replayed:
                    bind_run_state()
                    admit_provider_call = getattr(
                        self.tool_bridge,
                        "admit_provider_call",
                        None,
                    )
                    if durable_provider_call:
                        if not callable(admit_provider_call):
                            return stop(
                                RunStopCode.HARNESS_FAILED,
                                detail=(
                                    "durable Provider Call bridge omitted "
                                    "dispatch admission"
                                ),
                            )
                        try:
                            admitted = admit_provider_call(
                                request,
                                control=control,
                            )
                        except Exception as error:  # noqa: BLE001 - admission is local durable state.
                            return stop(
                                RunStopCode.HARNESS_FAILED,
                                detail=(
                                    "Provider dispatch admission failed: "
                                    f"{type(error).__name__}: {error}"
                                ),
                            )
                        if not admitted:
                            return stop(
                                (
                                    RunStopCode.CANCELLED
                                    if cancellation.cancelled
                                    else RunStopCode.BUDGET_EXHAUSTED
                                ),
                                detail=(
                                    "Provider dispatch admission closed before "
                                    "physical invocation"
                                ),
                            )
                    elif cancellation.cancelled:
                        return stop(RunStopCode.CANCELLED)
                    elif execution_deadline_expired():
                        return stop(
                            RunStopCode.BUDGET_EXHAUSTED,
                            detail=(
                                "effective Run deadline expired at Provider "
                                "dispatch admission"
                            ),
                        )
                try:
                    if replayed_failure is not None:
                        durable_failure = replayed_failure
                        replayed_failure = None
                        raise AgentTurnAdapterError(
                            durable_failure.detail,
                            failure_code=AgentTurnFailureCode(
                                durable_failure.failure_code
                            ),
                            dispatch_safety=AgentTurnDispatchSafety(
                                durable_failure.dispatch_safety
                            ),
                        )
                    start_invoke = getattr(self.adapter, "start_invoke", None)
                    supports_handle = getattr(
                        self.adapter, "supports_call_handle", True
                    )
                    if callable(start_invoke) and supports_handle:
                        handle = start_invoke(request, control)
                        while True:
                            if (
                                cancellation.cancelled
                                or execution_deadline_expired()
                            ):
                                self._cancel_and_drain_model_call(handle)
                                interrupted = AgentTurnAdapterError(
                                    (
                                        "Provider cancellation outcome is unknown"
                                        if cancellation.cancelled
                                        else "Provider deadline outcome is unknown"
                                    ),
                                    failure_code=AgentTurnFailureCode.TIMEOUT,
                                    dispatch_safety=(
                                        AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS
                                    ),
                                )
                                failure_recorder = getattr(
                                    self.tool_bridge,
                                    "fail_provider_call",
                                    None,
                                )
                                if callable(failure_recorder):
                                    bind_run_state()
                                    failure_recorder(
                                        request,
                                        interrupted,
                                        unknown=True,
                                    )
                                return stop(
                                    (
                                        RunStopCode.CANCEL_UNKNOWN
                                        if cancellation.cancelled
                                        else RunStopCode.PROVIDER_STATE_UNKNOWN
                                    ),
                                    detail=str(interrupted),
                                )
                            result = handle.poll(
                                min(
                                    0.05,
                                    max(0.001, control.remaining_ms / 1_000),
                                )
                            )
                            if result is not None:
                                break
                    else:
                        controlled_invoke = getattr(
                            self.adapter, "invoke_with_control", None
                        )
                        result = (
                            controlled_invoke(request, control)
                            if callable(controlled_invoke)
                            else self.adapter.invoke(request)
                        )
                except AgentTurnAdapterError as error:
                    unknown = (
                        error.dispatch_safety
                        is AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS
                    )
                    failure_recorder = getattr(
                        self.tool_bridge,
                        "fail_provider_call",
                        None,
                    )
                    if callable(failure_recorder) and not failure_was_replayed:
                        bind_run_state()
                        failure_recorder(request, error, unknown=unknown)
                    recorder.record(
                        "model_call_attempt_failed",
                        {
                            "turnId": turn_id,
                            "attempt": provider_attempt,
                            "failureCode": error.failure_code.value,
                            "dispatchSafety": error.dispatch_safety.value,
                            "providerRequestDigest": provider_request_digest,
                            "detail": str(error)[:2_048],
                            "replayedDurableFailure": failure_was_replayed,
                        },
                    )
                    retryable = (
                        error.dispatch_safety
                        is AgentTurnDispatchSafety.PRE_DISPATCH_SAFE
                        and error.failure_code
                        in {
                            AgentTurnFailureCode.TRANSPORT_FAILED,
                            AgentTurnFailureCode.UNAVAILABLE,
                        }
                    )
                    if (
                        retryable
                        and model_retries < self.budget.max_model_retries
                        and not cancellation.cancelled
                        and control.remaining_ms > 1
                        and not assignment_deadline_expired()
                    ):
                        model_retries += 1
                        delay_ms = min(
                            2_000,
                            250 * (2 ** min(model_retries - 1, 3)),
                            max(0, control.remaining_ms - 1),
                        )
                        recorder.record(
                            "model_call_retry_scheduled",
                            {
                                "turnId": turn_id,
                                "attempt": provider_attempt,
                                "retry": model_retries,
                                "delayMs": delay_ms,
                                "failureCode": error.failure_code.value,
                            },
                        )
                        slept_ms = 0
                        while slept_ms < delay_ms:
                            if (
                                cancellation.cancelled
                                or execution_deadline_expired()
                            ):
                                return stop(
                                    RunStopCode.CANCELLED
                                    if cancellation.cancelled
                                    else RunStopCode.BUDGET_EXHAUSTED,
                                    detail=str(error),
                                )
                            slice_ms = min(50, delay_ms - slept_ms)
                            time.sleep(slice_ms / 1_000)
                            slept_ms += slice_ms
                        bind_run_state()
                        retry_provider_call = getattr(
                            self.tool_bridge,
                            "retry_provider_call",
                            None,
                        )
                        if callable(retry_provider_call):
                            retry_provider_call(request)
                        continue
                    if unknown:
                        return stop(
                            RunStopCode.PROVIDER_STATE_UNKNOWN,
                            detail=str(error),
                        )
                    stop_code = {
                        AgentTurnFailureCode.FAILED: RunStopCode.PROVIDER_FAILED,
                        AgentTurnFailureCode.TIMEOUT: RunStopCode.PROVIDER_TIMEOUT,
                        AgentTurnFailureCode.TRANSPORT_FAILED: (
                            RunStopCode.PROVIDER_TRANSPORT_FAILED
                        ),
                        AgentTurnFailureCode.REJECTED: RunStopCode.PROVIDER_REJECTED,
                        AgentTurnFailureCode.UNAVAILABLE: RunStopCode.PROVIDER_UNAVAILABLE,
                    }[error.failure_code]
                    return stop(stop_code, detail=str(error))
                except (TypeError, ValueError) as error:
                    malformed = AgentTurnAdapterError(
                        str(error),
                        failure_code=AgentTurnFailureCode.REJECTED,
                        dispatch_safety=(
                            AgentTurnDispatchSafety.PROVIDER_REJECTED
                        ),
                    )
                    failure_recorder = getattr(
                        self.tool_bridge,
                        "fail_provider_call",
                        None,
                    )
                    if callable(failure_recorder):
                        bind_run_state()
                        failure_recorder(request, malformed, unknown=False)
                    return stop(RunStopCode.INVALID_MODEL_OUTPUT, detail=str(error))
                except Exception as error:  # noqa: BLE001 - unknown dispatch must not retry.
                    ambiguous = AgentTurnAdapterError(
                        f"{type(error).__name__}: {error}",
                        failure_code=AgentTurnFailureCode.FAILED,
                        dispatch_safety=(
                            AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS
                        ),
                    )
                    failure_recorder = getattr(
                        self.tool_bridge,
                        "fail_provider_call",
                        None,
                    )
                    if callable(failure_recorder):
                        bind_run_state()
                        failure_recorder(request, ambiguous, unknown=True)
                    return stop(
                        RunStopCode.PROVIDER_STATE_UNKNOWN,
                        detail=str(ambiguous),
                    )
                complete_provider_call = getattr(
                    self.tool_bridge,
                    "complete_provider_call",
                    None,
                )
                if callable(complete_provider_call):
                    bind_run_state()
                    complete_provider_call(request, result)
            if cancellation.cancelled:
                return stop(
                    RunStopCode.CANCELLED,
                    detail="cancellation was requested during the Provider call",
                )
            if execution_deadline_expired():
                return stop(
                    RunStopCode.BUDGET_EXHAUSTED,
                    detail="wall-time deadline expired during the Provider call",
                )
            effective_model = result.effective_model
            model_calls += 1
            effective_models.append(effective_model)
            usage = dict(result.usage)
            usage["requestedModelId"] = result.model_id
            usage["effectiveModelId"] = effective_model
            provider_usage.append(usage)
            turn_tokens = _usage_total_tokens(result.usage)
            if turn_tokens is not None:
                total_tokens += turn_tokens
            recorder.record(
                "model_call_completed",
                {
                    "turnId": turn_id,
                    "modelCallId": result.model_call_id,
                    "requestedModelId": result.model_id,
                    "effectiveModelId": effective_model,
                    "resultDigest": result.digest,
                    "rawResponseDigest": result.raw_response_digest,
                    "providerRequestDigest": provider_request_digest,
                    "finishReason": result.finish_reason,
                    "totalTokens": turn_tokens,
                    "cumulativeTotalTokens": total_tokens,
                    "normalizedResult": result.to_dict(),
                },
            )
            if total_tokens > self.budget.max_total_tokens:
                return stop(
                    RunStopCode.BUDGET_EXHAUSTED,
                    detail=(
                        "Provider token usage exceeded the configured hard limit: "
                        f"{total_tokens}>{self.budget.max_total_tokens}"
                    ),
                )
            if result.model_id != self.adapter.model_id:
                return stop(
                    RunStopCode.INVALID_MODEL_OUTPUT,
                    detail="requested model identity differs from the Adapter",
                )
            accepts_model = getattr(self.adapter, "accepts_effective_model_id", None)
            if effective_model != self.adapter.model_id and not (
                callable(accepts_model) and accepts_model(effective_model)
            ):
                return stop(
                    RunStopCode.INVALID_MODEL_OUTPUT,
                    detail=(
                        "effective Provider model identity is not admitted by the Adapter: "
                        f"{effective_model}"
                    ),
                )
            if result.model_call_id in seen_model_call_ids:
                return stop(
                    RunStopCode.INVALID_MODEL_OUTPUT,
                    detail=f"duplicate Model Call identity: {result.model_call_id}",
                )
            seen_model_call_ids.add(result.model_call_id)
            if result.conclusion is not None:
                messages.append(
                    {
                        "role": "assistant",
                        "content": result.content,
                        "conclusion": result.conclusion.to_dict(),
                    }
                )
                if result.conclusion.status == "candidate_completed":
                    return stop(
                        RunStopCode.CANDIDATE_COMPLETED,
                        conclusion=result.conclusion,
                    )
                try:
                    bind_run_state()
                    pause_recorder = getattr(self.tool_bridge, "record_pause", None)
                    if callable(pause_recorder):
                        pause_recorder("needs_input")
                except ToolBridgeError as error:
                    return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(error))
                except Exception as error:  # noqa: BLE001 - pause persistence failure terminates the Run.
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=f"{type(error).__name__}: {error}",
                    )
                return stop(RunStopCode.NEEDS_INPUT, conclusion=result.conclusion)

            if tool_calls + len(result.tool_calls) > self.budget.max_tool_calls:
                return stop(RunStopCode.BUDGET_EXHAUSTED)
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content,
                    "toolCalls": [call.to_dict() for call in result.tool_calls],
                }
            )
            turn_observations: list[ToolObservation] = []
            stopped = execute_tool_calls(
                result.tool_calls,
                turn_id=turn_id,
                sequence=sequence,
                turn_observations=turn_observations,
            )
            if stopped is not None:
                return stopped

            stopped = evaluate_turn_progress(
                result.tool_calls,
                turn_observations,
                turn_id=turn_id,
            )
            if stopped is not None:
                return stopped












def _usage_total_tokens(usage: dict[str, JsonValue]) -> int | None:
    for key in ("total_tokens", "totalTokens"):
        value = usage.get(key)
        if type(value) is int and value >= 0:
            return value
    prompt = usage.get("prompt_tokens", usage.get("promptTokens"))
    completion = usage.get("completion_tokens", usage.get("completionTokens"))
    if (
        type(prompt) is int
        and prompt >= 0
        and type(completion) is int
        and completion >= 0
    ):
        return prompt + completion
    return None

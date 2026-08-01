from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from anc_canonical import JsonValue, canonical_bytes

from .control import CancellationToken, ExecutionControl, RunDeadline
from .events import HarnessTrace, TraceRecorder
from .model import (
    AgentRunConclusion,
    AgentTurnAdapter,
    AgentTurnAdapterError,
    AgentTurnCallHandle,
    AgentTurnFailureCode,
    AgentTurnRequest,
)
from .run_store import StoredHarnessRunSnapshot
from .tools import ToolBridge, ToolBridgeError, ToolObservation


class RunStopCode(str, Enum):
    CANDIDATE_COMPLETED = "candidate_completed"
    NEEDS_INPUT = "needs_input"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    CANCEL_UNKNOWN = "cancel_unknown"
    PROVIDER_FAILED = "provider_failed"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_TRANSPORT_FAILED = "provider_transport_failed"
    PROVIDER_REJECTED = "provider_rejected"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
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

    def __post_init__(self) -> None:
        if (
            min(
                self.max_model_calls,
                self.max_tool_calls,
                self.max_observation_bytes,
                self.max_wall_time_ms,
            )
            < 1
        ):
            raise ValueError("Ordivon Harness budgets must be positive")

    def remaining(
        self,
        *,
        model_calls: int,
        tool_calls: int,
        observation_bytes: int,
        elapsed_ms: int,
    ) -> dict[str, JsonValue]:
        return {
            "modelCalls": max(0, self.max_model_calls - model_calls),
            "toolCalls": max(0, self.max_tool_calls - tool_calls),
            "observationBytes": max(0, self.max_observation_bytes - observation_bytes),
            "wallTimeMs": max(0, self.max_wall_time_ms - elapsed_ms),
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
    ) -> None:
        self.adapter = adapter
        self.tool_bridge = tool_bridge
        self.budget = budget
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic_ms = monotonic_ms or (
            clock_ms
            if clock_ms is not None
            else lambda: time.monotonic_ns() // 1_000_000
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
        else:
            snapshot = retained.snapshot
            state = retained.state
            if (
                snapshot.harness_run_id != harness_run_id
                or snapshot.assignment_id != assignment_id
                or snapshot.tool_catalog_digest != self.tool_bridge.catalog_digest
                or state.requested_model_id != self.adapter.model_id
            ):
                raise ValueError("Harness Run resume identities differ")
            remaining = state.remaining_budget
            expected_budget_fields = {
                "modelCalls",
                "toolCalls",
                "observationBytes",
                "wallTimeMs",
            }
            if set(remaining) != expected_budget_fields or any(
                type(remaining[field]) is not int or remaining[field] < 0
                for field in expected_budget_fields
            ):
                raise ValueError("Harness Run resume budget is invalid")
            model_calls = self.budget.max_model_calls - int(remaining["modelCalls"])
            tool_calls = self.budget.max_tool_calls - int(remaining["toolCalls"])
            observation_bytes = self.budget.max_observation_bytes - int(
                remaining["observationBytes"]
            )
            prior_elapsed_ms = self.budget.max_wall_time_ms - int(
                remaining["wallTimeMs"]
            )
            if min(model_calls, tool_calls, observation_bytes, prior_elapsed_ms) < 0:
                raise ValueError("Harness Run resume budget exceeds configured limits")
            remaining_wall_time_ms = int(remaining["wallTimeMs"])
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

        deadline = RunDeadline.after(
            remaining_wall_time_ms,
            monotonic_ms=self.monotonic_ms,
        )
        control = ExecutionControl(cancellation, deadline)
        recorder = TraceRecorder(harness_run_id, clock_ms=self.clock_ms)
        started_at_ms = self.monotonic_ms()
        recorder.record(
            "run_resumed" if retained is not None else "run_started",
            {
                "assignmentId": assignment_id,
                "contextDigest": context_digest,
                "toolCatalogDigest": self.tool_bridge.catalog_digest,
                "adapterId": self.adapter.adapter_id,
                "requestedModelId": self.adapter.model_id,
                "deadlineMonotonicMs": deadline.expires_at_ms,
                "priorElapsedMs": prior_elapsed_ms,
                "snapshotDigest": (
                    None if retained is None else retained.snapshot.digest
                ),
            },
        )

        def elapsed_ms() -> int:
            return prior_elapsed_ms + max(0, self.monotonic_ms() - started_at_ms)

        def bind_run_state() -> None:
            binder = getattr(self.tool_bridge, "bind_run_state", None)
            if not callable(binder):
                return
            binder(
                messages=tuple(messages),
                observations=tuple(observations),
                remaining_budget=self.budget.remaining(
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                    observation_bytes=observation_bytes,
                    elapsed_ms=elapsed_ms(),
                ),
                requested_model_id=self.adapter.model_id,
                effective_model_id=(effective_models[-1] if effective_models else None),
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
                    "wallTimeMs": elapsed,
                    "deadlineOverrunMs": max(0, elapsed - self.budget.max_wall_time_ms),
                    "requestedModelId": self.adapter.model_id,
                    "effectiveModelIds": list(dict.fromkeys(effective_models)),
                    "providerUsage": provider_usage,
                },
            )

        if retained is not None and retained.snapshot.active_tool_step_intent_digests:
            reconciler = getattr(self.tool_bridge, "reconcile_current_tool_step", None)
            if not callable(reconciler):
                return stop(
                    RunStopCode.RUNTIME_UNKNOWN,
                    detail="resumed Harness Run has an active Tool Step without reconciliation",
                )
            try:
                observation = reconciler()
            except ToolBridgeError as error:
                return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(error))
            except Exception as error:  # noqa: BLE001 - Run boundary converts component failure to a receipt.
                return stop(
                    RunStopCode.HARNESS_FAILED,
                    detail=f"{type(error).__name__}: {error}",
                )
            tool_calls += 1
            seen_tool_call_ids.add(observation.tool_call_id)
            remaining_observation_bytes = (
                self.budget.max_observation_bytes - observation_bytes
            )
            bounded = getattr(observation, "bounded", None)
            if callable(bounded):
                observation = bounded(remaining_observation_bytes)
            encoded_size = len(canonical_bytes(observation.to_dict()))
            if encoded_size > remaining_observation_bytes:
                return stop(
                    RunStopCode.BUDGET_EXHAUSTED,
                    detail="reconciled Tool Observation exceeds the remaining Run budget",
                )
            observations.append(observation)
            observation_bytes += encoded_size
            messages.append(observation.to_model_message())
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
            if observation.status == "unknown":
                return stop(
                    RunStopCode.RUNTIME_UNKNOWN,
                    detail="resumed Tool Step remains unknown",
                )
            if observation.status == "cancel-requested":
                return stop(
                    RunStopCode.CANCEL_UNKNOWN,
                    detail="resumed Tool Step cancellation remains unconfirmed",
                )
            if observation.status == "cancelled":
                return stop(RunStopCode.CANCELLED)

        while True:
            if cancellation.cancelled:
                return stop(RunStopCode.CANCELLED)
            if model_calls >= self.budget.max_model_calls or deadline.expired:
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
                ),
            )
            recorder.record(
                "model_call_started",
                {
                    "turnId": turn_id,
                    "requestDigest": request.digest,
                    "remainingWallTimeMs": control.remaining_ms,
                },
            )
            try:
                start_invoke = getattr(self.adapter, "start_invoke", None)
                supports_handle = getattr(self.adapter, "supports_call_handle", True)
                if callable(start_invoke) and supports_handle:
                    handle = start_invoke(request, control)
                    while True:
                        if cancellation.cancelled:
                            self._cancel_and_drain_model_call(handle)
                            return stop(
                                RunStopCode.CANCELLED,
                                detail=(
                                    "cancellation interrupted the active Provider call"
                                ),
                            )
                        if deadline.expired:
                            self._cancel_and_drain_model_call(handle)
                            return stop(
                                RunStopCode.BUDGET_EXHAUSTED,
                                detail=(
                                    "wall-time deadline interrupted the active Provider call"
                                ),
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
                if cancellation.cancelled:
                    return stop(RunStopCode.CANCELLED, detail=str(error))
                if deadline.expired:
                    return stop(RunStopCode.BUDGET_EXHAUSTED, detail=str(error))
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
                return stop(RunStopCode.INVALID_MODEL_OUTPUT, detail=str(error))
            except Exception as error:  # noqa: BLE001 - Run boundary must emit a terminal receipt.
                return stop(
                    RunStopCode.HARNESS_FAILED,
                    detail=f"{type(error).__name__}: {error}",
                )
            if cancellation.cancelled:
                return stop(
                    RunStopCode.CANCELLED,
                    detail="cancellation was requested during the Provider call",
                )
            if deadline.expired:
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
            recorder.record(
                "model_call_completed",
                {
                    "turnId": turn_id,
                    "modelCallId": result.model_call_id,
                    "requestedModelId": result.model_id,
                    "effectiveModelId": effective_model,
                    "resultDigest": result.digest,
                    "rawResponseDigest": result.raw_response_digest,
                    "finishReason": result.finish_reason,
                },
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
            for call in result.tool_calls:
                if call.tool_call_id in seen_tool_call_ids:
                    return stop(
                        RunStopCode.INVALID_MODEL_OUTPUT,
                        detail=f"duplicate Tool Call identity: {call.tool_call_id}",
                    )
                seen_tool_call_ids.add(call.tool_call_id)
                if cancellation.cancelled:
                    return stop(RunStopCode.CANCELLED)
                if deadline.expired:
                    return stop(RunStopCode.BUDGET_EXHAUSTED)
                recorder.record(
                    "tool_call_proposed",
                    {
                        "toolCallId": call.tool_call_id,
                        "toolName": call.name,
                        "toolCallDigest": call.digest,
                    },
                )
                step_id = f"turn-{sequence}-tool-{tool_calls + 1}:{call.tool_call_id}"
                try:
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
                    return stop(RunStopCode.INVALID_TOOL_CALL, detail=str(error))
                except Exception as error:  # noqa: BLE001 - Tool implementation failure terminates the Run.
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=f"{type(error).__name__}: {error}",
                    )
                tool_calls += 1
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
                        observations.append(observation)
                        return stop(
                            RunStopCode.CANCEL_UNKNOWN,
                            detail=(
                                "cancellation was requested after Runtime dispatch, but the "
                                "Tool Bridge cannot confirm physical cancellation"
                            ),
                        )
                remaining_observation_bytes = (
                    self.budget.max_observation_bytes - observation_bytes
                )
                bounded = getattr(observation, "bounded", None)
                if callable(bounded):
                    observation = bounded(remaining_observation_bytes)
                encoded_size = len(canonical_bytes(observation.to_dict()))
                if encoded_size > remaining_observation_bytes:
                    return stop(
                        RunStopCode.BUDGET_EXHAUSTED,
                        detail="Tool Observation exceeds the remaining Run budget",
                    )
                observations.append(observation)
                observation_bytes += encoded_size
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
                if observation.status == "unknown":
                    return stop(
                        RunStopCode.RUNTIME_UNKNOWN,
                        detail=f"Tool Call {call.tool_call_id} has uncertain delivery or outcome",
                    )
                if observation.status == "cancel-requested":
                    return stop(
                        RunStopCode.CANCEL_UNKNOWN,
                        detail=f"Tool Call {call.tool_call_id} cancellation is unconfirmed",
                    )
                if observation.status == "cancelled":
                    return stop(RunStopCode.CANCELLED)
                if cancellation.cancelled:
                    return stop(RunStopCode.CANCELLED)
                if deadline.expired:
                    return stop(RunStopCode.BUDGET_EXHAUSTED)

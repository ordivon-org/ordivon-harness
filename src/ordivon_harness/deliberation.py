from __future__ import annotations

from dataclasses import dataclass, replace
import time
from collections.abc import Callable
from typing import cast

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value

from .domain_tools import DomainToolBridge, DomainToolLoopPlan, DomainToolLoopRunner
from .ordivon.control import CancellationToken, ExecutionControl, RunDeadline
from .ordivon.loop import AgentLoopResult, RunBudget, RunStopCode, _usage_total_tokens
from .ordivon.model import (
    AgentTurnAdapter,
    AgentTurnAdapterError,
    AgentTurnCallHandle,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
    AgentTurnRequest,
    AgentTurnResult,
)


_DELIBERATION_RECORD_REVISION = "deliberation-before-tools-v1"
_RECORD_MARKER = "PRIOR_NON_AUTHORITATIVE_SELF_DELIBERATION_RECORD"


@dataclass(frozen=True, slots=True)
class NonAuthoritativeDeliberationRecord:
    """Exact identity/projection of one no-Tool cognition turn.

    The record is model cognition evidence only. It is not world truth, domain
    admission, Tool intent, or proof of strategy correctness.
    """

    context_digest: str
    request_digest: str
    result_digest: str
    adapter_id: str
    requested_model_id: str
    effective_model_id: str
    summary: str
    unresolved_unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        value = self.to_dict()
        validate_json_value(value)
        if not self.context_digest.startswith("sha256:"):
            raise ValueError("deliberation Context digest must be sha256")
        if not self.request_digest.startswith("sha256:"):
            raise ValueError("deliberation request digest must be sha256")
        if not self.result_digest.startswith("sha256:"):
            raise ValueError("deliberation result digest must be sha256")
        if not self.adapter_id.strip() or not self.requested_model_id.strip():
            raise ValueError("deliberation adapter/model identity must be non-empty")
        if not self.effective_model_id.strip():
            raise ValueError("deliberation effective model identity must be non-empty")
        if not self.summary.strip():
            raise ValueError("deliberation summary must be non-empty")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.non-authoritative-deliberation-record",
            "revision": _DELIBERATION_RECORD_REVISION,
            "truthRole": "model-cognition-not-world-truth-or-domain-authority",
            "contextDigest": self.context_digest,
            "requestDigest": self.request_digest,
            "resultDigest": self.result_digest,
            "adapterId": self.adapter_id,
            "requestedModelId": self.requested_model_id,
            "effectiveModelId": self.effective_model_id,
            "summary": self.summary,
            "unresolvedUnknowns": list(self.unresolved_unknowns),
            "domainToolIntent": False,
            "domainAdmission": False,
            "externalEffect": False,
        }

    def to_model_message(self) -> dict[str, JsonValue]:
        projection = canonical_bytes(self.to_dict()).decode("utf-8")
        message: dict[str, JsonValue] = {
            "role": "user",
            "content": (
                f"{_RECORD_MARKER}\n{projection}\n\n"
                "This is your prior cognition record for the same Context. It is not world truth, "
                "not domain Tool intent, and not admission or evidence that any external effect "
                "occurred. Re-check it against the unchanged Context and use the caller-granted "
                "Tools only for the action/choice you currently endorse."
            ),
        }
        validate_json_value(message)
        return message


@dataclass(frozen=True, slots=True)
class DeliberationThenToolExecution:
    deliberation: NonAuthoritativeDeliberationRecord
    deliberation_result: AgentTurnResult
    tool_plan: DomainToolLoopPlan
    tool_result: AgentLoopResult

    @property
    def execution_digest(self) -> str:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.deliberation-then-tool-execution",
            "deliberationDigest": self.deliberation.digest,
            "toolContextDigest": self.tool_plan.context_digest,
            "toolTraceDigest": canonical_digest(self.tool_result.trace.to_dict()),
            "toolStopCode": str(
                getattr(self.tool_result.stop_code, "value", self.tool_result.stop_code)
            ),
        }
        return canonical_digest(value)


class DeliberationLifecycleError(RuntimeError):
    """Fail-closed lifecycle stop before a composed execution can be claimed."""

    def __init__(
        self,
        stop_code: RunStopCode,
        detail: str,
        *,
        phase: str,
        provider_dispatched: bool,
    ) -> None:
        super().__init__(detail)
        self.stop_code = stop_code
        self.detail = detail
        self.phase = phase
        self.provider_dispatched = provider_dispatched


def _budget_projection(budget: RunBudget) -> dict[str, JsonValue]:
    value: dict[str, JsonValue] = {
        "maxModelCalls": budget.max_model_calls,
        "maxToolCalls": budget.max_tool_calls,
        "maxObservationBytes": budget.max_observation_bytes,
        "maxWallTimeMs": budget.max_wall_time_ms,
        "maxTotalTokens": budget.max_total_tokens,
        "maxModelRetries": budget.max_model_retries,
        "maxToolCorrections": budget.max_tool_corrections,
        "maxConclusionCorrections": budget.max_conclusion_corrections,
        "maxObservationOnlyTurns": budget.max_observation_only_turns,
        "maxNoProgressTurns": budget.max_no_progress_turns,
        "maxModelObservationBytes": budget.max_model_observation_bytes,
    }
    validate_json_value(value)
    return value


@dataclass(frozen=True, slots=True)
class LifecycleBoundDeliberationThenToolExecution:
    deliberation: NonAuthoritativeDeliberationRecord
    deliberation_result: AgentTurnResult
    tool_plan: DomainToolLoopPlan
    tool_result: AgentLoopResult
    aggregate_budget: RunBudget
    phase_b_budget: RunBudget
    phase_a_elapsed_ms: int
    phase_a_total_tokens: int
    aggregate_usage: dict[str, JsonValue]
    deadline_monotonic_ms: int

    @property
    def execution_digest(self) -> str:
        value: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.lifecycle-bound-deliberation-then-tool-execution",
            "deliberationDigest": self.deliberation.digest,
            "toolTraceDigest": canonical_digest(self.tool_result.trace.to_dict()),
            "phaseABudget": _budget_projection(self.aggregate_budget),
            "phaseBBudget": _budget_projection(self.phase_b_budget),
            "phaseAElapsedMs": self.phase_a_elapsed_ms,
            "phaseATotalTokens": self.phase_a_total_tokens,
            "aggregateUsage": self.aggregate_usage,
            "deadlineMonotonicMs": self.deadline_monotonic_ms,
        }
        validate_json_value(value)
        return canonical_digest(value)


class DeliberationThenToolRunner:
    """Optionally compose one bounded no-Tool cognition turn before a domain Tool loop.

    Harness owns only sequencing, exact cognition-record identity, same-Context
    binding, and the Tool-surface transition. Domain semantics/admission/effects
    remain entirely behind the caller-supplied DomainToolBridge.

    The deliberation request and Tool plan retain their caller-supplied budgets;
    this helper does not invent or claim a new aggregate cross-phase budget.
    """

    def __init__(
        self,
        adapter: AgentTurnAdapter,
        bridge: DomainToolBridge,
        *,
        clock_ms: Callable[[], int] | None = None,
        monotonic_ms: Callable[[], int] | None = None,
    ) -> None:
        self.adapter = adapter
        self.bridge = bridge
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic_ms = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)

    def run(
        self,
        deliberation_request: AgentTurnRequest,
        tool_plan: DomainToolLoopPlan,
        *,
        cancellation: CancellationToken | None = None,
    ) -> DeliberationThenToolExecution:
        self._validate_inputs(deliberation_request, tool_plan)
        deliberation_result = self.adapter.invoke(deliberation_request)
        record = self._record(deliberation_request, deliberation_result)
        augmented_plan = replace(
            tool_plan,
            initial_messages=(
                *tool_plan.initial_messages,
                record.to_model_message(),
            ),
        )
        tool_result = DomainToolLoopRunner(self.adapter, self.bridge).run(
            augmented_plan,
            cancellation=cancellation,
        )
        return DeliberationThenToolExecution(
            deliberation=record,
            deliberation_result=deliberation_result,
            tool_plan=augmented_plan,
            tool_result=tool_result,
        )

    def run_lifecycle_bound(
        self,
        deliberation_request: AgentTurnRequest,
        tool_plan: DomainToolLoopPlan,
        *,
        budget: RunBudget,
        cancellation: CancellationToken | None = None,
    ) -> LifecycleBoundDeliberationThenToolExecution:
        """Run both phases under one cancellation/deadline/budget authority.

        The caller-supplied ``budget`` is authoritative for the composition. The
        deliberation request's ``remaining_budget`` and Tool plan's ``budget`` are
        templates only in this mode and are replaced by exact remaining authority.
        """

        self._validate_inputs(deliberation_request, tool_plan)
        if budget.max_model_calls < 2:
            raise DeliberationLifecycleError(
                RunStopCode.BUDGET_EXHAUSTED,
                "composition budget must allow one deliberation model call and at least one Tool-phase model call",
                phase="preflight",
                provider_dispatched=False,
            )
        cancellation = cancellation or CancellationToken(monotonic_ms=self.monotonic_ms)
        started_at_ms = self.monotonic_ms()
        deadline_monotonic_ms = started_at_ms + budget.max_wall_time_ms
        if tool_plan.assignment_deadline_ms is not None:
            assignment_remaining_ms = tool_plan.assignment_deadline_ms - self.clock_ms()
            if assignment_remaining_ms <= 0:
                raise DeliberationLifecycleError(
                    RunStopCode.BUDGET_EXHAUSTED,
                    "assignment deadline expired before deliberation Provider dispatch",
                    phase="deliberation",
                    provider_dispatched=False,
                )
            assignment_deadline_monotonic_ms = (
                self.monotonic_ms() + assignment_remaining_ms
            )
            deadline_monotonic_ms = min(
                deadline_monotonic_ms,
                assignment_deadline_monotonic_ms,
            )
        deadline = RunDeadline(deadline_monotonic_ms, self.monotonic_ms)
        control = ExecutionControl(cancellation, deadline)
        if cancellation.cancelled:
            raise DeliberationLifecycleError(
                RunStopCode.CANCELLED,
                "composition cancellation was already requested before deliberation dispatch",
                phase="deliberation",
                provider_dispatched=False,
            )
        if deadline.expired:
            raise DeliberationLifecycleError(
                RunStopCode.BUDGET_EXHAUSTED,
                "composition deadline expired before deliberation dispatch",
                phase="deliberation",
                provider_dispatched=False,
            )
        phase_a_request = replace(
            deliberation_request,
            remaining_budget=budget.remaining(
                model_calls=0,
                tool_calls=0,
                observation_bytes=0,
                elapsed_ms=0,
                total_tokens=0,
                model_retries=0,
                tool_corrections=0,
                conclusion_corrections=0,
                observation_only_turns=0,
                no_progress_turns=0,
            ),
        )
        token_bound = self._request_token_upper_bound(phase_a_request)
        if token_bound is not None and token_bound > budget.max_total_tokens:
            raise DeliberationLifecycleError(
                RunStopCode.BUDGET_EXHAUSTED,
                (
                    "deliberation Provider request conservative token bound exceeds the aggregate "
                    f"composition token budget ({token_bound} > {budget.max_total_tokens})"
                ),
                phase="deliberation",
                provider_dispatched=False,
            )
        deliberation_result = self._invoke_lifecycle_bound(phase_a_request, control)
        phase_a_elapsed_ms = max(0, self.monotonic_ms() - started_at_ms)
        phase_a_tokens = _usage_total_tokens(deliberation_result.usage)
        if phase_a_tokens is None:
            raise DeliberationLifecycleError(
                RunStopCode.HARNESS_FAILED,
                "deliberation Provider usage does not expose accountable token consumption",
                phase="deliberation",
                provider_dispatched=True,
            )
        if phase_a_tokens > budget.max_total_tokens:
            raise DeliberationLifecycleError(
                RunStopCode.BUDGET_EXHAUSTED,
                "deliberation Provider result exceeded the aggregate composition token budget",
                phase="deliberation",
                provider_dispatched=True,
            )
        record = self._record(phase_a_request, deliberation_result)
        remaining_model_calls = budget.max_model_calls - 1
        remaining_total_tokens = budget.max_total_tokens - phase_a_tokens
        remaining_wall_time_ms = deadline.remaining_ms
        if (
            remaining_model_calls < 1
            or remaining_total_tokens < 1
            or remaining_wall_time_ms < 1
            or cancellation.cancelled
        ):
            code = RunStopCode.CANCELLED if cancellation.cancelled else RunStopCode.BUDGET_EXHAUSTED
            raise DeliberationLifecycleError(
                code,
                "aggregate composition authority has no valid budget/liveness left for Tool exposure",
                phase="between-phases",
                provider_dispatched=True,
            )
        phase_b_budget = RunBudget(
            max_model_calls=remaining_model_calls,
            max_tool_calls=budget.max_tool_calls,
            max_observation_bytes=budget.max_observation_bytes,
            max_wall_time_ms=remaining_wall_time_ms,
            max_total_tokens=remaining_total_tokens,
            max_model_retries=budget.max_model_retries,
            max_tool_corrections=budget.max_tool_corrections,
            max_conclusion_corrections=budget.max_conclusion_corrections,
            max_observation_only_turns=budget.max_observation_only_turns,
            max_no_progress_turns=budget.max_no_progress_turns,
            max_model_observation_bytes=budget.max_model_observation_bytes,
        )
        augmented_plan = replace(
            tool_plan,
            initial_messages=(*tool_plan.initial_messages, record.to_model_message()),
            budget=phase_b_budget,
        )
        tool_result = DomainToolLoopRunner(
            self.adapter,
            self.bridge,
            clock_ms=self.clock_ms,
            monotonic_ms=self.monotonic_ms,
        ).run(
            augmented_plan,
            cancellation=cancellation,
            deadline=deadline,
        )
        tool_model_calls = int(tool_result.usage.get("modelCalls", tool_result.model_calls))
        tool_tokens = int(tool_result.usage.get("totalTokens", 0))
        tool_wall_ms = int(tool_result.usage.get("wallTimeMs", 0))
        aggregate_elapsed_ms = max(0, self.monotonic_ms() - started_at_ms)
        aggregate_usage: dict[str, JsonValue] = {
            "modelCalls": 1 + tool_model_calls,
            "toolCalls": int(tool_result.usage.get("toolCalls", tool_result.tool_calls)),
            "totalTokens": phase_a_tokens + tool_tokens,
            "wallTimeMs": aggregate_elapsed_ms,
            "phaseAModelCalls": 1,
            "phaseATotalTokens": phase_a_tokens,
            "phaseAElapsedMs": phase_a_elapsed_ms,
            "phaseBModelCalls": tool_model_calls,
            "phaseBTotalTokens": tool_tokens,
            "phaseBWallTimeMs": tool_wall_ms,
        }
        validate_json_value(aggregate_usage)
        if int(aggregate_usage["modelCalls"]) > budget.max_model_calls:
            raise RuntimeError("lifecycle-bound composition double-spent model-call budget")
        if int(aggregate_usage["totalTokens"]) > budget.max_total_tokens:
            raise RuntimeError("lifecycle-bound composition double-spent token budget")
        return LifecycleBoundDeliberationThenToolExecution(
            deliberation=record,
            deliberation_result=deliberation_result,
            tool_plan=augmented_plan,
            tool_result=tool_result,
            aggregate_budget=budget,
            phase_b_budget=phase_b_budget,
            phase_a_elapsed_ms=phase_a_elapsed_ms,
            phase_a_total_tokens=phase_a_tokens,
            aggregate_usage=aggregate_usage,
            deadline_monotonic_ms=deadline.expires_at_ms,
        )

    def _request_token_upper_bound(self, request: AgentTurnRequest) -> int | None:
        estimator = getattr(self.adapter, "request_token_upper_bound", None)
        if not callable(estimator):
            return None
        value = estimator(request)
        if type(value) is not int or value < 0:
            raise DeliberationLifecycleError(
                RunStopCode.HARNESS_FAILED,
                "adapter request_token_upper_bound returned an invalid value",
                phase="deliberation",
                provider_dispatched=False,
            )
        return value

    def _invoke_lifecycle_bound(
        self,
        request: AgentTurnRequest,
        control: ExecutionControl,
    ) -> AgentTurnResult:
        if control.cancellation.cancelled:
            raise DeliberationLifecycleError(
                RunStopCode.CANCELLED,
                "composition cancelled before deliberation Provider dispatch",
                phase="deliberation",
                provider_dispatched=False,
            )
        start_invoke = getattr(self.adapter, "start_invoke", None)
        supports_call_handle = bool(getattr(self.adapter, "supports_call_handle", False))
        try:
            if callable(start_invoke) and supports_call_handle:
                handle = cast(AgentTurnCallHandle, start_invoke(request, control))
                while True:
                    if control.cancellation.cancelled:
                        self._cancel_and_drain(handle)
                        raise DeliberationLifecycleError(
                            RunStopCode.CANCEL_UNKNOWN,
                            "deliberation Provider call was cancelled after dispatch",
                            phase="deliberation",
                            provider_dispatched=True,
                        )
                    if control.deadline.expired:
                        self._cancel_and_drain(handle)
                        raise DeliberationLifecycleError(
                            RunStopCode.PROVIDER_STATE_UNKNOWN,
                            "deliberation Provider call crossed the composition deadline after dispatch",
                            phase="deliberation",
                            provider_dispatched=True,
                        )
                    poll_seconds = max(0.001, min(0.05, control.remaining_ms / 1000.0))
                    result = handle.poll(poll_seconds)
                    if result is not None:
                        return result
            invoke_with_control = getattr(self.adapter, "invoke_with_control", None)
            if callable(invoke_with_control):
                return cast(AgentTurnResult, invoke_with_control(request, control))
        except DeliberationLifecycleError:
            raise
        except AgentTurnAdapterError as error:
            if error.dispatch_safety is AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS:
                stop_code = RunStopCode.PROVIDER_STATE_UNKNOWN
                provider_dispatched = True
            else:
                stop_code = {
                    AgentTurnFailureCode.FAILED: RunStopCode.PROVIDER_FAILED,
                    AgentTurnFailureCode.TIMEOUT: RunStopCode.PROVIDER_TIMEOUT,
                    AgentTurnFailureCode.TRANSPORT_FAILED: (
                        RunStopCode.PROVIDER_TRANSPORT_FAILED
                    ),
                    AgentTurnFailureCode.REJECTED: RunStopCode.PROVIDER_REJECTED,
                    AgentTurnFailureCode.UNAVAILABLE: RunStopCode.PROVIDER_UNAVAILABLE,
                }[error.failure_code]
                provider_dispatched = (
                    error.dispatch_safety is not AgentTurnDispatchSafety.PRE_DISPATCH_SAFE
                )
            raise DeliberationLifecycleError(
                stop_code,
                f"deliberation Provider failed: {error}",
                phase="deliberation",
                provider_dispatched=provider_dispatched,
            ) from error
        raise DeliberationLifecycleError(
            RunStopCode.HARNESS_FAILED,
            (
                "lifecycle-bound composition requires adapter controlled invocation "
                "(start_invoke handle or invoke_with_control)"
            ),
            phase="deliberation",
            provider_dispatched=False,
        )

    @staticmethod
    def _cancel_and_drain(handle: AgentTurnCallHandle) -> None:
        handle.cancel()
        try:
            handle.poll(0.5)
        except Exception:
            return


    def _validate_inputs(
        self,
        deliberation_request: AgentTurnRequest,
        tool_plan: DomainToolLoopPlan,
    ) -> None:
        if deliberation_request.tools:
            raise ValueError("deliberation-before-Tools request must not expose domain Tools")
        if not deliberation_request.capabilities.default:
            raise ValueError(
                "deliberation-before-Tools request must use default non-mutating Harness capabilities"
            )
        if deliberation_request.context_digest != tool_plan.context_digest:
            raise ValueError("deliberation and Tool phases must bind the same Context digest")

    def _record(
        self,
        request: AgentTurnRequest,
        result: AgentTurnResult,
    ) -> NonAuthoritativeDeliberationRecord:
        if result.tool_calls:
            raise ValueError("deliberation-before-Tools Provider result unexpectedly contains Tool Calls")
        if result.conclusion is None:
            raise ValueError("deliberation-before-Tools Provider result must contain a conclusion")
        if result.conclusion.status != "candidate_completed":
            raise ValueError(
                "deliberation-before-Tools conclusion must be candidate_completed before Tool exposure"
            )
        if result.model_id != self.adapter.model_id:
            raise ValueError("deliberation result requested model differs from runner adapter")
        return NonAuthoritativeDeliberationRecord(
            context_digest=request.context_digest,
            request_digest=request.dispatch_digest,
            result_digest=result.digest,
            adapter_id=self.adapter.adapter_id,
            requested_model_id=self.adapter.model_id,
            effective_model_id=result.effective_model,
            summary=result.conclusion.summary,
            unresolved_unknowns=result.conclusion.unresolved_unknowns,
        )


__all__ = [
    "DeliberationLifecycleError",
    "DeliberationThenToolExecution",
    "DeliberationThenToolRunner",
    "LifecycleBoundDeliberationThenToolExecution",
    "NonAuthoritativeDeliberationRecord",
]

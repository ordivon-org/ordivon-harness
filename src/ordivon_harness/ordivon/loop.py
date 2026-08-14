from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum

from anc_canonical import JsonValue, canonical_bytes, canonical_digest

from ..protocol import HarnessProviderCallFailureReceipt
from ..working_view import (
    WORKING_SET_HISTORY_CONTROL_NAME,
    CallerIngressPromotionHandler,
    WorkingSetHistoryReader,
    WorkingSetTransitionHandler,
    WorkingViewProjector,
    parse_working_set_history_query,
)
from .control import CancellationToken, ExecutionControl, RunDeadline
from .cognition_admission import CognitionAdmissionKernel, CognitionSurfaceUnavailable
from .events import HarnessRunEvent, HarnessTrace, TraceRecorder
from .model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnAdapter,
    AgentTurnAdapterError,
    AgentTurnCallHandle,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
)
from .provider_lifecycle import ProviderCallLifecycle, ProviderLifecycleError
from .run_store_port import HarnessProviderCallRecoveryRequired, StoredHarnessRunSnapshot
from .run_recovery import (
    _observation_evidence_signature,
    _path_subsumes,
    _recover_tool_batch,
    _retained_tool_calls,
    _search_evidence,
)
from .tool_bridge import ToolBridge, ToolObservation
from .tool_errors import ToolBridgeError, ToolBridgeErrorKind
from ..tool_program_recovery import (
    derive_tool_program_inner_call,
    recover_tool_program_action,
)
from .turn_projection import AgentTurnProjectionError, AgentTurnProjector

_OBSERVATION_ONLY_TOOLS = frozenset(
    {
        "read_workspace",
        "search_workspace",
        "diff_workspace",
        "observe_job",
        "read_artifact",
        WORKING_SET_HISTORY_CONTROL_NAME,
    }
)



def _validated_projected_caller_ingress(
    messages: tuple[dict[str, JsonValue], ...],
) -> tuple[dict[str, JsonValue], ...]:
    validated: list[dict[str, JsonValue]] = []
    for message in messages:
        if (
            set(message) != {"role", "content"}
            or message.get("role") != "user"
            or not isinstance(message.get("content"), str)
        ):
            raise ValueError(
                "projected caller cognition ingress requires plain user messages"
            )
        validated.append(dict(message))
    return tuple(validated)


class LoopSchedulingMode(str, Enum):
    """Built-in scheduling policies around the same constitution-owned loop kernel."""

    SEQUENTIAL = "sequential"
    DELIBERATE_THEN_ACT = "deliberate_then_act"


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
    max_conclusion_corrections: int = 3
    max_observation_only_turns: int = 6
    max_no_progress_turns: int = 3
    max_model_observation_bytes: int = 32_768

    def __post_init__(self) -> None:
        if (
            min(
                self.max_model_calls,
                self.max_observation_bytes,
                self.max_wall_time_ms,
                self.max_total_tokens,
            )
            < 1
        ):
            raise ValueError("Ordivon Harness primary budgets must be positive")
        if self.max_tool_calls < 0:
            raise ValueError("Ordivon Harness Tool Call budget must be non-negative")
        if (
            self.max_model_retries < 0
            or self.max_tool_corrections < 0
            or self.max_conclusion_corrections < 0
            or self.max_observation_only_turns < 0
            or self.max_no_progress_turns < 0
        ):
            raise ValueError("Ordivon Harness secondary budgets must be non-negative")
        if self.max_model_observation_bytes < 1:
            raise ValueError("Ordivon Harness Observation message bound must be positive")

    def to_contract_dict(self) -> dict[str, JsonValue]:
        """Return the complete durable budget projection for a new Run Contract."""
        return {
            "maxModelCalls": self.max_model_calls,
            "maxToolCalls": self.max_tool_calls,
            "maxObservationBytes": self.max_observation_bytes,
            "maxWallTimeMs": self.max_wall_time_ms,
            "maxTotalTokens": self.max_total_tokens,
            "maxModelRetries": self.max_model_retries,
            "maxToolCorrections": self.max_tool_corrections,
            "maxConclusionCorrections": self.max_conclusion_corrections,
            "maxObservationOnlyTurns": self.max_observation_only_turns,
            "maxNoProgressTurns": self.max_no_progress_turns,
            "maxModelObservationBytes": self.max_model_observation_bytes,
        }

    @classmethod
    def from_contract_dict(
        cls, contract_budget: Mapping[str, JsonValue]
    ) -> RunBudget:
        """Materialize schema-v1 Contract budget authority for execution.

        Early caller-neutral Contracts may omit fields that predate the complete
        budget projection. Missing fields use the historical Harness defaults;
        every field that is present remains exact authority and unknown fields
        fail closed through ``require_contract_match``.
        """
        defaults = cls(
            max_model_calls=8,
            max_tool_calls=16,
            max_observation_bytes=1_048_576,
            max_wall_time_ms=600_000,
            max_total_tokens=131_072,
            max_model_retries=2,
            max_tool_corrections=3,
            max_conclusion_corrections=3,
            max_observation_only_turns=6,
            max_no_progress_turns=3,
            max_model_observation_bytes=32_768,
        )
        names = {
            "maxModelCalls": "max_model_calls",
            "maxToolCalls": "max_tool_calls",
            "maxObservationBytes": "max_observation_bytes",
            "maxWallTimeMs": "max_wall_time_ms",
            "maxTotalTokens": "max_total_tokens",
            "maxModelRetries": "max_model_retries",
            "maxToolCorrections": "max_tool_corrections",
            "maxConclusionCorrections": "max_conclusion_corrections",
            "maxObservationOnlyTurns": "max_observation_only_turns",
            "maxNoProgressTurns": "max_no_progress_turns",
            "maxModelObservationBytes": "max_model_observation_bytes",
        }
        unknown = set(contract_budget) - set(names)
        if unknown:
            raise ValueError(
                "Harness Run Contract budget has unsupported fields: "
                + ", ".join(sorted(unknown))
            )
        values = {name: getattr(defaults, name) for name in names.values()}
        for field, value in contract_budget.items():
            if type(value) is not int:
                raise ValueError(f"Harness Run Contract budget {field} must be an integer")
            values[names[field]] = value
        materialized = cls(**values)
        materialized.require_contract_match(contract_budget)
        return materialized

    def require_contract_match(self, contract_budget: Mapping[str, JsonValue]) -> None:
        """Require every budget bound claimed by a Contract to match execution.

        Early schema-v1 independent Contracts bound only a subset of RunBudget.
        Missing known fields therefore retain their historical unbound/default
        meaning. A claimed known field is authoritative and must match exactly;
        an unknown field cannot be silently ignored by an executing Runner.
        """
        execution = self.to_contract_dict()
        unknown = set(contract_budget) - set(execution)
        if unknown:
            raise ValueError(
                "Standalone Runner Contract budget has unsupported fields: "
                + ", ".join(sorted(unknown))
            )
        for field, claimed in contract_budget.items():
            if type(claimed) is not int:
                raise ValueError(
                    f"Standalone Runner Contract budget {field} must be an integer"
                )
            if claimed != execution[field]:
                raise ValueError(f"Standalone Runner budget differs at {field}")

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
        conclusion_corrections: int = 0,
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
            "conclusionCorrections": max(
                0, self.max_conclusion_corrections - conclusion_corrections
            ),
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
    """Sequential Run coordinator over separate Agent, cognition and Provider seams."""

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
        working_view_projector: WorkingViewProjector | None = None,
        working_set_transition_handler: WorkingSetTransitionHandler | None = None,
        caller_ingress_promotion_handler: CallerIngressPromotionHandler | None = None,
        working_set_history_reader: WorkingSetHistoryReader | None = None,
        tool_program_actions: bool = False,
        scheduling_mode: LoopSchedulingMode = LoopSchedulingMode.SEQUENTIAL,
    ) -> None:
        self.adapter = adapter
        self.tool_bridge = tool_bridge
        self.budget = budget
        self.working_view_projector = working_view_projector
        self.working_set_transition_handler = working_set_transition_handler
        self.caller_ingress_promotion_handler = caller_ingress_promotion_handler
        self.working_set_history_reader = working_set_history_reader
        if type(tool_program_actions) is not bool:
            raise ValueError("ToolProgram action installation must be boolean")
        self.tool_program_actions = tool_program_actions
        if not isinstance(scheduling_mode, LoopSchedulingMode):
            raise TypeError("Loop scheduling mode must be a LoopSchedulingMode")
        self.scheduling_mode = scheduling_mode
        self.cognition_admission = CognitionAdmissionKernel(
            working_set_transition_handler=working_set_transition_handler,
            caller_ingress_promotion_handler=caller_ingress_promotion_handler,
        )
        if working_set_transition_handler is not None and working_view_projector is None:
            raise ValueError(
                "Agent Working Set transitions require a Working View projector"
            )
        if caller_ingress_promotion_handler is not None and working_view_projector is None:
            raise ValueError(
                "caller ingress promotion requires a Working View projector"
            )
        if working_set_history_reader is not None and working_view_projector is None:
            raise ValueError(
                "Working Set history inspection requires a Working View projector"
            )
        self.turn_projector = AgentTurnProjector(
            tool_surface=tool_bridge,
            working_view_projector=working_view_projector,
            caller_ingress_projector=caller_ingress_promotion_handler,
            working_set_transition_installed=(working_set_transition_handler is not None),
            caller_ingress_promotion_installed=(
                caller_ingress_promotion_handler is not None
            ),
            working_set_history_installed=(working_set_history_reader is not None),
            tool_program_installed=tool_program_actions,
        )
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic_ms = monotonic_ms or (
            lambda: time.monotonic_ns() // 1_000_000
        )
        if assignment_deadline_ms is not None and assignment_deadline_ms < 0:
            raise ValueError("Assignment deadline must be non-negative")
        self.assignment_deadline_ms = assignment_deadline_ms
        self.event_sink = event_sink
        self.provider_lifecycle = ProviderCallLifecycle(
            bridge=self.tool_bridge,
            adapter=self.adapter,
        )

    def run(
        self,
        *,
        harness_run_id: str,
        assignment_id: str,
        context_digest: str,
        initial_messages: tuple[dict[str, JsonValue], ...],
        cancellation: CancellationToken | None = None,
        deadline: RunDeadline | None = None,
    ) -> AgentLoopResult:
        return self._run(
            harness_run_id=harness_run_id,
            assignment_id=assignment_id,
            context_digest=context_digest,
            initial_messages=initial_messages,
            cancellation=cancellation,
            external_deadline=deadline,
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
        deadline: RunDeadline | None = None,
    ) -> AgentLoopResult:
        return self._run(
            harness_run_id=retained.snapshot.harness_run_id,
            assignment_id=assignment_id,
            context_digest=context_digest,
            initial_messages=additional_messages,
            cancellation=cancellation,
            external_deadline=deadline,
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
        external_deadline: RunDeadline | None,
        retained: StoredHarnessRunSnapshot | None,
    ) -> AgentLoopResult:
        cancellation = cancellation or CancellationToken(monotonic_ms=self.monotonic_ms)
        projected_caller_input = (
            _validated_projected_caller_ingress(initial_messages)
            if retained is not None and self.working_view_projector is not None
            else ()
        )
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
            conclusion_corrections = 0
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
            if not state.messages_retained or not state.observations_retained:
                raise ValueError(
                    "Harness Run resume content was not retained by the Privacy policy; "
                    "caller-authorized content rehydration is required"
                )
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
                "conclusionCorrections",
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
            conclusion_corrections = self.budget.max_conclusion_corrections - int(
                remaining.get(
                    "conclusionCorrections", self.budget.max_conclusion_corrections
                )
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
            if (
                initial_messages and self.working_view_projector is None
            ) or projected_caller_input:
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
                    conclusion_corrections,
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

        # Tool exchanges are attempt-local cognition. Caller ingress is instead
        # caller-owned interaction cognition: it crosses Agent WorkingSet transitions
        # until the next needs-input Snapshot becomes the new interaction boundary.
        pre_caller_tool_exchange_messages: list[dict[str, JsonValue]] = []
        caller_ingress_messages: list[dict[str, JsonValue]] = [
            dict(message) for message in projected_caller_input
        ]
        post_caller_tool_exchange_messages: list[dict[str, JsonValue]] = []
        transient_working_set_digest: str | None = None

        def soft_observation_gate_reason() -> str | None:
            if (
                self.budget.max_no_progress_turns > 0
                and no_progress_turns >= self.budget.max_no_progress_turns
            ):
                return (
                    "external observation gate closed after "
                    f"{no_progress_turns} consecutive turns without a mutation, "
                    "check, materially new bounded observation, or conclusion"
                )
            if (
                self.budget.max_observation_only_turns > 0
                and observation_only_turns
                >= self.budget.max_observation_only_turns
            ):
                return (
                    "external observation gate closed after "
                    f"{observation_only_turns} consecutive observation-only turns "
                    "without a mutation, check, or conclusion"
                )
            return None

        external_observation_gate_reason = soft_observation_gate_reason()

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
        internal_deadline_expires_at_ms = started_at_ms + effective_remaining_ms
        if (
            external_deadline is not None
            and external_deadline.expires_at_ms <= internal_deadline_expires_at_ms
        ):
            deadline = external_deadline
            effective_remaining_ms = max(0, deadline.expires_at_ms - started_at_ms)
            deadline_source = "external_deadline"
        else:
            deadline = RunDeadline(
                internal_deadline_expires_at_ms,
                self.monotonic_ms,
            )
        effective_total_wall_budget_ms = prior_elapsed_ms + effective_remaining_ms
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
                    conclusion_corrections=conclusion_corrections,
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
                "conclusionCorrections": conclusion_corrections,
                "observationOnlyTurns": observation_only_turns,
                "noProgressTurns": no_progress_turns,
                "providerAttempts": provider_attempts,
                "providerResultsReplayed": provider_result_replays,
                "elapsedMs": elapsed,
                "deadlineOverrunMs": max(0, elapsed - self.budget.max_wall_time_ms),
                "effectiveDeadlineOverrunMs": max(
                    0, elapsed - effective_total_wall_budget_ms
                ),
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
                    "conclusionCorrections": conclusion_corrections,
                    "conclusionCorrectionLimit": self.budget.max_conclusion_corrections,
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
                    "effectiveDeadlineOverrunMs": max(
                        0, elapsed - effective_total_wall_budget_ms
                    ),
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
            count_tool_call: bool = True,
            physical_dispatch: bool = True,
            project_to_messages: bool = True,
        ) -> AgentLoopResult | None:
            nonlocal observation_bytes, tool_calls, tool_corrections
            if count_tool_call:
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
            elif not physical_dispatch:
                recorder.record(
                    "working_set_history_observed",
                    {
                        "toolCallId": call.tool_call_id,
                        "toolName": call.name,
                        "observationDigest": observation.digest,
                        "encodedBytes": encoded_size,
                        "physicalDispatch": False,
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
            if project_to_messages:
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
            raw_observation_sink: list[ToolObservation] | None = None,
            project_to_messages: bool = True,
        ) -> AgentLoopResult | None:
            nonlocal tool_calls, tool_corrections
            history_calls = [
                call
                for call in calls
                if call.name == WORKING_SET_HISTORY_CONTROL_NAME
            ]
            if history_calls and len(calls) != 1:
                return stop(
                    RunStopCode.INVALID_MODEL_OUTPUT,
                    detail=(
                        "Working Set history cognition control cannot mix with "
                        "Runtime Tool Calls"
                    ),
                )
            if history_calls and self.working_set_history_reader is None:
                return stop(
                    RunStopCode.INVALID_MODEL_OUTPUT,
                    detail=(
                        "Agent requested Working Set history but this Loop did not "
                        "grant a history cognition surface"
                    ),
                )
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
                if call.name == WORKING_SET_HISTORY_CONTROL_NAME:
                    if call.argument_error is not None:
                        return stop(
                            RunStopCode.INVALID_MODEL_OUTPUT,
                            detail=(
                                "Working Set history cognition control carried an "
                                f"argument error: {call.argument_error}"
                            ),
                        )
                    try:
                        history_limit, history_before_sequence = (
                            parse_working_set_history_query(call.arguments)
                        )
                    except (TypeError, ValueError) as error:
                        return stop(
                            RunStopCode.INVALID_MODEL_OUTPUT,
                            detail=f"Working Set history query rejected: {error}",
                        )
                    history_reader = self.working_set_history_reader
                    assert history_reader is not None
                    try:
                        history_content = history_reader.inspect_working_set_history(
                            limit=history_limit,
                            before_sequence=history_before_sequence,
                        )
                    except Exception as error:  # noqa: BLE001 - cognition authority boundary.
                        return stop(
                            RunStopCode.HARNESS_FAILED,
                            detail=(
                                "Working Set history inspection failed: "
                                f"{type(error).__name__}: {error}"
                            ),
                        )
                    history_observation = ToolObservation(
                        call.tool_call_id,
                        call.name,
                        "observed",
                        history_content,
                    )
                    stopped = retain_tool_observation(
                        call,
                        history_observation,
                        turn_observations=turn_observations,
                        step_id=None,
                        reconciled=False,
                        count_tool_call=False,
                        physical_dispatch=False,
                    )
                    if stopped is not None:
                        return stopped
                    continue
                step_id = f"turn-{sequence}-tool-{tool_calls + 1}:{call.tool_call_id}"
                try:
                    if call.argument_error is not None:
                        detail = (
                            (
                                f"Runtime Tool {call.name} is unavailable for this turn: "
                                f"{external_observation_gate_reason}. No physical dispatch "
                                "occurred. Do not substitute another Runtime Tool name; "
                                "choose an available Harness cognition action or "
                                "submit_run_conclusion instead."
                            )
                            if call.argument_error == "unavailable_tool"
                            and external_observation_gate_reason is not None
                            else (
                                f"Provider Tool Call {call.name} arguments were "
                                f"rejected ({call.argument_error}); raw digest "
                                f"{call.raw_arguments_digest}"
                            )
                        )
                        raise ToolBridgeError(
                            detail,
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
                                "physicalDispatch": False,
                                "commitState": "not_started",
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
                if raw_observation_sink is not None:
                    raw_observation_sink.append(observation)
                stopped = retain_tool_observation(
                    call,
                    observation,
                    turn_observations=turn_observations,
                    step_id=step_id,
                    reconciled=False,
                    count_tool_call=(call.argument_error != "unavailable_tool"),
                    project_to_messages=project_to_messages,
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
            nonlocal external_observation_gate_reason, no_progress_turns, observation_only_turns
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
            gate_reason = soft_observation_gate_reason()
            if gate_reason is not None:
                external_observation_gate_reason = gate_reason
            return None

        def restore_projected_cognition_overlay() -> AgentLoopResult | None:
            nonlocal transient_working_set_digest
            if retained is None or self.working_view_projector is None:
                return None
            structured_restorer = getattr(
                self.tool_bridge,
                "restore_current_attempt_cognition_overlay",
                None,
            )
            try:
                restored_base_view = self.working_view_projector.project()
                if callable(structured_restorer):
                    restored = structured_restorer(
                        tuple(messages),
                        tuple(observations),
                    )
                    if not isinstance(restored, dict) or set(restored) != {
                        "preCallerToolMessages",
                        "callerMessages",
                        "postCallerToolMessages",
                    }:
                        raise ValueError(
                            "restored projected cognition overlay has invalid fields"
                        )
                    raw_pre = restored["preCallerToolMessages"]
                    raw_caller = restored["callerMessages"]
                    raw_post = restored["postCallerToolMessages"]
                    if not all(
                        isinstance(value, list)
                        and all(isinstance(item, dict) for item in value)
                        for value in (raw_pre, raw_caller, raw_post)
                    ):
                        raise ValueError(
                            "restored projected cognition overlay must contain message lists"
                        )
                    pre_caller_tool_exchange_messages.clear()
                    pre_caller_tool_exchange_messages.extend(
                        dict(message) for message in raw_pre
                    )
                    caller_ingress_messages.clear()
                    caller_ingress_messages.extend(
                        dict(message) for message in raw_caller
                    )
                    post_caller_tool_exchange_messages.clear()
                    post_caller_tool_exchange_messages.extend(
                        dict(message) for message in raw_post
                    )
                else:
                    exchange_restorer = getattr(
                        self.tool_bridge,
                        "restore_current_attempt_tool_exchanges",
                        None,
                    )
                    if callable(exchange_restorer) and observations:
                        restored_exchange = exchange_restorer(tuple(observations))
                        pre_caller_tool_exchange_messages.clear()
                        pre_caller_tool_exchange_messages.extend(
                            dict(message) for message in restored_exchange
                        )
                        post_caller_tool_exchange_messages.clear()
            except ToolBridgeError as error:
                return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(error))
            except Exception as error:  # noqa: BLE001 - recovery projection is a Harness boundary.
                return stop(
                    RunStopCode.HARNESS_FAILED,
                    detail=(
                        "projected cognition recovery failed: "
                        f"{type(error).__name__}: {error}"
                    ),
                )
            tool_messages = (
                tuple(pre_caller_tool_exchange_messages)
                + tuple(post_caller_tool_exchange_messages)
            )
            transient_working_set_digest = (
                restored_base_view.working_set_digest
                if tool_messages
                else None
            )
            if tool_messages:
                recorder.record(
                    "transient_tool_exchange_restored",
                    {
                        "workingSetDigest": restored_base_view.working_set_digest,
                        "restoredMessages": len(tool_messages),
                        "restoredExchangeDigest": canonical_digest(
                            list(tool_messages)
                        ),
                    },
                )
            if caller_ingress_messages:
                recorder.record(
                    "caller_cognition_ingress_restored",
                    {
                        "messages": len(caller_ingress_messages),
                        "ingressDigest": canonical_digest(
                            list(caller_ingress_messages)
                        ),
                    },
                )
            return None

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

        if retained is not None:
            stopped = restore_projected_cognition_overlay()
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
            if (
                tool_calls >= self.budget.max_tool_calls
                and external_observation_gate_reason is None
            ):
                external_observation_gate_reason = (
                    "external Tool Call budget is exhausted; choose cognition transition "
                    "or conclusion without further external Tool effects"
                )
            try:
                projection = self.turn_projector.project(
                    harness_run_id=harness_run_id,
                    turn_id=turn_id,
                    sequence=sequence,
                    assignment_id=assignment_id,
                    canonical_context_digest=context_digest,
                    canonical_messages=tuple(messages),
                    remaining_budget=self.budget.remaining(
                        model_calls=model_calls,
                        tool_calls=tool_calls,
                        observation_bytes=observation_bytes,
                        elapsed_ms=elapsed_ms(),
                        total_tokens=total_tokens,
                        model_retries=model_retries,
                        tool_corrections=tool_corrections,
                        conclusion_corrections=conclusion_corrections,
                        observation_only_turns=observation_only_turns,
                        no_progress_turns=no_progress_turns,
                    ),
                    admit_runtime_tools=(
                        external_observation_gate_reason is None
                        and not (
                            self.scheduling_mode is LoopSchedulingMode.DELIBERATE_THEN_ACT
                            and sequence == 1
                        )
                    ),
                    transient_working_set_digest=transient_working_set_digest,
                    caller_ingress_messages=tuple(caller_ingress_messages),
                    pre_caller_tool_exchange_messages=tuple(
                        pre_caller_tool_exchange_messages
                    ),
                    post_caller_tool_exchange_messages=tuple(
                        post_caller_tool_exchange_messages
                    ),
                )
            except AgentTurnProjectionError as error:
                return stop(RunStopCode.HARNESS_FAILED, detail=str(error))
            if projection.discarded_stale_transient_tool_exchange:
                pre_caller_tool_exchange_messages.clear()
                post_caller_tool_exchange_messages.clear()
                transient_working_set_digest = None
            request = projection.request
            working_view = projection.effective_working_view
            if working_view is not None:
                recorder.record(
                    "model_view_projected",
                    {
                        "turnId": turn_id,
                        "attemptId": working_view.attempt_id,
                        "workingSetDigest": working_view.working_set_digest,
                        "baseWorkingViewDigest": projection.base_working_view_digest,
                        "workingViewDigest": working_view.digest,
                        "transientToolExchangeMessages": (
                            projection.transient_tool_exchange_messages
                        ),
                        "callerCognitionIngressMessages": (
                            projection.caller_cognition_ingress_messages
                        ),
                        "canonicalMessagesDigest": (
                            projection.canonical_messages_digest
                        ),
                        "projectedMessagesDigest": (
                            projection.projected_messages_digest
                        ),
                    },
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
            durable_provider_call = self.provider_lifecycle.durable
            try:
                provider_request_digest = self.provider_lifecycle.request_digest(
                    request
                )
            except ProviderLifecycleError as error:
                return stop(RunStopCode.HARNESS_FAILED, detail=str(error))
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
            provider_outcome = self.provider_lifecycle.begin(
                request,
                provider_request_digest=provider_request_digest,
            )
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
                    if durable_provider_call:
                        # begin()/retry() just bound the exact state that owns this
                        # durable Provider claim. Rebinding before dispatch adds no
                        # semantic information and creates a generic Run-lease race
                        # that can strand the rightful claim owner in CLAIMED.
                        try:
                            admitted = self.provider_lifecycle.admit(
                                request, control=control
                            )
                        except ProviderLifecycleError as error:
                            return stop(RunStopCode.HARNESS_FAILED, detail=str(error))
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
                    else:
                        bind_run_state()
                        if cancellation.cancelled:
                            return stop(RunStopCode.CANCELLED)
                        if execution_deadline_expired():
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
                                if self.provider_lifecycle.records_failures:
                                    bind_run_state()
                                    self.provider_lifecycle.fail(
                                        request, interrupted, unknown=True
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
                except HarnessProviderCallRecoveryRequired:
                    raise
                except AgentTurnAdapterError as error:
                    unknown = (
                        error.dispatch_safety
                        is AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS
                    )
                    if (
                        not failure_was_replayed
                        and self.provider_lifecycle.records_failures
                    ):
                        bind_run_state()
                        self.provider_lifecycle.fail(request, error, unknown=unknown)
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
                        self.provider_lifecycle.retry(request)
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
                    if self.provider_lifecycle.records_failures:
                        bind_run_state()
                        self.provider_lifecycle.fail(request, malformed, unknown=False)
                    return stop(RunStopCode.INVALID_MODEL_OUTPUT, detail=str(error))
                except Exception as error:  # noqa: BLE001 - unknown dispatch must not retry.
                    ambiguous = AgentTurnAdapterError(
                        f"{type(error).__name__}: {error}",
                        failure_code=AgentTurnFailureCode.FAILED,
                        dispatch_safety=(
                            AgentTurnDispatchSafety.DISPATCH_AMBIGUOUS
                        ),
                    )
                    if self.provider_lifecycle.records_failures:
                        bind_run_state()
                        self.provider_lifecycle.fail(request, ambiguous, unknown=True)
                    return stop(
                        RunStopCode.PROVIDER_STATE_UNKNOWN,
                        detail=str(ambiguous),
                    )
                if self.provider_lifecycle.records_completions:
                    bind_run_state()
                    self.provider_lifecycle.complete(request, result)
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
            if external_observation_gate_reason is not None and any(
                call.name != WORKING_SET_HISTORY_CONTROL_NAME
                and call.argument_error != "unavailable_tool"
                for call in result.tool_calls
            ):
                return stop(
                    RunStopCode.NO_PROGRESS,
                    detail=(
                        external_observation_gate_reason
                        + "; the Agent requested another admitted external Tool after the gate closed"
                    ),
                )
            if result.caller_ingress_promotion is not None:
                if working_view is None:
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail="caller ingress promotion omitted its source Working View",
                    )
                try:
                    admission = self.cognition_admission.apply_caller_ingress_promotion(
                        result.caller_ingress_promotion,
                        source_working_set_digest=working_view.working_set_digest,
                        source_model_view_digest=request.context_digest,
                    )
                    committed_working_set = admission.committed_working_set
                    selection_changed = admission.selection_changed
                except CognitionSurfaceUnavailable as error:
                    return stop(RunStopCode.INVALID_MODEL_OUTPUT, detail=str(error))
                except ValueError as error:
                    return stop(
                        RunStopCode.INVALID_MODEL_OUTPUT,
                        detail=f"caller ingress promotion rejected: {error}",
                    )
                except Exception as error:  # noqa: BLE001 - durable cognition admission failure terminates this Run.
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=(
                            "caller ingress promotion admission failed: "
                            f"{type(error).__name__}: {error}"
                        ),
                    )
                pre_caller_tool_exchange_messages.clear()
                post_caller_tool_exchange_messages.clear()
                transient_working_set_digest = None
                if selection_changed:
                    external_observation_gate_reason = None
                    observation_only_turns = 0
                    no_progress_turns = 0
                messages.append(
                    {
                        "role": "assistant",
                        "content": result.content,
                        "callerIngressPromotion": result.caller_ingress_promotion.to_dict(),
                    }
                )
                recorder.record(
                    "caller_ingress_promotion_applied",
                    {
                        "turnId": turn_id,
                        "proposalDigest": result.caller_ingress_promotion.digest,
                        "sourceWorkingSetDigest": working_view.working_set_digest,
                        "sourceModelViewDigest": request.context_digest,
                        "nextAttemptId": committed_working_set.attempt_id,
                        "committedWorkingSetDigest": committed_working_set.digest,
                        "promotionSlot": result.caller_ingress_promotion.promotion_slot,
                        "callerMessageIndexes": list(
                            result.caller_ingress_promotion.caller_message_indexes
                        ),
                        "selectionChanged": selection_changed,
                    },
                )
                recorder.record(
                    "run_progress_evaluated",
                    {
                        "turnId": turn_id,
                        "observationOnly": False,
                        "actionProgress": selection_changed,
                        "newEvidence": True,
                        "observationOnlyTurns": observation_only_turns,
                        "noProgressTurns": no_progress_turns,
                        "callerIngressPromotion": True,
                        "workingSetSelectionChanged": selection_changed,
                    },
                )
                try:
                    bind_run_state()
                except ToolBridgeError as state_error:
                    return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(state_error))
                except Exception as state_error:  # noqa: BLE001
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=f"{type(state_error).__name__}: {state_error}",
                    )
                continue

            if result.working_set_transition is not None:
                if working_view is None:
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail="Working Set transition omitted its source Working View",
                    )
                try:
                    admission = self.cognition_admission.apply_working_set_transition(
                        result.working_set_transition,
                        source_working_set_digest=working_view.working_set_digest,
                        source_model_view_digest=request.context_digest,
                    )
                    committed_working_set = admission.committed_working_set
                    selection_changed = admission.selection_changed
                except CognitionSurfaceUnavailable as error:
                    return stop(RunStopCode.INVALID_MODEL_OUTPUT, detail=str(error))
                except ValueError as error:
                    return stop(
                        RunStopCode.INVALID_MODEL_OUTPUT,
                        detail=f"Working Set transition rejected: {error}",
                    )
                except Exception as error:  # noqa: BLE001 - durable cognition admission failure terminates this Run.
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=(
                            "Working Set transition admission failed: "
                            f"{type(error).__name__}: {error}"
                        ),
                    )
                pre_caller_tool_exchange_messages.clear()
                post_caller_tool_exchange_messages.clear()
                transient_working_set_digest = None
                if selection_changed:
                    external_observation_gate_reason = None
                    observation_only_turns = 0
                    no_progress_turns = 0
                messages.append(
                    {
                        "role": "assistant",
                        "content": result.content,
                        "workingSetTransition": result.working_set_transition.to_dict(),
                    }
                )
                recorder.record(
                    "working_set_transition_applied",
                    {
                        "turnId": turn_id,
                        "proposalDigest": result.working_set_transition.digest,
                        "sourceWorkingSetDigest": working_view.working_set_digest,
                        "sourceModelViewDigest": request.context_digest,
                        "nextAttemptId": committed_working_set.attempt_id,
                        "committedWorkingSetDigest": committed_working_set.digest,
                        "selectionChanged": selection_changed,
                        "attemptResetOnly": not selection_changed,
                    },
                )
                recorder.record(
                    "run_progress_evaluated",
                    {
                        "turnId": turn_id,
                        "observationOnly": False,
                        "actionProgress": selection_changed,
                        "newEvidence": False,
                        "observationOnlyTurns": observation_only_turns,
                        "noProgressTurns": no_progress_turns,
                        "cognitionAttemptReset": True,
                        "workingSetSelectionChanged": selection_changed,
                    },
                )
                try:
                    bind_run_state()
                except ToolBridgeError as state_error:
                    return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(state_error))
                except Exception as state_error:  # noqa: BLE001
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=f"{type(state_error).__name__}: {state_error}",
                    )
                continue
            if result.tool_program_action is not None:
                if not request.capabilities.tool_program or not self.tool_program_actions:
                    return stop(
                        RunStopCode.INVALID_MODEL_OUTPUT,
                        detail="Agent requested ToolProgram without exact turn capability",
                    )
                action = result.tool_program_action
                admitted_program_tools = {tool.name for tool in request.tools}
                unavailable_program_tools = sorted(
                    {
                        step.tool_name
                        for step in action.program.steps
                        if step.tool_name not in admitted_program_tools
                    }
                )
                if unavailable_program_tools:
                    return stop(
                        RunStopCode.INVALID_MODEL_OUTPUT,
                        detail=(
                            "ToolProgram requested Tools outside the exact turn surface: "
                            + ", ".join(unavailable_program_tools)
                        ),
                    )
                if action.physical_tool_calls > int(
                    request.remaining_budget.get("toolCalls", 0)
                ):
                    return stop(
                        RunStopCode.BUDGET_EXHAUSTED,
                        detail="ToolProgram exceeds remaining physical Tool Call budget",
                    )
                assistant_program_message: dict[str, JsonValue] = {
                    "role": "assistant",
                    "content": result.content,
                    "toolProgramAction": action.to_dict(),
                }
                messages.append(assistant_program_message)
                raw_program_observations: list[ToolObservation] = []
                retained_program_observations: list[ToolObservation] = []
                program_calls: list[AgentToolCall] = []
                for program_index in range(len(action.program.steps)):
                    try:
                        program_call = derive_tool_program_inner_call(
                            action,
                            program_index,
                            tuple(raw_program_observations),
                        )
                    except (TypeError, ValueError) as error:
                        return stop(
                            RunStopCode.INVALID_MODEL_OUTPUT,
                            detail=f"ToolProgram dataflow rejected: {error}",
                        )
                    program_calls.append(program_call)
                    stopped = execute_tool_calls(
                        (program_call,),
                        turn_id=turn_id,
                        sequence=sequence,
                        turn_observations=retained_program_observations,
                        raw_observation_sink=raw_program_observations,
                        project_to_messages=False,
                    )
                    if stopped is not None:
                        return stopped
                    if raw_program_observations[-1].status != "observed":
                        break
                try:
                    recovery = recover_tool_program_action(
                        action,
                        tuple(raw_program_observations),
                    )
                except (TypeError, ValueError) as error:
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=f"ToolProgram result reconstruction failed: {error}",
                    )
                if not recovery.terminal or recovery.terminal_result is None:
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail="ToolProgram execution ended without a terminal result",
                    )
                compact_result = recovery.terminal_result.to_model_projection()
                compact_message: dict[str, JsonValue] = {
                    "role": "user",
                    "content": (
                        "Harness ToolProgram result: "
                        + canonical_bytes(compact_result).decode("utf-8")
                    ),
                }
                messages.append(compact_message)
                if working_view is not None:
                    if (
                        transient_working_set_digest is not None
                        and transient_working_set_digest != working_view.working_set_digest
                    ):
                        pre_caller_tool_exchange_messages.clear()
                        post_caller_tool_exchange_messages.clear()
                    transient_working_set_digest = working_view.working_set_digest
                    post_caller_tool_exchange_messages.extend(
                        (assistant_program_message, compact_message)
                    )
                recorder.record(
                    "tool_program_completed",
                    {
                        "turnId": turn_id,
                        "actionDigest": action.digest,
                        "programDigest": action.program.digest,
                        "physicalToolCalls": len(raw_program_observations),
                        "status": recovery.terminal_result.status,
                        "modelProjectionDigest": canonical_digest(compact_result),
                    },
                )
                stopped = evaluate_turn_progress(
                    tuple(program_calls),
                    retained_program_observations,
                    turn_id=turn_id,
                )
                if stopped is not None:
                    return stopped
                continue
            if (
                result.conclusion is not None
                and result.conclusion.status == "candidate_completed"
                and self.scheduling_mode is LoopSchedulingMode.DELIBERATE_THEN_ACT
                and sequence == 1
            ):
                # E2/E3: the first no-runtime-Tool turn is cognition only. The
                # Provider call, token/deadline accounting, durable completion and
                # replay semantics above are unchanged; only the scheduling policy
                # declines to treat this first candidate conclusion as Run completion.
                # The second turn is then projected with the ordinary exact Tool
                # surface. No raw Adapter/Tool authority is handed to a Driver.
                messages.append({
                    "role": "assistant",
                    "content": result.content,
                })
                deliberation_record: dict[str, JsonValue] = {
                    "schemaVersion": 1,
                    "kind": "ordivon.non-authoritative-scheduling-deliberation",
                    "truthRole": "model-cognition-not-world-truth-or-effect-authority",
                    "turnId": turn_id,
                    "resultDigest": result.digest,
                    "summary": result.conclusion.summary,
                    "unresolvedUnknowns": list(result.conclusion.unresolved_unknowns),
                }
                messages.append({
                    "role": "user",
                    "content": (
                        "Harness scheduling note: the preceding candidate conclusion "
                        "was retained only as non-authoritative deliberation. Re-check "
                        "it against the unchanged Context. Runtime Tools, if admitted "
                        "by this exact turn, are now available for the action/evidence "
                        "you currently endorse. Deliberation record: "
                        + canonical_bytes(deliberation_record).decode("utf-8")
                    ),
                })
                recorder.record(
                    "deliberation_phase_completed",
                    {
                        "turnId": turn_id,
                        "resultDigest": result.digest,
                        "conclusionDigest": canonical_digest(result.conclusion.to_dict()),
                        "externalEffect": False,
                    },
                )
                try:
                    bind_run_state()
                except ToolBridgeError as state_error:
                    return stop(RunStopCode.RUNTIME_UNKNOWN, detail=str(state_error))
                except Exception as state_error:  # noqa: BLE001
                    return stop(
                        RunStopCode.HARNESS_FAILED,
                        detail=f"{type(state_error).__name__}: {state_error}",
                    )
                continue

            if result.conclusion is not None:
                conclusion_validator = getattr(
                    self.tool_bridge, "validate_conclusion", None
                )
                if callable(conclusion_validator):
                    try:
                        conclusion_validator(result.conclusion)
                    except ToolBridgeError as error:
                        if not error.recoverable_by_model:
                            return stop(
                                RunStopCode.INVALID_MODEL_OUTPUT,
                                detail=f"Conclusion rejected: {error}",
                            )
                        if (
                            conclusion_corrections
                            >= self.budget.max_conclusion_corrections
                        ):
                            return stop(
                                RunStopCode.INVALID_MODEL_OUTPUT,
                                detail=(
                                    "Conclusion correction budget exhausted after "
                                    f"local rejection: {error}"
                                ),
                            )
                        conclusion_corrections += 1
                        messages.append(
                            {
                                "role": "assistant",
                                "content": result.content,
                                "conclusion": result.conclusion.to_dict(),
                            }
                        )
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Harness conclusion gate rejected this candidate "
                                    "conclusion. Correct the candidate using the caller/domain "
                                    "rejection reason below; use available tools or evidence only "
                                    f"when relevant: {str(error)[:1_500]}"
                                ),
                            }
                        )
                        recorder.record(
                            "conclusion_rejected",
                            {
                                "conclusionDigest": canonical_digest(
                                    result.conclusion.to_dict()
                                ),
                                "errorKind": error.kind.value,
                                "correction": conclusion_corrections,
                                "conclusionCorrection": conclusion_corrections,
                                "safeToCorrect": True,
                            },
                        )
                        try:
                            bind_run_state()
                        except ToolBridgeError as state_error:
                            return stop(
                                RunStopCode.RUNTIME_UNKNOWN,
                                detail=str(state_error),
                            )
                        except Exception as state_error:  # noqa: BLE001
                            return stop(
                                RunStopCode.HARNESS_FAILED,
                                detail=(
                                    f"{type(state_error).__name__}: {state_error}"
                                ),
                            )
                        continue
                    except Exception as error:  # noqa: BLE001
                        return stop(
                            RunStopCode.HARNESS_FAILED,
                            detail=(
                                "Conclusion validation failed: "
                                f"{type(error).__name__}: {error}"
                            ),
                        )
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

            budgeted_tool_calls = tuple(
                call
                for call in result.tool_calls
                if call.name != WORKING_SET_HISTORY_CONTROL_NAME
                and call.argument_error != "unavailable_tool"
            )
            if tool_calls + len(budgeted_tool_calls) > self.budget.max_tool_calls:
                return stop(RunStopCode.BUDGET_EXHAUSTED)
            assistant_tool_message: dict[str, JsonValue] = {
                "role": "assistant",
                "content": result.content,
                "toolCalls": [call.to_dict() for call in result.tool_calls],
            }
            messages.append(assistant_tool_message)
            if working_view is not None:
                if (
                    transient_working_set_digest is not None
                    and transient_working_set_digest != working_view.working_set_digest
                ):
                    pre_caller_tool_exchange_messages.clear()
                    post_caller_tool_exchange_messages.clear()
                transient_working_set_digest = working_view.working_set_digest
                post_caller_tool_exchange_messages.append(dict(assistant_tool_message))
            turn_observations: list[ToolObservation] = []
            stopped = execute_tool_calls(
                result.tool_calls,
                turn_id=turn_id,
                sequence=sequence,
                turn_observations=turn_observations,
            )
            if stopped is not None:
                return stopped
            if working_view is not None:
                post_caller_tool_exchange_messages.extend(
                    observation.to_model_message()
                    for observation in turn_observations
                )

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
    input_tokens = usage.get("input_tokens", usage.get("inputTokens"))
    output_tokens = usage.get("output_tokens", usage.get("outputTokens"))
    if (
        type(input_tokens) is int
        and input_tokens >= 0
        and type(output_tokens) is int
        and output_tokens >= 0
    ):
        return input_tokens + output_tokens
    return None

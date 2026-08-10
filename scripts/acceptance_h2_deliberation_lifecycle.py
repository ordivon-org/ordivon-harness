from __future__ import annotations

import argparse
import json
import subprocess
from collections import deque
from pathlib import Path
from typing import Any, cast

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, validate_json_value

from ordivon_harness.deliberation import DeliberationLifecycleError, DeliberationThenToolRunner
from ordivon_harness.domain_tools import (
    AgentToolDefinition,
    DomainToolCatalog,
    DomainToolLoopPlan,
    ToolObservation,
)
from ordivon_harness.ordivon.control import CancellationToken, ExecutionControl
from ordivon_harness.ordivon.loop import RunBudget
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnRequest,
    AgentTurnResult,
)

REVISION = "harness-deliberation-lifecycle-h2-v1"
CONTEXT = canonical_digest({"kind": "harness-h2-lifecycle-acceptance"})
TOOL = AgentToolDefinition(
    "submit_choice",
    "Record one neutral caller-owned choice without external effect.",
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {"choice": {"type": "string"}},
        "required": ["choice"],
    },
)


def _git_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


class Clock:
    def __init__(self, value: int = 1000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value

    def advance(self, ms: int) -> None:
        self.value += ms


class Handle:
    def __init__(
        self,
        adapter: "Adapter",
        result: AgentTurnResult,
        *,
        on_poll=None,
        defer_result_after_hook: bool = False,
    ) -> None:
        self.adapter = adapter
        self.result = result
        self.on_poll = on_poll
        self.defer_result_after_hook = defer_result_after_hook
        self.returned = False
        self.cancelled = False

    def poll(self, timeout_seconds: float) -> AgentTurnResult | None:
        self.adapter.polls.append(timeout_seconds)
        if self.on_poll is not None:
            fn, self.on_poll = self.on_poll, None
            fn()
            if self.defer_result_after_hook:
                return None
        if self.cancelled:
            return None
        if not self.returned:
            self.returned = True
            return self.result
        return None

    def cancel(self) -> None:
        self.cancelled = True
        self.adapter.cancel_calls += 1


class Adapter:
    adapter_id = "adapter:h2-acceptance"
    model_id = "model:h2-acceptance"
    supports_call_handle = True

    def __init__(
        self,
        results: list[AgentTurnResult],
        *,
        token_bound: int = 10,
        first_poll_hook=None,
        defer_first_result_after_hook: bool = False,
    ) -> None:
        self.results = deque(results)
        self.token_bound = token_bound
        self.first_poll_hook = first_poll_hook
        self.defer_first_result_after_hook = defer_first_result_after_hook
        self.requests: list[AgentTurnRequest] = []
        self.controls: list[ExecutionControl] = []
        self.polls: list[float] = []
        self.cancel_calls = 0

    def provider_request_digest(self, request: AgentTurnRequest) -> str:
        return request.dispatch_digest

    def request_token_upper_bound(self, request: AgentTurnRequest) -> int:
        return self.token_bound

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        raise AssertionError("H2 lifecycle acceptance must not use uncontrolled invoke")

    def start_invoke(self, request: AgentTurnRequest, control: ExecutionControl) -> Handle:
        self.requests.append(request)
        self.controls.append(control)
        result = self.results.popleft()
        first = len(self.requests) == 1
        hook = self.first_poll_hook if first else None
        return Handle(
            self,
            result,
            on_poll=hook,
            defer_result_after_hook=first and self.defer_first_result_after_hook,
        )


class Bridge:
    catalog = DomainToolCatalog("domain:h2-acceptance", "1", (TOOL,))
    bridge_identity: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.h2-deterministic-bridge",
        "externalEffect": False,
    }

    def __init__(self) -> None:
        self.choices: list[str] = []

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        choice = call.arguments["choice"]
        if not isinstance(choice, str):
            raise ValueError("H2 deterministic choice must be text")
        self.choices.append(choice)
        return ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="observed",
            structured_content={
                "recorded": True,
                "externalEffect": False,
                "stepId": step_id,
            },
        )


def _conclusion(name: str, summary: str, tokens: int) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:{name}",
        model_id=Adapter.model_id,
        content=None,
        tool_calls=(),
        conclusion=AgentRunConclusion("candidate_completed", summary),
        usage={"total_tokens": tokens},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"name": name}),
    )


def _tool(name: str, choice: str, tokens: int) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:{name}",
        model_id=Adapter.model_id,
        content=None,
        tool_calls=(AgentToolCall(f"tool-call:{name}", "submit_choice", {"choice": choice}),),
        conclusion=None,
        usage={"total_tokens": tokens},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"name": name}),
    )


def _request() -> AgentTurnRequest:
    return AgentTurnRequest(
        harness_run_id="harness-run:h2-acceptance-a",
        turn_id="turn:h2-acceptance-a:1",
        sequence=1,
        assignment_id="assignment:h2-acceptance",
        context_digest=CONTEXT,
        tool_catalog_digest=canonical_digest({"tools": []}),
        messages=(
            {"role": "system", "content": "Deliberate only."},
            {"role": "user", "content": "Choose cobalt later."},
        ),
        tools=(),
        remaining_budget={"modelCalls": 999, "toolCalls": 999, "totalTokens": 999999},
    )


def _budget(**overrides: Any) -> RunBudget:
    values: dict[str, Any] = {
        "max_model_calls": 3,
        "max_tool_calls": 2,
        "max_observation_bytes": 32768,
        "max_wall_time_ms": 1000,
        "max_total_tokens": 100,
        "max_model_retries": 0,
        "max_tool_corrections": 0,
        "max_conclusion_corrections": 0,
        "max_observation_only_turns": 0,
        "max_no_progress_turns": 1,
        "max_model_observation_bytes": 32768,
    }
    values.update(overrides)
    return RunBudget(**values)


def _plan() -> DomainToolLoopPlan:
    return DomainToolLoopPlan(
        harness_run_id="harness-run:h2-acceptance-b",
        assignment_id="assignment:h2-acceptance",
        context_digest=CONTEXT,
        initial_messages=(
            {"role": "system", "content": "Use the caller-owned Tool."},
            {"role": "user", "content": "Same deterministic task."},
        ),
        allowed_tools=("submit_choice",),
        budget=_budget(max_model_calls=99, max_total_tokens=999999, max_wall_time_ms=999999),
    )


def _error(error: DeliberationLifecycleError) -> dict[str, JsonValue]:
    value: dict[str, JsonValue] = {
        "stopCode": str(getattr(error.stop_code, "value", error.stop_code)),
        "phase": error.phase,
        "providerDispatched": error.provider_dispatched,
    }
    validate_json_value(value)
    return value


def run() -> dict[str, JsonValue]:
    clock = Clock()
    normal_adapter = Adapter([
        _conclusion("normal-a", "Cobalt is my considered choice.", 30),
        _tool("normal-b1", "cobalt", 20),
        _conclusion("normal-b2", "Recorded cobalt.", 10),
    ])
    normal_bridge = Bridge()
    normal = DeliberationThenToolRunner(
        normal_adapter, normal_bridge, monotonic_ms=clock
    ).run_lifecycle_bound(_request(), _plan(), budget=_budget())
    normal_record: dict[str, JsonValue] = {
        "choices": list(normal_bridge.choices),
        "phaseATokens": normal.phase_a_total_tokens,
        "phaseBModelCalls": normal.phase_b_budget.max_model_calls,
        "phaseBTokens": normal.phase_b_budget.max_total_tokens,
        "aggregateUsage": normal.aggregate_usage,
        "sharedCancellation": normal_adapter.controls[0].cancellation
        is normal_adapter.controls[1].cancellation,
        "sharedDeadline": normal_adapter.controls[0].deadline.expires_at_ms
        == normal_adapter.controls[1].deadline.expires_at_ms,
        "executionDigest": normal.execution_digest,
    }
    validate_json_value(normal_record)

    exhaustion_adapter = Adapter([_conclusion("exhaustion", "Known.", 50)])
    exhaustion_bridge = Bridge()
    try:
        DeliberationThenToolRunner(exhaustion_adapter, exhaustion_bridge).run_lifecycle_bound(
            _request(), _plan(), budget=_budget(max_total_tokens=50)
        )
        raise AssertionError("expected phase-A aggregate budget exhaustion")
    except DeliberationLifecycleError as exc:
        exhaustion = _error(exc)
    exhaustion["providerCalls"] = len(exhaustion_adapter.requests)
    exhaustion["choices"] = list(exhaustion_bridge.choices)

    preflight_adapter = Adapter([_conclusion("unused", "Unused.", 1)], token_bound=101)
    try:
        DeliberationThenToolRunner(preflight_adapter, Bridge()).run_lifecycle_bound(
            _request(), _plan(), budget=_budget(max_total_tokens=100)
        )
        raise AssertionError("expected token preflight rejection")
    except DeliberationLifecycleError as exc:
        preflight = _error(exc)
    preflight["providerCalls"] = len(preflight_adapter.requests)

    pending_clock = Clock()
    pending_token = CancellationToken(monotonic_ms=pending_clock)
    pending_adapter = Adapter(
        [_conclusion("cancel-pending", "Unused.", 1)],
        first_poll_hook=pending_token.cancel,
        defer_first_result_after_hook=True,
    )
    pending_bridge = Bridge()
    try:
        DeliberationThenToolRunner(
            pending_adapter, pending_bridge, monotonic_ms=pending_clock
        ).run_lifecycle_bound(_request(), _plan(), budget=_budget(), cancellation=pending_token)
        raise AssertionError("expected in-flight cancellation")
    except DeliberationLifecycleError as exc:
        cancel_pending = _error(exc)
    cancel_pending["handleCancelCalls"] = pending_adapter.cancel_calls
    cancel_pending["choices"] = list(pending_bridge.choices)

    race_clock = Clock()
    race_token = CancellationToken(monotonic_ms=race_clock)
    race_adapter = Adapter(
        [_conclusion("cancel-race", "Known result.", 1)],
        first_poll_hook=race_token.cancel,
    )
    race_bridge = Bridge()
    try:
        DeliberationThenToolRunner(
            race_adapter, race_bridge, monotonic_ms=race_clock
        ).run_lifecycle_bound(_request(), _plan(), budget=_budget(), cancellation=race_token)
        raise AssertionError("expected cancellation at phase boundary")
    except DeliberationLifecycleError as exc:
        cancel_result_race = _error(exc)
    cancel_result_race["handleCancelCalls"] = race_adapter.cancel_calls
    cancel_result_race["choices"] = list(race_bridge.choices)

    deadline_clock = Clock()

    def consume_phase_a_time() -> None:
        deadline_clock.advance(400)

    deadline_adapter = Adapter(
        [
            _conclusion("deadline-a", "Cobalt.", 10),
            _tool("deadline-b1", "cobalt", 10),
            _conclusion("deadline-b2", "Done.", 10),
        ],
        first_poll_hook=consume_phase_a_time,
    )
    deadline = DeliberationThenToolRunner(
        deadline_adapter, Bridge(), monotonic_ms=deadline_clock
    ).run_lifecycle_bound(_request(), _plan(), budget=_budget(max_wall_time_ms=1000))
    deadline_record: dict[str, JsonValue] = {
        "phaseAElapsedMs": deadline.phase_a_elapsed_ms,
        "phaseBWallBudgetMs": deadline.phase_b_budget.max_wall_time_ms,
        "phaseADeadline": deadline_adapter.controls[0].deadline.expires_at_ms,
        "phaseBDeadline": deadline_adapter.controls[1].deadline.expires_at_ms,
    }
    validate_json_value(deadline_record)

    class MinimalAdapter:
        adapter_id = "adapter:h2-minimal"
        model_id = Adapter.model_id

        def provider_request_digest(self, request: AgentTurnRequest) -> str:
            return request.dispatch_digest

        def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
            return _conclusion("minimal", "Known.", 1)

    try:
        DeliberationThenToolRunner(MinimalAdapter(), Bridge()).run_lifecycle_bound(
            _request(), _plan(), budget=_budget()
        )
        raise AssertionError("expected uncontrolled adapter rejection")
    except DeliberationLifecycleError as exc:
        uncontrolled = _error(exc)

    normal_usage = cast(dict[str, JsonValue], normal_record["aggregateUsage"])
    gates = {
        "normalChoiceRecorded": normal_record["choices"] == ["cobalt"],
        "aggregateModelBudgetCarried": normal_record["phaseBModelCalls"] == 2,
        "aggregateTokenBudgetCarried": normal_record["phaseBTokens"] == 70,
        "aggregateUsageNoDoubleSpend": normal_usage["modelCalls"] == 3
        and normal_usage["totalTokens"] == 60,
        "oneCancellationAuthority": normal_record["sharedCancellation"] is True,
        "oneAbsoluteDeadline": normal_record["sharedDeadline"] is True,
        "phaseAExhaustionBlocksTools": exhaustion["stopCode"] == "budget_exhausted"
        and exhaustion["providerCalls"] == 1
        and exhaustion["choices"] == [],
        "tokenPreflightBlocksProvider": preflight["stopCode"] == "budget_exhausted"
        and preflight["providerCalls"] == 0,
        "pendingCancelBecomesUnknownAndBlocksTools": cancel_pending["stopCode"] == "cancel_unknown"
        and cancel_pending["handleCancelCalls"] == 1
        and cancel_pending["choices"] == [],
        "knownResultCancelRaceBlocksToolsWithoutFalseUnknown": cancel_result_race["stopCode"] == "cancelled"
        and cancel_result_race["handleCancelCalls"] == 0
        and cancel_result_race["choices"] == [],
        "deadlineConsumptionCarries": deadline_record["phaseAElapsedMs"] == 400
        and deadline_record["phaseBWallBudgetMs"] == 600
        and deadline_record["phaseADeadline"] == deadline_record["phaseBDeadline"],
        "uncontrolledAdapterFailsClosed": uncontrolled["stopCode"] == "harness_failed"
        and uncontrolled["providerDispatched"] is False,
    }
    receipt: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness.deliberation-lifecycle-h2",
        "status": "accepted" if all(gates.values()) else "falsified",
        "researchOutcome": "lifecycle-semantics-accepted" if all(gates.values()) else "lifecycle-semantics-falsified",
        "implementationRevision": _git_revision(),
        "experimentRevision": REVISION,
        "contextDigest": CONTEXT,
        "normal": normal_record,
        "phaseAExhaustion": exhaustion,
        "tokenPreflight": preflight,
        "pendingCancellation": cancel_pending,
        "cancelResultRace": cancel_result_race,
        "deadlineCarry": deadline_record,
        "uncontrolledAdapter": uncontrolled,
        "gates": gates,
        "interpretation": {
            "oneAggregateBudgetValidated": True,
            "oneCancellationAuthorityValidated": True,
            "oneAbsoluteDeadlineValidated": True,
            "domainStrategyOwnedByLifecycle": False,
            "recommendedPublicApiForced": False,
            "defaultHiddenDeliberationForced": False,
        },
    }
    validate_json_value(receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic Harness H2 lifecycle acceptance")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = run()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(canonical_bytes(receipt) + b"\n")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    if receipt["status"] != "accepted":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

from __future__ import annotations

import unittest
from collections import deque

from anc_canonical import canonical_digest

from ordivon_harness.deliberation import DeliberationLifecycleError, DeliberationThenToolRunner
from ordivon_harness.domain_tools import (
    AgentToolDefinition,
    DomainToolCatalog,
    DomainToolLoopPlan,
    ToolObservation,
)
from ordivon_harness.ordivon.control import CancellationToken, ExecutionControl
from ordivon_harness.ordivon.loop import RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnRequest,
    AgentTurnResult,
)


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
        adapter: "ControlledAdapter",
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


class ControlledAdapter:
    adapter_id = "adapter:h2-controlled"
    model_id = "model:h2"
    supports_call_handle = True

    def __init__(
        self,
        results,
        *,
        token_bound: int = 10,
        first_poll_hook=None,
        defer_first_result_after_hook: bool = False,
    ) -> None:
        self.results = deque(results)
        self.requests: list[AgentTurnRequest] = []
        self.controls: list[ExecutionControl] = []
        self.token_bound = token_bound
        self.first_poll_hook = first_poll_hook
        self.defer_first_result_after_hook = defer_first_result_after_hook
        self.polls: list[float] = []
        self.cancel_calls = 0

    def provider_request_digest(self, request: AgentTurnRequest) -> str:
        return request.dispatch_digest

    def request_token_upper_bound(self, request: AgentTurnRequest) -> int:
        return self.token_bound

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        raise AssertionError("H2 lifecycle-bound path must not use uncontrolled invoke")

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


TOOL = AgentToolDefinition(
    "submit_choice",
    "Record neutral choice.",
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {"choice": {"type": "string"}},
        "required": ["choice"],
    },
)
CONTEXT = canonical_digest({"context": "h2"})


class Bridge:
    catalog = DomainToolCatalog("domain:h2", "1", (TOOL,))
    bridge_identity = {"schemaVersion": 1, "kind": "h2-bridge", "externalEffect": False}

    def __init__(self) -> None:
        self.choices: list[str] = []

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        choice = call.arguments["choice"]
        assert isinstance(choice, str)
        self.choices.append(choice)
        return ToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="observed",
            structured_content={"recorded": True, "stepId": step_id},
        )


def result_conclusion(call: str, summary: str, *, tokens: int) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=call,
        model_id="model:h2",
        content=None,
        tool_calls=(),
        conclusion=AgentRunConclusion("candidate_completed", summary),
        usage={"total_tokens": tokens},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"call": call}),
    )


def result_tool(call: str, choice: str, *, tokens: int) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=call,
        model_id="model:h2",
        content=None,
        tool_calls=(AgentToolCall(f"tool:{call}", "submit_choice", {"choice": choice}),),
        conclusion=None,
        usage={"total_tokens": tokens},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"call": call}),
    )


def deliberation_request() -> AgentTurnRequest:
    return AgentTurnRequest(
        harness_run_id="harness-run:h2-a",
        turn_id="turn:h2:a:1",
        sequence=1,
        assignment_id="assignment:h2",
        context_digest=CONTEXT,
        tool_catalog_digest=canonical_digest({"tools": []}),
        messages=(
            {"role": "system", "content": "Think first."},
            {"role": "user", "content": "Neutral task."},
        ),
        tools=(),
        remaining_budget={"modelCalls": 999, "toolCalls": 999, "totalTokens": 999999},
    )


def tool_plan() -> DomainToolLoopPlan:
    return DomainToolLoopPlan(
        harness_run_id="harness-run:h2-b",
        assignment_id="assignment:h2",
        context_digest=CONTEXT,
        initial_messages=(
            {"role": "system", "content": "Use tool."},
            {"role": "user", "content": "Neutral task."},
        ),
        allowed_tools=("submit_choice",),
        budget=RunBudget(99, 99, 99999, 999999, 999999),
    )


def budget(**overrides) -> RunBudget:
    values = dict(
        max_model_calls=3,
        max_tool_calls=2,
        max_observation_bytes=32768,
        max_wall_time_ms=1000,
        max_total_tokens=100,
        max_model_retries=0,
        max_tool_corrections=0,
        max_conclusion_corrections=0,
        max_observation_only_turns=0,
        max_no_progress_turns=1,
        max_model_observation_bytes=32768,
    )
    values.update(overrides)
    return RunBudget(**values)


class DeliberationLifecycleH2Tests(unittest.TestCase):
    def test_one_budget_is_consumed_across_both_phases(self) -> None:
        clock = Clock()
        adapter = ControlledAdapter(
            [
                result_conclusion("a", "Choose cobalt.", tokens=30),
                result_tool("b1", "cobalt", tokens=20),
                result_conclusion("b2", "Done.", tokens=10),
            ]
        )
        bridge = Bridge()
        execution = DeliberationThenToolRunner(
            adapter, bridge, monotonic_ms=clock
        ).run_lifecycle_bound(deliberation_request(), tool_plan(), budget=budget())

        self.assertEqual(bridge.choices, ["cobalt"])
        self.assertEqual(execution.phase_a_total_tokens, 30)
        self.assertEqual(execution.phase_b_budget.max_model_calls, 2)
        self.assertEqual(execution.phase_b_budget.max_total_tokens, 70)
        self.assertEqual(execution.aggregate_usage["modelCalls"], 3)
        self.assertEqual(execution.aggregate_usage["totalTokens"], 60)
        self.assertEqual(adapter.requests[0].remaining_budget["modelCalls"], 3)
        self.assertEqual(adapter.requests[0].remaining_budget["totalTokens"], 100)
        self.assertEqual(adapter.requests[1].remaining_budget["modelCalls"], 2)
        self.assertEqual(adapter.requests[1].remaining_budget["totalTokens"], 70)
        self.assertIs(adapter.controls[0].cancellation, adapter.controls[1].cancellation)
        self.assertEqual(adapter.controls[0].deadline.expires_at_ms, adapter.controls[1].deadline.expires_at_ms)

    def test_budget_exhaustion_after_deliberation_never_opens_tool_phase(self) -> None:
        clock = Clock()
        adapter = ControlledAdapter([result_conclusion("a", "Done.", tokens=50)])
        bridge = Bridge()
        with self.assertRaises(DeliberationLifecycleError) as raised:
            DeliberationThenToolRunner(adapter, bridge, monotonic_ms=clock).run_lifecycle_bound(
                deliberation_request(),
                tool_plan(),
                budget=budget(max_total_tokens=50),
            )
        self.assertEqual(raised.exception.stop_code, RunStopCode.BUDGET_EXHAUSTED)
        self.assertEqual(raised.exception.phase, "between-phases")
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(bridge.choices, [])

    def test_token_preflight_stops_before_provider_dispatch(self) -> None:
        adapter = ControlledAdapter([result_conclusion("unused", "unused", tokens=1)], token_bound=101)
        with self.assertRaises(DeliberationLifecycleError) as raised:
            DeliberationThenToolRunner(adapter, Bridge()).run_lifecycle_bound(
                deliberation_request(), tool_plan(), budget=budget(max_total_tokens=100)
            )
        self.assertEqual(raised.exception.stop_code, RunStopCode.BUDGET_EXHAUSTED)
        self.assertFalse(raised.exception.provider_dispatched)
        self.assertEqual(adapter.requests, [])

    def test_pre_cancelled_composition_never_dispatches_provider(self) -> None:
        clock = Clock()
        token = CancellationToken()
        token.cancel()
        adapter = ControlledAdapter([result_conclusion("unused", "unused", tokens=1)])
        with self.assertRaises(DeliberationLifecycleError) as raised:
            DeliberationThenToolRunner(adapter, Bridge(), monotonic_ms=clock).run_lifecycle_bound(
                deliberation_request(), tool_plan(), budget=budget(), cancellation=token
            )
        self.assertEqual(raised.exception.stop_code, RunStopCode.CANCELLED)
        self.assertFalse(raised.exception.provider_dispatched)
        self.assertEqual(adapter.requests, [])

    def test_inflight_phase_a_cancellation_uses_handle_and_never_opens_tools(self) -> None:
        clock = Clock()
        token = CancellationToken()
        adapter = ControlledAdapter(
            [result_conclusion("a", "unused", tokens=1)],
            first_poll_hook=token.cancel,
            defer_first_result_after_hook=True,
        )
        with self.assertRaises(DeliberationLifecycleError) as raised:
            DeliberationThenToolRunner(adapter, Bridge(), monotonic_ms=clock).run_lifecycle_bound(
                deliberation_request(), tool_plan(), budget=budget(), cancellation=token
            )
        self.assertEqual(raised.exception.stop_code, RunStopCode.CANCEL_UNKNOWN)
        self.assertTrue(raised.exception.provider_dispatched)
        self.assertEqual(adapter.cancel_calls, 1)
        self.assertEqual(len(adapter.requests), 1)

    def test_cancel_and_provider_result_race_keeps_known_result_but_blocks_tools(self) -> None:
        clock = Clock()
        token = CancellationToken(monotonic_ms=clock)
        adapter = ControlledAdapter(
            [result_conclusion("a", "Known result.", tokens=1)],
            first_poll_hook=token.cancel,
        )
        bridge = Bridge()
        with self.assertRaises(DeliberationLifecycleError) as raised:
            DeliberationThenToolRunner(adapter, bridge, monotonic_ms=clock).run_lifecycle_bound(
                deliberation_request(), tool_plan(), budget=budget(), cancellation=token
            )
        self.assertEqual(raised.exception.stop_code, RunStopCode.CANCELLED)
        self.assertTrue(raised.exception.provider_dispatched)
        self.assertEqual(adapter.cancel_calls, 0)
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(bridge.choices, [])

    def test_shared_absolute_deadline_reaches_tool_loop(self) -> None:
        clock = Clock()
        def consume_time():
            clock.advance(400)
        adapter = ControlledAdapter(
            [
                result_conclusion("a", "Choose cobalt.", tokens=10),
                result_tool("b1", "cobalt", tokens=10),
                result_conclusion("b2", "Done.", tokens=10),
            ],
            first_poll_hook=consume_time,
        )
        execution = DeliberationThenToolRunner(
            adapter, Bridge(), monotonic_ms=clock
        ).run_lifecycle_bound(
            deliberation_request(), tool_plan(), budget=budget(max_wall_time_ms=1000)
        )
        self.assertEqual(execution.phase_a_elapsed_ms, 400)
        self.assertEqual(execution.phase_b_budget.max_wall_time_ms, 600)
        self.assertEqual(execution.deadline_monotonic_ms, 2000)
        self.assertEqual(adapter.controls[0].deadline.expires_at_ms, 2000)
        self.assertEqual(adapter.controls[1].deadline.expires_at_ms, 2000)

    def test_uncontrolled_minimal_adapter_fails_closed_in_lifecycle_mode(self) -> None:
        class Minimal:
            adapter_id = "minimal"
            model_id = "model:h2"
            def provider_request_digest(self, request): return request.dispatch_digest
            def invoke(self, request): return result_conclusion("a", "Done", tokens=1)
        with self.assertRaises(DeliberationLifecycleError) as raised:
            DeliberationThenToolRunner(Minimal(), Bridge()).run_lifecycle_bound(
                deliberation_request(), tool_plan(), budget=budget()
            )
        self.assertEqual(raised.exception.stop_code, RunStopCode.HARNESS_FAILED)
        self.assertFalse(raised.exception.provider_dispatched)


if __name__ == "__main__":
    unittest.main()

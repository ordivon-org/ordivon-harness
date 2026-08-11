from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_bytes, canonical_digest

from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnRequest,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.ordivon.sqlite_runtime_bridge import SQLiteHarnessRuntimeBridge
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.working_view import (
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    WorkingSetViewProjector,
)

from tests.test_p0_sqlite_runtime_bridge import (
    FakeRuntime,
    FixedClock,
    contract,
    execution_binding,
)


def private_contract(
    suffix: str,
    *,
    max_model_calls: int,
    max_tool_calls: int,
):
    return replace(
        contract(suffix),
        budget={
            "maxModelCalls": max_model_calls,
            "maxToolCalls": max_tool_calls,
            "maxWallTimeMs": 10_000,
        },
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=True,
        ),
    )


def run_budget(
    *,
    max_model_calls: int,
    max_tool_calls: int,
    max_tool_corrections: int = 3,
    max_observation_only_turns: int = 6,
    max_no_progress_turns: int = 3,
) -> RunBudget:
    return RunBudget(
        max_model_calls=max_model_calls,
        max_tool_calls=max_tool_calls,
        max_observation_bytes=65_536,
        max_wall_time_ms=10_000,
        max_total_tokens=65_536,
        max_model_retries=1,
        max_tool_corrections=max_tool_corrections,
        max_observation_only_turns=max_observation_only_turns,
        max_no_progress_turns=max_no_progress_turns,
    )


def tool_call(call_id: str, query: str) -> AgentToolCall:
    return AgentToolCall(
        tool_call_id=call_id,
        name="search_workspace",
        arguments={"query": query, "relativePath": "src", "maxMatches": 20},
    )


def tool_turn(
    suffix: str,
    calls: tuple[AgentToolCall, ...],
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:pc15-{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content="I need bounded external evidence.",
        tool_calls=calls,
        conclusion=None,
        usage={"inputTokens": 11, "outputTokens": 7},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"pc15": suffix, "kind": "tools"}),
    )


def unavailable_turn(suffix: str, name: str = "search_workspace") -> AgentTurnResult:
    raw = '{"query":"another search"}'
    call = AgentToolCall(
        tool_call_id=f"tool-call:pc15-{suffix}-unavailable",
        name=name,
        arguments={"query": "another search"},
        argument_error="unavailable_tool",
        raw_arguments_digest=canonical_digest({"raw": raw}),
        raw_arguments_preview=raw,
    )
    return AgentTurnResult(
        model_call_id=f"model-call:pc15-{suffix}-unavailable",
        model_id=ScriptedTurnAdapter.model_id,
        content="I tried a Runtime Tool retained from earlier context.",
        tool_calls=(call,),
        conclusion=None,
        usage={"inputTokens": 13, "outputTokens": 7},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest(
            {"pc15": suffix, "kind": "unavailable"}
        ),
    )


def needs_input_turn(suffix: str, unknown: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:pc15-{suffix}-needs-input",
        model_id=ScriptedTurnAdapter.model_id,
        content="The bounded evidence cannot resolve the required fact.",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="needs_input",
            summary="Available bounded observations are insufficient for a current answer.",
            unresolved_unknowns=(unknown,),
        ),
        usage={"inputTokens": 17, "outputTokens": 9},
        finish_reason="stop",
        raw_response_digest=canonical_digest(
            {"pc15": suffix, "kind": "needs-input"}
        ),
    )


class CaptureTransport:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        self.requests.append(json.loads(body))
        return self.response


def unavailable_provider_response() -> bytes:
    return canonical_bytes(
        {
            "id": "provider-call:pc15-unavailable",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call:pc15-unavailable",
                                "type": "function",
                                "function": {
                                    "name": "search_workspace",
                                    "arguments": '{"query":"still searching"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
        }
    )


class EpistemicControlTests(unittest.TestCase):
    def test_deepseek_projects_execution_control_and_normalizes_revoked_tool(self) -> None:
        transport = CaptureTransport(unavailable_provider_response())
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=transport,
        )
        request = AgentTurnRequest(
            harness_run_id="harness-run:pc15-control-envelope",
            turn_id="turn:pc15-control-envelope:1",
            sequence=1,
            assignment_id="assignment:pc15-control-envelope",
            context_digest="sha256:" + "a" * 64,
            tool_catalog_digest="sha256:" + "b" * 64,
            messages=({"role": "user", "content": "close the bounded run"},),
            tools=(),
            remaining_budget={
                "modelCalls": 2,
                "toolCalls": 0,
                "totalTokens": 4096,
            },
        )
        result = adapter.invoke(request)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].name, "search_workspace")
        self.assertEqual(result.tool_calls[0].argument_error, "unavailable_tool")
        self.assertEqual(len(transport.requests), 1)
        body = transport.requests[0]
        messages = body["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("ordivon_harness_turn_control", messages[0]["content"])
        control = messages[-1]
        self.assertEqual(control["role"], "user")
        self.assertEqual(control["name"], "ordivon_harness_turn_control")
        self.assertIn('"admittedRuntimeTools":[]', control["content"])
        self.assertIn('"toolCalls":0', control["content"])
        self.assertEqual(messages[1:-1], list(request.messages))
        provider_tools = [item["function"]["name"] for item in body["tools"]]
        self.assertNotIn("search_workspace", provider_tools)
        self.assertIn("submit_run_conclusion", provider_tools)

    def initialize(
        self,
        root: Path,
        suffix: str,
        *,
        max_model_calls: int,
        max_tool_calls: int,
        runtime: FakeRuntime,
    ):
        run_contract = private_contract(
            suffix,
            max_model_calls=max_model_calls,
            max_tool_calls=max_tool_calls,
        )
        store = SQLiteHarnessStore.initialize(root)
        store.create_run(run_contract)
        clock = FixedClock()
        continuity = SQLiteHarnessRunContinuityStore(
            store,
            run_contract,
            clock_ms=clock,
        )
        source = HarnessWorkingViewSource(
            logical_ref=f"source://pc15/{suffix}/base",
            logical_generation="generation:1",
            messages=(
                {
                    "role": "user",
                    "content": "Resolve the current fact using only useful bounded evidence.",
                },
            ),
        )
        stored = continuity.store_working_view_source(source)
        pin = HarnessWorkingSetPin(
            slot="primary",
            logical_ref=source.logical_ref,
            logical_generation=source.logical_generation,
            resolved_digest=stored.digest,
        )
        initial = HarnessWorkingSetSpec.initial(
            f"working-attempt:pc15-{suffix}-a",
            pins=(pin,),
        )
        continuity.record_working_set(initial)
        continuity.record_working_set(initial.commit("seed P-C1.5 base view"))
        bridge = SQLiteHarnessRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
        )
        projector = WorkingSetViewProjector(store, continuity)
        return store, clock, run_contract, continuity, bridge, projector, source

    def test_multi_tool_exchange_is_complete_on_next_projected_turn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                source,
            ) = self.initialize(
                Path(directory) / "state",
                "multi-exchange",
                max_model_calls=2,
                max_tool_calls=2,
                runtime=runtime,
            )
            calls = (
                tool_call("tool-call:pc15-multi-a", "HarnessExecutionBinding"),
                tool_call("tool-call:pc15-multi-b", "Runtime"),
            )
            first = tool_turn("multi-exchange-1", calls)
            adapter = ScriptedTurnAdapter(
                (
                    first,
                    needs_input_turn(
                        "multi-exchange-2",
                        "No additional current fact is available in the bounded source.",
                    ),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(max_model_calls=2, max_tool_calls=2),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc15 multi exchange"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(runtime.workspace_exec_count, 2)
            self.assertEqual(len(adapter.requests), 2)
            second = adapter.requests[1]
            self.assertEqual(second.messages[:1], source.messages)
            self.assertEqual(second.messages[1]["role"], "assistant")
            self.assertEqual(
                [item["toolCallId"] for item in second.messages[1]["toolCalls"]],
                [call.tool_call_id for call in calls],
            )
            self.assertEqual(
                [message["toolCallId"] for message in second.messages[2:]],
                [call.tool_call_id for call in calls],
            )
            self.assertTrue(all(message["role"] == "tool" for message in second.messages[2:]))
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_soft_observation_gate_gives_agent_closure_turn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _,
            ) = self.initialize(
                Path(directory) / "state",
                "soft-gate",
                max_model_calls=2,
                max_tool_calls=2,
                runtime=runtime,
            )
            unknown = "The authoritative current launch code is not present in bounded evidence."
            adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "soft-gate-1",
                        (tool_call("tool-call:pc15-soft-search", "HarnessExecutionBinding"),),
                    ),
                    needs_input_turn("soft-gate-2", unknown),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(
                    max_model_calls=2,
                    max_tool_calls=2,
                    max_observation_only_turns=1,
                ),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc15 soft gate"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(result.conclusion.unresolved_unknowns, (unknown,))
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(len(adapter.requests), 2)
            self.assertEqual(adapter.requests[1].tools, ())
            self.assertEqual(adapter.requests[1].remaining_budget["toolCalls"], 1)
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

    def test_hard_tool_gate_corrects_historical_tool_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeRuntime("direct")
            (
                store,
                clock,
                run_contract,
                continuity,
                bridge,
                projector,
                _,
            ) = self.initialize(
                Path(directory) / "state",
                "hard-gate",
                max_model_calls=3,
                max_tool_calls=1,
                runtime=runtime,
            )
            unknown = "The current authoritative launch code remains unresolved."
            unavailable = unavailable_turn("hard-gate-2")
            adapter = ScriptedTurnAdapter(
                (
                    tool_turn(
                        "hard-gate-1",
                        (tool_call("tool-call:pc15-hard-search", "HarnessExecutionBinding"),),
                    ),
                    unavailable,
                    needs_input_turn("hard-gate-3", unknown),
                )
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=run_budget(max_model_calls=3, max_tool_calls=1),
                clock_ms=clock,
                monotonic_ms=clock,
                working_view_projector=projector,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "canonical pc15 hard gate"},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.NEEDS_INPUT)
            self.assertEqual(result.conclusion.unresolved_unknowns, (unknown,))
            self.assertEqual(result.tool_calls, 1)
            self.assertEqual(result.usage["toolCorrections"], 1)
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertEqual(len(adapter.requests), 3)
            self.assertEqual(adapter.requests[1].tools, ())
            self.assertEqual(adapter.requests[1].remaining_budget["toolCalls"], 0)
            self.assertEqual(adapter.requests[2].tools, ())
            correction = adapter.requests[2].messages[-1]
            self.assertEqual(correction["role"], "tool")
            error = correction["observation"]["content"]["error"]
            self.assertTrue(error["safeToCorrect"])
            self.assertFalse(error["physicalDispatch"])
            self.assertEqual(error["commitState"], "not_started")
            self.assertIn("external Tool Call budget is exhausted", error["message"])
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()


if __name__ == "__main__":
    unittest.main()

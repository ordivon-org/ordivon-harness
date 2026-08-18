from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    SQLiteHarnessAgentBridge,
)
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def contract() -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id="harness-run:p6-no-tool-conclusion-control",
        harness_implementation_id="ordivon-harness@p6-baseline",
        caller_id="caller:p6-no-tool-conclusion-control",
        caller_run_ref="trial:p6-no-tool-conclusion-control",
        objective_ref=HarnessBoundReference("objective:p6-no-tool", "objective", DIGEST_A),
        context_refs=(HarnessBoundReference("context:p6-no-tool", "context", DIGEST_B),),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=NO_TOOL_AGENT_GRANT_DIGEST,
        budget={
            "maxModelCalls": 2,
            "maxToolCalls": 0,
            "maxWallTimeMs": 10_000,
            "maxConclusionCorrections": 1,
            "maxToolCorrections": 0,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference("system:p6-no-tool", "system-manifest", DIGEST_A),
        created_at_ms=1_000,
    )


def invalid_conclusion_turn() -> AgentTurnResult:
    raw = '{"status":"candidate_completed","summary":42}'
    return AgentTurnResult(
        model_call_id="model-call:p6-invalid-conclusion",
        model_id=ScriptedTurnAdapter.model_id,
        content="candidate with malformed conclusion fields",
        tool_calls=(
            AgentToolCall(
                "control-call:p6-invalid-conclusion",
                "submit_run_conclusion",
                {"status": "candidate_completed", "summary": 42},
                argument_error="invalid_conclusion: summary must be a string",
                raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw.encode()).hexdigest(),
                raw_arguments_preview=raw,
            ),
        ),
        conclusion=None,
        usage={"inputTokens": 20, "outputTokens": 5, "totalTokens": 25},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"turn": "invalid-conclusion"}),
    )


def valid_conclusion_turn() -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:p6-valid-conclusion",
        model_id=ScriptedTurnAdapter.model_id,
        content="corrected candidate",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Corrected candidate conclusion.",
        ),
        usage={"inputTokens": 20, "outputTokens": 5, "totalTokens": 25},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"turn": "valid-conclusion"}),
    )


class P6NoToolConclusionControlTests(unittest.TestCase):
    def test_invalid_conclusion_is_harness_control_correction_not_runtime_tool(self) -> None:
        run_contract = contract()
        adapter = ScriptedTurnAdapter((invalid_conclusion_turn(), valid_conclusion_turn()))
        budget = RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=16_384,
            max_wall_time_ms=10_000,
            max_total_tokens=10_000,
            max_model_retries=0,
            max_tool_corrections=0,
            max_conclusion_corrections=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract)
            bridge = SQLiteHarnessAgentBridge(run_contract, continuity)
            result = OrdivonAgentLoop(adapter, bridge, budget=budget).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "produce a valid bounded conclusion"},),
            )

            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.tool_calls, 0)
            self.assertEqual(result.usage["toolCorrections"], 0)
            self.assertEqual(result.usage["conclusionCorrections"], 1)
            self.assertEqual(len(adapter.requests), 2)
            self.assertEqual(adapter.requests[0].tools, ())
            self.assertEqual(adapter.requests[1].tools, ())
            correction_messages = [
                message
                for message in result.messages
                if message.get("role") == "user"
                and isinstance(message.get("content"), str)
                and "conclusion" in message["content"].lower()
            ]
            self.assertTrue(correction_messages)
            store.close()

    def test_invalid_json_conclusion_control_uses_conclusion_budget(self) -> None:
        run_contract = contract()
        raw = "{not-json"
        malformed = AgentTurnResult(
            model_call_id="model-call:p6-invalid-json-conclusion",
            model_id=ScriptedTurnAdapter.model_id,
            content="malformed control json",
            tool_calls=(
                AgentToolCall(
                    "control-call:p6-invalid-json-conclusion",
                    "submit_run_conclusion",
                    {},
                    argument_error="invalid_json",
                    raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw.encode()).hexdigest(),
                    raw_arguments_preview=raw,
                ),
            ),
            conclusion=None,
            usage={"inputTokens": 20, "outputTokens": 5, "totalTokens": 25},
            finish_reason="tool_calls",
            raw_response_digest=canonical_digest({"turn": "invalid-json-conclusion"}),
        )
        adapter = ScriptedTurnAdapter((malformed, valid_conclusion_turn()))
        budget = RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=16_384,
            max_wall_time_ms=10_000,
            max_total_tokens=10_000,
            max_model_retries=0,
            max_tool_corrections=0,
            max_conclusion_corrections=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract)
            result = OrdivonAgentLoop(
                adapter,
                SQLiteHarnessAgentBridge(run_contract, continuity),
                budget=budget,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "produce a valid bounded conclusion"},),
            )
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.tool_calls, 0)
            self.assertEqual(result.usage["toolCorrections"], 0)
            self.assertEqual(result.usage["conclusionCorrections"], 1)
            store.close()

    def test_mixed_conclusion_control_and_runtime_tool_is_not_silently_dropped(self) -> None:
        run_contract = contract()
        raw_conclusion = '{"status":"candidate_completed","summary":42}'
        raw_tool = '{}'
        mixed = AgentTurnResult(
            model_call_id="model-call:p6-mixed-control-runtime",
            model_id=ScriptedTurnAdapter.model_id,
            content="mixed invalid actions",
            tool_calls=(
                AgentToolCall(
                    "control-call:p6-mixed-conclusion",
                    "submit_run_conclusion",
                    {"status": "candidate_completed", "summary": 42},
                    argument_error="invalid_conclusion: summary must be a string",
                    raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw_conclusion.encode()).hexdigest(),
                    raw_arguments_preview=raw_conclusion,
                ),
                AgentToolCall(
                    "runtime-call:p6-mixed-read",
                    "read_workspace",
                    {},
                    argument_error="unavailable_tool",
                    raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw_tool.encode()).hexdigest(),
                    raw_arguments_preview=raw_tool,
                ),
            ),
            conclusion=None,
            usage={"inputTokens": 20, "outputTokens": 5, "totalTokens": 25},
            finish_reason="tool_calls",
            raw_response_digest=canonical_digest({"turn": "mixed-control-runtime"}),
        )
        adapter = ScriptedTurnAdapter((mixed, valid_conclusion_turn()))
        budget = RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=16_384,
            max_wall_time_ms=10_000,
            max_total_tokens=10_000,
            max_model_retries=0,
            max_tool_corrections=0,
            max_conclusion_corrections=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract)
            result = OrdivonAgentLoop(
                adapter,
                SQLiteHarnessAgentBridge(run_contract, continuity),
                budget=budget,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "produce one conclusion without Runtime Tools"},),
            )
            self.assertFalse(result.candidate_completed)
            self.assertEqual(result.model_calls, 1)
            self.assertEqual(result.usage["conclusionCorrections"], 0)
            self.assertEqual(len(adapter.requests), 1)
            store.close()

    def test_unavailable_provider_tool_on_no_tool_surface_is_correction_not_runtime_history(self) -> None:
        run_contract = contract()
        raw = '{"path":"src/ordivon_harness/ordivon/loop.py"}'
        unavailable = AgentTurnResult(
            model_call_id="model-call:p6-unavailable-no-tool",
            model_id=ScriptedTurnAdapter.model_id,
            content="attempted unavailable observation",
            tool_calls=(
                AgentToolCall(
                    "provider-call:p6-unavailable-read-file",
                    "read_file",
                    {"path": "src/ordivon_harness/ordivon/loop.py"},
                    argument_error="unavailable_tool",
                    raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw.encode()).hexdigest(),
                    raw_arguments_preview=raw,
                ),
            ),
            conclusion=None,
            usage={"inputTokens": 20, "outputTokens": 5, "totalTokens": 25},
            finish_reason="tool_calls",
            raw_response_digest=canonical_digest({"turn": "unavailable-no-tool"}),
        )
        adapter = ScriptedTurnAdapter((unavailable, valid_conclusion_turn()))
        budget = RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=16_384,
            max_wall_time_ms=10_000,
            max_total_tokens=10_000,
            max_model_retries=0,
            max_tool_corrections=1,
            max_conclusion_corrections=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract)
            result = OrdivonAgentLoop(
                adapter,
                SQLiteHarnessAgentBridge(run_contract, continuity),
                budget=budget,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "inspect or conclude without Runtime Tools"},),
            )
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.tool_calls, 0)
            self.assertEqual(result.usage["toolCorrections"], 1)
            self.assertEqual(result.usage["conclusionCorrections"], 0)
            self.assertEqual(len(adapter.requests), 2)
            self.assertEqual(adapter.requests[0].tools, ())
            self.assertEqual(adapter.requests[1].tools, ())
            self.assertFalse(any(message.get("role") == "tool" for message in result.messages))
            store.close()

    def test_multiple_unavailable_provider_actions_are_one_no_tool_correction(self) -> None:
        run_contract = contract()
        raw_a = '{"capability":"read_file","path":"src/ordivon_harness/standalone.py"}'
        raw_b = '{"capability":"read_file","path":"src/ordivon_harness/ordivon/deepseek.py"}'
        unavailable = AgentTurnResult(
            model_call_id="model-call:p6-multiple-unavailable-no-tool",
            model_id=ScriptedTurnAdapter.model_id,
            content="attempted two unavailable observations",
            tool_calls=(
                AgentToolCall(
                    "provider-call:p6-unavailable-a",
                    "invoke",
                    {"capability": "read_file", "path": "src/ordivon_harness/standalone.py"},
                    argument_error="unavailable_tool",
                    raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw_a.encode()).hexdigest(),
                    raw_arguments_preview=raw_a,
                ),
                AgentToolCall(
                    "provider-call:p6-unavailable-b",
                    "invoke",
                    {"capability": "read_file", "path": "src/ordivon_harness/ordivon/deepseek.py"},
                    argument_error="unavailable_tool",
                    raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw_b.encode()).hexdigest(),
                    raw_arguments_preview=raw_b,
                ),
            ),
            conclusion=None,
            usage={"inputTokens": 30, "outputTokens": 8, "totalTokens": 38},
            finish_reason="tool_calls",
            raw_response_digest=canonical_digest({"turn": "multiple-unavailable-no-tool"}),
        )
        adapter = ScriptedTurnAdapter((unavailable, valid_conclusion_turn()))
        budget = RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=16_384,
            max_wall_time_ms=10_000,
            max_total_tokens=10_000,
            max_model_retries=0,
            max_tool_corrections=1,
            max_conclusion_corrections=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract)
            result = OrdivonAgentLoop(
                adapter,
                SQLiteHarnessAgentBridge(run_contract, continuity),
                budget=budget,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "inspect or conclude without Runtime Tools"},),
            )
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.tool_calls, 0)
            self.assertEqual(result.usage["toolCorrections"], 1)
            self.assertFalse(any(message.get("role") == "tool" for message in result.messages))
            store.close()

    def test_repeated_unavailable_provider_turns_are_bounded_by_tool_corrections(self) -> None:
        run_contract = contract()

        def unavailable_turn(model_call_id: str, tool_call_id: str) -> AgentTurnResult:
            raw = '{"path":"src/ordivon_harness/ordivon/loop.py"}'
            return AgentTurnResult(
                model_call_id=model_call_id,
                model_id=ScriptedTurnAdapter.model_id,
                content="attempted unavailable observation",
                tool_calls=(
                    AgentToolCall(
                        tool_call_id,
                        "read_file",
                        {"path": "src/ordivon_harness/ordivon/loop.py"},
                        argument_error="unavailable_tool",
                        raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw.encode()).hexdigest(),
                        raw_arguments_preview=raw,
                    ),
                ),
                conclusion=None,
                usage={"inputTokens": 20, "outputTokens": 5, "totalTokens": 25},
                finish_reason="tool_calls",
                raw_response_digest=canonical_digest({"turn": model_call_id}),
            )

        adapter = ScriptedTurnAdapter(
            (
                unavailable_turn("model-call:p6-unavailable-first", "provider-call:p6-unavailable-first"),
                unavailable_turn("model-call:p6-unavailable-second", "provider-call:p6-unavailable-second"),
            )
        )
        budget = RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=16_384,
            max_wall_time_ms=10_000,
            max_total_tokens=10_000,
            max_model_retries=0,
            max_tool_corrections=1,
            max_conclusion_corrections=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract)
            result = OrdivonAgentLoop(
                adapter,
                SQLiteHarnessAgentBridge(run_contract, continuity),
                budget=budget,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "do not use unavailable Runtime Tools"},),
            )
            self.assertEqual(result.stop_code, RunStopCode.INVALID_TOOL_CALL)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.tool_calls, 0)
            self.assertEqual(result.usage["toolCorrections"], 1)
            self.assertFalse(any(message.get("role") == "tool" for message in result.messages))
            store.close()

    def test_repeated_malformed_conclusion_is_bounded_by_conclusion_budget(self) -> None:
        run_contract = contract()
        first = invalid_conclusion_turn()
        raw = "{broken"
        second = AgentTurnResult(
            model_call_id="model-call:p6-second-malformed-conclusion",
            model_id=ScriptedTurnAdapter.model_id,
            content="still malformed",
            tool_calls=(
                AgentToolCall(
                    "control-call:p6-second-malformed-conclusion",
                    "submit_run_conclusion",
                    {},
                    argument_error="invalid_json",
                    raw_arguments_digest="sha256:" + __import__("hashlib").sha256(raw.encode()).hexdigest(),
                    raw_arguments_preview=raw,
                ),
            ),
            conclusion=None,
            usage={"inputTokens": 20, "outputTokens": 5, "totalTokens": 25},
            finish_reason="tool_calls",
            raw_response_digest=canonical_digest({"turn": "second-malformed-conclusion"}),
        )
        adapter = ScriptedTurnAdapter((first, second))
        budget = RunBudget(
            max_model_calls=2,
            max_tool_calls=0,
            max_observation_bytes=16_384,
            max_wall_time_ms=10_000,
            max_total_tokens=10_000,
            max_model_retries=0,
            max_tool_corrections=0,
            max_conclusion_corrections=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            store = SQLiteHarnessStore.initialize(root)
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract)
            result = OrdivonAgentLoop(
                adapter,
                SQLiteHarnessAgentBridge(run_contract, continuity),
                budget=budget,
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=({"role": "user", "content": "correct malformed conclusions at most once"},),
            )
            self.assertEqual(result.stop_code, RunStopCode.INVALID_MODEL_OUTPUT)
            self.assertEqual(result.model_calls, 2)
            self.assertEqual(result.tool_calls, 0)
            self.assertEqual(result.usage["conclusionCorrections"], 1)
            self.assertEqual(result.usage["toolCorrections"], 0)
            self.assertEqual(len(adapter.requests), 2)
            store.close()


if __name__ == "__main__":
    unittest.main()

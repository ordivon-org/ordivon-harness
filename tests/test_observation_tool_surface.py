from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from anc_canonical import canonical_digest

from ordivon_harness.api import (
    AgentTurnResult,
    HarnessBoundReference,
    HarnessExecutionBinding,
    HarnessPrivacyPolicy,
    HarnessRunContract,
    HarnessRuntimeReference,
)
from ordivon_harness.observation_tool_surface import (
    OBSERVATION_TOOL_SURFACE_DIGEST,
    HarnessObservationReadObject,
    HarnessObservationToolGrant,
    build_observation_tool_surface,
)
from ordivon_harness.ordivon.model import AgentRunConclusion, AgentToolCall, ScriptedTurnAdapter


def digest(label: str) -> str:
    return canonical_digest({"observation-surface": label})


def contract(suffix: str, grant: HarnessObservationToolGrant) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f"harness-run:observation-{suffix}",
        harness_implementation_id="ordivon-harness@observation-read-v1",
        caller_id="caller:observation-test",
        caller_run_ref=f"trial:observation-{suffix}",
        objective_ref=HarnessBoundReference("objective:observation", "objective", digest("objective")),
        context_refs=(HarnessBoundReference("context:observation", "context", digest("context")),),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=OBSERVATION_TOOL_SURFACE_DIGEST,
        tool_grant_digest=grant.digest,
        budget={
            "maxModelCalls": 5,
            "maxToolCalls": 3,
            "maxObservationBytes": 65536,
            "maxWallTimeMs": 10000,
            "maxTotalTokens": 10000,
            "maxModelRetries": 1,
            "maxToolCorrections": 2,
            "maxConclusionCorrections": 2,
            "maxObservationOnlyTurns": 4,
            "maxNoProgressTurns": 3,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            "manifest:observation", "system-manifest", digest("manifest")
        ),
        created_at_ms=1000,
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=True,
        ),
    )


def binding(value: HarnessRunContract) -> HarnessExecutionBinding:
    token = value.digest[7:31]
    return HarnessExecutionBinding(
        harness_run_id=value.harness_run_id,
        workspace_ref="workspace:observation-source",
        assignment_id=f"assignment:external:{token}",
        assignment_generation=1,
        assignment_digest=value.digest,
        runtime_binding_digest=digest("runtime-binding"),
        tool_catalog_digest=value.tool_catalog_digest,
        tool_grant_digest=value.tool_grant_digest,
        deadline_ms=value.deadline_ms,
        runtime_references=(
            HarnessRuntimeReference(
                namespace="ordivon.harness",
                reference_type="harness_run",
                reference_id=value.harness_run_id,
                generation="1",
                digest=value.digest,
            ),
        ),
    )


def tool_turn(call_id: str, name: str, arguments: dict) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:{call_id}",
        model_id=ScriptedTurnAdapter.model_id,
        content=name,
        tool_calls=(AgentToolCall(f"tool-call:{call_id}", name, arguments),),
        conclusion=None,
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="tool_calls",
        raw_response_digest=digest(call_id),
    )


def completed() -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:observation-done",
        model_id=ScriptedTurnAdapter.model_id,
        content="standing recovered",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Recovered standing from exact source-fenced object.",
        ),
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="stop",
        raw_response_digest=digest("done"),
    )


class FakeRuntime:
    def __init__(self, source_content: str, source_digest: str):
        self.source_content = source_content
        self.source_digest = source_digest
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "workspace.exec":
            match = {
                "type": "match",
                "data": {
                    "path": {"text": "source/standing.json"},
                    "lines": {"text": "STANDING:HISTORICAL_PRESERVED=true\n"},
                    "line_number": 1,
                    "absolute_offset": 0,
                    "submatches": [{"match": {"text": "HISTORICAL_PRESERVED"}, "start": 9, "end": 29}],
                },
            }
            return {
                "status": "succeeded",
                "jobId": "job:observation-search",
                "attemptId": "attempt:observation-search",
                "executionTerminal": True,
                "executionDisposition": "succeeded",
                "deliveryDisposition": "committed",
                "recoveryRequired": False,
                "semanticCompletionEvaluated": False,
                "exitCode": 0,
                "stdoutTail": json.dumps(match) + "\n",
                "stderrTail": "",
                "resultAvailable": True,
                "artifactsAvailable": False,
            }
        if name == "workspace.read":
            return {
                "content": self.source_content,
                "digest": self.source_digest,
                "eof": True,
                "fileByteLength": len(self.source_content.encode("utf-8")),
            }
        raise AssertionError(name)

    def find_jobs_by_client_request_id(self, client_request_id):
        return ()


class ObservationToolSurfaceTests(unittest.TestCase):
    def test_search_then_exact_digest_read_is_supported_without_mutation_surface(self):
        source = '{"standingStatements":["STANDING:HISTORICAL_PRESERVED=true","STANDING:FALSIFIED=true"]}'
        source_digest = "sha256:" + __import__("hashlib").sha256(source.encode()).hexdigest()
        grant = HarnessObservationToolGrant(
            search_paths=(".",),
            read_objects=(HarnessObservationReadObject("source/standing.json", source_digest),),
        )
        value = contract("happy", grant)
        runtime = FakeRuntime(source, source_digest)
        adapter = ScriptedTurnAdapter(
            (
                tool_turn("search", "search_workspace", {"query": "HISTORICAL_PRESERVED"}),
                tool_turn("read", "read_workspace", {"relativePath": "./source/standing.json", "mode": "FULL", "maxBytes": 4096}),
                completed(),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            run = build_observation_tool_surface(grant).create(
                Path(directory) / "state",
                value,
                lambda _contract: adapter,
                execution_binding=binding(value),
                runtime=runtime,
            )
            result = run.run(({"role": "user", "content": "recover exact standing"},))
        self.assertEqual(result.loop_result.stop_code.value, "candidate_completed")
        self.assertEqual(result.loop_result.usage["toolCalls"], 2)
        self.assertEqual([name for name, _ in runtime.calls], ["workspace.exec", "workspace.read"])
        self.assertEqual(
            {tool.name for tool in adapter.requests[0].tools},
            {"search_workspace", "read_workspace"},
        )
        self.assertNotIn("workspace.patch", grant.to_dict()["runtimeOperations"])

    def test_grant_rejects_unbound_paths_and_binds_expected_digest(self):
        read_digest = digest("exact-source")
        grant = HarnessObservationToolGrant(
            search_paths=(".", "source"),
            read_objects=(HarnessObservationReadObject("source/standing.json", read_digest),),
        )
        self.assertTrue(grant.allows_path("search_workspace", "."))
        self.assertTrue(grant.allows_path("read_workspace", "source/standing.json"))
        self.assertTrue(grant.allows_path("read_workspace", "./source/standing.json"))
        self.assertTrue(grant.allows_path("read_workspace", "source/./standing.json"))
        self.assertFalse(grant.allows_path("read_workspace", "source/other.json"))
        self.assertFalse(grant.allows_path("read_workspace", "../standing.json"))
        self.assertEqual(grant.expected_digest("read_workspace", "source/standing.json"), read_digest)
        self.assertEqual(grant.expected_digest("read_workspace", "./source/standing.json"), read_digest)
        self.assertEqual(grant.expected_digest("read_workspace", "source/./standing.json"), read_digest)
        self.assertIsNone(grant.expected_digest("search_workspace", "."))
        with self.assertRaisesRegex(ValueError, "canonical relative spelling"):
            HarnessObservationReadObject("./source/standing.json", read_digest)

    def test_source_digest_mismatch_fails_closed_before_completion_claim(self):
        source = '{"standingStatements":["STANDING:HISTORICAL_PRESERVED=true"]}'
        expected = digest("expected-source")
        observed = digest("different-source")
        grant = HarnessObservationToolGrant(
            search_paths=(".",),
            read_objects=(HarnessObservationReadObject("source/standing.json", expected),),
        )
        value = contract("mismatch", grant)
        runtime = FakeRuntime(source, observed)
        adapter = ScriptedTurnAdapter(
            (
                tool_turn("read-mismatch", "read_workspace", {"relativePath": "source/standing.json", "maxBytes": 4096}),
                AgentTurnResult(
                    model_call_id="model-call:mismatch-stop",
                    model_id=ScriptedTurnAdapter.model_id,
                    content="cannot rely on changed source",
                    tool_calls=(),
                    conclusion=AgentRunConclusion(
                        status="needs_input",
                        summary="Exact source fence changed.",
                        unresolved_unknowns=("current source object",),
                    ),
                    usage={"inputTokens": 1, "outputTokens": 1},
                    finish_reason="stop",
                    raw_response_digest=digest("mismatch-stop"),
                ),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            run = build_observation_tool_surface(grant).create(
                Path(directory) / "state",
                value,
                lambda _contract: adapter,
                execution_binding=binding(value),
                runtime=runtime,
            )
            result = run.run(({"role": "user", "content": "recover standing"},))
        self.assertTrue(result.paused)
        second_messages = adapter.requests[1].messages
        tool_messages = [message for message in second_messages if message.get("role") == "tool"]
        self.assertTrue(tool_messages)
        self.assertIn("SourceFenceMismatch", str(tool_messages[-1]))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
import json
import unittest

from anc_canonical import canonical_bytes, loads_strict

from ordivon_harness.api import (
    STRUCTURED_COMPLETION_MODE,
    decode_structured_completion_result,
    structured_completion_contract_digest,
)
from ordivon_harness.completion import structured_completion_result_schema
from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.model import AgentTurnRequest

from tests.test_p0_core_contracts import DIGEST_C, contract


class RecordingTransport:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.body: bytes | None = None

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        self.body = body
        return self.response


def provider_response(
    result: dict[str, object], *, unresolved_unknowns: list[str] | None = None
) -> bytes:
    arguments = {
        "status": "candidate_completed",
        "result": result,
        "artifact_refs": [],
        "evidence_refs": [],
        "unresolved_unknowns": (
            [] if unresolved_unknowns is None else unresolved_unknowns
        ),
    }
    return canonical_bytes(
        {
            "id": "provider-call:structured-1",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "toolcall:structured-conclusion",
                                "type": "function",
                                "function": {
                                    "name": "submit_run_conclusion",
                                    "arguments": json.dumps(arguments, separators=(",", ":")),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
    )


class StructuredCompletionTests(unittest.TestCase):
    def structured_contract(self):
        completion = {
            "mode": STRUCTURED_COMPLETION_MODE,
            "resultKind": "test-choice",
            "resultSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "choice": {"type": "string", "enum": ["observe"]},
                    "rationale": {"type": "string", "minLength": 1},
                },
                "required": ["choice", "rationale"],
            },
        }
        return replace(
            contract(),
            provider_id="provider:deepseek",
            adapter_id=DeepSeekTurnAdapter.adapter_id,
            requested_model_id="deepseek-v4-flash",
            completion_contract=completion,
        )

    def test_deepseek_binds_caller_schema_and_returns_canonical_structured_result(self) -> None:
        run_contract = self.structured_contract()
        expected = {"choice": "observe", "rationale": "inspect first"}
        transport = RecordingTransport(provider_response(expected))
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=transport,
            completion_contract=run_contract.completion_contract,
        )
        request = AgentTurnRequest(
            harness_run_id=run_contract.harness_run_id,
            turn_id="turn:structured-1",
            sequence=1,
            assignment_id="assignment:external:structured-1",
            context_digest=run_contract.context_refs[0].digest,
            tool_catalog_digest=DIGEST_C,
            messages=({"role": "user", "content": "choose"},),
            tools=(),
            remaining_budget={"modelCalls": 1, "toolCalls": 0, "totalTokens": 4096},
        )

        result = adapter.invoke(request)
        self.assertIsNotNone(result.conclusion)
        assert result.conclusion is not None
        self.assertEqual(decode_structured_completion_result(run_contract, result.conclusion), expected)
        self.assertEqual(
            adapter.structured_completion_contract_digest,
            structured_completion_contract_digest(run_contract.completion_contract),
        )
        assert transport.body is not None
        body = loads_strict(transport.body)
        assert isinstance(body, dict)
        tools = body["tools"]
        assert isinstance(tools, list)
        conclusion_tool = tools[-1]
        assert isinstance(conclusion_tool, dict)
        function = conclusion_tool["function"]
        assert isinstance(function, dict)
        parameters = function["parameters"]
        assert isinstance(parameters, dict)
        properties = parameters["properties"]
        assert isinstance(properties, dict)
        self.assertIn("result", properties)
        self.assertNotIn("summary", properties)
        self.assertEqual(properties["result"], run_contract.to_dict()["completionContract"]["resultSchema"])


    def test_structured_schema_rejects_non_string_object_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "completion schema object keys must be strings"):
            structured_completion_result_schema(
                {
                    "mode": STRUCTURED_COMPLETION_MODE,
                    "resultSchema": {1: {"type": "string"}},  # type: ignore[dict-item]
                }
            )

    def test_candidate_completed_may_retain_honest_unresolved_unknowns(self) -> None:
        run_contract = self.structured_contract()
        expected = {"choice": "observe", "rationale": "inspect first"}
        unknowns = ["Current workspace content remains unknown until the next Run observes it."]
        transport = RecordingTransport(
            provider_response(expected, unresolved_unknowns=unknowns)
        )
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=512),
            transport=transport,
            completion_contract=run_contract.completion_contract,
        )
        request = AgentTurnRequest(
            harness_run_id=run_contract.harness_run_id,
            turn_id="turn:structured-unknowns",
            sequence=1,
            assignment_id="assignment:external:structured-unknowns",
            context_digest=run_contract.context_refs[0].digest,
            tool_catalog_digest=DIGEST_C,
            messages=({"role": "user", "content": "choose a plan"},),
            tools=(),
            remaining_budget={"modelCalls": 1, "toolCalls": 0, "totalTokens": 4096},
        )
        result = adapter.invoke(request)
        self.assertIsNotNone(result.conclusion)
        assert result.conclusion is not None
        self.assertEqual(result.conclusion.status, "candidate_completed")
        self.assertEqual(result.conclusion.unresolved_unknowns, tuple(unknowns))
        self.assertEqual(
            decode_structured_completion_result(run_contract, result.conclusion),
            expected,
        )

    def test_plain_completion_keeps_summary_contract_and_caller_neutral_description(self) -> None:
        response = canonical_bytes(
            {
                "id": "provider-call:plain-1",
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "toolcall:plain",
                                    "type": "function",
                                    "function": {
                                        "name": "submit_run_conclusion",
                                        "arguments": json.dumps(
                                            {
                                                "status": "candidate_completed",
                                                "summary": "done",
                                                "artifact_refs": [],
                                                "evidence_refs": [],
                                                "unresolved_unknowns": [],
                                            },
                                            separators=(",", ":"),
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"total_tokens": 4},
            }
        )
        transport = RecordingTransport(response)
        adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="k" * 40, max_output_tokens=128),
            transport=transport,
        )
        request = AgentTurnRequest(
            harness_run_id="harness-run:plain",
            turn_id="turn:plain",
            sequence=1,
            assignment_id="assignment:external:plain",
            context_digest="sha256:" + "a" * 64,
            tool_catalog_digest="sha256:" + "b" * 64,
            messages=({"role": "user", "content": "finish"},),
            tools=(),
            remaining_budget={"modelCalls": 1},
        )
        result = adapter.invoke(request)
        assert result.conclusion is not None
        self.assertEqual(result.conclusion.summary, "done")
        assert transport.body is not None
        body = loads_strict(transport.body)
        assert isinstance(body, dict)
        tools = body["tools"]
        assert isinstance(tools, list)
        function = tools[-1]["function"]
        assert isinstance(function, dict)
        self.assertIn("caller or domain verification", function["description"] )
        properties = function["parameters"]["properties"]
        self.assertIn("summary", properties)
        self.assertNotIn("result", properties)


if __name__ == "__main__":
    unittest.main()

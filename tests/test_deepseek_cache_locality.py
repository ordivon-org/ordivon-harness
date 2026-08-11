from __future__ import annotations

import json
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from ordivon_harness.ordivon.model import (
    AgentCallerIngressRef,
    AgentTurnCapabilities,
    AgentTurnRequest,
)


class DeepSeekCacheLocalityTests(unittest.TestCase):
    def adapter(self) -> DeepSeekTurnAdapter:
        return DeepSeekTurnAdapter(
            DeepSeekSettings(api_key="cache-locality-test-secret", max_output_tokens=512)
        )

    def request(
        self,
        *,
        turn: int,
        model_calls: int,
        caller_message_index: int,
        request_message_index: int,
    ) -> AgentTurnRequest:
        messages = (
            {"role": "user", "content": "stable caller message zero"},
            {"role": "assistant", "content": "stable retained conclusion" , "conclusion": {"status": "candidate_completed", "summary": "stable", "artifactRefs": [], "evidenceRefs": [], "unresolvedUnknowns": []}},
            {"role": "user", "content": "stable caller message two"},
        )
        return AgentTurnRequest(
            harness_run_id="harness-run:cache-locality",
            turn_id=f"turn:cache-locality:{turn}",
            sequence=turn,
            assignment_id="assignment:cache-locality",
            context_digest=canonical_digest({"cache": "context"}),
            tool_catalog_digest=canonical_digest({"cache": "tools"}),
            messages=messages,
            tools=(),
            remaining_budget={
                "modelCalls": model_calls,
                "toolCalls": 0,
                "totalTokens": model_calls * 1000,
            },
            capabilities=AgentTurnCapabilities(caller_ingress_promotion=True),
            caller_ingress_refs=(
                AgentCallerIngressRef(
                    caller_message_index=caller_message_index,
                    request_message_index=request_message_index,
                ),
            ),
        )

    def body(self, request: AgentTurnRequest) -> dict[str, object]:
        _allowed, _url, _headers, body = self.adapter()._prepare_request(request)
        return json.loads(body)

    def promotion_tool(self, body: dict[str, object]) -> dict[str, object]:
        tools = body["tools"]
        self.assertIsInstance(tools, list)
        return next(
            item
            for item in tools
            if item["function"]["name"] == "promote_caller_ingress"
        )

    def test_dynamic_turn_control_is_trailing_named_harness_user(self) -> None:
        body = self.body(
            self.request(
                turn=1,
                model_calls=8,
                caller_message_index=0,
                request_message_index=0,
            )
        )
        messages = body["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertNotIn('"remainingBudget"', messages[0]["content"])
        self.assertIn("ordivon_harness_turn_control", messages[0]["content"])
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["name"], "ordivon_harness_turn_control")
        self.assertIn('"remainingBudget"', messages[-1]["content"])
        self.assertIn('"providerMessageIndex":1', messages[-1]["content"])

    def test_stable_system_and_history_prefix_survives_dynamic_control_change(self) -> None:
        first = self.body(
            self.request(
                turn=1,
                model_calls=8,
                caller_message_index=0,
                request_message_index=0,
            )
        )
        second = self.body(
            self.request(
                turn=2,
                model_calls=7,
                caller_message_index=2,
                request_message_index=2,
            )
        )
        self.assertEqual(first["messages"][:-1], second["messages"][:-1])
        self.assertNotEqual(first["messages"][-1], second["messages"][-1])
        self.assertIn('"modelCalls":8', first["messages"][-1]["content"])
        self.assertIn('"modelCalls":7', second["messages"][-1]["content"])
        self.assertIn('"providerMessageIndex":1', first["messages"][-1]["content"])
        self.assertIn('"providerMessageIndex":3', second["messages"][-1]["content"])

    def test_caller_promotion_provider_schema_is_static_across_exact_ref_changes(self) -> None:
        first = self.body(
            self.request(
                turn=1,
                model_calls=8,
                caller_message_index=0,
                request_message_index=0,
            )
        )
        second = self.body(
            self.request(
                turn=2,
                model_calls=7,
                caller_message_index=2,
                request_message_index=2,
            )
        )
        first_tool = self.promotion_tool(first)
        second_tool = self.promotion_tool(second)
        self.assertEqual(first_tool, second_tool)
        items = first_tool["function"]["parameters"]["properties"][
            "caller_message_indexes"
        ]["items"]
        self.assertEqual(items, {"type": "integer", "minimum": 0})
        self.assertNotIn("enum", items)


if __name__ == "__main__":
    unittest.main()

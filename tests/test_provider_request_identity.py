from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest

from anc_canonical import JsonValue, canonical_bytes, canonical_digest, loads_strict
from ordivon_host import HostStorage
from test_ordivon_harness_oh5 import (
    TASK_ID,
    _RecoveryRuntime,
    _create_task,
)
from test_runner_r0_r1 import _plan, _turn

from ordivon_harness import (
    HarnessHost,
    HarnessProviderCallRequestMismatch,
    HarnessRunner,
)
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentTurnRequest,
    DeepSeekSettings,
    DeepSeekTurnAdapter,
    HostHarnessRunStore,
    OrdivonAgentLoop,
    RunBudget,
    RuntimeToolBridge,
    static_provider_request_digest,
)


def _request(*, wall_time_ms: int = 30_000) -> AgentTurnRequest:
    return AgentTurnRequest(
        harness_run_id="harness-run:provider-request-identity",
        turn_id="turn:provider-request-identity:1",
        sequence=1,
        assignment_id="assignment:provider-request-identity",
        context_digest=canonical_digest({"context": "provider-request-identity"}),
        tool_catalog_digest=canonical_digest(
            {"toolCatalog": "provider-request-identity"}
        ),
        messages=(
            {
                "role": "user",
                "content": "Return a conclusion for the request identity fixture.",
            },
        ),
        tools=(),
        remaining_budget={
            "modelCalls": 4,
            "toolCalls": 4,
            "observationBytes": 65_536,
            "wallTimeMs": wall_time_ms,
        },
    )


def _conclusion_response() -> dict[str, JsonValue]:
    arguments = {
        "status": "candidate_completed",
        "summary": "The Provider request identity fixture completed.",
        "artifact_refs": [],
        "evidence_refs": [],
        "unresolved_unknowns": [],
    }
    return {
        "id": "chatcmpl-provider-request-identity",
        "created": 1,
        "model": "deepseek-v4-flash",
        "system_fingerprint": "fp-provider-request-identity",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-provider-request-identity",
                            "type": "function",
                            "function": {
                                "name": "submit_run_conclusion",
                                "arguments": canonical_bytes(arguments).decode("utf-8"),
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 40,
            "completion_tokens": 12,
            "total_tokens": 52,
        },
    }


class _CapturingTransport:
    def __init__(self, *, fail_if_called: bool = False) -> None:
        self.fail_if_called = fail_if_called
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeoutSeconds": timeout_seconds,
                "maxResponseBytes": max_response_bytes,
            }
        )
        if self.fail_if_called:
            raise AssertionError(
                "a mismatched Provider configuration reached the transport"
            )
        return canonical_bytes(_conclusion_response())


class _MutableClock:
    def __init__(self, value: int = 100_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class _CrashAfterProviderResult(RuntimeToolBridge):
    def complete_provider_call(self, request, result) -> None:
        super().complete_provider_call(request, result)
        raise RuntimeError("injected crash after durable Provider result")


class _DeepSeekPauseAdapter:
    adapter_id = DeepSeekTurnAdapter.adapter_id
    model_id = "deepseek-v4-flash"
    provider_request_digest = static_provider_request_digest

    def invoke(self, request):
        del request
        return replace(_needs_input(), model_id=self.model_id)


def _needs_input():
    return _turn(
        "provider-request-identity-needs-input",
        conclusion=AgentRunConclusion(
            status="needs_input",
            summary="Pause before testing Provider request identity.",
        ),
    )


class ProviderRequestIdentityTests(unittest.TestCase):
    def test_digest_changes_with_provider_enforced_completion_limit(self) -> None:
        request = _request()
        smaller_transport = _CapturingTransport()
        larger_transport = _CapturingTransport()
        smaller = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-" + "a" * 40,
                credential_scope_id="credential-scope:deepseek:test",
                max_output_tokens=64,
            ),
            transport=smaller_transport,
        )
        larger = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-" + "a" * 40,
                credential_scope_id="credential-scope:deepseek:test",
                max_output_tokens=128,
            ),
            transport=larger_transport,
        )

        self.assertNotEqual(
            smaller.provider_request_digest(request),
            larger.provider_request_digest(request),
        )
        smaller.invoke(request)
        larger.invoke(request)
        smaller_body = loads_strict(smaller_transport.calls[0]["body"])
        larger_body = loads_strict(larger_transport.calls[0]["body"])
        self.assertEqual(smaller_body["max_tokens"], 64)
        self.assertEqual(larger_body["max_tokens"], 128)

    def test_digest_matches_outbound_semantics_not_budget_or_secrets(self) -> None:
        first_transport = _CapturingTransport()
        second_transport = _CapturingTransport()
        first = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-" + "a" * 40,
                credential_scope_id="credential-scope:deepseek:test",
                timeout_seconds=2,
                max_response_bytes=4_096,
                max_output_tokens=64,
            ),
            transport=first_transport,
        )
        second = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-" + "b" * 40,
                credential_scope_id="credential-scope:deepseek:test",
                timeout_seconds=7,
                max_response_bytes=8_192,
                max_output_tokens=64,
            ),
            transport=second_transport,
        )
        different_scope = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-" + "b" * 40,
                credential_scope_id="credential-scope:deepseek:other",
                timeout_seconds=7,
                max_response_bytes=8_192,
                max_output_tokens=64,
            )
        )
        default_scope_first = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-" + "a" * 40,
                max_output_tokens=64,
            )
        )
        default_scope_second = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-" + "b" * 40,
                max_output_tokens=64,
            )
        )
        request = _request(wall_time_ms=30_000)
        later_request = replace(
            request,
            remaining_budget={
                **request.remaining_budget,
                "wallTimeMs": 5_000,
            },
        )

        first_digest = first.provider_request_digest(request)
        self.assertEqual(first_digest, first.provider_request_digest(later_request))
        self.assertEqual(first_digest, second.provider_request_digest(request))
        self.assertNotEqual(
            first_digest,
            different_scope.provider_request_digest(request),
        )
        self.assertEqual(
            default_scope_first.settings.credential_scope_id,
            default_scope_second.settings.credential_scope_id,
        )
        self.assertTrue(default_scope_first.settings.credential_scope_id)
        self.assertEqual(
            default_scope_first.provider_request_digest(request),
            default_scope_second.provider_request_digest(request),
        )

        first.invoke(request)
        second.invoke(request)
        first_call = first_transport.calls[0]
        second_call = second_transport.calls[0]
        self.assertEqual(first_call["url"], second_call["url"])
        self.assertEqual(first_call["body"], second_call["body"])
        self.assertEqual(
            loads_strict(first_call["body"]),
            loads_strict(second_call["body"]),
        )
        first_headers = first_call["headers"]
        second_headers = second_call["headers"]
        self.assertIsInstance(first_headers, dict)
        self.assertIsInstance(second_headers, dict)
        self.assertEqual(
            first_headers["Content-Type"],
            second_headers["Content-Type"],
        )
        self.assertNotEqual(
            first_headers["Authorization"],
            second_headers["Authorization"],
        )

    def test_completed_result_is_not_replayed_across_provider_configurations(
        self,
    ) -> None:
        additional = (
            {
                "role": "user",
                "content": "Resume with an exact Provider request identity.",
            },
        )
        first_transport = _CapturingTransport()
        first_adapter = DeepSeekTurnAdapter(
            DeepSeekSettings(
                api_key="sk-" + "a" * 40,
                credential_scope_id="credential-scope:deepseek:test",
                max_output_tokens=64,
            ),
            transport=first_transport,
        )

        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                clock = _MutableClock()
                _create_task(storage, clock)
                paused = HarnessRunner(
                    HarnessHost(storage, clock_ms=clock),
                    runtime=_RecoveryRuntime(),
                    adapter=_DeepSeekPauseAdapter(),
                ).run(_plan())
                self.assertTrue(paused.paused)

                host = HarnessHost(storage, clock_ms=clock)
                committed = host.load_current_assignment(TASK_ID)
                run_store = HostHarnessRunStore(host, committed)
                retained = run_store.load_current_snapshot()
                bridge = _CrashAfterProviderResult(
                    committed,
                    harness_run_id=run_store.harness_run_id,
                    runtime=_RecoveryRuntime(),
                    run_store=run_store,
                    provider_source=run_store.snapshot_provider_source(retained),
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected crash after durable Provider result",
                ):
                    OrdivonAgentLoop(
                        first_adapter,
                        bridge,
                        budget=RunBudget(4, 4, 262_144, 120_000),
                        clock_ms=clock,
                    ).resume(
                        retained=retained,
                        assignment_id=committed.assignment.assignment_id,
                        context_digest=committed.assignment.context_object_digest,
                        additional_messages=additional,
                    )
                self.assertEqual(len(first_transport.calls), 1)

            second_transport = _CapturingTransport(fail_if_called=True)
            second_adapter = DeepSeekTurnAdapter(
                DeepSeekSettings(
                    api_key="sk-" + "b" * 40,
                    credential_scope_id="credential-scope:deepseek:test",
                    max_output_tokens=128,
                ),
                transport=second_transport,
            )
            with HostStorage(directory) as storage:
                runner = HarnessRunner(
                    HarnessHost(storage, clock_ms=_MutableClock()),
                    runtime=_RecoveryRuntime(),
                    adapter=second_adapter,
                )
                with self.assertRaises(HarnessProviderCallRequestMismatch):
                    runner.resume(
                        TASK_ID,
                        additional_messages=additional,
                    )
                self.assertEqual(second_transport.calls, [])


if __name__ == "__main__":
    unittest.main()

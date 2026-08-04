#!/usr/bin/env python3
"""Run a network-free, deterministic Ordivon Agent loop demonstration."""

from __future__ import annotations

import json

from anc_canonical import canonical_digest
from ordivon_harness.ordivon import (
    AgentRunConclusion,
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnResult,
    OrdivonAgentLoop,
    RunBudget,
    ScriptedTurnAdapter,
    ToolObservation,
)


class Clock:
    def __init__(self) -> None:
        self.value = 1_000

    def __call__(self) -> int:
        self.value += 1
        return self.value


class ReadOnlyBridge:
    catalog_digest = canonical_digest({"demoCatalog": 1})

    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        return (
            AgentToolDefinition(
                "read_demo",
                "Read one deterministic demonstration value.",
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            ),
        )

    def execute(self, call: AgentToolCall, *, step_id: str) -> ToolObservation:
        if call.name != "read_demo" or call.arguments != {"key": "alpha"}:
            raise ValueError("demo received an unexpected Tool request")
        return ToolObservation(
            call.tool_call_id,
            call.name,
            "observed",
            {
                "stepId": step_id,
                "value": "alpha",
                "digest": canonical_digest("alpha"),
            },
        )


def result(
    suffix: str,
    *,
    calls: tuple[AgentToolCall, ...] = (),
    conclusion: AgentRunConclusion | None = None,
) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:demo:{suffix}",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=calls,
        conclusion=conclusion,
        usage={"inputTokens": 10, "outputTokens": 5},
        finish_reason="tool_calls" if calls else "stop",
        raw_response_digest=canonical_digest({"demoResponse": suffix}),
    )


def main() -> None:
    adapter = ScriptedTurnAdapter(
        (
            result(
                "read",
                calls=(
                    AgentToolCall(
                        "tool-call:demo:read",
                        "read_demo",
                        {"key": "alpha"},
                    ),
                ),
            ),
            result(
                "complete",
                conclusion=AgentRunConclusion(
                    "candidate_completed",
                    "The deterministic value was observed.",
                ),
            ),
        )
    )
    run = OrdivonAgentLoop(
        adapter,
        ReadOnlyBridge(),
        budget=RunBudget(4, 4, 65_536, 10_000),
        clock_ms=Clock(),
    ).run(
        harness_run_id="harness-run:deterministic-demo",
        assignment_id="assignment:deterministic-demo",
        context_digest=canonical_digest({"demoContext": 1}),
        initial_messages=(
            {"role": "user", "content": "Read the deterministic alpha value."},
        ),
    )
    if not run.candidate_completed or len(run.observations) != 1:
        raise AssertionError("deterministic Agent loop did not complete as expected")
    print(
        json.dumps(
            {
                "kind": "ordivon.harness-deterministic-demo",
                "status": "passed",
                "stopCode": run.stop_code.value,
                "modelCalls": run.model_calls,
                "toolCalls": run.tool_calls,
                "observationBytes": run.observation_bytes,
                "traceDigest": run.trace.digest,
                "conclusion": run.conclusion.to_dict() if run.conclusion else None,
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Prove the installed Harness Core completes and reopens without Host."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile

from anc_canonical import canonical_digest

from ordivon_harness.core import (
    AgentRunConclusion,
    AgentTurnResult,
    HarnessBoundReference,
    HarnessRunContract,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    RunBudget,
    SQLiteHarnessAgentBridge,
    SQLiteHarnessRunContinuityStore,
    SQLiteHarnessStore,
    ScriptedTurnAdapter,
    StandaloneHarnessRunner,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class FixedClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def main() -> int:
    if importlib.util.find_spec("ordivon_host") is not None:
        raise RuntimeError("Host-free Core check unexpectedly found ordivon-host")
    contract = HarnessRunContract(
        harness_run_id="harness-run:core-without-host",
        harness_implementation_id="ordivon-harness@core-smoke",
        caller_id="caller:core-without-host",
        caller_run_ref="core-smoke:1",
        objective_ref=HarnessBoundReference("objective:core-smoke", "objective", DIGEST_A),
        context_refs=(HarnessBoundReference("context:core-smoke", "context", DIGEST_B),),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=NO_TOOL_AGENT_SURFACE_DIGEST,
        tool_grant_digest=canonical_digest(
            {"schemaVersion": 1, "kind": "ordivon.no-tool-grant", "tools": []}
        ),
        budget={
            "maxModelCalls": 1,
            "maxToolCalls": 1,
            "maxWallTimeMs": 10_000,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            "system-manifest:core-smoke", "system-manifest", DIGEST_A
        ),
        created_at_ms=1_000,
    )
    result = AgentTurnResult(
        model_call_id="model-call:core-without-host",
        model_id=ScriptedTurnAdapter.model_id,
        content="completed",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Host-free Core completed and persisted its Run.",
        ),
        usage={"inputTokens": 5, "outputTokens": 3},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"core": "without-host"}),
    )
    budget = RunBudget(
        max_model_calls=1,
        max_tool_calls=1,
        max_observation_bytes=16_384,
        max_wall_time_ms=10_000,
        max_total_tokens=1_000,
        max_model_retries=0,
    )
    clock = FixedClock()
    with tempfile.TemporaryDirectory(prefix="ordivon-harness-core-") as directory:
        root = Path(directory) / "state"
        with SQLiteHarnessStore.initialize(root) as store:
            store.create_run(contract)
            continuity = SQLiteHarnessRunContinuityStore(store, contract, clock_ms=clock)
            adapter = ScriptedTurnAdapter((result,))
            bridge = SQLiteHarnessAgentBridge(contract, continuity)
            execution = StandaloneHarnessRunner(
                contract,
                continuity,
                adapter,
                bridge,
                budget=budget,
                clock_ms=clock,
                monotonic_ms=clock,
            ).run(({"role": "user", "content": "complete"},))
            if execution.terminal_result is None:
                raise RuntimeError("Host-free Core did not produce terminal evidence")
            receipt_digest = execution.terminal_result.receipt.digest
        with SQLiteHarnessStore(root) as reopened_store:
            reopened = SQLiteHarnessRunContinuityStore.open(
                reopened_store,
                contract.harness_run_id,
                clock_ms=clock,
            )
            inspected = StandaloneHarnessRunner(
                contract,
                reopened,
                ScriptedTurnAdapter((result,)),
                SQLiteHarnessAgentBridge(contract, reopened),
                budget=budget,
                clock_ms=clock,
                monotonic_ms=clock,
            ).inspect_terminal()
            if inspected.receipt.digest != receipt_digest:
                raise RuntimeError("Host-free Core restart inspection differs")
            if not reopened_store.doctor(full=True)["healthy"]:
                raise RuntimeError("Host-free Core Store Doctor failed")
    print("harness core without host: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

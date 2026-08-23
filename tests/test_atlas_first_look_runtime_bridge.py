from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from anc_canonical import JsonValue, canonical_digest

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.execution_binding import HarnessExecutionBinding, HarnessRuntimeReference
from ordivon_harness.ordivon.atlas_first_look_runtime_bridge import (
    ATLAS_FIRST_LOOK_TOOL_SURFACE_DIGEST,
    AtlasFirstLookRuntimeGrant,
    SQLiteHarnessAtlasFirstLookRuntimeBridge,
)
from ordivon_harness.ordivon.loop import OrdivonAgentLoop, RunBudget, RunStopCode
from ordivon_harness.ordivon.model import (
    AgentRunConclusion,
    AgentToolCall,
    AgentTurnResult,
    ScriptedTurnAdapter,
)
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.runtime_port import HarnessRuntimeClientError
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
ATLAS_REVISION = "a0df2648fd3d0ccba4898b3e642275613d4fda9f"
ATLAS_SOURCE_STATE_DIGEST = "sha256:" + "d" * 64
ATLAS_WORKSPACE = "atlas-runtime-source-fixture"


class FixedClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class AtlasFakeRuntime:
    def __init__(self, mode: str = "direct") -> None:
        self.mode = mode
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []
        self.workspace_exec_count = 0
        self.client_request_id: str | None = None
        self.job_id = "job:atlas-first-look-fixture"

    def atlas_result(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 0,
            "kind": "ordivon.atlas-prior-result-first-look-experimental",
            "truthRole": "non-authoritative-prior-result-candidate-projection",
            "query": "result consumer benefit graph",
            "queryTerms": ["benefit", "consumer", "graph", "result"],
            "candidateCount": 1,
            "candidates": [
                {
                    "sourceClass": "curated-synthesis",
                    "truthRole": "non-authoritative-cross-owner-synthesis",
                    "path": "synthesis/result-value/README.md",
                    "locator": "$file",
                    "score": 12,
                    "matchedTerms": ["result", "consumer"],
                    "excerpt": "Result -> consumer -> realized benefit was already studied.",
                }
            ],
            "projectionHealth": {
                "available": False,
                "currentness": "UNKNOWN_NO_GENERATED_PROJECTION_HEALTH",
                "counts": {},
            },
            "claims": {
                "semanticEquivalenceInferred": False,
                "noveltyStanding": "UNKNOWN_CALLER_MUST_ADJUDICATE",
                "researchAdmissionGranted": False,
                "ownerTruthMinted": False,
            },
        }

    def terminal(self) -> dict[str, JsonValue]:
        assert self.client_request_id is not None
        return {
            "schemaVersion": 1,
            "jobId": self.job_id,
            "clientRequestId": self.client_request_id,
            "status": "succeeded",
            "executionTerminal": True,
            "executionDisposition": "succeeded",
            "deliveryDisposition": "committed",
            "recoveryRequired": False,
            "semanticCompletionEvaluated": False,
            "resultAvailable": True,
            "artifacts": [],
            "stdoutTail": json.dumps(self.atlas_result(), ensure_ascii=False),
            "stderrTail": "",
        }

    def call_tool(self, name: str, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
        self.calls.append((name, arguments))
        if name == "workspace.exec":
            self.workspace_exec_count += 1
            request_id = arguments.get("clientRequestId")
            assert isinstance(request_id, str)
            self.client_request_id = request_id
            if self.mode == "loss":
                raise HarnessRuntimeClientError("injected Atlas Runtime response loss")
            return self.terminal()
        if name == "task.list":
            return {
                "schemaVersion": 1,
                "jobs": [
                    {
                        "jobId": self.job_id,
                        "clientRequestId": arguments.get("clientRequestId"),
                        "status": "succeeded",
                    }
                ],
                "nextCursor": None,
            }
        if name == "task.observe":
            return self.terminal()
        raise AssertionError(f"unexpected Runtime Tool: {name}")


def grant() -> AtlasFirstLookRuntimeGrant:
    return AtlasFirstLookRuntimeGrant(
        ATLAS_WORKSPACE,
        ATLAS_REVISION,
        ATLAS_SOURCE_STATE_DIGEST,
    )


def contract(suffix: str) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f"harness-run:atlas-first-look-{suffix}",
        harness_implementation_id="ordivon-harness@0.7.0-dev",
        caller_id="caller:atlas-first-look-test",
        caller_run_ref=f"trial:atlas-first-look-{suffix}",
        objective_ref=HarnessBoundReference(
            f"objective:atlas-first-look-{suffix}", "objective", DIGEST_A
        ),
        context_refs=(HarnessBoundReference(f"context:atlas-first-look-{suffix}", "context", DIGEST_B),),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=ATLAS_FIRST_LOOK_TOOL_SURFACE_DIGEST,
        tool_grant_digest=grant().digest,
        budget={"maxModelCalls": 3, "maxToolCalls": 2, "maxWallTimeMs": 10_000},
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            f"system-manifest:atlas-first-look-{suffix}", "system-manifest", DIGEST_C
        ),
        created_at_ms=1_000,
    )


def execution_binding(run_contract: HarnessRunContract, continuity: SQLiteHarnessRunContinuityStore) -> HarnessExecutionBinding:
    binding = continuity.binding
    references = (
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="harness_run",
            reference_id=run_contract.harness_run_id,
            generation=str(binding.assignment_generation),
            digest=binding.digest,
        ),
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="run_contract",
            reference_id=f"harness-run-contract:{run_contract.digest[7:31]}",
            generation="1",
            digest=run_contract.digest,
        ),
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="tool_grant",
            reference_id=f"tool-grant:{run_contract.tool_grant_digest[7:31]}",
            generation="1",
            digest=run_contract.tool_grant_digest,
        ),
    )
    return HarnessExecutionBinding(
        harness_run_id=run_contract.harness_run_id,
        workspace_ref=ATLAS_WORKSPACE,
        assignment_id=binding.assignment_id,
        assignment_generation=binding.assignment_generation,
        assignment_digest=binding.assignment_digest,
        runtime_binding_digest=canonical_digest(
            {
                "harnessRunId": run_contract.harness_run_id,
                "workspaceRef": ATLAS_WORKSPACE,
                "sourceRevisionExpected": ATLAS_REVISION,
            }
        ),
        tool_catalog_digest=run_contract.tool_catalog_digest,
        tool_grant_digest=run_contract.tool_grant_digest,
        deadline_ms=run_contract.deadline_ms,
        runtime_references=references,
    )


def budget() -> RunBudget:
    return RunBudget(
        max_model_calls=3,
        max_tool_calls=2,
        max_observation_bytes=32_768,
        max_wall_time_ms=10_000,
        max_total_tokens=10_000,
        max_model_retries=1,
    )


def first_turn(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:atlas-first-look-{suffix}-1",
        model_id=ScriptedTurnAdapter.model_id,
        content=None,
        tool_calls=(
            AgentToolCall(
                tool_call_id=f"tool-call:atlas-first-look-{suffix}-1",
                name="atlas_first_look",
                arguments={"query": "result consumer benefit graph", "limit": 6},
            ),
        ),
        conclusion=None,
        usage={"inputTokens": 20, "outputTokens": 10},
        finish_reason="tool_calls",
        raw_response_digest=canonical_digest({"turn": suffix, "phase": 1}),
    )


def completed_turn(suffix: str) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:atlas-first-look-{suffix}-2",
        model_id=ScriptedTurnAdapter.model_id,
        content="",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary=(
                "Prior-result candidates exist; semantic equivalence remains UNKNOWN "
                "and must be adjudicated before opening a new research branch."
            ),
            unresolved_unknowns=("semantic equivalence",),
        ),
        usage={"inputTokens": 30, "outputTokens": 20},
        finish_reason="stop",
        raw_response_digest=canonical_digest({"turn": suffix, "phase": 2}),
    )


class AtlasFirstLookRuntimeBridgeTests(unittest.TestCase):
    def initialize(self, directory: str, suffix: str, runtime: AtlasFakeRuntime):
        run_contract = contract(suffix)
        store = SQLiteHarnessStore.initialize(Path(directory) / "state")
        store.create_run(run_contract)
        continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=FixedClock())
        bridge = SQLiteHarnessAtlasFirstLookRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
            grant(),
        )
        return store, run_contract, continuity, bridge

    @staticmethod
    def bind_direct_state(bridge: SQLiteHarnessAtlasFirstLookRuntimeBridge) -> None:
        bridge.bind_run_state(
            messages=({"role": "user", "content": "check prior results"},),
            observations=(),
            remaining_budget={
                "modelCalls": 3,
                "modelRetries": 1,
                "toolCalls": 2,
                "wallTimeMs": 10_000,
                "observationOnlyTurns": 3,
                "noProgressTurns": 3,
            },
            requested_model_id=ScriptedTurnAdapter.model_id,
            effective_model_id=None,
            active_elapsed_ms=0,
        )

    def test_lowering_is_owner_scoped_and_source_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AtlasFakeRuntime()
            store, _, continuity, bridge = self.initialize(directory, "lower", runtime)
            self.bind_direct_state(bridge)
            observation = bridge.execute(first_turn("lower").tool_calls[0], step_id="step:1")
            self.assertEqual(observation.status, "observed")
            self.assertEqual(runtime.workspace_exec_count, 1)
            request = next(args for name, args in runtime.calls if name == "workspace.exec")
            execution = request["execution"]
            self.assertEqual(execution["workspaceId"], ATLAS_WORKSPACE)
            self.assertEqual(execution["executable"], "/usr/bin/python3")
            self.assertEqual(execution["env"], {"PYTHONPATH": "src"})
            self.assertEqual(
                execution["args"],
                ["-m", "ordivon_atlas.cli", "first-look", "result consumer benefit graph", "--limit", "6"],
            )
            self.assertFalse(
                observation.structured_content["atlasResult"]["claims"]["semanticEquivalenceInferred"]
            )
            self.assertTrue(
                observation.structured_content["epistemicGuard"][
                    "absenceDoesNotEstablishSemanticNonEquivalence"
                ]
            )
            self.assertFalse(
                observation.structured_content["epistemicGuard"]["candidateSetExhaustive"]
            )
            self.assertEqual(
                observation.structured_content["sourceFence"]["sourceRevisionExpected"],
                ATLAS_REVISION,
            )
            self.assertIsNotNone(continuity.load_current_tool_step().receipt)
            store.close()

    def test_response_loss_reconciles_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AtlasFakeRuntime("loss")
            store, run_contract, continuity, bridge = self.initialize(directory, "loss", runtime)
            result = OrdivonAgentLoop(
                ScriptedTurnAdapter((first_turn("loss"), completed_turn("loss"))),
                bridge,
                budget=budget(),
                clock_ms=FixedClock(),
                monotonic_ms=FixedClock(),
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {"role": "user", "content": "Check whether result consumer benefit graph was already researched."},
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(runtime.workspace_exec_count, 1)
            names = [name for name, _ in runtime.calls]
            self.assertEqual(names.count("workspace.exec"), 1)
            self.assertIn("task.list", names)
            self.assertIn("task.observe", names)
            self.assertTrue(continuity.load_current_tool_step().receipt.reconciled)
            store.close()

    def test_observation_only_semantics_closes_external_tool_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AtlasFakeRuntime()
            store, run_contract, continuity, bridge = self.initialize(
                directory, "observation-gate", runtime
            )
            adapter = ScriptedTurnAdapter(
                (first_turn("observation-gate"), completed_turn("observation-gate"))
            )
            result = OrdivonAgentLoop(
                adapter,
                bridge,
                budget=RunBudget(
                    max_model_calls=3,
                    max_tool_calls=2,
                    max_observation_bytes=32_768,
                    max_wall_time_ms=10_000,
                    max_total_tokens=10_000,
                    max_model_retries=1,
                    max_observation_only_turns=1,
                ),
                clock_ms=FixedClock(),
                monotonic_ms=FixedClock(),
            ).run(
                harness_run_id=run_contract.harness_run_id,
                assignment_id=continuity.binding.assignment_id,
                context_digest=run_contract.context_refs[0].digest,
                initial_messages=(
                    {
                        "role": "user",
                        "content": "Check prior results, then consume the evidence.",
                    },
                ),
            )
            self.assertEqual(result.stop_code, RunStopCode.CANDIDATE_COMPLETED)
            self.assertEqual(result.tool_calls, 1)
            self.assertEqual(len(adapter.requests), 2)
            self.assertEqual(
                tuple(tool.name for tool in adapter.requests[0].tools),
                ("atlas_first_look",),
            )
            self.assertEqual(adapter.requests[1].tools, ())
            self.assertTrue(
                any(
                    message.get("role") == "user"
                    and "external observation gate is now closed"
                    in str(message.get("content", ""))
                    for message in adapter.requests[1].messages
                )
            )
            progress = [
                event.payload
                for event in result.trace.events
                if event.kind == "run_progress_evaluated"
            ]
            self.assertTrue(progress)
            self.assertTrue(progress[0]["observationOnly"])
            self.assertFalse(progress[0]["actionProgress"])
            store.close()

    def test_invalid_atlas_authority_claim_fails_closed(self) -> None:
        class InvalidRuntime(AtlasFakeRuntime):
            def atlas_result(self):
                value = super().atlas_result()
                value["claims"]["semanticEquivalenceInferred"] = True
                return value

        with tempfile.TemporaryDirectory() as directory:
            store, _, _, bridge = self.initialize(directory, "invalid", InvalidRuntime())
            self.bind_direct_state(bridge)
            observation = bridge.execute(first_turn("invalid").tool_calls[0], step_id="step:invalid")
            self.assertEqual(observation.status, "unknown")
            self.assertEqual(observation.structured_content["type"], "AtlasFirstLookProtocolInvalid")
            store.close()

    def test_grant_workspace_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_contract = contract("mismatch")
            store = SQLiteHarnessStore.initialize(Path(directory) / "state")
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(store, run_contract, clock_ms=FixedClock())
            with self.assertRaisesRegex(ValueError, "Workspace differs"):
                SQLiteHarnessAtlasFirstLookRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(run_contract, continuity),
                    AtlasFakeRuntime(),
                    AtlasFirstLookRuntimeGrant(
                        "different-workspace",
                        ATLAS_REVISION,
                        ATLAS_SOURCE_STATE_DIGEST,
                    ),
                )
            store.close()


if __name__ == "__main__":
    unittest.main()

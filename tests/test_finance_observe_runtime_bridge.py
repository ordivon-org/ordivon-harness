from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from anc_canonical import JsonValue, canonical_digest

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.execution_binding import HarnessExecutionBinding, HarnessRuntimeReference
from ordivon_harness.ordivon.finance_observe_runtime_bridge import (
    FINANCE_OBSERVE_DEFINITION,
    FINANCE_OBSERVE_TOOL_SURFACE_DIGEST,
    FinanceObserveRuntimeGrant,
    SQLiteHarnessFinanceObserveRuntimeBridge,
)
from ordivon_harness.ordivon.model import AgentToolCall, ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.runtime_port import HarnessRuntimeClientError
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
FINANCE_REVISION = "21fc6c1741f712445164c5a7757abbcf58720393"
FINANCE_SOURCE_STATE_DIGEST = "sha256:" + "d" * 64
FINANCE_WORKSPACE = "finance-observe-source-fixture"
FINANCE_STATE_ROOT = "/tmp/ordivon-finance-bridge-test-state"
FINANCE_STATE_DB = FINANCE_STATE_ROOT + "/control/finance.db"
FINANCE_APP_PYTHON = "/root/projects/ordivon-finance/.venv/bin/python"


class FixedClock:
    def __init__(self, value: int = 1_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def finance_success() -> dict[str, JsonValue]:
    return {
        "schemaVersion": 1,
        "kind": "ordivon.finance.runtime-domain-result",
        "domain": "finance",
        "operation": "finance.observe",
        "interfaceVersion": 2,
        "ok": True,
        "effectContract": {
            "schemaVersion": 1,
            "kind": "ordivon.semantic-effect-contract",
            "owner": "ordivon-finance",
            "effectClass": "CANONICAL_OBSERVATION",
            "credentialAccess": "read",
            "environmentMutation": False,
            "externalWorldRead": True,
            "externalFinancialWrite": False,
            "financialSubmission": False,
            "authorityMutation": False,
        },
        "result": {
            "schemaVersion": 0,
            "kind": "ordivon.finance.semantic-observe-result",
            "status": "refreshed",
            "goalId": "goal:primary-capital-allocation",
            "portfolioId": "portfolio:okx-tradfi-primary",
            "stateVersionBefore": "10:aaaa",
            "stateVersionAfter": "15:bbbb",
            "observation": {
                "status": "success",
                "errors": [],
                "snapshotRef": "snapshot://fixture",
            },
            "contextStanding": {
                "decision": "abstain",
                "obligations": [{"kind": "decision", "need": "review-decision-epoch"}],
                "portfolioStatus": {
                    "snapshotAgeSeconds": 0.244407,
                    "exposureProjectionCurrent": True,
                },
            },
            "consumerStanding": {
                "canonicalStateMutation": True,
                "externalWorldRead": True,
                "credentialAccess": "read",
                "externalFinancialWrite": False,
                "financialSubmission": False,
                "authorityMutation": False,
            },
        },
    }


def finance_egress_error() -> dict[str, JsonValue]:
    return {
        "schemaVersion": 1,
        "kind": "ordivon.finance.runtime-domain-error",
        "ok": False,
        "error": {
            "type": "FinanceSemanticAdapterError",
            "code": "EGRESS_NOT_CURRENT",
            "message": "scoped egress is not currently AVAILABLE under the expected profile",
        },
        "externalFinancialWriteAttempted": False,
    }


class FinanceFakeRuntime:
    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []
        self.workspace_exec_count = 0
        self.client_request_id: str | None = None
        self.job_id = "job:finance-observe-fixture"

    def owner_stdout(self) -> str:
        if self.mode == "owner-error":
            return json.dumps(finance_egress_error(), ensure_ascii=False)
        if self.mode == "malformed":
            return "not-json"
        if self.mode == "large":
            value = finance_success()
            result = value["result"]
            assert isinstance(result, dict)
            result["diagnosticPadding"] = "x" * 80_000
            return json.dumps(value, ensure_ascii=False)
        return json.dumps(finance_success(), ensure_ascii=False)

    def terminal(self) -> dict[str, JsonValue]:
        assert self.client_request_id is not None
        owner_stdout = self.owner_stdout()
        encoded = owner_stdout.encode("utf-8")
        owner_error = self.mode == "owner-error"
        large = self.mode == "large"
        return {
            "schemaVersion": 1,
            "jobId": self.job_id,
            "clientRequestId": self.client_request_id,
            "status": "failed" if owner_error else "succeeded",
            "executionTerminal": True,
            "executionDisposition": "failed" if owner_error else "succeeded",
            "deliveryDisposition": "committed",
            "recoveryRequired": False,
            "semanticCompletionEvaluated": False,
            "resultAvailable": True,
            "artifacts": [
                {
                    "artifactId": "finance-observe.stdout",
                    "kind": "stdout",
                    "digest": "sha256:" + __import__("hashlib").sha256(encoded).hexdigest(),
                    "retainedBytes": len(encoded),
                    "droppedBytes": 0,
                    "truncated": False,
                }
            ],
            "stdoutTail": owner_stdout[-65_536:] if large else owner_stdout,
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
                raise HarnessRuntimeClientError("injected Finance Runtime response loss")
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
        if name == "artifact.read":
            terminal = self.terminal()
            artifact = terminal["artifacts"][0]
            assert isinstance(artifact, dict)
            return {
                "artifactId": artifact["artifactId"],
                "jobId": self.job_id,
                "content": self.owner_stdout(),
                "digest": artifact["digest"],
                "offset": 0,
                "nextOffset": artifact["retainedBytes"],
                "eof": True,
            }
        raise AssertionError(f"unexpected Runtime Tool: {name}")


def grant() -> FinanceObserveRuntimeGrant:
    return FinanceObserveRuntimeGrant(
        FINANCE_WORKSPACE,
        FINANCE_REVISION,
        FINANCE_SOURCE_STATE_DIGEST,
        FINANCE_STATE_ROOT,
        FINANCE_STATE_DB,
        FINANCE_APP_PYTHON,
    )


def contract(suffix: str) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f"harness-run:finance-observe-{suffix}",
        harness_implementation_id="ordivon-harness@0.7.0-dev",
        caller_id="caller:finance-observe-test",
        caller_run_ref=f"trial:finance-observe-{suffix}",
        objective_ref=HarnessBoundReference(
            f"objective:finance-observe-{suffix}", "objective", DIGEST_A
        ),
        context_refs=(
            HarnessBoundReference(
                f"context:finance-observe-{suffix}", "context", DIGEST_B
            ),
        ),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=FINANCE_OBSERVE_TOOL_SURFACE_DIGEST,
        tool_grant_digest=grant().digest,
        budget={"maxModelCalls": 3, "maxToolCalls": 2, "maxWallTimeMs": 10_000},
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            f"system-manifest:finance-observe-{suffix}", "system-manifest", DIGEST_C
        ),
        created_at_ms=1_000,
    )


def execution_binding(
    run_contract: HarnessRunContract,
    continuity: SQLiteHarnessRunContinuityStore,
    *,
    workspace_ref: str = FINANCE_WORKSPACE,
) -> HarnessExecutionBinding:
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
        workspace_ref=workspace_ref,
        assignment_id=binding.assignment_id,
        assignment_generation=binding.assignment_generation,
        assignment_digest=binding.assignment_digest,
        runtime_binding_digest=canonical_digest(
            {
                "harnessRunId": run_contract.harness_run_id,
                "workspaceRef": workspace_ref,
                "sourceRevisionExpected": FINANCE_REVISION,
            }
        ),
        tool_catalog_digest=run_contract.tool_catalog_digest,
        tool_grant_digest=run_contract.tool_grant_digest,
        deadline_ms=run_contract.deadline_ms,
        runtime_references=references,
    )


def finance_call(suffix: str, arguments=None) -> AgentToolCall:
    return AgentToolCall(
        tool_call_id=f"tool-call:finance-observe-{suffix}",
        name="finance_observe",
        arguments={} if arguments is None else arguments,
    )


class FinanceObserveRuntimeBridgeTests(unittest.TestCase):
    def initialize(self, directory: str, suffix: str, runtime: FinanceFakeRuntime):
        run_contract = contract(suffix)
        store = SQLiteHarnessStore.initialize(Path(directory) / "state")
        store.create_run(run_contract)
        continuity = SQLiteHarnessRunContinuityStore(
            store, run_contract, clock_ms=FixedClock()
        )
        bridge = SQLiteHarnessFinanceObserveRuntimeBridge(
            run_contract,
            continuity,
            execution_binding(run_contract, continuity),
            runtime,
            grant(),
        )
        return store, run_contract, continuity, bridge

    @staticmethod
    def bind_direct_state(bridge: SQLiteHarnessFinanceObserveRuntimeBridge) -> None:
        bridge.bind_run_state(
            messages=({"role": "user", "content": "refresh Finance current state"},),
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

    def test_surface_is_zero_argument_and_is_not_pure_read_only(self):
        schema = FINANCE_OBSERVE_DEFINITION.input_schema
        self.assertEqual(schema["properties"], {})
        self.assertFalse(schema["additionalProperties"])
        value = grant().to_dict()
        self.assertEqual(value["effectClass"], "canonical-observation-external-read-no-financial-write")
        self.assertEqual(value["progressClass"], "observation-no-capital-effect")
        self.assertFalse(value["providerPlumbingAllowed"])
        self.assertFalse(value["financialWriteAllowed"])
        self.assertEqual(
            SQLiteHarnessFinanceObserveRuntimeBridge.observation_only_tool_names,
            frozenset({"finance_observe"}),
        )

    def test_agent_cannot_invent_goal_identity_for_current_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FinanceFakeRuntime()
            _, _, _, bridge = self.initialize(directory, "invented-goal", runtime)
            self.bind_direct_state(bridge)
            with self.assertRaisesRegex(
                Exception, "accepts no Agent-authored arguments"
            ):
                bridge.execute(
                    finance_call("invented-goal", {"goalId": "goal:current"}),
                    step_id="step:1",
                )
            self.assertEqual(runtime.workspace_exec_count, 0)

    def test_lowering_hides_provider_plumbing_and_preserves_exact_owner_state_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FinanceFakeRuntime()
            _, _, _, bridge = self.initialize(directory, "lower", runtime)
            self.bind_direct_state(bridge)
            observation = bridge.execute(finance_call("lower"), step_id="step:1")
            self.assertEqual(observation.status, "observed")
            request = next(args for name, args in runtime.calls if name == "workspace.exec")
            execution = request["execution"]
            self.assertEqual(execution["workspaceId"], FINANCE_WORKSPACE)
            self.assertEqual(execution["executable"], "/usr/bin/node")
            self.assertEqual(
                execution["args"],
                [
                    "scripts/finance-domain.mjs",
                    "call",
                    "--operation",
                    "finance.observe",
                    "--arguments-json",
                    '{}',
                ],
            )
            self.assertEqual(
                execution["env"],
                {
                    "ORDIVON_FINANCE_STATE_ROOT": FINANCE_STATE_ROOT,
                    "ORDIVON_FINANCE_STATE_DB": FINANCE_STATE_DB,
                    "ORDIVON_FINANCE_APP_PYTHON": FINANCE_APP_PYTHON,
                },
            )
            encoded = json.dumps(request, sort_keys=True)
            for forbidden in ("proxy", "okx", "collector", "apiKey", "provider"):
                self.assertNotIn(forbidden, encoded)
            structured = observation.structured_content
            self.assertEqual(structured["owner"], "ordivon-finance")
            self.assertTrue(structured["effectBoundary"]["canonicalObservationStateMayMutate"])
            self.assertFalse(structured["effectBoundary"]["externalFinancialWrite"])
            self.assertFalse(structured["effectBoundary"]["authorityMutation"])

    def test_known_owner_egress_blocker_is_observed_even_when_process_exit_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FinanceFakeRuntime("owner-error")
            _, _, _, bridge = self.initialize(directory, "owner-error", runtime)
            self.bind_direct_state(bridge)
            observation = bridge.execute(finance_call("owner-error"), step_id="step:1")
            self.assertEqual(observation.status, "observed")
            self.assertEqual(observation.structured_content["ownerOutcome"], "blocked")
            owner_error = observation.structured_content["ownerError"]
            self.assertEqual(owner_error["code"], "EGRESS_NOT_CURRENT")
            self.assertFalse(observation.structured_content["effectBoundary"]["externalFinancialWriteAttempted"])
            self.assertEqual(
                observation.structured_content["runtime"]["executionDisposition"],
                "failed",
            )

    def test_malformed_owner_output_is_unknown_not_model_correctable(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FinanceFakeRuntime("malformed")
            _, _, _, bridge = self.initialize(directory, "malformed", runtime)
            self.bind_direct_state(bridge)
            observation = bridge.execute(finance_call("malformed"), step_id="step:1")
            self.assertEqual(observation.status, "unknown")
            self.assertEqual(
                observation.structured_content["type"], "FinanceObserveProtocolInvalid"
            )
            self.assertFalse(observation.structured_content["safeToCorrect"])

    def test_large_owner_output_uses_verified_runtime_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FinanceFakeRuntime("large")
            _, _, _, bridge = self.initialize(directory, "large", runtime)
            self.bind_direct_state(bridge)
            observation = bridge.execute(finance_call("large"), step_id="step:1")
            self.assertEqual(observation.status, "observed")
            self.assertIn("artifact.read", [name for name, _ in runtime.calls])
            self.assertIn("ownerEnvelopeDigest", observation.structured_content)
            projection = observation.structured_content["financeProjection"]
            self.assertEqual(projection["status"], "refreshed")
            self.assertNotIn("diagnosticPadding", projection)

    def test_runtime_response_loss_reattaches_same_job_without_redispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FinanceFakeRuntime("loss")
            _, _, _, bridge = self.initialize(directory, "loss", runtime)
            self.bind_direct_state(bridge)
            observation = bridge.execute(finance_call("loss"), step_id="step:1")
            self.assertEqual(observation.status, "observed")
            self.assertEqual(runtime.workspace_exec_count, 1)
            self.assertIn("task.list", [name for name, _ in runtime.calls])
            self.assertIn("task.observe", [name for name, _ in runtime.calls])

    def test_unknown_agent_argument_is_rejected_before_runtime_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FinanceFakeRuntime()
            _, _, _, bridge = self.initialize(directory, "unknown-arg", runtime)
            self.bind_direct_state(bridge)
            with self.assertRaisesRegex(Exception, "accepts no Agent-authored arguments"):
                bridge.execute(
                    finance_call("unknown-arg", {"proxy": "http://127.0.0.1:1"}),
                    step_id="step:1",
                )
            self.assertEqual(runtime.workspace_exec_count, 0)

    def test_workspace_grant_mismatch_fails_before_bridge_can_run(self):
        with tempfile.TemporaryDirectory() as directory:
            run_contract = contract("mismatch")
            store = SQLiteHarnessStore.initialize(Path(directory) / "state")
            store.create_run(run_contract)
            continuity = SQLiteHarnessRunContinuityStore(
                store, run_contract, clock_ms=FixedClock()
            )
            with self.assertRaisesRegex(ValueError, "grant Workspace differs"):
                SQLiteHarnessFinanceObserveRuntimeBridge(
                    run_contract,
                    continuity,
                    execution_binding(
                        run_contract, continuity, workspace_ref="wrong-finance-workspace"
                    ),
                    FinanceFakeRuntime(),
                    grant(),
                )


if __name__ == "__main__":
    unittest.main()

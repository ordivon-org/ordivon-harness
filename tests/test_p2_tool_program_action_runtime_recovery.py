from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.agent_tool_observation import HarnessToolObservation
from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.sqlite_repository_repair_bridge import (
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS,
    SQLiteHarnessRepositoryRepairRuntimeBridge,
)
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.protocol import HarnessToolStepIntent, HarnessToolStepReceipt
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.tool_program import HarnessToolProgramAction
from ordivon_harness.tool_program_durable_recovery import (
    HarnessToolProgramDurableStepEvidence,
    recover_tool_program_from_durable_evidence,
)
from ordivon_harness.tool_program_recovery import HarnessToolProgramActionExecutor

from tests.test_p1_repository_repair_runtime_bridge import (
    FakeRuntime,
    bound_state,
    contract,
    execution_binding,
)
from tests.test_p2_tool_program_runtime_bridge import (
    UnreconciledPatchRuntime,
    repair_program,
)


_TERMINAL_TOOL_EVENTS = {
    "harness.tool-step-recorded",
    "harness.tool-step-reconciled",
    "harness.tool-step-unknown",
}


def private_tool_contract(suffix: str):
    return replace(
        contract(suffix),
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=False,
            allow_tool_content=True,
        ),
    )


def initialize(
    root: Path,
    suffix: str,
    runtime: FakeRuntime,
    *,
    run_contract=None,
):
    run_contract = contract(suffix) if run_contract is None else run_contract
    store = SQLiteHarnessStore.initialize(root)
    store.create_run(run_contract)
    continuity = SQLiteHarnessRunContinuityStore(
        store,
        run_contract,
        clock_ms=lambda: 1_000,
    )
    bridge = SQLiteHarnessRepositoryRepairRuntimeBridge(
        run_contract,
        continuity,
        execution_binding(run_contract, continuity),
        runtime,
    )
    state = bound_state()
    bridge.bind_run_state(
        messages=state.messages,
        observations=(),
        remaining_budget=state.remaining_budget,
        requested_model_id=state.requested_model_id,
        effective_model_id=None,
        active_elapsed_ms=0,
    )
    return run_contract, store, continuity, bridge


def durable_program_evidence(
    store: SQLiteHarnessStore,
    harness_run_id: str,
) -> tuple[HarnessToolProgramDurableStepEvidence, ...]:
    evidence: list[HarnessToolProgramDurableStepEvidence] = []
    for event in store.list_run_events(harness_run_id):
        if event.event_kind not in _TERMINAL_TOOL_EVENTS:
            continue
        intent_object_digest = event.data.get("toolStepIntentObjectDigest")
        receipt_object_digest = event.data.get("receiptObjectDigest")
        if not isinstance(intent_object_digest, str) or not isinstance(
            receipt_object_digest, str
        ):
            continue

        raw_intent = store.get_object(
            intent_object_digest,
            expected_kind="harness-tool-step-intent",
        )
        raw_receipt = store.get_object(
            receipt_object_digest,
            expected_kind="harness-tool-step-receipt",
        )
        if not isinstance(raw_intent, dict) or not isinstance(raw_receipt, dict):
            raise TypeError("durable ToolProgram Intent/Receipt must be objects")
        intent = HarnessToolStepIntent.from_dict(raw_intent)
        receipt = HarnessToolStepReceipt.from_dict(raw_receipt)
        if not receipt.terminal:
            continue

        observation = None
        observation_object_digest = event.data.get("observationObjectDigest")
        if observation_object_digest is not None:
            if not isinstance(observation_object_digest, str):
                raise TypeError("durable observation reference must be a digest")
            raw_observation = store.get_object(
                observation_object_digest,
                expected_kind="harness-tool-observation",
            )
            if not isinstance(raw_observation, dict):
                raise TypeError("durable ToolProgram observation must be an object")
            observation = HarnessToolObservation.from_dict(raw_observation)

        evidence.append(
            HarnessToolProgramDurableStepEvidence(
                intent=intent,
                receipt=receipt,
                observation=observation,
            )
        )
    return tuple(evidence)


class ToolProgramActionRuntimeRecoveryP2Tests(unittest.TestCase):
    def action(self, suffix: str) -> HarnessToolProgramAction:
        return HarnessToolProgramAction(
            action_call_id=f"program-action:p2:{suffix}:1",
            program=repair_program(),
        )

    def test_metadata_only_restart_recognizes_completed_effects_and_stops_safely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = FakeRuntime()
            run_contract, store, continuity, bridge = initialize(
                root,
                "program-action-metadata-restart",
                runtime,
            )
            action = self.action("metadata-restart")
            live = HarnessToolProgramActionExecutor(
                bridge,
                INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS,
            ).execute(
                action,
                remaining_tool_calls=5,
                step_prefix="turn:p2:metadata-restart",
            )
            self.assertEqual(live.status, "completed")
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

            with SQLiteHarnessStore(root) as reopened:
                reopened.validate_run_history(run_contract.harness_run_id)
                evidence = durable_program_evidence(
                    reopened,
                    run_contract.harness_run_id,
                )
                self.assertEqual(len(evidence), 5)
                self.assertTrue(all(item.receipt.terminal for item in evidence))
                self.assertTrue(all(item.observation is None for item in evidence))
                self.assertEqual(
                    [item.receipt.status.value for item in evidence],
                    ["observed"] * 5,
                )

                recovered = recover_tool_program_from_durable_evidence(action, evidence)
                self.assertTrue(recovered.recovery_required)
                self.assertEqual(
                    recovered.recovery_reason,
                    "tool-observation-content-unavailable",
                )
                self.assertIsNone(recovered.next_call)
                self.assertEqual(
                    [item.to_projection()["toolName"] for item in evidence],
                    [step.tool_name for step in action.program.steps],
                )

            # Recovery recognized five already-terminal physical effects and never
            # redispatched step zero merely because privacy withheld observation bodies.
            self.assertEqual(runtime.patch_count, 1)
            self.assertEqual(runtime.exec_count, 1)

    def test_private_content_restart_reconstructs_result_and_intermediate_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = FakeRuntime()
            run_contract = private_tool_contract("program-action-private-restart")
            run_contract, store, continuity, bridge = initialize(
                root,
                "program-action-private-restart",
                runtime,
                run_contract=run_contract,
            )
            action = self.action("private-restart")
            live = HarnessToolProgramActionExecutor(
                bridge,
                INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS,
            ).execute(
                action,
                remaining_tool_calls=5,
                step_prefix="turn:p2:private-restart",
            )
            self.assertEqual(live.status, "completed")
            live_projection = live.to_model_projection()
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

            with SQLiteHarnessStore(root) as reopened:
                evidence = durable_program_evidence(
                    reopened,
                    run_contract.harness_run_id,
                )
                self.assertEqual(len(evidence), 5)
                self.assertTrue(all(item.observation is not None for item in evidence))

                recovered = recover_tool_program_from_durable_evidence(action, evidence)
                self.assertTrue(recovered.terminal)
                assert recovered.terminal_result is not None
                self.assertEqual(
                    recovered.terminal_result.to_model_projection(),
                    live_projection,
                )

                prefix = recover_tool_program_from_durable_evidence(action, evidence[:2])
                self.assertEqual(prefix.disposition, "ready-next")
                assert prefix.next_call is not None
                self.assertEqual(prefix.next_call.name, "run_check")
                self.assertEqual(prefix.next_call.arguments["checkId"], "visible-tests")

            self.assertEqual(runtime.patch_count, 1)
            self.assertEqual(runtime.exec_count, 1)

    def test_action_executor_preserves_patch_response_loss_and_private_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = FakeRuntime(patch_loss=True)
            run_contract = private_tool_contract("program-action-patch-loss")
            run_contract, store, continuity, bridge = initialize(
                root,
                "program-action-patch-loss",
                runtime,
                run_contract=run_contract,
            )
            action = self.action("patch-loss")
            result = HarnessToolProgramActionExecutor(
                bridge,
                INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS,
            ).execute(
                action,
                remaining_tool_calls=5,
                step_prefix="turn:p2:patch-loss",
            )
            self.assertEqual(result.status, "completed")
            self.assertEqual(runtime.patch_count, 1)
            self.assertTrue(result.observations[1].reconciled)
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

            with SQLiteHarnessStore(root) as reopened:
                evidence = durable_program_evidence(
                    reopened,
                    run_contract.harness_run_id,
                )
                self.assertTrue(evidence[1].receipt.reconciled)
                recovered = recover_tool_program_from_durable_evidence(action, evidence)
                self.assertTrue(recovered.terminal)
                assert recovered.terminal_result is not None
                self.assertEqual(recovered.terminal_result.output, result.output)

            self.assertEqual(runtime.patch_count, 1)

    def test_unreconciled_unknown_metadata_restart_never_derives_later_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = UnreconciledPatchRuntime()
            run_contract, store, continuity, bridge = initialize(
                root,
                "program-action-unknown",
                runtime,
            )
            action = self.action("unknown")
            live = HarnessToolProgramActionExecutor(
                bridge,
                INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS,
            ).execute(
                action,
                remaining_tool_calls=5,
                step_prefix="turn:p2:unknown",
            )
            self.assertEqual(live.status, "unknown")
            self.assertEqual(len(live.observations), 2)
            self.assertEqual(
                [name for name, _arguments in runtime.calls],
                ["workspace.read", "workspace.patch", "workspace.patch.get"],
            )
            self.assertTrue(continuity.doctor()["healthy"])
            store.close()

            with SQLiteHarnessStore(root) as reopened:
                evidence = durable_program_evidence(
                    reopened,
                    run_contract.harness_run_id,
                )
                self.assertEqual(len(evidence), 2)
                self.assertEqual(evidence[-1].receipt.status.value, "unknown")
                self.assertTrue(all(item.observation is None for item in evidence))
                recovered = recover_tool_program_from_durable_evidence(action, evidence)
                self.assertTrue(recovered.recovery_required)
                self.assertEqual(
                    recovered.recovery_reason,
                    "tool-observation-content-unavailable",
                )
                self.assertIsNone(recovered.next_call)

            self.assertEqual(
                [name for name, _arguments in runtime.calls],
                ["workspace.read", "workspace.patch", "workspace.patch.get"],
            )

    def test_forged_durable_intent_digest_fails_against_immutable_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            runtime = FakeRuntime()
            run_contract, store, _continuity, bridge = initialize(
                root,
                "program-action-forged-intent",
                runtime,
            )
            action = self.action("forged-intent")
            HarnessToolProgramActionExecutor(
                bridge,
                INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS,
            ).execute(
                action,
                remaining_tool_calls=5,
                step_prefix="turn:p2:forged-intent",
            )
            evidence = durable_program_evidence(store, run_contract.harness_run_id)
            first = evidence[0]
            forged_intent = replace(
                first.intent,
                tool_call_digest="sha256:" + "f" * 64,
            )
            forged_receipt = replace(
                first.receipt,
                intent_digest=forged_intent.digest,
            )
            forged = (
                HarnessToolProgramDurableStepEvidence(
                    intent=forged_intent,
                    receipt=forged_receipt,
                    observation=None,
                ),
            )
            with self.assertRaisesRegex(ValueError, "Tool Call digest differs"):
                recover_tool_program_from_durable_evidence(action, forged)
            store.close()


if __name__ == "__main__":
    unittest.main()

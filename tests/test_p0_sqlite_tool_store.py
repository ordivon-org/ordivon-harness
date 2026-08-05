from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

from ordivon_harness.errors import HarnessSuperseded
from ordivon_harness.ordivon.sqlite_run_store import (
    SQLiteHarnessRunContinuityStore,
)
from ordivon_harness.ordivon.tools import RuntimeToolBridge
from ordivon_harness.protocol import (
    HarnessRecoveryConsequence,
    HarnessRunPauseReason,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
    HarnessToolStepStatus,
)
from ordivon_harness.sqlite_store import SQLiteHarnessStore

from tests.test_p0_sqlite_provider_store import MutableClock, contract, state


class SQLiteHarnessRunContinuityToolTests(unittest.TestCase):
    def prepare(self, root: Path, clock: MutableClock):
        store = SQLiteHarnessStore.initialize(root)
        run_contract = contract()
        store.create_run(run_contract)
        continuity = SQLiteHarnessRunContinuityStore(
            store,
            run_contract,
            clock_ms=clock,
        )
        continuity.bind_state(state())
        binding = continuity.binding
        intent = HarnessToolStepIntent(
            intent_id="harness-tool-step-intent:p0-sqlite-tool-001",
            harness_run_id=run_contract.harness_run_id,
            assignment_id=binding.assignment_id,
            assignment_generation=binding.assignment_generation,
            assignment_digest=binding.assignment_digest,
            turn_id="turn:p0-sqlite-tool-001",
            tool_call_id="tool-call:p0-sqlite-tool-001",
            tool_name="workspace.read",
            tool_call_digest=canonical_digest({"toolCall": 1}),
            runtime_operation="workspace.read",
            runtime_arguments_digest=canonical_digest({"relativePath": "README.md"}),
            client_request_id="request:p0-sqlite-tool-001",
            recovery_consequence=HarnessRecoveryConsequence.OBSERVATION_ONLY,
            created_at_ms=clock(),
        )
        return store, continuity, intent

    @staticmethod
    def observation(status: str = "observed") -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.test-tool-observation",
            "status": status,
            "runtimeJobRef": "runtime-job:p0-sqlite-tool-001",
        }

    def test_prepare_persists_v2_fence_and_runtime_authority_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, continuity, intent = self.prepare(root, clock)
            retained = continuity.prepare_tool_step(intent)
            step = continuity.load_current_tool_step()
            self.assertEqual(step.intent, intent)
            self.assertEqual(step.receipt, None)
            self.assertIsNotNone(step.fence)
            assert step.fence is not None
            self.assertEqual(step.fence.authority_namespace, "ordivon.harness")
            self.assertEqual(step.fence.authority_type, "dispatch_fence")
            self.assertEqual(step.fence.authority_generation, 2)
            continuity.assert_dispatch_fence_current(step.fence)
            self.assertEqual(
                continuity.load_current_snapshot().snapshot,
                retained.snapshot,
            )
            arguments = RuntimeToolBridge._with_dispatch_fence(
                {"execution": {"foreignReferences": []}},
                step.fence,
            )
            references = arguments["execution"]["foreignReferences"]
            self.assertEqual(
                references,
                [
                    {
                        "namespace": "ordivon.harness",
                        "type": "dispatch_fence",
                        "id": step.fence.fence_id,
                        "generation": "2",
                        "digest": step.fence.digest,
                    }
                ],
            )
            store.close()

    def test_terminal_receipt_is_idempotent_and_fences_old_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, continuity, intent = self.prepare(root, clock)
            continuity.prepare_tool_step(intent)
            step = continuity.load_current_tool_step()
            assert step.fence is not None
            observation = self.observation()
            clock.advance()
            receipt = HarnessToolStepReceipt(
                receipt_id="harness-tool-step-receipt:p0-sqlite-tool-observed",
                intent_digest=intent.digest,
                harness_run_id=continuity.harness_run_id,
                tool_call_id=intent.tool_call_id,
                status=HarnessToolStepStatus.OBSERVED,
                runtime_job_ref="runtime-job:p0-sqlite-tool-001",
                observation_digest=canonical_digest(observation),
                reconciled=False,
                created_at_ms=clock(),
            )
            continuity.record_tool_step_receipt(receipt, observation)
            current = continuity.load_current_tool_step()
            self.assertEqual(current.receipt, receipt)
            self.assertEqual(current.observation, observation)
            continuity.record_tool_step_receipt(receipt, observation)
            self.assertEqual(continuity.caller_revision, 3)
            with self.assertRaises(HarnessSuperseded):
                continuity.assert_dispatch_fence_current(step.fence)
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore(
                    reopened_store,
                    contract(),
                    clock_ms=clock,
                )
                self.assertEqual(reopened.load_current_tool_step().receipt, receipt)
                report = reopened.doctor()
                self.assertTrue(report["healthy"])
                self.assertEqual(report["toolRecords"], 2)
                self.assertEqual(report["snapshots"], 1)

    def test_nonterminal_receipt_chains_to_reconciled_terminal_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, continuity, intent = self.prepare(root, clock)
            continuity.prepare_tool_step(intent)
            first_observation = self.observation("cancel-requested")
            clock.advance()
            first = HarnessToolStepReceipt(
                receipt_id="harness-tool-step-receipt:p0-sqlite-tool-cancel-requested",
                intent_digest=intent.digest,
                harness_run_id=continuity.harness_run_id,
                tool_call_id=intent.tool_call_id,
                status=HarnessToolStepStatus.CANCEL_REQUESTED,
                runtime_job_ref="runtime-job:p0-sqlite-tool-001",
                observation_digest=canonical_digest(first_observation),
                reconciled=False,
                created_at_ms=clock(),
            )
            continuity.record_tool_step_receipt(first, first_observation)
            second_observation = self.observation("cancelled")
            clock.advance()
            second = HarnessToolStepReceipt(
                receipt_id="harness-tool-step-receipt:p0-sqlite-tool-cancelled",
                intent_digest=intent.digest,
                harness_run_id=continuity.harness_run_id,
                tool_call_id=intent.tool_call_id,
                status=HarnessToolStepStatus.CANCELLED,
                runtime_job_ref="runtime-job:p0-sqlite-tool-001",
                observation_digest=canonical_digest(second_observation),
                reconciled=True,
                created_at_ms=clock(),
                previous_receipt_digest=first.digest,
            )
            continuity.record_tool_step_receipt(second, second_observation)
            current = continuity.load_current_tool_step()
            self.assertEqual(current.receipt, second)
            self.assertEqual(current.previous_receipt, first)
            self.assertEqual(current.observation, second_observation)
            self.assertEqual(continuity.doctor()["toolRecords"], 3)
            store.close()

    def test_pause_snapshot_reopens_and_supersedes_contract_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, continuity, _ = self.prepare(root, clock)
            initial_source = continuity.assignment_provider_source()
            clock.advance()
            paused = continuity.record_pause(HarnessRunPauseReason.NEEDS_INPUT)
            self.assertEqual(paused.snapshot.sequence, 1)
            with self.assertRaises(HarnessSuperseded):
                continuity.claim_provider_call(
                    source=initial_source,
                    turn_id="turn:p0-after-pause-001",
                    turn_sequence=1,
                    request_digest=canonical_digest({"request": 1}),
                    provider_request_digest=canonical_digest({"providerRequest": 1}),
                    adapter_id="adapter:scripted-v1",
                    requested_model_id="model:scripted",
                    holder_id="holder:stale-source",
                    ttl_ms=10,
                )
            source = continuity.snapshot_provider_source(paused)
            claimed = continuity.claim_provider_call(
                source=source,
                turn_id="turn:p0-after-pause-001",
                turn_sequence=1,
                request_digest=canonical_digest({"request": 1}),
                provider_request_digest=canonical_digest({"providerRequest": 1}),
                adapter_id="adapter:scripted-v1",
                requested_model_id="model:scripted",
                holder_id="holder:snapshot-source",
                ttl_ms=10,
            )
            self.assertEqual(claimed.record.source_kind.value, "snapshot")
            store.close()

            with SQLiteHarnessStore(root) as reopened_store:
                reopened = SQLiteHarnessRunContinuityStore(
                    reopened_store,
                    contract(),
                    clock_ms=clock,
                )
                retained = reopened.load_current_snapshot()
                self.assertEqual(retained.snapshot, paused.snapshot)
                reopened.bind_state(state())
                replay = reopened.load_provider_replay_state(
                    source=source,
                    snapshot=retained,
                    additional_messages=(),
                    adapter_id="adapter:scripted-v1",
                    requested_model_id="model:scripted",
                )
                self.assertEqual(replay, state())

    def test_intent_from_another_binding_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            clock = MutableClock()
            store, continuity, intent = self.prepare(root, clock)
            wrong = HarnessToolStepIntent(
                intent_id="harness-tool-step-intent:p0-sqlite-tool-wrong",
                harness_run_id=intent.harness_run_id,
                assignment_id="assignment:external:wrong",
                assignment_generation=1,
                assignment_digest=intent.assignment_digest,
                turn_id=intent.turn_id,
                tool_call_id="tool-call:p0-sqlite-tool-wrong",
                tool_name=intent.tool_name,
                tool_call_digest=intent.tool_call_digest,
                runtime_operation=intent.runtime_operation,
                runtime_arguments_digest=intent.runtime_arguments_digest,
                client_request_id="request:p0-sqlite-tool-wrong",
                recovery_consequence=intent.recovery_consequence,
                created_at_ms=intent.created_at_ms,
            )
            with self.assertRaisesRegex(ValueError, "Run binding"):
                continuity.prepare_tool_step(wrong)
            store.close()


if __name__ == "__main__":
    unittest.main()

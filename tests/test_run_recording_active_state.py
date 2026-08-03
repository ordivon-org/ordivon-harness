from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from anc_canonical import canonical_digest
from ordivon_host import HostStorage
from ordivon_host.objects import ObjectMissing
from test_ordivon_harness_oh5 import (
    TASK_ID,
    _RecoveryRuntime,
    _assign,
    _conclusion_result,
    _create_task,
)
from test_provider_call_history import _claim
from test_provider_call_recovery import (
    _MutableClock,
    _provider_failure,
    _provider_result,
    _provider_state,
)

from ordivon_harness import HarnessLifecycleError
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    AgentToolCall,
    HostHarnessRunStore,
    NativeRunTimes,
    ToolObservation,
    record_native_run_result,
)
from ordivon_harness.protocol import (
    HarnessRecoveryConsequence,
    HarnessToolStepIntent,
    HarnessToolStepReceipt,
    HarnessToolStepStatus,
)


def _tool_intent(store: HostHarnessRunStore, *, suffix: str) -> HarnessToolStepIntent:
    assignment = store.committed.assignment
    assert store.committed.native_run_contract is not None
    call = AgentToolCall(
        f"tool-call:run-recording:{suffix}",
        "read_workspace",
        {"relativePath": "README.md"},
    )
    runtime_arguments = {
        "schemaVersion": 1,
        "workspaceId": assignment.workspace_ref,
        "relativePath": "README.md",
    }
    return HarnessToolStepIntent(
        intent_id=f"harness-tool-step-intent:run-recording:{suffix}",
        harness_run_id=store.committed.native_run_contract.harness_run_id,
        assignment_id=assignment.assignment_id,
        assignment_generation=assignment.generation,
        assignment_digest=assignment.digest,
        turn_id=f"turn:run-recording:{suffix}",
        tool_call_id=call.tool_call_id,
        tool_name=call.name,
        tool_call_digest=call.digest,
        runtime_operation="workspace.read",
        runtime_arguments_digest=canonical_digest(runtime_arguments),
        client_request_id=f"runtime-client:run-recording:{suffix}",
        recovery_consequence=HarnessRecoveryConsequence.OBSERVATION_ONLY,
        created_at_ms=100_010,
    )


def _assert_no_recorded_run(
    testcase: unittest.TestCase,
    storage: HostStorage,
) -> None:
    snapshot = storage.read_task_event(TASK_ID)
    testcase.assertNotIn("harnessRunDigest", snapshot.data)
    testcase.assertNotIn("harnessRunObjectDigest", snapshot.data)


class RunRecordingActiveStateTests(unittest.TestCase):
    def test_claimed_and_dispatching_provider_heads_block_run_recording(self) -> None:
        for status in ("claimed", "dispatching"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    _create_task(storage, clock)
                    host, store, _, _, claimed = _claim(storage, clock)
                    retained = (
                        claimed
                        if status == "claimed"
                        else store.mark_provider_call_dispatching(claimed)
                    )
                    committed = store.committed
                    result = _conclusion_result(
                        committed,
                        committed.assignment.context_object_digest,
                        suffix=f"provider-{status}",
                    )
                    before = storage.read_task_event(TASK_ID)

                    with self.assertRaisesRegex(
                        HarnessLifecycleError,
                        rf"active {status} Provider Call",
                    ):
                        record_native_run_result(
                            host,
                            committed,
                            result,
                            times=NativeRunTimes(100_100, 100_110),
                        )

                    after = storage.read_task_event(TASK_ID)
                    self.assertEqual(after.projection.revision, before.projection.revision)
                    self.assertEqual(
                        after.data["activeHarnessProviderCallDigest"],
                        retained.record.digest,
                    )
                    self.assertEqual(
                        after.data["activeHarnessProviderCallStatus"],
                        status,
                    )
                    _assert_no_recorded_run(self, storage)
                    validate_history(storage)

    def test_missing_completed_provider_result_blocks_run_recording(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, store, _, _, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                completed = store.complete_provider_call(
                    dispatching,
                    _provider_result(),
                )
                committed = store.committed
                result = _conclusion_result(
                    committed,
                    committed.assignment.context_object_digest,
                    suffix="missing-provider-result",
                )
                before = storage.read_task_event(TASK_ID)
                original_get = storage.objects.get

                def missing_result(digest, *, expected_kind=None):
                    if digest == completed.record.result_object_digest:
                        raise ObjectMissing("injected missing Provider result")
                    return original_get(digest, expected_kind=expected_kind)

                with (
                    patch.object(storage.objects, "get", side_effect=missing_result),
                    self.assertRaisesRegex(
                        HarnessLifecycleError,
                        "malformed active Provider Call terminal outcome",
                    ),
                ):
                    record_native_run_result(
                        host,
                        committed,
                        result,
                        times=NativeRunTimes(100_100, 100_110),
                    )

                after = storage.read_task_event(TASK_ID)
                self.assertEqual(after.projection.revision, before.projection.revision)
                self.assertEqual(
                    after.data["activeHarnessProviderCallDigest"],
                    completed.record.digest,
                )
                self.assertEqual(
                    after.data["activeHarnessProviderCallStatus"],
                    "completed",
                )
                _assert_no_recorded_run(self, storage)
                validate_history(storage)

    def test_mismatched_provider_failure_blocks_run_recording(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                host, store, _, _, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                failure = _provider_failure(
                    dispatching,
                    dispatch_safety="pre_dispatch_safe",
                )
                failed = store.fail_provider_call(
                    dispatching,
                    failure=failure,
                )
                committed = store.committed
                result = _conclusion_result(
                    committed,
                    committed.assignment.context_object_digest,
                    suffix="mismatched-provider-failure",
                )
                before = storage.read_task_event(TASK_ID)
                original_get = storage.objects.get
                mismatched_failure = replace(
                    failure,
                    provider_call_id="provider-call:run-recording:mismatch",
                )

                def mismatched_outcome(digest, *, expected_kind=None):
                    if digest == failed.record.failure_object_digest:
                        return mismatched_failure.to_dict()
                    return original_get(digest, expected_kind=expected_kind)

                with (
                    patch.object(
                        storage.objects,
                        "get",
                        side_effect=mismatched_outcome,
                    ),
                    self.assertRaisesRegex(
                        HarnessLifecycleError,
                        "active Provider Call terminal outcome differs",
                    ),
                ):
                    record_native_run_result(
                        host,
                        committed,
                        result,
                        times=NativeRunTimes(100_100, 100_110),
                    )

                after = storage.read_task_event(TASK_ID)
                self.assertEqual(after.projection.revision, before.projection.revision)
                self.assertEqual(
                    after.data["activeHarnessProviderCallDigest"],
                    failed.record.digest,
                )
                self.assertEqual(
                    after.data["activeHarnessProviderCallStatus"],
                    "failed",
                )
                _assert_no_recorded_run(self, storage)
                validate_history(storage)

    def test_unadmitted_provider_record_or_state_blocks_run_recording(self) -> None:
        for target in ("record", "state"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    _create_task(storage, clock)
                    host, store, _, _, claimed = _claim(storage, clock)
                    dispatching = store.mark_provider_call_dispatching(claimed)
                    completed = store.complete_provider_call(
                        dispatching,
                        _provider_result(),
                    )
                    committed = store.committed
                    result = _conclusion_result(
                        committed,
                        committed.assignment.context_object_digest,
                        suffix=f"unadmitted-provider-{target}",
                    )
                    target_digest = (
                        completed.record_object.digest
                        if target == "record"
                        else completed.record.state_object_digest
                    )
                    admitted = storage.journal.connection.execute(
                        "SELECT digest, kind, byte_length, first_seen_at_ms "
                        "FROM object_refs WHERE digest = ?",
                        (target_digest,),
                    ).fetchone()
                    assert admitted is not None
                    edges = storage.journal.connection.execute(
                        "SELECT event_id, role FROM event_object_refs "
                        "WHERE digest = ? ORDER BY event_id, role",
                        (target_digest,),
                    ).fetchall()
                    self.assertGreater(len(edges), 0)
                    before = storage.read_task_event(TASK_ID)
                    storage.journal.connection.execute(
                        "DELETE FROM event_object_refs WHERE digest = ?",
                        (target_digest,),
                    )
                    storage.journal.connection.execute(
                        "DELETE FROM object_refs WHERE digest = ?",
                        (target_digest,),
                    )

                    with self.assertRaisesRegex(
                        HarnessLifecycleError,
                        "Provider Call",
                    ):
                        record_native_run_result(
                            host,
                            committed,
                            result,
                            times=NativeRunTimes(100_100, 100_110),
                        )

                    after = storage.read_task_event(TASK_ID)
                    self.assertEqual(
                        after.projection.revision,
                        before.projection.revision,
                    )
                    self.assertEqual(
                        after.data["activeHarnessProviderCallDigest"],
                        completed.record.digest,
                    )
                    self.assertEqual(
                        after.data["activeHarnessProviderCallStatus"],
                        "completed",
                    )
                    _assert_no_recorded_run(self, storage)

                    storage.journal.connection.execute(
                        "INSERT INTO object_refs("
                        "digest, kind, byte_length, first_seen_at_ms"
                        ") VALUES (?, ?, ?, ?)",
                        (
                            admitted["digest"],
                            admitted["kind"],
                            admitted["byte_length"],
                            admitted["first_seen_at_ms"],
                        ),
                    )
                    storage.journal.connection.executemany(
                        "INSERT INTO event_object_refs(event_id, digest, role) "
                        "VALUES (?, ?, ?)",
                        (
                            (edge["event_id"], target_digest, edge["role"])
                            for edge in edges
                        ),
                    )
                    validate_history(storage)

    def test_active_tool_intent_blocks_run_recording_without_clearing_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _RecoveryRuntime()
                host, committed, context_digest, _ = _assign(
                    storage,
                    clock,
                    runtime,
                )
                store = HostHarnessRunStore(host, committed)
                store.bind_state(_provider_state())
                intent = _tool_intent(store, suffix="active")
                store.prepare_tool_step(intent)
                committed = store.committed
                result = _conclusion_result(
                    committed,
                    context_digest,
                    suffix="active-tool-intent",
                )
                before = storage.read_task_event(TASK_ID)

                with self.assertRaisesRegex(
                    HarnessLifecycleError,
                    "active Harness Tool Step",
                ):
                    record_native_run_result(
                        host,
                        committed,
                        result,
                        times=NativeRunTimes(100_100, 100_110),
                    )

                after = storage.read_task_event(TASK_ID)
                self.assertEqual(after.projection.revision, before.projection.revision)
                self.assertEqual(
                    after.data["activeHarnessToolStepIntentDigest"],
                    intent.digest,
                )
                _assert_no_recorded_run(self, storage)
                validate_history(storage)

    def test_terminal_tool_receipt_requires_its_observation_in_this_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                runtime = _RecoveryRuntime()
                host, committed, context_digest, _ = _assign(
                    storage,
                    clock,
                    runtime,
                )
                store = HostHarnessRunStore(host, committed)
                store.bind_state(_provider_state())
                intent = _tool_intent(store, suffix="terminal")
                store.prepare_tool_step(intent)
                observation = ToolObservation(
                    tool_call_id=intent.tool_call_id,
                    tool_name=intent.tool_name,
                    status="observed",
                    structured_content={
                        "relativePath": "README.md",
                        "content": "# Ordivon Host\n",
                        "digest": canonical_digest("# Ordivon Host\n"),
                    },
                )
                receipt = HarnessToolStepReceipt(
                    receipt_id="harness-tool-step-receipt:run-recording:terminal",
                    intent_digest=intent.digest,
                    harness_run_id=intent.harness_run_id,
                    tool_call_id=intent.tool_call_id,
                    status=HarnessToolStepStatus.OBSERVED,
                    runtime_job_ref=None,
                    observation_digest=observation.digest,
                    reconciled=False,
                    created_at_ms=100_020,
                )
                store.record_tool_step_receipt(receipt, observation.to_dict())
                committed = store.committed
                base_result = _conclusion_result(
                    committed,
                    context_digest,
                    suffix="terminal-tool-receipt",
                )
                unrelated = ToolObservation(
                    tool_call_id="tool-call:run-recording:unrelated",
                    tool_name="read_workspace",
                    status="observed",
                    structured_content={"relativePath": "OTHER.md", "content": "other"},
                )
                unrelated_result = replace(
                    base_result,
                    observations=(unrelated,),
                    tool_calls=1,
                )
                before = storage.read_task_event(TASK_ID)

                with self.assertRaisesRegex(
                    HarnessLifecycleError,
                    "Tool Step Observation",
                ):
                    record_native_run_result(
                        host,
                        committed,
                        unrelated_result,
                        times=NativeRunTimes(100_100, 100_110),
                    )

                rejected = storage.read_task_event(TASK_ID)
                self.assertEqual(
                    rejected.projection.revision,
                    before.projection.revision,
                )
                self.assertEqual(
                    rejected.data["harnessToolStepReceiptDigest"],
                    receipt.digest,
                )
                self.assertNotIn("activeHarnessToolStepIntentDigest", rejected.data)
                _assert_no_recorded_run(self, storage)

                included_result = replace(
                    base_result,
                    observations=(observation,),
                    tool_calls=1,
                )
                recorded = record_native_run_result(
                    host,
                    committed,
                    included_result,
                    times=NativeRunTimes(100_100, 100_110),
                )

                self.assertEqual(len(recorded.observation_objects), 1)
                self.assertEqual(
                    storage.objects.get(
                        recorded.observation_objects[0].digest,
                        expected_kind="harness-tool-observation",
                    ),
                    observation.to_dict(),
                )
                self.assertEqual(
                    host.load_current_run(TASK_ID).receipt.digest,
                    recorded.receipt.digest,
                )
                validate_history(storage)


if __name__ == "__main__":
    unittest.main()

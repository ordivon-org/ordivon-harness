from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace

from anc_canonical import canonical_digest
from ordivon_host import EventKind, HostKernel, HostStorage, TaskState
from ordivon_host.journal import JournalCorruption
from test_ordivon_harness_oh5 import (
    _RecoveryRuntime,
    _assign,
    _conclusion_result,
    _create_task,
)
from test_provider_call_history import _claim
from test_provider_call_recovery import (
    _MutableClock,
    _provider_result,
    _provider_state,
)
from test_run_recording_active_state import _tool_intent

from ordivon_harness.event_kinds import (
    HARNESS_RUN_RECORDED,
    HARNESS_RUN_SNAPSHOT_RECORDED,
    HARNESS_TOOL_STEP_PREPARED,
    HARNESS_TOOL_STEP_RECORDED,
)
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import (
    HostHarnessRunStore,
    NativeRunTimes,
    ToolObservation,
    record_native_run_result,
)
from ordivon_harness.protocol import (
    HarnessRunPauseReason,
    HarnessToolStepReceipt,
    HarnessToolStepStatus,
)


def _event_data(storage: HostStorage, event_kind: EventKind) -> tuple[object, dict]:
    row = storage.journal.connection.execute(
        "SELECT sequence, event_id, payload_digest, recorded_at_ms FROM events "
        "WHERE event_kind = ? ORDER BY sequence DESC LIMIT 1",
        (event_kind.value,),
    ).fetchone()
    assert row is not None
    payload = storage.objects.get(
        row["payload_digest"], expected_kind="host-event-payload"
    )
    assert isinstance(payload, dict)
    data = payload["data"]
    assert isinstance(data, dict)
    return row, data


def _move_reference_to_later_same_ms_event(
    storage: HostStorage,
    *,
    source_event_id: str,
    source_sequence: int,
    recorded_at_ms: int,
    digest: str,
    suffix: str,
) -> None:
    changed = storage.journal.connection.execute(
        "DELETE FROM event_object_refs WHERE event_id = ? AND digest = ? "
        "AND role = 'reference'",
        (source_event_id, digest),
    ).rowcount
    if changed != 1:
        raise AssertionError(f"missing source reference edge: {suffix}")
    HostKernel(
        storage,
        clock_ms=lambda: recorded_at_ms,
        owner_id=f"host:causal-admission:{suffix}",
    ).create_task(
        event_id=f"event:causal-admission:{suffix}:later",
        kind=EventKind.TASK_CREATED,
        task_id=f"task:causal-admission:{suffix}:later",
        goal_id="goal:causal-admission",
        payload={"workloadId": f"causal-admission-{suffix}"},
        state=TaskState.READY,
        frontier=(f"node:causal-admission:{suffix}",),
        referenced_objects=(storage.objects.inspect(digest),),
    )
    later = storage.journal.connection.execute(
        "SELECT sequence, recorded_at_ms FROM events WHERE event_id = ?",
        (f"event:causal-admission:{suffix}:later",),
    ).fetchone()
    assert later is not None
    if int(later["sequence"]) <= source_sequence:
        raise AssertionError("later admission did not advance Journal sequence")
    if int(later["recorded_at_ms"]) != recorded_at_ms:
        raise AssertionError("later admission did not preserve the same millisecond")


class CausalHistoryAdmissionTests(unittest.TestCase):
    def _prepare_tool_step(self, storage: HostStorage, clock: _MutableClock):
        _create_task(storage, clock)
        host, committed, context_digest, _ = _assign(
            storage, clock, _RecoveryRuntime()
        )
        store = HostHarnessRunStore(host, committed)
        store.bind_state(_provider_state())
        intent = _tool_intent(store, suffix="causal-admission")
        store.prepare_tool_step(intent)
        return host, store, intent, context_digest

    def test_tool_prepare_evidence_cannot_be_forward_admitted(self) -> None:
        targets = (
            ("harnessToolStepIntentObjectDigest", "Tool Intent"),
            ("harnessDispatchFenceObjectDigest", "Dispatch Fence"),
            ("harnessRunSnapshotObjectDigest", "Run Snapshot"),
            ("harnessRunStateObjectDigest", "Run state"),
        )
        for key, label in targets:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    self._prepare_tool_step(storage, clock)
                    row, data = _event_data(storage, HARNESS_TOOL_STEP_PREPARED)
                    digest = data[key]
                    assert isinstance(digest, str)
                    _move_reference_to_later_same_ms_event(
                        storage,
                        source_event_id=str(row["event_id"]),
                        source_sequence=int(row["sequence"]),
                        recorded_at_ms=int(row["recorded_at_ms"]),
                        digest=digest,
                        suffix=f"tool-prepare-{key}",
                    )
                    with self.assertRaisesRegex(
                        JournalCorruption, rf"historical {label} is not admitted by its Event"
                    ):
                        validate_history(storage)

    def test_tool_receipt_evidence_cannot_be_forward_admitted(self) -> None:
        targets = (
            ("harnessToolStepReceiptObjectDigest", "Tool Receipt"),
            ("harnessToolStepObservationObjectDigest", "Tool Observation"),
        )
        for key, label in targets:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    _, store, intent, _ = self._prepare_tool_step(storage, clock)
                    observation = ToolObservation(
                        tool_call_id=intent.tool_call_id,
                        tool_name=intent.tool_name,
                        status="observed",
                        structured_content={
                            "relativePath": "README.md",
                            "content": "# causal admission\n",
                            "digest": canonical_digest("# causal admission\n"),
                        },
                    )
                    receipt = HarnessToolStepReceipt(
                        receipt_id="harness-tool-step-receipt:causal-admission",
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
                    row, data = _event_data(storage, HARNESS_TOOL_STEP_RECORDED)
                    digest = data[key]
                    assert isinstance(digest, str)
                    _move_reference_to_later_same_ms_event(
                        storage,
                        source_event_id=str(row["event_id"]),
                        source_sequence=int(row["sequence"]),
                        recorded_at_ms=int(row["recorded_at_ms"]),
                        digest=digest,
                        suffix=f"tool-receipt-{key}",
                    )
                    with self.assertRaisesRegex(
                        JournalCorruption, rf"historical {label} is not admitted by its Event"
                    ):
                        validate_history(storage)

    def test_snapshot_evidence_cannot_be_forward_admitted(self) -> None:
        targets = (
            ("harnessRunSnapshotObjectDigest", "Run Snapshot"),
            ("harnessRunStateObjectDigest", "Run state"),
        )
        for key, label in targets:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    _create_task(storage, clock)
                    host, committed, _, _ = _assign(
                        storage, clock, _RecoveryRuntime()
                    )
                    store = HostHarnessRunStore(host, committed)
                    store.bind_state(_provider_state())
                    store.record_pause(HarnessRunPauseReason.NEEDS_INPUT)
                    row, data = _event_data(storage, HARNESS_RUN_SNAPSHOT_RECORDED)
                    digest = data[key]
                    assert isinstance(digest, str)
                    _move_reference_to_later_same_ms_event(
                        storage,
                        source_event_id=str(row["event_id"]),
                        source_sequence=int(row["sequence"]),
                        recorded_at_ms=int(row["recorded_at_ms"]),
                        digest=digest,
                        suffix=f"snapshot-{key}",
                    )
                    with self.assertRaisesRegex(
                        JournalCorruption, rf"historical {label} is not admitted by its Event"
                    ):
                        validate_history(storage)

    def test_run_evidence_cannot_be_forward_admitted(self) -> None:
        targets = (
            ("harnessRunObjectDigest", "Run Receipt"),
            ("harnessTraceObjectDigest", "Run Trace"),
            ("runConclusionObjectDigest", "Run Conclusion"),
        )
        for key, label in targets:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                clock = _MutableClock()
                with HostStorage(directory) as storage:
                    _create_task(storage, clock)
                    host, committed, context_digest, _ = _assign(
                        storage, clock, _RecoveryRuntime()
                    )
                    result = _conclusion_result(
                        committed,
                        context_digest,
                        suffix=f"causal-admission-{key}",
                    )
                    record_native_run_result(
                        host,
                        committed,
                        result,
                        times=NativeRunTimes(100_100, 100_110),
                    )
                    row, data = _event_data(storage, HARNESS_RUN_RECORDED)
                    digest = data[key]
                    assert isinstance(digest, str)
                    _move_reference_to_later_same_ms_event(
                        storage,
                        source_event_id=str(row["event_id"]),
                        source_sequence=int(row["sequence"]),
                        recorded_at_ms=int(row["recorded_at_ms"]),
                        digest=digest,
                        suffix=f"run-{key}",
                    )
                    with self.assertRaisesRegex(
                        JournalCorruption, rf"historical {label} is not admitted by its Event"
                    ):
                        validate_history(storage)

    def test_run_observation_cannot_be_forward_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                host, store, intent, context_digest = self._prepare_tool_step(
                    storage, clock
                )
                observation = ToolObservation(
                    tool_call_id=intent.tool_call_id,
                    tool_name=intent.tool_name,
                    status="observed",
                    structured_content={
                        "relativePath": "README.md",
                        "content": "# run observation causal admission\n",
                        "digest": canonical_digest(
                            "# run observation causal admission\n"
                        ),
                    },
                )
                receipt = HarnessToolStepReceipt(
                    receipt_id=(
                        "harness-tool-step-receipt:causal-admission:run"
                    ),
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
                base = _conclusion_result(
                    committed,
                    context_digest,
                    suffix="causal-admission-run-observation",
                )
                result = replace(
                    base, observations=(observation,), tool_calls=1
                )
                record_native_run_result(
                    host,
                    committed,
                    result,
                    times=NativeRunTimes(100_100, 100_110),
                )
                row, data = _event_data(storage, HARNESS_RUN_RECORDED)
                observations = data["toolObservationObjectDigests"]
                assert isinstance(observations, list)
                digest = observations[0]
                assert isinstance(digest, str)
                _move_reference_to_later_same_ms_event(
                    storage,
                    source_event_id=str(row["event_id"]),
                    source_sequence=int(row["sequence"]),
                    recorded_at_ms=int(row["recorded_at_ms"]),
                    digest=digest,
                    suffix="run-observation",
                )
                with self.assertRaisesRegex(
                    JournalCorruption,
                    "historical Run Observation 0 is not admitted by its Event",
                ):
                    validate_history(storage)

    def test_migrated_v3_history_uses_explicit_legacy_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = _MutableClock()
            with HostStorage(directory) as storage:
                _create_task(storage, clock)
                _, store, _, _, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                store.complete_provider_call(dispatching, _provider_result())
                event_count = storage.journal.event_count()

            database = f"{directory}/host.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DROP TABLE event_object_refs")
            connection.execute("DROP TABLE legacy_object_refs")
            connection.execute(
                "DELETE FROM host_metadata "
                "WHERE key = 'event_object_refs_start_sequence'"
            )
            connection.execute(
                "UPDATE host_metadata SET value = '3' "
                "WHERE key = 'schema_version'"
            )
            connection.execute(
                "DELETE FROM schema_migrations WHERE to_version = 4"
            )
            connection.commit()
            connection.close()

            with HostStorage(directory) as storage:
                self.assertEqual(
                    storage.journal.event_object_refs_start_sequence(),
                    event_count + 1,
                )
                self.assertGreater(len(storage.journal.legacy_object_refs()), 0)
                self.assertEqual(validate_history(storage).events, event_count)


if __name__ == "__main__":
    unittest.main()

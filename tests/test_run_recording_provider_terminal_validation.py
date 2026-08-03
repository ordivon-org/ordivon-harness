from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ordivon_host import HostExtensionPort, HostStorage
from ordivon_host.objects import ObjectCorrupt, ObjectMissing
from test_ordivon_harness_oh5 import TASK_ID, _conclusion_result, _create_task
from test_provider_call_history import _append_provider_record, _claim
from test_provider_call_recovery import (
    _MutableClock,
    _provider_failure,
    _provider_result,
)

from ordivon_harness import HarnessLifecycleError
from ordivon_harness.event_kinds import (
    HARNESS_PROVIDER_CALL_FAILED,
    HARNESS_PROVIDER_CALL_UNKNOWN,
)
from ordivon_harness.history import validate_history
from ordivon_harness.ordivon import NativeRunTimes, record_native_run_result
from ordivon_harness.protocol import HarnessProviderCallStatus


class RunRecordingProviderTerminalValidationTests(unittest.TestCase):
    def _prepare_terminal(self, storage: HostStorage, status: str):
        clock = _MutableClock()
        _create_task(storage, clock)
        host, store, _, _, claimed = _claim(storage, clock)
        dispatching = store.mark_provider_call_dispatching(claimed)
        if status == "completed":
            outcome = _provider_result()
            terminal = store.complete_provider_call(dispatching, outcome)
            outcome_digest = terminal.record.result_object_digest
        else:
            safety = (
                "provider_rejected"
                if status == "failed"
                else "dispatch_ambiguous"
            )
            outcome = _provider_failure(dispatching, dispatch_safety=safety)
            terminal = store.fail_provider_call(dispatching, failure=outcome)
            outcome_digest = terminal.record.failure_object_digest
        assert outcome_digest is not None
        committed = store.committed
        result = _conclusion_result(
            committed,
            committed.assignment.context_object_digest,
            suffix=f"terminal-validation-{status}",
        )
        return host, committed, terminal, outcome, outcome_digest, result

    def _assert_rejected_without_state_change(
        self,
        storage: HostStorage,
        directory: str,
        *,
        host,
        committed,
        terminal,
        result,
        pattern: str,
    ) -> None:
        before = storage.read_task_event(TASK_ID)
        object_count = len(tuple((Path(directory) / "objects").glob("*.json")))
        with self.assertRaisesRegex(HarnessLifecycleError, pattern):
            record_native_run_result(
                host,
                committed,
                result,
                times=NativeRunTimes(100_100, 100_110),
            )
        after = storage.read_task_event(TASK_ID)
        self.assertEqual(after, before)
        self.assertEqual(
            after.data["activeHarnessProviderCallDigest"],
            terminal.record.digest,
        )
        self.assertEqual(
            after.data["activeHarnessProviderCallObjectDigest"],
            terminal.record_object.digest,
        )
        self.assertEqual(
            after.data["activeHarnessProviderCallStatus"],
            terminal.record.status.value,
        )
        self.assertNotIn("harnessRunObjectDigest", after.data)
        self.assertEqual(
            len(tuple((Path(directory) / "objects").glob("*.json"))),
            object_count,
        )

    def test_missing_wrong_kind_and_malformed_outcomes_preserve_head(self) -> None:
        for status in ("completed", "failed", "unknown"):
            for fault in ("missing", "wrong-kind", "malformed"):
                with (
                    self.subTest(status=status, fault=fault),
                    tempfile.TemporaryDirectory() as directory,
                    HostStorage(directory) as storage,
                ):
                    (
                        host,
                        committed,
                        terminal,
                        _,
                        outcome_digest,
                        result,
                    ) = self._prepare_terminal(storage, status)
                    original_get = storage.objects.get

                    def faulted_get(digest, *, expected_kind=None):
                        if digest != outcome_digest:
                            return original_get(digest, expected_kind=expected_kind)
                        if fault == "missing":
                            raise ObjectMissing("injected missing terminal outcome")
                        if fault == "wrong-kind":
                            raise ObjectCorrupt("injected wrong terminal outcome kind")
                        return {"schemaVersion": 1, "kind": "malformed"}

                    with patch.object(
                        storage.objects, "get", side_effect=faulted_get
                    ):
                        self._assert_rejected_without_state_change(
                            storage,
                            directory,
                            host=host,
                            committed=committed,
                            terminal=terminal,
                            result=result,
                            pattern=(
                                "malformed active Provider Call terminal outcome"
                            ),
                        )
                    validate_history(storage)

    def test_semantically_mismatched_outcomes_preserve_head(self) -> None:
        for status in ("completed", "failed", "unknown"):
            with (
                self.subTest(status=status),
                tempfile.TemporaryDirectory() as directory,
                HostStorage(directory) as storage,
            ):
                (
                    host,
                    committed,
                    terminal,
                    outcome,
                    outcome_digest,
                    result,
                ) = self._prepare_terminal(storage, status)
                original_get = storage.objects.get
                if status == "completed":
                    drifted = replace(
                        outcome,
                        model_call_id=(
                            "model-call:run-recording:terminal-mismatch"
                        ),
                    )
                else:
                    drifted = replace(
                        outcome,
                        provider_call_id=(
                            "provider-call:run-recording:terminal-mismatch"
                        ),
                    )

                def mismatched_get(digest, *, expected_kind=None):
                    if digest == outcome_digest:
                        return drifted.to_dict()
                    return original_get(digest, expected_kind=expected_kind)

                with patch.object(
                    storage.objects, "get", side_effect=mismatched_get
                ):
                    self._assert_rejected_without_state_change(
                        storage,
                        directory,
                        host=host,
                        committed=committed,
                        terminal=terminal,
                        result=result,
                        pattern="terminal outcome differs from its record",
                    )
                validate_history(storage)

    def test_terminal_outcome_must_belong_to_its_provider_event(self) -> None:
        for status in ("completed", "failed", "unknown"):
            with (
                self.subTest(status=status),
                tempfile.TemporaryDirectory() as directory,
                HostStorage(directory) as storage,
            ):
                (
                    host,
                    committed,
                    terminal,
                    _,
                    outcome_digest,
                    result,
                ) = self._prepare_terminal(storage, status)
                row = storage.journal.connection.execute(
                    "SELECT e.event_id FROM events e "
                    "JOIN event_object_refs r ON r.event_id = e.event_id "
                    "WHERE e.stream_id = ? AND r.digest = ? "
                    "AND r.role = 'reference' AND e.event_kind = ?",
                    (
                        TASK_ID,
                        terminal.record_object.digest,
                        f"harness.provider-call-{status}",
                    ),
                ).fetchone()
                assert row is not None
                event_id = str(row["event_id"])
                self.assertEqual(
                    storage.journal.connection.execute(
                        "DELETE FROM event_object_refs "
                        "WHERE event_id = ? AND digest = ? AND role = 'reference'",
                        (event_id, outcome_digest),
                    ).rowcount,
                    1,
                )
                self.assertIn(
                    outcome_digest,
                    {item.digest for item in storage.journal.object_refs()},
                )
                self._assert_rejected_without_state_change(
                    storage,
                    directory,
                    host=host,
                    committed=committed,
                    terminal=terminal,
                    result=result,
                    pattern=(
                        "terminal Provider lifecycle Event did not admit its "
                        "terminal outcome"
                    ),
                )
                storage.journal.connection.execute(
                    "INSERT INTO event_object_refs(event_id, digest, role) "
                    "VALUES (?, ?, 'reference')",
                    (event_id, outcome_digest),
                )
                validate_history(storage)

    def test_failure_dispatch_safety_must_match_terminal_status(self) -> None:
        cases = (
            (
                HarnessProviderCallStatus.FAILED,
                "dispatch_ambiguous",
                HARNESS_PROVIDER_CALL_FAILED,
            ),
            (
                HarnessProviderCallStatus.UNKNOWN,
                "provider_rejected",
                HARNESS_PROVIDER_CALL_UNKNOWN,
            ),
        )
        for status, dispatch_safety, event_kind in cases:
            with (
                self.subTest(status=status.value),
                tempfile.TemporaryDirectory() as directory,
                HostStorage(directory) as storage,
            ):
                clock = _MutableClock()
                _create_task(storage, clock)
                host, store, _, _, claimed = _claim(storage, clock)
                dispatching = store.mark_provider_call_dispatching(claimed)
                failure = _provider_failure(
                    dispatching,
                    dispatch_safety=dispatch_safety,
                )
                extension = HostExtensionPort(storage, host.kernel)
                failure_object = extension.put_object(
                    failure.to_dict(), kind="harness-provider-call-failure"
                )
                record = replace(
                    dispatching.record,
                    record_id=(
                        "harness-provider-call-record:run-recording:"
                        f"dispatch-safety-{status.value}"
                    ),
                    status=status,
                    result_digest=None,
                    result_object_digest=None,
                    failure_digest=failure.digest,
                    failure_object_digest=failure_object.digest,
                    previous_record_digest=dispatching.record.digest,
                    recorded_at_ms=dispatching.record.recorded_at_ms + 1,
                )
                record_object = _append_provider_record(
                    storage,
                    host,
                    record,
                    event_kind=event_kind,
                    referenced_objects=(
                        storage.objects.inspect(record.state_object_digest),
                        failure_object,
                    ),
                )
                committed = host.load_current_assignment(TASK_ID)
                result = _conclusion_result(
                    committed,
                    committed.assignment.context_object_digest,
                    suffix=f"dispatch-safety-{status.value}",
                )
                terminal = replace(
                    dispatching,
                    record=record,
                    record_object=record_object,
                    failure=failure,
                    failure_object=failure_object,
                )
                self._assert_rejected_without_state_change(
                    storage,
                    directory,
                    host=host,
                    committed=committed,
                    terminal=terminal,
                    result=result,
                    pattern="terminal outcome differs from its record",
                )

    def test_migrated_terminal_provider_history_remains_recordable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                (
                    _,
                    committed,
                    terminal,
                    _,
                    _,
                    result,
                ) = self._prepare_terminal(storage, "completed")
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
                from ordivon_harness import HarnessHost

                host = HarnessHost(storage, clock_ms=lambda: 200_000)
                reloaded = host.load_current_assignment(TASK_ID)
                self.assertEqual(reloaded.assignment, committed.assignment)
                self.assertEqual(
                    storage.journal.event_object_refs_start_sequence(),
                    event_count + 1,
                )
                legacy = {
                    item.digest for item in storage.journal.legacy_object_refs()
                }
                self.assertTrue(
                    {
                        terminal.record_object.digest,
                        terminal.record.state_object_digest,
                        terminal.record.result_object_digest,
                    }.issubset(legacy)
                )
                recorded = record_native_run_result(
                    host,
                    reloaded,
                    result,
                    times=NativeRunTimes(100_100, 100_110),
                )
                self.assertEqual(
                    host.load_current_run(TASK_ID).receipt.digest,
                    recorded.receipt.digest,
                )
                validate_history(storage)


if __name__ == "__main__":
    unittest.main()

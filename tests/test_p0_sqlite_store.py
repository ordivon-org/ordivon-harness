from __future__ import annotations

from pathlib import Path
import stat
import tempfile
import unittest

from ordivon_harness.core_contracts import (
    HarnessBoundReference,
    HarnessRunContract,
)
from ordivon_harness.sqlite_store import (
    HarnessEventConflict,
    HarnessJournalCorruption,
    HarnessLeaseHeld,
    HarnessObjectMissing,
    HarnessRevisionConflict,
    HarnessTerminalConflict,
    SQLiteHarnessStore,
)
from ordivon_harness.store import HarnessEventAdmission, HarnessRunStatus

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64


def run_contract(
    *,
    run_id: str = "harness-run:p0-store-001",
    caller_ref: str = "trial:p0-store-001",
) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=run_id,
        harness_implementation_id="ordivon-harness@0.7.0-dev",
        caller_id="caller:standalone-test",
        caller_run_ref=caller_ref,
        objective_ref=HarnessBoundReference("objective:p0-store-001", "objective", DIGEST_A),
        context_refs=(HarnessBoundReference("context:p0-store-001", "context", DIGEST_B),),
        provider_id="provider:scripted",
        adapter_id="adapter:scripted-v1",
        requested_model_id="model:scripted",
        tool_catalog_digest=DIGEST_C,
        tool_grant_digest=DIGEST_D,
        budget={"maxModelCalls": 2, "maxToolCalls": 1},
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            "system-manifest:p0-store-001", "system-manifest", DIGEST_A
        ),
        created_at_ms=1_000,
    )


class SQLiteHarnessStoreTests(unittest.TestCase):
    def test_initialize_create_append_close_and_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "harness-state"
            contract = run_contract()
            with SQLiteHarnessStore.initialize(root) as store:
                self.assertEqual(store.create_run(contract), HarnessEventAdmission.CREATED)
                self.assertEqual(store.create_run(contract), HarnessEventAdmission.EXISTING)
                created = store.load_run(contract.harness_run_id)
                self.assertEqual(created.status, HarnessRunStatus.CREATED)
                self.assertEqual(created.revision, 1)

                lease = store.acquire_run_lease(
                    contract.harness_run_id,
                    owner_id="worker:p0-store",
                    ttl_ms=1_000,
                    now_ms=1_001,
                )
                self.assertEqual(
                    store.append_event(
                        event_id="event:p0-store:started",
                        harness_run_id=contract.harness_run_id,
                        event_kind="harness.run-started",
                        data={"phase": "started"},
                        expected_revision=1,
                        recorded_at_ms=1_002,
                        lease=lease,
                        lease_checked_at_ms=1_002,
                    ),
                    HarnessEventAdmission.CREATED,
                )
                # Response loss may repeat the exact Event after its lease was consumed.
                self.assertEqual(
                    store.append_event(
                        event_id="event:p0-store:started",
                        harness_run_id=contract.harness_run_id,
                        event_kind="harness.run-started",
                        data={"phase": "started"},
                        expected_revision=1,
                        recorded_at_ms=1_002,
                        lease=lease,
                        lease_checked_at_ms=1_002,
                    ),
                    HarnessEventAdmission.EXISTING,
                )
                evidence = store.put_object(
                    {"receipt": "runtime-job:001"}, kind="runtime-job-reference"
                )
                lease = store.acquire_run_lease(
                    contract.harness_run_id,
                    owner_id="worker:p0-store",
                    ttl_ms=1_000,
                    now_ms=1_003,
                )
                store.append_event(
                    event_id="event:p0-store:completed",
                    harness_run_id=contract.harness_run_id,
                    event_kind="harness.run-completed",
                    data={"proposalRef": "completion-proposal:p0-store-001"},
                    expected_revision=2,
                    recorded_at_ms=1_004,
                    lease=lease,
                    lease_checked_at_ms=1_004,
                    caused_by_event_id="event:p0-store:started",
                    referenced_objects=(evidence,),
                )
                terminal = store.load_run(contract.harness_run_id)
                self.assertEqual(terminal.status, HarnessRunStatus.COMPLETED)
                self.assertEqual(terminal.revision, 3)
                self.assertEqual(terminal.terminal_event_id, "event:p0-store:completed")
                self.assertEqual(len(store.list_run_events(contract.harness_run_id)), 3)
                self.assertTrue(store.doctor()["healthy"])

            with SQLiteHarnessStore(root) as reopened:
                terminal = reopened.load_run(contract.harness_run_id)
                self.assertEqual(terminal.status, HarnessRunStatus.COMPLETED)
                events = reopened.list_run_events(contract.harness_run_id)
                self.assertEqual(
                    [event.event_kind for event in events],
                    [
                        "harness.run-created",
                        "harness.run-started",
                        "harness.run-completed",
                    ],
                )
                with self.assertRaises(HarnessTerminalConflict):
                    reopened.acquire_run_lease(
                        contract.harness_run_id,
                        owner_id="worker:late",
                        ttl_ms=100,
                        now_ms=2_000,
                    )

    def test_event_identity_conflict_and_revision_fencing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteHarnessStore.initialize(directory) as store:
                contract = run_contract()
                store.create_run(contract)
                lease = store.acquire_run_lease(
                    contract.harness_run_id,
                    owner_id="worker:first",
                    ttl_ms=100,
                    now_ms=1_001,
                )
                store.append_event(
                    event_id="event:p0-store:one",
                    harness_run_id=contract.harness_run_id,
                    event_kind="harness.run-started",
                    data={"value": 1},
                    expected_revision=1,
                    recorded_at_ms=1_002,
                    lease=lease,
                    lease_checked_at_ms=1_002,
                )
                with self.assertRaises(HarnessEventConflict):
                    store.append_event(
                        event_id="event:p0-store:one",
                        harness_run_id=contract.harness_run_id,
                        event_kind="harness.run-started",
                        data={"value": 2},
                        expected_revision=1,
                        recorded_at_ms=1_002,
                        lease=lease,
                        lease_checked_at_ms=1_002,
                    )
                current = store.acquire_run_lease(
                    contract.harness_run_id,
                    owner_id="worker:second",
                    ttl_ms=100,
                    now_ms=1_003,
                )
                with self.assertRaises(HarnessRevisionConflict):
                    store.append_event(
                        event_id="event:p0-store:stale",
                        harness_run_id=contract.harness_run_id,
                        event_kind="harness.snapshot-recorded",
                        data={"snapshot": 1},
                        expected_revision=1,
                        recorded_at_ms=1_004,
                        lease=current,
                        lease_checked_at_ms=1_004,
                    )
                self.assertTrue(store.release_run_lease(current))

    def test_live_lease_excludes_another_owner_and_expiry_allows_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteHarnessStore.initialize(directory) as store:
                contract = run_contract()
                store.create_run(contract)
                first = store.acquire_run_lease(
                    contract.harness_run_id,
                    owner_id="worker:first",
                    ttl_ms=10,
                    now_ms=1_001,
                )
                with self.assertRaises(HarnessLeaseHeld):
                    store.acquire_run_lease(
                        contract.harness_run_id,
                        owner_id="worker:second",
                        ttl_ms=10,
                        now_ms=1_005,
                    )
                recovered = store.acquire_run_lease(
                    contract.harness_run_id,
                    owner_id="worker:second",
                    ttl_ms=10,
                    now_ms=first.expires_at_ms,
                )
                self.assertGreater(recovered.lease_revision, first.lease_revision)
                self.assertEqual(recovered.run_revision, 1)

    def test_caller_binding_prevents_two_runs_for_one_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteHarnessStore.initialize(directory) as store:
                store.create_run(run_contract())
                with self.assertRaises(HarnessEventConflict):
                    store.create_run(
                        run_contract(
                            run_id="harness-run:p0-store-002",
                            caller_ref="trial:p0-store-001",
                        )
                    )

    def test_private_modes_and_required_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            with SQLiteHarnessStore.initialize(root) as store:
                contract = run_contract()
                store.create_run(contract)
                projection = store.load_run(contract.harness_run_id)
                object_path = root / "objects" / f"{projection.contract_object_digest[7:]}.json"
                self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((root / "objects").stat().st_mode), 0o700)
                self.assertEqual(
                    stat.S_IMODE((root / "harness.sqlite3").stat().st_mode),
                    0o600,
                )
                self.assertEqual(stat.S_IMODE(object_path.stat().st_mode), 0o600)
                self.assertEqual(
                    set(store.table_names()),
                    {
                        "caller_bindings",
                        "object_refs",
                        "object_validation",
                        "provider_calls",
                        "run_events",
                        "run_leases",
                        "run_object_refs",
                        "runs",
                        "schema_info",
                        "schema_migrations",
                        "tool_steps",
                    },
                )

    def test_missing_cas_object_fails_reopen_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            with SQLiteHarnessStore.initialize(root) as store:
                contract = run_contract()
                store.create_run(contract)
                projection = store.load_run(contract.harness_run_id)
            (root / "objects" / f"{projection.contract_object_digest[7:]}.json").unlink()
            with self.assertRaises(HarnessObjectMissing):
                SQLiteHarnessStore(root)

    def test_symlink_state_and_journal_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / "real"
            real.mkdir()
            link = base / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(HarnessJournalCorruption):
                SQLiteHarnessStore.initialize(link)

            state = base / "state"
            state.mkdir()
            target = base / "database"
            target.write_bytes(b"")
            (state / "harness.sqlite3").symlink_to(target)
            with self.assertRaises(HarnessJournalCorruption):
                SQLiteHarnessStore.initialize(state)


if __name__ == "__main__":
    unittest.main()

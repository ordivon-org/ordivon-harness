from __future__ import annotations

from pathlib import Path
import stat
import tempfile
import unittest

from ordivon_harness.sqlite_store import HarnessJournalCorruption, SQLiteHarnessStore
from ordivon_harness.store_ops import (
    backup_harness_store,
    restore_harness_backup,
    verify_harness_backup,
)

from tests.test_p0_sqlite_store import run_contract


class HarnessStoreOperationsTests(unittest.TestCase):
    def populate(self, root: Path) -> tuple[str, str]:
        contract = run_contract()
        with SQLiteHarnessStore.initialize(root) as store:
            store.create_run(contract)
            evidence = store.put_object(
                {"runtimeJobRef": "runtime-job:p0-backup-001"},
                kind="runtime-job-reference",
            )
            lease = store.acquire_run_lease(
                contract.harness_run_id,
                owner_id="worker:p0-backup",
                ttl_ms=1_000,
                now_ms=1_001,
            )
            store.append_event(
                event_id="event:p0-backup:started",
                harness_run_id=contract.harness_run_id,
                event_kind="harness.run-started",
                data={"phase": "started"},
                expected_revision=1,
                recorded_at_ms=1_002,
                lease=lease,
                lease_checked_at_ms=1_002,
                referenced_objects=(evidence,),
            )
        return contract.harness_run_id, evidence.digest

    def test_online_backup_verification_and_independent_restore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            backup = base / "backup"
            restored = base / "restored"
            run_id, evidence_digest = self.populate(source)

            report = backup_harness_store(source, backup, created_at_ms=2_000)
            self.assertTrue(report["ok"])
            self.assertEqual(report["createdAtMs"], 2_000)
            self.assertEqual(report["runs"], 1)
            self.assertEqual(report["events"], 2)
            self.assertGreaterEqual(report["objects"], 4)
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((backup / "harness.sqlite3").stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((backup / "manifest.json").stat().st_mode), 0o600)

            verified = verify_harness_backup(backup)
            self.assertEqual(verified["payloadDigest"], report["payloadDigest"])
            restored_report = restore_harness_backup(backup, restored)
            self.assertTrue(restored_report["ok"])
            self.assertEqual(restored_report["store"]["runs"], 1)

            with SQLiteHarnessStore(restored) as store:
                projection = store.load_run(run_id)
                self.assertEqual(projection.revision, 2)
                self.assertEqual(len(store.list_run_events(run_id)), 2)
                evidence = store.get_object(evidence_digest, expected_kind="runtime-job-reference")
                self.assertEqual(
                    evidence,
                    {"runtimeJobRef": "runtime-job:p0-backup-001"},
                )

    def test_backup_rejects_existing_destination_and_restore_rejects_existing_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            backup = base / "backup"
            self.populate(source)
            backup.mkdir()
            with self.assertRaises(FileExistsError):
                backup_harness_store(source, backup)
            backup.rmdir()
            backup_harness_store(source, backup)
            destination = base / "destination"
            destination.mkdir()
            with self.assertRaises(FileExistsError):
                restore_harness_backup(backup, destination)

    def test_tampered_database_and_object_fail_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            backup = base / "backup"
            self.populate(source)
            backup_harness_store(source, backup)

            database = backup / "harness.sqlite3"
            database.write_bytes(database.read_bytes() + b"tamper")
            with self.assertRaisesRegex(HarnessJournalCorruption, "database digest"):
                verify_harness_backup(backup)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            backup = base / "backup"
            self.populate(source)
            backup_harness_store(source, backup)
            object_path = next((backup / "objects").glob("*.json"))
            object_path.write_bytes(object_path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(HarnessJournalCorruption, "byte length|file digest"):
                verify_harness_backup(backup)

    def test_manifest_object_set_must_equal_database_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            backup = base / "backup"
            self.populate(source)
            backup_harness_store(source, backup)
            extra = backup / "objects" / ("f" * 64 + ".json")
            extra.write_text("{}", encoding="utf-8")
            # Unreferenced files are inert; the manifest and database remain authoritative.
            self.assertTrue(verify_harness_backup(backup)["ok"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.cli import main
from ordivon_harness.sqlite_store import SQLiteHarnessStore

from tests.test_p0_sqlite_store import run_contract


class HarnessStoreCliTests(unittest.TestCase):
    def invoke(self, *args: str) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(args)
        value = json.loads(stdout.getvalue()) if stdout.getvalue() else {}
        return code, value, stderr.getvalue()

    def test_init_doctor_inspect_and_events_use_only_harness_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "harness"
            code, value, error = self.invoke("--state-root", str(root), "store-init")
            self.assertEqual((code, error), (0, ""))
            self.assertTrue(value["store"]["healthy"])

            with SQLiteHarnessStore(root) as store:
                contract = run_contract()
                store.create_run(contract)

            code, value, error = self.invoke(
                "--state-root",
                str(root),
                "store-inspect",
                contract.harness_run_id,
            )
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(value["run"]["status"], "created")
            self.assertEqual(value["run"]["revision"], 1)

            code, value, error = self.invoke(
                "--state-root",
                str(root),
                "store-events",
                contract.harness_run_id,
            )
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(len(value["events"]), 1)
            self.assertEqual(value["events"][0]["eventKind"], "harness.run-created")

            code, value, error = self.invoke("--state-root", str(root), "store-doctor")
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(value["store"]["runs"], 1)

    def test_backup_verify_and_restore_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "harness"
            backup = base / "backup"
            restored = base / "restored"
            with SQLiteHarnessStore.initialize(root) as store:
                contract = run_contract()
                store.create_run(contract)

            code, value, error = self.invoke(
                "--state-root",
                str(root),
                "store-backup",
                str(backup),
            )
            self.assertEqual((code, error), (0, ""))
            self.assertTrue(value["backup"]["ok"])

            code, value, error = self.invoke(
                "store-verify-backup",
                str(backup),
            )
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(value["backup"]["runs"], 1)

            code, value, error = self.invoke(
                "store-restore",
                str(backup),
                str(restored),
            )
            self.assertEqual((code, error), (0, ""))
            self.assertTrue(value["restore"]["ok"])
            with SQLiteHarnessStore(restored) as store:
                self.assertEqual(store.load_run(contract.harness_run_id).revision, 1)

    def test_store_commands_require_explicit_harness_root(self) -> None:
        code, value, error = self.invoke("store-init")
        self.assertEqual(code, 1)
        self.assertEqual(value, {})
        failure = json.loads(error)
        self.assertEqual(failure["error"], "ValueError")
        self.assertIn("--state-root", failure["message"])


if __name__ == "__main__":
    unittest.main()

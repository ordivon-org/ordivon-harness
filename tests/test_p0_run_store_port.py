from __future__ import annotations

import inspect
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.errors import HarnessLifecycleError
from ordivon_harness.ordivon.run_store_port import (
    HarnessProviderCallRecoveryRequired,
    HarnessRunContinuityStore,
)
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from tests.test_p0_sqlite_provider_store import MutableClock, contract

ROOT = Path(__file__).resolve().parents[1] / "src" / "ordivon_harness"


class HarnessRunStorePortTests(unittest.TestCase):
    def test_lifecycle_error_has_one_harness_owner(self) -> None:
        self.assertTrue(issubclass(HarnessProviderCallRecoveryRequired, HarnessLifecycleError))

    def test_port_and_current_store_do_not_import_host(self) -> None:
        for relative in (
            "errors.py",
            "ordivon/run_store_port.py",
            "ordivon/sqlite_run_store.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("ordivon_host", source)
            self.assertNotIn("_host_compat", source)
            self.assertNotIn("HostHarnessRunStore", source)

    def test_sqlite_store_supplies_every_port_operation(self) -> None:
        required = {
            name
            for name, value in HarnessRunContinuityStore.__dict__.items()
            if name not in {"__module__", "__doc__", "__parameters__"}
            and (callable(value) or isinstance(value, property))
            and not name.startswith("_")
        }
        missing = sorted(
            name
            for name in required - {"harness_run_id"}
            if not hasattr(SQLiteHarnessRunContinuityStore, name)
        )
        self.assertEqual(missing, [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = contract()
            with SQLiteHarnessStore.initialize(root) as store:
                store.create_run(run_contract)
                continuity = SQLiteHarnessRunContinuityStore(
                    store, run_contract, clock_ms=MutableClock()
                )
                self.assertIsInstance(continuity, HarnessRunContinuityStore)

    def test_runtime_bridge_contract_depends_on_port_not_concrete_host_store(self) -> None:
        source = (ROOT / "ordivon" / "sqlite_runtime_bridge.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("HostHarnessRunStore", source)
        annotation = inspect.signature(
            SQLiteHarnessRunContinuityStore.__init__
        ).parameters["contract"].annotation
        self.assertTrue(annotation)


if __name__ == "__main__":
    unittest.main()

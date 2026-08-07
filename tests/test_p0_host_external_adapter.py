from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from ordivon_harness.host_external_adapter import (
    OrdivonHarnessExternalExecutorAdapter,
)
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from tests.test_p0_sqlite_agent_loop import contract as independent_contract


ROOT = Path(__file__).resolve().parents[1]


class HostExternalAdapterTests(unittest.TestCase):
    def test_recover_records_conservative_unknown_instead_of_invalid_safe_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory) / "harness"
            base = independent_contract("external-recover")
            request_id = "external-request:h1-recover"
            run_contract = replace(base, caller_run_ref=request_id)
            with SQLiteHarnessStore.initialize(state_root) as store:
                store.create_run(run_contract)

            request = SimpleNamespace(
                request_id=request_id,
                adapter_id="external-executor:ordivon-harness",
                task_id="task:h1-external-recover",
                task_attempt_ref="task-attempt:h1-external-recover",
                contract_digest=run_contract.digest,
                correlation_context={},
                created_at_ms=run_contract.created_at_ms,
            )
            adapter = OrdivonHarnessExternalExecutorAdapter(
                state_root,
                contract_resolver=lambda _: run_contract,
                driver_factory=lambda *_: None,
                clock_ms=lambda: run_contract.created_at_ms + 1,
            )
            observed = adapter.recover(request, run_contract.harness_run_id)
            self.assertEqual(observed.foreign_run_ref, run_contract.harness_run_id)
            self.assertIn("recoveryAssessmentDigest", observed.metadata)

            with SQLiteHarnessStore(state_root) as store:
                events = store.list_run_events(run_contract.harness_run_id)
                recovery_event = next(
                    event for event in events
                    if event.event_kind == "harness.run-recovery-recorded"
                )
                raw = store.get_object(
                    recovery_event.data["assessmentObjectDigest"],
                    expected_kind="native-run-recovery-assessment",
                )
                self.assertFalse(raw["safeToAbandon"])
                self.assertTrue(raw["unresolvedUnknowns"])

    def test_adapter_module_has_no_host_import(self) -> None:
        source = (ROOT / "src" / "ordivon_harness" / "host_external_adapter.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import ordivon_host", source)
        self.assertNotIn("from ordivon_host", source)
        self.assertIn("ExternalExecutorAdapter", source)


if __name__ == "__main__":
    unittest.main()

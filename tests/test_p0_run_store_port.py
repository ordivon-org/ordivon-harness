from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from ordivon_harness import HarnessLifecycleError
from ordivon_harness.host import HarnessLifecycleError as HostLifecycleError
from ordivon_harness.ordivon.run_store import HostHarnessRunStore
from ordivon_harness.ordivon.run_store_port import (
    HarnessProviderCallRecoveryRequired,
    HarnessRunContinuityStore,
)
from ordivon_harness.ordivon.tools import RuntimeToolBridge

ROOT = Path(__file__).resolve().parents[1] / "src" / "ordivon_harness"


class HarnessRunStorePortTests(unittest.TestCase):
    def test_lifecycle_error_has_one_owner(self) -> None:
        self.assertIs(HarnessLifecycleError, HostLifecycleError)
        self.assertTrue(issubclass(HarnessProviderCallRecoveryRequired, HarnessLifecycleError))

    def test_port_and_errors_do_not_import_host(self) -> None:
        for relative in ("errors.py", "ordivon/run_store_port.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("ordivon_host", source)
            self.assertNotIn("_host_compat", source)
            self.assertNotIn("CommittedHarnessAssignment", source)
            self.assertNotIn("HostHarnessRunStore", source)

    def test_runtime_bridge_depends_on_port_not_concrete_store(self) -> None:
        source = (ROOT / "ordivon" / "tools.py").read_text(encoding="utf-8")
        self.assertNotIn("HostHarnessRunStore", source)
        self.assertNotIn("run_store.committed", source)
        self.assertNotIn("run_store.host", source)
        annotation = (
            inspect.signature(RuntimeToolBridge.__init__).parameters["run_store"].annotation
        )
        self.assertIn("HarnessRunContinuityStore", str(annotation))

    def test_legacy_store_supplies_every_port_operation(self) -> None:
        required = {
            name
            for name, value in HarnessRunContinuityStore.__dict__.items()
            if name not in {"__module__", "__doc__", "__parameters__"}
            and (callable(value) or isinstance(value, property))
            and not name.startswith("_")
        }
        instance_fields = {"harness_run_id"}
        missing = sorted(
            name for name in required - instance_fields if not hasattr(HostHarnessRunStore, name)
        )
        self.assertEqual(missing, [])
        source = inspect.getsource(HostHarnessRunStore.__init__)
        self.assertIn("self.harness_run_id =", source)
        self.assertEqual(
            required,
            {
                "assignment_provider_source",
                "assert_dispatch_fence_current",
                "bind_state",
                "binding",
                "caller_revision",
                "claim_provider_call",
                "clock_ms",
                "complete_provider_call",
                "fail_claimed_provider_call",
                "fail_provider_call",
                "harness_run_id",
                "load_current_provider_call",
                "load_current_snapshot",
                "load_current_tool_step",
                "load_provider_replay_state",
                "mark_provider_call_dispatching",
                "prepare_tool_step",
                "provider_outcome_requires_resume",
                "record_pause",
                "record_tool_step_receipt",
                "retry_failed_provider_call",
                "snapshot_provider_source",
            },
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOST_SOURCE = Path("/root/projects/ordivon-host/src")


class HostExternalAdapterTests(unittest.TestCase):
    def test_real_host_harness_roundtrip_with_response_loss(self) -> None:
        if not HOST_SOURCE.exists():
            self.skipTest("local Ordivon Host source is unavailable")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            (str(HOST_SOURCE), str(ROOT / "src"), env.get("PYTHONPATH", ""))
        )
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_host_external_roundtrip.py")],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        receipt = ast.literal_eval(completed.stdout.strip().splitlines()[-1])
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["hostTaskState"], "ready")
        self.assertEqual(receipt["harnessRunState"], "completed")
        self.assertEqual(receipt["physicalHarnessExecutions"], 1)
        self.assertEqual(receipt["adapterStartCalls"], 2)
        self.assertGreater(receipt["hostEvents"], 1)
        self.assertGreater(receipt["harnessEvents"], 1)

    def test_adapter_module_has_no_host_import(self) -> None:
        source = (ROOT / "src" / "ordivon_harness" / "host_external_adapter.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import ordivon_host", source)
        self.assertNotIn("from ordivon_host", source)
        self.assertIn("ExternalExecutorAdapter", source)


if __name__ == "__main__":
    unittest.main()

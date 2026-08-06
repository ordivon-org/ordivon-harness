from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "harness_p0_scale_acceptance.py"
SPEC = importlib.util.spec_from_file_location("harness_p0_scale_acceptance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HarnessP0ScaleAcceptanceTests(unittest.TestCase):
    def test_small_scale_receipt_is_exact_and_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = MODULE.run_acceptance(
                root=Path(directory) / "state",
                run_count=8,
                events_per_run=12,
                batch_size=11,
                inspect_samples=4,
                max_write_ms=30_000,
                max_reopen_ms=30_000,
                max_inspect_p95_ms=1_000,
            )
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["counts"]["runs"], 8)
        self.assertEqual(receipt["counts"]["events"], 96)
        self.assertTrue(all(receipt["checks"].values()))
        self.assertTrue(
            receipt["integrity"]["payloadDigest"].startswith("sha256:")
        )


if __name__ == "__main__":
    unittest.main()

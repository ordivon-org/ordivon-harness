from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_p0_persistence_inventory.py"
SPEC = ROOT / "specs" / "p0-persistence-inventory-v1.json"

spec = importlib.util.spec_from_file_location("p0_inventory_check", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PersistenceInventoryTests(unittest.TestCase):
    def test_frozen_inventory_matches_current_sources(self) -> None:
        report = module.check_inventory(SPEC)
        self.assertTrue(report["ok"], report["issues"])
        self.assertGreaterEqual(report["objects"], 27)
        self.assertEqual(report["events"], 15)
        self.assertTrue(report["payloadDigest"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()

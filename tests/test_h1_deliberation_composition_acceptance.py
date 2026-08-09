from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "acceptance_h1_deliberation_composition.py"
spec = importlib.util.spec_from_file_location("h1_deliberation_composition_acceptance", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class H1DeliberationCompositionAcceptanceTests(unittest.TestCase):
    def test_reuses_exact_h0_task_and_oracle(self) -> None:
        self.assertEqual(
            module.TASK_DIGEST,
            "sha256:b402b3066ebd0fa64c4e464fd4f1640a3cd1cc08b0164426f2a39805f56e223f",
        )
        self.assertEqual(module.ORACLE, "cobalt")
        self.assertEqual(module.REPLICATES, 2)

    def test_h1_uses_generic_composition_not_hand_written_phase_injection(self) -> None:
        source = SCRIPT.read_text()
        self.assertIn("DeliberationThenToolRunner(adapter, bridge).run", source)
        self.assertNotIn("DomainToolLoopRunner", source)


if __name__ == "__main__":
    unittest.main()

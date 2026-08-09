from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "acceptance_h0_deliberation_authority.py"
spec = importlib.util.spec_from_file_location("h0_deliberation_authority", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class H0DeliberationAuthorityTests(unittest.TestCase):
    def test_oracle_is_unique_cobalt(self) -> None:
        table = module.score_table()
        by_id = {row["id"]: row for row in table}
        self.assertFalse(by_id["atlas"]["feasible"])
        self.assertFalse(by_id["birch"]["feasible"])
        self.assertEqual(by_id["cobalt"]["score"], 58)
        self.assertEqual(by_id["delta"]["score"], 57)
        self.assertEqual(module.oracle_choice(), "cobalt")

    def test_choice_bridge_records_replacements_without_external_effect(self) -> None:
        class Call:
            name = "submit_choice"
            tool_call_id = "call:h0"
            arguments = {"choice": "delta"}

        bridge = module.ChoiceBridge()
        first = bridge.execute(Call(), step_id="step:1")
        Call.arguments = {"choice": "cobalt"}
        second = bridge.execute(Call(), step_id="step:2")
        self.assertEqual(bridge.revisions, ["delta", "cobalt"])
        self.assertFalse(first.structured_content["externalEffectPerformed"])
        self.assertFalse(second.structured_content["evaluatorScoreRevealed"])
        self.assertTrue(second.structured_content["replacementAllowed"])

    def test_outcome_classification_is_not_success_biased(self) -> None:
        def rec(correct: bool):
            return {"correct": correct}

        self.assertEqual(
            module._classify([rec(True), rec(True)], [rec(True), rec(True)]),
            "ordering-pressure-not-reproduced",
        )
        self.assertEqual(
            module._classify([rec(False), rec(True)], [rec(True), rec(True)]),
            "ordering-pressure-reproduced-in-sample",
        )
        self.assertEqual(
            module._classify([rec(True), rec(True)], [rec(False), rec(True)]),
            "deliberation-first-not-sufficient-in-sample",
        )


if __name__ == "__main__":
    unittest.main()

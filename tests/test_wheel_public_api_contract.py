from __future__ import annotations

import ast
from pathlib import Path
import unittest

from ordivon_harness import api
from tests.test_public_api import EXPECTED_API as PUBLIC_TEST_API

ROOT = Path(__file__).resolve().parents[1]
CLAIM_STANDING_EXPORTS = {
    "OperationalClaimEvidenceRole",
    "OperationalClaimRef",
    "OperationalClaimStandingView",
    "project_operational_claim_standing_view",
}


def _literal_set(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                value = ast.literal_eval(node.value)
                return set(value)
    raise AssertionError(f"{name} not found in {path}")


class WheelPublicApiContractTests(unittest.TestCase):
    def test_all_existing_public_api_projections_agree(self) -> None:
        source = set(api.__all__)
        docs = _literal_set(ROOT / "scripts" / "check_docs.py", "STABLE_API")
        wheel = _literal_set(ROOT / "scripts" / "check_wheel.py", "EXPECTED_API")
        self.assertEqual(source, set(PUBLIC_TEST_API))
        self.assertEqual(source, docs)
        self.assertEqual(source, wheel)

    def test_claim_standing_exports_are_part_of_current_contract(self) -> None:
        source = set(api.__all__)
        self.assertTrue(CLAIM_STANDING_EXPORTS <= source)
        self.assertTrue(CLAIM_STANDING_EXPORTS <= set(PUBLIC_TEST_API))
        self.assertTrue(
            CLAIM_STANDING_EXPORTS
            <= _literal_set(ROOT / "scripts" / "check_docs.py", "STABLE_API")
        )


if __name__ == "__main__":
    unittest.main()

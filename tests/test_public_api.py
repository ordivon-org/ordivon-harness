from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

import ordivon_harness
import ordivon_harness.api as api
from ordivon_harness.version import package_version


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_API = {
    "CompletionMode",
    "DomainToolBridge",
    "DomainToolCatalog",
    "DomainToolLoopPlan",
    "DomainToolLoopRunner",
    "HarnessCancellationResult",
    "HarnessExecutionResult",
    "HarnessRunner",
    "HarnessRunPlan",
    "HarnessStatus",
    "RunHandle",
    "TaskContract",
    "ToolGrant",
}


class PublicApiTests(unittest.TestCase):
    def test_recommended_facade_is_exact_and_importable(self) -> None:
        self.assertEqual(set(api.__all__), EXPECTED_API)
        for name in EXPECTED_API:
            self.assertIsNotNone(getattr(api, name))

    def test_source_checkout_version_matches_project_metadata(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(package_version(), project["version"])

    def test_historical_root_exports_remain_during_transition(self) -> None:
        self.assertIs(ordivon_harness.HarnessRunner, api.HarnessRunner)
        self.assertTrue(hasattr(ordivon_harness, "HarnessProviderCallRecord"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessRunContract"))
        self.assertTrue(hasattr(ordivon_harness, "SQLiteHarnessStore"))


if __name__ == "__main__":
    unittest.main()

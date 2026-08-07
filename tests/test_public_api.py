from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tomllib
import unittest

import ordivon_harness
import ordivon_harness.api as api
from ordivon_harness.version import package_version


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_API = {
    "AgentTurnAdapter",
    "AgentTurnRequest",
    "AgentTurnResult",
    "DomainToolBridge",
    "DomainToolCatalog",
    "DomainToolLoopPlan",
    "DomainToolLoopRunner",
    "HarnessPrivacyPolicy",
    "HarnessRunContract",
    "HarnessRuntimeClient",
    "IndependentCompletionProposal",
    "IndependentHarnessRunReceipt",
    "OrdivonAgentLoop",
    "RunBudget",
    "RunStopCode",
    "SQLiteHarnessRunContinuityStore",
    "SQLiteHarnessRuntimeBridge",
    "SQLiteHarnessStore",
    "StandaloneHarnessExecution",
    "StandaloneHarnessRunner",
    "StandaloneToolBridge",
}

class PublicApiTests(unittest.TestCase):
    def test_recommended_facade_is_host_free_and_exact(self) -> None:
        self.assertEqual(set(api.__all__), EXPECTED_API)
        for name in EXPECTED_API:
            self.assertIsNotNone(getattr(api, name))

        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json,sys,ordivon_harness.api as api; "
                "print(json.dumps({'hostLoaded':any(k=='ordivon_host' or k.startswith('ordivon_host.') for k in sys.modules), 'api':sorted(api.__all__)}))",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        import json

        observed = json.loads(probe.stdout)
        self.assertFalse(observed["hostLoaded"])
        self.assertEqual(set(observed["api"]), EXPECTED_API)

    def test_host_integration_is_an_explicit_host_free_adapter_module(self) -> None:
        from ordivon_harness.host_external_adapter import (
            OrdivonHarnessExternalExecutorAdapter,
        )

        self.assertFalse(hasattr(ordivon_harness, "HarnessRunner"))
        self.assertTrue(callable(OrdivonHarnessExternalExecutorAdapter))

    def test_source_checkout_version_matches_project_metadata(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(package_version(), project["version"])

    def test_package_root_dir_advertises_recommended_capabilities_not_host_compat(self) -> None:
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json,sys,ordivon_harness; names=dir(ordivon_harness); "
                "print(json.dumps({'hasRunContract':'HarnessRunContract' in names,"
                "'hasHostRunner':'HarnessRunner' in names,"
                "'hostLoaded':any(k=='ordivon_host' or k.startswith('ordivon_host.') for k in sys.modules)}))",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        import json

        observed = json.loads(probe.stdout)
        self.assertTrue(observed["hasRunContract"])
        self.assertFalse(observed["hasHostRunner"])
        self.assertFalse(observed["hostLoaded"])

    def test_package_root_is_the_recommended_api_without_legacy_exports(self) -> None:
        self.assertEqual(set(ordivon_harness.__all__), EXPECTED_API | {"package_version"})
        for removed in (
            "HarnessRunner",
            "HarnessHost",
            "HarnessCutoverReceipt",
            "HarnessAssignment",
            "TaskContract",
            "HostHarnessRunStore",
        ):
            self.assertFalse(hasattr(ordivon_harness, removed))




if __name__ == "__main__":
    unittest.main()

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
EXPECTED_HOST_API = {
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

    def test_host_backed_facade_remains_explicit(self) -> None:
        import ordivon_harness.host_api as host_api

        self.assertEqual(set(host_api.__all__), EXPECTED_HOST_API)
        self.assertIs(ordivon_harness.HarnessRunner, host_api.HarnessRunner)

    def test_source_checkout_version_matches_project_metadata(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(package_version(), project["version"])

    def test_historical_root_exports_remain_during_transition(self) -> None:
        self.assertTrue(hasattr(ordivon_harness, "HarnessRunner"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessProviderCallRecord"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessRunContract"))
        self.assertTrue(hasattr(ordivon_harness, "SQLiteHarnessStore"))
        self.assertTrue(hasattr(ordivon_harness, "SQLiteHarnessRunContinuityStore"))
        self.assertTrue(hasattr(ordivon_harness, "SQLiteHarnessAgentBridge"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessExecutionBinding"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessRuntimeReference"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessRuntimeClient"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessToolObservation"))
        self.assertTrue(hasattr(ordivon_harness, "SQLiteHarnessRuntimeBridge"))
        self.assertTrue(hasattr(ordivon_harness, "IndependentHarnessRunReceipt"))
        self.assertTrue(hasattr(ordivon_harness, "IndependentCompletionProposal"))
        self.assertTrue(hasattr(ordivon_harness, "StandaloneHarnessRunner"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessCutoverReceipt"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessStoreMode"))
        self.assertTrue(hasattr(ordivon_harness, "OrdivonHarnessExternalExecutorAdapter"))


if __name__ == "__main__":
    unittest.main()

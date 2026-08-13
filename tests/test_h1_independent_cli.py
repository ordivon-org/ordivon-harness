from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ordivon_harness.cli import main as cli_main
from ordivon_harness.core_contracts import HarnessPrivacyPolicy
from ordivon_harness.ordivon.model import ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_runtime_bridge import (
    INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
    INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
)
from tests.test_p0_sqlite_agent_loop import (
    completed_result,
    contract,
    needs_input_result,
)


class IndependentCliTests(unittest.TestCase):
    @staticmethod
    def invoke(*argv: str):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli_main(argv)
        value = None if not stdout.getvalue() else json.loads(stdout.getvalue())
        return code, value, stderr.getvalue()

    def test_capabilities_describe_only_independent_authority(self) -> None:
        code, value, error = self.invoke("capabilities")
        self.assertEqual(code, 0, error)
        assert value is not None
        self.assertEqual(value["defaultAuthority"], "independent-harness-run")
        self.assertNotIn("hostCompatibilityCommand", value)
        self.assertFalse(value["toolBearingCliExecution"])
        mandate = value["executionMandate"]
        self.assertTrue(mandate["supported"])
        self.assertEqual(mandate["authority"], "caller-delegated")
        self.assertEqual(mandate["compilesTo"], "HarnessRunContract")
        self.assertFalse(mandate["builtInStrategyPolicy"])
        self.assertFalse(mandate["durableMandateStore"])
        profile = value["executionProfiles"][0]
        self.assertEqual(profile["profileId"], "deepseek-no-tool-v1")
        self.assertFalse(profile["runtimeRequired"])

    def test_independent_run_pause_resume_status_and_inspect_are_first_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "harness"
            run_contract = replace(
                contract("h1-cli"),
                privacy=HarnessPrivacyPolicy(
                    content_policy="bounded-private-content",
                    allow_model_content=True,
                    allow_tool_content=False,
                ),
            )
            contract_path = Path(directory) / "contract.json"
            contract_path.write_text(
                json.dumps(run_contract.to_dict(), sort_keys=True),
                encoding="utf-8",
            )
            code, _, error = self.invoke(
                "--state-root", str(root), "store-init"
            )
            self.assertEqual(code, 0, error)

            with patch(
                "ordivon_harness.independent_cli._adapter",
                return_value=ScriptedTurnAdapter((needs_input_result("h1-cli-pause"),)),
            ):
                code, paused, error = self.invoke(
                    "--state-root",
                    str(root),
                    "run",
                    str(contract_path),
                    "--message",
                    "start independently",
                )
            self.assertEqual(code, 0, error)
            assert paused is not None
            self.assertEqual(paused["authority"], "independent-harness-run")
            self.assertEqual(paused["run"]["status"], "paused")
            self.assertEqual(paused["stopCode"], "needs_input")
            self.assertIsNone(paused["runReceipt"])

            code, status, error = self.invoke(
                "--state-root",
                str(root),
                "status",
                run_contract.harness_run_id,
            )
            self.assertEqual(code, 0, error)
            assert status is not None
            self.assertEqual(status["run"]["status"], "paused")

            code, inspected, error = self.invoke(
                "--state-root",
                str(root),
                "inspect",
                run_contract.harness_run_id,
            )
            self.assertEqual(code, 0, error)
            assert inspected is not None
            self.assertEqual(inspected["contract"]["harnessRunId"], run_contract.harness_run_id)
            self.assertEqual(inspected["snapshot"]["pauseReason"], "needs-input")
            self.assertIsNone(inspected["providerCall"])

            code, telemetry, error = self.invoke(
                "--state-root",
                str(root),
                "telemetry",
                run_contract.harness_run_id,
            )
            self.assertEqual(code, 0, error)
            assert telemetry is not None
            self.assertEqual(telemetry["kind"], "ordivon.harness-telemetry-projection")
            self.assertEqual(telemetry["run"]["status"], "paused")
            self.assertEqual(telemetry["continuity"]["pauseReason"], "needs-input")
            self.assertEqual(telemetry["budget"]["remainingBasis"], "durable-run-snapshot")
            self.assertFalse(telemetry["cache"]["available"])

            code, recovery, error = self.invoke(
                "--state-root",
                str(root),
                "recover",
                run_contract.harness_run_id,
            )
            self.assertEqual(code, 0, error)
            assert recovery is not None
            self.assertTrue(recovery["recovery"]["safeToAbandon"])
            self.assertEqual(recovery["requiredAction"], "resume")

            with patch(
                "ordivon_harness.independent_cli._adapter",
                return_value=ScriptedTurnAdapter((completed_result("h1-cli-resume"),)),
            ):
                code, completed, error = self.invoke(
                    "--state-root",
                    str(root),
                    "resume",
                    run_contract.harness_run_id,
                    "--message",
                    "the bounded answer is yes",
                )
            self.assertEqual(code, 0, error)
            assert completed is not None
            self.assertEqual(completed["run"]["status"], "completed")
            self.assertEqual(completed["stopCode"], "candidate_completed")
            self.assertIsNotNone(completed["runReceipt"])
            self.assertIsNotNone(completed["completionProposal"])

            code, terminal, error = self.invoke(
                "--state-root",
                str(root),
                "recover",
                run_contract.harness_run_id,
            )
            self.assertEqual(code, 0, error)
            assert terminal is not None
            self.assertEqual(terminal["requiredAction"], "none")
            self.assertEqual(terminal["run"]["status"], "completed")

    def test_tool_bearing_contract_fails_closed_before_provider_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "harness"
            value = contract("h1-cli-tool-bearing").to_dict()
            value["toolCatalogDigest"] = INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST
            value["toolGrantDigest"] = INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST
            contract_path = Path(directory) / "contract.json"
            contract_path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(
                self.invoke("--state-root", str(root), "store-init")[0],
                0,
            )
            with patch(
                "ordivon_harness.independent_cli._adapter",
                side_effect=AssertionError("Provider must not be constructed"),
            ):
                code, value, error = self.invoke(
                    "--state-root",
                    str(root),
                    "run",
                    str(contract_path),
                    "--message",
                    "search the workspace",
                )
            self.assertEqual(code, 1)
            self.assertIsNone(value)
            self.assertIn("Tool-bearing Runs require", error)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Validate one Host-free Ordivon Harness wheel and isolated installation."""

from __future__ import annotations

import argparse
from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_API = {
    "HarnessAgentExecution",
    "HarnessAgentRun",
    "HarnessAgentRunCompositionError",
    "HarnessCognitionProfile",
    "HarnessCognitionSeed",
    "HarnessCognitionSeedSource",
    "HarnessCognitionSource",
    "AgentTurnAdapter",
    "AgentTurnRequest",
    "AgentTurnResult",
    "CompiledHarnessAttempt",
    "DeepSeekSettings",
    "DeepSeekTurnAdapter",
    "HarnessBoundReference",
    "HarnessCorrelationContext",
    "HarnessExecutionBinding",
    "HarnessExecutionMandate",
    "HarnessMandateConsumption",
    "HarnessExecutionProfile",
    "HarnessExecutionStrategy",
    "HarnessAgentStrategySelection",
    "HarnessPriorAttemptEvidence",
    "HarnessStrategyEvidence",
    "HarnessStrategySelectionContext",
    "AgentToolDefinition",
    "DomainToolBridge",
    "DomainToolCatalog",
    "DomainToolLoopPlan",
    "DomainToolLoopRunner",
    "ToolBridgeError",
    "ToolBridgeErrorKind",
    "ToolObservation",
    "HarnessPrivacyPolicy",
    "HarnessProviderRoute",
    "HarnessProviderUsePolicy",
    "HarnessProviderUsePolicyError",
    "HarnessRunContract",
    "HarnessRuntimeClient",
    "HarnessRuntimeClientError",
    "HarnessRuntimeErrorDetail",
    "HarnessRuntimeReference",
    "HarnessRuntimeToolRejected",
    "INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST",
    "INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST",
    "NO_TOOL_AGENT_GRANT_DIGEST",
    "NO_TOOL_AGENT_SURFACE_DIGEST",
    "IndependentCompletionProposal",
    "IndependentHarnessRunReceipt",
    "OrdivonAgentLoop",
    "RunBudget",
    "RunStopCode",
    "STRUCTURED_COMPLETION_MODE",
    "SQLiteHarnessRunContinuityStore",
    "SQLiteHarnessRuntimeBridge",
    "SQLiteHarnessStore",
    "StandaloneHarnessExecution",
    "StandaloneHarnessRunner",
    "StandaloneToolBridge",
    "admit_harness_agent_strategy",
    "build_harness_strategy_selection_context",
    "compile_harness_attempt",
    "compile_harness_selected_attempt",
    "decode_structured_completion_result",
    "derive_harness_mandate_consumption",
    "structured_completion_contract_digest",
    "structured_completion_result_schema",
}
REQUIRED_MEMBERS = {
    "ordivon_harness/agent_run.py",
    "ordivon_harness/api.py",
    "ordivon_harness/completion.py",
    "ordivon_harness/core.py",
    "ordivon_harness/mandate.py",
    "ordivon_harness/core_contracts.py",
    "ordivon_harness/independent_cli.py",
    "ordivon_harness/independent_result.py",
    "ordivon_harness/knowledge_topology.py",
    "ordivon_harness/host_external_adapter.py",
    "ordivon_harness/sqlite_store.py",
    "ordivon_harness/standalone.py",
    "ordivon_harness/store.py",
    "ordivon_harness/store_ops.py",
    "ordivon_harness/strategy_selection.py",
    "ordivon_harness/tool_program.py",
    "ordivon_harness/tool_program_recovery.py",
    "ordivon_harness/tool_program_durable_recovery.py",
    "ordivon_harness/ordivon/loop.py",
    "ordivon_harness/ordivon/model.py",
    "ordivon_harness/ordivon/sqlite_agent_bridge.py",
    "ordivon_harness/ordivon/sqlite_run_store.py",
    "ordivon_harness/ordivon/sqlite_runtime_bridge.py",
}
FORBIDDEN_MEMBERS = {
    "ordivon_harness/host.py",
    "ordivon_harness/host_api.py",
    "ordivon_harness/runner.py",
    "ordivon_harness/cutover.py",
    "ordivon_harness/history.py",
    "ordivon_harness/contracts.py",
    "ordivon_harness/models.py",
    "ordivon_harness/ordivon/run_store.py",
}
CLI_COMMANDS = (
    "capabilities",
    "doctor",
    "status",
    "inspect",
    "run",
    "resume",
    "recover",
    "store-init",
    "store-doctor",
    "store-backup",
    "store-verify-backup",
    "store-restore",
    "store-inspect",
    "store-events",
)


def fail(message: str) -> None:
    print(f"wheel: {message}", file=sys.stderr)
    raise SystemExit(1)


def checked(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        fail(f"command failed ({result.returncode}): {' '.join(args)}")
    return result


def resolve(value: str) -> Path:
    path = Path(value).resolve()
    if path.is_file() and path.suffix == ".whl":
        return path
    wheels = sorted(path.glob("*.whl")) if path.is_dir() else []
    if len(wheels) != 1:
        fail(f"expected exactly one wheel, observed {len(wheels)}")
    return wheels[0]


def validate_archive(wheel: Path) -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
        entry_names = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
        if len(metadata_names) != 1 or len(entry_names) != 1:
            fail("wheel metadata or entry point file is missing")
        missing = sorted(REQUIRED_MEMBERS - names)
        if missing:
            fail("wheel lacks required modules: " + ", ".join(missing))
        forbidden = sorted(FORBIDDEN_MEMBERS & names)
        if forbidden:
            fail("wheel still contains Host-backed modules: " + ", ".join(forbidden))
        metadata = BytesParser(policy=policy.default).parsebytes(archive.read(metadata_names[0]))
        entries = archive.read(entry_names[0]).decode()
    if metadata.get("Name") != project["name"] or metadata.get("Version") != project["version"]:
        fail("wheel name/version differs from pyproject")
    requirements = tuple(metadata.get_all("Requires-Dist", []))
    if len(requirements) != 1 or "ordivon-protocol" not in requirements[0]:
        fail(f"wheel must contain exactly one Protocol dependency: {requirements}")
    if any("ordivon-host" in item or "extra ==" in item for item in requirements):
        fail("wheel metadata still exposes Host/extra dependencies")
    if "ordivon-harness = ordivon_harness.cli:entrypoint" not in entries:
        fail("wheel entry point differs")
    return project["version"]


def install_smoke(wheel: Path, version: str) -> dict[str, object]:
    uv = shutil.which("uv")
    if uv is None:
        fail("uv is required")
    with tempfile.TemporaryDirectory(prefix="ordivon-harness-wheel-") as directory:
        root = Path(directory)
        checked([uv, "venv", "--python", "3.12", str(root)])
        python = root / "bin/python"
        cli = root / "bin/ordivon-harness"
        checked([uv, "pip", "install", "--link-mode", "copy", "--python", str(python), str(wheel)])
        probe = json.loads(
            checked(
                [
                    str(python),
                    "-c",
                    "import importlib.metadata as m,importlib.util,json,sys; import ordivon_harness,ordivon_harness.api as api; "
                    "print(json.dumps({'version':m.version('ordivon-harness'),'api':sorted(api.__all__),"
                    "'root':sorted(ordivon_harness.__all__),'hostInstalled':importlib.util.find_spec('ordivon_host') is not None,"
                    "'hostLoaded':any(k=='ordivon_host' or k.startswith('ordivon_host.') for k in sys.modules)}))",
                ]
            ).stdout
        )
        if probe["version"] != version or set(probe["api"]) != EXPECTED_API:
            fail("installed API/version differs")
        if set(probe["root"]) != EXPECTED_API | {"package_version"}:
            fail("package root differs from recommended API")
        if probe["hostInstalled"] or probe["hostLoaded"]:
            fail("Host appeared in isolated base installation")
        checked([str(python), str(ROOT / "scripts/check_core_without_host.py")])
        help_text = checked([str(cli), "--help"]).stdout
        for command in CLI_COMMANDS:
            if command not in help_text:
                fail(f"CLI lacks {command}")
        for removed in ("host", "cutover-status", "cutover-activate", "--harness-state-root"):
            if removed in help_text:
                fail(f"CLI still advertises removed surface: {removed}")
        caps = json.loads(checked([str(cli), "capabilities"]).stdout)
        if caps.get("defaultAuthority") != "independent-harness-run":
            fail("capabilities default authority differs")
        if "hostCompatibilityCommand" in caps:
            fail("capabilities still advertise Host compatibility")
        return {
            "installedVersion": version,
            "hostFreeCoreVerified": True,
            "cliCommandsVerified": len(CLI_COMMANDS),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel")
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    wheel = resolve(args.wheel)
    version = validate_archive(wheel)
    result: dict[str, object] = {
        "status": "passed",
        "wheel": wheel.name,
        "version": version,
        "metadataOnly": bool(args.metadata_only),
    }
    if not args.metadata_only:
        result.update(install_smoke(wheel, version))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

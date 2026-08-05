#!/usr/bin/env python3
"""Validate and install-smoke-test one Ordivon Harness wheel."""

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
REQUIRED_CORE_API = {
    "HarnessRunContract",
    "SQLiteHarnessStore",
    "SQLiteHarnessRunContinuityStore",
    "SQLiteHarnessAgentBridge",
    "SQLiteHarnessRuntimeBridge",
    "StandaloneHarnessRunner",
    "IndependentHarnessRunReceipt",
    "IndependentCompletionProposal",
}
REQUIRED_MEMBERS = {
    "ordivon_harness/agent_tool_observation.py",
    "ordivon_harness/core.py",
    "ordivon_harness/api.py",
    "ordivon_harness/core_contracts.py",
    "ordivon_harness/domain_tools.py",
    "ordivon_harness/errors.py",
    "ordivon_harness/execution_binding.py",
    "ordivon_harness/independent_result.py",
    "ordivon_harness/runtime_port.py",
    "ordivon_harness/sqlite_store.py",
    "ordivon_harness/standalone.py",
    "ordivon_harness/store.py",
    "ordivon_harness/store_ops.py",
    "ordivon_harness/version.py",
    "ordivon_harness/ordivon/continuity_records.py",
    "ordivon_harness/ordivon/run_recovery.py",
    "ordivon_harness/ordivon/run_store_port.py",
    "ordivon_harness/ordivon/sqlite_agent_bridge.py",
    "ordivon_harness/ordivon/sqlite_run_store.py",
    "ordivon_harness/ordivon/sqlite_runtime_bridge.py",
    "ordivon_harness/ordivon/runtime_lowering.py",
    "ordivon_harness/ordivon/tool_bridge.py",
    "ordivon_harness/ordivon/tool_errors.py",
}


def fail(message: str) -> None:
    print(f"wheel: {message}", file=sys.stderr)
    raise SystemExit(1)


def resolve_wheel(value: str) -> Path:
    path = Path(value).resolve()
    if path.is_file() and path.suffix == ".whl":
        return path
    if not path.is_dir():
        fail(f"wheel path does not exist: {path}")
    wheels = sorted(path.glob("*.whl"))
    if len(wheels) != 1:
        fail(f"expected exactly one wheel in {path}, observed {len(wheels)}")
    return wheels[0]


def run_checked(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(arguments, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        fail(f"command failed ({result.returncode}): {' '.join(arguments)}")
    return result


def validate_metadata(wheel: Path) -> tuple[str, tuple[str, ...]]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        entry_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        license_names = [name for name in names if name.endswith(".dist-info/licenses/LICENSE")]
        if len(metadata_names) != 1 or len(entry_names) != 1 or len(license_names) != 1:
            fail("wheel must contain one METADATA, entry_points.txt and Apache LICENSE")
        missing = sorted(REQUIRED_MEMBERS - names)
        if missing:
            fail("wheel lacks required modules: " + ", ".join(missing))
        metadata = BytesParser(policy=policy.default).parsebytes(archive.read(metadata_names[0]))
        entries = archive.read(entry_names[0]).decode("utf-8")

    if metadata.get("Name") != project["name"]:
        fail("wheel distribution name differs from pyproject")
    if metadata.get("Version") != version:
        fail("wheel version differs from pyproject")
    observed_python = metadata.get("Requires-Python")
    expected_python = project["requires-python"]

    def normalize_specifier(value: str) -> tuple[str, ...]:
        return tuple(sorted(part.strip() for part in value.split(",") if part.strip()))

    if not isinstance(observed_python, str) or normalize_specifier(
        observed_python
    ) != normalize_specifier(expected_python):
        fail("wheel Requires-Python differs from pyproject")
    if metadata.get("License-Expression") != project["license"]:
        fail("wheel license expression differs from pyproject")
    requirements = tuple(metadata.get_all("Requires-Dist", []))
    if len(requirements) != 2:
        fail(f"wheel must contain Protocol plus optional Host, observed {len(requirements)}")
    joined = "\n".join(requirements)
    protocol = project["dependencies"][0]
    protocol_name = protocol.split(" @ ", 1)[0]
    protocol_revision = protocol.rsplit("@", 1)[-1].split("#", 1)[0]
    if protocol_name not in joined or protocol_revision not in joined:
        fail("wheel metadata lacks the exact base Protocol dependency")
    host = project["optional-dependencies"]["host"][0]
    host_name = host.split(" @ ", 1)[0]
    host_revision = host.rsplit("@", 1)[-1].split("#", 1)[0]
    host_requirements = [item for item in requirements if host_name in item]
    if (
        len(host_requirements) != 1
        or host_revision not in host_requirements[0]
        or not any(
            marker in host_requirements[0]
            for marker in ("extra == 'host'", 'extra == "host"')
        )
    ):
        fail("wheel metadata lacks the exact optional Host integration dependency")
    if "ordivon-harness = ordivon_harness.cli:entrypoint" not in entries:
        fail("wheel entry point differs from the public CLI contract")
    return version, requirements


def install_smoke(wheel: Path, version: str) -> dict[str, object]:
    uv = shutil.which("uv")
    if uv is None:
        fail("uv is required for isolated wheel installation")
    with tempfile.TemporaryDirectory(prefix="ordivon-harness-wheel-") as directory:
        root = Path(directory)
        run_checked([uv, "venv", "--python", "3.12", str(root)])
        python = root / "bin" / "python"
        cli = root / "bin" / "ordivon-harness"
        run_checked(
            [
                uv,
                "pip",
                "install",
                "--link-mode",
                "copy",
                "--python",
                str(python),
                str(wheel),
            ]
        )
        core_probe = run_checked(
            [
                str(python),
                "-c",
                (
                    "import importlib.metadata as m,importlib.util,json; "
                    "import ordivon_harness.core as core; "
                    "print(json.dumps({'version':m.version('ordivon-harness'),"
                    "'core':sorted(core.__all__),"
                    "'hostInstalled':importlib.util.find_spec('ordivon_host') is not None}))"
                ),
            ]
        )
        observed_core = json.loads(core_probe.stdout)
        if observed_core.get("version") != version:
            fail("installed Core distribution version differs from wheel metadata")
        if not REQUIRED_CORE_API.issubset(set(observed_core.get("core", []))):
            fail("installed Core API lacks required independent symbols")
        if observed_core.get("hostInstalled") is not False:
            fail("base wheel installation unexpectedly installed Host")
        run_checked([str(python), str(ROOT / "scripts/check_core_without_host.py")])
        help_text = run_checked([str(cli), "--help"]).stdout
        for command in ("store-init", "store-doctor", "store-inspect", "store-events"):
            if command not in help_text:
                fail(f"Host-free CLI help lacks independent command: {command}")

        run_checked(
            [
                uv,
                "pip",
                "install",
                "--link-mode",
                "copy",
                "--python",
                str(python),
                f"ordivon-harness[host] @ {wheel.as_uri()}",
            ]
        )
        host_probe = run_checked(
            [
                str(python),
                "-c",
                (
                    "import importlib.util,json; import ordivon_harness.api as api; "
                    "print(json.dumps({'api':sorted(api.__all__),"
                    "'hostInstalled':importlib.util.find_spec('ordivon_host') is not None}))"
                ),
            ]
        )
        observed_host = json.loads(host_probe.stdout)
        if set(observed_host.get("api", [])) != EXPECTED_API:
            fail("installed Host public API differs from the repository contract")
        if observed_host.get("hostInstalled") is not True:
            fail("Host extra did not install ordivon-host")
        commands = (
            "doctor", "status", "inspect", "handoff", "run", "resume", "cancel",
            "recover", "store-init", "store-doctor", "store-inspect", "store-events",
            "store-backup", "store-verify-backup", "store-restore",
        )
        for command in commands:
            if command not in help_text:
                fail(f"installed CLI help lacks command: {command}")
        return {
            "installedVersion": observed_core["version"],
            "coreApiRequired": sorted(REQUIRED_CORE_API),
            "hostApi": observed_host["api"],
            "hostFreeCoreVerified": True,
            "hostExtraVerified": True,
            "cliCommandsVerified": len(commands),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate wheel metadata and perform an isolated installation smoke test."
    )
    parser.add_argument("wheel", help="wheel file or directory containing exactly one wheel")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="validate archive metadata without installing dependencies",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wheel = resolve_wheel(args.wheel)
    version, requirements = validate_metadata(wheel)
    result: dict[str, object] = {
        "status": "passed",
        "wheel": wheel.name,
        "version": version,
        "requirements": list(requirements),
        "metadataOnly": bool(args.metadata_only),
    }
    if not args.metadata_only:
        result.update(install_smoke(wheel, version))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

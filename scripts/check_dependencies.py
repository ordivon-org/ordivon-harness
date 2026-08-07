#!/usr/bin/env python3
"""Validate the exact Harness dependency graph and lockfile truth."""

from __future__ import annotations

import re
import sys
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
HOST_REVISION = "428a6f2f90b4050535507c9be078c450552177e5"
PROTOCOL_REVISION = "420dc356cb664d75db0f34f356156baebe5843db"


def fail(message: str) -> None:
    print(f"dependencies: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list):
        fail("project dependencies are missing")
    expected_host = (
        "ordivon-host @ git+https://github.com/zycxfyh/ordivon-host.git@"
        + HOST_REVISION
    )
    expected_protocol = (
        "ordivon-protocol @ git+https://github.com/zycxfyh/ordivon-computing.git@"
        + PROTOCOL_REVISION
        + "#subdirectory=packages/ordivon-protocol"
    )
    if dependencies != [expected_protocol]:
        fail("base dependencies must contain only the exact Protocol graph")
    optional = project.get("optional-dependencies")
    if not isinstance(optional, dict) or optional.get("host") != [expected_host]:
        fail("Host integration extra differs from the canonical exact graph")
    groups = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8")).get(
        "dependency-groups"
    )
    if not isinstance(groups, dict) or groups.get("dev") != [expected_host]:
        fail("development dependency group must install the exact Host graph")

    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    for revision, label in (
        (HOST_REVISION, "Host"),
        (PROTOCOL_REVISION, "Protocol"),
    ):
        if f"rev={revision}" not in lock or f"#{revision}" not in lock:
            fail(f"uv.lock does not bind the exact {label} revision")

    audit = [
        line.strip()
        for line in (ROOT / "requirements-audit.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if audit:
        fail(
            "requirements-audit.txt must contain only third-party PyPI runtime "
            "dependencies; current exact Git dependencies are audited by repository gates"
        )

    compat = (ROOT / "src/ordivon_harness/_host_compat/__init__.py").read_text(
        encoding="utf-8"
    )
    if f'HOST_REQUIRED_SOURCE_REVISION = "{HOST_REVISION}"' not in compat:
        fail("private Host compatibility metadata differs from the dependency pin")
    if f'PROTOCOL_REQUIRED_SOURCE_REVISION = "{PROTOCOL_REVISION}"' not in compat:
        fail("private Protocol compatibility metadata differs from the dependency pin")

    version_match = re.search(r'^version = "([^"]+)"$', (ROOT / "pyproject.toml").read_text(), re.MULTILINE)
    fallback_match = re.search(
        r'^_FALLBACK_VERSION = "([^"]+)"$',
        (ROOT / "src/ordivon_harness/version.py").read_text(),
        re.MULTILINE,
    )
    if version_match is None or fallback_match is None or version_match.group(1) != fallback_match.group(1):
        fail("package version and source-checkout fallback differ")

    print(
        f"dependency contract: valid base=protocol@{PROTOCOL_REVISION} "
        f"host-extra={HOST_REVISION}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

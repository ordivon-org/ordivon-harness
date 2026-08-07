#!/usr/bin/env python3
"""Validate the exact Host-free Harness dependency graph and lockfile truth."""

from __future__ import annotations

import re
import sys
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_REVISION = "420dc356cb664d75db0f34f356156baebe5843db"


def fail(message: str) -> None:
    print(f"dependencies: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    raw = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = raw["project"]
    expected_protocol = (
        "ordivon-protocol @ git+https://github.com/zycxfyh/ordivon-computing.git@"
        + PROTOCOL_REVISION
        + "#subdirectory=packages/ordivon-protocol"
    )
    if project.get("dependencies") != [expected_protocol]:
        fail("base dependencies must contain only the exact Protocol graph")
    if "optional-dependencies" in project:
        fail("Harness must not expose compatibility dependency extras")
    if "dependency-groups" in raw:
        fail("Harness repository must not require Host development dependencies")

    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    if f"rev={PROTOCOL_REVISION}" not in lock or f"#{PROTOCOL_REVISION}" not in lock:
        fail("uv.lock does not bind the exact Protocol revision")
    if "ordivon-host" in lock or "ordivon_host" in lock:
        fail("uv.lock still contains Ordivon Host")

    audit = [
        line.strip()
        for line in (ROOT / "requirements-audit.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if audit:
        fail("requirements-audit.txt must contain only third-party PyPI runtime dependencies")

    version_match = re.search(
        r'^version = "([^"]+)"$',
        (ROOT / "pyproject.toml").read_text(),
        re.MULTILINE,
    )
    fallback_match = re.search(
        r'^_FALLBACK_VERSION = "([^"]+)"$',
        (ROOT / "src/ordivon_harness/version.py").read_text(),
        re.MULTILINE,
    )
    if (
        version_match is None
        or fallback_match is None
        or version_match.group(1) != fallback_match.group(1)
    ):
        fail("package version and source-checkout fallback differ")

    print(f"dependency contract: valid protocol={PROTOCOL_REVISION} host=absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

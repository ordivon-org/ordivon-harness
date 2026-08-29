#!/usr/bin/env python3
"""Verify the physical executable realization required by runtime-search."""

from __future__ import annotations

import json
import os

from ordivon_harness.ordivon.runtime_lowering import RUNTIME_SEARCH_EXECUTABLES


def main() -> int:
    rows = []
    missing = []
    for name, path in sorted(RUNTIME_SEARCH_EXECUTABLES.items()):
        executable = os.path.isfile(path) and os.access(path, os.X_OK)
        rows.append({"name": name, "path": path, "executable": executable})
        if not executable:
            missing.append(path)
    document = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-runtime-search-physical-profile",
        "status": "passed" if not missing else "failed",
        "executables": rows,
        "missing": missing,
    }
    print(json.dumps(document, sort_keys=True))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())

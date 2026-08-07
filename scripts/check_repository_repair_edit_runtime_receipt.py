from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from anc_canonical import canonical_digest

EXPECTED_IMPLEMENTATION_REVISION = "dd50136ef722b9df3dfb0fef195fcc1a137fd8ed"
EXPECTED_SURFACE_DIGEST = (
    "sha256:fc2daeee2a95ff5d83d4efbc17a003788c52277ec582be3a14c34662cf1d51eb"
)
EXPECTED_GRANT_DIGEST = (
    "sha256:6c3a0a889c6082448b9e685f3388845e28e1b9ce226e95ad6404835324b37bec"
)
EXPECTED_CHECKS = {
    "allToolObservationsObserved",
    "candidateCompleted",
    "completionFileCreated",
    "diffObserved",
    "eightModelCalls",
    "harnessDoctorHealthy",
    "oneRuntimeJob",
    "prematureConclusionCorrected",
    "runtimeOperationsExact",
    "sixToolCalls",
    "sourceReplacementApplied",
    "visibleCheckSucceeded",
}
EXPECTED_LIMITS = [
    "This acceptance proves only the separate repository-repair edit V2 Tool surface",
    "The Provider is scripted and the acceptance does not claim model capability",
    "This V2 receipt does not resume or alter the frozen B5 comparison campaign",
    "Hidden verification and Host semantic acceptance remain separate responsibilities",
]
EXPECTED_FIELDS = {
    "schemaVersion",
    "kind",
    "implementationRevision",
    "harnessRevision",
    "harnessClean",
    "toolSurfaceDigest",
    "toolGrantDigest",
    "sourceRevision",
    "sourceAllocationDigest",
    "modelCalls",
    "toolCalls",
    "runtimeJobCount",
    "harnessEventCount",
    "traceDigest",
    "checks",
    "workspaceClosed",
    "productionActivated",
    "b6Implemented",
    "knownLimits",
    "integrity",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("receipt must be a JSON object")
    return value


def validate_receipt(path: Path) -> dict[str, Any]:
    value = _load(path)
    if set(value) != EXPECTED_FIELDS:
        raise ValueError("receipt fields differ")
    integrity = value.get("integrity")
    if not isinstance(integrity, dict) or set(integrity) != {
        "algorithm",
        "canonicalization",
        "payloadDigest",
    }:
        raise ValueError("receipt integrity fields differ")
    payload = dict(value)
    payload.pop("integrity")
    if integrity["algorithm"] != "sha256" or integrity["canonicalization"] != (
        "ordivon-evidence-json-v1"
    ):
        raise ValueError("receipt integrity contract differs")
    if integrity["payloadDigest"] != canonical_digest(payload):
        raise ValueError("receipt integrity differs")
    if value["schemaVersion"] != 1 or value["kind"] != (
        "ordivon.harness-repository-repair-edit-runtime-acceptance"
    ):
        raise ValueError("receipt kind or version differs")
    if value["implementationRevision"] != EXPECTED_IMPLEMENTATION_REVISION:
        raise ValueError("implementation revision differs")
    if value["harnessRevision"] != EXPECTED_IMPLEMENTATION_REVISION:
        raise ValueError("Harness revision differs")
    if value["harnessClean"] is not True:
        raise ValueError("acceptance did not run from a clean Harness revision")
    if value["toolSurfaceDigest"] != EXPECTED_SURFACE_DIGEST:
        raise ValueError("V2 Tool surface digest differs")
    if value["toolGrantDigest"] != EXPECTED_GRANT_DIGEST:
        raise ValueError("V2 Tool grant digest differs")
    if value["modelCalls"] != 8 or value["toolCalls"] != 6:
        raise ValueError("scripted acceptance call counts differ")
    if value["runtimeJobCount"] != 1 or value["harnessEventCount"] != 37:
        raise ValueError("Runtime Job or Harness Event count differs")
    checks = value["checks"]
    if not isinstance(checks, dict) or set(checks) != EXPECTED_CHECKS:
        raise ValueError("acceptance checks differ")
    if any(item is not True for item in checks.values()):
        raise ValueError("one or more acceptance checks failed")
    if value["workspaceClosed"] is not True:
        raise ValueError("Runtime Workspace was not closed")
    if value["productionActivated"] is not False:
        raise ValueError("acceptance must not activate production")
    if value["b6Implemented"] is not False:
        raise ValueError("acceptance must not claim B6")
    if value["knownLimits"] != EXPECTED_LIMITS:
        raise ValueError("known limits differ")
    for field in ("sourceAllocationDigest", "traceDigest"):
        digest = value[field]
        if not isinstance(digest, str) or len(digest) != 71 or not digest.startswith(
            "sha256:"
        ):
            raise ValueError(f"{field} is not a sha256 digest")
    source_revision = value["sourceRevision"]
    if not isinstance(source_revision, str) or len(source_revision) != 40:
        raise ValueError("source revision differs")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the frozen pre-A0 V2 edit receipt")
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    value = validate_receipt(args.receipt)
    print(
        json.dumps(
            {
                "kind": value["kind"],
                "implementationRevision": value["implementationRevision"],
                "payloadDigest": value["integrity"]["payloadDigest"],
                "status": "historical",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

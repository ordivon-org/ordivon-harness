#!/usr/bin/env python3
"""Validate the Harness claim-to-evidence index and historical receipt bindings."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
_VERIFIED_IMPLEMENTATION_PATHS = (
    "src/",
    "pyproject.toml",
    "uv.lock",
    "scripts/harness_p0_scale_acceptance.py",
)


def _canonical_payload_digest(value: dict[str, object]) -> str:
    payload = dict(value)
    payload.pop("integrity", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _verified_revision_is_current(revision: str) -> tuple[bool, list[str]]:
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        cwd=ROOT,
        check=False,
    )
    if ancestor.returncode != 0:
        return False, []
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{revision}..HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).splitlines()
    invalidating = [
        path
        for path in changed
        if any(path == prefix or path.startswith(prefix) for prefix in _VERIFIED_IMPLEMENTATION_PATHS)
    ]
    return not invalidating, invalidating


def main() -> int:
    errors: list[str] = []
    index_path = EVIDENCE / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"evidence: cannot read index: {error}", file=sys.stderr)
        return 1
    if index.get("kind") != "ordivon.harness-evidence-index":
        errors.append("index kind is invalid")
    entries = index.get("entries")
    if not isinstance(entries, list):
        errors.append("index entries are missing")
        entries = []
    claim_ids: set[str] = set()
    files: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("one evidence entry is not an object")
            continue
        claim_id = entry.get("claimId")
        filename = entry.get("file")
        revision = entry.get("implementationRevision")
        status = entry.get("status")
        if not isinstance(claim_id, str) or not claim_id:
            errors.append("one evidence entry has no claimId")
            continue
        if claim_id in claim_ids:
            errors.append(f"duplicate claimId: {claim_id}")
        claim_ids.add(claim_id)
        if not isinstance(filename, str) or filename in files:
            errors.append(f"invalid or duplicate evidence file for {claim_id}")
            continue
        files.add(filename)
        if status not in {"historical", "verified"}:
            errors.append(f"unsupported evidence status for {claim_id}: {status}")
        if not isinstance(revision, str) or len(revision) != 40:
            errors.append(f"invalid implementation revision: {claim_id}")
            continue
        path = EVIDENCE / filename
        if not path.is_file():
            errors.append(f"missing evidence file: {filename}")
            continue
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            errors.append(f"invalid JSON {filename}: {error}")
            continue
        observed = (
            receipt.get("implementationSourceRevision")
            or receipt.get("implementationRevision")
            or receipt.get("sourceRevision")
        )
        if observed != revision:
            errors.append(
                f"revision mismatch for {filename}: index={revision} receipt={observed}"
            )
        integrity = receipt.get("integrity")
        if integrity is not None and not isinstance(integrity, dict):
            errors.append(f"invalid integrity object: {filename}")
        if isinstance(integrity, dict) and receipt.get("kind") in {
            "ordivon.harness-p0-scale-acceptance",
            "ordivon.harness-c3-agent-first-api-acceptance",
            "ordivon.harness-h3-independent-product-acceptance",
        }:
            if integrity.get("payloadDigest") != _canonical_payload_digest(receipt):
                errors.append(f"integrity mismatch: {filename}")
        if receipt.get("kind") == "ordivon.harness-c3-agent-first-api-acceptance":
            checks = receipt.get("checks")
            expected_changed = {
                "CHANGELOG.md",
                "README.md",
                "docs/COMPATIBILITY.md",
                "docs/QUICKSTART.md",
                "pyproject.toml",
                "scripts/check_docs.py",
                "scripts/check_wheel.py",
                "src/ordivon_harness/api.py",
                "src/ordivon_harness/host_api.py",
                "tests/test_public_api.py",
            }
            if set(receipt.get("changedPaths", [])) != expected_changed:
                errors.append("C3 API receipt changed-path set differs")
            if not isinstance(checks, dict):
                errors.append("C3 API receipt checks are missing")
            else:
                for required_check in (
                    "fullRegressionPassed",
                    "documentationContractPassed",
                    "dependencyContractPassed",
                    "recommendedApiHostFreeInBaseWheel",
                    "hostCompatibilityFacadePassedWithHostExtra",
                    "deterministicDemoPassed",
                    "wheelSmokePassed",
                ):
                    if checks.get(required_check) is not True:
                        errors.append(f"C3 API receipt failed check: {required_check}")
                for forbidden_change in (
                    "productionCutoverActivated",
                    "dualWriteActivated",
                    "legacyWriterRemoved",
                    "durableRunStateModulesChanged",
                ):
                    if checks.get(forbidden_change) is not False:
                        errors.append(f"C3 API receipt changed forbidden state: {forbidden_change}")
                if checks.get("cliCommandsVerified") != 19:
                    errors.append("C3 API receipt CLI command count differs")
        if status == "verified":
            current, invalidating = _verified_revision_is_current(revision)
            if not current:
                errors.append(
                    f"verified receipt is stale for {claim_id}: "
                    f"invalidating={invalidating}"
                )

    receipt_files = {
        path.name for path in EVIDENCE.glob("*.json") if path.name != "index.json"
    }
    if files != receipt_files:
        errors.append(
            "evidence index/file set differs: "
            f"missing={sorted(receipt_files - files)} extra={sorted(files - receipt_files)}"
        )
    if errors:
        for error in errors:
            print(f"evidence: {error}", file=sys.stderr)
        return 1
    historical = sum(entry.get("status") == "historical" for entry in entries)
    verified = sum(entry.get("status") == "verified" for entry in entries)
    print(
        "evidence contract: valid "
        f"historical_receipts={historical} verified_receipts={verified}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

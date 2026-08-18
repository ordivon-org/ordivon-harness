#!/usr/bin/env python3
"""Validate Harness evidence/file correspondence and revision/currentness bindings."""

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
_INDEX_REVISION_HINT_FIELDS = (
    "implementationSourceRevision",
    "implementationRevision",
    "sourceRevision",
    "prebindingRevision",
    "repairCommit",
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


def _invalidating_paths(revision_from: str, revision_to: str) -> list[str]:
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", f"{revision_from}..{revision_to}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).splitlines()
    return [
        path
        for path in changed
        if any(
            path == prefix or path.startswith(prefix)
            for prefix in _VERIFIED_IMPLEMENTATION_PATHS
        )
    ]


def _verified_revision_is_current(revision: str) -> tuple[bool, list[str]]:
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        cwd=ROOT,
        check=False,
    )
    if ancestor.returncode != 0:
        return False, []
    invalidating = _invalidating_paths(revision, "HEAD")
    return not invalidating, invalidating


def _validate_index_creation_lineage_binding(
    filename: str,
    revision: str,
) -> list[str]:
    """Validate external revision binding for one immutable evidence projection."""

    errors: list[str] = []
    path = EVIDENCE / filename
    relative_path = path.relative_to(ROOT).as_posix()
    try:
        creation_revisions = subprocess.check_output(
            [
                "git",
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--",
                relative_path,
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).splitlines()
    except subprocess.CalledProcessError as error:
        return [f"cannot inspect evidence creation lineage for {filename}: {error}"]
    if len(creation_revisions) != 1:
        return [
            f"index-bound evidence must have exactly one creation commit for {filename}: "
            f"found={creation_revisions}"
        ]
    creation_revision = creation_revisions[0]
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, creation_revision],
        cwd=ROOT,
        check=False,
    )
    if ancestor.returncode != 0:
        errors.append(
            f"index-bound revision is not an ancestor of evidence creation for {filename}: "
            f"revision={revision} creation={creation_revision}"
        )
        return errors
    invalidating = _invalidating_paths(revision, creation_revision)
    if invalidating:
        errors.append(
            f"implementation changed before index-bound evidence creation for {filename}: "
            f"invalidating={invalidating}"
        )
    try:
        created_bytes = subprocess.check_output(
            ["git", "show", f"{creation_revision}:{relative_path}"],
            cwd=ROOT,
        )
        current_bytes = path.read_bytes()
    except (subprocess.CalledProcessError, OSError) as error:
        errors.append(f"cannot verify immutable evidence bytes for {filename}: {error}")
    else:
        if created_bytes != current_bytes:
            errors.append(
                f"index-bound evidence bytes changed after creation for {filename}: "
                f"creation={creation_revision}"
            )
    return errors


def _recognized_revision_hints(receipt: dict[str, object]) -> dict[str, str]:
    return {
        field: value
        for field in _INDEX_REVISION_HINT_FIELDS
        if isinstance((value := receipt.get(field)), str) and len(value) == 40
    }


def _validate_embedded_revision_binding(
    filename: str,
    receipt: dict[str, object],
    revision: str,
) -> list[str]:
    observed = (
        receipt.get("implementationSourceRevision")
        or receipt.get("implementationRevision")
        or receipt.get("sourceRevision")
    )
    if observed == revision:
        return []
    return [f"revision mismatch for {filename}: index={revision} receipt={observed}"]


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
        revision_binding = entry.get("revisionBinding", "embedded")
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
        if revision_binding not in {"embedded", "index-creation-lineage"}:
            errors.append(
                f"unsupported revision binding for {claim_id}: {revision_binding}"
            )
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
        if revision_binding == "embedded":
            errors.extend(_validate_embedded_revision_binding(filename, receipt, revision))
        elif revision_binding == "index-creation-lineage":
            errors.extend(_validate_index_creation_lineage_binding(filename, revision))
            for field, observed in _recognized_revision_hints(receipt).items():
                if field in {"prebindingRevision", "repairCommit"} and observed != revision:
                    errors.append(
                        f"index-bound revision hint differs for {filename}: "
                        f"field={field} index={revision} evidence={observed}"
                    )
                if field in {
                    "implementationSourceRevision",
                    "implementationRevision",
                    "sourceRevision",
                } and observed != revision:
                    errors.append(
                        f"index-bound embedded implementation revision differs for {filename}: "
                        f"field={field} index={revision} evidence={observed}"
                    )
        integrity = receipt.get("integrity")
        if integrity is not None and not isinstance(integrity, dict):
            errors.append(f"invalid integrity object: {filename}")
        if isinstance(integrity, dict) and receipt.get("kind") in {
            "ordivon.harness-p0-scale-acceptance",
            "ordivon.harness-c3-agent-first-api-acceptance",
            "ordivon.harness-h3-independent-product-acceptance",
            "ordivon.harness-h4-stress-acceptance",
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

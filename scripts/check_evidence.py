#!/usr/bin/env python3
"""Validate the Harness claim-to-evidence index and historical receipt bindings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"


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
        if status != "historical":
            errors.append(f"existing repository receipt must be historical: {claim_id}")
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
        observed = receipt.get("implementationSourceRevision") or receipt.get(
            "sourceRevision"
        )
        if observed != revision:
            errors.append(
                f"revision mismatch for {filename}: index={revision} receipt={observed}"
            )
        integrity = receipt.get("integrity")
        if integrity is not None and not isinstance(integrity, dict):
            errors.append(f"invalid integrity object: {filename}")

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
    print(f"evidence contract: valid historical_receipts={len(entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

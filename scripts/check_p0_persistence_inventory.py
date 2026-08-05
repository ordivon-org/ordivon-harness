from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "specs" / "p0-persistence-inventory-v1.json"

MANDATORY_OBJECTS = {
    "harness-run-state",
    "harness-run-state-delta",
    "harness-provider-call-record",
    "agent-turn-result",
    "harness-provider-call-failure",
    "harness-tool-step-intent",
    "harness-dispatch-fence",
    "harness-tool-step-receipt",
    "harness-tool-observation",
    "harness-run-snapshot",
    "harness-trace",
    "agent-run-conclusion",
    "harness-run-receipt",
    "native-run-recovery-assessment",
    "native-run-abandonment",
    "completion-proposal",
    "completion-verification",
    "completion-decision",
    "task-outcome",
}

MANDATORY_EVENTS = {
    "harness.assignment-committed",
    "harness.run-recovery-recorded",
    "harness.run-abandoned",
    "harness.run-recorded",
    "harness.provider-call-claimed",
    "harness.provider-call-completed",
    "harness.provider-call-dispatching",
    "harness.provider-call-failed",
    "harness.provider-call-superseded",
    "harness.provider-call-unknown",
    "harness.tool-step-prepared",
    "harness.tool-step-recorded",
    "harness.run-snapshot-recorded",
    "completion.proposed",
    "completion.decided",
}


def canonical_digest(value: dict[str, Any]) -> str:
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


def check_inventory(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    issues: list[str] = []
    if value.get("schemaVersion") != 1:
        issues.append("schemaVersion must be 1")
    if value.get("kind") != "ordivon.harness-p0-persistence-inventory":
        issues.append("kind differs")
    if value.get("inventoryId") != "HHO-P0-A-001":
        issues.append("inventory identity differs")
    if value.get("status") != "frozen_before_migration":
        issues.append("inventory is not frozen before migration")

    objects = value.get("objects")
    events = value.get("events")
    if not isinstance(objects, list):
        issues.append("objects must be a list")
        objects = []
    if not isinstance(events, list):
        issues.append("events must be a list")
        events = []

    object_ids = [item.get("id") for item in objects if isinstance(item, dict)]
    if len(object_ids) != len(set(object_ids)):
        issues.append("object identities must be unique")
    missing_objects = sorted(MANDATORY_OBJECTS - set(object_ids))
    if missing_objects:
        issues.append(f"mandatory objects are missing: {missing_objects}")

    event_kinds = [item.get("eventKind") for item in events if isinstance(item, dict)]
    if len(event_kinds) != len(set(event_kinds)):
        issues.append("event kinds must be unique")
    missing_events = sorted(MANDATORY_EVENTS - set(event_kinds))
    if missing_events:
        issues.append(f"mandatory events are missing: {missing_events}")

    for item in objects:
        if not isinstance(item, dict):
            issues.append("object entry must be an object")
            continue
        required = {
            "id",
            "casKind",
            "semanticKind",
            "schemaVersions",
            "currentOwner",
            "p0Owner",
            "disposition",
            "sourcePath",
            "sourceLiteral",
            "privacyClass",
            "causalRole",
        }
        if set(item) != required:
            issues.append(f"object {item.get('id')} fields differ")
            continue
        source = ROOT / item["sourcePath"]
        if not source.is_file():
            issues.append(f"object source is missing: {item['sourcePath']}")
        elif item["sourceLiteral"] not in source.read_text(encoding="utf-8"):
            issues.append(
                f"object source literal is missing: {item['id']} -> {item['sourceLiteral']}"
            )
        versions = item["schemaVersions"]
        if (
            not isinstance(versions, list)
            or not versions
            or any(type(version) is not int or version < 1 for version in versions)
        ):
            issues.append(f"object schema versions are invalid: {item['id']}")

    for item in events:
        if not isinstance(item, dict):
            issues.append("event entry must be an object")
            continue
        required = {
            "eventKind",
            "currentOwner",
            "p0Owner",
            "disposition",
            "sourcePath",
        }
        if set(item) != required:
            issues.append(f"event {item.get('eventKind')} fields differ")
            continue
        source = ROOT / item["sourcePath"]
        if not source.is_file():
            issues.append(f"event source is missing: {item['sourcePath']}")
        elif item["eventKind"] not in source.read_text(encoding="utf-8"):
            issues.append(f"event source literal is missing: {item['eventKind']}")

    cutover = value.get("cutoverRules")
    if cutover != {
        "newRunDualWriteAllowed": False,
        "bulkRewriteHistoricalBytes": False,
        "activeLegacyRunAllowedAtDefaultCutover": False,
        "legacyReaderRequired": True,
    }:
        issues.append("cutover rules differ from the accepted P0 boundary")

    integrity = value.get("integrity")
    expected_integrity = {
        "algorithm": "sha256",
        "canonicalization": "ordivon-evidence-json-v1",
        "payloadDigest": canonical_digest(value),
    }
    if integrity != expected_integrity:
        issues.append("inventory integrity differs")

    return {
        "schemaVersion": 1,
        "kind": "ordivon.harness-p0-persistence-inventory-check",
        "ok": not issues,
        "objects": len(objects),
        "events": len(events),
        "issues": issues,
        "payloadDigest": expected_integrity["payloadDigest"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    report = check_inventory(args.path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

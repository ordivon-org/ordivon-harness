#!/usr/bin/env python3
"""Produce the HHO-P0 1,000-Run / 100,000-Event scale receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
from typing import Any

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.sqlite_store import SQLiteHarnessStore
from ordivon_harness.store import HarnessEventAdmission, HarnessEventWrite

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64


def _contract(index: int, created_at_ms: int) -> HarnessRunContract:
    suffix = f"{index:04d}"
    return HarnessRunContract(
        harness_run_id=f"harness-run:p0-scale:{suffix}",
        harness_implementation_id="ordivon-harness@p0-scale",
        caller_id="caller:p0-scale",
        caller_run_ref=f"trial:p0-scale:{suffix}",
        objective_ref=HarnessBoundReference(
            f"objective:p0-scale:{suffix}", "objective", DIGEST_A
        ),
        context_refs=(
            HarnessBoundReference(
                f"context:p0-scale:{suffix}", "context", DIGEST_B
            ),
        ),
        provider_id="provider:scale-fixture",
        adapter_id="adapter:scale-fixture-v1",
        requested_model_id="model:scale-fixture",
        tool_catalog_digest=DIGEST_C,
        tool_grant_digest=DIGEST_D,
        budget={"maxModelCalls": 1, "maxToolCalls": 0},
        completion_contract={"mode": "scale-fixture"},
        system_manifest_ref=HarnessBoundReference(
            f"system-manifest:p0-scale:{suffix}", "system-manifest", DIGEST_A
        ),
        created_at_ms=created_at_ms,
    )


def _canonical_digest(value: dict[str, Any]) -> str:
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


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def _revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()


def _counts(database: Path) -> tuple[int, int, int]:
    connection = sqlite3.connect(database)
    try:
        runs = int(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
        events = int(connection.execute("SELECT COUNT(*) FROM run_events").fetchone()[0])
        objects = int(connection.execute("SELECT COUNT(*) FROM object_refs").fetchone()[0])
        return runs, events, objects
    finally:
        connection.close()


def run_acceptance(
    *,
    root: Path,
    run_count: int,
    events_per_run: int,
    batch_size: int,
    inspect_samples: int,
    max_write_ms: int,
    max_reopen_ms: int,
    max_inspect_p95_ms: int,
) -> dict[str, Any]:
    if run_count < 1 or events_per_run < 2:
        raise ValueError("scale acceptance requires positive Runs and at least two Events per Run")
    if not 1 <= batch_size <= 256:
        raise ValueError("batch size must be between 1 and 256")
    if inspect_samples < 1:
        raise ValueError("inspect sample count must be positive")

    started_at_ms = time.time_ns() // 1_000_000
    write_started = time.perf_counter_ns()
    with SQLiteHarnessStore.initialize(root) as store:
        for run_index in range(run_count):
            created_at_ms = 1_000_000 + run_index * (events_per_run + 2)
            contract = _contract(run_index, created_at_ms)
            if store.create_run(contract) is not HarnessEventAdmission.CREATED:
                raise AssertionError("fresh scale Run unexpectedly existed")
            remaining = events_per_run - 1
            next_event = 0
            while remaining:
                count = min(remaining, batch_size)
                projection = store.load_run(contract.harness_run_id)
                lease = store.acquire_run_lease(
                    contract.harness_run_id,
                    owner_id=f"scale:{run_index}:{next_event}",
                    ttl_ms=60_000,
                    now_ms=created_at_ms + 1 + next_event,
                )
                events = tuple(
                    HarnessEventWrite(
                        event_id=f"event:p0-scale:{run_index:04d}:{next_event + offset:04d}",
                        event_kind="harness.trace-recorded",
                        data={"kind": "scale-trace"},
                        recorded_at_ms=created_at_ms + 1 + next_event + offset,
                    )
                    for offset in range(count)
                )
                admission = store.append_events(
                    harness_run_id=contract.harness_run_id,
                    events=events,
                    expected_revision=projection.revision,
                    lease=lease,
                    lease_checked_at_ms=created_at_ms + 1 + next_event,
                )
                if admission is not HarnessEventAdmission.CREATED:
                    raise AssertionError("fresh scale Event batch unexpectedly existed")
                next_event += count
                remaining -= count
    write_elapsed_ms = (time.perf_counter_ns() - write_started) / 1_000_000

    database = root / "harness.sqlite3"
    actual_runs, actual_events, object_count = _counts(database)
    expected_events = run_count * events_per_run

    reopen_started = time.perf_counter_ns()
    with SQLiteHarnessStore(root) as reopened:
        doctor = reopened.doctor(full=True)
        inspect_latencies_ms: list[float] = []
        samples = min(run_count, inspect_samples)
        for sample in range(samples):
            run_index = (sample * run_count) // samples
            run_id = f"harness-run:p0-scale:{run_index:04d}"
            inspect_started = time.perf_counter_ns()
            projection = reopened.load_run(run_id)
            events = reopened.list_run_events(run_id)
            inspect_latencies_ms.append(
                (time.perf_counter_ns() - inspect_started) / 1_000_000
            )
            if projection.revision != events_per_run or len(events) != events_per_run:
                raise AssertionError("scale Run projection differs from event history")
    reopen_elapsed_ms = (time.perf_counter_ns() - reopen_started) / 1_000_000

    object_files = tuple((root / "objects").glob("*.json"))
    checks = {
        "runCountExact": actual_runs == run_count,
        "eventCountExact": actual_events == expected_events,
        "doctorHealthy": doctor.get("healthy") is True,
        "doctorCountsExact": (
            doctor.get("runs") == run_count and doctor.get("events") == expected_events
        ),
        "objectReferenceCountMatchesFiles": object_count == len(object_files),
        "writeWithinBound": write_elapsed_ms <= max_write_ms,
        "reopenAndFullDoctorWithinBound": reopen_elapsed_ms <= max_reopen_ms,
        "inspectP95UnderBound": (
            _percentile(inspect_latencies_ms, 0.95) <= max_inspect_p95_ms
        ),
    }
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": "ordivon.harness-p0-scale-acceptance",
        "implementationRevision": _revision(),
        "configuration": {
            "runCount": run_count,
            "eventsPerRun": events_per_run,
            "expectedEventCount": expected_events,
            "batchSize": batch_size,
            "inspectSamples": min(run_count, inspect_samples),
            "sqliteSynchronous": "FULL",
            "sqliteJournalMode": "WAL",
            "maxWriteMs": max_write_ms,
            "maxReopenMs": max_reopen_ms,
            "maxInspectP95Ms": max_inspect_p95_ms,
        },
        "measurements": {
            "writeElapsedMs": round(write_elapsed_ms, 3),
            "reopenAndFullDoctorElapsedMs": round(reopen_elapsed_ms, 3),
            "inspectP50Ms": round(_percentile(inspect_latencies_ms, 0.50), 3),
            "inspectP95Ms": round(_percentile(inspect_latencies_ms, 0.95), 3),
            "databaseBytes": database.stat().st_size,
            "objectFiles": len(object_files),
            "objectReferenceRows": object_count,
        },
        "counts": {
            "runs": actual_runs,
            "events": actual_events,
            "objects": object_count,
        },
        "checks": checks,
        "passed": all(checks.values()),
        "startedAtMs": started_at_ms,
        "finishedAtMs": time.time_ns() // 1_000_000,
    }
    receipt["integrity"] = {
        "algorithm": "sha256",
        "canonicalization": "ordivon-evidence-json-v1",
        "payloadDigest": _canonical_digest(receipt),
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--runs", type=int, default=1_000)
    parser.add_argument("--events-per-run", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--inspect-samples", type=int, default=100)
    parser.add_argument("--max-write-ms", type=int, default=180_000)
    parser.add_argument("--max-reopen-ms", type=int, default=120_000)
    parser.add_argument("--max-inspect-p95-ms", type=int, default=1_000)
    args = parser.parse_args()

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.state_root is None:
        temporary = tempfile.TemporaryDirectory(prefix="ordivon-harness-p0-scale-")
        root = Path(temporary.name) / "state"
    else:
        root = args.state_root.resolve()
        if root.exists():
            raise SystemExit(f"scale state root already exists: {root}")

    try:
        receipt = run_acceptance(
            root=root,
            run_count=args.runs,
            events_per_run=args.events_per_run,
            batch_size=args.batch_size,
            inspect_samples=args.inspect_samples,
            max_write_ms=args.max_write_ms,
            max_reopen_ms=args.max_reopen_ms,
            max_inspect_p95_ms=args.max_inspect_p95_ms,
        )
        encoded = json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
            args.output.chmod(0o600)
        print(encoded, end="")
        return 0 if receipt["passed"] else 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

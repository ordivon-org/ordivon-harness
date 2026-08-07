from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
from typing import Any
from urllib.parse import quote

from anc_canonical import canonical_digest as owner_digest, loads_strict

from .independent_result import IndependentHarnessRunReceipt
from .ordivon.continuity_records import HarnessDispatchFenceV2
from .protocol import HarnessDispatchFence, HarnessToolStepReceipt

MAPPING_VERSION = "harness-observation-v1"
PROJECT_ID = "ordivon-harness"
COMPONENT_ID = "harness-journal"
SCHEMA_VERSION = 1
_TYPED_KINDS = frozenset(
    {
        "harness-tool-step-receipt",
        "harness-dispatch-fence",
        "independent-harness-run-receipt",
    }
)


class HarnessObservationExportError(RuntimeError):
    pass


def _core() -> Any:
    try:
        import ordivon_observation_core as core
    except ImportError as error:
        raise HarnessObservationExportError(
            "install the exact ordivon-observation-core exporter contract"
        ) from error
    return core


def _revision(value: str, label: str) -> str:
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be an exact 40-character Git revision")
    return value


def _private_directory(path: Path, label: str, *, create: bool) -> Path:
    value = path.expanduser()
    if value.is_symlink():
        raise HarnessObservationExportError(f"{label} cannot be a symlink")
    if not value.exists():
        if not create:
            raise HarnessObservationExportError(f"{label} does not exist")
        value.mkdir(parents=True, mode=0o700)
        os.chmod(value, 0o700)
    resolved = value.resolve(strict=True)
    if not resolved.is_dir() or stat.S_IMODE(resolved.stat().st_mode) != 0o700:
        raise HarnessObservationExportError(f"{label} must be a private 0700 directory")
    return resolved


def _outside_owner(path: Path, owner_root: Path, label: str) -> None:
    resolved = path.expanduser().resolve(strict=False)
    if resolved == owner_root or owner_root in resolved.parents:
        raise HarnessObservationExportError(
            f"{label} must remain outside the Harness state root"
        )


def _database(root: Path) -> Path:
    database = root / "harness.sqlite3"
    if database.is_symlink() or not database.is_file():
        raise HarnessObservationExportError(
            "Harness database must be a regular non-symlink file"
        )
    if stat.S_IMODE(database.stat().st_mode) != 0o600:
        raise HarnessObservationExportError("Harness database must have mode 0600")
    return database


def _connection(database: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(database), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    row = connection.execute(
        "SELECT value FROM schema_info WHERE key='schema_version'"
    ).fetchone()
    if row is None or int(row["value"]) != SCHEMA_VERSION:
        connection.close()
        raise HarnessObservationExportError(
            f"Harness schema must be exactly {SCHEMA_VERSION}"
        )
    return connection


def _load_typed_object(
    objects_root: Path,
    digest: str,
    stored_kind: str,
) -> tuple[str, dict[str, Any]]:
    path = objects_root / f"{digest.removeprefix('sha256:')}.json"
    if path.is_symlink() or not path.is_file():
        raise HarnessObservationExportError(f"typed Harness object is absent: {digest}")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise HarnessObservationExportError(
            f"typed Harness object is not private: {digest}"
        )
    value = loads_strict(path.read_bytes())
    if owner_digest(value) != digest:
        raise HarnessObservationExportError(
            f"typed Harness object digest differs: {digest}"
        )
    if (
        not isinstance(value, dict)
        or set(value) != {"schemaVersion", "kind", "payload"}
        or value["schemaVersion"] != 1
        or value["kind"] != stored_kind
        or not isinstance(value["payload"], dict)
    ):
        raise HarnessObservationExportError(
            f"typed Harness object envelope differs: {digest}"
        )
    payload = value["payload"]
    try:
        if stored_kind == "harness-tool-step-receipt":
            receipt = HarnessToolStepReceipt.from_dict(payload)
            return stored_kind, {
                "harnessRunId": receipt.harness_run_id,
                "toolCallId": receipt.tool_call_id,
                "runtimeJobRef": receipt.runtime_job_ref,
            }
        if stored_kind == "independent-harness-run-receipt":
            receipt = IndependentHarnessRunReceipt.from_dict(payload)
            return stored_kind, {
                "harnessRunId": receipt.harness_run_id,
                "runtimeJobRefs": list(receipt.runtime_job_refs),
                "usage": dict(receipt.usage),
            }
        version = payload.get("schemaVersion")
        if version == 2:
            fence = HarnessDispatchFenceV2.from_dict(payload)
        elif version == 1:
            fence = HarnessDispatchFence.from_dict(payload)
        else:
            raise ValueError("Harness Dispatch Fence version is unsupported")
        return stored_kind, {
            "harnessRunId": fence.harness_run_id,
            "clientRequestId": fence.client_request_id,
        }
    except (TypeError, ValueError) as error:
        raise HarnessObservationExportError(
            f"typed Harness object is invalid: {digest}"
        ) from error


def _relations(
    core: Any,
    row: sqlite3.Row,
    refs: list[sqlite3.Row],
    typed: list[tuple[str, dict[str, Any]]],
) -> tuple[Any, ...]:
    values = [
        core.ObservationRelation(
            "belongs_to", "ordivon.harness.run", row["harness_run_id"]
        ),
        core.ObservationRelation(
            "requested_by", "ordivon.harness.caller", row["caller_id"]
        ),
    ]
    caller_kind = (
        "ordivon.host.external-request"
        if str(row["caller_run_ref"]).startswith("external-request:")
        else "ordivon.harness.caller-run"
    )
    values.append(
        core.ObservationRelation(
            "linked_to", caller_kind, row["caller_run_ref"]
        )
    )
    if row["caused_by_event_id"] is not None:
        values.append(
            core.ObservationRelation(
                "caused_by", "ordivon.harness.event", row["caused_by_event_id"]
            )
        )
    for ref in refs:
        if ref["role"] == "reference":
            values.append(
                core.ObservationRelation(
                    "references",
                    "ordivon.harness.object",
                    ref["digest"],
                    ref["digest"],
                )
            )
    for kind, item in typed:
        if kind == "harness-tool-step-receipt":
            values.append(
                core.ObservationRelation(
                    "linked_to",
                    "ordivon.harness.tool-call",
                    str(item["toolCallId"]),
                )
            )
            runtime_job = item["runtimeJobRef"]
            if runtime_job is not None:
                values.append(
                    core.ObservationRelation(
                        "executes", "ordivon.runtime.job", runtime_job
                    )
                )
        elif kind == "harness-dispatch-fence":
            values.append(
                core.ObservationRelation(
                    "requested_by",
                    "ordivon.runtime.client-request",
                    str(item["clientRequestId"]),
                )
            )
        elif kind == "independent-harness-run-receipt":
            runtime_jobs = item["runtimeJobRefs"]
            if not isinstance(runtime_jobs, list):
                raise HarnessObservationExportError(
                    "independent Harness Run Receipt Runtime Job refs are invalid"
                )
            for runtime_job in runtime_jobs:
                if not isinstance(runtime_job, str):
                    raise HarnessObservationExportError(
                        "independent Harness Run Receipt Runtime Job ref is invalid"
                    )
                values.append(
                    core.ObservationRelation(
                        "executes", "ordivon.runtime.job", runtime_job
                    )
                )
    return tuple(sorted(set(values)))


def _measurements(
    core: Any,
    typed: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for kind, item in typed:
        if kind != "independent-harness-run-receipt":
            continue
        usage = item.get("usage")
        if not isinstance(usage, dict):
            raise HarnessObservationExportError(
                "independent Harness Run Receipt usage is invalid"
            )
        mapping = {
            "modelCalls": ("ordivon.harness.model_calls", "1"),
            "toolCalls": ("ordivon.harness.tool_calls", "1"),
            "observationBytes": ("ordivon.harness.observation_bytes", "By"),
            "totalTokens": ("ordivon.harness.total_tokens", "token"),
            "wallTimeMs": ("ordivon.harness.wall_time", "ms"),
            "toolCorrections": ("ordivon.harness.tool_corrections", "1"),
        }
        for source, (target, unit) in mapping.items():
            value = usage.get(source)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise HarnessObservationExportError(
                    f"independent Harness Run Receipt {source} is not non-negative numeric"
                )
            result[target] = core.ObservationMeasurement(value=value, unit=unit)
    return result


def _read_events(
    state_root: Path,
    *,
    producer: Any,
    stream_id: str,
    after_sequence: int,
    limit: int,
) -> tuple[Any, ...]:
    core = _core()
    objects_root = state_root / "objects"
    if (
        objects_root.is_symlink()
        or not objects_root.is_dir()
        or stat.S_IMODE(objects_root.stat().st_mode) != 0o700
    ):
        raise HarnessObservationExportError(
            "Harness objects root must be a private directory"
        )
    connection = _connection(_database(state_root))
    try:
        connection.execute("BEGIN")
        rows = connection.execute(
            "SELECT e.sequence,e.event_id,e.harness_run_id,e.run_revision,"
            "e.event_kind,e.payload_digest,e.caused_by_event_id,e.recorded_at_ms,"
            "r.caller_id,r.caller_run_ref,r.contract_digest "
            "FROM run_events e JOIN runs r ON r.harness_run_id=e.harness_run_id "
            "WHERE e.sequence>? ORDER BY e.sequence LIMIT ?",
            (after_sequence, limit),
        ).fetchall()
        events: list[Any] = []
        for row in rows:
            refs = connection.execute(
                "SELECT rr.digest,rr.role,o.kind,o.byte_length FROM run_object_refs rr "
                "JOIN object_refs o ON o.digest=rr.digest WHERE rr.event_id=? "
                "ORDER BY rr.role,rr.digest",
                (row["event_id"],),
            ).fetchall()
            typed = [
                _load_typed_object(objects_root, ref["digest"], ref["kind"])
                for ref in refs
                if ref["role"] == "reference" and ref["kind"] in _TYPED_KINDS
            ]
            native = {
                "sequence": int(row["sequence"]),
                "eventId": row["event_id"],
                "harnessRunId": row["harness_run_id"],
                "runRevision": int(row["run_revision"]),
                "eventKind": row["event_kind"],
                "payloadDigest": row["payload_digest"],
                "causedByEventId": row["caused_by_event_id"],
                "recordedAtMs": int(row["recorded_at_ms"]),
                "callerId": row["caller_id"],
                "callerRunRef": row["caller_run_ref"],
                "contractDigest": row["contract_digest"],
                "references": [
                    {"digest": ref["digest"], "role": ref["role"], "kind": ref["kind"]}
                    for ref in refs
                ],
                "typedKeys": [item for _, item in typed],
            }
            source = core.ObservationSource(
                project_id=PROJECT_ID,
                component_id=COMPONENT_ID,
                instance_id=producer.instance_id,
                stream_id=stream_id,
                sequence=int(row["sequence"]),
                native_kind=f"ordivon.harness.{row['event_kind']}",
                native_id=row["event_id"],
                native_revision=int(row["run_revision"]),
                native_digest=core.canonical_digest(native),
                mapping_version=MAPPING_VERSION,
            )
            events.append(
                core.ObservationEnvelope.build(
                    occurred_at_ms=int(row["recorded_at_ms"]),
                    source=source,
                    relations=_relations(core, row, refs, typed),
                    attributes={
                        "eventKind": row["event_kind"],
                        "runRevision": int(row["run_revision"]),
                        "referenceCount": sum(ref["role"] == "reference" for ref in refs),
                        "typedKeyKinds": [kind for kind, _ in typed],
                    },
                    measurements=_measurements(core, typed),
                    privacy=core.ObservationPrivacy(
                        "private_content_ref", "harness-observation-metadata-v1"
                    ),
                    payload_ref=core.ObservationPayloadRef(
                        owner=PROJECT_ID,
                        kind="ordivon.harness.event-payload",
                        native_id=row["event_id"],
                        digest_value=row["payload_digest"],
                        locator_class="owner_cas",
                    ),
                )
            )
        connection.rollback()
        return tuple(events)
    finally:
        connection.close()


def export_harness_observations(
    *,
    state_root: str | Path,
    instance_id: str,
    checkpoint_path: str | Path,
    outbox_root: str | Path,
    owner_revision: str,
    exporter_revision: str,
    exported_at_ms: int,
    limit: int = 256,
    fail_after_bundle: bool = False,
) -> dict[str, Any]:
    core = _core()
    if not instance_id or instance_id != instance_id.strip():
        raise ValueError("instance_id must be non-empty and trimmed")
    if not 1 <= limit <= 10_000:
        raise ValueError("limit must be between 1 and 10000")
    _revision(owner_revision, "owner_revision")
    _revision(exporter_revision, "exporter_revision")
    if exported_at_ms < 0:
        raise ValueError("exported_at_ms must be non-negative")
    owner_root = _private_directory(Path(state_root), "Harness state root", create=False)
    checkpoint = Path(checkpoint_path)
    outbox = Path(outbox_root)
    _outside_owner(checkpoint, owner_root, "checkpoint")
    _outside_owner(outbox, owner_root, "outbox")
    producer = core.ObservationProducerIdentity(PROJECT_ID, COMPONENT_ID, instance_id)
    stream_id = f"harness-journal:{instance_id}"
    before = core.load_checkpoint(
        checkpoint, producer_identity=producer, mapping_version=MAPPING_VERSION
    )
    events = _read_events(
        owner_root,
        producer=producer,
        stream_id=stream_id,
        after_sequence=before.sequence(stream_id),
        limit=limit,
    )
    if not events:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-observation-export-result",
            "status": "no_events",
            "eventCount": 0,
            "lastSequence": before.sequence(stream_id),
            "checkpointDigest": before.integrity_digest,
            "bundlePath": None,
            "bundleDigest": None,
        }
    after = before.advance(
        {stream_id: events[-1].source.sequence}, updated_at_ms=exported_at_ms
    )
    batches = tuple(
        core.ObservationBatch.build(
            request_id=(
                f"harness-observation:{instance_id}:"
                f"{chunk[0].source.sequence}-{chunk[-1].source.sequence}"
            ),
            events=chunk,
        )
        for offset in range(0, len(events), core.MAX_BATCH_EVENTS)
        if (chunk := events[offset : offset + core.MAX_BATCH_EVENTS])
    )
    bundle = core.ObservationExportBundle.build(
        producer_identity=producer,
        mapping_version=MAPPING_VERSION,
        owner_revision=owner_revision,
        exporter_revision=exporter_revision,
        exported_at_ms=exported_at_ms,
        checkpoint_before=before,
        checkpoint_after=after,
        batches=batches,
    )
    bundle_path = core.write_export_bundle(outbox, bundle)
    if fail_after_bundle:
        raise HarnessObservationExportError("injected failure after durable bundle")
    core.write_checkpoint(
        checkpoint,
        after,
        expected_digest=(before.integrity_digest if checkpoint.exists() else None),
    )
    return {
        "schemaVersion": 1,
        "kind": "ordivon.harness-observation-export-result",
        "status": "exported",
        "ownerRevision": owner_revision,
        "exporterRevision": exporter_revision,
        "eventCount": len(events),
        "batchCount": len(batches),
        "lastSequence": events[-1].source.sequence,
        "checkpointBeforeDigest": before.integrity_digest,
        "checkpointAfterDigest": after.integrity_digest,
        "bundlePath": str(bundle_path),
        "bundleDigest": bundle.integrity_digest,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export bounded Harness Journal metadata observations"
    )
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--outbox", type=Path, required=True)
    parser.add_argument("--owner-revision", required=True)
    parser.add_argument("--exporter-revision", required=True)
    parser.add_argument("--exported-at-ms", type=int)
    parser.add_argument("--limit", type=int, default=256)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = export_harness_observations(
            state_root=args.state_root,
            instance_id=args.instance_id,
            checkpoint_path=args.checkpoint,
            outbox_root=args.outbox,
            owner_revision=args.owner_revision,
            exporter_revision=args.exporter_revision,
            exported_at_ms=(
                args.exported_at_ms
                if args.exported_at_ms is not None
                else time.time_ns() // 1_000_000
            ),
            limit=args.limit,
        )
    except (HarnessObservationExportError, OSError, sqlite3.Error, ValueError) as error:
        print(
            f"harness observation export: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

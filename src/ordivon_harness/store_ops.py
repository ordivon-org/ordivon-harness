from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Any

from anc_canonical import canonical_bytes, canonical_digest, loads_strict

from .sqlite_store import HarnessJournalCorruption, SQLiteHarnessStore

_BACKUP_MANIFEST = "manifest.json"
_BACKUP_DATABASE = "harness.sqlite3"
_BACKUP_OBJECTS = "objects"


def backup_harness_store(
    source_root: str | Path,
    destination: str | Path,
    *,
    created_at_ms: int | None = None,
) -> dict[str, object]:
    source = Path(source_root)
    target = Path(destination)
    if target.exists():
        raise FileExistsError(f"Harness backup destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise HarnessJournalCorruption("Harness backup parent must be a regular directory")
    os.chmod(target.parent, 0o700)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.backup-", dir=target.parent))
    os.chmod(temporary, 0o700)
    try:
        database = temporary / _BACKUP_DATABASE
        objects_root = temporary / _BACKUP_OBJECTS
        objects_root.mkdir(mode=0o700)
        os.chmod(objects_root, 0o700)
        with SQLiteHarnessStore(source) as store:
            store.doctor(full=True)
            _backup_database(store.connection, database)
            rows = store.connection.execute(
                "SELECT digest, kind, byte_length FROM object_refs ORDER BY digest"
            ).fetchall()
            object_entries: list[dict[str, object]] = []
            for row in rows:
                digest = str(row["digest"])
                source_path = store.objects.root / f"{digest[7:]}.json"
                destination_path = objects_root / source_path.name
                shutil.copyfile(source_path, destination_path)
                os.chmod(destination_path, 0o600)
                _fsync_file(destination_path)
                object_entries.append(
                    {
                        "digest": digest,
                        "kind": str(row["kind"]),
                        "byteLength": int(row["byte_length"]),
                        "file": f"{_BACKUP_OBJECTS}/{source_path.name}",
                        "fileSha256": _file_sha256(destination_path),
                    }
                )
            doctor = store.doctor(full=False)
        timestamp = time.time_ns() // 1_000_000 if created_at_ms is None else created_at_ms
        if timestamp < 0:
            raise ValueError("Harness backup creation time must be non-negative")
        manifest: dict[str, Any] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-store-backup",
            "createdAtMs": timestamp,
            "source": {
                "database": _BACKUP_DATABASE,
                "databaseSha256": _file_sha256(database),
                "schemaVersion": 1,
            },
            "objects": object_entries,
            "doctor": doctor,
        }
        manifest["integrity"] = {
            "algorithm": "sha256",
            "canonicalization": "ordivon-evidence-json-v1",
            "payloadDigest": canonical_digest(manifest),
        }
        manifest_path = temporary / _BACKUP_MANIFEST
        manifest_path.write_bytes(canonical_bytes(manifest))
        os.chmod(manifest_path, 0o600)
        _fsync_file(manifest_path)
        _fsync_directory(objects_root)
        _fsync_directory(temporary)
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return verify_harness_backup(target)


def verify_harness_backup(path: str | Path) -> dict[str, object]:
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise HarnessJournalCorruption("Harness backup must be a regular directory")
    manifest_path = root / _BACKUP_MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise HarnessJournalCorruption("Harness backup manifest is missing or irregular")
    try:
        value = loads_strict(manifest_path.read_bytes())
    except ValueError as error:
        raise HarnessJournalCorruption("Harness backup manifest cannot be decoded") from error
    if not isinstance(value, dict):
        raise HarnessJournalCorruption("Harness backup manifest must be an object")
    expected_fields = {
        "schemaVersion",
        "kind",
        "createdAtMs",
        "source",
        "objects",
        "doctor",
        "integrity",
    }
    if set(value) != expected_fields:
        raise HarnessJournalCorruption("Harness backup manifest fields differ")
    if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-store-backup":
        raise HarnessJournalCorruption("Harness backup version or kind is invalid")
    integrity = value["integrity"]
    if not isinstance(integrity, dict):
        raise HarnessJournalCorruption("Harness backup integrity must be an object")
    payload = dict(value)
    payload.pop("integrity")
    expected_integrity = {
        "algorithm": "sha256",
        "canonicalization": "ordivon-evidence-json-v1",
        "payloadDigest": canonical_digest(payload),
    }
    if integrity != expected_integrity:
        raise HarnessJournalCorruption("Harness backup manifest integrity differs")
    source = value["source"]
    objects = value["objects"]
    if not isinstance(source, dict) or set(source) != {
        "database",
        "databaseSha256",
        "schemaVersion",
    }:
        raise HarnessJournalCorruption("Harness backup source metadata differs")
    if source["database"] != _BACKUP_DATABASE or source["schemaVersion"] != 1:
        raise HarnessJournalCorruption("Harness backup database metadata is invalid")
    database = root / _BACKUP_DATABASE
    if database.is_symlink() or not database.is_file():
        raise HarnessJournalCorruption("Harness backup database is missing or irregular")
    if _file_sha256(database) != source["databaseSha256"]:
        raise HarnessJournalCorruption("Harness backup database digest differs")
    _verify_sqlite(database)
    if not isinstance(objects, list):
        raise HarnessJournalCorruption("Harness backup objects must be a list")
    seen: set[str] = set()
    for item in objects:
        if not isinstance(item, dict) or set(item) != {
            "digest",
            "kind",
            "byteLength",
            "file",
            "fileSha256",
        }:
            raise HarnessJournalCorruption("Harness backup object metadata differs")
        digest = item["digest"]
        relative = item["file"]
        if not isinstance(digest, str) or digest in seen:
            raise HarnessJournalCorruption("Harness backup object digest is invalid or repeated")
        if not isinstance(relative, str) or relative != f"objects/{digest[7:]}.json":
            raise HarnessJournalCorruption("Harness backup object path differs from digest")
        object_path = root / relative
        if object_path.is_symlink() or not object_path.is_file():
            raise HarnessJournalCorruption(
                f"Harness backup object is missing or irregular: {digest}"
            )
        encoded = object_path.read_bytes()
        if len(encoded) != item["byteLength"]:
            raise HarnessJournalCorruption(f"Harness backup object byte length differs: {digest}")
        if _file_sha256(object_path) != item["fileSha256"]:
            raise HarnessJournalCorruption(f"Harness backup object file digest differs: {digest}")
        try:
            envelope = loads_strict(encoded)
        except ValueError as error:
            raise HarnessJournalCorruption(
                f"Harness backup object cannot be decoded: {digest}"
            ) from error
        if canonical_digest(envelope) != digest:
            raise HarnessJournalCorruption(
                f"Harness backup object content address differs: {digest}"
            )
        if (
            not isinstance(envelope, dict)
            or set(envelope) != {"schemaVersion", "kind", "payload"}
            or envelope["schemaVersion"] != 1
            or envelope["kind"] != item["kind"]
        ):
            raise HarnessJournalCorruption(f"Harness backup object envelope differs: {digest}")
        seen.add(digest)
    database_refs = _database_object_refs(database)
    manifest_refs = {
        (str(item["digest"]), str(item["kind"]), int(item["byteLength"])) for item in objects
    }
    if database_refs != manifest_refs:
        raise HarnessJournalCorruption(
            "Harness backup manifest objects differ from database references"
        )
    return {
        "schemaVersion": 1,
        "kind": "ordivon.harness-store-backup-verification",
        "ok": True,
        "backupRoot": str(root),
        "createdAtMs": value["createdAtMs"],
        "objects": len(objects),
        "runs": value["doctor"].get("runs") if isinstance(value["doctor"], dict) else None,
        "events": value["doctor"].get("events") if isinstance(value["doctor"], dict) else None,
        "payloadDigest": expected_integrity["payloadDigest"],
    }


def restore_harness_backup(
    backup_root: str | Path,
    destination_root: str | Path,
) -> dict[str, object]:
    backup = Path(backup_root)
    target = Path(destination_root)
    verification = verify_harness_backup(backup)
    if target.exists():
        raise FileExistsError(f"Harness restore destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise HarnessJournalCorruption("Harness restore parent must be a regular directory")
    os.chmod(target.parent, 0o700)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.restore-", dir=target.parent))
    os.chmod(temporary, 0o700)
    try:
        shutil.copyfile(backup / _BACKUP_DATABASE, temporary / _BACKUP_DATABASE)
        os.chmod(temporary / _BACKUP_DATABASE, 0o600)
        _fsync_file(temporary / _BACKUP_DATABASE)
        shutil.copytree(backup / _BACKUP_OBJECTS, temporary / _BACKUP_OBJECTS)
        os.chmod(temporary / _BACKUP_OBJECTS, 0o700)
        for path in (temporary / _BACKUP_OBJECTS).glob("*.json"):
            if path.is_symlink() or not path.is_file():
                raise HarnessJournalCorruption(
                    f"Harness restore object is not regular: {path.name}"
                )
            os.chmod(path, 0o600)
            _fsync_file(path)
        _fsync_directory(temporary / _BACKUP_OBJECTS)
        _fsync_directory(temporary)
        with SQLiteHarnessStore(temporary) as restored:
            doctor = restored.doctor(full=True)
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "schemaVersion": 1,
        "kind": "ordivon.harness-store-restore",
        "ok": True,
        "backupRoot": str(backup),
        "destinationRoot": str(target),
        "backupPayloadDigest": verification["payloadDigest"],
        "store": doctor,
    }


def _backup_database(connection: sqlite3.Connection, destination: Path) -> None:
    target = sqlite3.connect(destination)
    try:
        connection.backup(target)
        target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        target.commit()
    finally:
        target.close()
    os.chmod(destination, 0o600)
    _fsync_file(destination)


def _verify_sqlite(path: Path) -> None:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        if rows != ("ok",):
            raise HarnessJournalCorruption(f"Harness backup SQLite quick_check failed: {rows}")
    finally:
        connection.close()


def _database_object_refs(path: Path) -> set[tuple[str, str, int]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT digest, kind, byte_length FROM object_refs ORDER BY digest"
        ).fetchall()
        return {(str(row[0]), str(row[1]), int(row[2])) for row in rows}
    finally:
        connection.close()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from anc_canonical import JsonValue, canonical_digest, validate_json_value

from .sqlite_store import SQLiteHarnessStore
from .version import package_version

_CUTOVER_DIR = "harness-cutover"
_RECEIPTS_DIR = "receipts"
_INVENTORIES_DIR = "inventories"
_MAX_TASKS = 10_000


class HarnessStoreMode(StrEnum):
    LEGACY_HOST = "legacy_host"
    INDEPENDENT = "independent"


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields differ: {sorted(set(value) ^ expected)}")


def _text(value: str, label: str, *, max_bytes: int = 2_048) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


def _digest(value: str, label: str) -> str:
    if (
        len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")
    return value


def _path_text(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


@dataclass(frozen=True, slots=True)
class LegacyHarnessRunInventoryItem:
    task_id: str
    task_state: str
    task_revision: int
    phase: str
    assignment_id: str | None
    assignment_generation: int | None
    harness_run_id: str | None
    termination_code: str | None
    blocking: bool
    reason: str

    def __post_init__(self) -> None:
        _text(self.task_id, "legacy Task identity", max_bytes=500)
        _text(self.task_state, "legacy Task state", max_bytes=100)
        if self.task_revision < 1:
            raise ValueError("legacy Task revision must be positive")
        _text(self.phase, "legacy Harness phase", max_bytes=200)
        for value, label in (
            (self.assignment_id, "legacy Assignment identity"),
            (self.harness_run_id, "legacy Harness Run identity"),
            (self.termination_code, "legacy termination code"),
        ):
            if value is not None:
                _text(value, label, max_bytes=1_024)
        if self.assignment_generation is not None and self.assignment_generation < 1:
            raise ValueError("legacy Assignment generation must be positive")
        if type(self.blocking) is not bool:
            raise ValueError("legacy blocking flag must be boolean")
        _text(self.reason, "legacy inventory reason", max_bytes=1_024)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "taskId": self.task_id,
            "taskState": self.task_state,
            "taskRevision": self.task_revision,
            "phase": self.phase,
            "assignmentId": self.assignment_id,
            "assignmentGeneration": self.assignment_generation,
            "harnessRunId": self.harness_run_id,
            "terminationCode": self.termination_code,
            "blocking": self.blocking,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> LegacyHarnessRunInventoryItem:
        expected = {
            "taskId",
            "taskState",
            "taskRevision",
            "phase",
            "assignmentId",
            "assignmentGeneration",
            "harnessRunId",
            "terminationCode",
            "blocking",
            "reason",
        }
        _exact(value, expected, "LegacyHarnessRunInventoryItem")
        for field in ("taskId", "taskState", "phase", "reason"):
            if not isinstance(value[field], str):
                raise ValueError(f"legacy inventory {field} must be a string")
        for field in ("assignmentId", "harnessRunId", "terminationCode"):
            if value[field] is not None and not isinstance(value[field], str):
                raise ValueError(f"legacy inventory {field} is invalid")
        if (
            type(value["taskRevision"]) is not int
            or (
                value["assignmentGeneration"] is not None
                and type(value["assignmentGeneration"]) is not int
            )
            or type(value["blocking"]) is not bool
        ):
            raise ValueError("legacy inventory scalar fields are invalid")
        return cls(
            task_id=value["taskId"],
            task_state=value["taskState"],
            task_revision=value["taskRevision"],
            phase=value["phase"],
            assignment_id=value["assignmentId"],
            assignment_generation=value["assignmentGeneration"],
            harness_run_id=value["harnessRunId"],
            termination_code=value["terminationCode"],
            blocking=value["blocking"],
            reason=value["reason"],
        )


@dataclass(frozen=True, slots=True)
class IndependentHarnessRunInventoryItem:
    harness_run_id: str
    caller_id: str
    caller_run_ref: str
    contract_digest: str
    status: str
    revision: int
    created_at_ms: int
    updated_at_ms: int
    blocking: bool

    def __post_init__(self) -> None:
        for value, label in (
            (self.harness_run_id, "independent Harness Run identity"),
            (self.caller_id, "independent caller identity"),
            (self.caller_run_ref, "independent caller Run reference"),
            (self.status, "independent Run status"),
        ):
            _text(value, label, max_bytes=1_024)
        _digest(self.contract_digest, "independent Contract digest")
        if self.revision < 1 or self.created_at_ms < 0 or self.updated_at_ms < self.created_at_ms:
            raise ValueError("independent Run revision or times are invalid")
        if type(self.blocking) is not bool:
            raise ValueError("independent blocking flag must be boolean")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "harnessRunId": self.harness_run_id,
            "callerId": self.caller_id,
            "callerRunRef": self.caller_run_ref,
            "contractDigest": self.contract_digest,
            "status": self.status,
            "revision": self.revision,
            "createdAtMs": self.created_at_ms,
            "updatedAtMs": self.updated_at_ms,
            "blocking": self.blocking,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> IndependentHarnessRunInventoryItem:
        expected = {
            "harnessRunId",
            "callerId",
            "callerRunRef",
            "contractDigest",
            "status",
            "revision",
            "createdAtMs",
            "updatedAtMs",
            "blocking",
        }
        _exact(value, expected, "IndependentHarnessRunInventoryItem")
        for field in (
            "harnessRunId",
            "callerId",
            "callerRunRef",
            "contractDigest",
            "status",
        ):
            if not isinstance(value[field], str):
                raise ValueError(f"independent inventory {field} must be a string")
        if any(type(value[field]) is not int for field in ("revision", "createdAtMs", "updatedAtMs")):
            raise ValueError("independent inventory revision and times must be integers")
        if type(value["blocking"]) is not bool:
            raise ValueError("independent inventory blocking flag must be boolean")
        return cls(
            harness_run_id=value["harnessRunId"],
            caller_id=value["callerId"],
            caller_run_ref=value["callerRunRef"],
            contract_digest=value["contractDigest"],
            status=value["status"],
            revision=value["revision"],
            created_at_ms=value["createdAtMs"],
            updated_at_ms=value["updatedAtMs"],
            blocking=value["blocking"],
        )


@dataclass(frozen=True, slots=True)
class ExternalHarnessRequestInventoryItem:
    task_id: str
    request_id: str
    foreign_run_ref: str | None
    status: str
    created_at_ms: int
    task_revision: int
    blocking: bool

    def __post_init__(self) -> None:
        _text(self.task_id, "external Harness Task identity", max_bytes=500)
        _text(self.request_id, "external Harness request identity", max_bytes=500)
        if self.foreign_run_ref is not None:
            _text(self.foreign_run_ref, "external Harness foreign Run", max_bytes=1_024)
        _text(self.status, "external Harness request status", max_bytes=100)
        if self.created_at_ms < 0 or self.task_revision < 1:
            raise ValueError("external Harness request time or Task revision is invalid")
        if type(self.blocking) is not bool:
            raise ValueError("external Harness request blocking flag must be boolean")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "taskId": self.task_id,
            "requestId": self.request_id,
            "foreignRunRef": self.foreign_run_ref,
            "status": self.status,
            "createdAtMs": self.created_at_ms,
            "taskRevision": self.task_revision,
            "blocking": self.blocking,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ExternalHarnessRequestInventoryItem:
        expected = {
            "taskId",
            "requestId",
            "foreignRunRef",
            "status",
            "createdAtMs",
            "taskRevision",
            "blocking",
        }
        _exact(value, expected, "ExternalHarnessRequestInventoryItem")
        if not isinstance(value["taskId"], str) or not isinstance(value["requestId"], str):
            raise ValueError("external Harness request identities must be strings")
        if value["foreignRunRef"] is not None and not isinstance(value["foreignRunRef"], str):
            raise ValueError("external Harness foreign Run reference is invalid")
        if not isinstance(value["status"], str):
            raise ValueError("external Harness request status must be a string")
        if (
            type(value["createdAtMs"]) is not int
            or type(value["taskRevision"]) is not int
            or type(value["blocking"]) is not bool
        ):
            raise ValueError("external Harness request scalars are invalid")
        return cls(
            task_id=value["taskId"],
            request_id=value["requestId"],
            foreign_run_ref=value["foreignRunRef"],
            status=value["status"],
            created_at_ms=value["createdAtMs"],
            task_revision=value["taskRevision"],
            blocking=value["blocking"],
        )


@dataclass(frozen=True, slots=True)
class HarnessCutoverInventory:
    host_state_root: str
    harness_state_root: str
    generated_at_ms: int
    legacy_runs: tuple[LegacyHarnessRunInventoryItem, ...]
    independent_runs: tuple[IndependentHarnessRunInventoryItem, ...]
    external_requests: tuple[ExternalHarnessRequestInventoryItem, ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.host_state_root, "Host state root", max_bytes=4_096)
        _text(self.harness_state_root, "Harness state root", max_bytes=4_096)
        if self.host_state_root == self.harness_state_root:
            raise ValueError("Host and Harness state roots must differ")
        if self.generated_at_ms < 0:
            raise ValueError("cutover inventory time must be non-negative")
        for blocker in self.blockers:
            _text(blocker, "cutover blocker", max_bytes=2_048)
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("cutover blockers must be unique")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @property
    def can_activate(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-cutover-inventory",
            "hostStateRoot": self.host_state_root,
            "harnessStateRoot": self.harness_state_root,
            "generatedAtMs": self.generated_at_ms,
            "legacyRuns": [item.to_dict() for item in self.legacy_runs],
            "independentRuns": [item.to_dict() for item in self.independent_runs],
            "externalRequests": [item.to_dict() for item in self.external_requests],
            "blockers": list(self.blockers),
            "canActivate": self.can_activate,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessCutoverInventory:
        expected = {
            "schemaVersion",
            "kind",
            "hostStateRoot",
            "harnessStateRoot",
            "generatedAtMs",
            "legacyRuns",
            "independentRuns",
            "externalRequests",
            "blockers",
            "canActivate",
        }
        _exact(value, expected, "HarnessCutoverInventory")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-cutover-inventory":
            raise ValueError("HarnessCutoverInventory version or kind is invalid")
        if not isinstance(value["hostStateRoot"], str) or not isinstance(value["harnessStateRoot"], str):
            raise ValueError("cutover inventory roots must be strings")
        if type(value["generatedAtMs"]) is not int or type(value["canActivate"]) is not bool:
            raise ValueError("cutover inventory time or disposition is invalid")
        collections = ("legacyRuns", "independentRuns", "externalRequests", "blockers")
        if any(not isinstance(value[field], list) for field in collections):
            raise ValueError("cutover inventory collections must be arrays")
        inventory = cls(
            host_state_root=value["hostStateRoot"],
            harness_state_root=value["harnessStateRoot"],
            generated_at_ms=value["generatedAtMs"],
            legacy_runs=tuple(
                LegacyHarnessRunInventoryItem.from_dict(item)
                for item in value["legacyRuns"]
                if isinstance(item, dict)
            ),
            independent_runs=tuple(
                IndependentHarnessRunInventoryItem.from_dict(item)
                for item in value["independentRuns"]
                if isinstance(item, dict)
            ),
            external_requests=tuple(
                ExternalHarnessRequestInventoryItem.from_dict(item)
                for item in value["externalRequests"]
                if isinstance(item, dict)
            ),
            blockers=tuple(value["blockers"]),
        )
        if (
            len(inventory.legacy_runs) != len(value["legacyRuns"])
            or len(inventory.independent_runs) != len(value["independentRuns"])
            or len(inventory.external_requests) != len(value["externalRequests"])
            or any(not isinstance(item, str) for item in value["blockers"])
            or inventory.can_activate != value["canActivate"]
        ):
            raise ValueError("cutover inventory collection or disposition differs")
        return inventory


@dataclass(frozen=True, slots=True)
class HarnessCutoverReceipt:
    sequence: int
    action: str
    previous_mode: HarnessStoreMode
    selected_mode: HarnessStoreMode
    host_state_root: str
    harness_state_root: str
    inventory_digest: str
    previous_receipt_digest: str | None
    created_at_ms: int
    harness_version: str

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("cutover receipt sequence must be positive")
        if self.action not in {"activate", "rollback"}:
            raise ValueError(f"unsupported cutover action: {self.action}")
        if self.action == "activate" and (
            self.previous_mode is not HarnessStoreMode.LEGACY_HOST
            or self.selected_mode is not HarnessStoreMode.INDEPENDENT
        ):
            raise ValueError("activation receipt modes differ")
        if self.action == "rollback" and (
            self.previous_mode is not HarnessStoreMode.INDEPENDENT
            or self.selected_mode is not HarnessStoreMode.LEGACY_HOST
        ):
            raise ValueError("rollback receipt modes differ")
        _text(self.host_state_root, "cutover Host state root", max_bytes=4_096)
        _text(self.harness_state_root, "cutover Harness state root", max_bytes=4_096)
        _digest(self.inventory_digest, "cutover inventory digest")
        if self.previous_receipt_digest is not None:
            _digest(self.previous_receipt_digest, "previous cutover receipt digest")
        if self.created_at_ms < 0:
            raise ValueError("cutover receipt time must be non-negative")
        _text(self.harness_version, "Harness version", max_bytes=300)

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def payload(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": 1,
            "kind": "ordivon.harness-cutover-receipt",
            "sequence": self.sequence,
            "action": self.action,
            "previousMode": self.previous_mode.value,
            "selectedMode": self.selected_mode.value,
            "hostStateRoot": self.host_state_root,
            "harnessStateRoot": self.harness_state_root,
            "inventoryDigest": self.inventory_digest,
            "previousReceiptDigest": self.previous_receipt_digest,
            "createdAtMs": self.created_at_ms,
            "harnessVersion": self.harness_version,
        }

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            **self.payload(),
            "integrity": {
                "algorithm": "sha256",
                "canonicalization": "ordivon-evidence-json-v1",
                "payloadDigest": self.digest,
            },
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> HarnessCutoverReceipt:
        expected = {
            "schemaVersion",
            "kind",
            "sequence",
            "action",
            "previousMode",
            "selectedMode",
            "hostStateRoot",
            "harnessStateRoot",
            "inventoryDigest",
            "previousReceiptDigest",
            "createdAtMs",
            "harnessVersion",
            "integrity",
        }
        _exact(value, expected, "HarnessCutoverReceipt")
        if value["schemaVersion"] != 1 or value["kind"] != "ordivon.harness-cutover-receipt":
            raise ValueError("HarnessCutoverReceipt version or kind is invalid")
        for field in (
            "action",
            "previousMode",
            "selectedMode",
            "hostStateRoot",
            "harnessStateRoot",
            "inventoryDigest",
            "harnessVersion",
        ):
            if not isinstance(value[field], str):
                raise ValueError(f"cutover receipt {field} must be a string")
        if value["previousReceiptDigest"] is not None and not isinstance(
            value["previousReceiptDigest"], str
        ):
            raise ValueError("cutover previous receipt digest is invalid")
        if type(value["sequence"]) is not int or type(value["createdAtMs"]) is not int:
            raise ValueError("cutover receipt sequence and time must be integers")
        receipt = cls(
            sequence=value["sequence"],
            action=value["action"],
            previous_mode=HarnessStoreMode(value["previousMode"]),
            selected_mode=HarnessStoreMode(value["selectedMode"]),
            host_state_root=value["hostStateRoot"],
            harness_state_root=value["harnessStateRoot"],
            inventory_digest=value["inventoryDigest"],
            previous_receipt_digest=value["previousReceiptDigest"],
            created_at_ms=value["createdAtMs"],
            harness_version=value["harnessVersion"],
        )
        integrity = value["integrity"]
        if not isinstance(integrity, dict) or integrity != {
            "algorithm": "sha256",
            "canonicalization": "ordivon-evidence-json-v1",
            "payloadDigest": receipt.digest,
        }:
            raise ValueError("cutover receipt integrity differs")
        return receipt


@dataclass(frozen=True, slots=True)
class HarnessCutoverStatus:
    selected_mode: HarnessStoreMode
    latest_receipt: HarnessCutoverReceipt | None
    receipts: tuple[HarnessCutoverReceipt, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "selectedMode": self.selected_mode.value,
            "latestReceipt": (
                None if self.latest_receipt is None else self.latest_receipt.to_dict()
            ),
            "receiptCount": len(self.receipts),
        }


def build_cutover_inventory(
    host_state_root: str | Path,
    harness_state_root: str | Path,
    *,
    generated_at_ms: int,
) -> HarnessCutoverInventory:
    host_root = Path(host_state_root).expanduser().resolve()
    harness_root = Path(harness_state_root).expanduser().resolve()
    if host_root == harness_root:
        raise ValueError("Host and Harness state roots must differ")
    if not (host_root / "host.sqlite3").is_file():
        raise FileNotFoundError(host_root / "host.sqlite3")
    if not (harness_root / "harness.sqlite3").is_file():
        raise FileNotFoundError(harness_root / "harness.sqlite3")

    from ._host_compat.storage import HostStorage
    from .host import HarnessHost
    from .runner import HarnessRunner

    legacy: list[LegacyHarnessRunInventoryItem] = []
    external: list[ExternalHarnessRequestInventoryItem] = []
    with HostStorage(host_root, validation_mode="full") as storage:
        task_ids = storage.journal.task_ids()
        if len(task_ids) > _MAX_TASKS:
            raise ValueError(f"Host Task inventory exceeds {_MAX_TASKS}")
        runner = HarnessRunner(HarnessHost(storage, clock_ms=lambda: generated_at_ms))
        for task_id in sorted(task_ids):
            snapshot = storage.read_task_event(task_id)
            if not isinstance(snapshot.data, dict):
                raise ValueError(f"Host Task data is not an object: {task_id}")
            data = snapshot.data
            native = isinstance(data.get("nativeHarnessRunContractObjectDigest"), str) or isinstance(
                data.get("harnessRunId"), str
            )
            if native:
                status = runner.status(task_id)
                abandoned = isinstance(data.get("harnessRunAbandonmentObjectDigest"), str)
                blocking = (
                    not snapshot.projection.state.terminal
                    and status.termination_code is None
                    and not abandoned
                )
                reason = (
                    f"nonterminal legacy Harness phase {status.phase}"
                    if blocking
                    else (
                        "legacy Harness Run abandoned"
                        if abandoned
                        else "legacy Harness Run terminal or Task terminal"
                    )
                )
                legacy.append(
                    LegacyHarnessRunInventoryItem(
                        task_id=task_id,
                        task_state=status.task_state,
                        task_revision=status.task_revision,
                        phase=status.phase,
                        assignment_id=status.assignment_id,
                        assignment_generation=status.assignment_generation,
                        harness_run_id=status.harness_run_id,
                        termination_code=status.termination_code,
                        blocking=blocking,
                        reason=reason,
                    )
                )
            request_digest = data.get("externalExecutionRequestObjectDigest")
            if isinstance(request_digest, str):
                request_value = storage.objects.get(
                    request_digest,
                    expected_kind="external-execution-request",
                )
                if not isinstance(request_value, dict):
                    raise ValueError("external execution request object is invalid")
                if request_value.get("adapterId") == "external-executor:ordivon-harness":
                    request_id = request_value.get("requestId")
                    created_at_ms = request_value.get("createdAtMs")
                    if not isinstance(request_id, str) or type(created_at_ms) is not int:
                        raise ValueError("external Harness request fields are invalid")
                    foreign_ref: str | None = None
                    external_status = "request_only"
                    binding_digest = data.get("externalRunBindingObjectDigest")
                    if isinstance(binding_digest, str):
                        binding_value = storage.objects.get(
                            binding_digest,
                            expected_kind="external-run-binding",
                        )
                        if not isinstance(binding_value, dict):
                            raise ValueError("external Harness binding object is invalid")
                        candidate = binding_value.get("foreignRunRef")
                        observed_status = binding_value.get("observedStatus")
                        if candidate is not None and not isinstance(candidate, str):
                            raise ValueError("external Harness foreign Run reference is invalid")
                        if not isinstance(observed_status, str):
                            raise ValueError("external Harness observed status is invalid")
                        foreign_ref = candidate
                        external_status = observed_status
                    external.append(
                        ExternalHarnessRequestInventoryItem(
                            task_id=task_id,
                            request_id=request_id,
                            foreign_run_ref=foreign_ref,
                            status=external_status,
                            created_at_ms=created_at_ms,
                            task_revision=snapshot.projection.revision,
                            blocking=external_status
                            not in {"completed", "failed", "cancelled"},
                        )
                    )

    independent: list[IndependentHarnessRunInventoryItem] = []
    with SQLiteHarnessStore(harness_root) as store:
        store.doctor(full=True)
        for projection in store.list_runs():
            independent.append(
                IndependentHarnessRunInventoryItem(
                    harness_run_id=projection.harness_run_id,
                    caller_id=projection.caller_id,
                    caller_run_ref=projection.caller_run_ref,
                    contract_digest=projection.contract_digest,
                    status=projection.status.value,
                    revision=projection.revision,
                    created_at_ms=projection.created_at_ms,
                    updated_at_ms=projection.updated_at_ms,
                    blocking=not projection.status.terminal,
                )
            )

    blockers = [
        f"legacy:{item.task_id}:{item.harness_run_id or item.assignment_id or 'unknown'}"
        for item in legacy
        if item.blocking
    ]
    blockers.extend(
        f"independent:{item.harness_run_id}:{item.status}"
        for item in independent
        if item.blocking
    )
    blockers.extend(
        f"external:{item.task_id}:{item.request_id}:{item.status}"
        for item in external
        if item.blocking
    )
    return HarnessCutoverInventory(
        host_state_root=str(host_root),
        harness_state_root=str(harness_root),
        generated_at_ms=generated_at_ms,
        legacy_runs=tuple(legacy),
        independent_runs=tuple(independent),
        external_requests=tuple(external),
        blockers=tuple(sorted(blockers)),
    )


def cutover_status(host_state_root: str | Path) -> HarnessCutoverStatus:
    receipts = _load_receipts(Path(host_state_root).expanduser().resolve())
    latest = None if not receipts else receipts[-1]
    return HarnessCutoverStatus(
        selected_mode=(
            HarnessStoreMode.LEGACY_HOST if latest is None else latest.selected_mode
        ),
        latest_receipt=latest,
        receipts=receipts,
    )


def activate_cutover(
    host_state_root: str | Path,
    harness_state_root: str | Path,
    *,
    created_at_ms: int,
) -> tuple[HarnessCutoverReceipt, HarnessCutoverInventory]:
    host_root = Path(host_state_root).expanduser().resolve()
    with _cutover_lock(host_root):
        status = cutover_status(host_root)
        if status.selected_mode is not HarnessStoreMode.LEGACY_HOST:
            raise RuntimeError("Harness cutover is already active")
        inventory = build_cutover_inventory(
            host_root,
            harness_state_root,
            generated_at_ms=created_at_ms,
        )
        if not inventory.can_activate:
            raise RuntimeError(
                "Harness cutover blocked: " + ", ".join(inventory.blockers)
            )
        receipt = HarnessCutoverReceipt(
            sequence=len(status.receipts) + 1,
            action="activate",
            previous_mode=HarnessStoreMode.LEGACY_HOST,
            selected_mode=HarnessStoreMode.INDEPENDENT,
            host_state_root=inventory.host_state_root,
            harness_state_root=inventory.harness_state_root,
            inventory_digest=inventory.digest,
            previous_receipt_digest=(
                None if status.latest_receipt is None else status.latest_receipt.digest
            ),
            created_at_ms=created_at_ms,
            harness_version=package_version(),
        )
        _publish_inventory_and_receipt(host_root, inventory, receipt)
        return receipt, inventory
    

def rollback_cutover(
    host_state_root: str | Path,
    harness_state_root: str | Path,
    *,
    created_at_ms: int,
) -> tuple[HarnessCutoverReceipt, HarnessCutoverInventory]:
    host_root = Path(host_state_root).expanduser().resolve()
    with _cutover_lock(host_root):
        status = cutover_status(host_root)
        if status.selected_mode is not HarnessStoreMode.INDEPENDENT or status.latest_receipt is None:
            raise RuntimeError("Harness cutover is not active")
        activation = next(
            receipt for receipt in reversed(status.receipts) if receipt.action == "activate"
        )
        inventory = build_cutover_inventory(
            host_root,
            harness_state_root,
            generated_at_ms=created_at_ms,
        )
        post_activation_runs = [
            item.harness_run_id
            for item in inventory.independent_runs
            if item.created_at_ms >= activation.created_at_ms
        ]
        post_activation_requests = [
            item.request_id
            for item in inventory.external_requests
            if item.created_at_ms >= activation.created_at_ms
        ]
        blockers = tuple(sorted(post_activation_runs + post_activation_requests))
        if blockers:
            raise RuntimeError(
                "Harness rollback blocked by post-activation independent work: "
                + ", ".join(blockers)
            )
        receipt = HarnessCutoverReceipt(
            sequence=len(status.receipts) + 1,
            action="rollback",
            previous_mode=HarnessStoreMode.INDEPENDENT,
            selected_mode=HarnessStoreMode.LEGACY_HOST,
            host_state_root=inventory.host_state_root,
            harness_state_root=inventory.harness_state_root,
            inventory_digest=inventory.digest,
            previous_receipt_digest=status.latest_receipt.digest,
            created_at_ms=created_at_ms,
            harness_version=package_version(),
        )
        _publish_inventory_and_receipt(host_root, inventory, receipt)
        return receipt, inventory
    

def assert_legacy_writer_allowed(host_state_root: str | Path) -> None:
    status = cutover_status(host_state_root)
    if status.selected_mode is HarnessStoreMode.INDEPENDENT:
        latest = status.latest_receipt
        assert latest is not None
        raise RuntimeError(
            "legacy Host-backed Harness writes are disabled by cutover receipt "
            f"{latest.digest}; use the Host external-executor path"
        )


@contextmanager
def _cutover_lock(host_root: Path):
    root = host_root / _CUTOVER_DIR
    _ensure_private_directory(root)
    lock_path = root / ".lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _load_receipts(host_root: Path) -> tuple[HarnessCutoverReceipt, ...]:
    receipt_root = host_root / _CUTOVER_DIR / _RECEIPTS_DIR
    if not receipt_root.exists():
        return ()
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise ValueError("Harness cutover receipt root is irregular")
    receipts: list[HarnessCutoverReceipt] = []
    for path in sorted(receipt_root.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Harness cutover receipt is irregular: {path}")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Harness cutover receipt cannot be decoded: {path}") from error
        if not isinstance(value, dict):
            raise ValueError(f"Harness cutover receipt must be an object: {path}")
        receipt = HarnessCutoverReceipt.from_dict(value)
        expected_name = f"{receipt.sequence:08d}-{receipt.action}-{receipt.digest[7:31]}.json"
        if path.name != expected_name:
            raise ValueError(f"Harness cutover receipt filename differs: {path.name}")
        expected_sequence = len(receipts) + 1
        expected_previous = None if not receipts else receipts[-1].digest
        if receipt.sequence != expected_sequence or receipt.previous_receipt_digest != expected_previous:
            raise ValueError("Harness cutover receipt chain differs")
        if receipts and (
            receipt.host_state_root != receipts[0].host_state_root
            or receipt.harness_state_root != receipts[0].harness_state_root
            or receipt.previous_mode is not receipts[-1].selected_mode
        ):
            raise ValueError("Harness cutover receipt roots or mode chain differ")
        inventory = _load_inventory(host_root, receipt.inventory_digest)
        if (
            inventory.host_state_root != receipt.host_state_root
            or inventory.harness_state_root != receipt.harness_state_root
        ):
            raise ValueError("Harness cutover inventory roots differ from receipt")
        receipts.append(receipt)
    return tuple(receipts)


def _load_inventory(
    host_root: Path,
    inventory_digest: str,
) -> HarnessCutoverInventory:
    _digest(inventory_digest, "cutover inventory digest")
    path = (
        host_root
        / _CUTOVER_DIR
        / _INVENTORIES_DIR
        / f"inventory-{inventory_digest[7:]}.json"
    )
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Harness cutover inventory is missing or irregular: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Harness cutover inventory cannot be decoded: {path}") from error
    if not isinstance(value, dict):
        raise ValueError("Harness cutover inventory must be an object")
    integrity = value.get("integrity")
    payload = dict(value)
    payload.pop("integrity", None)
    inventory = HarnessCutoverInventory.from_dict(payload)
    if inventory.digest != inventory_digest or integrity != {
        "algorithm": "sha256",
        "canonicalization": "ordivon-evidence-json-v1",
        "payloadDigest": inventory.digest,
    }:
        raise ValueError("Harness cutover inventory integrity differs")
    return inventory


def _publish_inventory_and_receipt(
    host_root: Path,
    inventory: HarnessCutoverInventory,
    receipt: HarnessCutoverReceipt,
) -> None:
    root = host_root / _CUTOVER_DIR
    receipts = root / _RECEIPTS_DIR
    inventories = root / _INVENTORIES_DIR
    for directory in (root, receipts, inventories):
        _ensure_private_directory(directory)
    inventory_path = inventories / f"inventory-{inventory.digest[7:]}.json"
    inventory_value = {
        **inventory.to_dict(),
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "ordivon-evidence-json-v1",
            "payloadDigest": inventory.digest,
        },
    }
    _write_new_json(inventory_path, inventory_value)
    receipt_path = receipts / (
        f"{receipt.sequence:08d}-{receipt.action}-{receipt.digest[7:31]}.json"
    )
    _write_new_json(receipt_path, receipt.to_dict())


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"Harness cutover directory is irregular: {path}")
    os.chmod(path, 0o700)


def _write_new_json(path: Path, value: dict[str, JsonValue]) -> None:
    validate_json_value(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    if path.exists() or path.is_symlink():
        existing = path.read_bytes() if path.is_file() and not path.is_symlink() else None
        if existing == encoded:
            return
        raise FileExistsError(path)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(temporary_fd, 0o600)
        with os.fdopen(temporary_fd, "wb", closefd=True) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = path.read_bytes() if path.is_file() and not path.is_symlink() else None
            if existing != encoded:
                raise
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "ExternalHarnessRequestInventoryItem",
    "HarnessCutoverInventory",
    "HarnessCutoverReceipt",
    "HarnessCutoverStatus",
    "HarnessStoreMode",
    "IndependentHarnessRunInventoryItem",
    "LegacyHarnessRunInventoryItem",
    "activate_cutover",
    "assert_legacy_writer_allowed",
    "build_cutover_inventory",
    "cutover_status",
    "rollback_cutover",
]

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anc_canonical import JsonValue, validate_json_value

from .core_contracts import HarnessRunContract
from .independent_result import IndependentRunRecorder, StoredIndependentRunResult
from .ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
from .ordivon.loop import RunBudget
from .ordivon.model import AgentTurnAdapter
from .ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
    SQLiteHarnessAgentBridge,
)
from .ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from .protocol import HarnessProviderCallStatus
from .sqlite_store import SQLiteHarnessStore
from .standalone import StandaloneHarnessExecution, StandaloneHarnessRunner
from .store import HarnessRunStatus


def capabilities() -> dict[str, JsonValue]:
    """Describe the Host-free operational surface without reading local state."""
    return {
        "ok": True,
        "schemaVersion": 1,
        "kind": "ordivon.harness-cli-capabilities",
        "defaultAuthority": "independent-harness-run",
        "executionProfiles": [
            {
                "profileId": "deepseek-no-tool-v1",
                "provider": "deepseek",
                "adapterId": DeepSeekTurnAdapter.adapter_id,
                "toolCatalogDigest": NO_TOOL_AGENT_SURFACE_DIGEST,
                "toolGrantDigest": NO_TOOL_AGENT_GRANT_DIGEST,
                "runtimeRequired": False,
                "commands": ["run", "resume", "recover", "status", "inspect"],
            }
        ],
        "toolBearingCliExecution": False,
        "toolBearingApi": "ordivon_harness.api / ordivon_harness.core",
            }


def dispatch(args, *, clock_ms) -> dict[str, object]:
    command = args.command
    if command == "capabilities":
        return dict(capabilities())
    root = _state_root(args)
    if command == "doctor":
        with SQLiteHarnessStore(root) as store:
            return {
                "ok": True,
                "authority": "independent-harness-run",
                "stateRoot": str(root),
                "store": store.doctor(full=True),
            }
    if command == "status":
        with SQLiteHarnessStore(root) as store:
            return {
                "ok": True,
                "authority": "independent-harness-run",
                "stateRoot": str(root),
                "run": store.load_run(args.harness_run_id).to_dict(),
            }
    if command == "inspect":
        with SQLiteHarnessStore(root) as store:
            return _inspect(store, args.harness_run_id, root=root, clock_ms=clock_ms)
    if command == "run":
        contract = _load_contract(args.contract)
        messages = _load_messages(args)
        if not messages:
            raise ValueError("independent run requires at least one input message")
        with SQLiteHarnessStore(root) as store:
            try:
                projection = store.load_run(contract.harness_run_id)
            except KeyError:
                store.create_run(contract)
            else:
                if projection.contract_digest != contract.digest:
                    raise ValueError("existing Harness Run differs from supplied Contract")
                if projection.status.terminal:
                    return _inspect(
                        store,
                        contract.harness_run_id,
                        root=root,
                        clock_ms=clock_ms,
                    )
                if projection.status is HarnessRunStatus.PAUSED:
                    raise ValueError("paused independent Harness Run requires resume")
            continuity = SQLiteHarnessRunContinuityStore.open(
                store,
                contract.harness_run_id,
                clock_ms=clock_ms,
            )
            execution = _runner(
                contract,
                continuity,
                args=args,
                clock_ms=clock_ms,
            ).run(messages)
            return _execution_value(execution, root=root, store=store)
    if command == "resume":
        with SQLiteHarnessStore(root) as store:
            continuity = SQLiteHarnessRunContinuityStore.open(
                store,
                args.harness_run_id,
                clock_ms=clock_ms,
            )
            retained = continuity.load_current_snapshot()
            execution = _runner(
                continuity.contract,
                continuity,
                args=args,
                clock_ms=clock_ms,
                provider_source=continuity.snapshot_provider_source(retained),
            ).resume(additional_messages=_load_messages(args))
            return _execution_value(execution, root=root, store=store)
    if command == "recover":
        with SQLiteHarnessStore(root) as store:
            return _recover(
                store,
                args.harness_run_id,
                root=root,
                trigger=args.trigger,
                clock_ms=clock_ms,
            )
    raise ValueError(f"unsupported independent Harness command: {command}")


def _state_root(args) -> Path:
    root = args.state_root
    if root is None:
        raise ValueError("Harness command requires --state-root")
    return root.expanduser().resolve()


def _load_contract(path: Path) -> HarnessRunContract:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise ValueError("Harness Run Contract file must contain one JSON object")
    return HarnessRunContract.from_dict(raw)


def _load_messages(args) -> tuple[dict[str, JsonValue], ...]:
    values: list[dict[str, JsonValue]] = []
    path = getattr(args, "messages_json", None)
    if path is not None:
        raw = _load_json(path)
        if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
            raise ValueError("messages JSON must contain an array of objects")
        for item in raw:
            value = dict(item)
            validate_json_value(value)
            values.append(value)
    for message in getattr(args, "message", ()):
        value: dict[str, JsonValue] = {"role": "user", "content": message}
        validate_json_value(value)
        values.append(value)
    return tuple(values)


def _load_json(path: Path) -> Any:
    resolved = path.expanduser().resolve()
    return json.loads(resolved.read_text(encoding="utf-8"))


def _adapter(contract: HarnessRunContract, args) -> AgentTurnAdapter:
    if contract.adapter_id != DeepSeekTurnAdapter.adapter_id:
        raise ValueError(
            "independent CLI execution currently supports only "
            f"{DeepSeekTurnAdapter.adapter_id}; use the Host-free Python API for another Adapter"
        )
    return DeepSeekTurnAdapter(
        DeepSeekSettings.from_secret_file(args.deepseek_secret),
        completion_contract=contract.completion_contract,
    )


def _runner(
    contract: HarnessRunContract,
    continuity: SQLiteHarnessRunContinuityStore,
    *,
    args,
    clock_ms,
    provider_source=None,
) -> StandaloneHarnessRunner:
    if (
        contract.tool_catalog_digest != NO_TOOL_AGENT_SURFACE_DIGEST
        or contract.tool_grant_digest != NO_TOOL_AGENT_GRANT_DIGEST
    ):
        raise ValueError(
            "independent CLI execution currently supports only the canonical no-Tool profile; "
            "Tool-bearing Runs require an application-supplied HarnessRuntimeClient through "
            "ordivon_harness.api or ordivon_harness.core"
        )
    adapter = _adapter(contract, args)
    bridge = SQLiteHarnessAgentBridge(
        contract,
        continuity,
        provider_source=provider_source,
    )
    budget = RunBudget.from_contract_dict(contract.budget)
    return StandaloneHarnessRunner(
        contract,
        continuity,
        adapter,
        bridge,
        budget=budget,
        clock_ms=clock_ms,
    )


def _execution_value(
    execution: StandaloneHarnessExecution,
    *,
    root: Path,
    store: SQLiteHarnessStore,
) -> dict[str, object]:
    projection = store.load_run(execution.loop_result.harness_run_id)
    terminal = execution.terminal_result
    return {
        "ok": True,
        "authority": "independent-harness-run",
        "stateRoot": str(root),
        "run": projection.to_dict(),
        "stopCode": execution.loop_result.stop_code.value,
        "usage": execution.loop_result.usage,
        "runReceipt": None if terminal is None else terminal.receipt.to_dict(),
        "completionProposal": (
            None
            if terminal is None or terminal.completion_proposal is None
            else terminal.completion_proposal.to_dict()
        ),
    }


def _inspect(
    store: SQLiteHarnessStore,
    harness_run_id: str,
    *,
    root: Path,
    clock_ms,
) -> dict[str, object]:
    projection = store.load_run(harness_run_id)
    continuity = SQLiteHarnessRunContinuityStore.open(
        store,
        harness_run_id,
        clock_ms=clock_ms,
    )
    recorder = IndependentRunRecorder(
        store,
        continuity.contract,
        continuity.binding,
        clock_ms=clock_ms,
    )
    provider: dict[str, JsonValue] | None = None
    try:
        provider = continuity.load_current_provider_call().record.to_dict()
    except KeyError:
        pass
    snapshot: dict[str, JsonValue] | None = None
    try:
        snapshot = continuity.load_current_snapshot().snapshot.to_dict()
    except KeyError:
        pass
    recovery: dict[str, JsonValue] | None = None
    try:
        recovery = recorder.load_latest_recovery_assessment().to_dict()
    except KeyError:
        pass
    terminal: StoredIndependentRunResult | None = None
    if projection.status.terminal:
        try:
            terminal = recorder.load_terminal_result()
        except KeyError:
            pass
    return {
        "ok": True,
        "authority": "independent-harness-run",
        "stateRoot": str(root),
        "run": projection.to_dict(),
        "contract": continuity.contract.to_dict(),
        "providerCall": provider,
        "snapshot": snapshot,
        "recovery": recovery,
        "runReceipt": None if terminal is None else terminal.receipt.to_dict(),
        "completionProposal": (
            None
            if terminal is None or terminal.completion_proposal is None
            else terminal.completion_proposal.to_dict()
        ),
    }


def _recover(
    store: SQLiteHarnessStore,
    harness_run_id: str,
    *,
    root: Path,
    trigger: str,
    clock_ms,
) -> dict[str, object]:
    projection = store.load_run(harness_run_id)
    continuity = SQLiteHarnessRunContinuityStore.open(
        store,
        harness_run_id,
        clock_ms=clock_ms,
    )
    if projection.status.terminal:
        value = _inspect(store, harness_run_id, root=root, clock_ms=clock_ms)
        value["requiredAction"] = "none"
        return value

    try:
        provider = continuity.load_current_provider_call()
    except KeyError:
        provider = None
    if provider is not None and provider.record.status in {
        HarnessProviderCallStatus.CLAIMED,
        HarnessProviderCallStatus.COMPLETED,
        HarnessProviderCallStatus.FAILED,
    }:
        return {
            "ok": True,
            "authority": "independent-harness-run",
            "stateRoot": str(root),
            "run": projection.to_dict(),
            "providerCall": provider.record.to_dict(),
            "recovery": None,
            "requiredAction": "resume" if projection.status is HarnessRunStatus.PAUSED else "retry-run",
            "reason": "durable Provider state can be reconciled by the normal execution path",
        }

    recorder = IndependentRunRecorder(
        store,
        continuity.contract,
        continuity.binding,
        clock_ms=clock_ms,
    )
    no_tool = (
        continuity.contract.tool_catalog_digest == NO_TOOL_AGENT_SURFACE_DIGEST
        and continuity.contract.tool_grant_digest == NO_TOOL_AGENT_GRANT_DIGEST
    )
    unresolved: tuple[str, ...]
    if provider is not None:
        unresolved = (
            f"Provider Call remains {provider.record.status.value}; physical Provider outcome is not safe to infer",
        )
    elif no_tool:
        unresolved = ()
    else:
        unresolved = (
            "CLI has no domain-specific Runtime/Tool reconciliation evidence for this Tool-bearing Run",
        )
    assessment = recorder.record_recovery_assessment(
        trigger=trigger,
        grant_effect_class="observation-only" if no_tool and not unresolved else "unknown",
        catalog_status="matched",
        workspace_status="not_applicable" if no_tool else "unknown",
        workspace_evidence={
            "providerCallStatus": None if provider is None else provider.record.status.value,
            "toolBearing": not no_tool,
        },
        unresolved_unknowns=unresolved,
    )
    return {
        "ok": True,
        "authority": "independent-harness-run",
        "stateRoot": str(root),
        "run": store.load_run(harness_run_id).to_dict(),
        "providerCall": None if provider is None else provider.record.to_dict(),
        "recovery": assessment.to_dict(),
        "requiredAction": (
            "retry-run"
            if assessment.safe_to_abandon and projection.status is HarnessRunStatus.CREATED
            else "resume"
            if assessment.safe_to_abandon and projection.status is HarnessRunStatus.PAUSED
            else "reconcile-external-state"
        ),
    }


__all__ = ["capabilities", "dispatch"]

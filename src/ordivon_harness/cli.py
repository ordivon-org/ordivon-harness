from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from .version import package_version
from .ordivon.deepseek import DEFAULT_DEEPSEEK_SECRET_PATH
from .recovery import NATIVE_RUN_RECOVERY_TRIGGERS
from .sqlite_store import SQLiteHarnessStore
from .store_ops import (
    backup_harness_store,
    restore_harness_backup,
    verify_harness_backup,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ordivon-harness",
        description=(
            "Host-free Harness Run operations are the default CLI. "
            "Historical Host-backed operations live under the explicit `host` namespace."
        ),
    )
    parser.add_argument("--config", type=Path, help="legacy Host compatibility config")
    parser.add_argument(
        "--state-root",
        type=Path,
        help="legacy Host state root used by `host` and cutover-* operations",
    )
    parser.add_argument(
        "--harness-state-root",
        type=Path,
        help="independent Harness Journal/CAS root",
    )
    parser.add_argument("--runtime-endpoint", help="legacy Host Runtime override")
    parser.add_argument(
        "--runtime-token-file", type=Path, help="legacy Host Runtime token override"
    )
    parser.add_argument(
        "--deepseek-secret",
        type=Path,
        default=DEFAULT_DEEPSEEK_SECRET_PATH,
        help="DeepSeek settings used by independent or Host-backed execution",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "capabilities",
        help="describe exact Host-free CLI execution capabilities and Contract identities",
    )
    commands.add_parser("doctor", help="validate the independent Harness Journal/CAS")

    status = commands.add_parser("status", help="read one independent Harness Run projection")
    status.add_argument("harness_run_id")

    inspect = commands.add_parser(
        "inspect", help="inspect independent Contract, continuity and terminal evidence"
    )
    inspect.add_argument("harness_run_id")

    run = commands.add_parser(
        "run",
        help="execute one caller-supplied Host-free HarnessRunContract",
    )
    run.add_argument("contract", type=Path, help="HarnessRunContract JSON file")
    _add_independent_input_options(run)

    resume = commands.add_parser("resume", help="resume one paused independent Harness Run")
    resume.add_argument("harness_run_id")
    _add_independent_input_options(resume)

    recover = commands.add_parser(
        "recover", help="assess independent recovery without blind redispatch"
    )
    recover.add_argument("harness_run_id")
    recover.add_argument(
        "--trigger",
        choices=NATIVE_RUN_RECOVERY_TRIGGERS,
        default="process_lost",
    )

    host = commands.add_parser(
        "host",
        help="historical Host-backed compatibility operations",
        description="Explicit compatibility surface for the legacy Host-backed Harness Runner.",
    )
    host_commands = host.add_subparsers(dest="host_command", required=True)
    host_commands.add_parser("doctor")

    host_status = host_commands.add_parser("status")
    host_status.add_argument("task_id")

    host_inspect = host_commands.add_parser("inspect")
    host_inspect.add_argument("task_id")

    host_handoff = host_commands.add_parser("handoff")
    host_handoff.add_argument("task_id")

    host_run = host_commands.add_parser("run")
    host_run.add_argument("task_id")
    _add_execution_options(host_run)

    host_resume = host_commands.add_parser("resume")
    host_resume.add_argument("task_id")
    host_resume.add_argument(
        "--message",
        action="append",
        default=[],
        help="additional user message; may be repeated",
    )
    _add_execution_options(host_resume)

    host_cancel = host_commands.add_parser("cancel")
    host_cancel.add_argument("task_id")

    host_recover = host_commands.add_parser("recover")
    host_recover.add_argument("task_id")
    host_recover.add_argument(
        "--trigger",
        choices=NATIVE_RUN_RECOVERY_TRIGGERS,
        default="host_restart",
    )
    host_recover.add_argument("--no-auto-abandon", action="store_true")

    commands.add_parser("cutover-status")
    commands.add_parser("cutover-inventory")
    commands.add_parser("cutover-activate")
    commands.add_parser("cutover-rollback")
    commands.add_parser("store-init")
    commands.add_parser("store-doctor")

    store_backup = commands.add_parser("store-backup")
    store_backup.add_argument("destination", type=Path)

    store_verify_backup = commands.add_parser("store-verify-backup")
    store_verify_backup.add_argument("backup", type=Path)

    store_restore = commands.add_parser("store-restore")
    store_restore.add_argument("backup", type=Path)
    store_restore.add_argument("destination", type=Path)

    store_inspect = commands.add_parser("store-inspect")
    store_inspect.add_argument("harness_run_id")

    store_events = commands.add_parser("store-events")
    store_events.add_argument("harness_run_id")
    store_events.add_argument("--after-sequence", type=int, default=0)
    return parser


def _add_independent_input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--message",
        action="append",
        default=[],
        help="append one user message; may be repeated",
    )
    parser.add_argument(
        "--messages-json",
        type=Path,
        help="JSON array of exact model message objects",
    )

def _add_execution_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--completion-mode",
        choices=("record", "propose"),
        default="record",
    )
    parser.add_argument("--max-model-calls", type=int)
    parser.add_argument("--max-tool-calls", type=int)
    parser.add_argument("--max-observation-bytes", type=int)
    parser.add_argument("--max-wall-time-ms", type=int)
    parser.add_argument("--max-total-tokens", type=int)
    parser.add_argument("--max-model-retries", type=int)
    parser.add_argument("--max-tool-corrections", type=int)
    parser.add_argument("--max-observation-only-turns", type=int)
    parser.add_argument("--max-no-progress-turns", type=int)
    parser.add_argument("--max-model-observation-bytes", type=int)
    parser.add_argument(
        "--events-jsonl",
        action="store_true",
        help="write live semantic events as JSON Lines to stderr",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command.startswith("store-"):
            result = _dispatch_store(args)
        elif args.command.startswith("cutover-"):
            result = _dispatch_cutover(args)
        elif args.command == "host":
            config = _config(args)
            result = _dispatch_host(config, args)
        else:
            from .independent_cli import dispatch as dispatch_independent

            result = dispatch_independent(args, clock_ms=_wall_clock_ms)
    except (
        ImportError,
        FileNotFoundError,
        KeyError,
        PermissionError,
        ValueError,
        RuntimeError,
    ) as error:
        print(
            json.dumps(
                {"ok": False, "error": type(error).__name__, "message": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result.get("ok", True) is True else 1


def _dispatch_store(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "store-verify-backup":
        return {"ok": True, "backup": verify_harness_backup(args.backup.expanduser())}
    if args.command == "store-restore":
        return {
            "ok": True,
            "restore": restore_harness_backup(
                args.backup.expanduser(),
                args.destination.expanduser(),
            ),
        }
    root = args.harness_state_root
    if root is None:
        raise ValueError("this store command requires --harness-state-root")
    root = root.expanduser()
    if args.command == "store-init":
        with SQLiteHarnessStore.initialize(root) as store:
            report = store.doctor(full=True)
        return {"ok": True, "stateRoot": str(root), "store": report}
    if args.command == "store-backup":
        return {
            "ok": True,
            "backup": backup_harness_store(root, args.destination.expanduser()),
        }
    with SQLiteHarnessStore(root) as store:
        if args.command == "store-doctor":
            return {
                "ok": True,
                "stateRoot": str(root),
                "store": store.doctor(full=True),
            }
        if args.command == "store-inspect":
            return {
                "ok": True,
                "stateRoot": str(root),
                "run": store.load_run(args.harness_run_id).to_dict(),
            }
        if args.command == "store-events":
            events = store.list_run_events(
                args.harness_run_id,
                after_sequence=args.after_sequence,
            )
            return {
                "ok": True,
                "stateRoot": str(root),
                "events": [event.to_dict() for event in events],
            }
    raise ValueError("unsupported Harness store command")


def _dispatch_cutover(args: argparse.Namespace) -> dict[str, object]:
    from .cutover import (
        activate_cutover,
        build_cutover_inventory,
        cutover_status,
        rollback_cutover,
    )

    host_root = args.state_root
    if host_root is None:
        raise ValueError("this cutover command requires --state-root")
    host_root = host_root.expanduser().resolve()
    if args.command == "cutover-status":
        return {"ok": True, "cutover": cutover_status(host_root).to_dict()}
    harness_root = args.harness_state_root
    if harness_root is None:
        raise ValueError("this cutover command requires --harness-state-root")
    harness_root = harness_root.expanduser().resolve()
    now_ms = _wall_clock_ms()
    if args.command == "cutover-inventory":
        inventory = build_cutover_inventory(
            host_root,
            harness_root,
            generated_at_ms=now_ms,
        )
        return {"ok": True, "inventory": inventory.to_dict(), "digest": inventory.digest}
    if args.command == "cutover-activate":
        receipt, inventory = activate_cutover(
            host_root,
            harness_root,
            created_at_ms=now_ms,
        )
        return {
            "ok": True,
            "receipt": receipt.to_dict(),
            "inventory": inventory.to_dict(),
        }
    if args.command == "cutover-rollback":
        receipt, inventory = rollback_cutover(
            host_root,
            harness_root,
            created_at_ms=now_ms,
        )
        return {
            "ok": True,
            "receipt": receipt.to_dict(),
            "inventory": inventory.to_dict(),
        }
    raise ValueError("unsupported Harness cutover command")


def _config(args: argparse.Namespace):
    from ._host_compat.config import load_config

    config = load_config(args.config)
    if args.state_root is not None:
        state_root = args.state_root.expanduser().resolve()
        config = replace(
            config,
            state_root=state_root,
            receipt_root=state_root / "receipts",
        )
    runtime = config.runtime
    if args.runtime_endpoint is not None:
        runtime = replace(runtime, endpoint=args.runtime_endpoint)
    if args.runtime_token_file is not None:
        runtime = replace(
            runtime,
            token_file=args.runtime_token_file.expanduser().resolve(),
        )
    return replace(config, runtime=runtime)


def _dispatch_host(config, args: argparse.Namespace) -> dict[str, object]:
    from ._host_compat.storage import HostStorage
    from .handoff import operator_handoff
    from .history import validate_history
    from .host import HarnessHost
    from .ordivon.deepseek import DeepSeekSettings, DeepSeekTurnAdapter
    from .runner import CompletionMode, HarnessRunner

    if args.host_command == "doctor":
        from .cutover import cutover_status

        with HostStorage(config.state_root, validation_mode="full") as storage:
            report = validate_history(storage).to_dict()
        return {
            "ok": True,
            "healthy": True,
            "stateRoot": str(config.state_root),
            "harnessHistory": report,
            "cutover": cutover_status(config.state_root).to_dict(),
        }

    with HostStorage(config.state_root) as storage:
        host = HarnessHost(storage, clock_ms=_wall_clock_ms)
        if args.host_command == "status":
            return {"ok": True, **HarnessRunner(host).status(args.task_id).to_dict()}
        if args.host_command == "handoff":
            return {"ok": True, "handoff": operator_handoff(storage, args.task_id).to_dict()}
        if args.host_command == "inspect":
            return {
                "ok": True,
                "status": HarnessRunner(host).status(args.task_id).to_dict(),
                "handoff": operator_handoff(storage, args.task_id).to_dict(),
            }

        from .cutover import assert_legacy_writer_allowed

        assert_legacy_writer_allowed(config.state_root)
        runtime = _runtime(config)
        if args.host_command == "cancel":
            result = HarnessRunner(host, runtime=runtime).cancel(args.task_id)
            return {"ok": True, **result.to_dict()}
        if args.host_command == "recover":
            result = HarnessRunner(host, runtime=runtime).recover(
                args.task_id,
                trigger=args.trigger,
                auto_abandon=not args.no_auto_abandon,
            )
            return {
                "ok": True,
                "safeToReplace": result.safe_to_replace,
                "recovery": result.recovery.assessment.to_dict(),
                "abandonment": (
                    None if result.abandonment is None else result.abandonment.abandonment.to_dict()
                ),
            }

        adapter = DeepSeekTurnAdapter(DeepSeekSettings.from_secret_file(args.deepseek_secret))
        runner = HarnessRunner(host, runtime=runtime, adapter=adapter)
        budget = _budget(args, host)
        completion_mode = CompletionMode(args.completion_mode)
        if args.host_command == "run":
            if args.events_jsonl:
                handle = runner.start_current(
                    args.task_id,
                    budget=budget,
                    completion_mode=completion_mode,
                )
                _write_events(handle)
                result = handle.result()
            else:
                result = runner.run_current(
                    args.task_id,
                    budget=budget,
                    completion_mode=completion_mode,
                )
        elif args.host_command == "resume":
            messages = tuple({"role": "user", "content": message} for message in args.message)
            if args.events_jsonl:
                handle = runner.start_resume(
                    args.task_id,
                    additional_messages=messages,
                    budget=budget,
                    completion_mode=completion_mode,
                )
                _write_events(handle)
                result = handle.result()
            else:
                result = runner.resume(
                    args.task_id,
                    additional_messages=messages,
                    budget=budget,
                    completion_mode=completion_mode,
                )
        else:
            raise ValueError("unsupported command")
        return {"ok": True, **result.to_dict()}


def _runtime(config):
    from ._host_compat.config import read_token_file
    from ._host_compat.runtime import McpRuntimeClient

    token = os.environ.get("ORDIVON_BEARER_TOKEN")
    if token is None:
        token = read_token_file(config.runtime.token_file)
    return McpRuntimeClient(
        config.runtime.endpoint,
        token,
        timeout_seconds=config.runtime.timeout_seconds,
        max_response_bytes=config.runtime.max_response_bytes,
        client_name="ordivon-harness",
        client_version=package_version(),
    )


def _budget(args: argparse.Namespace, host):
    from .ordivon.loop import RunBudget

    values = (
        args.max_model_calls,
        args.max_tool_calls,
        args.max_observation_bytes,
        args.max_wall_time_ms,
        args.max_total_tokens,
        args.max_model_retries,
        args.max_tool_corrections,
        args.max_observation_only_turns,
        args.max_no_progress_turns,
        args.max_model_observation_bytes,
    )
    if all(value is None for value in values):
        return None
    committed = host.load_current_assignment(args.task_id)
    raw = committed.assignment.budget

    def selected(
        value: int | None,
        name: str,
        fallback: int,
        *,
        allow_zero: bool = False,
    ) -> int:
        if value is not None:
            return value
        retained = raw.get(name)
        minimum = 0 if allow_zero else 1
        return retained if type(retained) is int and retained >= minimum else fallback

    return RunBudget(
        selected(args.max_model_calls, "maxModelCalls", 8),
        selected(args.max_tool_calls, "maxToolCalls", 16),
        selected(args.max_observation_bytes, "maxObservationBytes", 1_048_576),
        selected(args.max_wall_time_ms, "maxWallTimeMs", 600_000),
        selected(args.max_total_tokens, "maxTotalTokens", 131_072),
        selected(
            args.max_model_retries,
            "maxModelRetries",
            2,
            allow_zero=True,
        ),
        selected(
            args.max_tool_corrections,
            "maxToolCorrections",
            3,
            allow_zero=True,
        ),
        selected(
            args.max_observation_only_turns,
            "maxObservationOnlyTurns",
            6,
            allow_zero=True,
        ),
        selected(
            args.max_no_progress_turns,
            "maxNoProgressTurns",
            3,
            allow_zero=True,
        ),
        selected(
            args.max_model_observation_bytes,
            "maxModelObservationBytes",
            32_768,
        ),
    )


def _write_events(handle) -> None:
    for event in handle.iter_events():
        print(json.dumps(event.to_dict(), sort_keys=True), file=sys.stderr, flush=True)


def _wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


def entrypoint() -> None:
    raise SystemExit(main())

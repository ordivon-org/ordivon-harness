from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from .ordivon.deepseek import DEFAULT_DEEPSEEK_SECRET_PATH
from .recovery import NATIVE_RUN_RECOVERY_TRIGGERS
from .sqlite_store import SQLiteHarnessStore
from .store_ops import backup_harness_store, restore_harness_backup, verify_harness_backup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ordivon-harness",
        description="Caller-neutral Harness Run execution and durable recovery.",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        help="Harness Journal/CAS root",
    )
    parser.add_argument(
        "--deepseek-secret",
        type=Path,
        default=DEFAULT_DEEPSEEK_SECRET_PATH,
        help="DeepSeek settings for the built-in no-Tool execution profile",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    capabilities = commands.add_parser(
        "capabilities",
        help="project, search, or inspect the package-resolved capability surface",
    )
    capabilities.add_argument(
        "--query",
        help="return bounded task-conditioned capability candidates instead of the full catalog",
    )
    capabilities.add_argument(
        "--term",
        action="append",
        default=[],
        help="add an explicit discovery term; may be repeated",
    )
    capabilities.add_argument(
        "--owner",
        action="append",
        default=[],
        help="prefer candidates from an exact owner id; may be repeated",
    )
    capabilities.add_argument(
        "--limit",
        type=int,
        default=8,
        help="maximum candidates returned by --query (1-64)",
    )
    capabilities.add_argument(
        "--inspect",
        dest="inspect_capability_id",
        help="inspect one exact source-derived capability descriptor",
    )
    commands.add_parser("doctor")
    status = commands.add_parser("status")
    status.add_argument("harness_run_id")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("harness_run_id")
    explain = commands.add_parser(
        "explain",
        help="project one durable Run as a capability/composition workbench view",
    )
    explain.add_argument("harness_run_id")
    telemetry = commands.add_parser(
        "telemetry",
        help="project compact read-only Run usage, budget, cache, and recovery telemetry",
    )
    telemetry.add_argument("harness_run_id")
    run = commands.add_parser("run")
    run.add_argument("contract", type=Path)
    _add_input_options(run)
    resume = commands.add_parser("resume")
    resume.add_argument("harness_run_id")
    _add_input_options(resume)
    recover = commands.add_parser("recover")
    recover.add_argument("harness_run_id")
    recover.add_argument(
        "--trigger",
        choices=NATIVE_RUN_RECOVERY_TRIGGERS,
        default="process_lost",
    )
    commands.add_parser("store-init")
    commands.add_parser("store-doctor")
    store_backup = commands.add_parser("store-backup")
    store_backup.add_argument("destination", type=Path)
    store_verify = commands.add_parser("store-verify-backup")
    store_verify.add_argument("backup", type=Path)
    store_restore = commands.add_parser("store-restore")
    store_restore.add_argument("backup", type=Path)
    store_restore.add_argument("destination", type=Path)
    store_inspect = commands.add_parser("store-inspect")
    store_inspect.add_argument("harness_run_id")
    store_events = commands.add_parser("store-events")
    store_events.add_argument("harness_run_id")
    store_events.add_argument("--after-sequence", type=int, default=0)
    return parser


def _add_input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--message", action="append", default=[])
    parser.add_argument("--messages-json", type=Path)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command.startswith("store-"):
            result = _dispatch_store(args)
        else:
            from .independent_cli import dispatch
            result = dispatch(args, clock_ms=_wall_clock_ms)
    except (
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
                args.backup.expanduser(), args.destination.expanduser()
            ),
        }
    root = _state_root(args)
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
            return {"ok": True, "stateRoot": str(root), "store": store.doctor(full=True)}
        if args.command == "store-inspect":
            return {
                "ok": True,
                "stateRoot": str(root),
                "run": store.load_run(args.harness_run_id).to_dict(),
            }
        if args.command == "store-events":
            events = store.list_run_events(
                args.harness_run_id, after_sequence=args.after_sequence
            )
            return {
                "ok": True,
                "stateRoot": str(root),
                "events": [event.to_dict() for event in events],
            }
    raise ValueError("unsupported Harness store command")


def _state_root(args: argparse.Namespace) -> Path:
    if args.state_root is None:
        raise ValueError("Harness command requires --state-root")
    return args.state_root.expanduser().resolve()


def _wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()

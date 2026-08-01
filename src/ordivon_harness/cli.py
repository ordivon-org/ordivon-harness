from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from ordivon_host.storage import HostStorage

from .history import validate_history


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ordivon-harness")
    parser.add_argument("--state-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command != "doctor":
            raise ValueError("unsupported command")
        with HostStorage(args.state_root, validation_mode="full") as storage:
            report = validate_history(storage).to_dict()
        result = {
            "healthy": True,
            "stateRoot": str(args.state_root),
            "harnessHistory": report,
        }
    except BaseException as error:
        result = {
            "healthy": False,
            "stateRoot": str(args.state_root),
            "error": type(error).__name__,
            "message": str(error),
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["healthy"] is True else 1


def entrypoint() -> None:
    raise SystemExit(main())

"""Small diagnostic CLI for the qualified Origin K01 path."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .exporter import export_k01
from .models import OriginExportFailure, OriginPreflightFailure
from .preflight import preflight_origin


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m plotagent.origin.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "export-k01"):
        item = subparsers.add_parser(command)
        item.add_argument("target", help="absolute .opju target path")
        item.add_argument("--timeout", type=float, default=30.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preflight":
        preflight_result = preflight_origin(args.target, timeout_seconds=args.timeout)
        print(
            json.dumps(preflight_result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        )
        return 2 if isinstance(preflight_result, OriginPreflightFailure) else 0
    export_result = export_k01(args.target, timeout_seconds=args.timeout)
    print(json.dumps(export_result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if isinstance(export_result, OriginExportFailure) else 0


if __name__ == "__main__":
    raise SystemExit(main())

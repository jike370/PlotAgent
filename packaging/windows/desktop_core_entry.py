"""Stable PyInstaller entry for the desktop Core and sealed Origin worker."""

from __future__ import annotations

import sys

from plotagent.desktop_core.__main__ import main as core_main
from plotagent.engine.backends.origin.worker import main as origin_worker_main


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--origin-worker"]:
        return origin_worker_main(args[1:])
    if args:
        raise SystemExit("usage: plotagent-core [--origin-worker REQUEST_JSON RESPONSE_JSON]")
    return core_main()

if __name__ == "__main__":
    raise SystemExit(main())

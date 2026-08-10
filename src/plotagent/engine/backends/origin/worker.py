"""Sealed Origin automation worker entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from .k01 import execute_k01_request
from .k08 import execute_k08_request
from .messages import OriginWorkerRequest, OriginWorkerResponse


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        raise SystemExit("usage: origin worker REQUEST_JSON RESPONSE_JSON")
    request_path, response_path = (Path(value).resolve() for value in args)
    request = OriginWorkerRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    binders = {"K01": execute_k01_request, "K08": execute_k08_request}
    try:
        binder = binders[request.document.profile_id]
    except KeyError as exc:
        raise ValueError(f"Origin worker has no binder for {request.document.profile_id}") from exc

    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        readback = binder(
            op,
            request,
            Path(request.install_dir).resolve(),
            Path(request.output_opju).resolve(),
        )
        response_path.write_text(
            OriginWorkerResponse(readback=readback).model_dump_json(indent=2),
            encoding="utf-8",
        )
    finally:
        op.exit()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

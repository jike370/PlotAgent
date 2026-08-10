"""Dedicated hidden Origin worker for probe, typed build, and fresh reopen.

This module deliberately contains no attach call, caller-supplied script, formula,
property path, or template path. It is launched in a new process for every phase.
"""

from __future__ import annotations

import gc
import json
import math
import os
import sys
import traceback
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from plotagent.contracts.rendering import OriginExportPlan


@dataclass(slots=True)
class WorkerFailure(Exception):
    code: str
    message: str
    details: dict[str, Any]


def _fail(code: str, message: str, **details: Any) -> NoReturn:
    raise WorkerFailure(code, message, details)


def _probe(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"expected_runtime_version"}:
        _fail("START_FAILURE", "probe payload contains missing or unknown fields")
    import originpro as op  # type: ignore[import-untyped]

    try:
        root = op.root_folder()
        runtime_version = float(op.org_ver())
        if not root.obj.IsValid():
            _fail("LICENSE_UNAVAILABLE", "Origin root project is unavailable")
        expected = float(payload["expected_runtime_version"])
        if not math.isclose(runtime_version, expected, rel_tol=0.0, abs_tol=1e-12):
            _fail(
                "VERSION_UNSUPPORTED",
                "Origin runtime version differs from the build declaration",
                runtime_version=runtime_version,
            )
        return {"status": "ok", "runtime_version": runtime_version}
    except WorkerFailure:
        raise
    except Exception as exc:
        message = str(exc)
        code = (
            "LICENSE_UNAVAILABLE"
            if "licen" in message.lower() or "activat" in message.lower()
            else "START_FAILURE"
        )
        _fail(code, "dedicated Origin license probe failed", error=message)
    finally:
        with suppress(UnboundLocalError):
            del root
        gc.collect()
        op.exit()


def _prepare_origin_session_exit(op: Any, backend: Any | None = None) -> None:
    """Close the saved project and release its native handles."""

    op.new(asksave=False)
    if backend is not None:
        backend.release_native_handles()
    gc.collect()


def _write_worker_response(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _build_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"plan", "install_dir", "temporary_opju_path"}:
        _fail("BUILD_FAILURE", "typed-plan build payload contains missing or unknown fields")
    plan = OriginExportPlan.model_validate_json(json.dumps(payload["plan"], ensure_ascii=False))
    temporary_path = Path(str(payload["temporary_opju_path"])).resolve(strict=False)
    install_dir = Path(str(payload["install_dir"])).resolve(strict=True)
    import originpro as op

    from ._origin_backend import OriginProBackend
    from .native import build_native_project
    from .validation import expected_validation_sha256

    try:
        backend = OriginProBackend(op, install_dir)
        runtime_version = float(op.org_ver())
        report_sha256 = expected_validation_sha256(plan)

        def emit_validated_report(report: dict[str, object]) -> None:
            # OriginExt Save may finish writing while its COM call stays blocked.
            # The parent independently waits for a stable non-empty OPJU.
            _write_worker_response(
                {
                    "status": "ok",
                    "runtime_version": runtime_version,
                    "validation": {
                        "report": report,
                        "report_sha256": report_sha256,
                    },
                    "temporary_size": 0,
                }
            )

        report = build_native_project(
            backend,
            plan,
            str(temporary_path),
            on_validated=emit_validated_report,
        )
        return {
            "status": "ok",
            "runtime_version": runtime_version,
            "validation": {
                "report": report,
                "report_sha256": report_sha256,
            },
            "temporary_size": temporary_path.stat().st_size,
        }
    except WorkerFailure:
        raise
    except Exception as exc:
        _fail("BUILD_FAILURE", "typed native Origin construction failed", error=str(exc))
    finally:
        _prepare_origin_session_exit(op, locals().get("backend"))


def _reopen_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"plan", "install_dir", "temporary_opju_path"}:
        _fail("REOPEN_FAILURE", "typed-plan reopen payload contains missing or unknown fields")
    plan = OriginExportPlan.model_validate_json(json.dumps(payload["plan"], ensure_ascii=False))
    temporary_path = Path(str(payload["temporary_opju_path"])).resolve(strict=True)
    install_dir = Path(str(payload["install_dir"])).resolve(strict=True)
    import originpro as op

    from ._origin_backend import OriginProBackend
    from .native import inspect_native_project
    from .validation import expected_validation_sha256

    try:
        root = op.root_folder()
        if root.obj.Folders.GetCount() != 0 or root.obj.PageBases().GetCount() != 0:
            _fail("REOPEN_FAILURE", "fresh validation instance was not blank before load")
        if not op.open(str(temporary_path), readonly=True, asksave=False):
            _fail("REOPEN_FAILURE", "fresh Origin instance could not open the temporary OPJU")
        backend = OriginProBackend(op, install_dir)
        report = inspect_native_project(backend, plan)
        return {
            "status": "ok",
            "runtime_version": float(op.org_ver()),
            "validation": {
                "report": report,
                "report_sha256": expected_validation_sha256(plan),
            },
        }
    except WorkerFailure:
        raise
    except Exception as exc:
        _fail("REOPEN_FAILURE", "typed native Origin fresh reopen failed", error=str(exc))
    finally:
        _prepare_origin_session_exit(op, locals().get("backend"))


def _finalize_plan_worker(exit_code: int) -> NoReturn:
    import originpro as op

    try:
        op.exit()
    finally:
        os._exit(exit_code)


def _emit_worker_response(payload: dict[str, Any], exit_code: int) -> int:
    _write_worker_response(payload)
    if len(sys.argv) == 2 and sys.argv[1] in {"build-plan", "reopen-plan"}:
        # Emit the result before OriginExt begins its potentially blocking exit.
        _finalize_plan_worker(exit_code)
    return exit_code


def _main() -> int:
    handlers = {
        "probe": _probe,
        "build-plan": _build_plan,
        "reopen-plan": _reopen_plan,
    }
    if len(sys.argv) != 2 or sys.argv[1] not in handlers:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": {"code": "START_FAILURE", "message": "invalid worker mode"},
                }
            )
        )
        return 2
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            _fail("START_FAILURE", "worker payload must be a JSON object")
        result = handlers[sys.argv[1]](payload)
        return _emit_worker_response(result, 0)
    except WorkerFailure as exc:
        return _emit_worker_response(
            {
                "status": "error",
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
            2,
        )
    except Exception as exc:
        return _emit_worker_response(
            {
                "status": "error",
                "error": {
                    "code": "START_FAILURE",
                    "message": str(exc),
                    "details": {"traceback": traceback.format_exc(limit=5)},
                },
            },
            2,
        )


if __name__ == "__main__":
    raise SystemExit(_main())

"""Two-instance K01 OPJU export with fresh readback and atomic publication."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from ._process import WorkerInvocation, run_worker
from .constants import WORKER_DEFAULT_TIMEOUT_SECONDS
from .k01 import K01Data, K01OriginPlan, compile_k01_plan
from .models import (
    JsonValue,
    OriginError,
    OriginErrorCode,
    OriginExportFailure,
    OriginExportResult,
    OriginExportSuccess,
    OriginPreflightFailure,
    OriginStage,
)
from .preflight import preflight_origin, validate_target


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worker_error(
    invocation: WorkerInvocation,
    *,
    fallback_code: OriginErrorCode,
    stage: OriginStage,
) -> OriginError:
    if invocation.timed_out:
        return OriginError(
            code=fallback_code,
            stage=stage,
            message=f"dedicated Origin {stage.value} worker timed out",
            retryable=True,
        )
    payload: dict[str, Any] = invocation.payload or {}
    raw_error_value = payload.get("error")
    raw_error: dict[str, Any] = raw_error_value if isinstance(raw_error_value, dict) else {}
    raw_code = raw_error.get("code", fallback_code.value)
    try:
        code = OriginErrorCode(str(raw_code))
    except ValueError:
        code = fallback_code
    raw_details = raw_error.get("details")
    details: dict[str, JsonValue] = raw_details if isinstance(raw_details, dict) else {}
    if invocation.stderr:
        details = {**details, "worker_stderr": invocation.stderr}
    return OriginError(
        code=code,
        stage=stage,
        message=str(raw_error.get("message", f"Origin {stage.value} worker failed")),
        retryable=code in {OriginErrorCode.START_FAILURE, OriginErrorCode.REOPEN_FAILURE},
        details=details,
    )


def _failure(
    target: Path,
    started: float,
    error: OriginError,
    *,
    preflight: OriginPreflightFailure | None = None,
) -> OriginExportFailure:
    return OriginExportFailure(
        status="failed",
        target_path=str(target),
        error=error,
        elapsed_seconds=round(time.monotonic() - started, 3),
        preflight=preflight,
    )


def export_k01(
    target_path: str | os.PathLike[str],
    data: K01Data | None = None,
    *,
    expected_existing_sha256: str | None = None,
    timeout_seconds: float = WORKER_DEFAULT_TIMEOUT_SECONDS,
) -> OriginExportResult:
    """Create, fresh-reopen validate, and atomically publish one native K01 OPJU."""

    started = time.monotonic()
    target = Path(target_path).expanduser().resolve(strict=False)
    preflight = preflight_origin(
        target,
        expected_existing_sha256=expected_existing_sha256,
        timeout_seconds=timeout_seconds,
    )
    if isinstance(preflight, OriginPreflightFailure):
        return _failure(target, started, preflight.error, preflight=preflight)
    plan: K01OriginPlan = compile_k01_plan(preflight.environment, data)
    task_directory = Path(tempfile.mkdtemp(prefix=".plotagent-origin-k01-", dir=target.parent))
    temporary_opju = task_directory / "k01-building.opju"
    worker_plan = plan.to_dict()
    try:
        build = run_worker(
            "build",
            {
                "plan": worker_plan,
                "install_dir": preflight.environment.install_dir,
                "temporary_opju_path": str(temporary_opju),
            },
            timeout_seconds,
        )
        if not build.ok or build.payload is None:
            return _failure(
                target,
                started,
                _worker_error(
                    build, fallback_code=OriginErrorCode.BUILD_FAILURE, stage=OriginStage.BUILD
                ),
            )
        reopen = run_worker(
            "reopen",
            {"plan": worker_plan, "temporary_opju_path": str(temporary_opju)},
            timeout_seconds,
        )
        if not reopen.ok or reopen.payload is None:
            return _failure(
                target,
                started,
                _worker_error(
                    reopen,
                    fallback_code=OriginErrorCode.REOPEN_FAILURE,
                    stage=OriginStage.REOPEN,
                ),
            )
        build_validation = build.payload.get("validation")
        reopen_validation = reopen.payload.get("validation")
        if not isinstance(build_validation, dict) or not isinstance(reopen_validation, dict):
            return _failure(
                target,
                started,
                OriginError(
                    code=OriginErrorCode.VALIDATION_FAILURE,
                    stage=OriginStage.VALIDATE,
                    message="Origin worker omitted a typed validation report",
                ),
            )
        if build_validation != reopen_validation or (
            reopen_validation.get("report_sha256") != plan.validation_report_sha256
        ):
            return _failure(
                target,
                started,
                OriginError(
                    code=OriginErrorCode.VALIDATION_FAILURE,
                    stage=OriginStage.VALIDATE,
                    message="live and fresh-reopen reports are not identical",
                ),
            )
        target_failure = validate_target(
            target, expected_existing_sha256=expected_existing_sha256
        )
        if target_failure is not None:
            return _failure(target, started, target_failure.error)
        try:
            os.replace(temporary_opju, target)
        except PermissionError as exc:
            return _failure(
                target,
                started,
                OriginError(
                    code=OriginErrorCode.TARGET_LOCKED,
                    stage=OriginStage.COMMIT,
                    message="target became locked before atomic publication",
                    retryable=True,
                    details={"os_error": str(exc)},
                ),
            )
        except OSError as exc:
            return _failure(
                target,
                started,
                OriginError(
                    code=OriginErrorCode.SAVE_FAILURE,
                    stage=OriginStage.COMMIT,
                    message="atomic OPJU publication failed",
                    details={"os_error": str(exc)},
                ),
            )
        return OriginExportSuccess(
            status="succeeded",
            target_path=str(target),
            file_sha256=_sha256_file(target),
            file_size=target.stat().st_size,
            render_plan_sha256=plan.render_plan_sha256,
            validation_report_sha256=plan.validation_report_sha256,
            build_validation=build_validation,
            reopen_validation=reopen_validation,
            environment=preflight.environment,
            elapsed_seconds=round(time.monotonic() - started, 3),
        )
    finally:
        shutil.rmtree(task_directory, ignore_errors=True)

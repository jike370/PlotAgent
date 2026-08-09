"""Typed public results and stable errors for Origin operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class OriginErrorCode(StrEnum):
    """Stable W6 errors from the Origin export contract."""

    NOT_INSTALLED = "NOT_INSTALLED"
    VERSION_UNSUPPORTED = "VERSION_UNSUPPORTED"
    LICENSE_UNAVAILABLE = "LICENSE_UNAVAILABLE"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    TEMPLATE_OR_FONT_MISSING = "TEMPLATE_OR_FONT_MISSING"
    START_FAILURE = "START_FAILURE"
    BUILD_FAILURE = "BUILD_FAILURE"
    SAVE_FAILURE = "SAVE_FAILURE"
    REOPEN_FAILURE = "REOPEN_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    TARGET_LOCKED = "TARGET_LOCKED"
    EXTERNAL_MODIFIED = "EXTERNAL_MODIFIED"
    CANCELLED = "CANCELLED"


class OriginStage(StrEnum):
    PREFLIGHT = "preflight"
    PROBE = "probe"
    BUILD = "build"
    SAVE = "save"
    REOPEN = "reopen"
    VALIDATE = "validate"
    COMMIT = "commit"
    CLEANUP = "cleanup"


@dataclass(frozen=True, slots=True)
class OriginError:
    code: OriginErrorCode
    stage: OriginStage
    message: str
    retryable: bool = False
    details: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "code": self.code.value,
            "stage": self.stage.value,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class OriginEnvironment:
    display_name: str
    display_version: str
    install_dir: str
    executable_path: str
    origin_bitness: int
    python_bitness: int
    originpro_version: str
    runtime_version: float
    template_sha256: str
    license_available: bool
    discovery_source: Literal["configured", "portable", "registry"] = "registry"

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "display_name": self.display_name,
            "display_version": self.display_version,
            "install_dir": self.install_dir,
            "executable_path": self.executable_path,
            "origin_bitness": self.origin_bitness,
            "python_bitness": self.python_bitness,
            "originpro_version": self.originpro_version,
            "runtime_version": self.runtime_version,
            "template_sha256": self.template_sha256,
            "license_available": self.license_available,
            "discovery_source": self.discovery_source,
        }


@dataclass(frozen=True, slots=True)
class OriginPreflightSuccess:
    status: Literal["ready"]
    target_path: str
    environment: OriginEnvironment

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "status": self.status,
            "target_path": self.target_path,
            "environment": self.environment.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class OriginPreflightFailure:
    status: Literal["error"]
    target_path: str
    error: OriginError

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "status": self.status,
            "target_path": self.target_path,
            "error": self.error.to_dict(),
        }


type OriginPreflightResult = OriginPreflightSuccess | OriginPreflightFailure


@dataclass(frozen=True, slots=True)
class OriginExportSuccess:
    status: Literal["succeeded"]
    target_path: str
    file_sha256: str
    file_size: int
    render_plan_sha256: str
    validation_report_sha256: str
    build_validation: dict[str, JsonValue]
    reopen_validation: dict[str, JsonValue]
    environment: OriginEnvironment
    elapsed_seconds: float

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "status": self.status,
            "target_path": self.target_path,
            "file_sha256": self.file_sha256,
            "file_size": self.file_size,
            "render_plan_sha256": self.render_plan_sha256,
            "validation_report_sha256": self.validation_report_sha256,
            "build_validation": self.build_validation,
            "reopen_validation": self.reopen_validation,
            "environment": self.environment.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass(frozen=True, slots=True)
class OriginExportFailure:
    status: Literal["failed"]
    target_path: str
    error: OriginError
    elapsed_seconds: float
    preflight: OriginPreflightResult | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "status": self.status,
            "target_path": self.target_path,
            "error": self.error.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
        }
        if self.preflight is not None:
            payload["preflight"] = self.preflight.to_dict()
        return payload


type OriginExportResult = OriginExportSuccess | OriginExportFailure

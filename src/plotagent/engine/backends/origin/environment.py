"""Local Origin discovery and export-target preflight for the Agent Native backend."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from ctypes import (
    POINTER,
    Structure,
    WinDLL,
    byref,
    c_uint,
    c_void_p,
    c_wchar_p,
    cast,
    create_string_buffer,
    sizeof,
)
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

_SUPPORTED_FILE_VERSION = (10, 1, 0)
_ORIGIN_EXECUTABLE_NAME = re.compile(r"^origin(?:64|\d+)?\.exe$", re.IGNORECASE)

_ORIGIN_RELEASE_NAMES = {
    (9, 8, 0): "OriginPro 2021",
    (9, 8, 5): "OriginPro 2021b",
    (9, 9, 0): "OriginPro 2022",
    (9, 9, 5): "OriginPro 2022b",
    (10, 0, 0): "OriginPro 2023",
    (10, 0, 5): "OriginPro 2023b",
    (10, 1, 0): "OriginPro 2024",
    (10, 1, 5): "OriginPro 2024b",
    (10, 2, 0): "OriginPro 2025",
    (10, 2, 5): "OriginPro 2025b",
    (10, 3, 0): "OriginPro 2026",
    (10, 3, 5): "OriginPro 2026b",
}


class OriginErrorCode(StrEnum):
    NOT_INSTALLED = "NOT_INSTALLED"
    VERSION_UNSUPPORTED = "VERSION_UNSUPPORTED"
    LICENSE_UNAVAILABLE = "LICENSE_UNAVAILABLE"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    TEMPLATE_OR_FONT_MISSING = "TEMPLATE_OR_FONT_MISSING"
    START_FAILURE = "START_FAILURE"
    SAVE_FAILURE = "SAVE_FAILURE"
    EXTERNAL_MODIFIED = "EXTERNAL_MODIFIED"


@dataclass(frozen=True, slots=True)
class OriginEnvironment:
    display_name: str
    display_version: str
    install_dir: str
    executable_path: str
    discovery_source: Literal["configured", "portable", "registry"]

    def to_dict(self) -> dict[str, object]:
        return {
            "display_name": self.display_name,
            "display_version": self.display_version,
            "install_dir": self.install_dir,
            "executable_path": self.executable_path,
            "discovery_source": self.discovery_source,
        }


@dataclass(frozen=True, slots=True)
class OriginError:
    code: OriginErrorCode
    message: str
    retryable: bool = False
    environment: OriginEnvironment | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True, slots=True)
class OriginPreflightFailure:
    target_path: str
    error: OriginError
    environment: OriginEnvironment | None = None
    status: Literal["error"] = "error"

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "status": self.status,
            "target_path": self.target_path,
            "error": self.error.to_dict(),
        }
        if self.environment is not None:
            value["environment"] = self.environment.to_dict()
        return value


@dataclass(frozen=True, slots=True)
class OriginPreflightSuccess:
    target_path: str
    environment: OriginEnvironment
    status: Literal["ready"] = "ready"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "target_path": self.target_path,
            "environment": self.environment.to_dict(),
        }


OriginPreflightResult = OriginPreflightFailure | OriginPreflightSuccess


class _FixedFileInfo(Structure):
    _fields_ = [
        ("signature", c_uint),
        ("structure_version", c_uint),
        ("file_version_ms", c_uint),
        ("file_version_ls", c_uint),
        ("product_version_ms", c_uint),
        ("product_version_ls", c_uint),
        ("file_flags_mask", c_uint),
        ("file_flags", c_uint),
        ("file_os", c_uint),
        ("file_type", c_uint),
        ("file_subtype", c_uint),
        ("file_date_ms", c_uint),
        ("file_date_ls", c_uint),
    ]


def _file_version(path: Path) -> tuple[int, int, int, int] | None:
    """Read the signed Windows file-version resource without launching Origin."""

    if os.name != "nt":
        return None
    version = WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [c_wchar_p, POINTER(c_uint)]
    version.GetFileVersionInfoSizeW.restype = c_uint
    version.GetFileVersionInfoW.argtypes = [c_wchar_p, c_uint, c_uint, c_void_p]
    version.GetFileVersionInfoW.restype = c_uint
    version.VerQueryValueW.argtypes = [
        c_void_p,
        c_wchar_p,
        POINTER(c_void_p),
        POINTER(c_uint),
    ]
    version.VerQueryValueW.restype = c_uint
    ignored = c_uint(0)
    size = int(version.GetFileVersionInfoSizeW(str(path), byref(ignored)))
    if size <= 0:
        return None
    buffer = create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    value = c_void_p()
    value_size = c_uint(0)
    if not version.VerQueryValueW(buffer, "\\", byref(value), byref(value_size)):
        return None
    if value_size.value < sizeof(_FixedFileInfo):
        return None
    if value.value is None:
        return None
    info = cast(value.value, POINTER(_FixedFileInfo)).contents
    if info.signature != 0xFEEF04BD:
        return None
    return (
        info.file_version_ms >> 16,
        info.file_version_ms & 0xFFFF,
        info.file_version_ls >> 16,
        info.file_version_ls & 0xFFFF,
    )


def _failure(
    target: Path,
    code: OriginErrorCode,
    message: str,
    *,
    retryable: bool = False,
    environment: OriginEnvironment | None = None,
) -> OriginPreflightFailure:
    return OriginPreflightFailure(
        target_path=str(target),
        error=OriginError(code=code, message=message, retryable=retryable),
        environment=environment,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _environment_for_executable(
    executable: Path,
    source: Literal["configured", "portable", "registry"],
) -> OriginEnvironment | OriginError | None:
    resolved = executable.resolve(strict=False)
    if _ORIGIN_EXECUTABLE_NAME.fullmatch(resolved.name) is None or not resolved.is_file():
        return None
    version = _file_version(resolved)
    if version is None:
        return OriginError(
            code=OriginErrorCode.VERSION_UNSUPPORTED,
            message="The Origin executable version could not be verified.",
        )
    environment = OriginEnvironment(
        display_name=_ORIGIN_RELEASE_NAMES.get(version[:3], "OriginPro"),
        display_version=".".join(str(item) for item in version[:3]),
        install_dir=str(resolved.parent),
        executable_path=str(resolved),
        discovery_source=source,
    )
    if version[:3] != _SUPPORTED_FILE_VERSION:
        actual = ".".join(str(item) for item in version[:3])
        expected = ".".join(str(item) for item in _SUPPORTED_FILE_VERSION)
        return OriginError(
            code=OriginErrorCode.VERSION_UNSUPPORTED,
            message=f"Origin {actual} is unsupported; this build requires {expected}.",
            environment=environment,
        )
    return environment


def _discover_installation(
    configured_executable: str | os.PathLike[str] | None = None,
) -> OriginEnvironment | OriginError | None:
    configured = configured_executable or os.environ.get("PLOTAGENT_ORIGIN_EXECUTABLE")
    if configured:
        return _environment_for_executable(
            Path(configured).expanduser(),
            "configured",
        )
    candidates: list[tuple[Path, Literal["configured", "portable", "registry"]]] = []
    candidates.append((Path(r"D:\origin\Origin64.exe"), "portable"))
    if os.name == "nt":
        import winreg

        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                try:
                    root = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view)
                except OSError:
                    continue
                with root:
                    index = 0
                    while True:
                        try:
                            child_name = winreg.EnumKey(root, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            child = winreg.OpenKey(root, child_name)
                            with child:
                                name = str(winreg.QueryValueEx(child, "DisplayName")[0])
                                location = str(winreg.QueryValueEx(child, "InstallLocation")[0])
                        except OSError:
                            continue
                        if name.startswith("Origin"):
                            candidates.append((Path(location) / "Origin64.exe", "registry"))
    seen: set[str] = set()
    first_version_error: OriginError | None = None
    for executable, source in candidates:
        resolved = executable.resolve(strict=False)
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        result = _environment_for_executable(resolved, source)
        if isinstance(result, OriginEnvironment):
            return result
        if isinstance(result, OriginError) and first_version_error is None:
            first_version_error = result
    return first_version_error


def preflight_origin(
    target_path: str | os.PathLike[str],
    *,
    expected_existing_sha256: str | None = None,
    configured_executable: str | os.PathLike[str] | None = None,
) -> OriginPreflightResult:
    """Validate a user-authorized OPJU target and locate a usable local Origin install."""

    target = Path(target_path).expanduser().resolve(strict=False)
    if target.suffix.casefold() != ".opju":
        return _failure(target, OriginErrorCode.SAVE_FAILURE, "Target must use .opju.")
    if not target.parent.is_dir():
        return _failure(
            target,
            OriginErrorCode.SAVE_FAILURE,
            "The selected destination folder does not exist.",
        )
    if target.exists():
        if not target.is_file():
            return _failure(target, OriginErrorCode.SAVE_FAILURE, "Target is not a file.")
        if expected_existing_sha256 is None or _sha256(target) != expected_existing_sha256:
            return _failure(
                target,
                OriginErrorCode.EXTERNAL_MODIFIED,
                "The existing OPJU differs from the authorized export target.",
            )
    if shutil.disk_usage(target.parent).free < 16 * 1024 * 1024:
        return _failure(target, OriginErrorCode.SAVE_FAILURE, "Insufficient free disk space.")
    environment = (
        _discover_installation(configured_executable)
        if configured_executable is not None
        else _discover_installation()
    )
    if environment is None:
        return _failure(
            target,
            OriginErrorCode.NOT_INSTALLED,
            "No supported local Origin installation was found.",
        )
    if isinstance(environment, OriginError):
        return _failure(
            target,
            environment.code,
            environment.message,
            retryable=environment.retryable,
            environment=environment.environment,
        )
    return OriginPreflightSuccess(target_path=str(target), environment=environment)

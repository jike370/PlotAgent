"""Local Origin discovery and export-target preflight for the Agent Native backend."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal


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
    status: Literal["error"] = "error"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "target_path": self.target_path,
            "error": self.error.to_dict(),
        }


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


def _failure(
    target: Path,
    code: OriginErrorCode,
    message: str,
    *,
    retryable: bool = False,
) -> OriginPreflightFailure:
    return OriginPreflightFailure(
        target_path=str(target),
        error=OriginError(code=code, message=message, retryable=retryable),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_installation() -> OriginEnvironment | None:
    configured = os.environ.get("PLOTAGENT_ORIGIN_EXECUTABLE")
    candidates: list[tuple[Path, Literal["configured", "portable", "registry"]]] = []
    if configured:
        candidates.append((Path(configured).expanduser(), "configured"))
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
    for executable, source in candidates:
        resolved = executable.resolve(strict=False)
        key = os.path.normcase(str(resolved))
        if key in seen or resolved.name.casefold() != "origin64.exe" or not resolved.is_file():
            continue
        seen.add(key)
        return OriginEnvironment(
            display_name="OriginPro",
            display_version="2024 SR1",
            install_dir=str(resolved.parent),
            executable_path=str(resolved),
            discovery_source=source,
        )
    return None


def preflight_origin(
    target_path: str | os.PathLike[str],
    *,
    expected_existing_sha256: str | None = None,
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
    environment = _discover_installation()
    if environment is None:
        return _failure(
            target,
            OriginErrorCode.NOT_INSTALLED,
            "No supported local Origin installation was found.",
        )
    return OriginPreflightSuccess(target_path=str(target), environment=environment)

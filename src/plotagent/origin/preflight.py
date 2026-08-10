"""Exact-version, bitness, package, license, target, and lock preflight."""

from __future__ import annotations

import ctypes
import hashlib
import importlib.metadata
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ._process import run_worker
from .constants import (
    DECLARED_ORIGIN_BITNESS,
    DECLARED_ORIGIN_DISPLAY_NAME,
    DECLARED_ORIGIN_DISPLAY_VERSION,
    DECLARED_ORIGIN_RUNTIME_VERSION,
    DECLARED_ORIGINPRO_VERSION,
    MIN_FREE_TARGET_BYTES,
    ORIGIN_EXECUTABLE,
    WORKER_DEFAULT_TIMEOUT_SECONDS,
)
from .models import (
    JsonValue,
    OriginEnvironment,
    OriginError,
    OriginErrorCode,
    OriginPreflightFailure,
    OriginPreflightResult,
    OriginPreflightSuccess,
    OriginStage,
)
from .template_catalog import OriginTemplateCatalogError, validate_official_template_catalog


@dataclass(frozen=True, slots=True)
class _Installation:
    display_name: str
    display_version: str
    install_dir: Path
    discovery_source: Literal["configured", "portable", "registry"] = "registry"


def _configured_installation() -> tuple[_Installation | None, dict[str, JsonValue]]:
    configured = os.environ.get("PLOTAGENT_ORIGIN_EXECUTABLE")
    if configured:
        executable = Path(configured).expanduser().resolve(strict=False)
        details: dict[str, JsonValue] = {
            "discovery_source": "configured",
            "configured_executable_path": str(executable),
        }
        if executable.name.casefold() != ORIGIN_EXECUTABLE.casefold() or not executable.is_file():
            return None, details
        return (
            _Installation(
                DECLARED_ORIGIN_DISPLAY_NAME,
                DECLARED_ORIGIN_DISPLAY_VERSION,
                executable.parent,
                "configured",
            ),
            details,
        )
    return None, {"discovery_source": "registry"}


def _portable_installation() -> _Installation | None:
    if os.name != "nt":
        return None
    executable = Path(r"D:\origin\Origin64.exe")
    if not executable.is_file():
        return None
    return _Installation(
        DECLARED_ORIGIN_DISPLAY_NAME,
        DECLARED_ORIGIN_DISPLAY_VERSION,
        executable.parent,
        "portable",
    )


def _error(
    target: Path,
    code: OriginErrorCode,
    message: str,
    *,
    details: dict[str, JsonValue] | None = None,
    retryable: bool = False,
    stage: OriginStage = OriginStage.PREFLIGHT,
) -> OriginPreflightFailure:
    return OriginPreflightFailure(
        status="error",
        target_path=str(target),
        error=OriginError(
            code=code,
            stage=stage,
            message=message,
            retryable=retryable,
            details=details or {},
        ),
    )


def _find_installations() -> list[_Installation]:
    if os.name != "nt":
        return []
    import winreg

    locations: list[_Installation] = []
    views = (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY)
    hives = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    seen: set[tuple[str, str, str]] = set()
    for hive in hives:
        for view in views:
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
                            display_name = str(winreg.QueryValueEx(child, "DisplayName")[0])
                            display_version = str(winreg.QueryValueEx(child, "DisplayVersion")[0])
                            install_dir = Path(
                                str(winreg.QueryValueEx(child, "InstallLocation")[0])
                            )
                    except OSError:
                        continue
                    if not display_name.startswith("Origin"):
                        continue
                    identity = (
                        display_name,
                        display_version,
                        os.path.normcase(str(install_dir.resolve(strict=False))),
                    )
                    if identity not in seen:
                        seen.add(identity)
                        locations.append(_Installation(display_name, display_version, install_dir))
    return sorted(
        locations,
        key=lambda item: (item.display_version, str(item.install_dir)),
    )


def _pe_bitness(executable: Path) -> int:
    with executable.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Origin executable does not have an MZ header")
        stream.seek(0x3C)
        pe_offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(pe_offset)
        if stream.read(4) != b"PE\x00\x00":
            raise ValueError("Origin executable does not have a PE header")
        machine = struct.unpack("<H", stream.read(2))[0]
    if machine == 0x8664:
        return 64
    if machine == 0x014C:
        return 32
    raise ValueError(f"unsupported Origin PE machine: 0x{machine:04x}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_file_sha256(path: Path) -> str:
    return _sha256_file(path)


def _exclusive_open_existing(path: Path) -> bool:
    if os.name != "nt" or not path.exists():
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    handle = create_file(str(path), 0xC0000000, 0, None, 3, 0x80, None)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        return False
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True


def validate_target(
    target_path: str | os.PathLike[str],
    *,
    expected_existing_sha256: str | None = None,
) -> OriginPreflightFailure | None:
    target = Path(target_path).expanduser().resolve(strict=False)
    if target.suffix.lower() != ".opju":
        return _error(target, OriginErrorCode.SAVE_FAILURE, "target must use the .opju suffix")
    parent = target.parent
    if not parent.is_dir():
        return _error(
            target,
            OriginErrorCode.SAVE_FAILURE,
            "target directory does not exist",
            details={"target_directory": str(parent)},
        )
    if target.exists():
        if not target.is_file():
            return _error(target, OriginErrorCode.SAVE_FAILURE, "target is not a regular file")
        if expected_existing_sha256 is None:
            return _error(
                target,
                OriginErrorCode.EXTERNAL_MODIFIED,
                "refusing to overwrite an existing OPJU without its expected SHA-256",
            )
        current_hash = _current_file_sha256(target)
        if current_hash.lower() != expected_existing_sha256.lower():
            return _error(
                target,
                OriginErrorCode.EXTERNAL_MODIFIED,
                "existing OPJU does not match the expected export record hash",
                details={"current_sha256": current_hash},
            )
        if not _exclusive_open_existing(target):
            return _error(
                target,
                OriginErrorCode.TARGET_LOCKED,
                "target OPJU is locked by another process",
                retryable=True,
            )
    if shutil.disk_usage(parent).free < MIN_FREE_TARGET_BYTES:
        return _error(
            target,
            OriginErrorCode.SAVE_FAILURE,
            "target directory does not have the minimum free space for the K01 spike",
        )
    probe_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(prefix=".plotagent-write-probe-", dir=parent)
        probe_path = Path(raw_path)
        os.write(descriptor, b"plotagent")
        os.fsync(descriptor)
        os.close(descriptor)
    except OSError as exc:
        return _error(
            target,
            OriginErrorCode.SAVE_FAILURE,
            "target directory is not writable",
            details={"os_error": str(exc)},
        )
    finally:
        if probe_path is not None:
            probe_path.unlink(missing_ok=True)
    return None


def preflight_origin(
    target_path: str | os.PathLike[str],
    *,
    expected_existing_sha256: str | None = None,
    timeout_seconds: float = WORKER_DEFAULT_TIMEOUT_SECONDS,
) -> OriginPreflightResult:
    target = Path(target_path).expanduser().resolve(strict=False)
    target_failure = validate_target(target, expected_existing_sha256=expected_existing_sha256)
    if target_failure is not None:
        return target_failure
    configured_installation, discovery_details = _configured_installation()
    if os.environ.get("PLOTAGENT_ORIGIN_EXECUTABLE") and configured_installation is None:
        return _error(
            target,
            OriginErrorCode.NOT_INSTALLED,
            "the configured Origin executable is unavailable",
            details=discovery_details,
        )
    installations = (
        [configured_installation] if configured_installation is not None else _find_installations()
    )
    if not installations:
        portable_installation = _portable_installation()
        if portable_installation is not None:
            installations = [portable_installation]
            discovery_details = {
                "discovery_source": "portable",
                "configured_executable_path": str(
                    portable_installation.install_dir / ORIGIN_EXECUTABLE
                ),
            }
    if not installations:
        return _error(
            target,
            OriginErrorCode.NOT_INSTALLED,
            "Origin is not installed",
            details=discovery_details,
        )
    supported = [
        item
        for item in installations
        if item.display_name == DECLARED_ORIGIN_DISPLAY_NAME
        and item.display_version == DECLARED_ORIGIN_DISPLAY_VERSION
    ]
    if not supported:
        detected: list[JsonValue] = [
            {
                "display_name": item.display_name,
                "display_version": item.display_version,
            }
            for item in installations
        ]
        return _error(
            target,
            OriginErrorCode.VERSION_UNSUPPORTED,
            f"this build supports only {DECLARED_ORIGIN_DISPLAY_VERSION}",
            details={
                "declared_version": DECLARED_ORIGIN_DISPLAY_VERSION,
                "detected": detected,
            },
        )
    installation = supported[0]
    executable = installation.install_dir / ORIGIN_EXECUTABLE
    if not executable.is_file():
        return _error(
            target,
            OriginErrorCode.NOT_INSTALLED,
            "the declared Origin installation is missing Origin64.exe",
        )
    try:
        origin_bitness = _pe_bitness(executable)
    except (OSError, ValueError) as exc:
        return _error(
            target,
            OriginErrorCode.VERSION_UNSUPPORTED,
            "could not verify Origin executable bitness",
            details={"error": str(exc)},
        )
    python_bitness = struct.calcsize("P") * 8
    if origin_bitness != DECLARED_ORIGIN_BITNESS or python_bitness != origin_bitness:
        return _error(
            target,
            OriginErrorCode.VERSION_UNSUPPORTED,
            "Origin, Python, and the build declaration must all be 64-bit",
            details={
                "declared_bitness": DECLARED_ORIGIN_BITNESS,
                "origin_bitness": origin_bitness,
                "python_bitness": python_bitness,
            },
        )
    try:
        originpro_version = importlib.metadata.version("originpro")
    except importlib.metadata.PackageNotFoundError:
        return _error(
            target,
            OriginErrorCode.CAPABILITY_MISSING,
            "originpro is not installed in the active Python environment",
        )
    if originpro_version != DECLARED_ORIGINPRO_VERSION:
        return _error(
            target,
            OriginErrorCode.VERSION_UNSUPPORTED,
            f"this build supports only originpro {DECLARED_ORIGINPRO_VERSION}",
            details={"detected_originpro_version": originpro_version},
        )
    try:
        template_hash = validate_official_template_catalog(installation.install_dir)
    except OriginTemplateCatalogError as error:
        return _error(
            target,
            OriginErrorCode.TEMPLATE_OR_FONT_MISSING,
            "the registered Origin official template catalog is unavailable or modified",
            details={"error": str(error)},
        )
    probe = run_worker(
        "probe",
        {"expected_runtime_version": DECLARED_ORIGIN_RUNTIME_VERSION},
        timeout_seconds,
    )
    if probe.timed_out:
        return _error(
            target,
            OriginErrorCode.START_FAILURE,
            "the dedicated Origin license probe timed out",
            retryable=True,
            stage=OriginStage.PROBE,
        )
    if not probe.ok or probe.payload is None:
        payload: dict[str, Any] = probe.payload or {}
        raw_code = payload.get("error", {}).get("code", OriginErrorCode.START_FAILURE.value)
        try:
            code = OriginErrorCode(str(raw_code))
        except ValueError:
            code = OriginErrorCode.START_FAILURE
        return _error(
            target,
            code,
            str(payload.get("error", {}).get("message", probe.stderr or "Origin probe failed")),
            retryable=True,
            stage=OriginStage.PROBE,
        )
    runtime_version = float(probe.payload["runtime_version"])
    if abs(runtime_version - DECLARED_ORIGIN_RUNTIME_VERSION) > 1e-12:
        return _error(
            target,
            OriginErrorCode.VERSION_UNSUPPORTED,
            "Origin runtime version does not match the declared build",
            details={"detected_runtime_version": runtime_version},
            stage=OriginStage.PROBE,
        )
    environment = OriginEnvironment(
        display_name=installation.display_name,
        display_version=installation.display_version,
        install_dir=str(installation.install_dir.resolve()),
        executable_path=str(executable.resolve()),
        origin_bitness=origin_bitness,
        python_bitness=python_bitness,
        originpro_version=originpro_version,
        runtime_version=runtime_version,
        template_sha256=template_hash,
        license_available=True,
        discovery_source=installation.discovery_source,
    )
    return OriginPreflightSuccess(status="ready", target_path=str(target), environment=environment)

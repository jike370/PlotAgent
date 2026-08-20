from __future__ import annotations

from pathlib import Path

import pytest

import plotagent.engine.backends.origin.environment as environment_module
from plotagent.engine.backends.origin.environment import (
    OriginEnvironment,
    OriginError,
    OriginErrorCode,
    OriginPreflightFailure,
    OriginPreflightSuccess,
    _environment_for_executable,
    preflight_origin,
)


def _executable(tmp_path: Path) -> Path:
    executable = tmp_path / "Origin64.exe"
    executable.write_bytes(b"fixture executable")
    return executable


def test_supported_origin_version_is_read_from_the_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path)
    monkeypatch.setattr(environment_module, "_file_version", lambda _path: (10, 1, 0, 178))

    result = _environment_for_executable(executable, "configured")

    assert result == OriginEnvironment(
        display_name="OriginPro 2024",
        display_version="10.1.0",
        install_dir=str(tmp_path),
        executable_path=str(executable),
        discovery_source="configured",
    )


@pytest.mark.parametrize("version", [(10, 0, 0, 1), (10, 2, 0, 1), (11, 0, 0, 1)])
def test_wrong_origin_version_is_rejected_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: tuple[int, int, int, int],
) -> None:
    executable = _executable(tmp_path)
    monkeypatch.setattr(environment_module, "_file_version", lambda _path: version)

    result = _environment_for_executable(executable, "configured")

    assert isinstance(result, OriginError)
    assert result.code == OriginErrorCode.VERSION_UNSUPPORTED
    assert "requires 10.1.0" in result.message


def test_unversioned_origin_named_file_is_not_trusted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path)
    monkeypatch.setattr(environment_module, "_file_version", lambda _path: None)

    result = _environment_for_executable(executable, "configured")

    assert isinstance(result, OriginError)
    assert result.code == OriginErrorCode.VERSION_UNSUPPORTED
    assert "could not be verified" in result.message


def test_preflight_propagates_version_failure_without_starting_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        environment_module,
        "_discover_installation",
        lambda: OriginError(
            code=OriginErrorCode.VERSION_UNSUPPORTED,
            message="Origin 10.2.0 is unsupported; this build requires 10.1.0.",
        ),
    )

    result = preflight_origin(tmp_path / "result.opju")

    assert isinstance(result, OriginPreflightFailure)
    assert result.error.code == OriginErrorCode.VERSION_UNSUPPORTED
    assert result.error.retryable is False


def test_real_declared_origin_build_has_a_supported_file_version(tmp_path: Path) -> None:
    executable = Path(r"D:\origin\Origin64.exe")
    if not executable.is_file():
        pytest.skip("the declared portable Origin installation is not present")

    result = preflight_origin(tmp_path / "result.opju")

    assert isinstance(result, OriginPreflightSuccess)
    assert result.environment.display_version == "10.1.0"
    assert result.environment.discovery_source in {"configured", "portable", "registry"}

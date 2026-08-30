from __future__ import annotations

from pathlib import Path

import pytest

from scripts.origin_standalone_export import (
    _labtalk_string,
    _origin_executable,
    _standalone_ogs,
)


def test_origin_executable_prefers_origin64(tmp_path: Path) -> None:
    origin64 = tmp_path / "Origin64.exe"
    origin = tmp_path / "Origin.exe"
    origin.write_bytes(b"origin")
    origin64.write_bytes(b"origin64")

    assert _origin_executable(tmp_path) == origin64


def test_origin_executable_rejects_unknown_layout(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no supported Origin executable"):
        _origin_executable(tmp_path)


def test_standalone_ogs_opens_project_and_exports_png(tmp_path: Path) -> None:
    opju = tmp_path / "project folder" / "plot.opju"
    png = tmp_path / "evidence folder" / "fresh.png"

    script = _standalone_ogs(opju, png)

    assert f'string figAgentProject$ = "{_labtalk_string(opju)}";' in script
    assert "doc -o %(figAgentProject$);" in script
    assert f'path:="{_labtalk_string(png.parent)}"' in script
    assert 'filename:="fresh"' in script
    assert "doc -s;" in script
    assert script.rstrip().endswith("exit;")

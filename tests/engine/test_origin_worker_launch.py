from __future__ import annotations

import sys
from pathlib import Path

import pytest

from plotagent.engine.backends.origin.backend import _origin_worker_command


def test_origin_worker_uses_python_module_in_source_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    request = tmp_path / "plot.request.json"
    response = tmp_path / "plot.response.json"

    assert _origin_worker_command(request, response) == (
        sys.executable,
        "-m",
        "plotagent.engine.backends.origin.worker",
        str(request),
        str(response),
    )


def test_origin_worker_uses_explicit_frozen_entry_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    request = tmp_path / "plot.request.json"
    response = tmp_path / "plot.response.json"

    assert _origin_worker_command(request, response) == (
        sys.executable,
        "--origin-worker",
        str(request),
        str(response),
    )

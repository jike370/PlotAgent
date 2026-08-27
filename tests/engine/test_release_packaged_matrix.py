from __future__ import annotations

from scripts import run_release_packaged_matrix as packaged


def test_packaged_matrix_targets_only_the_frozen_release_layout() -> None:
    assert packaged.DESKTOP_EXECUTABLE == (
        packaged.REPOSITORY
        / "release"
        / "windows"
        / "electron"
        / "win-unpacked"
        / "fig-agent.exe"
    )
    assert (
        packaged.DESKTOP_EXECUTABLE.parent
        / "resources"
        / "core"
        / "plotagent-core"
        / "plotagent-core.exe"
    ) == packaged.CORE_EXECUTABLE
    assert packaged.PUBLISH_ROOT.is_relative_to(packaged.REPOSITORY / "release" / "windows")

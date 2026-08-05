from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from plotagent.security import LocalSecurityError, PrivateTempWorkspaceManager


@dataclass
class RecordingPermissions:
    fail_on_call: int | None = None
    paths: list[Path] = field(default_factory=list)

    def make_private(self, path: Path) -> None:
        self.paths.append(path)
        if self.fail_on_call == len(self.paths):
            raise OSError("injected ACL failure with a path that must not escape")


@dataclass
class ToggleRemover:
    fail: bool = True

    def __call__(self, path: Path) -> None:
        if self.fail:
            raise OSError("injected cleanup failure")
        import shutil

        shutil.rmtree(path)


def test_task_workspace_is_random_private_and_cleanup_is_bounded(tmp_path: Path) -> None:
    permissions = RecordingPermissions()
    root = tmp_path / "known-temp-root"
    manager = PrivateTempWorkspaceManager(root, permission_enforcer=permissions)

    workspace = manager.create()

    assert workspace.path.parent == root.resolve()
    assert workspace.path.name == f"task-{workspace.workspace_id}"
    assert len(permissions.paths) == 2
    assert (workspace.path / ".plotagent-task-temp").is_file()
    assert manager.cleanup(workspace).cleaned
    assert not workspace.path.exists()


def test_acl_failure_does_not_leave_task_workspace_or_expose_path(tmp_path: Path) -> None:
    permissions = RecordingPermissions(fail_on_call=2)
    root = tmp_path / "known-temp-root"
    manager = PrivateTempWorkspaceManager(root, permission_enforcer=permissions)

    with pytest.raises(LocalSecurityError) as captured:
        manager.create()

    assert str(captured.value) == "TEMP_ACL_FAILED"
    assert list(root.glob("task-*")) == []


def test_failed_cleanup_is_recoverable_and_reports_only_stable_code(tmp_path: Path) -> None:
    remover = ToggleRemover()
    manager = PrivateTempWorkspaceManager(
        tmp_path / "known-temp-root",
        permission_enforcer=RecordingPermissions(),
        remover=remover,
    )
    workspace = manager.create()

    first = manager.cleanup(workspace)
    assert first.cleaned is False
    assert first.error_code == "TEMP_CLEANUP_FAILED"
    assert workspace.path.exists()

    remover.fail = False
    second = manager.cleanup(workspace)
    assert second.cleaned is True
    assert not workspace.path.exists()


def test_startup_recovery_ignores_unmarked_directories(tmp_path: Path) -> None:
    root = tmp_path / "known-temp-root"
    manager = PrivateTempWorkspaceManager(root, permission_enforcer=RecordingPermissions())
    stale = manager.create()
    unrelated = root / "task-not-owned"
    unrelated.mkdir()
    (unrelated / "user-file.txt").write_text("keep", encoding="utf-8")

    results = manager.recover_stale()

    assert [result.workspace_id for result in results] == [stale.workspace_id]
    assert unrelated.is_dir()
    assert (unrelated / "user-file.txt").read_text(encoding="utf-8") == "keep"

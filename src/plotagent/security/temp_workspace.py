"""Private per-task temporary workspaces with bounded recovery cleanup."""

from __future__ import annotations

import getpass
import os
import shutil
import stat
import subprocess
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from plotagent.security.errors import LocalSecurityError


class PermissionEnforcer(Protocol):
    def make_private(self, path: Path) -> None: ...


class WindowsPrivateAcl:
    """Remove inherited ACLs and grant the current Windows account full control."""

    def make_private(self, path: Path) -> None:
        if os.name != "nt":
            raise OSError("Windows ACL enforcement is required")
        domain = os.environ.get("USERDOMAIN")
        username = os.environ.get("USERNAME") or getpass.getuser()
        principal = f"{domain}\\{username}" if domain else username
        result = subprocess.run(
            [
                "icacls.exe",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{principal}:(OI)(CI)F",
            ],
            check=False,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise OSError("private ACL could not be applied")


@dataclass(frozen=True, slots=True)
class TaskWorkspace:
    workspace_id: str
    path: Path


@dataclass(frozen=True, slots=True)
class CleanupResult:
    workspace_id: str
    cleaned: bool
    error_code: str | None = None


class PrivateTempWorkspaceManager:
    """Manage only immediate, marked children of one application-owned temp root."""

    _MARKER = ".plotagent-task-temp"
    _PREFIX = "task-"

    def __init__(
        self,
        root: Path,
        *,
        permission_enforcer: PermissionEnforcer | None = None,
        remover: Callable[[Path], None] | None = None,
    ) -> None:
        self.root = root.resolve(strict=False)
        self._permission_enforcer = permission_enforcer or WindowsPrivateAcl()
        self._remover = remover or self._remove_tree
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self._permission_enforcer.make_private(self.root)
        except OSError as error:
            raise LocalSecurityError("TEMP_ACL_FAILED", category="temp_acl") from error

    def create(self) -> TaskWorkspace:
        workspace_id = str(uuid.uuid4())
        path = self.root / f"{self._PREFIX}{workspace_id}"
        try:
            path.mkdir(mode=0o700)
            self._permission_enforcer.make_private(path)
            marker = path / self._MARKER
            marker.write_text(workspace_id, encoding="ascii")
            os.chmod(marker, stat.S_IREAD | stat.S_IWRITE)
        except (OSError, ValueError) as error:
            with suppress(OSError):
                self._remove_tree(path)
            raise LocalSecurityError("TEMP_ACL_FAILED", category="temp_acl") from error
        return TaskWorkspace(workspace_id=workspace_id, path=path)

    def cleanup(self, workspace: TaskWorkspace) -> CleanupResult:
        if not self._is_managed(workspace.path, workspace.workspace_id):
            return CleanupResult(
                workspace_id=workspace.workspace_id,
                cleaned=False,
                error_code="TEMP_CLEANUP_FAILED",
            )
        try:
            self._remover(workspace.path)
        except OSError:
            return CleanupResult(
                workspace_id=workspace.workspace_id,
                cleaned=False,
                error_code="TEMP_CLEANUP_FAILED",
            )
        return CleanupResult(workspace_id=workspace.workspace_id, cleaned=True)

    def recover_stale(self) -> tuple[CleanupResult, ...]:
        results: list[CleanupResult] = []
        for candidate in self.root.iterdir():
            if not candidate.is_dir() or not candidate.name.startswith(self._PREFIX):
                continue
            workspace_id = candidate.name.removeprefix(self._PREFIX)
            if not self._is_managed(candidate, workspace_id):
                continue
            results.append(self.cleanup(TaskWorkspace(workspace_id, candidate)))
        return tuple(results)

    def _is_managed(self, path: Path, workspace_id: str) -> bool:
        try:
            relative = path.resolve(strict=True).relative_to(self.root)
        except (OSError, ValueError):
            return False
        if len(relative.parts) != 1 or relative.name != f"{self._PREFIX}{workspace_id}":
            return False
        marker = path / self._MARKER
        try:
            return marker.is_file() and marker.read_text(encoding="ascii") == workspace_id
        except (OSError, UnicodeError):
            return False

    @staticmethod
    def _remove_tree(path: Path) -> None:
        shutil.rmtree(path)

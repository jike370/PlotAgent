"""Local fixed-disk policy for active SQLite/WAL workspaces."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from plotagent.storage.errors import StorageErrorCode, StorageProblem

_DRIVE_FIXED = 3


def ensure_local_fixed_workspace(path: Path) -> Path:
    resolved = path.resolve()
    if str(resolved).startswith("\\\\"):
        raise StorageProblem(
            StorageErrorCode.WORKSPACE_FILESYSTEM_UNSUPPORTED,
            "活动项目工作区不能位于 UNC 或网络共享。",
        )
    if os.name == "nt":
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(resolved.anchor)
        if drive_type != _DRIVE_FIXED:
            raise StorageProblem(
                StorageErrorCode.WORKSPACE_FILESYSTEM_UNSUPPORTED,
                "活动项目工作区必须位于本机固定磁盘。",
            )
    return resolved

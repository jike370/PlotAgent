"""Minimal global catalog: project locations, recent access, and settings only."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.models import CatalogProject
from plotagent.storage.schema import (
    CATALOG_SCHEMA_VERSION,
    initialize_catalog_schema,
    validate_schema,
)
from plotagent.storage.workspace import ensure_local_fixed_workspace


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Catalog:
    def __init__(self, path: Path, *, initialize: bool) -> None:
        self.path = path.resolve()
        self._thread_id = threading.get_ident()
        self._closed = False
        self._connection = sqlite3.connect(self.path, isolation_level=None)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA synchronous = FULL")
        try:
            if initialize:
                initialize_catalog_schema(self._connection)
            else:
                validate_schema(
                    self._connection,
                    CATALOG_SCHEMA_VERSION,
                    "plotagent-catalog",
                )
        except Exception:
            self._connection.close()
            raise

    @classmethod
    def create(cls, path: str | Path) -> Self:
        catalog_path = Path(path).resolve()
        ensure_local_fixed_workspace(catalog_path.parent)
        if catalog_path.exists():
            raise StorageProblem(
                StorageErrorCode.PROJECT_ALREADY_EXISTS,
                "catalog 已存在。",
            )
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return cls(catalog_path, initialize=True)
        except Exception:
            catalog_path.unlink(missing_ok=True)
            raise

    @classmethod
    def open(cls, path: str | Path) -> Self:
        catalog_path = Path(path).resolve()
        if not catalog_path.is_file():
            raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "catalog 不存在。")
        return cls(catalog_path, initialize=False)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _connection_for_write(self) -> sqlite3.Connection:
        if self._closed:
            raise StorageProblem(StorageErrorCode.PROJECT_CLOSED, "catalog 已关闭。")
        if threading.get_ident() != self._thread_id:
            raise StorageProblem(
                StorageErrorCode.PROJECT_WRITER_THREAD,
                "catalog 写入必须使用单一线程。",
            )
        return self._connection

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._connection.close()

    def register_project(
        self,
        *,
        project_id: str,
        workspace_path: str | Path,
        display_name: str | None = None,
    ) -> CatalogProject:
        connection = self._connection_for_write()
        now = _utc_now()
        resolved = str(ensure_local_fixed_workspace(Path(workspace_path)))
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO projects(
                    project_id, workspace_path, display_name, created_at, last_opened_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, resolved, display_name, now, now),
            )
            connection.commit()
        except sqlite3.DatabaseError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise StorageProblem(
                StorageErrorCode.CATALOG_FAILED,
                "项目未注册到 catalog。",
            ) from exc
        return CatalogProject(
            project_id=project_id,
            workspace_path=resolved,
            display_name=display_name,
            created_at=now,
            last_opened_at=now,
        )

    def touch_project(self, project_id: str) -> None:
        connection = self._connection_for_write()
        cursor = connection.execute(
            "UPDATE projects SET last_opened_at = ? WHERE project_id = ?",
            (_utc_now(), project_id),
        )
        if cursor.rowcount != 1:
            raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "catalog 中没有该项目。")

    def list_projects(self) -> tuple[CatalogProject, ...]:
        connection = self._connection_for_write()
        return tuple(
            CatalogProject(
                project_id=project_id,
                workspace_path=workspace_path,
                display_name=display_name,
                created_at=created_at,
                last_opened_at=last_opened_at,
            )
            for (
                project_id,
                workspace_path,
                display_name,
                created_at,
                last_opened_at,
            ) in connection.execute(
                """
                SELECT project_id, workspace_path, display_name, created_at, last_opened_at
                FROM projects ORDER BY last_opened_at DESC, project_id
                """
            )
        )

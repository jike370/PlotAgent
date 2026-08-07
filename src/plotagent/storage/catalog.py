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
        source_project_id: str | None = None,
        package_sha256: str | None = None,
    ) -> CatalogProject:
        connection = self._connection_for_write()
        now = _utc_now()
        resolved = str(ensure_local_fixed_workspace(Path(workspace_path)))
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO projects(
                    project_id, workspace_path, display_name, source_project_id,
                    package_sha256, created_at, last_opened_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    resolved,
                    display_name,
                    source_project_id,
                    package_sha256,
                    now,
                    now,
                ),
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
            source_project_id=source_project_id,
            package_sha256=package_sha256,
            created_at=now,
            last_opened_at=now,
        )

    def find_imported_project(
        self, *, package_sha256: str, source_project_id: str
    ) -> CatalogProject | None:
        connection = self._connection_for_write()
        row = connection.execute(
            """
            SELECT project_id, workspace_path, display_name, source_project_id,
                   package_sha256, created_at, last_opened_at
            FROM projects
            WHERE package_sha256 = ? OR source_project_id = ? OR project_id = ?
            ORDER BY
                CASE WHEN project_id = ? THEN 0
                     WHEN package_sha256 = ? THEN 1
                     ELSE 2 END,
                last_opened_at DESC,
                project_id
            LIMIT 1
            """,
            (
                package_sha256,
                source_project_id,
                source_project_id,
                source_project_id,
                package_sha256,
            ),
        ).fetchone()
        if row is None:
            return None
        return CatalogProject(
            project_id=str(row[0]),
            workspace_path=str(row[1]),
            display_name=row[2],
            source_project_id=row[3],
            package_sha256=row[4],
            created_at=str(row[5]),
            last_opened_at=str(row[6]),
        )

    def touch_project(self, project_id: str) -> None:
        connection = self._connection_for_write()
        cursor = connection.execute(
            "UPDATE projects SET last_opened_at = ? WHERE project_id = ?",
            (_utc_now(), project_id),
        )
        if cursor.rowcount != 1:
            raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "catalog 中没有该项目。")

    def rename_project(self, project_id: str, display_name: str) -> CatalogProject:
        connection = self._connection_for_write()
        normalized_name = display_name.strip()
        if not normalized_name:
            raise StorageProblem(StorageErrorCode.CATALOG_FAILED, "项目名称不能为空。")
        cursor = connection.execute(
            "UPDATE projects SET display_name = ? WHERE project_id = ?",
            (normalized_name, project_id),
        )
        if cursor.rowcount != 1:
            raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "catalog 中没有该项目。")
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        connection = self._connection_for_write()
        cursor = connection.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        if cursor.rowcount != 1:
            raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "catalog 中没有该项目。")

    def list_projects(self) -> tuple[CatalogProject, ...]:
        connection = self._connection_for_write()
        return tuple(
            CatalogProject(
                project_id=project_id,
                workspace_path=workspace_path,
                display_name=display_name,
                source_project_id=source_project_id,
                package_sha256=package_sha256,
                created_at=created_at,
                last_opened_at=last_opened_at,
            )
            for (
                project_id,
                workspace_path,
                display_name,
                source_project_id,
                package_sha256,
                created_at,
                last_opened_at,
            ) in connection.execute(
                """
                SELECT project_id, workspace_path, display_name, source_project_id,
                       package_sha256, created_at, last_opened_at
                FROM projects ORDER BY last_opened_at DESC, project_id
                """
            )
        )

    def get_project(self, project_id: str) -> CatalogProject:
        connection = self._connection_for_write()
        row = connection.execute(
            """
            SELECT project_id, workspace_path, display_name, created_at, last_opened_at
            FROM projects WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.PROJECT_NOT_FOUND, "catalog 中没有该项目。")
        return CatalogProject(
            project_id=str(row[0]),
            workspace_path=str(row[1]),
            display_name=None if row[2] is None else str(row[2]),
            created_at=str(row[3]),
            last_opened_at=str(row[4]),
        )

    def get_setting(self, key: str) -> str | None:
        """Return one application-scoped JSON setting without interpreting it."""

        connection = self._connection_for_write()
        row = connection.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_setting(self, key: str, value_json: str) -> None:
        """Atomically replace one application-scoped JSON setting."""

        connection = self._connection_for_write()
        connection.execute(
            """
            INSERT INTO settings(key, value_json) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
            """,
            (key, value_json),
        )

    def delete_setting(self, key: str) -> None:
        """Remove one application-scoped setting if it exists."""

        self._connection_for_write().execute("DELETE FROM settings WHERE key = ?", (key,))

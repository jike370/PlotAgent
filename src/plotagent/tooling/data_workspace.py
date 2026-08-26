"""Task-isolated, restart-safe staging for immutable Agent data handles."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pyarrow.parquet as pq  # type: ignore

from plotagent.contracts.agent_data import (
    DataOperationKind,
    DataViewHandle,
    DataViewHandleId,
    DataViewLineageStep,
    DataViewOperation,
    DataViewPreview,
    operation_input_handles,
)
from plotagent.contracts.agent_tasks import TaskId, TaskItemIdV2
from plotagent.contracts.base import FieldId
from plotagent.contracts.canonical import JsonValue, canonical_hash, canonical_json
from plotagent.engine.contracts import EngineColumn, EngineDataRef, EngineDataView
from plotagent.engine.data import EngineDataError, engine_values
from plotagent.engine.data_repository import serialize_engine_data_view
from plotagent.engine.ports import EngineDataProvider
from plotagent.storage.project import ProjectStore
from plotagent.tooling.data_workspace_ops import (
    DataWorkspaceError,
    apply_data_view_operation,
    data_payload_hash,
)

_ROW_ID_COLUMN = "__engine_row_id"
_MIN_TTL_SECONDS = 60
_MAX_TTL_SECONDS = 86_400


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StagedDataWorkspace:
    """Persist staged Parquet views without publishing project objects or revisions."""

    def __init__(
        self,
        project: ProjectStore,
        *,
        workspace_root: str | Path | None = None,
        compact_transaction_paths: bool = False,
        clock: Callable[[], datetime] | None = None,
        ttl_seconds: int = 3_600,
    ) -> None:
        if not _MIN_TTL_SECONDS <= ttl_seconds <= _MAX_TTL_SECONDS:
            raise ValueError("staged data TTL must be between 60 seconds and 24 hours")
        self._project = project
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ttl_seconds = ttl_seconds
        self._compact_transaction_paths = compact_transaction_paths
        self._root = (
            project.tmp_root / "agent-data-v2"
            if workspace_root is None
            else Path(workspace_root).resolve()
        )
        self._root.mkdir(parents=True, exist_ok=True)
        self._writer_thread_id = threading.get_ident()
        self._connection: sqlite3.Connection | None = sqlite3.connect(
            self._root / "index.sqlite3",
            isolation_level=None,
            check_same_thread=True,
        )
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_staged_data_views_v2 (
                handle_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                task_version INTEGER NOT NULL CHECK (task_version >= 1),
                item_id TEXT,
                artifact_hash TEXT NOT NULL CHECK (length(artifact_hash) = 64),
                handle_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            ) STRICT;
            CREATE INDEX IF NOT EXISTS idx_agent_staged_data_task_v2
                ON agent_staged_data_views_v2(task_id, task_version, expires_at);
            """
        )

    def __enter__(self) -> StagedDataWorkspace:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _assert_writer(self) -> sqlite3.Connection:
        if self._connection is None:
            raise DataWorkspaceError(
                "DATA_WORKSPACE_CLOSED",
                "The staged data workspace is closed.",
            )
        if threading.get_ident() != self._writer_thread_id:
            raise DataWorkspaceError(
                "DATA_WORKSPACE_THREAD_INVALID",
                "The staged data workspace has a different writer thread.",
            )
        return self._connection

    def stage_source(
        self,
        *,
        task_id: TaskId,
        task_version: int,
        item_id: TaskItemIdV2 | None,
        source: EngineDataRef,
        field_ids: tuple[FieldId, ...],
        provider: EngineDataProvider,
    ) -> DataViewHandle:
        if source.kind != "source":
            raise DataWorkspaceError(
                "DATA_SOURCE_REQUIRED",
                "A source handle must begin from an immutable source revision.",
            )
        if not field_ids or len(field_ids) != len(set(field_ids)):
            raise DataWorkspaceError(
                "DATA_FIELD_SELECTION_INVALID",
                "Source handle fields must be non-empty and unique.",
            )
        try:
            view = provider.materialize(source, field_ids)
        except EngineDataError as error:
            raise DataWorkspaceError(
                "DATA_SOURCE_MATERIALIZATION_FAILED",
                str(error),
            ) from error
        if view.data != source:
            raise DataWorkspaceError(
                "DATA_SOURCE_IDENTITY_MISMATCH",
                "The materialized data does not match the authorized source revision.",
            )
        materialized_fields = tuple(column.field.field_id for column in view.columns)
        if materialized_fields != field_ids:
            raise DataWorkspaceError(
                "DATA_SOURCE_MATERIALIZATION_INVALID",
                "The materialized fields differ from the explicit source selection.",
            )
        operation_payload = cast(
            JsonValue,
            {
                "kind": "source",
                "source": source.model_dump(mode="json"),
                "field_ids": list(field_ids),
            },
        )
        operation_hash = canonical_hash(operation_payload)
        return self._persist(
            task_id=task_id,
            task_version=task_version,
            item_id=item_id,
            parents=(),
            roots=(source,),
            operation_kind="source",
            operation_hash=operation_hash,
            view=view,
            terminal_step=DataViewLineageStep(
                step_id=f"step:{operation_hash[:24]}",
                operation_kind="source",
                parameters_hash=operation_hash,
                output_data_hash=data_payload_hash(view),
            ),
            lineage=(),
        )

    def apply(
        self,
        *,
        task_id: TaskId,
        task_version: int,
        item_id: TaskItemIdV2 | None,
        operation: DataViewOperation,
    ) -> DataViewHandle:
        parent_ids = operation_input_handles(operation)
        parents_and_views = tuple(
            self.get(
                handle_id,
                task_id=task_id,
                task_version=task_version,
                item_id=item_id,
            )
            for handle_id in parent_ids
        )
        parents = tuple(item[0] for item in parents_and_views)
        views = tuple(item[1] for item in parents_and_views)
        result = apply_data_view_operation(operation, views)
        data_hash = data_payload_hash(result)
        operation_hash = canonical_hash(cast(JsonValue, operation.model_dump(mode="json")))
        data_ref = EngineDataRef(
            kind="prepared",
            dataset_id=f"staged:{data_hash[:24]}",
            version=1,
            content_hash=data_hash,
        )
        result = result.model_copy(update={"data": data_ref})
        lineage = self._merged_lineage(parents)
        roots = self._merged_roots(parents)
        terminal = DataViewLineageStep(
            step_id=f"step:{canonical_hash(operation_hash + data_hash)[:24]}",
            operation_kind=operation.kind,
            input_handle_ids=parent_ids,
            input_data_hashes=tuple(parent.data_hash for parent in parents),
            parameters_hash=operation_hash,
            output_data_hash=data_hash,
        )
        return self._persist(
            task_id=task_id,
            task_version=task_version,
            item_id=item_id,
            parents=parent_ids,
            roots=roots,
            operation_kind=operation.kind,
            operation_hash=operation_hash,
            view=result,
            terminal_step=terminal,
            lineage=lineage,
        )

    def get(
        self,
        handle_id: DataViewHandleId,
        *,
        task_id: TaskId,
        task_version: int,
        item_id: TaskItemIdV2 | None,
    ) -> tuple[DataViewHandle, EngineDataView]:
        row = (
            self._assert_writer()
            .execute(
                """
                SELECT handle_json FROM agent_staged_data_views_v2
                WHERE handle_id = ? AND task_id = ? AND task_version = ? AND item_id IS ?
                """,
                (handle_id, task_id, task_version, item_id),
            )
            .fetchone()
        )
        if row is None:
            raise DataWorkspaceError(
                "DATA_HANDLE_NOT_FOUND",
                "The staged data handle is missing or belongs to another task version.",
            )
        handle = DataViewHandle.model_validate_json(str(row[0]))
        if _datetime(handle.expires_at) <= self._clock():
            raise DataWorkspaceError(
                "DATA_HANDLE_EXPIRED",
                "The staged data handle has expired and must be recreated.",
            )
        path = self._artifact_path(handle)
        if not path.is_file() or _file_hash(path) != handle.artifact_hash:
            raise DataWorkspaceError(
                "DATA_HANDLE_CORRUPT",
                "The staged data artifact is missing or differs from its receipt.",
            )
        try:
            table = pq.read_table(path)
            row_ids = tuple(str(value) for value in table[_ROW_ID_COLUMN].to_pylist())
            view = EngineDataView(
                data=handle.data,
                row_ids=row_ids,
                columns=tuple(
                    EngineColumn(
                        field=field,
                        values=engine_values(table[field.field_id].to_pylist()),
                    )
                    for field in handle.fields
                ),
            )
        except Exception as error:
            raise DataWorkspaceError(
                "DATA_HANDLE_CORRUPT",
                "The staged data artifact cannot satisfy its immutable schema.",
            ) from error
        if len(view.row_ids) != handle.row_count or data_payload_hash(view) != handle.data_hash:
            raise DataWorkspaceError(
                "DATA_HANDLE_CORRUPT",
                "The staged data values differ from the immutable handle.",
            )
        return handle, view

    def inspect(
        self,
        handle_id: DataViewHandleId,
        *,
        task_id: TaskId,
        task_version: int,
        item_id: TaskItemIdV2 | None,
    ) -> DataViewHandle:
        return self.get(
            handle_id,
            task_id=task_id,
            task_version=task_version,
            item_id=item_id,
        )[0]

    def preview(
        self,
        handle_id: DataViewHandleId,
        *,
        task_id: TaskId,
        task_version: int,
        item_id: TaskItemIdV2 | None,
        field_ids: tuple[FieldId, ...],
        offset: int = 0,
        limit: int = 5,
    ) -> DataViewPreview:
        if offset < 0 or not 1 <= limit <= 40:
            raise DataWorkspaceError(
                "DATA_PREVIEW_RANGE_INVALID",
                "Preview offset or limit is outside the published bounds.",
            )
        if not field_ids or len(field_ids) != len(set(field_ids)):
            raise DataWorkspaceError(
                "DATA_FIELD_SELECTION_INVALID",
                "Preview fields must be non-empty and unique.",
            )
        handle, view = self.get(
            handle_id,
            task_id=task_id,
            task_version=task_version,
            item_id=item_id,
        )
        columns = {column.field.field_id: column for column in view.columns}
        try:
            selected = tuple(columns[field_id] for field_id in field_ids)
        except KeyError as error:
            raise DataWorkspaceError(
                "DATA_FIELD_NOT_FOUND",
                "A preview field is not present in the staged data view.",
            ) from error
        end = min(offset + limit, handle.row_count)
        rows = tuple(
            tuple(column.values[index] for column in selected) for index in range(offset, end)
        )
        return DataViewPreview(
            handle=handle,
            field_ids=field_ids,
            offset=offset,
            rows=rows,
            has_more=end < handle.row_count,
        )

    def cleanup_expired(self) -> int:
        now = _iso(self._clock())
        connection = self._assert_writer()
        rows = connection.execute(
            """
            SELECT handle_json FROM agent_staged_data_views_v2
            WHERE expires_at <= ? ORDER BY handle_id
            """,
            (now,),
        ).fetchall()
        handles = tuple(DataViewHandle.model_validate_json(str(row[0])) for row in rows)
        if not handles:
            return 0
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.executemany(
                "DELETE FROM agent_staged_data_views_v2 WHERE handle_id = ?",
                ((handle.handle_id,) for handle in handles),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        for handle in handles:
            remaining = connection.execute(
                """
                SELECT COUNT(*) FROM agent_staged_data_views_v2
                WHERE task_id = ? AND artifact_hash = ?
                """,
                (handle.task_id, handle.artifact_hash),
            ).fetchone()
            if remaining is not None and int(remaining[0]) == 0:
                path = self._artifact_path(handle)
                try:
                    path.unlink(missing_ok=True)
                    path.parent.rmdir()
                except OSError:
                    pass
        return len(handles)

    def _persist(
        self,
        *,
        task_id: TaskId,
        task_version: int,
        item_id: TaskItemIdV2 | None,
        parents: tuple[DataViewHandleId, ...],
        roots: tuple[EngineDataRef, ...],
        operation_kind: DataOperationKind,
        operation_hash: str,
        view: EngineDataView,
        terminal_step: DataViewLineageStep,
        lineage: tuple[DataViewLineageStep, ...],
    ) -> DataViewHandle:
        now = self._clock()
        data_hash = data_payload_hash(view)
        payload = serialize_engine_data_view(view)
        artifact_hash = _sha256(payload)
        handle_id: DataViewHandleId = (
            "view:"
            + canonical_hash(
                cast(
                    JsonValue,
                    {
                        "task_id": task_id,
                        "task_version": task_version,
                        "item_id": item_id,
                        "parents": parents,
                        "operation_hash": operation_hash,
                        "data_hash": data_hash,
                    },
                )
            )[:32]
        )
        existing = self._existing(handle_id)
        if existing is not None:
            if _datetime(existing.expires_at) <= now:
                self.cleanup_expired()
            else:
                restored, _view = self.get(
                    handle_id,
                    task_id=task_id,
                    task_version=task_version,
                    item_id=item_id,
                )
                if restored.operation_hash != operation_hash or restored.data_hash != data_hash:
                    raise DataWorkspaceError(
                        "DATA_HANDLE_IDEMPOTENCY_CONFLICT",
                        "A staged handle identity is already bound to different data.",
                    )
                return restored
        handle = DataViewHandle(
            handle_id=handle_id,
            task_id=task_id,
            task_version=task_version,
            item_id=item_id,
            parent_handle_ids=parents,
            root_sources=roots,
            data=view.data,
            operation_kind=operation_kind,
            operation_hash=operation_hash,
            data_hash=data_hash,
            artifact_hash=artifact_hash,
            row_count=len(view.row_ids),
            fields=tuple(column.field for column in view.columns),
            lineage=(*lineage, terminal_step),
            created_at=_iso(now),
            expires_at=_iso(now + timedelta(seconds=self._ttl_seconds)),
        )
        path = self._artifact_path(handle)
        path.parent.mkdir(parents=True, exist_ok=True)
        created = False
        if self._compact_transaction_paths:
            # External SDK roots are caller-selected and may already be deep. The
            # final artifact path contains a task hash and a SHA-256 name, so do not
            # repeat both plus a UUID in the transactional filename on Windows.
            temporary = self._root / f".{uuid.uuid4().hex}.tmp"
        else:
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            if path.exists():
                if _file_hash(path) != artifact_hash:
                    raise DataWorkspaceError(
                        "DATA_HANDLE_CORRUPT",
                        "A staged artifact path contains different bytes.",
                    )
            else:
                os.replace(temporary, path)
                created = True
            connection = self._assert_writer()
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO agent_staged_data_views_v2 (
                        handle_id, task_id, task_version, item_id,
                        artifact_hash, handle_json, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        handle.handle_id,
                        handle.task_id,
                        handle.task_version,
                        handle.item_id,
                        handle.artifact_hash,
                        canonical_json(handle),
                        handle.created_at,
                        handle.expires_at,
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        except sqlite3.IntegrityError as error:
            existing_after_conflict = self._existing(handle_id)
            if existing_after_conflict is None or existing_after_conflict != handle:
                raise DataWorkspaceError(
                    "DATA_HANDLE_IDEMPOTENCY_CONFLICT",
                    "A staged handle identity was concurrently rebound.",
                ) from error
            return existing_after_conflict
        except Exception:
            if created:
                path.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)
        return handle

    def _existing(self, handle_id: DataViewHandleId) -> DataViewHandle | None:
        row = (
            self._assert_writer()
            .execute(
                "SELECT handle_json FROM agent_staged_data_views_v2 WHERE handle_id = ?",
                (handle_id,),
            )
            .fetchone()
        )
        return None if row is None else DataViewHandle.model_validate_json(str(row[0]))

    @staticmethod
    def _merged_roots(parents: tuple[DataViewHandle, ...]) -> tuple[EngineDataRef, ...]:
        result: list[EngineDataRef] = []
        identities: set[tuple[str, int, str]] = set()
        for parent in parents:
            for source in parent.root_sources:
                identity = (source.dataset_id, source.version, source.content_hash)
                if identity not in identities:
                    result.append(source)
                    identities.add(identity)
        return tuple(result)

    @staticmethod
    def _merged_lineage(
        parents: tuple[DataViewHandle, ...],
    ) -> tuple[DataViewLineageStep, ...]:
        result: list[DataViewLineageStep] = []
        seen: set[str] = set()
        for parent in parents:
            for step in parent.lineage:
                if step.step_id not in seen:
                    result.append(step)
                    seen.add(step.step_id)
        if len(result) >= 64:
            raise DataWorkspaceError(
                "DATA_LINEAGE_LIMIT_EXCEEDED",
                "The staged data operation chain exceeds the published limit.",
            )
        return tuple(result)

    def _artifact_path(self, handle: DataViewHandle) -> Path:
        task_directory = canonical_hash(handle.task_id)[:32]
        path = self._root / task_directory / f"{handle.artifact_hash}.parquet"
        try:
            path.resolve().relative_to(self._root.resolve())
        except (OSError, ValueError) as error:
            raise DataWorkspaceError(
                "DATA_HANDLE_CORRUPT",
                "The staged data artifact path escaped its task workspace.",
            ) from error
        return path


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

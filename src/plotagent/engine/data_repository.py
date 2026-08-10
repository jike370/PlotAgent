"""Persistent prepared/calculated data views for the replacement engine."""

from __future__ import annotations

import io
import json
from datetime import date, datetime
from typing import cast

import pyarrow as pa  # type: ignore
import pyarrow.parquet as pq  # type: ignore
from pydantic import TypeAdapter

from plotagent.contracts.base import FieldId
from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
)
from plotagent.engine.data import EngineDataError, _engine_values
from plotagent.storage.project import ProjectStore, _utc_now

_FIELDS_ADAPTER: TypeAdapter[tuple[EngineField, ...]] = TypeAdapter(tuple[EngineField, ...])
_ROW_ID_COLUMN = "__engine_row_id"


class EngineDataViewRepository:
    """Store non-source engine data without the legacy plot-input tables."""

    def __init__(self, project: ProjectStore) -> None:
        self._project = project
        project._assert_writer().executescript(  # noqa: SLF001
            """
            CREATE TABLE IF NOT EXISTS engine_data_view_versions (
                data_kind TEXT NOT NULL CHECK (data_kind IN ('prepared', 'calculated')),
                dataset_id TEXT NOT NULL,
                data_version INTEGER NOT NULL CHECK (data_version >= 1),
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                view_hash TEXT NOT NULL CHECK (length(view_hash) = 64),
                table_object_hash TEXT NOT NULL REFERENCES objects(content_hash)
                    ON DELETE RESTRICT,
                field_schema_json TEXT NOT NULL,
                row_count INTEGER NOT NULL CHECK (row_count > 0),
                created_at TEXT NOT NULL,
                PRIMARY KEY (data_kind, dataset_id, data_version),
                UNIQUE (data_kind, dataset_id, content_hash)
            );
            """
        )

    def register(self, view: EngineDataView) -> EngineDataView:
        if view.data.kind == "source":
            raise ValueError("source data remains authoritative in source_dataset_versions")
        existing = self._row(view.data, require_hash=False)
        if existing is not None:
            if str(existing[0]) != view.data.content_hash:
                raise EngineDataError("derived data version is already bound to different values")
            persisted = self.get(view.data)
            if canonical_hash(persisted) != canonical_hash(view):
                raise EngineDataError("derived data version is already bound to different values")
            return persisted

        payload = _parquet_bytes(view)
        staged = self._project.stage_bytes(
            payload,
            media_type="application/vnd.apache.parquet",
        )
        created_path = None
        connection = self._project._assert_writer()  # noqa: SLF001
        try:
            path, created = self._project._promote(staged)  # noqa: SLF001
            created_path = path if created else None
            now = _utc_now()
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO objects(content_hash, media_type, size, ref_count, created_at)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(content_hash) DO NOTHING
                """,
                (staged.content_hash, staged.media_type, staged.size, now),
            )
            connection.execute(
                """
                INSERT INTO engine_data_view_versions (
                    data_kind, dataset_id, data_version, content_hash, view_hash,
                    table_object_hash, field_schema_json, row_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    view.data.kind,
                    view.data.dataset_id,
                    view.data.version,
                    view.data.content_hash,
                    canonical_hash(view),
                    staged.content_hash,
                    json.dumps(
                        [column.field.model_dump(mode="json") for column in view.columns],
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    len(view.row_ids),
                    now,
                ),
            )
            owner_id = f"{view.data.kind}:{view.data.dataset_id}@{view.data.version}"
            connection.execute(
                """
                INSERT INTO object_refs(owner_type, owner_id, role, content_hash)
                VALUES ('engine_data_view', ?, 'table', ?)
                """,
                (owner_id, staged.content_hash),
            )
            connection.execute(
                "UPDATE objects SET ref_count = ref_count + 1 WHERE content_hash = ?",
                (staged.content_hash,),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            if created_path is not None:
                try:
                    created_path.unlink(missing_ok=True)
                    created_path.parent.rmdir()
                except OSError:
                    pass
            raise
        finally:
            self._project.cleanup_staged_task(staged.task_dir)
        persisted = self.get(view.data)
        if canonical_hash(persisted) != canonical_hash(view):
            raise EngineDataError("persisted engine data readback differs from registered values")
        return persisted

    def get(self, data: EngineDataRef) -> EngineDataView:
        row = self._row(data, require_hash=True)
        if row is None:
            raise EngineDataError("persisted engine data revision was not found")
        _content_hash, table_hash, fields_json, row_count, view_hash = row
        fields = _FIELDS_ADAPTER.validate_json(str(fields_json))
        path = self._project.object_path(str(table_hash))
        if not path.is_file():
            raise EngineDataError("persisted engine data object is missing")
        table = pq.read_table(path)
        row_ids = tuple(str(value) for value in table[_ROW_ID_COLUMN].to_pylist())
        if len(row_ids) != cast(int, row_count):
            raise EngineDataError("persisted engine data row count is invalid")
        view = EngineDataView(
            data=data,
            row_ids=row_ids,
            columns=tuple(
                EngineColumn(
                    field=field,
                    values=_engine_values(table[field.field_id].to_pylist()),
                )
                for field in fields
            ),
        )
        if canonical_hash(view) != str(view_hash):
            raise EngineDataError("persisted engine data failed canonical readback")
        return view

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[FieldId, ...],
    ) -> EngineDataView:
        if data.kind == "source":
            raise EngineDataError("source data belongs to ProjectEngineDataProvider")
        if not field_ids or len(field_ids) != len(set(field_ids)):
            raise EngineDataError("engine data materialization fields must be non-empty and unique")
        view = self.get(data)
        columns = {column.field.field_id: column for column in view.columns}
        missing = tuple(item for item in field_ids if item not in columns)
        if missing:
            raise EngineDataError(f"persisted data does not contain requested fields: {missing!r}")
        return view.model_copy(update={"columns": tuple(columns[item] for item in field_ids)})

    def _row(
        self,
        data: EngineDataRef,
        *,
        require_hash: bool,
    ) -> tuple[object, ...] | None:
        sql = """
            SELECT content_hash, table_object_hash, field_schema_json, row_count, view_hash
            FROM engine_data_view_versions
            WHERE data_kind = ? AND dataset_id = ? AND data_version = ?
        """
        parameters: tuple[object, ...] = (data.kind, data.dataset_id, data.version)
        if require_hash:
            sql += " AND content_hash = ?"
            parameters += (data.content_hash,)
        row = self._project._assert_writer().execute(sql, parameters).fetchone()  # noqa: SLF001
        return cast(tuple[object, ...] | None, row)


def _parquet_bytes(view: EngineDataView) -> bytes:
    arrays: list[pa.Array] = [pa.array(view.row_ids, type=pa.string())]
    names = [_ROW_ID_COLUMN]
    for column in view.columns:
        arrays.append(_array(column))
        names.append(column.field.field_id)
    table = pa.Table.from_arrays(arrays, names=names).replace_schema_metadata(
        {b"plotagent.schema_version": b"engine-data-view-v1"}
    )
    output = io.BytesIO()
    pq.write_table(
        table,
        output,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
        data_page_version="2.0",
        version="2.6",
    )
    return output.getvalue()


def _array(column: EngineColumn) -> pa.Array:
    values = column.values
    if column.field.logical_type == "numeric":
        observed = tuple(value for value in values if value is not None)
        if observed and all(
            isinstance(value, int) and not isinstance(value, bool) for value in observed
        ):
            return pa.array(values, type=pa.int64())
        return pa.array(values, type=pa.float64())
    if column.field.logical_type == "boolean":
        return pa.array(values, type=pa.bool_())
    if column.field.logical_type == "datetime":
        observed_dates = tuple(value for value in values if value is not None)
        if observed_dates and all(
            isinstance(value, date) and not isinstance(value, datetime) for value in observed_dates
        ):
            return pa.array(values, type=pa.date32())
        return pa.array(values, type=pa.timestamp("us"))
    return pa.array(values, type=pa.string())

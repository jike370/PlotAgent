"""Narrow repositories for the desktop plotting vertical slice.

The tables behind this module are explicit application objects.  This is not a
generic JSON document store: callers can commit only Plot inputs/specs, BatchSpec,
FigureSpec, and verified export records.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import TypeAdapter

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.datasets import (
    ExcelSourceCoordinate,
    FieldMapping,
    PreparationSpec,
    PreparedDataset,
    SourceCoordinate,
    SourceDataset,
    TextSourceCoordinate,
)
from plotagent.contracts.plots import BatchSpec, FigureSpec, PlotSpec
from plotagent.preparation.artifacts import PreparedArtifact, ResolvedSourceTable
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore
from plotagent.storage.schema import ensure_desktop_project_schema

_PREPARATION_ADAPTER: TypeAdapter[PreparationSpec] = TypeAdapter(PreparationSpec)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class StoredPlot:
    plot: PlotSpec
    field_mapping: FieldMapping
    preparation_spec: PreparationSpec
    prepared_dataset: PreparedDataset
    render_bindings: Mapping[str, str]
    content_hash: str


@dataclass(frozen=True, slots=True)
class StoredExport:
    export_id: str
    plot_id: str
    plot_version: int
    format: Literal["png", "svg", "opju"]
    destination_path: str
    artifact_hash: str
    artifact_size: int
    render_plan_hash: str
    created_at: str


class ProjectDomainRepository:
    """Single-writer domain repository layered over one active ProjectStore."""

    def __init__(self, project: ProjectStore) -> None:
        self.project = project
        ensure_desktop_project_schema(project._assert_writer())  # noqa: SLF001

    @property
    def revision(self) -> int:
        row = self.project._assert_writer().execute(  # noqa: SLF001
            "SELECT revision FROM project_meta"
        ).fetchone()
        return int(row[0])

    def require_revision(self, expected: int) -> None:
        if self.revision != expected:
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "The project changed after the request was created.",
            )

    def replay(
        self, operation: str, idempotency_key: str, request_hash: str
    ) -> dict[str, JsonValue] | None:
        row = self.project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT request_hash, response_json
            FROM idempotency_records
            WHERE operation = ? AND idempotency_key = ?
            """,
            (operation, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        if str(row[0]) != request_hash:
            raise StorageProblem(
                StorageErrorCode.IDEMPOTENCY_CONFLICT,
                "The idempotency key was already used for a different request.",
            )
        payload = json.loads(str(row[1]))
        if not isinstance(payload, dict):
            raise StorageProblem(StorageErrorCode.COMMIT_FAILED, "Invalid idempotency record.")
        return cast(dict[str, JsonValue], payload)

    def source_record(self, source_dataset_id: str, source_version: int) -> SourceDataset:
        row = self.project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT contract_json FROM source_dataset_versions
            WHERE source_dataset_id = ? AND source_version = ?
            """,
            (source_dataset_id, source_version),
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "SourceDataset was not found.")
        return SourceDataset.model_validate_json(str(row[0]))

    def resolve_source(self, source: SourceDataset) -> ResolvedSourceTable:
        row = self.project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT metadata_json FROM source_dataset_versions
            WHERE source_dataset_id = ? AND source_version = ?
            """,
            (source.source_dataset_id, source.source_version),
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "SourceDataset was not found.")
        table = pq.read_table(self.project.object_path(source.data_ref.object_hash))
        values = table.to_pydict()
        rows = tuple(
            tuple(values[field.field_id][index] for field in source.field_schema)
            for index in range(source.data_ref.row_count)
        )
        coordinates = tuple(
            self._coordinate(values, index, source)
            for index in range(source.data_ref.row_count)
        )
        metadata = json.loads(str(row[0]))
        return ResolvedSourceTable(
            source_dataset=source,
            rows=rows,
            coordinates=coordinates,
            instrument_metadata=metadata,
        )

    def prepared_table(self, prepared: PreparedDataset) -> dict[str, tuple[object, ...]]:
        table = pq.read_table(self.project.object_path(prepared.data_ref.object_hash))
        values = table.to_pydict()
        return {
            field_id: tuple(values[field_id])
            for field_id in prepared.data_ref.field_ids
        }

    def render_tables(
        self, stored: StoredPlot
    ) -> dict[str, dict[str, tuple[object, ...]]]:
        """Load every persisted renderer binding through its verified CAS object."""

        tables: dict[str, dict[str, tuple[object, ...]]] = {}
        for binding_hash, object_hash in stored.render_bindings.items():
            table = pq.read_table(self.project.object_path(object_hash))
            values = table.to_pydict()
            tables[binding_hash] = {
                field_id: tuple(column) for field_id, column in values.items()
            }
        return tables

    def latest_plot_version(self, plot_id: str) -> int | None:
        row = self.project._assert_writer().execute(  # noqa: SLF001
            "SELECT MAX(plot_version) FROM plot_spec_versions WHERE plot_id = ?",
            (plot_id,),
        ).fetchone()
        return None if row is None or row[0] is None else int(row[0])

    def get_plot(self, plot_id: str, plot_version: int | None = None) -> StoredPlot:
        if plot_version is None:
            plot_version = self.latest_plot_version(plot_id)
        if plot_version is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "PlotSpec was not found.")
        row = self.project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT p.spec_json, p.content_hash, i.field_mapping_json,
                   i.preparation_spec_json, i.prepared_dataset_json,
                   i.render_bindings_json
            FROM plot_spec_versions AS p
            JOIN plot_inputs AS i
              ON i.plot_id = p.plot_id AND i.plot_version = p.plot_version
            WHERE p.plot_id = ? AND p.plot_version = ?
            """,
            (plot_id, plot_version),
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "PlotSpec was not found.")
        return StoredPlot(
            plot=PlotSpec.model_validate_json(str(row[0])),
            content_hash=str(row[1]),
            field_mapping=FieldMapping.model_validate_json(str(row[2])),
            preparation_spec=_PREPARATION_ADAPTER.validate_json(str(row[3])),
            prepared_dataset=PreparedDataset.model_validate_json(str(row[4])),
            render_bindings=cast(dict[str, str], json.loads(str(row[5]))),
        )

    def list_plots(self) -> tuple[StoredPlot, ...]:
        rows = self.project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT plot_id, MAX(plot_version)
            FROM plot_spec_versions GROUP BY plot_id ORDER BY plot_id
            """
        ).fetchall()
        return tuple(self.get_plot(str(plot_id), int(version)) for plot_id, version in rows)

    def commit_new_plot(
        self,
        *,
        plot: PlotSpec,
        mapping: FieldMapping,
        preparation_spec: PreparationSpec,
        prepared: PreparedArtifact,
        expected_revision: int,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, JsonValue],
        render_artifacts: Mapping[str, bytes] | None = None,
    ) -> None:
        staged = self.project.stage_bytes(
            prepared.parquet_bytes,
            media_type="application/vnd.apache.parquet",
        )
        staged_render = {
            binding_hash: self.project.stage_bytes(
                payload,
                media_type="application/vnd.apache.parquet",
            )
            for binding_hash, payload in (render_artifacts or {}).items()
        }
        render_bindings = {
            prepared.prepared_dataset.output_hash: staged.content_hash,
            **{
                binding_hash: artifact.content_hash
                for binding_hash, artifact in staged_render.items()
            },
        }
        connection = self.project._assert_writer()  # noqa: SLF001
        created_paths: list[Path] = []
        try:
            path, created = self.project._promote(staged)  # noqa: SLF001
            if created:
                created_paths.append(path)
            for artifact in staged_render.values():
                path, created = self.project._promote(artifact)  # noqa: SLF001
                if created:
                    created_paths.append(path)
            connection.execute("BEGIN IMMEDIATE")
            self._require_revision_in_transaction(connection, expected_revision)
            if self.latest_plot_version(plot.plot_id) is not None:
                raise StorageProblem(
                    StorageErrorCode.VERSION_CONFLICT,
                    "PlotSpec already exists; use plots.patch to create a new version.",
                )
            now = _utc_now()
            self._register_object(connection, staged, now)
            for artifact in staged_render.values():
                self._register_object(connection, artifact, now)
            self._insert_plot_inputs(
                connection,
                plot,
                mapping,
                preparation_spec,
                prepared,
                render_bindings,
                now,
            )
            connection.execute(
                """
                INSERT INTO plot_spec_versions(
                    plot_id, plot_version, parent_plot_version, content_hash, spec_json, created_at
                ) VALUES (?, ?, NULL, ?, ?, ?)
                """,
                (plot.plot_id, plot.plot_version, canonical_hash(plot), _json(plot), now),
            )
            self._insert_render_refs(connection, plot, render_bindings)
            self._finish_write(
                connection,
                expected_revision,
                operation,
                idempotency_key,
                request_hash,
                response,
                now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            for created_path in created_paths:
                created_path.unlink(missing_ok=True)
            raise
        finally:
            self.project.cleanup_staged_task(staged.task_dir)
            for artifact in staged_render.values():
                self.project.cleanup_staged_task(artifact.task_dir)

    def commit_plot_patch(
        self,
        *,
        previous: StoredPlot,
        plot: PlotSpec,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, JsonValue],
    ) -> None:
        connection = self.project._assert_writer()  # noqa: SLF001
        connection.execute("BEGIN IMMEDIATE")
        try:
            latest = self.latest_plot_version(plot.plot_id)
            if latest != previous.plot.plot_version:
                raise StorageProblem(
                    StorageErrorCode.VERSION_CONFLICT,
                    "PlotSpec version is stale.",
                )
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO plot_inputs(
                    plot_id, plot_version, field_mapping_json, field_mapping_hash,
                    preparation_spec_json, preparation_spec_hash,
                    prepared_dataset_json, prepared_table_hash,
                    render_bindings_json, created_at
                ) SELECT plot_id, ?, field_mapping_json, field_mapping_hash,
                         preparation_spec_json, preparation_spec_hash,
                         prepared_dataset_json, prepared_table_hash,
                         render_bindings_json, ?
                  FROM plot_inputs WHERE plot_id = ? AND plot_version = ?
                """,
                (plot.plot_version, now, plot.plot_id, previous.plot.plot_version),
            )
            connection.execute(
                """
                INSERT INTO plot_spec_versions(
                    plot_id, plot_version, parent_plot_version, content_hash, spec_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    plot.plot_id,
                    plot.plot_version,
                    previous.plot.plot_version,
                    canonical_hash(plot),
                    _json(plot),
                    now,
                ),
            )
            self._insert_render_refs(connection, plot, previous.render_bindings)
            expected_revision = self.revision
            self._finish_write(
                connection,
                expected_revision,
                operation,
                idempotency_key,
                request_hash,
                response,
                now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    def save_batch(
        self,
        batch: BatchSpec,
        state: str,
        *,
        expected_revision: int,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, JsonValue],
    ) -> None:
        self._save_versioned(
            table="batch_spec_versions",
            id_column="batch_id",
            object_id=batch.batch_id,
            version_column="batch_version",
            version=batch.batch_version,
            payload=batch,
            state=state,
            expected_revision=expected_revision,
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )

    def get_batch(self, batch_id: str) -> tuple[BatchSpec, str]:
        row = self.project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT spec_json, state FROM batch_spec_versions
            WHERE batch_id = ? ORDER BY batch_version DESC LIMIT 1
            """,
            (batch_id,),
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "BatchSpec was not found.")
        return BatchSpec.model_validate_json(str(row[0])), str(row[1])

    def save_figure(
        self,
        figure: FigureSpec,
        *,
        expected_revision: int,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, JsonValue],
    ) -> None:
        self._save_versioned(
            table="figure_spec_versions",
            id_column="figure_id",
            object_id=figure.figure_id,
            version_column="figure_version",
            version=figure.figure_version,
            payload=figure,
            state=None,
            expected_revision=expected_revision,
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )

    def get_figure(self, figure_id: str) -> FigureSpec:
        row = self.project._assert_writer().execute(  # noqa: SLF001
            """
            SELECT spec_json FROM figure_spec_versions
            WHERE figure_id = ? ORDER BY figure_version DESC LIMIT 1
            """,
            (figure_id,),
        ).fetchone()
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "FigureSpec was not found.")
        return FigureSpec.model_validate_json(str(row[0]))

    def save_export(
        self,
        record: StoredExport,
        *,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, JsonValue],
    ) -> None:
        connection = self.project._assert_writer()  # noqa: SLF001
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """
                INSERT INTO export_records(
                    export_id, plot_id, plot_version, format, destination_path,
                    artifact_hash, artifact_size, render_plan_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.export_id,
                    record.plot_id,
                    record.plot_version,
                    record.format,
                    record.destination_path,
                    record.artifact_hash,
                    record.artifact_size,
                    record.render_plan_hash,
                    record.created_at,
                ),
            )
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO idempotency_records(
                    operation, idempotency_key, request_hash, response_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (operation, idempotency_key, request_hash, _json(response), now),
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    def _save_versioned(
        self,
        *,
        table: Literal["batch_spec_versions", "figure_spec_versions"],
        id_column: Literal["batch_id", "figure_id"],
        object_id: str,
        version_column: Literal["batch_version", "figure_version"],
        version: int,
        payload: BatchSpec | FigureSpec,
        state: str | None,
        expected_revision: int,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, JsonValue],
    ) -> None:
        connection = self.project._assert_writer()  # noqa: SLF001
        connection.execute("BEGIN IMMEDIATE")
        try:
            self._require_revision_in_transaction(connection, expected_revision)
            now = _utc_now()
            if table == "batch_spec_versions":
                connection.execute(
                    """
                    INSERT INTO batch_spec_versions(
                        batch_id, batch_version, state, content_hash, spec_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (object_id, version, state, canonical_hash(payload), _json(payload), now),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO figure_spec_versions(
                        figure_id, figure_version, content_hash, spec_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (object_id, version, canonical_hash(payload), _json(payload), now),
                )
            self._finish_write(
                connection,
                expected_revision,
                operation,
                idempotency_key,
                request_hash,
                response,
                now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    @staticmethod
    def _require_revision_in_transaction(
        connection: sqlite3.Connection, expected_revision: int
    ) -> None:
        row = connection.execute("SELECT revision FROM project_meta").fetchone()
        if row is None or int(row[0]) != expected_revision:
            raise StorageProblem(
                StorageErrorCode.VERSION_CONFLICT,
                "The project changed after the request was created.",
            )

    @staticmethod
    def _register_object(connection: sqlite3.Connection, staged: Any, now: str) -> None:
        connection.execute(
            """
            INSERT INTO objects(content_hash, media_type, size, ref_count, created_at)
            VALUES (?, ?, ?, 0, ?) ON CONFLICT(content_hash) DO NOTHING
            """,
            (staged.content_hash, staged.media_type, staged.size, now),
        )

    @staticmethod
    def _insert_plot_inputs(
        connection: sqlite3.Connection,
        plot: PlotSpec,
        mapping: FieldMapping,
        preparation_spec: PreparationSpec,
        prepared: PreparedArtifact,
        render_bindings: Mapping[str, str],
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO plot_inputs(
                plot_id, plot_version, field_mapping_json, field_mapping_hash,
                preparation_spec_json, preparation_spec_hash,
                prepared_dataset_json, prepared_table_hash,
                render_bindings_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plot.plot_id,
                plot.plot_version,
                _json(mapping),
                mapping.content_hash,
                _json(preparation_spec),
                canonical_hash(preparation_spec),
                _json(prepared.prepared_dataset),
                prepared.prepared_dataset.data_ref.object_hash,
                _json(render_bindings),
                now,
            ),
        )

    @staticmethod
    def _insert_render_refs(
        connection: sqlite3.Connection,
        plot: PlotSpec,
        render_bindings: Mapping[str, str],
    ) -> None:
        owner_id = f"{plot.plot_id}@{plot.plot_version}"
        for index, content_hash in enumerate(dict.fromkeys(render_bindings.values())):
            connection.execute(
                """
                INSERT INTO object_refs(owner_type, owner_id, role, content_hash)
                VALUES ('plot_spec', ?, ?, ?)
                """,
                (owner_id, f"render_table.{index}", content_hash),
            )
            connection.execute(
                "UPDATE objects SET ref_count = ref_count + 1 WHERE content_hash = ?",
                (content_hash,),
            )

    @staticmethod
    def _finish_write(
        connection: sqlite3.Connection,
        expected_revision: int,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, JsonValue],
        now: str,
    ) -> None:
        cursor = connection.execute(
            "UPDATE project_meta SET revision = revision + 1 WHERE revision = ?",
            (expected_revision,),
        )
        if cursor.rowcount != 1:
            raise StorageProblem(StorageErrorCode.VERSION_CONFLICT, "Project version is stale.")
        connection.execute(
            """
            INSERT INTO idempotency_records(
                operation, idempotency_key, request_hash, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (operation, idempotency_key, request_hash, _json(response), now),
        )

    @staticmethod
    def _coordinate(
        values: Mapping[str, Sequence[Any]], index: int, source: SourceDataset
    ) -> SourceCoordinate:
        kind = str(values["__source_kind"][index])
        row_id = str(values["__source_row_id"][index])
        if kind == "excel":
            return ExcelSourceCoordinate(
                workbook_hash=source.source_object_hash,
                sheet_name=str(values["__source_sheet"][index]),
                cell_range=str(values["__source_cell_range"][index]),
                source_row_id=row_id,
            )
        return TextSourceCoordinate(
            byte_start=int(values["__source_byte_start"][index]),
            byte_end=int(values["__source_byte_end"][index]),
            line_start=int(values["__source_line_start"][index]),
            line_end=int(values["__source_line_end"][index]),
            block=values["__source_block"][index],
            channel=values["__source_channel"][index],
            sweep=values["__source_sweep"][index],
            source_row_id=row_id,
        )

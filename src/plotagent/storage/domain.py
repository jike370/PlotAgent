"""Data and revision repository shared by imports, context, and Agent Native plots."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from plotagent.contracts.canonical import JsonValue
from plotagent.contracts.datasets import (
    ExcelSourceCoordinate,
    SourceCoordinate,
    SourceDataset,
    TextSourceCoordinate,
)
from plotagent.preparation.artifacts import ResolvedSourceTable
from plotagent.storage.errors import StorageErrorCode, StorageProblem
from plotagent.storage.project import ProjectStore
from plotagent.storage.schema import ensure_desktop_project_schema


class ProjectDomainRepository:
    """Single-writer domain repository layered over one active ProjectStore."""

    def __init__(self, project: ProjectStore) -> None:
        self.project = project
        ensure_desktop_project_schema(project._assert_writer())  # noqa: SLF001

    @property
    def revision(self) -> int:
        row = (
            self.project._assert_writer()
            .execute(  # noqa: SLF001
                "SELECT revision FROM project_meta"
            )
            .fetchone()
        )
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
        row = (
            self.project._assert_writer()
            .execute(  # noqa: SLF001
                """
            SELECT request_hash, response_json
            FROM idempotency_records
            WHERE operation = ? AND idempotency_key = ?
            """,
                (operation, idempotency_key),
            )
            .fetchone()
        )
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
        row = (
            self.project._assert_writer()
            .execute(  # noqa: SLF001
                """
            SELECT contract_json FROM source_dataset_versions
            WHERE source_dataset_id = ? AND source_version = ?
            """,
                (source_dataset_id, source_version),
            )
            .fetchone()
        )
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "SourceDataset was not found.")
        return SourceDataset.model_validate_json(str(row[0]))

    def resolve_source(self, source: SourceDataset) -> ResolvedSourceTable:
        row = (
            self.project._assert_writer()
            .execute(  # noqa: SLF001
                """
            SELECT metadata_json FROM source_dataset_versions
            WHERE source_dataset_id = ? AND source_version = ?
            """,
                (source.source_dataset_id, source.source_version),
            )
            .fetchone()
        )
        if row is None:
            raise StorageProblem(StorageErrorCode.OBJECT_NOT_FOUND, "SourceDataset was not found.")
        table = pq.read_table(self.project.object_path(source.data_ref.object_hash))
        values = table.to_pydict()
        rows = tuple(
            tuple(values[field.field_id][index] for field in source.field_schema)
            for index in range(source.data_ref.row_count)
        )
        coordinates = tuple(
            self._coordinate(values, index, source) for index in range(source.data_ref.row_count)
        )
        metadata = json.loads(str(row[0]))
        display_name: str | None = None
        if isinstance(metadata, dict):
            raw_display_name = metadata.get("__plotagent_display_name")
            if isinstance(raw_display_name, str) and raw_display_name:
                display_name = raw_display_name
            metadata = {
                key: value
                for key, value in metadata.items()
                if not str(key).startswith("__plotagent_")
            }
        return ResolvedSourceTable(
            source_dataset=source,
            rows=rows,
            coordinates=coordinates,
            instrument_metadata=metadata,
            display_name=display_name,
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

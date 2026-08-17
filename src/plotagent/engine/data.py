"""Adapters from immutable project data into renderer-neutral engine views."""

from __future__ import annotations

from collections.abc import Sequence

import pyarrow as pa  # type: ignore
import pyarrow.parquet as pq  # type: ignore

from plotagent.contracts.base import FieldId
from plotagent.contracts.datasets import SourceDataset, SourceField
from plotagent.engine.contracts import (
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    EngineScalar,
)
from plotagent.engine.ports import EngineDataProvider
from plotagent.storage.project import ProjectStore

_ROW_ID_COLUMN = "__source_row_id"


class EngineDataError(ValueError):
    """The requested immutable engine data view cannot be materialized."""


class ProjectEngineDataProvider:
    """Read bounded data views directly from the project content store.

    The adapter deliberately depends on the import/storage contracts, not the
    legacy plotting domain repository.  A renderer therefore receives the
    same immutable values regardless of which Agent requested the plot.
    """

    def __init__(self, project: ProjectStore) -> None:
        self._project = project

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[FieldId, ...],
    ) -> EngineDataView:
        if data.kind != "source":
            raise EngineDataError(
                f"engine data kind {data.kind!r} requires its own explicit adapter"
            )
        if not field_ids:
            raise EngineDataError("engine data materialization requires at least one field")
        if len(field_ids) != len(set(field_ids)):
            raise EngineDataError("engine data materialization fields must be unique")

        source = self._source_revision(data)
        fields_by_id = {field.field_id: field for field in source.field_schema}
        missing = tuple(field_id for field_id in field_ids if field_id not in fields_by_id)
        if missing:
            raise EngineDataError(f"source data does not contain requested fields: {missing!r}")

        table = self._read_source_table(source, field_ids)
        row_ids = tuple(str(value) for value in table[_ROW_ID_COLUMN].to_pylist())
        if len(row_ids) != source.data_ref.row_count:
            raise EngineDataError("source data row count differs from its immutable contract")
        if any(not row_id.startswith("row:") for row_id in row_ids):
            raise EngineDataError("source data contains an invalid stable row identity")

        columns = tuple(
            EngineColumn(
                field=_engine_field(fields_by_id[field_id]),
                values=engine_values(table[field_id].to_pylist()),
            )
            for field_id in field_ids
        )
        return EngineDataView(data=data, row_ids=row_ids, columns=columns)

    def _source_revision(self, data: EngineDataRef) -> SourceDataset:
        matches = tuple(
            record.source_dataset
            for record in self._project.list_source_datasets()
            if record.source_dataset.source_dataset_id == data.dataset_id
            and record.source_dataset.source_version == data.version
        )
        if len(matches) != 1:
            raise EngineDataError(
                f"source data revision {data.dataset_id!r} v{data.version} was not found"
            )
        source = matches[0]
        if source.content_hash != data.content_hash:
            raise EngineDataError("source data content hash does not match the requested revision")
        return source

    def _read_source_table(
        self,
        source: SourceDataset,
        field_ids: tuple[FieldId, ...],
    ) -> pa.Table:
        path = self._project.object_path(source.data_ref.object_hash)
        if not path.is_file():
            raise EngineDataError("source data object is missing from project storage")
        try:
            return pq.read_table(path, columns=[*field_ids, _ROW_ID_COLUMN])
        except Exception as exc:
            raise EngineDataError("source data object cannot satisfy its immutable schema") from exc


class RoutedEngineDataProvider:
    """Route immutable data kinds to explicit providers without renderer logic."""

    def __init__(
        self,
        source: EngineDataProvider,
        derived: EngineDataProvider,
    ) -> None:
        self._source = source
        self._derived = derived

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[FieldId, ...],
    ) -> EngineDataView:
        provider = self._source if data.kind == "source" else self._derived
        return provider.materialize(data, field_ids)


def _engine_field(field: SourceField) -> EngineField:
    unit_label = field.unit.source_text.strip() or field.unit.canonical_unit
    return EngineField(
        field_id=field.field_id,
        name=field.name,
        logical_type=field.logical_type,
        unit_label=unit_label,
    )


def engine_values(values: Sequence[object]) -> tuple[EngineScalar, ...]:
    allowed = (bool, int, float, str)
    result: list[EngineScalar] = []
    for value in values:
        if value is None or isinstance(value, allowed):
            result.append(value)
            continue
        # Arrow returns Python date/datetime values for temporal columns.  The
        # contract validates these exact types and canonical JSON serializes
        # them deterministically.
        from datetime import date, datetime

        if isinstance(value, (date, datetime)):
            result.append(value)
            continue
        raise EngineDataError(f"unsupported engine scalar type: {type(value).__name__}")
    return tuple(result)

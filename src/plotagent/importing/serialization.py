"""Deterministic Parquet serialization for immutable SourceDataset tables."""

from __future__ import annotations

import io
import json
from datetime import date, datetime

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from plotagent.contracts.datasets import (
    DataQualitySummary,
    SourceCoordinate,
    SourceField,
)
from plotagent.importing.models import ImportRecipe, Scalar, SourceDatasetArtifact


def _string_value(value: Scalar) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _array(field: SourceField, values: list[Scalar]) -> pa.Array:
    if field.logical_type == "numeric":
        if "float" not in field.physical_type:
            return pa.array(values, type=pa.int64())
        return pa.array(values, type=pa.float64())
    if field.logical_type == "boolean":
        return pa.array(values, type=pa.bool_())
    if field.logical_type == "datetime":
        normalized = [
            datetime.combine(value, datetime.min.time())
            if isinstance(value, date) and not isinstance(value, datetime)
            else value
            for value in values
        ]
        return pa.array(normalized, type=pa.timestamp("us"))
    return pa.array([_string_value(value) for value in values], type=pa.string())


def _coordinate_columns(
    coordinates: tuple[SourceCoordinate, ...],
) -> tuple[tuple[str, pa.DataType, list[object]], ...]:
    return (
        ("__source_kind", pa.string(), [item.kind for item in coordinates]),
        ("__source_row_id", pa.string(), [item.source_row_id for item in coordinates]),
        (
            "__source_sheet",
            pa.string(),
            [item.sheet_name if item.kind == "excel" else None for item in coordinates],
        ),
        (
            "__source_cell_range",
            pa.string(),
            [item.cell_range if item.kind == "excel" else None for item in coordinates],
        ),
        (
            "__source_block",
            pa.string(),
            [item.block if item.kind == "text" else None for item in coordinates],
        ),
        (
            "__source_channel",
            pa.string(),
            [item.channel if item.kind == "text" else None for item in coordinates],
        ),
        (
            "__source_sweep",
            pa.string(),
            [item.sweep if item.kind == "text" else None for item in coordinates],
        ),
        (
            "__source_line_start",
            pa.int64(),
            [item.line_start if item.kind == "text" else None for item in coordinates],
        ),
        (
            "__source_line_end",
            pa.int64(),
            [item.line_end if item.kind == "text" else None for item in coordinates],
        ),
        (
            "__source_byte_start",
            pa.int64(),
            [item.byte_start if item.kind == "text" else None for item in coordinates],
        ),
        (
            "__source_byte_end",
            pa.int64(),
            [item.byte_end if item.kind == "text" else None for item in coordinates],
        ),
    )


def table_to_parquet_bytes(
    *,
    source_dataset_id: str,
    source_object_hash: str,
    fields: tuple[SourceField, ...],
    rows: tuple[tuple[Scalar, ...], ...],
    coordinates: tuple[SourceCoordinate, ...],
    recipe: ImportRecipe,
    quality: DataQualitySummary,
) -> bytes:
    """Serialize all values and full row coordinates without changing non-finite data."""

    arrays: list[pa.Array] = []
    names: list[str] = []
    arrow_fields: list[pa.Field] = []
    for index, field in enumerate(fields):
        values = [row[index] for row in rows]
        array = _array(field, values)
        metadata = {
            b"plotagent.name": field.name.encode("utf-8"),
            b"plotagent.logical_type": field.logical_type.encode("ascii"),
            b"plotagent.physical_type": field.physical_type.encode("ascii"),
            b"plotagent.unit_source_text": field.unit.source_text.encode("utf-8"),
        }
        arrays.append(array)
        names.append(field.field_id)
        arrow_fields.append(pa.field(field.field_id, array.type, nullable=True, metadata=metadata))

    for name, data_type, coordinate_values in _coordinate_columns(coordinates):
        arrays.append(pa.array(coordinate_values, type=data_type))
        names.append(name)
        arrow_fields.append(pa.field(name, data_type, nullable=True))

    schema_metadata = {
        b"plotagent.schema_version": b"source-dataset-v1",
        b"plotagent.source_dataset_id": source_dataset_id.encode("ascii"),
        b"plotagent.source_object_hash": source_object_hash.encode("ascii"),
        b"plotagent.import_recipe": json.dumps(
            recipe.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8"),
        b"plotagent.quality": json.dumps(
            quality.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8"),
    }
    schema = pa.schema(arrow_fields, metadata=schema_metadata)
    table = pa.Table.from_arrays(arrays, names=names).cast(schema)
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


def source_artifact_to_parquet_bytes(artifact: SourceDatasetArtifact) -> bytes:
    """Return the already-hashed immutable bytes bound by the SourceDataset contract."""

    return artifact.parquet_bytes

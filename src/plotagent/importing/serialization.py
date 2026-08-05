"""Deterministic Parquet serialization for immutable SourceDataset tables."""

from __future__ import annotations

import io
import json
from datetime import date, datetime

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from plotagent.importing.models import DatasetCandidate, FieldSchema, Scalar


def _string_value(value: Scalar) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _array(field: FieldSchema, values: list[Scalar]) -> pa.Array:
    if field.logical_type == "numeric":
        if field.numeric_precision == "integer":
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


def candidate_to_parquet_bytes(candidate: DatasetCandidate) -> bytes:
    """Serialize all rows plus stable source coordinates without dropping non-finite values."""

    arrays: list[pa.Array] = []
    names: list[str] = []
    arrow_fields: list[pa.Field] = []
    for index, field in enumerate(candidate.fields):
        values = [row[index] for row in candidate.rows]
        array = _array(field, values)
        metadata = {
            b"plotagent.normalized_name": field.normalized_name.encode("utf-8"),
            b"plotagent.source_name": field.source_name.encode("utf-8"),
            b"plotagent.logical_type": field.logical_type.encode("ascii"),
        }
        if field.unit is not None:
            metadata[b"plotagent.unit_source_text"] = field.unit.source_text.encode("utf-8")
        arrays.append(array)
        names.append(field.field_id)
        arrow_fields.append(pa.field(field.field_id, array.type, nullable=True, metadata=metadata))

    coordinate_columns: tuple[tuple[str, pa.DataType, list[object]], ...] = (
        ("__source_row_id", pa.string(), [item.source_row_id for item in candidate.coordinates]),
        ("__source_row", pa.int64(), [item.source_row for item in candidate.coordinates]),
        ("__source_sheet", pa.string(), [item.sheet for item in candidate.coordinates]),
        ("__source_cell_range", pa.string(), [item.cell_range for item in candidate.coordinates]),
        ("__source_block", pa.string(), [item.block for item in candidate.coordinates]),
        ("__source_line", pa.int64(), [item.line for item in candidate.coordinates]),
        ("__source_byte_start", pa.int64(), [item.byte_start for item in candidate.coordinates]),
        ("__source_byte_end", pa.int64(), [item.byte_end for item in candidate.coordinates]),
    )
    for name, data_type, coordinate_values in coordinate_columns:
        arrays.append(pa.array(coordinate_values, type=data_type))
        names.append(name)
        arrow_fields.append(pa.field(name, data_type, nullable=True))

    schema_metadata = {
        b"plotagent.schema_version": b"source-dataset-v1",
        b"plotagent.candidate_id": candidate.candidate_id.encode("ascii"),
        b"plotagent.source_object_hash": candidate.source_object_hash.encode("ascii"),
        b"plotagent.import_recipe": json.dumps(
            candidate.recipe.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8"),
        b"plotagent.quality": json.dumps(
            candidate.quality.model_dump(mode="json"),
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

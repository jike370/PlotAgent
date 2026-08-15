"""Compiler for the closed W0 PreparationSpec union."""

from __future__ import annotations

import hashlib
import io
import math
from collections.abc import Iterable
from typing import cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from plotagent.contracts.base import (
    ContentTableRef,
    FieldMappingRef,
    PreparationSpecRef,
    RowExclusion,
    SourceDatasetRef,
    WarningRecord,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.datasets import (
    ApplyPlotOrderSpec,
    FieldMapping,
    FilterRowsSpec,
    IsomorphicConcatSpec,
    PreparationSpec,
    PreparedDataset,
    PreparedDatasetProvenance,
    ProjectMetadataLabelSpec,
    ProjectStructureSpec,
    SelectFieldsSpec,
    SourceCoordinate,
    SourceDataset,
    SourceField,
    UnitSpec,
)
from plotagent.importing.models import Scalar
from plotagent.importing.serialization import _array, _coordinate_columns
from plotagent.preparation.artifacts import (
    PreparedArtifact,
    ResolvedSourceTable,
    SourceTableResolver,
)
from plotagent.preparation.errors import PreparationErrorCode, PreparationProblem

_COMPILER_BUILD_HASH = hashlib.sha256(b"preparation-compiler-v1").hexdigest()


def _source_ref(source: SourceDataset) -> SourceDatasetRef:
    return SourceDatasetRef(
        source_dataset_id=source.source_dataset_id,
        source_version=source.source_version,
        content_hash=source.content_hash,
    )


def _mapping_ref(mapping: FieldMapping) -> FieldMappingRef:
    return FieldMappingRef(
        field_mapping_id=mapping.field_mapping_id,
        mapping_version=mapping.mapping_version,
        content_hash=mapping.content_hash,
    )


def _unit_key(unit: UnitSpec) -> tuple[str, str | None, str, str]:
    return (unit.kind, unit.canonical_unit, unit.dimensionality, unit.source_text)


def semantic_signature(source: SourceDataset, mapping: FieldMapping) -> str:
    """Return a column-order-independent signature of frozen plotting semantics."""

    fields = sorted(
        (
            {
                "field_id": field.field_id,
                "name": field.name,
                "logical_type": field.logical_type,
                "unit": field.unit.model_dump(mode="json"),
            }
            for field in source.field_schema
        ),
        key=lambda value: str(value["field_id"]),
    )
    bindings = sorted(
        (
            {"role": binding.role, "field_id": binding.field.field_id}
            for binding in mapping.bindings
        ),
        key=lambda value: (value["role"], value["field_id"]),
    )
    return canonical_hash(cast(JsonValue, {"fields": fields, "bindings": bindings}))


def _validate_contract_links(
    sources: tuple[SourceDataset, ...], mapping: FieldMapping, spec: PreparationSpec
) -> None:
    refs = tuple(_source_ref(source) for source in sources)
    if refs != spec.input_refs or any(ref not in mapping.source_dataset_refs for ref in refs):
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_UNSUPPORTED,
            "PreparationSpec、FieldMapping 与 SourceDataset 版本引用不一致。",
        )
    if spec.field_mapping_ref != _mapping_ref(mapping):
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_UNSUPPORTED,
            "PreparationSpec 未绑定当前 FieldMapping 内容哈希。",
        )
    roles = tuple(binding.role for binding in mapping.bindings)
    if len(set(roles)) != len(roles):
        raise PreparationProblem(
            PreparationErrorCode.MAPPING_DUPLICATE_ROLE,
            "FieldMapping 中的角色必须唯一。",
        )
    fields_by_ref = {
        _source_ref(source): {field.field_id for field in source.field_schema} for source in sources
    }
    for binding in mapping.bindings:
        known = fields_by_ref[binding.field.source_dataset_ref]
        if binding.field.field_id not in known:
            raise PreparationProblem(
                PreparationErrorCode.MAPPING_REQUIRED_ROLE_MISSING,
                "FieldMapping 引用了 SourceDataset 中不存在的字段。",
            )


def _field_index(source: SourceDataset) -> dict[str, int]:
    return {field.field_id: index for index, field in enumerate(source.field_schema)}


def _selected(
    table: ResolvedSourceTable, field_ids: tuple[str, ...]
) -> tuple[tuple[SourceField, ...], tuple[tuple[Scalar, ...], ...]]:
    indexes = _field_index(table.source_dataset)
    if any(field_id not in indexes for field_id in field_ids):
        raise PreparationProblem(
            PreparationErrorCode.MAPPING_REQUIRED_ROLE_MISSING,
            "PreparationSpec 引用了不存在的字段。",
        )
    positions = tuple(indexes[field_id] for field_id in field_ids)
    fields = tuple(table.source_dataset.field_schema[index] for index in positions)
    rows = tuple(tuple(row[index] for index in positions) for row in table.rows)
    return fields, rows


def _dimensionless() -> UnitSpec:
    return UnitSpec(
        source_text="",
        dimensionality="dimensionless",
        kind="dimensionless",
        registry_version="units.v1",
    )


def _wide_to_long(
    table: ResolvedSourceTable, spec: ProjectStructureSpec
) -> tuple[
    tuple[SourceField, ...],
    tuple[tuple[Scalar, ...], ...],
    tuple[SourceCoordinate, ...],
]:
    if len(spec.role_fields) < 2:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_UNSUPPORTED,
            "wide→long 至少需要一个索引字段和一个值字段。",
        )
    indexes = _field_index(table.source_dataset)
    if any(field_id not in indexes for field_id in spec.role_fields):
        raise PreparationProblem(
            PreparationErrorCode.MAPPING_REQUIRED_ROLE_MISSING,
            "结构投影引用了不存在的字段。",
        )
    index_id, *value_ids = spec.role_fields
    value_fields = tuple(table.source_dataset.field_schema[indexes[item]] for item in value_ids)
    shapes = {(field.logical_type, _unit_key(field.unit)) for field in value_fields}
    if len(shapes) != 1:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_UNIT_INCOMPATIBLE,
            "wide→long 的值字段必须具有相同逻辑类型和单位。",
        )
    index_field = table.source_dataset.field_schema[indexes[index_id]]
    variable_field = SourceField(
        field_id="field:variable_" + canonical_hash(list(value_ids))[:16],
        name="variable",
        logical_type="text",
        physical_type="string",
        unit=_dimensionless(),
        source_column_index=1,
    )
    value_field = value_fields[0].model_copy(
        update={
            "field_id": "field:value_" + canonical_hash(list(value_ids))[:16],
            "name": "value",
            "source_column_index": 2,
        }
    )
    rows: list[tuple[Scalar, ...]] = []
    coordinates: list[SourceCoordinate] = []
    for row, coordinate in zip(table.rows, table.coordinates, strict=True):
        for field in value_fields:
            rows.append((row[indexes[index_id]], field.name, row[indexes[field.field_id]]))
            coordinates.append(coordinate)
    return (index_field, variable_field, value_field), tuple(rows), tuple(coordinates)


def _source_label(table: ResolvedSourceTable, kind: str) -> str:
    if kind == "source_dataset":
        return table.display_name or table.source_dataset.source_dataset_id
    for coordinate in table.coordinates:
        if kind == "source_sheet" and coordinate.kind == "excel":
            return coordinate.sheet_name
        if kind == "source_block" and coordinate.kind == "text" and coordinate.block:
            return coordinate.block
    raise PreparationProblem(
        PreparationErrorCode.PREPARE_UNSUPPORTED,
        f"来源没有 {kind} 标签。",
    )


def _concat(
    tables: tuple[ResolvedSourceTable, ...], mapping: FieldMapping, spec: IsomorphicConcatSpec
) -> tuple[tuple[SourceField, ...], tuple[tuple[Scalar, ...], ...]]:
    signatures = {semantic_signature(table.source_dataset, mapping) for table in tables}
    if len(signatures) != 1:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_NON_ISOMORPHIC,
            "只有字段、逻辑类型、单位与最终语义完全一致的数据才能纵向拼接。",
        )
    canonical_fields = tables[0].source_dataset.field_schema
    canonical_ids = tuple(field.field_id for field in canonical_fields)
    rows: list[tuple[Scalar, ...]] = []
    for table in tables:
        indexes = _field_index(table.source_dataset)
        if set(indexes) != set(canonical_ids):
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_NON_ISOMORPHIC,
                "拼接来源的字段集合不一致。",
            )
        label = _source_label(table, spec.source_label_kind)
        rows.extend(
            tuple(row[indexes[field_id]] for field_id in canonical_ids) + (label,)
            for row in table.rows
        )
    label_field = SourceField(
        field_id=spec.source_label_field_id,
        name=spec.source_label_kind,
        logical_type="categorical",
        physical_type="string",
        unit=_dimensionless(),
        source_column_index=len(canonical_fields),
    )
    return canonical_fields + (label_field,), tuple(rows)


def _reason(value: Scalar) -> str | None:
    if value is None:
        return "missing"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if value == float("inf"):
            return "positive_inf"
        if value == float("-inf"):
            return "negative_inf"
    return None


def _serialize(
    fields: tuple[SourceField, ...],
    rows: tuple[tuple[Scalar, ...], ...],
    coordinates: tuple[SourceCoordinate, ...],
    row_mask: tuple[bool, ...],
) -> bytes:
    arrays: list[pa.Array] = []
    arrow_fields: list[pa.Field] = []
    for index, field in enumerate(fields):
        array = _array(field, [row[index] for row in rows])
        arrays.append(array)
        arrow_fields.append(pa.field(field.field_id, array.type, nullable=True))
    for name, data_type, values in _coordinate_columns(coordinates):
        arrays.append(pa.array(values, type=data_type))
        arrow_fields.append(pa.field(name, data_type, nullable=True))
    arrays.append(pa.array(row_mask, type=pa.bool_()))
    arrow_fields.append(pa.field("__plot_included", pa.bool_(), nullable=False))
    schema = pa.schema(
        arrow_fields,
        metadata={b"plotagent.schema_version": b"prepared-dataset-v1"},
    )
    table = pa.Table.from_arrays(arrays, schema=schema)
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


def prepare(
    sources: Iterable[SourceDataset],
    mapping: FieldMapping,
    spec: PreparationSpec,
    resolver: SourceTableResolver,
) -> PreparedArtifact:
    """Apply one closed preparation operation; never join/filter/dedupe/convert/evaluate."""

    datasets = tuple(sources)
    if not datasets:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_UNSUPPORTED,
            "Preparation 至少需要一个 SourceDataset。",
        )
    _validate_contract_links(datasets, mapping, spec)
    tables = tuple(resolver.resolve(source) for source in datasets)
    first = tables[0]
    coordinates = tuple(item for table in tables for item in table.coordinates)
    exclusions: tuple[RowExclusion, ...] = ()
    plot_order: tuple[str, ...] = ()

    if isinstance(spec, SelectFieldsSpec):
        if len(tables) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_UNSUPPORTED,
                "select_fields 只接受一个来源。",
            )
        fields, rows = _selected(first, spec.field_ids)
    elif isinstance(spec, ProjectStructureSpec):
        if len(tables) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_UNSUPPORTED,
                "project_structure 只接受一个来源。",
            )
        if spec.input_layout == spec.output_layout:
            fields, rows = _selected(first, spec.role_fields)
        elif (spec.input_layout, spec.output_layout) == ("wide", "long"):
            fields, rows, coordinates = _wide_to_long(first, spec)
        else:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_UNSUPPORTED,
                "该结构投影不在 v1 封闭集合中。",
            )
    elif isinstance(spec, IsomorphicConcatSpec):
        fields, rows = _concat(tables, mapping, spec)
    elif isinstance(spec, ProjectMetadataLabelSpec):
        if len(tables) != 1 or spec.metadata_key not in first.instrument_metadata:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_UNSUPPORTED,
                "选择的 InstrumentMetadata 字段不存在。",
            )
        value = first.instrument_metadata[spec.metadata_key]
        metadata_field = SourceField(
            field_id=spec.output_field_id,
            name=spec.metadata_key,
            logical_type="categorical",
            physical_type="string",
            unit=_dimensionless(),
            source_column_index=len(first.source_dataset.field_schema),
        )
        fields = first.source_dataset.field_schema + (metadata_field,)
        rows = tuple(row + (value,) for row in first.rows)
    elif isinstance(spec, ApplyPlotOrderSpec):
        if len(tables) != 1 or spec.field_id not in _field_index(first.source_dataset):
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_UNSUPPORTED,
                "显示顺序引用了不存在的字段。",
            )
        fields, rows = first.source_dataset.field_schema, first.rows
        plot_order = spec.ordered_values
    elif isinstance(spec, FilterRowsSpec):
        if len(tables) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_UNSUPPORTED,
                "filter_rows 只接受一个来源。",
            )
        indexes = _field_index(first.source_dataset)
        if any(field_id not in indexes for field_id in spec.field_ids):
            raise PreparationProblem(
                PreparationErrorCode.MAPPING_REQUIRED_ROLE_MISSING,
                "绘图 mask 引用了不存在的字段。",
            )
        fields, rows = first.source_dataset.field_schema, first.rows
        items: list[RowExclusion] = []
        mutable_mask: list[bool] = []
        for row, coordinate in zip(rows, first.coordinates, strict=True):
            reasons = tuple(
                reason
                for field_id in spec.field_ids
                if (reason := _reason(row[indexes[field_id]])) is not None
            )
            mutable_mask.append(not reasons)
            items.extend(
                RowExclusion(row_id=coordinate.source_row_id, reason=reason)  # type: ignore[arg-type]
                for reason in dict.fromkeys(reasons)
            )
        exclusions = tuple(items)
        if exclusions and spec.missing_policy == "fail":
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_NONFINITE_POLICY_REQUIRED,
                "参与绘图的字段包含缺失或非有限值；请选择 fail 或 exclude_with_report 策略。",
            )
        row_mask = tuple(mutable_mask)
    else:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_UNSUPPORTED,
            "PreparationSpec kind 不在封闭联合中。",
        )

    if not isinstance(spec, FilterRowsSpec):
        row_mask = tuple(True for _row in rows)
    parquet_bytes = _serialize(fields, rows, coordinates, row_mask)
    output_hash = hashlib.sha256(parquet_bytes).hexdigest()
    input_hash = canonical_hash(
        {
            "sources": [ref.model_dump(mode="json") for ref in spec.input_refs],
            "mapping": mapping.model_dump(mode="json"),
            "spec": spec.model_dump(mode="json"),
        }
    )
    warnings = (
        (
            WarningRecord(
                warning_id="rows_excluded",
                message=f"{len(row_mask) - sum(row_mask)} rows were excluded from plotting.",
            ),
        )
        if exclusions
        else ()
    )
    contract = PreparedDataset(
        prepared_dataset_id="prepared:" + output_hash[:24],
        prepared_version=1,
        source_dataset_refs=spec.input_refs,
        field_mapping_ref=spec.field_mapping_ref,
        preparation_spec_ref=PreparationSpecRef(
            preparation_spec_id=spec.preparation_spec_id,
            preparation_version=spec.preparation_version,
            content_hash=canonical_hash(spec),
        ),
        compiler_version=spec.compiler_version,
        input_hash=input_hash,
        output_hash=output_hash,
        data_ref=ContentTableRef(
            object_hash=output_hash,
            row_count=len(rows),
            field_ids=tuple(field.field_id for field in fields),
        ),
        included_row_count=sum(row_mask),
        excluded_row_count=len(row_mask) - sum(row_mask),
        provenance=PreparedDatasetProvenance(
            source_coordinate_kinds=tuple(sorted({coordinate.kind for coordinate in coordinates})),
            compiler_build_hash=_COMPILER_BUILD_HASH,
        ),
        warnings=warnings,
    )
    return PreparedArtifact(
        prepared_dataset=contract,
        fields=fields,
        rows=rows,
        coordinates=coordinates,
        row_mask=row_mask,
        exclusions=exclusions,
        plot_order=plot_order,
        parquet_bytes=parquet_bytes,
    )

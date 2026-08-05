"""Local compiler/executor for the closed PreparationSpec union."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from datetime import date, datetime

from plotagent.importing.models import DatasetCandidate, FieldSchema, Scalar
from plotagent.importing.normalize import stable_hash
from plotagent.preparation.errors import PreparationErrorCode, PreparationProblem
from plotagent.preparation.models import (
    ApplyPlotOrderSpec,
    FieldMapping,
    IsomorphicConcatSpec,
    MaskForPlotSpec,
    PreparationSpec,
    PreparedDataset,
    ProjectMetadataLabelSpec,
    ProjectStructureSpec,
    RowExclusion,
    SelectFieldsSpec,
)


def _canonical_scalar(value: Scalar) -> object:
    if isinstance(value, float):
        if math.isnan(value):
            return {"float": "nan"}
        if value == float("inf"):
            return {"float": "+inf"}
        if value == float("-inf"):
            return {"float": "-inf"}
        return value
    if isinstance(value, (date, datetime)):
        return {"datetime": value.isoformat()}
    return value


def _json_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _candidate_input(candidate: DatasetCandidate) -> object:
    return {
        "candidate_id": candidate.candidate_id,
        "fields": [field.model_dump(mode="json") for field in candidate.fields],
        "rows": [[_canonical_scalar(value) for value in row] for row in candidate.rows],
        "coordinates": [item.model_dump(mode="json") for item in candidate.coordinates],
    }


def _mapping_shape(mapping: FieldMapping) -> list[dict[str, str]]:
    return sorted(
        (assignment.model_dump(mode="json") for assignment in mapping.assignments),
        key=lambda item: (item["role"], item["field_id"]),
    )


def semantic_signature(candidate: DatasetCandidate, mapping: FieldMapping) -> str:
    """Column-order-independent signature for a fully mapped source."""

    field_shape = sorted(
        (
            {
                "field_id": field.field_id,
                "name": field.normalized_name,
                "logical_type": field.logical_type,
                "unit": field.unit.model_dump(mode="json") if field.unit else None,
            }
            for field in candidate.fields
        ),
        key=lambda item: str(item["field_id"]),
    )
    return _json_hash({"fields": field_shape, "mapping": _mapping_shape(mapping)})


def _validate_mapping(candidates: tuple[DatasetCandidate, ...], mapping: FieldMapping) -> None:
    roles = [assignment.role for assignment in mapping.assignments]
    if len(roles) != len(set(roles)):
        raise PreparationProblem(
            PreparationErrorCode.MAPPING_ROLE_DUPLICATE,
            "FieldMapping 中的角色必须唯一。",
        )
    for candidate in candidates:
        known = {field.field_id for field in candidate.fields}
        unknown = {assignment.field_id for assignment in mapping.assignments} - known
        if unknown:
            raise PreparationProblem(
                PreparationErrorCode.MAPPING_FIELD_UNKNOWN,
                "FieldMapping 引用了当前 SourceDataset 不存在的字段。",
            )


def _field_index(candidate: DatasetCandidate) -> dict[str, int]:
    return {field.field_id: index for index, field in enumerate(candidate.fields)}


def _selected(
    candidate: DatasetCandidate, field_ids: tuple[str, ...]
) -> tuple[tuple[FieldSchema, ...], tuple[tuple[Scalar, ...], ...]]:
    indexes = _field_index(candidate)
    if any(field_id not in indexes for field_id in field_ids):
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_FIELD_UNKNOWN,
            "PreparationSpec 引用了不存在的字段。",
        )
    positions = tuple(indexes[field_id] for field_id in field_ids)
    fields = tuple(candidate.fields[index] for index in positions)
    rows = tuple(tuple(row[index] for index in positions) for row in candidate.rows)
    return fields, rows


def _same_structure(left: DatasetCandidate, right: DatasetCandidate) -> bool:
    def shape(candidate: DatasetCandidate) -> list[tuple[str, str, str | None]]:
        return sorted(
            (
                field.normalized_name,
                field.logical_type,
                field.unit.source_text if field.unit else None,
            )
            for field in candidate.fields
        )

    return shape(left) == shape(right)


def _concat(
    candidates: tuple[DatasetCandidate, ...], spec: IsomorphicConcatSpec
) -> tuple[tuple[FieldSchema, ...], tuple[tuple[Scalar, ...], ...]]:
    first = candidates[0]
    if any(not _same_structure(first, candidate) for candidate in candidates[1:]):
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_NON_ISOMORPHIC,
            "只有字段、逻辑类型和单位完全一致的数据才能纵向拼接。",
        )
    canonical_ids = tuple(field.field_id for field in first.fields)
    rows: list[tuple[Scalar, ...]] = []
    for candidate in candidates:
        index = _field_index(candidate)
        label = (
            candidate.recipe.sheet
            if spec.source_label_field == "source_sheet"
            else candidate.recipe.block
        )
        if label is None:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_STRUCTURE_INVALID,
                f"来源没有 {spec.source_label_field} 标签。",
            )
        for row in candidate.rows:
            rows.append(tuple(row[index[field_id]] for field_id in canonical_ids) + (label,))
    label_id = "fld_" + stable_hash((spec.source_label_field,))[:20]
    label_field = FieldSchema(
        field_id=label_id,
        source_name=spec.source_label_field,
        normalized_name=spec.source_label_field,
        logical_type="text",
        physical_types=("string",),
    )
    return tuple(first.fields) + (label_field,), tuple(rows)


def _wide_to_long(
    candidate: DatasetCandidate, spec: ProjectStructureSpec
) -> tuple[tuple[FieldSchema, ...], tuple[tuple[Scalar, ...], ...]]:
    if spec.index_field_id is None or not spec.value_field_ids:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_STRUCTURE_INVALID,
            "wide_to_long 需要一个索引字段和至少一个值字段。",
        )
    indexes = _field_index(candidate)
    required = (spec.index_field_id,) + spec.value_field_ids
    if any(field_id not in indexes for field_id in required):
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_FIELD_UNKNOWN,
            "结构投影引用了不存在的字段。",
        )
    value_fields = tuple(candidate.fields[indexes[field_id]] for field_id in spec.value_field_ids)
    signatures = {
        (field.logical_type, field.unit.source_text if field.unit else None)
        for field in value_fields
    }
    if len(signatures) != 1:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_STRUCTURE_INVALID,
            "wide_to_long 的值字段必须具有相同逻辑类型和单位。",
        )
    index_field = candidate.fields[indexes[spec.index_field_id]]
    variable_field = FieldSchema(
        field_id="fld_" + stable_hash((spec.variable_field_name,))[:20],
        source_name=spec.variable_field_name,
        normalized_name=spec.variable_field_name,
        logical_type="text",
        physical_types=("string",),
    )
    base_value = value_fields[0]
    value_field = base_value.model_copy(
        update={
            "field_id": "fld_" + stable_hash((spec.value_field_name,))[:20],
            "source_name": spec.value_field_name,
            "normalized_name": spec.value_field_name,
        }
    )
    output_rows: list[tuple[Scalar, ...]] = []
    for row in candidate.rows:
        index_value = row[indexes[spec.index_field_id]]
        for field in value_fields:
            output_rows.append((index_value, field.normalized_name, row[indexes[field.field_id]]))
    return (index_field, variable_field, value_field), tuple(output_rows)


def _nonfinite_or_missing(value: Scalar) -> str | None:
    if value is None:
        return "missing"
    if isinstance(value, float) and not math.isfinite(value):
        return "nonfinite"
    return None


def prepare(
    candidates: Iterable[DatasetCandidate], mapping: FieldMapping, spec: PreparationSpec
) -> PreparedDataset:
    """Apply exactly one closed preparation operation; never joins, filters, or converts units."""

    sources = tuple(candidates)
    if not sources:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_SOURCE_COUNT_INVALID,
            "Preparation 至少需要一个 SourceDataset。",
        )
    _validate_mapping(sources, mapping)
    first = sources[0]
    fields: tuple[FieldSchema, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    coordinates = tuple(coordinate for source in sources for coordinate in source.coordinates)
    row_mask: tuple[bool, ...]
    exclusions: tuple[RowExclusion, ...] = ()
    plot_order: tuple[Scalar, ...] = ()

    if isinstance(spec, SelectFieldsSpec):
        if len(sources) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_SOURCE_COUNT_INVALID,
                "select_fields 只接受一个 SourceDataset。",
            )
        fields, rows = _selected(first, spec.field_ids)
    elif isinstance(spec, ProjectStructureSpec):
        if len(sources) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_SOURCE_COUNT_INVALID,
                "project_structure 只接受一个 SourceDataset。",
            )
        if spec.orientation == "identity":
            fields, rows = _selected(first, spec.field_ids)
        else:
            fields, rows = _wide_to_long(first, spec)
            coordinates = tuple(
                coordinate for coordinate in first.coordinates for _field in spec.value_field_ids
            )
    elif isinstance(spec, IsomorphicConcatSpec):
        if len(sources) < 2:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_SOURCE_COUNT_INVALID,
                "isomorphic_concat 至少需要两个 SourceDataset。",
            )
        signatures = {semantic_signature(source, mapping) for source in sources}
        if len(signatures) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_NON_ISOMORPHIC,
                "FieldMapping 或最终语义不同，不能进入同一拼接。",
            )
        fields, rows = _concat(sources, spec)
    elif isinstance(spec, ProjectMetadataLabelSpec):
        if len(sources) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_SOURCE_COUNT_INVALID,
                "project_metadata_label 只接受一个 SourceDataset。",
            )
        if spec.metadata_key not in first.instrument_metadata:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_METADATA_MISSING,
                "选择的 InstrumentMetadata 字段不存在。",
            )
        value = first.instrument_metadata[spec.metadata_key]
        metadata_field = FieldSchema(
            field_id="fld_" + stable_hash((spec.output_field_name,))[:20],
            source_name=spec.output_field_name,
            normalized_name=spec.output_field_name,
            logical_type="text",
            physical_types=("string",),
        )
        fields = tuple(first.fields) + (metadata_field,)
        rows = tuple(row + (value,) for row in first.rows)
    elif isinstance(spec, ApplyPlotOrderSpec):
        if len(sources) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_SOURCE_COUNT_INVALID,
                "apply_plot_order 只接受一个 SourceDataset。",
            )
        if spec.field_id not in _field_index(first):
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_FIELD_UNKNOWN,
                "显示顺序引用了不存在的字段。",
            )
        fields, rows = tuple(first.fields), tuple(first.rows)
        plot_order = spec.ordered_values
    elif isinstance(spec, MaskForPlotSpec):
        if len(sources) != 1:
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_SOURCE_COUNT_INVALID,
                "mask_for_plot 只接受一个 SourceDataset。",
            )
        fields, rows = tuple(first.fields), tuple(first.rows)
        indexes = _field_index(first)
        if any(field_id not in indexes for field_id in spec.field_ids):
            raise PreparationProblem(
                PreparationErrorCode.PREPARE_FIELD_UNKNOWN,
                "绘图 mask 引用了不存在的字段。",
            )
        exclusion_items: list[RowExclusion] = []
        mutable_mask: list[bool] = []
        for row_index, (row, coordinate) in enumerate(
            zip(first.rows, first.coordinates, strict=True)
        ):
            reasons = tuple(
                reason
                for field_id in spec.field_ids
                if (reason := _nonfinite_or_missing(row[indexes[field_id]])) is not None
            )
            mutable_mask.append(not reasons)
            if reasons:
                exclusion_items.append(
                    RowExclusion(
                        row_index=row_index,
                        source_row_id=coordinate.source_row_id,
                        reasons=tuple(sorted(set(reasons))),
                    )
                )
        exclusions = tuple(exclusion_items)
        if exclusions and spec.missing_policy == "fail":
            code = (
                PreparationErrorCode.PREPARE_NONFINITE
                if any("nonfinite" in item.reasons for item in exclusions)
                else PreparationErrorCode.PREPARE_MISSING
            )
            raise PreparationProblem(code, "参与绘图的字段包含缺失或非有限值。")
        row_mask = tuple(mutable_mask)
    else:
        raise PreparationProblem(
            PreparationErrorCode.PREPARE_UNSUPPORTED,
            "PreparationSpec kind 不在封闭联合中。",
        )

    if not isinstance(spec, MaskForPlotSpec):
        row_mask = tuple(True for _row in rows)
    input_hash = _json_hash([_candidate_input(source) for source in sources])
    signature = semantic_signature(first, mapping)
    output_payload = {
        "fields": [field.model_dump(mode="json") for field in fields],
        "rows": [[_canonical_scalar(value) for value in row] for row in rows],
        "coordinates": [item.model_dump(mode="json") for item in coordinates],
        "mask": list(row_mask),
        "mapping": mapping.model_dump(mode="json"),
        "spec": spec.model_dump(mode="json"),
        "plot_order": [_canonical_scalar(value) for value in plot_order],
    }
    output_hash = _json_hash(output_payload)
    return PreparedDataset(
        prepared_dataset_id="prepared_" + output_hash[:24],
        source_dataset_ids=tuple(source.candidate_id for source in sources),
        field_mapping=mapping,
        preparation_spec=spec,
        fields=fields,
        rows=rows,
        coordinates=coordinates,
        row_mask=row_mask,
        exclusions=exclusions,
        included_count=sum(row_mask),
        excluded_count=len(row_mask) - sum(row_mask),
        plot_order=plot_order,
        input_hash=input_hash,
        output_hash=output_hash,
        semantic_signature=signature,
    )

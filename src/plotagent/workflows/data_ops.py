"""Closed, deterministic data operations for compiled workflow items."""

from __future__ import annotations

import math
from typing import Any, Protocol, cast

from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.workflows import (
    CompiledTaskItem,
    FilterPredicate,
    WorkflowScalar,
)
from plotagent.engine import (
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
)


class WorkflowDataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WorkflowDataProvider(Protocol):
    def materialize(self, data: EngineDataRef, field_ids: tuple[str, ...]) -> EngineDataView: ...


class WorkflowDataRegistrar(Protocol):
    def register(self, view: EngineDataView) -> EngineDataView: ...


def prepare_task_data(
    item: CompiledTaskItem,
    provider: WorkflowDataProvider,
    registrar: WorkflowDataRegistrar,
) -> tuple[EngineDataRef, tuple[FieldBinding, ...]]:
    """Execute the item's closed data program and return immutable engine data."""

    fields_by_source: dict[str, list[str]] = {source.source_alias: [] for source in item.sources}
    for field in item.resolved_fields:
        if field.field_id.startswith("field:workflow_"):
            continue
        fields_by_source[field.source_alias].append(field.field_id)
    views: dict[str, EngineDataView] = {}
    for source in item.sources:
        field_ids = tuple(dict.fromkeys(fields_by_source[source.source_alias]))
        if not field_ids:
            raise WorkflowDataError(
                "WORKFLOW_SOURCE_UNUSED",
                "每个任务数据来源都必须参与绑定或数据处理。",
            )
        views[source.source_alias] = provider.materialize(
            EngineDataRef(
                kind="source",
                dataset_id=source.source_dataset_id,
                version=source.source_version,
                content_hash=source.content_hash,
            ),
            field_ids,
        )

    transformed = False
    for operation in item.data_operations:
        if operation.operation == "select_fields":
            views[operation.source_alias] = _select(
                views[operation.source_alias],
                tuple(_field_id(item, alias) for alias in operation.field_aliases),
            )
        elif operation.operation == "filter_rows":
            views[operation.source_alias] = _filter(
                views[operation.source_alias],
                tuple(
                    (_field_id(item, predicate.field_alias), predicate)
                    for predicate in operation.predicates
                ),
                operation.combine,
            )
        elif operation.operation == "sort_rows":
            views[operation.source_alias] = _sort(
                views[operation.source_alias],
                tuple(
                    (_field_id(item, key.field_alias), key.direction, key.missing)
                    for key in operation.keys
                ),
            )
        elif operation.operation == "reshape_wide_to_long":
            views[operation.source_alias] = _wide_to_long(
                views[operation.source_alias],
                tuple(_field_id(item, alias) for alias in operation.id_field_aliases),
                tuple(_field_id(item, alias) for alias in operation.value_field_aliases),
                _field_id(item, operation.output_name),
                _field_id(item, operation.output_value),
            )
        elif operation.operation == "reshape_long_to_wide":
            views[operation.source_alias] = _long_to_wide(
                views[operation.source_alias],
                tuple(_field_id(item, alias) for alias in operation.index_field_aliases),
                _field_id(item, operation.name_field_alias),
                _field_id(item, operation.value_field_alias),
            )
        elif operation.operation == "concatenate_sources":
            selected = tuple(views[alias] for alias in operation.source_aliases)
            source_by_alias = {source.source_alias: source for source in item.sources}
            source_labels = operation.source_labels or tuple(
                source_by_alias[alias].display_name for alias in operation.source_aliases
            )
            combined = _concatenate(
                selected,
                source_labels,
                _field_id(item, operation.source_label_field),
            )
            views = {operation.source_aliases[0]: combined}
        elif operation.operation == "calculate_chart_data":
            # Frozen chart calculations remain profile-owned and consume the
            # immutable values produced by the preceding structural operations.
            pass
        transformed = True

    if len(views) != 1:
        raise WorkflowDataError(
            "WORKFLOW_SOURCES_NOT_COMBINED",
            "同一任务项的多个数据来源必须通过 concatenate_sources 明确合并。",
        )
    view = next(iter(views.values()))
    if transformed:
        view = _derived_view(item, view)
        view = registrar.register(view)
    bindings = tuple(
        FieldBinding(role=binding.role, field_id=binding.field_id) for binding in item.bindings
    )
    available = {column.field.field_id for column in view.columns}
    missing = tuple(binding.field_id for binding in bindings if binding.field_id not in available)
    if missing:
        raise WorkflowDataError(
            "WORKFLOW_BINDING_OUTPUT_MISSING",
            f"数据处理结果缺少已确认字段：{missing!r}",
        )
    return view.data, bindings


def _field_id(item: CompiledTaskItem, alias: str) -> str:
    match = next(
        (field.field_id for field in item.resolved_fields if field.field_alias == alias),
        None,
    )
    if match is None:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", f"数据操作字段不可用：{alias}")
    return match


def _select(view: EngineDataView, field_ids: tuple[str, ...]) -> EngineDataView:
    columns = {column.field.field_id: column for column in view.columns}
    try:
        selected = tuple(columns[field_id] for field_id in field_ids)
    except KeyError as error:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "选择字段不属于数据表。") from error
    return view.model_copy(update={"columns": selected})


def _filter(
    view: EngineDataView,
    predicates: tuple[tuple[str, FilterPredicate], ...],
    combine: str,
) -> EngineDataView:
    columns = {column.field.field_id: column.values for column in view.columns}
    try:
        masks = tuple(
            tuple(_matches(value, predicate) for value in columns[field_id])
            for field_id, predicate in predicates
        )
    except KeyError as error:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "筛选字段不属于数据表。") from error
    keep = tuple(
        (all(values) if combine == "all" else any(values)) for values in zip(*masks, strict=True)
    )
    indices = tuple(index for index, included in enumerate(keep) if included)
    if not indices:
        raise WorkflowDataError("WORKFLOW_EMPTY_RESULT", "筛选后没有可绘制的数据行。")
    return _take(view, indices)


def _matches(value: WorkflowScalar, predicate: FilterPredicate) -> bool:
    if predicate.operator == "is_missing":
        return value is None or (isinstance(value, float) and math.isnan(value))
    if predicate.operator == "is_not_missing":
        return value is not None and not (isinstance(value, float) and math.isnan(value))
    if predicate.operator == "in_values":
        assert isinstance(predicate.value, tuple)
        return value in predicate.value
    target = predicate.value
    if value is None or target is None or isinstance(target, tuple):
        return False
    if predicate.operator == "equal":
        return value == target
    if predicate.operator == "not_equal":
        return value != target
    try:
        if predicate.operator == "less_than":
            return value < target  # type: ignore[operator]
        if predicate.operator == "less_or_equal":
            return value <= target  # type: ignore[operator]
        if predicate.operator == "greater_than":
            return value > target  # type: ignore[operator]
        return value >= target  # type: ignore[operator]
    except TypeError:
        return False


def _sort(
    view: EngineDataView,
    keys: tuple[tuple[str, str, str], ...],
) -> EngineDataView:
    columns = {column.field.field_id: column.values for column in view.columns}
    indices = list(range(len(view.row_ids)))
    for field_id, direction, missing in reversed(keys):
        try:
            values = columns[field_id]
        except KeyError as error:
            raise WorkflowDataError("FIELD_ALIAS_INVALID", "排序字段不属于数据表。") from error
        present = [index for index in indices if values[index] is not None]
        absent = [index for index in indices if values[index] is None]
        try:
            present.sort(
                key=lambda index: cast(Any, values[index]),
                reverse=direction == "descending",
            )
        except TypeError as error:
            raise WorkflowDataError(
                "WORKFLOW_SORT_TYPE_INVALID", "排序字段包含不可比较的混合值。"
            ) from error
        indices = absent + present if missing == "first" else present + absent
    return _take(view, tuple(indices))


def _take(view: EngineDataView, indices: tuple[int, ...]) -> EngineDataView:
    return view.model_copy(
        update={
            "row_ids": tuple(view.row_ids[index] for index in indices),
            "columns": tuple(
                column.model_copy(
                    update={"values": tuple(column.values[index] for index in indices)}
                )
                for column in view.columns
            ),
        }
    )


def _wide_to_long(
    view: EngineDataView,
    id_fields: tuple[str, ...],
    value_fields: tuple[str, ...],
    output_name_id: str,
    output_value_id: str,
) -> EngineDataView:
    columns = {column.field.field_id: column for column in view.columns}
    try:
        ids = tuple(columns[field_id] for field_id in id_fields)
        values = tuple(columns[field_id] for field_id in value_fields)
    except KeyError as error:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "宽转长字段不属于数据表。") from error
    row_ids: list[str] = []
    output_columns: list[list[WorkflowScalar]] = [[] for _ in ids]
    names: list[WorkflowScalar] = []
    output_values: list[WorkflowScalar] = []
    for row_index, row_id in enumerate(view.row_ids):
        for value_column in values:
            row_ids.append(f"{row_id}.{value_column.field.field_id.removeprefix('field:')}")
            for position, id_column in enumerate(ids):
                output_columns[position].append(id_column.values[row_index])
            names.append(value_column.field.name)
            output_values.append(value_column.values[row_index])
    return EngineDataView(
        data=view.data,
        row_ids=tuple(row_ids),
        columns=tuple(
            column.model_copy(update={"values": tuple(output_columns[index])})
            for index, column in enumerate(ids)
        )
        + (
            EngineColumn(
                field=EngineField(
                    field_id=output_name_id,
                    name="Series",
                    logical_type="categorical",
                ),
                values=tuple(names),
            ),
            EngineColumn(
                field=EngineField(
                    field_id=output_value_id,
                    name="Value",
                    logical_type="numeric",
                ),
                values=tuple(output_values),
            ),
        ),
    )


def _long_to_wide(
    view: EngineDataView,
    index_fields: tuple[str, ...],
    name_field: str,
    value_field: str,
) -> EngineDataView:
    columns = {column.field.field_id: column for column in view.columns}
    try:
        indices = tuple(columns[field_id] for field_id in index_fields)
        names = columns[name_field]
        values = columns[value_field]
    except KeyError as error:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "长转宽字段不属于数据表。") from error
    keys: list[tuple[WorkflowScalar, ...]] = []
    name_order: list[str] = []
    cells: dict[tuple[tuple[WorkflowScalar, ...], str], WorkflowScalar] = {}
    for row_index in range(len(view.row_ids)):
        key = tuple(column.values[row_index] for column in indices)
        name = str(names.values[row_index])
        if key not in keys:
            keys.append(key)
        if name not in name_order:
            name_order.append(name)
        cell = (key, name)
        if cell in cells:
            raise WorkflowDataError(
                "WORKFLOW_RESHAPE_DUPLICATE", "长转宽遇到重复键，禁止隐式聚合。"
            )
        cells[cell] = values.values[row_index]
    output = tuple(
        column.model_copy(update={"values": tuple(key[position] for key in keys)})
        for position, column in enumerate(indices)
    )
    value_columns = tuple(
        EngineColumn(
            field=EngineField(
                field_id=f"field:wide_{canonical_hash(name)[:20]}",
                name=name,
                logical_type=values.field.logical_type,
                unit_label=values.field.unit_label,
            ),
            values=tuple(cells.get((key, name)) for key in keys),
        )
        for name in name_order
    )
    return EngineDataView(
        data=view.data,
        row_ids=tuple(f"row:wide.{index + 1}" for index in range(len(keys))),
        columns=output + value_columns,
    )


def _concatenate(
    views: tuple[EngineDataView, ...],
    source_labels: tuple[str, ...],
    source_label_id: str,
) -> EngineDataView:
    baseline = views[0]
    signatures = tuple(
        tuple((column.field.name, column.field.logical_type) for column in view.columns)
        for view in views
    )
    if len(set(signatures)) != 1:
        raise WorkflowDataError(
            "WORKFLOW_NON_ISOMORPHIC",
            "合并到同一张图的数据表必须具有相同字段名称和类型。",
        )
    row_ids: list[str] = []
    output_values: list[list[WorkflowScalar]] = [[] for _ in baseline.columns]
    source_values: list[WorkflowScalar] = []
    for source_index, (label, view) in enumerate(zip(source_labels, views, strict=True), start=1):
        for row_index, _row_id in enumerate(view.row_ids):
            row_ids.append(f"row:concat.{source_index}.{row_index + 1}")
            source_values.append(label)
        for position, column in enumerate(view.columns):
            output_values[position].extend(column.values)
    return EngineDataView(
        data=baseline.data,
        row_ids=tuple(row_ids),
        columns=tuple(
            baseline.columns[position].model_copy(update={"values": tuple(values)})
            for position, values in enumerate(output_values)
        )
        + (
            EngineColumn(
                field=EngineField(
                    field_id=source_label_id,
                    name="Source",
                    logical_type="categorical",
                ),
                values=tuple(source_values),
            ),
        ),
    )


def _derived_view(item: CompiledTaskItem, view: EngineDataView) -> EngineDataView:
    payload = {
        "item_id": item.item_id,
        "operations": [operation.model_dump(mode="json") for operation in item.data_operations],
        "row_ids": view.row_ids,
        "columns": [column.model_dump(mode="json") for column in view.columns],
    }
    digest = canonical_hash(cast(Any, payload))
    return view.model_copy(
        update={
            "data": EngineDataRef(
                kind="prepared",
                dataset_id=f"workflow:{digest[:24]}",
                version=1,
                content_hash=digest,
            ),
            "row_ids": tuple(
                f"row:workflow.{digest[:16]}.{index + 1}" for index in range(len(view.row_ids))
            ),
        }
    )

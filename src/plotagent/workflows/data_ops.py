"""Closed, deterministic data operations for compiled workflow items."""

from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date, datetime
from typing import Any, Protocol, cast

from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.workflows import (
    CompiledTaskItem,
    DataOperation,
    FilterPredicate,
    RowPage,
    WorkflowContext,
    WorkflowScalar,
)
from plotagent.engine import (
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
)
from plotagent.units import convert_value, resolve_unit


class WorkflowDataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WorkflowDataProvider(Protocol):
    def materialize(self, data: EngineDataRef, field_ids: tuple[str, ...]) -> EngineDataView: ...


class WorkflowDataRegistrar(Protocol):
    def register(self, view: EngineDataView) -> EngineDataView: ...


def _operation_source_aliases(operation: DataOperation) -> tuple[str, ...]:
    if operation.operation == "concatenate_sources":
        return operation.source_aliases
    if operation.operation == "align_sources_on_x":
        return operation.source_aliases
    return (operation.source_alias,)


def preview_data_operation(
    context: WorkflowContext,
    rows_by_alias: dict[str, tuple[tuple[WorkflowScalar, ...], ...]],
    operation: DataOperation,
    *,
    limit: int = 5,
) -> RowPage:
    """Run one closed operation in memory and disclose a bounded preview."""

    if not 1 <= limit <= 40:
        raise WorkflowDataError("INSPECTION_RANGE_INVALID", "数据处理预览行数无效。")
    source_aliases = _operation_source_aliases(operation)
    views: dict[str, EngineDataView] = {}
    for source_alias in source_aliases:
        source = next(
            (candidate for candidate in context.sources if candidate.source_alias == source_alias),
            None,
        )
        if source is None:
            raise WorkflowDataError("SOURCE_ALIAS_INVALID", "数据处理来源不可用。")
        source_fields = tuple(
            field for field in context.fields if field.source_alias == source_alias
        )
        source_rows = rows_by_alias[source_alias]
        views[source_alias] = EngineDataView(
            data=EngineDataRef(
                kind="source",
                dataset_id=source.source_dataset_id,
                version=source.source_version,
                content_hash=source.content_hash,
            ),
            row_ids=tuple(f"row:preview.{index + 1}" for index in range(len(source_rows))),
            columns=tuple(
                EngineColumn(
                    field=EngineField(
                        field_id=_preview_field_id(field.field_alias),
                        name=field.name,
                        logical_type=field.logical_type,
                        unit_label=field.unit_label,
                    ),
                    values=tuple(row[position] for row in source_rows),
                )
                for position, field in enumerate(source_fields)
            ),
        )

    if operation.operation == "select_fields":
        result = _select(
            views[operation.source_alias],
            tuple(_preview_field_id(alias) for alias in operation.field_aliases),
        )
    elif operation.operation == "filter_rows":
        result = _filter(
            views[operation.source_alias],
            tuple(
                (_preview_field_id(predicate.field_alias), predicate)
                for predicate in operation.predicates
            ),
            operation.combine,
        )
    elif operation.operation == "sort_rows":
        result = _sort(
            views[operation.source_alias],
            tuple(
                (_preview_field_id(key.field_alias), key.direction, key.missing)
                for key in operation.keys
            ),
        )
    elif operation.operation == "exclude_rows":
        result = _exclude_rows(views[operation.source_alias], operation.row_indices)
    elif operation.operation == "drop_empty_fields":
        result = _drop_empty_fields(
            views[operation.source_alias],
            tuple(_preview_field_id(alias) for alias in operation.field_aliases),
        )
    elif operation.operation == "convert_type":
        result = _convert_type(
            views[operation.source_alias],
            _preview_field_id(operation.field_alias),
            operation.target_type,
            _preview_field_id(operation.output_field_alias),
            operation.output_name,
            operation.decimal_separator,
            operation.thousands_separator,
            operation.datetime_format,
            operation.datetime_numeric_mode,
            operation.true_values,
            operation.false_values,
            operation.case_sensitive,
        )
    elif operation.operation == "reshape_wide_to_long":
        result = _wide_to_long(
            views[operation.source_alias],
            tuple(_preview_field_id(alias) for alias in operation.id_field_aliases),
            tuple(_preview_field_id(alias) for alias in operation.value_field_aliases),
            _preview_field_id(operation.output_name),
            _preview_field_id(operation.output_value),
        )
    elif operation.operation == "reshape_long_to_wide":
        result = _long_to_wide(
            views[operation.source_alias],
            tuple(_preview_field_id(alias) for alias in operation.index_field_aliases),
            _preview_field_id(operation.name_field_alias),
            _preview_field_id(operation.value_field_alias),
            tuple(
                (_preview_field_id(item.field_alias), item.name) for item in operation.output_fields
            ),
        )
    elif operation.operation == "rename_field":
        result = _rename_field(
            views[operation.source_alias],
            _preview_field_id(operation.field_alias),
            _preview_field_id(operation.output_field_alias),
            operation.output_name,
        )
    elif operation.operation == "derive_column":
        result = _derive_column(
            views[operation.source_alias],
            tuple(_preview_field_id(alias) for alias in operation.input_field_aliases),
            operation.operator,
            operation.scalar,
            _preview_field_id(operation.output_field_alias),
            operation.output_name,
        )
    elif operation.operation == "convert_unit":
        result = _convert_unit(
            views[operation.source_alias],
            _preview_field_id(operation.field_alias),
            operation.target_unit,
            _preview_field_id(operation.output_field_alias),
            operation.output_name,
        )
    elif operation.operation == "bucketize_numeric":
        result = _bucketize_numeric(
            views[operation.source_alias],
            _preview_field_id(operation.field_alias),
            operation.boundaries,
            operation.labels,
            _preview_field_id(operation.output_field_alias),
            operation.output_name,
        )
    elif operation.operation == "concatenate_sources":
        source_by_alias = {source.source_alias: source for source in context.sources}
        labels = operation.source_labels or tuple(
            source_by_alias[alias].display_name for alias in operation.source_aliases
        )
        result = _concatenate(
            tuple(views[alias] for alias in operation.source_aliases),
            labels,
            _preview_field_id(operation.source_label_field),
        )
    else:
        result = _align_sources_on_x(
            tuple(views[alias] for alias in operation.source_aliases),
            tuple(_preview_field_id(alias) for alias in operation.x_field_aliases),
            tuple(_preview_field_id(alias) for alias in operation.value_field_aliases),
            _preview_field_id(operation.output_x_field_alias),
            operation.output_x_name,
            tuple(
                (_preview_field_id(field.field_alias), field.name)
                for field in operation.output_series_fields
            ),
            operation.numeric_tolerance,
        )
    selected_rows = tuple(
        tuple(column.values[index] for column in result.columns)
        for index in range(min(limit, len(result.row_ids)))
    )
    return RowPage(
        source_alias=source_aliases[0],
        field_aliases=tuple(
            cast(Any, column.field.field_id.removeprefix("field:")) for column in result.columns
        ),
        offset=0,
        rows=selected_rows,
        has_more=len(result.row_ids) > len(selected_rows),
    )


def _preview_field_id(alias: str) -> str:
    return f"field:{alias}"


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
        elif operation.operation == "exclude_rows":
            views[operation.source_alias] = _exclude_rows(
                views[operation.source_alias], operation.row_indices
            )
        elif operation.operation == "drop_empty_fields":
            views[operation.source_alias] = _drop_empty_fields(
                views[operation.source_alias],
                tuple(_field_id(item, alias) for alias in operation.field_aliases),
            )
        elif operation.operation == "convert_type":
            views[operation.source_alias] = _convert_type(
                views[operation.source_alias],
                _field_id(item, operation.field_alias),
                operation.target_type,
                _field_id(item, operation.output_field_alias),
                operation.output_name,
                operation.decimal_separator,
                operation.thousands_separator,
                operation.datetime_format,
                operation.datetime_numeric_mode,
                operation.true_values,
                operation.false_values,
                operation.case_sensitive,
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
                tuple(
                    (_field_id(item, output.field_alias), output.name)
                    for output in operation.output_fields
                ),
            )
        elif operation.operation == "rename_field":
            views[operation.source_alias] = _rename_field(
                views[operation.source_alias],
                _field_id(item, operation.field_alias),
                _field_id(item, operation.output_field_alias),
                operation.output_name,
            )
        elif operation.operation == "derive_column":
            views[operation.source_alias] = _derive_column(
                views[operation.source_alias],
                tuple(_field_id(item, alias) for alias in operation.input_field_aliases),
                operation.operator,
                operation.scalar,
                _field_id(item, operation.output_field_alias),
                operation.output_name,
            )
        elif operation.operation == "convert_unit":
            views[operation.source_alias] = _convert_unit(
                views[operation.source_alias],
                _field_id(item, operation.field_alias),
                operation.target_unit,
                _field_id(item, operation.output_field_alias),
                operation.output_name,
            )
        elif operation.operation == "bucketize_numeric":
            views[operation.source_alias] = _bucketize_numeric(
                views[operation.source_alias],
                _field_id(item, operation.field_alias),
                operation.boundaries,
                operation.labels,
                _field_id(item, operation.output_field_alias),
                operation.output_name,
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
        elif operation.operation == "align_sources_on_x":
            combined = _align_sources_on_x(
                tuple(views[alias] for alias in operation.source_aliases),
                tuple(_field_id(item, alias) for alias in operation.x_field_aliases),
                tuple(_field_id(item, alias) for alias in operation.value_field_aliases),
                _field_id(item, operation.output_x_field_alias),
                operation.output_x_name,
                tuple(
                    (_field_id(item, field.field_alias), field.name)
                    for field in operation.output_series_fields
                ),
                operation.numeric_tolerance,
            )
            views = {operation.source_aliases[0]: combined}
        transformed = True

    if len(views) != 1:
        raise WorkflowDataError(
            "WORKFLOW_SOURCES_NOT_COMBINED",
            "同一任务项的多个数据来源必须通过 concatenate_sources 或 "
            "align_sources_on_x 明确合并。",
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
    if predicate.operator == "is_finite":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    if predicate.operator == "is_not_finite":
        return isinstance(value, float) and not math.isfinite(value)
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


def _exclude_rows(view: EngineDataView, row_indices: tuple[int, ...]) -> EngineDataView:
    invalid = tuple(index for index in row_indices if index >= len(view.row_ids))
    if invalid:
        raise WorkflowDataError(
            "WORKFLOW_ROW_INDEX_INVALID",
            f"要排除的行超出当前数据范围：{invalid!r}",
        )
    excluded = set(row_indices)
    keep = tuple(index for index in range(len(view.row_ids)) if index not in excluded)
    if not keep:
        raise WorkflowDataError("WORKFLOW_EMPTY_RESULT", "排除指定行后没有可绘制的数据。")
    return _take(view, keep)


def _is_missing(value: WorkflowScalar) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _drop_empty_fields(view: EngineDataView, field_ids: tuple[str, ...]) -> EngineDataView:
    requested = set(field_ids)
    available = {column.field.field_id for column in view.columns}
    if not requested <= available:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "待删除的空字段不属于数据表。")
    for column in view.columns:
        if column.field.field_id not in requested:
            continue
        if any(
            not _is_missing(value) and (not isinstance(value, str) or bool(value.strip()))
            for value in column.values
        ):
            raise WorkflowDataError(
                "WORKFLOW_FIELD_NOT_EMPTY",
                f"字段 {column.field.name} 含有有效数据，不能作为空字段删除。",
            )
    remaining = tuple(
        column for column in view.columns if column.field.field_id not in requested
    )
    if not remaining:
        raise WorkflowDataError("WORKFLOW_EMPTY_RESULT", "删除空字段后没有可绘制字段。")
    return view.model_copy(update={"columns": remaining})


def _convert_type(
    view: EngineDataView,
    field_id: str,
    target_type: str,
    output_field_id: str,
    output_name: str,
    decimal_separator: str,
    thousands_separator: str | None,
    datetime_format: str | None,
    datetime_numeric_mode: str | None,
    true_values: tuple[str, ...],
    false_values: tuple[str, ...],
    case_sensitive: bool,
) -> EngineDataView:
    source = next((column for column in view.columns if column.field.field_id == field_id), None)
    if source is None:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "类型转换字段不属于数据表。")
    if any(column.field.field_id == output_field_id for column in view.columns):
        raise WorkflowDataError("FIELD_ALIAS_DUPLICATED", "类型转换输出字段已存在。")
    converted: list[WorkflowScalar] = []
    for row_index, (row_id, value) in enumerate(
        zip(view.row_ids, source.values, strict=True), start=1
    ):
        if _is_missing(value):
            converted.append(None)
            continue
        result: WorkflowScalar
        try:
            if target_type == "numeric":
                if datetime_numeric_mode == "ordinal_day":
                    if isinstance(value, datetime):
                        parsed = value
                    elif isinstance(value, date):
                        parsed = datetime.combine(value, datetime.min.time())
                    elif isinstance(value, str) and datetime_format is not None:
                        parsed = datetime.strptime(value.strip(), datetime_format)
                    else:
                        raise ValueError
                    seconds = (
                        parsed.hour * 3600
                        + parsed.minute * 60
                        + parsed.second
                        + parsed.microsecond / 1_000_000
                    )
                    result = float(parsed.toordinal()) + seconds / 86_400
                else:
                    if isinstance(value, bool):
                        raise ValueError
                    if isinstance(value, (int, float)):
                        result = float(value)
                    elif isinstance(value, str):
                        text = value.strip()
                        if thousands_separator:
                            text = text.replace(thousands_separator, "")
                        if decimal_separator == ",":
                            text = text.replace(",", ".")
                        numeric = float(text)
                        if not math.isfinite(numeric):
                            raise ValueError
                        result = numeric
                    else:
                        raise ValueError
                if not isinstance(result, float) or not math.isfinite(result):
                    raise ValueError
            elif target_type == "datetime":
                if isinstance(value, datetime):
                    result = value
                elif isinstance(value, date):
                    result = datetime.combine(value, datetime.min.time())
                elif isinstance(value, str) and datetime_format is not None:
                    result = datetime.strptime(value.strip(), datetime_format)
                else:
                    raise ValueError
            elif target_type == "boolean":
                if isinstance(value, bool):
                    result = value
                else:
                    text = str(value)
                    normalized = text if case_sensitive else text.casefold()
                    true_set = {
                        item if case_sensitive else item.casefold() for item in true_values
                    }
                    false_set = {
                        item if case_sensitive else item.casefold() for item in false_values
                    }
                    if normalized in true_set:
                        result = True
                    elif normalized in false_set:
                        result = False
                    else:
                        raise ValueError
            else:
                result = str(value)
        except (TypeError, ValueError) as error:
            raise WorkflowDataError(
                "WORKFLOW_TYPE_CONVERSION_FAILED",
                f"字段 {source.field.name} 的第 {row_index} 行（{row_id}）无法转换：{value!r}",
            ) from error
        converted.append(result)
    derived = EngineColumn(
        field=EngineField(
            field_id=output_field_id,
            name=output_name,
            logical_type=cast(Any, target_type),
            unit_label=(
                "day"
                if datetime_numeric_mode == "ordinal_day"
                else source.field.unit_label if target_type == "numeric" else None
            ),
        ),
        values=tuple(converted),
    )
    return view.model_copy(update={"columns": view.columns + (derived,)})


def _rename_field(
    view: EngineDataView,
    field_id: str,
    output_field_id: str,
    output_name: str,
) -> EngineDataView:
    column = next((item for item in view.columns if item.field.field_id == field_id), None)
    if column is None:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "重命名字段不属于数据表。")
    derived = column.model_copy(
        update={
            "field": column.field.model_copy(
                update={"field_id": output_field_id, "name": output_name}
            )
        }
    )
    return view.model_copy(update={"columns": view.columns + (derived,)})


def _derive_column(
    view: EngineDataView,
    input_field_ids: tuple[str, ...],
    operator: str,
    scalar: float | None,
    output_field_id: str,
    output_name: str,
) -> EngineDataView:
    by_id = {column.field.field_id: column for column in view.columns}
    try:
        inputs = tuple(by_id[field_id] for field_id in input_field_ids)
    except KeyError as error:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "派生字段输入不属于数据表。") from error
    if any(column.field.logical_type != "numeric" for column in inputs):
        raise WorkflowDataError("WORKFLOW_DERIVE_TYPE_INVALID", "派生计算只接受数值字段。")
    unit_labels = tuple(column.field.unit_label or "" for column in inputs)
    if operator in {"add", "subtract"} and len(set(unit_labels)) != 1:
        raise WorkflowDataError("WORKFLOW_UNIT_INCOMPATIBLE", "加减字段必须使用相同单位。")
    if operator in {"log10", "ln", "sqrt"} and unit_labels[0]:
        raise WorkflowDataError("WORKFLOW_UNIT_INCOMPATIBLE", "该数学操作只接受无量纲字段。")
    if len(inputs) == 2 and operator in {"multiply", "divide"} and any(unit_labels):
        raise WorkflowDataError(
            "WORKFLOW_DERIVE_DIMENSION_UNSUPPORTED",
            "两个有量纲字段的乘除尚未加入受控量纲注册表。",
        )

    values: list[WorkflowScalar] = []
    for row_index in range(len(view.row_ids)):
        operands = tuple(column.values[row_index] for column in inputs)
        if any(value is None for value in operands):
            values.append(None)
            continue
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) for value in operands
        ):
            raise WorkflowDataError("WORKFLOW_DERIVE_TYPE_INVALID", "派生计算遇到非数值。")
        numeric = tuple(float(cast(Any, value)) for value in operands)
        right = numeric[1] if len(numeric) == 2 else scalar
        try:
            if operator == "add":
                result = numeric[0] + cast(float, right)
            elif operator == "subtract":
                result = numeric[0] - cast(float, right)
            elif operator == "multiply":
                result = numeric[0] * cast(float, right)
            elif operator == "divide":
                result = numeric[0] / cast(float, right)
            elif operator == "absolute":
                result = abs(numeric[0])
            elif operator == "negate":
                result = -numeric[0]
            elif operator == "log10":
                result = math.log10(numeric[0])
            elif operator == "ln":
                result = math.log(numeric[0])
            else:
                result = math.sqrt(numeric[0])
        except (ValueError, ZeroDivisionError) as error:
            raise WorkflowDataError(
                "WORKFLOW_DERIVE_DOMAIN_INVALID", "派生计算遇到无效数学定义域。"
            ) from error
        if not math.isfinite(result):
            raise WorkflowDataError("WORKFLOW_DERIVE_NONFINITE", "派生计算产生非有限值。")
        values.append(result)
    derived = EngineColumn(
        field=EngineField(
            field_id=output_field_id,
            name=output_name,
            logical_type="numeric",
            unit_label=(
                None if operator in {"log10", "ln", "sqrt"} else inputs[0].field.unit_label
            ),
        ),
        values=tuple(values),
    )
    return view.model_copy(update={"columns": view.columns + (derived,)})


def _convert_unit(
    view: EngineDataView,
    field_id: str,
    target_unit: str,
    output_field_id: str,
    output_name: str,
) -> EngineDataView:
    column = next((item for item in view.columns if item.field.field_id == field_id), None)
    if column is None:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "单位换算字段不属于数据表。")
    source_unit = column.field.unit_label or ""
    source_definition = resolve_unit(source_unit)
    target_definition = resolve_unit(target_unit)
    if source_definition is None or target_definition is None:
        raise WorkflowDataError("WORKFLOW_UNIT_UNKNOWN", "源单位或目标单位不在注册表中。")
    if source_definition.dimensionality != target_definition.dimensionality:
        raise WorkflowDataError("WORKFLOW_UNIT_INCOMPATIBLE", "源单位与目标单位量纲不兼容。")
    converted: list[WorkflowScalar] = []
    for value in column.values:
        if value is None:
            converted.append(None)
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise WorkflowDataError("WORKFLOW_UNIT_TYPE_INVALID", "单位换算只接受数值字段。")
        else:
            converted.append(convert_value(float(value), source_unit, target_unit))
    derived = EngineColumn(
        field=EngineField(
            field_id=output_field_id,
            name=output_name,
            logical_type="numeric",
            unit_label=target_definition.symbol,
        ),
        values=tuple(converted),
    )
    return view.model_copy(update={"columns": view.columns + (derived,)})


def _bucketize_numeric(
    view: EngineDataView,
    field_id: str,
    boundaries: tuple[float, ...],
    labels: tuple[str, ...],
    output_field_id: str,
    output_name: str,
) -> EngineDataView:
    column = next((item for item in view.columns if item.field.field_id == field_id), None)
    if column is None:
        raise WorkflowDataError("FIELD_ALIAS_INVALID", "分组字段不属于数据表。")
    if column.field.logical_type != "numeric":
        raise WorkflowDataError("WORKFLOW_BUCKET_TYPE_INVALID", "阈值分组只接受数值字段。")
    categorized: list[WorkflowScalar] = []
    for value in column.values:
        if value is None:
            categorized.append(None)
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise WorkflowDataError("WORKFLOW_BUCKET_TYPE_INVALID", "阈值分组遇到非数值。")
        else:
            categorized.append(labels[bisect_right(boundaries, float(value))])
    derived = EngineColumn(
        field=EngineField(
            field_id=output_field_id,
            name=output_name,
            logical_type="categorical",
        ),
        values=tuple(categorized),
    )
    return view.model_copy(update={"columns": view.columns + (derived,)})


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
    output_fields: tuple[tuple[str, str], ...],
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
    expected_names = tuple(name for _field_id, name in output_fields)
    if tuple(name_order) != expected_names:
        raise WorkflowDataError(
            "WORKFLOW_RESHAPE_OUTPUT_MISMATCH",
            "长转宽实际系列与 Agent 声明的输出字段不一致。",
        )
    output = tuple(
        column.model_copy(update={"values": tuple(key[position] for key in keys)})
        for position, column in enumerate(indices)
    )
    value_columns = tuple(
        EngineColumn(
            field=EngineField(
                field_id=field_id,
                name=name,
                logical_type=values.field.logical_type,
                unit_label=values.field.unit_label,
            ),
            values=tuple(cells.get((key, name)) for key in keys),
        )
        for field_id, name in output_fields
    )
    return EngineDataView(
        data=view.data,
        row_ids=tuple(f"row:wide.{index + 1}" for index in range(len(keys))),
        columns=output + value_columns,
    )


def _aligned_x_values(
    baseline: tuple[WorkflowScalar, ...],
    candidate: tuple[WorkflowScalar, ...],
    tolerance: float,
) -> bool:
    if len(baseline) != len(candidate):
        return False
    for left, right in zip(baseline, candidate, strict=True):
        if (
            isinstance(left, (int, float))
            and not isinstance(left, bool)
            and isinstance(right, (int, float))
            and not isinstance(right, bool)
        ):
            if not math.isfinite(float(left)) or not math.isfinite(float(right)):
                return False
            if abs(float(left) - float(right)) > tolerance:
                return False
        elif left != right:
            return False
    return True


def _align_sources_on_x(
    views: tuple[EngineDataView, ...],
    x_field_ids: tuple[str, ...],
    value_field_ids: tuple[str, ...],
    output_x_field_id: str,
    output_x_name: str,
    output_series: tuple[tuple[str, str], ...],
    numeric_tolerance: float,
) -> EngineDataView:
    if not (
        len(views)
        == len(x_field_ids)
        == len(value_field_ids)
        == len(output_series)
    ):
        raise WorkflowDataError("WORKFLOW_ALIGNMENT_INVALID", "多源对齐参数数量不一致。")
    x_columns: list[EngineColumn] = []
    value_columns: list[EngineColumn] = []
    for view, x_field_id, value_field_id in zip(
        views, x_field_ids, value_field_ids, strict=True
    ):
        by_id = {column.field.field_id: column for column in view.columns}
        try:
            x_columns.append(by_id[x_field_id])
            value_columns.append(by_id[value_field_id])
        except KeyError as error:
            raise WorkflowDataError(
                "FIELD_ALIAS_INVALID", "多源对齐字段不属于对应数据表。"
            ) from error
    baseline_x = x_columns[0]
    baseline_signature = (baseline_x.field.logical_type, baseline_x.field.unit_label or "")
    if any(
        (column.field.logical_type, column.field.unit_label or "") != baseline_signature
        for column in x_columns[1:]
    ):
        raise WorkflowDataError(
            "WORKFLOW_ALIGNMENT_X_TYPE_MISMATCH", "多源数据的 X 字段类型或单位不一致。"
        )
    for position, column in enumerate(x_columns[1:], start=2):
        if not _aligned_x_values(baseline_x.values, column.values, numeric_tolerance):
            raise WorkflowDataError(
                "WORKFLOW_ALIGNMENT_X_MISMATCH",
                f"第 {position} 个数据源的 X 序列与第一个数据源不一致；"
                "未执行排序、插值或静默截断。",
            )
    value_signatures = {
        (column.field.logical_type, column.field.unit_label or "") for column in value_columns
    }
    if len(value_signatures) != 1:
        raise WorkflowDataError(
            "WORKFLOW_ALIGNMENT_SERIES_TYPE_MISMATCH",
            "合并到同一坐标轴的系列字段必须具有相同类型和单位。",
        )
    output_x = EngineColumn(
        field=EngineField(
            field_id=output_x_field_id,
            name=output_x_name,
            logical_type=baseline_x.field.logical_type,
            unit_label=baseline_x.field.unit_label,
        ),
        values=baseline_x.values,
    )
    output_values = tuple(
        EngineColumn(
            field=EngineField(
                field_id=output_field_id,
                name=output_name,
                logical_type=source.field.logical_type,
                unit_label=source.field.unit_label,
            ),
            values=source.values,
        )
        for source, (output_field_id, output_name) in zip(
            value_columns, output_series, strict=True
        )
    )
    return EngineDataView(
        data=views[0].data,
        row_ids=views[0].row_ids,
        columns=(output_x, *output_values),
    )


def _concatenate(
    views: tuple[EngineDataView, ...],
    source_labels: tuple[str, ...],
    source_label_id: str,
) -> EngineDataView:
    baseline = views[0]
    baseline_signature = tuple(
        (column.field.name, column.field.logical_type, column.field.unit_label or "")
        for column in baseline.columns
    )
    if len(baseline_signature) != len(set(baseline_signature)):
        raise WorkflowDataError(
            "WORKFLOW_NON_ISOMORPHIC",
            "合并到同一张图的数据表必须具有相同字段名称、类型和单位。",
        )
    aligned_columns: list[tuple[EngineColumn, ...]] = []
    for view in views:
        columns_by_signature = {
            (column.field.name, column.field.logical_type, column.field.unit_label or ""): column
            for column in view.columns
        }
        if len(columns_by_signature) != len(view.columns) or set(columns_by_signature) != set(
            baseline_signature
        ):
            raise WorkflowDataError(
                "WORKFLOW_NON_ISOMORPHIC",
                "合并到同一张图的数据表必须具有相同字段名称、类型和单位。",
            )
        aligned_columns.append(
            tuple(columns_by_signature[signature] for signature in baseline_signature)
        )
    row_ids: list[str] = []
    output_values: list[list[WorkflowScalar]] = [[] for _ in baseline.columns]
    source_values: list[WorkflowScalar] = []
    for source_index, (label, view, columns) in enumerate(
        zip(source_labels, views, aligned_columns, strict=True), start=1
    ):
        for row_index, _row_id in enumerate(view.row_ids):
            row_ids.append(f"row:concat.{source_index}.{row_index + 1}")
            source_values.append(label)
        for position, column in enumerate(columns):
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

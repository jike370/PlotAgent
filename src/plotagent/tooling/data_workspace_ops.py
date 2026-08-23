"""Deterministic, renderer-neutral operations for staged Agent data views."""

from __future__ import annotations

import math
import statistics
from datetime import date, datetime
from typing import Any, cast

from plotagent.contracts.agent_data import (
    AggregateMetric,
    AggregateOperation,
    ConcatenateOperation,
    ConvertTypeOperation,
    ConvertUnitOperation,
    DataFilterPredicate,
    DataScalar,
    DataViewOperation,
    DeduplicateRowsOperation,
    DeriveColumnOperation,
    FilterRowsOperation,
    KeyedJoinOperation,
    RenameFieldOperation,
    ReshapeLongToWideOperation,
    ReshapeWideToLongOperation,
    SelectFieldsOperation,
    SortRowsOperation,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import EngineColumn, EngineDataView, EngineField, EngineScalar
from plotagent.units import convert_value, resolve_unit


class DataWorkspaceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def data_payload_hash(view: EngineDataView) -> str:
    return canonical_hash(
        cast(
            Any,
            {
                "row_ids": view.row_ids,
                "columns": tuple(column.model_dump(mode="json") for column in view.columns),
            },
        )
    )


def apply_data_view_operation(
    operation: DataViewOperation,
    views: tuple[EngineDataView, ...],
) -> EngineDataView:
    """Apply one closed operation to the exact immutable inputs named by the contract."""

    if isinstance(operation, ConcatenateOperation):
        _expect_inputs(views, len(operation.input_handle_ids))
        return _concatenate(views, operation)
    if isinstance(operation, KeyedJoinOperation):
        _expect_inputs(views, 2)
        return _join(views[0], views[1], operation)
    _expect_inputs(views, 1)
    view = views[0]
    if isinstance(operation, SelectFieldsOperation):
        return _select(view, operation)
    if isinstance(operation, RenameFieldOperation):
        return _rename(view, operation)
    if isinstance(operation, ConvertTypeOperation):
        return _convert_type(view, operation)
    if isinstance(operation, FilterRowsOperation):
        return _filter(view, operation)
    if isinstance(operation, SortRowsOperation):
        return _sort(view, operation)
    if isinstance(operation, DeduplicateRowsOperation):
        return _deduplicate(view, operation)
    if isinstance(operation, DeriveColumnOperation):
        return _derive(view, operation)
    if isinstance(operation, ConvertUnitOperation):
        return _convert_unit(view, operation)
    if isinstance(operation, ReshapeWideToLongOperation):
        return _wide_to_long(view, operation)
    if isinstance(operation, ReshapeLongToWideOperation):
        return _long_to_wide(view, operation)
    if isinstance(operation, AggregateOperation):
        return _aggregate(view, operation)
    raise DataWorkspaceError("DATA_OPERATION_UNSUPPORTED", "The data operation is unsupported.")


def _expect_inputs(views: tuple[EngineDataView, ...], expected: int) -> None:
    if len(views) != expected:
        raise DataWorkspaceError(
            "DATA_HANDLE_INPUT_MISMATCH",
            "The operation did not receive its declared immutable inputs.",
        )


def _columns(view: EngineDataView) -> dict[str, EngineColumn]:
    return {column.field.field_id: column for column in view.columns}


def _require_columns(view: EngineDataView, field_ids: tuple[str, ...]) -> tuple[EngineColumn, ...]:
    by_id = _columns(view)
    try:
        return tuple(by_id[field_id] for field_id in field_ids)
    except KeyError as error:
        raise DataWorkspaceError(
            "DATA_FIELD_NOT_FOUND",
            "A requested field is not present in the staged data view.",
        ) from error


def _ensure_output_field_available(view: EngineDataView, field_id: str) -> None:
    if field_id in _columns(view):
        raise DataWorkspaceError(
            "DATA_OUTPUT_FIELD_CONFLICT",
            "A derived output field already exists in the staged data view.",
        )


def _take(view: EngineDataView, indices: tuple[int, ...]) -> EngineDataView:
    if not indices:
        raise DataWorkspaceError(
            "DATA_EMPTY_RESULT",
            "The data operation produced no rows.",
        )
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


def _select(view: EngineDataView, operation: SelectFieldsOperation) -> EngineDataView:
    return view.model_copy(update={"columns": _require_columns(view, operation.field_ids)})


def _rename(view: EngineDataView, operation: RenameFieldOperation) -> EngineDataView:
    _require_columns(view, (operation.field_id,))
    return view.model_copy(
        update={
            "columns": tuple(
                column.model_copy(
                    update={
                        "field": column.field.model_copy(update={"name": operation.output_name})
                    }
                )
                if column.field.field_id == operation.field_id
                else column
                for column in view.columns
            )
        }
    )


def _convert_type(view: EngineDataView, operation: ConvertTypeOperation) -> EngineDataView:
    _ensure_output_field_available(view, operation.output_field_id)
    source = _require_columns(view, (operation.field_id,))[0]
    values = tuple(_converted_value(value, operation) for value in source.values)
    derived = EngineColumn(
        field=EngineField(
            field_id=operation.output_field_id,
            name=operation.output_name,
            logical_type=operation.target_type,
            unit_label=source.field.unit_label if operation.target_type == "numeric" else None,
        ),
        values=values,
    )
    return view.model_copy(update={"columns": (*view.columns, derived)})


def _converted_value(value: EngineScalar, operation: ConvertTypeOperation) -> EngineScalar:
    if _is_missing(value):
        return None
    if operation.target_type == "numeric":
        if isinstance(value, bool):
            raise _conversion_error()
        if isinstance(value, (int, float)):
            result = float(value)
        elif isinstance(value, str):
            text = value.strip()
            if operation.thousands_separator:
                text = text.replace(operation.thousands_separator, "")
            if operation.decimal_separator == ",":
                text = text.replace(",", ".")
            try:
                result = float(text)
            except ValueError as error:
                raise _conversion_error() from error
        else:
            raise _conversion_error()
        if not math.isfinite(result):
            raise _conversion_error()
        return result
    if operation.target_type == "datetime":
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if not isinstance(value, str) or operation.datetime_format is None:
            raise _conversion_error()
        try:
            return datetime.strptime(value.strip(), operation.datetime_format)
        except ValueError as error:
            raise _conversion_error() from error
    if operation.target_type == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value)
        normalized = text if operation.case_sensitive else text.casefold()
        true_values = {
            item if operation.case_sensitive else item.casefold() for item in operation.true_values
        }
        false_values = {
            item if operation.case_sensitive else item.casefold() for item in operation.false_values
        }
        if normalized in true_values:
            return True
        if normalized in false_values:
            return False
        raise _conversion_error()
    return str(value)


def _conversion_error() -> DataWorkspaceError:
    return DataWorkspaceError(
        "DATA_TYPE_CONVERSION_FAILED",
        "At least one non-missing value cannot be converted using the explicit options.",
    )


def _filter(view: EngineDataView, operation: FilterRowsOperation) -> EngineDataView:
    columns = _columns(view)
    try:
        masks = tuple(
            tuple(_matches(value, predicate) for value in columns[predicate.field_id].values)
            for predicate in operation.predicates
        )
    except KeyError as error:
        raise DataWorkspaceError(
            "DATA_FIELD_NOT_FOUND",
            "A filter field is not present in the staged data view.",
        ) from error
    keep = tuple(
        (all(values) if operation.combine == "all" else any(values))
        for values in zip(*masks, strict=True)
    )
    return _take(view, tuple(index for index, included in enumerate(keep) if included))


def _matches(value: EngineScalar, predicate: DataFilterPredicate) -> bool:
    if predicate.operator == "is_missing":
        return _is_missing(value)
    if predicate.operator == "is_not_missing":
        return not _is_missing(value)
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
    if _is_missing(value) or target is None or isinstance(target, tuple):
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


def _sort(view: EngineDataView, operation: SortRowsOperation) -> EngineDataView:
    columns = _columns(view)
    indices = list(range(len(view.row_ids)))
    for key in reversed(operation.keys):
        if key.field_id not in columns:
            raise DataWorkspaceError(
                "DATA_FIELD_NOT_FOUND",
                "A sort field is not present in the staged data view.",
            )
        values = columns[key.field_id].values
        present = [index for index in indices if not _is_missing(values[index])]
        absent = [index for index in indices if _is_missing(values[index])]
        try:
            present.sort(
                key=lambda index: cast(Any, values[index]),
                reverse=key.direction == "descending",
            )
        except TypeError as error:
            raise DataWorkspaceError(
                "DATA_SORT_TYPE_INVALID",
                "A sort field contains incomparable mixed values.",
            ) from error
        indices = absent + present if key.missing == "first" else present + absent
    return _take(view, tuple(indices))


def _deduplicate(
    view: EngineDataView,
    operation: DeduplicateRowsOperation,
) -> EngineDataView:
    keys = _require_columns(view, operation.key_field_ids)
    selected: dict[tuple[object, ...], int] = {}
    order = range(len(view.row_ids))
    for index in order:
        key = tuple(_hashable_value(column.values[index]) for column in keys)
        if key not in selected or operation.keep == "last":
            selected[key] = index
    indices = tuple(sorted(selected.values()))
    return _take(view, indices)


def _derive(view: EngineDataView, operation: DeriveColumnOperation) -> EngineDataView:
    _ensure_output_field_available(view, operation.output_field_id)
    inputs = _require_columns(view, operation.input_field_ids)
    if any(column.field.logical_type != "numeric" for column in inputs):
        raise DataWorkspaceError(
            "DATA_DERIVE_TYPE_INVALID",
            "Derived arithmetic accepts only numeric fields.",
        )
    units = tuple(column.field.unit_label or "" for column in inputs)
    if operation.operator in {"add", "subtract"} and len(set(units)) != 1:
        raise DataWorkspaceError(
            "DATA_UNIT_INCOMPATIBLE",
            "Fields used in addition or subtraction must share one unit.",
        )
    if operation.operator in {"log10", "ln", "sqrt"} and units[0]:
        raise DataWorkspaceError(
            "DATA_UNIT_INCOMPATIBLE",
            "This mathematical operator requires a dimensionless field.",
        )
    if len(inputs) == 2 and operation.operator in {"multiply", "divide"} and any(units):
        raise DataWorkspaceError(
            "DATA_DERIVED_DIMENSION_UNSUPPORTED",
            "Multiplication or division of dimensional fields is not registered.",
        )
    values: list[EngineScalar] = []
    for index in range(len(view.row_ids)):
        operands = tuple(column.values[index] for column in inputs)
        if any(_is_missing(value) for value in operands):
            values.append(None)
            continue
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) for value in operands
        ):
            raise DataWorkspaceError(
                "DATA_DERIVE_TYPE_INVALID",
                "Derived arithmetic encountered a non-numeric value.",
            )
        numeric = tuple(float(cast(int | float, value)) for value in operands)
        right = numeric[1] if len(numeric) == 2 else operation.scalar
        try:
            if operation.operator == "add":
                result = numeric[0] + cast(float, right)
            elif operation.operator == "subtract":
                result = numeric[0] - cast(float, right)
            elif operation.operator == "multiply":
                result = numeric[0] * cast(float, right)
            elif operation.operator == "divide":
                result = numeric[0] / cast(float, right)
            elif operation.operator == "absolute":
                result = abs(numeric[0])
            elif operation.operator == "negate":
                result = -numeric[0]
            elif operation.operator == "log10":
                result = math.log10(numeric[0])
            elif operation.operator == "ln":
                result = math.log(numeric[0])
            else:
                result = math.sqrt(numeric[0])
        except (ValueError, ZeroDivisionError) as error:
            raise DataWorkspaceError(
                "DATA_DERIVE_DOMAIN_INVALID",
                "Derived arithmetic encountered an invalid mathematical domain.",
            ) from error
        if not math.isfinite(result):
            raise DataWorkspaceError(
                "DATA_DERIVE_NONFINITE",
                "Derived arithmetic produced a non-finite value.",
            )
        values.append(result)
    derived = EngineColumn(
        field=EngineField(
            field_id=operation.output_field_id,
            name=operation.output_name,
            logical_type="numeric",
            unit_label=(
                None
                if operation.operator in {"log10", "ln", "sqrt"}
                else inputs[0].field.unit_label
            ),
        ),
        values=tuple(values),
    )
    return view.model_copy(update={"columns": (*view.columns, derived)})


def _convert_unit(view: EngineDataView, operation: ConvertUnitOperation) -> EngineDataView:
    _ensure_output_field_available(view, operation.output_field_id)
    source = _require_columns(view, (operation.field_id,))[0]
    if source.field.logical_type != "numeric":
        raise DataWorkspaceError(
            "DATA_UNIT_TYPE_INVALID",
            "Unit conversion accepts only numeric fields.",
        )
    source_unit = source.field.unit_label or ""
    source_definition = resolve_unit(source_unit)
    target_definition = resolve_unit(operation.target_unit)
    if source_definition is None or target_definition is None:
        raise DataWorkspaceError(
            "DATA_UNIT_UNKNOWN",
            "The source or target unit is not registered.",
        )
    if source_definition.dimensionality != target_definition.dimensionality:
        raise DataWorkspaceError(
            "DATA_UNIT_INCOMPATIBLE",
            "The source and target units have different dimensionality.",
        )
    converted: list[EngineScalar] = []
    for value in source.values:
        if _is_missing(value):
            converted.append(None)
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DataWorkspaceError(
                "DATA_UNIT_TYPE_INVALID",
                "Unit conversion encountered a non-numeric value.",
            )
        else:
            converted.append(convert_value(float(value), source_unit, operation.target_unit))
    derived = EngineColumn(
        field=EngineField(
            field_id=operation.output_field_id,
            name=operation.output_name,
            logical_type="numeric",
            unit_label=target_definition.symbol,
        ),
        values=tuple(converted),
    )
    return view.model_copy(update={"columns": (*view.columns, derived)})


def _wide_to_long(
    view: EngineDataView,
    operation: ReshapeWideToLongOperation,
) -> EngineDataView:
    _ensure_output_field_available(view, operation.output_name_field_id)
    _ensure_output_field_available(view, operation.output_value_field_id)
    ids = _require_columns(view, operation.id_field_ids)
    values = _require_columns(view, operation.value_field_ids)
    value_types = {(column.field.logical_type, column.field.unit_label or "") for column in values}
    if len(value_types) != 1:
        raise DataWorkspaceError(
            "DATA_RESHAPE_VALUE_MISMATCH",
            "Wide-to-long value fields must share type and unit.",
        )
    row_ids: list[str] = []
    id_values: list[list[EngineScalar]] = [[] for _ in ids]
    names: list[EngineScalar] = []
    output_values: list[EngineScalar] = []
    operation_digest = canonical_hash(operation.model_dump(mode="json"))[:12]
    for row_index in range(len(view.row_ids)):
        for value_index, value_column in enumerate(values, start=1):
            row_ids.append(f"row:long.{operation_digest}.{row_index + 1}.{value_index}")
            for position, id_column in enumerate(ids):
                id_values[position].append(id_column.values[row_index])
            names.append(value_column.field.name)
            output_values.append(value_column.values[row_index])
    value_type, value_unit = next(iter(value_types))
    return EngineDataView(
        data=view.data,
        row_ids=tuple(row_ids),
        columns=tuple(
            column.model_copy(update={"values": tuple(id_values[index])})
            for index, column in enumerate(ids)
        )
        + (
            EngineColumn(
                field=EngineField(
                    field_id=operation.output_name_field_id,
                    name=operation.output_name,
                    logical_type="categorical",
                ),
                values=tuple(names),
            ),
            EngineColumn(
                field=EngineField(
                    field_id=operation.output_value_field_id,
                    name=operation.output_value_name,
                    logical_type=value_type,
                    unit_label=value_unit or None,
                ),
                values=tuple(output_values),
            ),
        ),
    )


def _long_to_wide(
    view: EngineDataView,
    operation: ReshapeLongToWideOperation,
) -> EngineDataView:
    index_columns = _require_columns(view, operation.index_field_ids)
    name_column = _require_columns(view, (operation.name_field_id,))[0]
    value_column = _require_columns(view, (operation.value_field_id,))[0]
    existing = set(_columns(view))
    if any(output.field_id in existing for output in operation.outputs):
        raise DataWorkspaceError(
            "DATA_OUTPUT_FIELD_CONFLICT",
            "A long-to-wide output field already exists.",
        )
    keys: list[tuple[EngineScalar, ...]] = []
    seen_keys: set[tuple[object, ...]] = set()
    cells: dict[tuple[tuple[object, ...], str], EngineScalar] = {}
    expected = {output.value for output in operation.outputs}
    observed: set[str] = set()
    for row_index in range(len(view.row_ids)):
        key = tuple(column.values[row_index] for column in index_columns)
        hashable_key = tuple(_hashable_value(value) for value in key)
        name_value = name_column.values[row_index]
        if not isinstance(name_value, str):
            raise DataWorkspaceError(
                "DATA_RESHAPE_NAME_INVALID",
                "Long-to-wide names must be text values.",
            )
        observed.add(name_value)
        if hashable_key not in seen_keys:
            seen_keys.add(hashable_key)
            keys.append(key)
        cell = (hashable_key, name_value)
        if cell in cells:
            raise DataWorkspaceError(
                "DATA_RESHAPE_DUPLICATE",
                "Long-to-wide encountered duplicate keys; implicit aggregation is forbidden.",
            )
        cells[cell] = value_column.values[row_index]
    if observed != expected:
        raise DataWorkspaceError(
            "DATA_RESHAPE_OUTPUT_MISMATCH",
            "Observed long-to-wide names differ from the declared outputs.",
        )
    digest = canonical_hash(operation.model_dump(mode="json"))[:16]
    output_columns = tuple(
        column.model_copy(update={"values": tuple(key[index] for key in keys)})
        for index, column in enumerate(index_columns)
    )
    value_columns = tuple(
        EngineColumn(
            field=EngineField(
                field_id=output.field_id,
                name=output.name,
                logical_type=value_column.field.logical_type,
                unit_label=value_column.field.unit_label,
            ),
            values=tuple(
                cells.get((tuple(_hashable_value(value) for value in key), output.value))
                for key in keys
            ),
        )
        for output in operation.outputs
    )
    return EngineDataView(
        data=view.data,
        row_ids=tuple(f"row:wide.{digest}.{index + 1}" for index in range(len(keys))),
        columns=output_columns + value_columns,
    )


def _concatenate(
    views: tuple[EngineDataView, ...],
    operation: ConcatenateOperation,
) -> EngineDataView:
    baseline = views[0]
    _ensure_output_field_available(baseline, operation.source_label_field_id)
    signature = tuple(
        (column.field.name, column.field.logical_type, column.field.unit_label or "")
        for column in baseline.columns
    )
    if len(signature) != len(set(signature)):
        raise DataWorkspaceError(
            "DATA_NON_ISOMORPHIC",
            "Concatenated data must have unique field name, type and unit signatures.",
        )
    aligned: list[tuple[EngineColumn, ...]] = []
    for view in views:
        by_signature = {
            (column.field.name, column.field.logical_type, column.field.unit_label or ""): column
            for column in view.columns
        }
        if len(by_signature) != len(view.columns) or set(by_signature) != set(signature):
            raise DataWorkspaceError(
                "DATA_NON_ISOMORPHIC",
                "Concatenated data must have matching field names, types and units.",
            )
        aligned.append(tuple(by_signature[item] for item in signature))
    digest = canonical_hash(operation.model_dump(mode="json"))[:12]
    row_ids: list[str] = []
    output_values: list[list[EngineScalar]] = [[] for _ in baseline.columns]
    labels: list[EngineScalar] = []
    for source_index, (label, view, columns) in enumerate(
        zip(operation.source_labels, views, aligned, strict=True),
        start=1,
    ):
        for row_index in range(len(view.row_ids)):
            row_ids.append(f"row:concat.{digest}.{source_index}.{row_index + 1}")
            labels.append(label)
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
                    field_id=operation.source_label_field_id,
                    name=operation.source_label_name,
                    logical_type="categorical",
                ),
                values=tuple(labels),
            ),
        ),
    )


def _join(
    left: EngineDataView,
    right: EngineDataView,
    operation: KeyedJoinOperation,
) -> EngineDataView:
    left_keys = _require_columns(
        left,
        tuple(key.left_field_id for key in operation.keys),
    )
    right_keys = _require_columns(
        right,
        tuple(key.right_field_id for key in operation.keys),
    )
    if any(
        _is_missing(value)
        for column in (*left_keys, *right_keys)
        for value in column.values
    ):
        raise DataWorkspaceError(
            "DATA_JOIN_KEY_MISSING",
            "Join-key fields cannot contain missing values; filter or repair them explicitly.",
        )
    left_index = _key_index(left_keys, len(left.row_ids))
    right_index = _key_index(right_keys, len(right.row_ids))
    left_unique = all(len(indices) == 1 for indices in left_index.values())
    right_unique = all(len(indices) == 1 for indices in right_index.values())
    expected = operation.expected_relationship
    relationship_valid = {
        "one_to_one": left_unique and right_unique,
        "one_to_many": left_unique,
        "many_to_one": right_unique,
    }[expected]
    if not relationship_valid:
        raise DataWorkspaceError(
            "DATA_JOIN_RELATIONSHIP_MISMATCH",
            "Observed join-key cardinality differs from the declared relationship.",
        )
    pairs: list[tuple[int | None, int | None]] = []
    if operation.how in {"inner", "left"}:
        for left_row in range(len(left.row_ids)):
            key = _row_key(left_keys, left_row)
            matches = right_index.get(key, ())
            if matches:
                pairs.extend((left_row, right_row) for right_row in matches)
            elif operation.how == "left":
                pairs.append((left_row, None))
    else:
        for right_row in range(len(right.row_ids)):
            key = _row_key(right_keys, right_row)
            matches = left_index.get(key, ())
            if matches:
                pairs.extend((left_row, right_row) for left_row in matches)
            else:
                pairs.append((None, right_row))
    if not pairs:
        raise DataWorkspaceError("DATA_EMPTY_RESULT", "The keyed join produced no rows.")
    right_key_ids = {key.right_field_id for key in operation.keys}
    right_outputs = tuple(
        column for column in right.columns if column.field.field_id not in right_key_ids
    )
    output_ids = tuple(
        _joined_field_id(operation.right_field_prefix, column) for column in right_outputs
    )
    if set(output_ids) & set(_columns(left)) or len(output_ids) != len(set(output_ids)):
        raise DataWorkspaceError(
            "DATA_OUTPUT_FIELD_CONFLICT",
            "Joined right-side fields cannot be assigned unique output identities.",
        )
    right_key_by_left = {
        key.left_field_id: right_keys[index] for index, key in enumerate(operation.keys)
    }
    digest = canonical_hash(operation.model_dump(mode="json"))[:16]
    left_columns = tuple(
        column.model_copy(
            update={
                "values": tuple(
                    column.values[left_row]
                    if left_row is not None
                    else right_key_by_left[column.field.field_id].values[cast(int, right_row)]
                    if column.field.field_id in right_key_by_left
                    else None
                    for left_row, right_row in pairs
                )
            }
        )
        for column in left.columns
    )
    joined_columns = tuple(
        EngineColumn(
            field=EngineField(
                field_id=field_id,
                name=f"{operation.right_field_prefix}.{column.field.name}",
                logical_type=column.field.logical_type,
                unit_label=column.field.unit_label,
            ),
            values=tuple(
                column.values[right_row] if right_row is not None else None
                for _left_row, right_row in pairs
            ),
        )
        for field_id, column in zip(output_ids, right_outputs, strict=True)
    )
    return EngineDataView(
        data=left.data,
        row_ids=tuple(f"row:join.{digest}.{index + 1}" for index in range(len(pairs))),
        columns=left_columns + joined_columns,
    )


def _aggregate(view: EngineDataView, operation: AggregateOperation) -> EngineDataView:
    groups = _require_columns(view, operation.group_field_ids)
    by_id = _columns(view)
    for metric in operation.metrics:
        if metric.output_field_id in by_id:
            raise DataWorkspaceError(
                "DATA_OUTPUT_FIELD_CONFLICT",
                "An aggregate output field already exists.",
            )
        if metric.input_field_id is not None and metric.input_field_id not in by_id:
            raise DataWorkspaceError(
                "DATA_FIELD_NOT_FOUND",
                "An aggregate input field is not present.",
            )
    grouped: dict[tuple[object, ...], tuple[tuple[EngineScalar, ...], list[int]]] = {}
    for index in range(len(view.row_ids)):
        display_key = tuple(column.values[index] for column in groups)
        hashable_key = tuple(_hashable_value(value) for value in display_key)
        if hashable_key not in grouped:
            grouped[hashable_key] = (display_key, [])
        grouped[hashable_key][1].append(index)
    if not grouped:
        raise DataWorkspaceError("DATA_EMPTY_RESULT", "The aggregate produced no groups.")
    ordered = tuple(grouped.values())
    digest = canonical_hash(operation.model_dump(mode="json"))[:16]
    group_columns = tuple(
        column.model_copy(
            update={"values": tuple(display_key[position] for display_key, _rows in ordered)}
        )
        for position, column in enumerate(groups)
    )
    metric_columns = tuple(
        EngineColumn(
            field=EngineField(
                field_id=metric.output_field_id,
                name=metric.output_name,
                logical_type="numeric",
                unit_label=_aggregate_unit(metric, by_id),
            ),
            values=tuple(_metric_value(metric, by_id, rows) for _key, rows in ordered),
        )
        for metric in operation.metrics
    )
    return EngineDataView(
        data=view.data,
        row_ids=tuple(f"row:aggregate.{digest}.{index + 1}" for index in range(len(ordered))),
        columns=group_columns + metric_columns,
    )


def _aggregate_unit(metric: AggregateMetric, columns: dict[str, EngineColumn]) -> str | None:
    if metric.operator in {"count", "count_nonmissing"}:
        return None
    assert metric.input_field_id is not None
    return columns[metric.input_field_id].field.unit_label


def _metric_value(
    metric: AggregateMetric,
    columns: dict[str, EngineColumn],
    rows: list[int],
) -> int | float | None:
    if metric.operator == "count":
        return len(rows)
    assert metric.input_field_id is not None
    values = tuple(columns[metric.input_field_id].values[index] for index in rows)
    present = tuple(value for value in values if not _is_missing(value))
    if metric.operator == "count_nonmissing":
        return len(present)
    if not present:
        return None
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in present):
        raise DataWorkspaceError(
            "DATA_AGGREGATE_TYPE_INVALID",
            "This aggregate metric accepts only numeric values.",
        )
    numeric = tuple(float(cast(int | float, value)) for value in present)
    if metric.operator == "sum":
        return sum(numeric)
    if metric.operator == "mean":
        return statistics.fmean(numeric)
    if metric.operator == "min":
        return min(numeric)
    if metric.operator == "max":
        return max(numeric)
    return statistics.median(numeric)


def _key_index(
    columns: tuple[EngineColumn, ...],
    row_count: int,
) -> dict[tuple[object, ...], tuple[int, ...]]:
    mutable: dict[tuple[object, ...], list[int]] = {}
    for index in range(row_count):
        mutable.setdefault(_row_key(columns, index), []).append(index)
    return {key: tuple(indices) for key, indices in mutable.items()}


def _row_key(columns: tuple[EngineColumn, ...], index: int) -> tuple[object, ...]:
    return tuple(_hashable_value(column.values[index]) for column in columns)


def _joined_field_id(prefix: str, column: EngineColumn) -> str:
    digest = canonical_hash(cast(Any, (prefix, column.field.field_id)))[:20]
    return f"field:{prefix}_{digest}"


def _hashable_value(value: EngineScalar) -> object:
    if _is_missing(value):
        return ("missing",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    if isinstance(value, datetime):
        return ("datetime", value.isoformat())
    if isinstance(value, date):
        return ("date", value.isoformat())
    return ("string", cast(DataScalar, value))


def _is_missing(value: EngineScalar) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))

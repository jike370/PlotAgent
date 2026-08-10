"""Profile-level data normalization shared by independent backends.

This module contains no drawing or backend-native object model.  It only
turns an ``EngineDataView`` into the semantic data shape promised by a public
engine profile so independent renderers cannot disagree about row/column
ordering or duplicate-cell handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, nan
from typing import Literal

from .contracts import EngineColumn, EngineDataView, PlotDocument


@dataclass(frozen=True, slots=True)
class K20Grid:
    row_labels: tuple[str, ...]
    column_labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]
    row_field_name: str
    column_field_name: str
    value_field_name: str
    value_unit: str | None


@dataclass(frozen=True, slots=True)
class X23SeriesData:
    x_values: tuple[str | float, ...]
    x_labels: tuple[str, ...] | None
    left_values: tuple[float, ...]
    right_values: tuple[float, ...]
    x_field_name: str
    left_field_name: str
    right_field_name: str
    x_scale: Literal["categorical", "linear"]


def k20_grid(document: PlotDocument, data: EngineDataView) -> K20Grid:
    """Materialize a deterministic K20 grid from one immutable long table.

    First appearance defines category order.  Duplicate cells are rejected
    rather than silently averaged.  Missing row/column combinations remain
    NaN so both backends distinguish missing values from numeric zero.
    """

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        row = columns[bindings["row"]]
        column = columns[bindings["column"]]
        value = columns[bindings["value"]]
    except KeyError as error:
        raise ValueError("K20 requires row, column and value bindings") from error

    row_labels = _ordered_labels(row, "row")
    column_labels = _ordered_labels(column, "column")
    row_index = {label: index for index, label in enumerate(row_labels)}
    column_index = {label: index for index, label in enumerate(column_labels)}
    matrix = [[nan for _ in column_labels] for _ in row_labels]
    occupied: set[tuple[int, int]] = set()
    for row_value, column_value, cell_value in zip(
        row.values,
        column.values,
        value.values,
        strict=True,
    ):
        row_label = _label(row_value, "row")
        column_label = _label(column_value, "column")
        position = (row_index[row_label], column_index[column_label])
        if position in occupied:
            raise ValueError(
                f"K20 contains a duplicate matrix cell: {row_label!r}, {column_label!r}"
            )
        occupied.add(position)
        matrix[position[0]][position[1]] = _numeric(cell_value)
    return K20Grid(
        row_labels=row_labels,
        column_labels=column_labels,
        values=tuple(tuple(row_values) for row_values in matrix),
        row_field_name=row.field.name,
        column_field_name=column.field.name,
        value_field_name=value.field.name,
        value_unit=value.field.unit_label,
    )


def x23_series(document: PlotDocument, data: EngineDataView) -> X23SeriesData:
    """Validate and normalize one dual-Y input without describing either backend."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        x = columns[bindings["x"]]
        left = columns[bindings["left"]]
        right = columns[bindings["right"]]
    except KeyError as error:
        raise ValueError("X23 requires x, left and right bindings") from error
    left_values = tuple(_numeric(value) for value in left.values)
    right_values = tuple(_numeric(value) for value in right.values)
    x_scale: Literal["categorical", "linear"]
    if x.field.logical_type in {"categorical", "text"}:
        labels = tuple(_label(value, "x") for value in x.values)
        if len(labels) != len(set(labels)):
            raise ValueError("X23 categorical x labels must be unique")
        x_values: tuple[str | float, ...] = labels
        x_scale = "categorical"
    elif x.field.logical_type == "numeric":
        labels = None
        numeric_x = tuple(_numeric(value) for value in x.values)
        if any(not isfinite(value) for value in numeric_x):
            raise ValueError("X23 x values must be finite")
        x_values = numeric_x
        x_scale = "linear"
    else:
        raise ValueError("X23 currently supports categorical or numeric x data")
    return X23SeriesData(
        x_values=x_values,
        x_labels=labels,
        left_values=left_values,
        right_values=right_values,
        x_field_name=x.field.name,
        left_field_name=left.field.name,
        right_field_name=right.field.name,
        x_scale=x_scale,
    )


def _ordered_labels(column: EngineColumn, role: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_label(value, role) for value in column.values))


def _label(value: object, role: str) -> str:
    if value is None:
        raise ValueError(f"K20 {role} categories cannot be missing")
    label = str(value).strip()
    if not label:
        raise ValueError(f"K20 {role} categories cannot be empty")
    return label


def _numeric(value: object) -> float:
    if value is None:
        return nan
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("K20 value data must be numeric")
    return float(value)

"""Immutable table bindings consumed by the W4 resolver and adapters."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import TypeGuard, cast

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.rendering import ResolvedLayer, ResolvedRenderPlan

type Scalar = str | int | float | bool | None
_FIELD_ID = re.compile(r"^field:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _normalized_scalar(value: object) -> Scalar:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).isoformat()
    raise TypeError(f"unsupported render-table scalar {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class RenderTable:
    """A small immutable view over persisted or resolver-produced plot data."""

    columns: Mapping[str, tuple[Scalar, ...]]
    object_hash: str
    row_count: int

    @classmethod
    def from_columns(cls, columns: Mapping[str, Sequence[object]]) -> RenderTable:
        if not columns:
            raise ValueError("a render table must contain at least one field")
        normalized: dict[str, tuple[Scalar, ...]] = {}
        row_count: int | None = None
        for field_id, values in columns.items():
            if not _FIELD_ID.fullmatch(field_id):
                raise ValueError(f"invalid field id {field_id!r}")
            column = tuple(_normalized_scalar(value) for value in values)
            if row_count is None:
                row_count = len(column)
            elif len(column) != row_count:
                raise ValueError("all render-table columns must have equal length")
            normalized[field_id] = column
        assert row_count is not None
        payload = {"columns": normalized, "row_count": row_count}
        return cls(
            columns=MappingProxyType(normalized),
            object_hash=canonical_hash(cast(JsonValue, payload)),
            row_count=row_count,
        )

    @property
    def field_ids(self) -> tuple[str, ...]:
        return tuple(self.columns)

    def column(self, field_id: str) -> tuple[Scalar, ...]:
        try:
            return self.columns[field_id]
        except KeyError as error:
            raise KeyError(
                f"field {field_id!r} is not present in table {self.object_hash}"
            ) from error

    def select(self, row_indices: Sequence[int]) -> RenderTable:
        selected = tuple(row_indices)
        if any(index < 0 or index >= self.row_count for index in selected):
            raise IndexError("render-table selection is outside the table")
        return RenderTable.from_columns(
            {
                field_id: tuple(values[index] for index in selected)
                for field_id, values in self.columns.items()
            }
        )


@dataclass(frozen=True, slots=True)
class RenderDataStore:
    """Lookup from immutable contract/content hashes to validated tables."""

    tables: Mapping[str, RenderTable]

    def __init__(self, tables: Mapping[str, RenderTable] | None = None) -> None:
        object.__setattr__(self, "tables", MappingProxyType(dict(tables or {})))

    def get(self, binding_hash: str) -> RenderTable:
        try:
            return self.tables[binding_hash]
        except KeyError as error:
            raise KeyError(f"no render data is bound for {binding_hash}") from error


@dataclass(frozen=True, slots=True)
class ResolvedPlot:
    """The single contract plan plus its immutable content-addressed tables."""

    plan: ResolvedRenderPlan
    tables: Mapping[str, RenderTable]
    render_plan_hash: str

    @classmethod
    def create(
        cls,
        plan: ResolvedRenderPlan,
        tables: Mapping[str, RenderTable],
    ) -> ResolvedPlot:
        frozen_tables = MappingProxyType(dict(tables))
        for layer in plan.layers:
            table = frozen_tables.get(layer.data_ref.object_hash)
            if table is None:
                raise ValueError(f"resolved layer {layer.layer_id} has no content table")
            if table.row_count != layer.data_ref.row_count:
                raise ValueError(f"resolved layer {layer.layer_id} row count does not match")
        return cls(
            plan=plan,
            tables=frozen_tables,
            render_plan_hash=canonical_hash(plan),
        )

    def table_for(self, layer: ResolvedLayer) -> RenderTable:
        return self.tables[layer.data_ref.object_hash]


def is_finite_number(value: Scalar) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

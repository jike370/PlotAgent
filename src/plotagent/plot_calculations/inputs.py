"""Immutable in-memory inputs for fixed plot calculations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class PlotCalculationInput:
    """Complete row-aligned columns and, optionally, a regular numeric matrix."""

    row_ids: Sequence[str]
    columns: Mapping[str, Sequence[object]]
    matrix: Sequence[Sequence[object]] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_ids", tuple(self.row_ids))
        object.__setattr__(
            self,
            "columns",
            MappingProxyType(
                {field_id: tuple(values) for field_id, values in self.columns.items()}
            ),
        )
        if self.matrix is not None:
            object.__setattr__(self, "matrix", tuple(tuple(row) for row in self.matrix))

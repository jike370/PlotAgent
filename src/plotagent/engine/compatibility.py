"""Mechanical SourceDataset-to-profile compatibility without semantic binding."""

from __future__ import annotations

import re
from typing import Literal

from plotagent.contracts.datasets import SourceDataset
from plotagent.engine.contracts import (
    EngineProfile,
    EngineProfileCompatibility,
    EngineRoleCompatibility,
)

LogicalType = Literal["numeric", "categorical", "datetime", "boolean", "text"]

_NUMERIC_ROLES = {
    "base_x",
    "base_y",
    "center",
    "color",
    "count",
    "end",
    "frequency",
    "left",
    "lower",
    "middle",
    "pvalue",
    "qvalue",
    "right",
    "size",
    "start",
    "upper",
    "value",
    "x_err_minus",
    "x_err_plus",
    "y",
    "y_err_minus",
    "y_err_plus",
    "z",
    "z_imaginary",
    "z_real",
}
_CATEGORICAL_ROLES = {
    "actual",
    "category",
    "column",
    "column_label",
    "component",
    "facet",
    "group",
    "label",
    "predicted",
    "row",
    "row_label",
}


def accepted_types_for_role(role: str) -> tuple[LogicalType, ...]:
    if role == "time":
        return ("datetime", "numeric")
    if role == "x":
        return ("numeric", "datetime", "categorical", "text")
    if role in _NUMERIC_ROLES or re.fullmatch(r"series_[1-9][0-9]*", role):
        return ("numeric",)
    if role in _CATEGORICAL_ROLES:
        return ("categorical", "text", "boolean")
    return ("numeric", "categorical", "datetime", "boolean", "text")


def _has_injective_assignment(
    requirements: tuple[tuple[str, tuple[LogicalType, ...]], ...],
    field_types: tuple[LogicalType, ...],
) -> bool:
    """Bipartite matching proves counts/types can work without exposing a mapping."""

    matched_roles: dict[int, int] = {}

    def assign(role_index: int, seen_fields: set[int]) -> bool:
        accepted = requirements[role_index][1]
        for field_index, logical_type in enumerate(field_types):
            if field_index in seen_fields or logical_type not in accepted:
                continue
            seen_fields.add(field_index)
            previous = matched_roles.get(field_index)
            if previous is None or assign(previous, seen_fields):
                matched_roles[field_index] = role_index
                return True
        return False

    return all(assign(index, set()) for index in range(len(requirements)))


def profile_compatibility(
    profile: EngineProfile,
    source: SourceDataset,
) -> EngineProfileCompatibility:
    field_types = tuple(field.logical_type for field in source.field_schema)
    requirements = tuple(
        (role, accepted_types_for_role(role)) for role in profile.required_roles
    )
    rows_available = source.data_ref.row_count > 0
    assignable = _has_injective_assignment(requirements, field_types)
    reason_codes: list[str] = []
    if not rows_available:
        reason_codes.append("DATASET_EMPTY")
    if not assignable:
        reason_codes.append("REQUIRED_ROLE_TYPES_UNAVAILABLE")
    return EngineProfileCompatibility(
        profile_id=profile.profile_id,
        status="compatible" if rows_available and assignable else "incompatible",
        row_count=source.data_ref.row_count,
        field_count=len(field_types),
        requirements=tuple(
            EngineRoleCompatibility(
                role=role,
                accepted_logical_types=accepted,
                candidate_count=sum(logical_type in accepted for logical_type in field_types),
            )
            for role, accepted in requirements
        ),
        reason_codes=tuple(reason_codes),
    )

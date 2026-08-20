"""Frozen data cases for the 34-profile release matrix.

The fixtures live at the renderer-neutral EngineDataView boundary.  They are
small enough to audit in source and are shared by Matplotlib, Origin and the
release-manifest verifier.  `minimal` is the smallest useful valid shape;
`representative` exercises the chart's characteristic structure; `edge_error`
keeps the same bindings but poisons one numeric role with text so every export
surface must reject the same input deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal

from plotagent.engine import (
    CreatePlot,
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
    FieldBinding,
    PlotDocument,
)
from plotagent.engine.contracts import EngineScalar
from plotagent.engine.profiles import ENGINE_PROFILES

LogicalType = Literal["numeric", "categorical", "datetime", "boolean", "text"]


@dataclass(frozen=True, slots=True)
class ColumnCase:
    role: str
    name: str
    logical_type: LogicalType
    values: tuple[EngineScalar, ...]
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseCase:
    profile_id: str
    variant: Literal["minimal", "representative", "edge_error"]
    create: CreatePlot
    document: PlotDocument
    view: EngineDataView


def _n(*values: float | int | None) -> tuple[EngineScalar, ...]:
    return tuple(values)


def _c(*values: str | None) -> tuple[EngineScalar, ...]:
    return tuple(values)


def _column(
    role: str,
    name: str,
    logical_type: LogicalType,
    values: tuple[EngineScalar, ...],
    unit: str | None = None,
) -> ColumnCase:
    return ColumnCase(role, name, logical_type, values, unit)


def _xy(*, grouped: bool = False) -> tuple[tuple[ColumnCase, ...], tuple[ColumnCase, ...]]:
    minimal = (
        _column("x", "X", "numeric", _n(0, 1), "s"),
        _column("y", "Response", "numeric", _n(1.0, 2.0), "mV"),
    )
    representative: tuple[ColumnCase, ...] = (
        _column("x", "X", "numeric", _n(0, 1, 2, 3, 4, 5), "s"),
        _column("y", "Response", "numeric", _n(1.0, 2.2, 1.7, 3.4, 2.8, 4.1), "mV"),
    )
    if grouped:
        representative += (
            _column(
                "group",
                "Group",
                "categorical",
                _c("Control", "Control", "Control", "Treatment", "Treatment", "Treatment"),
            ),
        )
    return minimal, representative


def _profile_columns() -> dict[str, tuple[tuple[ColumnCase, ...], tuple[ColumnCase, ...]]]:
    base_time = datetime(2026, 1, 1)
    result: dict[str, tuple[tuple[ColumnCase, ...], tuple[ColumnCase, ...]]] = {}
    for profile_id in ("K01", "K02", "K03"):
        result[profile_id] = _xy(grouped=profile_id != "K01")

    result.update(
        {
            "K04": (
                (
                    _column("x", "X", "numeric", _n(0, 1)),
                    _column("y", "Y", "numeric", _n(1, 2)),
                ),
                (
                    _column("x", "X", "numeric", _n(0, 1, 2, 3, 4, 5)),
                    _column("y", "Y", "numeric", _n(1, 2.4, 1.8, 3.6, 3.0, 4.2)),
                    _column("size", "Bubble size", "numeric", _n(4, 9, 16, 25, 36, 49)),
                    _column("color", "Color value", "numeric", _n(0.05, 0.2, 0.4, 0.6, 0.8, 0.95)),
                ),
            ),
            "K06": (
                (
                    _column("x", "X", "numeric", _n(1, 2)),
                    _column("center", "Estimate", "numeric", _n(3, 5)),
                    _column("x_err_minus", "X error -", "numeric", _n(0.1, 0.2)),
                    _column("x_err_plus", "X error +", "numeric", _n(0.2, 0.3)),
                    _column("y_err_minus", "Y error -", "numeric", _n(0.3, 0.4)),
                    _column("y_err_plus", "Y error +", "numeric", _n(0.4, 0.5)),
                ),
                (
                    _column("x", "X", "numeric", _n(1, 2, 3, 4, 5)),
                    _column("center", "Estimate", "numeric", _n(3, 4.2, 5.4, 6.0, 7.1)),
                    _column("x_err_minus", "X error -", "numeric", _n(0.1, 0.1, 0.2, 0.2, 0.3)),
                    _column("x_err_plus", "X error +", "numeric", _n(0.2, 0.2, 0.3, 0.3, 0.4)),
                    _column("y_err_minus", "Y error -", "numeric", _n(0.3, 0.35, 0.4, 0.45, 0.5)),
                    _column("y_err_plus", "Y error +", "numeric", _n(0.4, 0.45, 0.5, 0.55, 0.6)),
                ),
            ),
            "K07": (
                (
                    _column("x", "X", "numeric", _n(1, 2)),
                    _column("center", "Mean", "numeric", _n(3, 4)),
                    _column("lower", "Lower", "numeric", _n(2.5, 3.4)),
                    _column("upper", "Upper", "numeric", _n(3.7, 4.8)),
                ),
                (
                    _column("x", "X", "numeric", _n(1, 2, 3, 4, 5, 6)),
                    _column("center", "Mean", "numeric", _n(3, 3.8, 4.5, 4.1, 5.2, 6.0)),
                    _column("lower", "Lower", "numeric", _n(2.4, 3.1, 3.7, 3.4, 4.4, 5.1)),
                    _column("upper", "Upper", "numeric", _n(3.8, 4.6, 5.4, 5.0, 6.1, 7.0)),
                ),
            ),
            "K08": (
                (
                    _column("category", "Category", "categorical", _c("A", "B")),
                    _column("value", "Value", "numeric", _n(1, 2)),
                ),
                (
                    _column(
                        "category",
                        "Category",
                        "categorical",
                        _c("Short", "A deliberately long category", "Zero", "Negative", "High"),
                    ),
                    _column("value", "Value", "numeric", _n(12, 18, 0, -4, 37)),
                ),
            ),
            "K09": (
                (
                    _column("category", "Category", "categorical", _c("A", "A", "B", "B")),
                    _column("group", "Group", "categorical", _c("G1", "G2", "G1", "G2")),
                    _column("value", "Value", "numeric", _n(1, 2, 3, 4)),
                ),
                (
                    _column(
                        "category",
                        "Category",
                        "categorical",
                        _c("A", "A", "A", "B", "B", "B", "C", "C", "C"),
                    ),
                    _column(
                        "group",
                        "Group",
                        "categorical",
                        _c(
                            "Control",
                            "Low",
                            "High",
                            "Control",
                            "Low",
                            "High",
                            "Control",
                            "Low",
                            "High",
                        ),
                    ),
                    _column("value", "Value", "numeric", _n(8, 10, 12, 11, 13, 15, 14, 16, 18)),
                ),
            ),
            "K10": (
                (
                    _column("category", "Category", "categorical", _c("A", "A", "B", "B")),
                    _column(
                        "component", "Component", "categorical", _c("One", "Two", "One", "Two")
                    ),
                    _column("value", "Value", "numeric", _n(1, 2, 3, 4)),
                ),
                (
                    _column(
                        "category",
                        "Category",
                        "categorical",
                        _c("Q1", "Q1", "Q1", "Q2", "Q2", "Q2", "Q3", "Q3", "Q3"),
                    ),
                    _column(
                        "component",
                        "Component",
                        "categorical",
                        _c(
                            "North",
                            "South",
                            "West",
                            "North",
                            "South",
                            "West",
                            "North",
                            "South",
                            "West",
                        ),
                    ),
                    _column("value", "Value", "numeric", _n(5, 7, 9, 6, 8, 10, 7, 9, 11)),
                ),
            ),
            "K11": (
                (
                    _column("category", "Category", "categorical", _c("A", "A", "B", "B")),
                    _column(
                        "component", "Component", "categorical", _c("One", "Two", "One", "Two")
                    ),
                    _column("value", "Value", "numeric", _n(1, 3, 2, 6)),
                ),
                (
                    _column(
                        "category",
                        "Category",
                        "categorical",
                        _c("A", "A", "A", "B", "B", "B", "C", "C", "C"),
                    ),
                    _column(
                        "component",
                        "Component",
                        "categorical",
                        _c(
                            "Type 1",
                            "Type 2",
                            "Type 3",
                            "Type 1",
                            "Type 2",
                            "Type 3",
                            "Type 1",
                            "Type 2",
                            "Type 3",
                        ),
                    ),
                    _column("value", "Value", "numeric", _n(10, 13, 16, 15, 18, 21, 20, 23, 26)),
                ),
            ),
        }
    )

    for profile_id in ("K12", "K13", "K14", "X05"):
        result[profile_id] = (
            (
                _column("value", "Value", "numeric", _n(1, 2, 3, 4)),
                _column("group", "Group", "categorical", _c("A", "A", "B", "B")),
            ),
            (
                _column(
                    "value",
                    "Value",
                    "numeric",
                    _n(4.9, 5.2, 4.7, 5.5, 7.1, 6.8, 7.4, 7.0, 9.2, 8.8, 9.5, 9.0),
                ),
                _column(
                    "group",
                    "Group",
                    "categorical",
                    _c("A", "A", "A", "A", "B", "B", "B", "B", "C", "C", "C", "C"),
                ),
            ),
        )

    result.update(
        {
            "K15": (
                (_column("value", "Measurement", "numeric", _n(1, 2, 2.5, 3)),),
                (
                    _column(
                        "value",
                        "Measurement",
                        "numeric",
                        _n(
                            2.1,
                            2.4,
                            2.8,
                            3.0,
                            3.2,
                            3.6,
                            3.9,
                            4.1,
                            4.3,
                            4.7,
                            5.0,
                            5.3,
                            5.8,
                            6.1,
                            6.4,
                        ),
                    ),
                ),
            ),
            "K18": (
                (
                    _column("x", "X", "numeric", _n(0, 1, 2)),
                    _column("series_1", "Series 1", "numeric", _n(1, 2, 1.5)),
                ),
                (
                    _column("x", "X", "numeric", _n(0, 1, 2, 3, 4, 5)),
                    _column("series_1", "Base", "numeric", _n(1, 2, 1.5, 2.5, 2.0, 3.0)),
                    _column("series_2", "Top", "numeric", _n(2, 3.1, 2.7, 3.8, 3.4, 4.2)),
                ),
            ),
            "K19": (
                (
                    _column(
                        "time",
                        "Timestamp",
                        "datetime",
                        tuple(base_time + timedelta(days=i) for i in range(3)),
                    ),
                    _column("series_1", "Sensor A", "numeric", _n(20, 21, 19)),
                ),
                (
                    _column(
                        "time",
                        "Timestamp",
                        "datetime",
                        tuple(base_time + timedelta(hours=i * i + 3 * i) for i in range(8)),
                    ),
                    _column(
                        "series_1",
                        "Sensor A",
                        "numeric",
                        _n(20, 21.5, 22.9, 21.8, 23.2, 24.1, 23.7, 25.0),
                    ),
                    _column(
                        "series_2",
                        "Sensor B",
                        "numeric",
                        _n(18, 19.0, 20.2, 20.8, 21.1, 22.4, 23.0, 23.8),
                    ),
                ),
            ),
            "K20": (
                (
                    _column("row", "Row", "categorical", _c("R1", "R1", "R2", "R2")),
                    _column("column", "Column", "categorical", _c("C1", "C2", "C1", "C2")),
                    _column("value", "Value", "numeric", _n(0.1, 0.4, 0.7, 1.0)),
                ),
                (
                    _column(
                        "row",
                        "Row",
                        "categorical",
                        _c("R1", "R1", "R1", "R2", "R2", "R2", "R3", "R3", "R3"),
                    ),
                    _column(
                        "column",
                        "Column",
                        "categorical",
                        _c("C1", "C2", "C3", "C1", "C2", "C3", "C1", "C2", "C3"),
                    ),
                    _column(
                        "value", "Value", "numeric", _n(0.1, 0.5, 0.9, 0.3, 0.8, 0.2, 0.7, 0.4, 1.0)
                    ),
                ),
            ),
            "K21": (
                (
                    _column("row_label", "Row", "categorical", _c("A", "A", "B", "B")),
                    _column("column_label", "Column", "categorical", _c("A", "B", "A", "B")),
                    _column("value", "Correlation", "numeric", _n(1, 0.4, 0.4, 1)),
                ),
                (
                    _column(
                        "row_label",
                        "Row",
                        "categorical",
                        _c("A", "A", "A", "B", "B", "B", "C", "C", "C"),
                    ),
                    _column(
                        "column_label",
                        "Column",
                        "categorical",
                        _c("A", "B", "C", "A", "B", "C", "A", "B", "C"),
                    ),
                    _column(
                        "value",
                        "Correlation",
                        "numeric",
                        _n(1, 0.6, -0.2, 0.6, 1, 0.3, -0.2, 0.3, 1),
                    ),
                ),
            ),
            "K22": (
                (
                    _column("x", "Grid X", "numeric", _n(0, 1, 0, 1)),
                    _column("y", "Grid Y", "numeric", _n(0, 0, 1, 1)),
                    _column("z", "Z", "numeric", _n(0, 1, 1, 2)),
                ),
                (
                    _column("x", "Grid X", "numeric", _n(0, 1, 2, 0, 1, 2, 0, 1, 2)),
                    _column("y", "Grid Y", "numeric", _n(0, 0, 0, 1, 1, 1, 2, 2, 2)),
                    _column("z", "Z", "numeric", _n(0.0, 0.5, 1.0, -0.2, 0.8, 1.4, -0.5, 0.2, 1.1)),
                ),
            ),
            "K24": (
                (
                    _column("facet", "Facet", "categorical", _c("A", "A", "B", "B")),
                    _column("base_x", "X", "numeric", _n(0, 1, 0, 1)),
                    _column("base_y", "Y", "numeric", _n(1, 2, 2, 3)),
                ),
                (
                    _column(
                        "facet",
                        "Facet",
                        "categorical",
                        _c(
                            "Panel A",
                            "Panel A",
                            "Panel A",
                            "Panel B",
                            "Panel B",
                            "Panel B",
                            "Panel C",
                            "Panel C",
                            "Panel C",
                        ),
                    ),
                    _column("base_x", "X", "numeric", _n(0, 1, 2, 0, 1, 2, 0, 1, 2)),
                    _column("base_y", "Y", "numeric", _n(1, 2.2, 1.8, 2, 3.1, 2.7, 3, 3.8, 4.2)),
                ),
            ),
            "S34": (
                (
                    _column("z_real", "Z real", "numeric", _n(10, 12, 15)),
                    _column("z_imaginary", "-Z imaginary", "numeric", _n(0, 2, 0)),
                ),
                (
                    _column("z_real", "Z real", "numeric", _n(10, 10.8, 13, 17, 22, 28, 34, 40)),
                    _column(
                        "z_imaginary", "-Z imaginary", "numeric", _n(0, 4, 8, 11, 12, 10, 6, 0)
                    ),
                    _column(
                        "frequency",
                        "Frequency",
                        "numeric",
                        _n(100000, 50000, 20000, 10000, 5000, 2000, 1000, 500),
                    ),
                ),
            ),
            "S61": (
                (
                    _column("actual", "Actual", "categorical", _c("Cat", "Cat", "Dog", "Dog")),
                    _column(
                        "predicted", "Predicted", "categorical", _c("Cat", "Dog", "Cat", "Dog")
                    ),
                    _column("count", "Count", "numeric", _n(8, 1, 2, 7)),
                ),
                (
                    _column(
                        "actual",
                        "Actual",
                        "categorical",
                        _c("Cat", "Cat", "Cat", "Dog", "Dog", "Dog", "Bird", "Bird", "Bird"),
                    ),
                    _column(
                        "predicted",
                        "Predicted",
                        "categorical",
                        _c("Cat", "Dog", "Bird", "Cat", "Dog", "Bird", "Cat", "Dog", "Bird"),
                    ),
                    _column("count", "Count", "numeric", _n(42, 4, 5, 4, 38, 6, 5, 6, 34)),
                ),
            ),
            "X02": (
                (
                    _column("x", "X", "numeric", _n(0, 1)),
                    _column("y", "Y", "numeric", _n(1, 2)),
                ),
                (
                    _column("x", "X", "numeric", _n(0, 1, 2, 3, 4, 5)),
                    _column("y", "Y", "numeric", _n(1, 2.5, 1.8, 3.2, 2.9, 4.0)),
                    _column("label", "Label", "categorical", _c("A", "B", "C", "D", "E", "F")),
                ),
            ),
            "X03": (
                (
                    _column("category", "Category", "categorical", _c("A", "B")),
                    _column("series_1", "Series 1", "numeric", _n(1, 2)),
                    _column("series_2", "Series 2", "numeric", _n(2, 3)),
                ),
                (
                    _column("category", "Category", "categorical", _c("A", "B", "C", "D", "E")),
                    _column("series_1", "Series 1", "numeric", _n(5, 7, 9, 11, 13)),
                    _column("series_2", "Series 2", "numeric", _n(6, 8, 10, 12, 14)),
                    _column("series_3", "Series 3", "numeric", _n(4, 6, 8, 10, 12)),
                ),
            ),
            "X09": (
                (
                    _column("category", "Category", "categorical", _c("A", "B")),
                    _column("start", "Start", "numeric", _n(1, 2)),
                    _column("end", "End", "numeric", _n(3, 5)),
                ),
                (
                    _column(
                        "category",
                        "Category",
                        "categorical",
                        _c("A", "B", "C", "Long interval label"),
                    ),
                    _column("start", "Start", "numeric", _n(2, -3, 5, 1)),
                    _column("middle", "Middle", "numeric", _n(4, 2, 8, 7)),
                    _column("end", "End", "numeric", _n(7, 4, 11, 15)),
                ),
            ),
            "X13": (
                (
                    _column("category", "Age group", "categorical", _c("Young", "Old")),
                    _column("left", "Male", "numeric", _n(5, 4)),
                    _column("right", "Female", "numeric", _n(6, 5)),
                ),
                (
                    _column(
                        "category",
                        "Age group",
                        "categorical",
                        _c("0–9", "10–19", "20–29", "30–39", "40–49", "50+"),
                    ),
                    _column("left", "Male", "numeric", _n(520, 610, 700, 660, 580, 490)),
                    _column("right", "Female", "numeric", _n(500, 590, 720, 690, 610, 530)),
                ),
            ),
            "X23": (
                (
                    _column("x", "X", "numeric", _n(0, 1)),
                    _column("left", "Left Y", "numeric", _n(10, 12)),
                    _column("right", "Right Y", "numeric", _n(0.2, 0.3)),
                ),
                (
                    _column("x", "X", "numeric", _n(1, 2, 3, 4, 5, 6)),
                    _column("left", "Left Y", "numeric", _n(10, 12, 14, 16, 18, 20)),
                    _column("right", "Right Y", "numeric", _n(0.2, 0.23, 0.25, 0.27, 0.28, 0.26)),
                ),
            ),
            "X24": (
                (
                    _column("category", "Category", "categorical", _c("A", "B")),
                    _column("value", "Count", "numeric", _n(8, 2)),
                ),
                (
                    _column(
                        "category",
                        "Category",
                        "categorical",
                        _c("Defect A", "Defect B", "Defect C", "Defect D", "Other"),
                    ),
                    _column("value", "Count", "numeric", _n(42, 26, 18, 9, 5)),
                ),
            ),
            "X35": (
                (
                    _column("category", "Category", "categorical", _c("A", "B")),
                    _column("left", "Left Y", "numeric", _n(12, 18)),
                    _column("right", "Right Y", "numeric", _n(0.3, 0.55)),
                ),
                (
                    _column("category", "Category", "categorical", _c("A", "B", "C", "D")),
                    _column("left", "Left Y", "numeric", _n(12, 18, 9, 25)),
                    _column("right", "Right Y", "numeric", _n(0.3, 0.55, 0.2, 0.72)),
                ),
            ),
            "X36": (
                (
                    _column("category", "Category", "categorical", _c("A", "B")),
                    _column("left", "Bar value", "numeric", _n(12, 18)),
                    _column("right", "Line value", "numeric", _n(0.2, 0.35)),
                ),
                (
                    _column(
                        "category", "Category", "categorical", _c("Jan", "Feb", "Mar", "Apr", "May")
                    ),
                    _column("left", "Bar value", "numeric", _n(12, 18, 15, 24, 21)),
                    _column("right", "Line value", "numeric", _n(0.2, 0.35, 0.55, 0.7, 0.82)),
                ),
            ),
            "X38": (
                (
                    _column("x", "X", "numeric", _n(0, 1, 2)),
                    _column("series_1", "Trace 1", "numeric", _n(0, 1, 0)),
                ),
                (
                    _column("x", "X", "numeric", _n(1, 2, 3, 4, 5, 6, 7, 8)),
                    _column(
                        "series_1", "Trace 1", "numeric", _n(0, 0.3, 0.6, 0.8, 1.0, 0.9, 0.6, 0.2)
                    ),
                    _column(
                        "series_2", "Trace 2", "numeric", _n(2, 2.3, 2.6, 2.8, 3.0, 2.9, 2.6, 2.2)
                    ),
                    _column(
                        "series_3", "Trace 3", "numeric", _n(4, 4.3, 4.6, 4.8, 5.0, 4.9, 4.6, 4.2)
                    ),
                ),
            ),
            "X39": (
                (
                    _column("series_1", "Week 1", "numeric", _n(1, 2, 3)),
                    _column("series_2", "Week 2", "numeric", _n(2, 3, 4)),
                ),
                (
                    _column("series_1", "Week 1", "numeric", _n(1, 2, 3, 4, 5)),
                    _column("series_2", "Week 2", "numeric", _n(2, 3, 4, 5, 6)),
                    _column("series_3", "Week 3", "numeric", _n(3, 4, 5, 6, 7)),
                    _column("series_4", "Week 4", "numeric", _n(4, 5, 6, 7, 8)),
                ),
            ),
            "X40": (
                (
                    _column("label", "Subject", "categorical", _c("P01", "P02")),
                    _column("series_1", "Before", "numeric", _n(10, 12)),
                    _column("series_2", "After", "numeric", _n(11, 14)),
                ),
                (
                    _column(
                        "label",
                        "Subject",
                        "categorical",
                        _c("P01", "P02", "P03", "P04", "P05", "P06"),
                    ),
                    _column("series_1", "Before", "numeric", _n(10, 11, 12, 13, 14, 10)),
                    _column("series_2", "After", "numeric", _n(11, 12.5, 14, 14, 15.5, 12)),
                    _column(
                        "group",
                        "Group",
                        "categorical",
                        _c("Control", "Control", "Control", "Treatment", "Treatment", "Treatment"),
                    ),
                ),
            ),
        }
    )
    return result


def _release_case(profile_id: str, variant: str, columns: tuple[ColumnCase, ...]) -> ReleaseCase:
    payload = json.dumps(
        [(item.role, item.name, item.logical_type, item.values, item.unit) for item in columns],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    digest = sha256(payload).hexdigest()
    token = f"release-{profile_id.lower()}-{variant.replace('_', '-')}"
    data = EngineDataRef(
        kind="source", dataset_id=f"dataset.{token}", version=1, content_hash=digest
    )
    engine_columns = tuple(
        EngineColumn(
            field=EngineField(
                field_id=f"field:{token}-{item.role.replace('_', '-')}",
                name=item.name,
                logical_type=item.logical_type,
                unit_label=item.unit,
            ),
            values=item.values,
        )
        for item in columns
    )
    row_count = len(engine_columns[0].values)
    view = EngineDataView(
        data=data,
        row_ids=tuple(f"row:{token}-{index + 1}" for index in range(row_count)),
        columns=engine_columns,
    )
    bindings = tuple(
        FieldBinding(role=item.role, field_id=column.field.field_id)
        for item, column in zip(columns, engine_columns, strict=True)
    )
    create = CreatePlot(
        action_id=f"action:{token}-create",
        plot_id=f"plot:{token}",
        profile_id=profile_id,
        data=data,
        bindings=bindings,
    )
    document = PlotDocument(
        plot_id=create.plot_id,
        plot_version=1,
        profile_id=profile_id,
        data=data,
        bindings=bindings,
        applied_action_ids=(create.action_id,),
    )
    return ReleaseCase(profile_id, variant, create, document, view)  # type: ignore[arg-type]


def _edge_columns(
    profile_id: str, representative: tuple[ColumnCase, ...]
) -> tuple[ColumnCase, ...]:
    profile = next(item for item in ENGINE_PROFILES if str(item.profile_id) == profile_id)
    numeric_roles = {
        role for role, accepted in profile.role_field_types.items() if accepted == ("numeric",)
    }
    chosen = next(
        (index for index, item in enumerate(representative) if item.role in numeric_roles),
        None,
    )
    if chosen is None:
        raise RuntimeError(f"{profile_id} has no numeric role for the stable edge/error fixture")
    result = list(representative)
    source = result[chosen]
    result[chosen] = ColumnCase(
        role=source.role,
        name=source.name,
        logical_type="text",
        values=tuple("not-a-number" for _value in source.values),
        unit=source.unit,
    )
    return tuple(result)


def release_cases() -> tuple[ReleaseCase, ...]:
    columns = _profile_columns()
    public_ids = tuple(str(profile.profile_id) for profile in ENGINE_PROFILES)
    if set(columns) != set(public_ids):
        missing = sorted(set(public_ids) - set(columns))
        extra = sorted(set(columns) - set(public_ids))
        raise RuntimeError(
            f"release fixtures differ from public profiles: missing={missing}, extra={extra}"
        )
    result: list[ReleaseCase] = []
    for profile_id in public_ids:
        minimal, representative = columns[profile_id]
        result.extend(
            (
                _release_case(profile_id, "minimal", minimal),
                _release_case(profile_id, "representative", representative),
                _release_case(profile_id, "edge_error", _edge_columns(profile_id, representative)),
            )
        )
    return tuple(result)


RELEASE_CASES = release_cases()

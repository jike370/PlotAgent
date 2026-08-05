"""Compact geometry signatures shared by the 31 explicit chart entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from plotagent.contracts.base import ChartTypeId

SeriesDataKind = Literal["prepared", "calculated", "precomputed"]


@dataclass(frozen=True, slots=True)
class SeriesRule:
    resolved_geometry: str
    role_signatures: tuple[tuple[str, ...], ...]
    data_kinds: tuple[SeriesDataKind, ...]
    x_range_roles: tuple[str, ...]
    y_range_roles: tuple[str, ...]

    def roles_for_count(self, count: int) -> tuple[str, ...]:
        matches = tuple(signature for signature in self.role_signatures if len(signature) == count)
        if len(matches) != 1:
            expected = ", ".join(str(len(item)) for item in self.role_signatures)
            raise ValueError(f"expected one of [{expected}] role fields, received {count}")
        return matches[0]


def _rule(
    geometry: str,
    roles: tuple[str, ...] | tuple[tuple[str, ...], ...],
    data_kinds: tuple[SeriesDataKind, ...],
    x_roles: tuple[str, ...],
    y_roles: tuple[str, ...],
) -> SeriesRule:
    signatures = (roles,) if roles and isinstance(roles[0], str) else roles
    return SeriesRule(
        resolved_geometry=geometry,
        role_signatures=signatures,  # type: ignore[arg-type]
        data_kinds=data_kinds,
        x_range_roles=x_roles,
        y_range_roles=y_roles,
    )


_P: tuple[SeriesDataKind, ...] = ("prepared",)
_C: tuple[SeriesDataKind, ...] = ("calculated",)
_PC: tuple[SeriesDataKind, ...] = ("prepared", "calculated")
_U: tuple[SeriesDataKind, ...] = ("precomputed",)
_PU: tuple[SeriesDataKind, ...] = ("prepared", "precomputed")

XY = ("x", "y")
GROUPED_XY = (XY, ("x", "y", "group"))

SERIES_RULES: dict[tuple[ChartTypeId, str], SeriesRule] = {
    ("K01", "line"): _rule("xy.line", XY, _P, ("x",), ("y",)),
    ("K02", "line"): _rule("xy.line", XY, _P, ("x",), ("y",)),
    ("K02", "symbol"): _rule("xy.symbol", XY, _P, ("x",), ("y",)),
    ("K03", "symbol"): _rule("xy.symbol", GROUPED_XY, _P, ("x",), ("y",)),
    ("K04", "symbol"): _rule(
        "xy.bubble",
        (XY, ("x", "y", "size"), ("x", "y", "size", "color"), ("x", "y", "size", "color", "group")),
        _P,
        ("x",),
        ("y",),
    ),
    ("K05", "symbol"): _rule("xy.symbol", XY, _P, ("x",), ("y",)),
    ("K05", "line"): _rule("xy.line", XY, _U, ("x",), ("y",)),
    ("K05", "band"): _rule("xy.band", ("x", "lower", "upper"), _U, ("x",), ("lower", "upper")),
    ("K06", "symbol"): _rule("xy.symbol", ("x", "center"), _PC, ("x",), ("center",)),
    ("K06", "error_bar"): _rule(
        "xy.error",
        (("x", "center", "error"), ("x", "center", "lower", "upper")),
        _PC,
        ("x",),
        ("center", "lower", "upper", "error"),
    ),
    ("K07", "line"): _rule("xy.line", ("x", "center"), _PC, ("x",), ("center",)),
    ("K07", "band"): _rule("xy.band", ("x", "lower", "upper"), _PC, ("x",), ("lower", "upper")),
    ("K08", "bar"): _rule(
        "bar.single",
        (("category", "value"), ("category", "value", "lower", "upper")),
        _PC,
        ("category",),
        ("value", "lower", "upper"),
    ),
    ("K09", "bar"): _rule(
        "bar.grouped",
        (("category", "group", "value"), ("category", "group", "value", "lower", "upper")),
        _PC,
        ("category",),
        ("value", "lower", "upper"),
    ),
    ("K10", "bar"): _rule(
        "bar.stacked", ("category", "component", "value"), _P, ("category",), ("value",)
    ),
    ("K11", "bar"): _rule(
        "bar.percent", ("category", "component", "value"), _C, ("category",), ("value",)
    ),
    ("K12", "strip"): _rule(
        "distribution.strip", (("value",), ("value", "group")), _P, ("group",), ("value",)
    ),
    ("K13", "box"): _rule(
        "distribution.box",
        (
            ("q1", "median", "q3", "whisker_low", "whisker_high"),
            ("group", "q1", "median", "q3", "whisker_low", "whisker_high"),
        ),
        _C,
        ("group",),
        ("q1", "median", "q3", "whisker_low", "whisker_high"),
    ),
    ("K14", "violin"): _rule(
        "distribution.violin",
        (("grid", "density"), ("group", "grid", "density")),
        _C,
        ("group",),
        ("grid",),
    ),
    ("K15", "histogram"): _rule(
        "distribution.histogram", ("left", "right", "height"), _C, ("left", "right"), ("height",)
    ),
    ("K16", "density"): _rule(
        "distribution.density",
        (("grid", "density"), ("grid", "density", "group")),
        _C,
        ("grid",),
        ("density",),
    ),
    ("K17", "step"): _rule(
        "distribution.step",
        (("x", "probability"), ("x", "probability", "group")),
        _C,
        ("x",),
        ("probability",),
    ),
    ("K18", "area"): _rule("xy.area", XY, _P, ("x",), ("y",)),
    ("K19", "line"): _rule("xy.datetime_line", ("time", "value"), _P, ("time",), ("value",)),
    ("K20", "heatmap"): _rule(
        "matrix.heatmap", ("row", "column", "value"), _PC, ("column",), ("row",)
    ),
    ("K21", "heatmap"): _rule(
        "matrix.correlation",
        ("row_label", "column_label", "value"),
        _U,
        ("column_label",),
        ("row_label",),
    ),
    ("K22", "contour"): _rule("matrix.contour", ("x", "y", "z"), _U, ("x",), ("y",)),
    ("K24", "panel"): _rule(
        "facet.xy", ("facet", "base_x", "base_y"), _P, ("base_x",), ("base_y",)
    ),
    ("K25", "panel"): _rule("facet.panel", ("panel",), _P, (), ()),
    ("S01", "step"): _rule(
        "special.survival_step",
        (("time", "survival"), ("time", "survival", "group")),
        _U,
        ("time",),
        ("survival",),
    ),
    ("S01", "band"): _rule(
        "special.survival_band",
        (("time", "lower", "upper"), ("time", "lower", "upper", "group")),
        _U,
        ("time",),
        ("lower", "upper"),
    ),
    ("S01", "risk_table"): _rule(
        "special.risk_table",
        (("time", "risk_count"), ("time", "risk_count", "group")),
        _U,
        ("time",),
        (),
    ),
    ("S05", "symbol"): _rule("xy.symbol", ("dose", "response"), _PU, ("dose",), ("response",)),
    ("S05", "line"): _rule("xy.line", ("dose", "response"), _U, ("dose",), ("response",)),
    ("S05", "band"): _rule(
        "xy.band", ("dose", "lower", "upper"), _U, ("dose",), ("lower", "upper")
    ),
    ("S21", "interval"): _rule(
        "special.forest_interval",
        (("label", "effect", "lower", "upper"), ("label", "effect", "lower", "upper", "weight")),
        _U,
        ("effect", "lower", "upper"),
        ("label",),
    ),
    ("S21", "symbol"): _rule(
        "special.forest_symbol",
        (("label", "effect"), ("label", "effect", "weight")),
        _U,
        ("effect",),
        ("label",),
    ),
    ("S25", "line"): _rule(
        "xy.spectrum", ("spectral_axis", "intensity"), _U, ("spectral_axis",), ("intensity",)
    ),
    ("S31", "line"): _rule("xy.spectrum", ("angle", "intensity"), _U, ("angle",), ("intensity",)),
    ("S34", "line"): _rule(
        "xy.nyquist",
        (("z_real", "z_imaginary"), ("z_real", "z_imaginary", "frequency")),
        _U,
        ("z_real",),
        ("z_imaginary",),
    ),
    ("S34", "symbol"): _rule(
        "xy.nyquist",
        (("z_real", "z_imaginary"), ("z_real", "z_imaginary", "frequency")),
        _U,
        ("z_real",),
        ("z_imaginary",),
    ),
    ("S61", "heatmap"): _rule(
        "matrix.confusion", ("actual", "predicted", "value"), _C, ("predicted",), ("actual",)
    ),
}


def get_series_rule(chart_type_id: ChartTypeId, geometry: str) -> SeriesRule:
    try:
        return SERIES_RULES[(chart_type_id, geometry)]
    except KeyError as error:
        raise ValueError(f"{chart_type_id} does not support {geometry!r} series") from error

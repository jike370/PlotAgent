"""Closed execution boundary for a typed OriginExportPlan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from plotagent.contracts.rendering import (
    OriginDataObject,
    OriginExportPlan,
    OriginGraphObject,
    OriginPlotPlan,
    OriginScalar,
)

PROJECT_FOLDERS = ("Data", "Analysis", "Graphs", "Metadata")


@dataclass(frozen=True, slots=True)
class NativePrimitive:
    """One fixed editable primitive; role names can only come from the typed plan."""

    plot_type: str
    x_role: str | None
    y_role: str | None
    error_role: str | None = None
    y2_role: str | None = None
    size_role: str | None = None
    color_role: str | None = None
    transform: Literal[
        "direct",
        "interval_connector",
        "band",
        "box_outline",
        "violin_polygon",
        "step",
        "forest_interval",
        "forest_symbol",
    ] = "direct"


@dataclass(frozen=True, slots=True)
class NativePrimitiveTable:
    x: tuple[OriginScalar, ...]
    y: tuple[OriginScalar, ...]
    y2: tuple[OriginScalar, ...] | None = None


_LINE_KINDS = {
    "line",
    "area",
    "density",
    "step",
    "survival_step",
    "survival_band",
    "spectrum",
    "nyquist",
    "facet_line",
}
_SYMBOL_KINDS = {"scatter", "bubble", "strip", "risk_table"}
_BAR_KINDS = {"bar", "grouped_bar", "stacked_bar", "percent_bar", "histogram"}


def _first_role(plot: OriginPlotPlan, candidates: tuple[str, ...]) -> str | None:
    roles = {item.role for item in plot.role_columns}
    return next((role for role in candidates if role in roles), None)


def native_primitives(plot: OriginPlotPlan) -> tuple[NativePrimitive, ...]:
    """Normalize every semantic plot into an allowlisted native Origin primitive set."""

    x_role = _first_role(
        plot,
        (
            "x",
            "time",
            "dose",
            "grid",
            "spectral_axis",
            "angle",
            "z_real",
            "left",
            "group",
            "label",
        ),
    )
    y_role = _first_role(
        plot,
        (
            "y",
            "center",
            "value",
            "response",
            "intensity",
            "z_imaginary",
            "height",
            "density",
            "probability",
            "survival",
            "effect",
            "median",
        ),
    )
    if plot.native_kind in _LINE_KINDS:
        plot_type = "area" if plot.native_kind == "area" else "line"
        if plot.native_kind in {"step", "survival_step"}:
            return (NativePrimitive(plot_type, x_role, y_role, transform="step"),)
        return (NativePrimitive(plot_type, x_role, y_role),)
    if plot.native_kind == "line_symbol":
        return (NativePrimitive("line_symbol", x_role, y_role),)
    if plot.native_kind == "bubble":
        return (
            NativePrimitive(
                "scatter",
                x_role,
                y_role,
                size_role=_first_role(plot, ("size", "marker_area")),
                color_role=_first_role(plot, ("color",)),
            ),
        )
    if plot.native_kind in _SYMBOL_KINDS:
        return (NativePrimitive("scatter", x_role, y_role),)
    if plot.native_kind in _BAR_KINDS:
        if plot.native_kind in {"bar", "grouped_bar", "histogram"}:
            bar = NativePrimitive("column", x_role, "height")
        else:
            bar = NativePrimitive("floating_column", x_role, "bottom", y2_role="top")
        roles = {item.role for item in plot.role_columns}
        if {"lower", "upper"}.issubset(roles):
            return (
                bar,
                NativePrimitive("line", x_role, None, transform="interval_connector"),
                NativePrimitive("scatter", x_role, "lower"),
                NativePrimitive("scatter", x_role, "upper"),
            )
        return (bar,)
    if plot.native_kind == "error_bar":
        return (
            NativePrimitive("line", x_role, None, transform="interval_connector"),
            NativePrimitive("scatter", x_role, "lower"),
            NativePrimitive("line_symbol", x_role, y_role),
            NativePrimitive("scatter", x_role, "upper"),
        )
    if plot.native_kind == "band":
        return (
            NativePrimitive(
                "fill_area",
                x_role,
                "lower",
                y2_role="upper",
                transform="band",
            ),
        )
    if plot.native_kind == "box":
        return (
            NativePrimitive("line", "group", None, transform="box_outline"),
            NativePrimitive("scatter", "group", "median"),
        )
    if plot.native_kind == "violin":
        return (NativePrimitive("area", x_role, y_role, transform="violin_polygon"),)
    if plot.native_kind == "forest_interval":
        return (NativePrimitive("line", "effect", "label", transform="forest_interval"),)
    if plot.native_kind == "forest_symbol":
        return (
            NativePrimitive(
                "scatter",
                "effect",
                "label",
                size_role="weight",
                transform="forest_symbol",
            ),
        )
    if plot.native_kind in {"heatmap", "contour"}:
        return (NativePrimitive(plot.native_kind, None, None),)
    raise ValueError(f"unsupported typed Origin native kind: {plot.native_kind}")


def physical_plot_count(primitive: NativePrimitive) -> int:
    """Return Origin's persisted DataPlot count for one logical primitive."""

    return 2 if primitive.plot_type in {"fill_area", "floating_column"} else 1


def primitive_book_name(
    graph_name: str,
    layer_index: int,
    plot_index: int,
    primitive_index: int,
) -> str:
    """Return a stable Origin identifier for one materialized primitive table."""

    return f"P{graph_name[:12]}{layer_index:02d}{plot_index:02d}{primitive_index:02d}"


def _role_values(data: OriginDataObject, role: str) -> tuple[OriginScalar, ...]:
    for column in data.columns:
        if column.role == role:
            return column.values
    raise ValueError(f"Origin primitive requires missing role {role!r}")


def _number(value: OriginScalar, role: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Origin {role} primitive values must be numeric")
    return float(value)


def _category_positions(values: tuple[OriginScalar, ...]) -> tuple[float, ...]:
    """Map stable first-seen categories to the resolver's zero-based coordinates."""

    categories: dict[OriginScalar, float] = {}
    output: list[float] = []
    for value in values:
        if value is None:
            raise ValueError("Origin categorical primitive values cannot be missing")
        if value not in categories:
            categories[value] = float(len(categories))
        output.append(categories[value])
    return tuple(output)


def materialize_primitive(
    primitive: NativePrimitive,
    data: OriginDataObject,
) -> NativePrimitiveTable | None:
    """Materialize only fixed visual geometry; no statistics or user expression is run."""

    if primitive.transform == "direct":
        return None
    if data.object_kind != "worksheet":
        raise ValueError("derived native primitives require worksheet data")
    if primitive.x_role is None:
        raise ValueError("derived native primitive has no X role")
    x_values = _role_values(data, primitive.x_role)
    if primitive.transform == "step":
        if primitive.y_role is None:
            raise ValueError("step primitive has no Y role")
        y_values = _role_values(data, primitive.y_role)
        if len(x_values) < 2:
            return NativePrimitiveTable(x_values, y_values)
        step_x: list[OriginScalar] = [x_values[0]]
        step_y: list[OriginScalar] = [y_values[0]]
        for index in range(1, len(x_values)):
            step_x.extend((x_values[index], x_values[index]))
            step_y.extend((y_values[index - 1], y_values[index]))
        return NativePrimitiveTable(tuple(step_x), tuple(step_y))
    if primitive.transform == "band":
        return NativePrimitiveTable(
            x_values,
            _role_values(data, "lower"),
            _role_values(data, "upper"),
        )
    if primitive.transform == "interval_connector":
        lower = _role_values(data, "lower")
        upper = _role_values(data, "upper")
        x_output: list[OriginScalar] = []
        y_output: list[OriginScalar] = []
        for x_value, low, high in zip(x_values, lower, upper, strict=True):
            x_output.extend((x_value, x_value, None))
            y_output.extend((low, high, None))
        return NativePrimitiveTable(tuple(x_output), tuple(y_output))
    if primitive.transform == "box_outline":
        q1 = _role_values(data, "q1")
        median = _role_values(data, "median")
        q3 = _role_values(data, "q3")
        whisker_low = _role_values(data, "whisker_low")
        whisker_high = _role_values(data, "whisker_high")
        x_output = []
        y_output = []
        numeric_x = _category_positions(x_values)
        for x, low, low_box, middle, high_box, high in zip(
            numeric_x,
            whisker_low,
            q1,
            median,
            q3,
            whisker_high,
            strict=True,
        ):
            left, right = x - 0.3, x + 0.3
            cap_left, cap_right = x - 0.15, x + 0.15
            x_output.extend(
                (
                    left,
                    right,
                    right,
                    left,
                    left,
                    None,
                    x,
                    x,
                    None,
                    x,
                    x,
                    None,
                    cap_left,
                    cap_right,
                    None,
                    cap_left,
                    cap_right,
                    None,
                    left,
                    right,
                    None,
                )
            )
            y_output.extend(
                (
                    low_box,
                    low_box,
                    high_box,
                    high_box,
                    low_box,
                    None,
                    low,
                    low_box,
                    None,
                    high_box,
                    high,
                    None,
                    low,
                    low,
                    None,
                    high,
                    high,
                    None,
                    middle,
                    middle,
                    None,
                )
            )
        return NativePrimitiveTable(tuple(x_output), tuple(y_output))
    if primitive.transform == "violin_polygon":
        centers = tuple(
            _number(value, "violin X") for value in _role_values(data, primitive.x_role)
        )
        grid = _role_values(data, primitive.y_role or "y")
        half_width = _role_values(data, "half_width")
        left = tuple(
            center - _number(width, "violin half width")
            for center, width in zip(centers, half_width, strict=True)
        )
        right = tuple(
            center + _number(width, "violin half width")
            for center, width in zip(centers, half_width, strict=True)
        )
        return NativePrimitiveTable(
            left + tuple(reversed(right)) + (left[0],),
            grid + tuple(reversed(grid)) + (grid[0],),
        )
    if primitive.transform == "forest_interval":
        labels = _category_positions(_role_values(data, "label"))
        lower = _role_values(data, "lower")
        upper = _role_values(data, "upper")
        output_x: list[OriginScalar] = []
        output_y: list[OriginScalar] = []
        for position, low, high in zip(labels, lower, upper, strict=True):
            output_x.extend((low, high))
            output_y.extend((position, position))
        return NativePrimitiveTable(tuple(output_x), tuple(output_y))
    if primitive.transform == "forest_symbol":
        return NativePrimitiveTable(
            _role_values(data, "effect"),
            _category_positions(_role_values(data, "label")),
            _role_values(data, "weight"),
        )
    raise ValueError(f"unsupported native primitive transform: {primitive.transform}")


class NativeOriginBackend(Protocol):
    """Minimal backend surface; it intentionally has no script or property-string method."""

    def set_plan(self, plan: OriginExportPlan) -> None: ...

    def ensure_blank(self) -> None: ...

    def create_folder(self, name: str) -> None: ...

    def write_data_object(self, data: OriginDataObject) -> None: ...

    def write_graph_object(self, graph: OriginGraphObject) -> None: ...

    def write_manifest(self, plan: OriginExportPlan) -> None: ...

    def inspect(self, plan: OriginExportPlan) -> dict[str, object]: ...

    def save(self, path: str) -> None: ...


def build_native_project(
    backend: NativeOriginBackend,
    plan: OriginExportPlan,
    temporary_path: str,
) -> dict[str, object]:
    """Build, inspect, then save one project through the closed backend protocol."""

    from .validation import expected_validation_report

    backend.set_plan(plan)
    backend.ensure_blank()
    for folder in PROJECT_FOLDERS:
        backend.create_folder(folder)
    for data in plan.data_objects:
        backend.write_data_object(data)
    for graph in plan.graph_objects:
        backend.write_graph_object(graph)
    backend.write_manifest(plan)
    report = backend.inspect(plan)
    if report != expected_validation_report(plan):
        raise ValueError("live native Origin report differs from the typed execution plan")
    backend.save(temporary_path)
    return report


def inspect_native_project(
    backend: NativeOriginBackend,
    plan: OriginExportPlan,
) -> dict[str, object]:
    from .validation import expected_validation_report

    report = backend.inspect(plan)
    if report != expected_validation_report(plan):
        raise ValueError("fresh native Origin report differs from the typed execution plan")
    return report

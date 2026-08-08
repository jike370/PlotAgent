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
from plotagent.origin.constants import ORIGIN_VARIABLE_SIZE_FACTOR

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
    bar_width_role: str | None = None
    cap_size_pt: float | None = None
    step_where: Literal["pre", "mid", "post"] = "post"
    transform: Literal[
        "direct",
        "interval_connector",
        "point_interval",
        "band",
        "step_band",
        "box_outline",
        "violin_polygon",
        "step",
        "forest_interval",
        "forest_symbol",
        "floating_polygon",
        "drop_line",
        "horizontal_polygon",
        "histogram",
    ] = "direct"


@dataclass(frozen=True, slots=True)
class NativePrimitiveTable:
    x: tuple[OriginScalar, ...]
    y: tuple[OriginScalar, ...]
    y2: tuple[OriginScalar, ...] | None = None
    auxiliary: tuple[OriginScalar, ...] | None = None


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
    if plot.native_kind == "nyquist":
        return (NativePrimitive("line_symbol", x_role, y_role),)
    if plot.native_kind == "survival_band":
        return (
            NativePrimitive(
                "fill_area",
                x_role,
                "lower",
                y2_role="upper",
                step_where="post",
                transform="step_band",
            ),
        )
    if plot.native_kind in _LINE_KINDS:
        plot_type = "area" if plot.native_kind == "area" else "line"
        if plot.native_kind in {"step", "survival_step"}:
            return (
                NativePrimitive(
                    plot_type,
                    x_role,
                    y_role,
                    step_where=(plot.step_where if plot.native_kind == "step" else "post"),
                    transform="step",
                ),
            )
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
    if plot.native_kind == "drop_line":
        return (
            NativePrimitive(
                "scatter",
                x_role,
                y_role,
                transform="drop_line",
            ),
        )
    if plot.native_kind in _BAR_KINDS:
        if plot.native_kind == "histogram":
            bar = NativePrimitive(
                "column",
                "left",
                "height",
                transform="histogram",
            )
        elif plot.native_kind in {"bar", "grouped_bar"}:
            bar = NativePrimitive(
                "column",
                x_role,
                "height",
                bar_width_role=(
                    "width" if plot.native_kind == "grouped_bar" else None
                ),
            )
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
    if plot.native_kind == "floating_bar":
        return (
            NativePrimitive(
                "floating_column",
                "x",
                "bottom",
                y2_role="top",
                bar_width_role="width",
            ),
        )
    if plot.native_kind == "horizontal_bar":
        return (
            NativePrimitive(
                "area",
                "y",
                "left",
                transform="horizontal_polygon",
            ),
        )
    if plot.native_kind == "error_bar":
        return (
            NativePrimitive(
                "line",
                x_role,
                None,
                cap_size_pt=plot.cap_size_pt,
                transform="point_interval",
            ),
            # Point estimates are independent observations.  The interval primitive
            # owns lower/upper and its caps; the only symbol primitive owns center.
            NativePrimitive("scatter", x_role, y_role),
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
        return (
            NativePrimitive("line", "effect", "label", transform="forest_interval"),
            NativePrimitive(
                "scatter",
                "effect",
                "label",
                size_role="weight",
                transform="forest_symbol",
            ),
        )
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

    if primitive.transform in {"direct", "drop_line"}:
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
            if primitive.step_where == "pre":
                step_x.extend((x_values[index - 1], x_values[index]))
                step_y.extend((y_values[index], y_values[index]))
            elif primitive.step_where == "mid":
                left = _number(x_values[index - 1], "step X")
                right = _number(x_values[index], "step X")
                midpoint = (left + right) / 2
                step_x.extend((midpoint, midpoint, right))
                step_y.extend((y_values[index - 1], y_values[index], y_values[index]))
            else:
                step_x.extend((x_values[index], x_values[index]))
                step_y.extend((y_values[index - 1], y_values[index]))
        return NativePrimitiveTable(tuple(step_x), tuple(step_y))
    if primitive.transform == "band":
        return NativePrimitiveTable(
            x_values,
            _role_values(data, "lower"),
            _role_values(data, "upper"),
        )
    if primitive.transform == "step_band":
        lower = _role_values(data, "lower")
        upper = _role_values(data, "upper")
        if len(x_values) < 2:
            return NativePrimitiveTable(x_values, lower, upper)
        band_x: list[OriginScalar] = [x_values[0]]
        step_lower: list[OriginScalar] = [lower[0]]
        step_upper: list[OriginScalar] = [upper[0]]
        for index in range(1, len(x_values)):
            band_x.extend((x_values[index], x_values[index]))
            step_lower.extend((lower[index - 1], lower[index]))
            step_upper.extend((upper[index - 1], upper[index]))
        return NativePrimitiveTable(
            tuple(band_x),
            tuple(step_lower),
            tuple(step_upper),
        )
    if primitive.transform == "histogram":
        right_values = _role_values(data, "right")
        height_values = _role_values(data, primitive.y_role or "height")
        histogram_centers: list[OriginScalar] = []
        for left_edge, right_edge in zip(x_values, right_values, strict=True):
            numeric_left = _number(left_edge, "histogram left")
            numeric_right = _number(right_edge, "histogram right")
            if numeric_right <= numeric_left:
                raise ValueError("Origin histogram bins require right > left")
            histogram_centers.append((numeric_left + numeric_right) / 2)
        return NativePrimitiveTable(tuple(histogram_centers), height_values)
    if primitive.transform == "floating_polygon":
        bottoms = _role_values(data, "bottom")
        tops = _role_values(data, "top")
        widths = _role_values(data, "width")
        numeric_x = (
            tuple(_number(value, "floating-bar X") for value in x_values)
            if all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in x_values
            )
            else _category_positions(x_values)
        )
        floating_x: list[OriginScalar] = []
        floating_y: list[OriginScalar] = []
        for x, bottom, top, width in zip(numeric_x, bottoms, tops, widths, strict=True):
            half_width = _number(width, "floating-bar width") / 2
            floating_x.extend(
                (
                    x - half_width,
                    x + half_width,
                    x + half_width,
                    x - half_width,
                    x - half_width,
                    None,
                )
            )
            floating_y.extend((bottom, bottom, top, top, bottom, None))
        return NativePrimitiveTable(tuple(floating_x), tuple(floating_y))
    if primitive.transform == "horizontal_polygon":
        lefts = _role_values(data, "left")
        rights = _role_values(data, "right")
        heights = _role_values(data, "height")
        numeric_y = (
            tuple(_number(value, "horizontal-bar Y") for value in x_values)
            if all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in x_values
            )
            else _category_positions(x_values)
        )
        horizontal_x: list[OriginScalar] = []
        horizontal_y: list[OriginScalar] = []
        for y_position, left_value, right_value, height_value in zip(
            numeric_y, lefts, rights, heights, strict=True
        ):
            half_height = _number(height_value, "horizontal-bar height") / 2
            horizontal_x.extend(
                (left_value, right_value, right_value, left_value, left_value, None)
            )
            horizontal_y.extend(
                (
                    y_position - half_height,
                    y_position - half_height,
                    y_position + half_height,
                    y_position + half_height,
                    y_position - half_height,
                    None,
                )
            )
        return NativePrimitiveTable(tuple(horizontal_x), tuple(horizontal_y))
    if primitive.transform == "interval_connector":
        lower = _role_values(data, "lower")
        upper = _role_values(data, "upper")
        x_output: list[OriginScalar] = []
        y_output: list[OriginScalar] = []
        for x_value, low, high in zip(x_values, lower, upper, strict=True):
            x_output.extend((x_value, x_value, None))
            y_output.extend((low, high, None))
        return NativePrimitiveTable(tuple(x_output), tuple(y_output))
    if primitive.transform == "point_interval":
        lower = _role_values(data, "lower")
        upper = _role_values(data, "upper")
        center = _role_values(data, "center")
        roles = {column.role for column in data.columns}
        has_horizontal_interval = {"x_lower", "x_upper"}.issubset(roles)
        x_lower = _role_values(data, "x_lower") if has_horizontal_interval else ()
        x_upper = _role_values(data, "x_upper") if has_horizontal_interval else ()
        numeric_x = (
            tuple(_number(value, "point-interval X") for value in x_values)
            if all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in x_values
            )
            else _category_positions(x_values)
        )
        ordered_x = sorted(set(numeric_x))
        positive_steps = tuple(
            right - left
            for left, right in zip(ordered_x, ordered_x[1:], strict=False)
            if right > left
        )
        spacing = min(positive_steps, default=1.0)
        cap_size_pt = primitive.cap_size_pt if primitive.cap_size_pt is not None else 4.0
        if not 0 < cap_size_pt <= 72:
            raise ValueError("Origin point-interval cap size must be in (0, 72] pt")
        cap_half_width = spacing * min(cap_size_pt / 50.0, 0.4)
        numeric_center = tuple(_number(value, "point-interval center") for value in center)
        ordered_center = sorted(set(numeric_center))
        positive_y_steps = tuple(
            high - low
            for low, high in zip(ordered_center, ordered_center[1:], strict=False)
            if high > low
        )
        y_extent = max(
            (
                _number(high, "point-interval upper")
                - _number(low, "point-interval lower")
                for low, high in zip(lower, upper, strict=True)
            ),
            default=1.0,
        )
        y_spacing = min(positive_y_steps, default=max(y_extent, 1.0))
        cap_half_height = y_spacing * min(cap_size_pt / 50.0, 0.4)
        interval_x: list[OriginScalar] = []
        interval_y: list[OriginScalar] = []
        row_values = zip(
            numeric_x,
            numeric_center,
            lower,
            upper,
            x_lower if has_horizontal_interval else (None,) * len(numeric_x),
            x_upper if has_horizontal_interval else (None,) * len(numeric_x),
            strict=True,
        )
        for x_value, center_value, low, high, left, right in row_values:
            low_number = _number(low, "point-interval lower")
            high_number = _number(high, "point-interval upper")
            if low_number > high_number:
                raise ValueError("Origin point interval requires lower <= upper")
            if not low_number <= center_value <= high_number:
                raise ValueError("Origin point interval requires lower <= center <= upper")
            if has_horizontal_interval:
                left_number = _number(left, "point-interval x_lower")
                right_number = _number(right, "point-interval x_upper")
                if not left_number <= x_value <= right_number:
                    raise ValueError(
                        "Origin point interval requires x_lower <= x <= x_upper"
                    )
                # Three independent horizontal-error segments: left cap, interval,
                # and right cap.  Each separator prevents joins to another segment.
                interval_x.extend(
                    (
                        left_number,
                        left_number,
                        None,
                        left_number,
                        right_number,
                        None,
                        right_number,
                        right_number,
                        None,
                    )
                )
                interval_y.extend(
                    (
                        center_value - cap_half_height,
                        center_value + cap_half_height,
                        None,
                        center_value,
                        center_value,
                        None,
                        center_value - cap_half_height,
                        center_value + cap_half_height,
                        None,
                    )
                )
            # Three independent line segments per observation: lower cap, vertical
            # interval, upper cap. None separators prohibit cross-observation joins.
            interval_x.extend(
                (
                    x_value - cap_half_width,
                    x_value + cap_half_width,
                    None,
                    x_value,
                    x_value,
                    None,
                    x_value - cap_half_width,
                    x_value + cap_half_width,
                    None,
                )
            )
            interval_y.extend(
                (
                    low_number,
                    low_number,
                    None,
                    low_number,
                    high_number,
                    None,
                    high_number,
                    high_number,
                    None,
                )
            )
        return NativePrimitiveTable(tuple(interval_x), tuple(interval_y))
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
            box_left, box_right = x - 0.3, x + 0.3
            cap_left, cap_right = x - 0.15, x + 0.15
            x_output.extend(
                (
                    box_left,
                    box_right,
                    box_right,
                    box_left,
                    box_left,
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
                    box_left,
                    box_right,
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
        violin_half_widths = _role_values(data, "half_width")
        violin_left = tuple(
            center - _number(width, "violin half width")
            for center, width in zip(centers, violin_half_widths, strict=True)
        )
        violin_right = tuple(
            center + _number(width, "violin half width")
            for center, width in zip(centers, violin_half_widths, strict=True)
        )
        return NativePrimitiveTable(
            violin_left + tuple(reversed(violin_right)) + (violin_left[0],),
            grid + tuple(reversed(grid)) + (grid[0],),
        )
    if primitive.transform == "forest_interval":
        labels = _category_positions(_role_values(data, "label"))
        lower = _role_values(data, "lower")
        upper = _role_values(data, "upper")
        forest_x: list[OriginScalar] = []
        forest_y: list[OriginScalar] = []
        for position, low, high in zip(labels, lower, upper, strict=True):
            forest_x.extend((low, high))
            forest_y.extend((position, position))
        return NativePrimitiveTable(tuple(forest_x), tuple(forest_y))
    if primitive.transform == "forest_symbol":
        weights = tuple(
            _number(value, "forest weight") for value in _role_values(data, "weight")
        )
        if any(weight < 0 for weight in weights):
            raise ValueError("Origin forest weights must be non-negative")
        maximum = max(weights, default=0.0)
        marker_sizes = tuple(
            (6.0 + 9.0 * weight / maximum) / ORIGIN_VARIABLE_SIZE_FACTOR
            if maximum > 0
            else 6.0 / ORIGIN_VARIABLE_SIZE_FACTOR
            for weight in weights
        )
        return NativePrimitiveTable(
            _role_values(data, "effect"),
            _category_positions(_role_values(data, "label")),
            marker_sizes,
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

    # Fresh-reopen validation owns a new backend instance.  Restore the typed
    # plan before inspection so graph-specific validators can derive their
    # expected native objects from the same immutable data used at build time.
    backend.set_plan(plan)
    report = backend.inspect(plan)
    if report != expected_validation_report(plan):
        raise ValueError("fresh native Origin report differs from the typed execution plan")
    return report

"""Matplotlib Agg mapping for resolved, target-neutral geometry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import matplotlib

matplotlib.use("Agg", force=True)

import numpy as np
from matplotlib import colors as mcolors
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.text import Text
from matplotlib.ticker import NullLocator

from plotagent.contracts.plots import SafeRichText
from plotagent.contracts.rendering import ResolvedAxis, ResolvedLayer
from plotagent.contracts.styles import matplotlib_marker
from plotagent.rendering.data import RenderTable, ResolvedPlot, Scalar

_SUBSCRIPT = str.maketrans("0123456789+-()", "₀₁₂₃₄₅₆₇₈₉₊₋₍₎")
_SUPERSCRIPT = str.maketrans("0123456789+-()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾")


def safe_text(value: SafeRichText | None) -> str | None:
    """Flatten the safe AST without enabling MathText, TeX, HTML, or scripts."""

    if value is None:
        return None
    output: list[str] = []
    for node in value.nodes:
        if node.kind == "newline":
            output.append("\n")
        elif node.kind == "sub":
            output.append(node.text.translate(_SUBSCRIPT))
        elif node.kind == "sup":
            output.append(
                f"^{node.text}"
                if node.text.startswith(("-", "+"))
                else node.text.translate(_SUPERSCRIPT)
            )
        elif node.kind == "fraction":
            output.append(f"{node.text}/{node.denominator}")
        else:
            output.append(node.text)
    return "".join(output)


def _role_columns(layer: ResolvedLayer, table: RenderTable) -> dict[str, tuple[Scalar, ...]]:
    return {binding.role: table.column(binding.field_id) for binding in layer.field_bindings}


def _numeric(values: Sequence[Scalar]) -> np.ndarray[Any, np.dtype[np.float64]]:
    return np.asarray(values, dtype=np.float64)


def _first(roles: Mapping[str, Sequence[Scalar]], names: Sequence[str]) -> Sequence[Scalar]:
    for name in names:
        if name in roles:
            return roles[name]
    raise ValueError(f"none of the required resolved roles are present: {', '.join(names)}")


def _edges(centers: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, np.dtype[np.float64]]:
    if len(centers) == 1:
        return np.asarray((centers[0] - 0.5, centers[0] + 0.5), dtype=np.float64)
    middle = (centers[:-1] + centers[1:]) / 2
    return np.concatenate(
        (
            np.asarray((centers[0] - (middle[0] - centers[0]),)),
            middle,
            np.asarray((centers[-1] + (centers[-1] - middle[-1]),)),
        )
    )


class MatplotlibRenderer:
    """Map a ResolvedRenderPlan to a Matplotlib Figure without resolving defaults."""

    backend = "Agg"

    def build_figure(self, resolved: ResolvedPlot) -> Figure:
        plan = resolved.plan
        width_mm = plan.canvas.width.value
        height_mm = plan.canvas.height.value
        width_pixels = round(width_mm / 25.4 * plan.dpi)
        height_pixels = round(height_mm / 25.4 * plan.dpi)
        figure = Figure(
            figsize=(width_pixels / plan.dpi, height_pixels / plan.dpi),
            dpi=plan.dpi,
            facecolor=plan.background.value,
            layout=None,
        )
        FigureCanvasAgg(figure)
        axes = self._create_axes(figure, resolved)
        for panel in plan.panels:
            panel_label = safe_text(panel.label)
            if panel_label:
                axes[panel.panel_id].text(
                    0.02,
                    0.98,
                    panel_label,
                    transform=axes[panel.panel_id].transAxes,
                    ha="left",
                    va="top",
                    fontweight="bold",
                    zorder=100,
                )
        title = safe_text(plan.title)
        if title:
            title_axis = axes.get("panel:main")
            if title_axis is None:
                title_axis = next(iter(axes.values()))
            title_axis.set_title(title, pad=8)
        for layer in sorted(plan.layers, key=lambda item: item.z_order):
            axis = axes[layer.panel_id]
            roles = _role_columns(layer, resolved.table_for(layer))
            self._draw_layer(axis, layer, roles)
        self._draw_annotations(axes, resolved)
        self._draw_legends(axes, resolved)
        self._draw_colorbar(figure, axes, resolved)
        self._apply_text_style(figure, resolved)
        for axis in axes.values():
            axis.set_autoscale_on(False)
        return figure

    def _create_axes(self, figure: Figure, resolved: ResolvedPlot) -> dict[str, Axes]:
        plan = resolved.plan
        width_mm = plan.canvas.width.value
        height_mm = plan.canvas.height.value
        axes: dict[str, Axes] = {}
        for panel in plan.panels:
            bounds = (
                panel.left.value / width_mm,
                1.0 - (panel.top.value + panel.height.value) / height_mm,
                panel.width.value / width_mm,
                panel.height.value / height_mm,
            )
            axes[panel.panel_id] = figure.add_axes(bounds, label=panel.panel_id)
            axes[panel.panel_id].set_facecolor(plan.background.value)
            if panel.panel_id == "panel:right" and any(
                other.panel_id != panel.panel_id
                and other.left == panel.left
                and other.top == panel.top
                and other.width == panel.width
                and other.height == panel.height
                for other in plan.panels
            ):
                axes[panel.panel_id].patch.set_alpha(0.0)
        for axis_plan in plan.axes:
            self._configure_axis(axes[axis_plan.panel_id], axis_plan)
        for panel in plan.panels:
            if any(
                other.panel_id != panel.panel_id
                and other.left == panel.left
                and other.top == panel.top
                and other.width == panel.width
                and other.height == panel.height
                for other in plan.panels
            ) and panel.panel_id.endswith("right"):
                axes[panel.panel_id].xaxis.set_visible(False)
                if plan.chart_type_id in {"X23", "X24", "X35", "X36", "X37"}:
                    right_axis = axes[panel.panel_id]
                    left_panel = next(
                        other
                        for other in plan.panels
                        if other.panel_id != panel.panel_id
                        and other.left == panel.left
                        and other.top == panel.top
                        and other.width == panel.width
                        and other.height == panel.height
                    )
                    left_axis = axes[left_panel.panel_id]
                    # One physical frame is shared by the two data axes. Hide the
                    # duplicate spines so the right edge is not painted twice, then
                    # explicitly mirror the primary axis/tick/text weight.
                    left_axis.spines["right"].set_visible(False)
                    for spine_name in ("left", "top", "bottom"):
                        right_axis.spines[spine_name].set_visible(False)
                    axis_width = left_axis.spines["left"].get_linewidth()
                    right_axis.spines["right"].set_linewidth(axis_width)
                    right_axis.tick_params(axis="y", which="both", width=axis_width)
                    right_axis.yaxis.label.set_fontweight(left_axis.yaxis.label.get_fontweight())
                    for left_label, right_label in zip(
                        left_axis.get_yticklabels(),
                        right_axis.get_yticklabels(),
                        strict=False,
                    ):
                        right_label.set_fontweight(left_label.get_fontweight())
        for panel_id, axis in axes.items():
            if not any(item.panel_id == panel_id for item in plan.axes):
                axis.set_axis_off()
        return axes

    def _configure_axis(self, axis: Axes, plan: ResolvedAxis) -> None:
        orientation = plan.orientation
        if plan.scale == "log10":
            if orientation == "x":
                axis.set_xscale("log", base=10)
            elif orientation == "y":
                axis.set_yscale("log", base=10)
        minimum, maximum = plan.minimum, plan.maximum
        if minimum is None or maximum is None:
            raise ValueError("the Matplotlib adapter requires a fully resolved axis range")
        limits = (maximum, minimum) if plan.reverse else (minimum, maximum)
        tick_values = tuple(item.value for item in plan.ticks)
        tick_labels = tuple(safe_text(item.label) or "" for item in plan.ticks)
        if orientation == "x":
            axis.set_xlim(*limits)
            axis.set_xticks(tick_values, labels=tick_labels)
            if len(tick_labels) >= 7 or max((len(label) for label in tick_labels), default=0) >= 9:
                axis.tick_params(axis="x", labelrotation=30)
                for label in axis.get_xticklabels():
                    label.set_horizontalalignment("right")
            axis.xaxis.set_minor_locator(NullLocator())
            axis.set_xlabel(safe_text(plan.label) or "")
            axis.spines["bottom"].set_color(plan.color.value)
            axis.spines["bottom"].set_linewidth(plan.line_width.value)
            axis.tick_params(axis="x", colors=plan.color.value, width=plan.line_width.value)
            axis.xaxis.label.set_color(plan.color.value)
            if plan.cross_at is not None:
                axis.spines["bottom"].set_position(("data", plan.cross_at))
            if plan.position == "top":
                axis.xaxis.set_label_position("top")
                axis.xaxis.tick_top()
        elif orientation == "y":
            axis.set_ylim(*limits)
            axis.set_yticks(tick_values, labels=tick_labels)
            axis.yaxis.set_minor_locator(NullLocator())
            axis.set_ylabel(safe_text(plan.label) or "")
            spine = "right" if plan.position == "right" else "left"
            axis.spines[spine].set_color(plan.color.value)
            axis.spines[spine].set_linewidth(plan.line_width.value)
            axis.tick_params(axis="y", colors=plan.color.value, width=plan.line_width.value)
            axis.yaxis.label.set_color(plan.color.value)
            if plan.position == "right":
                axis.yaxis.set_label_position("right")
                axis.yaxis.tick_right()
        if plan.position == "none":
            if orientation == "x":
                axis.tick_params(
                    axis="x", bottom=False, top=False, labelbottom=False, labeltop=False
                )
                axis.set_xlabel("")
            elif orientation == "y":
                axis.tick_params(
                    axis="y", left=False, right=False, labelleft=False, labelright=False
                )
                axis.set_ylabel("")

    def _draw_layer(
        self,
        axis: Axes,
        layer: ResolvedLayer,
        roles: Mapping[str, tuple[Scalar, ...]],
    ) -> None:
        geometry = layer.geometry
        if geometry.startswith(("xy.", "facet.")):
            self._draw_xy(axis, layer, roles)
        elif geometry.startswith("bar."):
            self._draw_bar(axis, layer, roles)
        elif geometry.startswith("distribution."):
            self._draw_distribution(axis, layer, roles)
        elif geometry.startswith("matrix."):
            self._draw_matrix(axis, layer, roles)
        elif geometry.startswith("special."):
            self._draw_special(axis, layer, roles)
        else:
            raise ValueError(f"unsupported resolved geometry {geometry!r}")

    def _style(self, layer: ResolvedLayer) -> tuple[str, float, float, str | None]:
        color = layer.color.value if layer.color is not None else "#000000"
        line_width = layer.line_width.value if layer.line_width is not None else 1.0
        marker_size = layer.marker_size.value if layer.marker_size is not None else 4.0
        return color, line_width, marker_size, safe_text(layer.label)

    @staticmethod
    def _line_style(layer: ResolvedLayer) -> str:
        return {
            "solid": "-",
            "dashed": "--",
            "dotted": ":",
            "dash_dot": "-.",
        }[layer.line_style]

    @staticmethod
    def _symbol_style(axis: Axes, layer: ResolvedLayer, color: str) -> dict[str, Any]:
        marker = matplotlib_marker(layer.symbol.shape)
        if layer.symbol.shape in {"plus", "cross"}:
            return {"marker": marker, "color": color}
        if layer.symbol.interior == "solid":
            return {"marker": marker, "facecolors": color, "edgecolors": color}
        if layer.symbol.interior == "open":
            return {
                "marker": marker,
                "facecolors": axis.get_facecolor(),
                "edgecolors": color,
            }
        return {"marker": marker, "facecolors": "none", "edgecolors": color}

    @staticmethod
    def _line_symbol_style(axis: Axes, layer: ResolvedLayer, color: str) -> dict[str, Any]:
        marker = matplotlib_marker(layer.symbol.shape)
        if layer.symbol.shape in {"plus", "cross"}:
            return {"marker": marker, "markeredgecolor": color}
        if layer.symbol.interior == "solid":
            return {"marker": marker, "markerfacecolor": color, "markeredgecolor": color}
        if layer.symbol.interior == "open":
            return {
                "marker": marker,
                "markerfacecolor": axis.get_facecolor(),
                "markeredgecolor": color,
            }
        return {"marker": marker, "markerfacecolor": "none", "markeredgecolor": color}

    def _draw_xy(
        self,
        axis: Axes,
        layer: ResolvedLayer,
        roles: Mapping[str, tuple[Scalar, ...]],
    ) -> None:
        color, line_width, marker_size, label = self._style(layer)
        x = _numeric(_first(roles, ("x", "time", "dose", "spectral_axis", "angle", "z_real")))
        if layer.geometry == "xy.band":
            lower = _numeric(roles["lower"])
            upper = _numeric(roles["upper"])
            axis.fill_between(
                x,
                lower,
                upper,
                color=(layer.fill_color.value if layer.fill_color is not None else color),
                alpha=layer.band_alpha,
                linewidth=0,
                label=label,
                zorder=layer.z_order,
            )
            return
        y = _numeric(
            _first(roles, ("y", "center", "value", "response", "intensity", "z_imaginary"))
        )
        if layer.geometry in {"xy.line", "xy.datetime_line", "xy.spectrum", "facet.xy"}:
            axis.plot(
                x,
                y,
                color=color,
                linewidth=line_width,
                linestyle=self._line_style(layer),
                label=label,
                zorder=layer.z_order,
            )
        elif layer.geometry == "xy.symbol":
            axis.scatter(
                x,
                y,
                s=marker_size**2,
                label=label,
                zorder=layer.z_order,
                **self._symbol_style(axis, layer, color),
            )
        elif layer.geometry == "xy.bubble":
            sizes = _numeric(roles.get("marker_area", tuple(marker_size**2 for _ in x)))
            colors: str | Sequence[Scalar] = roles.get("point_color", color)
            axis.scatter(x, y, c=cast(Any, colors), s=sizes, label=label, zorder=layer.z_order)
        elif layer.geometry == "xy.error":
            lower = _numeric(roles["lower"])
            upper = _numeric(roles["upper"])
            axis.errorbar(
                x,
                y,
                yerr=np.vstack((y - lower, upper - y)),
                fmt="none",
                ecolor=(
                    layer.uncertainty_color.value if layer.uncertainty_color is not None else color
                ),
                elinewidth=(
                    layer.uncertainty_line_width.value
                    if layer.uncertainty_line_width is not None
                    else line_width
                ),
                capsize=(layer.cap_size.value if layer.cap_size is not None else marker_size),
                label=label,
                zorder=layer.z_order,
            )
        elif layer.geometry == "xy.area":
            axis.fill_between(
                x,
                np.zeros_like(y),
                y,
                color=(layer.fill_color.value if layer.fill_color is not None else color),
                alpha=layer.alpha,
                edgecolor=(layer.edge_color.value if layer.edge_color is not None else "none"),
                linewidth=(
                    layer.edge_width.value
                    if layer.edge_color is not None and layer.edge_width is not None
                    else 0
                ),
                label=label,
                zorder=layer.z_order,
            )
        elif layer.geometry == "xy.nyquist":
            axis.plot(
                x,
                y,
                color=color,
                linewidth=line_width,
                linestyle=self._line_style(layer),
                markersize=marker_size,
                label=label,
                zorder=layer.z_order,
                **self._line_symbol_style(axis, layer, color),
            )
            axis.set_aspect("equal", adjustable="box")
        else:
            raise ValueError(f"unsupported XY geometry {layer.geometry!r}")

    def _draw_bar(
        self,
        axis: Axes,
        layer: ResolvedLayer,
        roles: Mapping[str, tuple[Scalar, ...]],
    ) -> None:
        color, line_width, marker_size, label = self._style(layer)
        fill_color = layer.fill_color.value if layer.fill_color is not None else color
        edge_color = layer.edge_color.value if layer.edge_color is not None else fill_color
        edge_width = layer.edge_width.value if layer.edge_width is not None else line_width
        if layer.geometry == "bar.horizontal":
            axis.barh(
                _numeric(roles["y"]),
                _numeric(roles["width"]),
                height=_numeric(roles["height"]),
                left=_numeric(roles["left"]),
                color=fill_color,
                edgecolor=edge_color,
                linewidth=edge_width,
                alpha=layer.alpha,
                label=label,
                zorder=layer.z_order,
            )
            return
        x = _numeric(roles["x"])
        height = _numeric(roles["height"])
        bottom = _numeric(roles["bottom"])
        width = _numeric(roles["width"])
        error_kw: dict[str, Any] = {}
        if "lower" in roles and "upper" in roles:
            center = bottom + height
            lower = _numeric(roles["lower"])
            upper = _numeric(roles["upper"])
            error_kw = {
                "yerr": np.vstack((center - lower, upper - center)),
                "error_kw": {
                    "ecolor": (
                        layer.uncertainty_color.value
                        if layer.uncertainty_color is not None
                        else edge_color
                    ),
                    "elinewidth": (
                        layer.uncertainty_line_width.value
                        if layer.uncertainty_line_width is not None
                        else line_width
                    ),
                    "capsize": (
                        layer.cap_size.value if layer.cap_size is not None else marker_size
                    ),
                },
            }
        axis.bar(
            x,
            height,
            width=width,
            bottom=bottom,
            color=fill_color,
            edgecolor=edge_color,
            linewidth=edge_width,
            alpha=layer.alpha,
            label=label,
            zorder=layer.z_order,
            **error_kw,
        )

    def _draw_distribution(
        self,
        axis: Axes,
        layer: ResolvedLayer,
        roles: Mapping[str, tuple[Scalar, ...]],
    ) -> None:
        color, line_width, marker_size, label = self._style(layer)
        geometry = layer.geometry
        if geometry == "distribution.strip":
            axis.scatter(
                _numeric(roles["x"]),
                _numeric(roles["y"]),
                color=color,
                s=marker_size**2,
                label=label,
                zorder=layer.z_order,
            )
        elif geometry == "distribution.box":
            x = _numeric(roles["group"])
            q1 = _numeric(roles["q1"])
            median = _numeric(roles["median"])
            q3 = _numeric(roles["q3"])
            low = _numeric(roles["whisker_low"])
            high = _numeric(roles["whisker_high"])
            for position, lower, middle, upper, whisker_low, whisker_high in zip(
                x, q1, median, q3, low, high, strict=True
            ):
                axis.add_patch(
                    Rectangle(
                        (position - 0.3, lower),
                        0.6,
                        upper - lower,
                        facecolor=mcolors.to_rgba(color, 0.25),
                        edgecolor=color,
                        linewidth=line_width,
                        zorder=layer.z_order,
                    )
                )
                axis.hlines(
                    middle,
                    position - 0.3,
                    position + 0.3,
                    color=color,
                    linewidth=line_width,
                    zorder=layer.z_order + 0.1,
                )
                axis.vlines(position, whisker_low, lower, color=color, linewidth=line_width)
                axis.vlines(position, upper, whisker_high, color=color, linewidth=line_width)
                axis.hlines(
                    (whisker_low, whisker_high),
                    position - 0.15,
                    position + 0.15,
                    color=color,
                    linewidth=line_width,
                )
        elif geometry == "distribution.violin":
            x = _numeric(roles["x"])
            y = _numeric(roles["y"])
            half_width = _numeric(roles["half_width"])
            axis.fill_betweenx(
                y,
                x - half_width,
                x + half_width,
                color=color,
                alpha=0.35,
                linewidth=line_width,
                label=label,
                zorder=layer.z_order,
            )
        elif geometry == "distribution.histogram":
            left = _numeric(roles["left"])
            right = _numeric(roles["right"])
            centers = (left + right) / 2
            axis.bar(
                centers,
                _numeric(roles["height"]),
                width=(right - left) * layer.width_ratio,
                align="center",
                color=color,
                edgecolor=color,
                linewidth=line_width,
                label=label,
                zorder=layer.z_order,
            )
        elif geometry == "distribution.density":
            axis.plot(
                _numeric(roles["grid"]),
                _numeric(roles["density"]),
                color=color,
                linewidth=line_width,
                label=label,
                zorder=layer.z_order,
            )
        elif geometry == "distribution.step":
            axis.step(
                _numeric(roles["x"]),
                _numeric(roles["probability"]),
                where=layer.step_where,
                color=color,
                linewidth=line_width,
                label=label,
                zorder=layer.z_order,
            )
        else:
            raise ValueError(f"unsupported distribution geometry {geometry!r}")

    def _draw_matrix(
        self,
        axis: Axes,
        layer: ResolvedLayer,
        roles: Mapping[str, tuple[Scalar, ...]],
    ) -> None:
        x_role = next(
            role for role in ("column", "column_label", "x", "predicted") if role in roles
        )
        y_role = next(role for role in ("row", "row_label", "y", "actual") if role in roles)
        value_role = "z" if "z" in roles else "value"
        x = _numeric(roles[x_role])
        y = _numeric(roles[y_role])
        values = _numeric(roles[value_role])
        x_unique = np.asarray(sorted(set(x)), dtype=np.float64)
        y_unique = np.asarray(sorted(set(y)), dtype=np.float64)
        matrix = np.full((len(y_unique), len(x_unique)), np.nan, dtype=np.float64)
        x_index = {value: index for index, value in enumerate(x_unique)}
        y_index = {value: index for index, value in enumerate(y_unique)}
        for x_value, y_value, value in zip(x, y, values, strict=True):
            matrix[y_index[y_value], x_index[x_value]] = value
        palette = tuple(color.value for color in layer.palette) or _SEQUENTIAL_FALLBACK
        color_map = mcolors.LinearSegmentedColormap.from_list(
            f"plotagent_{layer.layer_id}", palette
        )
        if layer.geometry == "matrix.contour" and len(layer.levels) >= 2:
            grid_x, grid_y = np.meshgrid(x_unique, y_unique)
            axis.contourf(
                grid_x,
                grid_y,
                matrix,
                levels=layer.levels,
                cmap=color_map,
                vmin=layer.color_minimum,
                vmax=layer.color_maximum,
                zorder=layer.z_order,
            )
        else:
            axis.pcolormesh(
                _edges(x_unique),
                _edges(y_unique),
                matrix,
                cmap=color_map,
                vmin=layer.color_minimum,
                vmax=layer.color_maximum,
                shading="flat",
                zorder=layer.z_order,
            )

    def _draw_special(
        self,
        axis: Axes,
        layer: ResolvedLayer,
        roles: Mapping[str, tuple[Scalar, ...]],
    ) -> None:
        color, line_width, marker_size, label = self._style(layer)
        geometry = layer.geometry
        if geometry == "special.lollipop":
            x = _numeric(roles["x"])
            y = _numeric(roles["y"])
            # The baseline is a data-space value and also controls the X-axis
            # crossing, so changing the visible Y range cannot move the stems.
            baseline_values = _numeric(roles.get("baseline", tuple(0.0 for _ in y)))
            axis.vlines(
                x,
                baseline_values,
                y,
                color="#B8BDC6",
                linewidth=line_width,
                zorder=layer.z_order,
            )
            axis.scatter(
                x,
                y,
                color=color,
                s=marker_size**2,
                label=label,
                zorder=layer.z_order + 0.1,
            )
        elif geometry == "special.survival_step":
            axis.step(
                _numeric(roles["time"]),
                _numeric(roles["survival"]),
                where="post",
                color=color,
                linewidth=line_width,
                label=label,
                zorder=layer.z_order,
            )
        elif geometry == "special.survival_band":
            axis.fill_between(
                _numeric(roles["time"]),
                _numeric(roles["lower"]),
                _numeric(roles["upper"]),
                step="post",
                color=(layer.fill_color.value if layer.fill_color is not None else color),
                alpha=layer.band_alpha,
                linewidth=0,
                label=label,
                zorder=layer.z_order,
            )
        elif geometry == "special.risk_table":
            axis.set_axis_off()
            x = _numeric(roles["time"])
            counts = roles["risk_count"]
            risk_y = 0.85 - (layer.z_order % 5) * 0.18
            x_min, x_max = float(min(x)), float(max(x))
            span = x_max - x_min or 1.0
            for x_value, count in zip(x, counts, strict=True):
                axis.text(
                    (x_value - x_min) / span,
                    risk_y,
                    str(count),
                    transform=axis.transAxes,
                    ha="center",
                    va="center",
                    color=color,
                )
            if label:
                axis.text(
                    0.0,
                    risk_y,
                    label,
                    transform=axis.transAxes,
                    ha="right",
                    va="center",
                )
        elif geometry == "special.forest_interval":
            forest_y = _numeric(roles["label"])
            effect = _numeric(roles["effect"])
            lower = _numeric(roles["lower"])
            upper = _numeric(roles["upper"])
            sizes = _numeric(roles.get("weight", tuple(marker_size**2 for _ in effect)))
            if len(sizes) == 0:
                sizes = np.full(effect.shape, marker_size**2, dtype=np.float64)
            else:
                sizes = 16 + 64 * sizes / max(float(max(sizes)), 1e-12)
            axis.hlines(
                forest_y, lower, upper, color=color, linewidth=line_width, zorder=layer.z_order
            )
            axis.scatter(
                effect,
                forest_y,
                s=sizes,
                color=color,
                label=label,
                zorder=layer.z_order + 0.1,
            )
        elif geometry == "special.forest_symbol":
            axis.scatter(
                _numeric(roles["effect"]),
                _numeric(roles["label"]),
                color=color,
                s=marker_size**2,
                label=label,
                zorder=layer.z_order,
            )
        else:
            raise ValueError(f"unsupported special geometry {geometry!r}")

    def _draw_annotations(self, axes: Mapping[str, Axes], resolved: ResolvedPlot) -> None:
        for annotation in resolved.plan.annotations:
            axis = axes[annotation.panel_id]
            text = safe_text(annotation.text) or ""
            if annotation.kind == "panel_label":
                axis.text(
                    annotation.x or 0.02,
                    annotation.y or 0.98,
                    text,
                    transform=axis.transAxes,
                    ha="left",
                    va="top",
                    fontweight="bold",
                )
            elif annotation.kind in {"text", "peak_label"}:
                axis.text(annotation.x or 0.0, annotation.y or 0.0, text)
            elif annotation.kind == "reference_line":
                if annotation.x is not None:
                    axis.axvline(annotation.x, color="#666666", linewidth=0.8, linestyle="--")
                if annotation.y is not None:
                    axis.axhline(annotation.y, color="#666666", linewidth=0.8, linestyle="--")
            elif annotation.kind == "reference_band":
                if annotation.x is not None and annotation.x2 is not None:
                    axis.axvspan(annotation.x, annotation.x2, color="#666666", alpha=0.14)
                if annotation.y is not None and annotation.y2 is not None:
                    axis.axhspan(annotation.y, annotation.y2, color="#666666", alpha=0.14)

    def _draw_legends(self, axes: Mapping[str, Axes], resolved: ResolvedPlot) -> None:
        legend = resolved.plan.legend
        if not legend.visible:
            return
        if legend.common:
            common_handles: list[Any] = []
            common_labels: list[str] = []
            for candidate in axes.values():
                candidate_handles, candidate_labels = candidate.get_legend_handles_labels()
                for handle, label in zip(candidate_handles, candidate_labels, strict=True):
                    if label not in common_labels:
                        common_handles.append(handle)
                        common_labels.append(label)
            if common_handles:
                axis = next(iter(axes.values()))
                axis.legend(
                    common_handles,
                    common_labels,
                    loc="upper right",
                    bbox_to_anchor=(legend.anchor_x, legend.anchor_y),
                    frameon=False,
                )
            return
        grouped: dict[tuple[float, float, float, float], list[Axes]] = {}
        for axis in axes.values():
            bounds = tuple(round(value, 9) for value in axis.get_position().bounds)
            grouped.setdefault(cast(Any, bounds), []).append(axis)
        for axis_group in grouped.values():
            handles: list[Any] = []
            labels: list[str] = []
            for candidate in axis_group:
                candidate_handles, candidate_labels = candidate.get_legend_handles_labels()
                for handle, label in zip(candidate_handles, candidate_labels, strict=True):
                    if label not in labels:
                        handles.append(handle)
                        labels.append(label)
            if not handles:
                continue
            axis = axis_group[-1]
            if legend.placement == "outside_right":
                axis.legend(
                    handles, labels, loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False
                )
            elif legend.placement == "outside_bottom":
                axis.legend(
                    handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.15), frameon=False
                )
            else:
                axis.legend(
                    handles,
                    labels,
                    loc="upper right",
                    bbox_to_anchor=(legend.anchor_x, legend.anchor_y),
                    frameon=False,
                )

    def _draw_colorbar(
        self,
        figure: Figure,
        axes: Mapping[str, Axes],
        resolved: ResolvedPlot,
    ) -> None:
        colorbar = resolved.plan.colorbar
        if not colorbar.visible:
            return
        for axis in axes.values():
            mappable = next(
                (
                    collection
                    for collection in axis.collections
                    if collection.get_array() is not None
                ),
                None,
            )
            if mappable is None:
                continue
            native = figure.colorbar(mappable, ax=axis, fraction=0.046, pad=0.04)
            if native.solids is not None:
                # Matplotlib rasterizes long color bars by default. Formal SVG
                # must remain composed only of native vector elements.
                native.solids.set_rasterized(False)
            title = safe_text(colorbar.title)
            if title:
                native.set_label(title)
            return

    def _apply_text_style(self, figure: Figure, resolved: ResolvedPlot) -> None:
        font = resolved.plan.fonts[0]
        for text in figure.findobj(match=Text):
            text.set_fontfamily(font.family)
            text.set_fontsize(font.size.value)
            if hasattr(text, "set_parse_math"):
                text.set_parse_math(False)


_SEQUENTIAL_FALLBACK = ("#440154", "#21918C", "#FDE725")

"""Independent Matplotlib renderers for the non-composite T2 profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import ceil, sqrt
from pathlib import Path
from typing import Any, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetChartParameter,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import (
    FacetData,
    ForestData,
    K20Grid,
    NyquistData,
    SurvivalData,
    k24_facets,
    s01_survival,
    s21_forest,
    s34_nyquist,
    s61_confusion_grid,
)
from plotagent.engine.repository import document_ref

_COLORS = ("#2A6FDB", "#D94B4B", "#2A9D6F", "#8A5CC2", "#D88700")
_SYMBOLS = {"circle": "o", "square": "s", "diamond": "D", "triangle": "^", "plus": "+"}


@dataclass(frozen=True, slots=True)
class _AxesState:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_scale: str = "linear"
    y_scale: str = "linear"
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None
    x_reverse: bool = False
    y_reverse: bool = False


@dataclass(frozen=True, slots=True)
class _Style:
    color: str | None = None
    line_width_pt: float = 1.5
    line_style: str = "solid"
    symbol: str = "circle"
    symbol_size_pt: float = 6.0


def _line_style(value: str) -> str:
    return {"solid": "-", "dash": "--", "dot": ":", "dash_dot": "-.", "none": ""}[value]


def _style(current: _Style, action: SetSeriesStyle) -> _Style:
    return replace(
        current,
        color=current.color if action.color is None else action.color,
        line_width_pt=current.line_width_pt
        if action.line_width_pt is None
        else action.line_width_pt,
        line_style=current.line_style if action.line_style is None else action.line_style,
        symbol=current.symbol if action.symbol is None else action.symbol,
        symbol_size_pt=(
            current.symbol_size_pt if action.symbol_size_pt is None else action.symbol_size_pt
        ),
    )


def _apply_axes(axis: Any, state: _AxesState) -> None:
    axis.set_title(state.title)
    axis.set_xlabel(state.x_label)
    axis.set_ylabel(state.y_label)
    axis.set_xscale(state.x_scale)
    axis.set_yscale(state.y_scale)
    if state.x_minimum is not None and state.x_maximum is not None:
        axis.set_xlim(state.x_minimum, state.x_maximum)
    if state.y_minimum is not None and state.y_maximum is not None:
        axis.set_ylim(state.y_minimum, state.y_maximum)
    if state.x_reverse:
        axis.invert_xaxis()
    if state.y_reverse:
        axis.invert_yaxis()


def _save(figure: Any, png_path: Path, svg_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png_path, dpi=160)
    figure.savefig(svg_path)
    plt.close(figure)


def _base_objects(document: PlotDocument) -> tuple[EngineObjectRef, ...]:
    token = document.plot_id.removeprefix("plot:")
    return (
        EngineObjectRef(
            semantic_id=document.plot_id,
            backend="matplotlib",
            object_kind="figure",
            native_ref="figure:0",
        ),
        EngineObjectRef(
            semantic_id=f"axis:{token}.x",
            backend="matplotlib",
            object_kind="axis",
            native_ref="axes:0.xaxis",
        ),
        EngineObjectRef(
            semantic_id=f"axis:{token}.y",
            backend="matplotlib",
            object_kind="axis",
            native_ref="axes:0.yaxis",
        ),
    )


def _axis_edit(state: _AxesState, action: SetAxis, token: str) -> _AxesState:
    axis = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
    if axis is None:
        raise ValueError("axis target does not belong to this plot")
    if axis == "x":
        return replace(
            state,
            x_label=state.x_label if action.label is None else action.label,
            x_scale=state.x_scale if action.scale is None else action.scale,
            x_minimum=state.x_minimum if action.minimum is None else action.minimum,
            x_maximum=state.x_maximum if action.maximum is None else action.maximum,
            x_reverse=state.x_reverse if action.reverse is None else action.reverse,
        )
    return replace(
        state,
        y_label=state.y_label if action.label is None else action.label,
        y_scale=state.y_scale if action.scale is None else action.scale,
        y_minimum=state.y_minimum if action.minimum is None else action.minimum,
        y_maximum=state.y_maximum if action.maximum is None else action.maximum,
        y_reverse=state.y_reverse if action.reverse is None else action.reverse,
    )


class K24FacetRenderer:
    profile_id = "K24"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        facets = k24_facets(document, data)
        axes_state, styles, visible, columns = self._state(document, actions, facets)
        column_count = columns or max(1, ceil(sqrt(len(facets.panels))))
        row_count = ceil(len(facets.panels) / column_count)
        figure, axes = plt.subplots(
            row_count,
            column_count,
            squeeze=False,
            figsize=(4.0 * column_count, 3.2 * row_count),
            constrained_layout=True,
        )
        objects = list(_base_objects(document))
        token = document.plot_id.removeprefix("plot:")
        for index, panel in enumerate(facets.panels):
            axis = axes.flat[index]
            style = styles[index]
            axis.plot(
                panel.x_values,
                panel.y_values,
                color=style.color or _COLORS[index % len(_COLORS)],
                linewidth=style.line_width_pt,
                linestyle=_line_style(style.line_style),
                label=panel.label,
            )
            local = replace(axes_state, title=panel.label)
            _apply_axes(axis, local)
            if visible:
                axis.legend()
            objects.extend(
                (
                    EngineObjectRef(
                        semantic_id=f"panel:{token}.facet_{index + 1}",
                        backend="matplotlib",
                        object_kind="facet_panel",
                        native_ref=f"axes:{index}",
                    ),
                    EngineObjectRef(
                        semantic_id=f"series:{token}.facet_{index + 1}",
                        backend="matplotlib",
                        object_kind="facet_series",
                        native_ref=f"axes:{index}.line:0",
                    ),
                )
            )
        for axis in axes.flat[len(facets.panels) :]:
            axis.remove()
        if axes_state.title:
            figure.suptitle(axes_state.title)
        _save(figure, png_path, svg_path)
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "axes": asdict(axes_state),
                        "styles": [asdict(style) for style in styles],
                        "legend": visible,
                        "facet_columns": column_count,
                    },
                )
            ),
        )

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], facets: FacetData
    ) -> tuple[_AxesState, tuple[_Style, ...], bool, int | None]:
        token = document.plot_id.removeprefix("plot:")
        axes = _AxesState(x_label=facets.x_field_name, y_label=facets.y_field_name)
        styles = tuple(_Style() for _panel in facets.panels)
        visible = False
        columns: int | None = None
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K24 title target does not belong to this plot")
                axes = replace(axes, title=action.text)
            elif isinstance(action, SetAxis):
                axes = _axis_edit(axes, action, token)
            elif isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.facet_"
                if not action.target.startswith(prefix):
                    raise ValueError("K24 series target does not belong to this plot")
                index = int(action.target.removeprefix(prefix)) - 1
                if not 0 <= index < len(styles):
                    raise ValueError("K24 facet series target is out of range")
                mutable = list(styles)
                mutable[index] = _style(mutable[index], action)
                styles = tuple(mutable)
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("K24 exposes only legend visibility")
                visible = visible if action.visible is None else action.visible
            elif isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "facet_columns"
                    or isinstance(action.value, bool)
                    or not isinstance(action.value, int)
                    or not 1 <= action.value <= 5
                ):
                    raise ValueError("K24 facet_columns must be an integer from 1 to 5")
                columns = action.value
            else:
                raise ValueError(f"K24 Matplotlib renderer cannot apply {action.operation}")
        return axes, styles, visible, columns


class S01SurvivalRenderer:
    profile_id = "S01"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        survival = s01_survival(document, data)
        axes_state, styles, legend_visible, show_risk = self._state(document, actions, survival)
        has_risk = show_risk and all(group.risk_count is not None for group in survival.groups)
        if has_risk:
            figure = plt.figure(
                figsize=(7.2, 5.1 + 0.32 * len(survival.groups)), constrained_layout=True
            )
            grid = figure.add_gridspec(
                2, 1, height_ratios=(4.0, 0.65 + 0.32 * len(survival.groups))
            )
            axis = figure.add_subplot(grid[0])
            risk_axis = figure.add_subplot(grid[1], sharex=axis)
        else:
            figure, axis = plt.subplots(figsize=(7.2, 5.0), constrained_layout=True)
            risk_axis = None
        token = document.plot_id.removeprefix("plot:")
        objects = list(_base_objects(document))
        for index, group in enumerate(survival.groups):
            style = styles[index]
            color = style.color or _COLORS[index % len(_COLORS)]
            if group.lower is not None and group.upper is not None:
                axis.fill_between(
                    group.time,
                    group.lower,
                    group.upper,
                    step="post",
                    color=color,
                    alpha=0.18,
                )
            axis.step(
                group.time,
                group.survival,
                where="post",
                color=color,
                linewidth=style.line_width_pt,
                linestyle=_line_style(style.line_style),
                label=group.label,
            )
            objects.append(
                EngineObjectRef(
                    semantic_id=f"series:{token}.group_{index + 1}",
                    backend="matplotlib",
                    object_kind="survival_step_series",
                    native_ref=f"axes:0.line:{index}",
                )
            )
        _apply_axes(axis, axes_state)
        axis.set_ylim(0.0, 1.05) if axes_state.y_minimum is None else None
        if legend_visible and len(survival.groups) > 1:
            axis.legend()
        if risk_axis is not None:
            risk_axis.set_yticks(
                range(len(survival.groups)), [group.label for group in survival.groups]
            )
            risk_axis.set_ylim(-0.6, len(survival.groups) - 0.4)
            risk_axis.set_xlabel(axes_state.x_label)
            risk_axis.set_ylabel("At risk")
            axis.set_xlabel("")
            for row, group in enumerate(survival.groups):
                assert group.risk_count is not None
                for time, count in zip(group.time, group.risk_count, strict=True):
                    risk_axis.text(time, row, str(count), ha="center", va="center")
            objects.append(
                EngineObjectRef(
                    semantic_id=f"panel:{token}.risk",
                    backend="matplotlib",
                    object_kind="risk_table_panel",
                    native_ref="axes:1",
                )
            )
        _save(figure, png_path, svg_path)
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "axes": asdict(axes_state),
                        "styles": [asdict(style) for style in styles],
                        "legend": legend_visible,
                        "risk": has_risk,
                    },
                )
            ),
        )

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], survival: SurvivalData
    ) -> tuple[_AxesState, tuple[_Style, ...], bool, bool]:
        token = document.plot_id.removeprefix("plot:")
        axes = _AxesState(
            x_label=survival.time_field_name,
            y_label=survival.survival_field_name,
        )
        styles = tuple(_Style() for _group in survival.groups)
        legend_visible = len(survival.groups) > 1
        show_risk = True
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                axes = replace(axes, title=action.text)
            elif isinstance(action, SetAxis):
                if action.scale not in {None, "linear"}:
                    raise ValueError("S01 axes require linear scale")
                axes = _axis_edit(axes, action, token)
            elif isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.group_"
                if not action.target.startswith(prefix):
                    raise ValueError("S01 series target does not belong to this plot")
                index = int(action.target.removeprefix(prefix)) - 1
                mutable = list(styles)
                mutable[index] = _style(mutable[index], action)
                styles = tuple(mutable)
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("S01 exposes only legend visibility")
                legend_visible = legend_visible if action.visible is None else action.visible
            elif isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "show_risk_table"
                    or not isinstance(action.value, bool)
                ):
                    raise ValueError("S01 show_risk_table must be boolean")
                show_risk = action.value
            else:
                raise ValueError(f"S01 Matplotlib renderer cannot apply {action.operation}")
        return axes, styles, legend_visible, show_risk


class S21ForestRenderer:
    profile_id = "S21"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        forest = s21_forest(document, data)
        axes, interval_style, point_style, null_effect = self._state(document, actions, forest)
        y = np.arange(len(forest.labels), dtype=float)
        sizes = 25.0 + 90.0 * np.asarray(forest.weight) / max(forest.weight)
        figure, axis = plt.subplots(
            figsize=(7.2, max(4.5, 0.38 * len(forest.labels) + 2.0)), constrained_layout=True
        )
        axis.hlines(
            y,
            forest.lower,
            forest.upper,
            colors=interval_style.color or _COLORS[0],
            linewidth=interval_style.line_width_pt,
            linestyles=cast(Any, _line_style(interval_style.line_style)),
        )
        axis.scatter(
            forest.effect,
            y,
            s=sizes * (point_style.symbol_size_pt / 6.0) ** 2,
            marker=_SYMBOLS.get(point_style.symbol, point_style.symbol),
            color=point_style.color or interval_style.color or _COLORS[0],
            zorder=3,
        )
        axis.axvline(null_effect, color="#6B7280", linestyle="--", linewidth=1.0)
        axis.set_yticks(y, forest.labels)
        _apply_axes(axis, axes)
        axis.invert_yaxis()
        _save(figure, png_path, svg_path)
        token = document.plot_id.removeprefix("plot:")
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=_base_objects(document)
            + (
                EngineObjectRef(
                    semantic_id=f"series:{token}.interval",
                    backend="matplotlib",
                    object_kind="forest_intervals",
                    native_ref="axes:0.collection:0",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.points",
                    backend="matplotlib",
                    object_kind="forest_weighted_points",
                    native_ref="axes:0.collection:1",
                ),
                EngineObjectRef(
                    semantic_id=f"annotation:{token}.null_effect",
                    backend="matplotlib",
                    object_kind="reference_line",
                    native_ref="axes:0.line:0",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "axes": asdict(axes),
                        "interval": asdict(interval_style),
                        "point": asdict(point_style),
                        "null_effect": null_effect,
                    },
                )
            ),
        )

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], forest: ForestData
    ) -> tuple[_AxesState, _Style, _Style, float]:
        token = document.plot_id.removeprefix("plot:")
        axes = _AxesState(x_label=forest.effect_field_name, y_label=forest.label_field_name)
        interval = _Style(symbol_size_pt=6.0)
        point = _Style(line_style="none")
        null_effect = 0.0
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                axes = replace(axes, title=action.text)
            elif isinstance(action, SetAxis):
                if action.target == f"axis:{token}.y" and action.scale not in {None, "categorical"}:
                    raise ValueError("S21 y axis requires categorical scale")
                axes = _axis_edit(axes, action, token)
            elif isinstance(action, SetSeriesStyle):
                if action.target == f"series:{token}.interval":
                    if action.symbol is not None or action.symbol_size_pt is not None:
                        raise ValueError("S21 intervals do not expose symbols")
                    interval = _style(interval, action)
                elif action.target == f"series:{token}.points":
                    if action.line_style is not None or action.line_width_pt is not None:
                        raise ValueError("S21 points do not expose line styles")
                    point = _style(point, action)
                else:
                    raise ValueError("S21 series target does not belong to this plot")
            elif isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "null_effect"
                    or isinstance(action.value, bool)
                    or not isinstance(action.value, (int, float))
                ):
                    raise ValueError("S21 null_effect must be numeric")
                null_effect = float(action.value)
            else:
                raise ValueError(f"S21 Matplotlib renderer cannot apply {action.operation}")
        return axes, interval, point, null_effect


class S34NyquistRenderer:
    profile_id = "S34"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        nyquist = s34_nyquist(document, data)
        axes, styles, legend_visible, equal_axes = self._state(document, actions, nyquist)
        figure, axis = plt.subplots(figsize=(6.2, 5.4), constrained_layout=True)
        token = document.plot_id.removeprefix("plot:")
        objects = list(_base_objects(document))
        for index, series in enumerate(nyquist.series):
            style = styles[index]
            axis.plot(
                series.z_real,
                series.z_imaginary,
                color=style.color or _COLORS[index % len(_COLORS)],
                linewidth=style.line_width_pt,
                linestyle=_line_style(style.line_style),
                marker=_SYMBOLS.get(style.symbol, style.symbol),
                markersize=style.symbol_size_pt,
                label=series.label,
            )
            objects.append(
                EngineObjectRef(
                    semantic_id=f"series:{token}.group_{index + 1}",
                    backend="matplotlib",
                    object_kind="nyquist_series",
                    native_ref=f"axes:0.line:{index}",
                )
            )
        _apply_axes(axis, axes)
        if equal_axes:
            axis.set_aspect("equal", adjustable="box")
        if legend_visible and len(nyquist.series) > 1:
            axis.legend()
        _save(figure, png_path, svg_path)
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "axes": asdict(axes),
                        "styles": [asdict(style) for style in styles],
                        "legend": legend_visible,
                        "equal_axes": equal_axes,
                    },
                )
            ),
        )

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], nyquist: NyquistData
    ) -> tuple[_AxesState, tuple[_Style, ...], bool, bool]:
        token = document.plot_id.removeprefix("plot:")
        axes = _AxesState(
            x_label=nyquist.z_real_field_name,
            y_label=nyquist.z_imaginary_field_name,
        )
        styles = tuple(_Style() for _series in nyquist.series)
        legend_visible = len(nyquist.series) > 1
        equal_axes = True
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                axes = replace(axes, title=action.text)
            elif isinstance(action, SetAxis):
                if action.scale not in {None, "linear"}:
                    raise ValueError("S34 axes require linear scale")
                axes = _axis_edit(axes, action, token)
            elif isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.group_"
                if not action.target.startswith(prefix):
                    raise ValueError("S34 series target does not belong to this plot")
                index = int(action.target.removeprefix(prefix)) - 1
                mutable = list(styles)
                mutable[index] = _style(mutable[index], action)
                styles = tuple(mutable)
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("S34 exposes only legend visibility")
                legend_visible = legend_visible if action.visible is None else action.visible
            elif isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "equal_axes"
                    or not isinstance(action.value, bool)
                ):
                    raise ValueError("S34 equal_axes must be boolean")
                equal_axes = action.value
            else:
                raise ValueError(f"S34 Matplotlib renderer cannot apply {action.operation}")
        return axes, styles, legend_visible, equal_axes


class S61ConfusionRenderer:
    profile_id = "S61"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        matrix = s61_confusion_grid(document, data)
        axes, show_counts = self._state(document, actions, matrix)
        values = np.asarray(matrix.values, dtype=float)
        figure, axis = plt.subplots(figsize=(6.0, 5.4), constrained_layout=True)
        axis.imshow(values, cmap="Blues", origin="upper")
        axis.set_xticks(np.arange(len(matrix.column_labels)), matrix.column_labels)
        axis.set_yticks(np.arange(len(matrix.row_labels)), matrix.row_labels)
        if show_counts:
            midpoint = (float(values.min()) + float(values.max())) / 2.0
            for row, values_row in enumerate(values):
                for column, value in enumerate(values_row):
                    axis.text(
                        column,
                        row,
                        str(int(value)),
                        ha="center",
                        va="center",
                        color="white" if value > midpoint else "black",
                    )
        _apply_axes(axis, axes)
        _save(figure, png_path, svg_path)
        token = document.plot_id.removeprefix("plot:")
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=_base_objects(document)
            + (
                EngineObjectRef(
                    semantic_id=f"series:{token}.matrix",
                    backend="matplotlib",
                    object_kind="confusion_matrix",
                    native_ref="axes:0.image:0",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(JsonValue, {"axes": asdict(axes), "show_counts": show_counts})
            ),
        )

    @staticmethod
    def _state(
        document: PlotDocument, actions: tuple[PlotEngineAction, ...], matrix: K20Grid
    ) -> tuple[_AxesState, bool]:
        token = document.plot_id.removeprefix("plot:")
        axes = _AxesState(x_label=matrix.column_field_name, y_label=matrix.row_field_name)
        show_counts = True
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                axes = replace(axes, title=action.text)
            elif isinstance(action, SetAxis):
                if action.scale not in {None, "categorical"} or action.minimum is not None:
                    raise ValueError("S61 axes expose labels and reverse only")
                axes = _axis_edit(axes, action, token)
            elif isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "show_counts"
                    or not isinstance(action.value, bool)
                ):
                    raise ValueError("S61 show_counts must be boolean")
                show_counts = action.value
            else:
                raise ValueError(f"S61 Matplotlib renderer cannot apply {action.operation}")
        return axes, show_counts

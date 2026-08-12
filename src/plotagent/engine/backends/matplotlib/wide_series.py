"""Independent X03/X39/X40 renderers for dynamic wide data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import TransposedSeriesData, transposed_series, x03_lollipop
from plotagent.engine.repository import document_ref

_PALETTE = ("#1676D2", "#D97800", "#299764", "#C53D4D", "#7656B5", "#008A99")
_LINE_STYLES: dict[str, Literal["-", "--", ":", "-."]] = {
    "solid": "-",
    "dash": "--",
    "dot": ":",
    "dash_dot": "-.",
}
_MARKERS = {
    "circle": "o",
    "square": "s",
    "diamond": "D",
    "triangle": "^",
    "triangle_up": "^",
}


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"] = "linear"
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _SeriesState:
    color: str
    line_width_pt: float = 1.2
    line_style: str = "solid"
    symbol: str = "circle"
    symbol_size_pt: float = 6.0


@dataclass(frozen=True, slots=True)
class _State:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    series: tuple[_SeriesState, ...]
    legend_visible: bool = True


class X03LollipopRenderer:
    profile_id = "X03"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        lollipop = x03_lollipop(document, data)
        state = _state(
            document,
            actions,
            x_label="Value",
            y_label=lollipop.category_field_name,
            count=len(lollipop.columns.values),
            profile_id="X03",
        )
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        category_positions = np.arange(len(lollipop.categories), dtype=float)
        for index, (label, values, style) in enumerate(
            zip(lollipop.columns.labels, lollipop.columns.values, state.series, strict=True)
        ):
            axis.scatter(
                values,
                category_positions,
                color=style.color,
                marker=_MARKERS.get(style.symbol, "o"),
                s=style.symbol_size_pt**2,
                label=label,
                zorder=3,
            )
            if index + 1 < len(lollipop.columns.values) and style.line_style != "none":
                next_values = lollipop.columns.values[index + 1]
                axis.hlines(
                    category_positions,
                    values,
                    next_values,
                    color=style.color,
                    linewidth=style.line_width_pt,
                    linestyles=_LINE_STYLES.get(style.line_style, "-"),
                    zorder=1,
                )
        axis.set_yticks(category_positions, lollipop.categories)
        _finish(axis, figure, state, png_path, svg_path)
        return _readback(document, data, state, "lollipop_series", len(state.series), "column")


class X39LineSeriesRenderer:
    profile_id = "X39"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = transposed_series(document, data, profile_id="X39")
        state = _state(
            document,
            actions,
            x_label="Series",
            y_label="Value",
            count=len(series.rows),
            profile_id="X39",
        )
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        _draw_rows(axis, series, state)
        _finish(axis, figure, state, png_path, svg_path)
        return _readback(document, data, state, "line_series", len(state.series), "row")


class X40BeforeAfterRenderer:
    profile_id = "X40"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = transposed_series(document, data, profile_id="X40")
        state = _state(
            document,
            actions,
            x_label="Series",
            y_label="Value",
            count=len(series.rows),
            profile_id="X40",
        )
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        x_values = np.asarray((0.0, 1.0))
        for row, style in zip(series.rows, state.series, strict=True):
            if style.line_style == "none":
                raise ValueError("X40 cannot hide a paired connector")
            axis.plot(
                x_values,
                row,
                color=style.color,
                linewidth=style.line_width_pt,
                linestyle=_LINE_STYLES[style.line_style],
                zorder=1,
            )
            axis.scatter(
                x_values,
                row,
                color=("#2E73D2", "#D94A4A"),
                marker=_MARKERS.get(style.symbol, "o"),
                s=style.symbol_size_pt**2,
                zorder=2,
            )
        axis.set_xticks(x_values, series.axis_labels)
        if state.legend_visible:
            axis.legend(
                handles=(
                    Line2D([], [], marker="o", linestyle="none", color="#2E73D2"),
                    Line2D([], [], marker="o", linestyle="none", color="#D94A4A"),
                ),
                labels=series.axis_labels,
                loc="best",
            )
        _finish(axis, figure, replace(state, legend_visible=False), png_path, svg_path)
        return _readback(document, data, state, "before_after_row", len(state.series), "row")


def _draw_rows(axis: Axes, series: TransposedSeriesData, state: _State) -> None:
    x_values = np.arange(len(series.axis_labels), dtype=float)
    for row, label, style in zip(series.rows, series.row_labels, state.series, strict=True):
        if style.line_style == "none":
            raise ValueError("X39 cannot hide a line series")
        axis.plot(
            x_values,
            row,
            color=style.color,
            linewidth=style.line_width_pt,
            linestyle=_LINE_STYLES[style.line_style],
            marker=_MARKERS.get(style.symbol, "o"),
            markersize=style.symbol_size_pt,
            label=label,
        )
    axis.set_xticks(x_values, series.axis_labels)


def _finish(
    axis: Axes,
    figure: Figure,
    state: _State,
    png_path: Path,
    svg_path: Path,
) -> None:
    axis.set_title(state.title)
    axis.set_xlabel(state.x_axis.label)
    axis.set_ylabel(state.y_axis.label)
    _apply_axis(axis, "x", state.x_axis)
    _apply_axis(axis, "y", state.y_axis)
    if state.legend_visible:
        axis.legend(loc="best")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png_path, dpi=160)
    figure.savefig(svg_path)
    plt.close(figure)


def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
    if state.scale != "categorical":
        scale = "log" if state.scale == "log10" else state.scale
        if scale not in {"linear", "log"}:
            raise ValueError("wide-series numeric axes support only linear or log10 scale")
        getattr(axis, f"set_{name}scale")(scale)
    if state.minimum is not None and state.maximum is not None:
        getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
    if state.reverse:
        getattr(axis, f"invert_{name}axis")()


def _state(
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
    *,
    x_label: str,
    y_label: str,
    count: int,
    profile_id: Literal["X03", "X39", "X40"],
) -> _State:
    token = document.plot_id.removeprefix("plot:")
    state = _State(
        title="",
        x_axis=_AxisState(x_label, scale="linear" if profile_id == "X03" else "categorical"),
        y_axis=_AxisState(y_label, scale="categorical" if profile_id == "X03" else "linear"),
        series=tuple(_SeriesState(_PALETTE[index % len(_PALETTE)]) for index in range(count)),
    )
    last_binding = max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    for index, action in enumerate(actions):
        if isinstance(action, (CreatePlot, BindFields)):
            continue
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError(f"{profile_id} title target does not belong to this plot")
            state = replace(state, title=action.text)
        elif isinstance(action, SetAxis):
            name = {f"axis:{token}.x": "x_axis", f"axis:{token}.y": "y_axis"}.get(
                action.target
            )
            if name is None:
                raise ValueError(f"{profile_id} axis target does not belong to this plot")
            current = getattr(state, name)
            if action.scale is not None:
                categorical_axis = "y_axis" if profile_id == "X03" else "x_axis"
                if name == categorical_axis and action.scale != "categorical":
                    raise ValueError(
                        f"{profile_id} {name.removesuffix('_axis').upper()} axis is categorical"
                    )
                if name != categorical_axis and action.scale not in {"linear", "log10"}:
                    raise ValueError(
                        f"{profile_id} {name.removesuffix('_axis').upper()} axis supports "
                        "linear or log10"
                    )
            bounds = (
                (current.minimum, current.maximum)
                if action.minimum is None
                else (action.minimum, action.maximum)
            )
            state = replace(
                state,
                **{
                    name: replace(
                        current,
                        label=current.label if action.label is None else action.label,
                        scale=current.scale if action.scale is None else action.scale,
                        minimum=bounds[0],
                        maximum=bounds[1],
                        reverse=current.reverse if action.reverse is None else action.reverse,
                    )
                },
            )
        elif isinstance(action, SetSeriesStyle):
            if index < last_binding:
                continue
            ordinal = _row_or_column_ordinal(action.target, token, count, profile_id)
            current = state.series[ordinal - 1]
            updated = replace(
                current,
                color=current.color if action.color is None else action.color,
                line_width_pt=(
                    current.line_width_pt
                    if action.line_width_pt is None
                    else action.line_width_pt
                ),
                line_style=current.line_style if action.line_style is None else action.line_style,
                symbol=current.symbol if action.symbol is None else action.symbol,
                symbol_size_pt=(
                    current.symbol_size_pt
                    if action.symbol_size_pt is None
                    else action.symbol_size_pt
                ),
            )
            items = list(state.series)
            items[ordinal - 1] = updated
            state = replace(state, series=tuple(items))
        elif isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main":
                raise ValueError(f"{profile_id} legend target does not belong to this plot")
            state = replace(
                state,
                legend_visible=(state.legend_visible if action.visible is None else action.visible),
            )
        else:
            raise ValueError(f"{profile_id} renderer cannot apply {action.operation}")
    return state


def _row_or_column_ordinal(target: str, token: str, count: int, profile_id: str) -> int:
    key = "column" if profile_id == "X03" else "row"
    prefix = f"series:{token}.{key}_"
    suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
    if not suffix.isdigit() or not 1 <= int(suffix) <= count:
        raise ValueError(f"{profile_id} series target is outside the materialized data")
    return int(suffix)


def _readback(
    document: PlotDocument,
    data: EngineDataView,
    state: _State,
    object_kind: str,
    count: int,
    key: str,
) -> EngineReadback:
    token = document.plot_id.removeprefix("plot:")
    objects = (
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
        *tuple(
            EngineObjectRef(
                semantic_id=f"series:{token}.{key}_{index}",
                backend="matplotlib",
                object_kind=object_kind,
                native_ref=f"axes:0.{object_kind}:{index - 1}",
            )
            for index in range(1, count + 1)
        ),
        EngineObjectRef(
            semantic_id=f"legend:{token}.main",
            backend="matplotlib",
            object_kind="legend",
            native_ref="axes:0.legend",
        ),
    )
    return EngineReadback(
        document=document_ref(document),
        backend="matplotlib",
        objects=objects,
        data_hash=canonical_hash(data),
        style_hash=canonical_hash(asdict(state)),
    )

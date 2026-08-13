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
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

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
from plotagent.engine.profile_data import (
    WideSeriesData,
    wide_series,
    x03_lollipop,
    x40_identity_label_positions,
)
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
class _ConnectorState:
    color: str = "#202020"
    line_width_pt: float = 1.2
    line_style: str = "solid"


@dataclass(frozen=True, slots=True)
class _State:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    series: tuple[_SeriesState, ...]
    connector: _ConnectorState | None = None
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
        category_positions: np.ndarray = np.arange(
            len(lollipop.categories), dtype=float
        )
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
        return _readback(
            document,
            data,
            state,
            "lollipop_series",
            len(state.series),
            "column",
        )


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
        series = wide_series(document, data, profile_id="X39")
        state = _state(
            document,
            actions,
            x_label="Series",
            y_label="Value",
            count=len(series.column_values),
            profile_id="X39",
        )
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        _draw_wide_series(axis, series, state)
        _finish(axis, figure, state, png_path, svg_path)
        return _readback(
            document,
            data,
            state,
            "line_series_column",
            len(state.series),
            "column",
            connector_kind="line_series_connector",
        )


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
        series = wide_series(document, data, profile_id="X40")
        state = _state(
            document,
            actions,
            x_label="Series",
            y_label="Value",
            count=len(series.column_values),
            profile_id="X40",
        )
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        _draw_wide_series(axis, series, state)
        _finish(axis, figure, state, png_path, svg_path)
        return _readback(
            document,
            data,
            state,
            "before_after_column",
            len(state.series),
            "column",
            connector_kind="before_after_connector",
        )


def _draw_wide_series(axis: Axes, series: WideSeriesData, state: _State) -> None:
    connector = state.connector
    if connector is None or connector.line_style == "none":
        raise ValueError("X39/X40 require one visible native connector group")
    x_values: np.ndarray = np.arange(len(series.column_labels), dtype=float)
    rows = tuple(zip(*series.column_values, strict=True))
    segments = tuple(np.column_stack((x_values, np.asarray(row, dtype=float))) for row in rows)
    axis.add_collection(
        LineCollection(
            segments,
            colors=connector.color,
            linewidths=connector.line_width_pt,
            linestyles=_LINE_STYLES[connector.line_style],
            zorder=1,
        )
    )
    for x_value, label, values, style in zip(
        x_values,
        series.column_labels,
        series.column_values,
        state.series,
        strict=True,
    ):
        axis.scatter(
            np.full(series.row_count, x_value),
            values,
            color=style.color,
            marker=_MARKERS.get(style.symbol, "o"),
            s=style.symbol_size_pt**2,
            label=label,
            zorder=2,
        )
    if series.row_labels is not None:
        after_x = x_values[-1]
        label_positions = x40_identity_label_positions(series.column_values[-1])
        for row, (subject, after_value, label_y) in enumerate(
            zip(
                series.row_labels,
                series.column_values[-1],
                label_positions,
                strict=True,
            )
        ):
            group = "" if series.row_groups is None else f" · {series.row_groups[row]}"
            axis.annotate(
                f"{subject}{group}",
                (after_x, after_value),
                xytext=(after_x + 0.03, label_y),
                textcoords="data",
                ha="left",
                va="center",
                fontsize=8,
                arrowprops={"arrowstyle": "-", "color": "#666666", "linewidth": 0.6},
            )
    axis.set_xticks(x_values, series.column_labels)
    axis.autoscale_view()


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
        series=tuple(_SeriesState(_column_color(profile_id, index)) for index in range(count)),
        connector=None if profile_id == "X03" else _ConnectorState(),
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
            name = {f"axis:{token}.x": "x_axis", f"axis:{token}.y": "y_axis"}.get(action.target)
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
            if action.target == f"series:{token}.connector":
                if profile_id == "X03" or state.connector is None:
                    raise ValueError(f"{profile_id} has no connector-group target")
                if action.symbol is not None or action.symbol_size_pt is not None:
                    raise ValueError(
                        f"{profile_id} connector supports line style, width and color only"
                    )
                if action.line_style == "none":
                    raise ValueError(f"{profile_id} cannot hide its connector group")
                state = replace(
                    state,
                    connector=replace(
                        state.connector,
                        color=(state.connector.color if action.color is None else action.color),
                        line_width_pt=(
                            state.connector.line_width_pt
                            if action.line_width_pt is None
                            else action.line_width_pt
                        ),
                        line_style=(
                            state.connector.line_style
                            if action.line_style is None
                            else action.line_style
                        ),
                    ),
                )
                continue
            ordinal = _column_ordinal(action.target, token, count, profile_id)
            if profile_id != "X03" and (
                action.line_width_pt is not None
                or action.line_style is not None
                or action.symbol_size_pt is not None
            ):
                raise ValueError(
                    f"{profile_id} column targets support marker color and symbol only"
                )
            current = state.series[ordinal - 1]
            updated = replace(
                current,
                color=current.color if action.color is None else action.color,
                line_width_pt=(
                    current.line_width_pt if action.line_width_pt is None else action.line_width_pt
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


def _column_ordinal(target: str, token: str, count: int, profile_id: str) -> int:
    prefix = f"series:{token}.column_"
    suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
    if not suffix.isdigit() or not 1 <= int(suffix) <= count:
        raise ValueError(f"{profile_id} series target is outside the materialized data")
    return int(suffix)


def _column_color(profile_id: str, zero_based_index: int) -> str:
    if profile_id == "X40":
        return ("#2E73D2", "#D94A4A")[zero_based_index]
    return _PALETTE[zero_based_index % len(_PALETTE)]


def _readback(
    document: PlotDocument,
    data: EngineDataView,
    state: _State,
    object_kind: str,
    count: int,
    key: str,
    *,
    connector_kind: str | None = None,
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
        *(
            (
                EngineObjectRef(
                    semantic_id=f"series:{token}.connector",
                    backend="matplotlib",
                    object_kind=connector_kind,
                    native_ref="axes:0.collection:connector",
                ),
            )
            if connector_kind is not None
            else ()
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

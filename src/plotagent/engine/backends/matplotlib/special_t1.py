"""Independent Matplotlib renderers for the remaining T1 special profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from plotagent.contracts.canonical import JsonValue, canonical_hash
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
    OffsetStackData,
    ParetoData,
    X23SeriesData,
    x24_pareto,
    x35_series,
    x36_series,
    x38_offset_stack,
)
from plotagent.engine.repository import document_ref

_PALETTE = ("#1676D2", "#D97800", "#299764", "#C53D4D", "#7656B5", "#008A99")
_LINE_STYLE = {"solid": "-", "dash": "--", "dot": ":", "dash_dot": "-.", "none": ""}
_MARKER = {"circle": "o", "square": "s", "diamond": "D", "triangle": "^", "triangle_up": "^"}


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
    line_width_pt: float = 1.4
    line_style: str = "solid"
    symbol: str = "circle"
    symbol_size_pt: float = 6.0


@dataclass(frozen=True, slots=True)
class _DualState:
    title: str
    x_axis: _AxisState
    left_axis: _AxisState
    right_axis: _AxisState
    left_series: _SeriesState
    right_series: _SeriesState
    legend_visible: bool = True


class X24ParetoRenderer:
    profile_id = "X24"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        pareto = x24_pareto(document, data)
        state = _pareto_state(document, actions, pareto)
        figure, left = plt.subplots(figsize=(7.2, 4.8), layout="constrained")
        right = left.twinx()
        positions = np.arange(len(pareto.categories), dtype=float)
        bars = left.bar(
            positions,
            pareto.values,
            width=0.68,
            color=state.left_series.color,
            edgecolor=state.left_series.color,
            linewidth=state.left_series.line_width_pt,
            linestyle=_LINE_STYLE[state.left_series.line_style],
            label=pareto.value_field_name,
        )
        line = right.plot(
            positions,
            pareto.cumulative_percent,
            color=state.right_series.color,
            linewidth=state.right_series.line_width_pt,
            linestyle=_LINE_STYLE[state.right_series.line_style],
            marker=_MARKER[state.right_series.symbol],
            markersize=state.right_series.symbol_size_pt,
            label="Cumulative (%)",
        )[0]
        right.axhline(80.0, color="#6B7280", linestyle="--", linewidth=1.0)
        right.set_ylim(0.0, 110.0)
        left.set_xticks(positions, pareto.categories)
        _finish_dual(figure, left, right, state, (bars, line), png_path, svg_path)
        return _dual_readback(
            document,
            data,
            state,
            "pareto_bar_series",
            "pareto_cumulative_series",
            extra=("pareto_reference_line",),
            left_key="bars",
            right_key="cumulative",
            style_extra={"pareto_reference_percent": 80.0},
        )


class X35DualYColumnRenderer:
    profile_id = "X35"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        values = x35_series(document, data)
        state = _dual_state(document, actions, values, "X35")
        figure, left = plt.subplots(figsize=(7.2, 4.8), layout="constrained")
        right = left.twinx()
        positions = np.arange(len(values.x_labels or ()), dtype=float)
        width = 0.34
        left_bars = left.bar(
            positions - width / 2,
            values.left_values,
            width=width,
            color=state.left_series.color,
            edgecolor=state.left_series.color,
            linewidth=state.left_series.line_width_pt,
            label=values.left_field_name,
        )
        right_bars = right.bar(
            positions + width / 2,
            values.right_values,
            width=width,
            color=state.right_series.color,
            edgecolor=state.right_series.color,
            linewidth=state.right_series.line_width_pt,
            label=values.right_field_name,
        )
        left.set_xticks(positions, values.x_labels)
        _finish_dual(figure, left, right, state, (left_bars, right_bars), png_path, svg_path)
        return _dual_readback(document, data, state, "dual_y_column_series", "dual_y_column_series")


class X36DualYColumnLineRenderer:
    profile_id = "X36"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        values = x36_series(document, data)
        state = _dual_state(document, actions, values, "X36")
        figure, left = plt.subplots(figsize=(7.2, 4.8), layout="constrained")
        right = left.twinx()
        positions = np.arange(len(values.x_labels or ()), dtype=float)
        bars = left.bar(
            positions,
            values.left_values,
            width=0.62,
            color=state.left_series.color,
            edgecolor=state.left_series.color,
            linewidth=state.left_series.line_width_pt,
            label=values.left_field_name,
        )
        line = right.plot(
            positions,
            values.right_values,
            color=state.right_series.color,
            linewidth=state.right_series.line_width_pt,
            linestyle=_LINE_STYLE[state.right_series.line_style],
            marker=_MARKER[state.right_series.symbol],
            markersize=state.right_series.symbol_size_pt,
            label=values.right_field_name,
        )[0]
        left.set_xticks(positions, values.x_labels)
        _finish_dual(figure, left, right, state, (bars, line), png_path, svg_path)
        return _dual_readback(document, data, state, "dual_y_column_series", "dual_y_line_series")


@dataclass(frozen=True, slots=True)
class _OffsetState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    series: tuple[_SeriesState, ...]
    legend_visible: bool = True


class X38OffsetStackRenderer:
    profile_id = "X38"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        offset_data = x38_offset_stack(document, data)
        state = _offset_state(document, actions, offset_data)
        figure, axis = plt.subplots(figsize=(7.2, 4.8), layout="constrained")
        finite = [
            value
            for series in offset_data.series
            for value in series.y_values
            if np.isfinite(value)
        ]
        distance = max(float(np.ptp(finite)) * 0.32, 1.0) if finite else 1.0
        for index, (series, style) in enumerate(zip(offset_data.series, state.series, strict=True)):
            axis.plot(
                series.x_values,
                np.asarray(series.y_values, dtype=float) + index * distance,
                color=style.color,
                linewidth=style.line_width_pt,
                linestyle=_LINE_STYLE[style.line_style],
                label=series.label,
            )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_axis.label)
        axis.set_ylabel(state.y_axis.label)
        _apply_axis(axis, "x", state.x_axis)
        _apply_axis(axis, "y", state.y_axis)
        if state.legend_visible:
            axis.legend(loc="best")
        _save(figure, png_path, svg_path)
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
                    semantic_id=f"series:{token}.group_{index}",
                    backend="matplotlib",
                    object_kind="offset_line_series",
                    native_ref=f"axes:0.line:{index - 1}",
                )
                for index in range(1, len(state.series) + 1)
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


def _pareto_state(
    document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: ParetoData
) -> _DualState:
    state = _DualState(
        title="",
        x_axis=_AxisState("", "categorical"),
        left_axis=_AxisState(data.value_field_name),
        right_axis=_AxisState("Cumulative (%)"),
        left_series=_SeriesState("#1676D2"),
        right_series=_SeriesState("#D97800"),
        legend_visible=False,
    )
    token = document.plot_id.removeprefix("plot:")
    for action in actions:
        if isinstance(action, (CreatePlot, BindFields)):
            continue
        state = _apply_dual_action(
            document, state, action, token, "X24", allow_left_symbol=False, allow_right_symbol=True
        )
    return state


def _dual_state(
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
    data: X23SeriesData,
    profile_id: Literal["X35", "X36"],
) -> _DualState:
    state = _DualState(
        title="",
        x_axis=_AxisState(data.x_field_name, "categorical"),
        left_axis=_AxisState(data.left_field_name),
        right_axis=_AxisState(data.right_field_name),
        left_series=_SeriesState("#1676D2"),
        right_series=_SeriesState("#D97800"),
    )
    token = document.plot_id.removeprefix("plot:")
    for action in actions:
        if isinstance(action, (CreatePlot, BindFields)):
            continue
        state = _apply_dual_action(
            document,
            state,
            action,
            token,
            profile_id,
            allow_left_symbol=False,
            allow_right_symbol=profile_id == "X36",
        )
    return state


def _apply_dual_action(
    document: PlotDocument,
    state: _DualState,
    action: PlotEngineAction,
    token: str,
    profile_id: str,
    *,
    allow_left_symbol: bool,
    allow_right_symbol: bool,
) -> _DualState:
    if isinstance(action, SetTitle):
        if action.target != document.plot_id:
            raise ValueError(f"{profile_id} title target does not belong to this plot")
        return replace(state, title=action.text)
    if isinstance(action, SetAxis):
        key = {
            f"axis:{token}.x": "x_axis",
            f"axis:{token}.y_left": "left_axis",
            f"axis:{token}.y_right": "right_axis",
        }.get(action.target)
        if key is None:
            raise ValueError(f"{profile_id} axis target does not belong to this plot")
        current = getattr(state, key)
        scale = current.scale if action.scale is None else action.scale
        if key == "x_axis" and scale != "categorical":
            raise ValueError(f"{profile_id} X axis is categorical")
        if key != "x_axis" and scale not in {"linear", "log10"}:
            raise ValueError(f"{profile_id} Y axes support linear or log10")
        updated = replace(
            current,
            label=current.label if action.label is None else action.label,
            scale=scale,
            minimum=current.minimum if action.minimum is None else action.minimum,
            maximum=current.maximum if action.maximum is None else action.maximum,
            reverse=current.reverse if action.reverse is None else action.reverse,
        )
        return replace(state, **{key: updated})
    if isinstance(action, SetSeriesStyle):
        key = {
            f"series:{token}.bars": "left_series",
            f"series:{token}.cumulative": "right_series",
            f"series:{token}.left": "left_series",
            f"series:{token}.right": "right_series",
        }.get(action.target)
        if key is None:
            raise ValueError(f"{profile_id} series target does not belong to this plot")
        allow_symbol = allow_left_symbol if key == "left_series" else allow_right_symbol
        if not allow_symbol and (action.symbol is not None or action.symbol_size_pt is not None):
            raise ValueError(f"{profile_id} column series does not expose symbol edits")
        current = getattr(state, key)
        updated = replace(
            current,
            color=current.color if action.color is None else action.color,
            line_width_pt=current.line_width_pt
            if action.line_width_pt is None
            else action.line_width_pt,
            line_style=current.line_style if action.line_style is None else action.line_style,
            symbol=current.symbol if action.symbol is None else action.symbol,
            symbol_size_pt=current.symbol_size_pt
            if action.symbol_size_pt is None
            else action.symbol_size_pt,
        )
        return replace(state, **{key: updated})
    if isinstance(action, SetLegend):
        if action.target != f"legend:{token}.main" or action.anchor is not None:
            raise ValueError(f"{profile_id} exposes only legend visibility")
        return replace(
            state, legend_visible=state.legend_visible if action.visible is None else action.visible
        )
    raise ValueError(f"{profile_id} renderer cannot apply {action.operation}")


def _offset_state(
    document: PlotDocument, actions: tuple[PlotEngineAction, ...], data: OffsetStackData
) -> _OffsetState:
    token = document.plot_id.removeprefix("plot:")
    state = _OffsetState(
        title="",
        x_axis=_AxisState(data.x_field_name),
        y_axis=_AxisState(data.y_field_name),
        series=tuple(
            _SeriesState(_PALETTE[index % len(_PALETTE)]) for index in range(len(data.series))
        ),
    )
    for action in actions:
        if isinstance(action, (CreatePlot, BindFields)):
            continue
        if isinstance(action, SetTitle):
            if action.target != document.plot_id:
                raise ValueError("X38 title target does not belong to this plot")
            state = replace(state, title=action.text)
        elif isinstance(action, SetAxis):
            key = {f"axis:{token}.x": "x_axis", f"axis:{token}.y": "y_axis"}.get(action.target)
            if key is None:
                raise ValueError("X38 axis target does not belong to this plot")
            current = getattr(state, key)
            scale = current.scale if action.scale is None else action.scale
            if scale not in {"linear", "log10"}:
                raise ValueError("X38 axes support linear or log10")
            state = replace(
                state,
                **{
                    key: replace(
                        current,
                        label=current.label if action.label is None else action.label,
                        scale=scale,
                        minimum=current.minimum if action.minimum is None else action.minimum,
                        maximum=current.maximum if action.maximum is None else action.maximum,
                        reverse=current.reverse if action.reverse is None else action.reverse,
                    )
                },
            )
        elif isinstance(action, SetSeriesStyle):
            raise ValueError(
                "X38 keeps the official dependent style group and does not expose "
                "per-series style edits"
            )
        elif isinstance(action, SetLegend):
            if action.target != f"legend:{token}.main" or action.anchor is not None:
                raise ValueError("X38 exposes only legend visibility")
            state = replace(
                state,
                legend_visible=state.legend_visible if action.visible is None else action.visible,
            )
        else:
            raise ValueError(f"X38 renderer cannot apply {action.operation}")
    return state


def _finish_dual(
    figure: Figure,
    left: Axes,
    right: Axes,
    state: _DualState,
    handles: tuple[object, object],
    png_path: Path,
    svg_path: Path,
) -> None:
    left.set_title(state.title)
    left.set_xlabel(state.x_axis.label)
    left.set_ylabel(state.left_axis.label)
    right.set_ylabel(state.right_axis.label)
    _apply_axis(left, "x", state.x_axis)
    _apply_axis(left, "y", state.left_axis)
    _apply_axis(right, "y", state.right_axis)
    if state.legend_visible:
        figure.legend(
            handles=handles,
            labels=(state.left_axis.label, state.right_axis.label),
            loc="outside right upper",
            frameon=False,
        )
    _save(figure, png_path, svg_path)


def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
    if state.scale != "categorical":
        getattr(axis, f"set_{name}scale")("log" if state.scale == "log10" else "linear")
    if state.minimum is not None and state.maximum is not None:
        getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
    if state.reverse:
        getattr(axis, f"invert_{name}axis")()


def _save(figure: Figure, png_path: Path, svg_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png_path, dpi=160)
    figure.savefig(svg_path)
    plt.close(figure)


def _dual_readback(
    document: PlotDocument,
    data: EngineDataView,
    state: _DualState,
    left_kind: str,
    right_kind: str,
    *,
    extra: tuple[str, ...] = (),
    left_key: str = "left",
    right_key: str = "right",
    style_extra: dict[str, float] | None = None,
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
            semantic_id=f"axis:{token}.y_left",
            backend="matplotlib",
            object_kind="axis",
            native_ref="axes:0.yaxis",
        ),
        EngineObjectRef(
            semantic_id=f"axis:{token}.y_right",
            backend="matplotlib",
            object_kind="axis",
            native_ref="axes:1.yaxis",
        ),
        EngineObjectRef(
            semantic_id=f"series:{token}.{left_key}",
            backend="matplotlib",
            object_kind=left_kind,
            native_ref="axes:0.series:0",
        ),
        EngineObjectRef(
            semantic_id=f"series:{token}.{right_key}",
            backend="matplotlib",
            object_kind=right_kind,
            native_ref="axes:1.series:0",
        ),
        *tuple(
            EngineObjectRef(
                semantic_id=f"annotation:{token}.{kind}",
                backend="matplotlib",
                object_kind=kind,
                native_ref=f"axes:1.{kind}",
            )
            for kind in extra
        ),
        EngineObjectRef(
            semantic_id=f"legend:{token}.main",
            backend="matplotlib",
            object_kind="legend",
            native_ref="figure:0.legend:0",
        ),
    )
    return EngineReadback(
        document=document_ref(document),
        backend="matplotlib",
        objects=objects,
        data_hash=canonical_hash(data),
        style_hash=canonical_hash(
            cast(
                JsonValue,
                {"state": asdict(state), "parameters": {} if style_extra is None else style_extra},
            )
        ),
    )

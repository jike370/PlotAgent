"""Independent X23 Matplotlib renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes

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
from plotagent.engine.profile_data import X23SeriesData, x23_series
from plotagent.engine.repository import document_ref

_LINE_STYLE = {
    "solid": "-",
    "dash": "--",
    "dot": ":",
    "dash_dot": "-.",
    "none": "",
}


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"]
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _SeriesState:
    label: str
    color: str
    line_width_pt: float = 1.5
    line_style: Literal["solid", "dash", "dot", "dash_dot", "none"] = "solid"


@dataclass(frozen=True, slots=True)
class _DualYState:
    title: str
    x_axis: _AxisState
    left_axis: _AxisState
    right_axis: _AxisState
    left_series: _SeriesState
    right_series: _SeriesState
    legend_visible: bool = True


class X23DualYRenderer:
    profile_id = "X23"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = x23_series(document, data)
        state = self._state(document, actions, series)
        if series.x_labels is None:
            x_values = np.asarray(series.x_values, dtype=float)
        else:
            x_values = np.arange(len(series.x_labels), dtype=float)

        figure, left_axis = plt.subplots(figsize=(7.2, 4.8), layout="constrained")
        right_axis = left_axis.twinx()
        left_line = left_axis.plot(
            x_values,
            np.asarray(series.left_values, dtype=float),
            color=state.left_series.color,
            linewidth=state.left_series.line_width_pt,
            linestyle=_LINE_STYLE[state.left_series.line_style],
            marker="o",
            label=state.left_series.label,
        )[0]
        right_line = right_axis.plot(
            x_values,
            np.asarray(series.right_values, dtype=float),
            color=state.right_series.color,
            linewidth=state.right_series.line_width_pt,
            linestyle=_LINE_STYLE[state.right_series.line_style],
            marker="s",
            label=state.right_series.label,
        )[0]
        left_axis.set_title(state.title, pad=12.0)
        left_axis.set_xlabel(state.x_axis.label)
        left_axis.set_ylabel(state.left_axis.label)
        right_axis.set_ylabel(state.right_axis.label)
        if series.x_labels is not None:
            left_axis.set_xticks(x_values, series.x_labels)
        self._apply_axis(left_axis, "x", state.x_axis)
        self._apply_axis(left_axis, "y", state.left_axis)
        self._apply_axis(right_axis, "y", state.right_axis)
        if state.legend_visible:
            figure.legend(
                handles=(left_line, right_line),
                labels=(state.left_series.label, state.right_series.label),
                loc="outside right upper",
                ncols=1,
                frameon=False,
            )
        png_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(png_path, dpi=160)
        figure.savefig(svg_path)
        plt.close(figure)

        token = document.plot_id.removeprefix("plot:")
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=(
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
                    semantic_id=f"series:{token}.left",
                    backend="matplotlib",
                    object_kind="line_series",
                    native_ref="axes:0.line:0",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.right",
                    backend="matplotlib",
                    object_kind="line_series",
                    native_ref="axes:1.line:0",
                ),
                EngineObjectRef(
                    semantic_id=f"legend:{token}.main",
                    backend="matplotlib",
                    object_kind="legend",
                    native_ref="figure:0.legend:0",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(asdict(state)),
        )

    @staticmethod
    def _apply_axis(axis: Axes, orientation: Literal["x", "y"], state: _AxisState) -> None:
        if state.scale == "categorical":
            if orientation != "x":
                raise ValueError("X23 categorical scale is supported only on x")
        elif state.scale in {"linear", "log10"}:
            getattr(axis, f"set_{orientation}scale")(
                "log" if state.scale == "log10" else "linear"
            )
        else:
            raise ValueError("X23 currently supports categorical, linear or log10 axes")
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{orientation}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{orientation}axis")()

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: X23SeriesData,
    ) -> _DualYState:
        token = document.plot_id.removeprefix("plot:")
        state = _DualYState(
            title="",
            x_axis=_AxisState(data.x_field_name, data.x_scale),
            left_axis=_AxisState(data.left_field_name, "linear"),
            right_axis=_AxisState(data.right_field_name, "linear"),
            left_series=_SeriesState(data.left_field_name, "#1676D2"),
            right_series=_SeriesState(data.right_field_name, "#D97706"),
        )
        axis_targets = {
            f"axis:{token}.x": "x_axis",
            f"axis:{token}.y_left": "left_axis",
            f"axis:{token}.y_right": "right_axis",
        }
        series_targets = {
            f"series:{token}.left": "left_series",
            f"series:{token}.right": "right_series",
        }
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("X23 title target does not belong to this plot")
                state = replace(state, title=action.text)
                continue
            if isinstance(action, SetAxis):
                attribute = axis_targets.get(action.target)
                if attribute is None:
                    raise ValueError("X23 axis target does not belong to this plot")
                current = getattr(state, attribute)
                scale = current.scale if action.scale is None else action.scale
                if attribute == "x_axis" and data.x_scale == "categorical":
                    if scale != "categorical":
                        raise ValueError("X23 categorical x data cannot use a numeric scale")
                elif scale not in {"linear", "log10"}:
                    raise ValueError("X23 numeric axes support only linear or log10")
                updated_axis = replace(
                    current,
                    label=current.label if action.label is None else action.label,
                    scale=scale,
                    minimum=current.minimum if action.minimum is None else action.minimum,
                    maximum=current.maximum if action.maximum is None else action.maximum,
                    reverse=current.reverse if action.reverse is None else action.reverse,
                )
                if attribute == "x_axis":
                    state = replace(state, x_axis=updated_axis)
                elif attribute == "left_axis":
                    state = replace(state, left_axis=updated_axis)
                else:
                    state = replace(state, right_axis=updated_axis)
                continue
            if isinstance(action, SetSeriesStyle):
                attribute = series_targets.get(action.target)
                if attribute is None:
                    raise ValueError("X23 series target does not belong to this plot")
                if action.symbol is not None or action.symbol_size_pt is not None:
                    raise ValueError("X23 does not expose symbol edits")
                current_series = getattr(state, attribute)
                updated_series = replace(
                    current_series,
                    color=current_series.color if action.color is None else action.color,
                    line_width_pt=(
                        current_series.line_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt
                    ),
                    line_style=(
                        current_series.line_style
                        if action.line_style is None
                        else action.line_style
                    ),
                )
                if attribute == "left_series":
                    state = replace(state, left_series=updated_series)
                else:
                    state = replace(state, right_series=updated_series)
                continue
            if isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main":
                    raise ValueError("X23 legend target does not belong to this plot")
                if action.anchor is not None:
                    raise ValueError("X23 does not expose legend anchor edits")
                state = replace(
                    state,
                    legend_visible=(
                        state.legend_visible if action.visible is None else action.visible
                    ),
                )
                continue
            raise ValueError(f"X23 Matplotlib renderer cannot apply {action.operation}")
        return state

"""Independent K19 datetime-series Matplotlib renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

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
from plotagent.engine.profile_data import k19_time_series
from plotagent.engine.repository import document_ref

_LINE_STYLES: dict[str, Literal["-", "--", ":", "-.", ""]] = {
    "solid": "-",
    "dash": "--",
    "dot": ":",
    "dash_dot": "-.",
    "none": "",
}
_MARKERS = {"none": "", "circle": "o", "square": "s", "triangle": "^", "diamond": "D"}


@dataclass(frozen=True, slots=True)
class _K19State:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False
    color: str = "#1676D2"
    line_width_pt: float = 1.5
    line_style: str = "solid"
    symbol: str = "none"
    symbol_size_pt: float = 5.0
    legend_visible: bool = False


class K19TimeSeriesRenderer:
    profile_id = "K19"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = k19_time_series(document, data)
        state = self._state(document, actions, series.time_field_name, series.value_field_name)
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        date_values = mdates.date2num(series.time_values)  # type: ignore[no-untyped-call]
        (line,) = axis.plot(
            date_values,
            series.values,
            color=state.color,
            linewidth=state.line_width_pt,
            linestyle=_LINE_STYLES[state.line_style],
            marker=_MARKERS.get(state.symbol, state.symbol),
            markersize=state.symbol_size_pt,
            label=series.value_field_name,
        )
        locator = mdates.AutoDateLocator()  # type: ignore[no-untyped-call]
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(
            mdates.ConciseDateFormatter(locator)  # type: ignore[no-untyped-call]
        )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_label)
        axis.set_ylabel(state.y_label)
        if state.x_reverse:
            axis.invert_xaxis()
        if state.y_reverse:
            axis.invert_yaxis()
        if state.legend_visible:
            axis.legend(loc="best")
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
                    semantic_id=f"axis:{token}.y",
                    backend="matplotlib",
                    object_kind="axis",
                    native_ref="axes:0.yaxis",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.primary",
                    backend="matplotlib",
                    object_kind="datetime_line",
                    native_ref=f"axes:0.line:{line.get_gid() or 0}",
                ),
                EngineObjectRef(
                    semantic_id=f"legend:{token}.main",
                    backend="matplotlib",
                    object_kind="legend",
                    native_ref="axes:0.legend",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(asdict(state)),
        )

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        time_name: str,
        value_name: str,
    ) -> _K19State:
        token = document.plot_id.removeprefix("plot:")
        state = _K19State(title="", x_label=time_name, y_label=value_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K19 title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
                if axis_name is None:
                    raise ValueError("K19 axis target does not belong to this plot")
                expected_scale = "datetime" if axis_name == "x" else "linear"
                if action.scale not in {None, expected_scale}:
                    raise ValueError(f"K19 {axis_name} axis requires {expected_scale} scale")
                if action.minimum is not None or action.maximum is not None:
                    raise ValueError("K19 public datetime axes do not expose numeric bounds")
                if axis_name == "x":
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_reverse=state.x_reverse if action.reverse is None else action.reverse,
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_reverse=state.y_reverse if action.reverse is None else action.reverse,
                    )
            elif isinstance(action, SetSeriesStyle):
                if action.target != f"series:{token}.primary":
                    raise ValueError("K19 series target does not belong to this plot")
                state = replace(
                    state,
                    color=state.color if action.color is None else action.color,
                    line_width_pt=(
                        state.line_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt
                    ),
                    line_style=state.line_style if action.line_style is None else action.line_style,
                    symbol=state.symbol if action.symbol is None else action.symbol,
                    symbol_size_pt=(
                        state.symbol_size_pt
                        if action.symbol_size_pt is None
                        else action.symbol_size_pt
                    ),
                )
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main":
                    raise ValueError("K19 legend target does not belong to this plot")
                if action.anchor not in {None, "inside"}:
                    raise ValueError("K19 currently exposes only the template legend anchor")
                state = replace(
                    state,
                    legend_visible=(
                        state.legend_visible if action.visible is None else action.visible
                    ),
                )
            else:
                raise ValueError(f"K19 Matplotlib renderer cannot apply {action.operation}")
        return state

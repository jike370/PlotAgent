"""Independent X02 continuous drop-line renderer ending at the bottom X axis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import xy_series
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"] = "linear"
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _DropLineState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    color: str = "#1676D2"
    line_width_pt: float = 1.0
    line_style: str = "solid"
    symbol: str = "circle"
    symbol_size_pt: float = 5.0
    legend_visible: bool = False


class X02DropLineRenderer:
    profile_id = "X02"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = xy_series(document, data, profile_id=self.profile_id)
        state = self._state(document, actions, series.x_field_name, series.y_field_name)
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        points = axis.scatter(
            series.x_values,
            series.y_values,
            color=state.color,
            marker=self._marker(state.symbol),
            s=state.symbol_size_pt**2,
            label=series.y_field_name,
            zorder=2,
        )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_axis.label)
        axis.set_ylabel(state.y_axis.label)
        self._apply_axis(axis, "x", state.x_axis)
        self._apply_axis(axis, "y", state.y_axis)
        visible_y_limits = axis.get_ylim()
        stems = axis.vlines(
            series.x_values,
            visible_y_limits[0],
            series.y_values,
            color=state.color,
            linewidth=state.line_width_pt,
            linestyles=self._line_style(state.line_style),
            label="_nolegend_",
            zorder=1,
        )
        axis.set_ylim(visible_y_limits)
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
                    object_kind="drop_line_series",
                    native_ref=(
                        f"axes:0.collection:{stems.get_gid() or 1}+points:{points.get_gid() or 0}"
                    ),
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
    def _marker(symbol: str) -> str:
        try:
            return {
                "circle": "o",
                "square": "s",
                "triangle": "^",
                "triangle_up": "^",
                "diamond": "D",
            }[symbol]
        except KeyError as error:
            raise ValueError(f"X02 does not support symbol {symbol}") from error

    @staticmethod
    def _line_style(
        style: str,
    ) -> Literal["solid", "dashed", "dotted", "dashdot"]:
        styles: dict[str, Literal["solid", "dashed", "dotted", "dashdot"]] = {
            "solid": "solid",
            "dash": "dashed",
            "dot": "dotted",
            "dash_dot": "dashdot",
        }
        return styles[style]

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        scale = "log" if state.scale == "log10" else state.scale
        if scale not in {"linear", "log"}:
            raise ValueError(f"X02 does not support {state.scale} on the {name} axis")
        getattr(axis, f"set_{name}scale")(scale)
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        x_name: str,
        y_name: str,
    ) -> _DropLineState:
        document.plot_id.removeprefix("plot:")
        state = _DropLineState(
            title="",
            x_axis=_AxisState(x_name),
            y_axis=_AxisState(y_name),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"X02 renderer cannot apply {action.operation}")
        return state

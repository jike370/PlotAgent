"""Independent K06 bidirectional point-error renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import k06_point_error
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"] = "linear"
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _K06State:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    color: str = "#1676D2"
    line_width_pt: float = 1.25
    symbol: str = "circle"
    symbol_size_pt: float = 5.0
    legend_visible: bool = False
    legend_anchor: str = "inside"


class K06PointErrorRenderer:
    profile_id = "K06"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = k06_point_error(document, data)
        state = self._state(document, actions, series.x_field_name, series.center_field_name)

        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        container = axis.errorbar(
            np.asarray(series.x_values, dtype=float),
            np.asarray(series.center_values, dtype=float),
            xerr=np.asarray((series.x_minus_errors, series.x_plus_errors), dtype=float),
            yerr=np.asarray((series.y_minus_errors, series.y_plus_errors), dtype=float),
            fmt=self._marker(state.symbol),
            linestyle="none",
            color=state.color,
            ecolor=state.color,
            markersize=state.symbol_size_pt,
            elinewidth=state.line_width_pt,
            capsize=4.0,
            capthick=state.line_width_pt,
            label=series.center_field_name,
        )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_axis.label)
        axis.set_ylabel(state.y_axis.label)
        self._apply_axis(axis, "x", state.x_axis)
        self._apply_axis(axis, "y", state.y_axis)
        self._apply_legend(axis, state)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(png_path, dpi=160)
        figure.savefig(svg_path)
        plt.close(figure)

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
            EngineObjectRef(
                semantic_id=f"series:{token}.primary",
                backend="matplotlib",
                object_kind="point_error_series",
                native_ref=f"axes:0.errorbar:{len(container.lines)}",
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
            raise ValueError(f"K06 does not support symbol {symbol}") from error

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        scale = "log" if state.scale == "log10" else state.scale
        if scale not in {"linear", "log"}:
            raise ValueError(f"K06 does not support {state.scale} on the {name} axis")
        getattr(axis, f"set_{name}scale")(scale)
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    @staticmethod
    def _apply_legend(axis: Axes, state: _K06State) -> None:
        placements: dict[str, dict[str, object]] = {
            "inside": {"loc": "best"},
            "right": {"loc": "center left", "bbox_to_anchor": (1.02, 0.5)},
            "bottom": {"loc": "upper center", "bbox_to_anchor": (0.5, -0.15)},
        }
        if state.legend_visible and state.legend_anchor != "none":
            axis.legend(**placements[state.legend_anchor])

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        x_name: str,
        center_name: str,
    ) -> _K06State:
        document.plot_id.removeprefix("plot:")
        state = _K06State(
            title="",
            x_axis=_AxisState(x_name),
            y_axis=_AxisState(center_name),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"K06 renderer cannot apply {action.operation}")
        return state

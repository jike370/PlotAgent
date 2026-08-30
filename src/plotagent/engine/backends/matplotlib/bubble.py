"""Independent K04 renderer matching Origin's Bubble Scale default."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isfinite
from pathlib import Path
from typing import Literal, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from numpy.typing import NDArray

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetChartParameter,
    SetPointMarkerMap,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import K04BubbleData, k04_bubble, point_marker_shapes
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"] = "linear"
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _K04State:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    color: str = "#1676D2"
    symbol: str = "circle"
    symbol_size_pt: float = 12.0
    legend_visible: bool = False
    color_scale_visible: bool = False
    size_key_visible: bool = False


class K04BubbleRenderer:
    profile_id = "K04"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        bubble = k04_bubble(document, data)
        state = self._state(document, actions, bubble)
        sizes = self._marker_areas(bubble, state.symbol_size_pt)

        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        scatter = axis.scatter(
            bubble.x_values,
            bubble.y_values,
            s=sizes,
            c=state.color if bubble.color_values is None else bubble.color_values,
            cmap=None if bubble.color_values is None else "viridis",
            marker=self._marker(state.symbol),
            label=bubble.y_field_name,
        )
        marker_action = next(
            (action for action in reversed(actions) if isinstance(action, SetPointMarkerMap)),
            None,
        )
        marker_data = (
            None if marker_action is None else point_marker_shapes(data, marker_action)
        )
        if marker_data is not None:
            scatter.set_paths(
                [
                    MarkerStyle(self._marker(shape)).get_path().transformed(
                        MarkerStyle(self._marker(shape)).get_transform()
                    )
                    for shape in marker_data.shapes
                ]
            )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_axis.label)
        axis.set_ylabel(state.y_axis.label)
        self._apply_axis(axis, "x", state.x_axis)
        self._apply_axis(axis, "y", state.y_axis)
        main_legend = axis.legend(loc="best") if state.legend_visible else None
        if state.size_key_visible:
            if bubble.size_values is None:
                raise ValueError("K04 cannot show a size key without a size binding")
            if main_legend is not None:
                axis.add_artist(main_legend)
            handles, labels = self._size_key_entries(bubble, state.symbol_size_pt)
            size_legend = axis.legend(
                handles,
                labels,
                title=bubble.size_field_name,
                loc="upper right",
            )
            size_legend.set_gid("plotagent-auxiliary-legend:size-key")
            axis.add_artist(size_legend)
            axis.legend_ = main_legend
        if state.color_scale_visible:
            if bubble.color_values is None:
                raise ValueError("K04 cannot show a color scale without a color binding")
            colorbar = figure.colorbar(scatter, ax=axis)
            colorbar.set_label(bubble.color_field_name or "")

        png_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(png_path, dpi=160)
        figure.savefig(svg_path)
        plt.close(figure)

        token = document.plot_id.removeprefix("plot:")
        objects = [
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
                object_kind="bubble_series",
                native_ref="axes:0.collection:0",
            ),
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="matplotlib",
                object_kind="legend",
                native_ref="axes:0.legend",
            ),
        ]
        if state.color_scale_visible:
            objects.append(
                EngineObjectRef(
                    semantic_id=f"legend:{token}.color_scale",
                    backend="matplotlib",
                    object_kind="color_scale",
                    native_ref="axes:1.colorbar",
                )
            )
        if state.size_key_visible:
            objects.append(
                EngineObjectRef(
                    semantic_id=f"legend:{token}.size_key",
                    backend="matplotlib",
                    object_kind="size_key",
                    native_ref="axes:0.size_legend",
                )
            )
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                {
                    "state": asdict(state),
                    "point_marker_map": (
                        None
                        if marker_action is None
                        else marker_action.model_dump(mode="json")
                    ),
                }
            ),
        )

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        bubble: K04BubbleData,
    ) -> _K04State:
        document.plot_id.removeprefix("plot:")
        state = _K04State(
            title="",
            x_axis=_AxisState(bubble.x_field_name),
            y_axis=_AxisState(bubble.y_field_name),
            size_key_visible=bubble.size_values is not None,
        )
        last_binding = max(
            (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
            default=-1,
        )
        for index, action in enumerate(actions):
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetPointMarkerMap):
                continue
            if isinstance(action, SetChartParameter):
                if index < last_binding:
                    continue
                if action.target != document.plot_id or not isinstance(action.value, bool):
                    raise ValueError("K04 scale parameters require the plot target and a boolean")
                if action.parameter == "color_scale_visible":
                    if action.value and bubble.color_values is None:
                        raise ValueError("K04 color scale requires a color binding")
                    state = replace(state, color_scale_visible=action.value)
                elif action.parameter == "size_key_visible":
                    if action.value and bubble.size_values is None:
                        raise ValueError("K04 size key requires a size binding")
                    state = replace(state, size_key_visible=action.value)
                else:
                    raise ValueError(f"K04 does not support parameter {action.parameter}")
            else:
                raise ValueError(f"K04 renderer cannot apply {action.operation}")
        return state

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        scale = "log" if state.scale == "log10" else state.scale
        if scale not in {"linear", "log"}:
            raise ValueError(f"K04 does not support {state.scale} on the {name} axis")
        getattr(axis, f"set_{name}scale")(scale)
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    @staticmethod
    def _marker(symbol: str) -> str:
        try:
            return {
                "circle": "o",
                "square": "s",
                "triangle": "^",
                "triangle_up": "^",
                "triangle_down": "v",
                "triangle_left": "<",
                "triangle_right": ">",
                "diamond": "D",
                "plus": "+",
                "cross": "x",
                "hexagon": "h",
                "star": "*",
                "pentagon": "p",
            }[symbol]
        except KeyError as error:
            raise ValueError(f"K04 does not support symbol {symbol}") from error

    @staticmethod
    def _marker_areas(
        bubble: K04BubbleData,
        maximum_size_pt: float,
    ) -> NDArray[np.float64]:
        if bubble.size_values is None:
            return np.full(len(bubble.x_values), maximum_size_pt**2, dtype=np.float64)
        values = np.asarray(bubble.size_values, dtype=float)
        finite = values[np.isfinite(values)]
        high = float(np.max(finite))
        if high <= 0:
            return np.zeros_like(values)
        normalized = np.clip(np.nan_to_num(values, nan=0.0) / high, 0.0, 1.0)
        return cast(NDArray[np.float64], normalized * maximum_size_pt**2)

    def _size_key_entries(
        self,
        bubble: K04BubbleData,
        maximum_size_pt: float,
    ) -> tuple[list[Line2D], list[str]]:
        assert bubble.size_values is not None
        finite = sorted({value for value in bubble.size_values if isfinite(value)})
        indexes = sorted({0, len(finite) // 2, len(finite) - 1})
        values = [finite[index] for index in indexes]
        high = max(values)
        handles = [
            Line2D(
                [],
                [],
                linestyle="none",
                marker="o",
                color="#667085",
                markersize=0.0 if high <= 0 else maximum_size_pt * (value / high) ** 0.5,
            )
            for value in values
        ]
        labels = [f"{value:g}" for value in values]
        return handles, labels

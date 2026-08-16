"""Independent X13 population-pyramid renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.ticker import FuncFormatter

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import PopulationPyramidData, x13_population_pyramid
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "categorical"]
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _SeriesState:
    label: str
    color: str
    edge_width_pt: float = 0.8


@dataclass(frozen=True, slots=True)
class _PyramidState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    left: _SeriesState
    right: _SeriesState
    legend_visible: bool = True


class X13PopulationPyramidRenderer:
    profile_id = "X13"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        pyramid = x13_population_pyramid(document, data)
        state = self._state(document, actions, pyramid)
        positions = np.arange(len(pyramid.categories), dtype=float)
        figure, axis = plt.subplots(figsize=(7.2, 5.2), layout="constrained")
        left = axis.barh(
            positions,
            -np.asarray(pyramid.left_values),
            height=0.78,
            color=state.left.color,
            edgecolor="#1A1A1A",
            linewidth=state.left.edge_width_pt,
            label=state.left.label,
        )
        right = axis.barh(
            positions,
            pyramid.right_values,
            height=0.78,
            color=state.right.color,
            edgecolor="#1A1A1A",
            linewidth=state.right.edge_width_pt,
            label=state.right.label,
        )
        axis.axvline(0.0, color="#1A1A1A", linewidth=0.8)
        axis.set_yticks(positions, ())
        for position, category in zip(positions, pyramid.categories, strict=True):
            axis.text(
                0.0,
                position,
                category,
                ha="center",
                va="center",
                zorder=4,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5, "alpha": 0.88},
            )
        axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{abs(value):g}"))
        axis.set_title(state.title)
        axis.set_xlabel(state.x_axis.label)
        axis.set_ylabel(state.y_axis.label)
        self._apply_axis(axis, "x", state.x_axis)
        self._apply_axis(axis, "y", state.y_axis)
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
                    semantic_id=f"series:{token}.left",
                    backend="matplotlib",
                    object_kind="population_bar_series",
                    native_ref=f"axes:0.barh:0:{len(left)}",
                ),
                EngineObjectRef(
                    semantic_id=f"series:{token}.right",
                    backend="matplotlib",
                    object_kind="population_bar_series",
                    native_ref=f"axes:0.barh:1:{len(right)}",
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
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        if name == "x" and state.scale != "linear":
            raise ValueError("X13 population axis supports only linear scale")
        if name == "y" and state.scale != "categorical":
            raise ValueError("X13 category axis supports only categorical scale")
        if state.minimum is not None and state.maximum is not None:
            if name == "x":
                bound = max(abs(state.minimum), abs(state.maximum))
                axis.set_xlim(-bound, bound)
            else:
                axis.set_ylim(state.minimum, state.maximum)
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        pyramid: PopulationPyramidData,
    ) -> _PyramidState:
        document.plot_id.removeprefix("plot:")
        state = _PyramidState(
            title="",
            x_axis=_AxisState("Population", "linear"),
            y_axis=_AxisState(pyramid.category_field_name, "categorical"),
            left=_SeriesState(pyramid.left_field_name, "#1676D2"),
            right=_SeriesState(pyramid.right_field_name, "#D97800"),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"X13 renderer cannot apply {action.operation}")
        return state

"""Independent K15 histogram renderer over shared deterministic calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import k15_histogram
from plotagent.engine.repository import document_ref

_PALETTE = ("#1676D2", "#D97800", "#299764", "#C53D4D", "#7656B5", "#008A99")


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


@dataclass(frozen=True, slots=True)
class _State:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    series: tuple[_SeriesState, ...]
    legend_visible: bool = False


def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
    scale = "log" if state.scale == "log10" else state.scale
    if scale not in {"linear", "log"}:
        raise ValueError("calculated distribution axes support only linear or log10 scale")
    getattr(axis, f"set_{name}scale")(scale)
    if state.minimum is not None and state.maximum is not None:
        getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
    if state.reverse:
        getattr(axis, f"invert_{name}axis")()


def _objects(document: PlotDocument, backend_kind: str, count: int) -> tuple[EngineObjectRef, ...]:
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
        *tuple(
            EngineObjectRef(
                semantic_id=(
                    f"series:{token}.primary" if count == 1 else f"series:{token}.group_{index}"
                ),
                backend="matplotlib",
                object_kind=backend_kind,
                native_ref=f"axes:0.{backend_kind}:{index - 1}",
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


class K15HistogramRenderer:
    profile_id = "K15"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        histogram = k15_histogram(document, data)
        state = _state(document, actions, histogram.value_field_name, "Count")
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        axis.bar(
            histogram.center,
            histogram.height,
            width=np.asarray(histogram.right) - np.asarray(histogram.left),
            align="center",
            color=state.series[0].color,
            edgecolor="#1A1A1A",
            linewidth=state.series[0].line_width_pt,
            label=histogram.value_field_name,
        )
        _finish(axis, figure, state, png_path, svg_path)
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=_objects(document, "histogram_series", 1),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(asdict(state)),
        )


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


def _state(
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
    x_label: str,
    y_label: str,
) -> _State:
    document.plot_id.removeprefix("plot:")
    state = _State(
        title="",
        x_axis=_AxisState(x_label),
        y_axis=_AxisState(y_label),
        series=(_SeriesState(_PALETTE[0]),),
    )
    max(
        (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
        default=-1,
    )
    for _index, action in enumerate(actions):
        if isinstance(action, (CreatePlot, BindFields)):
            continue
        raise ValueError(f"K15 renderer cannot apply {action.operation}")
    return state

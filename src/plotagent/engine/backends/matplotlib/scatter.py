"""Independent K03 grouped-scatter renderer with dynamic series identities."""

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
from plotagent.engine.profile_data import k03_scatter
from plotagent.engine.repository import document_ref

_PALETTE = (
    "#1676D2",
    "#D97800",
    "#299764",
    "#C53D4D",
    "#7656B5",
    "#008A99",
    "#A55A2A",
    "#667085",
)


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
    symbol: str = "circle"
    symbol_size_pt: float = 5.0


@dataclass(frozen=True, slots=True)
class _K03State:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    series: tuple[_SeriesState, ...]
    legend_visible: bool = False


class K03ScatterRenderer:
    profile_id = "K03"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        scatter = k03_scatter(document, data)
        state = self._state(
            document,
            actions,
            scatter.x_field_name,
            scatter.y_field_name,
            len(scatter.groups),
        )

        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        artists = []
        for group, style in zip(scatter.groups, state.series, strict=True):
            artist = axis.scatter(
                group.x_values,
                group.y_values,
                color=style.color,
                marker=self._marker(style.symbol),
                s=style.symbol_size_pt**2,
                label=group.label,
            )
            artists.append(artist)
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
        series_objects = tuple(
            EngineObjectRef(
                semantic_id=f"series:{token}.group_{index}",
                backend="matplotlib",
                object_kind="scatter_series",
                native_ref=f"axes:0.collection:{index - 1}",
            )
            for index in range(1, len(artists) + 1)
        )
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
            *series_objects,
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
            raise ValueError(f"K03 does not support symbol {symbol}") from error

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        scale = "log" if state.scale == "log10" else state.scale
        if scale not in {"linear", "log"}:
            raise ValueError(f"K03 does not support {state.scale} on the {name} axis")
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
        group_count: int,
    ) -> _K03State:
        document.plot_id.removeprefix("plot:")
        state = _K03State(
            title="",
            x_axis=_AxisState(x_name),
            y_axis=_AxisState(y_name),
            series=tuple(
                _SeriesState(color=_PALETTE[index % len(_PALETTE)]) for index in range(group_count)
            ),
            legend_visible=group_count > 1,
        )
        max(
            (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
            default=-1,
        )
        for _index, action in enumerate(actions):
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"K03 renderer cannot apply {action.operation}")
        return state

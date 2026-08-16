"""Independent K01 Matplotlib renderer; no legacy resolver is involved."""

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
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"] = "linear"
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _LineState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    color: str = "#1676D2"
    line_width_pt: float = 1.5
    line_style: str = "solid"
    symbol: str = "none"
    symbol_size_pt: float = 5.0
    legend_visible: bool = False
    legend_anchor: str = "inside"


class K01LineRenderer:
    profile_id = "K01"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        columns = {column.field.field_id: column for column in data.columns}
        bindings = {binding.role: binding.field_id for binding in document.bindings}
        x_column = columns[bindings["x"]]
        y_column = columns[bindings["y"]]
        state = self._state(document, actions, x_column.field.name, y_column.field.name)
        x = self._numeric(x_column.values, role="x")
        y = self._numeric(y_column.values, role="y")

        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        marker = None if state.symbol == "none" else self._marker(state.symbol)
        (line,) = axis.plot(
            x,
            y,
            color=state.color,
            linewidth=state.line_width_pt,
            linestyle=self._line_style(state.line_style),
            marker=marker,
            markersize=state.symbol_size_pt,
            label=y_column.field.name,
        )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_axis.label)
        axis.set_ylabel(state.y_axis.label)
        self._apply_axis(axis, "x", state.x_axis)
        self._apply_axis(axis, "y", state.y_axis)
        if state.legend_visible:
            placements: dict[str, dict[str, object]] = {
                "inside": {"loc": "best"},
                "right": {"loc": "center left", "bbox_to_anchor": (1.02, 0.5)},
                "bottom": {"loc": "upper center", "bbox_to_anchor": (0.5, -0.15)},
                "none": {},
            }
            placement = placements[state.legend_anchor]
            if state.legend_anchor != "none":
                axis.legend(**placement)
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
                object_kind="line",
                native_ref=f"axes:0.line:{line.get_gid() or 0}",
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
    def _numeric(values: tuple[object, ...], *, role: str) -> np.ndarray:
        result: list[float] = []
        for value in values:
            if value is None:
                result.append(float("nan"))
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"K01 {role} values must be numeric")
            else:
                result.append(float(value))
        return np.asarray(result, dtype=float)

    @staticmethod
    def _marker(symbol: str) -> str:
        return {"circle": "o", "square": "s", "triangle": "^", "diamond": "D"}.get(
            symbol,
            symbol,
        )

    @staticmethod
    def _line_style(style: str) -> str:
        return {
            "solid": "-",
            "dash": "--",
            "dot": ":",
            "dash_dot": "-.",
            "none": "",
        }[style]

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        scale = "log" if state.scale == "log10" else state.scale
        if scale not in {"linear", "log"}:
            raise ValueError(f"K01 does not support {state.scale} on the {name} axis")
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
    ) -> _LineState:
        document.plot_id.removeprefix("plot:")
        state = _LineState(title="", x_axis=_AxisState(x_name), y_axis=_AxisState(y_name))
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"K01 Matplotlib renderer cannot apply {action.operation}")
        return state

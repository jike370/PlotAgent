"""Independent K08 Matplotlib renderer."""

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
class _ColumnState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    color: str = "#1676D2"
    edge_width_pt: float = 0.8
    legend_visible: bool = False


class K08ColumnRenderer:
    profile_id = "K08"

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
        categories = columns[bindings["category"]]
        values = columns[bindings["value"]]
        state = self._state(document, actions, categories.field.name, values.field.name)
        labels = tuple("" if value is None else str(value) for value in categories.values)
        heights = self._numeric(values.values)
        positions = np.arange(len(labels), dtype=float)

        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        bars = axis.bar(
            positions,
            heights,
            width=0.8,
            color=state.color,
            edgecolor="#1A1A1A",
            linewidth=state.edge_width_pt,
            label=values.field.name,
        )
        axis.set_xticks(positions, labels)
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
                object_kind="column_series",
                native_ref=f"axes:0.bar_container:{len(bars)}",
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
    def _numeric(values: tuple[object, ...]) -> np.ndarray:
        result: list[float] = []
        for value in values:
            if value is None:
                result.append(float("nan"))
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("K08 value data must be numeric")
            else:
                result.append(float(value))
        return np.asarray(result, dtype=float)

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        if name == "x" and state.scale not in {"linear", "categorical"}:
            raise ValueError("K08 category axis supports only categorical scale")
        if name == "y":
            scale = "log" if state.scale == "log10" else state.scale
            if scale not in {"linear", "log"}:
                raise ValueError("K08 value axis supports only linear or log10 scale")
            axis.set_yscale(scale)
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        category_name: str,
        value_name: str,
    ) -> _ColumnState:
        document.plot_id.removeprefix("plot:")
        state = _ColumnState(
            title="",
            x_axis=_AxisState(category_name, scale="categorical"),
            y_axis=_AxisState(value_name),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"K08 renderer cannot apply {action.operation}")
        return state

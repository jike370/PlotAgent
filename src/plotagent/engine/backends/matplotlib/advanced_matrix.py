"""Independent K21 correlation and K22 contour Matplotlib renderers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetChartParameter,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import k21_correlation_grid, k22_regular_grid
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _MatrixState:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False
    triangle: Literal["full", "lower", "upper"] = "full"
    levels: int = 12
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None


def _objects(document: PlotDocument, kind: str) -> tuple[EngineObjectRef, ...]:
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
        EngineObjectRef(
            semantic_id=f"series:{token}.matrix",
            backend="matplotlib",
            object_kind=kind,
            native_ref="axes:0.collection:0",
        ),
    )


class K21CorrelationMatrixRenderer:
    profile_id = "K21"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        grid = k21_correlation_grid(document, data)
        state = self._state(document, actions, grid.row_field_name, grid.column_field_name)
        values = np.asarray(grid.values, dtype=float)
        if state.triangle == "lower":
            values = np.where(np.tri(len(grid.row_labels), dtype=bool), values, np.nan)
        elif state.triangle == "upper":
            values = np.where(np.triu(np.ones(values.shape, dtype=bool)), values, np.nan)

        figure, axis = plt.subplots(figsize=(6.4, 5.6), constrained_layout=True)
        image = axis.imshow(values, cmap="coolwarm", vmin=-1.0, vmax=1.0, origin="upper")
        axis.set_xticks(np.arange(len(grid.column_labels)), grid.column_labels, rotation=45)
        axis.set_yticks(np.arange(len(grid.row_labels)), grid.row_labels)
        for row_index, row in enumerate(values):
            for column_index, value in enumerate(row):
                if np.isfinite(value):
                    color = "white" if abs(float(value)) >= 0.55 else "black"
                    axis.text(
                        column_index,
                        row_index,
                        f"{value:.2f}",
                        ha="center",
                        va="center",
                        color=color,
                    )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_label)
        axis.set_ylabel(state.y_label)
        if state.x_reverse:
            axis.invert_xaxis()
        if state.y_reverse:
            axis.invert_yaxis()
        figure.colorbar(image, ax=axis, label=grid.value_field_name)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(png_path, dpi=160)
        figure.savefig(svg_path)
        plt.close(figure)
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=_objects(document, "correlation_matrix"),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(asdict(state)),
        )

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        row_name: str,
        column_name: str,
    ) -> _MatrixState:
        token = document.plot_id.removeprefix("plot:")
        state = _MatrixState(title="", x_label=column_name, y_label=row_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K21 title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
                if axis_name is None:
                    raise ValueError("K21 axis target does not belong to this plot")
                if action.scale not in {None, "categorical"}:
                    raise ValueError("K21 axes require categorical scale")
                if action.minimum is not None or action.maximum is not None:
                    raise ValueError("K21 public axes do not expose numeric bounds")
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
            elif isinstance(action, SetChartParameter):
                if action.target != document.plot_id or action.parameter != "triangle":
                    raise ValueError("K21 exposes only the triangle chart parameter")
                if action.value not in {"full", "lower", "upper"}:
                    raise ValueError("K21 triangle must be full, lower or upper")
                state = replace(
                    state,
                    triangle=cast(Literal["full", "lower", "upper"], action.value),
                )
            else:
                raise ValueError(f"K21 Matplotlib renderer cannot apply {action.operation}")
        return state


class K22ContourRenderer:
    profile_id = "K22"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        grid = k22_regular_grid(document, data)
        state = self._state(document, actions, grid.x_field_name, grid.y_field_name)
        x_grid, y_grid = np.meshgrid(grid.x_values, grid.y_values)
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        contour = axis.contourf(
            x_grid,
            y_grid,
            np.asarray(grid.z_values),
            levels=state.levels,
            cmap="viridis",
        )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_label)
        axis.set_ylabel(state.y_label)
        if state.x_minimum is not None and state.x_maximum is not None:
            axis.set_xlim(state.x_minimum, state.x_maximum)
        if state.y_minimum is not None and state.y_maximum is not None:
            axis.set_ylim(state.y_minimum, state.y_maximum)
        if state.x_reverse:
            axis.invert_xaxis()
        if state.y_reverse:
            axis.invert_yaxis()
        color_label = (
            grid.z_field_name
            if grid.z_unit is None
            else f"{grid.z_field_name} ({grid.z_unit})"
        )
        figure.colorbar(contour, ax=axis, label=color_label)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(png_path, dpi=160)
        figure.savefig(svg_path)
        plt.close(figure)
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=_objects(document, "filled_contour"),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(asdict(state)),
        )

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        x_name: str,
        y_name: str,
    ) -> _MatrixState:
        token = document.plot_id.removeprefix("plot:")
        state = _MatrixState(title="", x_label=x_name, y_label=y_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K22 title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
                if axis_name is None:
                    raise ValueError("K22 axis target does not belong to this plot")
                if action.scale not in {None, "linear"}:
                    raise ValueError("K22 axes require linear scale")
                if axis_name == "x":
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_minimum=action.minimum,
                        x_maximum=action.maximum,
                        x_reverse=state.x_reverse if action.reverse is None else action.reverse,
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_minimum=action.minimum,
                        y_maximum=action.maximum,
                        y_reverse=state.y_reverse if action.reverse is None else action.reverse,
                    )
            elif isinstance(action, SetChartParameter):
                if action.target != document.plot_id or action.parameter != "levels":
                    raise ValueError("K22 exposes only the levels chart parameter")
                if (
                    isinstance(action.value, bool)
                    or not isinstance(action.value, int)
                    or not 2 <= action.value <= 64
                ):
                    raise ValueError("K22 levels must be an integer from 2 to 64")
                state = replace(state, levels=action.value)
            else:
                raise ValueError(f"K22 Matplotlib renderer cannot apply {action.operation}")
        return state

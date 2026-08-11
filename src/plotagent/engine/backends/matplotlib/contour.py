"""Independent K22 regular-grid filled-contour Matplotlib renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

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
from plotagent.engine.profile_data import RegularGridData, k22_regular_grid
from plotagent.engine.repository import document_ref

from .font import resolve_font_family


@dataclass(frozen=True, slots=True)
class _K22State:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False
    levels: int = 12
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None


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
        state = self._state(document, actions, grid)
        x_grid, y_grid = np.meshgrid(grid.x_values, grid.y_values)
        boundaries = np.linspace(
            min(value for row in grid.z_values for value in row),
            max(value for row in grid.z_values for value in row),
            state.levels + 1,
        )
        color_label = (
            grid.z_field_name
            if grid.z_unit is None
            else f"{grid.z_field_name} ({grid.z_unit})"
        )
        font_family = resolve_font_family(
            (state.title, state.x_label, state.y_label, color_label)
        )
        with matplotlib.rc_context({"font.family": font_family}):
            figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
            contour = axis.contourf(
                x_grid,
                y_grid,
                np.asarray(grid.z_values, dtype=float),
                levels=boundaries,
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
            colorbar = figure.colorbar(contour, ax=axis)
            colorbar.set_label(color_label)
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
                    semantic_id=f"series:{token}.matrix",
                    backend="matplotlib",
                    object_kind="filled_contour",
                    native_ref="axes:0.contour:0",
                ),
                EngineObjectRef(
                    semantic_id=f"legend:{token}.colorbar",
                    backend="matplotlib",
                    object_kind="colorbar",
                    native_ref="axes:1.colorbar",
                ),
            ),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(asdict(state)),
        )

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        grid: RegularGridData,
    ) -> _K22State:
        token = document.plot_id.removeprefix("plot:")
        state = _K22State("", grid.x_field_name, grid.y_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K22 title target does not belong to this plot")
                state = replace(state, title=action.text)
                continue
            if isinstance(action, SetAxis):
                axis_name = {
                    f"axis:{token}.x": "x",
                    f"axis:{token}.y": "y",
                }.get(action.target)
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
                        x_reverse=(
                            state.x_reverse if action.reverse is None else action.reverse
                        ),
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_minimum=action.minimum,
                        y_maximum=action.maximum,
                        y_reverse=(
                            state.y_reverse if action.reverse is None else action.reverse
                        ),
                    )
                continue
            if isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "levels"
                    or isinstance(action.value, bool)
                    or not isinstance(action.value, int)
                    or not 2 <= action.value <= 64
                ):
                    raise ValueError("K22 levels must be an integer from 2 to 64")
                state = replace(state, levels=action.value)
                continue
            raise ValueError(f"K22 Matplotlib renderer cannot apply {action.operation}")
        return state

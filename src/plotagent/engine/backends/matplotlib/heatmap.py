"""Independent K20 Matplotlib renderer."""

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
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import K20Grid, k20_grid
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _K20State:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False


class K20HeatmapRenderer:
    profile_id = "K20"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        grid = k20_grid(document, data)
        state = self._state(document, actions, grid)
        values = np.asarray(grid.values, dtype=float)

        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        image = axis.imshow(
            values,
            cmap="cividis",
            interpolation="nearest",
            aspect="auto",
            origin="upper",
        )
        axis.set_xticks(np.arange(len(grid.column_labels)), grid.column_labels)
        axis.set_yticks(np.arange(len(grid.row_labels)), grid.row_labels)
        axis.set_title(state.title)
        axis.set_xlabel(state.x_label)
        axis.set_ylabel(state.y_label)
        if state.x_reverse:
            axis.invert_xaxis()
        if state.y_reverse:
            axis.invert_yaxis()
        colorbar = figure.colorbar(image, ax=axis)
        colorbar.set_label(
            grid.value_field_name
            if grid.value_unit is None
            else f"{grid.value_field_name} ({grid.value_unit})"
        )
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
                object_kind="heatmap_series",
                native_ref="axes:0.image:0",
            ),
            EngineObjectRef(
                semantic_id=f"legend:{token}.colorbar",
                backend="matplotlib",
                object_kind="colorbar",
                native_ref="axes:1.colorbar",
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
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        grid: K20Grid,
    ) -> _K20State:
        token = document.plot_id.removeprefix("plot:")
        state = _K20State(title="", x_label=grid.column_field_name, y_label=grid.row_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K20 title target does not belong to this plot")
                state = replace(state, title=action.text)
                continue
            if isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(
                    action.target
                )
                if axis_name is None:
                    raise ValueError("K20 axis target does not belong to this plot")
                if action.scale not in {None, "categorical"}:
                    raise ValueError("K20 axes support only categorical scale")
                if action.minimum is not None or action.maximum is not None:
                    raise ValueError("K20 public axes do not expose numeric bounds")
                if axis_name == "x":
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_reverse=(
                            state.x_reverse if action.reverse is None else action.reverse
                        ),
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_reverse=(
                            state.y_reverse if action.reverse is None else action.reverse
                        ),
                    )
                continue
            raise ValueError(f"K20 Matplotlib renderer cannot apply {action.operation}")
        return state

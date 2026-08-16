"""Independent S61 confusion-matrix Matplotlib renderer."""

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
    SetChartParameter,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import K20Grid, s61_confusion_grid
from plotagent.engine.repository import document_ref

from .font import resolve_font_family


@dataclass(frozen=True, slots=True)
class _S61State:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False
    show_counts: bool = True


class S61ConfusionRenderer:
    """Render the supplied count table without changing its aggregation semantics."""

    profile_id = "S61"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        grid = s61_confusion_grid(document, data)
        state = self._state(document, actions, grid)
        values = np.asarray(grid.values, dtype=float)
        font_family = resolve_font_family(
            (
                state.title,
                state.x_label,
                state.y_label,
                grid.value_field_name,
                *grid.column_labels,
                *grid.row_labels,
            )
        )
        with matplotlib.rc_context({"font.family": font_family}):
            figure, axis = plt.subplots(figsize=(6.2, 5.4), constrained_layout=True)
            maximum = max(1.0, float(np.nanmax(values)))
            image = axis.imshow(
                values,
                cmap="Blues",
                vmin=0.0,
                vmax=maximum,
                interpolation="nearest",
                origin="upper",
            )
            axis.set_xticks(np.arange(len(grid.column_labels)), grid.column_labels)
            axis.set_yticks(np.arange(len(grid.row_labels)), grid.row_labels)
            if state.show_counts:
                for row_index, row in enumerate(values):
                    for column_index, value in enumerate(row):
                        axis.text(
                            column_index,
                            row_index,
                            f"{value:g}",
                            ha="center",
                            va="center",
                            color="white" if float(value) > maximum / 2.0 else "black",
                        )
            axis.set_title(state.title)
            axis.set_xlabel(state.x_label)
            axis.set_ylabel(state.y_label)
            if state.x_reverse:
                axis.invert_xaxis()
            if state.y_reverse:
                axis.invert_yaxis()
            colorbar = figure.colorbar(image, ax=axis)
            colorbar.set_label(grid.value_field_name)
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
                    object_kind="confusion_matrix",
                    native_ref="axes:0.image:0",
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
        grid: K20Grid,
    ) -> _S61State:
        document.plot_id.removeprefix("plot:")
        state = _S61State("", grid.column_field_name, grid.row_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "show_counts"
                    or (not isinstance(action.value, bool))
                ):
                    raise ValueError("S61 show_counts must be boolean")
                state = replace(state, show_counts=action.value)
                continue
            raise ValueError(f"S61 Matplotlib renderer cannot apply {action.operation}")
        return state

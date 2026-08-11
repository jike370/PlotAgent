"""Independent K21 correlation-matrix Matplotlib renderer."""

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
from plotagent.engine.profile_data import K20Grid, k21_correlation_grid
from plotagent.engine.repository import document_ref

from .font import resolve_font_family


@dataclass(frozen=True, slots=True)
class _K21State:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False
    triangle: Literal["full", "lower", "upper"] = "full"


def _display_values(grid: K20Grid, triangle: str) -> np.ndarray:
    """Return a display-only mask; the supplied matrix remains untouched."""

    values = np.asarray(grid.values, dtype=float)
    if triangle == "lower":
        return np.ma.masked_where(~np.tri(len(grid.row_labels), dtype=bool), values)
    if triangle == "upper":
        return np.ma.masked_where(
            ~np.triu(np.ones(values.shape, dtype=bool)),
            values,
        )
    return values


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
        state = self._state(document, actions, grid)
        display_values = _display_values(grid, state.triangle)
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
            figure, axis = plt.subplots(figsize=(6.4, 5.6), constrained_layout=True)
            image = axis.imshow(
                display_values,
                cmap="coolwarm",
                vmin=-1.0,
                vmax=1.0,
                interpolation="nearest",
                origin="upper",
            )
            axis.set_xticks(
                np.arange(len(grid.column_labels)),
                grid.column_labels,
                rotation=45,
                ha="right",
            )
            axis.set_yticks(np.arange(len(grid.row_labels)), grid.row_labels)
            visible = ~np.ma.getmaskarray(display_values)
            raw_values = np.asarray(grid.values, dtype=float)
            for row_index, row in enumerate(raw_values):
                for column_index, value in enumerate(row):
                    if visible[row_index, column_index]:
                        axis.text(
                            column_index,
                            row_index,
                            f"{value:.2f}",
                            ha="center",
                            va="center",
                            color="white" if abs(float(value)) >= 0.55 else "black",
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
                    object_kind="correlation_matrix",
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
    ) -> _K21State:
        token = document.plot_id.removeprefix("plot:")
        state = _K21State("", grid.column_field_name, grid.row_field_name)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K21 title target does not belong to this plot")
                state = replace(state, title=action.text)
                continue
            if isinstance(action, SetAxis):
                axis_name = {
                    f"axis:{token}.x": "x",
                    f"axis:{token}.y": "y",
                }.get(action.target)
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
            if isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "triangle"
                    or action.value not in {"full", "lower", "upper"}
                ):
                    raise ValueError("K21 exposes triangle=full|lower|upper")
                state = replace(
                    state,
                    triangle=cast(
                        Literal["full", "lower", "upper"], action.value
                    ),
                )
                continue
            raise ValueError(
                f"K21 Matplotlib renderer cannot apply {action.operation}"
            )
        return state

"""Independent X09 Floating Column renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

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
from plotagent.engine.product_style import (
    PRODUCT_TYPOGRAPHY,
    X09_FLOATING_COLUMN_STYLE,
    x09_auto_range_bounds,
)
from plotagent.engine.profile_data import FloatingIntervalData, x09_floating_intervals
from plotagent.engine.repository import document_ref

from .font import resolve_font_family


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"]
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _FloatingState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    legend_visible: bool = True


class X09FloatingIntervalRenderer:
    """Mirror Origin FLOATCOL semantics without sorting its boundary columns."""

    profile_id = "X09"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        intervals = x09_floating_intervals(document, data)
        state = self._state(document, actions, intervals)
        positions = np.arange(len(intervals.categories), dtype=float)
        font_family = resolve_font_family(
            (
                state.title,
                state.x_axis.label,
                state.y_axis.label,
                *intervals.categories,
                intervals.start_field_name,
                intervals.end_field_name,
                intervals.middle_field_name or "",
            )
        )
        with matplotlib.rc_context(
            {"font.family": font_family, **PRODUCT_TYPOGRAPHY.matplotlib_rc()}
        ):
            figure, axis = plt.subplots(figsize=(6.4, 4.8), layout="constrained")
            semantic_target = f"series:{document.plot_id.removeprefix('plot:')}.primary"
            if intervals.middle_values is None:
                interval_containers = (
                    axis.bar(
                        positions,
                        np.subtract(intervals.end_values, intervals.start_values),
                        bottom=intervals.start_values,
                        width=X09_FLOATING_COLUMN_STYLE.bar_width_fraction,
                        color=X09_FLOATING_COLUMN_STYLE.interval_colors[0],
                        edgecolor=X09_FLOATING_COLUMN_STYLE.border_color,
                        linewidth=X09_FLOATING_COLUMN_STYLE.border_width_pt,
                        label=intervals.end_field_name,
                    ),
                )
            else:
                interval_containers = (
                    axis.bar(
                        positions,
                        np.subtract(intervals.middle_values, intervals.start_values),
                        bottom=intervals.start_values,
                        width=X09_FLOATING_COLUMN_STYLE.bar_width_fraction,
                        color=X09_FLOATING_COLUMN_STYLE.interval_colors[0],
                        edgecolor=X09_FLOATING_COLUMN_STYLE.border_color,
                        linewidth=X09_FLOATING_COLUMN_STYLE.border_width_pt,
                        label=intervals.middle_field_name,
                    ),
                    axis.bar(
                        positions,
                        np.subtract(intervals.end_values, intervals.middle_values),
                        bottom=intervals.middle_values,
                        width=X09_FLOATING_COLUMN_STYLE.bar_width_fraction,
                        color=X09_FLOATING_COLUMN_STYLE.interval_colors[1],
                        edgecolor=X09_FLOATING_COLUMN_STYLE.border_color,
                        linewidth=X09_FLOATING_COLUMN_STYLE.border_width_pt,
                        label=intervals.end_field_name,
                    ),
                )
            # ``series.primary`` is one public interval series even when an
            # optional middle boundary materializes two native bar
            # containers.  Tag every member so the shared visual adapter can
            # apply one public action to the complete visible object.
            for container in interval_containers:
                cast(Any, container)._plotagent_semantic_target = semantic_target
            axis.set_xticks(positions, intervals.categories)
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
                    semantic_id=f"series:{token}.primary",
                    backend="matplotlib",
                    object_kind="floating_column_group",
                    native_ref="axes:0.bar_containers",
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
        if name == "x" and state.scale != "categorical":
            raise ValueError("X09 horizontal category axis supports only categorical scale")
        if name == "y":
            if state.scale not in {"linear", "log10"}:
                raise ValueError("X09 vertical value axis supports linear or log10")
            axis.set_yscale("log" if state.scale == "log10" else "linear")
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        intervals: FloatingIntervalData,
    ) -> _FloatingState:
        document.plot_id.removeprefix("plot:")
        boundary_columns = [intervals.start_values, intervals.end_values]
        if intervals.middle_values is not None:
            boundary_columns.insert(1, intervals.middle_values)
        y_minimum, y_maximum = x09_auto_range_bounds(tuple(boundary_columns))
        state = _FloatingState(
            title="",
            x_axis=_AxisState(intervals.category_field_name, "categorical"),
            y_axis=_AxisState(
                f"{intervals.start_field_name}–{intervals.end_field_name}",
                "linear",
                y_minimum,
                y_maximum,
            ),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"X09 renderer cannot apply {action.operation}")
        return state

"""Independent X09 Floating Bar renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
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
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
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
class _SegmentStyle:
    color: str
    edge_width_pt: float = 0.8


@dataclass(frozen=True, slots=True)
class _FloatingState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    lower: _SegmentStyle = _SegmentStyle("#1676D2")
    upper: _SegmentStyle = _SegmentStyle("#D97800")
    legend_visible: bool = True


class X09FloatingIntervalRenderer:
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
        with matplotlib.rc_context({"font.family": font_family}):
            figure, axis = plt.subplots(figsize=(6.4, 4.8), layout="constrained")
            if intervals.middle_values is None:
                axis.barh(
                    positions,
                    np.subtract(intervals.end_values, intervals.start_values),
                    left=intervals.start_values,
                    height=0.72,
                    color=state.lower.color,
                    edgecolor="#1A1A1A",
                    linewidth=state.lower.edge_width_pt,
                    label=intervals.end_field_name,
                )
                segment_count = 1
            else:
                axis.barh(
                    positions,
                    np.subtract(intervals.middle_values, intervals.start_values),
                    left=intervals.start_values,
                    height=0.72,
                    color=state.lower.color,
                    edgecolor="#1A1A1A",
                    linewidth=state.lower.edge_width_pt,
                    label=intervals.middle_field_name,
                )
                axis.barh(
                    positions,
                    np.subtract(intervals.end_values, intervals.middle_values),
                    left=intervals.middle_values,
                    height=0.72,
                    color=state.upper.color,
                    edgecolor="#1A1A1A",
                    linewidth=state.upper.edge_width_pt,
                    label=intervals.end_field_name,
                )
                segment_count = 2
            axis.set_yticks(positions, intervals.categories)
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
        objects = [
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
                semantic_id=f"series:{token}.lower",
                backend="matplotlib",
                object_kind="floating_bar_segment",
                native_ref="axes:0.bar_container:0",
            ),
        ]
        if segment_count == 2:
            objects.append(
                EngineObjectRef(
                    semantic_id=f"series:{token}.upper",
                    backend="matplotlib",
                    object_kind="floating_bar_segment",
                    native_ref="axes:0.bar_container:1",
                )
            )
        objects.append(
            EngineObjectRef(
                semantic_id=f"legend:{token}.main",
                backend="matplotlib",
                object_kind="legend",
                native_ref="axes:0.legend",
            )
        )
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(asdict(state)),
        )

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        if name == "x":
            if state.scale not in {"linear", "log10"}:
                raise ValueError("X09 horizontal value axis supports linear or log10")
            axis.set_xscale("log" if state.scale == "log10" else "linear")
        if name == "y" and state.scale != "categorical":
            raise ValueError("X09 vertical category axis supports only categorical scale")
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
        token = document.plot_id.removeprefix("plot:")
        state = _FloatingState(
            title="",
            x_axis=_AxisState(
                f"{intervals.start_field_name}–{intervals.end_field_name}", "linear"
            ),
            y_axis=_AxisState(intervals.category_field_name, "categorical"),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("X09 title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                attribute = {
                    f"axis:{token}.x": "x_axis",
                    f"axis:{token}.y": "y_axis",
                }.get(action.target)
                if attribute is None:
                    raise ValueError("X09 axis target does not belong to this plot")
                current = getattr(state, attribute)
                state = replace(
                    state,
                    **{
                        attribute: replace(
                            current,
                            label=current.label if action.label is None else action.label,
                            scale=current.scale if action.scale is None else action.scale,
                            minimum=current.minimum if action.minimum is None else action.minimum,
                            maximum=current.maximum if action.maximum is None else action.maximum,
                            reverse=current.reverse if action.reverse is None else action.reverse,
                        )
                    },
                )
            elif isinstance(action, SetSeriesStyle):
                attribute = {
                    f"series:{token}.lower": "lower",
                    f"series:{token}.upper": "upper",
                }.get(action.target)
                if attribute is None or (attribute == "upper" and intervals.middle_values is None):
                    raise ValueError("X09 series target is outside the bound interval data")
                if any(
                    value is not None
                    for value in (action.line_style, action.symbol, action.symbol_size_pt)
                ):
                    raise ValueError("X09 exposes interval fill color and edge width only")
                current = getattr(state, attribute)
                state = replace(
                    state,
                    **{
                        attribute: replace(
                            current,
                            color=current.color if action.color is None else action.color,
                            edge_width_pt=(
                                current.edge_width_pt
                                if action.line_width_pt is None
                                else action.line_width_pt
                            ),
                        )
                    },
                )
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("X09 legend target or anchor is not supported")
                state = replace(
                    state,
                    legend_visible=(
                        state.legend_visible if action.visible is None else action.visible
                    ),
                )
            else:
                raise ValueError(f"X09 renderer cannot apply {action.operation}")
        return state

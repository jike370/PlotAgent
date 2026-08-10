"""Independent K07 center-line and error-band renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
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
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import k07_error_band
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"] = "linear"
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _K07State:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    color: str = "#1676D2"
    line_width_pt: float = 1.5
    line_style: str = "solid"
    legend_visible: bool = False
    legend_anchor: str = "inside"


class K07ErrorBandRenderer:
    profile_id = "K07"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = k07_error_band(document, data)
        state = self._state(document, actions, series.x_field_name, series.center_field_name)

        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        band = axis.fill_between(
            series.x_values,
            series.lower_values,
            series.upper_values,
            color=state.color,
            alpha=0.25,
            linewidth=0,
            label="_nolegend_",
        )
        (line,) = axis.plot(
            series.x_values,
            series.center_values,
            color=state.color,
            linewidth=state.line_width_pt,
            linestyle=self._line_style(state.line_style),
            label=series.center_field_name,
        )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_axis.label)
        axis.set_ylabel(state.y_axis.label)
        self._apply_axis(axis, "x", state.x_axis)
        self._apply_axis(axis, "y", state.y_axis)
        self._apply_legend(axis, state)
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
                object_kind="error_band_series",
                native_ref=f"axes:0.line:{line.get_gid() or 0}.band:{band.get_gid() or 0}",
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
            raise ValueError(f"K07 does not support {state.scale} on the {name} axis")
        getattr(axis, f"set_{name}scale")(scale)
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    @staticmethod
    def _apply_legend(axis: Axes, state: _K07State) -> None:
        placements: dict[str, dict[str, object]] = {
            "inside": {"loc": "best"},
            "right": {"loc": "center left", "bbox_to_anchor": (1.02, 0.5)},
            "bottom": {"loc": "upper center", "bbox_to_anchor": (0.5, -0.15)},
        }
        if state.legend_visible and state.legend_anchor != "none":
            axis.legend(**placements[state.legend_anchor])

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        x_name: str,
        center_name: str,
    ) -> _K07State:
        token = document.plot_id.removeprefix("plot:")
        state = _K07State(
            title="",
            x_axis=_AxisState(x_name),
            y_axis=_AxisState(center_name),
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K07 title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x_axis", f"axis:{token}.y": "y_axis"}.get(
                    action.target
                )
                if axis_name is None:
                    raise ValueError("K07 axis target does not belong to this plot")
                current = getattr(state, axis_name)
                bounds = (
                    (current.minimum, current.maximum)
                    if action.minimum is None
                    else (action.minimum, action.maximum)
                )
                state = replace(
                    state,
                    **{
                        axis_name: replace(
                            current,
                            label=current.label if action.label is None else action.label,
                            scale=current.scale if action.scale is None else action.scale,
                            minimum=bounds[0],
                            maximum=bounds[1],
                            reverse=current.reverse if action.reverse is None else action.reverse,
                        )
                    },
                )
            elif isinstance(action, SetSeriesStyle):
                if action.target != f"series:{token}.primary":
                    raise ValueError("K07 series target does not belong to this plot")
                state = replace(
                    state,
                    color=state.color if action.color is None else action.color,
                    line_width_pt=(
                        state.line_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt
                    ),
                    line_style=(
                        state.line_style if action.line_style is None else action.line_style
                    ),
                )
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main":
                    raise ValueError("K07 legend target does not belong to this plot")
                state = replace(
                    state,
                    legend_visible=(
                        state.legend_visible if action.visible is None else action.visible
                    ),
                    legend_anchor=state.legend_anchor if action.anchor is None else action.anchor,
                )
            else:
                raise ValueError(f"K07 renderer cannot apply {action.operation}")
        return state

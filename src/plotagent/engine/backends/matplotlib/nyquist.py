"""Independent S34 Nyquist Matplotlib renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetChartParameter,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import NyquistData, s34_nyquist
from plotagent.engine.repository import document_ref

from .font import resolve_font_family

_COLORS = ("#2A6FDB", "#D94B4B", "#2A9D6F", "#8A5CC2", "#D88700")
_LINE_STYLE: dict[str, Literal["-", "--", ":", "-.", ""]] = {
    "solid": "-",
    "dash": "--",
    "dot": ":",
    "dash_dot": "-.",
    "none": "",
}
_SYMBOL = {"circle": "o", "square": "s", "diamond": "D", "triangle": "^", "plus": "+"}


@dataclass(frozen=True, slots=True)
class _AxesState:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None
    x_reverse: bool = False
    y_reverse: bool = False


@dataclass(frozen=True, slots=True)
class _Style:
    color: str | None = None
    line_width_pt: float | None = None
    line_style: str | None = None
    symbol: str | None = None
    symbol_size_pt: float | None = None


class S34NyquistRenderer:
    """Render the same declarative S34 actions as the native Origin binder."""

    profile_id = "S34"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        nyquist = s34_nyquist(document, data)
        axes, styles, legend_visible, equal_axes = self._state(document, actions, nyquist)
        font = resolve_font_family(
            (
                axes.title,
                axes.x_label,
                axes.y_label,
                *(series.label for series in nyquist.series),
            )
        )
        with matplotlib.rc_context({"font.family": font}):
            figure, axis = plt.subplots(figsize=(6.2, 5.4), constrained_layout=True)
            token = document.plot_id.removeprefix("plot:")
            objects: list[EngineObjectRef] = [
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
                    semantic_id=f"legend:{token}.main",
                    backend="matplotlib",
                    object_kind="legend",
                    native_ref="axes:0.legend",
                ),
            ]
            for index, (series, style) in enumerate(
                zip(nyquist.series, styles, strict=True)
            ):
                axis.plot(
                    series.z_real,
                    series.z_imaginary,
                    color=style.color or _COLORS[index % len(_COLORS)],
                    linewidth=style.line_width_pt or 1.5,
                    linestyle=_LINE_STYLE[style.line_style or "solid"],
                    marker=_SYMBOL[style.symbol or "circle"],
                    markersize=style.symbol_size_pt or 6.0,
                    label=series.label,
                )
                objects.append(
                    EngineObjectRef(
                        semantic_id=f"series:{token}.group_{index + 1}",
                        backend="matplotlib",
                        object_kind="nyquist_series",
                        native_ref=f"axes:0.line:{index}",
                    )
                )
            axis.set_title(axes.title)
            axis.set_xlabel(axes.x_label)
            axis.set_ylabel(axes.y_label)
            if axes.x_minimum is not None and axes.x_maximum is not None:
                axis.set_xlim(axes.x_minimum, axes.x_maximum)
            if axes.y_minimum is not None and axes.y_maximum is not None:
                axis.set_ylim(axes.y_minimum, axes.y_maximum)
            if axes.x_reverse:
                axis.invert_xaxis()
            if axes.y_reverse:
                axis.invert_yaxis()
            if equal_axes:
                axis.set_aspect("equal", adjustable="box")
            if legend_visible:
                axis.legend()
            png_path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(png_path, dpi=160)
            figure.savefig(svg_path)
            plt.close(figure)
        return EngineReadback(
            document=document_ref(document),
            backend="matplotlib",
            objects=tuple(objects),
            data_hash=canonical_hash(data),
            style_hash=canonical_hash(
                cast(
                    JsonValue,
                    {
                        "axes": asdict(axes),
                        "styles": [asdict(style) for style in styles],
                        "legend": legend_visible,
                        "equal_axes": equal_axes,
                        "font_family": font,
                    },
                )
            ),
        )

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        nyquist: NyquistData,
    ) -> tuple[_AxesState, tuple[_Style, ...], bool, bool]:
        token = document.plot_id.removeprefix("plot:")
        axes = _AxesState(
            x_label=nyquist.z_real_field_name,
            y_label=nyquist.z_imaginary_field_name,
        )
        styles = tuple(_Style() for _series in nyquist.series)
        legend_visible, equal_axes = len(nyquist.series) > 1, True
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("S34 title target does not belong")
                axes = replace(axes, title=action.text)
            elif isinstance(action, SetAxis):
                if action.scale not in {None, "linear"}:
                    raise ValueError("S34 axes require linear scale")
                axes = _edit_axis(axes, action, token)
            elif isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.group_"
                if not action.target.startswith(prefix):
                    raise ValueError("S34 series target does not belong")
                if action.line_style == "none":
                    raise ValueError("S34 Line + Symbol cannot hide its native line")
                if action.symbol is not None and action.symbol not in _SYMBOL:
                    raise ValueError("S34 symbol is outside the shared renderer vocabulary")
                try:
                    index = int(action.target.removeprefix(prefix)) - 1
                except ValueError as error:
                    raise ValueError("S34 series target requires a numeric ordinal") from error
                if not 0 <= index < len(styles):
                    raise ValueError("S34 series target is outside the current data")
                mutable = list(styles)
                current = mutable[index]
                mutable[index] = replace(
                    current,
                    color=current.color if action.color is None else action.color,
                    line_width_pt=(
                        current.line_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt
                    ),
                    line_style=(
                        current.line_style
                        if action.line_style is None
                        else action.line_style
                    ),
                    symbol=current.symbol if action.symbol is None else action.symbol,
                    symbol_size_pt=(
                        current.symbol_size_pt
                        if action.symbol_size_pt is None
                        else action.symbol_size_pt
                    ),
                )
                styles = tuple(mutable)
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main" or action.anchor is not None:
                    raise ValueError("S34 exposes only legend visibility")
                legend_visible = (
                    legend_visible if action.visible is None else action.visible
                )
            elif isinstance(action, SetChartParameter):
                if (
                    action.target != document.plot_id
                    or action.parameter != "equal_axes"
                    or not isinstance(action.value, bool)
                ):
                    raise ValueError("S34 equal_axes must be boolean")
                equal_axes = action.value
            else:
                raise ValueError(f"S34 Matplotlib renderer cannot apply {action.operation}")
        return axes, styles, legend_visible, equal_axes


def _edit_axis(state: _AxesState, action: SetAxis, token: str) -> _AxesState:
    axis = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(action.target)
    if axis is None:
        raise ValueError("S34 axis target does not belong")
    if axis == "x":
        return replace(
            state,
            x_label=state.x_label if action.label is None else action.label,
            x_minimum=state.x_minimum if action.minimum is None else action.minimum,
            x_maximum=state.x_maximum if action.maximum is None else action.maximum,
            x_reverse=state.x_reverse if action.reverse is None else action.reverse,
        )
    return replace(
        state,
        y_label=state.y_label if action.label is None else action.label,
        y_minimum=state.y_minimum if action.minimum is None else action.minimum,
        y_maximum=state.y_maximum if action.maximum is None else action.maximum,
        y_reverse=state.y_reverse if action.reverse is None else action.reverse,
    )

"""Independent K18 multi-series Area renderer."""

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
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import k18_area_series
from plotagent.engine.repository import document_ref

from .font import resolve_font_family

_LINE_STYLES = {"solid": "-", "dash": "--", "dot": ":", "dash_dot": "-."}
_PALETTE = (
    "#1676D2",
    "#D84A4A",
    "#299764",
    "#7656B5",
    "#D97800",
    "#008A99",
)


@dataclass(frozen=True, slots=True)
class _AreaLineState:
    color: str
    line_width_pt: float = 1.5
    line_style: str = "solid"


@dataclass(frozen=True, slots=True)
class _AreaState:
    title: str
    x_label: str
    y_label: str
    x_scale: str = "linear"
    y_scale: str = "linear"
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None
    x_reverse: bool = False
    y_reverse: bool = False
    areas: tuple[_AreaLineState, ...] = ()
    legend_visible: bool = False


class K18AreaRenderer:
    profile_id = "K18"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = k18_area_series(document, data)
        state = self._state(
            document,
            actions,
            series.x_field_name,
            tuple(item.value_field_name for item in series.series),
        )
        self._validate_log_data(series.x_values, state.x_scale, "x")
        for item in series.series:
            self._validate_log_data(item.values, state.y_scale, item.role)

        font_family = resolve_font_family(
            (
                state.title,
                state.x_label,
                state.y_label,
                *(item.value_field_name for item in series.series),
            )
        )
        with matplotlib.rc_context({"font.family": font_family}):
            figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
            artists: list[tuple[object, object]] = []
            for item, area_state in zip(series.series, state.areas, strict=True):
                fill = axis.fill_between(
                    series.x_values,
                    item.values,
                    0.0,
                    color=area_state.color,
                    alpha=0.35,
                    label=item.value_field_name,
                )
                (boundary,) = axis.plot(
                    series.x_values,
                    item.values,
                    color=area_state.color,
                    linewidth=area_state.line_width_pt,
                    linestyle=_LINE_STYLES[area_state.line_style],
                    label="_nolegend_",
                )
                artists.append((fill, boundary))

            axis.set_title(state.title)
            axis.set_xlabel(state.x_label)
            axis.set_ylabel(state.y_label)
            axis.set_xscale("log" if state.x_scale == "log10" else "linear")
            axis.set_yscale("log" if state.y_scale == "log10" else "linear")
            if state.x_minimum is not None and state.x_maximum is not None:
                axis.set_xlim(state.x_minimum, state.x_maximum)
            if state.y_minimum is not None and state.y_maximum is not None:
                axis.set_ylim(state.y_minimum, state.y_maximum)
            if state.x_reverse:
                axis.invert_xaxis()
            if state.y_reverse:
                axis.invert_yaxis()
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
                *(
                    EngineObjectRef(
                        semantic_id=f"series:{token}.area_{index}",
                        backend="matplotlib",
                        object_kind="area_series",
                        native_ref=f"axes:0.collection:{index - 1}+line:{index - 1}",
                    )
                    for index, _artists in enumerate(artists, start=1)
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
    def _validate_log_data(values: tuple[float, ...], scale: str, role: str) -> None:
        if scale == "log10" and any(np.isfinite(value) and value <= 0 for value in values):
            raise ValueError(f"K18 {role} values must be positive on a log10 axis")

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        x_name: str,
        value_names: tuple[str, ...],
    ) -> _AreaState:
        token = document.plot_id.removeprefix("plot:")
        state = _AreaState(
            title="",
            x_label=x_name,
            y_label=value_names[0] if len(value_names) == 1 else "Value",
            areas=tuple(
                _AreaLineState(color=_PALETTE[index % len(_PALETTE)])
                for index in range(len(value_names))
            ),
            legend_visible=len(value_names) > 1,
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K18 title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x", f"axis:{token}.y": "y"}.get(
                    action.target
                )
                if axis_name is None:
                    raise ValueError("K18 axis target does not belong to this plot")
                if action.scale not in {None, "linear", "log10"}:
                    raise ValueError("K18 axes support only linear or log10 scale")
                if axis_name == "x":
                    state = replace(
                        state,
                        x_label=state.x_label if action.label is None else action.label,
                        x_scale=state.x_scale if action.scale is None else action.scale,
                        x_minimum=(
                            state.x_minimum
                            if action.minimum is None
                            else float(action.minimum)
                        ),
                        x_maximum=(
                            state.x_maximum
                            if action.maximum is None
                            else float(action.maximum)
                        ),
                        x_reverse=(
                            state.x_reverse if action.reverse is None else action.reverse
                        ),
                    )
                else:
                    state = replace(
                        state,
                        y_label=state.y_label if action.label is None else action.label,
                        y_scale=state.y_scale if action.scale is None else action.scale,
                        y_minimum=(
                            state.y_minimum
                            if action.minimum is None
                            else float(action.minimum)
                        ),
                        y_maximum=(
                            state.y_maximum
                            if action.maximum is None
                            else float(action.maximum)
                        ),
                        y_reverse=(
                            state.y_reverse if action.reverse is None else action.reverse
                        ),
                    )
            elif isinstance(action, SetSeriesStyle):
                ordinal = K18AreaRenderer._series_ordinal(
                    action.target, token, len(state.areas)
                )
                if action.symbol is not None or action.symbol_size_pt is not None:
                    raise ValueError("K18 Area does not expose symbol edits")
                if action.line_style == "none":
                    raise ValueError("K18 Area cannot hide its boundary line")
                current = state.areas[ordinal - 1]
                updated = replace(
                    current,
                    color=current.color if action.color is None else action.color,
                    line_width_pt=(
                        current.line_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt
                    ),
                    line_style=(
                        current.line_style if action.line_style is None else action.line_style
                    ),
                )
                areas = list(state.areas)
                areas[ordinal - 1] = updated
                state = replace(state, areas=tuple(areas))
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main":
                    raise ValueError("K18 legend target does not belong to this plot")
                if action.anchor not in {None, "inside"}:
                    raise ValueError("K18 currently exposes only the template legend anchor")
                state = replace(
                    state,
                    legend_visible=(
                        state.legend_visible if action.visible is None else action.visible
                    ),
                )
            else:
                raise ValueError(f"K18 Matplotlib renderer cannot apply {action.operation}")
        return state

    @staticmethod
    def _series_ordinal(target: str, token: str, series_count: int) -> int:
        prefix = f"series:{token}.area_"
        if not target.startswith(prefix):
            raise ValueError("K18 series target does not belong to this plot")
        try:
            ordinal = int(target.removeprefix(prefix))
        except ValueError as error:
            raise ValueError("K18 series target requires a numeric ordinal") from error
        if ordinal < 1 or ordinal > series_count:
            raise ValueError("K18 series target ordinal is outside the bound data")
        return ordinal

"""Independent K18 multi-series Area renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
        document.plot_id.removeprefix("plot:")
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
            raise ValueError(f"K18 Matplotlib renderer cannot apply {action.operation}")
        return state

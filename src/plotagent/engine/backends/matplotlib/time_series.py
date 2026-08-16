"""Independent K19 datetime-series Matplotlib renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import k19_time_series
from plotagent.engine.repository import document_ref

_LINE_STYLES: dict[str, Literal["-", "--", ":", "-.", ""]] = {
    "solid": "-",
    "dash": "--",
    "dot": ":",
    "dash_dot": "-.",
    "none": "",
}
_PALETTE = (
    "#1676D2",
    "#D84A4A",
    "#299764",
    "#7656B5",
    "#D97800",
    "#008A99",
)


@dataclass(frozen=True, slots=True)
class _K19LineState:
    color: str
    line_width_pt: float = 1.5
    line_style: str = "solid"


@dataclass(frozen=True, slots=True)
class _K19State:
    title: str
    x_label: str
    y_label: str
    x_reverse: bool = False
    y_reverse: bool = False
    y_scale: str = "linear"
    y_minimum: float | None = None
    y_maximum: float | None = None
    lines: tuple[_K19LineState, ...] = ()
    legend_visible: bool = False


class K19TimeSeriesRenderer:
    profile_id = "K19"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        series = k19_time_series(document, data)
        state = self._state(
            document,
            actions,
            series.time_field_name,
            tuple(item.value_field_name for item in series.series),
        )
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        lines = []
        for item, line_state in zip(series.series, state.lines, strict=True):
            date_values = mdates.date2num(item.time_values)  # type: ignore[no-untyped-call]
            (line,) = axis.plot(
                date_values,
                item.values,
                color=line_state.color,
                linewidth=line_state.line_width_pt,
                linestyle=_LINE_STYLES[line_state.line_style],
                label=item.value_field_name,
            )
            lines.append(line)
        locator = mdates.AutoDateLocator()  # type: ignore[no-untyped-call]
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(
            mdates.ConciseDateFormatter(locator)  # type: ignore[no-untyped-call]
        )
        axis.set_title(state.title)
        axis.set_xlabel(state.x_label)
        axis.set_ylabel(state.y_label)
        axis.set_yscale(state.y_scale)
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
                        semantic_id=f"series:{token}.line_{index}",
                        backend="matplotlib",
                        object_kind="datetime_line",
                        native_ref=f"axes:0.line:{line.get_gid() or index - 1}",
                    )
                    for index, line in enumerate(lines, start=1)
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
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        time_name: str,
        value_names: tuple[str, ...],
    ) -> _K19State:
        document.plot_id.removeprefix("plot:")
        state = _K19State(
            title="",
            x_label=time_name,
            y_label=value_names[0] if len(value_names) == 1 else "Value",
            lines=tuple(
                _K19LineState(color=_PALETTE[index % len(_PALETTE)])
                for index in range(len(value_names))
            ),
            legend_visible=len(value_names) > 1,
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"K19 Matplotlib renderer cannot apply {action.operation}")
        return state

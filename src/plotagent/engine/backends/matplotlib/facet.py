"""Independent K24 Trellis renderer for the Matplotlib backend."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import ceil, sqrt
from pathlib import Path
from typing import Any, cast

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
from plotagent.engine.profile_data import FacetData, k24_facets
from plotagent.engine.repository import document_ref

from .font import resolve_font_family

_COLORS = ("#2A6FDB", "#D94B4B", "#2A9D6F", "#8A5CC2", "#D88700")


@dataclass(frozen=True, slots=True)
class _K24Axes:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_scale: str = "linear"
    y_scale: str = "linear"
    x_minimum: float | None = None
    x_maximum: float | None = None
    y_minimum: float | None = None
    y_maximum: float | None = None
    x_reverse: bool = False
    y_reverse: bool = False


@dataclass(frozen=True, slots=True)
class _K24Style:
    color: str | None = None


def _apply_axis(axis: Any, state: _K24Axes, panel_title: str) -> None:
    axis.set_title(panel_title)
    axis.set_xlabel(state.x_label)
    axis.set_ylabel(state.y_label)
    axis.set_xscale(state.x_scale)
    axis.set_yscale(state.y_scale)
    if state.x_minimum is not None and state.x_maximum is not None:
        axis.set_xlim(state.x_minimum, state.x_maximum)
    if state.y_minimum is not None and state.y_maximum is not None:
        axis.set_ylim(state.y_minimum, state.y_maximum)
    if state.x_reverse:
        axis.invert_xaxis()
    if state.y_reverse:
        axis.invert_yaxis()


class K24FacetRenderer:
    """Render the common K24 contract without emulating Origin internals."""

    profile_id = "K24"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        facets = k24_facets(document, data)
        axes_state, styles = self._state(document, actions, facets)
        column_count = max(1, ceil(sqrt(len(facets.panels))))
        row_count = ceil(len(facets.panels) / column_count)
        visible_text = (
            axes_state.title,
            axes_state.x_label,
            axes_state.y_label,
            *(panel.label for panel in facets.panels),
        )
        font_family = resolve_font_family(visible_text)
        with matplotlib.rc_context({"font.family": font_family}):
            figure, axes = plt.subplots(
                row_count,
                column_count,
                squeeze=False,
                figsize=(4.0 * column_count, 3.2 * row_count),
                constrained_layout=True,
            )
            objects = list(self._base_objects(document))
            token = document.plot_id.removeprefix("plot:")
            for index, panel in enumerate(facets.panels):
                axis = axes.flat[index]
                style = styles[index]
                axis.plot(
                    panel.x_values,
                    panel.y_values,
                    color=style.color or _COLORS[index % len(_COLORS)],
                    marker="o",
                    linewidth=1.5,
                    label=panel.label,
                )
                _apply_axis(axis, axes_state, panel.label)
                objects.extend(
                    (
                        EngineObjectRef(
                            semantic_id=f"panel:{token}.facet_{index + 1}",
                            backend="matplotlib",
                            object_kind="facet_panel",
                            native_ref=f"axes:{index}",
                        ),
                        EngineObjectRef(
                            semantic_id=f"series:{token}.facet_{index + 1}",
                            backend="matplotlib",
                            object_kind="facet_series",
                            native_ref=f"axes:{index}.line:0",
                        ),
                    )
                )
            for axis in axes.flat[len(facets.panels) :]:
                axis.remove()
            if axes_state.title:
                figure.suptitle(axes_state.title)
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
                        "axes": asdict(axes_state),
                        "styles": [asdict(style) for style in styles],
                        "facet_columns": column_count,
                    },
                )
            ),
        )

    @staticmethod
    def _base_objects(document: PlotDocument) -> tuple[EngineObjectRef, ...]:
        token = document.plot_id.removeprefix("plot:")
        return (
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
        )

    @staticmethod
    def _state(
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        facets: FacetData,
    ) -> tuple[_K24Axes, tuple[_K24Style, ...]]:
        token = document.plot_id.removeprefix("plot:")
        axes = _K24Axes(
            x_label=facets.x_field_name,
            y_label=facets.y_field_name,
        )
        styles = tuple(_K24Style() for _panel in facets.panels)
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError("K24 title target does not belong to this plot")
                axes = replace(axes, title=action.text)
                continue
            if isinstance(action, SetAxis):
                axis_name = {
                    f"axis:{token}.x": "x",
                    f"axis:{token}.y": "y",
                }.get(action.target)
                if axis_name is None:
                    raise ValueError("K24 axis target does not belong to this plot")
                if action.scale not in {None, "linear"}:
                    raise ValueError("K24 Trellis axes currently expose only linear scale")
                if axis_name == "x":
                    axes = replace(
                        axes,
                        x_label=axes.x_label if action.label is None else action.label,
                        x_minimum=action.minimum,
                        x_maximum=action.maximum,
                        x_reverse=axes.x_reverse if action.reverse is None else action.reverse,
                    )
                else:
                    axes = replace(
                        axes,
                        y_label=axes.y_label if action.label is None else action.label,
                        y_minimum=action.minimum,
                        y_maximum=action.maximum,
                        y_reverse=axes.y_reverse if action.reverse is None else action.reverse,
                    )
                continue
            if isinstance(action, SetSeriesStyle):
                prefix = f"series:{token}.facet_"
                if not action.target.startswith(prefix):
                    raise ValueError("K24 series target does not belong to this plot")
                index = int(action.target.removeprefix(prefix)) - 1
                if not 0 <= index < len(styles):
                    raise ValueError("K24 facet series target is out of range")
                if (
                    action.color is None
                    or action.line_width_pt is not None
                    or action.line_style is not None
                    or action.symbol is not None
                    or action.symbol_size_pt is not None
                ):
                    raise ValueError("K24 exposes only per-facet color")
                mutable = list(styles)
                mutable[index] = replace(mutable[index], color=action.color)
                styles = tuple(mutable)
                continue
            if isinstance(action, (SetLegend, SetChartParameter)):
                raise ValueError(
                    "K24 exposes neither a standalone legend nor manual panel layout"
                )
            raise ValueError(f"K24 Matplotlib renderer cannot apply {action.operation}")
        return axes, styles

"""Independent K01 Matplotlib renderer; no legacy resolver is involved."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.product_style import (
    K01_AUTO_RANGE_MARGIN_PERCENT,
    PRODUCT_SERIES_PALETTE,
)
from plotagent.engine.profile_data import grouped_xy
from plotagent.engine.repository import document_ref


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"] = "linear"
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _LineState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    color: str = "#1676D2"
    line_width_pt: float = 1.5
    line_style: str = "solid"
    symbol: str = "none"
    symbol_size_pt: float = 5.0
    legend_visible: bool = False
    legend_anchor: str = "inside"


class K01LineRenderer:
    profile_id = "K01"

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        grouped = grouped_xy(document, data, profile_id="K01")
        state = self._state(
            document,
            actions,
            grouped.x_field_name,
            grouped.y_field_name,
            len(grouped.groups),
        )

        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        marker = None if state.symbol == "none" else self._marker(state.symbol)
        lines = []
        for index, group in enumerate(grouped.groups):
            (line,) = axis.plot(
                group.x_values,
                group.y_values,
                color=PRODUCT_SERIES_PALETTE[index % len(PRODUCT_SERIES_PALETTE)],
                linewidth=state.line_width_pt,
                linestyle=self._line_style(state.line_style),
                marker=marker,
                markersize=state.symbol_size_pt,
                label=group.label,
            )
            lines.append(line)
        margin = K01_AUTO_RANGE_MARGIN_PERCENT / 100.0
        axis.margins(x=margin, y=margin)
        axis.set_title(state.title)
        axis.set_xlabel(state.x_axis.label)
        axis.set_ylabel(state.y_axis.label)
        self._apply_axis(axis, "x", state.x_axis)
        self._apply_axis(axis, "y", state.y_axis)
        if grouped.x_labels is not None:
            axis.set_xticks(range(len(grouped.x_labels)), grouped.x_labels)
        if state.legend_visible:
            placements: dict[str, dict[str, object]] = {
                "inside": {"loc": "best"},
                "right": {"loc": "center left", "bbox_to_anchor": (1.02, 0.5)},
                "bottom": {"loc": "upper center", "bbox_to_anchor": (0.5, -0.15)},
                "none": {},
            }
            placement = placements[state.legend_anchor]
            if state.legend_anchor != "none":
                axis.legend(**placement)
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
            *tuple(
                EngineObjectRef(
                    semantic_id=f"series:{token}.group_{index}",
                    backend="matplotlib",
                    object_kind="line",
                    native_ref=f"axes:0.line:{index - 1}",
                )
                for index in range(1, len(lines) + 1)
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
    def _marker(symbol: str) -> str:
        return {"circle": "o", "square": "s", "triangle": "^", "diamond": "D"}.get(
            symbol,
            symbol,
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
            raise ValueError(f"K01 does not support {state.scale} on the {name} axis")
        getattr(axis, f"set_{name}scale")(scale)
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        x_name: str,
        y_name: str,
        group_count: int,
    ) -> _LineState:
        document.plot_id.removeprefix("plot:")
        state = _LineState(
            title="",
            x_axis=_AxisState(x_name),
            y_axis=_AxisState(y_name),
            legend_visible=group_count > 1,
        )
        for action in actions:
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            raise ValueError(f"K01 Matplotlib renderer cannot apply {action.operation}")
        return state

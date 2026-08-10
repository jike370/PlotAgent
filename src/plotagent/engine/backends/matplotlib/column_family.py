"""Independent K09/K10/K11 renderers over one validated category grid."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

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
from plotagent.engine.profile_data import CategorySeriesGrid, category_series_grid
from plotagent.engine.repository import document_ref

_PALETTE = (
    "#1676D2",
    "#D97800",
    "#299764",
    "#C53D4D",
    "#7656B5",
    "#008A99",
    "#A55A2A",
    "#667085",
)


@dataclass(frozen=True, slots=True)
class _AxisState:
    label: str
    scale: Literal["linear", "log10", "datetime", "categorical"] = "linear"
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False


@dataclass(frozen=True, slots=True)
class _SeriesState:
    color: str
    edge_width_pt: float = 0.8


@dataclass(frozen=True, slots=True)
class _ColumnFamilyState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    series: tuple[_SeriesState, ...]
    legend_visible: bool = True


class _ColumnFamilyRenderer:
    profile_id: str
    mode: Literal["grouped", "stacked", "percent"]
    series_key: Literal["group", "component"]

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        grid = category_series_grid(
            document,
            data,
            profile_id=cast(Literal["K09", "K10", "K11"], self.profile_id),
        )
        values = self._plot_values(grid)
        state = self._state(document, actions, grid)
        positions = np.arange(len(grid.category_labels), dtype=float)
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        containers = self._draw(axis, positions, values, grid, state)
        axis.set_xticks(positions, grid.category_labels)
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
                    semantic_id=f"series:{token}.{self.series_key}_{index}",
                    backend="matplotlib",
                    object_kind=f"{self.mode}_column_series",
                    native_ref=f"axes:0.bar_container:{index - 1}:{len(container)}",
                )
                for index, container in enumerate(containers, start=1)
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
            style_hash=canonical_hash({"mode": self.mode, **asdict(state)}),
        )

    def _draw(
        self,
        axis: Axes,
        positions: np.ndarray,
        values: np.ndarray,
        grid: CategorySeriesGrid,
        state: _ColumnFamilyState,
    ) -> tuple[BarContainer, ...]:
        containers: list[BarContainer] = []
        count = len(grid.series_labels)
        if self.mode == "grouped":
            group_width = 0.8
            width = group_width / count
            offsets = (np.arange(count, dtype=float) - (count - 1) / 2.0) * width
            for index, (label, style) in enumerate(
                zip(grid.series_labels, state.series, strict=True)
            ):
                containers.append(
                    axis.bar(
                        positions + offsets[index],
                        values[:, index],
                        width=width,
                        color=style.color,
                        edgecolor="#1A1A1A",
                        linewidth=style.edge_width_pt,
                        label=label,
                    )
                )
            return tuple(containers)

        bottom = np.zeros(len(grid.category_labels), dtype=float)
        for index, (label, style) in enumerate(zip(grid.series_labels, state.series, strict=True)):
            heights = values[:, index]
            containers.append(
                axis.bar(
                    positions,
                    heights,
                    width=0.8,
                    bottom=bottom,
                    color=style.color,
                    edgecolor="#1A1A1A",
                    linewidth=style.edge_width_pt,
                    label=label,
                )
            )
            bottom += np.nan_to_num(heights, nan=0.0)
        return tuple(containers)

    def _plot_values(self, grid: CategorySeriesGrid) -> np.ndarray:
        values = np.asarray(grid.values, dtype=float)
        if self.mode != "percent":
            return values
        finite_values = values[np.isfinite(values)]
        if np.any(finite_values < 0):
            raise ValueError("K11 percent-stack values must be non-negative")
        totals = np.nansum(values, axis=1)
        if np.any(totals <= 0):
            raise ValueError("K11 each category must have a positive total")
        return values / totals[:, np.newaxis] * 100.0

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        if name == "x" and state.scale not in {"linear", "categorical"}:
            raise ValueError("column category axes support only categorical scale")
        if name == "y":
            scale = "log" if state.scale == "log10" else state.scale
            if scale not in {"linear", "log"}:
                raise ValueError("column value axes support only linear or log10 scale")
            axis.set_yscale(scale)
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        grid: CategorySeriesGrid,
    ) -> _ColumnFamilyState:
        token = document.plot_id.removeprefix("plot:")
        state = _ColumnFamilyState(
            title="",
            x_axis=_AxisState(grid.category_field_name, scale="categorical"),
            y_axis=_AxisState("Percent" if self.mode == "percent" else grid.value_field_name),
            series=tuple(
                _SeriesState(color=_PALETTE[index % len(_PALETTE)])
                for index in range(len(grid.series_labels))
            ),
        )
        last_binding = max(
            (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
            default=-1,
        )
        for index, action in enumerate(actions):
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetTitle):
                if action.target != document.plot_id:
                    raise ValueError(f"{self.profile_id} title target does not belong to this plot")
                state = replace(state, title=action.text)
            elif isinstance(action, SetAxis):
                axis_name = {f"axis:{token}.x": "x_axis", f"axis:{token}.y": "y_axis"}.get(
                    action.target
                )
                if axis_name is None:
                    raise ValueError(f"{self.profile_id} axis target does not belong to this plot")
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
                if index < last_binding:
                    continue
                ordinal = self._series_ordinal(action.target, token, len(grid.series_labels))
                current = state.series[ordinal - 1]
                updated = replace(
                    current,
                    color=current.color if action.color is None else action.color,
                    edge_width_pt=(
                        current.edge_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt
                    ),
                )
                series = list(state.series)
                series[ordinal - 1] = updated
                state = replace(state, series=tuple(series))
            elif isinstance(action, SetLegend):
                if action.target != f"legend:{token}.main":
                    raise ValueError(
                        f"{self.profile_id} legend target does not belong to this plot"
                    )
                state = replace(
                    state,
                    legend_visible=(
                        state.legend_visible if action.visible is None else action.visible
                    ),
                )
            else:
                raise ValueError(f"{self.profile_id} renderer cannot apply {action.operation}")
        return state

    def _series_ordinal(self, target: str, token: str, series_count: int) -> int:
        prefix = f"series:{token}.{self.series_key}_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        if not suffix.isdigit() or not 1 <= int(suffix) <= series_count:
            raise ValueError(f"{self.profile_id} series target is outside the materialized data")
        return int(suffix)


class K09GroupedColumnRenderer(_ColumnFamilyRenderer):
    profile_id = "K09"
    mode = "grouped"
    series_key = "group"


class K10StackedColumnRenderer(_ColumnFamilyRenderer):
    profile_id = "K10"
    mode = "stacked"
    series_key = "component"


class K11PercentStackRenderer(_ColumnFamilyRenderer):
    profile_id = "K11"
    mode = "percent"
    series_key = "component"

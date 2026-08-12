"""Independent K12/K13/K14 distribution renderers over raw observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
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
    SetAxis,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import DistributionData, distribution_groups
from plotagent.engine.repository import document_ref
from plotagent.plot_calculations.kernels import scott_kde_geometry

_PALETTE = ("#1676D2", "#D97800", "#299764", "#C53D4D", "#7656B5", "#008A99")


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
    line_width_pt: float = 1.0
    symbol: str = "circle"
    symbol_size_pt: float = 5.0


@dataclass(frozen=True, slots=True)
class _DistributionState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    series: tuple[_SeriesState, ...]
    legend_visible: bool = False


class _DistributionRenderer:
    profile_id: str
    object_kind: str

    def render(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        data: EngineDataView,
        png_path: Path,
        svg_path: Path,
    ) -> EngineReadback:
        distribution = distribution_groups(
            document,
            data,
            profile_id=cast(Literal["K12", "K13", "K14", "X05"], self.profile_id),
        )
        state = self._state(document, actions, distribution)
        figure, axis = plt.subplots(figsize=(6.4, 4.8), constrained_layout=True)
        artists = self._draw(axis, distribution, state)
        positions = np.arange(1, len(distribution.groups) + 1, dtype=float)
        axis.set_xticks(positions, tuple(group.label for group in distribution.groups))
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
                    semantic_id=f"series:{token}.group_{index}",
                    backend="matplotlib",
                    object_kind=self.object_kind,
                    native_ref=f"axes:0.{self.object_kind}:{index - 1}:{native_count}",
                )
                for index, native_count in enumerate(artists, start=1)
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

    def _draw(
        self,
        axis: Axes,
        distribution: DistributionData,
        state: _DistributionState,
    ) -> tuple[int, ...]:
        raise NotImplementedError

    @staticmethod
    def _apply_axis(axis: Axes, name: Literal["x", "y"], state: _AxisState) -> None:
        if name == "x" and state.scale not in {"linear", "categorical"}:
            raise ValueError("distribution category axes support only categorical scale")
        if name == "y":
            scale = "log" if state.scale == "log10" else state.scale
            if scale not in {"linear", "log"}:
                raise ValueError("distribution value axes support only linear or log10")
            axis.set_yscale(scale)
        if state.minimum is not None and state.maximum is not None:
            getattr(axis, f"set_{name}lim")((state.minimum, state.maximum))
        if state.reverse:
            getattr(axis, f"invert_{name}axis")()

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        distribution: DistributionData,
    ) -> _DistributionState:
        token = document.plot_id.removeprefix("plot:")
        state = _DistributionState(
            title="",
            x_axis=_AxisState("Group", scale="categorical"),
            y_axis=_AxisState(distribution.value_field_name),
            series=tuple(
                _SeriesState(color=_PALETTE[index % len(_PALETTE)])
                for index in range(len(distribution.groups))
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
                ordinal = self._series_ordinal(action.target, token, len(distribution.groups))
                current = state.series[ordinal - 1]
                updated = replace(
                    current,
                    color=current.color if action.color is None else action.color,
                    line_width_pt=(
                        current.line_width_pt
                        if action.line_width_pt is None
                        else action.line_width_pt
                    ),
                    symbol=current.symbol if action.symbol is None else action.symbol,
                    symbol_size_pt=(
                        current.symbol_size_pt
                        if action.symbol_size_pt is None
                        else action.symbol_size_pt
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

    def _series_ordinal(self, target: str, token: str, group_count: int) -> int:
        prefix = f"series:{token}.group_"
        suffix = target.removeprefix(prefix) if target.startswith(prefix) else ""
        if not suffix.isdigit() or not 1 <= int(suffix) <= group_count:
            raise ValueError(f"{self.profile_id} series target is outside the materialized groups")
        return int(suffix)


class K12StripRenderer(_DistributionRenderer):
    profile_id = "K12"
    object_kind = "strip_series"

    def _draw(
        self,
        axis: Axes,
        distribution: DistributionData,
        state: _DistributionState,
    ) -> tuple[int, ...]:
        counts: list[int] = []
        markers = {
            "circle": "o",
            "square": "s",
            "diamond": "D",
            "triangle": "^",
            "triangle_up": "^",
        }
        for position, (group, style) in enumerate(
            zip(distribution.groups, state.series, strict=True), start=1
        ):
            count = len(group.values)
            jitter = np.linspace(-0.18, 0.18, count) if count > 1 else np.asarray([0.0])
            axis.scatter(
                np.full(count, position, dtype=float) + jitter,
                group.values,
                color=style.color,
                marker=markers.get(style.symbol, "o"),
                s=style.symbol_size_pt**2,
                label=group.label,
            )
            counts.append(count)
        return tuple(counts)


class K13BoxRenderer(_DistributionRenderer):
    profile_id = "K13"
    object_kind = "box_series"

    def _draw(
        self,
        axis: Axes,
        distribution: DistributionData,
        state: _DistributionState,
    ) -> tuple[int, ...]:
        result = axis.boxplot(
            [group.values for group in distribution.groups],
            positions=np.arange(1, len(distribution.groups) + 1),
            widths=0.55,
            patch_artist=True,
            whis=1.5,
        )
        for group, style, box in zip(
            distribution.groups,
            state.series,
            result["boxes"],
            strict=True,
        ):
            box.set_facecolor(style.color)
            box.set_edgecolor("#1A1A1A")
            box.set_linewidth(style.line_width_pt)
            box.set_label(group.label)
        return tuple(len(group.values) for group in distribution.groups)


class K14ViolinRenderer(_DistributionRenderer):
    profile_id = "K14"
    object_kind = "violin_series"

    def _draw(
        self,
        axis: Axes,
        distribution: DistributionData,
        state: _DistributionState,
    ) -> tuple[int, ...]:
        pooled_values = tuple(
            value for group in distribution.groups for value in group.values
        )
        shared_bandwidth = scott_kde_geometry(
            pooled_values,
            grid_points=256,
            extend_bandwidths=0.0,
        ).bandwidth
        # Origin stores one absolute KDE bandwidth for the native violin
        # group. Matplotlib accepts a covariance factor per call, so divide
        # the shared absolute bandwidth by each group's sample SD.
        for position, (group, style) in enumerate(
            zip(distribution.groups, state.series, strict=True), start=1
        ):
            sample_sd = float(np.std(group.values, ddof=1))
            if sample_sd <= 0:
                raise ValueError("K14 violin groups require non-zero sample variance")
            result = axis.violinplot(
                [group.values],
                positions=[position],
                widths=0.75,
                showmeans=False,
                showmedians=True,
                showextrema=False,
                points=256,
                bw_method=shared_bandwidth / sample_sd,
            )
            bodies = cast(list[Any], result["bodies"])
            if len(bodies) != 1:
                raise RuntimeError("Matplotlib K14 must create one body per raw group")
            body = bodies[0]
            body.set_facecolor(style.color)
            body.set_edgecolor("#1A1A1A")
            body.set_linewidth(style.line_width_pt)
            body.set_alpha(0.75)
            body.set_label(group.label)
        return tuple(len(group.values) for group in distribution.groups)


class X05BeeswarmRenderer(_DistributionRenderer):
    """Independent deterministic beeswarm renderer over raw observations."""

    profile_id = "X05"
    object_kind = "beeswarm_series"

    def _draw(
        self,
        axis: Axes,
        distribution: DistributionData,
        state: _DistributionState,
    ) -> tuple[int, ...]:
        counts: list[int] = []
        markers = {
            "circle": "o",
            "square": "s",
            "diamond": "D",
            "triangle": "^",
            "triangle_up": "^",
        }
        for position, (group, style) in enumerate(
            zip(distribution.groups, state.series, strict=True), start=1
        ):
            offsets = _beeswarm_offsets(group.values)
            axis.scatter(
                np.full(len(group.values), position, dtype=float) + offsets,
                group.values,
                color=style.color,
                marker=markers.get(style.symbol, "o"),
                s=style.symbol_size_pt**2,
                label=group.label,
            )
            counts.append(len(group.values))
        return tuple(counts)


def _beeswarm_offsets(values: tuple[float, ...]) -> np.ndarray:
    """Pack nearby observations symmetrically without random jitter."""

    if len(values) <= 1:
        return np.zeros(len(values), dtype=float)
    low, high = min(values), max(values)
    width = (high - low) / 24.0 if high > low else 1.0
    bins: dict[int, list[int]] = {}
    for index, value in enumerate(values):
        key = round((value - low) / width)
        bins.setdefault(key, []).append(index)
    offsets = np.zeros(len(values), dtype=float)
    for indexes in bins.values():
        count = len(indexes)
        step = min(0.09, 0.36 / max(count - 1, 1))
        centered = (np.arange(count, dtype=float) - (count - 1) / 2.0) * step
        for index, offset in zip(indexes, centered, strict=True):
            offsets[index] = offset
    return offsets

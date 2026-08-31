"""Independent K12/K13/K14 distribution renderers over raw observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors as mcolors
from matplotlib.axes import Axes

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    BindFields,
    CreatePlot,
    EngineDataView,
    PlotDocument,
    PlotEngineAction,
    SetObservationOverlay,
)
from plotagent.engine.ports import EngineObjectRef, EngineReadback
from plotagent.engine.profile_data import (
    DistributionData,
    distribution_groups,
    regular_observation_positions,
)
from plotagent.engine.repository import document_ref
from plotagent.engine.product_style import K14_VIOLIN_STYLE, k14_auto_range_bounds
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
class _ObservationOverlayState:
    visible: bool
    jitter_fraction: float
    marker_shape: str
    marker_size_pt: float
    marker_interior: str
    marker_fill_color: str
    marker_stroke_color: str
    marker_opacity: float


@dataclass(frozen=True, slots=True)
class _DistributionState:
    title: str
    x_axis: _AxisState
    y_axis: _AxisState
    series: tuple[_SeriesState, ...]
    legend_visible: bool = False
    observation_overlay: _ObservationOverlayState | None = None


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
        extra_objects = self._extra_objects(document, distribution, state)
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
            *extra_objects,
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

    def _extra_objects(
        self,
        document: PlotDocument,
        distribution: DistributionData,
        state: _DistributionState,
    ) -> tuple[EngineObjectRef, ...]:
        if state.observation_overlay is None:
            return ()
        token = document.plot_id.removeprefix("plot:")
        point_count = sum(len(group.values) for group in distribution.groups)
        return (
            EngineObjectRef(
                semantic_id=f"observation_overlay:{token}.raw",
                backend="matplotlib",
                object_kind="observation_overlay",
                native_ref=(
                    "axes:0.observation_overlay:"
                    f"{len(distribution.groups)}:{point_count}"
                ),
            ),
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
        document.plot_id.removeprefix("plot:")
        state = _DistributionState(
            title="",
            x_axis=_AxisState("Group", scale="categorical"),
            y_axis=_AxisState(distribution.value_field_name),
            series=tuple(
                _SeriesState(color=_PALETTE[index % len(_PALETTE)])
                for index in range(len(distribution.groups))
            ),
        )
        max(
            (index for index, action in enumerate(actions) if isinstance(action, BindFields)),
            default=-1,
        )
        for _index, action in enumerate(actions):
            if isinstance(action, (CreatePlot, BindFields)):
                continue
            if isinstance(action, SetObservationOverlay) and self.profile_id == "K13":
                state = _DistributionState(
                    title=state.title,
                    x_axis=state.x_axis,
                    y_axis=state.y_axis,
                    series=state.series,
                    legend_visible=state.legend_visible,
                    observation_overlay=_ObservationOverlayState(
                        visible=action.visible,
                        jitter_fraction=action.jitter_fraction,
                        marker_shape=action.marker_shape,
                        marker_size_pt=action.marker_size_pt,
                        marker_interior=action.marker_interior,
                        marker_fill_color=action.marker_fill_color,
                        marker_stroke_color=action.marker_stroke_color,
                        marker_opacity=action.marker_opacity,
                    ),
                )
                continue
            raise ValueError(f"{self.profile_id} renderer cannot apply {action.operation}")
        return state


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
            showfliers=(
                state.observation_overlay is None
                or not state.observation_overlay.visible
            ),
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
        overlay = state.observation_overlay
        if overlay is not None and overlay.visible:
            markers = {
                "circle": "o",
                "square": "s",
                "triangle_up": "^",
                "triangle_down": "v",
                "diamond": "D",
            }
            face_color: str = (
                "none"
                if overlay.marker_interior in {"open", "hollow"}
                else overlay.marker_fill_color
            )
            for position, group in enumerate(distribution.groups, start=1):
                x_values = regular_observation_positions(
                    position,
                    len(group.values),
                    overlay.jitter_fraction,
                )
                axis.scatter(
                    x_values,
                    group.values,
                    marker=markers[overlay.marker_shape],
                    s=overlay.marker_size_pt**2,
                    facecolors=face_color,
                    edgecolors=overlay.marker_stroke_color,
                    alpha=overlay.marker_opacity,
                    linewidths=0.8,
                    zorder=4,
                )
        return tuple(len(group.values) for group in distribution.groups)


class K14ViolinRenderer(_DistributionRenderer):
    profile_id = "K14"
    object_kind = "violin_series"

    def _state(
        self,
        document: PlotDocument,
        actions: tuple[PlotEngineAction, ...],
        distribution: DistributionData,
    ) -> _DistributionState:
        state = super()._state(document, actions, distribution)
        x_bounds, y_bounds = k14_auto_range_bounds(
            tuple(value for group in distribution.groups for value in group.values),
            len(distribution.groups),
        )
        return _DistributionState(
            title=state.title,
            x_axis=_AxisState(
                state.x_axis.label,
                scale=state.x_axis.scale,
                minimum=x_bounds[0],
                maximum=x_bounds[1],
            ),
            y_axis=_AxisState(
                state.y_axis.label,
                scale=state.y_axis.scale,
                minimum=y_bounds[0],
                maximum=y_bounds[1],
            ),
            series=state.series,
            legend_visible=K14_VIOLIN_STYLE.legend_visible,
            observation_overlay=state.observation_overlay,
        )

    def _draw(
        self,
        axis: Axes,
        distribution: DistributionData,
        state: _DistributionState,
    ) -> tuple[int, ...]:
        pooled_values = tuple(value for group in distribution.groups for value in group.values)
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
                showmedians=K14_VIOLIN_STYLE.median_visible,
                showextrema=False,
                points=256,
                bw_method=shared_bandwidth / sample_sd,
            )
            bodies = cast(list[Any], result["bodies"])
            if len(bodies) != 1:
                raise RuntimeError("Matplotlib K14 must create one body per raw group")
            body = bodies[0]
            # ``Axes.violinplot`` installs a collection-level alpha of 0.3.
            # Clear it before assigning the product RGBA; otherwise the
            # requested 0.75 face opacity is multiplied by that hidden alpha.
            body.set_alpha(None)
            body.set_facecolor(
                mcolors.to_rgba(style.color, alpha=K14_VIOLIN_STYLE.fill_opacity)
            )
            body.set_edgecolor(K14_VIOLIN_STYLE.outline_color)
            body.set_linewidth(K14_VIOLIN_STYLE.outline_width_pt)
            body.set_linestyle(K14_VIOLIN_STYLE.outline_style)
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

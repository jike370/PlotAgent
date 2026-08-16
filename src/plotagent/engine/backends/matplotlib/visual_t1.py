"""Shared T1 visual language for native Matplotlib figures.

Profile renderers own chart geometry and data semantics.  This module owns the
small, closed visual vocabulary that is shared with Origin and may be emitted
either by a workflow draft or by the focus editor.  Keeping that vocabulary at
the backend boundary prevents every chart family from inventing a second set
of colour, type and legend controls.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any, Literal, cast
from weakref import WeakSet

import matplotlib.colors as mcolors
from matplotlib import colormaps
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PathCollection, PolyCollection
from matplotlib.container import BarContainer, ErrorbarContainer
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.patches import Patch
from matplotlib.ticker import AutoMinorLocator, FuncFormatter, MultipleLocator

from plotagent.engine.contracts import (
    AddAnnotation,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)

_LINE_STYLES: dict[str, Any] = {
    "solid": "-",
    "dash": "--",
    "dot": ":",
    "dash_dot": "-.",
    "none": "",
}
_MARKERS = {
    "circle": "o",
    "square": "s",
    "triangle_up": "^",
    "triangle_down": "v",
    "triangle_left": "<",
    "triangle_right": ">",
    "diamond": "D",
    "plus": "+",
    "cross": "x",
    "hexagon": "h",
    "star": "*",
    "pentagon": "p",
    "none": "",
}
_PALETTES = {
    "viridis": "viridis",
    "plasma": "plasma",
    "inferno": "inferno",
    "magma": "magma",
    "cividis": "cividis",
    "turbo": "turbo",
    "blue_orange": "PuOr",
    "red_white_blue": "RdBu_r",
    "blue_white_red": "bwr",
    "gray_scale": "gray",
    "fire": "afmhot",
    "rainbow_modified": "turbo",
    "cool_warm": "coolwarm",
    "spectral": "Spectral",
    "terrain": "terrain",
    "ocean": "ocean",
}


@contextmanager
def apply_visuals_before_save(
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
) -> Iterator[None]:
    """Apply shared visuals exactly once immediately before a figure is saved.

    Independent renderers deliberately own their figure lifecycle.  Scoping the
    save hook here preserves that boundary while giving every renderer the same
    T1 implementation.  Matplotlib rendering is already serialized by the
    backend and is not thread-safe, so the class-level hook cannot overlap.
    """

    original: Any = Figure.savefig
    applied: WeakSet[Figure] = WeakSet()

    def savefig(figure: Figure, *args: object, **kwargs: object) -> Any:
        if figure not in applied:
            apply_visual_actions(figure, document, actions)
            applied.add(figure)
        return original(figure, *args, **kwargs)

    cast(Any, Figure).savefig = savefig
    try:
        yield
    finally:
        cast(Any, Figure).savefig = original


def apply_visual_actions(
    figure: Figure,
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
) -> None:
    for action in actions:
        if isinstance(action, SetTitle):
            _apply_title(figure, action)
        elif isinstance(action, SetAxis):
            _apply_axis(figure, action)
        elif isinstance(action, SetSeriesStyle):
            _apply_series(figure, action)
        elif isinstance(action, SetLegend):
            _apply_legend(figure, action)
        elif isinstance(action, SetColorMap):
            _apply_colormap(figure, action)
        elif isinstance(action, SetErrorStyle):
            _apply_error(figure, action)
        elif isinstance(action, SetDataLabels):
            _apply_data_labels(figure, action)
        elif isinstance(action, AddAnnotation):
            _apply_annotation(figure, action)
        else:  # pragma: no cover - split_visual_actions is the closed dispatcher
            raise TypeError(f"unsupported Matplotlib visual action {action.operation}")


def _data_axes(figure: Figure) -> list[Axes]:
    result = [axis for axis in figure.axes if axis.get_label() != "<colorbar>"]
    return result or list(figure.axes)


def _target_key(target: str) -> str:
    return target.rsplit(".", 1)[-1]


def _axis_for_target(figure: Figure, target: str) -> tuple[Axes, Literal["x", "y"]]:
    axes = _data_axes(figure)
    key = _target_key(target)
    if key == "x":
        return axes[0], "x"
    if key in {"y", "y_left"}:
        return axes[0], "y"
    if key == "y_right":
        return axes[-1], "y"
    raise ValueError(f"unknown Matplotlib axis target {target}")


def _font(family: str | None) -> str | None:
    return None if family in {None, "auto"} else family


def _weight(weight: str | None) -> str | None:
    return None if weight in {None, "auto"} else weight


def _text_style(
    *,
    family: str | None,
    size: float | None,
    weight: str | None,
    italic: bool | None,
    color: str | None,
) -> dict[str, Any]:
    style: dict[str, Any] = {}
    if _font(family) is not None:
        style["fontfamily"] = _font(family)
    if size is not None:
        style["fontsize"] = size
    if _weight(weight) is not None:
        style["fontweight"] = _weight(weight)
    if italic is not None:
        style["fontstyle"] = "italic" if italic else "normal"
    if color is not None:
        style["color"] = color
    return style


def _apply_title(figure: Figure, action: SetTitle) -> None:
    axis = _data_axes(figure)[0]
    current = axis.get_title()
    cast(Any, axis.set_title)(
        current if action.text is None else action.text,
        **_text_style(
            family=action.font_family,
            size=action.font_size_pt,
            weight=action.font_weight,
            italic=action.italic,
            color=action.color,
        ),
    )


def _formatter(kind: str) -> FuncFormatter | None:
    if kind == "auto":
        return None
    if kind == "decimal":
        return FuncFormatter(lambda value, _position: f"{value:g}")
    if kind == "scientific":
        return FuncFormatter(lambda value, _position: f"{value:.3e}")
    if kind == "percent":
        return FuncFormatter(lambda value, _position: f"{value * 100:g}%")
    if kind == "date":
        return None
    if kind == "time":
        return None
    raise ValueError(f"unknown tick format {kind}")


def _apply_axis(figure: Figure, action: SetAxis) -> None:
    axis, name = _axis_for_target(figure, action.target)
    axis_object = axis.xaxis if name == "x" else axis.yaxis
    current_label = axis.get_xlabel() if name == "x" else axis.get_ylabel()
    setter = axis.set_xlabel if name == "x" else axis.set_ylabel
    cast(Any, setter)(
        current_label if action.label is None else action.label,
        **_text_style(
            family=action.title_font_family,
            size=action.title_font_size_pt,
            weight=action.title_font_weight,
            italic=action.title_italic,
            color=action.title_color,
        ),
    )
    if action.scale in {"linear", "log10"}:
        getattr(axis, f"set_{name}scale")("log" if action.scale == "log10" else "linear")
    if action.minimum is not None and action.maximum is not None:
        getattr(axis, f"set_{name}lim")((action.minimum, action.maximum))
    if action.reverse is True:
        current = getattr(axis, f"get_{name}lim")()
        if current[0] < current[1]:
            getattr(axis, f"invert_{name}axis")()
    elif action.reverse is False:
        current = getattr(axis, f"get_{name}lim")()
        if current[0] > current[1]:
            getattr(axis, f"invert_{name}axis")()
    if action.major_tick_step is not None:
        axis_object.set_major_locator(MultipleLocator(action.major_tick_step))
    if action.minor_tick_count is not None:
        axis_object.set_minor_locator(AutoMinorLocator(action.minor_tick_count + 1))
    if action.tick_format is not None:
        formatter = _formatter(action.tick_format)
        if formatter is not None:
            axis_object.set_major_formatter(formatter)
    tick_labels = axis.get_xticklabels() if name == "x" else axis.get_yticklabels()
    for label in tick_labels:
        if action.tick_rotation_deg is not None:
            label.set_rotation(action.tick_rotation_deg)
        if action.tick_font_family not in {None, "auto"}:
            label.set_fontfamily(cast(str, action.tick_font_family))
        if action.tick_font_size_pt is not None:
            label.set_fontsize(action.tick_font_size_pt)
        if action.tick_color is not None:
            label.set_color(action.tick_color)
    spine_name = "bottom" if name == "x" else "left"
    spine = axis.spines[spine_name]
    if action.axis_line_color is not None:
        spine.set_color(action.axis_line_color)
    if action.axis_line_width_pt is not None:
        spine.set_linewidth(action.axis_line_width_pt)
    if action.major_grid_visible is not None:
        axis.grid(
            action.major_grid_visible,
            which="major",
            axis=name,
            color=action.grid_color,
            linewidth=action.grid_line_width_pt,
            linestyle=(
                None if action.grid_line_style is None else _LINE_STYLES[action.grid_line_style]
            ),
        )
    if action.minor_grid_visible is not None:
        axis.grid(
            action.minor_grid_visible,
            which="minor",
            axis=name,
            color=action.grid_color,
            linewidth=action.grid_line_width_pt,
            linestyle=(
                None if action.grid_line_style is None else _LINE_STYLES[action.grid_line_style]
            ),
        )


def _series_ordinal(key: str) -> int:
    if key.startswith(("series_", "column_", "group_", "area_", "component_", "facet_")):
        try:
            return max(0, int(key.rsplit("_", 1)[-1]) - 1)
        except ValueError:
            return 0
    return {"right": 1, "cumulative": 1}.get(key, 0)


def _axis_artists(axis: Axes) -> list[Any]:
    result: list[Any] = []
    result.extend(axis.lines)
    result.extend(axis.collections)
    for container in axis.containers:
        if isinstance(container, BarContainer):
            result.append(container)
    if axis.images:
        result.extend(axis.images)
    return result


def _series_artists(figure: Figure, target: str) -> list[Any]:
    key = _target_key(target)
    axes = _data_axes(figure)
    if key in {"right", "cumulative"} and len(axes) > 1:
        candidates = _axis_artists(axes[-1])
    elif key == "bars":
        candidates = [item for item in _axis_artists(axes[0]) if isinstance(item, BarContainer)]
    elif key == "matrix":
        candidates = [*axes[0].images, *axes[0].collections]
    elif key == "connector":
        candidates = [
            item for item in _axis_artists(axes[0]) if isinstance(item, (Line2D, LineCollection))
        ]
    else:
        candidates = _axis_artists(axes[0])
    if not candidates:
        raise ValueError(f"Matplotlib target {target} has no rendered artist")
    ordinal = _series_ordinal(key)
    if key.startswith(
        ("series_", "column_", "group_", "area_", "component_", "facet_")
    ) and ordinal >= len(candidates):
        raise ValueError(f"Matplotlib target {target} is outside the materialized series")
    if key in {"primary", "left", "right", "bars", "cumulative", "matrix", "connector"}:
        return [candidates[min(ordinal, len(candidates) - 1)]]
    return [candidates[ordinal]]


def _iter_primitives(artist: Any) -> Iterable[Any]:
    if isinstance(artist, BarContainer):
        return artist.patches
    return (artist,)


def _set_marker(artist: Any, action: SetSeriesStyle) -> None:
    shape = None if action.marker_shape is None else _MARKERS[action.marker_shape]
    if isinstance(artist, Line2D):
        if shape is not None:
            artist.set_marker(shape)
        if action.marker_size_pt is not None:
            artist.set_markersize(action.marker_size_pt)
        if action.marker_fill_color is not None:
            artist.set_markerfacecolor(action.marker_fill_color)
        if action.marker_stroke_color is not None:
            artist.set_markeredgecolor(action.marker_stroke_color)
        if action.marker_stroke_width_pt is not None:
            artist.set_markeredgewidth(action.marker_stroke_width_pt)
        if action.marker_interior == "open":
            artist.set_markerfacecolor("none")
        elif action.marker_interior == "hollow":
            artist.set_markerfacecolor("white")
        if action.marker_opacity is not None:
            artist.set_alpha(action.marker_opacity)
    elif isinstance(artist, PathCollection):
        if action.marker_size_pt is not None:
            artist.set_sizes([action.marker_size_pt**2])
        if action.marker_fill_color is not None:
            artist.set_facecolor(action.marker_fill_color)
        if action.marker_stroke_color is not None:
            artist.set_edgecolor(action.marker_stroke_color)
        if action.marker_stroke_width_pt is not None:
            artist.set_linewidth(action.marker_stroke_width_pt)
        if action.marker_interior == "open":
            artist.set_facecolor("none")
        elif action.marker_interior == "hollow":
            artist.set_facecolor("white")
        if action.marker_opacity is not None:
            artist.set_alpha(action.marker_opacity)
        # PathCollection has no stable public marker setter.  Replacing the
        # path with a Line2D marker path retains native vector output.
        if shape not in {None, ""}:
            marker = MarkerStyle(cast(str, shape))
            artist.set_paths([marker.get_path().transformed(marker.get_transform())])


def _set_line(artist: Any, action: SetSeriesStyle) -> None:
    if not isinstance(artist, (Line2D, LineCollection)):
        return
    if action.line_stroke_color is not None:
        artist.set_color(action.line_stroke_color)
    if action.line_width_pt is not None:
        artist.set_linewidth(action.line_width_pt)
    if action.line_style is not None:
        artist.set_linestyle(_LINE_STYLES[action.line_style])
    if action.line_opacity is not None:
        artist.set_alpha(action.line_opacity)


def _set_fill(artist: Any, action: SetSeriesStyle) -> None:
    for primitive in _iter_primitives(artist):
        if not isinstance(primitive, (Patch, PolyCollection)):
            continue
        if action.fill_color is not None:
            primitive.set_facecolor(action.fill_color)
        if action.fill_opacity is not None:
            primitive.set_alpha(action.fill_opacity)
        if action.fill_stroke_color is not None:
            primitive.set_edgecolor(action.fill_stroke_color)
        if action.fill_stroke_width_pt is not None:
            primitive.set_linewidth(action.fill_stroke_width_pt)
        if action.fill_stroke_style is not None:
            primitive.set_linestyle(_LINE_STYLES[action.fill_stroke_style])


def _apply_series(figure: Figure, action: SetSeriesStyle) -> None:
    for artist in _series_artists(figure, action.target):
        for primitive in _iter_primitives(artist):
            _set_line(primitive, action)
            _set_marker(primitive, action)
        _set_fill(artist, action)


def _apply_legend(figure: Figure, action: SetLegend) -> None:
    axes = _data_axes(figure)
    for axis in axes:
        existing = axis.get_legend()
        visible = existing is not None if action.visible is None else action.visible
        if not visible or action.anchor == "none":
            if existing is not None:
                existing.remove()
            continue
        handles, labels = axis.get_legend_handles_labels()
        if not handles and existing is not None:
            handles = [handle for handle in existing.legend_handles if handle is not None]
            labels = [text.get_text() for text in existing.get_texts()]
        if not handles:
            continue
        placements: dict[str, dict[str, object]] = {
            "inside": {"loc": "best"},
            "right": {"loc": "center left", "bbox_to_anchor": (1.02, 0.5)},
            "bottom": {"loc": "upper center", "bbox_to_anchor": (0.5, -0.15)},
        }
        anchor = cast(
            Literal["inside", "right", "bottom"],
            "inside" if action.anchor in {None, "none"} else action.anchor,
        )
        legend = axis.legend(  # type: ignore[call-overload]
            handles,
            labels,
            ncols=action.columns or 1,
            title=action.title,
            frameon=True if action.frame_visible is None else action.frame_visible,
            **placements[anchor],
        )
        for text in [*legend.get_texts(), legend.get_title()]:
            if action.font_family not in {None, "auto"}:
                text.set_fontfamily(action.font_family)
            if action.font_size_pt is not None:
                text.set_fontsize(action.font_size_pt)
            if action.font_color is not None:
                text.set_color(action.font_color)
        frame = legend.get_frame()
        if action.frame_color is not None:
            frame.set_edgecolor(action.frame_color)
        if action.frame_width_pt is not None:
            frame.set_linewidth(action.frame_width_pt)


def _apply_colormap(figure: Figure, action: SetColorMap) -> None:
    artist = _series_artists(figure, action.target)[0]
    if not hasattr(artist, "set_cmap"):
        raise ValueError(f"Matplotlib target {action.target} does not expose a colormap")
    palette = _PALETTES[action.palette or "viridis"]
    if action.reverse:
        palette = palette[:-2] if palette.endswith("_r") else f"{palette}_r"
    colormap = colormaps[palette].with_extremes(bad=action.missing_color or "#BDBDBD")
    artist.set_cmap(colormap)
    if action.minimum is not None and action.maximum is not None:
        if action.midpoint is None:
            artist.set_clim(action.minimum, action.maximum)
        else:
            artist.set_norm(
                mcolors.TwoSlopeNorm(
                    vmin=action.minimum,
                    vcenter=action.midpoint,
                    vmax=action.maximum,
                )
            )
    if action.mode == "discrete":
        values = artist.get_array()
        minimum = action.minimum if action.minimum is not None else float(values.min())
        maximum = action.maximum if action.maximum is not None else float(values.max())
        levels = action.levels or 8
        boundaries = [minimum + (maximum - minimum) * index / levels for index in range(levels + 1)]
        artist.set_norm(mcolors.BoundaryNorm(boundaries, artist.get_cmap().N))
    colorbar_axes = [axis for axis in figure.axes if axis.get_label() == "<colorbar>"]
    if action.colorbar_visible is False:
        for axis in colorbar_axes:
            axis.remove()
    elif action.colorbar_visible is True and not colorbar_axes:
        orientation = "horizontal" if action.colorbar_anchor == "bottom" else "vertical"
        colorbar = figure.colorbar(artist, ax=_data_axes(figure), orientation=orientation)
        if action.colorbar_title is not None:
            colorbar.set_label(action.colorbar_title)


def _apply_error(figure: Figure, action: SetErrorStyle) -> None:
    axes = _data_axes(figure)
    for axis in axes:
        for container in axis.containers:
            if not isinstance(container, ErrorbarContainer):
                continue
            _line, caps, bars = container.lines
            for cap in caps:
                if action.bar_color is not None:
                    cap.set_color(action.bar_color)
                if action.bar_width_pt is not None:
                    cap.set_linewidth(action.bar_width_pt)
                if action.cap_size_pt is not None:
                    cap.set_markersize(action.cap_size_pt)
                if action.bar_opacity is not None:
                    cap.set_alpha(action.bar_opacity)
            for bar in bars:
                if action.bar_color is not None:
                    bar.set_color(action.bar_color)
                if action.bar_width_pt is not None:
                    bar.set_linewidth(action.bar_width_pt)
                if action.bar_opacity is not None:
                    bar.set_alpha(action.bar_opacity)
        for collection in axis.collections:
            if not isinstance(collection, PolyCollection):
                continue
            if action.band_fill_color is not None:
                collection.set_facecolor(action.band_fill_color)
            if action.band_fill_opacity is not None:
                collection.set_alpha(action.band_fill_opacity)
            if action.band_stroke_color is not None:
                collection.set_edgecolor(action.band_stroke_color)
            if action.band_stroke_width_pt is not None:
                collection.set_linewidth(action.band_stroke_width_pt)


def _label_text(value: float, action: SetDataLabels) -> str:
    if action.value_format == "scientific":
        body = f"{value:.3e}"
    elif action.value_format == "percent":
        body = f"{value * 100:g}%"
    else:
        body = f"{value:g}"
    return f"{action.prefix or ''}{body}{action.suffix or ''}"


def _apply_data_labels(figure: Figure, action: SetDataLabels) -> None:
    axes = _data_axes(figure)
    for axis in axes:
        for text in tuple(axis.texts):
            if text.get_gid() == f"plotagent-label:{action.target}":
                text.remove()
    if action.visible is False:
        return
    artist = _series_artists(figure, action.target)[0]
    axis = getattr(artist, "axes", axes[0]) or axes[0]
    points: list[tuple[float, float]] = []
    if isinstance(artist, Line2D):
        line_points: Any = artist.get_xydata()
        points = [(float(row[0]), float(row[1])) for row in line_points]
    elif isinstance(artist, PathCollection):
        collection_points: Any = artist.get_offsets()
        points = [(float(row[0]), float(row[1])) for row in collection_points]
    elif isinstance(artist, BarContainer):
        points = [
            (patch.get_x() + patch.get_width() / 2, patch.get_y() + patch.get_height())
            for patch in artist.patches
        ]
    for x, y in points:
        horizontal = action.position if action.position in {"left", "right"} else "center"
        vertical = action.position if action.position in {"above", "below", "center"} else "bottom"
        text = axis.text(
            x,
            y,
            _label_text(float(y), action),
            ha={"left": "right", "right": "left", "center": "center"}.get(horizontal, "center"),
            va={"above": "bottom", "below": "top", "center": "center"}.get(vertical, "bottom"),
            rotation=action.rotation_deg or 0,
            fontfamily=_font(action.font_family),
            fontsize=action.font_size_pt,
            fontweight=_weight(action.font_weight),
            color=action.font_color,
        )
        text.set_gid(f"plotagent-label:{action.target}")


def _apply_annotation(figure: Figure, action: AddAnnotation) -> None:
    axis = _data_axes(figure)[0]
    transform = axis.transData if action.coordinate_system == "data" else axis.transAxes
    text = axis.text(
        action.x,
        action.y,
        action.text,
        transform=transform,
        fontfamily=_font(action.font_family),
        fontsize=action.font_size_pt,
        fontweight=_weight(action.font_weight),
        fontstyle="italic" if action.italic else None,
        color=action.color,
        rotation=action.rotation_deg or 0,
    )
    text.set_gid(action.annotation_id)

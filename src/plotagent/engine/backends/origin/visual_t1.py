"""Shared T1 visual language applied to editable native Origin objects."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import blake2s
from math import isclose, isfinite, log10
from pathlib import Path
from re import IGNORECASE
from re import compile as re_compile
from typing import Any, Literal

from plotagent.engine.backends.origin.native_visual_t1 import (
    K07ErrorBandStyleState,
    K14ViolinStyleState,
    X40GroupStyleState,
    configure_k09_axis_labels,
    read_axis_line_show,
    read_axis_tick_font_size,
    read_color_scale_anchor,
    read_color_scale_tick_format,
    read_color_scale_title,
    read_color_scale_title_show,
    read_color_scale_typography,
    read_k09_axis_labels,
    read_k07_error_band_style,
    read_k14_violin_style,
    read_k22_contour_lines,
    read_scale_arrow,
    read_x09_group_fill_colors,
    read_x40_group_style,
    remove_graph_object,
    set_axis_line_show,
    set_axis_tick_font_size,
    set_color_scale_anchor,
    set_color_scale_tick_format,
    set_color_scale_title,
    set_color_scale_typography,
    set_k07_error_band_fill_transparency,
    set_k14_violin_style,
    set_k22_contour_lines_visible,
    set_scale_arrow,
    set_scale_arrow_head,
    set_x09_group_fill_color,
    set_x40_group_style,
)
from plotagent.engine.backends.origin.readback import axis_scale_matches
from plotagent.engine.contracts import (
    AddAnnotation,
    AddCallout,
    AddReferenceLine,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetCanvas,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.product_style import (
    K14_VIOLIN_STYLE,
    K22_FILLED_CONTOUR_STYLE,
    PRODUCT_SERIES_PALETTE,
    PRODUCT_TYPOGRAPHY,
)
from plotagent.engine.visual_t1 import (
    K09_VISUAL_CHART_PARAMETERS,
    effective_visual_actions,
    product_default_visual_actions,
    resolve_canvas_inches,
    resolve_k09_grouped_column_style,
)

_LINE_STYLE = {"solid": 1, "dash": 2, "dot": 3, "dash_dot": 4, "none": 0}
_K07_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3, "none": 0}
_REFERENCE_LINE_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3}
_BORDER_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3, "none": 0}
_BAR_COLUMN_PIDS = {203, 207, 213}
_LINE_SYMBOL_PIDS = {202}
_MARKER = {
    "none": 0,
    "square": 1,
    "circle": 2,
    "triangle_up": 3,
    "triangle_down": 4,
    "diamond": 5,
    "plus": 8,
    "cross": 9,
    "triangle_left": 11,
    "triangle_right": 12,
    "hexagon": 15,
    "star": 17,
    "pentagon": 18,
}
_INTERIOR = {"solid": 0, "open": 1, "hollow": 1}
_PALETTE = {
    "viridis": "Viridis",
    "plasma": "Plasma",
    "inferno": "Inferno",
    "magma": "Magma",
    "cividis": "ColorBlindSafe8",
    "turbo": "Rainbow_Modified",
    "blue_orange": "BlueOrange",
    "red_white_blue": "RedWhiteBlue",
    "blue_white_red": "RedWhiteBlue",
    "gray_scale": "Gray Scale",
    "fire": "Fire",
    "rainbow_modified": "Rainbow_Modified",
    "cool_warm": "Temperature",
    "spectral": "Spectrum",
    "terrain": "Topography1",
    "ocean": "Blue Planet",
}
_LABEL_POSITION = {"auto": 1, "center": 1, "left": 2, "right": 3, "above": 4, "below": 5}
_FONT_WEIGHT = {"auto": 0, "normal": 0, "bold": 1}
# Origin's Python graph proxy exposes the manual/fixed state differently
# before and after a project round-trip.  The value written by the renderer
# is 0, Origin's documented LabTalk manual state is 1, and OriginPro 2024
# currently reads the saved state back as 8.  The user-visible contract is
# the persisted pair of limits; these are the native encodings that are
# equivalent to a fixed two-sided range.
_FIXED_AXIS_NATIVE_RESCALE_MODES = frozenset({0, 1, 8})
_ORIGIN_FRAME_AXIS_NAMES = {
    0: "bottom",
    1: "left",
    2: "top",
    3: "right",
}
# PlotAgent uses a boxed product default for conventional single-layer
# Cartesian charts.  Matrix/color plots, native Trellis, centered-axis charts,
# and overlaid dual-axis templates keep their official Origin frame topology;
# mechanically boxing every native layer would create duplicate or misleading
# internal borders in those families.
_ORIGIN_FOUR_SIDED_FRAME_PROFILES = frozenset(
    {
        "K01",
        "K02",
        "K03",
        "K04",
        "K06",
        "K07",
        "K08",
        "K09",
        "K10",
        "K11",
        "K12",
        "K13",
        "K14",
        "K15",
        "K18",
        "K19",
        "S34",
        "X02",
        "X03",
        "X05",
        "X09",
        "X38",
        "X39",
        "X40",
    }
)


def apply_origin_visual_actions(
    op: Any,
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
    output: Path,
    *,
    post_apply_invariant: Callable[[Any], dict[str, Any]] | None = None,
    post_reopen_invariant: Callable[[Any], dict[str, Any]] | None = None,
) -> dict[str, object]:
    """Open the native project, apply the closed T1 vocabulary, save and verify.

    Chart binders produce official-template structure.  This second pass only
    touches public Origin graph objects and LabTalk properties; it never
    rebuilds plots or rewrites source data.
    """

    effective_actions = effective_visual_actions(
        (*product_default_visual_actions(document), *actions)
    )
    op.new()
    if not op.open(str(output), readonly=False, asksave=False):
        raise RuntimeError("Origin could not reopen the project for T1 visual edits")
    graph = _graph(op)
    template_frame = _capture_origin_template_frame(op, graph)
    product_frame = _apply_origin_product_frame(
        op,
        graph,
        document.profile_id,
        template_frame,
    )
    _apply_origin_product_typography(op, graph)
    k14_product_style = (
        _apply_k14_product_style(op, graph)
        if document.profile_id == "K14"
        else None
    )
    k09_subset_fill_action_ids = _apply_k09_subset_fill_colors(
        op,
        graph,
        document,
        effective_actions,
    )
    x40_group_style_action_ids = _apply_x40_group_style(
        op,
        graph,
        document,
        effective_actions,
    )
    reference_lines = tuple(
        action for action in effective_actions if isinstance(action, AddReferenceLine)
    )
    callouts = tuple(action for action in effective_actions if isinstance(action, AddCallout))
    for action in effective_actions:
        if isinstance(action, (AddReferenceLine, AddCallout)):
            continue
        if (
            isinstance(action, SetChartParameter)
            and action.parameter in K09_VISUAL_CHART_PARAMETERS
        ):
            # The three values share one indexed DataPlot and are resolved as
            # one final style by _configure_k09_presentation below.
            continue
        if action.action_id in k09_subset_fill_action_ids:
            continue
        if action.action_id in x40_group_style_action_ids:
            continue
        _apply_action(op, graph, document, action)
    k22_product_style = (
        _apply_k22_product_style(op, graph)
        if document.profile_id == "K22"
        else None
    )
    k01_physical_axes = _apply_k01_physical_axis_sides(
        graph,
        document.profile_id,
    )
    k09_presentation = (
        _configure_k09_presentation(op, graph, document, effective_actions)
        if document.profile_id == "K09"
        else None
    )
    _apply_reference_lines(
        op,
        graph,
        reference_lines,
        touched_actions=tuple(action for action in actions if isinstance(action, AddReferenceLine)),
    )
    _apply_callouts(
        op,
        graph,
        callouts,
        reference_lines=reference_lines,
        touched_actions=tuple(action for action in actions if isinstance(action, AddCallout)),
    )
    applied_invariant = None if post_apply_invariant is None else post_apply_invariant(graph)
    graph.activate()
    if not op.lt_exec("doc -uw;"):
        raise RuntimeError("Origin could not redraw after T1 visual edits")
    op.save(str(output))
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("Origin did not persist the T1 visual edits")
    op.new()
    if not op.open(str(output), readonly=True, asksave=False):
        raise RuntimeError("Origin could not fresh-reopen the T1 visual project")
    reopened = _graph(op)
    snapshot = _verify_actions(op, reopened, document, effective_actions)
    snapshot["origin_product_frame"] = _verify_origin_product_frame(
        op,
        reopened,
        effective_actions,
        product_frame,
    )
    snapshot["origin_product_opposite_axes"] = _verify_origin_product_opposite_axes(
        reopened, document.profile_id
    )
    if k01_physical_axes is not None:
        snapshot["k01_physical_axes"] = _verify_k01_physical_axis_sides(
            reopened,
            document.profile_id,
        )
    snapshot["origin_product_typography"] = _verify_origin_product_typography(
        op,
        reopened,
        effective_actions,
    )
    if k14_product_style is not None:
        snapshot["k14_product_style"] = _verify_k14_product_style(
            op,
            reopened,
            effective_actions,
            k14_product_style,
        )
    if k22_product_style is not None:
        snapshot["k22_product_style"] = _verify_k22_product_style(
            op,
            reopened,
        )
    if k09_presentation is not None:
        snapshot["k09_presentation"] = _verify_k09_presentation(
            op,
            reopened,
            k09_presentation,
        )
    if post_reopen_invariant is not None:
        snapshot["post_edit_invariant"] = post_reopen_invariant(reopened)
    elif applied_invariant is not None:
        snapshot["post_edit_invariant"] = applied_invariant
    snapshot["actions"] = len(actions)
    snapshot["effective_actions"] = len(effective_actions)
    snapshot["fresh_reopen"] = True
    return snapshot


def _graph(op: Any) -> Any:
    graphs = list(op.pages("g"))
    if not graphs:
        raise RuntimeError("Origin T1 visual pass found no graph page")
    return graphs[0]


def _layers(graph: Any) -> list[Any]:
    layers = list(graph)
    if not layers:
        raise RuntimeError("Origin T1 visual pass found no graph layer")
    return layers


def _apply_k14_product_style(
    op: Any,
    graph: Any,
) -> tuple[K14ViolinStyleState, ...]:
    """Materialize K14 defaults on the native fields that paint the violin.

    OriginPro 2024 PID 206 stores the visible body below the center line in
    ``Patterns.Below`` and the visible outline on the root line node.  The
    generic pattern options target ``Patterns.Above`` and can therefore read
    back successfully without changing the rendered violin.
    """

    layer = _layers(graph)[0]
    plot_count = _plot_count(op, graph, layer)
    _activate_layer(op, graph, layer)
    if plot_count > 1 and not op.lt_exec("layer -gu;"):
        raise RuntimeError("Origin could not make K14 violin formatting independent")
    expected: list[K14ViolinStyleState] = []
    for plot_index in range(1, plot_count + 1):
        fill_color = _color(
            op,
            K14_VIOLIN_STYLE.palette[
                (plot_index - 1) % len(K14_VIOLIN_STYLE.palette)
            ],
        )
        state = K14ViolinStyleState(
            fill_color=fill_color,
            fill_transparency=(1 - K14_VIOLIN_STYLE.fill_opacity) * 100,
            fill_only=1,
            follow_line_transparency=0,
            outline_color=_color(op, K14_VIOLIN_STYLE.outline_color),
            outline_width=K14_VIOLIN_STYLE.outline_width_pt,
            outline_style=_BORDER_STYLE[K14_VIOLIN_STYLE.outline_style],
        )
        set_k14_violin_style(
            op,
            str(graph.name),
            _layer_index(layer),
            plot_index,
            fill_color=state.fill_color,
            fill_transparency=state.fill_transparency,
            outline_color=state.outline_color,
            outline_width=state.outline_width,
            outline_style=state.outline_style,
        )
        expected.append(state)
    legend = layer.label("legend")
    if legend is not None:
        legend.set_int("show", int(K14_VIOLIN_STYLE.legend_visible))
    return tuple(expected)


def _apply_k22_product_style(op: Any, graph: Any) -> dict[str, object]:
    """Materialize K22 defaults on native properties with visible ownership.

    The CONTOUR.otpu template owns interval boundary visibility and color-scale
    typography outside the public SetColorMap fields.  Apply these product
    defaults after public edits so Origin cannot reintroduce template lines or
    the template's 22 pt scale title while rebuilding its color map.
    """

    layer = _layers(graph)[0]
    set_k22_contour_lines_visible(
        op,
        str(graph.name),
        _layer_index(layer),
        1,
        K22_FILLED_CONTOUR_STYLE.contour_lines_visible,
    )
    set_color_scale_typography(
        op,
        str(graph.name),
        _layer_index(layer),
        title_font_size_pt=K22_FILLED_CONTOUR_STYLE.colorbar_title_font_size_pt,
        tick_font_size_pt=K22_FILLED_CONTOUR_STYLE.colorbar_tick_font_size_pt,
    )
    return {
        "contour_lines_visible": K22_FILLED_CONTOUR_STYLE.contour_lines_visible,
        "colorbar_title_font_size_pt": (
            K22_FILLED_CONTOUR_STYLE.colorbar_title_font_size_pt
        ),
        "colorbar_tick_font_size_pt": K22_FILLED_CONTOUR_STYLE.colorbar_tick_font_size_pt,
    }


def _verify_k22_product_style(op: Any, graph: Any) -> dict[str, object]:
    """Verify K22's visible contour and color-scale defaults after fresh reopen."""

    layer = _layers(graph)[0]
    layer_index = _layer_index(layer)
    lines = read_k22_contour_lines(op, str(graph.name), layer_index, 1)
    if lines.interval_count < 1:
        raise RuntimeError("Origin K22 contour line readback has no intervals")
    _require_equal("K22 visible contour interval lines", lines.visible_interval_count, 0)
    _require_equal("K22 above-range contour line", lines.above_visible, 0)
    typography = read_color_scale_typography(op, str(graph.name), layer_index)
    _require_number(
        "K22 color scale title font size",
        typography.title_font_size_pt,
        K22_FILLED_CONTOUR_STYLE.colorbar_title_font_size_pt,
    )
    _require_number(
        "K22 color scale tick font size",
        typography.tick_font_size_pt,
        K22_FILLED_CONTOUR_STYLE.colorbar_tick_font_size_pt,
    )
    anchor = read_color_scale_anchor(op, str(graph.name), layer_index)
    if anchor.arrangement == 1:
        _require_number("K22 right color scale width", anchor.width, 300.0)
    elif anchor.arrangement == 2:
        _require_number("K22 bottom color scale height", anchor.height, 300.0)
    else:
        raise RuntimeError(
            f"Origin K22 color scale has unsupported arrangement {anchor.arrangement}"
        )
    return {
        "contour_interval_count": lines.interval_count,
        "visible_contour_interval_count": lines.visible_interval_count,
        "above_contour_visible": lines.above_visible,
        "colorbar_title_font_size_pt": typography.title_font_size_pt,
        "colorbar_tick_font_size_pt": typography.tick_font_size_pt,
        "colorbar_arrangement": anchor.arrangement,
        "colorbar_width": anchor.width,
        "colorbar_height": anchor.height,
        "fresh_reopen": True,
    }


def _layer_index(layer: Any) -> int:
    """Return Origin's stable one-based layer index.

    OriginPro creates a fresh Python proxy whenever a graph is enumerated, so
    Python object identity is not a valid way to recover a layer position.
    """

    return int(layer.index()) + 1


def _target_key(target: str) -> str:
    return target.rsplit(".", 1)[-1]


def _ordinal(key: str) -> int:
    for prefix in ("series_", "column_", "group_", "area_", "component_", "facet_"):
        if key.startswith(prefix):
            try:
                return max(1, int(key.rsplit("_", 1)[-1]))
            except ValueError:
                return 1
    return 1


def _layer_and_plot(graph: Any, target: str) -> tuple[Any, int]:
    layers = _layers(graph)
    key = _target_key(target)
    if key in {"right", "cumulative"} and len(layers) > 1:
        return layers[-1], 1
    if key.startswith("facet_"):
        index = min(_ordinal(key), len(layers))
        return layers[index - 1], 1
    return layers[0], _ordinal(key)


_X40_COLUMN_STYLE_FIELDS = frozenset(
    {
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    }
)
_X40_CONNECTOR_STYLE_FIELDS = frozenset(
    {"visible", "line_stroke_color", "line_width_pt", "line_style"}
)


def _requested_series_style_fields(action: SetSeriesStyle) -> frozenset[str]:
    return frozenset(name for name in _K09_SERIES_STYLE_FIELDS if getattr(action, name) is not None)


def _x40_style_action(action: PlotEngineAction) -> SetSeriesStyle | None:
    if not isinstance(action, SetSeriesStyle):
        return None
    key = _target_key(action.target)
    if key not in {"column_1", "column_2", "connector"}:
        return None
    requested = _requested_series_style_fields(action)
    allowed = _X40_CONNECTOR_STYLE_FIELDS if key == "connector" else _X40_COLUMN_STYLE_FIELDS
    unsupported = sorted(requested - allowed)
    if unsupported:
        raise ValueError(
            "Origin X40 preserves its native dependent Before/After group; "
            f"{key} does not support {', '.join(unsupported)}"
        )
    return action


def _apply_x40_group_style(
    op: Any,
    graph: Any,
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
) -> frozenset[str]:
    """Apply X40 member and connector styles without destroying its group."""

    if document.profile_id != "X40":
        return frozenset()
    style_actions = tuple(
        action for candidate in actions if (action := _x40_style_action(candidate)) is not None
    )
    if not style_actions:
        return frozenset()

    layer = _layers(graph)[0]
    state = read_x40_group_style(op, str(graph.name), _layer_index(layer))
    marker_shapes = list(state.marker_shapes)
    marker_sizes = list(state.marker_sizes)
    marker_interiors = list(state.marker_interiors)
    marker_edge_colors = list(state.marker_edge_colors)
    marker_fill_colors = list(state.marker_fill_colors)
    connector_visible = state.connector_visible
    connector_style = state.connector_style
    connector_width = state.connector_width
    connector_color = state.connector_color

    for action in style_actions:
        key = _target_key(action.target)
        if key == "connector":
            if action.visible is not None:
                connector_visible = action.visible
            if action.line_style is not None:
                if action.line_style == "none":
                    connector_visible = False
                else:
                    connector_style = _REFERENCE_LINE_STYLE[action.line_style]
            if action.line_width_pt is not None:
                connector_width = action.line_width_pt
            if action.line_stroke_color is not None:
                connector_color = _color(op, action.line_stroke_color)
            continue

        member = _ordinal(key) - 1
        if action.marker_shape is not None:
            marker_shapes[member] = _MARKER[action.marker_shape]
        if action.marker_size_pt is not None:
            marker_sizes[member] = action.marker_size_pt
        if action.marker_interior is not None:
            marker_interiors[member] = _INTERIOR[action.marker_interior]
        if action.marker_stroke_color is not None:
            marker_edge_colors[member] = _color(op, action.marker_stroke_color)
        if action.marker_interior in {"open", "hollow"}:
            marker_fill_colors[member] = _color(op, "#FFFFFF")
        elif action.marker_fill_color is not None:
            marker_fill_colors[member] = _color(op, action.marker_fill_color)

    set_x40_group_style(
        op,
        str(graph.name),
        _layer_index(layer),
        marker_shapes=(marker_shapes[0], marker_shapes[1]),
        marker_sizes=(marker_sizes[0], marker_sizes[1]),
        marker_interiors=(marker_interiors[0], marker_interiors[1]),
        marker_edge_colors=(marker_edge_colors[0], marker_edge_colors[1]),
        marker_fill_colors=(marker_fill_colors[0], marker_fill_colors[1]),
        connector_visible=connector_visible,
        connector_style=connector_style,
        connector_width=connector_width,
        connector_color=connector_color,
    )
    return frozenset(action.action_id for action in style_actions)


_K09_SERIES_STYLE_FIELDS = (
    "visible",
    "line_stroke_color",
    "line_width_pt",
    "line_style",
    "line_opacity",
    "marker_shape",
    "marker_size_pt",
    "marker_interior",
    "marker_fill_color",
    "marker_stroke_color",
    "marker_stroke_width_pt",
    "marker_opacity",
    "fill_color",
    "fill_opacity",
    "fill_stroke_color",
    "fill_stroke_width_pt",
    "fill_stroke_style",
)


def _k09_subset_fill_action(
    document: PlotDocument,
    action: PlotEngineAction,
) -> SetSeriesStyle | None:
    """Return a K09 subset fill edit and reject false per-plot promises.

    Origin's official ``plot_gindexed`` route deliberately owns one native
    DataPlot with multiple subsets. A semantic ``group_n`` is therefore not
    native plot ``n``. Origin exposes subgroup fill color through the native
    custom increment list; other ``SetSeriesStyle`` fields do not have the
    same independently verified subset contract and must not silently mutate
    the whole DataPlot.
    """

    if document.profile_id != "K09" or not isinstance(action, SetSeriesStyle):
        return None
    if not _target_key(action.target).startswith("group_"):
        return None
    requested = tuple(
        name for name in _K09_SERIES_STYLE_FIELDS if getattr(action, name) is not None
    )
    if requested == ("fill_color",):
        return action
    raise ValueError(
        "Origin K09 indexed subgroups currently support only independent fill_color; "
        f"requested {', '.join(requested)} for {_target_key(action.target)}"
    )


def _k09_subset_count(graph: Any) -> int:
    legend = _layers(graph)[0].label("legend")
    count = 0 if legend is None else legend.text.count("\\l(")
    if count < 1:
        raise RuntimeError("Origin K09 legend exposes no native subset samples")
    return count


def _read_k09_subset_fill_colors(
    op: Any,
    graph: Any,
    count: int,
    *,
    variable: str,
) -> tuple[int, ...]:
    layer = _layers(graph)[0]
    plot_range = _checked_plot_range(op, graph, layer, 1)
    plot_ref = _bind_plot_range(op, plot_range)
    if not op.lt_exec(f"get {plot_ref} -cue __PAT1K09ENABLED;"):
        raise RuntimeError("Origin could not read the K09 custom color-list state")
    enabled = int(op.lt_float("__PAT1K09ENABLED"))
    if enabled:
        if not op.lt_exec(f"dataset {variable}; get {plot_ref} -cuf {variable};"):
            raise RuntimeError("Origin could not read the K09 subset fill-color list")
        values = tuple(int(op.lt_float(f"{variable}[{index}]")) for index in range(1, count + 1))
    else:
        if not op.lt_exec(f"get {plot_ref} -pfbi __PAT1K09START;"):
            raise RuntimeError("Origin could not read the K09 fill increment start")
        start = int(op.lt_float("__PAT1K09START"))
        values = tuple(start + index for index in range(count))
    if any(not isfinite(float(value)) for value in values):
        raise RuntimeError("Origin returned an invalid K09 subset fill-color list")
    return values


def _apply_k09_subset_fill_colors(
    op: Any,
    graph: Any,
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
) -> frozenset[str]:
    edits = tuple(
        action
        for candidate in actions
        if (action := _k09_subset_fill_action(document, candidate)) is not None
    )
    if document.profile_id != "K09":
        return frozenset()
    count = _k09_subset_count(graph)
    colors = list(
        _color(op, PRODUCT_SERIES_PALETTE[index % len(PRODUCT_SERIES_PALETTE)])
        for index in range(count)
    )
    for action in edits:
        ordinal = _ordinal(_target_key(action.target))
        if ordinal > count:
            raise ValueError(
                f"Origin K09 target subset {ordinal} is outside the native subset count {count}"
            )
        assert action.fill_color is not None
        colors[ordinal - 1] = _color(op, action.fill_color)
    expression = ",".join(str(value) for value in colors)
    layer = _layers(graph)[0]
    plot_range = _checked_plot_range(op, graph, layer, 1)
    plot_ref = _bind_plot_range(op, plot_range)
    command = (
        f"dataset __PAT1K09COLORS={{{expression}}}; "
        f"set {plot_ref} -pfbi 1; set {plot_ref} -cue 1; "
        f"set {plot_ref} -cuf __PAT1K09COLORS;"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin rejected the K09 native subset fill-color list")
    return frozenset(action.action_id for action in edits)


def _verify_k09_subset_fill_color(
    op: Any,
    graph: Any,
    action: SetSeriesStyle,
) -> dict[str, object]:
    count = _k09_subset_count(graph)
    ordinal = _ordinal(_target_key(action.target))
    if ordinal > count:
        raise ValueError(
            f"Origin K09 target subset {ordinal} is outside the native subset count {count}"
        )
    colors = _read_k09_subset_fill_colors(
        op,
        graph,
        count,
        variable="__PAT1K09READ",
    )
    assert action.fill_color is not None
    expected = _color(op, action.fill_color)
    observed = colors[ordinal - 1]
    _require_equal("K09 subset fill color", observed, expected)
    return {"subset": ordinal, "fill_color": observed, "custom_increment_list": True}


_K09_LEGEND_SAMPLE = re_compile(r"\\l\([^)]*\)", IGNORECASE)
_K09_LEGEND_FILL = re_compile(r"PatternFill:(#[0-9A-Fa-f]{6})")


def _k09_legend_parts(text: str) -> tuple[str, tuple[str, ...]]:
    matches = tuple(_K09_LEGEND_SAMPLE.finditer(text))
    if not matches:
        raise RuntimeError("Origin K09 legend contains no subset entries")
    title = text[: matches[0].start()].strip()
    labels: list[str] = []
    for index, match in enumerate(matches):
        stop = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        labels.append(text[match.end() : stop].strip())
    if any(not label for label in labels):
        raise RuntimeError("Origin K09 legend contains an empty subset label")
    return title, tuple(labels)


def _k09_color_html(op: Any, value: int) -> str:
    rgb = int(op.lt_float(f"ocolor2rgb({value})"))
    if rgb < 0:
        raise RuntimeError("Origin returned an invalid K09 RGB legend color")
    return f"#{rgb & 0xFF:02X}{(rgb >> 8) & 0xFF:02X}{(rgb >> 16) & 0xFF:02X}"


def _k09_requested_legend_columns(actions: tuple[PlotEngineAction, ...]) -> int | None:
    requested = tuple(
        action.columns
        for action in actions
        if isinstance(action, SetLegend) and action.columns is not None
    )
    return requested[-1] if requested else None


def _k09_requested_x_tick_font_size(
    actions: tuple[PlotEngineAction, ...],
) -> float | None:
    requested = tuple(
        action.tick_font_size_pt
        for action in actions
        if isinstance(action, SetAxis)
        and _target_key(action.target) == "x"
        and action.tick_font_size_pt is not None
    )
    return requested[-1] if requested else None


def _configure_k09_presentation(
    op: Any,
    graph: Any,
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
) -> dict[str, object]:
    """Persist the publication-facing defaults missing from ``plot_gindexed``.

    Origin's official indexed-column route creates two table-label rows and
    boxed cells. K09 needs only one merged category label per bar group; the
    subgroup names live in the legend. The presentation pass also adds half
    a data step at each side and defaults the remaining category row to 12 pt
    unless the user explicitly requested another tick-label size.
    """

    layer = _layers(graph)[0]
    configure_k09_axis_labels(op, str(graph.name), _layer_index(layer))
    explicit_x_bounds = any(
        isinstance(action, SetAxis)
        and _target_key(action.target) == "x"
        and (action.minimum is not None or action.maximum is not None)
        for action in actions
    )
    x_from, x_to, x_step = (float(value) for value in layer.xlim)
    if (
        not explicit_x_bounds
        and isclose(x_from % 1, 0.5, abs_tol=1e-7)
        and isclose(
            x_to % 1,
            0.5,
            abs_tol=1e-7,
        )
    ):
        layer.set_xlim(x_from - 0.5, x_to + 0.5, x_step)
    category_tick_font = (
        _k09_requested_x_tick_font_size(actions) or PRODUCT_TYPOGRAPHY.tick_font_size_pt
    )
    set_axis_tick_font_size(
        op,
        str(graph.name),
        _layer_index(layer),
        _axis_native_code("x"),
        category_tick_font,
    )

    bar_style = resolve_k09_grouped_column_style(document, actions)
    plot_range = _checked_plot_range(op, graph, layer, 1)
    plot_ref = _bind_plot_range(op, plot_range)
    border = f'color("{bar_style.border_color}")' if bar_style.bar_border_visible else "-4"
    if not op.lt_exec(
        f"set {plot_ref} -pbc {border}; "
        f"set {plot_ref} -vg {bar_style.within_group_gap_percent:.12g};"
    ):
        raise RuntimeError("Origin rejected the K09 border or within-group gap")
    _set_plot_property(
        op,
        graph,
        layer,
        1,
        "subsetgap",
        bar_style.between_group_gap_percent,
    )

    legend = layer.label("legend")
    if legend is None:
        raise RuntimeError("Origin K09 lost its legend before color materialization")
    count = _k09_subset_count(graph)
    title, labels = _k09_legend_parts(legend.text)
    if len(labels) != count:
        raise RuntimeError("Origin K09 legend label count differs from its subsets")
    colors = _read_k09_subset_fill_colors(
        op,
        graph,
        count,
        variable="__PAT1K09LEGEND",
    )
    legend_colors = tuple(_k09_color_html(op, value) for value in colors)
    entries = tuple(
        f"\\L(1, PatternFill:{color} BorderColor:{color} Width:40 Height:50)\\sc {label}"
        for color, label in zip(legend_colors, labels, strict=True)
    )
    legend.text = (f"{title}\n" if title else "") + "\n".join(entries)
    legend.set_int("link", 0)
    columns = _k09_requested_legend_columns(actions)
    if columns is not None:
        layer.activate()
        if columns == 1:
            if not op.lt_exec("legend -av;"):
                raise RuntimeError("Origin could not arrange the K09 legend vertically")
        elif columns == count:
            if not op.lt_exec(f"label -al {columns};"):
                raise RuntimeError("Origin could not arrange the K09 legend into one row")
        else:
            raise ValueError(
                "Origin K09 indexed-subset legend currently supports either one "
                f"column or one row of {count} columns"
            )

    tick_font = read_axis_tick_font_size(
        op,
        str(graph.name),
        _layer_index(layer),
        _axis_native_code("x"),
    )
    return {
        "bar_border_visible": bar_style.bar_border_visible,
        "bar_border_color": (
            _color(op, bar_style.border_color) if bar_style.bar_border_visible else -4
        ),
        "within_group_gap_percent": bar_style.within_group_gap_percent,
        "between_group_gap_percent": bar_style.between_group_gap_percent,
        "legend_fill_colors": list(legend_colors),
        "tick_font_pt": tick_font,
        "xlim": [float(value) for value in layer.xlim],
    }


def _verify_k09_presentation(
    op: Any,
    graph: Any,
    expected: dict[str, object],
) -> dict[str, object]:
    layer = _layers(graph)[0]
    state = read_k09_axis_labels(op, str(graph.name), _layer_index(layer))
    if state.table_enabled != 1 or state.table_design != 0 or state.subgroup_row_hidden != 1:
        raise RuntimeError(f"Origin K09 axis-label presentation differs after reopen: {state}")
    observed_xlim = tuple(float(value) for value in layer.xlim)
    expected_xlim_value = expected["xlim"]
    if not isinstance(expected_xlim_value, (list, tuple)):
        raise RuntimeError("Origin K09 expected category-axis padding is invalid")
    expected_xlim = tuple(float(value) for value in expected_xlim_value)
    if len(observed_xlim) != len(expected_xlim) or any(
        not isclose(observed, wanted, abs_tol=1e-7)
        for observed, wanted in zip(observed_xlim, expected_xlim, strict=True)
    ):
        raise RuntimeError("Origin K09 category-axis padding differs after reopen")
    tick_font = read_axis_tick_font_size(
        op,
        str(graph.name),
        _layer_index(layer),
        _axis_native_code("x"),
    )
    expected_tick_font = expected["tick_font_pt"]
    if not isinstance(expected_tick_font, (int, float)):
        raise RuntimeError("Origin K09 expected category-label font size is invalid")
    if not isclose(tick_font, float(expected_tick_font), abs_tol=0.01):
        raise RuntimeError("Origin K09 category-label font size differs after reopen")
    expected_colors_value = expected["legend_fill_colors"]
    if not isinstance(expected_colors_value, (list, tuple)):
        raise RuntimeError("Origin K09 expected legend colors are invalid")
    expected_colors = tuple(str(value).upper() for value in expected_colors_value)
    observed_colors: tuple[str, ...] = ()
    if expected_colors:
        legend = layer.label("legend")
        if legend is None:
            raise RuntimeError("Origin K09 colored legend differs after reopen")
        observed_colors = tuple(
            match.group(1).upper() for match in _K09_LEGEND_FILL.finditer(legend.text)
        )
        if observed_colors != expected_colors:
            raise RuntimeError("Origin K09 legend colors differ from the plotted subsets")
    plot_range = _checked_plot_range(op, graph, layer, 1)
    border_color = int(_get_plot_option(op, plot_range, "-pbc"))
    within_gap = float(_get_plot_option(op, plot_range, "-vg"))
    between_gap = float(_get_plot_property(op, graph, layer, 1, "subsetgap"))
    _require_equal(
        "K09 bar border color",
        border_color,
        int(expected["bar_border_color"]),
    )
    _require_number(
        "K09 within-group gap",
        within_gap,
        float(expected["within_group_gap_percent"]),
    )
    _require_number(
        "K09 between-group gap",
        between_gap,
        float(expected["between_group_gap_percent"]),
    )
    return {
        "bar_border_visible": border_color != -4,
        "bar_border_color": border_color,
        "within_group_gap_percent": within_gap,
        "between_group_gap_percent": between_gap,
        "category_axis_xlim": list(observed_xlim),
        "category_tick_font_pt": tick_font,
        "legend_fill_colors": list(observed_colors),
        "subgroup_row_hidden": state.subgroup_row_hidden,
        "table_design": state.table_design,
        "table_enabled": state.table_enabled,
    }


def _activate_layer(op: Any, graph: Any, layer: Any) -> int:
    layer_index = _layer_index(layer)
    if not op.lt_exec(f"window -a {graph.name}; {graph.name}!page.active={layer_index};"):
        raise RuntimeError("Origin could not activate the targeted graph layer")
    return layer_index


def _plot_count(op: Any, graph: Any, layer: Any) -> int:
    _activate_layer(op, graph, layer)
    if not op.lt_exec("layer -c; __PAT1COUNT=count;"):
        raise RuntimeError("Origin could not enumerate native data plots")
    return int(op.lt_float("__PAT1COUNT"))


def _checked_plot_range(op: Any, graph: Any, layer: Any, plot_index: int) -> str:
    count = _plot_count(op, graph, layer)
    if plot_index < 1 or plot_index > count:
        raise ValueError(
            f"Origin target plot {plot_index} is outside the native plot count {count}"
        )
    return _plot_range(graph, layer, plot_index)


def _get_plot_option(op: Any, plot_range: str, option: str) -> float:
    if not op.lt_exec(f"range __PAT1P={plot_range}; get __PAT1P {option} __PAT1VALUE;"):
        raise RuntimeError(f"Origin could not read back plot option {option}")
    return float(op.lt_float("__PAT1VALUE"))


def _get_plot_option_str(op: Any, plot_range: str, option: str) -> str:
    if not op.lt_exec(f"range __PAT1P={plot_range}; get __PAT1P {option} __PAT1TEXT$;"):
        raise RuntimeError(f"Origin could not read back plot option {option}")
    return str(op.get_lt_str("__PAT1TEXT"))


def _set_plot_property(
    op: Any,
    graph: Any,
    layer: Any,
    plot_index: int,
    property_path: str,
    value: float,
) -> None:
    _activate_layer(op, graph, layer)
    if not op.lt_exec(f"layer.plot{plot_index}.{property_path}={value:.12g};"):
        raise RuntimeError(f"Origin rejected plot property {property_path}")


def _get_plot_property(
    op: Any,
    graph: Any,
    layer: Any,
    plot_index: int,
    property_path: str,
) -> float:
    _activate_layer(op, graph, layer)
    return float(op.lt_float(f"layer.plot{plot_index}.{property_path}"))


def _error_plots(op: Any, graph: Any, target: str) -> tuple[Any, tuple[int, ...]]:
    layer, _ = _layer_and_plot(graph, target)
    key = _target_key(target)
    ordinal = _ordinal(key)
    error_plots: list[int] = []
    for plot_index in range(1, _plot_count(op, graph, layer) + 1):
        plot_range = _plot_range(graph, layer, plot_index)
        if int(_get_plot_option(op, plot_range, "-pt")) in {231, 233}:
            error_plots.append(plot_index)
    if key == "primary":
        if not error_plots:
            raise ValueError("Origin target primary has no native error plots")
        return layer, tuple(error_plots)
    if ordinal > len(error_plots):
        raise ValueError(
            f"Origin target error series {ordinal} is outside the native error plot count "
            f"{len(error_plots)}"
        )
    return layer, (error_plots[ordinal - 1],)


def _plot_range(graph: Any, layer: Any, plot_index: int) -> str:
    layer_index = _layer_index(layer)
    return f"[{graph.name}]{layer_index}!{plot_index}"


def _color(op: Any, value: str) -> int:
    return int(op.lt_float(f'color("{value}")'))


def _execute_plot_commands(op: Any, commands: list[str], *, operation: str) -> None:
    for command in commands:
        if not op.lt_exec(command + ";"):
            raise RuntimeError(f"Origin rejected T1 {operation}: {command}")


def _bind_plot_range(op: Any, plot_range: str) -> str:
    if not op.lt_exec(f"range __PAT1P={plot_range};"):
        raise RuntimeError(f"Origin could not bind native plot range {plot_range}")
    return "__PAT1P"


def _font(op: Any, value: str | None) -> int | None:
    if value in {None, "auto"}:
        return None
    return int(op.lt_float(f'font("{value}")'))


def _label(layer: Any, name: str, text: str) -> Any:
    result = layer.label(name)
    if result is None:
        result = layer.add_label(text)
        if result is None:
            raise RuntimeError(f"Origin could not create graph label {name}")
        result.name = name
    return result


def _text_style(text: str) -> tuple[str, bool, bool]:
    bold = False
    italic = False
    value = text
    while len(value) >= 4:
        if value.startswith(r"\b(") and value.endswith(")"):
            bold = True
            value = value[3:-1]
        elif value.startswith(r"\i(") and value.endswith(")"):
            italic = True
            value = value[3:-1]
        else:
            break
    return value, bold, italic


def _styled_text(
    text: str,
    *,
    weight: str | None,
    italic: bool | None,
) -> str:
    plain, current_bold, current_italic = _text_style(text)
    bold = current_bold if weight is None else weight == "bold"
    slanted = current_italic if italic is None else italic
    value = rf"\b({plain})" if bold else plain
    return rf"\i({value})" if slanted else value


def _replace_styled_text(current: str, replacement: str) -> str:
    _plain, bold, italic = _text_style(current)
    value = rf"\b({replacement})" if bold else replacement
    return rf"\i({value})" if italic else value


def _style_label(
    op: Any, label: Any, action: SetTitle | SetAxis | SetLegend | AddAnnotation
) -> None:
    family = getattr(action, "font_family", None)
    size = getattr(action, "font_size_pt", None)
    weight = getattr(action, "font_weight", None)
    italic = getattr(action, "italic", None)
    color = getattr(action, "color", None)
    font_index = _font(op, family)
    if font_index is not None:
        label.set_int("font", font_index)
    if size is not None:
        label.set_float("fsize", size)
    label.text = _styled_text(label.text, weight=weight, italic=italic)
    if color is not None:
        label.set_int("color", _color(op, color))


def _graph_page_size(graph: Any) -> tuple[float, float]:
    """Read the physical graph-page size through PyOrigin's page API.

    ``GPage.get_float('width')`` addresses the page theme tree and does not
    mutate the native GraphPage dimensions in OriginPro 2024.  The wrapped
    PyOrigin object exposes the authoritative inch-based GetWidth/GetHeight
    pair.  Origin's documented LabTalk page size is stored in printer dots,
    so writes use ``page.width/page.resx`` and ``page.height/page.resy`` rather
    than assuming the theme-tree values are inches.  The fallback only keeps
    older deterministic wrappers usable.
    """

    native = getattr(graph, "obj", None)
    get_width = getattr(native, "GetWidth", None)
    get_height = getattr(native, "GetHeight", None)
    if callable(get_width) and callable(get_height):
        return float(get_width()), float(get_height())
    return float(graph.get_float("width")), float(graph.get_float("height"))


def _set_graph_page_size(graph: Any, width: float, height: float) -> None:
    native = getattr(graph, "obj", None)
    execute = getattr(native, "LT_execute", None)
    if callable(execute):
        set_num_prop = getattr(native, "SetNumProp", None)
        if callable(set_num_prop) and not set_num_prop("KAR", 0):
            raise RuntimeError("Origin could not disable graph-page aspect locking")
        resolution_x = float(graph.get_float("resx"))
        resolution_y = float(graph.get_float("resy"))
        if resolution_x <= 0 or resolution_y <= 0:
            raise RuntimeError("Origin graph-page printer resolution is invalid")
        command = (
            f"page.width={round(width * resolution_x)}; page.height={round(height * resolution_y)};"
        )
        if not execute(command):
            raise RuntimeError("Origin could not set the native graph-page dimensions")
        if not execute("gfitp margin:=5 aspect:=0;"):
            raise RuntimeError("Origin could not fit graph layers to the resized page")
        return
    graph.set_float("width", width)
    graph.set_float("height", height)


def _apply_action(op: Any, graph: Any, document: PlotDocument, action: PlotEngineAction) -> None:
    if isinstance(action, SetCanvas):
        current_width, current_height = _graph_page_size(graph)
        width, height = resolve_canvas_inches(
            current_width,
            current_height,
            action,
        )
        _set_graph_page_size(graph, width, height)
    elif isinstance(action, SetTitle):
        layer = _layers(graph)[0]
        title = _label(layer, "_ENGINE_TITLE", action.text or "")
        if action.text is not None:
            title.text = _replace_styled_text(title.text, action.text)
        title.set_int("show", int(bool(title.text)))
        title.set_int("attach", 1)
        title.set_float("x1", 0.5)
        title.set_float("y1", 0.012)
        _style_label(op, title, action)
        if action.font_size_pt is None:
            title.set_float("fsize", PRODUCT_TYPOGRAPHY.title_font_size_pt)
    elif isinstance(action, SetAxis):
        _apply_axis(op, graph, action)
    elif isinstance(action, SetSeriesStyle):
        _apply_series(op, graph, action, profile_id=document.profile_id)
    elif isinstance(action, SetLegend):
        _apply_legend(op, graph, action, profile_id=document.profile_id)
    elif isinstance(action, SetColorMap):
        _apply_colormap(op, graph, action, profile_id=document.profile_id)
    elif isinstance(action, SetErrorStyle):
        _apply_error(op, graph, action, profile_id=document.profile_id)
    elif isinstance(action, SetDataLabels):
        _apply_data_labels(op, graph, action)
    elif isinstance(action, AddAnnotation):
        _apply_annotation(op, graph, action)
    elif isinstance(action, AddReferenceLine):
        _apply_reference_line(op, graph, action)
    else:  # pragma: no cover - caller passes the closed visual action tuple
        raise TypeError(f"unsupported Origin visual action {action.operation}")


def _axis_target(graph: Any, target: str) -> tuple[Any, Literal["x", "y"]]:
    layers = _layers(graph)
    key = _target_key(target)
    if key == "x":
        return layers[0], "x"
    if key in {"y", "y_left"}:
        return layers[0], "y"
    if key == "y_right":
        return layers[-1], "y"
    raise ValueError(f"unknown Origin axis target {target}")


def _axis_side_bit(target: str) -> int:
    return 2 if _target_key(target) == "y_right" else 1


def _axis_native_code(target: str) -> int:
    key = _target_key(target)
    if key == "x":
        return 0
    if key in {"y", "y_left"}:
        return 1
    if key == "y_right":
        return 3
    raise ValueError(f"unknown Origin axis target {target}")


def _axis_visual_prefix(axis_name: Literal["x", "y"], target: str) -> str:
    """Return the LabTalk prefix for the requested physical axis side.

    Origin stores a layer's Y scale once, but side-specific visual properties
    live under ``y`` (left) and ``y2`` (right).  Using ``y`` on the second
    layer can therefore pass a scale-level readback while editing the hidden
    left-side formatting instead of the visible right axis.
    """

    return f"{axis_name}2" if _target_key(target) == "y_right" else axis_name


def _capture_origin_template_frame(
    op: Any,
    graph: Any,
) -> dict[tuple[int, int], bool]:
    """Read the official template's axis-frame state without normalizing it."""

    return {
        (_layer_index(layer), axis_code): bool(
            read_axis_line_show(
                op,
                graph.name,
                _layer_index(layer),
                axis_code,
            )
        )
        for layer in _layers(graph)
        for axis_code in _ORIGIN_FRAME_AXIS_NAMES
    }


def _apply_origin_product_frame(
    op: Any,
    graph: Any,
    profile_id: str,
    template_frame: dict[tuple[int, int], bool],
) -> dict[tuple[int, int], bool]:
    """Apply the boxed product default only to eligible Cartesian profiles."""

    expected = dict(template_frame)
    if profile_id not in _ORIGIN_FOUR_SIDED_FRAME_PROFILES:
        return expected
    layers = _layers(graph)
    if len(layers) != 1:
        raise RuntimeError("Origin boxed product frame requires exactly one native graph layer")
    for (layer_index, axis_code), visible in template_frame.items():
        if not visible:
            set_axis_line_show(op, graph.name, layer_index, axis_code, True)
        expected[(layer_index, axis_code)] = True
    layer = layers[0]
    # A boxed single-axis chart uses the top and right sides as clean frame
    # lines, not as additional semantic axes. Origin keeps tick and label
    # state per opposite axis, so clear those states explicitly after showing
    # the missing frame lines.
    layer.set_int("x2.ticks", 0)
    layer.set_int("y2.ticks", 0)
    layer.set_int("x.showLabels", layer.get_int("x.showLabels") & ~2)
    layer.set_int("y.showLabels", layer.get_int("y.showLabels") & ~2)
    layer.set_int("x2.showlabel", 0)
    layer.set_int("y2.showlabel", 0)
    for label_name in ("xt", "yr"):
        label = layer.label(label_name)
        if label is not None:
            label.set_int("show", 0)
    return expected


def _origin_product_tick_targets(graph: Any) -> tuple[tuple[Any, int], ...]:
    """Return public semantic tick targets without changing axis visibility."""

    layers = _layers(graph)
    targets = [(layer, axis_code) for layer in layers for axis_code in (0, 1)]
    if len(layers) > 1:
        targets.append((layers[-1], 3))
    return tuple(targets)


def _apply_origin_product_typography(op: Any, graph: Any) -> None:
    """Replace unrelated Origin template defaults with physical pt defaults."""

    for layer, axis_code in _origin_product_tick_targets(graph):
        set_axis_tick_font_size(
            op,
            str(graph.name),
            _layer_index(layer),
            axis_code,
            PRODUCT_TYPOGRAPHY.tick_font_size_pt,
        )
    for layer in _layers(graph):
        for name in ("xb", "yl", "yr"):
            label = layer.label(name)
            if label is not None:
                label.set_float("fsize", PRODUCT_TYPOGRAPHY.axis_title_font_size_pt)
        legend = layer.label("legend")
        if legend is not None:
            legend.set_float("fsize", PRODUCT_TYPOGRAPHY.legend_font_size_pt)
    title = _layers(graph)[0].label("_ENGINE_TITLE")
    if title is not None:
        title.set_float("fsize", PRODUCT_TYPOGRAPHY.title_font_size_pt)


def _verify_origin_product_typography(
    op: Any,
    graph: Any,
    actions: tuple[PlotEngineAction, ...],
) -> dict[str, float]:
    """Fresh-read the product defaults after applying explicit overrides."""

    tick_expected = {
        (_layer_index(layer), axis_code): PRODUCT_TYPOGRAPHY.tick_font_size_pt
        for layer, axis_code in _origin_product_tick_targets(graph)
    }
    label_expected: dict[tuple[int, str], float] = {}
    for layer in _layers(graph):
        for name in ("xb", "yl", "yr"):
            if layer.label(name) is not None:
                label_expected[(_layer_index(layer), name)] = (
                    PRODUCT_TYPOGRAPHY.axis_title_font_size_pt
                )
    title_expected = PRODUCT_TYPOGRAPHY.title_font_size_pt
    legend_expected = {
        _layer_index(layer): PRODUCT_TYPOGRAPHY.legend_font_size_pt
        for layer in _layers(graph)
        if layer.label("legend") is not None
    }
    for action in actions:
        if isinstance(action, SetTitle) and action.font_size_pt is not None:
            title_expected = action.font_size_pt
        elif isinstance(action, SetAxis):
            layer, axis_name = _axis_target(graph, action.target)
            if action.tick_font_size_pt is not None:
                tick_expected[(_layer_index(layer), _axis_native_code(action.target))] = (
                    action.tick_font_size_pt
                )
            if action.title_font_size_pt is not None:
                label_expected[(_layer_index(layer), _axis_label_name(graph, layer, axis_name))] = (
                    action.title_font_size_pt
                )
        elif isinstance(action, SetLegend) and action.font_size_pt is not None:
            legend_expected[_layer_index(_layers(graph)[0])] = action.font_size_pt

    snapshot: dict[str, float] = {}
    for (layer_index, axis_code), expected in tick_expected.items():
        observed = read_axis_tick_font_size(
            op,
            str(graph.name),
            layer_index,
            axis_code,
        )
        _require_number("product tick font", observed, expected, tolerance=0.01)
        snapshot[f"layer:{layer_index}.{_ORIGIN_FRAME_AXIS_NAMES[axis_code]}.tick_font_pt"] = (
            observed
        )
    for (layer_index, name), expected in label_expected.items():
        label = _layers(graph)[layer_index - 1].label(name)
        if label is None:
            raise RuntimeError(f"Origin product axis title disappeared after reopen: {name}")
        observed = float(label.get_float("fsize"))
        _require_number("product axis-title font", observed, expected, tolerance=0.01)
        snapshot[f"layer:{layer_index}.{name}.font_pt"] = observed
    title = _layers(graph)[0].label("_ENGINE_TITLE")
    if title is not None:
        observed = float(title.get_float("fsize"))
        _require_number("product title font", observed, title_expected, tolerance=0.01)
        snapshot["title.font_pt"] = observed
    for layer_index, expected in legend_expected.items():
        legend = _layers(graph)[layer_index - 1].label("legend")
        if legend is None:
            raise RuntimeError("Origin product legend disappeared after reopen")
        observed = float(legend.get_float("fsize"))
        _require_number("product legend font", observed, expected, tolerance=0.01)
        snapshot[f"layer:{layer_index}.legend.font_pt"] = observed
    return snapshot


def _verify_origin_product_opposite_axes(
    graph: Any,
    profile_id: str,
) -> dict[str, int | bool]:
    """Verify clean top/right frame sides for boxed single-axis charts."""

    if profile_id not in _ORIGIN_FOUR_SIDED_FRAME_PROFILES:
        return {}
    layers = _layers(graph)
    if len(layers) != 1:
        raise RuntimeError("Origin boxed product frame requires exactly one native graph layer")
    layer = layers[0]
    snapshot: dict[str, int | bool] = {}
    for side, axis_name, title_name in (("top", "x", "xt"), ("right", "y", "yr")):
        ticks = int(layer.get_int(f"{axis_name}2.ticks"))
        labels = bool(layer.get_int(f"{axis_name}.showLabels") & 2)
        direct_labels = bool(layer.get_int(f"{axis_name}2.showlabel"))
        title = layer.label(title_name)
        title_visible = False if title is None else bool(title.get_int("show"))
        if ticks != 0 or labels or direct_labels or title_visible:
            raise RuntimeError(
                "Origin boxed product frame opposite axis is not clean: "
                f"side={side}, ticks={ticks}, labels={int(labels)}, "
                f"direct_labels={int(direct_labels)}, title={int(title_visible)}"
            )
        snapshot[f"{side}.ticks"] = ticks
        snapshot[f"{side}.labels"] = labels
        snapshot[f"{side}.direct_labels"] = direct_labels
        snapshot[f"{side}.title"] = title_visible
    return snapshot


def _k01_physical_axis_expectation(layer: Any) -> dict[str, float | int]:
    """Resolve physical left/bottom anchors from the final native scales.

    Origin's default first-axis position follows the perpendicular scale's
    ``From`` endpoint.  Reversing that perpendicular scale moves the same
    semantic axis to the opposite physical side while ``showLabels`` and the
    title objects still report it as the first/left/bottom axis.  K01 promises
    Matplotlib-style physical left and bottom axes, so it must persist explicit
    data-coordinate anchors after every scale edit.
    """

    x_limits = tuple(float(value) for value in layer.axis("x").limits)
    y_limits = tuple(float(value) for value in layer.axis("y").limits)
    if len(x_limits) < 2 or len(y_limits) < 2:
        raise RuntimeError("Origin K01 axis limits are unavailable")
    x_reverse = int(bool(layer.get_int("x.reverse")))
    y_reverse = int(bool(layer.get_int("y.reverse")))
    return {
        "x_reverse": x_reverse,
        "y_reverse": y_reverse,
        "y_position": x_limits[1] if x_reverse else x_limits[0],
        "x_position": y_limits[1] if y_reverse else y_limits[0],
    }


def _apply_k01_physical_axis_sides(
    graph: Any,
    profile_id: str,
) -> dict[str, float | int] | None:
    """Keep K01 primary axes on the physical left and bottom after reversal."""

    if profile_id != "K01":
        return None
    layers = _layers(graph)
    if len(layers) != 1:
        raise RuntimeError("Origin K01 physical-axis contract requires one layer")
    layer = layers[0]
    expected = _k01_physical_axis_expectation(layer)
    layer.set_int("y.postype", 2)
    layer.set_float("y.position", float(expected["y_position"]))
    layer.set_int("x.postype", 2)
    layer.set_float("x.position", float(expected["x_position"]))
    return expected


def _verify_k01_physical_axis_sides(
    graph: Any,
    profile_id: str,
) -> dict[str, float | int]:
    """Fresh-read the native anchors that determine K01's visible axis sides."""

    if profile_id != "K01":
        return {}
    layers = _layers(graph)
    if len(layers) != 1:
        raise RuntimeError("Origin K01 physical-axis contract requires one layer")
    layer = layers[0]
    expected = _k01_physical_axis_expectation(layer)
    observed = {
        "x_reverse": int(bool(layer.get_int("x.reverse"))),
        "y_reverse": int(bool(layer.get_int("y.reverse"))),
        "x_postype": int(layer.get_int("x.postype")),
        "y_postype": int(layer.get_int("y.postype")),
        "x_position": float(layer.get_float("x.position")),
        "y_position": float(layer.get_float("y.position")),
    }
    if observed["x_postype"] != 2 or observed["y_postype"] != 2:
        raise RuntimeError(
            "Origin K01 primary axes are not anchored by data coordinate after reopen"
        )
    _require_number(
        "K01 physical bottom axis",
        float(observed["x_position"]),
        float(expected["x_position"]),
        tolerance=1e-9,
    )
    _require_number(
        "K01 physical left axis",
        float(observed["y_position"]),
        float(expected["y_position"]),
        tolerance=1e-9,
    )
    return observed


def _origin_frame_expectations(
    graph: Any,
    actions: tuple[PlotEngineAction, ...],
    product_frame: dict[tuple[int, int], bool],
) -> dict[tuple[int, int], bool]:
    expected = dict(product_frame)
    current_keys = {
        (_layer_index(layer), axis_code)
        for layer in _layers(graph)
        for axis_code in _ORIGIN_FRAME_AXIS_NAMES
    }
    if current_keys != set(expected):
        raise RuntimeError("Origin template frame layer structure changed after save")
    for action in actions:
        if not isinstance(action, SetAxis) or action.axis_line_visible is None:
            continue
        layer, _axis_name = _axis_target(graph, action.target)
        expected[(_layer_index(layer), _axis_native_code(action.target))] = action.axis_line_visible
    return expected


def _verify_origin_product_frame(
    op: Any,
    graph: Any,
    actions: tuple[PlotEngineAction, ...],
    product_frame: dict[tuple[int, int], bool],
) -> dict[str, bool]:
    """Verify the product default plus any explicit user overrides persisted."""

    snapshot: dict[str, bool] = {}
    for (layer_index, axis_code), expected in _origin_frame_expectations(
        graph, actions, product_frame
    ).items():
        observed = bool(read_axis_line_show(op, graph.name, layer_index, axis_code))
        side = _ORIGIN_FRAME_AXIS_NAMES[axis_code]
        if observed != expected:
            raise RuntimeError(
                "Origin product frame did not persist: "
                f"layer={layer_index}, side={side}, "
                f"expected={int(expected)}, observed={int(observed)}"
            )
        snapshot[f"layer:{layer_index}.{side}"] = observed
    return snapshot


def _with_bit(current: int, bit: int, visible: bool) -> int:
    return current | bit if visible else current & ~bit


_TICK_DIRECTION_BITS = {
    "in": (1, 4),
    "out": (2, 8),
    "inout": (3, 12),
}


def _updated_tick_bits(current: int, action: SetAxis) -> int:
    major = current & 3
    minor = current & 12
    direction = (
        None if action.tick_direction is None else _TICK_DIRECTION_BITS[action.tick_direction]
    )
    if action.major_ticks_visible is False:
        major = 0
    elif action.major_ticks_visible is True:
        major = direction[0] if direction is not None else (major or 2)
    elif direction is not None and major:
        major = direction[0]
    if action.minor_ticks_visible is False:
        minor = 0
    elif action.minor_ticks_visible is True:
        minor = direction[1] if direction is not None else (minor or 8)
    elif direction is not None and minor:
        minor = direction[1]
    return major | minor


def _fixed_axis_bounds_mode_is_valid(observed_mode: int) -> bool:
    """Return whether Origin reports a two-sided fixed/manual axis range."""

    return observed_mode in _FIXED_AXIS_NATIVE_RESCALE_MODES


def _apply_axis(op: Any, graph: Any, action: SetAxis) -> None:
    layer, axis_name = _axis_target(graph, action.target)
    visual_prefix = _axis_visual_prefix(axis_name, action.target)
    side_bit = _axis_side_bit(action.target)
    axis = layer.axis(axis_name)
    if action.scale in {"linear", "log10"}:
        axis.scale = action.scale
    if action.bounds_mode == "automatic":
        # Origin's skip string names the scales that remain fixed. This resets
        # only the requested axis and preserves bounds on sibling axes/layers.
        layer.set_int(f"{axis_name}.rescale", 3)
        layer.rescale("yzm" if axis_name == "x" else "xzm")
    elif action.minimum is not None and action.maximum is not None:
        layer.set_int(f"{axis_name}.rescale", 0)
        axis.set_limits(action.minimum, action.maximum)
    if action.reverse is not None:
        layer.set_int(f"{axis_name}.reverse", int(action.reverse))
    title_style_requested = any(
        value is not None
        for value in (
            action.title_font_family,
            action.title_font_size_pt,
            action.title_font_weight,
            action.title_italic,
            action.title_color,
        )
    )
    title = None
    if action.label is not None:
        title = _label(layer, _axis_label_name(graph, layer, axis_name), action.label)
        title.text = _replace_styled_text(title.text, action.label)
        title.set_int("show", 1)
    elif title_style_requested:
        title = layer.label(_axis_label_name(graph, layer, axis_name))
        if title is None:
            raise RuntimeError("Origin axis title object is unavailable for style editing")
    if title is not None:
        family = _font(op, action.title_font_family)
        if family is not None:
            title.set_int("font", family)
        title.set_float(
            "fsize",
            action.title_font_size_pt
            if action.title_font_size_pt is not None
            else PRODUCT_TYPOGRAPHY.axis_title_font_size_pt,
        )
        title.text = _styled_text(
            title.text,
            weight=action.title_font_weight,
            italic=action.title_italic,
        )
        if action.title_color is not None:
            title.set_int("color", _color(op, action.title_color))
    if action.major_tick_step is not None:
        layer.set_float(f"{axis_name}.inc", action.major_tick_step)
    if action.minor_tick_count is not None:
        layer.set_int(f"{axis_name}.minorTicks", action.minor_tick_count)
    if action.tick_format is not None:
        formats = {"auto": 0, "decimal": 1, "scientific": 2, "percent": 1, "date": 4, "time": 3}
        if action.tick_format in {"date", "time"}:
            layer.set_int(f"{visual_prefix}.label.type", formats[action.tick_format])
            layer.set_str(f"{visual_prefix}.label.suf", "")
        else:
            layer.set_int(f"{visual_prefix}.label.type", 0)
            layer.set_int(f"{visual_prefix}.label.numFormat", formats[action.tick_format])
            layer.set_str(
                f"{visual_prefix}.label.suf",
                "%" if action.tick_format == "percent" else "",
            )
    if action.tick_rotation_deg is not None:
        layer.set_float(f"{visual_prefix}.label.rotate", action.tick_rotation_deg)
    tick_font = _font(op, action.tick_font_family)
    if tick_font is not None:
        layer.set_int(f"{visual_prefix}.label.font", tick_font)
    if action.tick_font_size_pt is not None:
        set_axis_tick_font_size(
            op,
            str(graph.name),
            _layer_index(layer),
            _axis_native_code(action.target),
            action.tick_font_size_pt,
        )
    if action.tick_color is not None:
        layer.set_int(f"{visual_prefix}.label.color", _color(op, action.tick_color))
    if action.tick_labels_visible is not None:
        current = layer.get_int(f"{axis_name}.showLabels")
        layer.set_int(
            f"{axis_name}.showLabels",
            _with_bit(current, side_bit, action.tick_labels_visible),
        )
    if (
        action.major_ticks_visible is not None
        or action.minor_ticks_visible is not None
        or action.tick_direction is not None
    ):
        current = layer.get_int(f"{axis_name}.ticks")
        layer.set_int(f"{axis_name}.ticks", _updated_tick_bits(current, action))
    if action.axis_line_visible is not None:
        set_axis_line_show(
            op,
            graph.name,
            _layer_index(layer),
            _axis_native_code(action.target),
            action.axis_line_visible,
        )
    if action.axis_title_visible is not None:
        title = layer.label(_axis_label_name(graph, layer, axis_name))
        if title is None:
            if action.axis_title_visible:
                raise RuntimeError("Origin axis title object is unavailable")
        else:
            title.set_int("show", int(action.axis_title_visible))
    if action.axis_line_color is not None:
        layer.set_int(f"{visual_prefix}.color", _color(op, action.axis_line_color))
    if action.axis_line_width_pt is not None:
        layer.set_float(f"{visual_prefix}.thickness", action.axis_line_width_pt)
    if action.major_grid_visible is not None or action.minor_grid_visible is not None:
        current = layer.get_int(f"{axis_name}.grid.show")
        major = (
            bool(current & 1) if action.major_grid_visible is None else action.major_grid_visible
        )
        minor = (
            bool(current & 2) if action.minor_grid_visible is None else action.minor_grid_visible
        )
        layer.set_int(f"{axis_name}.grid.show", int(major) + 2 * int(minor))
    for prefix in ("major", "minor"):
        if action.grid_color is not None:
            layer.set_int(f"{axis_name}.grid.{prefix}Color", _color(op, action.grid_color))
        if action.grid_line_width_pt is not None:
            layer.set_float(f"{axis_name}.grid.{prefix}Width", action.grid_line_width_pt)
        if action.grid_line_style is not None:
            layer.set_int(f"{axis_name}.grid.{prefix}Type", _LINE_STYLE[action.grid_line_style])


def _series_style_member_indices(
    op: Any,
    graph: Any,
    layer: Any,
    plot_index: int,
    action: SetSeriesStyle,
    *,
    profile_id: str | None,
) -> tuple[int, ...]:
    """Map one public series to every native member that paints it."""

    count = _plot_count(op, graph, layer)
    if profile_id == "X09" and _target_key(action.target) == "primary":
        # FLOATCOL stores each boundary as a plot. Plot 1 is the invisible
        # start baseline; plots 2..N paint the visible adjacent intervals.
        if count < 2:
            raise RuntimeError("Origin X09 primary has no visible interval plot")
        return tuple(range(2, count + 1))
    return (plot_index,)


def _read_x09_primary_fill_colors(
    op: Any,
    graph: Any,
    layer: Any,
    plot_count: int,
) -> tuple[int, ...]:
    colors = read_x09_group_fill_colors(
        op,
        str(graph.name),
        _layer_index(layer),
    )
    if len(colors) != plot_count:
        raise RuntimeError("Origin X09 group count differs from its native plot count")
    return colors


def _apply_x09_primary_series(
    op: Any,
    graph: Any,
    layer: Any,
    action: SetSeriesStyle,
) -> None:
    """Apply one public X09 series edit through FLOATCOL's native group owner."""

    plot_count = _plot_count(op, graph, layer)
    if plot_count < 2:
        raise RuntimeError("Origin X09 primary has no visible interval plot")
    if action.visible is not None:
        for plot_index in range(2, plot_count + 1):
            _set_plot_property(
                op,
                graph,
                layer,
                plot_index,
                "show",
                int(action.visible),
            )

    leader_range = _checked_plot_range(op, graph, layer, 1)
    leader_ref = _bind_plot_range(op, leader_range)
    commands: list[str] = []
    if action.fill_color is not None:
        set_x09_group_fill_color(
            op,
            str(graph.name),
            _layer_index(layer),
            _color(op, action.fill_color),
        )
    if action.fill_stroke_color is not None:
        commands.append(f'set {leader_ref} -pbc color("{action.fill_stroke_color}")')
    if action.fill_stroke_width_pt is not None:
        commands.append(f"set {leader_ref} -pbw {action.fill_stroke_width_pt:.12g}")
    if action.fill_stroke_style is not None:
        commands.append(f"set {leader_ref} -pbs {_BORDER_STYLE[action.fill_stroke_style]}")
    if action.fill_opacity is not None:
        commands.append(f"set {leader_ref} -paap 1")
    _execute_plot_commands(op, commands, operation="X09 primary series style")
    if action.fill_opacity is not None:
        _set_plot_property(
            op,
            graph,
            layer,
            1,
            "transparency",
            (1 - action.fill_opacity) * 100,
        )


def _apply_k07_primary_series(
    op: Any,
    graph: Any,
    layer: Any,
    action: SetSeriesStyle,
) -> None:
    """Materialize K07's public center line on its native PID 201 plot."""

    plot_range = _checked_plot_range(op, graph, layer, 1)
    plot_ref = _bind_plot_range(op, plot_range)
    commands: list[str] = []
    if action.visible is not None:
        _set_plot_property(op, graph, layer, 1, "show", int(action.visible))
    line_requested = any(
        value is not None
        for value in (
            action.line_stroke_color,
            action.line_width_pt,
            action.line_style,
            action.line_opacity,
        )
    )
    if line_requested:
        connection = 0 if action.line_style == "none" else 1
        commands.extend((f"set {plot_ref} -l {connection}", f"set {plot_ref} -z 0"))
    if action.line_stroke_color is not None:
        commands.append(f'set {plot_ref} -cl color("{action.line_stroke_color}")')
    if action.line_width_pt is not None:
        commands.append(f"set {plot_ref} -wp {action.line_width_pt:.12g}")
    if action.line_style is not None:
        commands.append(f"set {plot_ref} -d {_K07_LINE_STYLE[action.line_style]}")
    _execute_plot_commands(op, commands, operation="K07 center line style")
    if action.line_opacity is not None:
        _set_plot_property(
            op,
            graph,
            layer,
            1,
            "transparency",
            (1 - action.line_opacity) * 100,
        )


def _apply_series(
    op: Any,
    graph: Any,
    action: SetSeriesStyle,
    *,
    profile_id: str | None = None,
) -> None:
    layer, plot_index = _layer_and_plot(graph, action.target)
    key = _target_key(action.target)
    if profile_id == "K14":
        _apply_k14_violin_series(op, graph, layer, plot_index, action)
        return
    if profile_id == "K07" and key == "primary":
        _apply_k07_primary_series(op, graph, layer, action)
        return
    if profile_id == "X09" and key == "primary":
        _apply_x09_primary_series(op, graph, layer, action)
        return
    # Origin's official templates commonly group multiple plots so the first
    # plot owns an incrementing style list.  A direct ``set plotN`` command can
    # then read back the requested value while the grouped renderer still
    # paints a different incremented value.  PlotAgent exposes every semantic
    # series as an independently editable object, so break only the targeted
    # layer's presentation group before applying a public series edit.  This
    # preserves the native plots and source bindings while making the visible
    # result agree with the per-series contract.
    plot_count = _plot_count(op, graph, layer)
    if plot_count > 1:
        _activate_layer(op, graph, layer)
        if not op.lt_exec("layer -gu;"):
            raise RuntimeError("Origin could not make series formatting independent")
    member_indices = _series_style_member_indices(
        op,
        graph,
        layer,
        plot_index,
        action,
        profile_id=profile_id,
    )
    visibility_indices = (
        member_indices
        if profile_id == "X09" and key == "primary"
        else (
            range(1, plot_count + 1)
            if key in {"primary", "left", "right", "bars", "cumulative", "matrix", "connector"}
            else (plot_index,)
        )
    )
    if action.visible is not None:
        for visibility_index in visibility_indices:
            _set_plot_property(
                op,
                graph,
                layer,
                visibility_index,
                "show",
                int(action.visible),
            )
    for member_index in member_indices:
        _apply_series_member(op, graph, layer, member_index, action)


def _k14_plot_indices(
    op: Any,
    graph: Any,
    layer: Any,
    plot_index: int,
    target: str,
) -> tuple[int, ...]:
    if _target_key(target) == "primary":
        return tuple(range(1, _plot_count(op, graph, layer) + 1))
    return (plot_index,)


def _updated_k14_style(
    op: Any,
    current: K14ViolinStyleState,
    action: SetSeriesStyle,
) -> K14ViolinStyleState:
    fill_color = (
        current.fill_color if action.fill_color is None else _color(op, action.fill_color)
    )
    fill_transparency = (
        current.fill_transparency
        if action.fill_opacity is None
        else (1 - action.fill_opacity) * 100
    )
    outline_color = current.outline_color
    outline_width = current.outline_width
    outline_style = current.outline_style
    # Matplotlib applies the public line family first and the fill-stroke
    # family second on a violin PolyCollection.  K14 exposes both historical
    # aliases for the same visible outline, so preserve that precedence.
    if action.line_stroke_color is not None:
        outline_color = _color(op, action.line_stroke_color)
    if action.line_width_pt is not None:
        outline_width = action.line_width_pt
    if action.line_style is not None:
        outline_style = _BORDER_STYLE[action.line_style]
    if action.fill_stroke_color is not None:
        outline_color = _color(op, action.fill_stroke_color)
    if action.fill_stroke_width_pt is not None:
        outline_width = action.fill_stroke_width_pt
    if action.fill_stroke_style is not None:
        outline_style = _BORDER_STYLE[action.fill_stroke_style]
    return K14ViolinStyleState(
        fill_color=fill_color,
        fill_transparency=fill_transparency,
        fill_only=1,
        follow_line_transparency=0,
        outline_color=outline_color,
        outline_width=outline_width,
        outline_style=outline_style,
    )


def _apply_k14_violin_series(
    op: Any,
    graph: Any,
    layer: Any,
    plot_index: int,
    action: SetSeriesStyle,
) -> None:
    """Edit the visible native K14 body instead of the inert Above branch."""

    indices = _k14_plot_indices(op, graph, layer, plot_index, action.target)
    for member_index in indices:
        if action.visible is not None:
            _set_plot_property(
                op,
                graph,
                layer,
                member_index,
                "show",
                int(action.visible),
            )
        current = read_k14_violin_style(
            op,
            str(graph.name),
            _layer_index(layer),
            member_index,
        )
        expected = _updated_k14_style(op, current, action)
        set_k14_violin_style(
            op,
            str(graph.name),
            _layer_index(layer),
            member_index,
            fill_color=expected.fill_color,
            fill_transparency=expected.fill_transparency,
            outline_color=expected.outline_color,
            outline_width=expected.outline_width,
            outline_style=expected.outline_style,
        )


def _apply_series_member(
    op: Any,
    graph: Any,
    layer: Any,
    plot_index: int,
    action: SetSeriesStyle,
) -> None:
    plot_range = _checked_plot_range(op, graph, layer, plot_index)
    plot_ref = _bind_plot_range(op, plot_range)
    line_symbol_color_cascade = (
        action.line_stroke_color is not None
        and int(_get_plot_option(op, plot_range, "-pt")) in _LINE_SYMBOL_PIDS
    )
    commands: list[str] = []
    if action.line_stroke_color is not None:
        commands.append(f'set {plot_ref} -cl color("{action.line_stroke_color}")')
    if action.line_width_pt is not None:
        commands.append(f"set {plot_ref} -wp {action.line_width_pt:.12g}")
    if action.line_style is not None:
        commands.append(f"set {plot_ref} -d {_LINE_STYLE[action.line_style]}")
    if action.marker_shape is not None:
        commands.append(f"set {plot_ref} -k {_MARKER[action.marker_shape]}")
    if action.marker_size_pt is not None:
        commands.append(f"set {plot_ref} -z {action.marker_size_pt:.12g}")
    if action.marker_interior is not None:
        commands.append(f"set {plot_ref} -kf {_INTERIOR[action.marker_interior]}")
    # ``marker_interior`` is the higher-level semantic and therefore owns the
    # visible fill.  Matplotlib already makes ``open`` transparent and
    # ``hollow`` white after applying any requested fill colour.  Origin 2024
    # persists both -kf and -csf, and a later black -csf can still paint a
    # nominally hollow marker solid.  Use the product's white graph background
    # as the stable Origin representation for both non-solid interiors.
    effective_marker_fill = (
        "#FFFFFF"
        if action.marker_interior in {"open", "hollow"}
        else (
            action.marker_fill_color
            if action.marker_fill_color is not None
            else action.line_stroke_color
            if line_symbol_color_cascade
            else None
        )
    )
    if effective_marker_fill is not None:
        commands.append(f'set {plot_ref} -csf color("{effective_marker_fill}")')
    effective_marker_stroke = (
        action.marker_stroke_color
        if action.marker_stroke_color is not None
        else action.line_stroke_color
        if line_symbol_color_cascade
        else None
    )
    if effective_marker_stroke is not None:
        commands.append(f'set {plot_ref} -cse color("{effective_marker_stroke}")')
    # Origin 2024 does not expose a stable native read/write contract for
    # marker edge width. Keep the official template default, including when a
    # legacy action still carries marker_stroke_width_pt.
    if action.fill_color is not None:
        commands.extend(
            (
                f'set {plot_ref} -pfb color("{action.fill_color}")',
                f'set {plot_ref} -cf color("{action.fill_color}")',
            )
        )
    if action.fill_stroke_color is not None:
        commands.append(f'set {plot_ref} -pbc color("{action.fill_stroke_color}")')
    if action.fill_stroke_width_pt is not None:
        commands.append(f"set {plot_ref} -pbw {action.fill_stroke_width_pt:.12g}")
    if action.fill_stroke_style is not None:
        commands.append(f"set {plot_ref} -pbs {_BORDER_STYLE[action.fill_stroke_style]}")
    if action.fill_opacity is not None:
        fill_only_option = (
            "-paap" if int(_get_plot_option(op, plot_range, "-pt")) in _BAR_COLUMN_PIDS else "-paaf"
        )
        commands.append(f"set {plot_ref} {fill_only_option} 1")
    _execute_plot_commands(op, commands, operation="series style")
    if action.line_opacity is not None:
        _set_plot_property(
            op,
            graph,
            layer,
            plot_index,
            "transparency",
            (1 - action.line_opacity) * 100,
        )
    if action.marker_opacity is not None:
        _set_plot_property(
            op,
            graph,
            layer,
            plot_index,
            "symbol.transparency",
            (1 - action.marker_opacity) * 100,
        )
    if action.fill_opacity is not None:
        _set_plot_property(
            op,
            graph,
            layer,
            plot_index,
            "transparency",
            (1 - action.fill_opacity) * 100,
        )


def _apply_legend(
    op: Any,
    graph: Any,
    action: SetLegend,
    *,
    profile_id: str,
) -> None:
    layer = _layers(graph)[0]
    legend = layer.label("legend")
    if action.visible and legend is None:
        layer.activate()
        if not layer.obj.LT_execute("legend"):
            raise RuntimeError("Origin could not create a native legend")
        legend = layer.label("legend")
    if legend is None:
        return
    if action.visible is not None:
        legend.set_int("show", int(action.visible))
    if action.columns is not None:
        if profile_id == "K09":
            entry_count = legend.text.count("\\l(")
            if action.columns == 1:
                command = "legend -av;"
            elif action.columns == entry_count:
                command = "legend -ah;"
            else:
                raise ValueError(
                    "Origin K09 indexed-subset legend currently supports either one "
                    f"column or one row of {entry_count} columns"
                )
            layer.activate()
            if not op.lt_exec(command):
                raise RuntimeError("Origin could not rearrange the K09 subset legend")
        else:
            legend.set_int("ncols", action.columns)
    if action.title is not None:
        lines = legend.text.splitlines()
        if lines and "\\l(" not in lines[0]:
            lines[0] = action.title
        else:
            lines.insert(0, action.title)
        legend.text = _replace_styled_text(legend.text, "\n".join(lines))
    font_index = _font(op, action.font_family)
    if font_index is not None:
        legend.set_int("font", font_index)
    legend.set_float(
        "fsize",
        action.font_size_pt
        if action.font_size_pt is not None
        else PRODUCT_TYPOGRAPHY.legend_font_size_pt,
    )
    if action.font_color is not None:
        legend.set_int("color", _color(op, action.font_color))
    if action.frame_visible is not None:
        legend.set_int("background", int(action.frame_visible))
    if action.frame_color is not None:
        legend.set_int("borderColor", _color(op, action.frame_color))
    if action.frame_width_pt is not None:
        legend.set_float("lineWidth", action.frame_width_pt)
    if action.anchor is not None:
        # Position after text/style edits because right/bottom placement needs
        # the final native legend bounding box.
        attach, left, top = _origin_legend_anchor(graph, layer, legend, action.anchor)
        legend.set_int("attach", attach)
        # Origin's own Python examples position legends through the integer
        # page-dot ``left``/``top`` properties.  ``x1``/``y1`` change meaning
        # when attachment changes and can read back unchanged while rendering
        # elsewhere after a project is reopened.
        legend.set_int("left", round(left))
        legend.set_int("top", round(top))
        if action.anchor == "none":
            legend.set_int("show", 0)


def _origin_layer_rect_printer_dots(
    graph: Any,
    layer: Any,
) -> tuple[float, float, float, float]:
    page_width, page_height = _graph_page_size(graph)
    resolution_x = float(graph.get_float("resx"))
    resolution_y = float(graph.get_float("resy"))
    left = float(layer.get_float("left"))
    top = float(layer.get_float("top"))
    width = float(layer.get_float("width"))
    height = float(layer.get_float("height"))
    unit = int(layer.get_int("unit"))
    if unit == 1:  # percent of graph page
        return (
            page_width * resolution_x * left / 100,
            page_height * resolution_y * top / 100,
            page_width * resolution_x * width / 100,
            page_height * resolution_y * height / 100,
        )
    if unit == 2:  # inches
        return (
            left * resolution_x,
            top * resolution_y,
            width * resolution_x,
            height * resolution_y,
        )
    if unit == 3:  # centimetres
        return (
            left / 2.54 * resolution_x,
            top / 2.54 * resolution_y,
            width / 2.54 * resolution_x,
            height / 2.54 * resolution_y,
        )
    if unit == 4:  # millimetres
        return (
            left / 25.4 * resolution_x,
            top / 25.4 * resolution_y,
            width / 25.4 * resolution_x,
            height / 25.4 * resolution_y,
        )
    if unit == 6:  # points
        return (
            left / 72 * resolution_x,
            top / 72 * resolution_y,
            width / 72 * resolution_x,
            height / 72 * resolution_y,
        )
    raise RuntimeError(f"Origin legend placement does not support layer unit {unit}")


def _origin_legend_anchor(
    graph: Any,
    layer: Any,
    legend: Any,
    anchor: str,
) -> tuple[int, float, float]:
    """Map public legend placement to Origin attachment and coordinates.

    Origin uses attachment 0 for coordinates relative to the layer frame and
    attachment 1 for page coordinates.  The public ``inside_*`` names are
    layer-relative by definition; page attachment makes an inside legend
    drift outside the plot whenever the graph page or layer is resized.
    """

    if anchor in {
        "inside",
        "inside_top_left",
        "inside_top_right",
        "inside_bottom_left",
        "inside_bottom_right",
    }:
        layer_left, layer_top, layer_width, layer_height = _origin_layer_rect_printer_dots(
            graph, layer
        )
        if layer_width <= 0 or layer_height <= 0:
            raise RuntimeError("Origin legend target layer has invalid dimensions")
        legend_width = float(legend.get_float("width"))
        legend_height = float(legend.get_float("height"))
        padding = 0.06
        left = layer_left + padding * layer_width
        right = max(left, layer_left + (1 - padding) * layer_width - legend_width)
        top = layer_top + padding * layer_height
        bottom = max(top, layer_top + (1 - padding) * layer_height - legend_height)
        return {
            "inside": (0, right, top),
            "inside_top_left": (0, left, top),
            "inside_top_right": (0, right, top),
            "inside_bottom_left": (0, left, bottom),
            "inside_bottom_right": (0, right, bottom),
        }[anchor]
    if anchor in {"right", "bottom"}:
        layer_left, layer_top, layer_width, layer_height = _origin_layer_rect_printer_dots(
            graph, layer
        )
        legend_width = float(legend.get_float("width"))
        legend_height = float(legend.get_float("height"))
        if anchor == "right":
            return (
                0,
                layer_left + 1.03 * layer_width,
                layer_top + max(0.0, (layer_height - legend_height) / 2),
            )
        return (
            0,
            layer_left + max(0.0, (layer_width - legend_width) / 2),
            layer_top + 1.03 * layer_height,
        )
    return 0, 0.0, 0.0


def _origin_colormap_flip(
    profile_id: str | None,
    palette: str | None,
    reverse: bool,
) -> int:
    """Map the public low-to-high direction to Origin's native palette order.

    K22 is independently verified against its visible regular-grid contour.
    Origin 2024 stores the sequential palette direction used by that plot in
    the opposite order from Matplotlib's public palette names.  Keep this
    adjudication profile-scoped instead of assuming every color-plot family
    shares the same native convention.
    """

    if profile_id == "K22" or palette == "blue_white_red":
        return int(not reverse)
    return int(reverse)


def _apply_colormap(
    op: Any,
    graph: Any,
    action: SetColorMap,
    *,
    profile_id: str | None = None,
) -> None:
    layer, _plot_index = _layer_and_plot(graph, action.target)
    _activate_layer(op, graph, layer)
    commands: list[str] = []
    if action.palette is not None:
        commands.extend(
            (
                f'layer.cmap.palette$="{_PALETTE[action.palette]}.pal"',
                "layer.cmap.linkpal=1",
                "layer.cmap.stretchpal=1",
            )
        )
    if action.reverse is not None:
        commands.append(
            f"layer.cmap.flippal={_origin_colormap_flip(profile_id, action.palette, action.reverse)}"
        )
    if action.minimum is not None and action.maximum is not None:
        commands.extend(
            (
                f"layer.cmap.zMin={action.minimum:.17g}",
                f"layer.cmap.zMax={action.maximum:.17g}",
            )
        )
    level_count = action.levels
    if level_count is None and action.mode is not None:
        level_count = 8 if action.mode == "discrete" else 256
    if level_count is not None:
        commands.extend(
            (
                f"layer.cmap.numColors={level_count}",
                f"layer.cmap.numMajorLevels={level_count}",
                "layer.cmap.numMinorLevels=0",
            )
        )
    if action.missing_color is not None:
        commands.append(f"layer.cmap.colorMiss={_color(op, action.missing_color)}")
    commands.append("layer.cmap.SetLevels(1)")
    if action.midpoint is not None:
        assert action.minimum is not None and action.maximum is not None
        values = _centered_levels(
            action.minimum,
            action.midpoint,
            action.maximum,
            level_count or 256,
        )
        commands.extend(
            f"layer.cmap.z{index}={value:.17g}" for index, value in enumerate(values, start=1)
        )
    commands.append("layer.cmap.updateScale()")
    if not op.lt_exec("; ".join(commands) + ";"):
        raise RuntimeError("Origin could not update the T1 colormap")
    spectrum = _color_scale_for_action(op, layer, action)
    if spectrum is not None:
        if action.colorbar_visible is not None:
            spectrum.set_int("show", int(action.colorbar_visible))
        if action.colorbar_title is not None:
            set_color_scale_title(
                op,
                graph.name,
                _layer_index(layer),
                action.colorbar_title,
            )
        if action.colorbar_anchor is not None:
            set_color_scale_anchor(
                op,
                graph.name,
                _layer_index(layer),
                action.colorbar_anchor,
            )
        if action.colorbar_tick_format is not None:
            set_color_scale_tick_format(
                op,
                graph.name,
                _layer_index(layer),
                action.colorbar_tick_format,
            )


def _color_scale_for_action(op: Any, layer: Any, action: SetColorMap) -> Any | None:
    """Resolve or create the native color scale required by a public edit.

    Origin templates such as heat maps normally contain ``SPECTRUM1`` while
    the official K04 bubble template does not.  ``colorbar_visible=True`` is a
    creation request in both public backends, so silently ignoring it when the
    object is absent would make the same action backend-dependent.  Styling an
    absent and non-requested scale is rejected explicitly instead of being a
    false successful edit.
    """

    spectrum = layer.label("SPECTRUM1")
    if spectrum is None and action.colorbar_visible is True:
        layer.activate()
        native = layer.obj.GraphObjects.Add(13)
        if native is None or not native.IsValid():
            raise RuntimeError("Origin could not create the requested native color scale")
        spectrum = op.Label(native, layer.obj)
        spectrum.name = "SPECTRUM1"
    style_requested = any(
        value is not None
        for value in (
            action.colorbar_title,
            action.colorbar_anchor,
            action.colorbar_tick_format,
        )
    )
    if spectrum is None and style_requested and action.colorbar_visible is not False:
        raise RuntimeError(
            "Origin cannot style a color scale that is absent; set colorbar_visible=true"
        )
    return spectrum


def _centered_levels(
    minimum: float, midpoint: float, maximum: float, level_count: int
) -> tuple[float, ...]:
    """Return strict levels with the requested midpoint at the palette center."""

    count = max(3, level_count)
    lower_count = count // 2
    upper_count = count - lower_count - 1
    lower = tuple(
        minimum + (midpoint - minimum) * index / lower_count for index in range(lower_count)
    )
    upper = tuple(
        midpoint + (maximum - midpoint) * index / upper_count for index in range(1, upper_count + 1)
    )
    return (*lower, midpoint, *upper)


def _apply_error(
    op: Any,
    graph: Any,
    action: SetErrorStyle,
    *,
    profile_id: str | None = None,
) -> None:
    layer, plot_indices = _error_plots(op, graph, action.target)
    k07_native_band = profile_id == "K07" and _target_key(action.target) == "primary"
    for plot_index in plot_indices:
        plot_range = _checked_plot_range(op, graph, layer, plot_index)
        plot_ref = _bind_plot_range(op, plot_range)
        commands: list[str] = []
        if action.bar_color is not None:
            commands.append(f'set {plot_ref} -c color("{action.bar_color}")')
        if action.bar_width_pt is not None:
            commands.append(f"set {plot_ref} -erw {action.bar_width_pt:.12g}")
        if action.cap_size_pt is not None:
            commands.append(f"set {plot_ref} -erwc {action.cap_size_pt:.12g}")
        if action.band_fill_color is not None:
            commands.append(f'set {plot_ref} -pfb color("{action.band_fill_color}")')
        if action.band_fill_opacity is not None and not k07_native_band:
            commands.append(f"set {plot_ref} -paaf 1")
        if action.band_stroke_color is not None:
            option = "-c" if k07_native_band else "-pbc"
            commands.append(f'set {plot_ref} {option} color("{action.band_stroke_color}")')
        if action.band_stroke_width_pt is not None:
            option = "-wp" if k07_native_band else "-pbw"
            commands.append(f"set {plot_ref} {option} {action.band_stroke_width_pt:.12g}")
        _execute_plot_commands(op, commands, operation="error style")
        if action.bar_opacity is not None:
            _set_plot_property(
                op,
                graph,
                layer,
                plot_index,
                "transparency",
                (1 - action.bar_opacity) * 100,
            )
        if action.band_fill_opacity is not None and not k07_native_band:
            _set_plot_property(
                op,
                graph,
                layer,
                plot_index,
                "transparency",
                (1 - action.band_fill_opacity) * 100,
            )
    if k07_native_band and action.band_fill_opacity is not None:
        set_k07_error_band_fill_transparency(
            op,
            str(graph.name),
            _layer_index(layer),
            fill_transparency=(1 - action.band_fill_opacity) * 100,
        )


def _apply_data_labels(op: Any, graph: Any, action: SetDataLabels) -> None:
    layer, plot_index = _layer_and_plot(graph, action.target)
    plot_range = _checked_plot_range(op, graph, layer, plot_index)
    plot_ref = _bind_plot_range(op, plot_range)
    commands: list[str] = []
    if action.visible is not None:
        commands.append(f"set {plot_ref} -q {int(action.visible)}")
    if action.value_format is not None or action.prefix is not None or action.suffix is not None:
        format_code = {"auto": "*", "decimal": "*3", "scientific": "E3", "percent": "*3"}[
            action.value_format or "auto"
        ]
        suffix = f"{action.suffix or ''}{'%' if action.value_format == 'percent' else ''}"
        display = f"{action.prefix or ''}$(Y,{format_code}){suffix}"
        commands.extend((f"set {plot_ref} -qm 5", f'set {plot_ref} -j -qms "{display}"'))
    if action.position is not None:
        commands.append(f"set {plot_ref} -qp {_LABEL_POSITION[action.position]}")
    if action.rotation_deg is not None:
        commands.append(f"set {plot_ref} -qr {action.rotation_deg:.12g}")
    font_index = _font(op, action.font_family)
    if font_index is not None:
        commands.append(f"set {plot_ref} -qf {font_index}")
    if action.font_size_pt is not None:
        commands.append(f"set {plot_ref} -qs {action.font_size_pt:.12g}")
    if action.font_weight is not None:
        commands.append(f"set {plot_ref} -qb {_FONT_WEIGHT[action.font_weight]}")
    if action.font_color is not None:
        commands.append(f'set {plot_ref} -qc color("{action.font_color}")')
    _execute_plot_commands(op, commands, operation="data labels")


def _apply_annotation(op: Any, graph: Any, action: AddAnnotation) -> None:
    layer = _layers(graph)[0]
    name = action.annotation_id.replace(":", "_").replace(".", "_")
    label = _label(layer, name, action.text)
    label.text = _replace_styled_text(label.text, action.text)
    label.set_int("show", 1)
    label.set_int("attach", 2 if action.coordinate_system == "data" else 0)
    if action.rotation_deg is not None:
        label.set_float("rotate", action.rotation_deg)
    _style_label(op, label, action)
    # Origin stores text-object x/y at the bounding-box center.  Font and rich
    # text edits resize that box while preserving its edge, so position must
    # be assigned after styling to keep the requested data coordinate.
    label.set_float("x", action.x)
    label.set_float("y", action.y)


def _reference_line_slots(
    graph: Any,
    actions: tuple[AddReferenceLine, ...],
) -> tuple[tuple[AddReferenceLine, Any, Literal["x", "y"], int], ...]:
    """Assign stable one-based native indices within each layer/axis collection."""

    counts: dict[tuple[int, str], int] = {}
    slots: list[tuple[AddReferenceLine, Any, Literal["x", "y"], int]] = []
    for action in actions:
        layer, axis_name = _axis_target(graph, action.target)
        key = (_layer_index(layer), axis_name)
        index = counts.get(key, 0) + 1
        counts[key] = index
        slots.append((action, layer, axis_name, index))
    return tuple(slots)


def _apply_reference_lines(
    op: Any,
    graph: Any,
    actions: tuple[AddReferenceLine, ...],
    *,
    touched_actions: tuple[AddReferenceLine, ...] | None = None,
) -> None:
    """Rebuild touched native axis-reference-line collections exactly.

    Origin's ``addline`` X-Function creates a graphical Straight Line whose
    saved position is quantized through page pixels.  The documented
    ``layer.axis.refline#`` object instead persists ``VALUE`` as an axis value.
    Rebuilding every axis touched by the journal also removes stale native
    lines when an addressable reference-line ID changes axis.
    """

    slots = _reference_line_slots(graph, actions)
    touched = _reference_line_slots(graph, touched_actions or actions)
    groups: dict[tuple[int, str], tuple[Any, Literal["x", "y"]]] = {
        (_layer_index(layer), axis_name): (layer, axis_name)
        for _action, layer, axis_name, _index in touched
    }
    group_counts: dict[tuple[int, str], int] = {}
    for _action, layer, axis_name, index in slots:
        group_counts[(_layer_index(layer), axis_name)] = index

    for key, (layer, axis_name) in groups.items():
        layer.activate()
        layer.set_int(f"{axis_name}.reflines.count", group_counts.get(key, 0))
        if group_counts.get(key, 0):
            layer.set_int(f"{axis_name}.reflines.lineshow", 1)

    for action, layer, axis_name, index in slots:
        layer.activate()
        prefix = f"{axis_name}.refline{index}"
        layer.set_float(f"{prefix}.value", action.value)
        layer.set_int(f"{prefix}.lineshow", 1)
        layer.set_int(f"{prefix}.lineauto", 0)
        layer.set_int(f"{prefix}.linecolor", _color(op, action.line_color or "#667085"))
        layer.set_int(
            f"{prefix}.linestyle",
            _REFERENCE_LINE_STYLE[action.line_style or "dash"],
        )
        layer.set_float(f"{prefix}.linethickness", action.line_width_pt or 1.0)
        layer.set_int(f"{prefix}.labelshow", int(bool(action.label)))
        layer.set_str(f"{prefix}.labeltext", action.label or "")


def _apply_reference_line(op: Any, graph: Any, action: AddReferenceLine) -> None:
    """Compatibility wrapper for direct adapter tests and internal callers."""

    _apply_reference_lines(op, graph, (action,))


def _callout_object_names(callout_id: str) -> tuple[str, str]:
    """Return short stable names accepted by Origin's graph-object collection."""

    digest = blake2s(callout_id.encode("utf-8"), digest_size=8).hexdigest()
    return f"pac_{digest}_a", f"pac_{digest}_t"


def _axis_fraction_value(layer: Any, axis_name: Literal["x", "y"], fraction: float) -> float:
    """Translate an axes fraction to the layer's native scale coordinate."""

    axis = layer.axis(axis_name)
    start, end, *_ = (float(value) for value in axis.limits)
    if not all(isfinite(value) for value in (start, end, fraction)):
        raise RuntimeError("Origin callout axis geometry is not finite")
    scale = axis.scale
    if scale in {"linear", 1}:
        return start + fraction * (end - start)
    if scale in {"log10", 2}:
        if start <= 0 or end <= 0:
            raise RuntimeError("Origin callout cannot interpolate a non-positive log axis")
        return 10 ** (log10(start) + fraction * (log10(end) - log10(start)))
    raise ValueError(f"Origin callouts do not support axis scale {scale!r}")


def _callout_geometry(
    graph: Any,
    action: AddCallout,
    reference: AddReferenceLine,
) -> tuple[Any, tuple[float, float, float, float]]:
    """Resolve backend-neutral fractions to one native scale-space arrow."""

    layer, reference_axis = _axis_target(graph, reference.target)
    text_x = _axis_fraction_value(layer, "x", action.text_x_fraction)
    text_y = _axis_fraction_value(layer, "y", action.text_y_fraction)
    if reference_axis == "x":
        anchor_x = reference.value
        anchor_y = _axis_fraction_value(layer, "y", action.anchor_fraction)
    else:
        anchor_x = _axis_fraction_value(layer, "x", action.anchor_fraction)
        anchor_y = reference.value
    return layer, (text_x, text_y, anchor_x, anchor_y)


def _apply_callouts(
    op: Any,
    graph: Any,
    actions: tuple[AddCallout, ...],
    *,
    reference_lines: tuple[AddReferenceLine, ...],
    touched_actions: tuple[AddCallout, ...] | None = None,
) -> None:
    """Create native arrows bound to effective axis-reference-line objects."""

    references = {action.reference_line_id: action for action in reference_lines}
    for action in touched_actions or actions:
        arrow_name, text_name = _callout_object_names(action.callout_id)
        for layer in _layers(graph):
            remove_graph_object(
                op,
                graph.name,
                _layer_index(layer),
                arrow_name,
            )
            remove_graph_object(
                op,
                graph.name,
                _layer_index(layer),
                text_name,
            )

    for action in actions:
        reference = references.get(action.target)
        if reference is None:
            raise ValueError(
                f"Origin callout target is not an effective reference line: {action.target}"
            )
        layer, (text_x, text_y, anchor_x, anchor_y) = _callout_geometry(
            graph,
            action,
            reference,
        )
        arrow_name, text_name = _callout_object_names(action.callout_id)
        set_scale_arrow(
            op,
            graph.name,
            _layer_index(layer),
            arrow_name,
            x0=text_x,
            y0=text_y,
            x1=anchor_x,
            y1=anchor_y,
        )
        arrow = layer.label(arrow_name)
        if arrow is None:
            raise RuntimeError("Origin did not expose the native callout arrow")
        arrow.set_int("show", 1)
        arrow.set_int("attach", 2)
        arrow.set_int("color", _color(op, action.arrow_color or "#101828"))
        arrow.set_float("lineWidth", action.arrow_width_pt or 1.0)
        arrow.set_int("arrowBeginShape", 0)
        arrow.set_int("arrowEndShape", 2 if action.arrow_head == "open" else 1)
        arrow.set_float("arrowEndWidth", 8.0)
        arrow.set_float("arrowEndLength", 8.0)
        set_scale_arrow_head(
            op,
            graph.name,
            _layer_index(layer),
            arrow_name,
            2 if action.arrow_head == "open" else 1,
        )

        label = _label(layer, text_name, action.text)
        label.text = _styled_text(
            action.text,
            weight=action.font_weight,
            italic=action.italic,
        )
        label.set_int("show", 1)
        label.set_int("attach", 2)
        font_index = _font(op, action.font_family)
        if font_index is not None:
            label.set_int("font", font_index)
        label.set_float(
            "fsize",
            action.font_size_pt or PRODUCT_TYPOGRAPHY.tick_font_size_pt,
        )
        label.set_int(
            "color",
            _color(op, action.text_color or action.arrow_color or "#101828"),
        )
        # Text object coordinates describe its center.  Assign them after
        # font/rich-text edits so a resize cannot move the requested anchor.
        label.set_float("x", text_x)
        label.set_float("y", text_y)


def _require_number(
    name: str, observed: float, expected: float, *, tolerance: float = 1e-7
) -> None:
    if not isclose(observed, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise RuntimeError(
            f"Origin T1 fresh readback mismatch for {name}: expected {expected}, "
            f"observed {observed}"
        )


def _require_equal(name: str, observed: object, expected: object) -> None:
    if observed != expected:
        raise RuntimeError(
            f"Origin T1 fresh readback mismatch for {name}: expected {expected!r}, "
            f"observed {observed!r}"
        )


def _axis_label_name(graph: Any, layer: Any, axis_name: str) -> str:
    if axis_name == "x":
        return "xb"
    return "yr" if _layer_index(layer) == len(_layers(graph)) and len(_layers(graph)) > 1 else "yl"


def _verify_label_style(
    op: Any,
    label: Any,
    action: SetTitle | SetLegend | AddAnnotation,
) -> dict[str, object]:
    plain_text, bold, italic = _text_style(label.text)
    observed: dict[str, object] = {"text": plain_text, "show": label.get_int("show")}
    expected_font = _font(op, getattr(action, "font_family", None))
    if expected_font is not None:
        value = label.get_int("font")
        _require_equal("font", value, expected_font)
        observed["font"] = value
    size = getattr(action, "font_size_pt", None)
    if size is not None:
        value = label.get_float("fsize")
        _require_number("font size", value, size)
        observed["font_size_pt"] = value
    weight = getattr(action, "font_weight", None)
    if weight is not None:
        _require_equal("font weight", bold, weight == "bold")
        observed["bold"] = bold
    requested_italic = getattr(action, "italic", None)
    if requested_italic is not None:
        _require_equal("italic", italic, requested_italic)
        observed["italic"] = italic
    color = getattr(action, "color", None)
    if color is not None:
        value = label.get_int("color")
        _require_equal("font color", value, _color(op, color))
        observed["color"] = value
    return observed


def _series_numeric_tolerance(name: str) -> float:
    # Origin 2024 stores plot and border widths at 0.1 pt resolution.  The
    # setter accepts finer decimals, but a saved-and-reopened project reports
    # the nearest tenth (for example 2.25 -> 2.3).  Treat half a storage step
    # as the native representational tolerance; other numeric properties stay
    # exact at the public contract's precision.
    return 0.051 if name in {"line_width", "fill_stroke_width"} else 1e-7


def _legend_column_count(stored: int) -> int:
    # Origin normalizes an explicit single-column legend to ncols=0, its
    # native "automatic vertical layout" sentinel.  The renderer-neutral
    # contract expresses that same visible state as one column.
    return 1 if stored == 0 else stored


def _k09_legend_column_count(text: str) -> int:
    """Read the visible K09 legend layout from its native text rows.

    Origin's ``legend -ah`` persists a horizontal indexed-subset legend as
    one text row while normalizing ``legend.ncols`` to 0. The row's native
    ``\\l(1,mN,2)`` samples are the authoritative visible column count.
    """

    rows = text.splitlines() or [text]
    counts = tuple(len(tuple(_K09_LEGEND_SAMPLE.finditer(row))) for row in rows)
    if not counts or max(counts) < 1:
        raise RuntimeError("Origin K09 legend contains no native subset samples")
    return max(counts)


def _verify_x09_primary_series(
    op: Any,
    graph: Any,
    layer: Any,
    action: SetSeriesStyle,
) -> dict[str, object]:
    plot_count = _plot_count(op, graph, layer)
    if plot_count < 2:
        raise RuntimeError("Origin X09 primary has no visible interval plot")
    observed: dict[str, object] = {
        "native_group_leader": 1,
        "visible_interval_plots": list(range(2, plot_count + 1)),
    }
    if action.visible is not None:
        visibility = tuple(
            int(_get_plot_property(op, graph, layer, index, "show"))
            for index in range(2, plot_count + 1)
        )
        if any(value != int(action.visible) for value in visibility):
            raise RuntimeError("Origin X09 primary visibility did not survive fresh reopen")
        observed["visible"] = visibility
    if action.fill_color is not None:
        colors = _read_x09_primary_fill_colors(
            op,
            graph,
            layer,
            plot_count,
        )
        expected = _color(op, action.fill_color)
        if any(value != expected for value in colors):
            raise RuntimeError("Origin X09 interval fill colors differ after fresh reopen")
        observed["fill_colors"] = list(colors)

    group_action = action.model_copy(update={"visible": None, "fill_color": None})
    group_properties = _verify_series_member(op, graph, layer, 1, group_action)
    if group_properties:
        observed["group_properties"] = group_properties
    return observed


def _verify_k07_primary_series(
    op: Any,
    graph: Any,
    layer: Any,
    action: SetSeriesStyle,
) -> dict[str, object]:
    plot_range = _checked_plot_range(op, graph, layer, 1)
    observed: dict[str, object] = {"native_center_plot": 1}
    if action.visible is not None:
        show = int(_get_plot_property(op, graph, layer, 1, "show"))
        _require_equal("K07 center visibility", show, int(action.visible))
        observed["visible"] = show
    line_requested = any(
        value is not None
        for value in (
            action.line_stroke_color,
            action.line_width_pt,
            action.line_style,
            action.line_opacity,
        )
    )
    if line_requested:
        connection = int(_get_plot_option(op, plot_range, "-l"))
        expected_connection = 0 if action.line_style == "none" else 1
        _require_equal("K07 center line connection", connection, expected_connection)
        marker_size = float(_get_plot_option(op, plot_range, "-z"))
        _require_number("K07 hidden center marker", marker_size, 0.0)
        observed.update({"line_connection": connection, "marker_size": marker_size})
    if action.line_stroke_color is not None:
        color = int(_get_plot_option(op, plot_range, "-cl"))
        _require_equal("K07 center line color", color, _color(op, action.line_stroke_color))
        observed["line_color"] = color
    if action.line_width_pt is not None:
        width = float(_get_plot_option(op, plot_range, "-wp"))
        _require_number("K07 center line width", width, action.line_width_pt, tolerance=0.051)
        observed["line_width"] = width
    if action.line_style is not None:
        style = int(_get_plot_option(op, plot_range, "-d"))
        _require_equal("K07 center line style", style, _K07_LINE_STYLE[action.line_style])
        observed["line_style"] = style
    if action.line_opacity is not None:
        opacity = 1 - _get_plot_property(op, graph, layer, 1, "transparency") / 100
        _require_number("K07 center line opacity", opacity, action.line_opacity)
        observed["line_opacity"] = opacity
    return observed


def _verify_series(
    op: Any,
    graph: Any,
    action: SetSeriesStyle,
    *,
    profile_id: str | None = None,
) -> dict[str, object]:
    layer, plot_index = _layer_and_plot(graph, action.target)
    if profile_id == "K14":
        return _verify_k14_violin_series(op, graph, layer, plot_index, action)
    if profile_id == "K07" and _target_key(action.target) == "primary":
        return _verify_k07_primary_series(op, graph, layer, action)
    if profile_id == "X09" and _target_key(action.target) == "primary":
        return _verify_x09_primary_series(op, graph, layer, action)
    member_indices = _series_style_member_indices(
        op,
        graph,
        layer,
        plot_index,
        action,
        profile_id=profile_id,
    )
    observed_visibility: tuple[int, ...] | None = None
    if action.visible is not None:
        key = _target_key(action.target)
        visibility_indices = (
            member_indices
            if profile_id == "X09" and key == "primary"
            else (
                range(1, _plot_count(op, graph, layer) + 1)
                if key
                in {
                    "primary",
                    "left",
                    "right",
                    "bars",
                    "cumulative",
                    "matrix",
                    "connector",
                }
                else (plot_index,)
            )
        )
        observed_visibility = tuple(
            int(_get_plot_property(op, graph, layer, index, "show")) for index in visibility_indices
        )
        expected_visibility = int(action.visible)
        if any(value != expected_visibility for value in observed_visibility):
            raise RuntimeError("Origin series visibility did not survive T1 fresh reopen")

    members = tuple(
        _verify_series_member(op, graph, layer, member_index, action)
        for member_index in member_indices
    )
    if len(members) == 1:
        observed = dict(members[0])
        if observed_visibility is not None:
            observed["visible"] = observed_visibility
        return observed
    result: dict[str, object] = {
        "native_plot_indices": list(member_indices),
        "members": list(members),
    }
    if observed_visibility is not None:
        result["visible"] = observed_visibility
    return result


def _k14_state_snapshot(state: K14ViolinStyleState) -> dict[str, int | float]:
    return {
        "fill_color": state.fill_color,
        "fill_transparency": state.fill_transparency,
        "fill_only": state.fill_only,
        "follow_line_transparency": state.follow_line_transparency,
        "outline_color": state.outline_color,
        "outline_width": state.outline_width,
        "outline_style": state.outline_style,
    }


def _require_k14_style(
    observed: K14ViolinStyleState,
    expected: K14ViolinStyleState,
    *,
    prefix: str,
) -> None:
    for name in (
        "fill_color",
        "fill_only",
        "follow_line_transparency",
        "outline_color",
        "outline_style",
    ):
        _require_equal(
            f"{prefix} {name}",
            getattr(observed, name),
            getattr(expected, name),
        )
    if abs(observed.fill_transparency - expected.fill_transparency) > 1.01:
        raise RuntimeError(
            f"Origin T1 fresh readback mismatch for {prefix} fill transparency: "
            f"expected {expected.fill_transparency}, observed {observed.fill_transparency}"
        )
    _require_number(
        f"{prefix} outline width",
        observed.outline_width,
        expected.outline_width,
        tolerance=0.051,
    )


def _verify_k14_violin_series(
    op: Any,
    graph: Any,
    layer: Any,
    plot_index: int,
    action: SetSeriesStyle,
) -> dict[str, object]:
    members: list[dict[str, int | float]] = []
    for member_index in _k14_plot_indices(
        op,
        graph,
        layer,
        plot_index,
        action.target,
    ):
        observed = read_k14_violin_style(
            op,
            str(graph.name),
            _layer_index(layer),
            member_index,
        )
        if action.fill_color is not None:
            _require_equal(
                "K14 visible fill color",
                observed.fill_color,
                _color(op, action.fill_color),
            )
        if action.fill_opacity is not None:
            expected_transparency = (1 - action.fill_opacity) * 100
            if abs(observed.fill_transparency - expected_transparency) > 1.01:
                raise RuntimeError(
                    "Origin T1 fresh readback mismatch for K14 visible fill opacity: "
                    f"expected transparency {expected_transparency}, "
                    f"observed {observed.fill_transparency}"
                )
        requested_outline_color = action.fill_stroke_color or action.line_stroke_color
        requested_outline_width = (
            action.fill_stroke_width_pt
            if action.fill_stroke_width_pt is not None
            else action.line_width_pt
        )
        requested_outline_style = action.fill_stroke_style or action.line_style
        if requested_outline_color is not None:
            _require_equal(
                "K14 visible outline color",
                observed.outline_color,
                _color(op, requested_outline_color),
            )
        if requested_outline_width is not None:
            _require_number(
                "K14 visible outline width",
                observed.outline_width,
                requested_outline_width,
                tolerance=0.051,
            )
        if requested_outline_style is not None:
            _require_equal(
                "K14 visible outline style",
                observed.outline_style,
                _BORDER_STYLE[requested_outline_style],
            )
        _require_equal("K14 fill-only transparency", observed.fill_only, 1)
        _require_equal("K14 line-transparency independence", observed.follow_line_transparency, 0)
        member = _k14_state_snapshot(observed)
        if action.visible is not None:
            visible = int(_get_plot_property(op, graph, layer, member_index, "show"))
            _require_equal("K14 series visibility", visible, int(action.visible))
            member["visible"] = visible
        members.append(member)
    return {
        "native_plot_indices": list(
            _k14_plot_indices(op, graph, layer, plot_index, action.target)
        ),
        "members": members,
    }


def _verify_k14_product_style(
    op: Any,
    graph: Any,
    actions: tuple[PlotEngineAction, ...],
    defaults: tuple[K14ViolinStyleState, ...],
) -> dict[str, object]:
    """Verify final K14 visible styles, including defaults and user edits."""

    layer = _layers(graph)[0]
    expected = list(defaults)
    for action in actions:
        if not isinstance(action, SetSeriesStyle):
            continue
        _, plot_index = _layer_and_plot(graph, action.target)
        for member_index in _k14_plot_indices(
            op,
            graph,
            layer,
            plot_index,
            action.target,
        ):
            expected[member_index - 1] = _updated_k14_style(
                op,
                expected[member_index - 1],
                action,
            )
    observed_rows: list[dict[str, int | float]] = []
    for plot_index, expected_state in enumerate(expected, start=1):
        observed = read_k14_violin_style(
            op,
            str(graph.name),
            _layer_index(layer),
            plot_index,
        )
        _require_k14_style(
            observed,
            expected_state,
            prefix=f"K14 group {plot_index}",
        )
        observed_rows.append(_k14_state_snapshot(observed))
    if not any(isinstance(action, SetLegend) for action in actions):
        legend = layer.label("legend")
        if legend is not None:
            _require_equal(
                "K14 product legend visibility",
                int(legend.get_int("show")),
                int(K14_VIOLIN_STYLE.legend_visible),
            )
    return {"groups": observed_rows, "fresh_reopen": True}


def _verify_series_member(
    op: Any,
    graph: Any,
    layer: Any,
    plot_index: int,
    action: SetSeriesStyle,
) -> dict[str, object]:
    plot_range = _checked_plot_range(op, graph, layer, plot_index)
    line_symbol_color_cascade = (
        action.line_stroke_color is not None
        and int(_get_plot_option(op, plot_range, "-pt")) in _LINE_SYMBOL_PIDS
    )
    effective_marker_fill = (
        "#FFFFFF"
        if action.marker_interior in {"open", "hollow"}
        else (
            action.marker_fill_color
            if action.marker_fill_color is not None
            else action.line_stroke_color
            if line_symbol_color_cascade
            else None
        )
    )
    effective_marker_stroke = (
        action.marker_stroke_color
        if action.marker_stroke_color is not None
        else action.line_stroke_color
        if line_symbol_color_cascade
        else None
    )
    numeric_options: tuple[tuple[str, object, str, float], ...] = (
        (
            "line_color",
            action.line_stroke_color,
            "-cl",
            float(_color(op, action.line_stroke_color)) if action.line_stroke_color else 0,
        ),
        ("line_width", action.line_width_pt, "-wp", action.line_width_pt or 0),
        (
            "line_style",
            action.line_style,
            "-d",
            float(_LINE_STYLE[action.line_style]) if action.line_style else 0,
        ),
        (
            "marker_shape",
            action.marker_shape,
            "-k",
            float(_MARKER[action.marker_shape]) if action.marker_shape else 0,
        ),
        ("marker_size", action.marker_size_pt, "-z", action.marker_size_pt or 0),
        (
            "marker_interior",
            action.marker_interior,
            "-kf",
            float(_INTERIOR[action.marker_interior]) if action.marker_interior else 0,
        ),
        (
            "marker_fill_color",
            effective_marker_fill,
            "-csf",
            float(_color(op, effective_marker_fill)) if effective_marker_fill else 0,
        ),
        (
            "marker_stroke_color",
            effective_marker_stroke,
            "-cse",
            float(_color(op, effective_marker_stroke)) if effective_marker_stroke else 0,
        ),
        (
            "fill_color",
            action.fill_color,
            "-pfb",
            float(_color(op, action.fill_color)) if action.fill_color else 0,
        ),
        (
            "fill_stroke_color",
            action.fill_stroke_color,
            "-pbc",
            float(_color(op, action.fill_stroke_color)) if action.fill_stroke_color else 0,
        ),
        (
            "fill_stroke_width",
            action.fill_stroke_width_pt,
            "-pbw",
            action.fill_stroke_width_pt or 0,
        ),
        (
            "fill_stroke_style",
            action.fill_stroke_style,
            "-pbs",
            float(_BORDER_STYLE[action.fill_stroke_style]) if action.fill_stroke_style else 0,
        ),
    )
    observed: dict[str, object] = {}
    for name, requested, option, expected in numeric_options:
        if requested is None:
            continue
        value = _get_plot_option(op, plot_range, option)
        _require_number(
            name,
            value,
            expected,
            tolerance=_series_numeric_tolerance(name),
        )
        observed[name] = value
    for name, requested, property_path in (
        ("line_opacity", action.line_opacity, "transparency"),
        ("marker_opacity", action.marker_opacity, "symbol.transparency"),
    ):
        if requested is not None:
            value = 1 - _get_plot_property(op, graph, layer, plot_index, property_path) / 100
            _require_number(name, value, requested)
            observed[name] = value
    if action.fill_opacity is not None:
        fill_only_option = (
            "-paap" if int(_get_plot_option(op, plot_range, "-pt")) in _BAR_COLUMN_PIDS else "-paaf"
        )
        _require_number(
            "fill-only transparency mode",
            _get_plot_option(op, plot_range, fill_only_option),
            1,
        )
        value = 1 - _get_plot_property(op, graph, layer, plot_index, "transparency") / 100
        _require_number("fill opacity", value, action.fill_opacity)
        observed["fill_opacity"] = value
    return observed


def _verify_x40_group_structure(
    state: X40GroupStyleState,
    actions: tuple[PlotEngineAction, ...],
) -> dict[str, object]:
    _require_equal("X40 native group member count", state.group_count, 2)
    _require_equal("X40 native subgroup size", state.subgroup_size, 2)
    _require_equal("X40 connector subgroup mode", state.connector_by_subgroup, 1)
    expected_connector_visible = True
    for candidate in actions:
        action = _x40_style_action(candidate)
        if action is None or _target_key(action.target) != "connector":
            continue
        if action.visible is not None:
            expected_connector_visible = action.visible
        if action.line_style == "none":
            expected_connector_visible = False
    _require_equal(
        "X40 connector visibility",
        state.connector_visible,
        expected_connector_visible,
    )
    return {
        "group_count": state.group_count,
        "subgroup_size": state.subgroup_size,
        "connector_by_subgroup": state.connector_by_subgroup,
        "connector_visible": state.connector_visible,
        "marker_shapes": list(state.marker_shapes),
        "marker_sizes": list(state.marker_sizes),
        "marker_interiors": list(state.marker_interiors),
        "marker_edge_colors": list(state.marker_edge_colors),
        "marker_fill_colors": list(state.marker_fill_colors),
        "connector_style": state.connector_style,
        "connector_width": state.connector_width,
        "connector_color": state.connector_color,
    }


def _verify_x40_style_action(
    op: Any,
    action: SetSeriesStyle,
    state: X40GroupStyleState,
) -> dict[str, object]:
    checked = _x40_style_action(action)
    if checked is None:
        raise ValueError(f"X40 style target is not part of the native group: {action.target}")
    key = _target_key(action.target)
    observed: dict[str, object] = {}
    if key == "connector":
        if action.visible is not None or action.line_style == "none":
            expected_visible = False if action.line_style == "none" else bool(action.visible)
            _require_equal("X40 connector visibility", state.connector_visible, expected_visible)
            observed["visible"] = state.connector_visible
        if action.line_style is not None and action.line_style != "none":
            expected_style = _REFERENCE_LINE_STYLE[action.line_style]
            _require_equal("X40 connector style", state.connector_style, expected_style)
            observed["line_style"] = state.connector_style
        if action.line_width_pt is not None:
            _require_number("X40 connector width", state.connector_width, action.line_width_pt)
            observed["line_width"] = state.connector_width
        if action.line_stroke_color is not None:
            expected_color = _color(op, action.line_stroke_color)
            _require_equal("X40 connector color", state.connector_color, expected_color)
            observed["line_color"] = state.connector_color
        return observed

    member = _ordinal(key) - 1
    if action.marker_shape is not None:
        expected_shape = _MARKER[action.marker_shape]
        _require_equal("X40 marker shape", state.marker_shapes[member], expected_shape)
        observed["marker_shape"] = state.marker_shapes[member]
    if action.marker_size_pt is not None:
        _require_number(
            "X40 marker size",
            state.marker_sizes[member],
            action.marker_size_pt,
            tolerance=0.01,
        )
        observed["marker_size"] = state.marker_sizes[member]
    if action.marker_interior is not None:
        expected_interior = _INTERIOR[action.marker_interior]
        _require_equal(
            "X40 marker interior",
            state.marker_interiors[member],
            expected_interior,
        )
        observed["marker_interior"] = state.marker_interiors[member]
    if action.marker_stroke_color is not None:
        expected_edge = _color(op, action.marker_stroke_color)
        _require_equal("X40 marker edge color", state.marker_edge_colors[member], expected_edge)
        observed["marker_stroke_color"] = state.marker_edge_colors[member]
    effective_fill = (
        "#FFFFFF" if action.marker_interior in {"open", "hollow"} else action.marker_fill_color
    )
    if effective_fill is not None:
        expected_fill = _color(op, effective_fill)
        _require_equal("X40 marker fill color", state.marker_fill_colors[member], expected_fill)
        observed["marker_fill_color"] = state.marker_fill_colors[member]
    return observed


def _axis_coordinate_fraction(
    layer: Any,
    axis_name: Literal["x", "y"],
    value: float,
) -> float:
    axis = layer.axis(axis_name)
    start, end, *_ = (float(item) for item in axis.limits)
    scale = axis.scale
    if scale in {"linear", 1}:
        transformed = (start, end, value)
    elif scale in {"log10", 2}:
        if min(start, end, value) <= 0:
            raise RuntimeError("Origin callout readback contains a non-positive log value")
        transformed = (log10(start), log10(end), log10(value))
    else:
        raise ValueError(f"Origin callouts do not support axis scale {scale!r}")
    lower, upper, observed = transformed
    if isclose(lower, upper, rel_tol=0, abs_tol=1e-15):
        raise RuntimeError("Origin callout readback axis has zero span")
    return (observed - lower) / (upper - lower)


def _require_axis_coordinate(
    name: str,
    observed: float,
    expected: float,
    *,
    layer: Any,
    axis_name: Literal["x", "y"],
) -> None:
    """Accept only Origin's sub-pixel graph-object serialization noise."""

    observed_fraction = _axis_coordinate_fraction(layer, axis_name, observed)
    expected_fraction = _axis_coordinate_fraction(layer, axis_name, expected)
    if not isclose(observed_fraction, expected_fraction, rel_tol=0, abs_tol=5e-4):
        raise RuntimeError(
            f"Origin T1 fresh readback mismatch for {name}: expected {expected}, "
            f"observed {observed}; normalized delta="
            f"{abs(observed_fraction - expected_fraction):.12g}"
        )


def _verify_actions(
    op: Any,
    graph: Any,
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
) -> dict[str, object]:
    """Read back stable public properties for the fresh-reopen gate."""

    snapshot: dict[str, object] = {}
    x40_group_state = (
        read_x40_group_style(
            op,
            str(graph.name),
            _layer_index(_layers(graph)[0]),
        )
        if document.profile_id == "X40"
        else None
    )
    if x40_group_state is not None:
        snapshot["x40_native_group"] = _verify_x40_group_structure(
            x40_group_state,
            actions,
        )
    k07_band_state: K07ErrorBandStyleState | None = (
        read_k07_error_band_style(
            op,
            str(graph.name),
            _layer_index(_layers(graph)[0]),
        )
        if document.profile_id == "K07"
        else None
    )
    reference_line_slots = {
        action.action_id: (layer, axis_name, index)
        for action, layer, axis_name, index in _reference_line_slots(
            graph,
            tuple(action for action in actions if isinstance(action, AddReferenceLine)),
        )
    }
    reference_lines_by_id = {
        action.reference_line_id: action
        for action in actions
        if isinstance(action, AddReferenceLine)
    }
    for action in actions:
        if isinstance(action, SetCanvas):
            width, height = _graph_page_size(graph)
            expected_width, expected_height = resolve_canvas_inches(width, height, action)
            if action.width_mm is not None:
                expected_width = action.width_mm / 25.4
            if action.height_mm is not None:
                expected_height = action.height_mm / 25.4
            if (
                action.aspect_ratio is not None
                and action.width_mm is None
                and action.height_mm is None
            ):
                _require_number(
                    "canvas aspect ratio",
                    width / height,
                    action.aspect_ratio,
                    tolerance=1e-3,
                )
            else:
                _require_number("canvas width", width, expected_width, tolerance=1e-3)
                _require_number("canvas height", height, expected_height, tolerance=1e-3)
            snapshot[action.action_id] = {
                "width_mm": width * 25.4,
                "height_mm": height * 25.4,
                "aspect_ratio": width / height,
            }
        elif isinstance(action, SetTitle):
            title = _layers(graph)[0].label("_ENGINE_TITLE")
            if title is None:
                raise RuntimeError("Origin title did not survive T1 fresh reopen")
            title_text, _bold, _italic = _text_style(title.text)
            if action.text is not None and title_text != action.text:
                raise RuntimeError("Origin title did not survive T1 fresh reopen")
            snapshot[action.action_id] = _verify_label_style(op, title, action)
        elif isinstance(action, SetAxis):
            layer, axis_name = _axis_target(graph, action.target)
            visual_prefix = _axis_visual_prefix(axis_name, action.target)
            observed: dict[str, object] = {"reverse": layer.get_int(f"{axis_name}.reverse")}
            side_bit = _axis_side_bit(action.target)
            if action.scale is not None:
                observed_scale = layer.axis(axis_name).scale
                if not axis_scale_matches(observed_scale, action.scale):
                    raise RuntimeError(
                        "Origin T1 fresh readback mismatch for axis scale: "
                        f"expected {action.scale!r}, observed {observed_scale!r}"
                    )
                observed["scale"] = observed_scale
            if action.minimum is not None and action.maximum is not None:
                begin, end, *_ = (float(value) for value in layer.axis(axis_name).limits)
                expected_limits = (
                    (action.maximum, action.minimum)
                    if action.reverse
                    else (action.minimum, action.maximum)
                )
                _require_number("axis minimum", begin, expected_limits[0])
                _require_number("axis maximum", end, expected_limits[1])
                observed["limits"] = (begin, end)
            if action.bounds_mode is not None:
                observed_mode = int(layer.get_int(f"{axis_name}.rescale"))
                if action.bounds_mode == "automatic":
                    _require_equal("axis bounds mode", observed_mode, 3)
                elif not _fixed_axis_bounds_mode_is_valid(observed_mode):
                    raise RuntimeError(
                        "Origin T1 fresh readback mismatch for axis bounds mode: "
                        f"expected a fixed/manual mode, observed {observed_mode}"
                    )
                observed["bounds_mode"] = action.bounds_mode
                observed["bounds_mode_native"] = observed_mode
            if action.reverse is not None:
                _require_equal("axis reverse", observed["reverse"], int(action.reverse))
            if action.label is not None:
                label_name = _axis_label_name(graph, layer, axis_name)
                label = layer.label(label_name)
                if label is None:
                    raise RuntimeError("Origin axis label did not survive T1 fresh reopen")
                label_text, label_bold, label_italic = _text_style(label.text)
                if label_text != action.label:
                    raise RuntimeError("Origin axis label did not survive T1 fresh reopen")
                observed["label"] = label_text
                for name, requested, prop, expected_value in (
                    (
                        "title font",
                        action.title_font_family,
                        "font",
                        _font(op, action.title_font_family),
                    ),
                    ("title size", action.title_font_size_pt, "fsize", action.title_font_size_pt),
                    (
                        "title color",
                        action.title_color,
                        "color",
                        _color(op, action.title_color) if action.title_color else None,
                    ),
                ):
                    if requested is not None and expected_value is not None:
                        value = label.get_float(prop)
                        _require_number(name, value, float(expected_value))
                        observed[name.replace(" ", "_")] = value
                if action.title_font_weight is not None:
                    _require_equal(
                        "title weight",
                        label_bold,
                        action.title_font_weight == "bold",
                    )
                    observed["title_weight"] = label_bold
                if action.title_italic is not None:
                    _require_equal("title italic", label_italic, action.title_italic)
                    observed["title_italic"] = label_italic
            if action.axis_title_visible is not None:
                title = layer.label(_axis_label_name(graph, layer, axis_name))
                title_visible = 0 if title is None else int(title.get_int("show"))
                _require_equal(
                    "axis title visibility",
                    title_visible,
                    int(action.axis_title_visible),
                )
                observed["axis_title_visible"] = title_visible
            if action.tick_labels_visible is not None:
                show_labels = layer.get_int(f"{axis_name}.showLabels")
                _require_equal(
                    "tick label visibility",
                    bool(show_labels & side_bit),
                    action.tick_labels_visible,
                )
                observed["show_labels"] = show_labels
            if action.axis_line_visible is not None:
                show_axis = read_axis_line_show(
                    op,
                    graph.name,
                    _layer_index(layer),
                    _axis_native_code(action.target),
                )
                _require_equal(
                    "axis line visibility",
                    bool(show_axis),
                    action.axis_line_visible,
                )
                observed["show_axis"] = show_axis
            if (
                action.major_ticks_visible is not None
                or action.minor_ticks_visible is not None
                or action.tick_direction is not None
            ):
                ticks = layer.get_int(f"{axis_name}.ticks")
                major_bits = ticks & 3
                minor_bits = ticks & 12
                if action.major_ticks_visible is not None:
                    _require_equal(
                        "major tick visibility",
                        bool(major_bits),
                        action.major_ticks_visible,
                    )
                if action.minor_ticks_visible is not None:
                    _require_equal(
                        "minor tick visibility",
                        bool(minor_bits),
                        action.minor_ticks_visible,
                    )
                if action.tick_direction is not None:
                    expected_major, expected_minor = _TICK_DIRECTION_BITS[action.tick_direction]
                    if major_bits:
                        _require_equal("major tick direction", major_bits, expected_major)
                    if minor_bits:
                        _require_equal("minor tick direction", minor_bits, expected_minor)
                observed["ticks"] = ticks
            direct_properties = (
                (
                    "major_tick_step",
                    action.major_tick_step,
                    f"{axis_name}.inc",
                    action.major_tick_step,
                ),
                (
                    "minor_tick_count",
                    action.minor_tick_count,
                    f"{axis_name}.minorTicks",
                    action.minor_tick_count,
                ),
                (
                    "tick_rotation",
                    action.tick_rotation_deg,
                    f"{visual_prefix}.label.rotate",
                    action.tick_rotation_deg,
                ),
                (
                    "tick_font",
                    action.tick_font_family,
                    f"{visual_prefix}.label.font",
                    _font(op, action.tick_font_family),
                ),
                (
                    "tick_color",
                    action.tick_color,
                    f"{visual_prefix}.label.color",
                    _color(op, action.tick_color) if action.tick_color else None,
                ),
                (
                    "axis_color",
                    action.axis_line_color,
                    f"{visual_prefix}.color",
                    _color(op, action.axis_line_color) if action.axis_line_color else None,
                ),
                (
                    "axis_width",
                    action.axis_line_width_pt,
                    f"{visual_prefix}.thickness",
                    action.axis_line_width_pt,
                ),
            )
            if action.tick_font_size_pt is not None:
                value = read_axis_tick_font_size(
                    op,
                    str(graph.name),
                    _layer_index(layer),
                    _axis_native_code(action.target),
                )
                _require_number("tick_size", value, action.tick_font_size_pt)
                observed["tick_size"] = value
            for name, requested, prop, expected_value in direct_properties:
                if requested is not None and expected_value is not None:
                    value = layer.get_float(prop)
                    tolerance = 0.051 if name in {"axis_width", "major_tick_step"} else 1e-7
                    _require_number(
                        name,
                        value,
                        float(expected_value),
                        tolerance=tolerance,
                    )
                    observed[name] = value
            if action.tick_format is not None:
                if action.tick_format in {"date", "time"}:
                    expected_type = {"date": 4, "time": 3}[action.tick_format]
                    tick_type = layer.get_int(f"{visual_prefix}.label.type")
                    _require_equal("tick format type", tick_type, expected_type)
                    observed["tick_format_type"] = tick_type
                else:
                    expected_format = {
                        "auto": 0,
                        "decimal": 1,
                        "scientific": 2,
                        "percent": 1,
                    }[action.tick_format]
                    tick_format = layer.get_int(f"{visual_prefix}.label.numFormat")
                    _require_equal("tick numeric format", tick_format, expected_format)
                    suffix = layer.get_str(f"{visual_prefix}.label.suf")
                    _require_equal(
                        "tick format suffix",
                        suffix,
                        "%" if action.tick_format == "percent" else "",
                    )
                    observed["tick_format"] = tick_format
                    observed["tick_suffix"] = suffix
            if action.major_grid_visible is not None or action.minor_grid_visible is not None:
                grid_bits = layer.get_int(f"{axis_name}.grid.show")
                if action.major_grid_visible is not None:
                    _require_equal(
                        "major grid visibility",
                        bool(grid_bits & 1),
                        action.major_grid_visible,
                    )
                if action.minor_grid_visible is not None:
                    _require_equal(
                        "minor grid visibility",
                        bool(grid_bits & 2),
                        action.minor_grid_visible,
                    )
                observed["grid_visibility"] = grid_bits
            for prefix in ("major", "minor"):
                for name, requested, prop, expected_value, tolerance in (
                    (
                        f"{prefix}_grid_color",
                        action.grid_color,
                        f"{axis_name}.grid.{prefix}Color",
                        _color(op, action.grid_color) if action.grid_color else None,
                        1e-7,
                    ),
                    (
                        f"{prefix}_grid_width",
                        action.grid_line_width_pt,
                        f"{axis_name}.grid.{prefix}Width",
                        action.grid_line_width_pt,
                        0.051,
                    ),
                    (
                        f"{prefix}_grid_style",
                        action.grid_line_style,
                        f"{axis_name}.grid.{prefix}Type",
                        (_LINE_STYLE[action.grid_line_style] if action.grid_line_style else None),
                        1e-7,
                    ),
                ):
                    if requested is not None and expected_value is not None:
                        value = layer.get_float(prop)
                        _require_number(
                            name,
                            value,
                            float(expected_value),
                            tolerance=tolerance,
                        )
                        observed[name] = value
            snapshot[action.action_id] = observed
        elif isinstance(action, SetSeriesStyle):
            k09_subset_action = _k09_subset_fill_action(document, action)
            if x40_group_state is not None and _x40_style_action(action) is not None:
                snapshot[action.action_id] = _verify_x40_style_action(
                    op,
                    action,
                    x40_group_state,
                )
            else:
                snapshot[action.action_id] = (
                    _verify_k09_subset_fill_color(op, graph, k09_subset_action)
                    if k09_subset_action is not None
                    else _verify_series(
                        op,
                        graph,
                        action,
                        profile_id=document.profile_id,
                    )
                )
        elif (
            isinstance(action, SetChartParameter)
            and action.parameter in K09_VISUAL_CHART_PARAMETERS
        ):
            if document.profile_id != "K09" or action.target != document.plot_id:
                raise ValueError("K09 grouped-column parameters require the K09 plot target")
            layer = _layers(graph)[0]
            plot_range = _checked_plot_range(op, graph, layer, 1)
            if action.parameter == "bar_border_visible":
                observed_color = int(_get_plot_option(op, plot_range, "-pbc"))
                expected_visible = bool(action.value)
                _require_equal(
                    "K09 bar border visibility",
                    observed_color != -4,
                    expected_visible,
                )
                snapshot[action.action_id] = {
                    "bar_border_visible": observed_color != -4,
                    "bar_border_color": observed_color,
                }
            elif action.parameter == "within_group_gap_percent":
                observed_gap = float(_get_plot_option(op, plot_range, "-vg"))
                _require_number(
                    "K09 within-group gap",
                    observed_gap,
                    float(action.value),
                )
                snapshot[action.action_id] = {"within_group_gap_percent": observed_gap}
            else:
                observed_gap = float(_get_plot_property(op, graph, layer, 1, "subsetgap"))
                _require_number(
                    "K09 between-group gap",
                    observed_gap,
                    float(action.value),
                )
                snapshot[action.action_id] = {"between_group_gap_percent": observed_gap}
        elif isinstance(action, SetLegend):
            legend = _layers(graph)[0].label("legend")
            if action.visible is True and (legend is None or not legend.get_int("show")):
                raise RuntimeError("Origin legend did not survive T1 fresh reopen")
            if legend is None:
                snapshot[action.action_id] = None
            else:
                observed = {"show": legend.get_int("show")}
                if action.visible is not None:
                    _require_equal("legend visibility", observed["show"], int(action.visible))
                if action.columns is not None:
                    columns = (
                        _k09_legend_column_count(legend.text)
                        if document.profile_id == "K09"
                        else _legend_column_count(legend.get_int("ncols"))
                    )
                    _require_equal("legend columns", columns, action.columns)
                    observed["columns"] = columns
                if action.title is not None:
                    legend_text, _bold, _italic = _text_style(legend.text)
                    title = legend_text.splitlines()[0] if legend_text else ""
                    _require_equal("legend title", title, action.title)
                    observed["title"] = title
                if action.anchor is not None:
                    expected_anchor = _origin_legend_anchor(
                        graph,
                        _layers(graph)[0],
                        legend,
                        action.anchor,
                    )
                    attach = legend.get_int("attach")
                    left = legend.get_int("left")
                    top = legend.get_int("top")
                    _require_equal("legend attachment", attach, expected_anchor[0])
                    if abs(left - expected_anchor[1]) > 2:
                        raise RuntimeError(
                            "Origin T1 fresh readback mismatch for legend left: "
                            f"expected {expected_anchor[1]}, observed {left}"
                        )
                    if abs(top - expected_anchor[2]) > 2:
                        raise RuntimeError(
                            "Origin T1 fresh readback mismatch for legend top: "
                            f"expected {expected_anchor[2]}, observed {top}"
                        )
                    observed["anchor"] = (attach, left, top)
                for name, requested, prop, expected_value, tolerance in (
                    (
                        "font",
                        action.font_family,
                        "font",
                        _font(op, action.font_family),
                        1e-7,
                    ),
                    (
                        "font_size",
                        action.font_size_pt,
                        "fsize",
                        action.font_size_pt,
                        1e-7,
                    ),
                    (
                        "font_color",
                        action.font_color,
                        "color",
                        _color(op, action.font_color) if action.font_color else None,
                        1e-7,
                    ),
                    (
                        "frame_visible",
                        action.frame_visible,
                        "background",
                        int(action.frame_visible) if action.frame_visible is not None else None,
                        1e-7,
                    ),
                    (
                        "frame_color",
                        action.frame_color,
                        "borderColor",
                        _color(op, action.frame_color) if action.frame_color else None,
                        1e-7,
                    ),
                    (
                        "frame_width",
                        action.frame_width_pt,
                        "lineWidth",
                        action.frame_width_pt,
                        0.051,
                    ),
                ):
                    if requested is not None and expected_value is not None:
                        value = legend.get_float(prop)
                        _require_number(
                            f"legend {name}",
                            value,
                            float(expected_value),
                            tolerance=tolerance,
                        )
                        observed[name] = value
                snapshot[action.action_id] = observed
        elif isinstance(action, SetColorMap):
            layer, _ = _layer_and_plot(graph, action.target)
            observed_palette = layer.get_str("cmap.palette")
            observed_reverse = layer.get_int("cmap.flippal")
            observed_minimum = layer.get_float("cmap.zMin")
            observed_maximum = layer.get_float("cmap.zMax")
            observed_levels = layer.get_int("cmap.numColors")
            observed_colormap: dict[str, object] = {
                "palette": observed_palette,
                "reverse": observed_reverse,
                "minimum": observed_minimum,
                "maximum": observed_maximum,
                "levels": observed_levels,
            }
            if action.palette is not None:
                _require_equal(
                    "colormap palette",
                    Path(observed_palette).stem.casefold(),
                    _PALETTE[action.palette].casefold(),
                )
            if action.reverse is not None:
                expected_reverse = _origin_colormap_flip(
                    document.profile_id,
                    action.palette,
                    action.reverse,
                )
                _require_equal("colormap reverse", observed_reverse, expected_reverse)
            if action.minimum is not None and action.maximum is not None:
                _require_number("colormap minimum", observed_minimum, action.minimum)
                _require_number("colormap maximum", observed_maximum, action.maximum)
            expected_levels = action.levels or (
                8 if action.mode == "discrete" else (256 if action.mode == "continuous" else None)
            )
            if expected_levels is not None:
                _require_equal("colormap levels", observed_levels, expected_levels)
            if action.midpoint is not None:
                middle_index = observed_levels // 2 + 1
                midpoint = layer.get_float(f"cmap.z{middle_index}")
                _require_number("colormap midpoint", midpoint, action.midpoint)
                observed_colormap["midpoint"] = midpoint
            if action.missing_color is not None:
                missing_color = layer.get_int("cmap.colorMiss")
                _require_equal(
                    "colormap missing color",
                    missing_color,
                    _color(op, action.missing_color),
                )
                observed_colormap["missing_color"] = missing_color
            spectrum = layer.label("SPECTRUM1")
            if action.colorbar_visible is not None:
                if spectrum is None:
                    raise RuntimeError("Origin color scale has no native object")
                colorbar_visible = spectrum.get_int("show")
                _require_equal(
                    "color scale visibility",
                    colorbar_visible,
                    int(action.colorbar_visible),
                )
                observed_colormap["colorbar_visible"] = colorbar_visible
            if action.colorbar_title is not None:
                if spectrum is None:
                    raise RuntimeError("Origin color scale title has no native object")
                layer_index = _layer_index(layer)
                _require_equal(
                    "color scale title visibility",
                    read_color_scale_title_show(op, graph.name, layer_index),
                    1,
                )
                observed_title = read_color_scale_title(op, graph.name, layer_index)
                _require_equal("color scale title", observed_title, action.colorbar_title)
                observed_colormap["colorbar_title"] = observed_title
            if action.colorbar_anchor is not None:
                if spectrum is None:
                    raise RuntimeError("Origin color scale anchor has no native object")
                anchor = read_color_scale_anchor(op, graph.name, _layer_index(layer))
                _require_equal(
                    "color scale arrangement",
                    anchor.arrangement,
                    2 if action.colorbar_anchor == "bottom" else 1,
                )
                _require_equal("color scale page attachment", anchor.attach, 1)
                if action.colorbar_anchor == "bottom":
                    if anchor.top < anchor.layer_bottom:
                        raise RuntimeError(
                            "Origin T1 fresh readback mismatch for color scale anchor: "
                            "bottom scale is above the layer bottom"
                        )
                    if anchor.width <= anchor.height:
                        raise RuntimeError(
                            "Origin T1 fresh readback mismatch for color scale arrangement: "
                            "horizontal scale is not wider than it is tall"
                        )
                else:
                    if anchor.left < anchor.layer_right:
                        raise RuntimeError(
                            "Origin T1 fresh readback mismatch for color scale anchor: "
                            "right scale is left of the layer right edge"
                        )
                    if anchor.height <= anchor.width:
                        raise RuntimeError(
                            "Origin T1 fresh readback mismatch for color scale arrangement: "
                            "vertical scale is not taller than it is wide"
                        )
                observed_colormap["colorbar_anchor"] = {
                    "anchor": action.colorbar_anchor,
                    "arrangement": anchor.arrangement,
                    "attach": anchor.attach,
                    "left": anchor.left,
                    "top": anchor.top,
                    "width": anchor.width,
                    "height": anchor.height,
                    "layer_left": anchor.layer_left,
                    "layer_top": anchor.layer_top,
                    "layer_right": anchor.layer_right,
                    "layer_bottom": anchor.layer_bottom,
                }
            if action.colorbar_tick_format is not None:
                if spectrum is None:
                    raise RuntimeError("Origin color scale ticks have no native object")
                tick_format = read_color_scale_tick_format(
                    op,
                    graph.name,
                    _layer_index(layer),
                )
                expected_display = {
                    "auto": None,
                    "decimal": 5,
                    "scientific": 4,
                    "percent": 5,
                }[action.colorbar_tick_format]
                _require_equal(
                    "color scale automatic tick format",
                    tick_format.automatic,
                    int(action.colorbar_tick_format == "auto"),
                )
                _require_equal("color scale tick label type", tick_format.label_type, 0)
                if expected_display is not None:
                    _require_equal(
                        "color scale numeric tick format",
                        tick_format.numeric_format,
                        expected_display,
                    )
                if action.colorbar_tick_format == "percent":
                    _require_equal(
                        "color scale percent tick format",
                        tick_format.custom_format,
                        "*3%",
                    )
                if action.colorbar_tick_format == "decimal":
                    _require_equal(
                        "color scale decimal tick format",
                        tick_format.custom_format,
                        "*6",
                    )
                observed_colormap["colorbar_tick_format"] = tick_format._asdict()
            snapshot[action.action_id] = observed_colormap
        elif isinstance(action, SetErrorStyle):
            layer, plot_indices = _error_plots(op, graph, action.target)
            k07_native_band = (
                document.profile_id == "K07" and _target_key(action.target) == "primary"
            )
            observed_plots: list[dict[str, object]] = []
            for plot_index in plot_indices:
                plot_range = _checked_plot_range(op, graph, layer, plot_index)
                observed: dict[str, object] = {"plot_index": plot_index}
                for name, requested, option, expected_value in (
                    (
                        "bar_color",
                        action.bar_color,
                        "-c",
                        _color(op, action.bar_color) if action.bar_color else None,
                    ),
                    ("bar_width", action.bar_width_pt, "-erw", action.bar_width_pt),
                    ("cap_size", action.cap_size_pt, "-erwc", action.cap_size_pt),
                    (
                        "band_fill_color",
                        action.band_fill_color,
                        "-pfb",
                        _color(op, action.band_fill_color) if action.band_fill_color else None,
                    ),
                    (
                        "band_stroke_color",
                        action.band_stroke_color,
                        "-pbc",
                        _color(op, action.band_stroke_color) if action.band_stroke_color else None,
                    ),
                    (
                        "band_stroke_width",
                        action.band_stroke_width_pt,
                        "-pbw",
                        action.band_stroke_width_pt,
                    ),
                ):
                    if k07_native_band and name in {
                        "band_stroke_color",
                        "band_stroke_width",
                    }:
                        continue
                    if requested is not None and expected_value is not None:
                        value = _get_plot_option(op, plot_range, option)
                        tolerance = 0.051 if name in {"bar_width", "band_stroke_width"} else 1e-7
                        _require_number(
                            name,
                            value,
                            float(expected_value),
                            tolerance=tolerance,
                        )
                        observed[name] = value
                if action.bar_opacity is not None:
                    value = 1 - (
                        _get_plot_property(op, graph, layer, plot_index, "transparency") / 100
                    )
                    _require_number("error opacity", value, action.bar_opacity)
                    observed["bar_opacity"] = value
                if action.band_fill_opacity is not None and not k07_native_band:
                    fill_only = _get_plot_option(op, plot_range, "-paaf")
                    _require_number("error band fill-only transparency", fill_only, 1)
                    value = 1 - (
                        _get_plot_property(op, graph, layer, plot_index, "transparency") / 100
                    )
                    _require_number("error band opacity", value, action.band_fill_opacity)
                    observed["band_fill_opacity"] = value
                observed_plots.append(observed)
            observed_action: dict[str, object] = (
                observed_plots[0] if len(observed_plots) == 1 else {"plots": observed_plots}
            )
            if k07_native_band:
                if k07_band_state is None:
                    raise RuntimeError("Origin K07 native error-band readback is missing")
                native_observed: dict[str, object] = {
                    "fill_transparencies": list(k07_band_state.fill_transparencies),
                    "line_colors": list(k07_band_state.line_colors),
                    "line_widths": list(k07_band_state.line_widths),
                }
                if action.band_fill_opacity is not None:
                    expected_transparency = (1 - action.band_fill_opacity) * 100
                    for value in k07_band_state.fill_transparencies:
                        _require_number(
                            "K07 native band fill transparency",
                            value,
                            expected_transparency,
                            tolerance=0.051,
                        )
                    native_observed["band_fill_opacity"] = action.band_fill_opacity
                if action.band_stroke_color is not None:
                    expected_color = _color(op, action.band_stroke_color)
                    for value in k07_band_state.line_colors:
                        _require_equal("K07 native band line color", value, expected_color)
                if action.band_stroke_width_pt is not None:
                    for value in k07_band_state.line_widths:
                        _require_number(
                            "K07 native band line width",
                            value,
                            action.band_stroke_width_pt,
                            tolerance=0.051,
                        )
                observed_action["native_error_band"] = native_observed
            snapshot[action.action_id] = observed_action
        elif isinstance(action, SetDataLabels):
            layer, plot_index = _layer_and_plot(graph, action.target)
            plot_range = _checked_plot_range(op, graph, layer, plot_index)
            observed = {}
            for name, requested, option, expected_value in (
                (
                    "visible",
                    action.visible,
                    "-q",
                    int(action.visible) if action.visible is not None else None,
                ),
                (
                    "position",
                    action.position,
                    "-qp",
                    _LABEL_POSITION[action.position] if action.position else None,
                ),
                ("rotation", action.rotation_deg, "-qr", action.rotation_deg),
                ("font", action.font_family, "-qf", _font(op, action.font_family)),
                ("font_size", action.font_size_pt, "-qs", action.font_size_pt),
                (
                    "font_weight",
                    action.font_weight,
                    "-qb",
                    _FONT_WEIGHT[action.font_weight] if action.font_weight else None,
                ),
                (
                    "font_color",
                    action.font_color,
                    "-qc",
                    _color(op, action.font_color) if action.font_color else None,
                ),
            ):
                if requested is not None and expected_value is not None:
                    value = _get_plot_option(op, plot_range, option)
                    _require_number(name, value, float(expected_value))
                    observed[name] = value
            if (
                action.value_format is not None
                or action.prefix is not None
                or action.suffix is not None
            ):
                format_code = {
                    "auto": "*",
                    "decimal": "*3",
                    "scientific": "E3",
                    "percent": "*3",
                }[action.value_format or "auto"]
                suffix = f"{action.suffix or ''}{'%' if action.value_format == 'percent' else ''}"
                expected_label_display = f"{action.prefix or ''}$(Y,{format_code}){suffix}"
                display = _get_plot_option_str(op, plot_range, "-qms")
                _require_equal("data label display", display, expected_label_display)
                observed["display"] = display
            snapshot[action.action_id] = observed
        elif isinstance(action, AddAnnotation):
            name = action.annotation_id.replace(":", "_").replace(".", "_")
            label = _layers(graph)[0].label(name)
            if label is None or _text_style(label.text)[0] != action.text:
                raise RuntimeError("Origin annotation did not survive T1 fresh reopen")
            observed = _verify_label_style(op, label, action)
            for prop, expected in (("x", action.x), ("y", action.y)):
                value = label.get_float(prop)
                # Origin serializes text-object centers through pixel space;
                # sub-pixel round trips can shift a data coordinate slightly.
                _require_number(f"annotation {prop}", value, expected, tolerance=1e-3)
                observed[prop] = value
            snapshot[action.action_id] = observed
        elif isinstance(action, AddReferenceLine):
            layer, axis_name, index = reference_line_slots[action.action_id]
            prefix = f"{axis_name}.refline{index}"
            coordinate = layer.get_float(f"{prefix}.value")
            _require_number("reference line value", coordinate, action.value)
            expected_color = _color(op, action.line_color or "#667085")
            expected_style = _REFERENCE_LINE_STYLE[action.line_style or "dash"]
            expected_width = action.line_width_pt or 1.0
            _require_equal(
                "reference line collection count",
                layer.get_int(f"{axis_name}.reflines.count"),
                sum(
                    1
                    for candidate in reference_line_slots.values()
                    if _layer_index(candidate[0]) == _layer_index(layer)
                    and candidate[1] == axis_name
                ),
            )
            _require_equal("reference line visibility", layer.get_int(f"{prefix}.lineshow"), 1)
            _require_equal("reference line auto format", layer.get_int(f"{prefix}.lineauto"), 0)
            _require_equal(
                "reference line color", layer.get_int(f"{prefix}.linecolor"), expected_color
            )
            _require_equal(
                "reference line style", layer.get_int(f"{prefix}.linestyle"), expected_style
            )
            width = layer.get_float(f"{prefix}.linethickness")
            _require_number("reference line width", width, expected_width, tolerance=0.051)
            reference_observed: dict[str, object] = {
                "reference_line_id": action.reference_line_id,
                "axis": axis_name,
                "native_index": index,
                "value": coordinate,
                "color": expected_color,
                "line_style": expected_style,
                "line_width_pt": width,
            }
            if action.label:
                if layer.get_int(f"{prefix}.labelshow") != 1:
                    raise RuntimeError(
                        "Origin reference line label did not survive T1 fresh reopen"
                    )
                label = layer.get_str(f"{prefix}.labeltext")
                _require_equal("reference line label", label, action.label)
                reference_observed["label"] = label
            else:
                _require_equal(
                    "reference line label visibility",
                    layer.get_int(f"{prefix}.labelshow"),
                    0,
                )
            snapshot[action.action_id] = reference_observed
        elif isinstance(action, AddCallout):
            reference = reference_lines_by_id.get(action.target)
            if reference is None:
                raise RuntimeError(
                    "Origin callout fresh readback has no effective reference-line target"
                )
            layer, expected_geometry = _callout_geometry(graph, action, reference)
            arrow_name, text_name = _callout_object_names(action.callout_id)
            arrow_state = read_scale_arrow(
                op,
                graph.name,
                _layer_index(layer),
                arrow_name,
            )
            _require_equal("callout arrow attachment", arrow_state.attach, 2)
            arrow_axes: tuple[Literal["x", "y"], ...] = ("x", "y", "x", "y")
            for name, axis_name, observed_value, expected_value in zip(
                ("x0", "y0", "x1", "y1"),
                arrow_axes,
                arrow_state[1:5],
                expected_geometry,
                strict=True,
            ):
                _require_axis_coordinate(
                    f"callout arrow {name}",
                    observed_value,
                    expected_value,
                    layer=layer,
                    axis_name=axis_name,
                )
            arrow = layer.label(arrow_name)
            if arrow is None:
                raise RuntimeError("Origin callout arrow did not survive T1 fresh reopen")
            expected_arrow_color = _color(op, action.arrow_color or "#101828")
            expected_arrow_width = action.arrow_width_pt or 1.0
            expected_arrow_head = 2 if action.arrow_head == "open" else 1
            _require_equal("callout arrow visibility", arrow.get_int("show"), 1)
            _require_equal(
                "callout arrow color",
                arrow.get_int("color"),
                expected_arrow_color,
            )
            _require_number(
                "callout arrow width",
                arrow.get_float("lineWidth"),
                expected_arrow_width,
                tolerance=0.051,
            )
            _require_equal("callout arrow begin shape", arrow_state.begin_style, 0)
            _require_equal("callout arrow end shape", arrow_state.end_style, expected_arrow_head)

            label = layer.label(text_name)
            if label is None:
                raise RuntimeError("Origin callout text did not survive T1 fresh reopen")
            plain_text, bold, italic = _text_style(label.text)
            _require_equal("callout text", plain_text, action.text)
            _require_equal("callout text visibility", label.get_int("show"), 1)
            _require_equal("callout text attachment", label.get_int("attach"), 2)
            text_axes: tuple[Literal["x", "y"], ...] = ("x", "y")
            for name, axis_name, expected_value in zip(
                ("x", "y"),
                text_axes,
                expected_geometry[:2],
                strict=True,
            ):
                _require_axis_coordinate(
                    f"callout text {name}",
                    label.get_float(name),
                    expected_value,
                    layer=layer,
                    axis_name=axis_name,
                )
            expected_font = _font(op, action.font_family)
            if expected_font is not None:
                _require_equal("callout font", label.get_int("font"), expected_font)
            expected_font_size = action.font_size_pt or PRODUCT_TYPOGRAPHY.tick_font_size_pt
            _require_number(
                "callout font size",
                label.get_float("fsize"),
                expected_font_size,
            )
            if action.font_weight is not None:
                _require_equal(
                    "callout font weight",
                    bold,
                    action.font_weight == "bold",
                )
            if action.italic is not None:
                _require_equal("callout italic", italic, action.italic)
            expected_text_color = _color(
                op,
                action.text_color or action.arrow_color or "#101828",
            )
            _require_equal(
                "callout text color",
                label.get_int("color"),
                expected_text_color,
            )
            snapshot[action.action_id] = {
                "callout_id": action.callout_id,
                "reference_line_id": action.target,
                "layer_index": _layer_index(layer),
                "arrow_name": arrow_name,
                "text_name": text_name,
                "arrow": arrow_state._asdict(),
                "arrow_color": expected_arrow_color,
                "arrow_width_pt": arrow.get_float("lineWidth"),
                "arrow_head": action.arrow_head or "filled",
                "text": plain_text,
                "text_x": label.get_float("x"),
                "text_y": label.get_float("y"),
                "font_size_pt": label.get_float("fsize"),
                "text_color": expected_text_color,
            }
    return snapshot

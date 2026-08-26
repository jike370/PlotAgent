"""Shared T1 visual language applied to editable native Origin objects."""

from __future__ import annotations

from collections.abc import Callable
from math import isclose
from pathlib import Path
from typing import Any, Literal

from plotagent.engine.backends.origin.native_visual_t1 import (
    read_axis_line_show,
    read_color_scale_anchor,
    read_color_scale_tick_format,
    read_color_scale_title,
    read_color_scale_title_show,
    set_axis_line_show,
    set_color_scale_anchor,
    set_color_scale_tick_format,
    set_color_scale_title,
)
from plotagent.engine.backends.origin.readback import axis_scale_matches
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
from plotagent.engine.visual_t1 import effective_visual_actions

_LINE_STYLE = {"solid": 1, "dash": 2, "dot": 3, "dash_dot": 4, "none": 0}
_BORDER_STYLE = {"solid": 0, "dash": 1, "dot": 2, "dash_dot": 3, "none": 0}
_BAR_COLUMN_PIDS = {203, 207, 213}
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

    effective_actions = effective_visual_actions(actions)
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
    for action in effective_actions:
        _apply_action(op, graph, document, action)
    applied_invariant = (
        None if post_apply_invariant is None else post_apply_invariant(graph)
    )
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
    if not op.lt_exec(
        f"range __PAT1P={plot_range}; get __PAT1P {option} __PAT1TEXT$;"
    ):
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


def _error_plot(op: Any, graph: Any, target: str) -> tuple[Any, int]:
    layer, _ = _layer_and_plot(graph, target)
    ordinal = _ordinal(_target_key(target))
    error_plots: list[int] = []
    for plot_index in range(1, _plot_count(op, graph, layer) + 1):
        plot_range = _plot_range(graph, layer, plot_index)
        if int(_get_plot_option(op, plot_range, "-pt")) in {231, 233}:
            error_plots.append(plot_index)
    if ordinal > len(error_plots):
        raise ValueError(
            f"Origin target error series {ordinal} is outside the native error plot count "
            f"{len(error_plots)}"
        )
    return layer, error_plots[ordinal - 1]


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


def _apply_action(op: Any, graph: Any, document: PlotDocument, action: PlotEngineAction) -> None:
    if isinstance(action, SetTitle):
        layer = _layers(graph)[0]
        title = _label(layer, "_ENGINE_TITLE", action.text or "")
        if action.text is not None:
            title.text = _replace_styled_text(title.text, action.text)
        title.set_int("show", int(bool(title.text)))
        title.set_int("attach", 1)
        title.set_float("x1", 0.5)
        title.set_float("y1", 0.012)
        _style_label(op, title, action)
    elif isinstance(action, SetAxis):
        _apply_axis(op, graph, action)
    elif isinstance(action, SetSeriesStyle):
        _apply_series(op, graph, action)
    elif isinstance(action, SetLegend):
        _apply_legend(op, graph, action)
    elif isinstance(action, SetColorMap):
        _apply_colormap(op, graph, action)
    elif isinstance(action, SetErrorStyle):
        _apply_error(op, graph, action)
    elif isinstance(action, SetDataLabels):
        _apply_data_labels(op, graph, action)
    elif isinstance(action, AddAnnotation):
        _apply_annotation(op, graph, action)
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
    for (layer_index, axis_code), visible in template_frame.items():
        if not visible:
            set_axis_line_show(op, graph.name, layer_index, axis_code, True)
        expected[(layer_index, axis_code)] = True
    return expected


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
        expected[(_layer_index(layer), _axis_native_code(action.target))] = (
            action.axis_line_visible
        )
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
        observed = bool(
            read_axis_line_show(op, graph.name, layer_index, axis_code)
        )
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
        None
        if action.tick_direction is None
        else _TICK_DIRECTION_BITS[action.tick_direction]
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
        if action.title_font_size_pt is not None:
            title.set_float("fsize", action.title_font_size_pt)
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
            layer.set_int(f"{axis_name}.label.type", formats[action.tick_format])
            layer.set_str(f"{axis_name}.label.suf", "")
        else:
            layer.set_int(f"{axis_name}.label.type", 0)
            layer.set_int(f"{axis_name}.label.numFormat", formats[action.tick_format])
            layer.set_str(
                f"{axis_name}.label.suf",
                "%" if action.tick_format == "percent" else "",
            )
    if action.tick_rotation_deg is not None:
        layer.set_float(f"{axis_name}.label.rotate", action.tick_rotation_deg)
    tick_font = _font(op, action.tick_font_family)
    if tick_font is not None:
        layer.set_int(f"{axis_name}.label.font", tick_font)
    if action.tick_font_size_pt is not None:
        layer.set_float(f"{axis_name}.label.pt", action.tick_font_size_pt)
    if action.tick_color is not None:
        layer.set_int(f"{axis_name}.label.color", _color(op, action.tick_color))
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
        layer.set_int(f"{axis_name}.color", _color(op, action.axis_line_color))
    if action.axis_line_width_pt is not None:
        layer.set_float(f"{axis_name}.thickness", action.axis_line_width_pt)
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


def _apply_series(op: Any, graph: Any, action: SetSeriesStyle) -> None:
    layer, plot_index = _layer_and_plot(graph, action.target)
    # Origin's official templates commonly group multiple plots so the first
    # plot owns an incrementing style list.  A direct ``set plotN`` command can
    # then read back the requested value while the grouped renderer still
    # paints a different incremented value.  PlotAgent exposes every semantic
    # series as an independently editable object, so break only the targeted
    # layer's presentation group before applying a public series edit.  This
    # preserves the native plots and source bindings while making the visible
    # result agree with the per-series contract.
    if _plot_count(op, graph, layer) > 1:
        _activate_layer(op, graph, layer)
        if not op.lt_exec("layer -gu;"):
            raise RuntimeError("Origin could not make series formatting independent")
    key = _target_key(action.target)
    visibility_indices = (
        range(1, _plot_count(op, graph, layer) + 1)
        if key in {"primary", "left", "right", "bars", "cumulative", "matrix", "connector"}
        else (plot_index,)
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
    plot_range = _checked_plot_range(op, graph, layer, plot_index)
    plot_ref = _bind_plot_range(op, plot_range)
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
    if action.marker_fill_color is not None:
        commands.append(f'set {plot_ref} -csf color("{action.marker_fill_color}")')
    if action.marker_stroke_color is not None:
        commands.append(f'set {plot_ref} -cse color("{action.marker_stroke_color}")')
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


def _apply_legend(op: Any, graph: Any, action: SetLegend) -> None:
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
    if action.anchor is not None:
        positions = {
            "inside": (1, 0.72, 0.06),
            "inside_top_left": (1, 0.06, 0.06),
            "inside_top_right": (1, 0.72, 0.06),
            "inside_bottom_left": (1, 0.06, 0.82),
            "inside_bottom_right": (1, 0.72, 0.82),
            "right": (1, 0.84, 0.12),
            "bottom": (1, 0.25, 0.88),
            "none": (1, 0.72, 0.06),
        }
        attach, x, y = positions[action.anchor]
        legend.set_int("attach", attach)
        legend.set_float("x1", x)
        legend.set_float("y1", y)
        if action.anchor == "none":
            legend.set_int("show", 0)
    if action.columns is not None:
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
    if action.font_size_pt is not None:
        legend.set_float("fsize", action.font_size_pt)
    if action.font_color is not None:
        legend.set_int("color", _color(op, action.font_color))
    if action.frame_visible is not None:
        legend.set_int("background", int(action.frame_visible))
    if action.frame_color is not None:
        legend.set_int("borderColor", _color(op, action.frame_color))
    if action.frame_width_pt is not None:
        legend.set_float("lineWidth", action.frame_width_pt)


def _apply_colormap(op: Any, graph: Any, action: SetColorMap) -> None:
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
    reverse = action.reverse
    if action.palette == "blue_white_red":
        reverse = not bool(reverse)
    if reverse is not None:
        commands.append(f"layer.cmap.flippal={int(reverse)}")
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


def _apply_error(op: Any, graph: Any, action: SetErrorStyle) -> None:
    layer, plot_index = _error_plot(op, graph, action.target)
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
    if action.band_fill_opacity is not None:
        commands.append(f"set {plot_ref} -paaf 1")
    if action.band_stroke_color is not None:
        commands.append(f'set {plot_ref} -pbc color("{action.band_stroke_color}")')
    if action.band_stroke_width_pt is not None:
        commands.append(f"set {plot_ref} -pbw {action.band_stroke_width_pt:.12g}")
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
    if action.band_fill_opacity is not None:
        _set_plot_property(
            op,
            graph,
            layer,
            plot_index,
            "transparency",
            (1 - action.band_fill_opacity) * 100,
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


def _verify_series(op: Any, graph: Any, action: SetSeriesStyle) -> dict[str, object]:
    layer, plot_index = _layer_and_plot(graph, action.target)
    plot_range = _checked_plot_range(op, graph, layer, plot_index)
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
            action.marker_fill_color,
            "-csf",
            float(_color(op, action.marker_fill_color)) if action.marker_fill_color else 0,
        ),
        (
            "marker_stroke_color",
            action.marker_stroke_color,
            "-cse",
            float(_color(op, action.marker_stroke_color)) if action.marker_stroke_color else 0,
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
    if action.visible is not None:
        key = _target_key(action.target)
        visibility_indices = (
            range(1, _plot_count(op, graph, layer) + 1)
            if key in {"primary", "left", "right", "bars", "cumulative", "matrix", "connector"}
            else (plot_index,)
        )
        visibility = tuple(
            int(_get_plot_property(op, graph, layer, index, "show"))
            for index in visibility_indices
        )
        expected_visibility = int(action.visible)
        if any(value != expected_visibility for value in visibility):
            raise RuntimeError("Origin series visibility did not survive T1 fresh reopen")
        observed["visible"] = visibility
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


def _verify_actions(
    op: Any,
    graph: Any,
    document: PlotDocument,
    actions: tuple[PlotEngineAction, ...],
) -> dict[str, object]:
    """Read back stable public properties for the fresh-reopen gate."""

    snapshot: dict[str, object] = {}
    for action in actions:
        if isinstance(action, SetTitle):
            title = _layers(graph)[0].label("_ENGINE_TITLE")
            if title is None:
                raise RuntimeError("Origin title did not survive T1 fresh reopen")
            title_text, _bold, _italic = _text_style(title.text)
            if action.text is not None and title_text != action.text:
                raise RuntimeError("Origin title did not survive T1 fresh reopen")
            snapshot[action.action_id] = _verify_label_style(op, title, action)
        elif isinstance(action, SetAxis):
            layer, axis_name = _axis_target(graph, action.target)
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
                    f"{axis_name}.label.rotate",
                    action.tick_rotation_deg,
                ),
                (
                    "tick_font",
                    action.tick_font_family,
                    f"{axis_name}.label.font",
                    _font(op, action.tick_font_family),
                ),
                (
                    "tick_size",
                    action.tick_font_size_pt,
                    f"{axis_name}.label.pt",
                    action.tick_font_size_pt,
                ),
                (
                    "tick_color",
                    action.tick_color,
                    f"{axis_name}.label.color",
                    _color(op, action.tick_color) if action.tick_color else None,
                ),
                (
                    "axis_color",
                    action.axis_line_color,
                    f"{axis_name}.color",
                    _color(op, action.axis_line_color) if action.axis_line_color else None,
                ),
                (
                    "axis_width",
                    action.axis_line_width_pt,
                    f"{axis_name}.thickness",
                    action.axis_line_width_pt,
                ),
            )
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
                    tick_type = layer.get_int(f"{axis_name}.label.type")
                    _require_equal("tick format type", tick_type, expected_type)
                    observed["tick_format_type"] = tick_type
                else:
                    expected_format = {
                        "auto": 0,
                        "decimal": 1,
                        "scientific": 2,
                        "percent": 1,
                    }[action.tick_format]
                    tick_format = layer.get_int(f"{axis_name}.label.numFormat")
                    _require_equal("tick numeric format", tick_format, expected_format)
                    suffix = layer.get_str(f"{axis_name}.label.suf")
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
                        (
                            _LINE_STYLE[action.grid_line_style]
                            if action.grid_line_style
                            else None
                        ),
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
            snapshot[action.action_id] = _verify_series(op, graph, action)
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
                    columns = _legend_column_count(legend.get_int("ncols"))
                    _require_equal("legend columns", columns, action.columns)
                    observed["columns"] = columns
                if action.title is not None:
                    legend_text, _bold, _italic = _text_style(legend.text)
                    title = legend_text.splitlines()[0] if legend_text else ""
                    _require_equal("legend title", title, action.title)
                    observed["title"] = title
                if action.anchor is not None:
                    expected_anchor = {
                        "inside": (1, 0.72, 0.06),
                        "inside_top_left": (1, 0.06, 0.06),
                        "inside_top_right": (1, 0.72, 0.06),
                        "inside_bottom_left": (1, 0.06, 0.82),
                        "inside_bottom_right": (1, 0.72, 0.82),
                        "right": (1, 0.84, 0.12),
                        "bottom": (1, 0.25, 0.88),
                        "none": (1, 0.72, 0.06),
                    }[action.anchor]
                    attach = legend.get_int("attach")
                    x = legend.get_float("x1")
                    y = legend.get_float("y1")
                    _require_equal("legend attachment", attach, expected_anchor[0])
                    _require_number("legend x", x, expected_anchor[1], tolerance=1e-3)
                    _require_number("legend y", y, expected_anchor[2], tolerance=1e-3)
                    observed["anchor"] = (attach, x, y)
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
                        int(action.frame_visible)
                        if action.frame_visible is not None
                        else None,
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
                expected_reverse = int(
                    not action.reverse
                    if action.palette == "blue_white_red"
                    else action.reverse
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
                    "decimal": 0,
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
                observed_colormap["colorbar_tick_format"] = tick_format._asdict()
            snapshot[action.action_id] = observed_colormap
        elif isinstance(action, SetErrorStyle):
            layer, plot_index = _error_plot(op, graph, action.target)
            plot_range = _checked_plot_range(op, graph, layer, plot_index)
            observed = {}
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
                value = 1 - _get_plot_property(op, graph, layer, plot_index, "transparency") / 100
                _require_number("error opacity", value, action.bar_opacity)
                observed["bar_opacity"] = value
            if action.band_fill_opacity is not None:
                fill_only = _get_plot_option(op, plot_range, "-paaf")
                _require_number("error band fill-only transparency", fill_only, 1)
                value = 1 - _get_plot_property(op, graph, layer, plot_index, "transparency") / 100
                _require_number("error band opacity", value, action.band_fill_opacity)
                observed["band_fill_opacity"] = value
            snapshot[action.action_id] = observed
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
                suffix = (
                    f"{action.suffix or ''}"
                    f"{'%' if action.value_format == 'percent' else ''}"
                )
                expected_label_display = (
                    f"{action.prefix or ''}$(Y,{format_code}){suffix}"
                )
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
    return snapshot

"""Reviewed Origin C bridge for point-valued shared T1 visual properties."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal, NamedTuple

_SOURCE = Path(__file__).with_name("native_visual_t1.c").resolve()
_BRIDGE_VERSION = 2026090122


def _safe_graph_name(value: str) -> str:
    if not value or not value.replace("_", "").isalnum():
        raise RuntimeError(f"unsafe Origin T1 visual graph name: {value!r}")
    return value


def _safe_object_name(value: str) -> str:
    if (
        not value
        or len(value) > 31
        or not (value[0].isalpha() or value[0] == "_")
        or not value.replace("_", "").isalnum()
    ):
        raise RuntimeError(f"unsafe Origin T1 visual object name: {value!r}")
    return value


def ensure_native_visual_bridge(op: Any) -> None:
    if not _SOURCE.is_file():
        raise RuntimeError(f"Origin T1 visual bridge is missing: {_SOURCE}")
    if not op.set_lt_str("__PAT1SOURCE", str(_SOURCE)):
        raise RuntimeError("Origin could not stage the T1 visual bridge path")
    command = (
        f"if(__PAT1BRIDGEVERSION!={_BRIDGE_VERSION}"
        " || exist(plotagent_set_scale_arrow,20)==0"
        " || exist(plotagent_set_k22_contour_lines_visible,20)==0"
        " || exist(plotagent_read_k22_contour_lines,20)==0) {"
        "__PAT1LOAD=run.LoadOC(__PAT1SOURCE$,16);"
        f"if(__PAT1LOAD==0) __PAT1BRIDGEVERSION={_BRIDGE_VERSION};"
        "} else __PAT1LOAD=0;"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke run.LoadOC for the T1 visual bridge")
    status = int(op.lt_float("__PAT1LOAD"))
    if status != 0:
        raise RuntimeError(f"Origin could not compile the T1 visual bridge: status={status}")


def set_color_scale_title(
    op: Any,
    graph_name: str,
    layer_index: int,
    title: str,
) -> None:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    if not op.set_lt_str("__PAT1CSTITLE", title):
        raise RuntimeError("Origin could not stage the color scale title")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_color_scale_title("
        f'"{graph}",{layer_index},__PAT1CSTITLE$'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native color scale-title editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native color scale-title editing failed: status={status}")


def _read_color_scale_title_state(op: Any, graph_name: str, layer_index: int) -> tuple[str, int]:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_color_scale_title("{graph}",{layer_index});}};'
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native color scale-title readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native color scale-title readback failed: status={status}")
    value = float(op.lt_float("__PAT1CSTITLESHOW"))
    if not math.isfinite(value):
        raise RuntimeError("Origin native color scale-title visibility is missing")
    return str(op.get_lt_str("__PAT1CSTITLEOBS")), int(value)


def read_color_scale_title(op: Any, graph_name: str, layer_index: int) -> str:
    return _read_color_scale_title_state(op, graph_name, layer_index)[0]


def read_color_scale_title_show(op: Any, graph_name: str, layer_index: int) -> int:
    return _read_color_scale_title_state(op, graph_name, layer_index)[1]


class ColorScaleAnchorState(NamedTuple):
    arrangement: int
    attach: int
    left: float
    top: float
    width: float
    height: float
    layer_left: float
    layer_top: float
    layer_right: float
    layer_bottom: float


class ColorScaleTickFormatState(NamedTuple):
    automatic: int
    label_type: int
    numeric_format: int
    custom_format: str


class ColorScaleTypographyState(NamedTuple):
    title_font_size_pt: float
    tick_font_size_pt: float


class K22ContourLineState(NamedTuple):
    interval_count: int
    visible_interval_count: int
    above_visible: int


class K09AxisLabelState(NamedTuple):
    table_enabled: int
    table_design: int
    subgroup_row_hidden: int


class K07ErrorBandStyleState(NamedTuple):
    fill_transparencies: tuple[float, float]
    line_colors: tuple[int, int]
    line_widths: tuple[float, float]


class K14ViolinStyleState(NamedTuple):
    fill_color: int
    fill_transparency: float
    fill_only: int
    follow_line_transparency: int
    outline_color: int
    outline_width: float
    outline_style: int


class ScaleArrowState(NamedTuple):
    attach: int
    x0: float
    y0: float
    x1: float
    y1: float
    begin_style: int
    end_style: int


class X40GroupStyleState(NamedTuple):
    group_count: int
    subgroup_size: int
    marker_shapes: tuple[int, int]
    marker_sizes: tuple[float, float]
    marker_interiors: tuple[int, int]
    marker_edge_colors: tuple[int, int]
    marker_fill_colors: tuple[int, int]
    connector_visible: bool
    connector_style: int
    connector_width: float
    connector_color: int
    connector_by_subgroup: int


def remove_graph_object(
    op: Any,
    graph_name: str,
    layer_index: int,
    object_name: str,
) -> None:
    """Remove one renderer-owned native object if it exists."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    name = _safe_object_name(object_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    if not op.set_lt_str("__PAT1OBJ", name):
        raise RuntimeError("Origin could not stage the graph-object name")
    command = (
        "run -oc {__PAT1STATUS=plotagent_remove_graph_object("
        f'"{graph}",{layer_index},__PAT1OBJ$'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native graph-object removal")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native graph-object removal failed: status={status}")


def set_scale_arrow(
    op: Any,
    graph_name: str,
    layer_index: int,
    arrow_name: str,
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> None:
    """Create an arrow whose two vertices persist as native axis values."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    name = _safe_object_name(arrow_name)
    coordinates = (x0, y0, x1, y1)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("Origin scale-arrow coordinates must be finite")
    if not op.set_lt_str("__PAT1ARROW", name):
        raise RuntimeError("Origin could not stage the scale-arrow name")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_scale_arrow("
        f'"{graph}",{layer_index},__PAT1ARROW$,'
        f"{x0:.17g},{y0:.17g},{x1:.17g},{y1:.17g}"
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native scale-arrow editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native scale-arrow editing failed: status={status}")


def read_scale_arrow(
    op: Any,
    graph_name: str,
    layer_index: int,
    arrow_name: str,
) -> ScaleArrowState:
    """Read persisted native vertices after a project round trip."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    name = _safe_object_name(arrow_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    if not op.set_lt_str("__PAT1ARROW", name):
        raise RuntimeError("Origin could not stage the scale-arrow name")
    command = (
        "run -oc {__PAT1STATUS=plotagent_read_scale_arrow("
        f'"{graph}",{layer_index},__PAT1ARROW$'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native scale-arrow readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native scale-arrow readback failed: status={status}")
    values = tuple(
        float(op.lt_float(name))
        for name in (
            "__PAT1CALLATTACH",
            "__PAT1CALLX0",
            "__PAT1CALLY0",
            "__PAT1CALLX1",
            "__PAT1CALLY1",
            "__PAT1CALLBEGIN",
            "__PAT1CALLEND",
        )
    )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Origin native scale-arrow geometry is missing")
    return ScaleArrowState(
        int(values[0]),
        values[1],
        values[2],
        values[3],
        values[4],
        int(values[5]),
        int(values[6]),
    )


def set_scale_arrow_head(
    op: Any,
    graph_name: str,
    layer_index: int,
    arrow_name: str,
    end_style: int,
) -> None:
    """Apply the arrow head after LabTalk line-style edits."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    name = _safe_object_name(arrow_name)
    if layer_index < 1 or end_style not in {1, 2}:
        raise ValueError("Origin scale-arrow head coordinates are invalid")
    if not op.set_lt_str("__PAT1ARROW", name):
        raise RuntimeError("Origin could not stage the scale-arrow name")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_scale_arrow_head("
        f'"{graph}",{layer_index},__PAT1ARROW$,{end_style}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native scale-arrow head editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native scale-arrow head editing failed: status={status}")


def set_k07_error_band_fill_transparency(
    op: Any,
    graph_name: str,
    layer_index: int,
    *,
    fill_transparency: float,
) -> None:
    """Set K07's visible band fill transparency through native Pattern format."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    if not (math.isfinite(fill_transparency) and 0 <= fill_transparency <= 100):
        raise ValueError("Origin K07 fill transparency must be between 0 and 100")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_k07_error_band_fill_transparency("
        f'"{graph}",{layer_index},'
        f"{fill_transparency:.17g}"
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native K07 error-band editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native K07 error-band editing failed: status={status}")


def read_k07_error_band_style(
    op: Any,
    graph_name: str,
    layer_index: int,
) -> K07ErrorBandStyleState:
    """Read the two native Y-error band styles after a project round trip."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_k07_error_band_style("{graph}",{layer_index});}};'
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native K07 error-band readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native K07 error-band readback failed: status={status}")
    values = tuple(
        float(op.lt_float(name))
        for name in (
            "__PAT1K07FILLTRANS1",
            "__PAT1K07FILLTRANS2",
            "__PAT1K07LINECOLOR1",
            "__PAT1K07LINECOLOR2",
            "__PAT1K07LINEWIDTH1",
            "__PAT1K07LINEWIDTH2",
        )
    )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Origin native K07 error-band style is missing")
    return K07ErrorBandStyleState(
        fill_transparencies=(values[0], values[1]),
        line_colors=(int(values[2]), int(values[3])),
        line_widths=(values[4], values[5]),
    )


def set_k14_violin_style(
    op: Any,
    graph_name: str,
    layer_index: int,
    plot_index: int,
    *,
    fill_color: int,
    fill_transparency: float,
    outline_color: int,
    outline_width: float,
    outline_style: int,
) -> None:
    """Set the visible PID-206 violin body and outline through native format."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or plot_index < 1:
        raise ValueError("Origin K14 visual indexes are one-based")
    if not (math.isfinite(fill_transparency) and 0 <= fill_transparency <= 100):
        raise ValueError("Origin K14 fill transparency must be between 0 and 100")
    if not (math.isfinite(outline_width) and outline_width >= 0):
        raise ValueError("Origin K14 outline width must be non-negative")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_k14_violin_style("
        f'"{graph}",{layer_index},{plot_index},{fill_color},'
        f"{fill_transparency:.17g},{outline_color},{outline_width:.17g},{outline_style}"
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native K14 violin editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native K14 violin editing failed: status={status}")


def read_k14_violin_style(
    op: Any,
    graph_name: str,
    layer_index: int,
    plot_index: int,
) -> K14ViolinStyleState:
    """Read the visible PID-206 violin body and outline after round trip."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or plot_index < 1:
        raise ValueError("Origin K14 visual indexes are one-based")
    command = (
        "run -oc {__PAT1STATUS=plotagent_read_k14_violin_style("
        f'"{graph}",{layer_index},{plot_index}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native K14 violin readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native K14 violin readback failed: status={status}")
    values = tuple(
        float(op.lt_float(name))
        for name in (
            "__PAT1K14FILLCOLOR",
            "__PAT1K14FILLTRANS",
            "__PAT1K14FILLONLY",
            "__PAT1K14FOLLOWLINE",
            "__PAT1K14LINECOLOR",
            "__PAT1K14LINEWIDTH",
            "__PAT1K14LINESTYLE",
        )
    )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Origin native K14 violin style is missing")
    return K14ViolinStyleState(
        fill_color=int(values[0]),
        fill_transparency=values[1],
        fill_only=int(values[2]),
        follow_line_transparency=int(values[3]),
        outline_color=int(values[4]),
        outline_width=values[5],
        outline_style=int(values[6]),
    )


def set_x09_group_fill_color(
    op: Any,
    graph_name: str,
    layer_index: int,
    fill_color: int,
) -> None:
    """Set X09's visible fill through the dependent FLOATCOL group list."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_x09_group_fill_color("
        f'"{graph}",{layer_index},{fill_color}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native X09 group-fill editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native X09 group-fill editing failed: status={status}")


def set_x09_group_fill_colors(
    op: Any,
    graph_name: str,
    layer_index: int,
    fill_colors: tuple[int, ...],
) -> None:
    """Set the two or three native FLOATCOL group increment colors."""

    if len(fill_colors) not in {2, 3}:
        raise ValueError("Origin X09 requires two or three group fill colors")
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    staged = (*fill_colors, fill_colors[-1])[:3]
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_x09_group_fill_colors("
        f'"{graph}",{layer_index},{staged[0]},{staged[1]},{staged[2]}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native X09 group-fill defaults")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native X09 group-fill defaults failed: status={status}")


def read_x09_group_fill_colors(
    op: Any,
    graph_name: str,
    layer_index: int,
) -> tuple[int, ...]:
    """Read the persisted FLOATCOL group fill increment list."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_x09_group_fill_colors("{graph}",{layer_index});}};'
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native X09 group-fill readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native X09 group-fill readback failed: status={status}")
    count = int(op.lt_float("__PAT1X09GROUPCOUNT"))
    try:
        colors = tuple(int(value) for value in op.get_lt_str("__PAT1X09GROUPCOLORS").split())
    except ValueError as exc:
        raise RuntimeError("Origin X09 group fill-color list is invalid") from exc
    if count < 2 or len(colors) != count:
        raise RuntimeError("Origin X09 group fill-color list is incomplete")
    return colors


def set_x40_group_style(
    op: Any,
    graph_name: str,
    layer_index: int,
    *,
    marker_shapes: tuple[int, int],
    marker_sizes: tuple[float, float],
    marker_interiors: tuple[int, int],
    marker_edge_colors: tuple[int, int],
    marker_fill_colors: tuple[int, int],
    connector_visible: bool,
    connector_style: int,
    connector_width: float,
    connector_color: int,
) -> None:
    """Style X40 through its dependent native group without ungrouping it."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    if not all(math.isfinite(value) and value > 0 for value in marker_sizes):
        raise ValueError("Origin X40 marker sizes must be finite and positive")
    if not math.isfinite(connector_width) or connector_width <= 0:
        raise ValueError("Origin X40 connector width must be finite and positive")
    values = (
        marker_shapes[0],
        marker_shapes[1],
        marker_sizes[0],
        marker_sizes[1],
        marker_interiors[0],
        marker_interiors[1],
        marker_edge_colors[0],
        marker_edge_colors[1],
        marker_fill_colors[0],
        marker_fill_colors[1],
        int(connector_visible),
        connector_style,
        connector_width,
        connector_color,
    )
    encoded = ",".join(
        f"{value:.17g}" if isinstance(value, float) else str(value) for value in values
    )
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_x40_group_style("
        f'"{graph}",{layer_index},{encoded}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native X40 group-style editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native X40 group-style editing failed: status={status}")


def _x40_marker_sizes(text: str, base_size: float) -> tuple[float, float]:
    value = text.strip()
    if not value or value.casefold() == "<auto>":
        return (base_size, base_size)
    try:
        sizes = tuple(float(token) for token in value.replace(",", " ").split())
    except ValueError as exc:
        raise RuntimeError(f"Origin X40 symbol-size increment list is invalid: {text!r}") from exc
    if len(sizes) < 2 or not all(math.isfinite(size) and size > 0 for size in sizes[:2]):
        raise RuntimeError(f"Origin X40 symbol-size increment list is invalid: {text!r}")
    return (sizes[0], sizes[1])


def read_x40_group_style(
    op: Any,
    graph_name: str,
    layer_index: int,
) -> X40GroupStyleState:
    """Read the persisted group lists and true Connect Data Points properties."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = f'run -oc {{__PAT1STATUS=plotagent_read_x40_group_style("{graph}",{layer_index});}};'
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native X40 group-style readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native X40 group-style readback failed: status={status}")

    numeric = {
        name: float(op.lt_float(variable))
        for name, variable in (
            ("group_count", "__PAT1X40GROUPCOUNT"),
            ("subgroup_size", "__PAT1X40SUBGROUPSIZE"),
            ("stretch_color", "__PAT1X40STRETCHCOLOR"),
            ("stretch_shape", "__PAT1X40STRETCHSHAPE"),
            ("stretch_size", "__PAT1X40STRETCHSIZE"),
            ("stretch_interior", "__PAT1X40STRETCHINTERIOR"),
            ("base_shape", "__PAT1X40BASESHAPE"),
            ("base_size", "__PAT1X40BASESIZE"),
            ("base_interior", "__PAT1X40BASEINTERIOR"),
            ("base_edge", "__PAT1X40BASEEDGE"),
            ("base_fill", "__PAT1X40BASEFILL"),
            ("shape_1", "__PAT1X40SHAPE1"),
            ("shape_2", "__PAT1X40SHAPE2"),
            ("interior_1", "__PAT1X40INTERIOR1"),
            ("interior_2", "__PAT1X40INTERIOR2"),
            ("edge_1", "__PAT1X40EDGE1"),
            ("edge_2", "__PAT1X40EDGE2"),
            ("fill_1", "__PAT1X40FILL1"),
            ("fill_2", "__PAT1X40FILL2"),
            ("connector_visible", "__PAT1X40CONNECTSHOW"),
            ("connector_style", "__PAT1X40CONNECTSTYLE"),
            ("connector_width", "__PAT1X40CONNECTWIDTH"),
            ("connector_color", "__PAT1X40CONNECTCOLOR"),
            ("connector_by_subgroup", "__PAT1X40CONNECTSUBGROUP"),
        )
    }
    if not all(math.isfinite(value) for value in numeric.values()):
        raise RuntimeError("Origin native X40 group-style readback is incomplete")

    shapes = (
        (int(numeric["shape_1"]), int(numeric["shape_2"]))
        if int(numeric["stretch_shape"])
        else (int(numeric["base_shape"]),) * 2
    )
    sizes = (
        _x40_marker_sizes(str(op.get_lt_str("__PAT1X40SIZES")), numeric["base_size"])
        if int(numeric["stretch_size"])
        else (numeric["base_size"],) * 2
    )
    interiors = (
        (int(numeric["interior_1"]), int(numeric["interior_2"]))
        if int(numeric["stretch_interior"])
        else (int(numeric["base_interior"]),) * 2
    )
    edge_colors = (
        (int(numeric["edge_1"]), int(numeric["edge_2"]))
        if int(numeric["stretch_color"])
        else (int(numeric["base_edge"]),) * 2
    )
    fill_colors = (
        (int(numeric["fill_1"]), int(numeric["fill_2"]))
        if int(numeric["stretch_color"])
        else (int(numeric["base_fill"]),) * 2
    )
    return X40GroupStyleState(
        group_count=int(numeric["group_count"]),
        subgroup_size=int(numeric["subgroup_size"]),
        marker_shapes=shapes,
        marker_sizes=sizes,
        marker_interiors=interiors,
        marker_edge_colors=edge_colors,
        marker_fill_colors=fill_colors,
        connector_visible=bool(int(numeric["connector_visible"])),
        connector_style=int(numeric["connector_style"]),
        connector_width=numeric["connector_width"],
        connector_color=int(numeric["connector_color"]),
        connector_by_subgroup=int(numeric["connector_by_subgroup"]),
    )


def set_axis_tick_font_size(
    op: Any,
    graph_name: str,
    layer_index: int,
    axis_code: int,
    font_size_pt: float,
) -> None:
    """Set axis tick-label size through Origin 2024 SR1's format tree."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or axis_code not in {0, 1, 2, 3}:
        raise ValueError("Origin T1 visual axis coordinates are invalid")
    if not math.isfinite(font_size_pt) or font_size_pt <= 0:
        raise ValueError("Origin T1 visual tick-label size must be positive and finite")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_axis_tick_font_size("
        f'"{graph}",{layer_index},{axis_code},{font_size_pt:.12g}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native axis tick-font editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native axis tick-font editing failed: status={status}")


def read_axis_tick_font_size(
    op: Any,
    graph_name: str,
    layer_index: int,
    axis_code: int,
) -> float:
    """Read the persisted axis tick-label size from Origin's format tree."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or axis_code not in {0, 1, 2, 3}:
        raise ValueError("Origin T1 visual axis coordinates are invalid")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_axis_tick_font_size("{graph}",'
        f"{layer_index},{axis_code});}};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native axis tick-font readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native axis tick-font readback failed: status={status}")
    value = float(op.lt_float("__PAT1AXISTICKSIZE"))
    if not math.isfinite(value):
        raise RuntimeError("Origin native axis tick-font size is missing")
    return value


def set_color_scale_anchor(
    op: Any,
    graph_name: str,
    layer_index: int,
    anchor: Literal["right", "bottom"],
) -> None:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    if anchor not in {"right", "bottom"}:
        raise ValueError(f"unsupported Origin color scale anchor: {anchor!r}")
    anchor_code = 0 if anchor == "right" else 1
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_color_scale_anchor("
        f'"{graph}",{layer_index},{anchor_code}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native color scale-anchor editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native color scale-anchor editing failed: status={status}")


def read_color_scale_anchor(
    op: Any,
    graph_name: str,
    layer_index: int,
) -> ColorScaleAnchorState:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_color_scale_anchor("{graph}",{layer_index});}};'
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native color scale-anchor readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native color scale-anchor readback failed: status={status}")
    names = (
        "__PAT1CSARRANGEMENT",
        "__PAT1CSATTACH",
        "__PAT1CSLEFT",
        "__PAT1CSTOP",
        "__PAT1CSWIDTH",
        "__PAT1CSHEIGHT",
        "__PAT1LAYERLEFT",
        "__PAT1LAYERTOP",
        "__PAT1LAYERRIGHT",
        "__PAT1LAYERBOTTOM",
    )
    values = tuple(float(op.lt_float(name)) for name in names)
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Origin native color scale-anchor geometry is missing")
    return ColorScaleAnchorState(int(values[0]), int(values[1]), *values[2:])


def set_color_scale_tick_format(
    op: Any,
    graph_name: str,
    layer_index: int,
    tick_format: Literal["auto", "decimal", "scientific", "percent"],
) -> None:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    codes = {"auto": 0, "decimal": 1, "scientific": 2, "percent": 3}
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_color_scale_tick_format("
        f'"{graph}",{layer_index},{codes[tick_format]}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native color scale tick-format editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native color scale tick-format editing failed: status={status}")


def read_color_scale_tick_format(
    op: Any,
    graph_name: str,
    layer_index: int,
) -> ColorScaleTickFormatState:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_color_scale_tick_format("{graph}",'
        f"{layer_index});}};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native color scale tick-format readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(
            f"Origin native color scale tick-format readback failed: status={status}"
        )
    values = tuple(
        float(op.lt_float(name))
        for name in ("__PAT1CSTICKAUTO", "__PAT1CSTICKTYPE", "__PAT1CSTICKNUM")
    )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Origin native color scale tick-format state is missing")
    return ColorScaleTickFormatState(
        automatic=int(values[0]),
        label_type=int(values[1]),
        numeric_format=int(values[2]),
        custom_format=str(op.get_lt_str("__PAT1CSTICKCUSTOM")),
    )


def set_color_scale_typography(
    op: Any,
    graph_name: str,
    layer_index: int,
    *,
    title_font_size_pt: float,
    tick_font_size_pt: float,
) -> None:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or title_font_size_pt <= 0 or tick_font_size_pt <= 0:
        raise ValueError("Origin color scale typography values are invalid")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_color_scale_typography("
        f'"{graph}",{layer_index},{title_font_size_pt:.12g},{tick_font_size_pt:.12g}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native color scale typography editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native color scale typography editing failed: status={status}")


def read_color_scale_typography(
    op: Any,
    graph_name: str,
    layer_index: int,
) -> ColorScaleTypographyState:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_color_scale_typography("{graph}",'
        f"{layer_index});}};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native color scale typography readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native color scale typography readback failed: status={status}")
    values = tuple(
        float(op.lt_float(name))
        for name in ("__PAT1CSTITLEFONTSIZE", "__PAT1CSTICKFONTSIZE")
    )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Origin native color scale typography state is missing")
    return ColorScaleTypographyState(*values)


def set_k22_contour_lines_visible(
    op: Any,
    graph_name: str,
    layer_index: int,
    plot_index: int,
    visible: bool,
) -> None:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or plot_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_k22_contour_lines_visible("
        f'"{graph}",{layer_index},{plot_index},{int(visible)}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native K22 contour-line editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native K22 contour-line editing failed: status={status}")


def read_k22_contour_lines(
    op: Any,
    graph_name: str,
    layer_index: int,
    plot_index: int,
) -> K22ContourLineState:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or plot_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_k22_contour_lines("{graph}",'
        f"{layer_index},{plot_index});}};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native K22 contour-line readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native K22 contour-line readback failed: status={status}")
    values = tuple(
        float(op.lt_float(name))
        for name in ("__PAT1K22LINECOUNT", "__PAT1K22LINESHOW", "__PAT1K22ABOVELINE")
    )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Origin native K22 contour-line state is missing")
    return K22ContourLineState(*(int(value) for value in values))


def configure_k09_axis_labels(op: Any, graph_name: str, layer_index: int) -> None:
    """Keep one category label per group without Origin's redundant table row."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_configure_k09_axis_labels("{graph}",{layer_index});}};'
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native K09 axis-label formatting")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native K09 axis-label formatting failed: status={status}")


def read_k09_axis_labels(op: Any, graph_name: str, layer_index: int) -> K09AxisLabelState:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = f'run -oc {{__PAT1STATUS=plotagent_read_k09_axis_labels("{graph}",{layer_index});}};'
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native K09 axis-label readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native K09 axis-label readback failed: status={status}")
    values = tuple(
        float(op.lt_float(name))
        for name in (
            "__PAT1K09ISTABLE",
            "__PAT1K09TABLEDESIGN",
            "__PAT1K09LEVEL1HIDDEN",
        )
    )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("Origin native K09 axis-label state is missing")
    return K09AxisLabelState(*(int(value) for value in values))


def set_axis_line_show(
    op: Any,
    graph_name: str,
    layer_index: int,
    axis_code: int,
    visible: bool,
) -> None:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or axis_code not in {0, 1, 2, 3}:
        raise ValueError("Origin T1 visual axis coordinates are invalid")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_axis_line_show("
        f'"{graph}",{layer_index},{axis_code},{int(visible)}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native axis-line editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native axis-line editing failed: status={status}")


def read_axis_line_show(
    op: Any,
    graph_name: str,
    layer_index: int,
    axis_code: int,
) -> int:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or axis_code not in {0, 1, 2, 3}:
        raise ValueError("Origin T1 visual axis coordinates are invalid")
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_axis_line_show("{graph}",'
        f"{layer_index},{axis_code});}};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native axis-line readback")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native axis-line readback failed: status={status}")
    value = float(op.lt_float("__PAT1AXISSHOW"))
    if not math.isfinite(value):
        raise RuntimeError("Origin native axis-line visibility is missing")
    return int(value)

"""Reviewed Origin C bridge for point-valued shared T1 visual properties."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal, NamedTuple

_SOURCE = Path(__file__).with_name("native_visual_t1.c").resolve()
_BRIDGE_VERSION = 2026083004


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
        " || exist(plotagent_set_scale_arrow,20)==0) {"
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


class K09AxisLabelState(NamedTuple):
    table_enabled: int
    table_design: int
    subgroup_row_hidden: int


class ScaleArrowState(NamedTuple):
    attach: int
    x0: float
    y0: float
    x1: float
    y1: float
    begin_style: int
    end_style: int


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
        f'run -oc {{__PAT1STATUS=plotagent_read_color_scale_anchor("{graph}",'
        f"{layer_index});}};"
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
        raise RuntimeError(
            f"Origin native color scale tick-format editing failed: status={status}"
        )


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


def configure_k09_axis_labels(op: Any, graph_name: str, layer_index: int) -> None:
    """Keep one category label per group without Origin's redundant table row."""

    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    command = (
        "run -oc {__PAT1STATUS=plotagent_configure_k09_axis_labels("
        f'"{graph}",{layer_index}'
        ");};"
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
    command = (
        f'run -oc {{__PAT1STATUS=plotagent_read_k09_axis_labels("{graph}",'
        f"{layer_index});}};"
    )
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

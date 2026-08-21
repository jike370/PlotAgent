"""Reviewed Origin C bridge for point-valued shared T1 visual properties."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal, NamedTuple

_SOURCE = Path(__file__).with_name("native_visual_t1.c").resolve()
_BRIDGE_VERSION = 2026082201


def _safe_graph_name(value: str) -> str:
    if not value or not value.replace("_", "").isalnum():
        raise RuntimeError(f"unsafe Origin T1 visual graph name: {value!r}")
    return value


def ensure_native_visual_bridge(op: Any) -> None:
    if not _SOURCE.is_file():
        raise RuntimeError(f"Origin T1 visual bridge is missing: {_SOURCE}")
    if not op.set_lt_str("__PAT1SOURCE", str(_SOURCE)):
        raise RuntimeError("Origin could not stage the T1 visual bridge path")
    command = (
        f"if(__PAT1BRIDGEVERSION!={_BRIDGE_VERSION}"
        " || exist(plotagent_set_color_scale_tick_format,20)==0) {"
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

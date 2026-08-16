"""Reviewed Origin C bridge for point-valued shared T1 visual properties."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

SYMBOL_EDGE_WIDTH = 0x09B3

_SOURCE = Path(__file__).with_name("native_visual_t1.c").resolve()


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
        "if(exist(plotagent_set_symbol_edge_width,20)==0) "
        "__PAT1LOAD=run.LoadOC(__PAT1SOURCE$,16); else __PAT1LOAD=0;"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke run.LoadOC for the T1 visual bridge")
    status = int(op.lt_float("__PAT1LOAD"))
    if status != 0:
        raise RuntimeError(f"Origin could not compile the T1 visual bridge: status={status}")


def set_symbol_edge_width(
    op: Any,
    graph_name: str,
    layer_index: int,
    plot_index: int,
    width_points: float,
) -> None:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    if layer_index < 1 or plot_index < 1:
        raise ValueError("Origin T1 visual indexes are one-based")
    if not math.isfinite(width_points) or width_points < 0:
        raise ValueError("Origin symbol edge width must be finite and non-negative")
    command = (
        "run -oc {__PAT1STATUS=plotagent_set_symbol_edge_width("
        f'"{graph}",{layer_index},{plot_index},{width_points:.17g}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native symbol edge-width editing")
    status = int(op.lt_float("__PAT1STATUS"))
    if status != 0:
        raise RuntimeError(f"Origin native symbol edge-width editing failed: status={status}")


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


def read_native_visual_value(
    op: Any,
    graph_name: str,
    layer_index: int,
    plot_index: int,
    theme_id: int,
    *,
    numeric_type: Literal["int", "double"],
) -> int | float:
    ensure_native_visual_bridge(op)
    graph = _safe_graph_name(graph_name)
    kind = 0 if numeric_type == "int" else 1
    command = (
        "run -oc {__PAT1VALUE=plotagent_visual_value("
        f'"{graph}",{layer_index},{plot_index},{theme_id},{kind}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native T1 visual readback")
    value = float(op.lt_float("__PAT1VALUE"))
    if not math.isfinite(value):
        raise RuntimeError(
            f"Origin native T1 visual readback returned a missing value: theme_id=0x{theme_id:04X}"
        )
    return int(value) if numeric_type == "int" else value

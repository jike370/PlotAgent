"""Reviewed Origin C bridge for native PID 206/219 distribution formats."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

# Origin 2024 ``OriginC/OriginLab/okThemeID.h``.  Keep these numeric IDs in
# Python only for mechanical readback; the Origin C bridge compiles against
# the installed symbolic constants when applying formats.
BOX_TYPE = 0x030C
BOX_RANGE = 0x030D
WHISKER_RANGE = 0x030E
WHISKER_COEFF = 0x0312
HAS_OUTLIERS = 0x056A
DIST_CURVE_TYPE = 0x0937
DIST_CURVE_SCALE = 0x0938
DIST_SCALE_TYPE = 0x0939
DIST_BANDWIDTH = 0x093E
DIST_EXTEND = 0x093F
DIST_BANDWIDTH_FACTOR = 0x0950
DATA_HEIGHT_TYPE = 0x09A8

_SOURCE = Path(__file__).with_name("native_distribution.c").resolve()


def _safe_graph_name(value: str) -> str:
    if not value or not value.replace("_", "").isalnum():
        raise RuntimeError(f"unsafe Origin distribution graph name: {value!r}")
    return value


def ensure_native_distribution_bridge(op: Any) -> None:
    """Compile the reviewed bridge once in the current Origin workspace."""

    if not _SOURCE.is_file():
        raise RuntimeError(f"Origin distribution bridge is missing: {_SOURCE}")
    if not op.set_lt_str("__PADISTSOURCE", str(_SOURCE)):
        raise RuntimeError("Origin could not stage the distribution bridge path")
    command = (
        "if(exist(plotagent_configure_distribution,20)==0) "
        "__PADISTLOAD=run.LoadOC(__PADISTSOURCE$,16); "
        "else __PADISTLOAD=0;"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke run.LoadOC for the distribution bridge")
    status = int(op.lt_float("__PADISTLOAD"))
    if status != 0:
        raise RuntimeError(f"Origin could not compile the distribution bridge: status={status}")


def configure_native_distribution(
    op: Any,
    graph_name: str,
    plot_index: int,
    profile_id: Literal[13, 14, 15],
    *,
    bandwidth: float = 0.0,
) -> None:
    ensure_native_distribution_bridge(op)
    graph = _safe_graph_name(graph_name)
    if plot_index < 1:
        raise ValueError("Origin distribution plot indexes are one-based")
    if profile_id == 14 and (not math.isfinite(bandwidth) or bandwidth <= 0):
        raise ValueError("Origin K14 custom bandwidth must be positive and finite")
    command = (
        "run -oc {__PADISTSTATUS=plotagent_configure_distribution("
        f'"{graph}",{plot_index},{profile_id},{bandwidth:.17g}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke the native distribution formatter")
    status = int(op.lt_float("__PADISTSTATUS"))
    if status != 0:
        raise RuntimeError(
            "Origin native distribution formatter failed: "
            f"profile=K{profile_id}, plot={plot_index}, status={status}"
        )


def set_native_distribution_outliers(
    op: Any,
    graph_name: str,
    plot_index: int,
    *,
    visible: bool,
) -> None:
    """Toggle dedicated outlier symbols when all raw observations are visible."""

    ensure_native_distribution_bridge(op)
    graph = _safe_graph_name(graph_name)
    if plot_index < 1:
        raise ValueError("Origin distribution plot indexes are one-based")
    command = (
        "run -oc {__PADISTSTATUS=plotagent_set_distribution_outliers("
        f'"{graph}",{plot_index},{int(visible)}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke the native outlier formatter")
    status = int(op.lt_float("__PADISTSTATUS"))
    if status != 0:
        raise RuntimeError(
            "Origin native outlier formatter failed: "
            f"plot={plot_index}, visible={visible}, status={status}"
        )


def read_native_distribution_value(
    op: Any,
    graph_name: str,
    plot_index: int,
    theme_id: int,
    *,
    numeric_type: Literal["int", "double"],
) -> int | float:
    ensure_native_distribution_bridge(op)
    graph = _safe_graph_name(graph_name)
    kind = 0 if numeric_type == "int" else 1
    command = (
        "run -oc {__PADISTVALUE=plotagent_distribution_value("
        f'"{graph}",{plot_index},{theme_id},{kind}'
        ");};"
    )
    if not op.lt_exec(command):
        raise RuntimeError("Origin could not invoke native distribution readback")
    value = float(op.lt_float("__PADISTVALUE"))
    if not math.isfinite(value):
        raise RuntimeError(
            "Origin native distribution readback returned a missing value: "
            f"plot={plot_index}, theme_id=0x{theme_id:04X}"
        )
    return int(value) if numeric_type == "int" else value

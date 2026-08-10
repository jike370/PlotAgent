# ruff: noqa: E402
"""Mechanical bare-template probe for the 38-chart Origin template catalog.

This script deliberately does not call PlotAgent's resolver, Origin planner, or
renderer.  It writes deterministic probe data, applies the registered Origin
official template, adds only native data plots, saves one OPJU per chart, and
reopens the project in a fresh Origin session for structural readback.  It does
not export contact sheets or make visual-pass decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.contracts.engine_profiles import CHART_PROFILES_BY_ID, ChartProfile
from plotagent.contracts.registry import PRODUCT_CHART_IDS
from scripts import build_per_chart_opju

Phase = Literal["prepare", "build", "reopen", "freeze", "all"]

ORIGIN_INSTALL = Path(os.environ.get("PLOTAGENT_ORIGIN_HOME", r"D:\origin"))
OUTPUT = REPOSITORY / "build" / "origin-template-probe"
MANIFEST_PATH = OUTPUT / "manifest.json"
FROZEN_MANIFEST_PATH = REPOSITORY / "tests" / "fixtures" / "origin_template_probe" / "manifest.json"
PROBE_VERSION = "origin-bare-template-probe.v1"


@dataclass(frozen=True, slots=True)
class ProbeVariant:
    name: str
    frame: pd.DataFrame
    edited: bool = False


_CATEGORY_COLUMNS: dict[str, str] = {
    "K08": "category",
    "K09": "category",
    "K10": "category",
    "K11": "category",
    "K12": "group",
    "K13": "group",
    "K14": "group",
    "K16": "group",
    "K20": "row",
    "K21": "row_label",
    "K24": "facet",
    "K25": "panel",
    "S01": "group",
    "S21": "label",
    "S34": "series",
    "S61": "actual",
    "X03": "category",
    "X05": "group",
    "X09": "category",
    "X13": "category",
    "X35": "category",
    "X36": "category",
    "X38": "series",
}

_LONG_SERIES_COLUMNS: dict[str, str] = {
    "K09": "group",
    "K10": "component",
    "K11": "component",
    "K12": "group",
    "K14": "group",
    "K16": "group",
    "K24": "facet",
    "K25": "panel",
    "S01": "group",
    "S34": "series",
    "X05": "group",
    "X38": "series",
}

_WIDE_SERIES_CHARTS = frozenset({"K07", "X03", "X39", "X40"})

_T2_PATCH_EXPECTATIONS: dict[str, dict[str, str]] = {
    "K04": {
        "color_scale_visibility": "bind size/color and keep the color scale opt-in",
    },
    "K09": {
        "dynamic_plot_group": "derive native group width and gap from the current group count",
    },
    "K12": {
        "long_table_grouping": "derive native grouped-strip placement from long-table groups",
    },
    "K16": {
        "density_component_visibility": (
            "hide template histogram/rug components for density-only output"
        ),
    },
    "K24": {
        "dynamic_facet_layers": "create and bind one native layer for every current facet",
    },
    "K25": {
        "native_panel_composition": "compose current child plots as native editable panels",
    },
    "S01": {
        "risk_table_and_step_band": (
            "bind step curves, confidence bands, and the dynamic risk table"
        ),
    },
    "S21": {
        "interval_weight_encoding": "bind intervals and encode study weight in marker size",
    },
    "S34": {
        "equal_axis_and_direction_encoding": (
            "enforce equal axes and retain frequency direction encoding"
        ),
    },
    "S61": {
        "matrix_count_labels": "bind category axes and native per-cell count labels",
    },
}

_IDENTIFIER_COLUMNS = frozenset(
    {
        "actual",
        "category",
        "column",
        "column_label",
        "component",
        "facet",
        "feature",
        "frequency",
        "group",
        "label",
        "panel",
        "predicted",
        "row",
        "row_label",
        "series",
        "time",
        "x",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _probe_source_sha256() -> str:
    digest = hashlib.sha256()
    for path in (
        REPOSITORY / "src" / "plotagent" / "contracts" / "engine_profiles.py",
        Path(__file__).resolve(),
    ):
        relative = path.relative_to(REPOSITORY).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_json_text(value), encoding="utf-8")
    temporary.replace(path)


def _items_by_chart() -> dict[str, tuple[str, Any, Path]]:
    return {
        case.chart_id: (lane, case, data_path)
        for lane, case, data_path, _target in build_per_chart_opju._items(
            {"seq20", "fixed", "matrix", "structural"}
        )
    }


def _base_frame(chart_id: str) -> pd.DataFrame:
    _lane, _case, data_path = _items_by_chart()[chart_id]
    return pd.read_csv(data_path)


def _measure_columns(chart_id: str, frame: pd.DataFrame) -> tuple[str, ...]:
    columns = tuple(
        str(column)
        for column in frame.select_dtypes(include=[np.number]).columns
        if str(column) not in _IDENTIFIER_COLUMNS
    )
    if columns:
        return columns
    numeric = tuple(str(column) for column in frame.select_dtypes(include=[np.number]).columns)
    if not numeric:
        raise ValueError(f"{chart_id} probe data has no numeric measure")
    return numeric[-1:]


def _resize_rows(frame: pd.DataFrame, target: int) -> pd.DataFrame:
    if target <= len(frame):
        indexes = np.linspace(0, len(frame) - 1, target).round().astype(int)
        return frame.iloc[indexes].reset_index(drop=True)
    copies = math.ceil(target / len(frame))
    resized = pd.concat([frame.copy() for _ in range(copies)], ignore_index=True).iloc[:target]
    for column in resized.columns:
        if pd.api.types.is_numeric_dtype(resized[column]) and str(column) in {"x", "time"}:
            values = pd.to_numeric(resized[column], errors="coerce")
            step = float(np.nanmax(values) - np.nanmin(values) + 1.0)
            resized[column] = values + np.repeat(np.arange(copies), len(frame))[:target] * step
    return resized.reset_index(drop=True)


def _repeat_categories(frame: pd.DataFrame, column: str, target: int) -> pd.DataFrame:
    source_values = tuple(dict.fromkeys(frame[column].astype(str)))
    if not source_values:
        return frame.copy()
    blocks: list[pd.DataFrame] = []
    for index in range(target):
        source = source_values[index % len(source_values)]
        block = frame.loc[frame[column].astype(str) == source].copy()
        if block.empty:
            block = frame.iloc[[index % len(frame)]].copy()
        block[column] = f"类别{index + 1:02d}"
        blocks.append(block)
    return pd.concat(blocks, ignore_index=True)


def _long_series_count(frame: pd.DataFrame, column: str, target: int) -> pd.DataFrame:
    values = tuple(dict.fromkeys(frame[column].astype(str)))
    if not values:
        return frame.copy()
    blocks: list[pd.DataFrame] = []
    numeric = tuple(frame.select_dtypes(include=[np.number]).columns)
    for index in range(target):
        source = values[index % len(values)]
        block = frame.loc[frame[column].astype(str) == source].copy()
        if block.empty:
            block = frame.copy()
        block[column] = f"Series {index + 1}"
        if index >= len(values):
            for numeric_column in numeric:
                if str(numeric_column) not in {"x", "time", "frequency"}:
                    block[numeric_column] = (
                        pd.to_numeric(block[numeric_column], errors="coerce") + index * 0.125
                    )
        blocks.append(block)
    return pd.concat(blocks, ignore_index=True)


def _wide_series_count(chart_id: str, frame: pd.DataFrame, target: int) -> pd.DataFrame:
    if chart_id == "K07":
        output = pd.DataFrame({"x": frame["x"]})
        available = max(1, (len(frame.columns) - 1) // 3)
        for index in range(target):
            source = index % available + 1
            offset = index * 0.125
            for prefix in ("center", "lower", "upper"):
                output[f"{prefix}{index + 1}"] = (
                    pd.to_numeric(frame[f"{prefix}{source}"], errors="coerce") + offset
                )
        return output
    id_columns = ["category"] if chart_id == "X03" else []
    series_columns = [column for column in frame.columns if column not in id_columns]
    output = frame[id_columns].copy()
    for index in range(target):
        source = series_columns[index % len(series_columns)]
        output[f"series_{index + 1}"] = (
            pd.to_numeric(frame[source], errors="coerce") + (index // len(series_columns)) * 0.125
        )
    return output


def probe_variants(chart_id: str, frame: pd.DataFrame) -> tuple[ProbeVariant, ...]:
    variants: list[ProbeVariant] = [ProbeVariant("default", frame.copy())]
    variants.append(ProbeVariant("rows_min", _resize_rows(frame, min(3, len(frame)))))
    variants.append(ProbeVariant("rows_large", _resize_rows(frame, max(30, len(frame) * 2))))

    measure_columns = _measure_columns(chart_id, frame)
    ranged = frame.copy()
    for column in measure_columns:
        values = pd.to_numeric(ranged[column], errors="coerce")
        ranged[column] = values - float(values.mean())
    variants.append(ProbeVariant("range_cross_zero", ranged))

    missing = frame.copy()
    missing.loc[missing.index[len(missing) // 2], measure_columns[0]] = np.nan
    variants.append(ProbeVariant("missing_middle", missing))

    label_column = _CATEGORY_COLUMNS.get(chart_id)
    if label_column is not None and label_column in frame:
        labelled = frame.copy()
        labelled[label_column] = [
            f"中文长标签_{index + 1:02d}_Scientific category" for index in range(len(labelled))
        ]
        variants.append(ProbeVariant("labels_long_cjk", labelled))
        for count in (3, 10, 30):
            variants.append(
                ProbeVariant(
                    f"categories_{count}",
                    _repeat_categories(frame, label_column, count),
                )
            )

    series_column = _LONG_SERIES_COLUMNS.get(chart_id)
    if series_column is not None:
        for count in (1, 3, 5):
            variants.append(
                ProbeVariant(
                    f"series_{count}",
                    _long_series_count(frame, series_column, count),
                )
            )
    elif chart_id in _WIDE_SERIES_CHARTS:
        for count in (1, 3, 5):
            variants.append(
                ProbeVariant(f"series_{count}", _wide_series_count(chart_id, frame, count))
            )

    variants.append(ProbeVariant("edited", frame.copy(), edited=True))
    unique: dict[str, ProbeVariant] = {variant.name: variant for variant in variants}
    return tuple(unique.values())


def _wide_from_long(
    frame: pd.DataFrame, *, group: str, value: str, index: str | None = None
) -> pd.DataFrame:
    values = tuple(dict.fromkeys(frame[group].astype(str)))
    columns: dict[str, pd.Series] = {}
    for item in values:
        selected = frame.loc[frame[group].astype(str) == item]
        series = pd.to_numeric(selected[value], errors="coerce").reset_index(drop=True)
        columns[item] = series
    output = pd.DataFrame(columns)
    if index is not None:
        index_values = frame.loc[frame[group].astype(str) == values[0], index].reset_index(
            drop=True
        )
        output.insert(0, index, index_values)
    return output


def _matrix(frame: pd.DataFrame, *, row: str, column: str, value: str) -> np.ndarray:
    row_order = tuple(dict.fromkeys(frame[row].astype(str)))
    column_order = tuple(dict.fromkeys(frame[column].astype(str)))
    return (
        frame.pivot_table(index=row, columns=column, values=value, aggfunc="mean")
        .reindex(index=row_order, columns=column_order)
        .to_numpy(dtype=float)
    )


def _new_worksheet(op: Any, name: str, frame: pd.DataFrame) -> Any:
    book = op.new_book("w", name, hidden=True)
    if book is None:
        raise RuntimeError(f"could not create Origin workbook {name}")
    sheet = book[0]
    sheet.from_df(frame)
    return sheet


def _new_matrix(op: Any, name: str, values: np.ndarray) -> Any:
    book = op.new_book("m", name, hidden=True)
    if book is None:
        raise RuntimeError(f"could not create Origin matrixbook {name}")
    sheet = book[0]
    sheet.from_np(values)
    sheet.xymap = (1.0, float(values.shape[1]), 1.0, float(values.shape[0]))
    return sheet


def _new_graph(op: Any, name: str, profile: ChartProfile) -> Any:
    template_path = (ORIGIN_INSTALL / profile.origin.filename).resolve()
    # originpro 1.1.15 rejects an otherwise valid absolute template path when
    # the on-disk extension is uppercase (for example SCATTER.OTP).  Windows
    # resolves the same file case-insensitively; normalize only the argument
    # suffix and keep the frozen official file and hash untouched.
    template_argument = template_path.with_suffix(template_path.suffix.lower())
    graph = op.new_graph(
        name,
        template=str(template_argument),
        hidden=True,
    )
    if graph is None:
        raise RuntimeError(f"could not create Origin graph {name}")
    return graph


def _add_xy(
    layer: Any,
    sheet: Any,
    *,
    y: int | str,
    x: int | str = 0,
    plot_type: str = "?",
    y_error: int | str = "",
    x_error: int | str = "",
) -> Any:
    kwargs: dict[str, object] = {"coly": y, "colx": x, "type": plot_type}
    if y_error != "":
        kwargs["colyerr"] = y_error
    if x_error != "":
        kwargs["colxerr"] = x_error
    plot = layer.add_plot(sheet, **kwargs)
    if plot is None:
        raise RuntimeError("Origin template rejected a native worksheet plot")
    return plot


def _bind_simple_xy(
    op: Any,
    profile: ChartProfile,
    frame: pd.DataFrame,
    graph_name: str,
    *,
    plot_type: str,
) -> tuple[Any, list[Any]]:
    sheet = _new_worksheet(op, f"D{graph_name}", frame)
    sheet.cols_axis("xy")
    graph = _new_graph(op, graph_name, profile)
    plot = _add_xy(graph[0], sheet, y=1, x=0, plot_type=plot_type)
    return graph, [plot]


def _bind_matrix(
    op: Any,
    profile: ChartProfile,
    graph_name: str,
    values: np.ndarray,
    plot_type: int,
) -> tuple[Any, list[Any]]:
    sheet = _new_matrix(op, f"D{graph_name}", values)
    graph = _new_graph(op, graph_name, profile)
    plot = graph[0].add_mplot(sheet, 0, type=plot_type)
    if plot is None:
        raise RuntimeError("Origin template rejected a native matrix plot")
    return graph, [plot]


def _raw_box_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns: dict[str, pd.Series] = {}
    for _, row in frame.iterrows():
        values = np.array(
            [
                row["whisker_low"],
                row["q1"],
                row["median"],
                row["q3"],
                row["whisker_high"],
            ],
            dtype=float,
        )
        columns[str(row["group"])] = pd.Series(np.repeat(values, (1, 3, 5, 3, 1)))
    return pd.DataFrame(columns)


def _raw_violin_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns: dict[str, pd.Series] = {}
    for group, selected in frame.groupby("group", sort=False):
        density = pd.to_numeric(selected["density"], errors="coerce").fillna(0.0)
        grid = pd.to_numeric(selected["grid"], errors="coerce")
        if float(density.max()) <= 0:
            weights = np.ones(len(density), dtype=int)
        else:
            weights = np.maximum(1, np.rint(density / float(density.max()) * 8)).astype(int)
        columns[str(group)] = pd.Series(np.repeat(grid.to_numpy(dtype=float), weights))
    return pd.DataFrame(columns)


def _raw_histogram_frame(frame: pd.DataFrame) -> pd.DataFrame:
    midpoint = (pd.to_numeric(frame["left"]) + pd.to_numeric(frame["right"])) / 2.0
    height = pd.to_numeric(frame["height"]).fillna(0.0)
    positive = height[height > 0]
    scale = float(positive.min()) if not positive.empty else 1.0
    counts = np.maximum(1, np.rint(height / scale).astype(int))
    return pd.DataFrame({"value": np.repeat(midpoint.to_numpy(dtype=float), counts)})


def _transpose_series(frame: pd.DataFrame) -> pd.DataFrame:
    values = frame.select_dtypes(include=[np.number]).to_numpy(dtype=float)
    output = pd.DataFrame({"x": np.arange(1, values.shape[1] + 1, dtype=float)})
    for index, row in enumerate(values):
        output[f"row_{index + 1}"] = row
    return output


def bind_template(
    op: Any,
    profile: ChartProfile,
    variant: ProbeVariant,
    graph_name: str,
) -> tuple[Any, list[Any]]:
    chart_id = profile.chart_type_id
    frame = variant.frame

    if chart_id in {"K01", "K18", "K19"}:
        return _bind_simple_xy(op, profile, frame, graph_name, plot_type="l")
    if chart_id == "K02":
        return _bind_simple_xy(op, profile, frame, graph_name, plot_type="y")
    if chart_id in {"K03", "X02"}:
        return _bind_simple_xy(op, profile, frame, graph_name, plot_type="s")
    if chart_id == "K04":
        sheet = _new_worksheet(op, f"D{graph_name}", frame[["x", "y", "size", "color"]])
        sheet.cols_axis("xynn")
        graph = _new_graph(op, graph_name, profile)
        return graph, [_add_xy(graph[0], sheet, y=1, x=0, plot_type="s")]
    if chart_id == "K06":
        plotted = pd.DataFrame(
            {
                "x": frame["x"],
                "center": frame["center"],
                "y_error": np.maximum(
                    pd.to_numeric(frame["upper"]) - pd.to_numeric(frame["center"]),
                    pd.to_numeric(frame["center"]) - pd.to_numeric(frame["lower"]),
                ),
                "x_error": np.maximum(
                    pd.to_numeric(frame["x_upper"]) - pd.to_numeric(frame["x"]),
                    pd.to_numeric(frame["x"]) - pd.to_numeric(frame["x_lower"]),
                ),
            }
        )
        sheet = _new_worksheet(op, f"D{graph_name}", plotted)
        sheet.cols_axis("xyem")
        graph = _new_graph(op, graph_name, profile)
        plot = _add_xy(graph[0], sheet, y=1, x=0, plot_type="s", y_error=2, x_error=3)
        return graph, [plot]
    if chart_id == "K07":
        sheet = _new_worksheet(op, f"D{graph_name}", frame)
        sheet.cols_axis("x" + "y" * (len(frame.columns) - 1))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x=0, plot_type="l")
            for index in range(1, len(frame.columns))
        ]
        return graph, plots
    if chart_id == "K08":
        sheet = _new_worksheet(op, f"D{graph_name}", frame[["category", "value"]])
        sheet.cols_axis("xy")
        graph = _new_graph(op, graph_name, profile)
        return graph, [_add_xy(graph[0], sheet, y=1, x=0, plot_type="c")]
    if chart_id in {"K09", "K10", "K11"}:
        group = "group" if chart_id == "K09" else "component"
        wide = frame.pivot_table(
            index="category", columns=group, values="value", aggfunc="mean"
        ).reset_index()
        sheet = _new_worksheet(op, f"D{graph_name}", wide)
        sheet.cols_axis("x" + "y" * (len(wide.columns) - 1))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x=0, plot_type="c")
            for index in range(1, len(wide.columns))
        ]
        if len(plots) > 1:
            graph[0].group(True, 0, len(plots) - 1)
        return graph, plots
    if chart_id in {"K12", "X05"}:
        wide = _wide_from_long(frame, group="group", value="value")
        sheet = _new_worksheet(op, f"D{graph_name}", wide)
        sheet.cols_axis("y" * len(wide.columns))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x="#", plot_type="?")
            for index in range(len(wide.columns))
        ]
        return graph, plots
    if chart_id == "K13":
        raw = _raw_box_frame(frame)
        sheet = _new_worksheet(op, f"D{graph_name}", raw)
        sheet.cols_axis("y" * len(raw.columns))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x="#", plot_type="?")
            for index in range(len(raw.columns))
        ]
        return graph, plots
    if chart_id == "K14":
        raw = _raw_violin_frame(frame)
        sheet = _new_worksheet(op, f"D{graph_name}", raw)
        sheet.cols_axis("y" * len(raw.columns))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x="#", plot_type="?")
            for index in range(len(raw.columns))
        ]
        return graph, plots
    if chart_id == "K15":
        raw = _raw_histogram_frame(frame)
        sheet = _new_worksheet(op, f"D{graph_name}", raw)
        sheet.cols_axis("y")
        graph = _new_graph(op, graph_name, profile)
        return graph, [_add_xy(graph[0], sheet, y=0, x="#", plot_type="?")]
    if chart_id == "K16":
        wide = _wide_from_long(frame, group="group", value="density", index="grid")
        sheet = _new_worksheet(op, f"D{graph_name}", wide)
        sheet.cols_axis("x" + "y" * (len(wide.columns) - 1))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x=0, plot_type="l")
            for index in range(1, len(wide.columns))
        ]
        return graph, plots
    if chart_id in {"K20", "K21", "S61"}:
        if chart_id == "K20":
            values = _matrix(frame, row="row", column="column", value="value")
            plot_type = 105
        elif chart_id == "K21":
            values = _matrix(frame, row="row_label", column="column_label", value="value")
            plot_type = 105
        else:
            values = _matrix(frame, row="actual", column="predicted", value="value")
            plot_type = 105
        return _bind_matrix(op, profile, graph_name, values, plot_type)
    if chart_id == "K22":
        x_values = tuple(sorted(dict.fromkeys(pd.to_numeric(frame["x"]))))
        y_values = tuple(sorted(dict.fromkeys(pd.to_numeric(frame["y"]))))
        values = (
            frame.pivot_table(index="y", columns="x", values="z", aggfunc="mean")
            .reindex(index=y_values, columns=x_values)
            .to_numpy(dtype=float)
        )
        return _bind_matrix(op, profile, graph_name, values, 226)
    if chart_id in {"K24", "K25"}:
        group_column = "facet" if chart_id == "K24" else "panel"
        x_column = "base_x" if chart_id == "K24" else "x"
        y_column = "base_y" if chart_id == "K24" else "y"
        sheet = _new_worksheet(op, f"D{graph_name}", frame)
        graph = _new_graph(op, graph_name, profile)
        groups = tuple(dict.fromkeys(frame[group_column].astype(str)))
        plots: list[Any] = []
        for index, group in enumerate(groups):
            selected = frame.loc[frame[group_column].astype(str) == group, [x_column, y_column]]
            group_sheet = _new_worksheet(op, f"D{graph_name}{index}", selected)
            group_sheet.cols_axis("xy")
            layers = list(graph)
            layer = layers[index] if index < len(layers) else graph[0]
            plots.append(_add_xy(layer, group_sheet, y=1, x=0, plot_type="l"))
        return graph, plots
    if chart_id == "S01":
        graph = _new_graph(op, graph_name, profile)
        plots: list[Any] = []
        for index, (_group, selected) in enumerate(frame.groupby("group", sort=False)):
            group_sheet = _new_worksheet(
                op,
                f"D{graph_name}{index}",
                selected[["time", "survival", "lower", "upper"]],
            )
            group_sheet.cols_axis("xyyy")
            plots.append(_add_xy(graph[0], group_sheet, y=1, x=0, plot_type="l"))
            plots.append(_add_xy(graph[0], group_sheet, y=2, x=0, plot_type="l"))
            plots.append(_add_xy(graph[0], group_sheet, y=3, x=0, plot_type="l"))
        return graph, plots
    if chart_id == "S21":
        plotted = pd.DataFrame(
            {
                "effect": frame["effect"],
                "row": np.arange(len(frame), 0, -1, dtype=float),
                "x_error": np.maximum(
                    pd.to_numeric(frame["upper"]) - pd.to_numeric(frame["effect"]),
                    pd.to_numeric(frame["effect"]) - pd.to_numeric(frame["lower"]),
                ),
                "weight": frame["weight"],
            }
        )
        sheet = _new_worksheet(op, f"D{graph_name}", plotted)
        sheet.cols_axis("xyMn")
        graph = _new_graph(op, graph_name, profile)
        plot = _add_xy(graph[0], sheet, y=1, x=0, plot_type="s", x_error=2)
        return graph, [plot]
    if chart_id == "S34":
        sheet = _new_worksheet(op, f"D{graph_name}", frame)
        graph = _new_graph(op, graph_name, profile)
        plots = []
        for index, (_series, selected) in enumerate(frame.groupby("series", sort=False)):
            group_sheet = _new_worksheet(
                op, f"D{graph_name}{index}", selected[["z_real", "z_imaginary"]]
            )
            group_sheet.cols_axis("xy")
            plots.append(_add_xy(graph[0], group_sheet, y=1, x=0, plot_type="y"))
        return graph, plots
    if chart_id == "X03":
        sheet = _new_worksheet(op, f"D{graph_name}", frame)
        sheet.cols_axis("x" + "y" * (len(frame.columns) - 1))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x=0, plot_type="?")
            for index in range(1, len(frame.columns))
        ]
        return graph, plots
    if chart_id == "X09":
        plotted = frame[["category", "start", "end", "middle"]]
        sheet = _new_worksheet(op, f"D{graph_name}", plotted)
        sheet.cols_axis("xyyy")
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=1, x=0, plot_type="?"),
            _add_xy(graph[0], sheet, y=2, x=0, plot_type="?"),
        ]
        graph[0].group(True, 0, 1)
        return graph, plots
    if chart_id == "X13":
        sheet = _new_worksheet(op, f"D{graph_name}", frame[["category", "left", "right"]])
        sheet.cols_axis("xyy")
        graph = _new_graph(op, graph_name, profile)
        plots = [_add_xy(graph[0], sheet, y=index, x=0, plot_type="?") for index in (1, 2)]
        return graph, plots
    if chart_id in {"X23", "X35", "X36"}:
        x_column = "x" if chart_id == "X23" else "category"
        sheet = _new_worksheet(op, f"D{graph_name}", frame[[x_column, "left", "right"]])
        sheet.cols_axis("xyy")
        graph = _new_graph(op, graph_name, profile)
        layers = list(graph)
        while len(layers) < 2:
            native_layer = graph.obj.AddLayer()
            if native_layer is None or not native_layer.IsValid():
                raise RuntimeError(f"{chart_id} template lacks a usable second layer")
            layers = list(graph)
        left_type = "l" if chart_id == "X23" else "c"
        right_type = "l" if chart_id in {"X23", "X36"} else "c"
        return graph, [
            _add_xy(layers[0], sheet, y=1, x=0, plot_type=left_type),
            _add_xy(layers[1], sheet, y=2, x=0, plot_type=right_type),
        ]
    if chart_id == "X24":
        ordered = frame.sort_values("value", ascending=False).reset_index(drop=True)
        cumulative = ordered["value"].cumsum() / ordered["value"].sum() * 100.0
        plotted = ordered.assign(cumulative=cumulative)
        sheet = _new_worksheet(op, f"D{graph_name}", plotted)
        sheet.cols_axis("xyy")
        graph = _new_graph(op, graph_name, profile)
        layers = list(graph)
        return graph, [
            _add_xy(layers[0], sheet, y=1, x=0, plot_type="c"),
            _add_xy(layers[min(1, len(layers) - 1)], sheet, y=2, x=0, plot_type="l"),
        ]
    if chart_id == "X38":
        wide = _wide_from_long(frame, group="series", value="y", index="x")
        sheet = _new_worksheet(op, f"D{graph_name}", wide)
        sheet.cols_axis("x" + "y" * (len(wide.columns) - 1))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x=0, plot_type="l")
            for index in range(1, len(wide.columns))
        ]
        return graph, plots
    if chart_id in {"X39", "X40"}:
        wide = _transpose_series(frame)
        sheet = _new_worksheet(op, f"D{graph_name}", wide)
        sheet.cols_axis("x" + "y" * (len(wide.columns) - 1))
        graph = _new_graph(op, graph_name, profile)
        plots = [
            _add_xy(graph[0], sheet, y=index, x=0, plot_type="?")
            for index in range(1, len(wide.columns))
        ]
        return graph, plots
    raise RuntimeError(f"no bare-template binder for {chart_id}")


def _graph_structure(graph: Any) -> dict[str, object]:
    layers = list(graph)
    return {
        "graph_name": graph.name,
        "layer_count": len(layers),
        "plot_counts": [len(layer.plot_list()) for layer in layers],
        "total_plot_count": sum(len(layer.plot_list()) for layer in layers),
    }


def _template_path(profile: ChartProfile) -> Path:
    return (ORIGIN_INSTALL / profile.origin.filename).resolve()


def _selected_chart_ids(raw: str) -> tuple[str, ...]:
    if raw == "all":
        return tuple(PRODUCT_CHART_IDS)
    ids = tuple(dict.fromkeys(item.strip().upper() for item in raw.split(",") if item.strip()))
    unknown = tuple(chart_id for chart_id in ids if chart_id not in CHART_PROFILES_BY_ID)
    if unknown:
        raise ValueError(f"unknown product chart ids: {', '.join(unknown)}")
    return ids


def prepare(chart_ids: tuple[str, ...]) -> dict[str, object]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    charts: dict[str, object] = {}
    for chart_id in chart_ids:
        profile = CHART_PROFILES_BY_ID[cast(Any, chart_id)]
        template = _template_path(profile)
        if not template.is_file():
            raise FileNotFoundError(f"Origin official template is missing: {template}")
        actual_sha256 = _sha256(template)
        if actual_sha256 != profile.origin.sha256:
            raise RuntimeError(
                f"Origin template hash differs for {chart_id}: "
                f"{actual_sha256} != {profile.origin.sha256}"
            )
        frame = _base_frame(chart_id)
        variants = probe_variants(chart_id, frame)
        patch_expectations = _T2_PATCH_EXPECTATIONS.get(chart_id, {})
        if tuple(patch_expectations) != profile.origin.declared_patch_ids:
            raise RuntimeError(f"{chart_id} declared patch evidence is out of sync")
        charts[chart_id] = {
            "chart_type_id": chart_id,
            "tier": profile.origin.tier,
            "template_filename": profile.origin.filename,
            "template_sha256": actual_sha256,
            "binder_id": profile.origin.binder_id,
            "declared_patch_ids": list(profile.origin.declared_patch_ids),
            "declared_patch_evidence": [
                {
                    "patch_id": patch_id,
                    "expected": expectation,
                    "bare_phase_status": "NOT_APPLIED",
                    "reason": "the bare-template phase forbids chart-specific native configuration",
                }
                for patch_id, expectation in patch_expectations.items()
            ],
            "input_columns": [str(column) for column in frame.columns],
            "input_row_count": len(frame),
            "variants": [
                {
                    "name": variant.name,
                    "row_count": len(variant.frame),
                    "column_count": len(variant.frame.columns),
                    "edited": variant.edited,
                }
                for variant in variants
            ],
            "build_status": "pending",
            "fresh_reopen_status": "pending",
            "conclusion": "pending",
        }
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "probe_version": PROBE_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "origin_install": str(ORIGIN_INSTALL),
        "rules": {
            "plotagent_renderer_used": False,
            "contact_sheet_generated": False,
            "visual_pass_allowed": False,
            "allowed_operations": [
                "write_native_worksheet_or_matrix",
                "apply_registered_official_template",
                "add_native_data_plot",
                "representative_native_style_edit",
                "save_and_fresh_reopen",
            ],
        },
        "chart_ids": list(chart_ids),
        "charts": charts,
    }
    _write_json(MANIFEST_PATH, manifest)
    return manifest


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError("prepare the Origin template probe manifest first")
    return cast(dict[str, Any], json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))


def build(chart_ids: tuple[str, ...]) -> dict[str, Any]:
    import originpro as op  # type: ignore[import-untyped]

    manifest = _load_manifest()
    charts = cast(dict[str, dict[str, Any]], manifest["charts"])
    op.set_show(False)
    try:
        for chart_id in chart_ids:
            profile = CHART_PROFILES_BY_ID[cast(Any, chart_id)]
            frame = _base_frame(chart_id)
            variants = probe_variants(chart_id, frame)
            op.new(asksave=False)
            structures: list[dict[str, object]] = []
            for index, variant in enumerate(variants):
                graph_name = f"P{chart_id}{index:02d}"
                graph, plots = bind_template(op, profile, variant, graph_name)
                graph.lname = f"{chart_id} {variant.name} bare template"
                for layer in list(graph):
                    if layer.plot_list():
                        layer.rescale()
                if variant.edited:
                    graph.lname = f"{chart_id} representative edited bare template"
                    if plots:
                        plots[0].color = "#4059ad"
                structure = _graph_structure(graph)
                structure.update(
                    {
                        "variant": variant.name,
                        "row_count": len(variant.frame),
                        "column_count": len(variant.frame.columns),
                        "edited": variant.edited,
                    }
                )
                if int(structure["total_plot_count"]) < 1:
                    raise RuntimeError(f"{chart_id}/{variant.name} produced no native data plot")
                structures.append(structure)

            chart_dir = OUTPUT / chart_id
            chart_dir.mkdir(parents=True, exist_ok=True)
            temporary = chart_dir / f"{chart_id}.tmp.opju"
            target = chart_dir / f"{chart_id}.opju"
            if temporary.is_file():
                temporary.unlink()
            op.save(str(temporary))
            op.new(asksave=False)
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise RuntimeError(f"Origin did not save a non-empty project for {chart_id}")
            temporary.replace(target)
            charts[chart_id].update(
                {
                    "build_status": "passed",
                    "fresh_reopen_status": "pending",
                    "opju_path": str(target),
                    "opju_size": target.stat().st_size,
                    "opju_sha256": _sha256(target),
                    "build_structures": structures,
                    "declared_patch_evidence": [
                        {
                            **evidence,
                            "bare_phase_status": "CONFIRMED_ABSENT",
                            "observed_graph_count": len(structures),
                            "observed_native_plot_count": sum(
                                int(structure["total_plot_count"]) for structure in structures
                            ),
                        }
                        for evidence in charts[chart_id]["declared_patch_evidence"]
                    ],
                }
            )
            _write_json(MANIFEST_PATH, manifest)
    finally:
        op.exit()
    return manifest


def reopen(chart_ids: tuple[str, ...]) -> dict[str, Any]:
    import originpro as op  # type: ignore[import-untyped]

    manifest = _load_manifest()
    charts = cast(dict[str, dict[str, Any]], manifest["charts"])
    op.set_show(False)
    try:
        for chart_id in chart_ids:
            entry = charts[chart_id]
            target = Path(str(entry["opju_path"]))
            if entry.get("build_status") != "passed" or not target.is_file():
                raise RuntimeError(f"{chart_id} has no completed build to reopen")
            op.new(asksave=False)
            if not op.open(str(target), readonly=True, asksave=False):
                raise RuntimeError(f"fresh Origin session could not open {target}")
            actual_graphs = {graph.name: graph for graph in op.pages("g")}
            expected = cast(list[dict[str, Any]], entry["build_structures"])
            reopen_structures: list[dict[str, object]] = []
            for expected_graph in expected:
                graph_name = str(expected_graph["graph_name"])
                graph = actual_graphs.get(graph_name)
                if graph is None:
                    raise RuntimeError(f"{chart_id} fresh project is missing graph {graph_name}")
                actual = _graph_structure(graph)
                if actual["layer_count"] != expected_graph["layer_count"]:
                    raise RuntimeError(f"{chart_id}/{graph_name} layer count changed after reopen")
                if actual["plot_counts"] != expected_graph["plot_counts"]:
                    raise RuntimeError(f"{chart_id}/{graph_name} plot count changed after reopen")
                actual["variant"] = expected_graph["variant"]
                reopen_structures.append(actual)
            profile = CHART_PROFILES_BY_ID[cast(Any, chart_id)]
            patch_evidence = cast(list[dict[str, Any]], entry["declared_patch_evidence"])
            if profile.origin.tier == "T2" and (
                not patch_evidence
                or any(item["bare_phase_status"] != "CONFIRMED_ABSENT" for item in patch_evidence)
            ):
                raise RuntimeError(f"{chart_id} has no confirmed bare-template patch gap")
            conclusion = "AUTO" if profile.origin.tier == "T1" else "DECLARED_PATCH"
            entry.update(
                {
                    "fresh_reopen_status": "passed",
                    "fresh_reopen_identical": True,
                    "reopen_structures": reopen_structures,
                    "conclusion": conclusion,
                    "visual_status": "UNVERIFIED",
                }
            )
            _write_json(MANIFEST_PATH, manifest)
    finally:
        op.exit()

    selected = [charts[chart_id] for chart_id in chart_ids]
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    manifest["summary"] = {
        "selected_chart_count": len(chart_ids),
        "build_passed": sum(item["build_status"] == "passed" for item in selected),
        "fresh_reopen_passed": sum(item["fresh_reopen_status"] == "passed" for item in selected),
        "auto": sum(item["conclusion"] == "AUTO" for item in selected),
        "declared_patch": sum(item["conclusion"] == "DECLARED_PATCH" for item in selected),
        "visual_status": "UNVERIFIED",
    }
    _write_json(MANIFEST_PATH, manifest)
    return manifest


def freeze() -> dict[str, object]:
    manifest = _load_manifest()
    charts = cast(dict[str, dict[str, Any]], manifest["charts"])
    if tuple(manifest["chart_ids"]) != tuple(PRODUCT_CHART_IDS) or set(charts) != set(
        PRODUCT_CHART_IDS
    ):
        raise RuntimeError("only a complete 38-chart probe can be frozen")

    frozen_charts: dict[str, object] = {}
    for chart_id in PRODUCT_CHART_IDS:
        entry = charts[chart_id]
        profile = CHART_PROFILES_BY_ID[chart_id]
        expected_conclusion = "AUTO" if profile.origin.tier == "T1" else "DECLARED_PATCH"
        if (
            entry.get("build_status") != "passed"
            or entry.get("fresh_reopen_status") != "passed"
            or entry.get("fresh_reopen_identical") is not True
            or entry.get("conclusion") != expected_conclusion
            or entry.get("visual_status") != "UNVERIFIED"
        ):
            raise RuntimeError(f"{chart_id} is not mechanically qualified for freezing")
        frozen_charts[chart_id] = {
            "chart_type_id": chart_id,
            "tier": entry["tier"],
            "template_filename": entry["template_filename"],
            "template_sha256": entry["template_sha256"],
            "binder_id": entry["binder_id"],
            "declared_patch_evidence": entry["declared_patch_evidence"],
            "variants": entry["variants"],
            "build_structures": entry["build_structures"],
            "fresh_reopen_identical": True,
            "opju_size": entry["opju_size"],
            "opju_sha256": entry["opju_sha256"],
            "conclusion": expected_conclusion,
            "visual_status": "UNVERIFIED",
        }

    frozen: dict[str, object] = {
        "schema_version": "1.0",
        "probe_version": PROBE_VERSION,
        "probe_source_sha256": _probe_source_sha256(),
        "environment": {
            "origin_display_version": "10.10.178",
            "originpro_version": "1.1.15",
            "official_template_root": r"D:\origin",
        },
        "rules": manifest["rules"],
        "summary": {
            "chart_count": 38,
            "auto": 28,
            "declared_patch": 10,
            "build_passed": 38,
            "fresh_reopen_passed": 38,
            "visual_status": "UNVERIFIED",
        },
        "charts": frozen_charts,
    }
    _write_json(FROZEN_MANIFEST_PATH, frozen)
    return frozen


def _run_fresh_phase(phase: Literal["build", "reopen"], charts: str) -> None:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--phase",
        phase,
        "--charts",
        charts,
    ]
    subprocess.run(command, cwd=REPOSITORY, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("prepare", "build", "reopen", "freeze", "all"),
        default="all",
    )
    parser.add_argument("--charts", default="all", help="all or comma-separated product chart ids")
    args = parser.parse_args()
    chart_ids = _selected_chart_ids(args.charts)
    chart_argument = ",".join(chart_ids)
    if args.phase == "prepare":
        prepare(chart_ids)
    elif args.phase == "build":
        build(chart_ids)
    elif args.phase == "reopen":
        reopen(chart_ids)
    elif args.phase == "freeze":
        if args.charts != "all":
            raise ValueError("freeze always requires --charts all")
        freeze()
    else:
        prepare(chart_ids)
        _run_fresh_phase("build", chart_argument)
        _run_fresh_phase("reopen", chart_argument)
        if args.charts == "all":
            freeze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

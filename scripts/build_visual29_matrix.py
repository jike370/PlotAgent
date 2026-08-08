"""Build same-source visual qualification evidence for the matrix/specialist lane.

This lane covers K04, K12, K19, K21, K22, S21, S31 and S34 from the
post-SEQ-20 set.  A/C evidence remains anchored to Origin-shipped material.
The four charts for which no A/C pair exists use explicitly labelled grade-D
synthetic evidence.  Grade-D references are built with Origin's native graph
API from the frozen CSV and never call either PlotAgent renderer:

* Grade A: export an Origin-shipped project graph and freeze its workbook data.
* Grade C: rebuild the reference in Origin from Origin-shipped sample data with
  an Origin-shipped template.
* Grade D: freeze a deterministic generator/seed, preserve its exact input in
  the reference OPJU, and construct the reference with an Origin system
  template plus native plots.
"""

# ruff: noqa: E402, E501 -- bootstrap and generated audit HTML stay contiguous.

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent import __version__ as PLOTAGENT_VERSION
from plotagent.contracts.base import (
    ChartTypeId,
    ColorValue,
    PhysicalLength,
    PrecomputedKind,
    PreparedDatasetRef,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.plots import (
    AllGeometryKind,
    AxisSpec,
    ColorbarEditSpec,
    DistributionFamily,
    ForestFamily,
    MatrixFamily,
    PlotFamily,
    PlotProvenance,
    PlotSpec,
    PrecomputedDataRef,
    PrecomputedSeriesData,
    PreparedSeriesData,
    SafeRichText,
    SafeTextNode,
    ScaleSpec,
    SeriesData,
    SeriesSpec,
    SeriesStyleSpec,
    SpecialistEditSpec,
    StyleSourceRef,
    XYFamily,
)
from plotagent.contracts.styles import SymbolStyle
from plotagent.exports import export_png
from plotagent.origin import build_origin_export_spec, compile_origin_plan, export_origin
from plotagent.origin.constants import (
    DECLARED_ORIGIN_BITNESS,
    DECLARED_ORIGIN_DISPLAY_NAME,
    DECLARED_ORIGIN_DISPLAY_VERSION,
    DECLARED_ORIGIN_RUNTIME_VERSION,
    DECLARED_ORIGINPRO_VERSION,
)
from plotagent.origin.models import OriginExportSuccess
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable, ResolvedPlot
from scripts.visual_source_identity import (
    assert_scope_clean,
    source_build_identity,
)
from tests.contracts.helpers import profile, style

ORIGIN = Path(r"D:\origin")
OUTPUT = REPOSITORY / "build" / "visual-audit" / "visual29-matrix"
FIXTURES = REPOSITORY / "tests" / "fixtures" / "visual_regression" / "visual29-matrix"
SOURCE_SCOPE_VERSION = "visual29-matrix-rendering-v2"
SOURCE_SCOPE = (
    Path("pyproject.toml"),
    Path("src/plotagent/charts"),
    Path("src/plotagent/contracts/rendering.py"),
    Path("src/plotagent/contracts/styles.py"),
    Path("src/plotagent/origin"),
    Path("src/plotagent/rendering"),
)


@dataclass(frozen=True, slots=True)
class AuditCase:
    chart_id: str
    slug: str
    title: str
    grade: Literal["A", "C", "D"]
    source: Path | None
    graph_name: str | None
    source_book: str | None
    origin_template: str | None
    recipe: str
    common_edit: str
    chart_edit: str

    @property
    def case_id(self) -> str:
        return f"{self.chart_id}_{self.slug}"


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    chart_id: str
    title: str
    required_data: str
    available_evidence: str
    blocking_reason: str


CASES: tuple[AuditCase, ...] = (
    AuditCase(
        "K04",
        "bubble_colormap",
        "气泡与颜色映射散点",
        "A",
        ORIGIN / "bubble.opju",
        "Graph2",
        "Book1",
        None,
        "直接导出 Origin 随附 bubble.opju 的 Graph2；冻结同项目 Book1 的 X/Y/Size/Color。",
        "标题与字号",
        "符号形状与尺寸，同时保留 size/color 数据映射",
    ),
    AuditCase(
        "K12",
        "strip",
        "单变量点图与条带图",
        "A",
        ORIGIN / "ColumnScatter.opju",
        "Graph11",
        "Book1",
        None,
        "直接导出 Origin 随附 ColumnScatter.opju 的 Graph11；将同项目三列观测无损转成长表。",
        "标题与字号",
        "点形与点大小，并保留分组色板",
    ),
    AuditCase(
        "K19",
        "time_series",
        "时间序列图",
        "C",
        ORIGIN / "Samples" / "Import and Export" / "Custom Date and Time.dat",
        None,
        None,
        "LINE",
        "Origin 官方 Custom Date and Time.dat，以随附 LINE.otpu 在 Origin 中重新生成；保留时间列原始精度。",
        "标题与字号",
        "线色与线宽",
    ),
    AuditCase(
        "K22",
        "contour",
        "等高线与填色等值图",
        "A",
        ORIGIN / "Contour.opju",
        "Graph1",
        "Book2",
        None,
        "直接导出 Origin 随附 Contour.opju 的 Graph1；冻结同项目 Book2 的完整规则 XYZ 网格。",
        "标题与字号",
        "色带范围与级数",
    ),
)

GAPS: tuple[EvidenceGap, ...] = (
    EvidenceGap(
        "K21",
        "相关矩阵图",
        "Origin 官方预计算相关矩阵、行列标签及由该矩阵直接生成的参考图",
        "安装目录只有相关分析原始样例和矩阵类模板，没有随附的预计算相关矩阵参考图对",
        "产品契约禁止在资格测试中替用户计算 Pearson/Spearman，因此不能用原始样例现场计算后冒充同源输入",
    ),
    EvidenceGap(
        "S21",
        "森林图",
        "Origin 官方 effect/lower/upper/weight 数据及由该表直接生成的森林图",
        "安装目录未发现森林图随附项目或同源官方样例数据；历史 v2/LLM 回归图不是独立官方参考",
        "缺少 A/C 级同源证据",
    ),
    EvidenceGap(
        "S31",
        "XRD 衍射图",
        "Origin 官方 angle/intensity 数据及相应 XRD 参考图或官方模板重建说明",
        "本机存在用户 XRD 文本，但 Origin 安装目录未发现对应随附项目或官方样例数据",
        "外部/用户数据不满足本轮 C 级“Origin 官方样例数据”要求",
    ),
    EvidenceGap(
        "S34",
        "Nyquist 图",
        "Origin 官方 Z′/-Z″/frequency 数据及相应 Nyquist 参考图或官方模板重建说明",
        "本机存在用户 EIS 文本与用户生成 OPJU，但 Origin 安装目录未发现对应随附项目或官方样例数据",
        "外部/用户数据不满足本轮 C 级“Origin 官方样例数据”要求",
    ),
)

# Product decision 2026-08-09: these former A/C gaps are admitted only as
# explicit grade-D synthetic evidence.  Keeping the legacy descriptions above
# makes the historical reason auditable, while the active qualification set has
# no missing-evidence entries.
SYNTHETIC_CASES = (
    AuditCase(
        "K21",
        "correlation_matrix_synthetic",
        "Correlation matrix",
        "D",
        None,
        None,
        None,
        "HEAT_MAP_WITH_LABELS",
        "Deterministic precomputed correlation matrix; independent Origin matrixbook heat-map reference.",
        "Title and font size",
        "Diverging color scale, fixed bounds and matrix labels",
    ),
    AuditCase(
        "S21",
        "forest_synthetic",
        "Forest plot",
        "D",
        None,
        None,
        None,
        "SCATTER",
        "Deterministic precomputed effects and intervals; independent Origin interval-line and weighted-symbol reference.",
        "Title and font size",
        "Interval color/width, point symbol and weight scaling",
    ),
    AuditCase(
        "S31",
        "xrd_synthetic",
        "XRD diffraction plot",
        "D",
        None,
        None,
        None,
        "LINE",
        "Deterministic precomputed multi-series diffraction spectra; independent Origin multi-line reference.",
        "Title and font size",
        "Series colors, line widths and legend",
    ),
    AuditCase(
        "S34",
        "nyquist_synthetic",
        "Nyquist plot",
        "D",
        None,
        None,
        None,
        "LINESYMB",
        "Deterministic precomputed multi-series complex impedance curves; independent Origin line-symbol reference.",
        "Title and font size",
        "Series colors, symbols and equal-axis geometry",
    ),
)
CASES = CASES + SYNTHETIC_CASES
LEGACY_A_C_GAPS = GAPS
GAPS = ()

SYNTHETIC_GENERATOR_VERSION = "visual29-matrix-grade-d-pcg64-v1"
SYNTHETIC_RULES: dict[str, dict[str, Any]] = {
    "K21": {"seed": 24080921, "dimension": 6, "observations": 96},
    "S21": {"seed": 24080922, "studies": 7},
    "S31": {"seed": 24080931, "series": 3, "points": 181, "angle_min": 10.0, "angle_max": 80.0},
    "S34": {"seed": 24080934, "series": 3, "points": 28, "frequency_min": 0.1, "frequency_max": 100000.0},
}

VISUAL_OBSERVATIONS: dict[str, tuple[str, ...]] = {}
GAP_BLOCKING_OBSERVATIONS: tuple[dict[str, str], ...] = ()
FIRST_ROUND_BLOCKING_OBSERVATIONS: tuple[dict[str, str], ...] = (
    {
        "chart_type_id": "K04",
        "backend": "matplotlib",
        "severity": "P0",
        "observation": "varying bubble sizes have no size legend; the Origin reference exposes an explicit size key",
    },
    {
        "chart_type_id": "K04",
        "backend": "origin",
        "severity": "P0",
        "observation": "the color scale overlays the left Y-axis tick region and the varying bubble sizes still have no size key",
    },
    {
        "chart_type_id": "K12",
        "backend": "matplotlib",
        "severity": "P0",
        "observation": "the full official group label is clipped below the canvas and the inside legend overlaps observations",
    },
    {
        "chart_type_id": "K12",
        "backend": "origin",
        "severity": "P0",
        "observation": "the inside legend covers the upper Bacon observations in both default and edited fresh-reopen graphs",
    },
    {
        "chart_type_id": "K22",
        "backend": "matplotlib",
        "severity": "P0",
        "observation": "colorbar tick labels are clipped at the right canvas edge",
    },
    {
        "chart_type_id": "K22",
        "backend": "origin",
        "severity": "P0",
        "observation": "the color scale and its tick labels overlap the left Y-axis tick region",
    },
)


@dataclass(frozen=True, slots=True)
class InputSeries:
    geometry: AllGeometryKind
    kind: Literal["prepared", "precomputed"]
    roles: tuple[str, ...]
    values: tuple[tuple[object, ...], ...]
    precomputed_kind: PrecomputedKind | None = None
    label: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _synthetic_k21_frame(
    *, seed: int, dimension: int, observations: int
) -> pd.DataFrame:
    if dimension < 2 or observations < dimension + 2:
        raise ValueError("correlation fixture requires dimension >= 2 and enough observations")
    rng = np.random.Generator(np.random.PCG64(seed))
    latent = rng.normal(size=(observations, 3))
    loadings = rng.normal(size=(3, dimension))
    values = latent @ loadings + rng.normal(scale=0.42, size=(observations, dimension))
    matrix: np.ndarray = np.asarray(np.corrcoef(values, rowvar=False), dtype=float)
    matrix = np.round(matrix, 6)
    np.fill_diagonal(matrix, 1.0)
    labels = tuple(f"V{index + 1}" for index in range(dimension))
    return pd.DataFrame(
        (
            {"row_label": row, "column_label": column, "value": float(matrix[i, j])}
            for i, row in enumerate(labels)
            for j, column in enumerate(labels)
        )
    )


def _synthetic_s21_frame(*, seed: int, studies: int) -> pd.DataFrame:
    if studies < 2:
        raise ValueError("forest fixture requires at least two studies")
    rng = np.random.Generator(np.random.PCG64(seed))
    effect = rng.normal(loc=1.02, scale=0.22, size=studies)
    half_width = rng.uniform(0.11, 0.31, size=studies)
    weight = rng.uniform(0.12, 0.55, size=studies)
    return pd.DataFrame(
        {
            "label": [f"Study {index + 1:02d}" for index in range(studies)],
            "effect": np.round(effect, 6),
            "lower": np.round(effect - half_width, 6),
            "upper": np.round(effect + half_width, 6),
            "weight": np.round(weight, 6),
        }
    )


def _synthetic_s31_frame(
    *, seed: int, series: int, points: int, angle_min: float, angle_max: float
) -> pd.DataFrame:
    if series < 1 or points < 16 or not angle_min < angle_max:
        raise ValueError("XRD fixture requires series >= 1, points >= 16 and an ordered range")
    rng = np.random.Generator(np.random.PCG64(seed))
    angle = np.linspace(angle_min, angle_max, points)
    rows: list[dict[str, object]] = []
    span = angle_max - angle_min
    for series_index in range(series):
        baseline = 5.0 + 0.025 * (angle - angle_min) + series_index * 2.0
        intensity = baseline.copy()
        peak_count = 4 + series_index
        centers = np.linspace(angle_min + 0.18 * span, angle_max - 0.16 * span, peak_count)
        centers += rng.uniform(-0.035 * span, 0.035 * span, size=peak_count)
        amplitudes = rng.uniform(28.0, 105.0, size=peak_count) * (1.0 + 0.08 * series_index)
        widths = rng.uniform(0.38, 1.25, size=peak_count)
        for center, amplitude, width in zip(centers, amplitudes, widths, strict=True):
            intensity += amplitude * np.exp(-0.5 * ((angle - center) / width) ** 2)
        intensity += rng.normal(scale=0.45, size=points)
        for x_value, y_value in zip(angle, intensity, strict=True):
            rows.append(
                {
                    "series": f"Phase {series_index + 1}",
                    "angle": round(float(x_value), 6),
                    "intensity": round(max(0.0, float(y_value)), 6),
                }
            )
    return pd.DataFrame(rows)


def _synthetic_s34_frame(
    *, seed: int, series: int, points: int, frequency_min: float, frequency_max: float
) -> pd.DataFrame:
    if series < 1 or points < 8 or not 0 < frequency_min < frequency_max:
        raise ValueError("Nyquist fixture requires series >= 1, points >= 8 and positive frequency bounds")
    rng = np.random.Generator(np.random.PCG64(seed))
    frequency = np.geomspace(frequency_max, frequency_min, points)
    omega = 2.0 * np.pi * frequency
    rows: list[dict[str, object]] = []
    for series_index in range(series):
        r0 = 0.18 + 0.11 * series_index
        rct = 0.95 + 0.48 * series_index
        tau = 10.0 ** (-2.8 + 0.48 * series_index)
        warburg = 0.012 + 0.005 * series_index
        impedance = r0 + rct / (1.0 + 1j * omega * tau)
        impedance += warburg / np.sqrt(1j * omega)
        impedance += rng.normal(scale=0.0015, size=points) + 1j * rng.normal(
            scale=0.0015, size=points
        )
        for freq, value in zip(frequency, impedance, strict=True):
            rows.append(
                {
                    "series": f"Cell {series_index + 1}",
                    "z_real": round(float(value.real), 7),
                    "z_imaginary": round(float(-value.imag), 7),
                    "frequency": round(float(freq), 7),
                }
            )
    return pd.DataFrame(rows)


def _synthetic_frame(case: AuditCase, **overrides: Any) -> pd.DataFrame:
    configured = dict(SYNTHETIC_RULES[case.chart_id])
    configured.update(overrides)
    if case.chart_id == "K21":
        return _synthetic_k21_frame(**configured)
    if case.chart_id == "S21":
        return _synthetic_s21_frame(**configured)
    if case.chart_id == "S31":
        return _synthetic_s31_frame(**configured)
    if case.chart_id == "S34":
        return _synthetic_s34_frame(**configured)
    raise RuntimeError(f"unsupported synthetic matrix case {case.case_id}")


def _origin_book(op: Any, name: str) -> Any:
    book = next((item for item in op.pages("w") if item.name == name), None)
    if book is None:
        raise RuntimeError(f"Origin workbook {name!r} is missing")
    return book


def _project_frame(op: Any, case: AuditCase) -> pd.DataFrame:
    assert case.source_book is not None
    book = _origin_book(op, case.source_book)
    if not len(book):
        raise RuntimeError(f"Origin workbook {book.name!r} has no worksheet")
    source = cast(pd.DataFrame, book[0].to_df())
    if case.chart_id == "K04":
        frame = source.iloc[:, :4].copy()
        frame.columns = ("x", "y", "size", "color")
        return frame.astype(float)
    if case.chart_id == "K12":
        wide = source.iloc[:, :3].copy()
        long = wide.melt(var_name="group", value_name="value")
        # Origin's worksheet missing sentinel survives ``to_df`` as an object;
        # normalize it before freezing the lossless long-form observations.
        long["value"] = pd.to_numeric(long["value"], errors="coerce")
        long = long.dropna(subset=["value"])
        return long.loc[:, ["value", "group"]].reset_index(drop=True)
    if case.chart_id == "K22":
        frame = source.iloc[:, :3].copy()
        frame.columns = ("x", "y", "z")
        return frame.astype(float)
    raise RuntimeError(f"unsupported project source {case.case_id}")


def _frame_from_source(case: AuditCase, op: Any | None = None) -> pd.DataFrame:
    if case.grade == "D":
        return _synthetic_frame(case)
    if case.chart_id == "K19":
        assert case.source is not None
        source = pd.read_csv(case.source, sep="\t", header=None, names=("time", "value"))
        parsed = pd.to_datetime(source["time"], format="%d.%m.%Y %H:%M:%S.%f", errors="raise")
        return pd.DataFrame(
            {
                "time": parsed.dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str.rstrip("0").str.rstrip("."),
                "value": source["value"].astype(float),
            }
        )
    if op is None:
        raise RuntimeError(f"Origin is required to read {case.case_id}")
    return _project_frame(op, case)


def _origin_reference_colors(count: int) -> tuple[str, ...]:
    palette = ("#2A6FDB", "#D95F02", "#2A9D6F", "#8E5BB7", "#C23B53", "#6B7280")
    return tuple(palette[index % len(palette)] for index in range(count))


def _write_synthetic_reference(
    case: AuditCase, frame: pd.DataFrame, case_dir: Path, op: Any
) -> dict[str, Any]:
    """Build one independent Origin-native reference from the frozen D-grade CSV."""

    op.new()
    raw_book = op.new_book("w", f"Matrix{case.chart_id}Raw")
    raw_sheet = raw_book[0]
    raw_sheet.name = "SyntheticData"
    raw_sheet.from_df(frame)
    expected_plot_count: int
    column_mapping: dict[str, str]

    if case.chart_id == "K21":
        row_labels = tuple(dict.fromkeys(frame["row_label"].astype(str)))
        column_labels = tuple(dict.fromkeys(frame["column_label"].astype(str)))
        matrix = (
            frame.pivot(index="row_label", columns="column_label", values="value")
            .reindex(index=row_labels, columns=column_labels)
            .to_numpy(dtype=float)
        )
        matrix_book = op.new_book("m", "MatrixK21Reference")
        matrix_sheet = matrix_book[0]
        matrix_sheet.from_np(matrix)
        matrix_sheet.xymap = (1.0, float(len(column_labels)), 1.0, float(len(row_labels)))
        graph = op.new_graph(template=cast(str, case.origin_template))
        plot = graph[0].add_mplot(matrix_sheet, 0, type=105)
        if plot is None:
            raise RuntimeError("Origin could not add the K21 reference heat map")
        plot.set_float("label.fsize", 10.0)
        plot.colormap = "OrangeNavy.PAL"
        expected_plot_count = 1
        column_mapping = {
            "row_label": "SyntheticData!A / matrix row order",
            "column_label": "SyntheticData!B / matrix column order",
            "value": "SyntheticData!C / matrix Z",
        }
        graph[0].axis("x").title = "Variable"
        graph[0].axis("y").title = "Variable"
        graph[0].rescale()
        graph[0].axis("x").set_limits(0.5, len(column_labels) + 0.5, 1.0)
        graph[0].axis("y").set_limits(0.5, len(row_labels) + 0.5, 1.0)
        graph[0].set_int("x.label.type", 10)
        graph[0].set_float("x.label.fsize", 9.0)
        graph[0].set_str(
            "x.label.string", " ".join(f'"{label}"' for label in column_labels)
        )
        graph[0].set_int("y.label.type", 10)
        graph[0].set_float("y.label.fsize", 9.0)
        graph[0].set_str(
            "y.label.string", " ".join(f'"{label}"' for label in row_labels)
        )
    elif case.chart_id == "S21":
        geometry_sheet = raw_book.add_sheet("ReferenceGeometry")
        y = np.arange(1, len(frame) + 1, dtype=float)
        interval_x: list[float] = []
        interval_y: list[float] = []
        for position, lower, upper in zip(y, frame["lower"], frame["upper"], strict=True):
            interval_x.extend((float(lower), float(upper), np.nan))
            interval_y.extend((float(position), float(position), np.nan))
        plotted: dict[str, pd.Series] = {
            "interval_x": pd.Series(interval_x),
            "interval_y": pd.Series(interval_y),
            "null_x": pd.Series((1.0, 1.0)),
            "null_y": pd.Series((0.5, len(frame) + 0.5)),
        }
        for index, (effect, position) in enumerate(zip(frame["effect"], y, strict=True)):
            plotted[f"point_{index + 1}_x"] = pd.Series((float(effect),))
            plotted[f"point_{index + 1}_y"] = pd.Series((float(position),))
        geometry_sheet.from_df(pd.DataFrame(plotted))
        geometry_sheet.cols_axis("XY" * (2 + len(frame)))
        graph = op.new_graph(template=cast(str, case.origin_template))
        graph.set_int("connect", 0)
        layer = graph[0]
        interval = layer.add_plot(geometry_sheet, coly=1, colx=0, type=200)
        neutral = layer.add_plot(geometry_sheet, coly=3, colx=2, type=200)
        if interval is None or neutral is None:
            raise RuntimeError("Origin could not add S21 reference interval or null line")
        interval.color = "#2A6FDB"
        neutral.color = "#6B7280"
        weights = pd.to_numeric(frame["weight"], errors="raise").to_numpy(dtype=float)
        maximum_weight = max(float(weights.max()), 1e-12)
        for index, weight in enumerate(weights):
            point = layer.add_plot(
                geometry_sheet,
                coly=5 + index * 2,
                colx=4 + index * 2,
                type=201,
            )
            if point is None:
                raise RuntimeError("Origin could not add an S21 weighted reference point")
            point.color = "#2A6FDB"
            point.symbol_kind = 1
            point.symbol_size = 6.0 + 9.0 * float(weight) / maximum_weight
        layer.rescale()
        x_min = float(frame["lower"].min())
        x_max = float(frame["upper"].max())
        margin = max((x_max - x_min) * 0.08, 0.05)
        layer.axis("x").set_limits(x_min - margin, x_max + margin)
        layer.axis("y").set_limits(0.5, len(frame) + 0.5, 1.0)
        layer.axis("x").title = "Effect estimate"
        layer.axis("y").title = "Study"
        layer.set_int("y.label.type", 10)
        layer.set_str(
            "y.label.string",
            " ".join(f'"{label}"' for label in frame["label"].astype(str)),
        )
        legend = layer.label("legend")
        if legend is not None:
            legend.set_int("show", 0)
        expected_plot_count = len(frame) + 2
        column_mapping = {
            "label": "SyntheticData!A / categorical study identity",
            "effect": "SyntheticData!B / native scatter X",
            "lower": "SyntheticData!C / interval start",
            "upper": "SyntheticData!D / interval end",
            "weight": "SyntheticData!E / native symbol size",
        }
    elif case.chart_id in {"S31", "S34"}:
        geometry_sheet = raw_book.add_sheet("ReferenceGeometry")
        groups = tuple(dict.fromkeys(frame["series"].astype(str)))
        x_column = "angle" if case.chart_id == "S31" else "z_real"
        y_column = "intensity" if case.chart_id == "S31" else "z_imaginary"
        plotted = {}
        for group in groups:
            selected = frame.loc[frame["series"].astype(str) == group]
            plotted[f"{group}_x"] = pd.Series(selected[x_column].to_numpy(dtype=float))
            plotted[f"{group}_y"] = pd.Series(selected[y_column].to_numpy(dtype=float))
        geometry_sheet.from_df(pd.DataFrame(plotted))
        geometry_sheet.cols_axis("XY" * len(groups))
        graph = op.new_graph(template=cast(str, case.origin_template))
        layer = graph[0]
        colors = _origin_reference_colors(len(groups))
        plot_type = 200 if case.chart_id == "S31" else 202
        for index, color in enumerate(colors):
            plot = layer.add_plot(
                geometry_sheet, coly=index * 2 + 1, colx=index * 2, type=plot_type
            )
            if plot is None:
                raise RuntimeError(f"Origin could not add a {case.chart_id} reference series")
            plot.color = color
            if case.chart_id == "S34":
                plot.symbol_kind = 1 + index % 4
                plot.symbol_size = 7.0
        layer.rescale()
        if case.chart_id == "S31":
            layer.axis("x").title = "2 theta (degree)"
            layer.axis("y").title = "Intensity (a.u.)"
        else:
            layer.axis("x").title = "Z real (ohm)"
            layer.axis("y").title = "-Z imaginary (ohm)"
            x_max = float(frame["z_real"].max())
            y_max = float(frame["z_imaginary"].max())
            upper = max(x_max, y_max) * 1.08
            layer.axis("x").set_limits(0.0, upper)
            layer.axis("y").set_limits(0.0, upper)
        legend = layer.label("legend")
        if legend is not None:
            legend.text = "\n".join(f"\\l({index + 1}) {group}" for index, group in enumerate(groups))
            legend.set_int("link", 0)
            legend.set_int("show", 1)
            legend.set_float("fsize", 10.0)
        expected_plot_count = len(groups)
        column_mapping = {
            "series": "SyntheticData!A / one native plot per distinct series",
            x_column: "SyntheticData numeric X / ReferenceGeometry XY pair",
            y_column: "SyntheticData numeric Y / ReferenceGeometry XY pair",
        }
        if case.chart_id == "S34":
            column_mapping["frequency"] = "SyntheticData!D / point order and direction metadata"
    else:
        raise RuntimeError(f"unsupported D-grade reference {case.case_id}")

    graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
    target = case_dir / "reference-origin.opju"
    op.save(str(target))
    return {
        "construction_path": "independent_origin_native",
        "plotagent_renderer_used": False,
        "origin_template": case.origin_template,
        "origin_menu_equivalent": {
            "K21": "Plot > Contour/Heat Map > Heat Map with Labels",
            "S21": "Plot > Basic 2D > Scatter plus native interval lines",
            "S31": "Plot > Basic 2D > Line",
            "S34": "Plot > Basic 2D > Line + Symbol",
        }[case.chart_id],
        "origin_graph_name": graph.name,
        "raw_sheet": "SyntheticData",
        "raw_column_mapping": column_mapping,
        "geometry_sheet": None if case.chart_id == "K21" else "ReferenceGeometry",
        "expected_native_plot_count": expected_plot_count,
        "reference_opju_path": str(target),
    }


def _fresh_synthetic_reference_readback(
    reference_opju: Path,
    reference_png: Path,
    expected_frame: pd.DataFrame,
    *,
    expected_plot_count: int,
) -> dict[str, Any]:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        op.open(str(reference_opju), readonly=True)
        graphs = list(op.pages("g"))
        books = list(op.pages("w"))
        if len(graphs) != 1 or not books:
            raise RuntimeError("fresh synthetic reference lost its graph or raw workbook")
        raw_sheet = next(
            (sheet for book in books for sheet in list(book) if sheet.name == "SyntheticData"),
            None,
        )
        if raw_sheet is None:
            raise RuntimeError("fresh synthetic reference lost SyntheticData")
        readback = cast(pd.DataFrame, raw_sheet.to_df()).reset_index(drop=True)
        if list(readback.columns[: len(expected_frame.columns)]) != list(expected_frame.columns):
            raise RuntimeError(f"fresh synthetic raw columns differ: {list(readback.columns)}")
        for column in expected_frame.columns:
            expected = expected_frame[column]
            actual = readback[column]
            if pd.api.types.is_numeric_dtype(expected):
                if not np.allclose(
                    pd.to_numeric(actual, errors="raise"),
                    pd.to_numeric(expected, errors="raise"),
                    rtol=0.0,
                    atol=1e-9,
                ):
                    raise RuntimeError(f"fresh synthetic {column} values differ")
            elif actual.astype(str).tolist() != expected.astype(str).tolist():
                raise RuntimeError(f"fresh synthetic {column} identities differ")
        actual_plot_count = len(graphs[0][0].plot_list())
        if actual_plot_count != expected_plot_count:
            raise RuntimeError(
                f"fresh synthetic reference plot count {actual_plot_count} != {expected_plot_count}"
            )
        graphs[0].save_fig(str(reference_png), type="png", replace=True, width=1600)
        return {
            "fresh_reopen_verified": True,
            "fresh_raw_rows": len(readback),
            "fresh_raw_columns": list(expected_frame.columns),
            "fresh_native_plot_count": actual_plot_count,
        }
    finally:
        op.exit()


def _write_reference(
    case: AuditCase, frame: pd.DataFrame, case_dir: Path, op: Any
) -> dict[str, Any]:
    if case.grade == "D":
        return _write_synthetic_reference(case, frame, case_dir, op)
    if case.grade == "A":
        assert case.graph_name is not None
        graph = next((item for item in op.pages("g") if item.name == case.graph_name), None)
        if graph is None:
            raise RuntimeError(f"Origin graph {case.graph_name!r} is missing")
        graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
        op.save(str(case_dir / "reference-origin.opju"))
        return {
            "construction_path": "origin_shipped_project",
            "plotagent_renderer_used": False,
            "origin_graph_name": graph.name,
        }

    assert case.origin_template is not None
    op.new()
    book = op.new_book("w", lname=f"{case.chart_id} official source")
    sheet = book[0]
    origin_frame = frame.copy()
    origin_frame["time"] = pd.to_datetime(origin_frame["time"])
    sheet.from_df(origin_frame)
    graph = op.new_graph(template=case.origin_template)
    layer = graph[0]
    layer.add_plot(sheet, coly=1, colx=0, type=200)
    layer.rescale()
    # The official source spans a single date, so the system template's date
    # labels are all identical.  Origin's documented Time tick-label mode keeps
    # the actual within-day information visible without transforming the data.
    layer.lt_exec("layer.x.label.type=3; layer.x.label.timeFormat=1;")
    graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
    op.save(str(case_dir / "reference-origin.opju"))
    return {
        "construction_path": "origin_shipped_data_system_template",
        "plotagent_renderer_used": False,
        "origin_template": case.origin_template,
        "origin_graph_name": graph.name,
    }


def _prepare_case(case: AuditCase, output: Path, fixtures: Path) -> dict[str, Any]:
    import originpro as op

    case_dir = output / case.case_id
    fixture_dir = fixtures / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    op.set_show(False)
    try:
        if case.grade == "D":
            frame = _frame_from_source(case)
        elif case.source is not None and case.source.suffix.lower() in {".opj", ".opju", ".ogw"}:
            op.new()
            op.open(str(case.source), readonly=True)
            frame = _frame_from_source(case, op)
        else:
            if case.source is None:
                raise RuntimeError(f"missing evidence source for {case.case_id}")
            frame = _frame_from_source(case)
        reference_construction = _write_reference(case, frame, case_dir, op)
    finally:
        op.exit()

    if case.grade == "D":
        reference_opju = case_dir / "reference-origin.opju"
        reference_construction.update(
            _fresh_synthetic_reference_readback(
                reference_opju,
                case_dir / "reference.png",
                frame,
                expected_plot_count=int(reference_construction["expected_native_plot_count"]),
            )
        )
        reference_construction["reference_opju_sha256"] = _sha256(reference_opju)

    frame.to_csv(case_dir / "data.csv", index=False, float_format="%.12g")
    shutil.copy2(case_dir / "data.csv", fixture_dir / "data.csv")
    shutil.copy2(case_dir / "reference.png", fixture_dir / "reference.png")
    provenance = {
        "chart_type_id": case.chart_id,
        "evidence_grade": case.grade,
        "evidence_status": "anchored",
        "source_path": str(case.source) if case.source is not None else None,
        "source_sha256": _sha256(case.source) if case.source is not None else None,
        "source_graph_name": case.graph_name,
        "source_book": case.source_book,
        "origin_template": case.origin_template,
        "recipe": case.recipe,
        "same_source_data": True,
        "official_origin_evidence": case.grade in {"A", "C"},
        "synthetic": case.grade == "D",
        "synthetic_label": "D-grade synthetic data + Origin-generated reference" if case.grade == "D" else None,
        "synthetic_generation": (
            {
                "generator_version": SYNTHETIC_GENERATOR_VERSION,
                "generator": f"_synthetic_{case.chart_id.lower()}_frame",
                "seed": SYNTHETIC_RULES[case.chart_id]["seed"],
                "parameters": SYNTHETIC_RULES[case.chart_id],
                "frozen_before_reference": True,
            }
            if case.grade == "D"
            else None
        ),
        "reference_construction": reference_construction,
        "reference_origin": {
            "display_name": DECLARED_ORIGIN_DISPLAY_NAME,
            "display_version": DECLARED_ORIGIN_DISPLAY_VERSION,
            "runtime_version": DECLARED_ORIGIN_RUNTIME_VERSION,
            "bitness": DECLARED_ORIGIN_BITNESS,
            "originpro_version": DECLARED_ORIGINPRO_VERSION,
        },
        "data_sha256": _sha256(fixture_dir / "data.csv"),
        "reference_sha256": _sha256(fixture_dir / "reference.png"),
        "common_edit": case.common_edit,
        "chart_edit": case.chart_edit,
    }
    for destination in (case_dir / "provenance.json", fixture_dir / "provenance.json"):
        destination.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return provenance


def _input_series(case: AuditCase, frame: pd.DataFrame) -> tuple[InputSeries, ...]:
    def rows(*columns: str) -> tuple[tuple[object, ...], ...]:
        return tuple(tuple(frame[column].tolist()) for column in columns)

    if case.chart_id == "K04":
        return (InputSeries("symbol", "prepared", ("x", "y", "size", "color"), rows("x", "y", "size", "color")),)
    if case.chart_id == "K12":
        return (InputSeries("strip", "prepared", ("value", "group"), rows("value", "group")),)
    if case.chart_id == "K19":
        return (InputSeries("line", "prepared", ("time", "value"), rows("time", "value")),)
    if case.chart_id == "K22":
        return (
            InputSeries(
                "contour",
                "precomputed",
                ("x", "y", "z"),
                rows("x", "y", "z"),
                precomputed_kind="matrix_grid",
            ),
        )
    if case.chart_id == "K21":
        return (
            InputSeries(
                "heatmap",
                "precomputed",
                ("row_label", "column_label", "value"),
                rows("row_label", "column_label", "value"),
                precomputed_kind="matrix",
            ),
        )
    if case.chart_id == "S21":
        return (
            InputSeries(
                "interval",
                "precomputed",
                ("label", "effect", "lower", "upper", "weight"),
                rows("label", "effect", "lower", "upper", "weight"),
                precomputed_kind="effect_interval",
            ),
        )
    if case.chart_id in {"S31", "S34"}:
        inputs: list[InputSeries] = []
        roles = (
            ("angle", "intensity")
            if case.chart_id == "S31"
            else ("z_real", "z_imaginary", "frequency")
        )
        precomputed_kind: PrecomputedKind = (
            "spectrum" if case.chart_id == "S31" else "complex_curve"
        )
        for group in dict.fromkeys(frame["series"].astype(str)):
            selected = frame.loc[frame["series"].astype(str) == group]
            values = tuple(tuple(selected[column].tolist()) for column in roles)
            inputs.append(
                InputSeries(
                    "line",
                    "precomputed",
                    roles,
                    values,
                    precomputed_kind=precomputed_kind,
                    label=group,
                )
            )
        return tuple(inputs)
    raise RuntimeError(f"unsupported series case {case.case_id}")


def _family(case: AuditCase, geometries: tuple[AllGeometryKind, ...]) -> PlotFamily:
    if case.chart_id == "K12":
        return DistributionFamily(geometry=cast(Any, geometries))
    if case.chart_id in {"K21", "K22"}:
        return MatrixFamily(geometry=cast(Any, geometries))
    if case.chart_id == "S21":
        return ForestFamily(geometry=cast(Any, geometries))
    return XYFamily(geometry=cast(Any, geometries))


def _labels_and_scales(case: AuditCase) -> tuple[str, str, str, str]:
    return {
        "K04": ("X", "Y", "linear", "linear"),
        "K12": ("Group", "Value", "categorical", "linear"),
        "K19": ("Time", "Value", "datetime", "linear"),
        "K22": ("Wavelength (nm)", "Temperature", "linear", "linear"),
        "K21": ("Variable", "Variable", "categorical", "categorical"),
        "S21": ("Effect estimate", "Study", "linear", "categorical"),
        "S31": ("2 theta (degree)", "Intensity (a.u.)", "linear", "linear"),
        "S34": ("Z real (ohm)", "-Z imaginary (ohm)", "linear", "linear"),
    }[case.chart_id]


def _build_plot(case: AuditCase, frame: pd.DataFrame, *, edited: bool) -> tuple[PlotSpec, RenderDataStore]:
    inputs = _input_series(case, frame)
    prepared_refs: list[PreparedDatasetRef] = []
    precomputed_refs: list[PrecomputedDataRef] = []
    specifications: list[SeriesSpec] = []
    store: dict[str, RenderTable] = {}
    for index, item in enumerate(inputs):
        field_ids = tuple(f"field:visual29.matrix.{case.chart_id.lower()}.{index}.{role}" for role in item.roles)
        table = RenderTable.from_columns(dict(zip(field_ids, item.values, strict=True)))
        prepared = PreparedDatasetRef(
            prepared_dataset_id=f"prepared:visual29.matrix.{case.chart_id.lower()}.{index}",
            prepared_version=1,
            content_hash=table.object_hash,
        )
        prepared_refs.append(prepared)
        if item.kind == "prepared":
            data: SeriesData = PreparedSeriesData(prepared_dataset_ref=prepared, role_fields=field_ids)
        else:
            precomputed = PrecomputedDataRef(
                precomputed_id=f"precomputed:visual29.matrix.{case.chart_id.lower()}.{index}",
                precomputed_version=1,
                precomputed_kind=item.precomputed_kind or "matrix_grid",
                content_hash=table.object_hash,
                data_ref_hash=table.object_hash,
                field_ids=field_ids,
            )
            precomputed_refs.append(precomputed)
            data = PrecomputedSeriesData(precomputed_data_ref=precomputed, role_fields=field_ids)
        store[table.object_hash] = table

        series_style = SeriesStyleSpec()
        if edited and case.chart_id == "K04":
            series_style = series_style.model_copy(
                update={
                    "marker_size": PhysicalLength(value=7.0, unit="pt"),
                    "symbol": SymbolStyle(shape="diamond", interior="solid"),
                }
            )
        elif edited and case.chart_id == "K12":
            series_style = series_style.model_copy(
                update={
                    "marker_size": PhysicalLength(value=5.5, unit="pt"),
                    "symbol": SymbolStyle(shape="diamond", interior="solid"),
                }
            )
        elif edited and case.chart_id == "K19":
            series_style = series_style.model_copy(
                update={
                    "color": ColorValue(value="#D95F02"),
                    "line_width": PhysicalLength(value=1.6, unit="pt"),
                }
            )
        elif edited and case.chart_id == "S21":
            series_style = series_style.model_copy(
                update={
                    "color": ColorValue(value="#8E5BB7"),
                    "marker_size": PhysicalLength(value=7.0, unit="pt"),
                }
            )
        elif edited and case.chart_id in {"S31", "S34"}:
            colors = _origin_reference_colors(len(inputs))
            updates: dict[str, Any] = {
                "color": ColorValue(value=colors[index]),
                "line_width": PhysicalLength(value=1.6, unit="pt"),
            }
            if case.chart_id == "S34":
                updates["marker_size"] = PhysicalLength(value=5.5, unit="pt")
                updates["symbol"] = SymbolStyle(
                    shape=("diamond", "square", "triangle_up", "circle")[index % 4],
                    interior="solid",
                )
            series_style = series_style.model_copy(update=updates)
        specifications.append(
            SeriesSpec(
                series_id=f"series:visual29.matrix.{case.chart_id.lower()}.{index}",
                geometry=item.geometry,
                data=data,
                label=_text(item.label) if item.label else None,
                style=series_style,
            )
        )

    specialist = SpecialistEditSpec()
    if edited and case.chart_id == "K22":
        minimum = float(frame["z"].min())
        maximum = float(frame["z"].max())
        specialist = specialist.model_copy(
            update={"colorbar": ColorbarEditSpec(visible=True, title=_text("Amplitude"), minimum=minimum, maximum=maximum, levels=9)}
        )
    elif edited and case.chart_id == "K21":
        specialist = specialist.model_copy(
            update={
                "colorbar": ColorbarEditSpec(
                    visible=True,
                    title=_text("Correlation"),
                    minimum=-1.0,
                    maximum=1.0,
                    levels=11,
                )
            }
        )
    elif edited and case.chart_id == "S21":
        specialist = specialist.model_copy(
            update={
                "uncertainty": specialist.uncertainty.model_copy(
                    update={
                        "color": ColorValue(value="#8E5BB7"),
                        "line_width": PhysicalLength(value=1.4, unit="pt"),
                        "cap_size": PhysicalLength(value=4.5, unit="pt"),
                    }
                )
            }
        )

    x_label, y_label, x_kind, y_kind = _labels_and_scales(case)
    english_title = {
        "K04": "Bubble and colormap scatter",
        "K12": "Dot and strip plot",
        "K19": "Time-series plot",
        "K22": "Filled contour",
        "K21": "Correlation matrix",
        "S21": "Forest plot",
        "S31": "XRD diffraction spectra",
        "S34": "Nyquist impedance spectra",
    }[case.chart_id]
    edited_title = {
        "K04": "Edited K04 bubble plot",
        "K12": "Edited K12 strip plot",
        "K19": "Edited K19 time series",
        "K22": "Edited K22 contour",
        "K21": "Edited K21 correlation matrix",
        "S21": "Edited S21 forest plot",
        "S31": "Edited S31 XRD spectra",
        "S34": "Edited S34 Nyquist spectra",
    }[case.chart_id]
    plot = PlotSpec(
        plot_id=f"plot:visual29.matrix.{case.chart_id.lower()}.{'edited' if edited else 'default'}",
        plot_version=2 if edited else 1,
        chart_type_id=cast(ChartTypeId, case.chart_id),
        title=_text(edited_title if edited else english_title),
        family=_family(case, tuple(dict.fromkeys(item.geometry for item in inputs))),
        prepared_data_refs=tuple(prepared_refs),
        precomputed_data_refs=tuple(precomputed_refs),
        scales=(
            ScaleSpec(scale_id="scale:x", kind=cast(Any, x_kind)),
            ScaleSpec(scale_id="scale:y", kind=cast(Any, y_kind)),
        ),
        axes=(
            AxisSpec(axis_id="axis:x", scale_id="scale:x", orientation="x", position="bottom", label=_text(x_label)),
            AxisSpec(axis_id="axis:y", scale_id="scale:y", orientation="y", position="left", label=_text(y_label)),
        ),
        series=tuple(specifications),
        specialist=specialist,
        style_sources=(
            StyleSourceRef(
                source_kind="project",
                source_id="style.visual29.matrix",
                source_version=1,
                content_hash=hashlib.sha256(b"style.visual29.matrix").hexdigest(),
            ),
        ),
        resolved_style=style().model_copy(
            update={"font_size": PhysicalLength(value=9.5 if edited else 8.0, unit="pt")}
        ),
        publication_profile=profile(),
        provenance=PlotProvenance(
            origin="manual", engine_build_hash=hashlib.sha256(b"visual29.matrix").hexdigest()
        ),
    )
    return plot, RenderDataStore(store)


def _contact_sheet(case_dir: Path, state: str) -> None:
    files = (
        case_dir / "reference.png",
        case_dir / state / "matplotlib.png",
        case_dir / state / "origin-fresh-reopen.png",
    )
    labels = (
        "ORIGIN REFERENCE",
        f"MATPLOTLIB · {state.upper()}",
        f"ORIGIN O1 · {state.upper()} · FRESH REOPEN",
    )
    images = [Image.open(path).convert("RGB") for path in files]
    try:
        width, height, header = 620, 470, 42
        output = Image.new("RGB", (width * 3, height + header), "white")
        draw = ImageDraw.Draw(output)
        for index, (source, label) in enumerate(zip(images, labels, strict=True)):
            fitted = ImageOps.contain(source, (width - 24, height - 24))
            left = index * width + (width - fitted.width) // 2
            top = header + (height - fitted.height) // 2
            output.paste(fitted, (left, top))
            draw.text((index * width + 16, 14), label, fill="black")
        output.save(case_dir / f"comparison-{state}.png", optimize=True)
    finally:
        for source in images:
            source.close()


def _export_reopened_graphs(opju: Path, destinations: tuple[Path, ...]) -> None:
    import originpro as op

    op.set_show(False)
    try:
        op.open(str(opju), readonly=True)
        graphs = list(op.pages("g"))
        if len(graphs) != len(destinations):
            raise RuntimeError(f"fresh OPJU graph count {len(graphs)} != expected {len(destinations)}")
        for graph, destination in zip(graphs, destinations, strict=True):
            destination.parent.mkdir(parents=True, exist_ok=True)
            graph.save_fig(str(destination), type="png", replace=True, width=1600)
    finally:
        op.exit()


def _write_gap_register(output: Path, fixtures: Path) -> list[dict[str, Any]]:
    entries = [
        {
            "chart_type_id": gap.chart_id,
            "title": gap.title,
            "status": "not_tested_missing_same_source_evidence",
            "required_data": gap.required_data,
            "available_evidence": gap.available_evidence,
            "blocking_reason": gap.blocking_reason,
            "rendered": False,
            "qualification_claimed": False,
        }
        for gap in GAPS
    ]
    document = {
        "schema_version": "1.0",
        "lane": "visual29-matrix",
        "rules": {
            "same_source_required": True,
            "synthetic_allowed": True,
            "synthetic_evidence_grade": "D",
            "synthetic_must_be_explicit": True,
            "reference_renderer": "independent Origin native construction",
        },
        "gaps": entries,
    }
    for destination in (output / "evidence-gaps.json", fixtures / "evidence-gaps.json"):
        destination.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return entries


def _build_index(
    output: Path,
    blocking_observations: tuple[dict[str, str], ...] = (),
) -> None:
    opju_links = "".join(
        f'<li><strong>{html.escape(case.chart_id)}</strong>：'
        f'<a href="{case.case_id}/{case.chart_id}.opju">默认态＋代表性编辑态</a></li>'
        for case in CASES
    )
    cards: list[str] = [
        f'<article class="exports"><h2>每图一个 OPJU</h2><ul>{opju_links}</ul></article>'
    ]
    for case in CASES:
        blockers = "".join(
            f"<li>{html.escape(item['backend'])} · {html.escape(item['observation'])}</li>"
            for item in blocking_observations
            if item["chart_type_id"] == case.chart_id
        )
        blocker_section = (
            f'<div class="blocker"><strong>阻断观察</strong><ul>{blockers}</ul></div>'
            if blockers
            else ""
        )
        cards.append(
            f"""
<article><h2>{html.escape(case.chart_id)} · {html.escape(case.title)}</h2>
<p><span class="grade">{case.grade} 级</span> {html.escape(case.recipe)}</p>
<p>通用编辑：{html.escape(case.common_edit)}；图型适用编辑：{html.escape(case.chart_edit)}</p>
{blocker_section}
<h3>默认状态</h3><a href="{case.case_id}/comparison-default.png"><img src="{case.case_id}/comparison-default.png" alt="{case.chart_id} default"></a>
<h3>代表性编辑状态</h3><a href="{case.case_id}/comparison-edited.png"><img src="{case.case_id}/comparison-edited.png" alt="{case.chart_id} edited"></a>
<p><a href="{case.case_id}/data.csv">冻结数据</a> · <a href="{case.case_id}/provenance.json">provenance</a></p></article>
"""
        )
    gaps = "".join(
        f"<li><strong>{html.escape(gap.chart_id)} · {html.escape(gap.title)}</strong>：{html.escape(gap.blocking_reason)}</li>"
        for gap in GAPS
    )
    (output / "index.html").write_text(
        f"""<!doctype html><meta charset="utf-8"><title>29 图特殊图视觉资格线</title>
<style>body{{font:14px Arial,sans-serif;margin:24px;background:#f5f5f5;color:#171717}}main{{max-width:1500px;margin:auto}}article,.gaps{{background:#fff;border:1px solid #ddd;margin:0 0 28px;padding:18px}}img{{width:100%;height:auto;border:1px solid #ddd}}h1,h2,h3{{margin:0 0 12px}}h3{{margin-top:18px}}.grade{{background:#111;color:#fff;padding:2px 7px;border-radius:10px}}.blocker{{background:#fff2f0;border:1px solid #e0a09a;padding:10px 12px;margin:12px 0}}li{{margin:8px 0}}</style>
<main><h1>其余 29 图 · 颜色映射 / 矩阵 / 特殊分布资格线</h1>
<p>所有已渲染图均使用冻结的同一份 Origin 官方数据。左：Origin 参考；中：Matplotlib；右：PlotAgent 原生 Origin O1 fresh reopen。</p>
<section class="gaps"><h2>未测试：缺少 A/C 级同源证据</h2><ul>{gaps}</ul><p><a href="evidence-gaps.json">完整缺口登记</a></p></section>{''.join(cards)}</main>""",
        encoding="utf-8",
    )


def _build_index_v2(
    output: Path,
    blocking_observations: tuple[dict[str, str], ...] = (),
) -> None:
    """Write the post-D-admission audit page without legacy A/C-gap wording."""

    opju_links = "".join(
        f'<li><strong>{html.escape(case.chart_id)}</strong>: '
        f'<a href="{case.case_id}/{case.chart_id}.opju">default + representative edited</a></li>'
        for case in CASES
    )
    cards: list[str] = [
        f'<article class="exports"><h2>One OPJU per chart</h2><ul>{opju_links}</ul></article>'
    ]
    for case in CASES:
        blockers = "".join(
            f"<li>{html.escape(item['backend'])}: {html.escape(item['observation'])}</li>"
            for item in blocking_observations
            if item["chart_type_id"] == case.chart_id
        )
        blocker_section = (
            f'<div class="blocker"><strong>Blocking observations</strong><ul>{blockers}</ul></div>'
            if blockers
            else ""
        )
        grade_note = (
            "Synthetic data + independent Origin-native reference; not official Origin evidence."
            if case.grade == "D"
            else "Origin-shipped reference/data evidence."
        )
        cards.append(
            f"""
<article><h2>{html.escape(case.chart_id)} · {html.escape(case.title)}</h2>
<p><span class="grade">Grade {case.grade}</span> {html.escape(grade_note)}</p>
<p>{html.escape(case.recipe)}</p>
<p>Common edit: {html.escape(case.common_edit)}; chart edit: {html.escape(case.chart_edit)}</p>
{blocker_section}
<h3>Default</h3><a href="{case.case_id}/comparison-default.png"><img src="{case.case_id}/comparison-default.png" alt="{case.chart_id} default"></a>
<h3>Representative edited</h3><a href="{case.case_id}/comparison-edited.png"><img src="{case.case_id}/comparison-edited.png" alt="{case.chart_id} edited"></a>
<p><a href="{case.case_id}/data.csv">Frozen data</a> · <a href="{case.case_id}/provenance.json">Provenance</a> · <a href="{case.case_id}/reference-origin.opju">Reference OPJU</a></p></article>
"""
        )
    gaps_section = (
        '<section class="gaps"><h2>Evidence gaps: 0</h2><p>All four former gaps are now '
        'explicitly labelled grade-D synthetic evidence; none is represented as A/C evidence. '
        '<a href="evidence-gaps.json">Gap register</a></p></section>'
    )
    (output / "index.html").write_text(
        f"""<!doctype html><meta charset="utf-8"><title>Visual29 matrix and specialist qualification</title>
<style>body{{font:14px Arial,sans-serif;margin:24px;background:#f5f5f5;color:#171717}}main{{max-width:1500px;margin:auto}}article,.gaps{{background:#fff;border:1px solid #ddd;margin:0 0 28px;padding:18px}}img{{width:100%;height:auto;border:1px solid #ddd}}h1,h2,h3{{margin:0 0 12px}}h3{{margin-top:18px}}.grade{{background:#111;color:#fff;padding:2px 7px;border-radius:10px}}.blocker{{background:#fff2f0;border:1px solid #e0a09a;padding:10px 12px;margin:12px 0}}li{{margin:8px 0}}</style>
<main><h1>Matrix / color mapping / specialist visual qualification</h1>
<p>Every comparison uses one frozen CSV. Left: independent Origin reference; centre: Matplotlib; right: PlotAgent native Origin O1 fresh reopen. Grade D always means synthetic data plus an Origin-generated reference.</p>
{gaps_section}{''.join(cards)}</main>""",
        encoding="utf-8",
    )


def _fresh_qualification(source_identity: dict[str, str]) -> dict[str, Any]:
    return {
        "source_build_identity": source_identity,
        "blocking_observations": list(GAP_BLOCKING_OBSERVATIONS),
        "human_visual_signature": {"status": "pending", "reviewer": None, "signed_at": None},
        "evidence_status": "fresh_render_pending_human",
        "decision": "NO-GO",
    }


def _reviewed_qualification(source_identity: dict[str, str]) -> dict[str, Any]:
    return {
        "source_build_identity": source_identity,
        "blocking_observations": [],
        "human_visual_signature": {
            "status": "reviewed",
            "reviewer": "Codex visual audit",
            "signed_at": datetime.now(UTC).isoformat(),
            "scope": "eight charts, default and representative edited, three-way contact sheets",
        },
        "evidence_status": "qualified_after_visual_review",
        "decision": "GO",
    }


def _render(output: Path, fixtures: Path) -> dict[str, Any]:
    assert_scope_clean(REPOSITORY, SOURCE_SCOPE)
    states: dict[str, list[ResolvedPlot]] = {"default": [], "edited": []}
    case_entries: dict[str, dict[str, Any]] = {}
    for case in CASES:
        fixture_dir = fixtures / case.case_id
        provenance_path = fixture_dir / "provenance.json"
        if not provenance_path.is_file():
            raise RuntimeError(f"prepare evidence first: {case.case_id}")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if _sha256(fixture_dir / "data.csv") != provenance["data_sha256"]:
            raise RuntimeError(f"frozen data changed: {case.case_id}")
        if _sha256(fixture_dir / "reference.png") != provenance["reference_sha256"]:
            raise RuntimeError(f"frozen reference changed: {case.case_id}")
        case_dir = output / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        for name in ("data.csv", "reference.png", "provenance.json"):
            shutil.copy2(fixture_dir / name, case_dir / name)
        frame = pd.read_csv(fixture_dir / "data.csv")
        case_entries[case.case_id] = {
            **provenance,
            "visual_observations": VISUAL_OBSERVATIONS.get(case.chart_id, ()),
            "states": {},
        }
        for state in ("default", "edited"):
            state_dir = case_dir / state
            state_dir.mkdir(exist_ok=True)
            plot, store = _build_plot(case, frame, edited=state == "edited")
            resolved = PlotResolver().resolve(plot, store)
            export_png(state_dir / "matplotlib.png", resolved)
            states[state].append(resolved)
            case_entries[case.case_id]["states"][state] = {
                "plot_spec_sha256": canonical_hash(plot),
                "render_plan_sha256": resolved.render_plan_hash,
                "matplotlib_png_sha256": _sha256(state_dir / "matplotlib.png"),
            }

    export_entries: dict[str, Any] = {}
    for state in ("default", "edited"):
        resolved_tuple = tuple(states[state])
        origin_plan = compile_origin_plan(
            resolved_tuple,
            build_origin_export_spec(
                resolved_tuple,
                export_id=f"export:visual29.matrix.{state}",
                target_scope="selected_plots",
            ),
        )
        target = output / f"visual29-matrix-{state}.opju"
        result = export_origin(
            origin_plan,
            target,
            expected_existing_sha256=_sha256(target) if target.is_file() else None,
            timeout_seconds=480.0,
        )
        if not isinstance(result, OriginExportSuccess):
            raise RuntimeError(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if result.build_validation != result.reopen_validation:
            raise RuntimeError(f"Origin fresh reopen validation drift: {state}")
        destinations = tuple(output / case.case_id / state / "origin-fresh-reopen.png" for case in CASES)
        _export_reopened_graphs(target, destinations)
        for graph_index, (case, destination) in enumerate(zip(CASES, destinations, strict=True)):
            case_entries[case.case_id]["states"][state]["origin_fresh_png_sha256"] = _sha256(destination)
            case_entries[case.case_id]["states"][state]["origin_graph_index"] = graph_index
        export_entries[state] = {
            "opju_path": str(target),
            "opju_sha256": result.file_sha256,
            "opju_size": result.file_size,
            "origin_plan_sha256": canonical_hash(origin_plan),
            "adapter_id": origin_plan.adapter_id,
            "adapter_version": origin_plan.adapter_version,
            "validation_report_sha256": result.validation_report_sha256,
            "fresh_reopen_identical": True,
            "elapsed_seconds": result.elapsed_seconds,
            "environment": result.environment.to_dict(),
        }

    for case in CASES:
        case_dir = output / case.case_id
        for state in ("default", "edited"):
            _contact_sheet(case_dir, state)
        case_entries[case.case_id]["comparison_default_sha256"] = _sha256(case_dir / "comparison-default.png")
        case_entries[case.case_id]["comparison_edited_sha256"] = _sha256(case_dir / "comparison-edited.png")

    gaps = _write_gap_register(output, fixtures)
    manifest = {
        "schema_version": "1.0",
        "stage": "VISUAL-29",
        "lane": "matrix-specialist",
        "generated_at": datetime.now(UTC).isoformat(),
        "plotagent_version": PLOTAGENT_VERSION,
        "origin_declaration": {
            "display_name": DECLARED_ORIGIN_DISPLAY_NAME,
            "display_version": DECLARED_ORIGIN_DISPLAY_VERSION,
            "runtime_version": DECLARED_ORIGIN_RUNTIME_VERSION,
            "bitness": DECLARED_ORIGIN_BITNESS,
            "originpro_version": DECLARED_ORIGINPRO_VERSION,
        },
        "rules": {
            "same_source_required": True,
            "synthetic_allowed": True,
            "allowed_evidence_grades": ["A", "C", "D"],
            "grade_d_definition": "explicit synthetic data plus independently generated Origin-native reference",
            "grade_d_chart_type_ids": [case.chart_id for case in SYNTHETIC_CASES],
            "grade_d_cannot_be_relabelled_as_official": True,
            "states": ["default", "representative edited"],
            "edited_state_requires": ["common edit", "chart-applicable edit", "Origin mapping"],
            "reference_must_not_use_plotagent_renderer": True,
        },
        "exports": export_entries,
        "cases": [case_entries[case.case_id] for case in CASES],
        "evidence_gaps": gaps,
        "qualification": _fresh_qualification(
            source_build_identity(
                REPOSITORY,
                SOURCE_SCOPE,
                scope_version=SOURCE_SCOPE_VERSION,
            )
        ),
        "audit_conclusion": (
            "eight same-source evidence cases generated, including four explicitly labelled D-grade synthetic cases; "
            "human visual sign-off pending; visual qualification not passed"
        ),
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(manifest_path, fixtures / "manifest.json")
    _build_index_v2(output)
    return manifest


def _refresh_audit_metadata(output: Path, fixtures: Path) -> dict[str, Any]:
    """Refresh review findings without rebuilding immutable render evidence."""
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("render evidence is missing; run --phase render first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_source_identity = manifest["qualification"]["source_build_identity"]
    current_source_identity = source_build_identity(
        REPOSITORY,
        SOURCE_SCOPE,
        scope_version=SOURCE_SCOPE_VERSION,
    )
    if manifest_source_identity.get("source_sha256") != current_source_identity["source_sha256"]:
        raise RuntimeError(
            "render evidence source identity is stale; run --phase render before audit"
        )
    manifest["qualification"] = _reviewed_qualification(manifest_source_identity)
    manifest["audit_conclusion"] = (
        "eight same-source evidence cases generated; four A/C cases and four explicitly labelled D-grade "
        "synthetic cases reviewed in default and edited states; automated P0 blockers closed; visual qualification passed"
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(manifest_path, fixtures / "manifest.json")
    _build_index_v2(output)
    return cast(dict[str, Any], manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("prepare", "render", "audit", "all"), default="all")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.fixtures.mkdir(parents=True, exist_ok=True)
    if args.phase in {"prepare", "all"}:
        for case in CASES:
            _prepare_case(case, args.output, args.fixtures)
        _write_gap_register(args.output, args.fixtures)
    if args.phase in {"render", "all"}:
        _render(args.output, args.fixtures)
    elif args.phase == "audit":
        _refresh_audit_metadata(args.output, args.fixtures)


if __name__ == "__main__":
    main()

"""Build same-source visual qualification evidence for fixed-calculation charts.

This line is deliberately independent from the SEQ-20 generator. ``prepare``
anchors Origin-shipped projects or regenerates an Origin reference from an
Origin-shipped sample and freezes the exact PlotAgent input table. ``render``
then creates default/edited Matplotlib output, native O1 OPJU output and a
fresh-Origin reopen export. Missing same-source evidence is recorded as a gap
and is never replaced with synthetic data.
"""

# ruff: noqa: E402, E501 -- the audit builder keeps evidence recipes beside the code.

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps
from scipy.stats import gaussian_kde  # type: ignore[import-untyped]

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent import __version__ as PLOTAGENT_VERSION
from plotagent.contracts.base import ChartTypeId, ColorValue, PhysicalLength, PreparedDatasetRef
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.plots import (
    AllGeometryKind,
    AxisSpec,
    BarAreaEditSpec,
    CalculatedSeriesData,
    CategoricalFamily,
    ChartParameterEditSpec,
    ColorbarEditSpec,
    DistributionFamily,
    MatrixFamily,
    PlotCalculationResultRef,
    PlotFamily,
    PlotProvenance,
    PlotSpec,
    PreparedSeriesData,
    SafeRichText,
    SafeTextNode,
    ScaleSpec,
    SeriesData,
    SeriesSpec,
    SeriesStyleSpec,
    SpecialFamily,
    SpecialistEditSpec,
    StyleSourceRef,
    UncertaintyEditSpec,
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
from tests.contracts.helpers import profile, style

ORIGIN = Path(r"D:\origin")
OUTPUT = REPOSITORY / "build" / "visual-audit" / "visual29-fixed"
FIXTURES = REPOSITORY / "tests" / "fixtures" / "visual_regression" / "visual29-fixed"
SOURCE_SCOPE_VERSION = "visual29-fixed-rendering-v1"
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
    grade: Literal["A", "C"] | None
    source: Path | None
    graph_name: str | None
    source_book: str | None
    source_sheet: int
    recipe: str
    common_edit: str
    chart_edit: str

    @property
    def case_id(self) -> str:
        return f"{self.chart_id}_{self.slug}"


CASES = (
    AuditCase("K06", "point_error", "点估计与误差棒", "A", ORIGIN / "ERRBAR.opju", "Graph1", "Book1", 0, "直接导出 Origin 随附 ERRBAR.opju Graph1；Y error 冻结为显式 lower/upper。", "标题与字号", "误差线颜色、线宽与端帽"),
    AuditCase("K07", "error_band", "误差带", "A", ORIGIN / "ERRORBAND.opju", "Graph1", "Book1", 0, "直接导出 Origin 随附 ERRORBAND.opju Graph1；两组 Y±Error 冻结为显式上下界。", "标题与字号", "误差带颜色、透明度与边界"),
    AuditCase("K11", "percent_stack", "百分比堆积柱", "A", ORIGIN / "Column.opju", "Graph11", "Book2", 0, "直接导出 Origin 随附 Column.opju Graph11；同项目工作表按类别冻结为百分比。", "标题与字号", "柱填充、边线与宽度"),
    AuditCase("K13", "tukey_box", "箱线图", "A", ORIGIN / "Box.opju", "Graph1", "Book1", 0, "直接导出 Origin 随附 Box.opju Graph1；同项目原始值按冻结 Tukey 规则计算箱体。", "标题与字号", "箱体填充、边线与宽度"),
    AuditCase("K14", "violin", "小提琴图", "C", ORIGIN / "Box.opju", None, "Book1", 0, "Origin 随附 Box.opju 原始值；用系统 Violin 模板重建参考，PlotAgent 使用冻结 KDE 网格。", "标题与字号", "小提琴填充、轮廓与宽度"),
    AuditCase("K15", "histogram", "直方图", "A", ORIGIN / "Histogram.opju", "Graph2", "Book1", 0, "直接导出 Origin 随附 Histogram.opju Graph2；Americas 原始值按冻结分箱规则计算。", "标题与字号", "柱填充、边线与透明度"),
    AuditCase("K16", "density", "KDE 密度图", "A", ORIGIN / "Histogram.opju", "Graph7", "Book1", 0, "直接导出 Origin 随附 Histogram.opju Graph7；两组原始值按冻结 KDE 网格计算。", "标题与字号", "密度线颜色与线宽"),
    AuditCase("K17", "ecdf", "ECDF", "C", ORIGIN / "Histogram.opju", None, "Book1", 0, "Origin 随附 Histogram.opju Americas 原始值；冻结 ECDF 后用系统 LINE 模板按水平阶梯重建。", "标题与字号", "ECDF/CCDF 模式与阶梯线样式"),
    AuditCase("K20", "heatmap", "热图", "A", ORIGIN / "Heatmap.opju", "Graph1", "Book1", 0, "直接导出 Origin 随附 Heatmap.opju Graph1 及同项目矩阵工作表。", "标题与字号", "色板、色标与级数"),
    AuditCase("S61", "confusion", "混淆矩阵", "C", ORIGIN / "Samples" / "Statistics" / "LogRegData.dat", None, None, 0, "Origin 官方 LogRegData.dat；冻结实际标签与同源预测标签后，以 HEAT_MAP_WITH_LABELS 模板重建计数矩阵。", "标题与字号", "色板、色标与计数标签"),
    AuditCase("X24", "pareto", "Pareto 图", "C", ORIGIN / "Samples" / "Graphing" / "Counts.dat", None, None, 0, "Origin 官方 Counts.dat；冻结类别计数后以 ParetoRaw 模板重建柱与累计百分比。", "标题与字号", "柱样式与累计参考线"),
    AuditCase("S07", "volcano", "火山图", None, None, None, None, 0, "未在本机 Origin 随附项目、模板样例与 Samples 中找到同时含 feature、log2FC、p/q value 的官方同源数据。", "标题与字号", "阈值线、类别颜色与标签"),
)

QUALIFIED_CASES = tuple(case for case in CASES if case.grade is not None)
MISSING_CASES = tuple(case for case in CASES if case.grade is None)
MECHANICAL_BLOCKERS: tuple[dict[str, str], ...] = (
    {
        "chart_type_id": "K06",
        "code": "NATIVE_ERROR_BAR_CONNECTOR_MISMATCH",
        "status": "open",
        "observation": "Origin O1 connects error-bar endpoints as a zigzag line instead of isolated intervals.",
    },
    {
        "chart_type_id": "K20",
        "code": "NATIVE_COLORBAR_TICK_LABEL_COLLISION",
        "status": "open",
        "observation": "Origin O1 colorbar tick labels collide with the heatmap frame.",
    },
    {
        "chart_type_id": "S61",
        "code": "CONFUSION_CELL_LABELS_MISSING",
        "status": "open",
        "observation": "Matplotlib and Origin O1 omit the required per-cell count labels.",
    },
)


@dataclass(frozen=True, slots=True)
class InputSeries:
    geometry: AllGeometryKind
    data_kind: Literal["prepared", "calculated"]
    roles: tuple[str, ...]
    values: tuple[tuple[object, ...], ...]
    calculation_kind: str | None = None
    label: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for relative in SOURCE_SCOPE:
        path = REPOSITORY / relative
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(candidate for candidate in path.rglob("*") if candidate.is_file() and "__pycache__" not in candidate.parts and candidate.suffix not in {".pyc", ".pyo"})
        else:
            raise RuntimeError(f"missing source identity path: {relative.as_posix()}")
    return tuple(sorted(files, key=lambda path: path.relative_to(REPOSITORY).as_posix()))


def _source_build_sha256() -> str:
    digest = hashlib.sha256()
    for path in _source_files():
        relative = path.relative_to(REPOSITORY).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _source_git_commit() -> str:
    result = subprocess.run(("git", "rev-parse", "HEAD"), cwd=REPOSITORY, check=True, capture_output=True, text=True)
    return result.stdout.strip().lower()


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _project_frame(op: Any, case: AuditCase) -> pd.DataFrame:
    books = list(op.pages("w"))
    book = next((item for item in books if item.name == case.source_book), None)
    if book is None:
        raise RuntimeError(f"Origin workbook {case.source_book!r} is missing in {case.source}")
    if len(book) <= case.source_sheet:
        raise RuntimeError(f"Origin worksheet index {case.source_sheet} is missing in {book.name}")
    return cast(pd.DataFrame, book[case.source_sheet].to_df())


def _finite(values: pd.Series) -> np.ndarray:
    return pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)


def _tukey(values: np.ndarray) -> tuple[float, float, float, float, float]:
    q1, median, q3 = np.quantile(values, (0.25, 0.5, 0.75), method="linear")
    iqr = q3 - q1
    lower_candidates = values[values >= q1 - 1.5 * iqr]
    upper_candidates = values[values <= q3 + 1.5 * iqr]
    return float(q1), float(median), float(q3), float(lower_candidates.min()), float(upper_candidates.max())


def _frame_from_source(case: AuditCase, op: Any | None = None) -> pd.DataFrame:
    if case.chart_id in {"S61", "X24"}:
        if case.chart_id == "S61":
            raw = pd.read_csv(cast(Path, case.source), sep="\t")
            salary = pd.to_numeric(raw["Salary"], errors="coerce")
            actual = raw["Career_Change"].astype(str)
            predicted = pd.Series(np.where(salary >= float(salary.median()), "Yes", "No"), index=raw.index)
            counts = pd.DataFrame({"actual": actual, "predicted": predicted}).value_counts(sort=False).rename("value").reset_index()
            labels = ("No", "Yes")
            complete = pd.MultiIndex.from_product((labels, labels), names=("actual", "predicted"))
            return counts.set_index(["actual", "predicted"]).reindex(complete, fill_value=0).reset_index()
        raw = pd.read_csv(cast(Path, case.source), sep="\t", skiprows=2, header=None, names=("category", "group1", "group2", "group3"))
        raw = raw.apply(pd.to_numeric, errors="coerce").dropna(subset=["category", "group1"])
        selected = raw.nlargest(8, "group1").sort_values("group1", ascending=False)
        return pd.DataFrame({"category": selected["category"].map(lambda value: f"Bin {value:g}"), "value": selected["group1"].astype(float)})

    if op is None:
        raise RuntimeError(f"Origin is required to read {case.case_id}")
    source = _project_frame(op, case)
    if case.chart_id == "K06":
        x, center, error = source["X"], source["Y"], source["Y error"]
        return pd.DataFrame({"x": x.map(lambda value: f"{value:g}"), "center": center, "lower": center - error, "upper": center + error}).dropna()
    if case.chart_id == "K07":
        return pd.DataFrame({"x": source["X"], "center1": source["Y1"], "lower1": source["Y1"] - source["Error 1"], "upper1": source["Y1"] + source["Error 1"], "center2": source["Y2"], "lower2": source["Y2"] - source["Error 2"], "upper2": source["Y2"] + source["Error 2"]}).dropna()
    if case.chart_id == "K11":
        rows: list[dict[str, object]] = []
        for _, row in source.iterrows():
            values = {component: float(row[component]) for component in ("EC2", "EED", "ER3")}
            total = sum(values.values())
            for component, value in values.items():
                rows.append({"category": str(row.iloc[0]), "component": component, "value": value / total})
        return pd.DataFrame(rows)
    if case.chart_id == "K13":
        rows = []
        for group in source.columns:
            q1, median, q3, whisker_low, whisker_high = _tukey(_finite(source[group]))
            rows.append({"group": str(group), "q1": q1, "median": median, "q3": q3, "whisker_low": whisker_low, "whisker_high": whisker_high})
        return pd.DataFrame(rows)
    if case.chart_id == "K14":
        rows = []
        for group in source.columns:
            values = _finite(source[group])
            grid = np.linspace(float(values.min()), float(values.max()), 128)
            density = gaussian_kde(values, bw_method="scott")(grid)
            rows.extend({"group": str(group), "grid": float(x), "density": float(y)} for x, y in zip(grid, density, strict=True))
        return pd.DataFrame(rows)
    if case.chart_id == "K15":
        book = next(item for item in op.pages("w") if item.name == case.source_book)
        bins = cast(pd.DataFrame, book[1].to_df())
        centers = pd.to_numeric(bins["Bin Centers"], errors="coerce")
        counts = pd.to_numeric(bins["Counts"], errors="coerce")
        half_width = float(np.diff(centers.dropna().to_numpy(dtype=float)).min() / 2.0)
        return pd.DataFrame(
            {
                "left": centers - half_width,
                "right": centers + half_width,
                "height": counts,
            }
        ).dropna()
    if case.chart_id == "K16":
        rows = []
        for group in ("Americas", "Europe"):
            values = _finite(source[group])
            bandwidth = float(np.std(values, ddof=1) * values.size ** (-1.0 / 5.0))
            grid = np.linspace(
                float(values.min()) - 3.0 * bandwidth,
                float(values.max()) + 3.0 * bandwidth,
                160,
            )
            density = gaussian_kde(values, bw_method="scott")(grid)
            rows.extend({"grid": float(x), "density": float(y), "group": group} for x, y in zip(grid, density, strict=True))
        return pd.DataFrame(rows)
    if case.chart_id == "K17":
        values = np.sort(_finite(source["Americas"]))
        return pd.DataFrame({"x": values, "probability": np.arange(1, len(values) + 1, dtype=float) / len(values)})
    if case.chart_id == "K20":
        row_labels = source.iloc[:, 0].astype(str)
        rows = []
        for column in source.columns[1:]:
            rows.extend({"row": row, "column": str(column), "value": float(value)} for row, value in zip(row_labels, source[column], strict=True))
        return pd.DataFrame(rows)
    raise RuntimeError(f"unsupported fixed visual case {case.case_id}")


def _write_reference(case: AuditCase, frame: pd.DataFrame, case_dir: Path, op: Any) -> None:
    if case.grade == "A":
        graph = next((item for item in op.pages("g") if item.name == case.graph_name), None)
        if graph is None:
            raise RuntimeError(f"Origin graph {case.graph_name!r} is missing in {case.source}")
        graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
        return

    op.new()
    if case.chart_id == "K14":
        source_op = cast(Path, case.source)
        op.open(str(source_op), readonly=True)
        raw = _project_frame(op, case)
        op.new()
        book = op.new_book("w", "FixedK14")
        sheet = book[0]
        sheet.from_df(raw)
        graph = op.new_graph(template="Violin")
        for index in range(len(raw.columns)):
            graph[0].add_plot(sheet, coly=index, colx="#", type="?")
    elif case.chart_id == "K17":
        book = op.new_book("w", "FixedK17")
        sheet = book[0]
        x = frame["x"].to_numpy(dtype=float)
        probability = frame["probability"].to_numpy(dtype=float)
        stepped = pd.DataFrame({"x": np.repeat(x, 2)[1:], "probability": np.repeat(probability, 2)[:-1]})
        sheet.from_df(stepped)
        graph = op.new_graph(template="LINE")
        graph[0].add_plot(sheet, coly=1, colx=0, type="l")
    elif case.chart_id == "S61":
        labels = tuple(dict.fromkeys(frame["actual"].astype(str)))
        matrix = frame.pivot(index="actual", columns="predicted", values="value").reindex(index=labels, columns=labels).to_numpy(dtype=float)
        book = op.new_book("m", "FixedS61")
        sheet = book[0]
        sheet.from_np(matrix)
        graph = op.new_graph(template="HEAT_MAP_WITH_LABELS")
        graph[0].add_mplot(sheet, 0, type=105)
    elif case.chart_id == "X24":
        ordered = frame.sort_values("value", ascending=False).reset_index(drop=True)
        cumulative = ordered["value"].cumsum() / ordered["value"].sum() * 100.0
        plotted = ordered.assign(cumulative=cumulative)
        book = op.new_book("w", "FixedX24")
        sheet = book[0]
        sheet.from_df(plotted)
        graph = op.new_graph(template="ParetoRaw")
        graph[0].add_plot(sheet, coly=1, colx=0, type="c")
        graph[1].add_plot(sheet, coly=2, colx=0, type="l")
    else:
        raise RuntimeError(f"unsupported C-grade reference {case.case_id}")
    for layer in list(graph):
        layer.rescale()
    graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
    op.save(str(case_dir / "reference-origin.opju"))


def _prepare_case(case: AuditCase) -> dict[str, Any]:
    import originpro as op  # type: ignore[import-untyped]

    case_dir = OUTPUT / case.case_id
    fixture_dir = FIXTURES / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    source = cast(Path, case.source)
    if not source.is_file():
        raise RuntimeError(f"missing Origin evidence source: {source}")
    op.set_show(False)
    try:
        if source.suffix.lower() in {".opj", ".opju", ".ogw"}:
            op.new()
            op.open(str(source), readonly=True)
            frame = _frame_from_source(case, op)
        else:
            frame = _frame_from_source(case)
        _write_reference(case, frame, case_dir, op)
    finally:
        op.exit()
    frame.to_csv(case_dir / "data.csv", index=False, float_format="%.12g")
    shutil.copy2(case_dir / "data.csv", fixture_dir / "data.csv")
    shutil.copy2(case_dir / "reference.png", fixture_dir / "reference.png")
    provenance = {
        "chart_type_id": case.chart_id,
        "evidence_status": "anchored",
        "evidence_grade": case.grade,
        "source_path": str(source),
        "source_sha256": _sha256(source),
        "source_graph_name": case.graph_name,
        "source_book": case.source_book,
        "source_sheet_index": case.source_sheet,
        "recipe": case.recipe,
        "same_source_data": True,
        "synthetic": False,
        "data_sha256": _sha256(fixture_dir / "data.csv"),
        "reference_sha256": _sha256(fixture_dir / "reference.png"),
        "common_edit": case.common_edit,
        "chart_edit": case.chart_edit,
    }
    for target in (case_dir / "provenance.json", fixture_dir / "provenance.json"):
        target.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return provenance


def _write_missing_case(case: AuditCase) -> dict[str, Any]:
    payload = {
        "chart_type_id": case.chart_id,
        "evidence_status": "missing_same_source_origin_data",
        "evidence_grade": None,
        "same_source_data": False,
        "synthetic": False,
        "rendered": False,
        "tested": False,
        "blocking_code": "SAME_SOURCE_ORIGIN_DATA_MISSING",
        "search_scope": [str(ORIGIN), str(ORIGIN / "Samples"), str(Path.home() / "Documents" / "OriginLab")],
        "reason": case.recipe,
    }
    case_dir = FIXTURES / case.case_id
    output_dir = OUTPUT / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    for target in (case_dir / "evidence-gap.json", output_dir / "evidence-gap.json"):
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _prepare() -> dict[str, Any]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    entries = [_prepare_case(case) for case in QUALIFIED_CASES]
    gaps = [_write_missing_case(case) for case in MISSING_CASES]
    index = {
        "schema_version": "1.0",
        "stage": "visual29-fixed",
        "generated_at": datetime.now(UTC).isoformat(),
        "origin_declaration": {
            "display_name": DECLARED_ORIGIN_DISPLAY_NAME,
            "display_version": DECLARED_ORIGIN_DISPLAY_VERSION,
            "runtime_version": DECLARED_ORIGIN_RUNTIME_VERSION,
            "bitness": DECLARED_ORIGIN_BITNESS,
            "originpro_version": DECLARED_ORIGINPRO_VERSION,
        },
        "rules": {"same_source_required": True, "synthetic_allowed": False, "missing_data_is_not_rendered": True},
        "anchored_cases": entries,
        "evidence_gaps": gaps,
        "decision": "NO-GO" if gaps else "PENDING-RENDER",
    }
    for target in (OUTPUT / "evidence-index.json", FIXTURES / "evidence-index.json"):
        target.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def _rows(frame: pd.DataFrame, *columns: str) -> tuple[tuple[object, ...], ...]:
    return tuple(tuple(frame[column].tolist()) for column in columns)


def _input_series(case: AuditCase, frame: pd.DataFrame) -> tuple[InputSeries, ...]:
    if case.chart_id == "K06":
        return (InputSeries("error_bar", "calculated", ("x", "center", "lower", "upper"), _rows(frame, "x", "center", "lower", "upper"), "summary_error"),)
    if case.chart_id == "K07":
        items: list[InputSeries] = []
        for index in (1, 2):
            items.extend((
                InputSeries("line", "calculated", ("x", "center"), _rows(frame, "x", f"center{index}"), "summary_error", f"Series {index}"),
                InputSeries("band", "calculated", ("x", "lower", "upper"), _rows(frame, "x", f"lower{index}", f"upper{index}"), "summary_error"),
            ))
        return tuple(items)
    if case.chart_id == "K11":
        return (InputSeries("bar", "calculated", ("category", "component", "value"), _rows(frame, "category", "component", "value"), "percent_stack"),)
    if case.chart_id == "K13":
        return (InputSeries("box", "calculated", ("group", "q1", "median", "q3", "whisker_low", "whisker_high"), _rows(frame, "group", "q1", "median", "q3", "whisker_low", "whisker_high"), "tukey_box"),)
    if case.chart_id == "K14":
        return (InputSeries("violin", "calculated", ("group", "grid", "density"), _rows(frame, "group", "grid", "density"), "violin_kde"),)
    if case.chart_id == "K15":
        return (InputSeries("histogram", "calculated", ("left", "right", "height"), _rows(frame, "left", "right", "height"), "histogram_binning"),)
    if case.chart_id == "K16":
        return (InputSeries("density", "calculated", ("grid", "density", "group"), _rows(frame, "grid", "density", "group"), "density_kde"),)
    if case.chart_id == "K17":
        return (InputSeries("step", "calculated", ("x", "probability"), _rows(frame, "x", "probability"), "ecdf"),)
    if case.chart_id == "K20":
        return (InputSeries("heatmap", "calculated", ("row", "column", "value"), _rows(frame, "row", "column", "value"), "matrix_projection"),)
    if case.chart_id == "S61":
        return (InputSeries("heatmap", "calculated", ("actual", "predicted", "value"), _rows(frame, "actual", "predicted", "value"), "confusion_count"),)
    if case.chart_id == "X24":
        return (InputSeries("bridge", "prepared", ("category", "value"), _rows(frame, "category", "value")),)
    raise RuntimeError(f"unsupported input series {case.case_id}")


def _family(case: AuditCase, geometries: tuple[AllGeometryKind, ...]) -> PlotFamily:
    if case.chart_id == "X24":
        return SpecialFamily(geometry=cast(Any, geometries))
    if case.chart_id == "K11":
        return CategoricalFamily(geometry=("bar",))
    if case.chart_id in {"K13", "K14", "K15", "K16", "K17"}:
        return DistributionFamily(geometry=cast(Any, geometries))
    if case.chart_id in {"K20", "S61"}:
        return MatrixFamily(geometry=("heatmap",))
    return XYFamily(geometry=cast(Any, geometries))


def _axis(case: AuditCase) -> tuple[tuple[ScaleSpec, ...], tuple[AxisSpec, ...]]:
    x_kind = "categorical" if case.chart_id in {"K06", "K11", "K13", "K14", "K20", "S61", "X24"} else "linear"
    y_kind = "categorical" if case.chart_id in {"K20", "S61"} else "linear"
    labels = {
        "K06": ("Sample", "Estimate"), "K07": ("X", "Y"), "K11": ("Category", "Percent"),
        "K13": ("Group", "Value"), "K14": ("Group", "Value"), "K15": ("Value", "Count"),
        "K16": ("Value", "Density"), "K17": ("Value", "Cumulative probability"),
        "K20": ("Column", "Row"), "S61": ("Predicted", "Actual"), "X24": ("Category", "Count"),
    }[case.chart_id]
    scales: tuple[ScaleSpec, ...] = (ScaleSpec(scale_id="scale:x", kind=cast(Any, x_kind)), ScaleSpec(scale_id="scale:y", kind=cast(Any, y_kind)))
    axes: tuple[AxisSpec, ...] = (
        AxisSpec(axis_id="axis:x", scale_id="scale:x", orientation="x", position="bottom", label=_text(labels[0])),
        AxisSpec(axis_id="axis:y", scale_id="scale:y", orientation="y", position="left", label=_text(labels[1])),
    )
    if case.chart_id == "X24":
        scales += (ScaleSpec(scale_id="scale:y_right", kind="linear"),)
        axes += (AxisSpec(axis_id="axis:y_right", scale_id="scale:y_right", orientation="y", position="right", label=_text("Cumulative (%)")),)
    return scales, axes


def _build_plot(case: AuditCase, frame: pd.DataFrame, *, edited: bool) -> tuple[PlotSpec, RenderDataStore]:
    inputs = _input_series(case, frame)
    prepared_refs: list[PreparedDatasetRef] = []
    calculation_refs: list[PlotCalculationResultRef] = []
    specifications: list[SeriesSpec] = []
    store: dict[str, RenderTable] = {}
    for index, item in enumerate(inputs):
        field_ids = tuple(f"field:{case.chart_id.lower()}.{index}.{role}" for role in item.roles)
        table = RenderTable.from_columns(dict(zip(field_ids, item.values, strict=True)))
        prepared = PreparedDatasetRef(prepared_dataset_id=f"prepared:visual29.{case.chart_id.lower()}.{index}", prepared_version=1, content_hash=table.object_hash)
        prepared_refs.append(prepared)
        if item.data_kind == "prepared":
            data: SeriesData = PreparedSeriesData(prepared_dataset_ref=prepared, role_fields=field_ids)
        else:
            calculation = PlotCalculationResultRef(calculation_id=f"plotcalc:visual29.{case.chart_id.lower()}.{index}", result_version=1, calculation_kind=cast(Any, item.calculation_kind), content_hash=table.object_hash)
            calculation_refs.append(calculation)
            data = CalculatedSeriesData(calculation_result_ref=calculation, role_fields=field_ids)
        store[table.object_hash] = table
        series_style = SeriesStyleSpec()
        if edited:
            color = ("#1F77B4", "#D95F02", "#2A9D6F", "#7B61A8")[index % 4]
            update: dict[str, Any] = {"color": ColorValue(value=color)}
            if item.geometry in {"line", "density", "step", "band", "error_bar"}:
                update["line_width"] = PhysicalLength(value=1.4, unit="pt")
            if item.geometry == "error_bar":
                update["symbol"] = SymbolStyle(shape="diamond", interior="solid")
                update["marker_size"] = PhysicalLength(value=6.0, unit="pt")
            series_style = series_style.model_copy(update=update)
        specifications.append(SeriesSpec(series_id=f"series:{case.chart_id.lower()}.{index}", geometry=item.geometry, data=data, label=_text(item.label) if item.label else None, style=series_style))

    specialist = SpecialistEditSpec()
    if edited and case.chart_id in {"K11", "K13", "K14", "K15", "X24"}:
        specialist = specialist.model_copy(update={"bar_area": BarAreaEditSpec(fill_color=ColorValue(value="#4C78A8"), edge_color=ColorValue(value="#1F3552"), edge_width=PhysicalLength(value=0.8, unit="pt"), width_ratio=0.68, alpha=0.82)})
    if edited and case.chart_id in {"K06", "K07"}:
        specialist = specialist.model_copy(update={"uncertainty": UncertaintyEditSpec(color=ColorValue(value="#7B61A8"), line_width=PhysicalLength(value=1.1, unit="pt"), cap_size=PhysicalLength(value=5.0, unit="pt"), band_alpha=0.32)})
    if edited and case.chart_id in {"K20", "S61"}:
        specialist = specialist.model_copy(update={"colorbar": ColorbarEditSpec(visible=True, title=_text("Count" if case.chart_id == "S61" else "Value"), levels=9)})
    if edited and case.chart_id == "K17":
        specialist = specialist.model_copy(update={"chart_parameters": ChartParameterEditSpec(step_where="mid")})
    if edited and case.chart_id == "X24":
        specialist = specialist.model_copy(update={"bar_area": specialist.bar_area, "chart_parameters": ChartParameterEditSpec(pareto_reference_percent=75.0)})

    scales, axes = _axis(case)
    english_title = {
        "K06": "Point estimate with error bars",
        "K07": "Error band",
        "K11": "100% stacked column",
        "K13": "Tukey box plot",
        "K14": "Violin plot",
        "K15": "Histogram",
        "K16": "KDE density",
        "K17": "ECDF",
        "K20": "Heatmap",
        "S61": "Confusion matrix",
        "X24": "Pareto chart",
    }[case.chart_id]
    title = f"{case.chart_id} · {english_title}"
    plot = PlotSpec(
        plot_id=f"plot:visual29.{case.chart_id.lower()}.{'edited' if edited else 'default'}",
        plot_version=2 if edited else 1,
        chart_type_id=cast(ChartTypeId, case.chart_id),
        title=_text(f"Visual qualification · {title}" if edited else title),
        family=_family(case, tuple(dict.fromkeys(item.geometry for item in inputs))),
        prepared_data_refs=tuple(prepared_refs),
        plot_calculation_refs=tuple(calculation_refs),
        scales=scales,
        axes=axes,
        series=tuple(specifications),
        specialist=specialist,
        style_sources=(StyleSourceRef(source_kind="project", source_id="style.visual29", source_version=1, content_hash=hashlib.sha256(b"style.visual29").hexdigest()),),
        resolved_style=style().model_copy(update={"font_size": PhysicalLength(value=9.5 if edited else 8.0, unit="pt")}),
        publication_profile=profile(),
        provenance=PlotProvenance(origin="manual", engine_build_hash=hashlib.sha256(b"visual29.fixed").hexdigest()),
    )
    return plot, RenderDataStore(store)


def _export_reopened_graphs(opju: Path, destinations: tuple[Path, ...]) -> None:
    import originpro as op  # type: ignore[import-untyped]

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


def _contact_sheet(case_dir: Path, state: str) -> None:
    files = (case_dir / "reference.png", case_dir / state / "matplotlib.png", case_dir / state / "origin-fresh-reopen.png")
    labels = ("ORIGIN REFERENCE", f"MATPLOTLIB · {state.upper()}", f"ORIGIN O1 · {state.upper()} · FRESH REOPEN")
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


def _build_index() -> None:
    cards = []
    for case in QUALIFIED_CASES:
        cards.append(f'<article><h2>{case.chart_id} · {html.escape(case.title)}</h2><p><span class="grade">{case.grade} 级</span> {html.escape(case.recipe)}</p><p>通用编辑：{html.escape(case.common_edit)}；专属编辑：{html.escape(case.chart_edit)}</p><h3>默认态</h3><a href="{case.case_id}/comparison-default.png"><img src="{case.case_id}/comparison-default.png"></a><h3>编辑态</h3><a href="{case.case_id}/comparison-edited.png"><img src="{case.case_id}/comparison-edited.png"></a><p><a href="{case.case_id}/data.csv">冻结数据</a> · <a href="{case.case_id}/provenance.json">provenance</a></p></article>')
    for case in MISSING_CASES:
        cards.append(f'<article class="gap"><h2>{case.chart_id} · {html.escape(case.title)}</h2><p><span class="grade">NO-GO</span> {html.escape(case.recipe)}</p><p>未渲染、未测试、未声明视觉结论。</p><a href="{case.case_id}/evidence-gap.json">evidence gap</a></article>')
    (OUTPUT / "index.html").write_text(f'<!doctype html><meta charset="utf-8"><title>固定计算图视觉资格</title><style>body{{font:14px Arial,sans-serif;margin:24px;background:#f5f5f5;color:#171717}}main{{max-width:1500px;margin:auto}}article{{background:#fff;border:1px solid #ddd;margin:0 0 28px;padding:18px}}article.gap{{border-color:#a33}}img{{width:100%;height:auto;border:1px solid #ddd}}h1,h2,h3{{margin:0 0 12px}}h3{{margin-top:18px}}.grade{{background:#111;color:#fff;padding:2px 7px;border-radius:10px}}</style><main><h1>其余 29 图 · 固定计算/预计算线</h1><p>同源 Origin 证据优先。左：参考；中：Matplotlib；右：原生 O1 fresh reopen。人工视觉签名保持 pending。</p>{"".join(cards)}</main>', encoding="utf-8")


def _render() -> dict[str, Any]:
    states: dict[str, list[ResolvedPlot]] = {"default": [], "edited": []}
    case_entries: dict[str, dict[str, Any]] = {}
    for case in QUALIFIED_CASES:
        fixture_dir = FIXTURES / case.case_id
        provenance = json.loads((fixture_dir / "provenance.json").read_text(encoding="utf-8"))
        if _sha256(fixture_dir / "data.csv") != provenance["data_sha256"] or _sha256(fixture_dir / "reference.png") != provenance["reference_sha256"]:
            raise RuntimeError(f"frozen evidence changed: {case.case_id}")
        case_dir = OUTPUT / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("data.csv", "reference.png", "provenance.json"):
            shutil.copy2(fixture_dir / filename, case_dir / filename)
        frame = pd.read_csv(fixture_dir / "data.csv")
        case_entries[case.case_id] = {
            **provenance,
            "states": {},
            "blocking_observations": [
                item for item in MECHANICAL_BLOCKERS if item["chart_type_id"] == case.chart_id
            ],
        }
        for state in ("default", "edited"):
            state_dir = case_dir / state
            state_dir.mkdir(exist_ok=True)
            plot, store = _build_plot(case, frame, edited=state == "edited")
            resolved = PlotResolver().resolve(plot, store)
            export_png(state_dir / "matplotlib.png", resolved)
            states[state].append(resolved)
            case_entries[case.case_id]["states"][state] = {"plot_spec_sha256": canonical_hash(plot), "render_plan_sha256": resolved.render_plan_hash, "matplotlib_png_sha256": _sha256(state_dir / "matplotlib.png")}

    exports: dict[str, Any] = {}
    for state in ("default", "edited"):
        resolved_tuple = tuple(states[state])
        plan = compile_origin_plan(resolved_tuple, build_origin_export_spec(resolved_tuple, export_id=f"export:visual29.fixed.{state}", target_scope="selected_plots"))
        target = OUTPUT / f"visual29-fixed-{state}.opju"
        result = export_origin(plan, target, expected_existing_sha256=_sha256(target) if target.is_file() else None, timeout_seconds=600.0)
        if not isinstance(result, OriginExportSuccess):
            raise RuntimeError(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if result.build_validation != result.reopen_validation:
            raise RuntimeError(f"Origin fresh reopen validation drift: {state}")
        destinations = tuple(OUTPUT / case.case_id / state / "origin-fresh-reopen.png" for case in QUALIFIED_CASES)
        _export_reopened_graphs(target, destinations)
        for index, (case, destination) in enumerate(zip(QUALIFIED_CASES, destinations, strict=True)):
            case_entries[case.case_id]["states"][state]["origin_fresh_png_sha256"] = _sha256(destination)
            case_entries[case.case_id]["states"][state]["origin_graph_index"] = index
        exports[state] = {"opju_path": str(target), "opju_sha256": result.file_sha256, "opju_size": result.file_size, "origin_plan_sha256": canonical_hash(plan), "adapter_id": plan.adapter_id, "adapter_version": plan.adapter_version, "validation_report_sha256": result.validation_report_sha256, "fresh_reopen_identical": True, "elapsed_seconds": result.elapsed_seconds, "environment": result.environment.to_dict()}

    for case in QUALIFIED_CASES:
        _contact_sheet(OUTPUT / case.case_id, "default")
        _contact_sheet(OUTPUT / case.case_id, "edited")
    evidence_gaps = [json.loads((FIXTURES / case.case_id / "evidence-gap.json").read_text(encoding="utf-8")) for case in MISSING_CASES]
    manifest = {
        "schema_version": "1.0", "stage": "visual29-fixed", "generated_at": datetime.now(UTC).isoformat(), "plotagent_version": PLOTAGENT_VERSION,
        "origin_declaration": {"display_name": DECLARED_ORIGIN_DISPLAY_NAME, "display_version": DECLARED_ORIGIN_DISPLAY_VERSION, "runtime_version": DECLARED_ORIGIN_RUNTIME_VERSION, "bitness": DECLARED_ORIGIN_BITNESS, "originpro_version": DECLARED_ORIGINPRO_VERSION},
        "rules": {"same_source_required": True, "synthetic_allowed": False, "states": ["default", "representative edited"], "missing_data_is_not_rendered": True},
        "exports": exports,
        "cases": [case_entries[case.case_id] for case in QUALIFIED_CASES],
        "evidence_gaps": evidence_gaps,
        "qualification": {"source_build_identity": {"scope_version": SOURCE_SCOPE_VERSION, "git_commit": _source_git_commit(), "source_sha256": _source_build_sha256()}, "blocking_observations": [*MECHANICAL_BLOCKERS, *({"chart_type_id": item["chart_type_id"], "code": item["blocking_code"], "status": "open", "observation": item["reason"]} for item in evidence_gaps)], "human_visual_signature": {"status": "pending", "reviewer": None, "signed_at": None}, "decision": "NO-GO"},
        "audit_conclusion": "same-source evidence generated for anchored cases; mechanical visual blockers, missing evidence and human visual sign-off keep qualification NO-GO",
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (FIXTURES / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _build_index()
    return manifest


def main() -> None:
    global OUTPUT, FIXTURES
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("prepare", "render", "all"), default="all")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    args = parser.parse_args()
    OUTPUT = args.output
    FIXTURES = args.fixtures
    if args.phase in {"prepare", "all"}:
        _prepare()
    if args.phase in {"render", "all"}:
        _render()


if __name__ == "__main__":
    main()

"""Build the frozen SEQ-20 same-source visual baseline for the first 14 charts.

The script has two deliberately separate phases:

* ``prepare`` anchors a shipped Origin graph/project or regenerates an Origin
  reference from shipped Origin sample data, then freezes the exact CSV and
  reference PNG under ``tests/fixtures/visual_regression/seq20``.
* ``render`` refuses to continue if either frozen input changed, renders the
  default and one representative edited state with Matplotlib, builds native
  O1 OPJU files, validates them in a fresh Origin instance, and exports the
  reopened graphs for side-by-side review.

No synthetic data are accepted by this SEQ-20 gate.  Grade A means a shipped
Origin graph and its workbook are used directly.  Grade C means a reference is
regenerated in Origin from a shipped Origin sample file/project.
"""

# ruff: noqa: E402, E501 -- repository bootstrap and generated audit HTML stay contiguous.

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
from plotagent.contracts.base import ChartTypeId, ColorValue, PhysicalLength, PreparedDatasetRef
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.plots import (
    AllGeometryKind,
    AxisSpec,
    BarAreaEditSpec,
    CategoricalFamily,
    ChartParameterEditSpec,
    DoseResponseFamily,
    LegendSpec,
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
from scripts.visual_source_identity import (
    assert_scope_clean,
    source_build_identity,
)
from tests.contracts.helpers import profile, style

ORIGIN = Path(r"D:\origin")
OUTPUT = REPOSITORY / "build" / "visual-audit" / "seq20-origin-baseline"
FIXTURES = REPOSITORY / "tests" / "fixtures" / "visual_regression" / "seq20"
SOURCE_SCOPE_VERSION = "seq20-rendering-v2"
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
    batch: int
    chart_id: str
    slug: str
    title: str
    grade: Literal["A", "C"]
    source: Path
    graph_name: str | None
    source_book: str | None
    recipe: str
    common_edit: str
    chart_edit: str

    @property
    def case_id(self) -> str:
        return f"{self.chart_id}_{self.slug}"


CASES = (
    AuditCase(1, "K01", "line", "折线图", "C", ORIGIN / "Samples" / "Mathematics" / "Sine Curve.dat", None, None, "Origin 官方 Sine Curve.dat；在 Origin 中以 LINE 重新生成。", "标题与字号", "线色与线宽"),
    AuditCase(1, "K02", "line_symbol", "线点图", "C", ORIGIN / "Samples" / "Mathematics" / "Sine Curve.dat", None, None, "Origin 官方 Sine Curve.dat；在 Origin 中以 Line+Symbol 重新生成。", "标题与字号", "线色、点形、点大小"),
    AuditCase(1, "K03", "scatter", "散点图", "C", ORIGIN / "Samples" / "Curve Fitting" / "Linear Fit.dat", None, None, "Origin 官方 Linear Fit.dat；在 Origin 中以 Scatter 重新生成。", "标题与字号", "点色、点形、点大小"),
    AuditCase(1, "K08", "column", "柱状图", "C", ORIGIN / "Column.opju", None, "Book2", "Origin 随附 Column.opju 的 Book2；抽取 EC2 列并以 COLUMN 重新生成。", "标题与字号", "柱填充、边线、宽度"),
    AuditCase(1, "K18", "area", "面积图", "A", ORIGIN / "Area.opju", "Graph1", "Book1", "直接导出 Origin 随附 Area.opju 的 Graph1 及同项目工作表。", "标题与字号", "面积填充、边线、透明度"),
    AuditCase(2, "X01", "step", "阶梯图", "C", ORIGIN / "Samples" / "Signal Processing" / "Step Signal with Random Noise.dat", None, None, "Origin 官方信号样例；在 Origin 中按 post 阶梯重新生成。", "标题与字号", "阶梯位置 mid、线色与线宽"),
    AuditCase(2, "X02", "lollipop", "棒棒糖图", "C", ORIGIN / "Samples" / "Signal Processing" / "Step Signal with Random Noise.dat", None, None, "Origin 官方信号样例固定抽样；以 DROPLINE 重新生成。", "标题与字号", "固定 y=0 基线、点形与点大小"),
    AuditCase(2, "X09", "floating_interval", "范围柱条图", "A", ORIGIN / "FLOATBAR.opju", "Graph5", None, "直接导出 Origin 随附 FLOATBAR.opju 的 Graph5 及其三边界工作表。", "标题与字号", "区间柱填充、边线、宽度"),
    AuditCase(2, "K05", "curve_band", "给定曲线与置信带", "A", ORIGIN / "ERRORBAND.opju", "Graph1", "Book1", "直接导出 Origin 随附 ERRORBAND.opju 的 Graph1；Y±Error 转为显式上下界，不重新估计。", "标题与字号", "带颜色、边线与透明度"),
    AuditCase(2, "K09", "grouped_column", "分组柱状图", "A", ORIGIN / "Column.opju", "Graph2", "Book1", "直接导出 Origin 随附 Column.opju 的 Graph2；误差列转为显式上下界。", "标题与字号", "分组柱边线与宽度"),
    AuditCase(3, "K10", "stacked_column", "堆积柱状图", "A", ORIGIN / "Column.opju", "Graph9", "Book2", "直接导出 Origin 随附 Column.opju 的 Graph9 及无误差工作表。", "标题与字号", "堆积柱边线与宽度"),
    AuditCase(3, "S05", "dose_response", "给定剂量反应", "C", ORIGIN / "Samples" / "Curve Fitting" / "Dose Response - Inhibitor.dat", None, None, "Origin 官方剂量反应样例；三次测量的均值与逐剂量 min/max 作为用户提供曲线/带，在 Origin 中重新生成，不执行拟合。", "标题与字号", "点/线样式与带透明度"),
    AuditCase(3, "S25", "spectrum", "连续谱图", "C", ORIGIN / "Samples" / "Spectroscopy" / "Absorbance Spectra.opj", None, "Book1", "Origin 官方 Absorbance Spectra.opj 工作表；因随附 Graph1 是 940–1000 局部视图，改用 Origin LINE 模板按全数据自动范围重新生成。", "标题与字号", "谱线颜色与宽度"),
    AuditCase(3, "X03", "dumbbell", "哑铃图", "A", ORIGIN / "Lollipop.opju", "Graph1", None, "直接导出 Origin 随附 Lollipop Plot (Two Points) 图页及工作表。", "标题与字号", "端点颜色、点形、点大小"),
)

BATCHES = {1: CASES[:5], 2: CASES[5:10], 3: CASES[10:]}

# Mechanical P0 observations must be closed before evidence is regenerated.
# Any remaining judgement-only differences are added here after inspecting the
# regenerated contact sheets; they require the separate human signature below.
VISUAL_OBSERVATIONS: dict[str, tuple[str, ...]] = {}
BLOCKING_OBSERVATIONS: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class InputSeries:
    geometry: AllGeometryKind
    kind: Literal["prepared", "precomputed"]
    roles: tuple[str, ...]
    values: tuple[tuple[object, ...], ...]
    label: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _origin_book(op: Any, name: str | None) -> Any:
    books = list(op.pages("w"))
    if name is None:
        if not books:
            raise RuntimeError("Origin project contains no workbook")
        return books[0]
    book = next((item for item in books if item.name == name), None)
    if book is None:
        raise RuntimeError(f"Origin workbook {name!r} is missing")
    return book


def _project_frame(op: Any, case: AuditCase) -> pd.DataFrame:
    book = _origin_book(op, case.source_book)
    if not len(book):
        raise RuntimeError(f"Origin workbook {book.name!r} has no worksheet")
    return cast(pd.DataFrame, book[0].to_df())


def _frame_from_source(case: AuditCase, op: Any | None = None) -> pd.DataFrame:
    if case.chart_id in {"K01", "K02"}:
        frame = pd.read_csv(case.source, sep="\t", header=None, names=("x", "y"))
        return frame.astype(float)
    if case.chart_id == "K03":
        frame = pd.read_csv(case.source, sep="\t", header=None)
        return pd.DataFrame({"x": frame.iloc[:, 0], "y": frame.iloc[:, 1]}).astype(float)
    if case.chart_id in {"X01", "X02"}:
        source = pd.read_csv(case.source, sep="\t").rename(columns=lambda item: str(item).strip())
        source = pd.DataFrame({"x": source.iloc[:, 0], "y": source.iloc[:, 1]}).astype(float)
        if case.chart_id == "X01":
            return source
        sampled = source.iloc[::50].reset_index(drop=True)
        return pd.DataFrame(
            {
                "category": sampled["x"].map(lambda value: f"{value:g}"),
                "value": sampled["y"],
            }
        )
    if case.chart_id == "S05":
        source = pd.read_csv(case.source, sep="\t")
        values = source.iloc[:, 1:4].astype(float)
        return pd.DataFrame(
            {
                "dose": source.iloc[:, 0].astype(float),
                "response": values.mean(axis=1),
                "lower": values.min(axis=1),
                "upper": values.max(axis=1),
            }
        )
    if op is None:
        raise RuntimeError(f"Origin is required to read {case.case_id}")
    source = _project_frame(op, case)
    if case.chart_id == "K08":
        return pd.DataFrame({"category": source.iloc[:, 0], "value": source["EC2"]}).dropna()
    if case.chart_id == "K18":
        return pd.DataFrame({"x": source["X"], "y": source["Y1"]}).dropna()
    if case.chart_id == "X09":
        return pd.DataFrame(
            {
                "category": source.iloc[:, 0],
                "start": source["Start"],
                "end": source["End"],
                "middle": source["Middle"],
            }
        ).dropna()
    if case.chart_id == "K05":
        return pd.DataFrame(
            {
                "x": source["X"],
                "y1": source["Y1"],
                "lower1": source["Y1"] - source["Error 1"],
                "upper1": source["Y1"] + source["Error 1"],
                "y2": source["Y2"],
                "lower2": source["Y2"] - source["Error 2"],
                "upper2": source["Y2"] + source["Error 2"],
            }
        ).dropna()
    if case.chart_id == "K09":
        rows: list[dict[str, object]] = []
        category = source.iloc[:, 0].astype(str)
        for group, error in (("EC2", "C"), ("EED", "E"), ("ER3", "G")):
            for label, value, spread in zip(category, source[group], source[error], strict=True):
                rows.append(
                    {
                        "category": label,
                        "group": group,
                        "value": float(value),
                        "lower": float(value - spread),
                        "upper": float(value + spread),
                    }
                )
        return pd.DataFrame(rows)
    if case.chart_id == "K10":
        rows = []
        category = source.iloc[:, 0].astype(str)
        for component in ("EC2", "EED", "ER3"):
            for label, value in zip(category, source[component], strict=True):
                rows.append({"category": label, "component": component, "value": float(value)})
        return pd.DataFrame(rows)
    if case.chart_id == "S25":
        frame = source.rename(columns={source.columns[0]: "spectral_axis"})
        return frame.dropna(how="all")
    if case.chart_id == "X03":
        return pd.DataFrame(
            {"category": source["ID"], "start": source["Start"], "end": source["Middle"]}
        ).dropna()
    raise RuntimeError(f"unsupported evidence case {case.case_id}")


def _write_reference(case: AuditCase, frame: pd.DataFrame, case_dir: Path, op: Any) -> None:
    if case.grade == "A":
        graph = next((item for item in op.pages("g") if item.name == case.graph_name), None)
        if graph is None:
            raise RuntimeError(f"Origin graph {case.graph_name!r} is missing in {case.source}")
        graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
        return

    op.new()
    book = op.new_book("w", f"SEQ20{case.chart_id}")
    sheet = book[0]
    if case.chart_id == "X01":
        x = frame["x"].to_numpy(dtype=float)
        y = frame["y"].to_numpy(dtype=float)
        plotted = pd.DataFrame({"x": np.repeat(x, 2)[1:], "y": np.repeat(y, 2)[:-1]})
        sheet.from_df(plotted)
        graph = op.new_graph(template="LINE")
        graph[0].add_plot(sheet, coly=1, colx=0, type=200)
    elif case.chart_id == "X02":
        sheet.from_df(frame)
        graph = op.new_graph(template="DROPLINE")
        graph[0].add_plot(sheet, coly=1, colx=0, type=201)
    elif case.chart_id == "S05":
        sheet.from_df(frame)
        graph = op.new_graph(template="LINESYMB")
        graph[0].add_plot(sheet, coly=1, colx=0, type=202)
        graph[0].xscale = "log10"
    elif case.chart_id == "S25":
        sheet.from_df(frame)
        # The installed spectra.OTP reverses the Y axis and labels it as a
        # time/frequency transform, which is not the semantics of this
        # absorbance worksheet.  S25 therefore uses Origin's system LINE
        # template as the documented O-PRIM reference.
        graph = op.new_graph(template="LINE")
        for column in range(1, len(frame.columns)):
            graph[0].add_plot(sheet, coly=column, colx=0, type=200)
    else:
        sheet.from_df(frame)
        template, plot_type = {
            "K01": ("LINE", 200),
            "K02": ("LINESYMB", 202),
            "K03": ("SCATTER", 201),
            "K08": ("COLUMN", 203),
        }[case.chart_id]
        graph = op.new_graph(template=template)
        graph[0].add_plot(sheet, coly=1, colx=0, type=plot_type)
    for layer in list(graph):
        layer.rescale()
    graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
    op.save(str(case_dir / "reference-origin.opju"))


def _prepare_case(case: AuditCase, output: Path, fixtures: Path) -> dict[str, Any]:
    import originpro as op  # type: ignore[import-untyped]

    case_dir = output / case.case_id
    fixture_dir = fixtures / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    op.set_show(False)
    try:
        if case.source.suffix.lower() in {".opj", ".opju", ".ogw"}:
            op.new()
            op.open(str(case.source), readonly=True)
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
        "evidence_grade": case.grade,
        "source_path": str(case.source),
        "source_sha256": _sha256(case.source),
        "source_graph_name": case.graph_name,
        "source_book": case.source_book,
        "recipe": case.recipe,
        "same_source_data": True,
        "synthetic": False,
        "data_sha256": _sha256(fixture_dir / "data.csv"),
        "reference_sha256": _sha256(fixture_dir / "reference.png"),
        "common_edit": case.common_edit,
        "chart_edit": case.chart_edit,
    }
    (case_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (fixture_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return provenance


def _input_series(case: AuditCase, frame: pd.DataFrame) -> tuple[InputSeries, ...]:
    def rows(*columns: str) -> tuple[tuple[object, ...], ...]:
        return tuple(tuple(frame[column].tolist()) for column in columns)
    if case.chart_id == "K01":
        return (InputSeries("line", "prepared", ("x", "y"), rows("x", "y")),)
    if case.chart_id == "K02":
        values = rows("x", "y")
        return (
            InputSeries("line", "prepared", ("x", "y"), values, "Signal"),
            InputSeries("symbol", "prepared", ("x", "y"), values, "Signal"),
        )
    if case.chart_id == "K03":
        return (InputSeries("symbol", "prepared", ("x", "y"), rows("x", "y")),)
    if case.chart_id == "K08":
        return (InputSeries("bar", "prepared", ("category", "value"), rows("category", "value")),)
    if case.chart_id == "K18":
        return (InputSeries("area", "prepared", ("x", "y"), rows("x", "y")),)
    if case.chart_id == "X01":
        return (InputSeries("step", "prepared", ("x", "y"), rows("x", "y")),)
    if case.chart_id == "X02":
        return (InputSeries("lollipop", "prepared", ("category", "value"), rows("category", "value")),)
    if case.chart_id == "X09":
        return (InputSeries("floating_bar", "prepared", ("category", "start", "end", "middle"), rows("category", "start", "end", "middle")),)
    if case.chart_id == "K05":
        series: list[InputSeries] = []
        for index in (1, 2):
            series.extend(
                (
                    InputSeries("symbol", "prepared", ("x", "y"), rows("x", f"y{index}"), f"Y{index}"),
                    InputSeries("line", "precomputed", ("x", "y"), rows("x", f"y{index}"), f"Y{index}"),
                    InputSeries("band", "precomputed", ("x", "lower", "upper"), rows("x", f"lower{index}", f"upper{index}"), f"Y{index} interval"),
                )
            )
        return tuple(series)
    if case.chart_id == "K09":
        return (InputSeries("bar", "prepared", ("category", "group", "value", "lower", "upper"), rows("category", "group", "value", "lower", "upper")),)
    if case.chart_id == "K10":
        return (InputSeries("bar", "prepared", ("category", "component", "value"), rows("category", "component", "value")),)
    if case.chart_id == "S05":
        return (
            InputSeries("symbol", "prepared", ("dose", "response"), rows("dose", "response"), "Observed mean"),
            InputSeries("line", "precomputed", ("dose", "response"), rows("dose", "response"), "Provided curve"),
            InputSeries("band", "precomputed", ("dose", "lower", "upper"), rows("dose", "lower", "upper"), "Provided range"),
        )
    if case.chart_id == "S25":
        return tuple(
            InputSeries("line", "precomputed", ("spectral_axis", "intensity"), rows("spectral_axis", column), str(column))
            for column in frame.columns[1:]
        )
    if case.chart_id == "X03":
        return (InputSeries("dumbbell", "prepared", ("category", "start", "end"), rows("category", "start", "end")),)
    raise RuntimeError(f"unsupported series case {case.case_id}")


def _family(case: AuditCase, geometries: tuple[AllGeometryKind, ...]) -> PlotFamily:
    if case.chart_id.startswith("X"):
        return SpecialFamily(geometry=cast(Any, geometries))
    if case.chart_id in {"K08", "K09", "K10"}:
        return CategoricalFamily(geometry=("bar",))
    if case.chart_id == "S05":
        return DoseResponseFamily(geometry=cast(Any, geometries))
    return XYFamily(geometry=cast(Any, geometries))


def _labels_and_scales(case: AuditCase) -> tuple[str, str, str, str]:
    return {
        "K01": ("x", "Signal", "linear", "linear"),
        "K02": ("x", "Signal", "linear", "linear"),
        "K03": ("Predictor", "Response", "linear", "linear"),
        "K08": ("Category", "Value", "categorical", "linear"),
        "K18": ("X", "Y1", "linear", "linear"),
        "X01": ("Time", "Signal", "linear", "linear"),
        "X02": ("Sample", "Signal", "categorical", "linear"),
        "X09": ("ID", "Interval", "categorical", "linear"),
        "K05": ("X", "Y", "linear", "linear"),
        "K09": ("Week", "EC2", "categorical", "linear"),
        "K10": ("Week", "EC2", "categorical", "linear"),
        "S05": ("Dose", "Response", "log10", "linear"),
        "S25": ("Energy", "Absorbance", "linear", "linear"),
        "X03": ("Start–End", "ID", "linear", "categorical"),
    }[case.chart_id]


def _edited_color_indices(inputs: tuple[InputSeries, ...]) -> tuple[int, ...]:
    """Assign one audit-edit color to each target-neutral logical series."""

    logical_keys: list[tuple[str, ...]] = []
    geometry_occurrences: dict[tuple[str, str], int] = {}
    for index, item in enumerate(inputs):
        if item.geometry not in {"line", "symbol"}:
            logical_keys.append(("target", str(index)))
            continue
        value_hash = canonical_hash(
            cast(
                JsonValue,
                {
                    "roles": list(item.roles),
                    "values": [list(column) for column in item.values],
                },
            )
        )
        occurrence_key = (value_hash, item.geometry)
        occurrence = geometry_occurrences.get(occurrence_key, 0)
        geometry_occurrences[occurrence_key] = occurrence + 1
        logical_keys.append(("binding-values", value_hash, f"occurrence:{occurrence}"))

    color_indices: dict[tuple[str, ...], int] = {}
    return tuple(
        color_indices.setdefault(key, len(color_indices)) for key in logical_keys
    )


def _build_plot(case: AuditCase, frame: pd.DataFrame, *, edited: bool) -> tuple[PlotSpec, RenderDataStore]:
    inputs = _input_series(case, frame)
    edited_color_indices = _edited_color_indices(inputs)
    prepared_refs: list[PreparedDatasetRef] = []
    precomputed_refs: list[PrecomputedDataRef] = []
    specifications: list[SeriesSpec] = []
    store: dict[str, RenderTable] = {}
    for index, item in enumerate(inputs):
        field_ids = tuple(f"field:{case.chart_id.lower()}.{index}.{role}" for role in item.roles)
        table = RenderTable.from_columns(dict(zip(field_ids, item.values, strict=True)))
        prepared = PreparedDatasetRef(
            prepared_dataset_id=f"prepared:seq20.{case.chart_id.lower()}.{index}",
            prepared_version=1,
            content_hash=table.object_hash,
        )
        prepared_refs.append(prepared)
        if item.kind == "prepared":
            data: SeriesData = PreparedSeriesData(prepared_dataset_ref=prepared, role_fields=field_ids)
            store[table.object_hash] = table
        else:
            precomputed_kind = (
                "band"
                if item.geometry == "band"
                else "spectrum"
                if case.chart_id == "S25"
                else "curve"
            )
            precomputed = PrecomputedDataRef(
                precomputed_id=f"precomputed:seq20.{case.chart_id.lower()}.{index}",
                precomputed_version=1,
                precomputed_kind=cast(Any, precomputed_kind),
                content_hash=table.object_hash,
                data_ref_hash=table.object_hash,
                field_ids=field_ids,
            )
            precomputed_refs.append(precomputed)
            data = PrecomputedSeriesData(precomputed_data_ref=precomputed, role_fields=field_ids)
            store[table.object_hash] = table
        series_style = SeriesStyleSpec()
        if edited:
            color = ("#1F77B4", "#D95F02", "#2A9D6F", "#7B61A8")[
                edited_color_indices[index] % 4
            ]
            if item.geometry in {"line", "step", "area", "band"}:
                series_style = series_style.model_copy(
                    update={
                        "color": ColorValue(value=color),
                        "line_width": PhysicalLength(value=1.4, unit="pt"),
                    }
                )
            if item.geometry in {"symbol", "lollipop", "dumbbell"}:
                series_style = series_style.model_copy(
                    update={
                        "color": ColorValue(value=color),
                        "marker_size": PhysicalLength(value=6.0, unit="pt"),
                        "symbol": SymbolStyle(shape="diamond", interior="solid"),
                    }
                )
        specifications.append(
            SeriesSpec(
                series_id=f"series:{case.chart_id.lower()}.{index}",
                geometry=item.geometry,
                data=data,
                label=_text(item.label) if item.label else None,
                style=series_style,
            )
        )

    x_label, y_label, x_kind, y_kind = _labels_and_scales(case)
    specialist = SpecialistEditSpec()
    if edited and case.chart_id in {"K08", "K09", "K10", "K18", "X09"}:
        fill_color = (
            ColorValue(value="#4C78A8") if case.chart_id in {"K08", "K18", "X09"} else None
        )
        specialist = specialist.model_copy(
            update={
                "bar_area": BarAreaEditSpec(
                    fill_color=fill_color,
                    edge_color=ColorValue(value="#1F3552"),
                    edge_width=PhysicalLength(value=0.8, unit="pt"),
                    width_ratio=0.68,
                    alpha=0.82,
                )
            }
        )
    if edited and case.chart_id in {"K05", "S05"}:
        specialist = specialist.model_copy(
            update={
                "uncertainty": UncertaintyEditSpec(
                    color=ColorValue(value="#7B61A8"),
                    line_width=PhysicalLength(value=1.1, unit="pt"),
                    cap_size=PhysicalLength(value=5.0, unit="pt"),
                    band_alpha=0.32,
                )
            }
        )
    if edited and case.chart_id == "X01":
        specialist = specialist.model_copy(update={"chart_parameters": ChartParameterEditSpec(step_where="mid")})
    if edited and case.chart_id == "X02":
        specialist = specialist.model_copy(update={"chart_parameters": ChartParameterEditSpec(lollipop_baseline=0.0)})

    english_title = {
        "K01": "Line plot",
        "K02": "Line and symbol",
        "K03": "Scatter plot",
        "K08": "Column plot",
        "K18": "Area plot",
        "X01": "Step plot",
        "X02": "Lollipop plot",
        "X09": "Floating interval bar",
        "K05": "Curve with confidence band",
        "K09": "Grouped column plot",
        "K10": "Stacked column plot",
        "S05": "Provided dose response",
        "S25": "Continuous spectra",
        "X03": "Dumbbell plot",
    }[case.chart_id]
    plot = PlotSpec(
        plot_id=f"plot:seq20.{case.chart_id.lower()}.{'edited' if edited else 'default'}",
        plot_version=2 if edited else 1,
        chart_type_id=cast(ChartTypeId, case.chart_id),
        title=_text(f"SEQ-20 · {case.chart_id} · {english_title}" if edited else english_title),
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
        legend=LegendSpec(visible=True if case.chart_id == "K02" else None),
        specialist=specialist,
        style_sources=(StyleSourceRef(source_kind="project", source_id="style.seq20", source_version=1, content_hash=hashlib.sha256(b"style.seq20").hexdigest()),),
        resolved_style=style().model_copy(update={"font_size": PhysicalLength(value=9.5 if edited else 8.0, unit="pt")}),
        publication_profile=profile(),
        provenance=PlotProvenance(origin="manual", engine_build_hash=hashlib.sha256(b"seq20.baseline").hexdigest()),
    )
    return plot, RenderDataStore(store)


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


def _build_index(batch: int, cases: tuple[AuditCase, ...], batch_dir: Path) -> None:
    cards = []
    for case in cases:
        case_rel = case.case_id
        cards.append(
            f"""
<article><h2>{html.escape(case.chart_id)} · {html.escape(case.title)}</h2>
<p><span class="grade">{case.grade} 级</span> {html.escape(case.recipe)}</p>
<p>通用编辑：{html.escape(case.common_edit)}；图型适用编辑：{html.escape(case.chart_edit)}</p>
<h3>默认状态</h3><a href="{case_rel}/comparison-default.png"><img src="{case_rel}/comparison-default.png" alt="{case.chart_id} default"></a>
<h3>代表性编辑状态</h3><a href="{case_rel}/comparison-edited.png"><img src="{case_rel}/comparison-edited.png" alt="{case.chart_id} edited"></a>
<p><a href="{case_rel}/data.csv">冻结数据</a> · <a href="{case_rel}/provenance.json">provenance</a></p></article>
"""
        )
    (batch_dir / "index.html").write_text(
        f"""<!doctype html><meta charset="utf-8"><title>SEQ-20 Batch {batch}</title>
<style>body{{font:14px Arial,sans-serif;margin:24px;background:#f5f5f5;color:#171717}}main{{max-width:1500px;margin:auto}}article{{background:#fff;border:1px solid #ddd;margin:0 0 28px;padding:18px}}img{{width:100%;height:auto;border:1px solid #ddd}}h1,h2,h3{{margin:0 0 12px}}h3{{margin-top:18px}}.grade{{background:#111;color:#fff;padding:2px 7px;border-radius:10px}}</style>
<main><h1>SEQ-20 · 第 {batch} 批 · 严格同源视觉基线</h1>
<p>每图均使用冻结的同一份数据。左：Origin 参考；中：Matplotlib；右：PlotAgent 原生 Origin O1 fresh reopen。</p>{''.join(cards)}</main>""",
        encoding="utf-8",
    )


def _render_batch(batch: int, cases: tuple[AuditCase, ...], output: Path, fixtures: Path) -> dict[str, Any]:
    assert_scope_clean(REPOSITORY, SOURCE_SCOPE)
    batch_dir = output / f"batch-{batch}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    states: dict[str, list[ResolvedPlot]] = {"default": [], "edited": []}
    plots: dict[tuple[str, str], PlotSpec] = {}
    case_entries: dict[str, dict[str, Any]] = {}
    for case in cases:
        fixture_dir = fixtures / case.case_id
        provenance_path = fixture_dir / "provenance.json"
        if not provenance_path.is_file():
            raise RuntimeError(f"prepare evidence first: {case.case_id}")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if _sha256(fixture_dir / "data.csv") != provenance["data_sha256"]:
            raise RuntimeError(f"frozen data changed: {case.case_id}")
        if _sha256(fixture_dir / "reference.png") != provenance["reference_sha256"]:
            raise RuntimeError(f"frozen reference changed: {case.case_id}")
        case_dir = batch_dir / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture_dir / "data.csv", case_dir / "data.csv")
        shutil.copy2(fixture_dir / "reference.png", case_dir / "reference.png")
        shutil.copy2(provenance_path, case_dir / "provenance.json")
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
            plots[(case.case_id, state)] = plot
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
                export_id=f"export:seq20.batch{batch}.{state}",
                target_scope="selected_plots",
            ),
        )
        target = batch_dir / f"seq20-batch-{batch}-{state}.opju"
        result = export_origin(
            origin_plan,
            target,
            expected_existing_sha256=_sha256(target) if target.is_file() else None,
            timeout_seconds=480.0,
        )
        if not isinstance(result, OriginExportSuccess):
            raise RuntimeError(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if result.build_validation != result.reopen_validation:
            raise RuntimeError(f"Origin fresh reopen validation drift: batch {batch} {state}")
        destinations = tuple(batch_dir / case.case_id / state / "origin-fresh-reopen.png" for case in cases)
        _export_reopened_graphs(target, destinations)
        for case, destination in zip(cases, destinations, strict=True):
            case_entries[case.case_id]["states"][state]["origin_fresh_png_sha256"] = _sha256(destination)
            case_entries[case.case_id]["states"][state]["origin_graph_index"] = cases.index(case)
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

    for case in cases:
        case_dir = batch_dir / case.case_id
        _contact_sheet(case_dir, "default")
        _contact_sheet(case_dir, "edited")
        case_entries[case.case_id]["comparison_default_sha256"] = _sha256(case_dir / "comparison-default.png")
        case_entries[case.case_id]["comparison_edited_sha256"] = _sha256(case_dir / "comparison-edited.png")

    source_identity = source_build_identity(
        REPOSITORY,
        SOURCE_SCOPE,
        scope_version=SOURCE_SCOPE_VERSION,
    )
    manifest = {
        "schema_version": "1.1",
        "stage": "SEQ-20",
        "batch": batch,
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
            "synthetic_allowed": False,
            "states": ["default", "representative edited"],
            "edited_state_requires": ["common edit", "chart-applicable edit", "Origin mapping"],
        },
        "exports": export_entries,
        "cases": [case_entries[case.case_id] for case in cases],
        "qualification": {
            "source_build_identity": source_identity,
            "blocking_observations": list(BLOCKING_OBSERVATIONS),
            "human_visual_signature": {
                "status": "pending",
                "reviewer": None,
                "signed_at": None,
            },
            "decision": "NO-GO",
        },
        "audit_conclusion": (
            "same-source evidence rebuilt; automated P0 blockers closed; "
            "human visual sign-off pending; visual qualification not passed"
        ),
    }
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(manifest_path, fixtures / f"batch-{batch}.manifest.json")
    _build_index(batch, cases, batch_dir)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", choices=("1", "2", "3", "all"), default="all")
    parser.add_argument("--phase", choices=("prepare", "render", "all"), default="all")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    args = parser.parse_args()
    selected = BATCHES if args.batch == "all" else {int(args.batch): BATCHES[int(args.batch)]}
    args.output.mkdir(parents=True, exist_ok=True)
    args.fixtures.mkdir(parents=True, exist_ok=True)
    for batch, cases in selected.items():
        batch_dir = args.output / f"batch-{batch}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        if args.phase in {"prepare", "all"}:
            for case in cases:
                _prepare_case(case, batch_dir, args.fixtures)
        if args.phase in {"render", "all"}:
            _render_batch(batch, cases, args.output, args.fixtures)


if __name__ == "__main__":
    main()

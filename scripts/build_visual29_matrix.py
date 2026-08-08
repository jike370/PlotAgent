"""Build same-source visual qualification evidence for the matrix/specialist lane.

This lane covers K04, K12, K19, K21, K22, S21, S31 and S34 from the
post-SEQ-20 set.  It deliberately refuses to render a chart unless an Origin
installation supplies both the reference construction and the exact source
data:

* Grade A: export an Origin-shipped project graph and freeze its workbook data.
* Grade C: rebuild the reference in Origin from Origin-shipped sample data with
  an Origin-shipped template.

Cases without such a pair are written to the evidence-gap register only.  Old
PlotAgent output, synthetic data and look-alike third-party data are never used
as qualification references.
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

import pandas as pd
from PIL import Image, ImageDraw, ImageOps

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent import __version__ as PLOTAGENT_VERSION
from plotagent.contracts.base import ChartTypeId, ColorValue, PhysicalLength, PreparedDatasetRef
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.plots import (
    AllGeometryKind,
    AxisSpec,
    ColorbarEditSpec,
    DistributionFamily,
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
    grade: Literal["A", "C"]
    source: Path
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


CASES = (
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

GAPS = (
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

VISUAL_OBSERVATIONS: dict[str, tuple[str, ...]] = {}
GAP_BLOCKING_OBSERVATIONS: tuple[dict[str, str], ...] = tuple(
    {
        "chart_type_id": item.chart_id,
        "code": "SAME_SOURCE_EVIDENCE_MISSING",
        "status": "open",
        "backend": "evidence",
        "observation": item.blocking_reason,
    }
    for item in GAPS
)
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
    label: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


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
    if case.chart_id == "K19":
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


def _write_reference(case: AuditCase, frame: pd.DataFrame, case_dir: Path, op: Any) -> None:
    if case.grade == "A":
        assert case.graph_name is not None
        graph = next((item for item in op.pages("g") if item.name == case.graph_name), None)
        if graph is None:
            raise RuntimeError(f"Origin graph {case.graph_name!r} is missing")
        graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
        op.save(str(case_dir / "reference-origin.opju"))
        return

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
        "origin_template": case.origin_template,
        "recipe": case.recipe,
        "same_source_data": True,
        "synthetic": False,
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
        return (InputSeries("contour", "precomputed", ("x", "y", "z"), rows("x", "y", "z")),)
    raise RuntimeError(f"unsupported series case {case.case_id}")


def _family(case: AuditCase, geometries: tuple[AllGeometryKind, ...]) -> PlotFamily:
    if case.chart_id == "K12":
        return DistributionFamily(geometry=cast(Any, geometries))
    if case.chart_id == "K22":
        return MatrixFamily(geometry=cast(Any, geometries))
    return XYFamily(geometry=cast(Any, geometries))


def _labels_and_scales(case: AuditCase) -> tuple[str, str, str, str]:
    return {
        "K04": ("X", "Y", "linear", "linear"),
        "K12": ("Group", "Value", "categorical", "linear"),
        "K19": ("Time", "Value", "datetime", "linear"),
        "K22": ("Wavelength (nm)", "Temperature", "linear", "linear"),
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
                precomputed_kind="matrix_grid",
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

    x_label, y_label, x_kind, y_kind = _labels_and_scales(case)
    english_title = {
        "K04": "Bubble and colormap scatter",
        "K12": "Dot and strip plot",
        "K19": "Time-series plot",
        "K22": "Filled contour",
    }[case.chart_id]
    edited_title = {
        "K04": "Edited K04 bubble plot",
        "K12": "Edited K12 strip plot",
        "K19": "Edited K19 time series",
        "K22": "Edited K22 contour",
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
        "rules": {"same_source_required": True, "synthetic_allowed": False},
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


def _fresh_qualification(source_identity: dict[str, str]) -> dict[str, Any]:
    return {
        "source_build_identity": source_identity,
        "blocking_observations": list(GAP_BLOCKING_OBSERVATIONS),
        "human_visual_signature": {"status": "pending", "reviewer": None, "signed_at": None},
        "evidence_status": "fresh_render_pending_human",
        "decision": "NO-GO",
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
            "synthetic_allowed": False,
            "allowed_evidence_grades": ["A", "C"],
            "states": ["default", "representative edited"],
            "edited_state_requires": ["common edit", "chart-applicable edit", "Origin mapping"],
            "missing_same_source_action": "register_gap_without_rendering",
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
            "four same-source evidence cases generated; four cases withheld for missing A/C evidence; "
            "human visual sign-off pending; visual qualification not passed"
        ),
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(manifest_path, fixtures / "manifest.json")
    _build_index(output)
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
    manifest["qualification"] = _fresh_qualification(manifest_source_identity)
    manifest["audit_conclusion"] = (
        "four same-source evidence cases generated; four cases withheld for missing A/C evidence; "
        "automated P0 blockers closed; human visual sign-off pending; visual qualification not passed"
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(manifest_path, fixtures / "manifest.json")
    _build_index(output)
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

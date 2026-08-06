"""Build a strict same-source Origin/Matplotlib audit for the added P1 charts.

Only cases with an Origin reference and the exact data used to make that reference are
eligible. Grade A opens a shipped Origin project. Grade C regenerates a reference in
Origin from shipped Origin sample data. Missing pairs stay explicitly untested.
"""

# ruff: noqa: E402, E501 -- repo-path bootstrap and contiguous generated audit HTML.

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.contracts.base import PreparedDatasetRef
from plotagent.contracts.plots import (
    AxisSpec,
    PreparedSeriesData,
    SafeRichText,
    SafeTextNode,
    ScaleSpec,
)
from plotagent.exports import export_png
from plotagent.origin import build_origin_export_spec, compile_origin_plan, export_origin
from plotagent.origin.models import OriginExportSuccess
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable, ResolvedPlot
from tests.rendering.fixture_factory import build_plot_and_store

ORIGIN = Path(r"D:\origin")
DEFAULT_OUTPUT = REPOSITORY / "build" / "visual-audit" / "p1-origin-evidence"
ADDED_P1 = (
    "X01",
    "X02",
    "X03",
    "X05",
    "X07",
    "X09",
    "X11",
    "X12",
    "X13",
    "X15",
    "X16",
    "X17",
    "X18",
    "X19",
    "X23",
    "X24",
    "X35",
    "X36",
    "X37",
    "X38",
    "S07",
)


@dataclass(frozen=True, slots=True)
class AuditCase:
    case_id: str
    chart_id: str
    title: str
    grade: Literal["A", "C"]
    source: Path
    graph_name: str | None
    recipe: str


CASES = (
    AuditCase(
        "X01_step_official_signal",
        "X01",
        "阶梯图",
        "C",
        ORIGIN / "Samples" / "Signal Processing" / "Step Signal with Random Noise.dat",
        None,
        "Origin 官方信号样例数据；在 Origin 中按水平阶梯连接规则重新生成。",
    ),
    AuditCase(
        "X02_drop_line_official_signal",
        "X02",
        "棒棒糖图",
        "C",
        ORIGIN / "Samples" / "Signal Processing" / "Step Signal with Random Noise.dat",
        None,
        "Origin 官方信号样例数据；抽取固定步长后以 DROPLINE.OTP 重新生成。",
    ),
    AuditCase(
        "X03_lollipop_two_points",
        "X03",
        "哑铃图",
        "A",
        ORIGIN / "Lollipop.opju",
        "Graph1",
        "直接导出随 Origin 安装的 Lollipop Plot (Two Points) 图页及其工作表。",
    ),
    AuditCase(
        "X05_beeswarm",
        "X05",
        "蜂群图",
        "A",
        ORIGIN / "ColumnScatter.opju",
        "Graph10",
        "直接导出随 Origin 安装的 Beeswarm Plot 图页；宽表仅作无损长表化。",
    ),
    AuditCase(
        "X09_floating_column",
        "X09",
        "范围柱条图",
        "A",
        ORIGIN / "FLOATBAR.opju",
        "Graph5",
        "直接导出随 Origin 安装的 Floating Column 图页及其三边界工作表。",
    ),
    AuditCase(
        "X13_population_pyramid",
        "X13",
        "人口金字塔",
        "C",
        ORIGIN / "Samples" / "Graphing" / "African_population.dat",
        None,
        "Origin 官方非洲人口样例数据；以 PopulationPyramid.otpu 重新生成。",
    ),
    AuditCase(
        "X23_dual_y_line",
        "X23",
        "双 Y 轴折线图",
        "A",
        ORIGIN / "Double Y.opju",
        "Graph1",
        "直接导出随 Origin 安装的 Double Y 图页及其工作表。",
    ),
    AuditCase(
        "X35_dual_y_column",
        "X35",
        "双 Y 轴柱状图",
        "A",
        ORIGIN / "Double Y.opju",
        "Graph2",
        "直接导出随 Origin 安装的 Double-Y Column 图页及其工作表。",
    ),
    AuditCase(
        "X36_dual_y_column_line",
        "X36",
        "双 Y 轴柱线图",
        "A",
        ORIGIN / "Double Y.opju",
        "Graph3",
        "直接导出随 Origin 安装的 Double-Y Column-Line Symbol 图页及其工作表。",
    ),
    AuditCase(
        "X38_offset_stack_y",
        "X38",
        "Y 偏移堆积线图",
        "C",
        ORIGIN / "waterfall.opju",
        None,
        "Origin 官方 Waterfall 项目数据；以 OffsetStackY.otp 和固定偏移重新生成。",
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _project_frame(path: Path) -> pd.DataFrame:
    import originpro as op  # type: ignore[import-untyped]

    op.new()
    op.open(str(path), readonly=True)
    books = list(op.pages("w"))
    if not books or not len(books[0]):
        raise RuntimeError(f"Origin project has no worksheet: {path}")
    return cast(pd.DataFrame, books[0][0].to_df())


def _write_a_evidence(case: AuditCase, case_dir: Path) -> pd.DataFrame:
    import originpro as op  # type: ignore[import-untyped]

    frame = _project_frame(case.source)
    graph = next((item for item in op.pages("g") if item.name == case.graph_name), None)
    if graph is None:
        raise RuntimeError(f"missing graph {case.graph_name} in {case.source}")
    graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
    if case.chart_id == "X03":
        return pd.DataFrame(
            {"category": frame["ID"], "start": frame["Start"], "end": frame["Middle"]}
        )
    if case.chart_id == "X05":
        long = frame.melt(var_name="group", value_name="value")[["value", "group"]]
        long["value"] = pd.to_numeric(long["value"], errors="coerce")
        return long.dropna().reset_index(drop=True)
    if case.chart_id == "X09":
        return pd.DataFrame(
            {
                "category": frame.iloc[:, 0],
                "start": frame["Start"],
                "end": frame["End"],
                "middle": frame["Middle"],
            }
        )
    if case.chart_id in {"X23", "X35", "X36"}:
        category_role = "x" if case.chart_id == "X23" else "category"
        return pd.DataFrame(
            {
                category_role: frame["Country"],
                "left": frame["Population"],
                "right": frame["GDP per capita"],
            }
        )
    raise RuntimeError(f"unsupported A evidence case {case.chart_id}")


def _step_frame() -> pd.DataFrame:
    frame = pd.read_csv(
        ORIGIN / "Samples" / "Signal Processing" / "Step Signal with Random Noise.dat",
        sep="\t",
    )
    return frame.rename(columns={frame.columns[0]: "x", frame.columns[1]: "y"})[["x", "y"]]


def _african_population_frame() -> pd.DataFrame:
    rows: list[tuple[str, float, float]] = []
    lines = (
        (ORIGIN / "Samples" / "Graphing" / "African_population.dat")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    for line in lines[3:]:
        cells = line.split("\t")
        if len(cells) >= 3:
            rows.append((cells[0], float(cells[1]), float(cells[2])))
    return pd.DataFrame(rows, columns=("category", "left", "right"))


def _waterfall_frame() -> pd.DataFrame:
    wide = _project_frame(ORIGIN / "waterfall.opju")
    records: list[pd.DataFrame] = []
    for index in range(0, len(wide.columns), 2):
        label = str(wide.columns[index + 1])
        records.append(
            pd.DataFrame({"x": wide.iloc[:, index], "y": wide.iloc[:, index + 1], "series": label})
        )
    return pd.concat(records, ignore_index=True).dropna().reset_index(drop=True)


def _origin_new_graph_reference(case: AuditCase, frame: pd.DataFrame, case_dir: Path) -> None:
    import originpro as op  # type: ignore[import-untyped]

    op.new()
    book = op.new_book("w", f"Evidence{case.chart_id}")
    sheet = book[0]
    if case.chart_id == "X01":
        x = frame["x"].to_numpy(dtype=float)
        y = frame["y"].to_numpy(dtype=float)
        step_x = np.repeat(x, 2)[1:]
        step_y = np.repeat(y, 2)[:-1]
        plotted = pd.DataFrame({"x": step_x, "y": step_y})
        sheet.from_df(plotted)
        graph = op.new_graph(template="LINE")
        graph[0].add_plot(sheet, coly=1, colx=0, type="l")
    elif case.chart_id == "X02":
        sheet.from_df(frame)
        graph = op.new_graph(template="DROPLINE")
        graph[0].add_plot(sheet, coly=1, colx=0, type="s")
    elif case.chart_id == "X13":
        plotted = frame.copy()
        sheet.from_df(plotted)
        graph = op.new_graph(template=str(ORIGIN / "PopulationPyramid.otpu"))
        graph[0].add_plot(sheet, coly=1, colx=0, type=215)
        graph[1].add_plot(sheet, coly=2, colx=0, type=215)
    elif case.chart_id == "X38":
        labels = tuple(dict.fromkeys(frame["series"].astype(str)))
        span = float(frame["y"].max() - frame["y"].min())
        offset = span * 0.35 if span else 1.0
        plotted = pd.DataFrame()
        for index, label in enumerate(labels):
            selected = frame.loc[frame["series"].astype(str) == label]
            plotted[f"x{index}"] = selected["x"].to_numpy()
            plotted[label] = selected["y"].to_numpy(dtype=float) + index * offset
        sheet.from_df(plotted)
        graph = op.new_graph(template=str(ORIGIN / "OffsetStackY.otp"))
        for index in range(len(labels)):
            graph[0].add_plot(sheet, coly=index * 2 + 1, colx=index * 2, type="l")
    else:
        raise RuntimeError(f"unsupported C evidence case {case.chart_id}")
    for layer in graph:
        layer.rescale()
    graph.save_fig(str(case_dir / "reference.png"), type="png", replace=True, width=1600)
    op.save(str(case_dir / "reference-origin.opju"))


def _write_c_evidence(case: AuditCase, case_dir: Path) -> pd.DataFrame:
    if case.chart_id == "X01":
        frame = _step_frame()
    elif case.chart_id == "X02":
        source = _step_frame()
        frame = pd.DataFrame(
            {
                "category": source["x"].iloc[::50].reset_index(drop=True),
                "value": source["y"].iloc[::50].reset_index(drop=True),
            }
        )
    elif case.chart_id == "X13":
        frame = _african_population_frame()
    elif case.chart_id == "X38":
        frame = _waterfall_frame()
    else:
        raise RuntimeError(f"unsupported C evidence case {case.chart_id}")
    _origin_new_graph_reference(case, frame, case_dir)
    return frame


def _resolved(case: AuditCase, frame: pd.DataFrame) -> ResolvedPlot:
    base, _ = build_plot_and_store(case.chart_id)
    field_ids = tuple(f"field:{case.chart_id.lower()}.{role}" for role in frame.columns)
    table = RenderTable.from_columns(
        {
            field_id: tuple(frame[role].tolist())
            for role, field_id in zip(frame.columns, field_ids, strict=True)
        }
    )
    prepared = PreparedDatasetRef(
        prepared_dataset_id=f"prepared:audit.{case.chart_id.lower()}",
        prepared_version=1,
        content_hash=table.object_hash,
    )
    data = PreparedSeriesData(prepared_dataset_ref=prepared, role_fields=field_ids)
    series = base.series[0].model_copy(update={"data": data})
    scale_kinds: dict[str, tuple[str, str]] = {
        "X03": ("linear", "categorical"),
        "X05": ("categorical", "linear"),
        "X09": ("categorical", "linear"),
        "X13": ("linear", "categorical"),
        "X23": ("categorical", "linear"),
        "X35": ("categorical", "linear"),
        "X36": ("categorical", "linear"),
    }
    x_kind, y_kind = scale_kinds.get(case.chart_id, ("linear", "linear"))
    labels: dict[str, tuple[str, str]] = {
        "X01": ("Time", "Signal"),
        "X02": ("Sample", "Signal"),
        "X03": ("Start–End", "ID"),
        "X05": ("Food", "Range"),
        "X09": ("ID", "Interval"),
        "X13": ("Population (million)", "Age group"),
        "X23": ("Country", "Population"),
        "X35": ("Country", "Population"),
        "X36": ("Country", "Population"),
        "X38": ("2-Theta", "Offset intensity"),
    }
    x_label, y_label = labels[case.chart_id]
    scales: tuple[ScaleSpec, ...] = (
        ScaleSpec(scale_id="scale:x", kind=cast(Any, x_kind)),
        ScaleSpec(scale_id="scale:y", kind=cast(Any, y_kind)),
    )
    axes: tuple[AxisSpec, ...] = (
        AxisSpec(
            axis_id="axis:x",
            scale_id="scale:x",
            orientation="x",
            position="bottom",
            label=_text(x_label),
        ),
        AxisSpec(
            axis_id="axis:y",
            scale_id="scale:y",
            orientation="y",
            position="left",
            label=_text(y_label),
        ),
    )
    if case.chart_id in {"X23", "X35", "X36"}:
        scales += (ScaleSpec(scale_id="scale:y_right", kind="linear"),)
        axes += (
            AxisSpec(
                axis_id="axis:y_right",
                scale_id="scale:y_right",
                orientation="y",
                position="right",
                label=_text("GDP per capita ($)"),
            ),
        )
    plot = base.model_copy(
        update={
            "prepared_data_refs": (prepared,),
            "series": (series,),
            "scales": scales,
            "axes": axes,
        }
    )
    return PlotResolver().resolve(plot, RenderDataStore({table.object_hash: table}))


def _origin_png(opju: Path, output: Path) -> None:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        op.open(str(opju), readonly=True)
        graphs = list(op.pages("g"))
        if not graphs:
            raise RuntimeError(f"no graph in {opju}")
        graphs[0].save_fig(str(output), type="png", replace=True, width=1600)
    finally:
        op.exit()


def _contact_sheet(case_dir: Path) -> None:
    filenames = ("reference.png", "matplotlib.png", "origin.png")
    labels = ("ORIGIN REFERENCE", "MATPLOTLIB", "PLOTAGENT ORIGIN")
    images = [Image.open(case_dir / name).convert("RGB") for name in filenames]
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
        output.save(case_dir / "comparison.png", optimize=True)
    finally:
        for source in images:
            source.close()


def _prepare_case(case: AuditCase, output: Path) -> dict[str, Any]:
    import originpro as op  # type: ignore[import-untyped]

    case_dir = output / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    op.set_show(False)
    try:
        frame = (
            _write_a_evidence(case, case_dir)
            if case.grade == "A"
            else _write_c_evidence(case, case_dir)
        )
    finally:
        op.exit()
    frame.to_csv(case_dir / "data.csv", index=False, float_format="%.12g")
    provenance = {
        "chart_type_id": case.chart_id,
        "evidence_grade": case.grade,
        "source_path": str(case.source),
        "source_sha256": _sha256(case.source),
        "source_graph_name": case.graph_name,
        "recipe": case.recipe,
        "same_source_data": True,
        "data_sha256": _sha256(case_dir / "data.csv"),
        "reference_sha256": _sha256(case_dir / "reference.png"),
    }
    (case_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return provenance


def _render_case(case: AuditCase, output: Path) -> dict[str, Any]:
    case_dir = output / case.case_id
    provenance_path = case_dir / "provenance.json"
    if not provenance_path.is_file():
        raise RuntimeError(f"evidence must be prepared before rendering: {case.case_id}")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    data_path = case_dir / "data.csv"
    if provenance["data_sha256"] != _sha256(data_path):
        raise RuntimeError(f"data changed after evidence anchoring: {case.case_id}")
    frame = pd.read_csv(data_path)
    resolved = _resolved(case, frame)
    export_png(case_dir / "matplotlib.png", resolved)
    origin_plan = compile_origin_plan(
        (resolved,),
        build_origin_export_spec((resolved,), export_id=f"export:audit.{case.chart_id.lower()}"),
    )
    target = case_dir / f"{case.case_id}.opju"
    result = export_origin(
        origin_plan,
        target,
        expected_existing_sha256=_sha256(target) if target.is_file() else None,
        timeout_seconds=120.0,
    )
    if not isinstance(result, OriginExportSuccess):
        raise RuntimeError(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    _origin_png(target, case_dir / "origin.png")
    _contact_sheet(case_dir)
    provenance["plotagent_origin_sha256"] = _sha256(target)
    provenance["matplotlib_sha256"] = _sha256(case_dir / "matplotlib.png")
    provenance["plotagent_origin_png_sha256"] = _sha256(case_dir / "origin.png")
    provenance["fresh_reopen_identical"] = result.build_validation == result.reopen_validation
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return provenance


def _write_index(output: Path) -> None:
    tested: list[dict[str, Any]] = []
    cards: list[str] = []
    for case in CASES:
        case_dir = output / case.case_id
        provenance_path = case_dir / "provenance.json"
        comparison = case_dir / "comparison.png"
        if not provenance_path.is_file() or not comparison.is_file():
            continue
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        tested.append(provenance)
        cards.append(
            f"""<section><h2>{html.escape(case.chart_id)} · {html.escape(case.title)} · {case.grade}级</h2>
<p>{html.escape(case.recipe)}</p><a href="{case.case_id}/comparison.png"><img src="{case.case_id}/comparison.png" alt="comparison"></a>
<p><a href="{case.case_id}/reference.png">示例图片</a> · <a href="{case.case_id}/data.csv">同源数据</a> · <a href="{case.case_id}/matplotlib.png">Matplotlib</a> · <a href="{case.case_id}/origin.png">Origin 结果</a> · <a href="{case.case_id}/{case.case_id}.opju">OPJU</a> · <a href="{case.case_id}/provenance.json">来源证明</a></p></section>"""
        )
    tested_ids = {item["chart_type_id"] for item in tested}
    untested = [chart_id for chart_id in ADDED_P1 if chart_id not in tested_ids]
    untested_items = "".join(
        f"<li>{html.escape(chart_id)}：缺少已锚定的同源示例图—数据对，暂不做视觉测试。</li>"
        for chart_id in untested
    )
    document = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>P1 Origin 同源视觉审计</title>
<style>body{{font:15px system-ui;margin:30px;background:#f3f5f8;color:#20242a}}main{{max-width:1520px;margin:auto}}section{{background:white;padding:20px;margin:20px 0;border-radius:14px;box-shadow:0 2px 12px #0001}}img{{width:100%;border:1px solid #d8dde5}}a{{color:#145bcc}}code{{background:#eef1f5;padding:2px 5px}}</style>
<main><h1>P1 Origin 同源视觉审计</h1><p>生成时间：{html.escape(datetime.now().astimezone().isoformat(timespec="seconds"))}。只有示例图片与测试数据同源的案例进入三栏对照。</p>
<p>A级：Origin 随附项目原图；C级：Origin 随附官方样例数据在 Origin 中重新生成。每项均记录源文件与数据哈希。</p>{"".join(cards)}
<section><h2>暂不做视觉测试</h2><ul>{untested_items}</ul></section></main></html>"""
    (output / "index.html").write_text(document, encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps(
            {"tested": tested, "untested_missing_same_source_pair": untested},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--phase", choices=("evidence", "render", "all", "index"), default="all")
    parser.add_argument("--case", dest="case_id")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = tuple(case for case in CASES if not args.case_id or case.case_id == args.case_id)
    if not selected and args.phase != "index":
        raise SystemExit(f"unknown audit case: {args.case_id}")
    if args.phase in {"evidence", "all"}:
        for case in selected:
            _prepare_case(case, output)
            print(f"evidence {case.case_id}", flush=True)
    if args.phase in {"render", "all"}:
        for case in selected:
            _render_case(case, output)
            print(f"rendered {case.case_id}", flush=True)
    _write_index(output)
    print(output / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

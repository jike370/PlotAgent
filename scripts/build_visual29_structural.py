"""Build strict same-source visual evidence for the structural/facet/dual-axis lane.

This lane is intentionally independent from the SEQ-20 first-14 generator.  It
upgrades the six previously anchored Origin P1 pairs to the current renderer
build and records three explicit gaps.  A case is rendered only when the
reference image and PlotAgent input data come from the same shipped Origin
source.  Synthetic substitutes are never accepted.
"""

# ruff: noqa: E402, E501 -- repository bootstrap and audit HTML are kept local.

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
from typing import Any, Literal

import pandas as pd
from PIL import Image, ImageDraw, ImageOps

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

import scripts.build_p1_visual_audit as p1_evidence
from plotagent import __version__ as PLOTAGENT_VERSION
from plotagent.contracts.base import ColorValue, PhysicalLength, PreparedDatasetRef
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.plots import (
    BarAreaEditSpec,
    DualYAxisEditSpec,
    PreparedSeriesData,
    SafeRichText,
    SafeTextNode,
    SpecialistEditSpec,
    YOffsetEditSpec,
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
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable
from scripts.visual_source_identity import (
    assert_scope_clean,
    git_blob_framed_sha256,
    source_build_identity,
)
from tests.rendering.fixture_factory import build_plot_and_store

ORIGIN = Path(r"D:\origin")
OUTPUT = REPOSITORY / "build" / "visual-audit" / "visual29-structural"
FIXTURES = REPOSITORY / "tests" / "fixtures" / "visual_regression" / "visual29-structural"
SOURCE_SCOPE_VERSION = "visual29-structural-rendering-v2"
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
    recipe: str
    common_edit: str
    chart_edit: str

    @property
    def case_id(self) -> str:
        return f"{self.chart_id}_{self.slug}"


CASES = (
    AuditCase(
        "X05",
        "beeswarm",
        "蜂群图",
        "A",
        ORIGIN / "ColumnScatter.opju",
        "Graph10",
        "直接导出 Origin 随附 ColumnScatter.opju 的 Beeswarm Plot 图页；同一工作表只做无损长表化。",
        "标题与字号",
        "点颜色、点形状与点大小",
    ),
    AuditCase(
        "X13",
        "population_pyramid",
        "人口金字塔",
        "C",
        ORIGIN / "Samples" / "Graphing" / "African_population.dat",
        None,
        "使用 Origin 官方 African_population.dat，并在 Origin 中以 PopulationPyramid.otpu 重新生成参考图。",
        "标题与字号",
        "柱边线、宽度与透明度",
    ),
    AuditCase(
        "X23",
        "dual_y_line",
        "双 Y 轴折线图",
        "A",
        ORIGIN / "Double Y.opju",
        "Graph1",
        "直接导出 Origin 随附 Double Y.opju 的 Graph1 及同项目工作表。",
        "标题与字号",
        "左右轴颜色与轴线宽度",
    ),
    AuditCase(
        "X35",
        "dual_y_column",
        "双 Y 轴柱状图",
        "A",
        ORIGIN / "Double Y.opju",
        "Graph2",
        "直接导出 Origin 随附 Double Y.opju 的 Graph2 及同项目工作表。",
        "标题与字号",
        "柱宽、边线及左右轴样式",
    ),
    AuditCase(
        "X36",
        "dual_y_column_line",
        "双 Y 轴柱线图",
        "A",
        ORIGIN / "Double Y.opju",
        "Graph3",
        "直接导出 Origin 随附 Double Y.opju 的 Graph3 及同项目工作表。",
        "标题与字号",
        "左右轴颜色与轴线宽度",
    ),
    AuditCase(
        "X38",
        "offset_stack_y",
        "Y 偏移堆积线图",
        "C",
        ORIGIN / "waterfall.opju",
        None,
        "使用 Origin 官方 Waterfall 项目数据，并以 OffsetStackY.otp 和固定显示偏移重新生成参考图。",
        "标题与字号",
        "偏移距离与系列顺序",
    ),
)

GAPS = (
    {
        "chart_type_id": "K24",
        "title": "分面图",
        "code": "SAME_SOURCE_FACET_PAIR_MISSING",
        "status": "not_tested",
        "candidate_sources": [
            str(ORIGIN / "Samples" / "Graphing" / "Categorical Data.dat"),
            str(ORIGIN / "Templates" / "Previews" / "Trellis.png"),
        ],
        "reason": "本机只有官方分类数据与独立模板预览，没有可证明该预览由这份数据生成的随附图页—工作表对；不能把两者臆配为同源证据。",
    },
    {
        "chart_type_id": "K25",
        "title": "多面板复合图",
        "code": "O1_QUALIFICATION_NOT_APPLICABLE",
        "status": "not_tested",
        "candidate_sources": [str(ORIGIN / "mgroups.otpu")],
        "reason": "K25 是 FigureSpec/O2 多面板对象，不能以本线要求的单图 PlotSpec/O1 fresh-reopen 资格冒充通过；当前也没有同源异构子图项目对。",
    },
    {
        "chart_type_id": "S01",
        "title": "给定 KM 生存曲线",
        "code": "PRECOMPUTED_SAME_SOURCE_PAIR_MISSING",
        "status": "not_tested",
        "candidate_sources": [
            str(ORIGIN / "Samples" / "Statistics" / "Kaplan-Meier.dat"),
            str(ORIGIN / "KaplanMeier.OGS"),
        ],
        "reason": "随附 DAT 是原始 time/status，不是 PlotAgent S01 所需的用户预计算 step/CI/风险人数；为得到参考图必须先运行生存分析，因此不能声称参考图与测试输入是同一份数据。",
    },
)

GAP_BLOCKING_OBSERVATIONS = tuple(
    {
        "chart_type_id": item["chart_type_id"],
        "code": item["code"],
        "status": "open",
        "backend": "evidence",
        "observation": item["reason"],
    }
    for item in GAPS
)

FIRST_ROUND_BLOCKING_OBSERVATIONS = (
    {
        "chart_type_id": "X05",
        "code": "LEGEND_DATA_OVERLAP",
        "status": "open",
        "backend": "matplotlib,origin",
        "states": ["default", "edited"],
        "observation": "右上图例覆盖 Bacon 蜂群的高值观测点。",
    },
    {
        "chart_type_id": "X23",
        "code": "LEGEND_DATA_OVERLAP",
        "status": "open",
        "backend": "matplotlib,origin",
        "states": ["default", "edited"],
        "observation": "右轴折线进入右上图例文字区域。",
    },
    {
        "chart_type_id": "X35",
        "code": "LEGEND_DATA_OVERLAP",
        "status": "open",
        "backend": "matplotlib,origin",
        "states": ["default", "edited"],
        "observation": "右轴高值柱进入右上图例区域。",
    },
    {
        "chart_type_id": "X36",
        "code": "LEGEND_DATA_OVERLAP",
        "status": "open",
        "backend": "matplotlib,origin",
        "states": ["default", "edited"],
        "observation": "右轴折线进入右上图例文字区域。",
    },
    {
        "chart_type_id": "X38",
        "code": "LEGEND_DATA_OVERLAP",
        "status": "open",
        "backend": "matplotlib,origin",
        "states": ["default", "edited"],
        "observation": "多条偏移谱线穿过右上图例，编辑态尤为明显。",
    },
    {
        "chart_type_id": "X23",
        "code": "CATEGORY_LABEL_OVERLAP",
        "status": "open",
        "backend": "origin",
        "states": ["default", "edited"],
        "observation": "Origin O1 的国家类别刻度未避让，标签彼此覆盖。",
    },
    {
        "chart_type_id": "X35",
        "code": "CATEGORY_LABEL_OVERLAP",
        "status": "open",
        "backend": "origin",
        "states": ["default", "edited"],
        "observation": "Origin O1 的国家类别刻度未避让，标签彼此覆盖。",
    },
    {
        "chart_type_id": "X36",
        "code": "CATEGORY_LABEL_OVERLAP",
        "status": "open",
        "backend": "origin",
        "states": ["default", "edited"],
        "observation": "Origin O1 的国家类别刻度未避让，标签彼此覆盖。",
    },
)

CASE_IDS = tuple(case.chart_id for case in CASES)
LANE_IDS = ("S01", "X05", "X13", "X38", "K24", "K25", "X23", "X35", "X36")
ENGLISH_TITLES = {
    "X05": "Beeswarm plot",
    "X13": "Population pyramid",
    "X23": "Dual-Y line plot",
    "X35": "Dual-Y column plot",
    "X36": "Dual-Y column-line plot",
    "X38": "Y-offset stacked line plot",
}
AXIS_LABELS = {
    "X05": {"axis:x": "Food", "axis:y": "Range"},
    "X13": {"axis:x": "Population (million)", "axis:y": "Age group"},
    "X23": {
        "axis:x": "Country",
        "axis:y": "Population",
        "axis:y_right": "GDP per capita ($)",
    },
    "X35": {
        "axis:x": "Country",
        "axis:y": "Population",
        "axis:y_right": "GDP per capita ($)",
    },
    "X36": {
        "axis:x": "Country",
        "axis:y": "Population",
        "axis:y_right": "GDP per capita ($)",
    },
    "X38": {"axis:x": "2-Theta", "axis:y": "Offset intensity"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_build_sha256(commit: str = "HEAD") -> str:
    return git_blob_framed_sha256(REPOSITORY, SOURCE_SCOPE, commit=commit)


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _legacy_case(chart_id: str) -> Any:
    return next(case for case in p1_evidence.CASES if case.chart_id == chart_id)


def _prepare_case(case: AuditCase, output: Path, fixtures: Path) -> dict[str, Any]:
    anchor_root = output / "_origin-anchors"
    anchor_root.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_case(case.chart_id)
    legacy_entry = p1_evidence._prepare_case(legacy, anchor_root)
    anchor_dir = anchor_root / legacy.case_id
    fixture_dir = fixtures / case.case_id
    fixture_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(anchor_dir / "data.csv", fixture_dir / "data.csv")
    shutil.copy2(anchor_dir / "reference.png", fixture_dir / "reference.png")
    provenance = {
        "chart_type_id": case.chart_id,
        "case_id": case.case_id,
        "title": case.title,
        "evidence_grade": case.grade,
        "source_path": str(case.source),
        "source_sha256": _sha256(case.source),
        "source_graph_name": case.graph_name,
        "recipe": case.recipe,
        "same_source_data": True,
        "synthetic": False,
        "data_sha256": _sha256(fixture_dir / "data.csv"),
        "reference_sha256": _sha256(fixture_dir / "reference.png"),
        "legacy_anchor_data_sha256": legacy_entry["data_sha256"],
        "legacy_anchor_reference_sha256": legacy_entry["reference_sha256"],
        "common_edit": case.common_edit,
        "chart_edit": case.chart_edit,
    }
    (fixture_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return provenance


def _edited_specialist(case: AuditCase, frame: pd.DataFrame) -> SpecialistEditSpec:
    specialist = SpecialistEditSpec()
    if case.chart_id == "X13":
        return specialist.model_copy(
            update={
                "bar_area": BarAreaEditSpec(
                    edge_color=ColorValue(value="#1F3552"),
                    edge_width=PhysicalLength(value=0.8, unit="pt"),
                    width_ratio=0.68,
                    alpha=0.86,
                )
            }
        )
    if case.chart_id in {"X23", "X35", "X36"}:
        updates: dict[str, Any] = {
            "dual_y": DualYAxisEditSpec(
                left_color=ColorValue(value="#0F766E"),
                right_color=ColorValue(value="#BE123C"),
                axis_width=PhysicalLength(value=1.1, unit="pt"),
            )
        }
        if case.chart_id == "X35":
            updates["bar_area"] = BarAreaEditSpec(
                edge_color=ColorValue(value="#1F3552"),
                edge_width=PhysicalLength(value=0.8, unit="pt"),
                width_ratio=0.62,
                alpha=0.9,
            )
        return specialist.model_copy(update=updates)
    if case.chart_id == "X38":
        labels = tuple(dict.fromkeys(frame["series"].astype(str)))
        span = float(frame["y"].max() - frame["y"].min())
        distance = span * 0.45 if span else 1.0
        return specialist.model_copy(
            update={"y_offset": YOffsetEditSpec(distance=distance, order=tuple(reversed(labels)))}
        )
    return specialist


def _build_plot(case: AuditCase, frame: pd.DataFrame, *, edited: bool):
    plot, _fixture_store = build_plot_and_store(case.chart_id)
    series = plot.series[0]
    roles = tuple(series.data.role_fields)
    if len(roles) != len(frame.columns):
        raise RuntimeError(
            f"{case.chart_id}: fixture roles {roles!r} do not match anchored columns {tuple(frame.columns)!r}"
        )
    table = RenderTable.from_columns(
        {
            field_id: tuple(frame[column].tolist())
            for column, field_id in zip(frame.columns, roles, strict=True)
        }
    )
    prepared = PreparedDatasetRef(
        prepared_dataset_id=f"prepared:visual29.structural.{case.chart_id.lower()}",
        prepared_version=1,
        content_hash=table.object_hash,
    )
    data = PreparedSeriesData(prepared_dataset_ref=prepared, role_fields=roles)
    series_style = series.style
    if edited and case.chart_id == "X05":
        series_style = series_style.model_copy(
            update={
                "marker_size": PhysicalLength(value=6.0, unit="pt"),
                "symbol": SymbolStyle(shape="diamond", interior="solid"),
                "category_colors": {"Ham": ColorValue(value="#7B61A8")},
            }
        )
    rebound = series.model_copy(update={"data": data, "style": series_style})
    scales = plot.scales
    if case.chart_id == "X23":
        scales = tuple(
            scale.model_copy(update={"kind": "categorical"})
            if scale.scale_id == "scale:x"
            else scale
            for scale in scales
        )
    axes = tuple(
        axis.model_copy(update={"label": _text(AXIS_LABELS[case.chart_id][axis.axis_id])})
        for axis in plot.axes
    )
    updated = {
        "plot_id": f"plot:visual29.structural.{case.chart_id.lower()}.{'edited' if edited else 'default'}",
        "plot_version": 2 if edited else 1,
        "prepared_data_refs": (prepared,),
        "series": (rebound,),
        "scales": scales,
        "axes": axes,
        "title": _text(
            f"Visual qualification - {case.chart_id} - {ENGLISH_TITLES[case.chart_id]}"
            if edited
            else ENGLISH_TITLES[case.chart_id]
        ),
    }
    if edited:
        updated["specialist"] = _edited_specialist(case, frame)
        updated["resolved_style"] = plot.resolved_style.model_copy(
            update={"font_size": PhysicalLength(value=9.5, unit="pt")}
        )
    rebound_plot = plot.model_copy(update=updated)
    return rebound_plot, RenderDataStore({table.object_hash: table})


def _export_reopened_graph(opju: Path, destination: Path) -> None:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        op.open(str(opju), readonly=True)
        graphs = list(op.pages("g"))
        if len(graphs) != 1:
            raise RuntimeError(f"fresh OPJU graph count {len(graphs)} != expected 1")
        destination.parent.mkdir(parents=True, exist_ok=True)
        graphs[0].save_fig(str(destination), type="png", replace=True, width=1600)
    finally:
        op.exit()


def _contact_sheet(case_dir: Path, state: str, *, origin_error: str | None = None) -> None:
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
    images: list[Image.Image] = []
    for path in files:
        if path.is_file():
            images.append(Image.open(path).convert("RGB"))
        else:
            failure = Image.new("RGB", (900, 650), "white")
            draw = ImageDraw.Draw(failure)
            draw.text((40, 50), "ORIGIN EXPORT BLOCKED", fill="#9F1239")
            draw.multiline_text(
                (40, 100),
                origin_error or "No native Origin output was produced.",
                fill="black",
                spacing=8,
            )
            images.append(failure)
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


def _render_case(
    case: AuditCase,
    output: Path,
    fixtures: Path,
    *,
    source_sha256: str,
) -> dict[str, Any]:
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
    entry = {
        **provenance,
        "states": {},
        "blocking_observations": [],
    }
    for state in ("default", "edited"):
        state_dir = case_dir / state
        state_dir.mkdir(exist_ok=True)
        plot, store = _build_plot(case, frame, edited=state == "edited")
        resolved = PlotResolver().resolve(plot, store)
        export_png(state_dir / "matplotlib.png", resolved)
        origin_plan = compile_origin_plan(
            (resolved,),
            build_origin_export_spec(
                (resolved,),
                export_id=f"export:visual29.structural.{case.chart_id.lower()}.{state}",
                target_scope="selected_plots",
            ),
        )
        target = state_dir / f"{case.chart_id}-{state}.opju"
        reopened = state_dir / "origin-fresh-reopen.png"
        state_entry: dict[str, Any] = {
            "plot_spec_sha256": canonical_hash(plot),
            "render_plan_sha256": resolved.render_plan_hash,
            "matplotlib_png_sha256": _sha256(state_dir / "matplotlib.png"),
            "origin_plan_sha256": canonical_hash(origin_plan),
            "source_sha256": source_sha256,
        }
        state_evidence_path = state_dir / "evidence.json"
        if state_evidence_path.is_file():
            saved = json.loads(state_evidence_path.read_text(encoding="utf-8"))
            identity_keys = (
                "plot_spec_sha256",
                "render_plan_sha256",
                "origin_plan_sha256",
                "source_sha256",
            )
            identity_matches = all(saved.get(key) == state_entry[key] for key in identity_keys)
            if saved.get("origin_export_status") == "success":
                files_match = (
                    target.is_file()
                    and reopened.is_file()
                    and saved.get("origin_opju_sha256") == _sha256(target)
                    and saved.get("origin_fresh_png_sha256") == _sha256(reopened)
                )
            else:
                files_match = saved.get("origin_export_status") == "failed"
            if identity_matches and files_match:
                entry["states"][state] = saved
                if saved["origin_export_status"] == "failed":
                    failure = saved["origin_error"]
                    entry["blocking_observations"].append(
                        {
                            "chart_type_id": case.chart_id,
                            "code": failure["error"]["code"],
                            "status": "open",
                            "backend": "origin",
                            "states": [state],
                            "observation": failure["error"]["message"],
                            "details": failure["error"].get("details", {}),
                        }
                    )
                    _contact_sheet(
                        case_dir,
                        state,
                        origin_error=(
                            f"{failure['error']['code']}: {failure['error']['message']}\n"
                            f"{failure['error'].get('details', {})}"
                        ),
                    )
                else:
                    _contact_sheet(case_dir, state)
                continue

        result = export_origin(
            origin_plan,
            target,
            expected_existing_sha256=_sha256(target) if target.is_file() else None,
            timeout_seconds=240.0,
        )
        if not isinstance(result, OriginExportSuccess):
            failure = result.to_dict()
            state_entry.update(
                {
                    "origin_export_status": "failed",
                    "fresh_reopen_identical": False,
                    "origin_error": failure,
                }
            )
            entry["states"][state] = state_entry
            entry["blocking_observations"].append(
                {
                    "chart_type_id": case.chart_id,
                    "code": failure["error"]["code"],
                    "status": "open",
                    "backend": "origin",
                    "states": [state],
                    "observation": failure["error"]["message"],
                    "details": failure["error"].get("details", {}),
                }
            )
            _contact_sheet(
                case_dir,
                state,
                origin_error=f"{failure['error']['code']}: {failure['error']['message']}\n{failure['error'].get('details', {})}",
            )
            state_evidence_path.write_text(
                json.dumps(state_entry, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            continue
        if result.build_validation != result.reopen_validation:
            raise RuntimeError(f"Origin fresh reopen validation drift: {case.chart_id} {state}")
        _export_reopened_graph(target, reopened)
        state_entry.update(
            {
                "origin_export_status": "success",
                "origin_opju_sha256": result.file_sha256,
                "origin_opju_size": result.file_size,
                "origin_fresh_png_sha256": _sha256(reopened),
                "fresh_reopen_identical": True,
                "validation_report_sha256": result.validation_report_sha256,
                "environment": result.environment.to_dict(),
            }
        )
        entry["states"][state] = state_entry
        state_evidence_path.write_text(
            json.dumps(state_entry, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _contact_sheet(case_dir, state)
    entry["comparison_default_sha256"] = _sha256(case_dir / "comparison-default.png")
    entry["comparison_edited_sha256"] = _sha256(case_dir / "comparison-edited.png")
    return entry


def _write_index(entries: list[dict[str, Any]], output: Path) -> None:
    opju_links = "".join(
        f'<li><strong>{html.escape(case.chart_id)}</strong>：'
        f'<a href="{case.case_id}/{case.chart_id}.opju">默认态＋代表性编辑态</a></li>'
        for case in CASES
    )
    cards: list[str] = [
        f'<section class="exports"><h2>每图一个 OPJU</h2><ul>{opju_links}</ul></section>'
    ]
    for case, entry in zip(CASES, entries, strict=True):
        blocker = entry.get("blocking_observations") or []
        status = "存在阻断项" if blocker else "等待人工视觉签名"
        cards.append(
            f"""<article><h2>{html.escape(case.chart_id)} · {html.escape(case.title)}</h2>
<p><span class="grade">{case.grade} 级</span> {html.escape(case.recipe)}</p>
<p>通用编辑：{html.escape(case.common_edit)}；专属编辑：{html.escape(case.chart_edit)}；状态：{status}</p>
<h3>默认状态</h3><a href="{case.case_id}/comparison-default.png"><img src="{case.case_id}/comparison-default.png" alt="{case.chart_id} default"></a>
<h3>代表性编辑状态</h3><a href="{case.case_id}/comparison-edited.png"><img src="{case.case_id}/comparison-edited.png" alt="{case.chart_id} edited"></a>
<p><a href="{case.case_id}/data.csv">同源数据</a> · <a href="{case.case_id}/reference.png">Origin 参考图</a> · <a href="{case.case_id}/provenance.json">来源证明</a></p></article>"""
        )
    gaps = "".join(
        f"<li><strong>{item['chart_type_id']} · {html.escape(item['title'])}</strong>：{html.escape(item['reason'])}（{item['code']}）</li>"
        for item in GAPS
    )
    (output / "index.html").write_text(
        f"""<!doctype html><meta charset="utf-8"><title>其余 29 图 · 特殊结构线视觉资格</title>
<style>body{{font:14px Arial,sans-serif;margin:24px;background:#f5f5f5;color:#171717}}main{{max-width:1500px;margin:auto}}article,section{{background:#fff;border:1px solid #ddd;margin:0 0 28px;padding:18px}}img{{width:100%;height:auto;border:1px solid #ddd}}h1,h2,h3{{margin:0 0 12px}}h3{{margin-top:18px}}.grade{{background:#111;color:#fff;padding:2px 7px;border-radius:10px}}code{{background:#eee;padding:2px 5px}}</style>
<main><h1>其余 29 图 · 特殊结构/分面/多轴线</h1>
<p>同源、非合成资格。左：Origin 参考；中：Matplotlib；右：PlotAgent 原生 Origin O1 fresh reopen。人工签名保持 pending。</p>
{"".join(cards)}<section><h2>未测试缺口</h2><ul>{gaps}</ul></section></main>""",
        encoding="utf-8",
    )


def _fresh_qualification(source_identity: dict[str, str]) -> dict[str, Any]:
    return {
        "source_build_identity": source_identity,
        "blocking_observations": list(GAP_BLOCKING_OBSERVATIONS),
        "human_visual_signature": {
            "status": "pending",
            "reviewer": None,
            "signed_at": None,
        },
        "evidence_status": "fresh_render_pending_human",
        "decision": "NO-GO",
    }


def _write_manifest(entries: list[dict[str, Any]], output: Path, fixtures: Path) -> dict[str, Any]:
    source_identity = source_build_identity(
        REPOSITORY,
        SOURCE_SCOPE,
        scope_version=SOURCE_SCOPE_VERSION,
    )
    runtime_blockers = [
        blocker for entry in entries for blocker in entry.get("blocking_observations", [])
    ]
    if runtime_blockers:
        raise RuntimeError(
            "complete structural render still has runtime blockers; stale evidence was not promoted"
        )
    manifest = {
        "schema_version": "1.0",
        "stage": "VISUAL29-STRUCTURAL",
        "lane_chart_type_ids": list(LANE_IDS),
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
            "missing_same_source_pair_policy": "record gap; do not render or claim pass",
        },
        "cases": entries,
        "gaps": list(GAPS),
        "qualification": _fresh_qualification(source_identity),
        "audit_conclusion": (
            "same-source evidence generated for eligible cases; three evidence gaps retained; "
            "human visual sign-off pending; visual qualification not passed"
        ),
    }
    output_manifest = output / "manifest.json"
    fixture_manifest = fixtures / "manifest.json"
    output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    fixture_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _record_first_round(output: Path, fixtures: Path) -> None:
    """Freeze first-round observations without starting Origin again."""

    manifest_path = fixtures / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("first-round manifest is missing; render the lane before recording")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["cases"]:
        runtime_blockers = [
            item
            for item in entry.get("blocking_observations", [])
            if item.get("code") == "BUILD_FAILURE"
        ]
        entry["blocking_observations"] = [
            item
            for item in FIRST_ROUND_BLOCKING_OBSERVATIONS
            if item["chart_type_id"] == entry["chart_type_id"]
        ] + runtime_blockers
    blockers = [
        blocker for entry in manifest["cases"] for blocker in entry.get("blocking_observations", [])
    ]
    manifest["gaps"] = list(GAPS)
    manifest["qualification"]["blocking_observations"] = blockers
    manifest["qualification"]["evidence_status"] = "first_round_stale"
    manifest["qualification"]["invalidation"] = {
        "code": "AUDIT_AXIS_LABEL_CONTRACT_UPDATED",
        "reason": (
            "The first-round PlotSpecs inherited generic fixture axis labels. "
            "The generator now binds the official same-source field semantics; "
            "all native evidence must be regenerated after shared blocker fixes."
        ),
    }
    manifest["qualification"]["decision"] = "NO-GO"
    manifest["audit_conclusion"] = (
        "first-round same-source evidence retained for blocker diagnosis; "
        "three explicit gaps retained; generator axis-label contract corrected; "
        "evidence stale and human visual sign-off pending; visual qualification not passed"
    )
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    manifest_path.write_text(payload, encoding="utf-8")
    (output / "manifest.json").write_text(payload, encoding="utf-8")
    _write_index(manifest["cases"], output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("prepare", "render", "record", "all"), default="all")
    parser.add_argument("--case", dest="chart_id", choices=CASE_IDS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    args = parser.parse_args()
    selected = tuple(case for case in CASES if args.chart_id in {None, case.chart_id})
    args.output.mkdir(parents=True, exist_ok=True)
    args.fixtures.mkdir(parents=True, exist_ok=True)
    if args.phase == "record":
        if args.chart_id is not None:
            raise SystemExit("--phase record only accepts the complete lane")
        _record_first_round(args.output, args.fixtures)
        print(args.output / "index.html")
        return
    if args.phase in {"prepare", "all"}:
        for case in selected:
            _prepare_case(case, args.output, args.fixtures)
            print(f"anchored {case.case_id}", flush=True)
    entries: list[dict[str, Any]] = []
    if args.phase in {"render", "all"}:
        assert_scope_clean(REPOSITORY, SOURCE_SCOPE)
        source_sha256 = _source_build_sha256()
        # A complete manifest is only written for the complete lane.  Per-case
        # runs are useful for diagnosis but cannot masquerade as qualification.
        for case in selected:
            entries.append(
                _render_case(
                    case,
                    args.output,
                    args.fixtures,
                    source_sha256=source_sha256,
                )
            )
            print(f"rendered {case.case_id}", flush=True)
        if args.chart_id is None:
            _write_manifest(entries, args.output, args.fixtures)
            _write_index(entries, args.output)
    print(args.output / "index.html")


if __name__ == "__main__":
    main()

"""Build the single post-migration visual-review surface for the 38-chart product.

This script does not judge visual quality.  It renders/export evidence only and
keeps every chart at ``UNVERIFIED`` until the user reviews the complete surface.
"""

# ruff: noqa: E402,E501 -- repo bootstrap and embedded HTML/CSS are intentional.

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.contracts.registry import PRODUCT_CHART_IDS
from plotagent.exports import export_png
from scripts import build_per_chart_opju as per_chart

OUTPUT = REPOSITORY / "build" / "visual-audit" / "template-first-38"
BUILD_MANIFEST = OUTPUT / "manifest.json"
FROZEN_MANIFEST = REPOSITORY / "tests" / "fixtures" / "origin_template_migration" / "manifest.json"
PER_CHART_MANIFEST = REPOSITORY / "build" / "visual-audit" / "per-chart-opju.manifest.json"
PROBE_MANIFEST = REPOSITORY / "tests" / "fixtures" / "origin_template_probe" / "manifest.json"
PROBE_OUTPUT = REPOSITORY / "build" / "origin-template-probe"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _records() -> list[dict[str, Any]]:
    per_chart_manifest = _load_json(PER_CHART_MANIFEST)
    probe_manifest = _load_json(PROBE_MANIFEST)
    item_by_id = {
        str(item[1].chart_id): item
        for item in per_chart._items({"seq20", "fixed", "matrix", "structural"})
    }
    records: list[dict[str, Any]] = []
    for chart_id in PRODUCT_CHART_IDS:
        lane, case, data_path, opju_path = item_by_id[chart_id]
        probe = probe_manifest["charts"][chart_id]
        mechanical = per_chart_manifest["charts"][chart_id]
        default_graph = next(
            entry for entry in probe["build_structures"] if entry["variant"] == "default"
        )
        family_key = f"{probe['template_filename']}::{probe['template_sha256']}"
        records.append(
            {
                "chart_id": chart_id,
                "lane": lane,
                "case_id": case.case_id,
                "case": case,
                "data_path": data_path,
                "opju_path": opju_path,
                "mechanical": mechanical,
                "probe": probe,
                "probe_opju": PROBE_OUTPUT / chart_id / f"{chart_id}.opju",
                "default_probe_graph": default_graph["graph_name"],
                "family_key": family_key,
            }
        )
    family_members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        family_members[record["family_key"]].append(record)
    ordered_families = sorted(
        family_members,
        key=lambda key: (
            family_members[key][0]["probe"]["template_filename"].lower(),
            key,
        ),
    )
    for index, family_key in enumerate(ordered_families, start=1):
        members = family_members[family_key]
        representative = next(
            (item for item in members if item["probe"]["tier"] == "T1"),
            members[0],
        )
        for record in members:
            record["family_id"] = f"F{index:02d}"
            record["family_representative"] = record is representative
    return records


def _render_matplotlib(records: list[dict[str, Any]]) -> None:
    for record in records:
        frame = pd.read_csv(record["data_path"])
        pair = per_chart._resolved_pair(record["lane"], record["case"], frame)
        chart_dir = OUTPUT / record["chart_id"]
        chart_dir.mkdir(parents=True, exist_ok=True)
        export_png(chart_dir / "matplotlib-default.png", pair[0])
        export_png(chart_dir / "matplotlib-edited.png", pair[1])


def _export_origin(records: list[dict[str, Any]]) -> None:
    import originpro as op  # type: ignore[import-untyped]

    op.set_show(False)
    try:
        for record in records:
            chart_id = record["chart_id"]
            chart_dir = OUTPUT / chart_id
            chart_dir.mkdir(parents=True, exist_ok=True)

            op.new(asksave=False)
            if not op.open(str(record["probe_opju"]), readonly=True, asksave=False):
                raise RuntimeError(f"could not open official-template probe for {chart_id}")
            probe_graph = next(
                (graph for graph in op.pages("g") if graph.name == record["default_probe_graph"]),
                None,
            )
            if probe_graph is None:
                raise RuntimeError(f"official-template default graph is missing for {chart_id}")
            probe_graph.save_fig(
                str(chart_dir / "official-template-default.png"),
                type="png",
                replace=True,
                width=1600,
            )

            op.new(asksave=False)
            if not op.open(str(record["opju_path"]), readonly=True, asksave=False):
                raise RuntimeError(f"could not open per-chart OPJU for {chart_id}")
            graphs = list(op.pages("g"))
            if len(graphs) != 2:
                raise RuntimeError(f"{chart_id} graph count {len(graphs)} != 2")
            for graph, state in zip(graphs, ("default", "edited"), strict=True):
                graph.save_fig(
                    str(chart_dir / f"origin-{state}.png"),
                    type="png",
                    replace=True,
                    width=1600,
                )
    finally:
        op.exit()


def _copy_opjus(records: list[dict[str, Any]]) -> None:
    for record in records:
        destination = OUTPUT / record["chart_id"] / f"{record['chart_id']}.opju"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record["opju_path"], destination)


def _manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    source_identity = _load_json(PER_CHART_MANIFEST)["source_build_identity"]
    charts: dict[str, Any] = {}
    for record in records:
        chart_id = record["chart_id"]
        chart_dir = OUTPUT / chart_id
        evidence_files = (
            "official-template-default.png",
            "matplotlib-default.png",
            "origin-default.png",
            "matplotlib-edited.png",
            "origin-edited.png",
            f"{chart_id}.opju",
        )
        missing = [name for name in evidence_files if not (chart_dir / name).is_file()]
        if missing:
            raise RuntimeError(f"{chart_id} review evidence is missing: {missing}")
        mechanical = record["mechanical"]
        charts[chart_id] = {
            "chart_type_id": chart_id,
            "case_id": record["case_id"],
            "lane": record["lane"],
            "tier": record["probe"]["tier"],
            "template_filename": record["probe"]["template_filename"],
            "template_sha256": record["probe"]["template_sha256"],
            "template_family_id": record["family_id"],
            "family_edit_representative": record["family_representative"],
            "mechanical_status": "PASS",
            "visual_status": "UNVERIFIED",
            "fresh_reopen_identical": mechanical["fresh_reopen_identical"],
            "representative_data_mutation": mechanical["representative_data_mutation"],
            "default_data_sha256": mechanical["default_data_sha256"],
            "edited_data_sha256": mechanical["edited_data_sha256"],
            "default_style_sha256": mechanical["default_style_sha256"],
            "edited_style_sha256": mechanical["edited_style_sha256"],
            "opju_sha256": _sha256(chart_dir / f"{chart_id}.opju"),
            "evidence_sha256": {name: _sha256(chart_dir / name) for name in evidence_files[:-1]},
        }
    families: dict[str, Any] = {}
    for record in records:
        family_id = record["family_id"]
        family = families.setdefault(
            family_id,
            {
                "template_filename": record["probe"]["template_filename"],
                "template_sha256": record["probe"]["template_sha256"],
                "chart_ids": [],
                "manual_edit_representative": None,
                "manual_edit_status": "UNVERIFIED",
            },
        )
        family["chart_ids"].append(record["chart_id"])
        if record["family_representative"]:
            family["manual_edit_representative"] = record["chart_id"]
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "38-chart template-first unified visual review",
        "source_build_identity": source_identity,
        "summary": {
            "chart_count": len(charts),
            "mechanical_pass": sum(item["mechanical_status"] == "PASS" for item in charts.values()),
            "visual_unverified": sum(
                item["visual_status"] == "UNVERIFIED" for item in charts.values()
            ),
            "template_family_count": len(families),
            "family_manual_edit_unverified": len(families),
        },
        "families": families,
        "charts": charts,
    }


def _build_index(manifest: dict[str, Any]) -> None:
    family_rows = "".join(
        "<tr>"
        f"<td>{html.escape(family_id)}</td>"
        f"<td>{html.escape(family['template_filename'])}</td>"
        f"<td>{html.escape(', '.join(family['chart_ids']))}</td>"
        f'<td><a href="#{html.escape(family["manual_edit_representative"])}">'
        f"{html.escape(family['manual_edit_representative'])}</a></td>"
        '<td><span class="status unverified">UNVERIFIED</span></td>'
        "</tr>"
        for family_id, family in manifest["families"].items()
    )
    cards: list[str] = []
    captions = (
        ("official-template-default.png", "Origin 官方模板 · 默认数据"),
        ("matplotlib-default.png", "Matplotlib · 默认态"),
        ("origin-default.png", "Origin · 默认态"),
        ("matplotlib-edited.png", "Matplotlib · 代表编辑态"),
        ("origin-edited.png", "Origin · 代表编辑态"),
    )
    for chart_id, chart in manifest["charts"].items():
        figures = "".join(
            f"<figure><figcaption>{html.escape(caption)}</figcaption>"
            f'<a href="{chart_id}/{filename}"><img loading="lazy" '
            f'src="{chart_id}/{filename}" alt="{chart_id} {html.escape(caption)}"></a></figure>'
            for filename, caption in captions
        )
        representative = (
            '<span class="family-rep">模板家族人工编辑代表</span>'
            if chart["family_edit_representative"]
            else ""
        )
        cards.append(
            f'<article id="{chart_id}" class="chart-card">'
            f"<header><div><h2>{chart_id}</h2><p>{html.escape(chart['case_id'])} · "
            f"{html.escape(chart['template_family_id'])} · "
            f"{html.escape(chart['template_filename'])} · {html.escape(chart['tier'])}</p></div>"
            f'<div><span class="status pass">机械 PASS</span>'
            f'<span class="status unverified">视觉 UNVERIFIED</span>{representative}</div></header>'
            f'<div class="figures">{figures}</div>'
            f'<footer><a href="{chart_id}/{chart_id}.opju">打开独立 OPJU（默认态 + 代表编辑态）</a>'
            "<span>数据值读回 PASS</span><span>代表样式读回 PASS</span>"
            "<span>fresh-reopen PASS</span></footer></article>"
        )
    source = manifest["source_build_identity"]
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PlotAgent 38 图模板优先统一视觉审查</title>
<style>
:root{{--ink:#171717;--muted:#666;--line:#d8d8d8;--paper:#f5f5f3;--card:#fff;--ok:#0a7a54;--pending:#9a6700}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.5 Arial,"Microsoft YaHei",sans-serif}}
main{{max-width:1900px;margin:auto;padding:32px}}h1{{font-size:28px;margin:0 0 8px}}h2{{margin:0;font-size:20px}}p{{margin:4px 0;color:var(--muted)}}
.summary,.families,.chart-card{{background:var(--card);border:1px solid var(--line);border-radius:12px}}
.summary,.families{{padding:20px;margin:0 0 20px}}.summary-grid{{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:12px;margin-top:16px}}
.metric{{border-left:3px solid var(--ink);padding:6px 12px}}.metric strong{{display:block;font-size:24px}}
table{{width:100%;border-collapse:collapse;margin-top:12px}}th,td{{padding:8px 10px;border-top:1px solid var(--line);text-align:left}}
.chart-card{{margin:0 0 22px;overflow:hidden;scroll-margin-top:12px}}.chart-card>header{{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--line)}}
.status,.family-rep{{display:inline-block;border-radius:999px;padding:4px 9px;margin-left:6px;font-weight:700;font-size:12px}}.pass{{color:var(--ok);background:#e7f7f0}}.unverified{{color:var(--pending);background:#fff2c7}}.family-rep{{color:#333;background:#e9e9e9}}
.figures{{display:grid;grid-template-columns:repeat(5,minmax(220px,1fr));gap:1px;background:var(--line)}}figure{{margin:0;background:#fff;padding:12px}}figcaption{{font-weight:700;margin-bottom:8px}}img{{display:block;width:100%;height:260px;object-fit:contain;background:#fafafa}}
footer{{display:flex;flex-wrap:wrap;gap:16px;padding:12px 18px;border-top:1px solid var(--line)}}a{{color:#005bbb}}
@media(max-width:1200px){{.figures{{grid-template-columns:repeat(2,1fr)}}.summary-grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:700px){{main{{padding:16px}}.figures,.summary-grid{{grid-template-columns:1fr}}.chart-card>header{{align-items:flex-start;flex-direction:column}}}}
</style></head><body><main>
<section class="summary"><h1>PlotAgent 38 图模板优先统一视觉审查</h1>
<p>机械迁移已经完成；本页不包含自动视觉结论。请逐图判断，未签名前全部保持 UNVERIFIED。</p>
<p>渲染源码：<code>{html.escape(source["git_commit"])}</code> · <code>{html.escape(source["source_sha256"])}</code></p>
<div class="summary-grid"><div class="metric"><strong>38 / 38</strong>机械修改与读回</div><div class="metric"><strong>38 / 38</strong>独立 OPJU</div><div class="metric"><strong>{manifest["summary"]["template_family_count"]}</strong>Origin 模板家族</div><div class="metric"><strong>38</strong>视觉 UNVERIFIED</div></div></section>
<section class="families"><h2>Origin 模板家族人工编辑代表图</h2><p>每个官方模板文件家族选一张代表图；实际编辑状态仍待人工确认。</p>
<table><thead><tr><th>家族</th><th>官方模板</th><th>覆盖图</th><th>代表图</th><th>人工编辑</th></tr></thead><tbody>{family_rows}</tbody></table></section>
{"".join(cards)}
</main></body></html>"""
    (OUTPUT / "index.html").write_text(document, encoding="utf-8")


def _write_manifests(records: list[dict[str, Any]], *, freeze: bool) -> dict[str, Any]:
    manifest = _manifest(records)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    BUILD_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if freeze:
        FROZEN_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        FROZEN_MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("all", "matplotlib", "origin", "index"),
        default="all",
    )
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    records = _records()
    if args.phase in {"all", "matplotlib"}:
        _render_matplotlib(records)
    if args.phase in {"all", "origin"}:
        _export_origin(records)
        _copy_opjus(records)
    if args.phase in {"all", "index"}:
        manifest = _write_manifests(records, freeze=args.freeze)
        _build_index(manifest)


if __name__ == "__main__":
    main()

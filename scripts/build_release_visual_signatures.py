"""Build a reviewable 34-chart visual-signature sheet from a frozen matrix."""

# ruff: noqa: E501 -- keeping the self-contained audit HTML legible is preferable here.

from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
import struct
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from plotagent.engine.backends.origin.recipe import ORIGIN_RENDERABLE_RECIPES

REPOSITORY = Path(__file__).resolve().parents[1]


def _git(repository: Path, *args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=repository, text=True, encoding="utf-8"
    ).strip()


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"visual signature is not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


def _representative_rows(offline: Path) -> dict[str, dict[str, Any]]:
    raw_rows = json.loads((offline / "matrix-results.json").read_text(encoding="utf-8"))
    rows = {
        str(row["profile_id"]): row
        for row in raw_rows
        if row["variant"] == "representative" and row["format"] == "png"
    }
    expected = {str(profile_id) for profile_id in ORIGIN_RENDERABLE_RECIPES}
    if len(rows) != 34 or set(rows) != expected:
        raise RuntimeError("visual signatures require exactly one representative PNG for all 34 charts")
    return rows


def _chart_row(profile_id: str, source: Path, destination: Path) -> dict[str, Any]:
    recipe = ORIGIN_RENDERABLE_RECIPES[profile_id]  # type: ignore[index]
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    digest = _sha(destination)
    width, height = _png_size(destination)
    template = recipe.primary_template
    template_or_process = "Origin 原生流程" if template is None else template.filename
    return {
        "profile_id": profile_id,
        "chinese_name": recipe.chinese_name,
        "official_name": recipe.official_name,
        "template_or_process": template_or_process,
        "official_entry": recipe.official_entry,
        "official_help_url": str(recipe.official_help_url),
        "image": f"images/{profile_id}.png",
        "sha256": digest,
        "size_bytes": destination.stat().st_size,
        "width": width,
        "height": height,
        "review_status": "PENDING",
    }


def _page(manifest: dict[str, Any]) -> str:
    cards = "".join(
        f"""
<article id="{html.escape(chart['profile_id'])}" data-search="{html.escape((chart['profile_id'] + ' ' + chart['chinese_name'] + ' ' + chart['official_name']).lower())}">
  <a class="figure" href="{html.escape(chart['image'])}">
    <img loading="lazy" src="{html.escape(chart['image'])}" alt="{html.escape(chart['chinese_name'])}代表数据渲染结果">
  </a>
  <div class="caption">
    <div><b>{html.escape(chart['profile_id'])}</b><h2>{html.escape(chart['chinese_name'])}</h2></div>
    <p>{html.escape(chart['official_name'])}</p>
    <dl><dt>Origin</dt><dd>{html.escape(chart['template_or_process'])}</dd><dt>签名</dt><dd><code>{html.escape(chart['sha256'][:12])}</code></dd></dl>
  </div>
</article>"""
        for chart in manifest["charts"]
    )
    commit = html.escape(manifest["git_head"][:7])
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PlotAgent 34图视觉签名 · {commit}</title>
<style>
:root{{--page:#eef2f7;--surface:#fff;--ink:#18212f;--muted:#5a687b;--line:#d7dee8;--accent:#17283e;--focus:#4263eb}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--page);color:var(--ink);font:14px/1.45 "Microsoft YaHei UI","Segoe UI",sans-serif}}
header{{position:sticky;top:0;z-index:2;display:flex;align-items:center;gap:18px;padding:16px 24px;background:rgb(255 255 255 / 96%);border-bottom:1px solid var(--line);backdrop-filter:blur(8px)}}
.title{{min-width:max-content}}h1{{margin:0;font-size:20px;letter-spacing:-.01em}}.title p{{margin:3px 0 0;color:var(--muted);font-size:12px}}
input{{width:min(420px,42vw);height:38px;margin-left:auto;padding:0 12px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font:inherit}}
input:focus-visible{{outline:2px solid var(--focus);outline-offset:2px}}.count{{min-width:max-content;color:var(--muted);font-size:12px}}
main{{max-width:1660px;margin:auto;padding:20px 24px 44px}}.notice{{display:flex;gap:12px;align-items:flex-start;margin-bottom:18px;padding:12px 14px;background:#e7edf5;border-radius:10px}}
.notice b{{white-space:nowrap}}.notice p{{margin:0;color:#405069}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px}}
article{{min-width:0;background:var(--surface);border-radius:10px;overflow:hidden}}.figure{{display:block;height:280px;padding:8px;background:#fff;border-bottom:1px solid var(--line)}}
img{{display:block;width:100%;height:100%;object-fit:contain}}.caption{{padding:11px 13px 13px}}.caption>div{{display:flex;gap:8px;align-items:baseline}}
.caption b{{color:var(--focus);font-size:12px}}h2{{margin:0;font-size:15px}}.caption p{{margin:3px 0 9px;color:var(--muted);font-size:12px}}
dl{{display:grid;grid-template-columns:54px minmax(0,1fr);gap:3px 7px;margin:0;font-size:11px}}dt{{color:var(--muted)}}dd{{min-width:0;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}code{{font-family:"Cascadia Mono",Consolas,monospace}}
article[hidden]{{display:none}}@media(max-width:760px){{header{{flex-wrap:wrap;padding:12px}}input{{order:3;width:100%;margin:0}}main{{padding:12px}}.figure{{height:240px}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
</style></head><body>
<header><div class="title"><h1>34 图视觉签名</h1><p>当前候选 {commit} · representative 数据 · 等待最终视觉验收</p></div><input id="filter" type="search" placeholder="按图类、编号或 Origin 名称筛选" aria-label="筛选图形"><span class="count" id="count">34 / 34</span></header>
<main><section class="notice"><b>审查口径</b><p>逐图检查图类语义、数据表达和明显视觉错误。每张图下方给出 Origin 官方名称或模板与 PNG 哈希；本页不替代 OPJU fresh reopen 和机械读回。</p></section><section class="grid">{cards}</section></main>
<script>const input=document.querySelector('#filter');const cards=[...document.querySelectorAll('article')];const count=document.querySelector('#count');input.addEventListener('input',()=>{{const q=input.value.trim().toLowerCase();let visible=0;cards.forEach(card=>{{card.hidden=!!q&&!card.dataset.search.includes(q);if(!card.hidden)visible++}});count.textContent=`${{visible}} / ${{cards.length}}`;}});</script>
</body></html>"""


def build_visual_signatures(
    *, offline: Path, output: Path, repository: Path = REPOSITORY
) -> dict[str, Any]:
    offline = offline.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    metadata = json.loads((offline / "run-metadata.json").read_text(encoding="utf-8"))
    head = _git(repository, "rev-parse", "HEAD")
    if metadata["git_head"] != head:
        raise RuntimeError("offline matrix HEAD differs from the visual-signature HEAD")
    rows = _representative_rows(offline)
    charts: list[dict[str, Any]] = []
    for profile_id in ORIGIN_RENDERABLE_RECIPES:
        key = str(profile_id)
        row = rows[key]
        if row["status"] != "PASS" or row["artifact"] is None:
            raise RuntimeError(f"{key} representative PNG is not qualified")
        source = offline / row["artifact"]
        if not source.is_file() or _sha(source) != row["artifact_sha256"]:
            raise RuntimeError(f"{key} representative PNG identity differs from the matrix")
        charts.append(_chart_row(key, source, output / "images" / f"{key}.png"))
    manifest: dict[str, Any] = {
        "schema_version": "plotagent.release-visual-signatures.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_head": head,
        "source_offline_matrix": str(offline),
        "chart_count": len(charts),
        "review_status": "PENDING",
        "charts": charts,
    }
    (output / "visual-signatures.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output / "visual-signatures.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(charts[0]))
        writer.writeheader()
        writer.writerows(charts)
    (output / "index.html").write_text(_page(manifest), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        head = _git(REPOSITORY, "rev-parse", "--short", "HEAD")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = REPOSITORY / "build" / "visual-audit" / f"release-signatures-{head}-{stamp}"
    else:
        output = args.output
    manifest = build_visual_signatures(offline=args.offline, output=output)
    print(f"OUTPUT={output.resolve()}")
    print(f"CHARTS={manifest['chart_count']} STATUS={manifest['review_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the project-local visual audit for the final OriginRecipe renderer batch."""

# ruff: noqa: E501 -- embedded HTML/CSS is clearer when kept in complete declarations.

from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote

REPOSITORY = Path(__file__).resolve().parents[1]
ROOT = REPOSITORY / "build" / "visual-audit" / "origin-recipe-renderer-final"
CHARTS = (
    ("K12", "列散点图", "Column Scatter", "ColumnScatter.otp", "Plot.ogs [ColumnScatter]"),
    ("K13", "Tukey箱线图", "Box Chart", "BOX.OTP", "Plot.ogs [BoxChart]"),
    ("K14", "小提琴图", "Violin Plot", "Violin.otpu", "Plot.ogs [ViolinPlot]"),
    ("K15", "直方图", "Histogram", "Hist.otpu", "Plot.ogs [Histogram]"),
    (
        "X13",
        "人口金字塔图",
        "Population Pyramid",
        "PopulationPyramid.otpu",
        "Plot.ogs [PopulationPyramid]",
    ),
    ("X23", "双Y轴Y-Y图", "2Ys Y-Y", "DOUBLEY.OTP", "Plot.ogs [2Ys_Y-Y]"),
    ("X39", "线条序列图", "Line Series", "BoxLser.otpu", "Plot.ogs [LineSeries]"),
    ("X40", "前后对比图", "Before After", "BeforeAfter.otpu", "Plot.ogs [BeforeAfter]"),
)


def _uri(path: Path) -> str:
    return "file:///" + quote(path.resolve().as_posix(), safe="/:.-_")


def _find_directory(chart_id: str) -> Path:
    matches = tuple(path for path in ROOT.glob(f"{chart_id}-*") if path.is_dir())
    if len(matches) != 1:
        raise RuntimeError(f"expected one audit directory for {chart_id}, found {matches}")
    return matches[0]


def _asset(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"missing visual-audit asset: {path}")
    return path


def _card(
    chart_id: str,
    chinese_name: str,
    official_name: str,
    template: str,
    dispatcher: str,
) -> str:
    directory = _find_directory(chart_id)
    images = (
        ("Matplotlib 默认态", _asset(directory, "matplotlib-default.png")),
        ("Origin 官方模板默认态（fresh reopen）", _asset(directory, "origin-default-fresh.png")),
        ("Matplotlib 代表编辑态", _asset(directory, "matplotlib-edited.png")),
        ("Origin 原生代表编辑态（fresh reopen）", _asset(directory, "origin-edited-fresh.png")),
    )
    panels = "".join(
        f"<figure><figcaption>{html.escape(label)}</figcaption>"
        f'<a href="{_uri(path)}"><img loading="lazy" src="{_uri(path)}" alt="{html.escape(label)}"></a>'
        "</figure>"
        for label, path in images
    )
    links = " · ".join(
        f'<a href="{_uri(_asset(directory, name))}">{html.escape(label)}</a>'
        for label, name in (
            ("默认 OPJU", "origin-default.opju"),
            ("编辑 OPJU", "origin-edited.opju"),
            ("默认读回", "origin-default.readback.json"),
            ("编辑读回", "origin-edited.readback.json"),
            ("执行轨迹", "execution-trace.jsonl"),
        )
    )
    return f"""
      <article id="{chart_id}" class="card">
        <header><h2>{chart_id}　{html.escape(chinese_name)}｜{html.escape(official_name)}</h2>
          <span class="badge">LIVE + FRESH</span></header>
        <p><b>本机官方模板：</b>{html.escape(template)}　<b>菜单入口：</b>{html.escape(dispatcher)}</p>
        <p class="links">{links}</p>
        <div class="grid">{panels}</div>
      </article>"""


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    cards = "".join(_card(*chart) for chart in CHARTS)
    index = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OriginRecipe renderer 视觉审计</title><style>
:root{{--bg:#f4f6f8;--card:#fff;--ink:#17202a;--muted:#5f6b76;--line:#dce1e6;--ok:#127a48}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Microsoft YaHei UI",sans-serif}}
main{{max-width:1680px;margin:auto;padding:28px}}.intro,.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 2px 12px #18232d0d}}
.intro{{padding:24px;margin-bottom:22px}}h1{{margin:0 0 8px;font-size:28px}}.intro p{{margin:5px 0;color:var(--muted)}}
nav{{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}}nav a,.links a{{color:#145c9e;text-decoration:none}}nav a{{padding:5px 10px;border:1px solid var(--line);border-radius:999px}}
.card{{padding:18px;margin:18px 0;scroll-margin-top:12px}}header{{display:flex;align-items:center;justify-content:space-between;gap:16px}}h2{{font-size:20px;margin:0}}
.badge{{white-space:nowrap;background:#e7f6ee;color:var(--ok);border:1px solid #abd9c1;border-radius:999px;padding:3px 9px;font-size:12px;font-weight:700}}
.card p{{margin:8px 0}}.links{{font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px}}
figure{{margin:0;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}}figcaption{{padding:8px 10px;background:#f7f8fa;border-bottom:1px solid var(--line);font-weight:600}}
img{{display:block;width:100%;height:520px;object-fit:contain;background:white}}@media(max-width:900px){{main{{padding:12px}}.grid{{grid-template-columns:1fr}}img{{height:auto}}}}
</style></head><body><main><section class="intro"><h1>OriginRecipe renderer 视觉审计</h1>
<p>本页只展示本轮按 Origin 2024 官方模板/菜单重做并完成真实保存、退出、全新会话重开的 8 张图。</p>
<p>每张图按名称区分；点击图片看原图，点击 OPJU 可在 Origin 中继续编辑。结构通过不替代你的视觉签名。</p>
<nav>{"".join(f'<a href="#{item[0]}">{item[0]} {html.escape(item[1])}</a>' for item in CHARTS)}</nav></section>
{cards}</main></body></html>"""
    (ROOT / "index.html").write_text(index, encoding="utf-8")
    manifest = {
        "charts": [
            {"profile_id": item[0], "chinese_name": item[1], "official_name": item[2]}
            for item in CHARTS
        ],
        "count": len(CHARTS),
        "qualification": "renderer live build + independent fresh reopen; user visual review pending",
    }
    (ROOT / "audit-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(ROOT / "index.html")


if __name__ == "__main__":
    main()

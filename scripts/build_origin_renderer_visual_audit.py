"""Build the complete project-local visual audit for renderable Origin recipes."""

# ruff: noqa: E501 -- complete HTML/CSS declarations are easier to audit in place.

from __future__ import annotations

import html
import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from plotagent.engine.backends.origin.recipe import ORIGIN_RENDERABLE_RECIPES

REPOSITORY = Path(__file__).resolve().parents[1]
VISUAL_ROOT = REPOSITORY / "build" / "visual-audit"
FIRST_BATCH = VISUAL_ROOT / "agent-native-renderer"
FINAL_BATCH = VISUAL_ROOT / "origin-recipe-renderer-final"
OUTPUT = VISUAL_ROOT / "origin-recipe-renderer-35"
VISUAL_REVIEW_STATUS = "approved"
VISUAL_REVIEWED_ON = "2026-08-12"
VISUAL_REVIEW_NOTE = "产品负责人确认35图视觉验收通过"


class _AuditPageParser(HTMLParser):
    def __init__(self, page: Path) -> None:
        super().__init__()
        self.page = page
        self.figures: list[tuple[str, str]] = []
        self.links: list[tuple[str, str]] = []
        self._inside_figure = False
        self._inside_caption = False
        self._figure_image: str | None = None
        self._caption: list[str] = []
        self._inside_link = False
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value for key, value in attrs}
        if tag == "figure":
            self._inside_figure = True
            self._figure_image = None
            self._caption = []
        elif tag == "figcaption" and self._inside_figure:
            self._inside_caption = True
        elif tag == "img" and self._inside_figure and values.get("src"):
            self._figure_image = urljoin(self.page.resolve().as_uri(), values["src"])
        elif tag == "a" and values.get("href"):
            self._inside_link = True
            self._link_href = urljoin(self.page.resolve().as_uri(), values["href"])
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "figcaption":
            self._inside_caption = False
        elif tag == "figure":
            if self._figure_image is not None:
                caption = "".join(self._caption).strip() or "审计图"
                self.figures.append((caption, self._figure_image))
            self._inside_figure = False
        elif tag == "a" and self._inside_link:
            if self._link_href is not None:
                self.links.append(("".join(self._link_text).strip(), self._link_href))
            self._inside_link = False
            self._link_href = None

    def handle_data(self, data: str) -> None:
        if self._inside_caption:
            self._caption.append(data)
        if self._inside_link:
            self._link_text.append(data)


def _single_directory(root: Path, profile_id: str) -> Path | None:
    matches = tuple(path for path in root.glob(f"{profile_id}-*") if path.is_dir())
    if len(matches) > 1:
        raise RuntimeError(f"multiple visual directories for {profile_id}: {matches}")
    return None if not matches else matches[0]


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _assert_file_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise RuntimeError(f"visual evidence is not a local file: {uri}")
    raw = unquote(parsed.path)
    if len(raw) >= 3 and raw[0] == "/" and raw[2] == ":":
        raw = raw[1:]
    path = Path(raw)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"missing visual evidence: {path}")


def _first_batch_evidence(profile_id: str) -> tuple[str, list[tuple[str, str]], list[tuple[str, str]]]:
    directory = _single_directory(FIRST_BATCH, profile_id)
    if directory is None:
        raise RuntimeError(f"missing first-batch audit for {profile_id}")
    page = directory / "index.html"
    parser = _AuditPageParser(page)
    parser.feed(page.read_text(encoding="utf-8"))
    if len(parser.figures) < 4:
        raise RuntimeError(f"{profile_id} has only {len(parser.figures)} audit figures")
    for _caption, uri in parser.figures:
        _assert_file_uri(uri)
    for _label, uri in parser.links:
        if uri.lower().endswith(".opju"):
            _assert_file_uri(uri)
    return _file_uri(page), parser.figures, parser.links


def _final_batch_evidence(profile_id: str) -> tuple[str, list[tuple[str, str]], list[tuple[str, str]]]:
    directory = _single_directory(FINAL_BATCH, profile_id)
    if directory is None:
        raise RuntimeError(f"missing final-batch audit for {profile_id}")
    figures = [
        ("Matplotlib 默认态", _file_uri(directory / "matplotlib-default.png")),
        ("Origin 官方模板默认态（独立 fresh reopen）", _file_uri(directory / "origin-default-fresh.png")),
        ("Matplotlib 代表编辑态", _file_uri(directory / "matplotlib-edited.png")),
        ("Origin 原生代表编辑态（独立 fresh reopen）", _file_uri(directory / "origin-edited-fresh.png")),
    ]
    links = [
        ("默认 OPJU", _file_uri(directory / "origin-default.opju")),
        ("编辑 OPJU", _file_uri(directory / "origin-edited.opju")),
        ("执行轨迹", _file_uri(directory / "execution-trace.jsonl")),
    ]
    for _label, uri in (*figures, *links):
        _assert_file_uri(uri)
    return f"{_file_uri(FINAL_BATCH / 'index.html')}#{profile_id}", figures, links


def _evidence(profile_id: str) -> tuple[str, list[tuple[str, str]], list[tuple[str, str]]]:
    if _single_directory(FINAL_BATCH, profile_id) is not None:
        return _final_batch_evidence(profile_id)
    return _first_batch_evidence(profile_id)


def _card(profile_id: str) -> tuple[str, dict[str, object]]:
    recipe = ORIGIN_RENDERABLE_RECIPES[profile_id]  # type: ignore[index]
    page, figures, raw_links = _evidence(profile_id)
    opju_links = [(label or "OPJU", uri) for label, uri in raw_links if uri.lower().endswith(".opju")]
    panels = "".join(
        f"<figure><figcaption>{html.escape(caption)}</figcaption>"
        f'<a href="{html.escape(uri)}"><img loading="lazy" src="{html.escape(uri)}" '
        f'alt="{html.escape(recipe.chinese_name)} {html.escape(caption)}"></a></figure>'
        for caption, uri in figures
    )
    links = [f'<a href="{html.escape(page)}">打开本图完整审计</a>']
    links.extend(
        f'<a href="{html.escape(uri)}">{html.escape(label)}</a>' for label, uri in opju_links
    )
    template = recipe.primary_template
    template_name = "原生组合流程" if template is None else template.filename
    card = f"""
<article id="{profile_id}" data-name="{html.escape(recipe.chinese_name)} {html.escape(recipe.official_name)}">
  <header><div><h2>{html.escape(recipe.chinese_name)}</h2><p>{html.escape(recipe.official_name)}</p></div><span>视觉验收通过</span></header>
  <p class="route"><b>Origin 模板/流程：</b>{html.escape(template_name)}　<b>创建入口：</b>{html.escape(recipe.official_entry)}</p>
  <p class="links">{'　'.join(links)}</p>
  <div class="figures">{panels}</div>
</article>"""
    manifest = {
        "profile_id": profile_id,
        "chinese_name": recipe.chinese_name,
        "official_name": recipe.official_name,
        "official_help_url": str(recipe.official_help_url),
        "template_or_process": template_name,
        "audit_page": page,
        "figure_count": len(figures),
        "figures": [{"caption": label, "uri": uri} for label, uri in figures],
        "opju": [{"label": label, "uri": uri} for label, uri in opju_links],
        "visual_status": VISUAL_REVIEW_STATUS,
        "visual_reviewed_on": VISUAL_REVIEWED_ON,
    }
    return card, manifest


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    profile_ids = tuple(str(profile_id) for profile_id in ORIGIN_RENDERABLE_RECIPES)
    if len(profile_ids) != 35:
        raise RuntimeError(f"expected 35 renderable recipes, found {len(profile_ids)}")
    cards_and_rows = [_card(profile_id) for profile_id in profile_ids]
    cards = "".join(card for card, _row in cards_and_rows)
    rows = [row for _card_html, row in cards_and_rows]
    nav = "".join(
        f'<a href="#{html.escape(str(row["profile_id"]))}">{html.escape(str(row["chinese_name"]))}</a>'
        for row in rows
    )
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PlotAgent OriginRecipe renderer｜35 图视觉审计</title><style>
:root{{--bg:#f3f5f7;--card:#fff;--ink:#17202a;--muted:#5b6670;--line:#d8dee4;--accent:#1769aa;--warn:#8a5a00}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 "Microsoft YaHei UI",sans-serif}}
main{{max-width:1720px;margin:auto;padding:28px}}.intro,article{{background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 2px 12px #14202a0d}}
.intro{{padding:24px;margin-bottom:20px}}h1{{margin:0 0 8px;font-size:28px}}.intro p{{margin:5px 0;color:var(--muted)}}
#filter{{width:min(520px,100%);margin:14px 0 8px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;font:inherit}}
nav{{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}}nav a,.links a{{color:var(--accent);text-decoration:none}}nav a{{border:1px solid var(--line);border-radius:999px;padding:4px 9px;background:#fff}}
article{{padding:18px;margin:18px 0;scroll-margin-top:12px}}article header{{display:flex;align-items:center;justify-content:space-between;gap:14px;border-bottom:1px solid var(--line);padding-bottom:10px}}
h2{{font-size:21px;margin:0}}header p{{margin:2px 0 0;color:var(--muted)}}header span{{white-space:nowrap;color:var(--warn);background:#fff6dd;border:1px solid #e5c77f;border-radius:999px;padding:3px 9px;font-size:12px}}
.route,.links{{margin:9px 0}}.links{{font-size:13px}}.figures{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
figure{{margin:0;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}}figcaption{{padding:7px 10px;background:#f7f8fa;border-bottom:1px solid var(--line);font-weight:600}}
img{{display:block;width:100%;height:430px;object-fit:contain;background:#fff}}@media(max-width:900px){{main{{padding:12px}}.figures{{grid-template-columns:1fr}}img{{height:auto}}}}
</style></head><body><main><section class="intro"><h1>PlotAgent OriginRecipe renderer｜35 图视觉审计</h1>
<p>本页是当前可用 Origin renderer 的统一视觉交付：35 类均来自已经核实的 Origin 2024 官方模板、菜单、X-Function 或原生组合流程。</p>
<p>结构、数据绑定和 fresh reopen 已通过机械验证；产品负责人已于2026-08-12确认35图视觉验收通过。核密度图、Kaplan–Meier 生存曲线、森林图已明确排除，不在本页伪装实现。</p>
<p><a href="audit-manifest.json">审计清单</a>　<a href="../origin-recipe-renderer-final/index.html">最后 8 图原始审计页</a>　<a href="../agent-native-renderer/index.html">前批次原始审计页</a></p>
<input id="filter" type="search" placeholder="输入中文图类名或 Origin 官方名称筛选"><nav>{nav}</nav></section>{cards}
<script>const q=document.querySelector('#filter');q.addEventListener('input',()=>{{const v=q.value.trim().toLowerCase();document.querySelectorAll('article').forEach(x=>x.hidden=v&&!x.dataset.name.toLowerCase().includes(v));}});</script>
</main></body></html>"""
    (OUTPUT / "index.html").write_text(page, encoding="utf-8")
    manifest = {
        "schema_version": "origin-recipe-renderer-audit.v1",
        "source_commit": subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=REPOSITORY, text=True
        ).strip(),
        "renderable_count": len(rows),
        "qualification": "mechanically qualified; user visual review approved",
        "visual_review": {
            "status": VISUAL_REVIEW_STATUS,
            "reviewed_on": VISUAL_REVIEWED_ON,
            "note": VISUAL_REVIEW_NOTE,
            "scope": "all 35 Origin-renderable profiles",
        },
        "charts": rows,
    }
    (OUTPUT / "audit-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(OUTPUT / "index.html")


if __name__ == "__main__":
    main()

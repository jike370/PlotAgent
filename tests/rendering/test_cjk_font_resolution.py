from __future__ import annotations

import hashlib
import warnings
from pathlib import Path

from matplotlib import font_manager
from matplotlib.ft2font import FT2Font
from matplotlib.text import Text

from plotagent.contracts.plots import (
    AnnotationSpec,
    CalculatedSeriesData,
    SafeRichText,
    SafeTextNode,
)
from plotagent.exports import export_png, export_svg
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable
from plotagent.rendering.matplotlib.adapter import MatplotlibRenderer
from tests.rendering.fixture_factory import build_plot_and_store


def _text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _cjk_plot() -> tuple[object, RenderDataStore]:
    plot, store = build_plot_and_store("K08")
    series = plot.series[0]
    assert isinstance(series.data, CalculatedSeriesData)
    fields = series.data.role_fields
    table = RenderTable.from_columns(
        {
            fields[0]: ("对照组", "处理组", "恢复组"),
            fields[1]: (1.0, 2.5, 1.8),
            fields[2]: (0.8, 2.2, 1.5),
            fields[3]: (1.2, 2.8, 2.1),
        }
    )
    content_hash = series.data.calculation_result_ref.content_hash
    axes = tuple(
        axis.model_copy(
            update={"label": _text("实验条件" if axis.orientation == "x" else "响应值")}
        )
        for axis in plot.axes
    )
    updated = plot.model_copy(
        update={
            "title": _text("中文科研图标题"),
            "axes": axes,
            "series": (series.model_copy(update={"label": _text("测量系列")}),),
            "legend": plot.legend.model_copy(update={"visible": True}),
            "annotations": (
                AnnotationSpec(
                    annotation_id="annotation:cjk.note",
                    kind="text",
                    text=_text("显著变化"),
                    x=1.0,
                    y=2.5,
                ),
            ),
        }
    )
    return updated, RenderDataStore({**store.tables, content_hash: table})


def test_cjk_font_covers_title_axes_legend_ticks_and_annotation() -> None:
    plot, store = _cjk_plot()
    resolved = PlotResolver().resolve(plot, store)
    font = resolved.plan.fonts[0]
    path = Path(
        font_manager.findfont(
            font_manager.FontProperties(family=[font.family]),
            fallback_to_default=False,
        )
    )
    face = FT2Font(path)
    required = set("中文科研图标题实验条件响应值测量系列显著变化对照组处理恢复")

    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == font.file_hash
    assert all(face.get_char_index(ord(character)) != 0 for character in required)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        figure = MatplotlibRenderer().build_figure(resolved)
        figure.canvas.draw()

    assert not [warning for warning in caught if "Glyph" in str(warning.message)]
    rendered = {
        item.get_text(): tuple(item.get_fontproperties().get_family())
        for item in figure.findobj(match=Text)
        if item.get_text()
    }
    expected_text = {
        "中文科研图标题",
        "实验条件",
        "响应值",
        "测量系列",
        "显著变化",
        "对照组",
        "处理组",
        "恢复组",
    }
    assert expected_text <= set(rendered)
    assert all(font.family in rendered[text] for text in expected_text)


def test_cjk_png_and_svg_share_resolved_vector_font(tmp_path: Path) -> None:
    plot, store = _cjk_plot()
    resolved = PlotResolver().resolve(plot, store)

    png = export_png(tmp_path / "cjk.png", resolved)
    svg = export_svg(tmp_path / "cjk.svg", resolved)
    svg_text = (tmp_path / "cjk.svg").read_text(encoding="utf-8")

    assert png.render_plan_hash == svg.render_plan_hash == resolved.render_plan_hash
    assert svg.element_counts.get("text", 0) == 0
    assert svg.element_counts.get("image", 0) == 0
    assert "<path" in svg_text


def test_ascii_only_plot_keeps_requested_font_and_plan_geometry() -> None:
    plot, store = build_plot_and_store("K01")
    resolved = PlotResolver().resolve(plot, store)

    requested = plot.resolved_style.font_family
    requested_path = Path(
        font_manager.findfont(
            font_manager.FontProperties(family=[requested]),
            fallback_to_default=False,
        )
    )
    assert resolved.plan.fonts[0].family == requested
    assert (
        resolved.plan.fonts[0].file_hash == hashlib.sha256(requested_path.read_bytes()).hexdigest()
    )
    assert resolved.plan.fonts[0].size == plot.resolved_style.font_size

"""Build Origin-style chart-library preview icons.

The chart library is a type picker, so its previews follow the compact visual
grammar used by OriginPro 2024's graph gallery instead of embedding a reduced
production render.  Every icon is a deterministic, code-native SVG replica
linked to an explicit Origin gallery name and template family.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
OUTPUT = REPOSITORY / "src" / "renderer" / "src" / "assets" / "chart-previews"
EXPECTED_SIZE = (1024, 768)
VIEW_SIZE = (120, 90)
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NAMESPACE)

INK = "#15191f"
BLUE = "#1676d2"
BLUE_DARK = "#0f55a8"
BLUE_LIGHT = "#62a6e3"
BLUE_PALE = "#b8d7f2"
RED = "#ef4b4b"
RED_PALE = "#f6aaaa"
GREEN = "#42ad6d"
GRAY = "#77818f"
GRAY_PALE = "#e8edf3"
WHITE = "#ffffff"


@dataclass(frozen=True, slots=True)
class OriginPreviewSpec:
    profile_id: str
    origin_preview_name: str
    origin_template: str
    gallery_group: str
    draw: Callable[[ET.Element], None]


def _tag(name: str) -> str:
    return f"{{{SVG_NAMESPACE}}}{name}"


def _attrs(values: dict[str, object]) -> dict[str, str]:
    return {
        key.rstrip("_").replace("_", "-"): str(value)
        for key, value in values.items()
        if value is not None
    }


def _add(parent: ET.Element, name: str, **attributes: object) -> ET.Element:
    return ET.SubElement(parent, _tag(name), _attrs(attributes))


def _root() -> ET.Element:
    root = ET.Element(
        _tag("svg"),
        {
            "width": str(EXPECTED_SIZE[0]),
            "height": str(EXPECTED_SIZE[1]),
            "viewBox": f"0 0 {VIEW_SIZE[0]} {VIEW_SIZE[1]}",
            "preserveAspectRatio": "xMidYMid meet",
        },
    )
    _add(root, "rect", x=0, y=0, width=120, height=90, fill=WHITE)
    return root


def _frame(
    parent: ET.Element,
    *,
    x: float = 7,
    y: float = 7,
    width: float = 106,
    height: float = 70,
    fill: str = WHITE,
) -> None:
    _add(
        parent,
        "rect",
        x=x,
        y=y,
        width=width,
        height=height,
        fill=fill,
        stroke=INK,
        stroke_width=1.35,
    )


def _points(values: Iterable[tuple[float, float]]) -> str:
    return " ".join(f"{x:g},{y:g}" for x, y in values)


def _polyline(
    parent: ET.Element,
    values: Iterable[tuple[float, float]],
    *,
    color: str = BLUE,
    width: float = 2.3,
    fill: str = "none",
    dash: str | None = None,
) -> None:
    _add(
        parent,
        "polyline",
        points=_points(values),
        fill=fill,
        stroke=color,
        stroke_width=width,
        stroke_linecap="round",
        stroke_linejoin="round",
        stroke_dasharray=dash,
    )


def _line(
    parent: ET.Element,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    color: str = BLUE,
    width: float = 2,
    dash: str | None = None,
) -> None:
    _add(
        parent,
        "line",
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        stroke=color,
        stroke_width=width,
        stroke_linecap="round",
        stroke_dasharray=dash,
    )


def _dot(
    parent: ET.Element,
    x: float,
    y: float,
    *,
    radius: float = 2.8,
    fill: str = BLUE,
    stroke: str | None = None,
    stroke_width: float = 1.2,
) -> None:
    _add(
        parent,
        "circle",
        cx=x,
        cy=y,
        r=radius,
        fill=fill,
        stroke=stroke,
        stroke_width=stroke_width if stroke else None,
    )


def _dots(
    parent: ET.Element,
    values: Iterable[tuple[float, float]],
    *,
    radius: float = 2.8,
    fill: str = BLUE,
) -> None:
    for x, y in values:
        _dot(parent, x, y, radius=radius, fill=fill)


def _bar(
    parent: ET.Element,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fill: str = BLUE,
    stroke: str = BLUE_DARK,
) -> None:
    _add(
        parent,
        "rect",
        x=x,
        y=y,
        width=width,
        height=height,
        fill=fill,
        stroke=stroke,
        stroke_width=1.05,
    )


def _path(
    parent: ET.Element,
    data: str,
    *,
    fill: str = "none",
    stroke: str = BLUE,
    width: float = 2,
    opacity: float | None = None,
) -> None:
    _add(
        parent,
        "path",
        d=data,
        fill=fill,
        stroke=stroke,
        stroke_width=width,
        stroke_linecap="round",
        stroke_linejoin="round",
        opacity=opacity,
    )


def _error_bar(
    parent: ET.Element,
    x: float,
    y: float,
    *,
    horizontal: float = 0,
    vertical: float = 10,
    color: str = BLUE,
) -> None:
    if vertical:
        _line(parent, x, y - vertical, x, y + vertical, color=color, width=1.8)
        _line(parent, x - 4, y - vertical, x + 4, y - vertical, color=color, width=1.8)
        _line(parent, x - 4, y + vertical, x + 4, y + vertical, color=color, width=1.8)
    if horizontal:
        _line(parent, x - horizontal, y, x + horizontal, y, color=color, width=1.8)
        _line(parent, x - horizontal, y - 4, x - horizontal, y + 4, color=color, width=1.8)
        _line(parent, x + horizontal, y - 4, x + horizontal, y + 4, color=color, width=1.8)
    _dot(parent, x, y, radius=3, fill=color)


def _draw_line(parent: ET.Element) -> None:
    _frame(parent)
    _path(parent, "M 13 58 C 28 31, 37 24, 48 50 S 72 20, 82 39 S 100 32, 108 17")


def _draw_line_symbol(parent: ET.Element) -> None:
    _frame(parent)
    values = ((15, 62), (35, 39), (55, 49), (77, 28), (104, 42))
    _polyline(parent, values)
    _dots(parent, values, radius=3.1)


def _draw_scatter(parent: ET.Element) -> None:
    _frame(parent)
    _dots(
        parent,
        ((18, 59), (28, 31), (39, 52), (50, 24), (61, 42), (73, 17), (89, 35), (103, 20)),
        radius=3,
    )


def _draw_bubble(parent: ET.Element) -> None:
    _frame(parent)
    bubbles = (
        (18, 59, 2.7, RED),
        (34, 49, 4, "#ffb000"),
        (51, 43, 5.8, GREEN),
        (72, 35, 7.5, "#18a0ae"),
        (98, 24, 10, WHITE),
    )
    for x, y, radius, fill in bubbles:
        _dot(
            parent,
            x,
            y,
            radius=radius,
            fill=fill,
            stroke=BLUE if fill == WHITE else fill,
            stroke_width=1.8,
        )


def _draw_error(parent: ET.Element) -> None:
    _frame(parent)
    for x, y, horizontal, vertical, color in (
        (22, 56, 8, 9, BLUE),
        (48, 37, 7, 12, RED),
        (76, 48, 10, 8, BLUE),
        (100, 26, 7, 10, RED),
    ):
        _error_bar(parent, x, y, horizontal=horizontal, vertical=vertical, color=color)


def _draw_error_band(parent: ET.Element) -> None:
    _frame(parent)
    _path(
        parent,
        (
            "M 12 62 C 28 53, 38 30, 53 39 S 75 18, 88 25 "
            "S 100 19, 108 13 L 108 38 C 96 43, 88 46, 77 49 "
            "S 55 56, 43 58 S 24 69, 12 71 Z"
        ),
        fill=BLUE_LIGHT,
        stroke="none",
        width=0,
        opacity=0.75,
    )
    values = ((13, 64), (32, 47), (50, 43), (69, 32), (87, 35), (107, 22))
    _polyline(parent, values, width=2.2)
    _dots(parent, values, radius=2.2)


def _draw_column(parent: ET.Element) -> None:
    _frame(parent)
    for x, y, height in ((20, 43, 29), (48, 22, 50), (78, 35, 37)):
        _bar(parent, x, y, 18, height)


def _draw_grouped_column(parent: ET.Element) -> None:
    _frame(parent)
    for index, (left, first, second) in enumerate(((16, 28, 44), (51, 46, 32), (86, 38, 54))):
        _bar(parent, left, 72 - first, 12, first, fill=BLUE)
        _bar(parent, left + 13, 72 - second, 12, second, fill=BLUE_LIGHT, stroke=BLUE)
        if index == 2:
            _line(parent, left + 26, 72, left + 26, 72, color=BLUE)


def _draw_stacked(parent: ET.Element, *, percent: bool = False) -> None:
    _frame(parent)
    totals = (58, 65, 50) if not percent else (62, 62, 62)
    for index, (x, total) in enumerate(zip((17, 51, 85), totals, strict=True)):
        parts = (
            (0.34, 0.31, 0.35)
            if percent
            else ((0.38, 0.27, 0.35), (0.48, 0.25, 0.27), (0.3, 0.4, 0.3))[index]
        )
        bottom = 72.0
        for fraction, color in zip(parts, (BLUE, BLUE_LIGHT, BLUE_PALE), strict=True):
            height = total * fraction
            bottom -= height
            _bar(parent, x, bottom, 20, height, fill=color, stroke=BLUE_DARK)


def _draw_strip(parent: ET.Element) -> None:
    _frame(parent)
    for index, x in enumerate((31, 61, 91)):
        ys = (61, 53, 48, 41, 34, 27) if index != 1 else (63, 57, 49, 40, 35, 23, 18)
        for offset, y in zip((-3, 2, -1, 3, 0, -2, 2), ys, strict=False):
            _dot(parent, x + offset, y, radius=2.3)


def _draw_box(parent: ET.Element) -> None:
    _frame(parent)
    for x, top, bottom, median in ((34, 24, 61, 43), (78, 18, 57, 34)):
        _line(parent, x, top - 8, x, bottom + 8, width=1.5)
        _line(parent, x - 8, top - 8, x + 8, top - 8, width=1.5)
        _line(parent, x - 8, bottom + 8, x + 8, bottom + 8, width=1.5)
        _add(
            parent,
            "rect",
            x=x - 12,
            y=top,
            width=24,
            height=bottom - top,
            fill=BLUE_PALE,
            stroke=BLUE,
            stroke_width=1.5,
        )
        _line(parent, x - 12, median, x + 12, median, color=RED, width=1.8)


def _draw_violin(parent: ET.Element) -> None:
    _frame(parent)
    for x, scale in ((30, 0.8), (60, 1.15), (90, 0.92)):
        half = 11 * scale
        data = (
            f"M {x:g} 16 C {x - 2:g} 25, {x - half:g} 31, {x - half:g} 42 "
            f"C {x - half:g} 54, {x - 3:g} 60, {x:g} 69 "
            f"C {x + 3:g} 60, {x + half:g} 54, {x + half:g} 42 "
            f"C {x + half:g} 31, {x + 2:g} 25, {x:g} 16 Z"
        )
        _path(parent, data, fill=BLUE_PALE, stroke=BLUE, width=1.5)
        _line(parent, x - 4, 42, x + 4, 42, color=RED, width=1.4)


def _draw_histogram(parent: ET.Element) -> None:
    _frame(parent)
    heights = (14, 27, 48, 61, 50, 31, 17)
    for index, height in enumerate(heights):
        _bar(
            parent,
            15 + index * 13,
            72 - height,
            13,
            height,
            fill=BLUE_LIGHT if index in {1, 5} else BLUE,
        )


def _draw_area(parent: ET.Element) -> None:
    _frame(parent)
    _path(
        parent,
        "M 12 72 L 12 58 L 33 34 L 54 48 L 76 22 L 108 39 L 108 72 Z",
        fill=BLUE_LIGHT,
        stroke=BLUE,
        width=1.8,
        opacity=0.82,
    )


def _draw_time_series(parent: ET.Element) -> None:
    _frame(parent)
    values = ((12, 62), (30, 43), (48, 53), (62, 26), (78, 34), (94, 17), (108, 27))
    _polyline(parent, values)
    _dots(parent, values, radius=2.4)


def _draw_heatmap(
    parent: ET.Element, *, correlation: bool = False, confusion: bool = False
) -> None:
    _frame(parent)
    colors = (
        ("#103f82", "#8bb8e7", "#d8e7f7"),
        ("#a7c9ed", "#165fae", "#9ec3ea"),
        ("#e1edf9", "#83b2e4", "#0f4f9a"),
    )
    if correlation:
        colors = (
            ("#c44255", "#f2b7ae", "#dceafb"),
            ("#f3c2b9", "#b92845", "#f0a79d"),
            ("#deebf8", "#f1b8ad", "#c12543"),
        )
    if confusion:
        colors = (
            ("#0f4a91", "#e1ecf8", "#f3f7fb"),
            ("#deebf7", "#145da8", "#e5eff8"),
            ("#f4f7fb", "#dbe9f6", "#1c6ab5"),
        )
    cell = 20
    for row in range(3):
        for column in range(3):
            _add(
                parent,
                "rect",
                x=30 + column * cell,
                y=12 + row * cell,
                width=cell,
                height=cell,
                fill=colors[row][column],
                stroke=WHITE,
                stroke_width=1.1,
            )


def _draw_contour(parent: ET.Element) -> None:
    _frame(parent)
    bands = (
        ("M 8 72 C 32 63, 36 37, 60 35 S 88 18, 113 11 L 113 77 L 8 77 Z", "#155aa8"),
        (
            "M 8 61 C 29 53, 40 31, 62 28 S 88 14, 113 9 "
            "L 113 22 C 87 28, 78 43, 57 45 S 30 67, 8 71 Z",
            "#3f8ad0",
        ),
        (
            "M 8 45 C 28 41, 40 21, 62 19 S 90 9, 113 7 "
            "L 113 15 C 91 19, 83 32, 60 34 S 30 54, 8 60 Z",
            "#78b4e8",
        ),
        (
            "M 8 29 C 28 26, 43 11, 66 10 S 94 7, 113 7 "
            "L 113 11 C 92 12, 84 20, 61 23 S 29 41, 8 44 Z",
            "#c9e0f5",
        ),
    )
    for data, color in bands:
        _path(parent, data, fill=color, stroke=color, width=0.8)


def _draw_trellis(parent: ET.Element) -> None:
    for row in range(2):
        for column in range(2):
            x = 8 + column * 55
            y = 8 + row * 36
            _frame(parent, x=x, y=y, width=49, height=30)
            values = (
                (x + 5, y + 23),
                (x + 15, y + 13 + row * 2),
                (x + 27, y + 19 - column * 3),
                (x + 42, y + 7 + row * 3),
            )
            _polyline(parent, values, width=1.7)
            _dots(parent, values, radius=1.8)


def _draw_nyquist(parent: ET.Element) -> None:
    _frame(parent)
    values = ((17, 64), (25, 48), (37, 32), (53, 21), (70, 18), (87, 27), (102, 45))
    _path(parent, "M 17 64 C 28 32, 44 17, 67 18 C 84 18, 96 32, 102 45")
    _dots(parent, values, radius=2.5)


def _draw_dropline(parent: ET.Element) -> None:
    _frame(parent)
    for x, y in ((22, 55), (46, 25), (72, 42), (99, 18)):
        _line(parent, x, y, x, 70, color=BLUE, width=1.8)
        _dot(parent, x, y, radius=3)


def _draw_lollipop(parent: ET.Element) -> None:
    _frame(parent)
    for y, left, right in ((18, 63, 102), (34, 43, 91), (50, 29, 79), (66, 17, 61)):
        _line(parent, left, y, right, y, color=GRAY, width=1.7)
        _dot(parent, left, y, radius=2.8, fill=BLUE)
        _dot(parent, right, y, radius=2.8, fill=RED)


def _draw_beeswarm(parent: ET.Element) -> None:
    _frame(parent)
    for group, x in enumerate((29, 60, 91)):
        for index, y in enumerate((62, 56, 49, 43, 36, 30, 24, 18)):
            offset = ((index * 5 + group * 2) % 11) - 5
            _dot(parent, x + offset, y, radius=2.1, fill=BLUE if group != 1 else RED)


def _draw_floating(parent: ET.Element) -> None:
    _frame(parent)
    for x, top, split, bottom in ((19, 19, 42, 65), (51, 12, 34, 57), (83, 29, 47, 70)):
        _bar(parent, x, top, 20, split - top, fill=BLUE_LIGHT, stroke=BLUE_DARK)
        _bar(parent, x, split, 20, bottom - split, fill=BLUE, stroke=BLUE_DARK)


def _draw_pyramid(parent: ET.Element) -> None:
    _frame(parent)
    _line(parent, 60, 10, 60, 73, color=INK, width=1.25)
    widths = (20, 30, 40, 48)
    for index, width in enumerate(widths):
        y = 14 + index * 14
        _bar(parent, 60 - width, y, width, 11, fill=BLUE, stroke=BLUE_DARK)
        _bar(parent, 60, y, width * 0.88, 11, fill=BLUE_LIGHT, stroke=BLUE_DARK)


def _draw_dual_y(parent: ET.Element) -> None:
    _frame(parent)
    blue_values = ((13, 60), (34, 43), (56, 50), (78, 25), (106, 35))
    red_values = ((13, 30), (34, 38), (56, 22), (78, 43), (106, 16))
    _polyline(parent, blue_values, color=BLUE)
    _polyline(parent, red_values, color=RED)
    _dots(parent, blue_values, radius=2.4, fill=BLUE)
    _dots(parent, red_values, radius=2.4, fill=RED)


def _draw_pareto(parent: ET.Element) -> None:
    _frame(parent)
    heights = (55, 43, 31, 22, 14)
    cumulative = ((18, 61), (38, 43), (58, 30), (78, 20), (98, 14))
    for index, height in enumerate(heights):
        _bar(parent, 12 + index * 19, 72 - height, 15, height, fill=BLUE)
    _polyline(parent, cumulative, color=RED, width=2)
    _dots(parent, cumulative, radius=2.5, fill=RED)


def _draw_dual_column(parent: ET.Element) -> None:
    _frame(parent)
    for index, x in enumerate((17, 47, 77)):
        _bar(parent, x, 72 - (31 + index * 10), 13, 31 + index * 10, fill=BLUE)
        _bar(parent, x + 14, 72 - (50 - index * 7), 13, 50 - index * 7, fill=RED, stroke="#bd3030")


def _draw_column_line(parent: ET.Element) -> None:
    _frame(parent)
    values = ((23, 49), (49, 27), (75, 40), (101, 18))
    for index, (x, _y) in enumerate(values):
        height = (27, 42, 31, 49)[index]
        _bar(parent, x - 7, 72 - height, 14, height, fill=BLUE)
    _polyline(parent, values, color=RED, width=2.2)
    _dots(parent, values, radius=2.7, fill=RED)


def _draw_offset(parent: ET.Element) -> None:
    _frame(parent)
    colors = (BLUE, GREEN, RED)
    for index, color in enumerate(colors):
        y = 20 + index * 20
        _path(
            parent,
            f"M 12 {y + 8} C 30 {y - 6}, 48 {y + 10}, 66 {y - 2} S 94 {y - 8}, 108 {y + 2}",
            stroke=color,
            width=2,
        )


def _draw_line_series(parent: ET.Element) -> None:
    _frame(parent)
    for ys in ((17, 30, 24), (30, 42, 35), (44, 55, 48), (58, 66, 61)):
        values = ((18, ys[0]), (60, ys[1]), (102, ys[2]))
        _polyline(parent, values, color=INK, width=1.5)
        for column, (x, y) in enumerate(values):
            _dot(parent, x, y, radius=2.4, fill=(BLUE, GREEN, RED)[column])


def _draw_before_after(parent: ET.Element) -> None:
    _frame(parent)
    pairs = ((18, 28), (31, 52), (45, 34), (59, 66))
    for start, end in pairs:
        _line(parent, 23, start, 97, end, color=INK, width=1.5)
        _dot(parent, 23, start, radius=2.7, fill=BLUE)
        _dot(parent, 97, end, radius=2.7, fill=RED)


PREVIEW_SPECS = (
    OriginPreviewSpec("K01", "折线图", "LINE.OTP", "基础 2D 图", _draw_line),
    OriginPreviewSpec("K02", "点线图", "LINESYMB.OTP", "基础 2D 图", _draw_line_symbol),
    OriginPreviewSpec("K03", "散点图", "SCATTER.OTP", "基础 2D 图", _draw_scatter),
    OriginPreviewSpec("K04", "气泡+颜色映射图", "Bubble.OTP", "基础 2D 图", _draw_bubble),
    OriginPreviewSpec("K06", "XY 误差图", "ERRBAR.OTP", "基础 2D 图", _draw_error),
    OriginPreviewSpec("K07", "误差带图", "ERRORBAND.OTP", "基础 2D 图", _draw_error_band),
    OriginPreviewSpec("K08", "柱状图", "COLUMN.OTP", "条形图、饼图、面积图", _draw_column),
    OriginPreviewSpec(
        "K09", "分组柱状图", "gColumn.otpu", "条形图、饼图、面积图", _draw_grouped_column
    ),
    OriginPreviewSpec(
        "K10",
        "堆积柱状图",
        "STACKCOLUMN.otp",
        "条形图、饼图、面积图",
        lambda root: _draw_stacked(root),
    ),
    OriginPreviewSpec(
        "K11",
        "百分比堆积柱状图",
        "StackColP.otp",
        "条形图、饼图、面积图",
        lambda root: _draw_stacked(root, percent=True),
    ),
    OriginPreviewSpec("K12", "列散点图", "ColumnScatter.otp", "统计图", _draw_strip),
    OriginPreviewSpec("K13", "箱线图", "BOX.OTP", "统计图", _draw_box),
    OriginPreviewSpec("K14", "小提琴图", "Violin.otpu", "统计图", _draw_violin),
    OriginPreviewSpec("K15", "直方图", "Hist.otpu", "统计图", _draw_histogram),
    OriginPreviewSpec("K18", "面积图", "AREA.OTP", "条形图、饼图、面积图", _draw_area),
    OriginPreviewSpec("K19", "折线图（日期时间 X）", "LINE.OTP", "基础 2D 图", _draw_time_series),
    OriginPreviewSpec("K20", "热图", "Heat_Map.otpu", "等高线图", _draw_heatmap),
    OriginPreviewSpec(
        "K21",
        "带标签热图",
        "Heat_Map_With_Labels.otpu",
        "等高线图",
        lambda root: _draw_heatmap(root, correlation=True),
    ),
    OriginPreviewSpec("K22", "填色等高线图", "CONTOUR.OTP", "等高线图", _draw_contour),
    OriginPreviewSpec("K24", "Trellis 图", "Grouped.otp", "多面板、多轴", _draw_trellis),
    OriginPreviewSpec("S34", "点线图（Nyquist 语义）", "LINESYMB.OTP", "基础 2D 图", _draw_nyquist),
    OriginPreviewSpec(
        "S61",
        "带标签热图（混淆矩阵语义）",
        "Heat_Map_With_Labels.otpu",
        "等高线图",
        lambda root: _draw_heatmap(root, confusion=True),
    ),
    OriginPreviewSpec("X02", "垂线图", "DROPLINE.OTP", "基础 2D 图", _draw_dropline),
    OriginPreviewSpec("X03", "棒棒糖图", "Lollipop.otpu", "基础 2D 图", _draw_lollipop),
    OriginPreviewSpec("X05", "蜂群图", "Beeswarm.otpu", "统计图", _draw_beeswarm),
    OriginPreviewSpec("X09", "浮动柱状图", "FloatCol.otp", "条形图、饼图、面积图", _draw_floating),
    OriginPreviewSpec("X13", "人口金字塔", "PopulationPyramid.otpu", "统计图", _draw_pyramid),
    OriginPreviewSpec("X23", "2Ys Y-Y 图", "DOUBLEY.OTP", "多面板、多轴", _draw_dual_y),
    OriginPreviewSpec("X24", "帕累托图", "ParetoBin.otpu", "统计图", _draw_pareto),
    OriginPreviewSpec("X35", "2Ys 柱状图", "2Ys_Col.otpu", "多面板、多轴", _draw_dual_column),
    OriginPreviewSpec("X36", "2Ys 柱线图", "2Ys_ColSymb.otpu", "多面板、多轴", _draw_column_line),
    OriginPreviewSpec("X38", "Y 偏移堆积线图", "OffsetStackY.otp", "基础 2D 图", _draw_offset),
    OriginPreviewSpec("X39", "线条序列", "BoxLser.otpu", "基础 2D 图", _draw_line_series),
    OriginPreviewSpec("X40", "前后对比图", "BeforeAfter.otpu", "基础 2D 图", _draw_before_after),
)


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_audit_page(entries: list[dict[str, object]]) -> Path:
    catalog_source = (
        REPOSITORY / "src" / "renderer" / "src" / "data" / "chartCatalog.ts"
    ).read_text(encoding="utf-8")
    chinese_names = dict(re.findall(r"^\s*(\w+): \{ name: '([^']+)'", catalog_source, re.MULTILINE))
    audit_directory = REPOSITORY / "build" / "visual-audit" / "chart-library-previews"
    audit_directory.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(
        (
            '<article><img src="../../../src/renderer/src/assets/chart-previews/'
            f'{entry["profile_id"]}.svg" alt=""><footer><strong>{entry["profile_id"]}</strong>'
            f"<span>{html.escape(chinese_names.get(str(entry['profile_id']), ''))}</span>"
            f"<small>{html.escape(str(entry['origin_preview_name']))}</small></footer></article>"
        )
        for entry in entries
    )
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>图形库 Origin 预览复刻审计</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 32px; background: #f4f6f8; color: #172033;
      font: 14px/1.45 system-ui, sans-serif;
    }}
    header {{
      display: flex; align-items: end; justify-content: space-between;
      margin-bottom: 22px;
    }}
    h1 {{ margin: 0; font-size: 24px; }}
    p {{ margin: 2px 0 0; color: #607086; }}
    main {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 14px;
    }}
    article {{
      overflow: hidden; border: 1px solid #d9e0e8; border-radius: 10px;
      background: #fff;
    }}
    img {{
      display: block; width: 100%; aspect-ratio: 4 / 3;
      object-fit: contain; background: #fff;
    }}
    footer {{
      display: grid; grid-template-columns: auto 1fr; column-gap: 8px;
      padding: 9px 11px 10px; border-top: 1px solid #e6ebf0;
    }}
    footer strong {{ color: #0968e5; }}
    footer span {{ font-weight: 650; }}
    footer small {{ grid-column: 2; color: #68778c; font-size: 11px; }}
  </style>
</head>
<body>
  <header>
    <div><h1>图形库 Origin 预览复刻</h1>
      <p>依据 OriginPro 2024 图形库预览、本机模板名称和官方菜单语义重绘</p>
    </div>
    <strong>{len(entries)} 张</strong>
  </header>
  <main>{cards}</main>
</body>
</html>
"""
    target = audit_directory / "index.html"
    target.write_text(page, encoding="utf-8")
    return target


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    source_commit = _source_commit()
    expected_names = {f"{spec.profile_id}.svg" for spec in PREVIEW_SPECS}
    for index, spec in enumerate(PREVIEW_SPECS, start=1):
        root = _root()
        spec.draw(root)
        ET.indent(root, space=" ")
        destination = OUTPUT / f"{spec.profile_id}.svg"
        ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
        entries.append(
            {
                "profile_id": spec.profile_id,
                "backend": "origin-gallery-replica",
                "state": "type-preview",
                "origin_preview_name": spec.origin_preview_name,
                "origin_template": spec.origin_template,
                "origin_gallery_group": spec.gallery_group,
                "asset_format": "svg",
                "asset_sha256": sha256(destination.read_bytes()).hexdigest(),
                "width": EXPECTED_SIZE[0],
                "height": EXPECTED_SIZE[1],
            }
        )
        print(f"[{index:02d}/{len(PREVIEW_SPECS)}] {spec.profile_id} -> {destination.name}")
    for old in OUTPUT.glob("*.svg"):
        if old.name not in expected_names:
            old.unlink()
    manifest = {
        "schema_version": "plotagent.chart-library-previews.v5",
        "source_commit": source_commit,
        "source_policy": (
            "code-native SVG replicas of OriginPro 2024 graph-gallery previews, "
            "mapped to verified local template names"
        ),
        "reference_policy": (
            "visual grammar follows the five user-provided OriginPro gallery screenshots; "
            "chart identity follows docs/ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md"
        ),
        "preview_policy": (
            "show the canonical graph-type symbol inside an Origin-style plot frame; "
            "omit axes labels, legends, and data-specific decoration"
        ),
        "count": len(entries),
        "entries": entries,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    audit_page = _write_audit_page(entries)
    print(f"audit -> {audit_page}")


if __name__ == "__main__":
    main()

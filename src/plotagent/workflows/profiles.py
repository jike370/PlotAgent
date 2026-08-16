"""Stable user-facing chart names used by deterministic workflow routing."""

from __future__ import annotations

import re
from collections.abc import Iterable

PROFILE_ALIASES: dict[str, tuple[str, ...]] = {
    "K01": ("折线图", "line graph", "line chart"),
    "K02": ("线点图", "线符号图", "line and symbol", "line+symbol"),
    "K03": ("散点图", "scatter plot"),
    "K04": ("气泡图", "bubble plot", "bubble chart"),
    "K06": ("点估计与误差棒", "xy误差棒", "point estimate and error bar"),
    "K07": ("误差带", "误差带图", "error ribbon", "error band"),
    "K08": ("柱状图", "column chart", "column plot"),
    "K09": ("分组柱状图", "grouped column"),
    "K10": ("堆积柱状图", "stacked column"),
    "K11": ("百分比堆积柱状图", "100% stacked column"),
    "K12": ("条带图", "列散点图", "strip plot", "column scatter"),
    "K13": ("箱线图", "box plot", "box chart"),
    "K14": ("小提琴图", "violin plot"),
    "K15": ("直方图", "histogram"),
    "K18": ("面积图", "area plot", "area chart"),
    "K19": (
        "日期时间折线图",
        "日期时间图",
        "时间序列图",
        "datetime line chart",
        "date time line chart",
        "time series",
    ),
    "K20": ("热图", "heatmap", "heat map"),
    "K21": ("相关矩阵图", "correlation matrix"),
    "K22": ("填色等高线图", "filled contour"),
    "K24": ("分面图", "faceted plot", "facet plot"),
    "S34": ("nyquist图", "nyquist plot", "nyquist"),
    "S61": ("混淆矩阵", "confusion matrix"),
    "X02": ("垂线图", "drop line"),
    "X03": ("棒棒糖图", "lollipop"),
    "X05": ("蜂群图", "beeswarm"),
    "X09": ("浮动柱状图", "floating column"),
    "X13": ("人口金字塔", "population pyramid"),
    "X23": ("双y轴折线图", "dual-y line", "dual y line"),
    "X24": ("帕累托图", "pareto"),
    "X35": ("双y轴柱状图", "dual-y column", "dual y column"),
    "X36": ("双y轴柱线图", "dual-y column and line", "dual y column and line"),
    "X38": ("y偏移堆叠线图", "y-offset stacked line", "y offset stacked line"),
    "X39": ("线条序列图", "line series"),
    "X40": ("前后对比图", "before and after"),
}


def _fold(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value.casefold())


def explicit_profile_ids(instruction: str, allowed: Iterable[str]) -> tuple[str, ...]:
    """Return chart types explicitly named by the user, longest aliases first."""

    allowed_ids = tuple(allowed)
    folded = _fold(instruction)
    direct = tuple(profile_id for profile_id in allowed_ids if _fold(profile_id) in folded)
    if direct:
        return direct
    candidates = sorted(
        (
            (_fold(alias), profile_id)
            for profile_id in allowed_ids
            for alias in PROFILE_ALIASES.get(profile_id, ())
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    remaining = folded
    found: list[str] = []
    for alias, profile_id in candidates:
        if alias and alias in remaining:
            if profile_id not in found:
                found.append(profile_id)
            remaining = remaining.replace(alias, "", 1)
    return tuple(profile_id for profile_id in allowed_ids if profile_id in found)


def profile_mentions(instruction: str, allowed: Iterable[str]) -> tuple[tuple[str, int, int], ...]:
    """Return non-overlapping explicit chart mentions in textual order.

    Unlike :func:`explicit_profile_ids`, this preserves where each chart was
    named.  The workflow resolver uses the positions to pair heterogeneous
    batch clauses with their data sources instead of flattening all roles into
    one task.
    """

    candidates: list[tuple[int, int, str]] = []
    for profile_id in allowed:
        labels = (profile_id, *PROFILE_ALIASES.get(profile_id, ()))
        for label in labels:
            for matched in re.finditer(re.escape(label), instruction, flags=re.IGNORECASE):
                candidates.append((matched.start(), matched.end(), profile_id))
    selected: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, profile_id in sorted(
        candidates,
        key=lambda item: (item[0], -(item[1] - item[0]), item[2]),
    ):
        if any(start < used_end and end > used_start for used_start, used_end in occupied):
            continue
        selected.append((start, end, profile_id))
        occupied.append((start, end))
    return tuple((profile_id, start, end) for start, end, profile_id in selected)


def unspecified_chart_request(instruction: str) -> bool:
    normalized = re.sub(r"[^\w]+", "", instruction.casefold()).replace("_", "")
    return normalized in {
        "画图",
        "画一个图",
        "画一张图",
        "请画图",
        "请画一个图",
        "请画一张图",
        "帮我画图",
        "绘图",
        "绘制一个图",
        "绘制一张图",
        "用这些数据画图",
        "用这个数据画图",
        "drawchart",
        "drawachart",
        "drawit",
        "makeaplot",
        "makeachart",
        "plot",
        "plotachart",
        "plotit",
    }

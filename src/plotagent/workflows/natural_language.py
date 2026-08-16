"""High-confidence local translation of explicit workflow parameters.

This module intentionally implements only the closed, unambiguous vocabulary
published by the workflow contract.  Returning ``None`` means "escalate to the
Agent"; it must never silently drop a requested parameter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from plotagent.contracts.workflows import (
    DataOperation,
    DraftSetAxis,
    DraftSetColorMap,
    DraftSetDataLabels,
    DraftSetErrorStyle,
    DraftSetLegend,
    DraftSetSeriesStyle,
    DraftSetTitle,
    DraftVisualAction,
    FilterPredicate,
    FilterRows,
    SortKey,
    SortRows,
    WorkflowContext,
)


@dataclass(frozen=True, slots=True)
class ExplicitGoal:
    visual_actions: tuple[DraftVisualAction, ...] = ()
    data_operations: tuple[DataOperation, ...] = ()
    hard_constraints: tuple[str, ...] = ()


_NUMBER = r"[-+]?\d+(?:\.\d+)?"
_COLOR = {
    "红色": "#D62728",
    "蓝色": "#1F77B4",
    "绿色": "#2CA02C",
    "橙色": "#FF7F0E",
    "紫色": "#9467BD",
    "灰色": "#7A7A7A",
    "黑色": "#000000",
    "黄色": "#F2C94C",
}
_LINE_STYLE = {
    "点划线": "dash_dot",
    "虚线": "dash",
    "点线": "dot",
    "实线": "solid",
}
_MARKER_SHAPE = {
    "圆": "circle",
    "圆点": "circle",
    "菱形": "diamond",
    "方形": "square",
    "三角形": "triangle_up",
    "星形": "star",
}
_PALETTE = {
    "rdbu": "red_white_blue",
    "red-white-blue": "red_white_blue",
    "red white blue": "red_white_blue",
    "红白蓝": "red_white_blue",
    "蓝白红": "blue_white_red",
    "viridis": "viridis",
    "plasma": "plasma",
    "inferno": "inferno",
    "magma": "magma",
    "cividis": "cividis",
    "turbo": "turbo",
    "灰度": "gray_scale",
    "火焰": "fire",
    "彩虹": "rainbow_modified",
    "冷暖": "cool_warm",
    "spectral": "spectral",
    "terrain": "terrain",
    "ocean": "ocean",
}


def _number(pattern: str, text: str) -> float | None:
    matched = re.search(pattern, text, flags=re.IGNORECASE)
    return None if matched is None else float(matched.group(1))


def _color_after(text: str, keyword: str) -> str | None:
    matched = re.search(
        rf"{keyword}[^#，,；;。]*?(#[0-9a-fA-F]{{6}}|{'|'.join(_COLOR)})",
        text,
        flags=re.IGNORECASE,
    )
    if matched is None:
        return None
    value = matched.group(1)
    return value.upper() if value.startswith("#") else _COLOR[value]


def _first_color(text: str) -> str | None:
    matched = re.search(r"#[0-9a-fA-F]{6}", text)
    if matched is not None:
        return matched.group(0).upper()
    for name, value in _COLOR.items():
        if name in text:
            return value
    return None


def _field_alias(context: WorkflowContext, source_alias: str, name: str) -> str | None:
    folded = re.sub(r"[^\w\u4e00-\u9fff]+", "", name.casefold())
    matches = tuple(
        field.field_alias
        for field in context.fields
        if field.source_alias == source_alias
        and re.sub(r"[^\w\u4e00-\u9fff]+", "", field.name.casefold()) == folded
    )
    return matches[0] if len(matches) == 1 else None


def _parse_title(text: str) -> DraftSetTitle | None:
    matched = re.search(
        r"(?:^|[，,；;。]|当前图|并把|把)\s*(?:图)?标题\s*(?:设为|改为|为)\s*([^，,；;。]+)",
        text,
        flags=re.IGNORECASE,
    )
    return None if matched is None else DraftSetTitle(text=matched.group(1).strip())


def _parse_axis(text: str) -> tuple[DraftSetAxis, ...] | None:
    requested = re.search(r"(?:[xXyY横纵]\s*轴标题|横轴标题|纵轴标题)", text)
    if requested is None:
        return ()
    actions: list[DraftSetAxis] = []
    pattern = re.compile(
        r"([xXyY横纵])\s*轴标题\s*(?:设为|改为|为)\s*([^，,；;。]+)",
        flags=re.IGNORECASE,
    )
    for axis, label in pattern.findall(text):
        target = "x_axis" if axis.casefold() in {"x", "横"} else "y_axis"
        actions.append(DraftSetAxis(target_alias=target, label=label.strip()))
    return tuple(actions) if actions else None


def _parse_series_style(text: str) -> DraftSetSeriesStyle | None:
    requested = re.search(
        r"线条|连接线|线宽|虚线|点划线|点线|实线|实心|空心|菱形|圆点|点使用|"
        r"符号|填充|边框|边缘宽度",
        text,
    )
    if requested is None:
        return None
    target = "connector" if "连接线" in text else "series_1"
    values: dict[str, object] = {"target_alias": target}

    for label, style in _LINE_STYLE.items():
        if label in text:
            values["line_style"] = style
            break
    line_context = re.search(r"(?:线条|连接线)[^，,；;。]*", text)
    if line_context is not None:
        color = _first_color(line_context.group(0))
        if color is not None:
            values["line_stroke_color"] = color
        width = _number(rf"(?:线宽|宽度|宽)\s*({_NUMBER})\s*(?:pt|磅)?", line_context.group(0))
        if width is not None:
            values["line_width_pt"] = width
    elif any(label in text for label in _LINE_STYLE):
        color = _first_color(text)
        if color is not None:
            values["line_stroke_color"] = color
        width = _number(rf"(?:线宽|宽度)\s*({_NUMBER})\s*(?:pt|磅)?", text)
        if width is not None:
            values["line_width_pt"] = width
    if ("线条" in text or "连接线" in text) and "line_width_pt" not in values:
        width = _number(rf"(?:线宽|宽度)\s*({_NUMBER})\s*(?:pt|磅)?", text)
        if width is not None:
            values["line_width_pt"] = width

    marker_requested = re.search(r"实心|空心|菱形|圆点|点使用|符号", text) is not None
    if marker_requested:
        for label, shape in _MARKER_SHAPE.items():
            if label in text:
                values["marker_shape"] = shape
                break
        if "实心" in text:
            values["marker_interior"] = "solid"
        elif "空心" in text:
            values["marker_interior"] = "hollow"
        size = _number(rf"(?:点大小|符号大小|大小)\s*({_NUMBER})\s*(?:pt|磅)?", text)
        if size is None:
            size = _number(rf"(?:点|符号)\s*({_NUMBER})\s*(?:pt|磅)", text)
        if size is not None:
            values["marker_size_pt"] = size
        edge = _number(rf"(?:边缘宽度|符号边缘宽度)\s*({_NUMBER})\s*(?:pt|磅)?", text)
        if edge is not None:
            values["marker_stroke_width_pt"] = edge
        color = _first_color(text)
        if color is not None:
            values["marker_fill_color"] = color
            values["marker_stroke_color"] = color

    if "填充" in text:
        color = _color_after(text, "填充")
        if color is None:
            return None
        values["fill_color"] = color
    if "边框" in text:
        color = _color_after(text, "边框")
        if color is not None:
            values["fill_stroke_color"] = color
        width = _number(rf"边框宽(?:度)?\s*({_NUMBER})\s*(?:pt|磅)?", text)
        if width is not None:
            values["fill_stroke_width_pt"] = width

    return DraftSetSeriesStyle(**values) if len(values) > 1 else None  # type: ignore[arg-type]


def _parse_colormap(text: str) -> DraftSetColorMap | None:
    if re.search(r"色板|色标|中点", text) is None:
        return None
    palette: str | None = None
    folded = text.casefold()
    for label, canonical in _PALETTE.items():
        if label in folded:
            palette = canonical
            break
    bounds = re.search(rf"范围\s*({_NUMBER})\s*(?:到|至|~|～)\s*({_NUMBER})", text)
    midpoint = _number(rf"中点\s*({_NUMBER})", text)
    title = re.search(r"色标标题\s*(?:设为|改为|为)\s*([^，,；;。]+)", text)
    values: dict[str, object] = {
        "target_alias": "series_1",
        "reverse": "反转" in text,
    }
    if palette is not None:
        values["palette"] = palette
    if bounds is not None:
        values["minimum"] = float(bounds.group(1))
        values["maximum"] = float(bounds.group(2))
    if midpoint is not None:
        values["midpoint"] = midpoint
    if title is not None:
        values["colorbar_title"] = title.group(1).strip()
        values["colorbar_visible"] = True
    return DraftSetColorMap(**values)  # type: ignore[arg-type]


def _parse_error_style(text: str) -> DraftSetErrorStyle | None:
    if re.search(r"误差棒|端帽", text) is None:
        return None
    color = _color_after(text, "误差棒")
    width = _number(rf"误差棒[^，,；;。]*?(?:宽|宽度|线宽)\s*({_NUMBER})", text)
    cap = _number(rf"端帽\s*({_NUMBER})", text)
    values: dict[str, object] = {"target_alias": "series_1"}
    if color is not None:
        values["bar_color"] = color
    if width is not None:
        values["bar_width_pt"] = width
    if cap is not None:
        values["cap_size_pt"] = cap
    return DraftSetErrorStyle(**values) if len(values) > 1 else None  # type: ignore[arg-type]


def _parse_legend(text: str) -> DraftSetLegend | None:
    if "图例" not in text:
        return None
    visible = not any(token in text for token in ("隐藏图例", "不显示图例", "关闭图例"))
    anchor: Literal["inside", "right", "bottom", "none"] | None = None
    if "右侧" in text or "右边" in text:
        anchor = "right"
    elif "底部" in text or "下方" in text:
        anchor = "bottom"
    elif "内部" in text or "图内" in text:
        anchor = "inside"
    return DraftSetLegend(visible=visible, anchor=anchor)


def _parse_data_operations(
    context: WorkflowContext,
    source_alias: str | None,
) -> tuple[DataOperation, ...] | None:
    text = context.instruction
    requested_filter = re.search(r"只保留|筛选|过滤|排除|剔除", text) is not None
    requested_sort = "排序" in text or re.search(r"按\s*[^，,；;。]+\s*(?:升序|降序)", text)
    if not requested_filter and requested_sort is None:
        return ()
    if source_alias is None:
        return None
    result: list[DataOperation] = []
    if requested_filter:
        matched = re.search(
            rf"(?:只保留|筛选|过滤)\s*([\w\u4e00-\u9fff]+)\s*"
            rf"(大于等于|小于等于|不等于|大于|小于|等于)\s*({_NUMBER})",
            text,
        )
        if matched is None:
            return None
        alias = _field_alias(context, source_alias, matched.group(1))
        if alias is None:
            return None
        operator = {
            "大于": "greater_than",
            "大于等于": "greater_or_equal",
            "小于": "less_than",
            "小于等于": "less_or_equal",
            "等于": "equal",
            "不等于": "not_equal",
        }[matched.group(2)]
        result.append(
            FilterRows(
                source_alias=source_alias,
                predicates=(
                    FilterPredicate(
                        field_alias=alias,
                        operator=operator,  # type: ignore[arg-type]
                        value=float(matched.group(3)),
                    ),
                ),
            )
        )
    if requested_sort is not None:
        matched = re.search(r"按\s*([\w\u4e00-\u9fff]+)\s*(升序|降序)(?:排列|排序)?", text)
        if matched is None:
            return None
        alias = _field_alias(context, source_alias, matched.group(1))
        if alias is None:
            return None
        result.append(
            SortRows(
                source_alias=source_alias,
                keys=(
                    SortKey(
                        field_alias=alias,
                        direction="descending" if matched.group(2) == "降序" else "ascending",
                    ),
                ),
            )
        )
    return tuple(result)


def parse_explicit_goal(
    context: WorkflowContext,
    *,
    source_alias: str | None,
) -> ExplicitGoal | None:
    """Translate a complete, explicit T1 goal or request Agent escalation."""

    text = context.instruction
    if re.search(
        r"字体|字号|透明|网格|刻度|坐标范围|轴范围|对数|log10|反向|旋转|加粗|"
        r"注释|参考线|宽转长|长转宽|拼接|合并|排除|剔除",
        text,
        flags=re.IGNORECASE,
    ):
        return None
    requested = {
        "title": re.search(r"(?:^|当前图|图)标题|[，,；;。]\s*标题", text) is not None,
        "axis": re.search(r"[xXyY横纵]\s*轴标题", text) is not None,
        "style": re.search(
            r"线条|连接线|线宽|虚线|点划线|点线|实线|实心|空心|菱形|圆点|点使用|"
            r"符号|填充|边框|边缘宽度",
            text,
        )
        is not None,
        "colormap": re.search(r"色板|色标|中点", text) is not None,
        "error": re.search(r"误差棒|端帽", text) is not None,
        "legend": "图例" in text,
        "labels": "数据标签" in text,
        "data": re.search(r"只保留|筛选|过滤|排除|剔除|排序|升序|降序", text)
        is not None,
    }
    title = _parse_title(text)
    axis = _parse_axis(text)
    style = _parse_series_style(text)
    colormap = _parse_colormap(text)
    error = _parse_error_style(text)
    legend = _parse_legend(text)
    operations = _parse_data_operations(context, source_alias)
    parsed = {
        "title": title is not None,
        "axis": axis not in (None, ()),
        "style": style is not None,
        "colormap": colormap is not None,
        "error": error is not None,
        "legend": legend is not None,
        "labels": not requested["labels"] or "数据标签" in text,
        "data": operations not in (None, ()),
    }
    if any(requested[name] and not parsed[name] for name in requested):
        return None
    visuals: list[DraftVisualAction] = []
    if title is not None:
        visuals.append(title)
    if axis:
        visuals.extend(axis)
    if style is not None:
        visuals.append(style)
    if colormap is not None:
        visuals.append(colormap)
    if error is not None:
        visuals.append(error)
    if requested["labels"]:
        visuals.append(DraftSetDataLabels(target_alias="series_1", visible=True))
    if legend is not None:
        visuals.append(legend)
    constraints: list[str] = []
    if visuals:
        constraints.append("preserve_explicit_visual_parameters")
    if operations:
        constraints.append("preserve_explicit_data_operations")
    return ExplicitGoal(
        visual_actions=tuple(visuals),
        data_operations=operations or (),
        hard_constraints=tuple(constraints),
    )

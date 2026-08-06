"""Single deterministic resolver for all v1 Matplotlib and Origin consumers."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

import numpy as np
from matplotlib import font_manager
from scipy.stats import gaussian_kde, norm  # type: ignore[import-untyped]

from plotagent.charts.registry import get_chart
from plotagent.charts.series_rules import SeriesRule, get_series_rule
from plotagent.contracts.base import (
    ColorValue,
    ContentTableRef,
    ObjectVersionRef,
    PhysicalLength,
    WarningRecord,
)
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.contracts.plots import AxisSpec, PlotSpec, SafeRichText, SafeTextNode, ScaleSpec
from plotagent.contracts.rendering import (
    DataIntegritySnapshot,
    ResolvedAnnotation,
    ResolvedAxis,
    ResolvedFieldBinding,
    ResolvedFont,
    ResolvedLayer,
    ResolvedLegend,
    ResolvedPanel,
    ResolvedRenderPlan,
)
from plotagent.contracts.styles import SYMBOL_MAPPINGS, SymbolStyle, resolve_palette
from plotagent.plots.validation import PlotValidationError, validate_plot_spec
from plotagent.rendering.axis import AxisResolution, resolve_axis
from plotagent.rendering.data import (
    RenderDataStore,
    RenderTable,
    ResolvedPlot,
    Scalar,
    is_finite_number,
)
from plotagent.rendering.policies import VOLCANO_THRESHOLDS

RESOLVER_VERSION = "resolver.v1"
THUMBNAIL_LIMIT = 5_000
INTERACTIVE_LIMIT = 20_000
_SEQUENTIAL_PALETTE = ("#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725")
_DIVERGING_PALETTE = ("#3B4CC0", "#8DB0FE", "#F7F7F7", "#F4987A", "#B40426")
type DataSourceKind = Literal["direct", "fixed", "user_precomputed", "panel_plan"]
type QualityTier = Literal["thumbnail", "interactive", "formal"]
type SvgTextMode = Literal["text_to_path", "editable_text"]


def _plain_text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


def _label_key(value: SafeRichText | None) -> str | None:
    if value is None:
        return None
    parts: list[str] = []
    for node in value.nodes:
        if node.kind == "newline":
            parts.append("\n")
        elif node.kind == "fraction":
            parts.append(f"{node.text}/{node.denominator}")
        else:
            parts.append(node.text)
    return "".join(parts)


def _mm(value: float) -> PhysicalLength:
    return PhysicalLength(value=value, unit="mm")


def _source_kind(kind: str) -> DataSourceKind:
    if kind == "prepared":
        return "direct"
    if kind == "calculated":
        return "fixed"
    if kind == "precomputed":
        return "user_precomputed"
    raise ValueError(f"unknown series data kind {kind!r}")


def _number(value: Scalar) -> float:
    if not is_finite_number(value):
        raise PlotValidationError("PLOTSPEC_NUMERIC_REQUIRED", "geometry field must be numeric")
    return float(value)


def _binding_hash(plot: PlotSpec, series_index: int) -> str:
    data = plot.series[series_index].data
    if data.kind == "prepared":
        return data.prepared_dataset_ref.content_hash
    if data.kind == "calculated":
        return data.calculation_result_ref.content_hash
    return data.precomputed_data_ref.data_ref_hash


def _ordered_unique(values: Sequence[Scalar]) -> tuple[Scalar, ...]:
    result: list[Scalar] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def _valid_rows(values: Mapping[str, tuple[Scalar, ...]]) -> tuple[tuple[int, ...], int]:
    row_count = len(next(iter(values.values())))
    valid: list[int] = []
    for index in range(row_count):
        row_values = tuple(column[index] for column in values.values())
        invalid = any(value is None for value in row_values)
        invalid = invalid or any(
            isinstance(value, float) and not math.isfinite(value) for value in row_values
        )
        if not invalid:
            valid.append(index)
    return tuple(valid), row_count - len(valid)


def _take(
    values: Mapping[str, tuple[Scalar, ...]], indices: Sequence[int]
) -> dict[str, tuple[Scalar, ...]]:
    return {role: tuple(column[index] for index in indices) for role, column in values.items()}


@dataclass(frozen=True, slots=True)
class _DraftLayer:
    layer_id: str
    target_id: str
    panel_id: str
    geometry: str
    source_kind: DataSourceKind
    roles: Mapping[str, tuple[Scalar, ...]]
    x_roles: tuple[str, ...]
    y_roles: tuple[str, ...]
    label: SafeRichText | None
    color_index: int
    excluded_rows: int = 0
    x_offset: tuple[float, ...] = ()
    palette: tuple[str, ...] = ()
    levels: tuple[float, ...] = ()
    color_minimum: float | None = None
    color_maximum: float | None = None
    color_override: str | None = None
    encoding_index: int = 0
    encoding_count: int = 1

    @property
    def row_count(self) -> int:
        return len(next(iter(self.roles.values())))


@dataclass(frozen=True, slots=True)
class PanelPlan:
    """An explicit K25 child plan and exact physical placement."""

    panel_id: str
    resolved_plot: ResolvedPlot
    left_mm: float
    top_mm: float
    width_mm: float
    height_mm: float
    panel_label: SafeRichText


def _series_values(
    plot: PlotSpec, store: RenderDataStore, index: int
) -> tuple[SeriesRule, dict[str, tuple[Scalar, ...]], int]:
    series = plot.series[index]
    rule = get_series_rule(plot.chart_type_id, series.geometry)
    roles = rule.roles_for_count(len(series.data.role_fields))
    table = store.get(_binding_hash(plot, index))
    values = {
        role: table.column(field_id)
        for role, field_id in zip(roles, series.data.role_fields, strict=True)
    }
    valid, excluded = _valid_rows(values)
    return rule, _take(values, valid), excluded


def _generic_drafts(plot: PlotSpec, store: RenderDataStore) -> list[_DraftLayer]:
    drafts: list[_DraftLayer] = []
    color_index = 0
    for index, series in enumerate(plot.series):
        rule, values, excluded = _series_values(plot, store, index)
        split_role = "group" if "group" in values else None
        groups = _ordered_unique(values[split_role]) if split_role else (None,)
        for group_index, group in enumerate(groups):
            if split_role:
                indices = tuple(i for i, item in enumerate(values[split_role]) if item == group)
                selected = _take(values, indices)
                label: SafeRichText | None = _plain_text(str(group))
            else:
                selected = values
                label = series.label
            geometry = rule.resolved_geometry
            if geometry == "xy.bubble":
                selected = _resolve_bubble(selected)
            if geometry == "xy.error" and "error" in selected:
                center = selected["center"]
                error = selected["error"]
                selected = dict(selected)
                selected["lower"] = tuple(
                    _number(c) - _number(e) for c, e in zip(center, error, strict=True)
                )
                selected["upper"] = tuple(
                    _number(c) + _number(e) for c, e in zip(center, error, strict=True)
                )
                selected.pop("error")
            drafts.append(
                _DraftLayer(
                    layer_id=f"layer.{index}.{group_index}",
                    target_id=series.series_id,
                    panel_id="panel:main",
                    geometry=geometry,
                    source_kind=_source_kind(series.data.kind),
                    roles=selected,
                    x_roles=rule.x_range_roles,
                    y_roles=rule.y_range_roles,
                    label=label,
                    color_index=color_index,
                    excluded_rows=excluded if group_index == 0 else 0,
                    encoding_index=group_index,
                    encoding_count=len(groups),
                )
            )
            color_index += 1
    return drafts


def _resolve_bubble(values: Mapping[str, tuple[Scalar, ...]]) -> dict[str, tuple[Scalar, ...]]:
    resolved = dict(values)
    if "size" in values:
        sizes = tuple(_number(value) for value in values["size"])
        if any(value < 0 for value in sizes):
            raise PlotValidationError(
                "PLOTSPEC_BUBBLE_SIZE_INVALID", "bubble sizes cannot be negative"
            )
        minimum, maximum = min(sizes), max(sizes)
        if minimum == maximum:
            areas = tuple(64.0 for _ in sizes)
        else:
            areas = tuple(16.0 + (value - minimum) / (maximum - minimum) * 128.0 for value in sizes)
        resolved["marker_area"] = areas
    if "color" in values:
        colors = tuple(_number(value) for value in values["color"])
        minimum, maximum = min(colors), max(colors)
        resolved["point_color"] = tuple(
            _palette_color(value, minimum, maximum, _SEQUENTIAL_PALETTE) for value in colors
        )
    return resolved


def _palette_color(value: float, minimum: float, maximum: float, palette: tuple[str, ...]) -> str:
    ratio = 0.5 if minimum == maximum else (value - minimum) / (maximum - minimum)
    index = min(len(palette) - 1, max(0, round(ratio * (len(palette) - 1))))
    return palette[index]


def _bar_drafts(plot: PlotSpec, store: RenderDataStore) -> list[_DraftLayer]:
    drafts: list[_DraftLayer] = []
    color_index = 0
    for series_index, series in enumerate(plot.series):
        rule, values, excluded = _series_values(plot, store, series_index)
        categories = _ordered_unique(values["category"])
        subgroup_role = (
            "group" if "group" in values else "component" if "component" in values else None
        )
        subgroups = _ordered_unique(values[subgroup_role]) if subgroup_role else (None,)
        seen = set()
        for category, subgroup in zip(
            values["category"],
            values[subgroup_role] if subgroup_role else (None,) * len(values["category"]),
            strict=True,
        ):
            key = (category, subgroup)
            if key in seen:
                raise PlotValidationError(
                    "PLOTSPEC_BAR_DUPLICATE",
                    "bar category/group coordinates must already be unique",
                )
            seen.add(key)

        stacked = rule.resolved_geometry in {"bar.stacked", "bar.percent"}
        if rule.resolved_geometry == "bar.percent":
            totals = {
                category: sum(
                    _number(value)
                    for item_category, value in zip(
                        values["category"], values["value"], strict=True
                    )
                    if item_category == category
                )
                for category in categories
            }
            if any(abs(total - 1.0) > 1e-6 for total in totals.values()):
                raise PlotValidationError(
                    "PLOTSPEC_PERCENT_STACK_INVALID",
                    "W3 percent-stack geometry must sum to one per category",
                )
        positive = {category: 0.0 for category in categories}
        negative = {category: 0.0 for category in categories}
        count = len(subgroups)
        width = 0.8 if stacked or count == 1 else 0.8 / count
        for subgroup_index, subgroup in enumerate(subgroups):
            indices = tuple(
                index
                for index, item in enumerate(
                    values[subgroup_role] if subgroup_role else values["category"]
                )
                if (item == subgroup if subgroup_role else True)
            )
            selected = _take(values, indices)
            x_values = selected["category"]
            heights = tuple(_number(value) for value in selected["value"])
            bottoms: list[float] = []
            for category, height in zip(x_values, heights, strict=True):
                if not stacked:
                    bottom = 0.0
                elif height >= 0:
                    bottom = positive[category]
                    positive[category] += height
                else:
                    bottom = negative[category]
                    negative[category] += height
                bottoms.append(bottom)
            tops = tuple(bottom + height for bottom, height in zip(bottoms, heights, strict=True))
            output: dict[str, tuple[Scalar, ...]] = {
                "x": x_values,
                "height": heights,
                "bottom": tuple(bottoms),
                "top": tops,
                "width": tuple(width for _ in heights),
            }
            for role in ("lower", "upper"):
                if role in selected:
                    output[role] = selected[role]
            offset = 0.0 if stacked or count == 1 else (subgroup_index - (count - 1) / 2) * width
            drafts.append(
                _DraftLayer(
                    layer_id=f"layer.{series_index}.{subgroup_index}",
                    target_id=series.series_id,
                    panel_id="panel:main",
                    geometry=rule.resolved_geometry,
                    source_kind=_source_kind(series.data.kind),
                    roles=output,
                    x_roles=("x",),
                    y_roles=tuple(
                        role for role in ("bottom", "top", "lower", "upper") if role in output
                    ),
                    label=_plain_text(str(subgroup)) if subgroup is not None else series.label,
                    color_index=color_index,
                    excluded_rows=excluded if subgroup_index == 0 else 0,
                    x_offset=tuple(offset for _ in heights),
                    encoding_index=subgroup_index,
                    encoding_count=count,
                )
            )
            color_index += 1
    return drafts


def _distribution_drafts(plot: PlotSpec, store: RenderDataStore) -> list[_DraftLayer]:
    if plot.chart_type_id not in {"K12", "K13", "K14"}:
        return _generic_drafts(plot, store)
    drafts: list[_DraftLayer] = []
    color_index = 0
    for series_index, series in enumerate(plot.series):
        rule, values, excluded = _series_values(plot, store, series_index)
        if plot.chart_type_id == "K12":
            group_values = values.get("group", tuple("All" for _ in values["value"]))
            groups = _ordered_unique(group_values)
            for group_index, group in enumerate(groups):
                indices = tuple(i for i, value in enumerate(group_values) if value == group)
                y_values = tuple(values["value"][i] for i in indices)
                jitter = tuple(
                    _deterministic_jitter(_binding_hash(plot, series_index), index)
                    for index in indices
                )
                drafts.append(
                    _DraftLayer(
                        layer_id=f"layer.{series_index}.{group_index}",
                        target_id=series.series_id,
                        panel_id="panel:main",
                        geometry=rule.resolved_geometry,
                        source_kind=_source_kind(series.data.kind),
                        roles={"x": tuple(group for _ in indices), "y": y_values},
                        x_roles=("x",),
                        y_roles=("y",),
                        label=_plain_text(str(group)),
                        color_index=color_index,
                        excluded_rows=excluded if group_index == 0 else 0,
                        x_offset=jitter,
                        encoding_index=group_index,
                        encoding_count=len(groups),
                    )
                )
                color_index += 1
        elif plot.chart_type_id == "K13":
            group_values = values.get("group", tuple("All" for _ in values["q1"]))
            output = dict(values)
            output["group"] = group_values
            drafts.append(
                _DraftLayer(
                    layer_id=f"layer.{series_index}.0",
                    target_id=series.series_id,
                    panel_id="panel:main",
                    geometry=rule.resolved_geometry,
                    source_kind=_source_kind(series.data.kind),
                    roles=output,
                    x_roles=("group",),
                    y_roles=rule.y_range_roles,
                    label=series.label,
                    color_index=color_index,
                    excluded_rows=excluded,
                )
            )
            color_index += 1
        else:
            group_values = values.get("group", tuple("All" for _ in values["grid"]))
            groups = _ordered_unique(group_values)
            for group_index, group in enumerate(groups):
                indices = tuple(i for i, value in enumerate(group_values) if value == group)
                grid = tuple(values["grid"][i] for i in indices)
                density = tuple(_number(values["density"][i]) for i in indices)
                maximum = max(density) if density else 1.0
                half_width = tuple(
                    0.4 * value / maximum if maximum > 0 else 0.0 for value in density
                )
                drafts.append(
                    _DraftLayer(
                        layer_id=f"layer.{series_index}.{group_index}",
                        target_id=series.series_id,
                        panel_id="panel:main",
                        geometry=rule.resolved_geometry,
                        source_kind=_source_kind(series.data.kind),
                        roles={
                            "x": tuple(group for _ in grid),
                            "y": grid,
                            "half_width": half_width,
                        },
                        x_roles=("x",),
                        y_roles=("y",),
                        label=_plain_text(str(group)),
                        color_index=color_index,
                        excluded_rows=excluded if group_index == 0 else 0,
                        encoding_index=group_index,
                        encoding_count=len(groups),
                    )
                )
                color_index += 1
    return drafts


def _deterministic_jitter(binding_hash: str, row_index: int) -> float:
    digest = hashlib.sha256(f"{binding_hash}:{row_index}".encode()).digest()
    unit = int.from_bytes(digest[:8], "big") / (2**64 - 1)
    return (unit - 0.5) * 0.4


def _beeswarm_offsets(values: tuple[Scalar, ...]) -> tuple[float, ...]:
    """Pack nearby observations into deterministic symmetric horizontal rows."""

    numeric = tuple(_number(value) for value in values)
    minimum, maximum = min(numeric), max(numeric)
    bin_width = max((maximum - minimum) / 48.0, 1e-12)
    bins: dict[int, list[int]] = {}
    for index, value in enumerate(numeric):
        bins.setdefault(round((value - minimum) / bin_width), []).append(index)
    offsets = [0.0] * len(values)
    for indices in bins.values():
        spacing = min(0.052, 0.76 / max(len(indices) - 1, 1))
        centered = (len(indices) - 1) / 2
        for slot, index in enumerate(indices):
            offsets[index] = (slot - centered) * spacing
    return tuple(offsets)


def _matrix_drafts(plot: PlotSpec, store: RenderDataStore) -> list[_DraftLayer]:
    drafts = _generic_drafts(plot, store)
    for index, draft in enumerate(drafts):
        x_role = draft.x_roles[0]
        y_role = draft.y_roles[0]
        coordinates = tuple(zip(draft.roles[x_role], draft.roles[y_role], strict=True))
        if len(set(coordinates)) != len(coordinates):
            raise PlotValidationError(
                "PLOTSPEC_MATRIX_DUPLICATE",
                "matrix coordinates must be unique; the resolver never aggregates duplicates",
            )
        x_values = _ordered_unique(draft.roles[x_role])
        y_values = _ordered_unique(draft.roles[y_role])
        if len(coordinates) != len(x_values) * len(y_values):
            raise PlotValidationError(
                "PLOTSPEC_MATRIX_INCOMPLETE",
                "matrix geometry must provide a complete rectangular grid",
            )
        value_role = next(role for role in ("value", "z") if role in draft.roles)
        numeric = tuple(_number(value) for value in draft.roles[value_role])
        minimum, maximum = min(numeric), max(numeric)
        palette = _DIVERGING_PALETTE if plot.chart_type_id == "K21" else _SEQUENTIAL_PALETTE
        levels: tuple[float, ...] = ()
        if plot.chart_type_id == "K22":
            if minimum == maximum:
                levels = (minimum,)
            else:
                levels = tuple(minimum + (maximum - minimum) * step / 6 for step in range(7))
        drafts[index] = replace(
            draft,
            palette=palette,
            levels=levels,
            color_minimum=minimum,
            color_maximum=maximum,
        )
    return drafts


def _facet_drafts(plot: PlotSpec, store: RenderDataStore) -> list[_DraftLayer]:
    series = plot.series[0]
    rule, values, excluded = _series_values(plot, store, 0)
    facets = _ordered_unique(values["facet"])
    drafts: list[_DraftLayer] = []
    for index, facet in enumerate(facets):
        indices = tuple(i for i, item in enumerate(values["facet"]) if item == facet)
        drafts.append(
            _DraftLayer(
                layer_id=f"layer.0.{index}",
                target_id=series.series_id,
                panel_id=f"panel:facet.{index}",
                geometry=rule.resolved_geometry,
                source_kind=_source_kind(series.data.kind),
                roles={
                    "x": tuple(values["base_x"][i] for i in indices),
                    "y": tuple(values["base_y"][i] for i in indices),
                },
                x_roles=("x",),
                y_roles=("y",),
                label=_plain_text(str(facet)),
                color_index=index,
                excluded_rows=excluded if index == 0 else 0,
                encoding_index=index,
                encoding_count=len(facets),
            )
        )
    return drafts


def _special_drafts(plot: PlotSpec, store: RenderDataStore) -> list[_DraftLayer]:
    series = plot.series[0]
    rule, values, excluded = _series_values(plot, store, 0)
    target = series.series_id
    direct = _source_kind(series.data.kind)

    def draft(
        suffix: str,
        geometry: str,
        roles: Mapping[str, tuple[Scalar, ...]],
        x_roles: tuple[str, ...],
        y_roles: tuple[str, ...],
        *,
        panel: str = "panel:main",
        color: int = 0,
        label: str | None = None,
        source: DataSourceKind = direct,
        palette: tuple[str, ...] = (),
        color_override: str | None = None,
        x_offset: tuple[float, ...] = (),
        encoding_index: int = 0,
        encoding_count: int = 1,
    ) -> _DraftLayer:
        return _DraftLayer(
            layer_id=f"layer.0.{suffix}",
            target_id=target,
            panel_id=panel,
            geometry=geometry,
            source_kind=source,
            roles=roles,
            x_roles=x_roles,
            y_roles=y_roles,
            label=_plain_text(label) if label else None,
            color_index=color,
            excluded_rows=excluded if suffix == "0" else 0,
            palette=palette,
            color_override=color_override,
            x_offset=x_offset,
            encoding_index=encoding_index,
            encoding_count=encoding_count,
        )

    chart_id = plot.chart_type_id
    if chart_id == "X01":
        return [
            draft(
                "0",
                "distribution.step",
                {"x": values["x"], "probability": values["y"]},
                ("x",),
                ("probability",),
            )
        ]

    if chart_id == "X02":
        return [
            draft(
                "0",
                "special.lollipop",
                {"x": values["category"], "y": values["value"]},
                ("x",),
                ("y",),
                color=0,
            )
        ]

    if chart_id == "X03":
        result = []
        for index, (category, start, end) in enumerate(
            zip(values["category"], values["start"], values["end"], strict=True)
        ):
            result.append(
                draft(
                    str(index),
                    "xy.line",
                    {"x": (start, end), "y": (category, category)},
                    ("x",),
                    ("y",),
                    color=0,
                    color_override="#B8BDC6",
                )
            )
        result.extend(
            (
                draft(
                    "start",
                    "xy.symbol",
                    {"x": values["start"], "y": values["category"]},
                    ("x",),
                    ("y",),
                    color=0,
                    label="Start",
                ),
                draft(
                    "end",
                    "xy.symbol",
                    {"x": values["end"], "y": values["category"]},
                    ("x",),
                    ("y",),
                    color=1,
                    label="End",
                ),
            )
        )
        return result

    if chart_id == "X05":
        groups = values.get("group", tuple("All" for _ in values["value"]))
        unique_groups = _ordered_unique(groups)
        result = []
        for group_index, group in enumerate(unique_groups):
            indices = tuple(index for index, item in enumerate(groups) if item == group)
            y = tuple(values["value"][index] for index in indices)
            jitter = _beeswarm_offsets(y)
            result.append(
                replace(
                    draft(
                        str(group_index),
                        "distribution.strip",
                        {"x": tuple(group for _ in indices), "y": y},
                        ("x",),
                        ("y",),
                        color=group_index,
                        label=str(group),
                        encoding_index=group_index,
                        encoding_count=len(unique_groups),
                    ),
                    x_offset=jitter,
                )
            )
        return result

    if chart_id == "X07":
        result = []
        groups = _ordered_unique(values["group"])
        for group_index, group in enumerate(groups):
            sample = np.asarray(
                [
                    _number(value)
                    for value, item in zip(values["value"], values["group"], strict=True)
                    if item == group
                ],
                dtype=float,
            )
            if len(sample) < 2 or float(np.ptp(sample)) == 0:
                grid = np.linspace(float(sample[0]) - 0.5, float(sample[0]) + 0.5, 64)
                density = np.exp(-((grid - float(sample[0])) ** 2) / 0.08)
            else:
                grid = np.linspace(float(sample.min()), float(sample.max()), 128)
                density = gaussian_kde(sample)(grid)
            density = density / max(float(density.max()), 1e-12) * 0.8
            result.append(
                draft(
                    str(group_index),
                    "xy.line",
                    {"x": tuple(grid), "y": tuple(group_index + density)},
                    ("x",),
                    ("y",),
                    color=group_index,
                    label=str(group),
                    source="fixed",
                    encoding_index=group_index,
                    encoding_count=len(groups),
                )
            )
        return result

    if chart_id == "X09":
        starts = tuple(_number(value) for value in values["start"])
        ends = tuple(_number(value) for value in values["end"])
        boundaries = (
            tuple(_number(value) for value in values["middle"]) if "middle" in values else ends
        )
        layers = [
            draft(
                "0",
                "bar.floating",
                {
                    "x": values["category"],
                    "height": tuple(
                        middle - start for start, middle in zip(starts, boundaries, strict=True)
                    ),
                    "bottom": starts,
                    "top": boundaries,
                    "width": tuple(0.72 for _ in starts),
                },
                ("x",),
                ("bottom", "top"),
                color=0,
                label="Middle" if "middle" in values else None,
            )
        ]
        if "middle" in values:
            layers.append(
                draft(
                    "1",
                    "bar.floating",
                    {
                        "x": values["category"],
                        "height": tuple(
                            end - middle for middle, end in zip(boundaries, ends, strict=True)
                        ),
                        "bottom": boundaries,
                        "top": ends,
                        "width": tuple(0.72 for _ in starts),
                    },
                    ("x",),
                    ("bottom", "top"),
                    color=2,
                    label="End",
                )
            )
        return layers

    if chart_id == "X11":
        deltas = tuple(_number(value) for value in values["delta"])
        running = 0.0
        bottoms: list[float] = []
        for delta in deltas:
            bottoms.append(running if delta >= 0 else running + delta)
            running += delta
        return [
            draft(
                str(index),
                "bar.stacked",
                {
                    "x": (values["category"][index],),
                    "height": (abs(delta),),
                    "bottom": (bottoms[index],),
                    "top": (bottoms[index] + abs(delta),),
                    "width": (0.72,),
                },
                ("x",),
                ("bottom", "top"),
                source="fixed",
                color_override="#2A9D6F" if delta >= 0 else "#D64545",
            )
            for index, delta in enumerate(deltas)
        ]

    if chart_id == "X12":
        actual = tuple(_number(value) for value in values["actual_value"])
        ranges = [
            tuple(_number(value) for value in values[name])
            for name in ("range3", "range2", "range1")
            if name in values
        ]
        if not ranges:
            ranges = [
                tuple(
                    max(a, _number(t)) * factor
                    for a, t in zip(actual, values["target"], strict=True)
                )
                for factor in (1.25, 1.0, 0.75)
            ]
        result = []
        range_colors = ("#E5E7EB", "#CBD5E1", "#94A3B8")
        for index, range_values in enumerate(ranges):
            result.append(
                draft(
                    f"range{index}",
                    "bar.single",
                    {
                        "x": values["item"],
                        "height": range_values,
                        "bottom": tuple(0.0 for _ in range_values),
                        "top": range_values,
                        "width": tuple(0.82 - index * 0.13 for _ in range_values),
                    },
                    ("x",),
                    ("top",),
                    color=index + 2,
                    color_override=range_colors[index],
                )
            )
        result.append(
            draft(
                "actual",
                "bar.single",
                {
                    "x": values["item"],
                    "height": actual,
                    "bottom": tuple(0.0 for _ in actual),
                    "top": actual,
                    "width": tuple(0.28 for _ in actual),
                },
                ("x",),
                ("top",),
                color=0,
                label="Actual",
                color_override="#1F2937",
            )
        )
        result.append(
            draft(
                "target",
                "xy.symbol",
                {"x": values["item"], "y": values["target"]},
                ("x",),
                ("y",),
                color=1,
                label="Target",
                color_override="#D64545",
            )
        )
        return result

    if chart_id == "X13":
        left = tuple(-abs(_number(value)) for value in values["left"])
        right = tuple(abs(_number(value)) for value in values["right"])
        return [
            draft(
                "0",
                "bar.horizontal",
                {
                    "y": values["category"],
                    "width": left,
                    "left": tuple(0.0 for _ in left),
                    "right": left,
                    "height": tuple(0.72 for _ in left),
                },
                ("left", "right"),
                ("y",),
                color=0,
                label="Left",
            ),
            draft(
                "1",
                "bar.horizontal",
                {
                    "y": values["category"],
                    "width": right,
                    "left": tuple(0.0 for _ in right),
                    "right": right,
                    "height": tuple(0.72 for _ in right),
                },
                ("left", "right"),
                ("y",),
                color=1,
                label="Right",
            ),
        ]

    if chart_id == "X15":
        result = []
        variables = (("x", values["x"]), ("y", values["y"]), ("z", values["z"]))
        for row, (_y_name, y_values) in enumerate(variables):
            for column, (_x_name, x_values) in enumerate(variables):
                panel = f"panel:matrix.{row}.{column}"
                if row == column:
                    numeric = np.asarray([_number(value) for value in x_values], dtype=float)
                    counts, edges = np.histogram(
                        numeric, bins=min(10, max(4, round(math.sqrt(len(numeric)))))
                    )
                    result.append(
                        draft(
                            f"{row}.{column}",
                            "distribution.histogram",
                            {
                                "left": tuple(edges[:-1]),
                                "right": tuple(edges[1:]),
                                "height": tuple(float(value) for value in counts),
                            },
                            ("left", "right"),
                            ("height",),
                            panel=panel,
                            color=row,
                            source="fixed",
                        )
                    )
                else:
                    result.append(
                        draft(
                            f"{row}.{column}",
                            "xy.symbol",
                            {"x": x_values, "y": y_values},
                            ("x",),
                            ("y",),
                            panel=panel,
                            color=(row + column) % 3,
                        )
                    )
        return result

    if chart_id == "X16":
        x_array = np.asarray([_number(value) for value in values["x"]], dtype=float)
        y_array = np.asarray([_number(value) for value in values["y"]], dtype=float)
        bins = min(30, max(8, round(math.sqrt(len(x_array)) / 2)))
        counts, x_edges, y_edges = np.histogram2d(x_array, y_array, bins=bins)
        x_centers = (x_edges[:-1] + x_edges[1:]) / 2
        y_centers = (y_edges[:-1] + y_edges[1:]) / 2
        grid_x, grid_y = np.meshgrid(x_centers, y_centers)
        flat = tuple(float(value) for value in counts.T.ravel())
        density_layer = draft(
            "0",
            "matrix.heatmap",
            {"x": tuple(grid_x.ravel()), "y": tuple(grid_y.ravel()), "z": flat},
            ("x",),
            ("y",),
            source="fixed",
            palette=_SEQUENTIAL_PALETTE,
        )
        return [replace(density_layer, color_minimum=min(flat), color_maximum=max(flat))]

    if chart_id == "X17":
        x_array = np.asarray([_number(value) for value in values["x"]], dtype=float)
        y_array = np.asarray([_number(value) for value in values["y"]], dtype=float)
        x_counts, x_edges = np.histogram(
            x_array, bins=min(16, max(6, round(math.sqrt(len(x_array)))))
        )
        y_grid = np.linspace(float(y_array.min()), float(y_array.max()), 96)
        y_density = (
            gaussian_kde(y_array)(y_grid)
            if len(y_array) > 1 and float(np.ptp(y_array)) > 0
            else np.ones_like(y_grid)
        )
        return [
            draft(
                "0",
                "xy.symbol",
                {"x": values["x"], "y": values["y"]},
                ("x",),
                ("y",),
                panel="panel:center",
            ),
            draft(
                "top",
                "distribution.histogram",
                {
                    "left": tuple(x_edges[:-1]),
                    "right": tuple(x_edges[1:]),
                    "height": tuple(float(value) for value in x_counts),
                },
                ("left", "right"),
                ("height",),
                panel="panel:top",
                source="fixed",
            ),
            draft(
                "right",
                "xy.line",
                {
                    "x": tuple(float(value) for value in y_density),
                    "y": tuple(float(value) for value in y_grid),
                },
                ("x",),
                ("y",),
                panel="panel:right",
                source="fixed",
            ),
        ]

    if chart_id == "X18":
        sample = np.sort(np.asarray([_number(value) for value in values["value"]], dtype=float))
        probabilities = (np.arange(len(sample)) + 0.5) / len(sample)
        theoretical = norm.ppf(probabilities)
        q1, q3 = np.quantile(sample, (0.25, 0.75))
        tq1, tq3 = norm.ppf((0.25, 0.75))
        slope = float((q3 - q1) / (tq3 - tq1)) if tq3 != tq1 else 1.0
        intercept = float(q1 - slope * tq1)
        x_line = (float(theoretical.min()), float(theoretical.max()))
        return [
            draft(
                "0",
                "xy.symbol",
                {"x": tuple(theoretical), "y": tuple(sample)},
                ("x",),
                ("y",),
                source="fixed",
            ),
            draft(
                "line",
                "xy.line",
                {"x": x_line, "y": tuple(intercept + slope * value for value in x_line)},
                ("x",),
                ("y",),
                color=1,
                source="fixed",
            ),
        ]

    if chart_id == "X19":
        a = np.asarray([_number(value) for value in values["method_a"]], dtype=float)
        b = np.asarray([_number(value) for value in values["method_b"]], dtype=float)
        mean = (a + b) / 2
        difference = a - b
        center = float(np.mean(difference))
        sd = float(np.std(difference, ddof=1)) if len(difference) > 1 else 0.0
        x_line = (float(mean.min()), float(mean.max()))
        result = [
            draft(
                "0",
                "xy.symbol",
                {"x": tuple(mean), "y": tuple(difference)},
                ("x",),
                ("y",),
                source="fixed",
            )
        ]
        for index, level in enumerate((center, center + 1.96 * sd, center - 1.96 * sd)):
            result.append(
                draft(
                    f"line{index}",
                    "xy.line",
                    {"x": x_line, "y": (level, level)},
                    ("x",),
                    ("y",),
                    color=index + 1,
                    source="fixed",
                )
            )
        return result

    if chart_id in {"X23", "X35", "X36"}:
        x_role = "x" if "x" in values else "category"
        x_values = values[x_role]
        left_geometry = (
            "xy.line"
            if chart_id == "X23"
            else "bar.floating"
            if chart_id == "X35"
            else "bar.single"
        )
        right_geometry = (
            "xy.line"
            if chart_id in {"X23", "X36"}
            else "bar.floating"
            if chart_id == "X35"
            else "bar.single"
        )

        def dual_roles(role: str, geometry: str) -> Mapping[str, tuple[Scalar, ...]]:
            if geometry == "xy.line":
                return {"x": x_values, "y": values[role]}
            numeric = tuple(_number(value) for value in values[role])
            return {
                "x": x_values,
                "height": numeric,
                "bottom": tuple(0.0 for _ in numeric),
                "top": numeric,
                "width": tuple(0.34 if chart_id == "X35" else 0.62 for _ in numeric),
            }

        return [
            draft(
                "0",
                left_geometry,
                dual_roles("left", left_geometry),
                ("x",),
                (("y",) if left_geometry == "xy.line" else ("top",)),
                panel="panel:left",
                color=0,
                label="Left",
                x_offset=(tuple(-0.19 for _ in x_values) if chart_id == "X35" else ()),
            ),
            draft(
                "1",
                right_geometry,
                dual_roles("right", right_geometry),
                ("x",),
                (("y",) if right_geometry == "xy.line" else ("top",)),
                panel="panel:right",
                color=1,
                label="Right",
                x_offset=(tuple(0.19 for _ in x_values) if chart_id == "X35" else ()),
            ),
        ]

    if chart_id == "X37":
        result = []
        for side_index, role in enumerate(("left", "right")):
            groups = _ordered_unique(values["group"])
            summaries: dict[str, list[Scalar]] = {
                name: [] for name in ("group", "q1", "median", "q3", "whisker_low", "whisker_high")
            }
            for group in groups:
                sample = np.asarray(
                    [
                        _number(value)
                        for value, item in zip(values[role], values["group"], strict=True)
                        if item == group
                    ],
                    dtype=float,
                )
                q1, median, q3 = np.quantile(sample, (0.25, 0.5, 0.75))
                iqr = q3 - q1
                summaries["group"].append(group)
                summaries["q1"].append(float(q1))
                summaries["median"].append(float(median))
                summaries["q3"].append(float(q3))
                summaries["whisker_low"].append(float(sample[sample >= q1 - 1.5 * iqr].min()))
                summaries["whisker_high"].append(float(sample[sample <= q3 + 1.5 * iqr].max()))
            result.append(
                draft(
                    str(side_index),
                    "distribution.box",
                    {key: tuple(items) for key, items in summaries.items()},
                    ("group",),
                    ("q1", "median", "q3", "whisker_low", "whisker_high"),
                    panel=("panel:left" if side_index == 0 else "panel:right"),
                    color=side_index,
                    label=role.title(),
                    source="fixed",
                )
            )
        return result

    if chart_id == "X38":
        result = []
        series_values = _ordered_unique(values["series"])
        all_y = np.asarray([_number(value) for value in values["y"]], dtype=float)
        offset = max(float(np.ptp(all_y)) * 0.32, 1.0)
        for index, series_value in enumerate(series_values):
            indices = tuple(i for i, item in enumerate(values["series"]) if item == series_value)
            result.append(
                draft(
                    str(index),
                    "xy.line",
                    {
                        "x": tuple(values["x"][i] for i in indices),
                        "y": tuple(_number(values["y"][i]) + index * offset for i in indices),
                    },
                    ("x",),
                    ("y",),
                    color=index,
                    label=str(series_value),
                    source="fixed",
                    encoding_index=index,
                    encoding_count=len(series_values),
                )
            )
        return result

    if chart_id == "S07":
        thresholds = VOLCANO_THRESHOLDS
        pvalues = np.asarray(
            [max(_number(value), np.finfo(float).tiny) for value in values["pvalue"]], dtype=float
        )
        volcano_y = -np.log10(pvalues)
        volcano_x = np.asarray([_number(value) for value in values["log2fc"]], dtype=float)
        significant = pvalues < thresholds.pvalue
        volcano_categories = np.where(
            significant & (volcano_x <= -thresholds.absolute_log2_fold_change),
            0,
            np.where(
                significant & (volcano_x >= thresholds.absolute_log2_fold_change),
                2,
                1,
            ),
        )
        labels = ("Down", "Not significant", "Up")
        volcano_result: list[_DraftLayer] = []
        for category in range(3):
            indices = tuple(int(index) for index in np.where(volcano_categories == category)[0])
            if indices:
                volcano_result.append(
                    draft(
                        str(category),
                        "xy.symbol",
                        {
                            "x": tuple(float(volcano_x[i]) for i in indices),
                            "y": tuple(float(volcano_y[i]) for i in indices),
                        },
                        ("x",),
                        ("y",),
                        color=category,
                        label=labels[category],
                        source="fixed",
                    )
                )
        x_limit = max(
            abs(float(volcano_x.min())),
            abs(float(volcano_x.max())),
            thresholds.absolute_log2_fold_change,
        )
        y_limit = max(float(volcano_y.max()), -math.log10(thresholds.pvalue))
        significance_y = -math.log10(thresholds.pvalue)
        volcano_result.append(
            draft(
                "threshold.pvalue",
                "xy.line",
                {"x": (-x_limit, x_limit), "y": (significance_y, significance_y)},
                ("x",),
                ("y",),
                color=1,
                source="fixed",
                color_override="#6B7280",
            )
        )
        for suffix, effect_threshold in (
            ("negative", -thresholds.absolute_log2_fold_change),
            ("positive", thresholds.absolute_log2_fold_change),
        ):
            volcano_result.append(
                draft(
                    f"threshold.fold_change.{suffix}",
                    "xy.line",
                    {"x": (effect_threshold, effect_threshold), "y": (0.0, y_limit)},
                    ("x",),
                    ("y",),
                    color=1,
                    source="fixed",
                    color_override="#6B7280",
                )
            )
        return volcano_result

    if chart_id == "X24":
        rows = sorted(
            zip(values["category"], values["value"], strict=True),
            key=lambda item: _number(item[1]),
            reverse=True,
        )
        pareto_categories = tuple(item[0] for item in rows)
        pareto_values = tuple(_number(item[1]) for item in rows)
        total = sum(pareto_values)
        cumulative = tuple(
            sum(pareto_values[: index + 1]) / total * 100 for index in range(len(pareto_values))
        )
        return [
            draft(
                "0",
                "bar.single",
                {
                    "x": pareto_categories,
                    "height": pareto_values,
                    "bottom": tuple(0.0 for _ in pareto_values),
                    "top": pareto_values,
                    "width": tuple(0.68 for _ in pareto_values),
                },
                ("x",),
                ("top",),
                panel="panel:left",
                color=0,
            ),
            draft(
                "1",
                "xy.line",
                {"x": pareto_categories, "y": cumulative},
                ("x",),
                ("y",),
                panel="panel:right",
                color=1,
                label="Cumulative %",
                source="fixed",
            ),
        ]

    raise PlotValidationError("PLOTSPEC_CHART_UNSUPPORTED", f"no resolver for {chart_id}")


def _build_drafts(plot: PlotSpec, store: RenderDataStore) -> list[_DraftLayer]:
    family = get_chart(plot.chart_type_id).adapter_family
    if family == "bar":
        return _bar_drafts(plot, store)
    if family == "distribution":
        return _distribution_drafts(plot, store)
    if family == "matrix":
        return _matrix_drafts(plot, store)
    if family == "facet":
        return _facet_drafts(plot, store)
    if plot.family.kind == "special":
        return _special_drafts(plot, store)
    return _generic_drafts(plot, store)


def _panel_layout(plot: PlotSpec, drafts: Sequence[_DraftLayer]) -> tuple[ResolvedPanel, ...]:
    width = plot.publication_profile.physical_size.width.value
    height = plot.publication_profile.physical_size.height.value
    panel_ids = tuple(dict.fromkeys(draft.panel_id for draft in drafts))
    if plot.chart_type_id in {"X23", "X24", "X35", "X36", "X37"}:
        # Pareto's percentage ticks and right-axis title need two additional
        # millimetres beyond the generic dual-axis margin at the formal 89 mm
        # canvas. Keep both overlay panels exactly coincident after reserving it.
        right_margin = 12.0 if plot.chart_type_id == "X24" else 10.0
        bounds = dict(
            left=_mm(14),
            top=_mm(5),
            width=_mm(max(10, width - 14 - right_margin)),
            height=_mm(max(10, height - 17)),
        )
        return tuple(ResolvedPanel(panel_id=panel_id, **bounds) for panel_id in panel_ids)
    if plot.chart_type_id == "X17":
        main_left, main_top = 14.0, 15.0
        main_width, main_height = max(10, width - 34), max(10, height - 29)
        return (
            ResolvedPanel(
                panel_id="panel:center",
                left=_mm(main_left),
                top=_mm(main_top),
                width=_mm(main_width),
                height=_mm(main_height),
            ),
            ResolvedPanel(
                panel_id="panel:top",
                left=_mm(main_left),
                top=_mm(4),
                width=_mm(main_width),
                height=_mm(9),
            ),
            ResolvedPanel(
                panel_id="panel:right",
                left=_mm(main_left + main_width + 2),
                top=_mm(main_top),
                width=_mm(12),
                height=_mm(main_height),
            ),
        )
    if any(draft.geometry == "special.risk_table" for draft in drafts):
        return (
            ResolvedPanel(
                panel_id="panel:main",
                left=_mm(14),
                top=_mm(5),
                width=_mm(max(10, width - 20)),
                height=_mm(max(10, (height - 17) * 0.72)),
            ),
            ResolvedPanel(
                panel_id="panel:risk",
                left=_mm(14),
                top=_mm(7 + (height - 17) * 0.72),
                width=_mm(max(10, width - 20)),
                height=_mm(max(8, (height - 17) * 0.24)),
            ),
        )
    if len(panel_ids) == 1:
        return (
            ResolvedPanel(
                panel_id=panel_ids[0],
                left=_mm(14),
                top=_mm(5),
                width=_mm(max(10, width - 20)),
                height=_mm(max(10, height - 17)),
            ),
        )
    columns = math.ceil(math.sqrt(len(panel_ids)))
    rows = math.ceil(len(panel_ids) / columns)
    left, top, right, bottom, gutter = 12.0, 5.0, 5.0, 10.0, 4.0
    panel_width = (width - left - right - gutter * (columns - 1)) / columns
    panel_height = (height - top - bottom - gutter * (rows - 1)) / rows
    return tuple(
        ResolvedPanel(
            panel_id=panel_id,
            left=_mm(left + (index % columns) * (panel_width + gutter)),
            top=_mm(top + (index // columns) * (panel_height + gutter)),
            width=_mm(panel_width),
            height=_mm(panel_height),
        )
        for index, panel_id in enumerate(panel_ids)
    )


def _find_axes(plot: PlotSpec) -> tuple[tuple[AxisSpec, ScaleSpec], tuple[AxisSpec, ScaleSpec]]:
    scale_by_id = {scale.scale_id: scale for scale in plot.scales}
    x_axis = next((axis for axis in plot.axes if axis.orientation == "x"), None)
    y_axis = next((axis for axis in plot.axes if axis.orientation == "y"), None)
    if x_axis is None or y_axis is None:
        raise PlotValidationError(
            "PLOTSPEC_AXIS_MISSING", "a renderable chart requires x and y axes"
        )
    return (x_axis, scale_by_id[x_axis.scale_id]), (y_axis, scale_by_id[y_axis.scale_id])


def _axis_values(drafts: Sequence[_DraftLayer], roles_name: str) -> tuple[Scalar, ...]:
    values: list[Scalar] = []
    for draft in drafts:
        roles = draft.x_roles if roles_name == "x" else draft.y_roles
        for role in roles:
            if role in draft.roles:
                values.extend(draft.roles[role])
    return tuple(values)


def _has_zero_y_baseline(drafts: Sequence[_DraftLayer]) -> bool:
    """Return whether visible geometry is anchored to a data-space zero baseline."""

    return any(
        draft.geometry in {"distribution.histogram", "xy.area"}
        or (
            draft.geometry.startswith("bar.")
            and draft.geometry != "bar.horizontal"
            and any(
                is_finite_number(value) and float(value) == 0.0
                for value in draft.roles.get("bottom", ())
            )
        )
        for draft in drafts
    )


def _resolve_panel_axes(
    plot: PlotSpec,
    panels: Sequence[ResolvedPanel],
    drafts: Sequence[_DraftLayer],
) -> tuple[tuple[ResolvedAxis, ...], dict[tuple[str, str], AxisResolution]]:
    (x_spec, x_scale), (y_spec, y_scale) = _find_axes(plot)
    scale_by_id = {scale.scale_id: scale for scale in plot.scales}
    overlay = plot.chart_type_id in {"X23", "X24", "X35", "X36", "X37"}
    right_y_spec = next(
        (axis for axis in plot.axes if axis.orientation == "y" and axis.position == "right"),
        None,
    )
    shared = plot.chart_type_id == "K24"
    all_x = _axis_values(drafts, "x")
    all_y = _axis_values(drafts, "y")
    axes: list[ResolvedAxis] = []
    resolutions: dict[tuple[str, str], AxisResolution] = {}
    for panel_index, panel in enumerate(panels):
        if panel.panel_id == "panel:risk":
            continue
        panel_drafts = tuple(draft for draft in drafts if draft.panel_id == panel.panel_id)
        x_values = all_x if shared else _axis_values(panel_drafts, "x")
        y_values = all_y if shared else _axis_values(panel_drafts, "y")
        if plot.annotations and panel.panel_id == "panel:main":
            x_values += tuple(
                item.x for item in plot.annotations if item.affect_range and item.x is not None
            )
            y_values += tuple(
                item.y for item in plot.annotations if item.affect_range and item.y is not None
            )
        suffix = "" if len(panels) == 1 else f".p{panel_index}"
        panel_y_spec = (
            right_y_spec
            if overlay and panel.panel_id == "panel:right" and right_y_spec is not None
            else y_spec
        )
        panel_y_scale = scale_by_id[panel_y_spec.scale_id]
        try:
            x_resolved = resolve_axis(
                x_spec,
                x_scale,
                x_values,
                panel_id=panel.panel_id,
                resolved_axis_id=f"{x_spec.axis_id}{suffix}",
            )
            y_resolved = resolve_axis(
                panel_y_spec,
                panel_y_scale,
                y_values,
                panel_id=panel.panel_id,
                resolved_axis_id=f"{panel_y_spec.axis_id}{suffix}",
                include_zero=_has_zero_y_baseline(panel_drafts),
            )
            if plot.chart_type_id == "X13":
                x_resolved = replace(
                    x_resolved,
                    axis=x_resolved.axis.model_copy(
                        update={
                            "ticks": tuple(
                                tick.model_copy(
                                    update={
                                        "label": _plain_text(
                                            "".join(
                                                node.text for node in tick.label.nodes
                                            ).removeprefix("-")
                                        )
                                    }
                                )
                                for tick in x_resolved.axis.ticks
                            )
                        }
                    ),
                )
        except ValueError as error:
            raise PlotValidationError("AXIS_RESOLUTION_FAILED", str(error)) from error
        axes.extend((x_resolved.axis, y_resolved.axis))
        resolutions[(panel.panel_id, "x")] = x_resolved
        resolutions[(panel.panel_id, "y")] = y_resolved
    return tuple(axes), resolutions


def _simplified_indices(row_count: int, limit: int) -> tuple[int, ...]:
    if row_count <= limit:
        return tuple(range(row_count))
    if limit == 1:
        return (0,)
    return tuple(round(index * (row_count - 1) / (limit - 1)) for index in range(limit))


def _font(plot: PlotSpec) -> ResolvedFont:
    candidates = tuple(
        dict.fromkeys((plot.resolved_style.font_family, "Arial", "Microsoft YaHei", "DejaVu Sans"))
    )
    for family in candidates:
        try:
            path = Path(
                font_manager.findfont(
                    font_manager.FontProperties(family=[family]),
                    fallback_to_default=False,
                )
            )
        except ValueError:
            continue
        if path.is_file():
            return ResolvedFont(
                family=family,
                file_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
                size=plot.resolved_style.font_size,
            )
    raise PlotValidationError(
        "FONT_REQUIRED_MISSING", "no font in the fixed fallback stack is available"
    )


def _resolved_table(
    draft: _DraftLayer,
    x_resolution: AxisResolution,
    y_resolution: AxisResolution,
    layer_index: int,
) -> RenderTable:
    columns: dict[str, tuple[Scalar, ...]] = {}
    for role, values in draft.roles.items():
        converted: tuple[Scalar, ...]
        if role in draft.x_roles:
            converted = tuple(x_resolution.convert(value) for value in values)
            if draft.x_offset:
                converted = tuple(
                    _number(value) + offset
                    for value, offset in zip(converted, draft.x_offset, strict=True)
                )
        elif role in draft.y_roles:
            converted = tuple(y_resolution.convert(value) for value in values)
        else:
            converted = values
        columns[f"field:resolved.{layer_index}.{role}"] = converted
    return RenderTable.from_columns(columns)


class PlotResolver:
    """Resolve every chart through one versioned, target-neutral decision chain."""

    def resolve(
        self,
        plot: PlotSpec,
        data_store: RenderDataStore,
        *,
        quality_tier: QualityTier = "formal",
        svg_text_mode: SvgTextMode = "text_to_path",
    ) -> ResolvedPlot:
        if quality_tier not in {"thumbnail", "interactive", "formal"}:
            raise PlotValidationError("RENDER_QUALITY_UNSUPPORTED", "unknown render quality tier")
        if svg_text_mode not in {"text_to_path", "editable_text"}:
            raise PlotValidationError("SVG_TEXT_MODE_UNSUPPORTED", "unknown SVG text mode")
        validate_plot_spec(plot, data_store)
        if plot.chart_type_id == "K25":
            raise PlotValidationError(
                "PLOTSPEC_PANEL_PLANS_REQUIRED",
                "K25 must use resolve_panel_plans",
            )

        drafts = _build_drafts(plot, data_store)
        if not drafts or any(draft.row_count == 0 for draft in drafts):
            raise PlotValidationError("RENDER_EMPTY_GEOMETRY", "resolved geometry cannot be empty")
        if any(draft.geometry == "special.risk_table" for draft in drafts):
            drafts = [
                replace(draft, panel_id="panel:risk")
                if draft.geometry == "special.risk_table"
                else draft
                for draft in drafts
            ]
        panels = _panel_layout(plot, drafts)
        axes, axis_resolutions = _resolve_panel_axes(plot, panels, drafts)

        output_tables: dict[str, RenderTable] = {}
        layers: list[ResolvedLayer] = []
        total_rows = 0
        displayed_rows = 0
        excluded_rows = sum(draft.excluded_rows for draft in drafts)
        simplification_applied = False
        full_hashes: list[str] = []
        series_by_id = {series.series_id: series for series in plot.series}
        category_palette_extended = False
        category_symbol_fallback = False
        limit = THUMBNAIL_LIMIT if quality_tier == "thumbnail" else INTERACTIVE_LIMIT
        for layer_index, draft in enumerate(drafts):
            panel_id = draft.panel_id
            if panel_id == "panel:risk":
                x_resolution = axis_resolutions[("panel:main", "x")]
                y_resolution = axis_resolutions[("panel:main", "y")]
            else:
                x_resolution = axis_resolutions[(panel_id, "x")]
                y_resolution = axis_resolutions[(panel_id, "y")]
            full_table = _resolved_table(draft, x_resolution, y_resolution, layer_index)
            full_hashes.append(full_table.object_hash)
            total_rows += full_table.row_count
            simplify_allowed = draft.geometry.startswith(("xy.", "distribution.strip"))
            if quality_tier != "formal" and simplify_allowed and full_table.row_count > limit:
                table = full_table.select(_simplified_indices(full_table.row_count, limit))
                simplification_applied = True
            else:
                table = full_table
            displayed_rows += table.row_count
            output_tables[table.object_hash] = table
            field_ids = tuple(table.field_ids)
            roles = tuple(draft.roles)
            series_style = series_by_id[draft.target_id].style
            palette_spec = series_style.palette
            palette_colors = (
                tuple(color.value for color in palette_spec.colors) if palette_spec else ()
            )
            symbol = series_style.symbol
            if (
                len(plot.resolved_style.colors) < draft.encoding_count <= 15
                and len(palette_colors) < draft.encoding_count
            ):
                category_palette_extended = True
                fallback = resolve_palette("ColorBlindSafe15")
                palette_spec = fallback
                palette_colors = tuple(color.value for color in fallback.colors)
            if draft.encoding_count > 15:
                capacity = 15 * len(SYMBOL_MAPPINGS)
                if draft.encoding_count > capacity:
                    raise PlotValidationError(
                        "STYLE_CATEGORY_CAPACITY_EXCEEDED",
                        f"{draft.target_id} has {draft.encoding_count} categories; "
                        f"capacity is {capacity}",
                    )
                category_symbol_fallback = True
                fallback = resolve_palette("ColorBlindSafe15")
                fallback_colors = tuple(color.value for color in fallback.colors)
                # The >15-category policy is itself a frozen encoding contract.
                # Always use the complete 15-color Origin list here so a shorter
                # user palette cannot silently repeat a color/symbol pair before
                # the declared 15 x 12 capacity is reached.
                palette_spec = fallback
                palette_colors = fallback_colors
                shape = tuple(SYMBOL_MAPPINGS)[
                    (draft.encoding_index // len(palette_colors)) % len(SYMBOL_MAPPINGS)
                ]
                symbol = SymbolStyle(shape=shape, interior=symbol.interior)
            if category_symbol_fallback and draft.encoding_count > 15:
                color_value = ColorValue(
                    value=palette_colors[draft.encoding_index % len(palette_colors)]
                )
            elif draft.color_override is not None:
                color_value = ColorValue(value=draft.color_override)
            elif (
                (label_key := _label_key(draft.label)) is not None
                and label_key in series_style.category_colors
            ):
                color_value = series_style.category_colors[label_key]
            elif series_style.color is not None:
                color_value = series_style.color
            elif palette_colors:
                color_value = ColorValue(
                    value=palette_colors[draft.encoding_index % len(palette_colors)]
                )
            else:
                color_value = plot.resolved_style.colors[
                    draft.color_index % len(plot.resolved_style.colors)
                ]
            resolved_palette = (
                tuple(palette_spec.colors)
                if palette_spec is not None
                else tuple(ColorValue(value=value) for value in draft.palette)
            )
            layers.append(
                ResolvedLayer(
                    layer_id=draft.layer_id,
                    target_id=draft.target_id,
                    panel_id=draft.panel_id,
                    geometry=draft.geometry,
                    data_source_kind=draft.source_kind,
                    data_ref=ContentTableRef(
                        object_hash=table.object_hash,
                        row_count=table.row_count,
                        field_ids=field_ids,
                    ),
                    field_ids=field_ids,
                    field_bindings=tuple(
                        ResolvedFieldBinding(role=role, field_id=field_id)
                        for role, field_id in zip(roles, field_ids, strict=True)
                    ),
                    full_row_count=full_table.row_count,
                    displayed_row_count=table.row_count,
                    z_order=layer_index + 1,
                    label=draft.label,
                    color=color_value,
                    palette=resolved_palette,
                    levels=draft.levels,
                    color_minimum=draft.color_minimum,
                    color_maximum=draft.color_maximum,
                    line_width=series_style.line_width or plot.resolved_style.line_width,
                    marker_size=series_style.marker_size or plot.resolved_style.marker_size,
                    line_style=series_style.line_style,
                    symbol=symbol,
                    palette_spec=palette_spec,
                )
            )

        warnings: list[WarningRecord] = []
        if simplification_applied:
            warnings.append(
                WarningRecord(
                    warning_id="preview.simplified",
                    message=f"Displayed {displayed_rows} of {total_rows} resolved primitives.",
                )
            )
        if svg_text_mode == "editable_text":
            warnings.append(
                WarningRecord(
                    warning_id="svg.editable_text_font_portability",
                    message=(
                        "Editable SVG text requires the resolved font on the destination system."
                    ),
                )
            )
        if category_symbol_fallback:
            warnings.append(
                WarningRecord(
                    warning_id="style.category_color_symbol_fallback",
                    message=(
                        "More than 15 categories were encoded with deterministic color and "
                        "symbol pairs; colors were not silently recycled."
                    ),
                )
            )
        elif category_palette_extended:
            warnings.append(
                WarningRecord(
                    warning_id="style.category_palette_extended",
                    message=(
                        "The frozen 15-color Origin list was used so category colors "
                        "remain distinct and are not recycled."
                    ),
                )
            )
        source_hashes = tuple(
            dict.fromkeys(
                (canonical_hash(plot),)
                + tuple(_binding_hash(plot, index) for index in range(len(plot.series)))
                + tuple(full_hashes)
            )
        )
        annotations = tuple(
            ResolvedAnnotation(
                annotation_id=item.annotation_id,
                kind=item.kind,
                text=item.text,
                x=item.x,
                y=item.y,
                x2=item.x2,
                y2=item.y2,
                affect_range=item.affect_range,
            )
            for item in plot.annotations
        )
        labeled_layers = sum(layer.label is not None for layer in layers)
        plan = ResolvedRenderPlan(
            render_plan_id=f"renderplan:{plot.plot_id.removeprefix('plot:')}.{quality_tier}",
            render_plan_version=plot.plot_version,
            chart_type_id=plot.chart_type_id,
            resolver_version=RESOLVER_VERSION,
            source_refs=(
                ObjectVersionRef(object_id=plot.plot_id, expected_version=plot.plot_version),
            ),
            source_content_hashes=source_hashes,
            quality_tier=quality_tier,
            canvas=plot.publication_profile.physical_size,
            dpi=plot.publication_profile.dpi,
            title=plot.title,
            svg_text_mode=svg_text_mode,
            panels=panels,
            axes=axes,
            layers=tuple(layers),
            fonts=(_font(plot),),
            legend=ResolvedLegend(
                visible=(
                    labeled_layers > 1 if plot.legend.visible is None else plot.legend.visible
                ),
                placement=plot.legend.placement,
                anchor_x=plot.legend.anchor_x,
                anchor_y=plot.legend.anchor_y,
            ),
            annotations=annotations,
            data_integrity=DataIntegritySnapshot(
                total_rows=total_rows + excluded_rows,
                visible_rows=displayed_rows,
                excluded_rows=excluded_rows,
                nonfinite_values=excluded_rows,
                simplification_applied=simplification_applied,
                full_data_hash=canonical_hash(cast(JsonValue, list(full_hashes))),
            ),
            warnings=tuple(warnings),
        )
        return ResolvedPlot.create(plan, output_tables)

    def resolve_panel_plans(
        self,
        plot: PlotSpec,
        panel_plans: Sequence[PanelPlan],
        *,
        quality_tier: QualityTier = "formal",
        svg_text_mode: SvgTextMode = "text_to_path",
    ) -> ResolvedPlot:
        """Resolve K25 only from explicit child plans; never infer or splice data."""

        validate_plot_spec(plot, RenderDataStore(), allow_panel_plan_placeholder=True)
        if plot.chart_type_id != "K25":
            raise PlotValidationError(
                "PLOTSPEC_FAMILY_MISMATCH", "panel plans are only valid for K25"
            )
        if not 2 <= len(panel_plans) <= 4:
            raise PlotValidationError(
                "FIGURE_LAYOUT_UNSUPPORTED", "K25 requires two to four panels"
            )
        canvas_width = plot.publication_profile.physical_size.width.value
        canvas_height = plot.publication_profile.physical_size.height.value
        _validate_panel_placements(panel_plans, canvas_width, canvas_height)

        panels = tuple(
            ResolvedPanel(
                panel_id=item.panel_id,
                left=_mm(item.left_mm),
                top=_mm(item.top_mm),
                width=_mm(item.width_mm),
                height=_mm(item.height_mm),
            )
            for item in panel_plans
        )
        tables: dict[str, RenderTable] = {}
        axes: list[ResolvedAxis] = []
        layers: list[ResolvedLayer] = []
        annotations: list[ResolvedAnnotation] = []
        source_refs = [ObjectVersionRef(object_id=plot.plot_id, expected_version=plot.plot_version)]
        source_hashes = [canonical_hash(plot)]
        total = visible = excluded = nonfinite = 0
        simplified = False
        for index, item in enumerate(panel_plans):
            child = item.resolved_plot
            if child.plan.quality_tier != quality_tier:
                raise PlotValidationError(
                    "RENDER_QUALITY_MISMATCH",
                    "every K25 child plan must use the requested quality tier",
                )
            if len(child.plan.panels) != 1:
                raise PlotValidationError(
                    "FIGURE_LAYOUT_UNSUPPORTED",
                    "a K25 child must be a single explicit panel plan",
                )
            tables.update(child.tables)
            source_refs.extend(child.plan.source_refs)
            source_hashes.append(child.render_plan_hash)
            for axis in child.plan.axes:
                axis_suffix = axis.axis_id.removeprefix("axis:")
                axes.append(
                    axis.model_copy(
                        update={
                            "axis_id": f"axis:k25.{index}.{axis_suffix}",
                            "panel_id": item.panel_id,
                        }
                    )
                )
            for layer in child.plan.layers:
                layers.append(
                    layer.model_copy(
                        update={
                            "layer_id": f"k25.{index}.{layer.layer_id}",
                            "panel_id": item.panel_id,
                            "data_source_kind": "panel_plan",
                            "z_order": len(layers) + 1,
                        }
                    )
                )
            annotations.append(
                ResolvedAnnotation(
                    annotation_id=f"annotation:k25.panel.{index}",
                    panel_id=item.panel_id,
                    kind="panel_label",
                    text=item.panel_label,
                    x=0.02,
                    y=0.98,
                )
            )
            snapshot = child.plan.data_integrity
            total += snapshot.total_rows
            visible += snapshot.visible_rows
            excluded += snapshot.excluded_rows
            nonfinite += snapshot.nonfinite_values
            simplified = simplified or snapshot.simplification_applied
        plan = ResolvedRenderPlan(
            render_plan_id=f"renderplan:{plot.plot_id.removeprefix('plot:')}.{quality_tier}",
            render_plan_version=plot.plot_version,
            chart_type_id="K25",
            resolver_version=RESOLVER_VERSION,
            source_refs=tuple(source_refs),
            source_content_hashes=tuple(source_hashes),
            quality_tier=quality_tier,
            canvas=plot.publication_profile.physical_size,
            dpi=plot.publication_profile.dpi,
            svg_text_mode=svg_text_mode,
            panels=panels,
            axes=tuple(axes),
            layers=tuple(layers),
            fonts=tuple(
                dict.fromkeys(
                    font for item in panel_plans for font in item.resolved_plot.plan.fonts
                )
            ),
            annotations=tuple(annotations),
            data_integrity=DataIntegritySnapshot(
                total_rows=total,
                visible_rows=visible,
                excluded_rows=excluded,
                nonfinite_values=nonfinite,
                simplification_applied=simplified,
                full_data_hash=canonical_hash(cast(JsonValue, list(source_hashes))),
            ),
        )
        return ResolvedPlot.create(plan, tables)


def _validate_panel_placements(
    panel_plans: Sequence[PanelPlan], width: float, height: float
) -> None:
    ids = [item.panel_id for item in panel_plans]
    if len(set(ids)) != len(ids):
        raise PlotValidationError("FIGURE_LAYOUT_UNSUPPORTED", "K25 panel ids must be unique")
    for item in panel_plans:
        if min(item.left_mm, item.top_mm, item.width_mm, item.height_mm) < 0:
            raise PlotValidationError(
                "FIGURE_LAYOUT_UNSUPPORTED", "panel geometry cannot be negative"
            )
        if item.width_mm <= 0 or item.height_mm <= 0:
            raise PlotValidationError("FIGURE_LAYOUT_UNSUPPORTED", "panel size must be positive")
        if item.left_mm + item.width_mm > width or item.top_mm + item.height_mm > height:
            raise PlotValidationError("FIGURE_LAYOUT_UNSUPPORTED", "panel lies outside the canvas")
    for first_index, first in enumerate(panel_plans):
        for second in panel_plans[first_index + 1 :]:
            separated = (
                first.left_mm + first.width_mm <= second.left_mm
                or second.left_mm + second.width_mm <= first.left_mm
                or first.top_mm + first.height_mm <= second.top_mm
                or second.top_mm + second.height_mm <= first.top_mm
            )
            if not separated:
                raise PlotValidationError("FIGURE_LAYOUT_UNSUPPORTED", "K25 panels cannot overlap")

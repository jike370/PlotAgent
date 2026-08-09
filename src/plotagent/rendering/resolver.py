"""Single deterministic resolver for all v1 Matplotlib and Origin consumers."""

from __future__ import annotations

import hashlib
import math
import re
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
    ResolvedColorbar,
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
_BLACK = ColorValue(value="#000000")
_WHITE = ColorValue(value="#FFFFFF")
type DataSourceKind = Literal["direct", "fixed", "user_precomputed", "panel_plan"]
type QualityTier = Literal["thumbnail", "interactive", "formal"]
type SvgTextMode = Literal["text_to_path", "editable_text"]


def _plain_text(value: str) -> SafeRichText:
    return SafeRichText(nodes=(SafeTextNode(kind="plain", text=value),))


_OPAQUE_FIELD_LABEL = re.compile(r"^[0-9a-f]{16,64}$", re.IGNORECASE)


def _field_display_name(field_id: str, *, fallback: str) -> str:
    """Derive a safe label, never exposing a content-addressed field identifier."""

    suffix = field_id.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
    normalized = " ".join(suffix.replace("_", " ").replace("-", " ").split())
    if not normalized or _OPAQUE_FIELD_LABEL.fullmatch(normalized.replace(" ", "")):
        return fallback
    return normalized


def _semantic_axis_label(plot: PlotSpec, orientation: Literal["x", "y"]) -> str | None:
    """Return fixed v1 scientific semantics for charts whose display axes derive values."""

    # Plot version one is the compiler-created default. Later versions may carry an
    # explicit user axis-label edit and must not be overwritten by the resolver.
    if plot.plot_version != 1:
        return None
    labels: dict[str, tuple[str, str]] = {
        "K20": ("Column", "Row"),
        "K21": ("Column", "Row"),
        "S61": ("Predicted", "Actual"),
    }
    if plot.chart_type_id == "S07":
        significance = "q" if len(plot.series[0].data.role_fields) >= 4 else "p"
        labels["S07"] = ("log2FC", f"-log10({significance})")
    pair = labels.get(plot.chart_type_id)
    return None if pair is None else pair[0 if orientation == "x" else 1]


def _rgb(color: str) -> tuple[float, float, float]:
    value = color.removeprefix("#")[:6]
    return (
        int(value[0:2], 16) / 255,
        int(value[2:4], 16) / 255,
        int(value[4:6], 16) / 255,
    )


def _interpolated_palette_rgb(
    value: float,
    minimum: float,
    maximum: float,
    palette: Sequence[ColorValue],
) -> tuple[float, float, float]:
    if not palette:
        return (1.0, 1.0, 1.0)
    if len(palette) == 1 or minimum == maximum:
        return _rgb(palette[0].value)
    unit = min(max((value - minimum) / (maximum - minimum), 0.0), 1.0)
    scaled = unit * (len(palette) - 1)
    lower_index = min(int(math.floor(scaled)), len(palette) - 1)
    upper_index = min(lower_index + 1, len(palette) - 1)
    fraction = scaled - lower_index
    lower = _rgb(palette[lower_index].value)
    upper = _rgb(palette[upper_index].value)
    return (
        lower[0] + (upper[0] - lower[0]) * fraction,
        lower[1] + (upper[1] - lower[1]) * fraction,
        lower[2] + (upper[2] - lower[2]) * fraction,
    )


def _relative_luminance(color: tuple[float, float, float]) -> float:
    def linearize(component: float) -> float:
        if component <= 0.04045:
            return component / 12.92
        return float(((component + 0.055) / 1.055) ** 2.4)

    red, green, blue = (linearize(component) for component in color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_text_color(
    value: float,
    minimum: float,
    maximum: float,
    palette: Sequence[ColorValue],
) -> ColorValue:
    luminance = _relative_luminance(_interpolated_palette_rgb(value, minimum, maximum, palette))
    black_contrast = (luminance + 0.05) / 0.05
    white_contrast = 1.05 / (luminance + 0.05)
    return _BLACK if black_contrast >= white_contrast else _WHITE


def _count_text(value: float) -> str:
    rounded = round(value)
    if math.isclose(value, rounded, rel_tol=0.0, abs_tol=1e-9):
        return str(rounded)
    return format(value, ".6g")


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


def _length_mm(value: PhysicalLength) -> float:
    return value.value if value.unit == "mm" else value.value * 25.4 / 72


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
    panel_label: SafeRichText | None = None

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


def _logical_series_key(
    plot: PlotSpec,
    series_index: int,
    values: Mapping[str, tuple[Scalar, ...]],
) -> tuple[str, ...]:
    """Return the target-neutral visual identity for one declared series layer.

    K02 intentionally keeps line and symbol as separate edit targets.  When both
    targets consume the exact same bound role values, they are two geometries of
    one logical series rather than two independently encoded series.  Production
    PlotSpecs normally share the same data reference; the semantic value hash also
    keeps portable/legacy specs stable when equivalent columns were materialized
    separately.  Labels and fixture names are deliberately not part of this
    decision.
    """

    series = plot.series[series_index]
    if plot.chart_type_id != "K02":
        return ("target", series.series_id)
    value_hash = canonical_hash(
        cast(JsonValue, {role: list(column) for role, column in values.items()})
    )
    return ("binding-values", value_hash)


def _generic_drafts(plot: PlotSpec, store: RenderDataStore) -> list[_DraftLayer]:
    drafts: list[_DraftLayer] = []
    series_values = tuple(_series_values(plot, store, index) for index in range(len(plot.series)))
    logical_bases = tuple(
        _logical_series_key(plot, index, values)
        for index, (_rule, values, _excluded) in enumerate(series_values)
    )
    logical_keys: list[tuple[str, ...]] = []
    geometry_occurrences: dict[tuple[tuple[str, ...], str], int] = {}
    for base, series in zip(logical_bases, plot.series, strict=True):
        if plot.chart_type_id != "K02":
            logical_keys.append(base)
            continue
        occurrence_key = (base, series.geometry)
        occurrence = geometry_occurrences.get(occurrence_key, 0)
        geometry_occurrences[occurrence_key] = occurrence + 1
        # Pair the Nth line with the Nth symbol for identical bound values. This
        # preserves distinct identities even when two logical series happen to
        # contain numerically identical observations.
        logical_keys.append((*base, f"occurrence:{occurrence}"))
    logical_labels: dict[tuple[str, ...], SafeRichText | None] = {}
    for key, series in zip(logical_keys, plot.series, strict=True):
        if key not in logical_labels or logical_labels[key] is None:
            logical_labels[key] = series.label
    color_indices: dict[tuple[tuple[str, ...], Scalar | None], int] = {}
    emitted_legend_entries: set[tuple[tuple[str, ...], Scalar | None]] = set()
    for index, series in enumerate(plot.series):
        rule, values, excluded = series_values[index]
        split_role = "group" if "group" in values else None
        groups = _ordered_unique(values[split_role]) if split_role else (None,)
        for group_index, group in enumerate(groups):
            logical_key = logical_keys[index]
            encoding_key = (logical_key, group)
            if encoding_key not in color_indices:
                color_indices[encoding_key] = len(color_indices)
            if split_role:
                indices = tuple(i for i, item in enumerate(values[split_role]) if item == group)
                selected = _take(values, indices)
                logical_label: SafeRichText | None = _plain_text(str(group))
            else:
                selected = values
                logical_label = logical_labels[logical_key]
            label = logical_label if encoding_key not in emitted_legend_entries else None
            emitted_legend_entries.add(encoding_key)
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
                    x_roles=tuple(role for role in rule.x_range_roles if role in selected),
                    y_roles=tuple(role for role in rule.y_range_roles if role in selected),
                    label=label,
                    color_index=color_indices[encoding_key],
                    excluded_rows=excluded if group_index == 0 else 0,
                    encoding_index=group_index,
                    encoding_count=len(groups),
                )
            )
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
        cluster_width = plot.specialist.bar_area.width_ratio
        width = cluster_width if stacked or count == 1 else cluster_width / count
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
        data_minimum, data_maximum = min(numeric), max(numeric)
        colorbar = plot.specialist.colorbar
        minimum = colorbar.minimum if colorbar.minimum is not None else data_minimum
        maximum = colorbar.maximum if colorbar.maximum is not None else data_maximum
        palette = _DIVERGING_PALETTE if plot.chart_type_id == "K21" else _SEQUENTIAL_PALETTE
        levels: tuple[float, ...] = ()
        if plot.chart_type_id == "K22":
            if minimum == maximum:
                levels = (minimum,)
            else:
                levels = tuple(
                    minimum + (maximum - minimum) * step / (colorbar.levels - 1)
                    for step in range(colorbar.levels)
                )
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
    natural_facets = _ordered_unique(values["facet"])
    configured_order = tuple(
        value for value in plot.specialist.facet.order if value in natural_facets
    )
    facets = (
        *configured_order,
        *(value for value in natural_facets if value not in configured_order),
    )
    label_overrides = {item.value: item.label for item in plot.specialist.facet.labels}
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
                panel_label=_plain_text(label_overrides.get(str(facet), str(facet))),
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
                "special.drop_line",
                {"x": values["x"], "y": values["y"]},
                ("x",),
                ("y",),
                color=0,
            )
        ]

    if chart_id == "X03":
        value_roles = tuple(role for role in values if role.startswith("series_"))
        labels = tuple(
            _field_display_name(field_id, fallback=f"Series {index + 1}")
            for index, field_id in enumerate(series.data.role_fields[1:])
        )
        lollipop_layers: list[_DraftLayer] = []
        for row_index, category in enumerate(values["category"]):
            row_x_values = tuple(_number(values[role][row_index]) for role in value_roles)
            lollipop_layers.append(
                draft(
                    f"row.{row_index}",
                    "xy.line",
                    {"x": row_x_values, "y": tuple(category for _ in row_x_values)},
                    ("x",),
                    ("y",),
                    color=0,
                    color_override="#B8BDC6",
                )
            )
        for series_index, (role, label) in enumerate(zip(value_roles, labels, strict=True)):
            lollipop_layers.append(
                draft(
                    f"series.{series_index}",
                    "xy.symbol",
                    {"x": values[role], "y": values["category"]},
                    ("x",),
                    ("y",),
                    color=series_index,
                    label=label,
                    encoding_index=series_index,
                    encoding_count=len(value_roles),
                )
            )
        return lollipop_layers

    if chart_id in {"X39", "X40"}:
        value_roles = tuple(role for role in values if role.startswith("series_"))
        labels = tuple(
            _field_display_name(field_id, fallback=f"Series {index + 1}")
            for index, field_id in enumerate(series.data.role_fields)
        )
        positions = tuple(float(index) for index in range(len(value_roles)))
        series_layers: list[_DraftLayer] = []
        row_count = len(values[value_roles[0]])
        if chart_id == "X39":
            for row_index in range(row_count):
                series_layers.append(
                    draft(
                        f"row.{row_index}",
                        "xy.line",
                        {
                            "x": positions,
                            "x_label": labels,
                            "y": tuple(_number(values[role][row_index]) for role in value_roles),
                        },
                        ("x",),
                        ("y",),
                        color=0,
                        color_override="#000000",
                    )
                )
        else:
            for pair_index in range(len(value_roles) // 2):
                first = pair_index * 2
                pair_positions = positions[first : first + 2]
                pair_labels = labels[first : first + 2]
                pair_roles = value_roles[first : first + 2]
                for row_index in range(row_count):
                    series_layers.append(
                        draft(
                            f"pair.{pair_index}.row.{row_index}",
                            "xy.line",
                            {
                                "x": pair_positions,
                                "x_label": pair_labels,
                                "y": tuple(_number(values[role][row_index]) for role in pair_roles),
                            },
                            ("x",),
                            ("y",),
                            color=0,
                            color_override="#000000",
                        )
                    )
        for series_index, (role, label, position) in enumerate(
            zip(value_roles, labels, positions, strict=True)
        ):
            column_values = values[role]
            series_layers.append(
                draft(
                    f"series.{series_index}",
                    "xy.symbol",
                    {
                        "x": tuple(position for _ in column_values),
                        "x_label": tuple(label for _ in column_values),
                        "y": column_values,
                    },
                    ("x",),
                    ("y",),
                    color=series_index if chart_id == "X39" else series_index % 2,
                    label=label,
                    encoding_index=series_index,
                    encoding_count=len(value_roles),
                )
            )
        return series_layers

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
        natural_series = _ordered_unique(values["series"])
        configured_order = tuple(
            value for value in plot.specialist.y_offset.order if value in natural_series
        )
        series_values = (
            *configured_order,
            *(value for value in natural_series if value not in configured_order),
        )
        all_y = np.asarray([_number(value) for value in values["y"]], dtype=float)
        offset = plot.specialist.y_offset.distance or max(float(np.ptp(all_y)) * 0.32, 1.0)
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
        parameters = plot.specialist.chart_parameters
        thresholds = replace(
            VOLCANO_THRESHOLDS,
            absolute_log2_fold_change=parameters.volcano_absolute_log2_fold_change,
            pvalue=parameters.volcano_pvalue,
        )
        significance_values = values.get("qvalue", values["pvalue"])
        pvalues = np.asarray(
            [max(_number(value), np.finfo(float).tiny) for value in significance_values],
            dtype=float,
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
        reference = plot.specialist.chart_parameters.pareto_reference_percent
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
            draft(
                "2",
                "xy.line",
                {
                    "x": (pareto_categories[0], pareto_categories[-1]),
                    "y": (reference, reference),
                },
                ("x",),
                ("y",),
                panel="panel:right",
                color=1,
                source="fixed",
                color_override="#6B7280",
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
        return tuple(
            ResolvedPanel(
                panel_id=panel_id,
                left=_mm(14),
                top=_mm(5),
                width=_mm(max(10, width - 14 - right_margin)),
                height=_mm(max(10, height - 17)),
            )
            for panel_id in panel_ids
        )
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
        risk_group_count = max(
            1,
            len(
                dict.fromkeys(
                    value
                    for draft in drafts
                    if draft.geometry == "special.risk_table"
                    for value in draft.roles.get("group", ())
                )
            ),
        )
        top = 5.0
        bottom = 6.0
        gap = 4.0
        available_height = max(18.0, height - top - bottom - gap)
        desired_risk_height = 6.0 + 4.0 * risk_group_count
        risk_height = min(
            max(8.0, desired_risk_height),
            max(8.0, available_height - 10.0),
        )
        main_height = max(10.0, available_height - risk_height)
        return (
            ResolvedPanel(
                panel_id="panel:main",
                left=_mm(14),
                top=_mm(top),
                width=_mm(max(10, width - 20)),
                height=_mm(main_height),
            ),
            ResolvedPanel(
                panel_id="panel:risk",
                left=_mm(14),
                top=_mm(top + main_height + gap),
                width=_mm(max(10, width - 20)),
                height=_mm(risk_height),
            ),
        )
    if len(panel_ids) == 1:
        panel_label = next(
            (draft.panel_label for draft in drafts if draft.panel_label is not None), None
        )
        return (
            ResolvedPanel(
                panel_id=panel_ids[0],
                left=_mm(14),
                top=_mm(5),
                width=_mm(max(10, width - 20)),
                height=_mm(max(10, height - 17)),
                label=panel_label,
            ),
        )
    columns = math.ceil(math.sqrt(len(panel_ids)))
    rows = math.ceil(len(panel_ids) / columns)
    gutter = _length_mm(plot.specialist.facet.gap) if plot.chart_type_id == "K24" else 4.0
    left, top, right, bottom = 12.0, 5.0, 5.0, 10.0
    panel_width = (width - left - right - gutter * (columns - 1)) / columns
    panel_height = (height - top - bottom - gutter * (rows - 1)) / rows
    return tuple(
        ResolvedPanel(
            panel_id=panel_id,
            left=_mm(left + (index % columns) * (panel_width + gutter)),
            top=_mm(top + (index // columns) * (panel_height + gutter)),
            width=_mm(panel_width),
            height=_mm(panel_height),
            label=next(
                (
                    draft.panel_label
                    for draft in drafts
                    if draft.panel_id == panel_id and draft.panel_label is not None
                ),
                None,
            ),
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
    shared_x = plot.chart_type_id == "K24" and plot.specialist.facet.shared_x
    shared_y = plot.chart_type_id == "K24" and plot.specialist.facet.shared_y
    all_x = _axis_values(drafts, "x")
    all_y = _axis_values(drafts, "y")
    axes: list[ResolvedAxis] = []
    resolutions: dict[tuple[str, str], AxisResolution] = {}
    for panel_index, panel in enumerate(panels):
        if panel.panel_id == "panel:risk":
            # A supplied risk table is a real second native panel, not a
            # decoration on the survival axes.  Resolve its supplied time and
            # risk-count values explicitly so every renderer receives the
            # same target-neutral panel contract.  No survival statistic is
            # calculated here.
            panel_drafts = tuple(draft for draft in drafts if draft.panel_id == panel.panel_id)
            risk_x_values = _axis_values(panel_drafts, "x")
            risk_y_values = tuple(
                value for draft in panel_drafts for value in draft.roles.get("risk_count", ())
            )
            suffix = f".p{panel_index}"
            try:
                x_resolved = resolve_axis(
                    x_spec,
                    x_scale,
                    risk_x_values,
                    panel_id=panel.panel_id,
                    resolved_axis_id=f"{x_spec.axis_id}{suffix}",
                )
                y_resolved = resolve_axis(
                    y_spec,
                    y_scale,
                    risk_y_values,
                    panel_id=panel.panel_id,
                    resolved_axis_id=f"{y_spec.axis_id}{suffix}",
                    include_zero=True,
                )
            except ValueError as error:
                raise PlotValidationError("AXIS_RESOLUTION_FAILED", str(error)) from error
            axes.extend((x_resolved.axis, y_resolved.axis))
            resolutions[(panel.panel_id, "x")] = x_resolved
            resolutions[(panel.panel_id, "y")] = y_resolved
            continue
        panel_drafts = tuple(draft for draft in drafts if draft.panel_id == panel.panel_id)
        x_values = all_x if shared_x else _axis_values(panel_drafts, "x")
        y_values = all_y if shared_y else _axis_values(panel_drafts, "y")
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
            dual_y = plot.specialist.dual_y
            if overlay:
                is_right = panel.panel_id == "panel:right"
                axis_color = dual_y.right_color if is_right else dual_y.left_color
                y_resolved = replace(
                    y_resolved,
                    axis=y_resolved.axis.model_copy(
                        update={
                            "color": axis_color or ColorValue(value="#000000"),
                            "line_width": dual_y.axis_width,
                        }
                    ),
                )
            if plot.chart_type_id in {"X39", "X40"}:
                labels_by_position: dict[str, str] = {}
                for draft in panel_drafts:
                    if "x_label" not in draft.roles:
                        continue
                    for position, label in zip(
                        draft.roles.get("x", ()), draft.roles["x_label"], strict=True
                    ):
                        labels_by_position.setdefault(str(position), str(label))
                x_resolved = replace(
                    x_resolved,
                    axis=x_resolved.axis.model_copy(
                        update={
                            "ticks": tuple(
                                tick.model_copy(
                                    update={
                                        "label": _plain_text(
                                            labels_by_position.get(category, category)
                                        )
                                    }
                                )
                                for tick, category in zip(
                                    x_resolved.axis.ticks,
                                    x_resolved.categories,
                                    strict=True,
                                )
                            )
                        }
                    ),
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
            semantic_x_label = _semantic_axis_label(plot, "x")
            semantic_y_label = _semantic_axis_label(plot, "y")
            if semantic_x_label is not None:
                x_resolved = replace(
                    x_resolved,
                    axis=x_resolved.axis.model_copy(
                        update={"label": _plain_text(semantic_x_label)}
                    ),
                )
            if semantic_y_label is not None:
                y_resolved = replace(
                    y_resolved,
                    axis=y_resolved.axis.model_copy(
                        update={"label": _plain_text(semantic_y_label)}
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


def _confusion_cell_annotations(
    draft: _DraftLayer,
    table: RenderTable,
    palette: Sequence[ColorValue],
    layer_index: int,
) -> tuple[ResolvedAnnotation, ...]:
    """Materialize target-neutral cell counts for the S61 confusion matrix only."""

    field_by_role = dict(zip(draft.roles, table.field_ids, strict=True))
    x_role = draft.x_roles[0]
    y_role = draft.y_roles[0]
    value_role = "value"
    minimum = draft.color_minimum
    maximum = draft.color_maximum
    if minimum is None or maximum is None:
        raise PlotValidationError(
            "PLOTSPEC_MATRIX_COLOR_RANGE_MISSING",
            "S61 cell labels require the resolved confusion-matrix color range",
        )
    x_values = table.column(field_by_role[x_role])
    y_values = table.column(field_by_role[y_role])
    values = table.column(field_by_role[value_role])
    annotations: list[ResolvedAnnotation] = []
    for row_index, (x_value, y_value, value) in enumerate(
        zip(x_values, y_values, values, strict=True)
    ):
        numeric_value = _number(value)
        annotations.append(
            ResolvedAnnotation(
                annotation_id=f"annotation:s61.cell.{layer_index}.{row_index}",
                panel_id=draft.panel_id,
                kind="text",
                text=_plain_text(_count_text(numeric_value)),
                color=_contrast_text_color(numeric_value, minimum, maximum, palette),
                x=_number(x_value),
                y=_number(y_value),
                affect_range=False,
            )
        )
    return tuple(annotations)


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
        derived_annotations: list[ResolvedAnnotation] = []
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
            if palette_spec is None and plot.chart_type_id == "K21":
                palette_spec = resolve_palette("OrangeNavy")
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
                label_key := _label_key(draft.label)
            ) is not None and label_key in series_style.category_colors:
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
                    fill_color=plot.specialist.bar_area.fill_color,
                    edge_color=plot.specialist.bar_area.edge_color,
                    edge_width=plot.specialist.bar_area.edge_width,
                    width_ratio=plot.specialist.bar_area.width_ratio,
                    alpha=plot.specialist.bar_area.alpha,
                    uncertainty_color=plot.specialist.uncertainty.color,
                    uncertainty_line_width=plot.specialist.uncertainty.line_width,
                    cap_size=plot.specialist.uncertainty.cap_size,
                    band_alpha=plot.specialist.uncertainty.band_alpha,
                    step_where=plot.specialist.chart_parameters.step_where,
                )
            )
            if plot.chart_type_id == "S61" and draft.geometry == "matrix.confusion":
                derived_annotations.extend(
                    _confusion_cell_annotations(draft, table, resolved_palette, layer_index)
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
                color=None,
                x=item.x,
                y=item.y,
                x2=item.x2,
                y2=item.y2,
                affect_range=item.affect_range,
            )
            for item in plot.annotations
        ) + tuple(derived_annotations)
        labeled_layers = sum(layer.label is not None for layer in layers)
        registration = get_chart(plot.chart_type_id)
        colorbar_style = plot.specialist.colorbar
        colorbar_layers = tuple(
            layer
            for layer in layers
            if layer.color_minimum is not None and layer.color_maximum is not None
        )
        color_minimums = tuple(
            float(layer.color_minimum)
            for layer in colorbar_layers
            if layer.color_minimum is not None
        )
        color_maximums = tuple(
            float(layer.color_maximum)
            for layer in colorbar_layers
            if layer.color_maximum is not None
        )
        resolved_colorbar = ResolvedColorbar(
            visible=("colorbar" in registration.edit_capabilities and colorbar_style.visible),
            title=colorbar_style.title,
            minimum=(
                colorbar_style.minimum
                if colorbar_style.minimum is not None
                else min(color_minimums, default=None)
            ),
            maximum=(
                colorbar_style.maximum
                if colorbar_style.maximum is not None
                else max(color_maximums, default=None)
            ),
            levels=colorbar_style.levels,
        )
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
                common=(plot.chart_type_id == "K24" and plot.specialist.facet.common_legend),
            ),
            colorbar=resolved_colorbar,
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

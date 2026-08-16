"""Profile-level data normalization shared by independent backends.

This module contains no drawing or backend-native object model.  It only
turns an ``EngineDataView`` into the semantic data shape promised by a public
engine profile so independent renderers cannot disagree about row/column
ordering or duplicate-cell handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isclose, isfinite, nan
from typing import Literal

from plotagent.plot_calculations.kernels import histogram_geometry

from .contracts import EngineColumn, EngineDataView, PlotDocument


@dataclass(frozen=True, slots=True)
class K20Grid:
    row_labels: tuple[str, ...]
    column_labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]
    row_field_name: str
    column_field_name: str
    value_field_name: str
    value_unit: str | None


@dataclass(frozen=True, slots=True)
class X23SeriesData:
    x_values: tuple[str | float, ...]
    x_labels: tuple[str, ...] | None
    left_values: tuple[float, ...]
    right_values: tuple[float, ...]
    x_field_name: str
    left_field_name: str
    right_field_name: str
    x_scale: Literal["categorical", "linear"]


@dataclass(frozen=True, slots=True)
class XYSeriesData:
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    x_field_name: str
    y_field_name: str


@dataclass(frozen=True, slots=True)
class PointErrorData:
    x_values: tuple[float, ...]
    center_values: tuple[float, ...]
    x_minus_errors: tuple[float, ...]
    x_plus_errors: tuple[float, ...]
    y_minus_errors: tuple[float, ...]
    y_plus_errors: tuple[float, ...]
    x_field_name: str
    center_field_name: str


@dataclass(frozen=True, slots=True)
class ErrorBandData:
    x_values: tuple[float, ...]
    center_values: tuple[float, ...]
    lower_values: tuple[float, ...]
    upper_values: tuple[float, ...]
    x_field_name: str
    center_field_name: str


@dataclass(frozen=True, slots=True)
class ScatterGroupData:
    label: str
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class K03ScatterData:
    groups: tuple[ScatterGroupData, ...]
    x_field_name: str
    y_field_name: str


@dataclass(frozen=True, slots=True)
class K04BubbleData:
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    size_values: tuple[float, ...] | None
    color_values: tuple[float, ...] | None
    x_field_name: str
    y_field_name: str
    size_field_name: str | None
    color_field_name: str | None


@dataclass(frozen=True, slots=True)
class CategorySeriesGrid:
    """Stable long-to-wide data used by one column-family profile.

    This is deliberately only a data shape.  Grouped, stacked and percent
    renderers remain independent and decide how the same cells are drawn.
    """

    category_labels: tuple[str, ...]
    series_labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]
    category_field_name: str
    value_field_name: str


@dataclass(frozen=True, slots=True)
class GroupedIndexedData:
    """Unpivoted summarized data for Origin's native ``plot_gindexed`` route."""

    indexes: tuple[int, ...]
    values: tuple[float, ...]
    categories: tuple[str, ...]
    groups: tuple[str, ...]
    category_labels: tuple[str, ...]
    group_labels: tuple[str, ...]
    category_field_name: str
    group_field_name: str
    value_field_name: str


@dataclass(frozen=True, slots=True)
class DistributionGroupData:
    label: str
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class DistributionData:
    groups: tuple[DistributionGroupData, ...]
    value_field_name: str


@dataclass(frozen=True, slots=True)
class FloatingIntervalData:
    categories: tuple[str, ...]
    start_values: tuple[float, ...]
    middle_values: tuple[float, ...] | None
    end_values: tuple[float, ...]
    category_field_name: str
    start_field_name: str
    middle_field_name: str | None
    end_field_name: str


@dataclass(frozen=True, slots=True)
class PopulationPyramidData:
    categories: tuple[str, ...]
    left_values: tuple[float, ...]
    right_values: tuple[float, ...]
    category_field_name: str
    left_field_name: str
    right_field_name: str


@dataclass(frozen=True, slots=True)
class ParetoData:
    categories: tuple[str, ...]
    values: tuple[float, ...]
    cumulative_percent: tuple[float, ...]
    category_field_name: str
    value_field_name: str


@dataclass(frozen=True, slots=True)
class ParetoSourceData:
    """Raw binned rows consumed by Origin's native ``plot_paretobin`` workflow."""

    categories: tuple[str, ...]
    values: tuple[float, ...]
    category_field_name: str
    value_field_name: str


@dataclass(frozen=True, slots=True)
class OffsetSeriesData:
    label: str
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class OffsetStackData:
    series: tuple[OffsetSeriesData, ...]
    x_field_name: str
    y_field_name: str
    series_field_name: str


@dataclass(frozen=True, slots=True)
class TrellisData:
    """Unpivoted rows consumed by Origin's native ``plot_group`` X-Function."""

    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    facet_values: tuple[str, ...]
    facet_labels: tuple[str, ...]
    facet_field_name: str
    x_field_name: str
    y_field_name: str


@dataclass(frozen=True, slots=True)
class HistogramData:
    left: tuple[float, ...]
    right: tuple[float, ...]
    center: tuple[float, ...]
    height: tuple[int | float, ...]
    count: tuple[int, ...]
    value_field_name: str
    normalization: Literal["count", "density"]
    rule: Literal["freedman_diaconis", "sturges", "constant"]


@dataclass(frozen=True, slots=True)
class WideColumnData:
    labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class LollipopData:
    categories: tuple[str, ...]
    columns: WideColumnData
    category_field_name: str


@dataclass(frozen=True, slots=True)
class WideSeriesData:
    """Official Origin row-wise source shape for X39 and X40.

    The worksheet remains wide: every bound value field is one Y column and
    every input observation remains one worksheet row.  Rendering backends may
    iterate equal-position values to draw the row-wise connectors, but they
    must not materialize those rows as public series objects or rewrite the
    source into one physical plot per row.
    """

    column_labels: tuple[str, ...]
    column_values: tuple[tuple[float, ...], ...]
    row_labels: tuple[str, ...] | None = None
    row_groups: tuple[str, ...] | None = None

    @property
    def row_count(self) -> int:
        return len(self.column_values[0])


def x40_identity_label_positions(values: tuple[float, ...]) -> tuple[float, ...]:
    """Spread colliding identity labels without changing source observations."""

    if not values:
        return ()
    span = max(values) - min(values)
    minimum_gap = max(span * 0.04, 0.1)
    ordered = sorted(range(len(values)), key=lambda index: (values[index], index))
    output = list(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and (
            values[ordered[end]] - values[ordered[end - 1]] < minimum_gap
        ):
            end += 1
        cluster = ordered[start:end]
        if len(cluster) > 1:
            center = sum(values[index] for index in cluster) / len(cluster)
            first = center - minimum_gap * (len(cluster) - 1) / 2
            for offset, index in enumerate(cluster):
                output[index] = first + minimum_gap * offset
        start = end
    return tuple(output)


@dataclass(frozen=True, slots=True)
class TimeSeriesLine:
    role: str
    time_values: tuple[datetime, ...]
    values: tuple[float, ...]
    value_field_name: str


@dataclass(frozen=True, slots=True)
class TimeSeriesData:
    time_values: tuple[datetime, ...]
    series: tuple[TimeSeriesLine, ...]
    time_field_name: str


@dataclass(frozen=True, slots=True)
class AreaSeriesLine:
    role: str
    values: tuple[float, ...]
    value_field_name: str


@dataclass(frozen=True, slots=True)
class AreaSeriesData:
    x_values: tuple[float, ...]
    series: tuple[AreaSeriesLine, ...]
    x_field_name: str


@dataclass(frozen=True, slots=True)
class RegularGridData:
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    z_values: tuple[tuple[float, ...], ...]
    x_field_name: str
    y_field_name: str
    z_field_name: str
    z_unit: str | None


@dataclass(frozen=True, slots=True)
class FacetSeriesData:
    label: str
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class FacetData:
    facet_field_name: str
    x_field_name: str
    y_field_name: str
    panels: tuple[FacetSeriesData, ...]


@dataclass(frozen=True, slots=True)
class NyquistSeriesData:
    label: str
    z_real: tuple[float, ...]
    z_imaginary: tuple[float, ...]
    frequency: tuple[float, ...] | None


@dataclass(frozen=True, slots=True)
class NyquistData:
    z_real_field_name: str
    z_imaginary_field_name: str
    series: tuple[NyquistSeriesData, ...]


def xy_series(document: PlotDocument, data: EngineDataView, *, profile_id: str) -> XYSeriesData:
    """Return one numeric X/Y series for a fixed-role profile."""

    columns = _bound_columns(document, data, ("x", "y"), profile_id)
    x, y = columns
    return XYSeriesData(
        x_values=_numeric_values(x, "x", profile_id),
        y_values=_numeric_values(y, "y", profile_id, allow_missing=True),
        x_field_name=x.field.name,
        y_field_name=y.field.name,
    )


def k06_point_error(document: PlotDocument, data: EngineDataView) -> PointErrorData:
    """Return the explicit asymmetric X/Y error magnitudes unchanged."""

    x, center, x_err_minus, x_err_plus, y_err_minus, y_err_plus = _bound_columns(
        document,
        data,
        ("x", "center", "x_err_minus", "x_err_plus", "y_err_minus", "y_err_plus"),
        "K06",
    )
    x_values = _numeric_values(x, "x", "K06")
    center_values = _numeric_values(center, "center", "K06", allow_missing=True)
    x_minus_errors = _numeric_values(x_err_minus, "x_err_minus", "K06", allow_missing=True)
    x_plus_errors = _numeric_values(x_err_plus, "x_err_plus", "K06", allow_missing=True)
    y_minus_errors = _numeric_values(y_err_minus, "y_err_minus", "K06", allow_missing=True)
    y_plus_errors = _numeric_values(y_err_plus, "y_err_plus", "K06", allow_missing=True)
    for row, values in enumerate(
        zip(
            center_values,
            x_minus_errors,
            x_plus_errors,
            y_minus_errors,
            y_plus_errors,
            strict=True,
        ),
        start=1,
    ):
        present = tuple(isfinite(value) for value in values)
        if any(present) and not all(present):
            raise ValueError(f"K06 row {row} must provide center and all four errors together")
        if all(present) and any(value < 0 for value in values[1:]):
            raise ValueError(f"K06 row {row} error magnitudes must be non-negative")
    return PointErrorData(
        x_values=x_values,
        center_values=center_values,
        x_minus_errors=x_minus_errors,
        x_plus_errors=x_plus_errors,
        y_minus_errors=y_minus_errors,
        y_plus_errors=y_plus_errors,
        x_field_name=x.field.name,
        center_field_name=center.field.name,
    )


def grouped_xy(
    document: PlotDocument,
    data: EngineDataView,
    *,
    profile_id: str,
) -> K03ScatterData:
    """Split an optional group field into stable first-appearance XY series."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        x = columns[bindings["x"]]
        y = columns[bindings["y"]]
    except KeyError as error:
        raise ValueError(f"{profile_id} requires x and y bindings") from error
    x_values = _numeric_values(x, "x", profile_id, allow_missing=True)
    y_values = _numeric_values(y, "y", profile_id, allow_missing=True)
    group_field_id = bindings.get("group")
    groups: tuple[ScatterGroupData, ...]
    if group_field_id is None:
        groups = (
            ScatterGroupData(
                label=y.field.name,
                x_values=x_values,
                y_values=y_values,
            ),
        )
    else:
        group = columns[group_field_id]
        ordered_labels = _ordered_labels(group, "group")
        grouped: list[ScatterGroupData] = []
        for label in ordered_labels:
            indexes = tuple(
                index for index, value in enumerate(group.values) if _label(value, "group") == label
            )
            grouped.append(
                ScatterGroupData(
                    label=label,
                    x_values=tuple(x_values[index] for index in indexes),
                    y_values=tuple(y_values[index] for index in indexes),
                )
            )
        groups = tuple(grouped)
    return K03ScatterData(
        groups=groups,
        x_field_name=x.field.name,
        y_field_name=y.field.name,
    )


def k03_scatter(document: PlotDocument, data: EngineDataView) -> K03ScatterData:
    return grouped_xy(document, data, profile_id="K03")


def k04_bubble(document: PlotDocument, data: EngineDataView) -> K04BubbleData:
    """Return the four native bubble dimensions without inventing a scale object.

    Binding a numeric color or size field controls point appearance.  It does
    not imply that either explanatory scale is visible; visibility remains an
    explicit public chart parameter in both backends.
    """

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        x = columns[bindings["x"]]
        y = columns[bindings["y"]]
    except KeyError as error:
        raise ValueError("K04 requires x and y bindings") from error
    size = columns[bindings["size"]] if "size" in bindings else None
    color = columns[bindings["color"]] if "color" in bindings else None
    size_values = None if size is None else _numeric_values(size, "size", "K04", allow_missing=True)
    if size_values is not None and not any(isfinite(value) for value in size_values):
        raise ValueError("K04 size binding requires at least one finite value")
    if size_values is not None and any(isfinite(value) and value < 0 for value in size_values):
        raise ValueError("K04 size values must be non-negative")
    color_values = (
        None if color is None else _numeric_values(color, "color", "K04", allow_missing=True)
    )
    if color_values is not None and not any(isfinite(value) for value in color_values):
        raise ValueError("K04 color binding requires at least one finite value")
    return K04BubbleData(
        x_values=_numeric_values(x, "x", "K04", allow_missing=True),
        y_values=_numeric_values(y, "y", "K04", allow_missing=True),
        size_values=size_values,
        color_values=color_values,
        x_field_name=x.field.name,
        y_field_name=y.field.name,
        size_field_name=None if size is None else size.field.name,
        color_field_name=None if color is None else color.field.name,
    )


def k07_error_band(document: PlotDocument, data: EngineDataView) -> ErrorBandData:
    """Validate one center curve and its lower/upper native band boundaries."""

    x, center, lower, upper = _bound_columns(
        document,
        data,
        ("x", "center", "lower", "upper"),
        "K07",
    )

    x_values = _numeric_values(x, "x", "K07")
    center_values = _numeric_values(center, "center", "K07", allow_missing=True)
    lower_values = _numeric_values(lower, "lower", "K07", allow_missing=True)
    upper_values = _numeric_values(upper, "upper", "K07", allow_missing=True)
    for row, (low, middle, high) in enumerate(
        zip(lower_values, center_values, upper_values, strict=True),
        start=1,
    ):
        present = tuple(isfinite(value) for value in (low, middle, high))
        if any(present) and not all(present):
            raise ValueError(f"K07 row {row} must provide center, lower and upper together")
        if all(present) and not low <= middle <= high:
            raise ValueError(f"K07 row {row} must satisfy lower <= center <= upper")
    return ErrorBandData(
        x_values=x_values,
        center_values=center_values,
        lower_values=lower_values,
        upper_values=upper_values,
        x_field_name=x.field.name,
        center_field_name=center.field.name,
    )


def category_series_grid(
    document: PlotDocument,
    data: EngineDataView,
    *,
    profile_id: Literal["K09", "K10", "K11"],
) -> CategorySeriesGrid:
    """Pivot a long categorical table without averaging duplicate cells.

    Category and series order follow first appearance.  Missing combinations
    stay NaN, while duplicate category/series cells fail closed instead of
    silently changing the user's data.
    """

    series_role = "group" if profile_id == "K09" else "component"
    category, series, value = _bound_columns(
        document,
        data,
        ("category", series_role, "value"),
        profile_id,
    )
    category_labels = _ordered_labels(category, "category")
    series_labels = _ordered_labels(series, series_role)
    category_index = {label: index for index, label in enumerate(category_labels)}
    series_index = {label: index for index, label in enumerate(series_labels)}
    matrix = [[nan for _ in series_labels] for _ in category_labels]
    occupied: set[tuple[int, int]] = set()
    for category_value, series_value, cell_value in zip(
        category.values,
        series.values,
        value.values,
        strict=True,
    ):
        category_label = _label(category_value, "category")
        series_label = _label(series_value, series_role)
        position = (category_index[category_label], series_index[series_label])
        if position in occupied:
            raise ValueError(
                f"{profile_id} contains a duplicate category/series cell: "
                f"{category_label!r}, {series_label!r}"
            )
        occupied.add(position)
        cell = _numeric_value(cell_value, profile_id, "value", allow_missing=True)
        matrix[position[0]][position[1]] = cell
    return CategorySeriesGrid(
        category_labels=category_labels,
        series_labels=series_labels,
        values=tuple(tuple(row) for row in matrix),
        category_field_name=category.field.name,
        value_field_name=value.field.name,
    )


def k09_grouped_indexed_data(
    document: PlotDocument,
    data: EngineDataView,
) -> GroupedIndexedData:
    """Preserve K09's long table for Origin's summarized-data graph.

    ``category_series_grid`` remains the shared validation authority for
    duplicate cells and first-appearance order.  This view deliberately does
    not pivot those cells: Origin receives Value as Y plus Category/Group as
    two native grouping columns, exactly as ``plot_gindexed`` expects.
    """

    grid = category_series_grid(document, data, profile_id="K09")
    category, group, value = _bound_columns(
        document,
        data,
        ("category", "group", "value"),
        "K09",
    )
    categories = tuple(_label(item, "category") for item in category.values)
    groups = tuple(_label(item, "group") for item in group.values)
    values = _numeric_values(value, "value", "K09", allow_missing=True)
    return GroupedIndexedData(
        indexes=tuple(range(1, len(values) + 1)),
        values=values,
        categories=categories,
        groups=groups,
        category_labels=grid.category_labels,
        group_labels=grid.series_labels,
        category_field_name=category.field.name,
        group_field_name=group.field.name,
        value_field_name=value.field.name,
    )


def distribution_groups(
    document: PlotDocument,
    data: EngineDataView,
    *,
    profile_id: Literal["K12", "K13", "K14", "K15", "X05"],
) -> DistributionData:
    """Return raw observations split by optional group in first-appearance order."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        value = columns[bindings["value"]]
    except KeyError as error:
        raise ValueError(f"{profile_id} requires a value binding") from error
    group_field_id = bindings.get("group")
    grouped: list[DistributionGroupData] = []
    if group_field_id is None:
        values = _finite_observations(value, profile_id)
        grouped.append(DistributionGroupData(label=value.field.name, values=values))
    else:
        group = columns[group_field_id]
        labels = _ordered_labels(group, "group")
        for label in labels:
            observations = tuple(
                cell
                for group_value, raw_value in zip(group.values, value.values, strict=True)
                if _label(group_value, "group") == label
                for cell in _optional_finite_observation(raw_value, profile_id)
            )
            if not observations:
                raise ValueError(f"{profile_id} group {label!r} has no finite observations")
            grouped.append(DistributionGroupData(label=label, values=observations))
    return DistributionData(groups=tuple(grouped), value_field_name=value.field.name)


def x09_floating_intervals(
    document: PlotDocument,
    data: EngineDataView,
) -> FloatingIntervalData:
    """Return ordered interval boundaries without deriving or sorting rows."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        category = columns[bindings["category"]]
        start = columns[bindings["start"]]
        end = columns[bindings["end"]]
    except KeyError as error:
        raise ValueError("X09 requires category, start and end bindings") from error
    middle = columns[bindings["middle"]] if "middle" in bindings else None
    categories = tuple(_label(value, "category") for value in category.values)
    start_values = _numeric_values(start, "start", "X09", allow_missing=False)
    end_values = _numeric_values(end, "end", "X09", allow_missing=False)
    middle_values = (
        None if middle is None else _numeric_values(middle, "middle", "X09", allow_missing=False)
    )
    return FloatingIntervalData(
        categories=categories,
        start_values=start_values,
        middle_values=middle_values,
        end_values=end_values,
        category_field_name=category.field.name,
        start_field_name=start.field.name,
        middle_field_name=None if middle is None else middle.field.name,
        end_field_name=end.field.name,
    )


def x13_population_pyramid(
    document: PlotDocument,
    data: EngineDataView,
) -> PopulationPyramidData:
    """Return positive magnitudes; each backend owns the native mirror convention."""

    category, left, right = _bound_columns(document, data, ("category", "left", "right"), "X13")
    categories = tuple(_label(value, "category") for value in category.values)
    if len(categories) != len(set(categories)):
        raise ValueError("X13 category labels must be unique")
    left_values = _numeric_values(left, "left", "X13", allow_missing=False)
    right_values = _numeric_values(right, "right", "X13", allow_missing=False)
    if any(value < 0 for value in (*left_values, *right_values)):
        raise ValueError("X13 population magnitudes must be non-negative")
    return PopulationPyramidData(
        categories=categories,
        left_values=left_values,
        right_values=right_values,
        category_field_name=category.field.name,
        left_field_name=left.field.name,
        right_field_name=right.field.name,
    )


def k15_histogram(document: PlotDocument, data: EngineDataView) -> HistogramData:
    """Calculate fixed bins once; both render targets consume these exact bins."""

    distribution = distribution_groups(document, data, profile_id="K15")
    if len(distribution.groups) != 1:
        raise ValueError("K15 accepts one value series")
    geometry = histogram_geometry(distribution.groups[0].values, normalization="count")
    return HistogramData(
        left=geometry.left,
        right=geometry.right,
        center=geometry.center,
        height=geometry.height,
        count=geometry.count,
        value_field_name=distribution.value_field_name,
        normalization="count",
        rule=geometry.rule,
    )


def x03_lollipop(document: PlotDocument, data: EngineDataView) -> LollipopData:
    """Return one category column plus a contiguous 2+ numeric series set."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        category = columns[bindings["category"]]
    except KeyError as error:
        raise ValueError("X03 requires a category binding") from error
    roles = _contiguous_series_roles(bindings, "X03", minimum=2)
    selected = tuple(columns[bindings[role]] for role in roles)
    categories = tuple(_label(value, "category") for value in category.values)
    if len(categories) != len(set(categories)):
        raise ValueError("X03 category labels must be unique")
    return LollipopData(
        categories=categories,
        columns=WideColumnData(
            labels=tuple(column.field.name for column in selected),
            values=tuple(
                _numeric_values(column, role, "X03", allow_missing=True)
                for role, column in zip(roles, selected, strict=True)
            ),
        ),
        category_field_name=category.field.name,
    )


def wide_series(
    document: PlotDocument,
    data: EngineDataView,
    *,
    profile_id: Literal["X39", "X40"],
) -> WideSeriesData:
    """Keep X39/X40 bound values in the official wide worksheet layout."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    roles = _contiguous_series_roles(bindings, profile_id, minimum=2)
    if profile_id == "X40" and len(roles) != 2:
        raise ValueError("X40 requires exactly two paired value columns")
    selected = tuple(columns[bindings[role]] for role in roles)
    column_values = tuple(
        _numeric_values(column, role, profile_id, allow_missing=False)
        for role, column in zip(roles, selected, strict=True)
    )
    return WideSeriesData(
        column_labels=tuple(column.field.name for column in selected),
        column_values=column_values,
        row_labels=(
            None
            if profile_id != "X40"
            else tuple(_label(value, "label") for value in columns[bindings["label"]].values)
        ),
        row_groups=(
            None
            if profile_id != "X40" or "group" not in bindings
            else tuple(_label(value, "group") for value in columns[bindings["group"]].values)
        ),
    )


def k19_time_series(document: PlotDocument, data: EngineDataView) -> TimeSeriesData:
    """Return native Date/Time lines from wide or explicitly grouped long data.

    A wide table binds one shared time field and one or more value fields.  A
    long table binds one value field plus ``group``; each group keeps its own
    observed timestamps so neither backend joins rows from different series or
    invents/interpolates missing observations.
    """

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    if "time" not in bindings:
        raise ValueError("K19 requires a time binding")
    roles = _contiguous_series_roles(bindings, "K19", minimum=1)
    time_column = columns[bindings["time"]]
    times = tuple(_datetime_value(value, "K19 time") for value in time_column.values)
    group_field_id = bindings.get("group")
    if group_field_id is not None:
        if len(roles) != 1:
            raise ValueError("K19 grouped long data requires exactly one bound series")
        value_column = columns[bindings[roles[0]]]
        values = _numeric_values(value_column, roles[0], "K19", allow_missing=True)
        group_column = columns[group_field_id]
        materialized: list[TimeSeriesLine] = []
        for ordinal, label in enumerate(_ordered_labels(group_column, "group"), start=1):
            indexes = tuple(
                index
                for index, raw_label in enumerate(group_column.values)
                if _label(raw_label, "group") == label
            )
            group_times = tuple(times[index] for index in indexes)
            if len(group_times) != len(set(group_times)):
                raise ValueError(f"K19 group {label!r} contains duplicate time values")
            materialized.append(
                TimeSeriesLine(
                    role=f"series_{ordinal}",
                    time_values=group_times,
                    values=tuple(values[index] for index in indexes),
                    value_field_name=label,
                )
            )
        if not materialized:
            raise ValueError("K19 grouped long data contains no groups")
        return TimeSeriesData(
            time_values=times,
            series=tuple(materialized),
            time_field_name=time_column.field.name,
        )
    return TimeSeriesData(
        time_values=times,
        series=tuple(
            TimeSeriesLine(
                role=role,
                time_values=times,
                values=_numeric_values(columns[bindings[role]], role, "K19", allow_missing=True),
                value_field_name=columns[bindings[role]].field.name,
            )
            for role in roles
        ),
        time_field_name=time_column.field.name,
    )


def k18_area_series(document: PlotDocument, data: EngineDataView) -> AreaSeriesData:
    """Return native area series from wide data or one explicitly grouped long series.

    Origin's Area graph and Matplotlib both consume one shared X column plus
    one Y column per area.  A long table therefore has to be pivoted before it
    reaches either backend; otherwise the last point of one group is joined to
    the first point of the next group.  The pivot is deliberately strict: each
    group must contain the same ordered X coordinates and duplicate X values
    within a group are rejected.
    """

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    if "x" not in bindings:
        raise ValueError("K18 requires an x binding")
    x_column = columns[bindings["x"]]
    roles = _contiguous_series_roles(bindings, "K18", minimum=1)
    x_values = _numeric_values(x_column, "x", "K18", allow_missing=False)
    group_field_id = bindings.get("group")
    if group_field_id is not None:
        if len(roles) != 1:
            raise ValueError("K18 grouped long data requires exactly one bound series")
        value_column = columns[bindings[roles[0]]]
        values = _numeric_values(value_column, roles[0], "K18", allow_missing=True)
        group_column = columns[group_field_id]
        labels = _ordered_labels(group_column, "group")
        grouped_series: list[AreaSeriesLine] = []
        shared_x: tuple[float, ...] | None = None
        for ordinal, label in enumerate(labels, start=1):
            indexes = tuple(
                index
                for index, raw_label in enumerate(group_column.values)
                if _label(raw_label, "group") == label
            )
            group_x = tuple(x_values[index] for index in indexes)
            if len(group_x) != len(set(group_x)):
                raise ValueError(f"K18 group {label!r} contains duplicate x values")
            if shared_x is None:
                shared_x = group_x
            elif group_x != shared_x:
                raise ValueError(
                    "K18 grouped long data requires identical ordered x values per group"
                )
            grouped_series.append(
                AreaSeriesLine(
                    role=f"series_{ordinal}",
                    values=tuple(values[index] for index in indexes),
                    value_field_name=label,
                )
            )
        if shared_x is None:
            raise ValueError("K18 grouped long data contains no groups")
        return AreaSeriesData(
            x_values=shared_x,
            series=tuple(grouped_series),
            x_field_name=x_column.field.name,
        )
    return AreaSeriesData(
        x_values=x_values,
        series=tuple(
            AreaSeriesLine(
                role=role,
                values=_numeric_values(columns[bindings[role]], role, "K18", allow_missing=True),
                value_field_name=columns[bindings[role]].field.name,
            )
            for role in roles
        ),
        x_field_name=x_column.field.name,
    )


def k21_correlation_grid(document: PlotDocument, data: EngineDataView) -> K20Grid:
    """Return a complete square matrix whose row and column variables agree."""

    grid = _long_matrix_grid(
        document,
        data,
        profile_id="K21",
        roles=("row_label", "column_label", "value"),
    )
    if set(grid.row_labels) != set(grid.column_labels):
        raise ValueError("K21 row and column variables must describe the same set")
    row_lookup = {label: row for label, row in zip(grid.row_labels, grid.values, strict=True)}
    column_positions = {label: index for index, label in enumerate(grid.column_labels)}
    reordered = tuple(
        tuple(
            row_lookup[row_label][column_positions[column_label]]
            for column_label in grid.column_labels
        )
        for row_label in grid.column_labels
    )
    if any(
        not isfinite(value) or value < -1.0 or value > 1.0 for row in reordered for value in row
    ):
        raise ValueError("K21 correlation values must be finite and within [-1, 1]")
    for index, row in enumerate(reordered):
        if not isclose(row[index], 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError("K21 correlation matrix diagonal must equal 1")
        for other in range(index):
            if not isclose(row[other], reordered[other][index], rel_tol=0, abs_tol=1e-12):
                raise ValueError("K21 correlation matrix must be symmetric")
    return K20Grid(
        row_labels=grid.column_labels,
        column_labels=grid.column_labels,
        values=reordered,
        row_field_name=grid.row_field_name,
        column_field_name=grid.column_field_name,
        value_field_name=grid.value_field_name,
        value_unit=grid.value_unit,
    )


def k22_regular_grid(document: PlotDocument, data: EngineDataView) -> RegularGridData:
    """Return one complete, non-interpolated regular XYZ grid."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        x_column = columns[bindings["x"]]
        y_column = columns[bindings["y"]]
        z_column = columns[bindings["z"]]
    except KeyError as error:
        raise ValueError("K22 requires x, y and z bindings") from error
    x_raw = _numeric_values(x_column, "x", "K22", allow_missing=False)
    y_raw = _numeric_values(y_column, "y", "K22", allow_missing=False)
    z_raw = _numeric_values(z_column, "z", "K22", allow_missing=False)
    x_values = tuple(sorted(set(x_raw)))
    y_values = tuple(sorted(set(y_raw)))
    if len(x_values) < 2 or len(y_values) < 2:
        raise ValueError("K22 requires at least a 2 by 2 regular grid")
    for axis_name, axis_values in (("x", x_values), ("y", y_values)):
        first_step = axis_values[1] - axis_values[0]
        tolerance = 1e-12 * max(1.0, abs(first_step))
        if any(
            not isclose(
                axis_values[index] - axis_values[index - 1],
                first_step,
                rel_tol=1e-12,
                abs_tol=tolerance,
            )
            for index in range(2, len(axis_values))
        ):
            raise ValueError(
                f"K22 {axis_name} coordinates must be evenly spaced for a matrix contour"
            )
    positions: dict[tuple[float, float], float] = {}
    for x_value, y_value, z_value in zip(x_raw, y_raw, z_raw, strict=True):
        key = (x_value, y_value)
        if key in positions:
            raise ValueError(f"K22 contains a duplicate grid cell: {key!r}")
        positions[key] = z_value
    missing = tuple(
        (x_value, y_value)
        for y_value in y_values
        for x_value in x_values
        if (x_value, y_value) not in positions
    )
    if missing:
        raise ValueError(
            "K22 requires a complete regular grid and never interpolates missing cells"
        )
    if isclose(min(z_raw), max(z_raw), rel_tol=0, abs_tol=1e-12):
        raise ValueError("K22 contour values must span more than one Z level")
    return RegularGridData(
        x_values=x_values,
        y_values=y_values,
        z_values=tuple(
            tuple(positions[(x_value, y_value)] for x_value in x_values) for y_value in y_values
        ),
        x_field_name=x_column.field.name,
        y_field_name=y_column.field.name,
        z_field_name=z_column.field.name,
        z_unit=z_column.field.unit_label,
    )


def k20_grid(document: PlotDocument, data: EngineDataView) -> K20Grid:
    """Materialize a deterministic K20 grid from one immutable long table.

    First appearance defines category order.  Duplicate cells are rejected
    rather than silently averaged.  Missing row/column combinations remain
    NaN so both backends distinguish missing values from numeric zero.
    """

    return _long_matrix_grid(
        document,
        data,
        profile_id="K20",
        roles=("row", "column", "value"),
    )


def _long_matrix_grid(
    document: PlotDocument,
    data: EngineDataView,
    *,
    profile_id: str,
    roles: tuple[str, str, str],
) -> K20Grid:
    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    row_role, column_role, value_role = roles
    try:
        row = columns[bindings[row_role]]
        column = columns[bindings[column_role]]
        value = columns[bindings[value_role]]
    except KeyError as error:
        raise ValueError(f"{profile_id} requires {', '.join(roles)} bindings") from error

    row_labels = _ordered_labels(row, row_role)
    column_labels = _ordered_labels(column, column_role)
    row_index = {label: index for index, label in enumerate(row_labels)}
    column_index = {label: index for index, label in enumerate(column_labels)}
    matrix = [[nan for _ in column_labels] for _ in row_labels]
    occupied: set[tuple[int, int]] = set()
    for row_value, column_value, cell_value in zip(
        row.values,
        column.values,
        value.values,
        strict=True,
    ):
        row_label = _label(row_value, row_role)
        column_label = _label(column_value, column_role)
        position = (row_index[row_label], column_index[column_label])
        if position in occupied:
            raise ValueError(
                f"{profile_id} contains a duplicate matrix cell: {row_label!r}, {column_label!r}"
            )
        occupied.add(position)
        matrix[position[0]][position[1]] = _numeric(cell_value)
    return K20Grid(
        row_labels=row_labels,
        column_labels=column_labels,
        values=tuple(tuple(row_values) for row_values in matrix),
        row_field_name=row.field.name,
        column_field_name=column.field.name,
        value_field_name=value.field.name,
        value_unit=value.field.unit_label,
    )


def x23_series(document: PlotDocument, data: EngineDataView) -> X23SeriesData:
    """Validate and normalize one dual-Y input without describing either backend."""

    return _dual_y_series(document, data, profile_id="X23", x_role="x")


def x35_series(document: PlotDocument, data: EngineDataView) -> X23SeriesData:
    """Return the categorical left/right values consumed by the dual-column profile."""

    return _dual_y_series(document, data, profile_id="X35", x_role="category")


def x36_series(document: PlotDocument, data: EngineDataView) -> X23SeriesData:
    """Return the categorical left-column/right-line values for the mixed profile."""

    return _dual_y_series(document, data, profile_id="X36", x_role="category")


def _dual_y_series(
    document: PlotDocument,
    data: EngineDataView,
    *,
    profile_id: Literal["X23", "X35", "X36"],
    x_role: Literal["x", "category"],
) -> X23SeriesData:
    """Normalize one dual-axis table while preserving its public role vocabulary."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        x = columns[bindings[x_role]]
        left = columns[bindings["left"]]
        right = columns[bindings["right"]]
    except KeyError as error:
        raise ValueError(f"{profile_id} requires {x_role}, left and right bindings") from error
    left_values = tuple(_numeric(value) for value in left.values)
    right_values = tuple(_numeric(value) for value in right.values)
    x_scale: Literal["categorical", "linear"]
    if x.field.logical_type in {"categorical", "text"}:
        labels = tuple(_label(value, "x") for value in x.values)
        if len(labels) != len(set(labels)):
            raise ValueError(f"{profile_id} categorical labels must be unique")
        x_values: tuple[str | float, ...] = labels
        x_scale = "categorical"
    elif x.field.logical_type == "numeric":
        labels = None
        numeric_x = tuple(_numeric(value) for value in x.values)
        if any(not isfinite(value) for value in numeric_x):
            raise ValueError(f"{profile_id} x values must be finite")
        x_values = numeric_x
        x_scale = "linear"
    else:
        raise ValueError(f"{profile_id} supports categorical or numeric x data")
    if profile_id in {"X35", "X36"} and x_scale != "categorical":
        raise ValueError(f"{profile_id} requires categorical data")
    return X23SeriesData(
        x_values=x_values,
        x_labels=labels,
        left_values=left_values,
        right_values=right_values,
        x_field_name=x.field.name,
        left_field_name=left.field.name,
        right_field_name=right.field.name,
        x_scale=x_scale,
    )


def x24_pareto(document: PlotDocument, data: EngineDataView) -> ParetoData:
    """Aggregate and sort contributions for the independent Matplotlib backend."""

    source = x24_pareto_source(document, data)
    aggregated: dict[str, float] = {}
    for label, value in zip(source.categories, source.values, strict=True):
        aggregated[label] = aggregated.get(label, 0.0) + value
    ordered = tuple(sorted(aggregated.items(), key=lambda item: item[1], reverse=True))
    ordered_labels = tuple(item[0] for item in ordered)
    ordered_values = tuple(item[1] for item in ordered)
    total = sum(ordered_values)
    running = 0.0
    cumulative: list[float] = []
    for item in ordered_values:
        running += item
        cumulative.append(running / total * 100.0)
    return ParetoData(
        categories=ordered_labels,
        values=ordered_values,
        cumulative_percent=tuple(cumulative),
        category_field_name=source.category_field_name,
        value_field_name=source.value_field_name,
    )


def x24_pareto_source(document: PlotDocument, data: EngineDataView) -> ParetoSourceData:
    """Preserve unsorted binned rows for Origin to aggregate, sort and cumulate."""

    category, value = _bound_columns(document, data, ("category", "value"), "X24")
    labels = tuple(_label(item, "category") for item in category.values)
    values = _numeric_values(value, "value", "X24", allow_missing=False)
    if any(item < 0 for item in values):
        raise ValueError("X24 contributions must be non-negative")
    if sum(values) <= 0:
        raise ValueError("X24 requires a positive total contribution")
    return ParetoSourceData(
        categories=labels,
        values=values,
        category_field_name=category.field.name,
        value_field_name=value.field.name,
    )


def x38_offset_stack(document: PlotDocument, data: EngineDataView) -> OffsetStackData:
    """Preserve Origin OffsetYs' canonical wide X + N Y worksheet layout."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        x = columns[bindings["x"]]
    except KeyError as error:
        raise ValueError("X38 requires an x binding") from error
    roles = _contiguous_series_roles(bindings, "X38", minimum=1)
    x_values = _numeric_values(x, "x", "X38", allow_missing=False)
    if len(x_values) < 2 or any(
        left >= right for left, right in zip(x_values[:-1], x_values[1:], strict=True)
    ):
        raise ValueError("X38 requires strictly increasing X values")
    materialized = [
        OffsetSeriesData(
            label=columns[bindings[role]].field.name,
            x_values=x_values,
            y_values=_numeric_values(columns[bindings[role]], role, "X38", allow_missing=True),
        )
        for role in roles
    ]
    return OffsetStackData(
        series=tuple(materialized),
        x_field_name=x.field.name,
        y_field_name="Value",
        series_field_name="Series",
    )


def k24_facets(document: PlotDocument, data: EngineDataView) -> FacetData:
    trellis = k24_trellis_data(document, data)
    panels: list[FacetSeriesData] = []
    for label in trellis.facet_labels:
        indexes = tuple(index for index, value in enumerate(trellis.facet_values) if value == label)
        panels.append(
            FacetSeriesData(
                label=label,
                x_values=tuple(trellis.x_values[index] for index in indexes),
                y_values=tuple(trellis.y_values[index] for index in indexes),
            )
        )
    return FacetData(
        facet_field_name=trellis.facet_field_name,
        x_field_name=trellis.x_field_name,
        y_field_name=trellis.y_field_name,
        panels=tuple(panels),
    )


def k24_trellis_data(document: PlotDocument, data: EngineDataView) -> TrellisData:
    """Preserve K24's long rows for Origin's official Trellis workflow."""

    facet, x, y = _bound_columns(document, data, ("facet", "base_x", "base_y"), "K24")
    facet_values = tuple(_label(item, "facet") for item in facet.values)
    x_values = _numeric_values(x, "base_x", "K24", allow_missing=False)
    y_values = _numeric_values(y, "base_y", "K24", allow_missing=True)
    facet_labels = tuple(dict.fromkeys(facet_values))
    for label in facet_labels:
        if sum(value == label for value in facet_values) < 2:
            raise ValueError("K24 requires at least two observations in every facet")
    return TrellisData(
        x_values=x_values,
        y_values=y_values,
        facet_values=facet_values,
        facet_labels=facet_labels,
        facet_field_name=facet.field.name,
        x_field_name=x.field.name,
        y_field_name=y.field.name,
    )


def s34_nyquist(document: PlotDocument, data: EngineDataView) -> NyquistData:
    real_column, imaginary_column = _bound_columns(document, data, ("z_real", "z_imaginary"), "S34")
    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    frequency_column = columns.get(bindings.get("frequency", ""))
    series_column = columns.get(bindings.get("series", ""))
    real = _numeric_values(real_column, "z_real", "S34", allow_missing=False)
    imaginary = _numeric_values(imaginary_column, "z_imaginary", "S34", allow_missing=False)
    frequency = (
        _numeric_values(frequency_column, "frequency", "S34", allow_missing=False)
        if frequency_column is not None
        else None
    )
    if frequency is not None and any(value <= 0 for value in frequency):
        raise ValueError("S34 frequency values must be positive")
    labels = (
        tuple(_label(value, "series") for value in series_column.values)
        if series_column is not None
        else tuple("Nyquist" for _value in real)
    )
    materialized: list[NyquistSeriesData] = []
    for label in dict.fromkeys(labels):
        indexes = tuple(index for index, value in enumerate(labels) if value == label)
        if len(indexes) < 2:
            raise ValueError("S34 requires at least two points in every series")
        materialized.append(
            NyquistSeriesData(
                label=label,
                z_real=tuple(real[index] for index in indexes),
                z_imaginary=tuple(imaginary[index] for index in indexes),
                frequency=(
                    tuple(frequency[index] for index in indexes) if frequency is not None else None
                ),
            )
        )
    return NyquistData(
        z_real_field_name=real_column.field.name,
        z_imaginary_field_name=imaginary_column.field.name,
        series=tuple(materialized),
    )


def s61_confusion_grid(document: PlotDocument, data: EngineDataView) -> K20Grid:
    actual_column, predicted_column = _bound_columns(document, data, ("actual", "predicted"), "S61")
    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    count_column = columns.get(bindings.get("count", ""))
    actual = tuple(_label(value, "actual") for value in actual_column.values)
    predicted = tuple(_label(value, "predicted") for value in predicted_column.values)
    row_labels = tuple(dict.fromkeys(actual))
    column_labels = tuple(dict.fromkeys(predicted))
    matrix = [[0.0 for _column in column_labels] for _row in row_labels]
    for index, (row_label, column_label) in enumerate(zip(actual, predicted, strict=True)):
        count = 1.0
        if count_column is not None:
            raw = count_column.values[index]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError("S61 count values must be non-negative integers")
            count = float(raw)
            if not isfinite(count) or count < 0 or not count.is_integer():
                raise ValueError("S61 count values must be non-negative integers")
        matrix[row_labels.index(row_label)][column_labels.index(column_label)] += count
    return K20Grid(
        row_labels=row_labels,
        column_labels=column_labels,
        values=tuple(tuple(row) for row in matrix),
        row_field_name=actual_column.field.name,
        column_field_name=predicted_column.field.name,
        value_field_name=count_column.field.name if count_column is not None else "Count",
        value_unit=None,
    )


def _ordered_labels(column: EngineColumn, role: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_label(value, role) for value in column.values))


def _contiguous_series_roles(
    bindings: dict[str, str],
    profile_id: str,
    *,
    minimum: int,
) -> tuple[str, ...]:
    indexed: list[tuple[int, str]] = []
    for role in bindings:
        prefix, separator, suffix = role.rpartition("_")
        if prefix != "series" or separator != "_" or not suffix.isdigit():
            continue
        indexed.append((int(suffix), role))
    indexed.sort()
    ordinals = tuple(index for index, _role in indexed)
    expected = tuple(range(1, len(indexed) + 1))
    if len(indexed) < minimum or ordinals != expected:
        raise ValueError(
            f"{profile_id} requires contiguous series_1..series_N bindings with N >= {minimum}"
        )
    return tuple(role for _index, role in indexed)


def _label(value: object, role: str) -> str:
    if value is None:
        raise ValueError(f"{role} categories cannot be missing")
    label = str(value).strip()
    if not label:
        raise ValueError(f"{role} categories cannot be empty")
    return label


def _datetime_value(value: object, role: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{role} values must be ISO date/time values") from error
    elif not isinstance(value, datetime):
        raise ValueError(f"{role} values must be date/time values")
    if parsed.tzinfo is not None:
        raise ValueError(f"{role} values must not contain a timezone offset")
    if parsed.microsecond % 1_000:
        raise ValueError(f"{role} values must use millisecond precision or coarser")
    return parsed


def _numeric(value: object) -> float:
    if value is None:
        return nan
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("K20 value data must be numeric")
    return float(value)


def _numeric_value(
    value: object,
    profile_id: str,
    role: str,
    *,
    allow_missing: bool = False,
) -> float:
    if value is None and allow_missing:
        return nan
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{profile_id} {role} values must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{profile_id} {role} values must be finite")
    return number


def _optional_finite_observation(value: object, profile_id: str) -> tuple[float, ...]:
    if value is None:
        return ()
    return (_numeric_value(value, profile_id, "value"),)


def _finite_observations(column: EngineColumn, profile_id: str) -> tuple[float, ...]:
    values = tuple(
        number
        for raw_value in column.values
        for number in _optional_finite_observation(raw_value, profile_id)
    )
    if not values:
        raise ValueError(f"{profile_id} requires at least one finite observation")
    return values


def _bound_columns(
    document: PlotDocument,
    data: EngineDataView,
    roles: tuple[str, ...],
    profile_id: str,
) -> tuple[EngineColumn, ...]:
    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        return tuple(columns[bindings[role]] for role in roles)
    except KeyError as error:
        raise ValueError(f"{profile_id} requires bindings: {', '.join(roles)}") from error


def _numeric_values(
    column: EngineColumn,
    role: str,
    profile_id: str,
    *,
    allow_missing: bool = False,
) -> tuple[float, ...]:
    values: list[float] = []
    for value in column.values:
        if value is None and allow_missing:
            values.append(nan)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{profile_id} {role} values must be numeric")
        number = float(value)
        if not isfinite(number):
            raise ValueError(f"{profile_id} {role} values must be finite")
        values.append(number)
    return tuple(values)

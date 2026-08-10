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

from plotagent.plot_calculations.kernels import histogram_geometry, scott_kde_geometry

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
    x_errors: tuple[float, ...]
    y_errors: tuple[float, ...]
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
class DistributionGroupData:
    label: str
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class DistributionData:
    groups: tuple[DistributionGroupData, ...]
    value_field_name: str


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
class DensitySeriesData:
    label: str
    grid: tuple[float, ...]
    density: tuple[float, ...]
    bandwidth: float


@dataclass(frozen=True, slots=True)
class DensityData:
    series: tuple[DensitySeriesData, ...]
    value_field_name: str


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
class TransposedSeriesData:
    axis_labels: tuple[str, ...]
    rows: tuple[tuple[float, ...], ...]
    row_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TimeSeriesData:
    time_values: tuple[datetime, ...]
    values: tuple[float, ...]
    time_field_name: str
    value_field_name: str


@dataclass(frozen=True, slots=True)
class RegularGridData:
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    z_values: tuple[tuple[float, ...], ...]
    x_field_name: str
    y_field_name: str
    z_field_name: str
    z_unit: str | None


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
    """Validate the symmetric X/Y error representation consumed by ERRBAR."""

    x, center, x_error, y_error = _bound_columns(
        document,
        data,
        ("x", "center", "x_error", "y_error"),
        "K06",
    )
    center_values = _numeric_values(center, "center", "K06", allow_missing=True)
    x_errors = _numeric_values(x_error, "x_error", "K06", allow_missing=True)
    y_errors = _numeric_values(y_error, "y_error", "K06", allow_missing=True)
    if any(isfinite(value) and value < 0 for value in x_errors + y_errors):
        raise ValueError("K06 error magnitudes must be non-negative")
    for row, values in enumerate(zip(center_values, x_errors, y_errors, strict=True), start=1):
        present = tuple(isfinite(value) for value in values)
        if any(present) and not all(present):
            raise ValueError(f"K06 row {row} must provide center and both errors together")
    return PointErrorData(
        x_values=_numeric_values(x, "x", "K06"),
        center_values=center_values,
        x_errors=x_errors,
        y_errors=y_errors,
        x_field_name=x.field.name,
        center_field_name=center.field.name,
    )


def k03_scatter(document: PlotDocument, data: EngineDataView) -> K03ScatterData:
    """Split one optional group field into stable first-appearance series."""

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        x = columns[bindings["x"]]
        y = columns[bindings["y"]]
    except KeyError as error:
        raise ValueError("K03 requires x and y bindings") from error
    x_values = _numeric_values(x, "x", "K03", allow_missing=True)
    y_values = _numeric_values(y, "y", "K03", allow_missing=True)
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


def distribution_groups(
    document: PlotDocument,
    data: EngineDataView,
    *,
    profile_id: Literal["K12", "K13", "K14", "K15", "K16"],
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


def k16_density(document: PlotDocument, data: EngineDataView) -> DensityData:
    """Calculate the frozen Scott KDE over raw observations and optional groups."""

    distribution = distribution_groups(document, data, profile_id="K16")
    series: list[DensitySeriesData] = []
    for index, group in enumerate(distribution.groups, start=1):
        try:
            geometry = scott_kde_geometry(group.values)
        except ValueError as error:
            raise ValueError(f"K16 group {index} cannot produce a density: {error}") from error
        series.append(
            DensitySeriesData(
                label=group.label,
                grid=geometry.grid,
                density=geometry.density,
                bandwidth=geometry.bandwidth,
            )
        )
    return DensityData(series=tuple(series), value_field_name=distribution.value_field_name)


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


def transposed_series(
    document: PlotDocument,
    data: EngineDataView,
    *,
    profile_id: Literal["X39", "X40"],
) -> TransposedSeriesData:
    """Transpose bound numeric columns so each source row becomes one native series."""

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
    rows = tuple(
        tuple(values[index] for values in column_values) for index in range(len(data.row_ids))
    )
    return TransposedSeriesData(
        axis_labels=tuple(column.field.name for column in selected),
        rows=rows,
        row_labels=tuple(f"Row {index}" for index in range(1, len(rows) + 1)),
    )


def k19_time_series(document: PlotDocument, data: EngineDataView) -> TimeSeriesData:
    """Return strictly increasing timestamps and their numeric observations."""

    time_column, value_column = _bound_columns(document, data, ("time", "value"), "K19")
    times = tuple(_datetime_value(value, "K19 time") for value in time_column.values)
    if any(left >= right for left, right in zip(times[:-1], times[1:], strict=True)):
        raise ValueError("K19 time values must be strictly increasing")
    return TimeSeriesData(
        time_values=times,
        values=_numeric_values(value_column, "value", "K19", allow_missing=True),
        time_field_name=time_column.field.name,
        value_field_name=value_column.field.name,
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
        not isfinite(value) or value < -1.0 or value > 1.0
        for row in reordered
        for value in row
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
    return RegularGridData(
        x_values=x_values,
        y_values=y_values,
        z_values=tuple(
            tuple(positions[(x_value, y_value)] for x_value in x_values)
            for y_value in y_values
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

    bindings = {binding.role: binding.field_id for binding in document.bindings}
    columns = {column.field.field_id: column for column in data.columns}
    try:
        x = columns[bindings["x"]]
        left = columns[bindings["left"]]
        right = columns[bindings["right"]]
    except KeyError as error:
        raise ValueError("X23 requires x, left and right bindings") from error
    left_values = tuple(_numeric(value) for value in left.values)
    right_values = tuple(_numeric(value) for value in right.values)
    x_scale: Literal["categorical", "linear"]
    if x.field.logical_type in {"categorical", "text"}:
        labels = tuple(_label(value, "x") for value in x.values)
        if len(labels) != len(set(labels)):
            raise ValueError("X23 categorical x labels must be unique")
        x_values: tuple[str | float, ...] = labels
        x_scale = "categorical"
    elif x.field.logical_type == "numeric":
        labels = None
        numeric_x = tuple(_numeric(value) for value in x.values)
        if any(not isfinite(value) for value in numeric_x):
            raise ValueError("X23 x values must be finite")
        x_values = numeric_x
        x_scale = "linear"
    else:
        raise ValueError("X23 currently supports categorical or numeric x data")
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
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{role} values must be ISO date/time values") from error
        return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
    raise ValueError(f"{role} values must be date/time values")


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

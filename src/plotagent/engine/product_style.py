"""Auditable product defaults shared by plotting backends.

Profile renderers own geometry and may declare a necessary exception.  These
values are the product fallback when neither the profile nor an explicit user
action supplies a style.  Keeping them in one module avoids silently inheriting
unrelated Matplotlib and Origin template defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class ProductTypography:
    title_font_size_pt: float
    axis_title_font_size_pt: float
    tick_font_size_pt: float
    legend_font_size_pt: float

    def matplotlib_rc(self) -> dict[str, float]:
        return {
            "axes.titlesize": self.title_font_size_pt,
            "axes.labelsize": self.axis_title_font_size_pt,
            "xtick.labelsize": self.tick_font_size_pt,
            "ytick.labelsize": self.tick_font_size_pt,
            "legend.fontsize": self.legend_font_size_pt,
            "legend.title_fontsize": self.legend_font_size_pt,
        }


PRODUCT_TYPOGRAPHY = ProductTypography(
    title_font_size_pt=10.0,
    axis_title_font_size_pt=9.0,
    tick_font_size_pt=8.0,
    legend_font_size_pt=8.0,
)

# X35/X36 expose two semantic series across independent Y axes.  Their default
# colors are part of the product contract, not backend-local suggestions: a
# request without SetSeriesStyle must render the same two colors in the preview
# and the editable Origin project.
DUAL_Y_SERIES_COLORS = ("#1676D2", "#D97800")

# Other multi-series renderers may reuse the same ordered product palette while
# retaining profile-specific geometry and explicit user overrides.
PRODUCT_SERIES_PALETTE = (
    *DUAL_Y_SERIES_COLORS,
    "#299764",
    "#C53D4D",
    "#7656B5",
    "#008A99",
    "#A55A2A",
    "#667085",
)


@dataclass(frozen=True, slots=True)
class K06PointErrorStyle:
    """Shared zero-edit presentation for one bidirectional point-error series."""

    color: str
    marker_shape: str
    marker_size_pt: float
    error_width_pt: float
    cap_size_pt: float
    legend_visible: bool


K06_POINT_ERROR_STYLE = K06PointErrorStyle(
    color=PRODUCT_SERIES_PALETTE[0],
    marker_shape="circle",
    marker_size_pt=5.0,
    error_width_pt=1.25,
    cap_size_pt=4.0,
    legend_visible=False,
)


@dataclass(frozen=True, slots=True)
class K07ErrorRibbonStyle:
    """Shared zero-edit presentation for one center line and error ribbon."""

    color: str
    line_width_pt: float
    line_style: str
    band_fill_opacity: float
    band_stroke_width_pt: float
    legend_visible: bool
    auto_range_margin_percent: float


K07_ERROR_RIBBON_STYLE = K07ErrorRibbonStyle(
    color=PRODUCT_SERIES_PALETTE[0],
    line_width_pt=1.5,
    line_style="solid",
    band_fill_opacity=0.25,
    band_stroke_width_pt=1.0,
    legend_visible=False,
    auto_range_margin_percent=5.0,
)


def k07_auto_range_bounds(
    x_values: tuple[float, ...],
    lower_values: tuple[float, ...],
    upper_values: tuple[float, ...],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return backend-neutral linear bounds for one K07 error ribbon.

    The visible Y extent is defined by the lower and upper boundaries, not by
    the center curve. Missing K07 rows are allowed by the data contract, so
    only finite boundary values participate in the product auto range.
    """

    def bounds(values: tuple[float, ...], *, axis: str) -> tuple[float, float]:
        finite_values = tuple(value for value in values if isfinite(value))
        if not finite_values:
            raise ValueError(f"K07 auto range requires finite {axis} values")
        minimum = min(finite_values)
        maximum = max(finite_values)
        span = maximum - minimum
        margin = (
            span * K07_ERROR_RIBBON_STYLE.auto_range_margin_percent / 100.0
            if span > 0.0
            else max(abs(minimum) * 0.05, 1.0)
        )
        return minimum - margin, maximum + margin

    return (
        bounds(x_values, axis="X"),
        bounds((*lower_values, *upper_values), axis="Y boundary"),
    )


# K01 uses Matplotlib's five-percent data margin as its product auto-range
# semantic.  Origin's official LINE template defaults to eight percent and
# rounds 0..1400 to -200..1600, exposing an extra major tick that the preview
# does not show.  Persisting the same five-percent intent keeps each backend's
# native tick locator while aligning the visible outer ticks.
K01_AUTO_RANGE_MARGIN_PERCENT = 5.0


@dataclass(frozen=True, slots=True)
class K09GroupedColumnStyle:
    """Renderer-neutral defaults for Origin's indexed grouped columns.

    Both gaps use Origin's public percentage semantics. ``within_group`` is
    the empty distance between adjacent bars expressed as a percentage of bar
    width; ``between_group`` is the fraction of one category step reserved
    between adjacent category groups. The remaining category width is divided
    equally between the series.
    """

    bar_border_visible: bool
    within_group_gap_percent: float
    between_group_gap_percent: float
    border_color: str
    border_width_pt: float


K09_GROUPED_COLUMN_STYLE = K09GroupedColumnStyle(
    bar_border_visible=False,
    within_group_gap_percent=20.0,
    between_group_gap_percent=20.0,
    border_color="#1A1A1A",
    border_width_pt=0.8,
)


@dataclass(frozen=True, slots=True)
class K14ViolinStyle:
    """Shared zero-edit presentation for native violin distributions."""

    palette: tuple[str, ...]
    fill_opacity: float
    outline_color: str
    outline_width_pt: float
    outline_style: str
    median_visible: bool
    legend_visible: bool
    auto_range_margin_percent: float


K14_VIOLIN_STYLE = K14ViolinStyle(
    palette=PRODUCT_SERIES_PALETTE,
    fill_opacity=0.75,
    outline_color="#1A1A1A",
    outline_width_pt=1.5,
    outline_style="solid",
    median_visible=False,
    legend_visible=False,
    auto_range_margin_percent=5.0,
)


@dataclass(frozen=True, slots=True)
class K22FilledContourStyle:
    """Shared zero-edit presentation for a regular-grid filled contour."""

    palette: str
    reverse: bool
    contour_lines_visible: bool
    colorbar_visible: bool
    colorbar_anchor: str
    colorbar_tick_format: str
    colorbar_title_font_size_pt: float
    colorbar_tick_font_size_pt: float


K22_FILLED_CONTOUR_STYLE = K22FilledContourStyle(
    palette="viridis",
    reverse=False,
    contour_lines_visible=False,
    colorbar_visible=True,
    colorbar_anchor="right",
    colorbar_tick_format="auto",
    colorbar_title_font_size_pt=PRODUCT_TYPOGRAPHY.axis_title_font_size_pt,
    colorbar_tick_font_size_pt=PRODUCT_TYPOGRAPHY.tick_font_size_pt,
)


def k14_auto_range_bounds(
    values: tuple[float, ...],
    group_count: int,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return fixed category and value bounds for a K14 violin plot."""

    if group_count < 1:
        raise ValueError("K14 auto range requires at least one group")
    finite_values = tuple(value for value in values if isfinite(value))
    if not finite_values:
        raise ValueError("K14 auto range requires finite values")
    minimum = min(finite_values)
    maximum = max(finite_values)
    span = maximum - minimum
    margin = (
        span * K14_VIOLIN_STYLE.auto_range_margin_percent / 100.0
        if span > 0.0
        else max(abs(minimum) * 0.05, 1.0)
    )
    return (0.5, group_count + 0.5), (minimum - margin, maximum + margin)


@dataclass(frozen=True, slots=True)
class X09FloatingColumnStyle:
    """Shared zero-edit presentation for adjacent floating intervals."""

    interval_colors: tuple[str, str]
    bar_width_fraction: float
    border_color: str
    border_width_pt: float
    legend_visible: bool
    auto_range_margin_percent: float


X09_FLOATING_COLUMN_STYLE = X09FloatingColumnStyle(
    interval_colors=(PRODUCT_SERIES_PALETTE[0], PRODUCT_SERIES_PALETTE[1]),
    bar_width_fraction=0.8,
    border_color="#1A1A1A",
    border_width_pt=0.8,
    legend_visible=True,
    auto_range_margin_percent=5.0,
)


def x09_auto_range_bounds(
    columns: tuple[tuple[float, ...], ...],
) -> tuple[float, float]:
    """Return one backend-neutral linear Y range for floating boundaries."""

    values = tuple(value for column in columns for value in column)
    if not values or any(not isfinite(value) for value in values):
        raise ValueError("X09 auto range requires finite boundary values")
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum
    margin = (
        span * X09_FLOATING_COLUMN_STYLE.auto_range_margin_percent / 100.0
        if span > 0.0
        else max(abs(minimum) * 0.05, 1.0)
    )
    return minimum - margin, maximum + margin


@dataclass(frozen=True, slots=True)
class X40BeforeAfterStyle:
    """Paper-backed product defaults for paired before/after observations."""

    before_color: str
    before_marker_shape: str
    after_color: str
    after_marker_shape: str
    marker_size_pt: float
    connector_color: str
    connector_width_pt: float
    legend_visible: bool
    identity_labels_visible: bool
    x_axis_title_visible: bool
    y_axis_label: str
    auto_range_margin_percent: float


X40_BEFORE_AFTER_STYLE = X40BeforeAfterStyle(
    before_color="#BDBDBD",
    before_marker_shape="square",
    after_color="#D95B67",
    after_marker_shape="circle",
    marker_size_pt=6.0,
    connector_color="#000000",
    connector_width_pt=1.0,
    legend_visible=False,
    identity_labels_visible=False,
    x_axis_title_visible=False,
    y_axis_label="Value",
    auto_range_margin_percent=5.0,
)


def x40_auto_range_bounds(
    columns: tuple[tuple[float, ...], ...],
) -> tuple[float, float]:
    """Return one backend-neutral linear Y range for paired observations."""

    values = tuple(value for column in columns for value in column)
    if not values or any(not isfinite(value) for value in values):
        raise ValueError("X40 auto range requires finite paired values")
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum
    margin = (
        span * X40_BEFORE_AFTER_STYLE.auto_range_margin_percent / 100.0
        if span > 0.0
        else max(abs(minimum) * 0.05, 1.0)
    )
    return minimum - margin, maximum + margin

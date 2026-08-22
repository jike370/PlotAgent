"""Closed T1 engine profile catalog.

Every profile is built directly from the final renderer-neutral capability
vocabulary. There is no legacy capability translation, alias or migration
layer.
"""

from __future__ import annotations

from typing import Any

from .contracts import EngineCapability, EngineProfile

_NUMERIC = ("numeric",)
_CATEGORY = ("categorical", "text", "numeric", "boolean")
_X_GENERAL = ("numeric", "categorical", "datetime", "text")

# Renderer input types are a reviewed product contract, not a runtime guess.
# Repeatable entries such as ``series`` apply to series_1, series_2, ... .
_ROLE_FIELD_TYPES: dict[str, dict[str, tuple[str, ...]]] = {
    "K01": {"x": _X_GENERAL, "y": _NUMERIC, "group": _CATEGORY},
    "K02": {"x": _X_GENERAL, "y": _NUMERIC, "group": _CATEGORY},
    "K03": {"x": _NUMERIC, "y": _NUMERIC, "group": _CATEGORY},
    "K04": {"x": _NUMERIC, "y": _NUMERIC, "size": _NUMERIC, "color": _NUMERIC},
    "K06": {
        "x": _NUMERIC,
        "center": _NUMERIC,
        "x_err_minus": _NUMERIC,
        "x_err_plus": _NUMERIC,
        "y_err_minus": _NUMERIC,
        "y_err_plus": _NUMERIC,
        "group": _CATEGORY,
    },
    "K07": {
        "x": _NUMERIC,
        "center": _NUMERIC,
        "lower": _NUMERIC,
        "upper": _NUMERIC,
        "group": _CATEGORY,
    },
    "K08": {"category": _CATEGORY, "value": _NUMERIC, "label": _CATEGORY},
    "K09": {"category": _CATEGORY, "group": _CATEGORY, "value": _NUMERIC},
    "K10": {"category": _CATEGORY, "component": _CATEGORY, "value": _NUMERIC},
    "K11": {"category": _CATEGORY, "component": _CATEGORY, "value": _NUMERIC},
    "K12": {"value": _NUMERIC, "group": _CATEGORY},
    "K13": {"value": _NUMERIC, "group": _CATEGORY},
    "K14": {"value": _NUMERIC, "group": _CATEGORY},
    "K15": {"value": _NUMERIC},
    "K18": {"x": _X_GENERAL, "series_1": _NUMERIC, "series": _NUMERIC, "group": _CATEGORY},
    "K19": {"time": ("datetime",), "series_1": _NUMERIC, "series": _NUMERIC, "group": _CATEGORY},
    "K20": {"row": _CATEGORY, "column": _CATEGORY, "value": _NUMERIC},
    "K21": {"row_label": _CATEGORY, "column_label": _CATEGORY, "value": _NUMERIC},
    "K22": {"x": _NUMERIC, "y": _NUMERIC, "z": _NUMERIC},
    "K24": {"facet": _CATEGORY, "base_x": _NUMERIC, "base_y": _NUMERIC},
    "S34": {
        "z_real": _NUMERIC,
        "z_imaginary": _NUMERIC,
        "frequency": _NUMERIC,
        "series": _CATEGORY,
    },
    "S61": {"actual": _CATEGORY, "predicted": _CATEGORY, "count": _NUMERIC},
    "X02": {"x": _X_GENERAL, "y": _NUMERIC, "label": _CATEGORY},
    "X03": {"category": _CATEGORY, "series_1": _NUMERIC, "series_2": _NUMERIC, "series": _NUMERIC},
    "X05": {"value": _NUMERIC, "group": _CATEGORY},
    "X09": {"category": _CATEGORY, "start": _NUMERIC, "end": _NUMERIC, "middle": _NUMERIC},
    "X13": {"category": _CATEGORY, "left": _NUMERIC, "right": _NUMERIC},
    "X23": {"x": _X_GENERAL, "left": _NUMERIC, "right": _NUMERIC},
    "X24": {"category": _CATEGORY, "value": _NUMERIC},
    "X35": {"category": _CATEGORY, "left": _NUMERIC, "right": _NUMERIC},
    "X36": {"category": _CATEGORY, "left": _NUMERIC, "right": _NUMERIC},
    "X38": {"x": _X_GENERAL, "series_1": _NUMERIC, "series": _NUMERIC},
    "X39": {"series_1": _NUMERIC, "series_2": _NUMERIC, "series": _NUMERIC},
    "X40": {"label": _CATEGORY, "series_1": _NUMERIC, "series_2": _NUMERIC, "group": _CATEGORY},
}

_TITLE_T1 = ("text", "font_family", "font_size_pt", "font_weight", "italic", "color")
_AXIS_T1 = (
    "title_font_family",
    "title_font_size_pt",
    "title_font_weight",
    "title_italic",
    "title_color",
    "major_tick_step",
    "minor_tick_count",
    "tick_format",
    "tick_rotation_deg",
    "tick_font_family",
    "tick_font_size_pt",
    "tick_color",
    "tick_labels_visible",
    "major_ticks_visible",
    "minor_ticks_visible",
    "tick_direction",
    "axis_line_visible",
    "axis_title_visible",
    "axis_line_color",
    "axis_line_width_pt",
    "major_grid_visible",
    "minor_grid_visible",
    "grid_color",
    "grid_line_width_pt",
    "grid_line_style",
)
_LEGEND_T1 = (
    "visible",
    "anchor",
    "columns",
    "title",
    "font_family",
    "font_size_pt",
    "font_color",
    "frame_visible",
    "frame_color",
    "frame_width_pt",
)
_COLORMAP_T1 = (
    "palette",
    "reverse",
    "minimum",
    "maximum",
    "midpoint",
    "mode",
    "levels",
    "missing_color",
    "colorbar_visible",
    "colorbar_anchor",
    "colorbar_title",
    "colorbar_tick_format",
)
_ERROR_BAR_T1 = (
    "bar_color",
    "bar_width_pt",
    "cap_size_pt",
    "bar_opacity",
)
_ERROR_BAND_T1 = (
    "band_fill_color",
    "band_fill_opacity",
    "band_stroke_color",
    "band_stroke_width_pt",
)
_LABEL_T1 = (
    "visible",
    "value_format",
    "prefix",
    "suffix",
    "position",
    "rotation_deg",
    "font_family",
    "font_size_pt",
    "font_weight",
    "font_color",
)

# OriginPro 2024 persists one transparency value for mixed primitives such as
# line+symbol or fill+border plots.  Per-element opacity is therefore declared
# only when the semantic target is a single native primitive (or a distinct
# native plot object), so both backends preserve the same public meaning.


def _capabilities(
    *,
    axis: tuple[str, ...],
    series: tuple[str, ...],
    legend: bool,
    colormap: bool,
    error: tuple[str, ...],
    labels: bool,
    chart: tuple[str, ...],
) -> tuple[EngineCapability, ...]:
    result = [
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=_TITLE_T1),
        EngineCapability(operation="set_axis", parameters=tuple(dict.fromkeys(axis + _AXIS_T1))),
    ]
    if series:
        result.append(EngineCapability(operation="set_series_style", parameters=series))
    if legend:
        result.append(EngineCapability(operation="set_legend", parameters=_LEGEND_T1))
    if colormap:
        result.append(EngineCapability(operation="set_colormap", parameters=_COLORMAP_T1))
    if error:
        result.append(EngineCapability(operation="set_error_style", parameters=error))
    if labels:
        result.append(EngineCapability(operation="set_data_labels", parameters=_LABEL_T1))
    if chart:
        result.append(EngineCapability(operation="set_chart_parameter", parameters=chart))
    result.append(EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")))
    return tuple(result)


def _profile(
    data: dict[str, Any],
    *,
    axis: tuple[str, ...] = ("label", "scale", "bounds", "reverse"),
    series: tuple[str, ...] = (),
    legend: bool = False,
    colormap: bool = False,
    error: tuple[str, ...] = (),
    labels: bool = False,
    chart: tuple[str, ...] = (),
) -> EngineProfile:
    profile_id = str(data["profile_id"])
    semantic_objects = (*data.get("objects", ()), *data.get("repeatable_objects", ()))
    has_series = any(item.get("object_kind") == "series" for item in semantic_objects)
    series_parameters = tuple(dict.fromkeys((("visible",) if has_series else ()) + series))
    return EngineProfile.model_validate(
        {
            **data,
            "role_field_types": _ROLE_FIELD_TYPES[profile_id],
            "capabilities": _capabilities(
                axis=axis,
                series=series_parameters,
                legend=legend,
                colormap=colormap,
                error=error,
                labels=labels,
                chart=chart,
            ),
        }
    )


K01_LINE_PROFILE = _profile(
    {
        "profile_id": "K01",
        "display_name": "Line",
        "required_roles": ("x", "y"),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    series=("line_stroke_color", "line_width_pt", "line_style", "line_opacity"),
    legend=True,
)

K02_LINE_SYMBOL_PROFILE = _profile(
    {
        "profile_id": "K02",
        "display_name": "Line and symbol",
        "required_roles": ("x", "y"),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
    legend=True,
)

K03_SCATTER_PROFILE = _profile(
    {
        "profile_id": "K03",
        "display_name": "Scatter",
        "required_roles": ("x", "y"),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    series=(
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
        "marker_opacity",
    ),
    legend=True,
)

K04_BUBBLE_PROFILE = _profile(
    {
        "profile_id": "K04",
        "display_name": "Bubble and color-mapped scatter",
        "required_roles": ("x", "y"),
        "optional_roles": ("size", "color"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "primary"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
        "marker_opacity",
    ),
    legend=True,
    colormap=True,
    chart=("color_scale_visible", "size_key_visible"),
)

K06_POINT_ERROR_PROFILE = _profile(
    {
        "profile_id": "K06",
        "display_name": "Point estimate and error bar",
        "required_roles": ("x", "center", "x_err_minus", "x_err_plus", "y_err_minus", "y_err_plus"),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "primary"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
        "marker_opacity",
    ),
    legend=True,
    error=_ERROR_BAR_T1,
)

K07_ERROR_BAND_PROFILE = _profile(
    {
        "profile_id": "K07",
        "display_name": "Error ribbon",
        "required_roles": ("x", "center", "lower", "upper"),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "primary"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=("line_stroke_color", "line_width_pt", "line_style", "line_opacity"),
    legend=True,
    error=_ERROR_BAND_T1,
)

K08_COLUMN_PROFILE = _profile(
    {
        "profile_id": "K08",
        "display_name": "Column",
        "required_roles": ("category", "value"),
        "optional_roles": ("label",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "primary"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

K09_GROUPED_COLUMN_PROFILE = _profile(
    {
        "profile_id": "K09",
        "display_name": "Grouped column",
        "required_roles": ("category", "group", "value"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

K10_STACKED_COLUMN_PROFILE = _profile(
    {
        "profile_id": "K10",
        "display_name": "Stacked column",
        "required_roles": ("category", "component", "value"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "component",
            },
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

K11_PERCENT_STACK_PROFILE = _profile(
    {
        "profile_id": "K11",
        "display_name": "100% stacked column",
        "required_roles": ("category", "component", "value"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "component",
            },
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

K12_STRIP_PROFILE = _profile(
    {
        "profile_id": "K12",
        "display_name": "Strip plot",
        "required_roles": ("value",),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    series=(
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
        "marker_opacity",
    ),
    legend=True,
)

K13_BOX_PROFILE = _profile(
    {
        "profile_id": "K13",
        "display_name": "Box plot",
        "required_roles": ("value",),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
    legend=True,
)

K14_VIOLIN_PROFILE = _profile(
    {
        "profile_id": "K14",
        "display_name": "Violin plot",
        "required_roles": ("value",),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
        "line_stroke_color",
        "line_width_pt",
        "line_style",
    ),
    legend=True,
)

K15_HISTOGRAM_PROFILE = _profile(
    {
        "profile_id": "K15",
        "display_name": "Histogram",
        "required_roles": ("value",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "primary"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
)

K18_AREA_PROFILE = _profile(
    {
        "profile_id": "K18",
        "display_name": "Area",
        "required_roles": ("x", "series_1"),
        "optional_roles": ("group",),
        "repeatable_role_prefixes": ("series",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {"object_alias_prefix": "series", "object_kind": "series", "object_key_prefix": "area"},
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
)

K19_TIME_SERIES_PROFILE = _profile(
    {
        "profile_id": "K19",
        "display_name": "Time series",
        "required_roles": ("time", "series_1"),
        "optional_roles": ("group",),
        "repeatable_role_prefixes": ("series",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {"object_alias_prefix": "series", "object_kind": "series", "object_key_prefix": "line"},
        ),
    },
    series=("line_stroke_color", "line_width_pt", "line_style", "line_opacity"),
    legend=True,
)

K20_HEATMAP_PROFILE = _profile(
    {
        "profile_id": "K20",
        "display_name": "Heatmap",
        "required_roles": ("row", "column", "value"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "matrix"},
        ),
    },
    axis=("label", "reverse"),
    colormap=True,
    labels=True,
)

K21_CORRELATION_MATRIX_PROFILE = _profile(
    {
        "profile_id": "K21",
        "display_name": "Correlation matrix",
        "required_roles": ("row_label", "column_label", "value"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "matrix"},
        ),
    },
    axis=("label", "reverse"),
    colormap=True,
    labels=True,
    chart=("triangle",),
)

K22_CONTOUR_PROFILE = _profile(
    {
        "profile_id": "K22",
        "display_name": "Filled contour",
        "required_roles": ("x", "y", "z"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "matrix"},
        ),
    },
    axis=("label", "bounds", "reverse"),
    colormap=True,
    chart=("levels",),
)

K24_FACET_PROFILE = _profile(
    {
        "profile_id": "K24",
        "display_name": "Faceted plot",
        "required_roles": ("facet", "base_x", "base_y"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
        ),
        "repeatable_objects": (
            {"object_alias_prefix": "panel", "object_kind": "panel", "object_key_prefix": "facet"},
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "facet",
            },
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
)

S34_NYQUIST_PROFILE = _profile(
    {
        "profile_id": "S34",
        "display_name": "Nyquist plot",
        "required_roles": ("z_real", "z_imaginary"),
        "optional_roles": ("frequency", "series"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    axis=("label", "bounds", "reverse"),
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
    legend=True,
    chart=("equal_axes",),
)

S61_CONFUSION_PROFILE = _profile(
    {
        "profile_id": "S61",
        "display_name": "Confusion matrix",
        "required_roles": ("actual", "predicted"),
        "optional_roles": ("count",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "matrix"},
        ),
    },
    axis=("label", "reverse"),
    colormap=True,
    labels=True,
    chart=("show_counts",),
)

X02_DROP_LINE_PROFILE = _profile(
    {
        "profile_id": "X02",
        "display_name": "Drop line",
        "required_roles": ("x", "y"),
        "optional_roles": ("label",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "primary"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
    legend=True,
)

X03_LOLLIPOP_PROFILE = _profile(
    {
        "profile_id": "X03",
        "display_name": "Lollipop",
        "required_roles": ("category", "series_1", "series_2"),
        "repeatable_role_prefixes": ("series",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "column",
            },
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
    legend=True,
)

X05_BEESWARM_PROFILE = _profile(
    {
        "profile_id": "X05",
        "display_name": "Beeswarm",
        "required_roles": ("value",),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    series=(
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
        "marker_opacity",
    ),
    legend=True,
)

X09_FLOATING_INTERVAL_PROFILE = _profile(
    {
        "profile_id": "X09",
        "display_name": "Floating column",
        "required_roles": ("category", "start", "end"),
        "optional_roles": ("middle",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "primary"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

X13_POPULATION_PYRAMID_PROFILE = _profile(
    {
        "profile_id": "X13",
        "display_name": "Population pyramid",
        "required_roles": ("category", "left", "right"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "left"},
            {"object_alias": "series_2", "object_kind": "series", "object_key": "right"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    axis=("label", "bounds", "reverse"),
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

X23_DUAL_Y_LINE_PROFILE = _profile(
    {
        "profile_id": "X23",
        "display_name": "Dual-Y line",
        "required_roles": ("x", "left", "right"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y_left"},
            {"object_alias": "right_y_axis", "object_kind": "axis", "object_key": "y_right"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "left"},
            {"object_alias": "series_2", "object_kind": "series", "object_key": "right"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
    legend=True,
)

X24_PARETO_PROFILE = _profile(
    {
        "profile_id": "X24",
        "display_name": "Pareto",
        "required_roles": ("category", "value"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y_left"},
            {"object_alias": "right_y_axis", "object_kind": "axis", "object_key": "y_right"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "bars"},
            {"object_alias": "series_2", "object_kind": "series", "object_key": "cumulative"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    axis=("label",),
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "line_opacity",
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

X35_DUAL_Y_COLUMN_PROFILE = _profile(
    {
        "profile_id": "X35",
        "display_name": "Dual-Y column",
        "required_roles": ("category", "left", "right"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y_left"},
            {"object_alias": "right_y_axis", "object_kind": "axis", "object_key": "y_right"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "left"},
            {"object_alias": "series_2", "object_kind": "series", "object_key": "right"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

X36_DUAL_Y_COLUMN_LINE_PROFILE = _profile(
    {
        "profile_id": "X36",
        "display_name": "Dual-Y column and line",
        "required_roles": ("category", "left", "right"),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y_left"},
            {"object_alias": "right_y_axis", "object_kind": "axis", "object_key": "y_right"},
            {"object_alias": "series_1", "object_kind": "series", "object_key": "left"},
            {"object_alias": "series_2", "object_kind": "series", "object_key": "right"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
        "fill_color",
        "fill_opacity",
        "fill_stroke_color",
        "fill_stroke_width_pt",
        "fill_stroke_style",
    ),
    legend=True,
    labels=True,
)

X38_OFFSET_STACK_PROFILE = _profile(
    {
        "profile_id": "X38",
        "display_name": "Y-offset stacked line",
        "required_roles": ("x", "series_1"),
        "repeatable_role_prefixes": ("series",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "group",
            },
        ),
    },
    axis=("label", "scale", "bounds", "reverse"),
    series=("line_stroke_color", "line_width_pt", "line_style", "line_opacity"),
    legend=True,
)

X39_LINE_SERIES_PROFILE = _profile(
    {
        "profile_id": "X39",
        "display_name": "Line series",
        "required_roles": ("series_1", "series_2"),
        "repeatable_role_prefixes": ("series",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "connector", "object_kind": "series", "object_key": "connector"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "column",
            },
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
    legend=True,
)

X40_BEFORE_AFTER_PROFILE = _profile(
    {
        "profile_id": "X40",
        "display_name": "Before and after",
        "required_roles": ("label", "series_1", "series_2"),
        "optional_roles": ("group",),
        "objects": (
            {"object_alias": "x_axis", "object_kind": "axis", "object_key": "x"},
            {"object_alias": "y_axis", "object_kind": "axis", "object_key": "y"},
            {"object_alias": "connector", "object_kind": "series", "object_key": "connector"},
            {"object_alias": "legend", "object_kind": "legend", "object_key": "main"},
        ),
        "repeatable_objects": (
            {
                "object_alias_prefix": "series",
                "object_kind": "series",
                "object_key_prefix": "column",
            },
        ),
    },
    series=(
        "line_stroke_color",
        "line_width_pt",
        "line_style",
        "marker_shape",
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
    ),
    legend=True,
)

ENGINE_PROFILES = (
    K01_LINE_PROFILE,
    K02_LINE_SYMBOL_PROFILE,
    K03_SCATTER_PROFILE,
    K04_BUBBLE_PROFILE,
    K06_POINT_ERROR_PROFILE,
    K07_ERROR_BAND_PROFILE,
    K08_COLUMN_PROFILE,
    K09_GROUPED_COLUMN_PROFILE,
    K10_STACKED_COLUMN_PROFILE,
    K11_PERCENT_STACK_PROFILE,
    K12_STRIP_PROFILE,
    K13_BOX_PROFILE,
    K14_VIOLIN_PROFILE,
    K15_HISTOGRAM_PROFILE,
    K18_AREA_PROFILE,
    K19_TIME_SERIES_PROFILE,
    K20_HEATMAP_PROFILE,
    K21_CORRELATION_MATRIX_PROFILE,
    K22_CONTOUR_PROFILE,
    K24_FACET_PROFILE,
    S34_NYQUIST_PROFILE,
    S61_CONFUSION_PROFILE,
    X02_DROP_LINE_PROFILE,
    X03_LOLLIPOP_PROFILE,
    X05_BEESWARM_PROFILE,
    X09_FLOATING_INTERVAL_PROFILE,
    X13_POPULATION_PYRAMID_PROFILE,
    X23_DUAL_Y_LINE_PROFILE,
    X24_PARETO_PROFILE,
    X35_DUAL_Y_COLUMN_PROFILE,
    X36_DUAL_Y_COLUMN_LINE_PROFILE,
    X38_OFFSET_STACK_PROFILE,
    X39_LINE_SERIES_PROFILE,
    X40_BEFORE_AFTER_PROFILE,
)

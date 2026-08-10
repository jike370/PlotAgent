"""Public engine profile catalog under the replacement plotting architecture."""

from __future__ import annotations

from .contracts import (
    EngineCapability,
    EngineObjectTemplate,
    EngineProfile,
    EngineRepeatableObjectTemplate,
)

K01_LINE_PROFILE = EngineProfile(
    profile_id="K01",
    display_name="Line",
    required_roles=("x", "y"),
    optional_roles=("label",),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="series_1", object_kind="series", object_key="primary"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(
            operation="set_axis",
            parameters=("label", "scale", "bounds", "reverse"),
        ),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "line_style"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K02_LINE_SYMBOL_PROFILE = EngineProfile(
    profile_id="K02",
    display_name="Line and symbol",
    required_roles=("x", "y"),
    optional_roles=("label",),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="series_1", object_kind="series", object_key="primary"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(
            operation="set_axis",
            parameters=("label", "scale", "bounds", "reverse"),
        ),
        EngineCapability(
            operation="set_series_style",
            parameters=(
                "color",
                "line_width_pt",
                "line_style",
                "symbol",
                "symbol_size_pt",
            ),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K03_SCATTER_PROFILE = EngineProfile(
    profile_id="K03",
    display_name="Scatter",
    required_roles=("x", "y"),
    optional_roles=("group",),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    repeatable_objects=(
        EngineRepeatableObjectTemplate(
            object_alias_prefix="series",
            object_kind="series",
            object_key_prefix="group",
        ),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(
            operation="set_axis",
            parameters=("label", "scale", "bounds", "reverse"),
        ),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "symbol", "symbol_size_pt"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K06_POINT_ERROR_PROFILE = EngineProfile(
    profile_id="K06",
    display_name="Point estimate and error bar",
    required_roles=("x", "center", "x_error", "y_error"),
    optional_roles=("label",),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="series_1", object_kind="series", object_key="primary"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(
            operation="set_axis",
            parameters=("label", "scale", "bounds", "reverse"),
        ),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "symbol", "symbol_size_pt"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K07_ERROR_BAND_PROFILE = EngineProfile(
    profile_id="K07",
    display_name="Error ribbon",
    required_roles=("x", "center", "lower", "upper"),
    optional_roles=("label",),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="series_1", object_kind="series", object_key="primary"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(
            operation="set_axis",
            parameters=("label", "scale", "bounds", "reverse"),
        ),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "line_style"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K08_COLUMN_PROFILE = EngineProfile(
    profile_id="K08",
    display_name="Column",
    required_roles=("category", "value"),
    optional_roles=("label",),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="series_1", object_kind="series", object_key="primary"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(
            operation="set_axis",
            parameters=("label", "scale", "bounds", "reverse"),
        ),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K20_HEATMAP_PROFILE = EngineProfile(
    profile_id="K20",
    display_name="Heatmap",
    required_roles=("row", "column", "value"),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(operation="set_axis", parameters=("label", "reverse")),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

X23_DUAL_Y_LINE_PROFILE = EngineProfile(
    profile_id="X23",
    display_name="Dual-Y line",
    required_roles=("x", "left", "right"),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y_left"),
        EngineObjectTemplate(object_alias="right_y_axis", object_kind="axis", object_key="y_right"),
        EngineObjectTemplate(object_alias="series_1", object_kind="series", object_key="left"),
        EngineObjectTemplate(object_alias="series_2", object_kind="series", object_key="right"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(
            operation="set_axis",
            parameters=("label", "scale", "bounds", "reverse"),
        ),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "line_style"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

ENGINE_PROFILES = (
    K01_LINE_PROFILE,
    K02_LINE_SYMBOL_PROFILE,
    K03_SCATTER_PROFILE,
    K06_POINT_ERROR_PROFILE,
    K07_ERROR_BAND_PROFILE,
    K08_COLUMN_PROFILE,
    K20_HEATMAP_PROFILE,
    X23_DUAL_Y_LINE_PROFILE,
)

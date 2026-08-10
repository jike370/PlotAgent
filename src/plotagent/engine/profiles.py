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

K04_BUBBLE_PROFILE = EngineProfile(
    profile_id="K04",
    display_name="Bubble and color-mapped scatter",
    required_roles=("x", "y"),
    optional_roles=("size", "color"),
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
            parameters=("color", "symbol", "symbol_size_pt"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(
            operation="set_chart_parameter",
            parameters=("color_scale_visible", "size_key_visible"),
        ),
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

K09_GROUPED_COLUMN_PROFILE = EngineProfile(
    profile_id="K09",
    display_name="Grouped column",
    required_roles=("category", "group", "value"),
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
        EngineCapability(operation="set_axis", parameters=("label", "scale", "bounds", "reverse")),
        EngineCapability(operation="set_series_style", parameters=("color", "line_width_pt")),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K10_STACKED_COLUMN_PROFILE = EngineProfile(
    profile_id="K10",
    display_name="Stacked column",
    required_roles=("category", "component", "value"),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    repeatable_objects=(
        EngineRepeatableObjectTemplate(
            object_alias_prefix="series",
            object_kind="series",
            object_key_prefix="component",
        ),
    ),
    capabilities=K09_GROUPED_COLUMN_PROFILE.capabilities,
)

K11_PERCENT_STACK_PROFILE = EngineProfile(
    profile_id="K11",
    display_name="100% stacked column",
    required_roles=("category", "component", "value"),
    objects=K10_STACKED_COLUMN_PROFILE.objects,
    repeatable_objects=K10_STACKED_COLUMN_PROFILE.repeatable_objects,
    capabilities=K09_GROUPED_COLUMN_PROFILE.capabilities,
)

K12_STRIP_PROFILE = EngineProfile(
    profile_id="K12",
    display_name="Strip plot",
    required_roles=("value",),
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
        EngineCapability(operation="set_axis", parameters=("label", "scale", "bounds", "reverse")),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "symbol", "symbol_size_pt"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K13_BOX_PROFILE = EngineProfile(
    profile_id="K13",
    display_name="Box plot",
    required_roles=("value",),
    optional_roles=("group",),
    objects=K12_STRIP_PROFILE.objects,
    repeatable_objects=K12_STRIP_PROFILE.repeatable_objects,
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(operation="set_axis", parameters=("label", "scale", "bounds", "reverse")),
        EngineCapability(operation="set_series_style", parameters=("color", "line_width_pt")),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K14_VIOLIN_PROFILE = EngineProfile(
    profile_id="K14",
    display_name="Violin plot",
    required_roles=("value",),
    optional_roles=("group",),
    objects=K12_STRIP_PROFILE.objects,
    repeatable_objects=K12_STRIP_PROFILE.repeatable_objects,
    capabilities=K13_BOX_PROFILE.capabilities,
)

K15_HISTOGRAM_PROFILE = EngineProfile(
    profile_id="K15",
    display_name="Histogram",
    required_roles=("value",),
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
        EngineCapability(operation="set_axis", parameters=("label", "scale", "bounds", "reverse")),
        EngineCapability(operation="set_series_style", parameters=("color", "line_width_pt")),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K16_DENSITY_PROFILE = EngineProfile(
    profile_id="K16",
    display_name="Kernel density",
    required_roles=("value",),
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
        EngineCapability(operation="set_axis", parameters=("label", "scale", "bounds", "reverse")),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "line_style"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K18_AREA_PROFILE = EngineProfile(
    profile_id="K18",
    display_name="Area",
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
        EngineCapability(operation="set_axis", parameters=("label", "scale", "bounds", "reverse")),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "line_style"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K19_TIME_SERIES_PROFILE = EngineProfile(
    profile_id="K19",
    display_name="Time series",
    required_roles=("time", "value"),
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
        EngineCapability(operation="set_axis", parameters=("label", "reverse")),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "line_style", "symbol", "symbol_size_pt"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K21_CORRELATION_MATRIX_PROFILE = EngineProfile(
    profile_id="K21",
    display_name="Correlation matrix",
    required_roles=("row_label", "column_label", "value"),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="series_1", object_kind="series", object_key="matrix"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(operation="set_axis", parameters=("label", "reverse")),
        EngineCapability(operation="set_chart_parameter", parameters=("triangle",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

K22_CONTOUR_PROFILE = EngineProfile(
    profile_id="K22",
    display_name="Filled contour",
    required_roles=("x", "y", "z"),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="series_1", object_kind="series", object_key="matrix"),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(operation="set_axis", parameters=("label", "bounds", "reverse")),
        EngineCapability(operation="set_chart_parameter", parameters=("levels",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

X02_DROP_LINE_PROFILE = EngineProfile(
    profile_id="X02",
    display_name="Drop line",
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
        EngineCapability(operation="set_axis", parameters=("label", "scale", "bounds", "reverse")),
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

X03_LOLLIPOP_PROFILE = EngineProfile(
    profile_id="X03",
    display_name="Lollipop",
    required_roles=("category", "series_1", "series_2"),
    repeatable_role_prefixes=("series",),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    repeatable_objects=(
        EngineRepeatableObjectTemplate(
            object_alias_prefix="series",
            object_kind="series",
            object_key_prefix="column",
        ),
    ),
    capabilities=(
        EngineCapability(operation="create_plot"),
        EngineCapability(operation="bind_fields"),
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(operation="set_axis", parameters=("label", "scale", "bounds", "reverse")),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "line_style", "symbol", "symbol_size_pt"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible",)),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

X39_LINE_SERIES_PROFILE = EngineProfile(
    profile_id="X39",
    display_name="Line series",
    required_roles=("series_1", "series_2"),
    repeatable_role_prefixes=("series",),
    objects=(
        EngineObjectTemplate(object_alias="x_axis", object_kind="axis", object_key="x"),
        EngineObjectTemplate(object_alias="y_axis", object_kind="axis", object_key="y"),
        EngineObjectTemplate(object_alias="legend", object_kind="legend", object_key="main"),
    ),
    repeatable_objects=(
        EngineRepeatableObjectTemplate(
            object_alias_prefix="series",
            object_kind="series",
            object_key_prefix="row",
        ),
    ),
    capabilities=X03_LOLLIPOP_PROFILE.capabilities,
)

X40_BEFORE_AFTER_PROFILE = EngineProfile(
    profile_id="X40",
    display_name="Before and after",
    required_roles=("series_1", "series_2"),
    objects=X39_LINE_SERIES_PROFILE.objects,
    repeatable_objects=X39_LINE_SERIES_PROFILE.repeatable_objects,
    capabilities=X03_LOLLIPOP_PROFILE.capabilities,
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
    K16_DENSITY_PROFILE,
    K18_AREA_PROFILE,
    K19_TIME_SERIES_PROFILE,
    K20_HEATMAP_PROFILE,
    K21_CORRELATION_MATRIX_PROFILE,
    K22_CONTOUR_PROFILE,
    X02_DROP_LINE_PROFILE,
    X03_LOLLIPOP_PROFILE,
    X23_DUAL_Y_LINE_PROFILE,
    X39_LINE_SERIES_PROFILE,
    X40_BEFORE_AFTER_PROFILE,
)

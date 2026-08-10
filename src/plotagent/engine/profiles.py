"""Public engine profile catalog under the replacement plotting architecture."""

from __future__ import annotations

from .contracts import EngineCapability, EngineProfile

K01_LINE_PROFILE = EngineProfile(
    profile_id="K01",
    display_name="Line",
    required_roles=("x", "y"),
    optional_roles=("label",),
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
    K08_COLUMN_PROFILE,
    K20_HEATMAP_PROFILE,
    X23_DUAL_Y_LINE_PROFILE,
)

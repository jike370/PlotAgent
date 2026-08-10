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
        EngineCapability(operation="set_title", parameters=("text",)),
        EngineCapability(
            operation="set_axis",
            parameters=("label", "scale", "bounds", "reverse"),
        ),
        EngineCapability(
            operation="set_series_style",
            parameters=("color", "line_width_pt", "line_style", "symbol", "symbol_size_pt"),
        ),
        EngineCapability(operation="set_legend", parameters=("visible", "anchor")),
        EngineCapability(operation="add_annotation", parameters=("text", "x", "y")),
        EngineCapability(operation="export_plot", parameters=("png", "svg", "opju")),
    ),
)

ENGINE_PROFILES = (K01_LINE_PROFILE,)

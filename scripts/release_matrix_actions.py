"""Deterministic representative edits shared by both release backends."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from plotagent.engine import (
    EngineCatalog,
    EngineReadback,
    PlotDocument,
    PlotEngineAction,
    SetAxis,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.profiles import ENGINE_PROFILES
from scripts.release_matrix_cases import ReleaseCase

_AXIS_SUFFIX = {
    "S34": "x",
    "X03": "x",
    "X13": "x",
    "X23": "y_left",
    "X24": "y_left",
    "X35": "y_left",
    "X36": "y_left",
}

_BOUND_ROLES: dict[str, tuple[str, ...]] = {
    "K01": ("y",),
    "K02": ("y",),
    "K03": ("y",),
    "K04": ("y",),
    "K06": ("center",),
    "K07": ("center",),
    "K08": ("value",),
    "K09": ("value",),
    "K10": ("value",),
    "K11": ("value",),
    "K12": ("value",),
    "K13": ("value",),
    "K14": ("value",),
    "K15": ("value",),
    "K18": ("series_1",),
    "K19": ("series_1",),
    "K22": ("y",),
    "K24": ("base_y",),
    "S34": ("z_real",),
    "X02": ("y",),
    "X03": ("series_1",),
    "X05": ("value",),
    "X09": ("start", "middle", "end"),
    "X13": ("left", "right"),
    "X23": ("left",),
    "X35": ("left",),
    "X36": ("left",),
    "X38": ("series_1",),
    "X39": ("series_1",),
    "X40": ("series_1", "series_2"),
}


def _parameters(profile_id: str, operation: str) -> frozenset[str]:
    profile = next(profile for profile in ENGINE_PROFILES if str(profile.profile_id) == profile_id)
    capability = next(item for item in profile.capabilities if item.operation == operation)
    return frozenset(capability.parameters)


def _target(readback: EngineReadback, kind: str, *, suffix: str | None = None) -> str:
    candidates = tuple(
        str(item.semantic_id)
        for item in readback.objects
        if str(item.semantic_id).startswith(kind + ":")
    )
    if suffix is not None:
        exact = next((item for item in candidates if item.endswith("." + suffix)), None)
        if exact is not None:
            return exact
    if not candidates:
        raise RuntimeError(f"release readback has no {kind} target")
    return candidates[0]


def _bound_values(case: ReleaseCase) -> tuple[float, float]:
    wanted = set(_BOUND_ROLES[case.profile_id])
    values = _numeric_values(case, wanted)
    if not values:
        raise RuntimeError(f"{case.profile_id} has no numeric values for axis bounds")
    if case.profile_id == "X13":
        extent = max(abs(value) for value in values) * 1.12
        return -extent, extent
    minimum, maximum = min(values), max(values)
    if minimum == maximum:
        return minimum - 1, maximum + 1
    padding = max((maximum - minimum) * 0.08, 0.05)
    return minimum - padding, maximum + padding


def _numeric_values(case: ReleaseCase, roles: set[str]) -> list[float]:
    result: list[float] = []
    for binding, column in zip(case.create.bindings, case.view.columns, strict=True):
        if binding.role not in roles:
            continue
        for value in column.values:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                result.append(float(value))
    return result


def _axis_action(
    case: ReleaseCase,
    readback: EngineReadback,
    *,
    expected_version: int,
) -> SetAxis:
    parameters = _parameters(case.profile_id, "set_axis")
    suffix = _AXIS_SUFFIX.get(case.profile_id, "y")
    minimum: float | None = None
    maximum: float | None = None
    scale: Literal["linear", "log10"] | None = None
    if "bounds" in parameters:
        minimum, maximum = _bound_values(case)
    if "scale" in parameters:
        roles = set(_BOUND_ROLES[case.profile_id])
        raw = _numeric_values(case, roles)
        positive = bool(raw) and all(value > 0 for value in raw)
        scale = "log10" if positive else "linear"
        if scale == "log10" and minimum is not None and maximum is not None:
            minimum = min(raw) * 0.8
            maximum = max(raw) * 1.2
    return SetAxis(
        action_id=f"action:release-{case.profile_id.lower()}-axis",
        target=_target(readback, "axis", suffix=suffix),
        expected_plot_version=expected_version,
        label=f"{case.profile_id} representative axis",
        scale=scale,
        minimum=minimum,
        maximum=maximum,
        reverse=False if "reverse" in parameters else None,
        title_font_family="Arial" if "title_font_family" in parameters else None,
        title_font_size_pt=11 if "title_font_size_pt" in parameters else None,
        title_font_weight="bold" if "title_font_weight" in parameters else None,
        title_italic=True if "title_italic" in parameters else None,
        title_color="#25324A" if "title_color" in parameters else None,
        major_tick_step=(
            (maximum - minimum) / 4
            if "major_tick_step" in parameters
            and minimum is not None
            and maximum is not None
            else (1 if "major_tick_step" in parameters else None)
        ),
        minor_tick_count=1 if "minor_tick_count" in parameters else None,
        tick_format="scientific" if "tick_format" in parameters else None,
        tick_rotation_deg=12 if "tick_rotation_deg" in parameters else None,
        tick_font_family="Arial" if "tick_font_family" in parameters else None,
        tick_font_size_pt=8.5 if "tick_font_size_pt" in parameters else None,
        tick_color="#344054" if "tick_color" in parameters else None,
        tick_labels_visible=True if "tick_labels_visible" in parameters else None,
        major_ticks_visible=True if "major_ticks_visible" in parameters else None,
        minor_ticks_visible=True if "minor_ticks_visible" in parameters else None,
        tick_direction="in" if "tick_direction" in parameters else None,
        axis_line_visible=True if "axis_line_visible" in parameters else None,
        axis_title_visible=True if "axis_title_visible" in parameters else None,
        axis_line_color="#475467" if "axis_line_color" in parameters else None,
        axis_line_width_pt=1.25 if "axis_line_width_pt" in parameters else None,
        major_grid_visible=True if "major_grid_visible" in parameters else None,
        minor_grid_visible=True if "minor_grid_visible" in parameters else None,
        grid_color="#D0D5DD" if "grid_color" in parameters else None,
        grid_line_width_pt=0.75 if "grid_line_width_pt" in parameters else None,
        grid_line_style="dot" if "grid_line_style" in parameters else None,
    )


def _series_action(
    case: ReleaseCase,
    readback: EngineReadback,
    *,
    expected_version: int,
) -> SetSeriesStyle:
    parameters = _parameters(case.profile_id, "set_series_style")
    action_id = f"action:release-{case.profile_id.lower()}-series"
    target = _target(readback, "series")
    return SetSeriesStyle(
        action_id=action_id,
        target=target,
        expected_plot_version=expected_version,
        visible=True if "visible" in parameters else None,
        line_stroke_color="#B42318" if "line_stroke_color" in parameters else None,
        line_width_pt=2.25 if "line_width_pt" in parameters else None,
        line_style="dash" if "line_style" in parameters else None,
        line_opacity=0.8 if "line_opacity" in parameters else None,
        marker_shape="diamond" if "marker_shape" in parameters else None,
        marker_size_pt=8 if "marker_size_pt" in parameters else None,
        marker_interior="open" if "marker_interior" in parameters else None,
        marker_fill_color="#B42318" if "marker_fill_color" in parameters else None,
        marker_stroke_color="#7A1F18" if "marker_stroke_color" in parameters else None,
        marker_opacity=0.85 if "marker_opacity" in parameters else None,
        fill_color="#7EA6D8" if "fill_color" in parameters else None,
        fill_opacity=0.75 if "fill_opacity" in parameters else None,
        fill_stroke_color="#4F78A8" if "fill_stroke_color" in parameters else None,
        fill_stroke_width_pt=1.25 if "fill_stroke_width_pt" in parameters else None,
        fill_stroke_style="dash" if "fill_stroke_style" in parameters else None,
    )


def _numeric_extent(case: ReleaseCase) -> tuple[float, float]:
    values = _numeric_values(
        case,
        {binding.role for binding in case.create.bindings},
    )
    if not values:
        raise RuntimeError(f"{case.profile_id} has no numeric values for a color map")
    minimum, maximum = min(values), max(values)
    if minimum == maximum:
        return minimum - 1, maximum + 1
    return minimum, maximum


def _colormap_action(
    case: ReleaseCase,
    readback: EngineReadback,
    *,
    expected_version: int,
) -> SetColorMap:
    parameters = _parameters(case.profile_id, "set_colormap")
    minimum, maximum = _numeric_extent(case)
    return SetColorMap(
        action_id=f"action:release-{case.profile_id.lower()}-colormap",
        target=_target(readback, "series"),
        expected_plot_version=expected_version,
        palette="blue_orange" if "palette" in parameters else None,
        reverse=True if "reverse" in parameters else None,
        minimum=minimum if "minimum" in parameters else None,
        maximum=maximum if "maximum" in parameters else None,
        midpoint=(minimum + maximum) / 2 if "midpoint" in parameters else None,
        mode="discrete" if "mode" in parameters else None,
        levels=6 if "levels" in parameters else None,
        missing_color="#98A2B3" if "missing_color" in parameters else None,
        colorbar_visible=True if "colorbar_visible" in parameters else None,
        colorbar_anchor="bottom" if "colorbar_anchor" in parameters else None,
        colorbar_title=(
            f"{case.profile_id} color scale" if "colorbar_title" in parameters else None
        ),
        colorbar_tick_format=(
            "scientific" if "colorbar_tick_format" in parameters else None
        ),
    )


def _error_action(
    case: ReleaseCase,
    readback: EngineReadback,
    *,
    expected_version: int,
) -> SetErrorStyle:
    parameters = _parameters(case.profile_id, "set_error_style")
    return SetErrorStyle(
        action_id=f"action:release-{case.profile_id.lower()}-error",
        target=_target(readback, "series"),
        expected_plot_version=expected_version,
        bar_color="#B42318" if "bar_color" in parameters else None,
        bar_width_pt=1.5 if "bar_width_pt" in parameters else None,
        cap_size_pt=6 if "cap_size_pt" in parameters else None,
        bar_opacity=0.75 if "bar_opacity" in parameters else None,
        band_fill_color="#B2CCFF" if "band_fill_color" in parameters else None,
        band_fill_opacity=0.35 if "band_fill_opacity" in parameters else None,
        band_stroke_color="#175CD3" if "band_stroke_color" in parameters else None,
        band_stroke_width_pt=(
            1.25 if "band_stroke_width_pt" in parameters else None
        ),
    )


def _labels_action(
    case: ReleaseCase,
    readback: EngineReadback,
    *,
    expected_version: int,
) -> SetDataLabels:
    parameters = _parameters(case.profile_id, "set_data_labels")
    return SetDataLabels(
        action_id=f"action:release-{case.profile_id.lower()}-labels",
        target=_target(readback, "series"),
        expected_plot_version=expected_version,
        visible=True if "visible" in parameters else None,
        value_format="decimal" if "value_format" in parameters else None,
        prefix="v=" if "prefix" in parameters else None,
        suffix=" unit" if "suffix" in parameters else None,
        position="above" if "position" in parameters else None,
        rotation_deg=10 if "rotation_deg" in parameters else None,
        font_family="Arial" if "font_family" in parameters else None,
        font_size_pt=8 if "font_size_pt" in parameters else None,
        font_weight="bold" if "font_weight" in parameters else None,
        font_color="#344054" if "font_color" in parameters else None,
    )


_CHART_PARAMETER_VALUES: dict[str, str | int | bool] = {
    "color_scale_visible": True,
    "equal_axes": False,
    "levels": 7,
    "show_counts": False,
    "size_key_visible": False,
    "triangle": "lower",
}


def _chart_parameter_actions(
    case: ReleaseCase,
    *,
    expected_version: int,
) -> tuple[SetChartParameter, ...]:
    return tuple(
        SetChartParameter(
            action_id=(
                f"action:release-{case.profile_id.lower()}-chart-{parameter.replace('_', '-')}"
            ),
            target=case.document.plot_id,
            expected_plot_version=expected_version + index,
            parameter=parameter,
            value=_CHART_PARAMETER_VALUES[parameter],
        )
        for index, parameter in enumerate(
            sorted(_parameters(case.profile_id, "set_chart_parameter"))
        )
    )


def action_parameter_names(action: PlotEngineAction) -> frozenset[str]:
    """Return the public capability parameters exercised by one edit action."""

    if isinstance(action, SetChartParameter):
        return frozenset((action.parameter,))
    metadata = {"operation", "action_id", "target", "expected_plot_version"}
    names = set(action.model_dump(exclude_none=True)) - metadata
    if isinstance(action, SetAxis) and {"minimum", "maximum"} <= names:
        names -= {"minimum", "maximum"}
        names.add("bounds")
    return frozenset(names)


def representative_edit_actions(
    case: ReleaseCase,
    readback: EngineReadback,
) -> tuple[PlotEngineAction, ...]:
    if case.variant != "representative":
        raise ValueError("representative edits require the representative fixture")
    actions: list[PlotEngineAction] = [
        SetTitle(
            action_id=f"action:release-{case.profile_id.lower()}-title",
            target=case.document.plot_id,
            expected_plot_version=1,
            text=f"{case.profile_id} representative edited title",
            font_family="Arial",
            font_size_pt=14,
            font_weight="bold",
            italic=True,
            color="#101828",
        )
    ]
    actions.append(_axis_action(case, readback, expected_version=len(actions) + 1))
    profile = next(
        profile for profile in ENGINE_PROFILES if str(profile.profile_id) == case.profile_id
    )
    series_parameters = _parameters(case.profile_id, "set_series_style")
    visibility_only = series_parameters == frozenset(("visible",))
    if not visibility_only:
        actions.append(_series_action(case, readback, expected_version=len(actions) + 1))
    if any(item.operation == "set_legend" for item in profile.capabilities):
        actions.append(
            SetLegend(
                action_id=f"action:release-{case.profile_id.lower()}-legend",
                target=_target(readback, "legend"),
                expected_plot_version=len(actions) + 1,
                visible=True,
                anchor="inside_top_right",
                columns=1,
                title=f"{case.profile_id} legend",
                font_family="Arial",
                font_size_pt=9,
                font_color="#344054",
                frame_visible=True,
                frame_color="#98A2B3",
                frame_width_pt=1,
            )
        )
    operation_names = {item.operation for item in profile.capabilities}
    if "set_chart_parameter" in operation_names:
        actions.extend(
            _chart_parameter_actions(case, expected_version=len(actions) + 1)
        )
    if "set_colormap" in operation_names:
        actions.append(
            _colormap_action(case, readback, expected_version=len(actions) + 1)
        )
    if "set_error_style" in operation_names:
        actions.append(_error_action(case, readback, expected_version=len(actions) + 1))
    if "set_data_labels" in operation_names:
        actions.append(_labels_action(case, readback, expected_version=len(actions) + 1))
    if visibility_only:
        actions.append(
            SetSeriesStyle(
                action_id=f"action:release-{case.profile_id.lower()}-series",
                target=_target(readback, "series"),
                expected_plot_version=len(actions) + 1,
                visible=False,
            )
        )
    catalog = EngineCatalog(ENGINE_PROFILES)
    for action in actions:
        catalog.validate_action(profile, action)
    expected = {
        capability.operation: frozenset(capability.parameters)
        for capability in profile.capabilities
        if capability.operation
        not in {"create_plot", "bind_fields", "export_plot"}
    }
    observed: dict[str, set[str]] = {}
    for action in actions:
        observed.setdefault(action.operation, set()).update(action_parameter_names(action))
    observed_frozen = {
        operation: frozenset(parameters) for operation, parameters in observed.items()
    }
    assert observed_frozen == expected
    return tuple(actions)


def document_for_actions(
    case: ReleaseCase,
    actions: Iterable[PlotEngineAction],
) -> PlotDocument:
    history = tuple(actions)
    version = len(history) + 1
    return case.document.model_copy(
        update={
            "plot_version": version,
            "parent_version": version - 1,
            "applied_action_ids": (
                *case.document.applied_action_ids,
                *(action.action_id for action in history),
            ),
        }
    )

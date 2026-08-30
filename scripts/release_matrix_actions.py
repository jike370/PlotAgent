"""Deterministic representative edits shared by both release backends."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from plotagent.engine import (
    AddCallout,
    AddReferenceLine,
    EngineCatalog,
    EngineReadback,
    PlotDocument,
    PlotEngineAction,
    PointMarkerMapEntry,
    SetAxis,
    SetCanvas,
    SetChartParameter,
    SetColorMap,
    SetDataLabels,
    SetErrorStyle,
    SetLegend,
    SetObservationOverlay,
    SetPointMarkerMap,
    SetSeriesStyle,
    SetTitle,
)
from plotagent.engine.profiles import ENGINE_PROFILES
from scripts.release_matrix_cases import ReleaseCase

_ACTION_METADATA = {
    "operation",
    "action_id",
    "target",
    "expected_plot_version",
    "reference_line_id",
    "callout_id",
}

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
    columns = {column.field.field_id: column for column in case.view.columns}
    for binding in case.create.bindings:
        if binding.role not in roles:
            continue
        column = columns[binding.field_id]
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
    parameters: frozenset[str] | None = None,
    target_suffix: str | None = None,
) -> SetSeriesStyle:
    selected = (
        _parameters(case.profile_id, "set_series_style")
        if parameters is None
        else parameters
    )
    suffix = "" if target_suffix is None else f"-{target_suffix.replace('_', '-')}"
    action_id = f"action:release-{case.profile_id.lower()}-series{suffix}"
    target = _target(readback, "series", suffix=target_suffix)
    return SetSeriesStyle(
        action_id=action_id,
        target=target,
        expected_plot_version=expected_version,
        visible=True if "visible" in selected else None,
        line_stroke_color="#B42318" if "line_stroke_color" in selected else None,
        line_width_pt=2.25 if "line_width_pt" in selected else None,
        line_style="dash" if "line_style" in selected else None,
        line_opacity=0.8 if "line_opacity" in selected else None,
        marker_shape="diamond" if "marker_shape" in selected else None,
        marker_size_pt=8 if "marker_size_pt" in selected else None,
        marker_interior="open" if "marker_interior" in selected else None,
        marker_fill_color="#B42318" if "marker_fill_color" in selected else None,
        marker_stroke_color="#7A1F18" if "marker_stroke_color" in selected else None,
        marker_opacity=0.85 if "marker_opacity" in selected else None,
        fill_color="#7EA6D8" if "fill_color" in selected else None,
        fill_opacity=0.75 if "fill_opacity" in selected else None,
        fill_stroke_color="#4F78A8" if "fill_stroke_color" in selected else None,
        fill_stroke_width_pt=1.25 if "fill_stroke_width_pt" in selected else None,
        fill_stroke_style="dash" if "fill_stroke_style" in selected else None,
    )


def _series_parameter_suffix(profile_id: str, parameter: str) -> str | None:
    family = (
        "marker"
        if parameter.startswith("marker_")
        else "line"
        if parameter.startswith("line_")
        else "fill"
        if parameter.startswith("fill_")
        else "visibility"
    )
    return {
        ("X24", "line"): "cumulative",
        ("X24", "fill"): "bars",
        ("X36", "line"): "right",
        ("X36", "marker"): "right",
        ("X36", "fill"): "left",
        ("X39", "line"): "connector",
        ("X39", "marker"): "column_1",
        ("X40", "line"): "connector",
        ("X40", "marker"): "column_1",
    }.get((profile_id, family))


def _series_actions(
    case: ReleaseCase,
    readback: EngineReadback,
    *,
    expected_version: int,
) -> tuple[SetSeriesStyle, ...]:
    grouped: dict[str | None, set[str]] = {}
    declared = _parameters(case.profile_id, "set_series_style")
    for parameter in declared - {"visible"}:
        suffix = _series_parameter_suffix(case.profile_id, parameter)
        grouped.setdefault(suffix, set()).add(parameter)
    result = [
        _series_action(
            case,
            readback,
            expected_version=expected_version + index,
            parameters=frozenset(parameters),
            target_suffix=suffix,
        )
        for index, (suffix, parameters) in enumerate(grouped.items())
    ]
    if "visible" in declared:
        visibility = _series_action(
            case,
            readback,
            expected_version=expected_version + len(result),
            parameters=frozenset(("visible",)),
        ).model_copy(
            update={
                "action_id": f"action:release-{case.profile_id.lower()}-series-visibility",
                "visible": False,
            }
        )
        result.append(visibility)
    return tuple(result)


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
    "identity_labels_visible": False,
    "triangle": "lower",
}


@dataclass(frozen=True, slots=True)
class IsolatedEditCase:
    """One public parameter exercised as a two-value visual comparison."""

    profile_id: str
    operation: str
    focal_parameters: tuple[str, ...]
    dependency_parameters: tuple[str, ...]
    setup_actions: tuple[PlotEngineAction, ...]
    action: PlotEngineAction
    comparison_action: PlotEngineAction
    comparison_mode: Literal["pixel_ab", "shared_property"]
    evidence_reason: str | None

    @property
    def case_id(self) -> str:
        suffix = "+".join(self.focal_parameters)
        return f"{self.profile_id}:{self.operation}:{suffix}"


def _comparison_evidence(
    case: ReleaseCase,
    readback: EngineReadback,
    operation: str,
    focal_parameters: tuple[str, ...],
) -> tuple[Literal["pixel_ab", "shared_property"], str | None]:
    """Choose evidence that can actually observe the focal parameter.

    A one-entry legend cannot reveal a column-count change in pixels, and a
    dataset without missing samples cannot reveal a missing-value colour.
    Those parameters still require executable evidence, but it belongs in a
    shared native-adapter property test with the required materialized state.
    Everything else remains a strict profile-specific pixel A/B comparison.
    """

    if operation == "set_legend" and focal_parameters == ("columns",):
        series_count = sum(
            str(item.semantic_id).startswith("series:") for item in readback.objects
        )
        if series_count < 2:
            return (
                "shared_property",
                "representative profile materializes fewer than two legend entries",
            )
    if operation == "set_colormap" and focal_parameters == ("missing_color",):
        has_missing = any(
            value is None
            or (isinstance(value, float) and not math.isfinite(value))
            for column in case.view.columns
            for value in column.values
        )
        if not has_missing:
            return (
                "shared_property",
                "representative profile contains no missing or non-finite sample",
            )
    return ("pixel_ab", None)


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


def _reference_line_action(
    case: ReleaseCase,
    readback: EngineReadback,
    *,
    expected_version: int,
) -> AddReferenceLine:
    suffix = _AXIS_SUFFIX.get(case.profile_id, "y")
    roles = set(_BOUND_ROLES.get(case.profile_id, ()))
    values = _numeric_values(case, roles) if roles else []
    if not values:
        values = [
            float(value)
            for column in case.view.columns
            for value in column.values
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ]
    if not values:
        raise RuntimeError(f"{case.profile_id} has no numeric reference-line value")
    value = (min(values) + max(values)) / 2
    return AddReferenceLine(
        action_id=f"action:release-{case.profile_id.lower()}-reference-line",
        target=_target(readback, "axis", suffix=suffix),
        expected_plot_version=expected_version,
        reference_line_id=f"reference_line:release.{case.profile_id.lower()}.threshold",
        value=value,
        label="Reference",
        line_color="#B42318",
        line_width_pt=1.5,
        line_style="dash",
    )


def _callout_action(
    case: ReleaseCase,
    reference_line: AddReferenceLine,
    *,
    expected_version: int,
) -> AddCallout:
    return AddCallout(
        action_id=f"action:release-{case.profile_id.lower()}-reference-callout",
        target=reference_line.reference_line_id,
        expected_plot_version=expected_version,
        callout_id=f"callout:release.{case.profile_id.lower()}.threshold",
        text="Reference callout",
        anchor_fraction=0.68,
        text_x_fraction=0.82,
        text_y_fraction=0.82,
        arrow_color="#B42318",
        arrow_width_pt=1.5,
        arrow_head="filled",
        font_family="Arial",
        font_size_pt=9,
        font_weight="bold",
        italic=True,
        text_color="#B42318",
    )


def action_parameter_names(action: PlotEngineAction) -> frozenset[str]:
    """Return the public capability parameters exercised by one edit action."""

    if isinstance(action, SetChartParameter):
        return frozenset((action.parameter,))
    if isinstance(action, SetPointMarkerMap):
        return frozenset(("field", "entries"))
    metadata = _ACTION_METADATA
    names = set(action.model_dump(exclude_none=True)) - metadata
    if isinstance(action, SetAxis) and {"minimum", "maximum"} <= names:
        names -= {"minimum", "maximum"}
        names.add("bounds")
    return frozenset(names)


def _isolated_dependencies(action: PlotEngineAction, parameter: str) -> tuple[str, ...]:
    if isinstance(action, SetPointMarkerMap):
        return ("entries",) if parameter == "field" else ("field",)
    if isinstance(action, SetObservationOverlay):
        return tuple(
            item
            for item in (
                "visible",
                "jitter_fraction",
                "marker_shape",
                "marker_size_pt",
                "marker_interior",
                "marker_fill_color",
                "marker_stroke_color",
                "marker_opacity",
            )
            if item != parameter
        )
    if isinstance(action, SetTitle) and parameter != "text":
        return ("text",)
    if isinstance(action, AddReferenceLine) and parameter != "value":
        return ("value",)
    if isinstance(action, AddCallout):
        required = ("text", "anchor_fraction", "text_x_fraction", "text_y_fraction")
        return tuple(item for item in required if item != parameter)
    if isinstance(action, SetCanvas):
        if parameter == "width_mm":
            return ("height_mm",)
        if parameter == "height_mm":
            return ("width_mm",)
    if isinstance(action, SetAxis):
        if parameter.startswith("title_"):
            return ("label",)
        if parameter in {
            "tick_format",
            "tick_rotation_deg",
            "tick_font_family",
            "tick_font_size_pt",
            "tick_color",
        }:
            return ("tick_labels_visible",)
        if parameter in {"axis_line_color", "axis_line_width_pt"}:
            return ("axis_line_visible",)
        if parameter in {"grid_color", "grid_line_width_pt", "grid_line_style"}:
            return ("major_grid_visible",)
        if parameter == "minor_ticks_visible":
            return ("minor_tick_count",)
        if parameter == "minor_grid_visible":
            return ("minor_ticks_visible", "minor_tick_count")
    if isinstance(action, SetSeriesStyle) and parameter in {
        "marker_size_pt",
        "marker_interior",
        "marker_fill_color",
        "marker_stroke_color",
        "marker_opacity",
    }:
        return ("marker_shape",)
    if isinstance(action, SetLegend) and parameter != "visible":
        return ("visible",)
    if isinstance(action, SetColorMap):
        if parameter == "midpoint":
            return ("minimum", "maximum")
        if parameter in {
            "colorbar_anchor",
            "colorbar_title",
            "colorbar_tick_format",
        }:
            return ("colorbar_visible",)
        if parameter == "levels":
            return ("mode",)
    if isinstance(action, SetErrorStyle) and parameter == "band_stroke_color":
        return ("band_stroke_width_pt",)
    if isinstance(action, SetDataLabels) and parameter != "visible":
        return ("visible",)
    return ()


def _isolated_value(action: PlotEngineAction, parameter: str) -> object:
    if isinstance(action, SetPointMarkerMap):
        return action.field_id if parameter == "field" else action.entries
    overrides: dict[str, object] = {
        "reverse": True,
        "tick_labels_visible": False,
        "major_ticks_visible": False,
        "minor_ticks_visible": False,
        "axis_line_visible": False,
        "axis_title_visible": False,
        "visible": not isinstance(action, SetSeriesStyle),
    }
    if parameter in overrides:
        return overrides[parameter]
    value = getattr(action, parameter)
    if value is None:
        raise RuntimeError(
            f"representative {action.operation} has no value for public parameter {parameter}"
        )
    return value


def _dependency_value(action: PlotEngineAction, parameter: str) -> object:
    """Return an enabling prerequisite, never a hidden comparison state."""

    enabling: dict[str, object] = {
        "tick_labels_visible": True,
        "minor_ticks_visible": True,
        "axis_line_visible": True,
        "major_grid_visible": True,
        "visible": True,
    }
    if parameter in enabling:
        return enabling[parameter]
    return _isolated_value(action, parameter)


def _alternate_text(parameter: str, value: str) -> str:
    choices: dict[str, str] = {
        "scale": "linear" if value != "linear" else "log10",
        "tick_format": "decimal" if value != "decimal" else "scientific",
        "colorbar_tick_format": "decimal" if value != "decimal" else "scientific",
        "value_format": "scientific" if value != "scientific" else "decimal",
        "tick_direction": "out" if value != "out" else "in",
        "line_style": "dot" if value != "dot" else "dash",
        "grid_line_style": "dash" if value != "dash" else "dot",
        "fill_stroke_style": "dot" if value != "dot" else "dash",
        "marker_shape": "square" if value != "square" else "diamond",
        "marker_interior": "solid" if value != "solid" else "open",
        "anchor": "bottom" if value != "bottom" else "right",
        "colorbar_anchor": "right" if value != "right" else "bottom",
        "mode": "continuous" if value != "continuous" else "discrete",
        "palette": "viridis" if value != "viridis" else "blue_orange",
        "position": "below" if value != "below" else "above",
        "font_family": "Calibri" if value != "Calibri" else "Arial",
        "title_font_family": "Calibri" if value != "Calibri" else "Arial",
        "tick_font_family": "Calibri" if value != "Calibri" else "Arial",
        "font_weight": "normal" if value != "normal" else "bold",
        "title_font_weight": "normal" if value != "normal" else "bold",
        "arrow_head": "open" if value != "open" else "filled",
    }
    if parameter in choices:
        return choices[parameter]
    if "color" in parameter:
        return "#00A36C" if value.upper() != "#00A36C" else "#B42318"
    if parameter in {"text", "label", "title", "colorbar_title"}:
        return value + " alternate"
    if parameter == "prefix":
        return "alt=" if value != "alt=" else "v="
    if parameter == "suffix":
        return " alt" if value != " alt" else " unit"
    if parameter == "triangle":
        return "upper" if value != "upper" else "lower"
    raise RuntimeError(f"no alternate string value for {parameter}={value!r}")


def _alternate_number(parameter: str, value: int | float) -> int | float:
    if parameter in {"columns", "minor_tick_count"}:
        return 2 if value != 2 else 3
    if parameter == "levels":
        return int(value) + 3
    if "opacity" in parameter:
        return 0.25 if float(value) > 0.5 else 0.85
    if parameter in {"rotation_deg", "tick_rotation_deg"}:
        return -25.0 if float(value) >= 0 else 25.0
    if parameter == "major_tick_step":
        return float(value) * 0.57
    if parameter in {"width_mm", "height_mm"}:
        return float(value) * 0.8
    if parameter == "aspect_ratio":
        return min(5.0, float(value) * 1.25)
    if parameter in {"anchor_fraction", "text_x_fraction", "text_y_fraction"}:
        return 0.25 if float(value) > 0.5 else 0.75
    if parameter == "jitter_fraction":
        return 0.35 if float(value) < 0.3 else 0.1
    if parameter == "value":
        return float(value) + max(abs(float(value)) * 0.2, 0.5)
    if "font_size_pt" in parameter:
        return min(72.0, float(value) + 4.0)
    if parameter.endswith("width_pt") or parameter in {
        "cap_size_pt",
        "marker_size_pt",
    }:
        return min(20.0 if parameter.endswith("width_pt") else 72.0, float(value) + 2.0)
    raise RuntimeError(f"no alternate numeric value for {parameter}={value!r}")


def _comparison_action(
    action: PlotEngineAction,
    focal_parameters: tuple[str, ...],
) -> PlotEngineAction:
    payload = action.model_dump(mode="python")
    payload["action_id"] = str(action.action_id) + "-comparison"
    if isinstance(action, SetPointMarkerMap):
        if focal_parameters == ("field",):
            payload["field_id"] = str(action.field_id).replace(
                "-marker-class", "-marker-class-alt"
            )
        elif focal_parameters == ("entries",):
            payload["entries"] = tuple(
                {
                    "value": entry.value,
                    "marker_shape": (
                        "triangle_down" if entry.marker_shape == "circle" else "circle"
                    ),
                }
                for entry in action.entries
            )
        else:
            raise RuntimeError(f"unsupported point-marker comparison {focal_parameters!r}")
        return SetPointMarkerMap.model_validate(payload)
    if isinstance(action, SetChartParameter):
        value = action.value
        if isinstance(value, bool):
            payload["value"] = not value
        elif isinstance(value, int):
            payload["value"] = value + 3
        elif isinstance(value, float):
            payload["value"] = value + 1.0
        else:
            payload["value"] = _alternate_text(action.parameter, value)
        return SetChartParameter.model_validate(payload)
    if isinstance(action, SetAxis) and "bounds" in focal_parameters:
        assert action.minimum is not None and action.maximum is not None
        span = action.maximum - action.minimum
        payload["minimum"] = action.minimum + span * 0.15
        payload["maximum"] = action.maximum - span * 0.1
        return SetAxis.model_validate(payload)
    if isinstance(action, SetColorMap) and {"minimum", "maximum"} <= set(
        focal_parameters
    ):
        assert action.minimum is not None and action.maximum is not None
        span = action.maximum - action.minimum
        payload["minimum"] = action.minimum + span * 0.12
        payload["maximum"] = action.maximum - span * 0.08
        return SetColorMap.model_validate(payload)
    if isinstance(action, SetColorMap) and "midpoint" in focal_parameters:
        assert action.minimum is not None and action.maximum is not None
        payload["midpoint"] = action.minimum + (action.maximum - action.minimum) * 0.68
        return SetColorMap.model_validate(payload)
    for parameter in focal_parameters:
        value = payload[parameter]
        if isinstance(value, bool):
            payload[parameter] = not value
        elif isinstance(value, (int, float)):
            payload[parameter] = _alternate_number(parameter, value)
        elif isinstance(value, str):
            payload[parameter] = _alternate_text(parameter, value)
        else:
            raise RuntimeError(
                f"no alternate value for {action.operation}.{parameter}={value!r}"
            )
    return type(action).model_validate(payload)


def _isolated_action(
    action: PlotEngineAction,
    focal_parameters: tuple[str, ...],
    dependency_parameters: tuple[str, ...],
) -> PlotEngineAction:
    payload = action.model_dump(mode="python")
    metadata = {name: payload[name] for name in _ACTION_METADATA if name in payload}
    metadata["action_id"] = (
        f"action:isolated-{str(metadata['target']).partition(':')[2].replace('.', '-')}-"
        f"{'-'.join(focal_parameters).replace('_', '-')}"
    )
    metadata["expected_plot_version"] = 1
    if isinstance(action, SetPointMarkerMap):
        return action.model_copy(
            update={
                "action_id": metadata["action_id"],
                "expected_plot_version": 1,
            }
        )
    if isinstance(action, SetAxis) and "bounds" in focal_parameters:
        metadata["minimum"] = action.minimum
        metadata["maximum"] = action.maximum
    else:
        for parameter in focal_parameters:
            metadata[parameter] = _isolated_value(action, parameter)
        for parameter in dependency_parameters:
            metadata[parameter] = _dependency_value(action, parameter)
    if isinstance(action, SetColorMap) and "midpoint" in focal_parameters:
        assert action.minimum is not None and action.maximum is not None
        metadata["midpoint"] = action.minimum + (action.maximum - action.minimum) * 0.35
    return type(action).model_validate(metadata)


def isolated_edit_cases(
    case: ReleaseCase,
    readback: EngineReadback,
) -> tuple[IsolatedEditCase, ...]:
    """Enumerate every declared edit parameter without unrelated edits.

    Dependencies are explicit (for example a colorbar title needs a visible
    colorbar) and are kept separate from the focal parameter in the coverage
    ledger.  Bounds are atomic pairs because both public action schemas reject
    half-open ranges.
    """

    representative = representative_edit_actions(case, readback)
    profile = next(
        profile for profile in ENGINE_PROFILES if str(profile.profile_id) == case.profile_id
    )
    catalog = EngineCatalog(ENGINE_PROFILES)
    result: list[IsolatedEditCase] = []
    for capability in profile.capabilities:
        if capability.operation in {"create_plot", "bind_fields", "export_plot"}:
            continue
        candidates = tuple(
            action for action in representative if action.operation == capability.operation
        )
        if capability.operation == "set_chart_parameter":
            for action in candidates:
                assert isinstance(action, SetChartParameter)
                isolated_chart = action.model_copy(update={"expected_plot_version": 1})
                catalog.validate_action(profile, isolated_chart)
                result.append(
                    IsolatedEditCase(
                        profile_id=case.profile_id,
                        operation=capability.operation,
                        focal_parameters=(action.parameter,),
                        dependency_parameters=(),
                        setup_actions=(),
                        action=isolated_chart,
                        comparison_action=_comparison_action(
                            isolated_chart,
                            (action.parameter,),
                        ),
                        comparison_mode="pixel_ab",
                        evidence_reason=None,
                    )
                )
            continue
        parameters = tuple(capability.parameters)
        for parameter in parameters:
            if parameter == "maximum" and "minimum" in parameters:
                continue
            focal = (
                ("minimum", "maximum")
                if parameter == "minimum" and "maximum" in parameters
                else (parameter,)
            )
            matching = tuple(
                action
                for action in candidates
                if parameter in action_parameter_names(action)
            )
            if len(matching) != 1:
                raise RuntimeError(
                    f"{case.profile_id} {capability.operation}.{parameter} has "
                    f"{len(matching)} representatives"
                )
            representative_action = matching[0]
            dependencies = tuple(
                item
                for item in _isolated_dependencies(representative_action, parameter)
                if item not in focal
            )
            isolated_action = _isolated_action(representative_action, focal, dependencies)
            setup_actions: tuple[PlotEngineAction, ...] = ()
            if isinstance(isolated_action, AddCallout):
                reference_action = next(
                    item
                    for item in representative
                    if isinstance(item, AddReferenceLine)
                    and item.reference_line_id == isolated_action.target
                ).model_copy(update={"expected_plot_version": 1})
                isolated_action = isolated_action.model_copy(update={"expected_plot_version": 2})
                setup_actions = (reference_action,)
            comparison_action = _comparison_action(isolated_action, focal)
            catalog.validate_action(profile, isolated_action)
            catalog.validate_action(profile, comparison_action)
            observed = action_parameter_names(isolated_action)
            if observed != frozenset((*focal, *dependencies)):
                raise RuntimeError(
                    f"{case.profile_id} {capability.operation} {focal} isolated "
                    f"unexpected parameters {sorted(observed)}"
                )
            comparison_mode, evidence_reason = _comparison_evidence(
                case,
                readback,
                capability.operation,
                focal,
            )
            result.append(
                IsolatedEditCase(
                    profile_id=case.profile_id,
                    operation=capability.operation,
                    focal_parameters=focal,
                    dependency_parameters=dependencies,
                    setup_actions=setup_actions,
                    action=isolated_action,
                    comparison_action=comparison_action,
                    comparison_mode=comparison_mode,
                    evidence_reason=evidence_reason,
                )
            )
    return tuple(result)


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
    actions.append(
        SetCanvas(
            action_id=f"action:release-{case.profile_id.lower()}-canvas",
            target=case.document.plot_id,
            expected_plot_version=len(actions) + 1,
            width_mm=180,
            height_mm=100,
            aspect_ratio=1.8,
        )
    )
    profile = next(
        profile for profile in ENGINE_PROFILES if str(profile.profile_id) == case.profile_id
    )
    operation_names = {item.operation for item in profile.capabilities}
    all_series_actions = _series_actions(
        case,
        readback,
        expected_version=len(actions) + 1,
    )
    deferred_visibility = tuple(
        action
        for action in all_series_actions
        if action_parameter_names(action) == frozenset(("visible",))
    )
    actions.extend(
        action
        for action in all_series_actions
        if action_parameter_names(action) != frozenset(("visible",))
    )
    if "set_point_marker_map" in operation_names:
        marker_field = next(
            column
            for column in case.view.columns
            if str(column.field.field_id).endswith("-marker-class")
        )
        actions.append(
            SetPointMarkerMap(
                action_id=f"action:release-{case.profile_id.lower()}-point-marker-map",
                target=_target(readback, "series"),
                expected_plot_version=len(actions) + 1,
                field_id=marker_field.field.field_id,
                entries=(
                    PointMarkerMapEntry(value="measured", marker_shape="circle"),
                    PointMarkerMapEntry(value="derived", marker_shape="triangle_down"),
                ),
            )
        )
    if "set_observation_overlay" in operation_names:
        token = str(case.document.plot_id).removeprefix("plot:")
        actions.append(
            SetObservationOverlay(
                action_id=f"action:release-{case.profile_id.lower()}-observation-overlay",
                target=f"observation_overlay:{token}.raw",
                expected_plot_version=len(actions) + 1,
                visible=True,
                jitter_fraction=0.2,
                marker_shape="diamond",
                marker_size_pt=5,
                marker_interior="solid",
                marker_fill_color="#F2F4F7",
                marker_stroke_color="#344054",
                marker_opacity=0.75,
            )
        )
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
    if "add_reference_line" in operation_names:
        reference_line = _reference_line_action(
            case,
            readback,
            expected_version=len(actions) + 1,
        )
        actions.append(reference_line)
        if "add_callout" in operation_names:
            actions.append(
                _callout_action(
                    case,
                    reference_line,
                    expected_version=len(actions) + 1,
                )
            )
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
    for deferred_action in deferred_visibility:
        actions.append(
            deferred_action.model_copy(update={"expected_plot_version": len(actions) + 1})
        )
    catalog = EngineCatalog(ENGINE_PROFILES)
    for planned_action in actions:
        catalog.validate_action(profile, planned_action)
    expected = {
        capability.operation: frozenset(capability.parameters)
        for capability in profile.capabilities
        if capability.operation
        not in {"create_plot", "bind_fields", "export_plot"}
    }
    observed: dict[str, set[str]] = {}
    for planned_action in actions:
        observed.setdefault(planned_action.operation, set()).update(
            action_parameter_names(planned_action)
        )
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

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
    if "line_stroke_color" in parameters:
        return SetSeriesStyle(
            action_id=action_id,
            target=target,
            expected_plot_version=expected_version,
            line_stroke_color="#B42318",
            line_width_pt=2.25 if "line_width_pt" in parameters else None,
            line_style="dash" if "line_style" in parameters else None,
        )
    if "marker_fill_color" in parameters:
        return SetSeriesStyle(
            action_id=action_id,
            target=target,
            expected_plot_version=expected_version,
            marker_shape="diamond" if "marker_shape" in parameters else None,
            marker_size_pt=8 if "marker_size_pt" in parameters else None,
            marker_fill_color="#B42318",
            marker_stroke_color=("#7A1F18" if "marker_stroke_color" in parameters else None),
        )
    if "fill_color" in parameters:
        return SetSeriesStyle(
            action_id=action_id,
            target=target,
            expected_plot_version=expected_version,
            fill_color="#7EA6D8",
            fill_opacity=0.75 if "fill_opacity" in parameters else None,
            fill_stroke_color=("#4F78A8" if "fill_stroke_color" in parameters else None),
        )
    return SetSeriesStyle(
        action_id=action_id,
        target=target,
        expected_plot_version=expected_version,
        visible=True,
    )


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
        )
    ]
    actions.append(_axis_action(case, readback, expected_version=len(actions) + 1))
    actions.append(_series_action(case, readback, expected_version=len(actions) + 1))
    profile = next(
        profile for profile in ENGINE_PROFILES if str(profile.profile_id) == case.profile_id
    )
    if any(item.operation == "set_legend" for item in profile.capabilities):
        actions.append(
            SetLegend(
                action_id=f"action:release-{case.profile_id.lower()}-legend",
                target=_target(readback, "legend"),
                expected_plot_version=len(actions) + 1,
                visible=True,
                columns=1,
                title=f"{case.profile_id} legend",
            )
        )
    catalog = EngineCatalog(ENGINE_PROFILES)
    for action in actions:
        catalog.validate_action(profile, action)
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

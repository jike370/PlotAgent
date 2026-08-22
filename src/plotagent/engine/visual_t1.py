"""Closed, renderer-neutral T1 visual action vocabulary."""

from __future__ import annotations

from plotagent.contracts.canonical import canonical_hash
from plotagent.engine.contracts import (
    AddAnnotation,
    BindFields,
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
from plotagent.engine.ports import EngineReadback

VISUAL_ACTION_TYPES = (
    SetTitle,
    SetAxis,
    SetSeriesStyle,
    SetLegend,
    SetColorMap,
    SetErrorStyle,
    SetDataLabels,
    AddAnnotation,
)
DATA_DERIVED_VISUAL_TYPES = (SetSeriesStyle, SetColorMap, SetErrorStyle, SetDataLabels)


def _belongs_to_plot(target: str, plot_target: str) -> bool:
    """Match a child semantic ID to the complete plot ID, including dots."""

    plot_token = plot_target.removeprefix("plot:")
    return target.partition(":")[2].startswith(plot_token + ".")


def _with_colorbar_visibility(action: SetColorMap, visible: bool) -> SetColorMap:
    """Normalize the overlapping color-scale visibility edit.

    ``SetChartParameter(color_scale_visible=...)`` and
    ``SetColorMap(colorbar_visible=...)`` intentionally expose the same user
    state through structural and visual vocabularies.  Structural renderers run
    before the shared visual pass, so the shared pass must carry the same final
    value rather than replaying an earlier one.  Other colormap properties stay
    latent while hidden and are applied if a later action shows the scale.
    """

    payload = action.model_dump(mode="python")
    payload["colorbar_visible"] = visible
    return SetColorMap.model_validate(payload)


def _supersede_colorbar_visibility(
    visual: list[PlotEngineAction], chart_action: SetChartParameter
) -> list[PlotEngineAction]:
    if chart_action.parameter != "color_scale_visible":
        return visual
    if not isinstance(chart_action.value, bool):
        raise ValueError("color_scale_visible must be boolean")
    normalized: list[PlotEngineAction] = []
    for item in visual:
        if (
            isinstance(item, SetColorMap)
            and item.colorbar_visible is not None
            and _belongs_to_plot(item.target, chart_action.target)
        ):
            normalized.append(_with_colorbar_visibility(item, chart_action.value))
        else:
            normalized.append(item)
    return normalized


def split_visual_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[tuple[PlotEngineAction, ...], tuple[PlotEngineAction, ...]]:
    structural: list[PlotEngineAction] = []
    visual: list[PlotEngineAction] = []
    for action in actions:
        if isinstance(action, BindFields):
            structural.append(action)
            visual = [item for item in visual if not isinstance(item, DATA_DERIVED_VISUAL_TYPES)]
        elif isinstance(action, VISUAL_ACTION_TYPES):
            visual.append(action)
        else:
            structural.append(action)
            if isinstance(action, SetChartParameter):
                visual = _supersede_colorbar_visibility(visual, action)
    return tuple(structural), tuple(visual)


def effective_visual_actions(
    actions: tuple[PlotEngineAction, ...],
) -> tuple[PlotEngineAction, ...]:
    """Collapse cumulative state edits property-by-property.

    Applying every historical value is normally harmless for persistent native
    objects, but it is incorrect for state whose temporary value removes an
    object (for example a hidden Matplotlib colorbar).  Both backends therefore
    consume the same final state per action type and target.  Annotations remain
    independent append-only objects.
    """

    stateful = (
        SetTitle,
        SetAxis,
        SetSeriesStyle,
        SetLegend,
        SetColorMap,
        SetErrorStyle,
        SetDataLabels,
    )
    merged: dict[tuple[type[PlotEngineAction], str], PlotEngineAction] = {}
    last_positions: dict[tuple[type[PlotEngineAction], str], int] = {}
    for index, action in enumerate(actions):
        if not isinstance(action, stateful):
            continue
        key = (type(action), action.target)
        previous = merged.get(key)
        merged[key] = (
            action
            if previous is None
            else previous.model_copy(update=action.model_dump(exclude_none=True))
        )
        last_positions[key] = index

    result: list[PlotEngineAction] = []
    for index, action in enumerate(actions):
        if not isinstance(action, stateful):
            result.append(action)
            continue
        key = (type(action), action.target)
        if last_positions[key] == index:
            result.append(merged[key])
    return tuple(result)


def visual_style_hash(readback: EngineReadback, actions: tuple[PlotEngineAction, ...]) -> str:
    return canonical_hash(
        {
            "profile_style_hash": readback.style_hash,
            "t1_visual_actions": [action.model_dump(mode="json") for action in actions],
        }
    )
